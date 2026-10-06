"""
토론 조립 헬퍼 - 참가자 설정으로 NaturalDiscussion 생성
"""
from dataclasses import dataclass
from typing import List, Optional

from src.core.agent import DiscussionAgent
from src.core.moderator import DiscussionModerator
from src.core.natural_discussion import NaturalDiscussion
from src.models.personas import LLMProvider, Persona
from src.utils.llm_provider import LLMBundle


@dataclass
class ParticipantSpec:
    """토론 참가자 1명의 페르소나와 LLM 설정"""
    persona: Persona
    provider: LLMProvider = LLMProvider.OPENAI
    model: Optional[str] = None


def create_discussion(participants: List[ParticipantSpec],
                      bundle: Optional[LLMBundle] = None,
                      use_moderator: bool = True,
                      enable_web_search: bool = False,
                      enable_belief_reasoning: bool = False,
                      max_statements: int = 20) -> NaturalDiscussion:
    """참가자별 provider/model로 에이전트를 만들고, 모더레이터는 첫 참가자의 provider를 사용한다."""
    bundle = bundle or LLMBundle()

    agents = [
        DiscussionAgent(
            spec.persona,
            llm=bundle.get(spec.provider, spec.model, 0.7),
            aux_llm=bundle.get(spec.provider, spec.model, 0.3),
            provider=spec.provider,
            track_evolution=True,
            enable_web_search=enable_web_search,
            enable_belief_reasoning=enable_belief_reasoning,
        )
        for spec in participants
    ]

    moderator = None
    if use_moderator and participants:
        lead = participants[0]
        moderator = DiscussionModerator(llm=bundle.get(lead.provider, lead.model, 0.5))

    return NaturalDiscussion(agents, moderator, max_statements)
