"""
사전·사후 설문 - 토론 전후로 참가자에게 같은 문항을 독립 호출로 묻는다

발언 중 분석이 추정한 입장(x)과 별개의 표준 측정이다. 인간 공론조사의 사전·사후 설문과 같은 형식
(고정 문항, 리커트 척도, 이유 한 문장)이라 결과를 직접 비교할 수 있다. 같은 문항을 사람 참가자에게도 쓴다.
"""
import logging
from typing import Any, Dict, List

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, ConfigDict, Field, field_validator

from config.config_loader import config_loader
from src.utils.llm_provider import structured_output

logger = logging.getLogger(__name__)

PRE, POST = "pre", "post"
TRANSCRIPT_CHARS = 15000  # 사후 설문에 넣는 토론 기록 길이 (끝에서부터)


class SurveyItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(..., min_length=1, max_length=30, pattern=r"^[A-Za-z0-9_]+$")
    text: str = Field(..., min_length=1, max_length=500)


class SurveyConfig(BaseModel):
    """설문 문항 (토론 생성 요청의 survey)"""
    model_config = ConfigDict(extra="forbid")
    items: List[SurveyItem] = Field(..., min_length=1, max_length=20)
    scale: int = Field(7, ge=3, le=11, description="리커트 척도 점수 수 (1 = 전혀 동의 안 함, scale = 매우 동의)")

    @field_validator("items")
    @classmethod
    def unique_ids(cls, items):
        ids = [i.id for i in items]
        if len(set(ids)) != len(ids):
            raise ValueError("survey item ids must be unique")
        return items


class SurveyAnswer(BaseModel):
    item_id: str
    score: int
    reason: str = ""


class SurveyAnswers(BaseModel):
    answers: List[SurveyAnswer] = Field(default_factory=list)


def _validate(answers: List[SurveyAnswer], survey: SurveyConfig) -> List[str]:
    ids = {i.id for i in survey.items}
    errors = [f"unknown item id {a.item_id}" for a in answers if a.item_id not in ids]
    errors += [f"score {a.score} for {a.item_id} is outside 1..{survey.scale}"
               for a in answers if not 1 <= a.score <= survey.scale]
    answered = {a.item_id for a in answers}
    errors += [f"missing answer for {i}" for i in ids - answered]
    return errors


async def run_survey(agent, survey: SurveyConfig, phase: str, transcript: str = "",
                     max_attempts: int = 2) -> List[Dict[str, Any]]:
    """참가자 1명의 설문 응답. 형식 오류가 있으면 오류를 알려 주고 다시 묻는다.
    끝까지 답하지 않은 문항은 score None으로 남긴다(조용히 채우지 않음)."""
    prompts = config_loader.prompts
    items = "\n".join(f"[{i.id}] {i.text}" for i in survey.items)
    user = prompts.render(f"survey.{phase}", items=items, scale=survey.scale,
                          transcript=transcript[-TRANSCRIPT_CHARS:] or "(none)")
    messages: List[Any] = [SystemMessage(content=agent._build_system_prompt()), HumanMessage(content=user)]
    valid: Dict[str, SurveyAnswer] = {}
    for attempt in range(max_attempts):
        try:
            result: SurveyAnswers = await structured_output(agent.llm, SurveyAnswers).ainvoke(messages)
        except Exception as e:
            logger.warning("Survey %s failed for %s (attempt %d): %s", phase, agent.persona.name, attempt + 1, e)
            continue
        for a in result.answers:
            if a.item_id in {i.id for i in survey.items} and 1 <= a.score <= survey.scale:
                valid[a.item_id] = a
        errors = _validate(result.answers, survey)
        if not errors:
            break
        messages = messages + [HumanMessage(content=prompts.render("survey.retry", errors="; ".join(errors)))]
    return [{"item_id": i.id, "score": valid[i.id].score if i.id in valid else None,
             "reason": valid[i.id].reason.strip() if i.id in valid else "", "scale": survey.scale}
            for i in survey.items]


def transcript_text(messages) -> str:
    """사후 설문에 넣을 토론 기록 (화자: 발언)"""
    return "\n\n".join(f"{m.agent_name}: {m.content}" for m in messages if m.content)

