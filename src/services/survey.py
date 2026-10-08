"""
사전·사후 설문 - 토론 전후로 참가자에게 같은 문항을 독립 호출로 묻는다

발언 중 분석이 추정한 입장(x)과 별개의 표준 측정이다. 인간 공론조사의 사전·사후 설문과 같은 형식
(고정 문항, 리커트 척도, 이유 한 문장)이라 결과를 직접 비교할 수 있다. 같은 문항을 사람 참가자에게도 쓴다.

문항 유형
- likert: scale_min ~ scale 정수 점수 (예: 1~7, 0~10)
- choice: 보기에서 고르기 (multi=True면 여러 개). correct가 있으면 정답 여부를 채점한다(참가자에게는 보이지 않음).

초기값 심기(seed): 참가자별로 사전 응답을 지정값으로 기록한다. 그 문항은 묻지 않고(source = seeded),
같은 값을 참가자의 시스템 프롬프트에 "토론 전 내 응답"으로 넣는다(initial_position_text).
"""
import logging
from typing import Any, Dict, List, Literal, Optional, Union

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from config.config_loader import config_loader
from src.utils.llm_provider import structured_output

logger = logging.getLogger(__name__)

PRE, POST = "pre", "post"

SeedValue = Union[int, List[str]]


class SurveyItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(..., min_length=1, max_length=30, pattern=r"^[A-Za-z0-9_]+$")
    text: str = Field(..., min_length=1, max_length=2000)
    type: Literal["likert", "choice"] = "likert"
    options: Optional[List[str]] = Field(None, description="choice 문항의 보기")
    multi: bool = Field(False, description="choice 문항에서 여러 개 선택 허용")
    correct: Optional[List[str]] = Field(None, description="정답 보기 (채점용, 참가자에게 보이지 않음)")

    @model_validator(mode="after")
    def check_choice(self):
        if self.type == "choice":
            if not self.options or len(self.options) < 2 or len(set(self.options)) != len(self.options):
                raise ValueError(f"choice item {self.id} needs at least 2 distinct options")
            if self.correct is not None:
                if not set(self.correct) <= set(self.options) or not self.correct:
                    raise ValueError(f"correct answer of {self.id} must be a non-empty subset of its options")
                if not self.multi and len(self.correct) != 1:
                    raise ValueError(f"single-choice item {self.id} must have exactly one correct option")
        elif self.options is not None or self.correct is not None:
            raise ValueError(f"likert item {self.id} cannot have options or correct")
        return self


class SurveyConfig(BaseModel):
    """설문 문항 (토론 생성 요청의 survey)"""
    model_config = ConfigDict(extra="forbid")
    items: List[SurveyItem] = Field(..., min_length=1, max_length=20)
    scale: int = Field(7, ge=2, le=11, description="리커트 최댓값 (매우 동의)")
    scale_min: Literal[0, 1] = Field(1, description="리커트 최솟값 (전혀 동의 안 함). 0~10 척도는 scale_min 0, scale 10")

    @field_validator("items")
    @classmethod
    def unique_ids(cls, items):
        ids = [i.id for i in items]
        if len(set(ids)) != len(ids):
            raise ValueError("survey item ids must be unique")
        return items

    @model_validator(mode="after")
    def check_range(self):
        if self.scale - self.scale_min < 2:
            raise ValueError("likert scale needs at least 3 points")
        return self

    def item(self, item_id: str) -> Optional[SurveyItem]:
        return next((i for i in self.items if i.id == item_id), None)


class SurveyAnswer(BaseModel):
    item_id: str
    score: Optional[int] = None
    choices: List[str] = Field(default_factory=list)
    reason: str = ""


class SurveyAnswers(BaseModel):
    answers: List[SurveyAnswer] = Field(default_factory=list)


# ---------- 문항별 형식 검사 ----------

def _norm(values: List[str]) -> List[str]:
    return [str(v).strip() for v in values if str(v).strip()]


def _match_options(values: List[str], options: List[str]) -> List[str]:
    """보기 이름을 대소문자 무시로 맞춘다 (예: 'a' → 'A')"""
    lookup = {o.lower(): o for o in options}
    return [lookup.get(v.lower(), v) for v in _norm(values)]


def value_problem(item: SurveyItem, survey: SurveyConfig, value: Any) -> Optional[str]:
    """값이 문항 형식에 맞지 않으면 그 이유 (초기값 검사와 응답 검사에 같이 쓴다)"""
    if item.type == "likert":
        if not isinstance(value, int) or isinstance(value, bool) or not survey.scale_min <= value <= survey.scale:
            return f"score for {item.id} must be an integer in {survey.scale_min}..{survey.scale}"
        return None
    if not isinstance(value, list) or not value:
        return f"choices for {item.id} must be a non-empty list"
    chosen = _match_options(value, item.options)
    unknown = [c for c in chosen if c not in item.options]
    if unknown:
        return f"unknown options {unknown} for {item.id}; options are {item.options}"
    if len(set(chosen)) != len(chosen):
        return f"duplicate options for {item.id}"
    if not item.multi and len(chosen) != 1:
        return f"choose exactly one option for {item.id}"
    return None


def validate_seed(survey: SurveyConfig, seed: Dict[str, SeedValue]) -> List[str]:
    errors = []
    for item_id, value in seed.items():
        item = survey.item(item_id)
        if item is None:
            errors.append(f"seed for unknown survey item {item_id}")
        elif (problem := value_problem(item, survey, value)):
            errors.append(problem)
    return errors


def _record(item: SurveyItem, survey: SurveyConfig, value: Any, reason: str, source: str) -> Dict[str, Any]:
    """저장 형식 1행: likert는 score, choice는 choices와 정답 여부"""
    row = {"item_id": item.id, "score": None, "choices": None, "correct": None, "reason": reason,
           "scale": survey.scale, "scale_min": survey.scale_min, "source": source}
    if value is None:
        return row
    if item.type == "likert":
        row["score"] = value
    else:
        chosen = sorted(_match_options(value, item.options), key=item.options.index)
        row["choices"] = chosen
        if item.correct is not None:
            row["correct"] = set(chosen) == set(item.correct)
    return row


def _format_item(item: SurveyItem, survey: SurveyConfig) -> str:
    prompts = config_loader.prompts
    if item.type == "likert":
        how = prompts.render("survey.format_likert", low=survey.scale_min, high=survey.scale)
    else:
        how = prompts.render("survey.format_multi" if item.multi else "survey.format_single",
                             options=", ".join(item.options))
    return f"[{item.id}] {item.text}\n    {how}"


def initial_position_text(survey: SurveyConfig, seed: Dict[str, SeedValue]) -> str:
    """시스템 프롬프트에 넣을 '토론 전 내 응답' (심은 초기값)"""
    prompts = config_loader.prompts
    lines = []
    for item in survey.items:
        if item.id not in seed:
            continue
        value = seed[item.id]
        if item.type == "likert":
            answer = prompts.render("survey.seed_likert", value=value, low=survey.scale_min, high=survey.scale)
        else:
            answer = prompts.render("survey.seed_choice", choices=", ".join(_match_options(value, item.options)))
        lines.append(f"- {item.text}\n  {answer}")
    return prompts.render("agent.initial_position_block", answers="\n".join(lines)) if lines else ""


async def run_survey(agent, survey: SurveyConfig, phase: str, transcript: str = "",
                     seeded: Optional[Dict[str, SeedValue]] = None, max_attempts: Optional[int] = None,
                     prompt_key: Optional[str] = None) -> List[Dict[str, Any]]:
    """참가자 1명의 설문 응답. 형식 오류가 있으면 오류를 알려 주고 다시 묻는다.
    심은 문항(seeded)은 묻지 않고 지정값으로 기록한다. 끝까지 답하지 않은 문항은 값을 비워 둔다(조용히 채우지 않음)."""
    prompts = config_loader.prompts
    settings = config_loader.config.survey  # 기록 길이·시도 횟수 (config.yaml survey)
    max_attempts = max_attempts or settings.max_attempts
    seeded = seeded or {}
    asked = [i for i in survey.items if i.id not in seeded]
    valid: Dict[str, SurveyAnswer] = {}
    if asked:
        items = "\n".join(_format_item(i, survey) for i in asked)
        user = prompts.render(f"survey.{prompt_key or phase}", items=items,
                              transcript=transcript[-settings.transcript_chars:] or "(none)")
        messages: List[Any] = [SystemMessage(content=agent._build_system_prompt()), HumanMessage(content=user)]
        asked_ids = {i.id for i in asked}
        for attempt in range(max_attempts):
            try:
                result: SurveyAnswers = await structured_output(agent.llm, SurveyAnswers).ainvoke(messages)
            except Exception as e:
                logger.warning("Survey %s failed for %s (attempt %d): %s", phase, agent.persona.name, attempt + 1, e)
                continue
            errors = []
            for a in result.answers:
                item = survey.item(a.item_id)
                if item is None or a.item_id not in asked_ids:
                    errors.append(f"unknown item id {a.item_id}")
                    continue
                value = a.score if item.type == "likert" else a.choices
                problem = value_problem(item, survey, value)
                if problem:
                    errors.append(problem)
                else:
                    valid[a.item_id] = a
            errors += [f"missing answer for {i}" for i in sorted(asked_ids - valid.keys())]
            if not errors:
                break
            messages = messages + [HumanMessage(content=prompts.render("survey.retry", errors="; ".join(errors)))]

    rows = []
    for item in survey.items:
        if item.id in seeded:
            rows.append(_record(item, survey, seeded[item.id], "", "seeded"))
        elif item.id in valid:
            a = valid[item.id]
            rows.append(_record(item, survey, a.score if item.type == "likert" else a.choices,
                                a.reason.strip(), "answered"))
        else:
            rows.append(_record(item, survey, None, "", "missing"))
    return rows


def transcript_text(messages) -> str:
    """사후 설문에 넣을 토론 기록 (화자: 발언)"""
    return "\n\n".join(f"{m.agent_name}: {m.content}" for m in messages if m.content)
