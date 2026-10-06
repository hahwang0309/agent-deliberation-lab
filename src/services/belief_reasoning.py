"""
신념 기반 추론 서비스 - Chain-of-Thought 기법 적용
"""
from typing import List, Optional
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage
from src.models.personas import Persona, Message, LLMProvider
from src.utils.llm_provider import LLMFactory
from config.config_loader import config_loader


class BeliefReasoningService:
    """신념과 가치관 기반 추론 서비스"""

    def __init__(self, persona: Persona, llm: Optional[BaseChatModel] = None):
        self.persona = persona
        self.llm = llm or LLMFactory.create_llm(LLMProvider.OPENAI, temperature=0.3)

    async def reason_about_topic(self, topic: str, context: List[Message] = None) -> str:
        """주제에 대한 신념 기반 추론 (Chain-of-Thought)"""
        reasoning_prompt = config_loader.prompts.render(
            "belief_reasoning.reason",
            name=self.persona.name,
            role=self.persona.role,
            background=self.persona.background,
            topic=topic,
            beliefs=', '.join(self.persona.beliefs[:3]),
        )
        response = await self.llm.ainvoke([HumanMessage(content=reasoning_prompt)])
        return response.content
