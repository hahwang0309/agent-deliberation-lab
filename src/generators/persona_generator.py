"""
주제 기반 페르소나 자동 생성
"""
import asyncio
import logging
from typing import List, Optional

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import ValidationError

from config.config_loader import config_loader
from src.models.personas import LLMProvider, Persona
from src.utils.language_detector import LanguageDetector
from src.utils.llm_provider import LLMFactory, structured_output

logger = logging.getLogger(__name__)



class PersonaGenerator:
    """주제에 맞는 페르소나를 생성하는 클래스 (구조화 출력 사용)"""

    def __init__(self, llm: Optional[BaseChatModel] = None, provider: Optional[LLMProvider] = None):
        self.llm = llm or LLMFactory.create_llm(
            provider, temperature=config_loader.get_llm_config().task_temperatures["persona_generation"],
            max_tokens=config_loader.get_llm_config().structured_max_tokens
        )
        self.structured_llm = structured_output(self.llm, Persona)

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

        messages = [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]
        for attempt in range(1, config_loader.config.persona_generation.max_attempts + 1):
            try:
                persona = await self.structured_llm.ainvoke(messages)
                break
            except ValidationError:
                if attempt == config_loader.config.persona_generation.max_attempts:
                    raise
                logger.warning("Persona output failed validation (attempt %d); retrying", attempt)
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
