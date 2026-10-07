"""
모더레이터 모듈 - 토론 진행자 및 소주제 관리
"""
from typing import List, Optional
from langchain_core.messages import HumanMessage
from pydantic import BaseModel, Field
from langchain_core.language_models import BaseChatModel
from src.models.personas import Message, LLMProvider
from src.utils.llm_provider import LLMFactory
from src.utils.language_detector import LanguageDetector
from config.config_loader import config_loader
from config.discussion_config import get_config

AI_ROLES = ("agent", "assistant")
QUESTION_TYPES = ("probing", "question", "forced")


class Subtopics(BaseModel):
    """소주제 구조화 출력 (텍스트 목록 파싱은 응답 형식에 따라 0개가 될 수 있어 사용하지 않음)"""
    subtopics: List[str] = Field(description="4-5 short subtopics as plain text")


class DiscussionModerator:
    """토론 진행자 - 소주제 관리 및 심화 유도"""

    def __init__(self, llm: Optional[BaseChatModel] = None, language: str = "auto"):
        self.llm = llm or LLMFactory.create_llm(None, temperature=0.5)
        self.language = language

        # 소주제 관리
        self.subtopics: List[str] = []
        self.current_subtopic_idx = 0

        # 질문 관리
        self.question_count = 0

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

    async def generate_subtopics(self, topic: str) -> List[str]:
        """주제에 대한 핵심 관점/소주제 생성"""
        prompt = config_loader.prompts.render(
            "moderator.subtopics", topic=topic, language_instruction=self._lang_instruction()
        )
        result = await self.llm.with_structured_output(Subtopics).ainvoke([HumanMessage(content=prompt)])
        cleaned = [s.replace('**', '').strip().lstrip('#-•* ').strip() for s in result.subtopics]
        self.subtopics = [s for s in cleaned if s][:get_config().max_subtopics]
        self.current_subtopic_idx = 0
        return self.subtopics

    async def generate_probing_question(self, topic: str, messages: List[Message],
                                        is_abstract: bool = False) -> str:
        """심화 질문 생성 (이전에 한 질문은 반복하지 않음)"""
        previous = [m.content[:200] for m in messages
                    if m.role == "moderator" and m.metadata.get("type") in QUESTION_TYPES]
        previous_questions = " / ".join(previous[-5:]) or "(none)"
        if is_abstract and messages:
            prompt = config_loader.prompts.render(
                "moderator.probing_abstract",
                statement=messages[-1].content[:200],
                previous_questions=previous_questions,
                language_instruction=self._lang_instruction(),
            )
        else:
            prompt = config_loader.prompts.render(
                "moderator.probing_general",
                topic=topic,
                subtopic=self.current_subtopic,
                recent_points=' | '.join(m.content[:100] for m in messages[-3:]),
                previous_questions=previous_questions,
                language_instruction=self._lang_instruction(),
            )

        response = await self.llm.ainvoke([HumanMessage(content=prompt)])
        self.question_count += 1
        return response.content.strip()

    def should_transition_subtopic(self, messages: List[Message], statements_on_current: int = 0,
                                   statements_per_subtopic: Optional[int] = None) -> bool:
        """주제 전환 필요 여부 판단 (발언 예산을 소주제 수로 나눈 몫을 다 쓰면 전환해 모든 관점을 다룸)"""
        config = get_config()
        current_topic = self.current_subtopic
        if current_topic is None or self.current_subtopic_idx >= len(self.subtopics) - 1:
            return False  # 마지막 소주제거나 모든 주제 완료
        if statements_per_subtopic and statements_on_current >= statements_per_subtopic:
            return True

        keywords = current_topic.lower().split()[:2]  # 주제의 첫 2단어

        def mentions(msg: Message) -> bool:
            return msg.role in AI_ROLES and any(k in msg.content.lower() for k in keywords)

        window = config.depth_analysis_window
        depth = sum(1 for m in messages[-window:] if mentions(m))
        if depth >= config.min_depth_per_subtopic:
            return True

        mentioned_recently = any(mentions(m) for m in messages[-config.recent_mention_window:])
        return not mentioned_recently and len(messages) > config.min_messages_before_transition

    async def transition_to_next_subtopic(self, topic: str) -> str:
        """다음 소주제로 전환"""
        self.current_subtopic_idx += 1
        if self.current_subtopic is not None:
            return self._localized("moderator.transition").format(subtopic=self.current_subtopic, topic=topic)
        return self._localized("moderator.all_covered")
