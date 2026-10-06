"""
주제 기반 페르소나 자동 생성
"""
import asyncio
import logging
from typing import List, Optional

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from config.config_loader import config_loader
from src.models.personas import LLMProvider, Persona
from src.utils.language_detector import LanguageDetector
from src.utils.llm_provider import LLMFactory

logger = logging.getLogger(__name__)


class PersonaGenerator:
    """주제에 맞는 페르소나를 생성하는 클래스 (구조화 출력 사용)"""

    def __init__(self, llm: Optional[BaseChatModel] = None, provider: Optional[LLMProvider] = None):
        self.llm = llm or LLMFactory.create_llm(provider, temperature=0.8)
        self.structured_llm = self.llm.with_structured_output(Persona)

    async def generate_persona(self, topic: str, perspective: Optional[str] = None,
                               agent_id: Optional[str] = None, language: Optional[str] = None) -> Persona:
        """단일 페르소나 생성"""
        prompts = config_loader.prompts
        language = language or LanguageDetector.detect_language(topic)

        perspective_text = f"with a {perspective} perspective" if perspective else ""
        system_prompt = (
            prompts.get_persona_system_prompt()
            + LanguageDetector.get_language_instruction(language)
            + (prompts.get(f"persona_generation.language_suffix.{language}") or "")
        )
        user_prompt = prompts.get_persona_user_prompt(topic, perspective_text)

        persona = await self.structured_llm.ainvoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ])
        if agent_id:
            persona = persona.model_copy(update={"name": agent_id})
        return persona

    async def generate_multiple_personas(self, topic: str, count: int = 3,
                                         language: Optional[str] = None) -> List[Persona]:
        """서로 다른 관점·말투의 페르소나 여러 명을 병렬 생성 (이름은 Agent A, B, ...)"""
        prompts = config_loader.prompts
        perspectives = prompts.get("persona_generation.perspectives")
        style_hints = prompts.get("persona_generation.style_hints")

        tasks = [
            self.generate_persona(
                topic,
                perspective=prompts.render(
                    "persona_generation.perspective_template",
                    perspective=perspectives[i % len(perspectives)],
                    style_hint=style_hints[i % len(style_hints)],
                ),
                agent_id=f"Agent {chr(65 + i)}",
                language=language,
            )
            for i in range(count)
        ]
        return list(await asyncio.gather(*tasks))
