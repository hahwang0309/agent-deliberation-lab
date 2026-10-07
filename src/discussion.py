"""
토론 조립 헬퍼 - 참가자 설정으로 NaturalDiscussion 생성
"""
from dataclasses import dataclass
from typing import List, Optional

from src.core.agent import DiscussionAgent
from src.core.experiment import ExperimentConfig, ParticipantCondition, engine_settings
from src.core.moderator import DiscussionModerator
from src.core.natural_discussion import NaturalDiscussion
from src.services.survey import SurveyConfig
from src.models.personas import LLMProvider, Persona
from src.utils.llm_provider import LLMBundle, LLMFactory


@dataclass
class ParticipantSpec:
    """토론 참가자 1명의 페르소나와 LLM 설정"""
    persona: Persona
    provider: Optional[LLMProvider] = None  # None이면 config의 기본 프로바이더
    model: Optional[str] = None


def create_discussion(participants: List[ParticipantSpec],
                      bundle: Optional[LLMBundle] = None,
                      use_moderator: bool = True,
                      enable_web_search: bool = False,
                      enable_belief_reasoning: bool = False,
                      max_statements: int = 20,
                      experiment: Optional[ExperimentConfig] = None,
                      propositions: Optional[List[str]] = None,
                      materials: Optional[str] = None,
                      survey: Optional[SurveyConfig] = None) -> NaturalDiscussion:
    """참가자별 provider/model로 에이전트를 만들고, 모더레이터·발언 분석은 첫 참가자의 provider를 사용한다.
    experiment가 있으면 그 조건으로 만든 토론별 설정을 엔진·에이전트에 넘긴다(전역 설정은 그대로)."""
    bundle = bundle or LLMBundle()
    settings = engine_settings(experiment)
    conditions = experiment.participants if experiment else {}
    participants = [
        ParticipantSpec(spec.persona, spec.provider or LLMFactory.default_provider(), spec.model)
        for spec in participants
    ]

    agents = []
    for spec in participants:
        condition = conditions.get(spec.persona.name) or ParticipantCondition()
        temperature = condition.temperature if condition.temperature is not None else settings.agent_temperature
        agents.append(DiscussionAgent(
            spec.persona,
            llm=bundle.get(spec.provider, spec.model, temperature),
            aux_llm=bundle.get(spec.provider, spec.model, 0.3),
            provider=spec.provider,
            enable_web_search=enable_web_search,
            enable_belief_reasoning=enable_belief_reasoning,
            config=settings,
            stubbornness=condition.stubbornness,
            materials=materials,
        ))

    lead = participants[0] if participants else ParticipantSpec(None, LLMFactory.default_provider())
    moderator = (DiscussionModerator(llm=bundle.get(lead.provider, lead.model, settings.moderator_temperature))
                 if use_moderator and participants else None)
    # 발언 분석(토론 상태·입장 동역학)은 판정이 흔들리지 않도록 temperature 0.
    # 실험 조건으로 분석 모델을 따로 지정할 수 있다(판정자와 참가자 모델 분리).
    analyzer = None
    if participants and (experiment is None or experiment.mechanisms.analysis):
        ref = experiment.analyzer if experiment and experiment.analyzer else None
        provider = LLMProvider(ref.provider) if ref and ref.provider else lead.provider
        model = ref.model if ref and ref.model else (lead.model if provider == lead.provider else None)
        analyzer = bundle.get(provider, model, 0.0)

    return NaturalDiscussion(agents, moderator, max_statements, analyzer=analyzer, config=settings,
                             propositions=propositions, survey=survey)
