"""
자연스러운 토론 시스템 - 동적 턴 관리

stream()은 토론 진행을 EngineEvent로 yield한다. 저장·전송은 호출 측(API 런타임)의 책임이다.
"""
import logging
import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, AsyncIterator, Dict, List, Optional, Protocol

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
    RESPOND_TO_HUMAN = "respond_to_human"  # 사람 참가자 발언에 응답


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


@dataclass
class HumanInput:
    """사람 참가자 발언 (저장·발행은 게이트 구현이 이미 마친 상태)"""
    name: str
    content: str
    seq: Optional[int] = None
    user_id: Optional[str] = None


class InterventionGate(Protocol):
    """발화가 끝날 때마다 호출되는 사람 개입 지점. 대기 중인 발언을 받아 반환한다 (없으면 빈 목록)."""

    async def after_utterance(self) -> List[HumanInput]: ...


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

        # 사람 개입: 응답해야 할 사람 발언과 남은 후속 응답 수
        self.pending_human: Optional[HumanInput] = None
        self.pending_followups = 0

        self.config = get_config()
        self.restored = False
        self.statements_on_subtopic = 0  # 현재 소주제에서 나온 AI 발언 수

    def restore(self, prior_messages: List[Message], subtopics: Optional[List[str]] = None,
                current_subtopic: Optional[str] = None) -> None:
        """중단된 토론을 저장된 발언으로 복원 (페르소나 진화 상태는 복원하지 않음)

        prior_messages: role assistant(AI) / moderator / user(사람, metadata speaker_type=human)
        """
        self.messages = list(prior_messages)
        for msg in self.messages:
            if msg.role in AI_ROLES:
                self.turn_count += 1
                if msg.agent_name in self.agent_turn_count:
                    self.agent_turn_count[msg.agent_name] += 1
                self.last_speakers = (self.last_speakers + [msg.agent_name])[-3:]

        # 마지막 발언이 응답받지 못한 사람 발언이면 이어서 응답하도록 예약
        spoken = [m for m in self.messages if m.role != "moderator"]
        if spoken and spoken[-1].metadata.get("speaker_type") == "human":
            last = spoken[-1]
            self.pending_human = HumanInput(last.agent_name, last.content, last.metadata.get("seq"))
            self.pending_followups = self.config.human_followup_responses

        if self.moderator and subtopics:
            self.moderator.subtopics = list(subtopics)
            # DB의 current_subtopic은 200자로 잘려 저장되므로 앞부분으로 비교
            prefix = (current_subtopic or "")[:200]
            self.moderator.current_subtopic_idx = next(
                (i for i, s in enumerate(subtopics) if s[:200] == prefix), 0)
        self.restored = True

    async def stream(self, topic: str, language: Optional[str] = None,
                     gate: Optional[InterventionGate] = None) -> AsyncIterator[EngineEvent]:
        """토론 실행 - 진행 상황을 EngineEvent로 yield. gate가 있으면 발화가 끝날 때마다 사람 개입을 받는다."""
        if not language:
            language = LanguageDetector.detect_language(topic)
        for agent in self.agents:
            agent.language = language

        if self.moderator:
            self.moderator.language = language
            if not self.restored:  # 재개 시에는 기존 소주제 유지
                subtopics = await self.moderator.generate_subtopics(topic)
                if subtopics:
                    yield EngineEvent(kind="subtopics", meta={"subtopics": subtopics})

        # 발언 예산이 끝나도 사람 발언에 대한 후속 응답은 수행한다
        while self.turn_count < self.max_statements or self.pending_followups > 0:
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
                "in_reply_to_seq": self.pending_human.seq if action == ActionType.RESPOND_TO_HUMAN and self.pending_human else None,
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
            self.statements_on_subtopic += 1
            self._process_evolution(speaker, response, topic)
            if action == ActionType.RESPOND_TO_HUMAN:
                self.pending_followups -= 1
            await self._human_checkpoint(gate)

            if self.moderator and self.pending_followups == 0 and self._should_moderator_intervene():
                event = await self._moderator_intervention(topic)
                if event:
                    yield event
                    await self._human_checkpoint(gate)

            self.turn_count += 1

        logger.info("Discussion completed: turns=%d messages=%d", self.turn_count, len(self.messages))

    async def _human_checkpoint(self, gate: Optional[InterventionGate]) -> None:
        """사람 개입 지점: 받은 발언을 대화에 넣고 다음 AI 발언이 응답하도록 예약"""
        if gate is None:
            return
        for human in await gate.after_utterance():
            self.messages.append(Message(role="user", content=human.content, agent_name=human.name,
                                         metadata={"speaker_type": "human", "seq": human.seq}))
            self.pending_human = human
            self.pending_followups = self.config.human_followup_responses

    def _select_next_speaker(self) -> tuple[Optional[DiscussionAgent], Optional[ActionType]]:
        """다음 발언자와 액션 선택 - 진행도에 따른 자연스러운 흐름"""
        eligible = [a for a in self.agents
                    if self.agent_turn_count[a.persona.name] < self.config.max_turns_per_agent]
        if self.pending_followups > 0:
            candidates = [a for a in (eligible or self.agents) if a.persona.name not in self.last_speakers[-1:]]
            pool = candidates or eligible or self.agents
            return min(pool, key=lambda a: self.agent_turn_count[a.persona.name]), ActionType.RESPOND_TO_HUMAN
        if not eligible:
            return None, None

        # 직전 발언자 제외 (연속 발언 방지)
        if self.last_speakers:
            eligible = [a for a in eligible if a.persona.name not in self.last_speakers[-1:]] or self.agents

        progress = self.turn_count / self.max_statements if self.max_statements > 0 else 0
        fewest = min(self.agent_turn_count[a.persona.name] for a in eligible)
        least_spoken = random.choice([a for a in eligible if self.agent_turn_count[a.persona.name] == fewest])

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
        return least_spoken, action

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

        if action == ActionType.RESPOND_TO_HUMAN and self.pending_human:
            return prompts.render("turn_actions.respond_to_human", topic=topic,
                                  human_name=self.pending_human.name, remark=self.pending_human.content)

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

    def _statements_per_subtopic(self) -> Optional[int]:
        count = len(self.moderator.subtopics) if self.moderator else 0
        return max(2, self.max_statements // count) if count else None

    def _transition_due(self) -> bool:
        return self.moderator.should_transition_subtopic(
            self.messages, self.statements_on_subtopic, self._statements_per_subtopic())

    def _should_moderator_intervene(self) -> bool:
        """모더레이터 개입 판단: 소주제 전환 시점, 추상적 발언 연속, 또는 AI 발언 N개마다.
        마지막 AI 발언 뒤에는 개입하지 않는다 (답 없는 질문으로 끝나지 않도록)."""
        done = self.turn_count + 1  # 지금까지 나온 AI 발언 수
        if done >= self.max_statements:
            return False
        if self._transition_due():
            return True
        if self._should_probe_for_specifics():
            return True
        every = self.config.moderator_every_statements
        return done >= 2 and done % every == 0

    async def _moderator_intervention(self, topic: str) -> Optional[EngineEvent]:
        """모더레이터 개입 - 주제 전환, 구체화 질문, 심화 질문"""
        if self._transition_due():
            content = await self.moderator.transition_to_next_subtopic(topic)
            msg_type = "transition"
            self.statements_on_subtopic = 0
        elif self._should_probe_for_specifics():
            content = await self.moderator.generate_probing_question(topic, self.messages, is_abstract=True)
            msg_type = "probing"
        else:
            msg_type = "question"
            content = await self.moderator.generate_probing_question(topic, self.messages)

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
