"""
토론 엔진 - 진행 계획, 상태 기반 발언자·발화 행위 선택, 발언 분석, 입장 동역학

설계 (이론적 배경은 docs/architecture.md 참고)
- 진행 계획: 참가자 수 N, AI 발언 수 S로 명제 수 k와 명제별 발언 예산을 정한다.
  종결 라운드 N발언을 따로 두고(본론이 N+1 이상 남을 때), k = clamp(본론 // (N+1), 1, max_subtopics).
  명제마다 전원이 먼저 입장을 밝히고(입장 표명) 남은 예산으로 상호 논증을 한다.
- 발언 선택(우선순위): 사람 발언 응답 → 종결 라운드 → 명제별 입장 표명 → 답하지 않은 반박·질문에 응답할 의무
  → 교착 시 제3자 중재·제3안 → 성급한 합의 시 반대 검토 → 입장 거리에 따른 동조·확장/사례 또는 반박/근거 공격
- 발언 분석: 발언마다 구조화 출력으로 주장·대상·관계·입장·청자별 설득력을 추출해 DebateState에 반영한다.

stream()은 진행을 EngineEvent로 yield한다. 저장·전송은 호출 측(API 런타임)의 책임이다.
"""
import asyncio
import hashlib
import logging
import random
from collections import Counter
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, AsyncIterator, Dict, List, Literal, Optional, Protocol, Tuple

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field, field_validator

from config.config_loader import config_loader
from config.discussion_config import DiscussionConfig, get_config
from src.core.agent import DiscussionAgent
from src.services.survey import POST, PRE, SurveyConfig, run_survey, transcript_text
from src.core.debate_state import Challenge, DebateState, DynamicsParams
from src.core.moderator import DiscussionModerator
from src.models.personas import Message
from src.utils.language_detector import LanguageDetector
from src.utils.llm_provider import structured_output

logger = logging.getLogger(__name__)

AI_ROLES = ("agent", "assistant")


class ActionType(Enum):
    """발화 행위"""
    POSITION = "position"                    # 입장 표명
    AGREE_EXTEND = "agree_extend"            # 동조하며 확장
    EXAMPLE = "example"                      # 사례 제시
    REBUT = "rebut"                          # 반박 (결론 반대)
    UNDERCUT = "undercut"                    # 근거 공격 (추론 비판)
    RESPOND_CHALLENGE = "respond_challenge"  # 받은 반박·질문에 응답 (방어·부분 양보·해명)
    MEDIATE = "mediate"                      # 제3자 중재
    THIRD_OPTION = "third_option"            # 제3의 안
    DEVILS_ADVOCATE = "devils_advocate"      # 성급한 합의에 대한 반대 검토
    CLOSING = "closing"                      # 종결 발언
    RESPOND_TO_HUMAN = "respond_to_human"    # 사람 참가자 발언에 응답
    REPLY = "reply"                          # 기준선 모드의 일반 발언 (발화 행위 지정 없음)


TARGETED_ACTIONS = (ActionType.AGREE_EXTEND, ActionType.EXAMPLE, ActionType.REBUT, ActionType.UNDERCUT,
                    ActionType.RESPOND_CHALLENGE, ActionType.DEVILS_ADVOCATE)


@dataclass
class EngineEvent:
    """토론 엔진 이벤트

    kind:
      - subtopics: meta["subtopics"]에 명제 목록
      - utterance_start: 발화 시작 (speaker, speaker_type, action)
      - chunk: 발화 스트리밍 조각 (content=조각)
      - utterance: 완성된 발화 (content=전체 텍스트, meta["seq"]=엔진이 붙인 순번)
      - analysis: 발언 분석과 토론 상태 (meta["seq"], meta["analysis"], meta["moves"], meta["stances"], meta["debate"])
      - survey: 사전·사후 설문 응답 (meta["phase"] = pre | post, meta["answers"])
    """
    kind: str
    speaker: Optional[str] = None
    speaker_type: Optional[str] = None  # ai | moderator | human
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


# ---------- 발언 분석 구조화 출력 ----------

RELATION_SYNONYMS = {  # 분석 LLM이 쓰는 동의어 → 정해진 관계 (한 값 때문에 분석 전체가 버려지지 않도록)
    "extend": "support", "agree": "support", "build": "support", "example": "support",
    "rebut": "attack", "undercut": "attack", "challenge": "attack", "counter": "attack", "disagree": "attack",
    "concession": "concede", "ask": "question",
}


class AnalysisTarget(BaseModel):
    seq: int
    speaker: str
    relation: Literal["support", "attack", "concede", "question"]

    @field_validator("relation", mode="before")
    @classmethod
    def normalize_relation(cls, value):
        value = str(value).strip().lower()
        return RELATION_SYNONYMS.get(value, value)


class ListenerInfluence(BaseModel):
    """청자별 설득 요인 (0~1). 결합 방식은 debate_state.persuasion 참고"""
    listener: str
    quality: float = 0.0       # 근거·논리의 질
    novelty: float = 1.0       # 이 청자에게 새로운 논거인가 (반복이면 0에 가깝게)
    value_match: float = 0.0   # 청자의 가치·신념의 언어로 말했는가
    credibility: float = 0.5   # 이 쟁점에서 화자의 전문성·신뢰성
    receptive: float = 0.0     # 청자의 논거를 인정했는가
    threat: float = 0.0        # 청자의 정체성·인격을 공격했는가

    @field_validator("quality", "novelty", "value_match", "credibility", "receptive", "threat", mode="before")
    @classmethod
    def clamp_unit(cls, value):
        return 0.0 if value is None else max(0.0, min(1.0, float(value)))


class Concession(BaseModel):
    to: str      # 양보받은 참가자
    claim: str   # 인정한 상대 주장 (짧게)


class UtteranceAnalysis(BaseModel):
    claims: List[str] = Field(default_factory=list)
    move: str = "position"
    targets: List[AnalysisTarget] = Field(default_factory=list)
    addressed: List[str] = Field(default_factory=list)
    concessions: List[Concession] = Field(default_factory=list)
    stance: float = Field(0.0, ge=-1.0, le=1.0)
    influence: List[ListenerInfluence] = Field(default_factory=list)

    @field_validator("targets", mode="before")
    @classmethod
    def drop_unknown_relations(cls, value):
        """알 수 없는 관계의 대상은 버린다 (나머지 분석은 유지)"""
        if not isinstance(value, list):
            return value
        valid = set(AnalysisTarget.model_fields["relation"].annotation.__args__)
        return [t for t in value if not isinstance(t, dict)
                or RELATION_SYNONYMS.get(str(t.get("relation", "")).strip().lower(),
                                         str(t.get("relation", "")).strip().lower()) in valid]


# ---------- 진행 계획 ----------

@dataclass
class DebatePlan:
    budgets: List[int]  # 명제별 AI 발언 예산
    closing: int        # 종결 라운드 발언 수


def plan_debate(n_agents: int, max_statements: int, max_subtopics: int, closing_round: bool = True) -> DebatePlan:
    """명제 수와 예산: 명제마다 '전원 입장 표명 + 상호 응답 1회 이상'(N+1발언)이 들어가도록"""
    n = max(1, n_agents)
    closing = n if closing_round and max_statements - n >= n + 1 else 0
    body = max_statements - closing
    k = max(1, min(max_subtopics, body // (n + 1)))
    return DebatePlan(budgets=split_budget(body, k), closing=closing)


def split_budget(total: int, count: int) -> List[int]:
    base, extra = divmod(total, max(1, count))
    return [base + (1 if i < extra else 0) for i in range(max(1, count))]


@dataclass
class Turn:
    speaker: DiscussionAgent
    action: ActionType
    target: Optional[Message] = None
    parties: Optional[Tuple[str, str]] = None


class SurveyFailed(RuntimeError):
    """설문 시점 하나에서 응답이 전혀 없음"""


class NaturalDiscussion:
    def __init__(self, agents: List[DiscussionAgent], moderator: Optional[DiscussionModerator] = None,
                 max_statements: int = 20, analyzer: Optional[BaseChatModel] = None,
                 config: Optional[DiscussionConfig] = None, propositions: Optional[List[str]] = None,
                 survey: Optional[SurveyConfig] = None):
        self.agents = agents
        self.moderator = moderator
        self.max_statements = max_statements
        self.analyzer = analyzer  # 발언 분석용 LLM (없으면 상태 분석 없이 진행 규칙만 적용)
        self.config = config or get_config()  # 토론별 설정 (실험 조건 반영, src/core/experiment.py)
        # 고정 명제: 지정하면 모더레이터가 명제를 만들지 않는다 (인간 토의와 같은 질문으로 비교할 때)
        self.fixed_propositions = [p for p in (propositions or []) if p.strip()] or None
        self.survey = survey  # 사전·사후 설문 (src/services/survey.py)
        # 기준선 모드: 순서대로 돌아가며 앞 발언에 답하는 단순 토론 (발화 행위·응답 의무·중재·입장 안내 없음).
        # 발언 분석은 측정용으로만 돌고 진행에는 쓰지 않는다.
        self.baseline = self.config.engine_mode == "baseline"
        self.turn_order: Optional[List[str]] = None  # baseline 고정 발언 순서 (create_discussion이 채움)
        self.post_survey = "standard"  # 사후 설문 문구 (실험 조건 post_survey, create_discussion이 채움)
        self.order_pos = 0
        self.llm_spec: Dict[str, Any] = {}  # 실행 기록용 모델·temperature (create_discussion이 채움)
        self.messages: List[Message] = []

        self.debate = DebateState(DynamicsParams.from_settings(self.config), self.config.commitments_kept)
        for agent in agents:
            self.debate.ensure(agent.persona.name, "ai", agent.stubbornness)

        # 진행 상태
        self.plan = plan_debate(len(agents), max_statements, self.config.max_subtopics,
                                closing_round=self.config.use_closing_round)
        self.propositions: List[str] = []
        self.subtopic_idx = 0
        self.statements_on_subtopic = 0
        self.spoken_in_subtopic: Counter = Counter()
        self.closing_started = False
        self.closing_done: List[str] = []
        self.devils_advocate_used = False
        self.mediations = 0
        self.alternation = 0

        self.turn_count = 0  # AI 발언 수
        self.agent_turn_count = {a.persona.name: 0 for a in agents}
        self.last_speakers: List[str] = []
        self.recent_moves: Dict[str, List[Dict[str, Any]]] = {}  # 화자의 마지막 발언 이후 입장 이동

        # 사람 개입
        self.pending_human: Optional[HumanInput] = None
        self.pending_followups = 0
        self.next_seq = 1
        self.restored = False

    # ---------- 복원 ----------

    def restore(self, prior_messages: List[Message], subtopics: Optional[List[str]] = None,
                current_subtopic: Optional[str] = None, snapshot: Optional[Dict[str, Any]] = None,
                snapshot_seq: Optional[int] = None) -> None:
        """중단된 토론을 저장된 발언과 마지막 상태 스냅숏으로 복원.
        snapshot_seq: 스냅숏이 붙은 메시지 번호. 그 뒤에 저장됐지만 분석 전에 중단된 발언은 진행 상태에 다시 반영한다."""
        self.messages = list(prior_messages)
        for msg in self.messages:
            if msg.role in AI_ROLES:
                self.turn_count += 1
                if msg.agent_name in self.agent_turn_count:
                    self.agent_turn_count[msg.agent_name] += 1
                self.last_speakers = (self.last_speakers + [msg.agent_name])[-3:]
        for agent in self.agents:  # 정해진 발언은 이미 말한 줄 수만큼 넘김
            if agent.scripted:
                agent.script_pos = self.agent_turn_count[agent.persona.name]
        if self.turn_order:
            self._restore_order_pos()
        seqs = [m.metadata.get("seq") for m in self.messages if m.metadata.get("seq")]
        self.next_seq = max(seqs) + 1 if seqs else 1

        spoken = [m for m in self.messages if m.role != "moderator"]
        if spoken and spoken[-1].metadata.get("speaker_type") == "human":
            last = spoken[-1]
            self.pending_human = HumanInput(last.agent_name, last.content, last.metadata.get("seq"))
            self.pending_followups = self.config.human_followup_responses

        if self.moderator and subtopics:
            self.moderator.subtopics = list(subtopics)
            prefix = (current_subtopic or "")[:200]
            self.moderator.current_subtopic_idx = next(
                (i for i, s in enumerate(subtopics) if s[:200] == prefix), 0)
            self.subtopic_idx = self.moderator.current_subtopic_idx
        if snapshot:
            self.subtopic_idx = snapshot.get("subtopic_idx", self.subtopic_idx)
            self.statements_on_subtopic = snapshot.get("statements_on_subtopic", 0)
            self.spoken_in_subtopic = Counter(snapshot.get("spoken_in_subtopic", {}))
            self.closing_started = snapshot.get("closing_started", False)
            self.closing_done = list(snapshot.get("closing_done", []))
            self.devils_advocate_used = snapshot.get("devils_advocate_used", False)
            if snapshot.get("state"):
                self.debate = DebateState.from_snapshot(snapshot["state"], self.debate.params,
                                                        self.config.commitments_kept)
            if snapshot_seq is not None:
                self._replay_after_snapshot(snapshot_seq)
            if self.moderator:
                self.moderator.current_subtopic_idx = self.subtopic_idx
        else:
            self._restore_progress_from_count(subtopics)
        self.restored = True

    def _restore_order_pos(self) -> None:
        """고정 순서에서의 위치: 저장된 본론 발언을 순서표에 차례로 맞춰 본다 (건너뛴 칸 포함)"""
        pos, size = 0, len(self.turn_order)
        for msg in self.messages:
            if msg.role not in AI_ROLES or msg.metadata.get("action") == ActionType.CLOSING.value:
                continue
            for _ in range(size):
                hit = self.turn_order[pos % size] == msg.agent_name
                pos += 1
                if hit:
                    break
        self.order_pos = pos

    def _replay_after_snapshot(self, snapshot_seq: int) -> None:
        """스냅숏 이후 메시지(분석이 저장되기 전에 중단된 발언, 그 뒤의 전환 안내)를 진행 상태에 반영"""
        for msg in self.messages:
            if (msg.metadata.get("seq") or 0) <= snapshot_seq:
                continue
            action = msg.metadata.get("action") or msg.metadata.get("type")
            if msg.role == "moderator":
                if action == "transition":
                    self.subtopic_idx += 1
                    self.statements_on_subtopic = 0
                    self.spoken_in_subtopic.clear()
                    self.devils_advocate_used = False
                    self.debate.reset_subtopic()
                elif action == "closing_announce":
                    self.closing_started = True
            elif msg.role in AI_ROLES:
                if action == ActionType.CLOSING.value:
                    self.closing_done.append(msg.agent_name)
                elif not self.closing_started:
                    self.statements_on_subtopic += 1
                    self.spoken_in_subtopic[msg.agent_name] += 1

    def _restore_progress_from_count(self, subtopics: Optional[List[str]]) -> None:
        """스냅숏이 없는 토론(이전 버전)은 지금까지의 AI 발언 수를 진행 계획에 대입해 위치를 정한다"""
        if subtopics and len(subtopics) != len(self.plan.budgets):
            self.plan.budgets = split_budget(sum(self.plan.budgets), len(subtopics))
        ai_speakers = [m.agent_name for m in self.messages if m.role in AI_ROLES]
        remaining, idx = len(ai_speakers), 0
        while idx < len(self.plan.budgets) - 1 and remaining >= self.plan.budgets[idx]:
            remaining -= self.plan.budgets[idx]
            idx += 1
        body = ai_speakers
        if remaining > self.plan.budgets[idx]:  # 본론을 다 쓰고 종결 라운드 진행 중
            done = remaining - self.plan.budgets[idx]
            self.closing_started = True
            self.closing_done = list(dict.fromkeys(ai_speakers[-done:]))
            body, remaining = ai_speakers[:-done], self.plan.budgets[idx]
        self.subtopic_idx = idx
        self.statements_on_subtopic = remaining
        self.spoken_in_subtopic = Counter(body[len(body) - remaining:] if remaining else [])
        if self.moderator:
            self.moderator.current_subtopic_idx = idx

    def snapshot(self) -> Dict[str, Any]:
        return {
            "subtopic_idx": self.subtopic_idx,
            "statements_on_subtopic": self.statements_on_subtopic,
            "spoken_in_subtopic": dict(self.spoken_in_subtopic),
            "closing_started": self.closing_started,
            "closing_done": self.closing_done,
            "devils_advocate_used": self.devils_advocate_used,
            "state": self.debate.snapshot(),
        }

    # ---------- 실행 ----------

    def set_language(self, topic: str, language: Optional[str] = None) -> None:
        """토론 언어를 정해 참가자·모더레이터에 적용 (지정이 없으면 주제로 감지)"""
        self.language = language = language or LanguageDetector.detect_language(topic)
        for agent in self.agents:
            agent.language = language
        if self.moderator:
            self.moderator.language = language

    def system_prompt_hashes(self) -> Dict[str, str]:
        """참가자별 시스템 프롬프트(페르소나·심은 응답·자료·언어 지시 포함)의 SHA-256 앞 16자리 (실행 기록용)"""
        return {a.persona.name: hashlib.sha256(a._build_system_prompt().encode("utf-8")).hexdigest()[:16]
                for a in self.agents}

    async def stream(self, topic: str, language: Optional[str] = None,
                     gate: Optional[InterventionGate] = None, start_seq: Optional[int] = None) -> AsyncIterator[EngineEvent]:
        """토론 실행. gate가 있으면 발화가 끝날 때마다 사람 개입을 받는다. start_seq: 다음 메시지 순번."""
        if start_seq is not None:
            self.next_seq = start_seq
        self.set_language(topic, language)

        if self.survey and not self.restored:  # 재개한 토론은 사전 설문을 이미 받았음
            async for event in self._run_surveys(PRE):
                yield event

        if self.config.engine_mode == "survey_only":  # 토론 없는 조건: 혼자 다시 답하고 끝냄
            if self.survey:
                key = "post_alone_neutral" if self.post_survey == "neutral" else "post_alone"
                async for event in self._run_surveys(POST, prompt_key=key):
                    yield event
            logger.info("Survey-only run completed")
            return

        if not self.restored:
            if self.fixed_propositions:
                if self.moderator:
                    self.moderator.subtopics = list(self.fixed_propositions)
                    self.moderator.current_subtopic_idx = 0
                yield EngineEvent(kind="subtopics", meta={"subtopics": list(self.fixed_propositions)})
                if self.moderator:
                    yield self._moderator_event(self.moderator.opening(), "opening")
            elif self.moderator:
                subtopics = await self.moderator.generate_subtopics(topic, len(self.plan.budgets))
                if subtopics:
                    yield EngineEvent(kind="subtopics", meta={"subtopics": subtopics})
                    yield self._moderator_event(self.moderator.opening(), "opening")
        self.propositions = ((self.moderator.subtopics if self.moderator else [])
                             or self.fixed_propositions or [topic])
        if len(self.propositions) != len(self.plan.budgets):
            self.plan.budgets = split_budget(sum(self.plan.budgets), len(self.propositions))

        while True:
            if self.pending_followups == 0:
                event, finished = self._advance_phase()
                if event:
                    yield event
                if finished:
                    break

            turn = self._select_turn()
            if turn is None:
                break
            async for event in self._speak(topic, turn):
                yield event
            async for event in self._human_checkpoint(gate):
                yield event

            # 참가자가 2명이면 교착을 중재할 제3자가 없으므로 모더레이터가 지목 질문
            if (self.moderator and len(self.agents) == 2 and not self.closing_started and not self.baseline
                    and self.config.use_stalemate_mediation
                    and self.statements_on_subtopic < self._current_budget()  # 답할 발언이 남아 있을 때만
                    and self.debate.stalemate_pair(self.config.stalemate_exchanges)):
                event = await self._moderator_mediation(topic)
                if event:
                    yield event

        if self.survey:
            key = "post_neutral" if self.post_survey == "neutral" else None
            async for event in self._run_surveys(POST, transcript_text(self.messages), prompt_key=key):
                yield event

        logger.info("Discussion completed: statements=%d messages=%d", self.turn_count, len(self.messages))

    async def _run_surveys(self, phase: str, transcript: str = "",
                           prompt_key: Optional[str] = None) -> AsyncIterator[EngineEvent]:
        """참가자(AI) 전원에게 같은 설문을 독립 호출로 동시에 묻는다 (정해진 발언만 하는 공모자는 제외)"""
        surveyed = [a for a in self.agents if not a.scripted]
        results = await asyncio.gather(*(
            run_survey(a, self.survey, phase, transcript, seeded=a.seed if phase == PRE else None,
                       prompt_key=prompt_key)
            for a in surveyed))
        asked = [row for answers in results for row in answers if row["source"] != "seeded"]
        if asked and all(row["source"] == "missing" for row in asked):
            # 전원이 한 문항도 답하지 못함 = 모델 호출 자체의 실패 (예: 없는 모델). 완료로 기록하지 않는다
            raise SurveyFailed(f"{phase} survey: no participant answered any item")
        for agent, answers in zip(surveyed, results):
            yield EngineEvent(kind="survey", speaker=agent.persona.name, speaker_type="ai",
                              meta={"phase": phase, "answers": answers})

    def _current_budget(self) -> int:
        return self.plan.budgets[min(self.subtopic_idx, len(self.plan.budgets) - 1)]

    def _advance_phase(self) -> Tuple[Optional[EngineEvent], bool]:
        """명제 예산을 다 쓰면 다음 명제·종결 라운드로. (모더레이터 안내 이벤트, 토론 종료 여부)"""
        if self.closing_started:
            return None, len(self.closing_done) >= len(self.agents)
        if self.statements_on_subtopic < self._current_budget():
            return None, False
        if self.subtopic_idx + 1 < len(self.propositions):
            self.subtopic_idx += 1
            self.statements_on_subtopic = 0
            self.spoken_in_subtopic.clear()
            self.devils_advocate_used = False
            self.debate.reset_subtopic()
            if self.moderator:
                return self._moderator_event(self.moderator.advance(), "transition"), False
            return None, False
        if self.plan.closing:
            self.closing_started = True
            if self.moderator:
                return self._moderator_event(self.moderator.closing_announcement(), "closing_announce"), False
            return None, False
        return None, True

    # ---------- 발언자·발화 행위 선택 ----------

    def _agent(self, name: str) -> Optional[DiscussionAgent]:
        return next((a for a in self.agents if a.persona.name == name), None)

    def _least_spoken(self, candidates: List[DiscussionAgent]) -> DiscussionAgent:
        fewest = min(self.spoken_in_subtopic[a.persona.name] for a in candidates)
        pool = [a for a in candidates if self.spoken_in_subtopic[a.persona.name] == fewest]
        fewest_total = min(self.agent_turn_count[a.persona.name] for a in pool)
        return random.choice([a for a in pool if self.agent_turn_count[a.persona.name] == fewest_total])

    def _latest_from_others(self, name: str) -> Optional[Message]:
        """현재 명제에서 다른 참가자(AI·사람)가 한 가장 최근 발언"""
        for msg in reversed(self.messages):
            if msg.metadata.get("subtopic_idx", self.subtopic_idx) != self.subtopic_idx:
                break
            if msg.role != "moderator" and msg.agent_name != name:
                return msg
        return None

    def _message_by_seq(self, seq: Optional[int]) -> Optional[Message]:
        return next((m for m in reversed(self.messages) if seq and m.metadata.get("seq") == seq), None)

    def _select_turn(self) -> Optional[Turn]:
        last = self.last_speakers[-1] if self.last_speakers else None
        others = [a for a in self.agents if a.persona.name != last] or self.agents

        # 1. 사람 발언에 대한 후속 응답
        if self.pending_followups > 0:
            able = [a for a in others if a.can_speak()] or [a for a in self.agents if a.can_speak()]
            return Turn(self._least_spoken(able), ActionType.RESPOND_TO_HUMAN) if able else None

        # 2. 종결 라운드: 아직 마무리하지 않은 참가자 순서대로 (정해진 발언을 다 쓴 참가자는 마무리 없이 끝)
        if self.closing_started:
            for a in self.agents:
                if a.persona.name not in self.closing_done and not a.can_speak():
                    self.closing_done.append(a.persona.name)
            remaining = [a for a in self.agents if a.persona.name not in self.closing_done]
            return Turn(remaining[0], ActionType.CLOSING) if remaining else None

        if self.baseline:
            return self._baseline_turn(last)

        # 3. 입장 표명: 이 명제에서 아직 말하지 않은 참가자 (명제마다 시작 순서를 바꿈)
        offset = self.subtopic_idx % len(self.agents)
        rotated = self.agents[offset:] + self.agents[:offset]
        unspoken = [a for a in rotated if self.spoken_in_subtopic[a.persona.name] == 0]
        if unspoken:
            speaker = unspoken[0]
            return Turn(speaker, ActionType.POSITION, self._latest_from_others(speaker.persona.name))

        names = [a.persona.name for a in others]

        # 4. 교착: 서로 반박만 주고받으면 응답 의무보다 먼저 제3자가 중재하거나 제3안 제시
        pair = self.debate.stalemate_pair(self.config.stalemate_exchanges) if self.config.use_stalemate_mediation else None
        if pair and len(self.agents) >= 3:
            thirds = [a for a in others if a.persona.name not in pair] or [a for a in self.agents if a.persona.name not in pair]
            if thirds:
                self.debate.clear_pair(pair)
                action = ActionType.MEDIATE if self.mediations % 2 == 0 else ActionType.THIRD_OPTION
                self.mediations += 1
                return Turn(self._least_spoken(thirds), action, parties=pair)

        # 5. 응답 의무: 답하지 않은 반박·질문을 받은 참가자
        challenge = self.debate.open_challenge_for(names) if self.config.use_reply_obligation else None
        if challenge:
            speaker = self._agent(challenge.target)
            target = self._message_by_seq(challenge.seq) or self._latest_from_others(speaker.persona.name)
            return Turn(speaker, ActionType.RESPOND_CHALLENGE, target)

        # 6. 성급한 합의: 반박 없이 입장이 모여 있으면 가장 먼 참가자가 반대 검토
        all_names = [a.persona.name for a in self.agents]
        spread = self.debate.spread(all_names)
        if (self.config.use_devils_advocate and not self.devils_advocate_used and self.debate.attacks_in_subtopic == 0
                and spread is not None and spread < self.config.consensus_spread):
            values = {n: self.debate.stance(n) for n in names}
            mean = sum(v for v in self.debate.stances().values() if v is not None) / len(all_names)
            speaker = self._agent(max(values, key=lambda n: abs(values[n] - mean)))
            self.devils_advocate_used = True
            return Turn(speaker, ActionType.DEVILS_ADVOCATE, self._latest_from_others(speaker.persona.name))

        # 7. 기본: 이 명제에서 덜 말한 참가자가 최근 다른 사람 발언에 입장 거리에 맞게 반응
        speaker = self._least_spoken(others)
        target = self._latest_from_others(speaker.persona.name)
        own, theirs = self.debate.stance(speaker.persona.name), self.debate.stance(target.agent_name) if target else None
        self.alternation += 1
        if own is not None and theirs is not None and abs(own - theirs) < self.config.close_stance_distance:
            action = ActionType.AGREE_EXTEND if self.alternation % 2 else ActionType.EXAMPLE
        else:
            action = ActionType.REBUT if self.alternation % 2 else ActionType.UNDERCUT
        return Turn(speaker, action, target)

    def _baseline_turn(self, last: Optional[str]) -> Optional[Turn]:
        """기준선: 참가자 목록(또는 turn_order) 순서대로 돌아가며 발언. 정해진 발언을 다 쓴 참가자는 건너뜀"""
        if self.turn_order:
            for _ in range(len(self.turn_order)):
                agent = self._agent(self.turn_order[self.order_pos % len(self.turn_order)])
                self.order_pos += 1
                if agent.can_speak():
                    return Turn(agent, ActionType.REPLY)
            return None
        names = [a.persona.name for a in self.agents]
        start = (names.index(last) + 1) % len(names) if last in names else 0
        for i in range(len(names)):
            agent = self.agents[(start + i) % len(names)]
            if agent.can_speak():
                return Turn(agent, ActionType.REPLY)
        return None

    # ---------- 발언 ----------

    def _stance_note(self, name: str) -> str:
        prompts = config_loader.prompts
        x = self.debate.stance(name)
        if x is None:
            return prompts.render("turn_actions.stance_unknown")
        labels = prompts.get("turn_actions.stance_labels")
        strong, lean = self.config.stance_strong, self.config.stance_lean
        label = (labels["strong_agree"] if x >= strong else labels["agree"] if x >= lean else
                 labels["undecided"] if x > -lean else labels["disagree"] if x > -strong else labels["strong_disagree"])
        note = prompts.render("turn_actions.stance_current", label=label, value=x)
        moves = self.recent_moves.get(name, [])
        total = sum(m["delta"] for m in moves)
        if abs(total) >= self.config.stance_note_min_shift:
            by = ", ".join(dict.fromkeys(m["by"] for m in moves))
            note += prompts.render("turn_actions.stance_moved", delta=total, by=by)
        return note

    def _build_prompt(self, topic: str, turn: Turn) -> str:
        prompts = config_loader.prompts
        name = turn.speaker.persona.name
        others = [n for n in self.debate.participants if n != name]
        if self.baseline:  # 입장 안내·공약·상호 양보 없이 주제·명제·참가자만
            parts = [prompts.render(
                "turn_actions.baseline_frame", topic=topic,
                proposition=self.propositions[self.subtopic_idx] if self.propositions else topic,
                roster=", ".join(self._describe(n, with_values=False) for n in others))]
            if turn.action == ActionType.RESPOND_TO_HUMAN and self.pending_human:
                parts.append(prompts.render("turn_actions.respond_to_human", human_name=self.pending_human.name,
                                            remark=self.pending_human.content))
            else:
                parts.append(prompts.render(f"turn_actions.{turn.action.value}"))
            return "\n".join(parts)
        commitments = self.debate.participants[name].commitments
        parts = [prompts.render(
            "turn_actions.frame", topic=topic,
            proposition=self.propositions[self.subtopic_idx] if self.propositions else topic,
            roster=", ".join(self._describe(n, with_values=False) for n in others),
            stance_note=self._stance_note(name),
            commitments=" / ".join(commitments) or "(none yet)",
        )]
        # 상호 양보: 내가 마지막으로 말한 뒤 상대가 나에게 인정한 점
        conceded = self.debate.concessions_to(name, self._last_seq_of(name))
        if conceded:
            parts.append(prompts.render("turn_actions.reciprocity", conceded="\n".join(
                f"- {c['by']}: {c['claim']}" for c in conceded)))
        if turn.target is not None and turn.action in TARGETED_ACTIONS + (ActionType.POSITION,):
            parts.append(prompts.render(
                "turn_actions.target_block", target_name=turn.target.agent_name,
                target_seq=turn.target.metadata.get("seq", "?"),
                target_text=turn.target.content[:self.config.context_chars]))
        if turn.action == ActionType.RESPOND_TO_HUMAN and self.pending_human:
            parts.append(prompts.render("turn_actions.respond_to_human", human_name=self.pending_human.name,
                                        remark=self.pending_human.content))
        else:
            party_a, party_b = turn.parties or ("", "")
            parts.append(prompts.render(
                f"turn_actions.{turn.action.value}",
                target_name=turn.target.agent_name if turn.target else "",
                party_a=party_a, party_b=party_b))
        if turn.action in TARGETED_ACTIONS and turn.target is not None:
            parts.append(prompts.render("turn_actions.reply_rules"))
        return "\n".join(parts)

    async def _speak(self, topic: str, turn: Turn) -> AsyncIterator[EngineEvent]:
        speaker, action, name = turn.speaker, turn.action, turn.speaker.persona.name
        prompt = self._build_prompt(topic, turn)

        yield EngineEvent(kind="utterance_start", speaker=name, speaker_type="ai", action=action.value)
        response = ""
        if speaker.scripted:  # 실험 공모자: 정해진 다음 줄 (LLM 호출 없음)
            response = speaker.script[speaker.script_pos]
            speaker.script_pos += 1
            yield EngineEvent(kind="chunk", speaker=name, speaker_type="ai", content=response, action=action.value)
        else:
            async for chunk in speaker.respond_stream(prompt, self.messages):
                response += chunk
                yield EngineEvent(kind="chunk", speaker=name, speaker_type="ai", content=chunk, action=action.value)

        seq = self.next_seq
        self.next_seq += 1
        rag = speaker.last_rag_result
        meta = {
            "seq": seq,
            "turn": self.turn_count,
            "subtopic_idx": self.subtopic_idx,
            "target_seq": turn.target.metadata.get("seq") if turn.target is not None else None,
            "in_reply_to_seq": self.pending_human.seq if action == ActionType.RESPOND_TO_HUMAN and self.pending_human else None,
            "rag_used": rag is not None,
            "rag_query": rag.query if rag else None,
            "sources": rag.sources if rag else None,
        }
        if speaker.scripted:
            meta["scripted"] = True
        if self.config.record_prompts and not speaker.scripted:  # 실험 재현·감사용 (시스템 프롬프트는 페르소나·프롬프트 해시로 재구성 가능)
            meta["prompt"] = prompt
        self.messages.append(Message(role="assistant", content=response, agent_name=name,
                                     metadata={"action": action.value, "speaker_type": "ai", **meta}))
        yield EngineEvent(kind="utterance", speaker=name, speaker_type="ai", content=response,
                          action=action.value, meta=meta)

        # 진행 상태 갱신
        self.turn_count += 1
        self.agent_turn_count[name] += 1
        self.last_speakers = (self.last_speakers + [name])[-3:]
        self.recent_moves[name] = []
        if action == ActionType.RESPOND_TO_HUMAN:
            self.pending_followups -= 1
        if action == ActionType.CLOSING:
            self.closing_done.append(name)
        elif not self.closing_started:  # 사람 응답도 명제 예산을 쓴다 (예산이 끝났으면 추가 발언)
            self.statements_on_subtopic += 1
            self.spoken_in_subtopic[name] += 1

        event = await self._analyze(seq, name, "ai", response)
        if event:
            yield event

    async def _human_checkpoint(self, gate: Optional[InterventionGate]) -> AsyncIterator[EngineEvent]:
        """사람 개입 지점: 받은 발언을 대화에 넣고 분석한 뒤 다음 AI 발언이 응답하도록 예약"""
        if gate is None:
            return
        for human in await gate.after_utterance():
            if human.seq:
                self.next_seq = max(self.next_seq, human.seq + 1)
            self.messages.append(Message(role="user", content=human.content, agent_name=human.name,
                                         metadata={"speaker_type": "human", "seq": human.seq,
                                                   "subtopic_idx": self.subtopic_idx}))
            self.pending_human = human
            self.pending_followups = self.config.human_followup_responses
            self.debate.ensure(human.name, "human")
            event = await self._analyze(human.seq, human.name, "human", human.content)
            if event:
                yield event

    def _moderator_event(self, content: str, msg_type: str) -> EngineEvent:
        seq = self.next_seq
        self.next_seq += 1
        meta = {"seq": seq, "turn": self.turn_count, "subtopic_idx": self.subtopic_idx,
                "subtopic": self.propositions[self.subtopic_idx] if self.propositions else
                (self.moderator.current_subtopic if self.moderator else None)}
        self.messages.append(Message(role="moderator", content=content, agent_name="Moderator",
                                     metadata={"type": msg_type, "speaker_type": "moderator", **meta}))
        return EngineEvent(kind="utterance", speaker="Moderator", speaker_type="moderator",
                           content=content, action=msg_type, meta=meta)

    async def _moderator_mediation(self, topic: str) -> Optional[EngineEvent]:
        pair = self.debate.stalemate_pair(self.config.stalemate_exchanges)
        if not pair:
            return None
        self.debate.clear_pair(pair)
        a, b = pair
        content = await self.moderator.mediation_question(
            topic, a, b, self.debate.participants[a].commitments, self.debate.participants[b].commitments)
        if not content:
            return None
        # 지목받은 참가자에게 응답 의무 (질문 메시지의 seq = 곧 붙을 번호)
        self.debate.challenges.append(Challenge("Moderator", b, self.next_seq, "question", content[:200]))
        return self._moderator_event(content, "mediation")

    # ---------- 발언 분석 ----------

    def _describe(self, name: str, with_values: bool = True) -> str:
        """참가자 이름·역할(·가치) — 분석의 출처 신뢰도·가치 일치 판정과 발언의 호칭에 쓴다"""
        agent = self._agent(name)
        if agent is None:
            return f"{name} (human participant)"
        persona = agent.persona
        values = f"; values: {' / '.join(persona.beliefs[:3])}" if with_values and persona.beliefs else ""
        return f"{name} ({persona.role}{values})"

    def _last_seq_of(self, name: str) -> int:
        return next((m.metadata.get("seq") or 0 for m in reversed(self.messages) if m.agent_name == name), 0)

    async def _analyze(self, seq: Optional[int], speaker: str, kind: str, text: str) -> Optional[EngineEvent]:
        """발언을 구조화 분석해 토론 상태(공약·도전·입장 동역학)에 반영"""
        if self.analyzer is None:
            return None
        prompts = config_loader.prompts
        participants = "\n".join(
            f"- {self._describe(name)}: stance {round(p.x, 2) if p.x is not None else 'null'}"
            for name, p in self.debate.participants.items())
        context = "\n".join(
            f"[#{m.metadata.get('seq')}] {m.agent_name}: {m.content[:self.config.analysis_context_chars]}"
            for m in self.messages[-(self.config.analysis_context_messages + 1):-1] if m.metadata.get("seq"))
        proposition = self.propositions[self.subtopic_idx] if self.propositions else ""
        try:
            result = await structured_output(self.analyzer, UtteranceAnalysis).ainvoke([
                SystemMessage(content=prompts.render("debate_analysis.system")),
                HumanMessage(content=prompts.render(
                    "debate_analysis.user", proposition=proposition, participants=participants,
                    context=context or "(none)", seq=seq, speaker=speaker, utterance=text)),
            ])
        except Exception:
            logger.warning("Utterance analysis failed for #%s %s", seq, speaker, exc_info=True)
            return None

        known_seqs = {m.metadata.get("seq") for m in self.messages}
        analysis = result.model_dump()
        analysis["targets"] = [t for t in analysis["targets"]
                               if t["seq"] in known_seqs and t["seq"] != seq and t["speaker"] in self.debate.participants]
        analysis["concessions"] = [c for c in analysis["concessions"]
                                   if c["to"] in self.debate.participants and c["to"] != speaker and c["claim"]]
        analysis["influence"] = [i for i in analysis["influence"]
                                 if i["listener"] in self.debate.participants
                                 and self.debate.participants[i["listener"]].kind == "ai"]  # 사람 입장은 추정하지 않음
        moves = self.debate.apply(seq, speaker, kind, analysis)
        for move in moves:
            self.recent_moves.setdefault(move["listener"], []).append(move)
        return EngineEvent(kind="analysis", speaker=speaker, meta={
            "seq": seq, "subtopic_idx": self.subtopic_idx, "analysis": analysis, "moves": moves,
            "stances": self.debate.stances(), "debate": self.snapshot(),
        })

