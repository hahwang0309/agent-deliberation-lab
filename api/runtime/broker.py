"""
토론 이벤트 브로커 - 단일 이벤트 루프 전용 Pub/Sub

모든 publish/subscribe는 uvicorn 메인 루프에서만 호출된다(스레드 사용 없음).
구독자 큐가 가득 차면 해당 구독자를 끊는다. 클라이언트는 Last-Event-ID로 재접속해 누락분을 재생한다.
"""
import asyncio
import logging
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Dict, Optional, Set

logger = logging.getLogger(__name__)


@dataclass
class StreamEvent:
    """SSE 이벤트 1건 (id는 저장된 메시지의 seq일 때만 설정)"""
    event: str
    data: Dict[str, Any]
    id: Optional[int] = None


@dataclass(eq=False)
class Subscription:
    queue: asyncio.Queue
    dropped: bool = False  # 큐 초과로 끊김 → 남은 이벤트 소진 후 연결 종료


class EventBroker:
    def __init__(self, max_queue: int = 1000):
        self.max_queue = max_queue
        self._subs: Dict[str, Set[Subscription]] = defaultdict(set)

    def subscribe(self, discussion_id: str) -> Subscription:
        sub = Subscription(queue=asyncio.Queue(maxsize=self.max_queue))
        self._subs[discussion_id].add(sub)
        return sub

    def unsubscribe(self, discussion_id: str, sub: Subscription) -> None:
        subs = self._subs.get(discussion_id)
        if subs is not None:
            subs.discard(sub)
            if not subs:
                del self._subs[discussion_id]

    def publish(self, discussion_id: str, event: str, data: Dict[str, Any], id: Optional[int] = None) -> None:
        item = StreamEvent(event=event, data=data, id=id)
        for sub in list(self._subs.get(discussion_id, ())):
            try:
                sub.queue.put_nowait(item)
            except asyncio.QueueFull:
                logger.warning("Subscriber queue full for %s; dropping subscriber", discussion_id)
                sub.dropped = True
                self.unsubscribe(discussion_id, sub)

    def subscriber_count(self, discussion_id: str) -> int:
        return len(self._subs.get(discussion_id, ()))
