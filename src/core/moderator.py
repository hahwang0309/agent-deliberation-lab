"""
모더레이터 모듈 - 명제(소주제) 설정, 진행 안내, 교착 시 중재 질문

진행 시점(언제 전환·중재할지)은 토론 엔진이 상태를 보고 정한다. 모더레이터는 내용만 만든다.
"""
from typing import List, Optional

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage
from pydantic import BaseModel, Field

from config.config_loader import config_loader
from src.utils.language_detector import LanguageDetector
from src.utils.llm_provider import LLMFactory, structured_output


class Subtopics(BaseModel):
    """명제 목록 구조화 출력 (텍스트 목록 파싱은 응답 형식에 따라 0개가 될 수 있어 사용하지 않음)"""
    subtopics: List[str] = Field(description="Debatable propositions as short plain text")


class DiscussionModerator:
    def __init__(self, llm: Optional[BaseChatModel] = None, language: str = "auto"):
        self.llm = llm or LLMFactory.create_llm(None, temperature=0.5)
        self.language = language
        self.subtopics: List[str] = []
        self.current_subtopic_idx = 0

    @property
    def current_subtopic(self) -> Optional[str]:
        if self.current_subtopic_idx < len(self.subtopics):
            return self.subtopics[self.current_subtopic_idx]
        return None

    def _lang_instruction(self) -> str:
        return LanguageDetector.get_language_instruction(self.language)

    def _localized(self, path: str) -> str:
        """언어별 템플릿 (없으면 영어)"""
        prompts = config_loader.prompts
        return prompts.get(f"{path}.{self.language}") or prompts.get(f"{path}.en")

    async def generate_subtopics(self, topic: str, count: int) -> List[str]:
        """참가자 수·발언 수로 정한 개수(count)만큼 찬반이 갈리는 명제를 만든다"""
        prompt = config_loader.prompts.render(
            "moderator.subtopics", topic=topic, count=count, language_instruction=self._lang_instruction())
        result = await structured_output(self.llm, Subtopics).ainvoke([HumanMessage(content=prompt)])
        cleaned = [s.replace('**', '').strip().lstrip('#-•*0123456789.) ').strip() for s in result.subtopics]
        self.subtopics = [s for s in cleaned if s][:count]
        self.current_subtopic_idx = 0
        return self.subtopics

    def opening(self) -> str:
        return self._localized("moderator.opening").format(subtopic=self.current_subtopic)

    def advance(self) -> str:
        """다음 명제로 전환하고 안내 문구를 돌려준다"""
        self.current_subtopic_idx += 1
        return self._localized("moderator.transition").format(subtopic=self.current_subtopic)

    def closing_announcement(self) -> str:
        return self._localized("moderator.closing_announce")

    async def mediation_question(self, topic: str, party_a: str, party_b: str,
                                 claims_a: List[str], claims_b: List[str]) -> str:
        """교착된 두 참가자 사이의 쟁점을 짚는 질문 (참가자가 2명이라 제3자가 없을 때 사용)"""
        prompt = config_loader.prompts.render(
            "moderator.mediate", topic=topic, proposition=self.current_subtopic or topic,
            party_a=party_a, party_b=party_b,
            claims_a=" / ".join(claims_a[-2:]) or "-", claims_b=" / ".join(claims_b[-2:]) or "-",
            language_instruction=self._lang_instruction(),
        )
        response = await self.llm.ainvoke([HumanMessage(content=prompt)])
        return response.text.strip()
