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

def _sides(positions: List[Dict[str, Any]], partial_weight: float) -> Optional[tuple]:
    """(지지 점수, 반대 점수). 지지 = (찬성 + w·부분찬성)/n, 반대 = 반대/n. 입장 없으면 None."""
    stated = [p for p in positions if p["stance"] != "no_position"]
    if not stated:
        return None
    n = len(stated)
    support = (sum(p["stance"] == "agree" for p in stated)
               + partial_weight * sum(p["stance"] == "partially_agree" for p in stated)) / n
    oppose = sum(p["stance"] == "disagree" for p in stated) / n
    return support, oppose


def agreement(positions: List[Dict[str, Any]], partial_weight: float = 0.7) -> Optional[float]:
    """입장 분포의 수렴도 = max(지지 점수, 반대 점수). 입장을 밝힌 참가자가 2명 미만이면 None.

    부분 찬성은 지지 쪽에만 w만큼 기여한다 (반대와 부분 찬성이 맞서면 합의로 보지 않음).
    """
    if sum(p["stance"] != "no_position" for p in positions) < 2:
        return None
    return round(max(_sides(positions, partial_weight)), 4)


def direction(positions: List[Dict[str, Any]], partial_weight: float = 0.7) -> Optional[str]:
    """수렴 방향: support(명제 지지) | oppose(명제 반대) | split"""
    sides = _sides(positions, partial_weight)
    if sides is None:
        return None
    support, oppose = sides
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


def score_issues(issues: List[Dict[str, Any]], agreed_threshold: float,
                 partial_threshold: float, partial_weight: float = 0.7) -> Dict[str, Any]:
    """쟁점별 종합/AI/사람 수렴도와 라벨, 토론 전체 점수를 계산해 issues에 기록하고 요약을 반환"""
    overall_pairs, ai_pairs, human_pairs = [], [], []
    for issue in issues:
        positions = issue["positions"]
        ai = [p for p in positions if p["participant_type"] == "ai"]
        human = [p for p in positions if p["participant_type"] == "human"]
        stated = lambda ps: sum(p["stance"] != "no_position" for p in ps)  # noqa: E731

        issue["scores"] = {"overall": agreement(positions, partial_weight), "ai": agreement(ai, partial_weight),
                           "human": agreement(human, partial_weight)}
        issue["label"] = label_for(issue["scores"]["overall"], agreed_threshold, partial_threshold)
        issue["direction"] = direction(positions, partial_weight)

        overall_pairs.append((issue["scores"]["overall"], stated(positions)))
        ai_pairs.append((issue["scores"]["ai"], stated(ai)))
        human_pairs.append((issue["scores"]["human"], stated(human)))

    scores = {"overall": _weighted_mean(overall_pairs), "ai": _weighted_mean(ai_pairs),
              "human": _weighted_mean(human_pairs)}
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
            stances = "; ".join(f"{p['participant']}: {p['stance']} — {p['claim']}" for p in issue["positions"])
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


def _pct(score: Optional[float]) -> str:
    return "-" if score is None else f"{round(score * 100)}%"


def to_markdown(report: Dict[str, Any]) -> str:
    """보고서 본문(JSON)을 마크다운 문서로 변환"""
    scores = report["scores"]
    narrative = report.get("narrative", {})
    lines = [
        f"# 종합보고서: {report['topic']}",
        "",
        f"- 합의 정도: 종합 {_pct(scores['overall'])} ({LABEL_TEXT.get(report.get('label'), '-')})"
        f" · AI {_pct(scores['ai'])} · 사람 {_pct(scores['human'])}",
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
                lines.append(f"- **{p['participant']}** ({STANCE_TEXT[p['stance']]}): {p['claim']}")
            lines.append("")
    for title, key in (("열린 질문", "open_questions"), ("제언", "recommendations")):
        items = narrative.get(key) or []
        lines += [f"## {title}", ""] + [f"- {item}" for item in items] + ([""] if items else ["- 없음", ""])
    lines.append(f"> 합의 정도는 쟁점별 수렴도의 가중 평균입니다. 수렴도 = max(지지, 반대), "
                 f"지지 = (찬성 + {report.get('partial_weight', 0.7)}×부분찬성)/입장 수, 반대 = 반대/입장 수. "
                 f"합의 ≥ {_pct(report['thresholds']['agreed'])}, 부분 합의 ≥ {_pct(report['thresholds']['partial'])}. "
                 f"입장을 밝힌 참가자가 2명 미만인 쟁점은 판단 보류로 점수에서 제외합니다.")
    return "\n".join(lines) + "\n"
