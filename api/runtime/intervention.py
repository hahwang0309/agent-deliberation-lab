"""
사람 참가자 개입 - 발언 대기열과 발언권 (런타임 1건당 1개, 메모리 상태)

흐름: 발언 요청(대기열 등록) → 진행 중인 AI 발화가 끝나면 엔진이 after_utterance() 호출 →
대기열 첫 사람에게 발언권 부여, 토론은 awaiting_human 상태로 입력을 무기한 대기 →
제출(저장·발행) / 본인 취소 / 생성자·관리자 회수 / 토론 중지로 발언권 종료 → 다음 사람 → 대기열이 비면 재개.
"""
import asyncio
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Deque, Dict, List, Optional

from api.models.discussion import DiscussionStatus
from api.models.message import SpeakerType
from config.config_loader import config_loader
from src.core.natural_discussion import HumanInput

if TYPE_CHECKING:
    from api.runtime.runtime import DiscussionRuntime

OPEN_STATUSES = (DiscussionStatus.RUNNING, DiscussionStatus.AWAITING_HUMAN)


class InterventionError(Exception):
    def __init__(self, status_code: int, code: str, message: str):
        super().__init__(message)
        self.status_code, self.code, self.message = status_code, code, message


@dataclass
class HandRaise:
    user_id: str
    name: str
    raised_at: str


@dataclass
class Floor:
    user_id: str
    name: str
    floor_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    done: asyncio.Event = field(default_factory=asyncio.Event)
    speech: Optional[str] = None
    reason: Optional[str] = None  # 발언 없이 끝난 사유: cancelled | revoked | stopped


class HumanDesk:
    def __init__(self, runtime: "DiscussionRuntime"):
        self.rt = runtime
        self.queue: Deque[HandRaise] = deque()
        self.floor: Optional[Floor] = None
        self.turns: Dict[str, int] = {}
        self.display_names: Dict[str, str] = {}

    # ---------- 조회 ----------

    def state(self) -> Dict[str, Any]:
        return {
            "queue": [{"user_id": h.user_id, "name": h.name} for h in self.queue],
            "floor": ({"user_id": self.floor.user_id, "name": self.floor.name, "floor_id": self.floor.floor_id}
                      if self.floor else None),
        }

    def _publish_state(self) -> None:
        self.rt.broker.publish(self.rt.discussion_id, "hand_queue", self.state())

    def _display_name(self, user_id: str, name: str) -> str:
        """보고서에서 참가자를 이름으로 구분하므로 페르소나·다른 사람과 겹치지 않는 이름을 쓴다"""
        if user_id not in self.display_names:
            taken = set(self.rt.persona_names) | set(self.display_names.values())
            self.display_names[user_id] = name if name not in taken else f"{name} ({user_id[-4:]})"
        return self.display_names[user_id]

    # ---------- 사용자 동작 ----------

    def raise_hand(self, user_id: str, name: str) -> int:
        """대기열 등록. 이미 등록·발언 중이면 현재 순번을 돌려준다 (0 = 발언권 보유)."""
        if self.rt.status not in OPEN_STATUSES:
            raise InterventionError(409, "NOT_ACCEPTING", "진행 중인 토론에서만 발언을 요청할 수 있습니다.")
        if self.floor and self.floor.user_id == user_id:
            return 0
        for position, hand in enumerate(self.queue, start=1):
            if hand.user_id == user_id:
                return position
        limit = config_loader.config.limits.max_human_turns_per_user
        if self.turns.get(user_id, 0) >= limit:
            raise InterventionError(429, "HUMAN_TURN_LIMIT", f"이 토론에서는 {limit}번까지 발언할 수 있습니다.")
        self.queue.append(HandRaise(user_id, self._display_name(user_id, name),
                                    datetime.now(timezone.utc).isoformat()))
        self._publish_state()
        return len(self.queue)

    def cancel(self, user_id: str) -> None:
        """본인 요청 취소 또는 보유 중인 발언권 포기"""
        if self.floor and self.floor.user_id == user_id:
            self._end_floor(reason="cancelled")
            return
        before = len(self.queue)
        self.queue = deque(h for h in self.queue if h.user_id != user_id)
        if len(self.queue) == before:
            raise InterventionError(409, "NOT_IN_QUEUE", "발언 요청 중이 아닙니다.")
        self._publish_state()

    def revoke(self) -> None:
        """생성자·관리자가 현재 발언권 회수"""
        if not self.floor:
            raise InterventionError(409, "NO_FLOOR", "발언권을 가진 사람이 없습니다.")
        self._end_floor(reason="revoked")

    def submit(self, user_id: str, floor_id: str, content: str) -> None:
        if not self.floor or self.floor.user_id != user_id:
            raise InterventionError(403, "NOT_YOUR_TURN", "지금은 발언권이 없습니다.")
        if self.floor.floor_id != floor_id:
            raise InterventionError(409, "STALE_FLOOR", "이미 종료된 발언권입니다.")
        content = content.strip()
        if not content:
            raise InterventionError(422, "EMPTY_SPEECH", "발언 내용을 입력하세요.")
        max_chars = config_loader.config.limits.max_human_chars
        if len(content) > max_chars:
            raise InterventionError(422, "SPEECH_TOO_LONG", f"발언은 {max_chars}자 이하여야 합니다.")
        self.floor.speech = content
        self.floor.done.set()

    def abort(self) -> None:
        """토론 중지 시: 발언권·대기열 정리"""
        if self.floor:
            self._end_floor(reason="stopped")
        if self.queue:
            self.queue.clear()
            self._publish_state()

    def _end_floor(self, reason: str) -> None:
        self.floor.reason = reason
        self.floor.done.set()

    # ---------- 엔진 개입 지점 (InterventionGate) ----------

    async def after_utterance(self) -> List[HumanInput]:
        inputs: List[HumanInput] = []
        paused = False
        try:
            while self.queue:
                if not paused:  # 상태를 먼저 기록해 발언권이 보이는 시점엔 항상 awaiting_human
                    await self.rt.set_status(DiscussionStatus.AWAITING_HUMAN)
                    paused = True
                if not self.queue:  # 상태 기록 중 취소된 경우
                    break
                hand = self.queue.popleft()
                floor = self.floor = Floor(hand.user_id, hand.name)
                self.rt.broker.publish(self.rt.discussion_id, "floor_granted",
                                       {"user_id": floor.user_id, "name": floor.name, "floor_id": floor.floor_id})
                self._publish_state()

                await floor.done.wait()  # 무기한 대기 (제출·취소·회수·중지)
                self.floor = None
                if floor.speech is not None:
                    message = await self.rt.save_and_publish(SpeakerType.HUMAN, floor.name, floor.speech,
                                                             action="human", user_id=floor.user_id)
                    self.turns[floor.user_id] = self.turns.get(floor.user_id, 0) + 1
                    inputs.append(HumanInput(floor.name, floor.speech, message["seq"], floor.user_id))
                else:
                    self.rt.broker.publish(self.rt.discussion_id, "floor_released",
                                           {"user_id": floor.user_id, "name": floor.name, "reason": floor.reason})
                self._publish_state()
        finally:
            if self.floor is not None:  # 대기 중 토론이 중지됨 (CancelledError)
                self.rt.broker.publish(self.rt.discussion_id, "floor_released",
                                       {"user_id": self.floor.user_id, "name": self.floor.name, "reason": "stopped"})
                self.floor = None
        if paused:
            await self.rt.set_status(DiscussionStatus.RUNNING)
        return inputs
