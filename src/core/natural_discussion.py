"""
자연스러운 토론 시스템 - 동적 턴 관리

stream()은 토론 진행을 EngineEvent로 yield한다. 저장·전송은 호출 측(API 런타임)의 책임이다.
"""
import logging
import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, AsyncIterator, Dict, List, Optional

from config.config_loader import config_loader
from config.discussion_config import get_config
from src.core.agent import DiscussionAgent
from src.core.moderator import DiscussionModerator
from src.models.personas import Message
from src.utils.language_detector import LanguageDetector

logger = logging.getLogger(__name__)

AI_ROLES = ("agent", "assistant")


class ActionType(Enum):
    """발화 액션 타입"""
    PRESENT = "present"        # 새로운 관점 제시
    RESPOND = "respond"        # 직접 응답
    BUILD = "build"            # 동의하며 확장
    CHALLENGE = "challenge"    # 도전/반박
    EXAMPLE = "example"        # 구체적 예시
    SYNTHESIZE = "synthesize"  # 종합


@dataclass
class EngineEvent:
    """토론 엔진 이벤트

    kind:
      - subtopics: content 없음, meta["subtopics"]에 소주제 목록
      - utterance_start: 발화 시작 (speaker, speaker_type, action)
      - chunk: 발화 스트리밍 조각 (content=조각)
      - utterance: 완성된 발화 (content=전체 텍스트)
    """
    kind: str
    speaker: Optional[str] = None
    speaker_type: Optional[str] = None  # ai | moderator
    content: str = ""
    action: Optional[str] = None
    meta: Dict[str, Any] = field(default_factory=dict)


class NaturalDiscussion:
    """자연스러운 토론 시스템"""

    def __init__(self, agents: List[DiscussionAgent], moderator: Optional[DiscussionModerator] = None,
                 max_statements: int = 20):
        self.agents = agents
        self.moderator = moderator
        self.max_statements = max_statements
        self.messages: List[Message] = []

        # 토론 상태 추적
        self.turn_count = 0
        self.agent_turn_count = {agent.persona.name: 0 for agent in agents}
        self.last_speakers: List[str] = []

        self.config = get_config()

    async def stream(self, topic: str, language: Optional[str] = None) -> AsyncIterator[EngineEvent]:
        """토론 실행 - 진행 상황을 EngineEvent로 yield"""
        if not language:
            language = LanguageDetector.detect_language(topic)
        for agent in self.agents:
            agent.language = language

        if self.moderator:
            self.moderator.language = language
            subtopics = await self.moderator.generate_subtopics(topic)
            if subtopics:
                yield EngineEvent(kind="subtopics", meta={"subtopics": subtopics})

        while self.turn_count < self.max_statements:
            speaker, action = self._select_next_speaker()
            if not speaker:
                break

            prompt = self._generate_prompt(topic, speaker, action)

            yield EngineEvent(kind="utterance_start", speaker=speaker.persona.name,
                              speaker_type="ai", action=action.value)
            response = ""
            async for chunk in speaker.respond_stream(prompt, self.messages):
                response += chunk
                yield EngineEvent(kind="chunk", speaker=speaker.persona.name,
                                  speaker_type="ai", content=chunk, action=action.value)

            rag = speaker.last_rag_result
            meta = {
                "turn": self.turn_count,
                "rag_used": rag is not None,
                "rag_query": rag.query if rag else None,
                "sources": rag.sources if rag else None,
            }
            self.messages.append(Message(role="assistant", content=response,
                                         agent_name=speaker.persona.name,
                                         metadata={"action": action.value, **meta}))
            yield EngineEvent(kind="utterance", speaker=speaker.persona.name, speaker_type="ai",
                              content=response, action=action.value, meta=meta)

            self._update_state(speaker)
            self._process_evolution(speaker, response, topic)

            if self.moderator and self._should_moderator_intervene():
                event = await self._moderator_intervention(topic)
                if event:
                    yield event

            self.turn_count += 1

        logger.info("Discussion completed: turns=%d messages=%d", self.turn_count, len(self.messages))

    def _select_next_speaker(self) -> tuple[Optional[DiscussionAgent], Optional[ActionType]]:
        """다음 발언자와 액션 선택 - 진행도에 따른 자연스러운 흐름"""
        eligible = [a for a in self.agents
                    if self.agent_turn_count[a.persona.name] < self.config.max_turns_per_agent]
        if not eligible:
            return None, None

        # 직전 발언자 제외 (연속 발언 방지)
        if self.last_speakers:
            eligible = [a for a in eligible if a.persona.name not in self.last_speakers[-1:]] or self.agents

        progress = self.turn_count / self.max_statements if self.max_statements > 0 else 0
        least_spoken = min(eligible, key=lambda a: self.agent_turn_count[a.persona.name])

        if self.turn_count == 0:
            return random.choice(eligible), ActionType.PRESENT
        if progress < 0.3:
            action = random.choices([ActionType.PRESENT, ActionType.EXAMPLE], weights=[0.7, 0.3])[0]
            return least_spoken, action
        if progress < 0.7:
            build_weight = self.config.prefer_building_over_challenging
            action = random.choices(
                [ActionType.RESPOND, ActionType.BUILD, ActionType.CHALLENGE, ActionType.EXAMPLE],
                weights=[0.3, build_weight * 0.4, (1.0 - build_weight) * 0.2, 0.2]
            )[0]
            return least_spoken, action
        action = random.choices([ActionType.SYNTHESIZE, ActionType.BUILD], weights=[0.6, 0.4])[0]
        return random.choice(eligible), action

    def _generate_prompt(self, topic: str, speaker: DiscussionAgent, action: ActionType) -> str:
        """액션에 맞는 프롬프트 생성 (config/prompts.yaml의 turn_actions)"""
        prompts = config_loader.prompts

        subtopic = self.moderator.current_subtopic if self.moderator else None
        focus_line = prompts.render("turn_actions.focus_line", subtopic=subtopic) if subtopic else ""

        recent_context = ""
        if self.messages:
            lines = [prompts.render("turn_actions.recent_context_header")]
            lines += [prompts.render("turn_actions.recent_context_line", name=m.agent_name, excerpt=m.content[:100])
                      for m in self.messages[-2:]]
            recent_context = "\n".join(lines)

        target = self._find_challengeable_point() if action == ActionType.CHALLENGE else (
            self.messages[-1] if self.messages else None)
        excerpt_len = 150 if action == ActionType.RESPOND else 100

        return prompts.render(
            f"turn_actions.{action.value}",
            topic=topic,
            focus_line=focus_line,
            recent_context=recent_context,
            target_name=target.agent_name if target else "Someone",
            target_excerpt=target.content[:excerpt_len] if target else topic,
        )

    def _update_state(self, speaker: DiscussionAgent):
        """토론 상태 업데이트"""
        self.agent_turn_count[speaker.persona.name] += 1
        self.last_speakers.append(speaker.persona.name)
        if len(self.last_speakers) > 3:
            self.last_speakers.pop(0)

    def _process_evolution(self, speaker: DiscussionAgent, response: str, topic: str):
        """다른 참가자의 페르소나 진화 처리"""
        for agent in self.agents:
            if agent is not speaker:
                change = agent.process_other_argument(response[:500], speaker.persona.name, topic)
                if change and change.get('position_changed'):
                    logger.debug("%s shifted position", agent.persona.name)

    def _should_moderator_intervene(self) -> bool:
        """모더레이터 개입 필요 판단"""
        if self.turn_count < 2:
            return False
        if self.turn_count % 2 == 0:
            return True
        if self._should_probe_for_specifics():
            return True
        if self.moderator.should_transition_subtopic(self.messages):
            return True
        return random.random() > 0.5

    async def _moderator_intervention(self, topic: str) -> Optional[EngineEvent]:
        """모더레이터 개입 - 주제 전환, 구체화 질문, 심화 질문"""
        if self.moderator.should_transition_subtopic(self.messages):
            content = await self.moderator.transition_to_next_subtopic(topic)
            msg_type = "transition"
        elif self._should_probe_for_specifics():
            content = await self.moderator.generate_probing_question(topic, self.messages, is_abstract=True)
            msg_type = "probing"
        else:
            msg_type = "question" if self.moderator.should_ask_question(self.turn_count) else "forced"
            content = await self.moderator.generate_probing_question(topic, self.messages)
            self.moderator.last_question_turn = self.turn_count

        if not content:
            return None

        self.messages.append(Message(role="moderator", content=content, agent_name="Moderator",
                                     metadata={"type": msg_type}))
        return EngineEvent(kind="utterance", speaker="Moderator", speaker_type="moderator",
                           content=content, action=msg_type,
                           meta={"turn": self.turn_count, "subtopic": self.moderator.current_subtopic})

    def _should_probe_for_specifics(self) -> bool:
        """최근 2개 AI 발언이 모두 추상적이면 구체화 필요"""
        if len(self.messages) < 2:
            return False
        abstract_keywords = [
            "in general", "overall", "basically", "essentially",
            "theoretically", "conceptually", "abstractly",
            "일반적으로", "전반적으로", "기본적으로", "이론적으로"
        ]
        abstract_count = sum(
            1 for msg in self.messages[-2:]
            if msg.role in AI_ROLES and any(kw in msg.content.lower() for kw in abstract_keywords)
        )
        return abstract_count >= 2

    def _find_challengeable_point(self) -> Optional[Message]:
        """도전할 만한 강한 주장 찾기"""
        for msg in reversed(self.messages[-5:]):
            if any(word in msg.content.lower() for word in ["must", "always", "never", "clearly"]):
                return msg
        return self.messages[-1] if self.messages else None
