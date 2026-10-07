"""
토론 조립 헬퍼 - 참가자 설정으로 NaturalDiscussion 생성
"""
from dataclasses import dataclass
from typing import List, Optional

from src.core.agent import DiscussionAgent
from src.core.moderator import DiscussionModerator
from src.core.natural_discussion import NaturalDiscussion
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
                      max_statements: int = 20) -> NaturalDiscussion:
    """참가자별 provider/model로 에이전트를 만들고, 모더레이터·발언 분석은 첫 참가자의 provider를 사용한다."""
    bundle = bundle or LLMBundle()
    participants = [
        ParticipantSpec(spec.persona, spec.provider or LLMFactory.default_provider(), spec.model)
        for spec in participants
    ]

    agents = [
        DiscussionAgent(
            spec.persona,
            llm=bundle.get(spec.provider, spec.model, 0.7),
            aux_llm=bundle.get(spec.provider, spec.model, 0.3),
            provider=spec.provider,
            enable_web_search=enable_web_search,
            enable_belief_reasoning=enable_belief_reasoning,
        )
        for spec in participants
    ]

    lead = participants[0] if participants else ParticipantSpec(None, LLMFactory.default_provider())
    moderator = DiscussionModerator(llm=bundle.get(lead.provider, lead.model, 0.5)) if use_moderator and participants else None
    # 발언 분석(토론 상태·입장 동역학)은 판정이 흔들리지 않도록 temperature 0
    analyzer = bundle.get(lead.provider, lead.model, 0.0) if participants else None

    return NaturalDiscussion(agents, moderator, max_statements, analyzer=analyzer)
