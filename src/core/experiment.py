"""
실험 조건 - 토론 1건의 엔진 설정을 바꾼다

전역 설정(config/discussion_config.py)은 그대로 두고, 토론마다 설정 사본을 만들어 엔진에 넘긴다.
그래서 조건이 다른 토론을 동시에 실행해도 서로 간섭하지 않는다.
알 수 없는 키는 거부한다(오타로 조건이 조용히 무시되지 않도록).
"""
from dataclasses import replace
from typing import Dict, List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field

from config.discussion_config import DiscussionConfig, get_config

ProviderName = Literal["openai", "claude", "gemini", "mistral"]

# 수용 범위를 입장 거리의 최대값(2.0)으로 두면 모든 화자가 수용 범위 안 → 순수 Friedkin-Johnsen
FULL_LATITUDE = 2.0


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ParticipantCondition(_Strict):
    """참가자(페르소나 이름)별 조건"""
    stubbornness: Optional[float] = Field(None, ge=0.0, le=1.0, description="비우면 성격 키워드로 정함")
    temperature: Optional[float] = Field(None, ge=0.0, le=1.5, description="발언 temperature")
    seed: Optional[Dict[str, Union[int, List[str]]]] = Field(
        None, description="심은 사전 설문 응답 {문항 id: 점수 또는 보기 목록}. 사전 설문을 묻지 않고 이 값으로 기록하고 프롬프트에 넣음")


class ModelRef(_Strict):
    provider: Optional[ProviderName] = None
    model: Optional[str] = Field(None, max_length=100)


class Mechanisms(_Strict):
    """진행 장치 on/off (기본은 모두 켬)"""
    analysis: bool = True             # 발언 분석(끄면 토론 상태·입장 동역학이 모두 없음)
    reply_obligation: bool = True     # 응답 의무
    stalemate_mediation: bool = True  # 교착 중재·제3안
    devils_advocate: bool = True      # 성급한 합의 시 반대 검토
    closing_round: bool = True        # 종결 라운드
    latitude: bool = True             # 수용·거부 범위 (끄면 거리와 무관하게 수용, 반발 없음)
    concession_shift: bool = True     # 양보에 따른 입장 이동 (끄면 기록만 함)


class Dynamics(_Strict):
    """입장 동역학 파라미터 (비우면 기본값, 의미는 docs/configuration.md)"""
    dynamics_step: Optional[float] = Field(None, ge=0.0, le=1.0)
    dynamics_anchor: Optional[float] = Field(None, ge=0.0, le=1.0)
    accept_wide: Optional[float] = Field(None, ge=0.0, le=2.0)
    accept_narrow: Optional[float] = Field(None, ge=0.0, le=2.0)
    noncommit_width: Optional[float] = Field(None, ge=0.0, le=2.0)
    noncommit_factor: Optional[float] = Field(None, ge=0.0, le=1.0)
    reject_factor: Optional[float] = Field(None, ge=0.0, le=1.0)
    threat_dampen: Optional[float] = Field(None, ge=0.0, le=1.0)
    boomerang_threshold: Optional[float] = Field(None, ge=0.0, le=1.0)
    boomerang_step: Optional[float] = Field(None, ge=0.0, le=1.0)
    concession_step: Optional[float] = Field(None, ge=0.0, le=1.0)
    concession_cap: Optional[float] = Field(None, ge=0.0, le=2.0)


class ExperimentConfig(_Strict):
    """토론 1건의 실험 조건. 비운 항목은 기본 설정을 쓴다."""
    label: Optional[str] = Field(None, max_length=100, description="조건 이름 (분석 시 구분용)")
    batch: Optional[str] = Field(None, max_length=100, description="배치 실행 이름 (scripts/run_experiment.py)")
    topic_key: Optional[str] = Field(None, max_length=100, description="배치 안의 주제 키")
    replicate: Optional[int] = Field(None, ge=0, description="반복 번호")
    mode: Literal["stateful", "baseline", "survey_only"] = Field(
        "stateful", description="baseline: 순서대로 앞 발언에 답하는 단순 토론 (비교 기준선). "
                                "survey_only: 토론 없이 사전 설문 후 혼자 다시 답함 (설문 필요)")
    record_prompts: bool = Field(True, description="발언마다 최종 지시 프롬프트를 meta.prompt에 저장")
    mechanisms: Mechanisms = Field(default_factory=Mechanisms)
    dynamics: Dynamics = Field(default_factory=Dynamics)
    stalemate_exchanges: Optional[int] = Field(None, ge=1, le=10)
    consensus_spread: Optional[float] = Field(None, ge=0.0, le=2.0)
    max_subtopics: Optional[int] = Field(None, ge=1, le=5)
    context_messages: Optional[int] = Field(None, ge=1, le=30)
    context_chars: Optional[int] = Field(None, ge=100, le=5000)
    agent_temperature: Optional[float] = Field(None, ge=0.0, le=1.5, description="참가자 기본 temperature")
    moderator_temperature: Optional[float] = Field(None, ge=0.0, le=1.5)
    analyzer: Optional[ModelRef] = Field(None, description="발언 분석 모델 (비우면 첫 참가자의 모델)")
    participants: Dict[str, ParticipantCondition] = Field(default_factory=dict)


def engine_settings(experiment: Optional[ExperimentConfig] = None) -> DiscussionConfig:
    """기본 설정에 실험 조건을 덮어쓴 사본 (전역 설정은 바꾸지 않음)"""
    base = get_config()
    if experiment is None:
        return replace(base)
    overrides = experiment.dynamics.model_dump(exclude_none=True)
    for key in ("stalemate_exchanges", "consensus_spread", "max_subtopics", "context_messages", "context_chars",
                "agent_temperature", "moderator_temperature"):
        value = getattr(experiment, key)
        if value is not None:
            overrides[key] = value
    overrides["engine_mode"] = experiment.mode
    overrides["record_prompts"] = experiment.record_prompts
    m = experiment.mechanisms
    overrides.update(use_reply_obligation=m.reply_obligation, use_stalemate_mediation=m.stalemate_mediation,
                     use_devils_advocate=m.devils_advocate, use_closing_round=m.closing_round)
    if not m.latitude:
        overrides.update(accept_wide=FULL_LATITUDE, accept_narrow=FULL_LATITUDE)
    if not m.concession_shift:
        overrides["concession_step"] = 0.0
    return replace(base, **overrides)
