"""
토론 종합보고서 생성

1) LLM 구조화 출력으로 쟁점(명제)과 참가자별 입장을 추출하고 검증·재시도한다.
2) 합의 정도는 LLM이 아니라 코드가 입장 분포로 계산한다 (종합 / AI / 사람 점수).
3) LLM이 분류 결과를 바탕으로 요약·열린 질문·제언을 작성한다.
"""
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Literal, Optional

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from pydantic import BaseModel, Field, ValidationError

from config.config_loader import config_loader
from src.utils.language_detector import LanguageDetector

logger = logging.getLogger(__name__)

Stance = Literal["agree", "partially_agree", "disagree", "no_position"]
ParticipantType = Literal["ai", "human"]

LABEL_AGREED = "agreed"
LABEL_PARTIAL = "partial"
LABEL_DISAGREED = "disagreed"
LABEL_INSUFFICIENT = "insufficient"  # 입장을 밝힌 참가자가 2명 미만 → 합의 여부 판단 불가


# ---------- LLM 출력 스키마 ----------

class Position(BaseModel):
    participant: str = Field(description="Exact participant name")
    stance: Stance
    claim: str = Field(description="One sentence summary of this participant's view on the issue")
    evidence_seqs: List[int] = Field(default_factory=list, description="Transcript [seq] numbers")
    unsourced_specifics: bool = Field(False, description="Relies on statistics/named cases/anecdotes without a verifiable source")


class Issue(BaseModel):
    title: str = Field(description="The issue stated as a debatable proposition")
    summary: str = Field(description="One or two sentences on what was argued")
    positions: List[Position]


class IssueMap(BaseModel):
    issues: List[Issue]


class Narrative(BaseModel):
    executive_summary: str
    open_questions: List[str] = Field(default_factory=list)
    recommendations: List[str] = Field(default_factory=list)


# ---------- 입력 ----------

@dataclass
class TranscriptMessage:
    seq: int
    speaker: str
    speaker_type: str  # ai | moderator | human
    content: str


class ReportGenerationError(Exception):
    pass


# ---------- 점수 계산 (결정적) ----------
# 쌍별 일치도: 입장을 수치화(찬성 1, 부분찬성 w, 반대 0)하고 두 참가자의 일치도 = 1 - |차이|.
# 종합 = 모든 쌍, AI간 = AI끼리, 인간간 = 사람끼리, AI-인간간 = AI×사람 쌍의 평균.

def _stated(positions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [p for p in positions if p["stance"] != "no_position"]


def _value(stance: str, partial_weight: float) -> float:
    return {"agree": 1.0, "partially_agree": partial_weight, "disagree": 0.0}[stance]


def _pairs_within(positions: List[Dict[str, Any]]) -> List[tuple]:
    stated = _stated(positions)
    return [(stated[i], stated[j]) for i in range(len(stated)) for j in range(i + 1, len(stated))]


def _pairs_between(group_a: List[Dict[str, Any]], group_b: List[Dict[str, Any]]) -> List[tuple]:
    return [(a, b) for a in _stated(group_a) for b in _stated(group_b)]


def _pair_score(pairs: List[tuple], partial_weight: float) -> Optional[float]:
    """쌍 목록의 평균 일치도 (쌍이 없으면 None)"""
    if not pairs:
        return None
    total = sum(1 - abs(_value(a["stance"], partial_weight) - _value(b["stance"], partial_weight))
                for a, b in pairs)
    return round(total / len(pairs), 4)


def agreement(positions: List[Dict[str, Any]], partial_weight: float = 0.7) -> Optional[float]:
    """같은 집단 안 참가자 쌍의 평균 일치도. 입장을 밝힌 참가자가 2명 미만이면 None."""
    return _pair_score(_pairs_within(positions), partial_weight)


def cross_agreement(group_a: List[Dict[str, Any]], group_b: List[Dict[str, Any]],
                    partial_weight: float = 0.7) -> Optional[float]:
    """두 집단 사이(예: AI × 사람) 쌍의 평균 일치도. 한쪽이라도 입장이 없으면 None."""
    return _pair_score(_pairs_between(group_a, group_b), partial_weight)


def direction(positions: List[Dict[str, Any]]) -> Optional[str]:
    """입장 쏠림 방향: support(명제 지지 쪽이 많음) | oppose | split"""
    stated = _stated(positions)
    if not stated:
        return None
    support = sum(p["stance"] in ("agree", "partially_agree") for p in stated)
    oppose = sum(p["stance"] == "disagree" for p in stated)
    if support > oppose:
        return "support"
    if oppose > support:
        return "oppose"
    return "split"


def label_for(score: Optional[float], agreed: float, partial: float) -> str:
    if score is None:
        return LABEL_INSUFFICIENT
    if score >= agreed:
        return LABEL_AGREED
    if score >= partial:
        return LABEL_PARTIAL
    return LABEL_DISAGREED


def _weighted_mean(pairs: List[tuple]) -> Optional[float]:
    """(점수, 가중치) 목록의 가중 평균. 점수 None은 제외."""
    valid = [(s, w) for s, w in pairs if s is not None and w > 0]
    total = sum(w for _, w in valid)
    return round(sum(s * w for s, w in valid) / total, 4) if total else None


SCORE_KEYS = ("overall", "ai", "human", "ai_human")


def score_issues(issues: List[Dict[str, Any]], agreed_threshold: float,
                 partial_threshold: float, partial_weight: float = 0.7) -> Dict[str, Any]:
    """쟁점별 종합/AI간/인간간/AI-인간간 일치도와 라벨을 issues에 기록하고, 쌍 개수로 가중 평균한 전체 점수를 반환"""
    weighted = {key: [] for key in SCORE_KEYS}
    for issue in issues:
        positions = issue["positions"]
        ai = [p for p in positions if p["participant_type"] == "ai"]
        human = [p for p in positions if p["participant_type"] == "human"]
        pair_sets = {
            "overall": _pairs_within(positions),
            "ai": _pairs_within(ai),
            "human": _pairs_within(human),        # 사람이 1명 이하면 쌍이 없어 None
            "ai_human": _pairs_between(ai, human),
        }
        issue["scores"] = {key: _pair_score(pairs, partial_weight) for key, pairs in pair_sets.items()}
        issue["label"] = label_for(issue["scores"]["overall"], agreed_threshold, partial_threshold)
        issue["direction"] = direction(positions)
        for key, pairs in pair_sets.items():
            weighted[key].append((issue["scores"][key], len(pairs)))

    scores = {key: _weighted_mean(values) for key, values in weighted.items()}
    return {
        "scores": scores,
        "label": label_for(scores["overall"], agreed_threshold, partial_threshold),
        "thresholds": {"agreed": agreed_threshold, "partial": partial_threshold},
        "partial_weight": partial_weight,
    }


# ---------- 생성기 ----------

class ConsensusReportGenerator:
    def __init__(self, llm: BaseChatModel, agreed_threshold: float = 0.8, partial_threshold: float = 0.6,
                 max_attempts: int = 3, partial_weight: float = 0.7):
        self.llm = llm
        self.agreed_threshold = agreed_threshold
        self.partial_threshold = partial_threshold
        self.max_attempts = max_attempts
        self.partial_weight = partial_weight

    async def generate(self, topic: str, transcript: List[TranscriptMessage],
                       participants: Dict[str, str], language: Optional[str] = None) -> Dict[str, Any]:
        """participants: 이름 → 'ai' | 'human'. 반환값은 JSON 직렬화 가능한 보고서 본문."""
        language = language or LanguageDetector.detect_language(topic)
        language_instruction = LanguageDetector.get_language_instruction(language)

        issue_map = await self._extract_issues(topic, transcript, participants, language_instruction)
        issues = [
            {
                "title": issue.title,
                "summary": issue.summary,
                "positions": [
                    {**p.model_dump(), "participant_type": participants[p.participant]}
                    for p in issue.positions
                ],
            }
            for issue in issue_map.issues
        ]
        summary = score_issues(issues, self.agreed_threshold, self.partial_threshold, self.partial_weight)
        narrative = await self._write_narrative(topic, issues, summary["scores"]["overall"], language_instruction)

        return {
            "topic": topic,
            "language": language,
            **summary,
            "issues": issues,
            "agreed": [i["title"] for i in issues if i["label"] == LABEL_AGREED],
            "partially_agreed": [i["title"] for i in issues if i["label"] == LABEL_PARTIAL],
            "disagreed": [i["title"] for i in issues if i["label"] == LABEL_DISAGREED],
            "insufficient": [i["title"] for i in issues if i["label"] == LABEL_INSUFFICIENT],
            "narrative": narrative.model_dump(),
            "participants": [{"name": n, "type": t} for n, t in participants.items()],
            "message_count": len(transcript),
        }

    async def _structured(self, schema, messages: List[Any], validate=None):
        """구조화 출력 + 검증. 실패하면 오류를 피드백해 재시도한다."""
        structured = self.llm.with_structured_output(schema)
        errors: List[str] = []
        for attempt in range(1, self.max_attempts + 1):
            try:
                result = await structured.ainvoke(messages)
                errors = validate(result) if validate else []
            except ValidationError as e:
                result, errors = None, [f"{'.'.join(map(str, err['loc']))}: {err['msg']}" for err in e.errors()]
            if not errors:
                return result
            logger.warning("Report %s output invalid (attempt %d): %s", schema.__name__, attempt, errors[:5])
            messages = messages + [
                AIMessage(content=result.model_dump_json() if result is not None else "(invalid output)"),
                HumanMessage(content=config_loader.prompts.render(
                    "report.retry_feedback", errors="\n".join(f"- {e}" for e in errors[:20]))),
            ]
        raise ReportGenerationError(f"{schema.__name__} invalid after {self.max_attempts} attempts: {errors[:5]}")

    async def _extract_issues(self, topic: str, transcript: List[TranscriptMessage],
                              participants: Dict[str, str], language_instruction: str) -> IssueMap:
        prompts = config_loader.prompts
        seqs = {m.seq for m in transcript}

        def validate(issue_map: IssueMap) -> List[str]:
            errors = []
            if not issue_map.issues:
                errors.append("issues: at least one issue is required")
            for i, issue in enumerate(issue_map.issues):
                for j, p in enumerate(issue.positions):
                    if p.participant not in participants:
                        errors.append(f"issues[{i}].positions[{j}].participant '{p.participant}' is not a listed participant")
                    unknown = [s for s in p.evidence_seqs if s not in seqs]
                    if unknown:
                        errors.append(f"issues[{i}].positions[{j}].evidence_seqs {unknown} not in transcript")
            return errors

        messages = [
            SystemMessage(content=prompts.render("report.issue_extraction.system",
                                                 language_instruction=language_instruction)),
            HumanMessage(content=prompts.render(
                "report.issue_extraction.user",
                topic=topic,
                participants="\n".join(f"- {name} — {kind}" for name, kind in participants.items()),
                transcript="\n".join(f"[{m.seq}] {m.speaker} ({m.speaker_type}): {m.content}" for m in transcript),
            )),
        ]
        return await self._structured(IssueMap, messages, validate)

    async def _write_narrative(self, topic: str, issues: List[Dict[str, Any]], overall_score: Optional[float],
                               language_instruction: str) -> Narrative:
        prompts = config_loader.prompts
        issue_lines = []
        for issue in issues:
            stances = "; ".join(
                f"{p['participant']}: {p['stance']}{' [unsourced]' if p.get('unsourced_specifics') else ''} — {p['claim']}"
                for p in issue["positions"])
            issue_lines.append(f"- [{issue['label']} {issue['scores']['overall']}] {issue['title']} | {stances}")
        messages = [
            SystemMessage(content=prompts.render("report.narrative.system", language_instruction=language_instruction)),
            HumanMessage(content=prompts.render("report.narrative.user", topic=topic,
                                                overall_score=overall_score, issues="\n".join(issue_lines))),
        ]
        return await self._structured(Narrative, messages)


# ---------- 마크다운 ----------

LABEL_TEXT = {LABEL_AGREED: "합의", LABEL_PARTIAL: "부분 합의", LABEL_DISAGREED: "이견",
              LABEL_INSUFFICIENT: "판단 보류"}
STANCE_TEXT = {"agree": "찬성", "partially_agree": "부분 찬성", "disagree": "반대", "no_position": "입장 없음"}
DIRECTION_TEXT = {"support": "지지 쪽", "oppose": "반대 쪽", "split": "양분"}


SCORE_LABELS = {"overall": "종합", "ai": "AI간", "human": "인간간", "ai_human": "AI-인간간"}


def score_line(report: Dict[str, Any]) -> str:
    """'종합 80% (합의) · AI간 85% · AI-인간간 70%' — 계산되지 않은 점수(예: 사람 1명의 인간간)는 생략"""
    scores = report["scores"]
    parts = [f"종합 {_pct(scores.get('overall'))} ({LABEL_TEXT.get(report.get('label'), '-')})"]
    parts += [f"{SCORE_LABELS[k]} {_pct(scores[k])}" for k in ("ai", "human", "ai_human") if scores.get(k) is not None]
    return " · ".join(parts)


def _pct(score: Optional[float]) -> str:
    return "-" if score is None else f"{round(score * 100)}%"


def to_markdown(report: Dict[str, Any]) -> str:
    """보고서 본문(JSON)을 마크다운 문서로 변환"""
    scores = report["scores"]
    narrative = report.get("narrative", {})
    lines = [
        f"# 종합보고서: {report['topic']}",
        "",
        f"- 합의 정도: {score_line(report)}",
        f"- 참가자: {', '.join(p['name'] + (' (사람)' if p['type'] == 'human' else '') for p in report['participants'])}",
        "",
        "## 요약",
        "",
        narrative.get("executive_summary", ""),
        "",
    ]
    for title, key in (("합의된 내용", LABEL_AGREED), ("부분 합의된 내용", LABEL_PARTIAL),
                       ("합의되지 않은 내용", LABEL_DISAGREED), ("판단 보류 (입장을 밝힌 참가자 1명 이하)", LABEL_INSUFFICIENT)):
        selected = [i for i in report["issues"] if i["label"] == key]
        if key == LABEL_INSUFFICIENT and not selected:
            continue
        lines += [f"## {title}", ""]
        if not selected:
            lines += ["- 없음", ""]
        for issue in selected:
            lines.append(f"### {issue['title']} — {_pct(issue['scores']['overall'])}, "
                         f"{DIRECTION_TEXT.get(issue['direction'], '-')}")
            lines += ["", issue["summary"], ""]
            for p in issue["positions"]:
                flag = " ⚠ 출처 없는 수치·사례" if p.get("unsourced_specifics") else ""
                lines.append(f"- **{p['participant']}** ({STANCE_TEXT[p['stance']]}): {p['claim']}{flag}")
            lines.append("")
    for title, key in (("열린 질문", "open_questions"), ("제언", "recommendations")):
        items = narrative.get(key) or []
        lines += [f"## {title}", ""] + [f"- {item}" for item in items] + ([""] if items else ["- 없음", ""])
    lines.append(f"> 합의 정도는 참가자 쌍의 평균 일치도입니다. 입장을 찬성 1, 부분찬성 {report.get('partial_weight', 0.7)}, "
                 f"반대 0으로 바꾸고 두 참가자의 일치도를 1 − |차이|로 계산합니다. 종합은 모든 쌍, AI간·인간간은 같은 집단 안의 쌍, "
                 f"AI-인간간은 AI와 사람 사이의 쌍을 쓰며 쟁점별 쌍 개수로 가중 평균합니다. "
                 f"합의 ≥ {_pct(report['thresholds']['agreed'])}, 부분 합의 ≥ {_pct(report['thresholds']['partial'])}. "
                 f"입장을 밝힌 참가자가 2명 미만인 쟁점은 판단 보류로 제외합니다.")
    return "\n".join(lines) + "\n"
