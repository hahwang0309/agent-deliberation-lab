"""
실시간 이벤트 브로커
토론 메시지를 실시간으로 SSE 클라이언트에게 전송하기 위한 Pub/Sub 패턴
"""
import asyncio
from typing import Dict, Set
from dataclasses import dataclass
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


@dataclass
class StreamEvent:
    """스트리밍 이벤트"""
    discussion_id: str
    event_type: str
    data: dict
    timestamp: datetime = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.utcnow()


class DiscussionEventBroker:
    """
    토론 이벤트 브로커 (Singleton)

    실시간으로 토론 이벤트를 여러 SSE 클라이언트에게 전송
    """
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        # discussion_id -> Set[Queue]
        self.subscribers: Dict[str, Set[asyncio.Queue]] = {}
        self._lock = asyncio.Lock()
        self._initialized = True
        logger.info("DiscussionEventBroker initialized")

    async def subscribe(self, discussion_id: str) -> asyncio.Queue:
        """
        특정 토론에 대한 이벤트 구독

        Args:
            discussion_id: 토론 ID

        Returns:
            이벤트를 받을 Queue
        """
        queue = asyncio.Queue(maxsize=100)  # 최대 100개 이벤트 버퍼

        async with self._lock:
            if discussion_id not in self.subscribers:
                self.subscribers[discussion_id] = set()
            self.subscribers[discussion_id].add(queue)

        logger.info(f"New subscriber for discussion {discussion_id}. Total: {len(self.subscribers[discussion_id])}")
        return queue

    async def unsubscribe(self, discussion_id: str, queue: asyncio.Queue):
        """
        구독 해제

        Args:
            discussion_id: 토론 ID
            queue: 구독 시 받은 Queue
        """
        async with self._lock:
            if discussion_id in self.subscribers:
                self.subscribers[discussion_id].discard(queue)

                # 구독자가 없으면 제거
                if not self.subscribers[discussion_id]:
                    del self.subscribers[discussion_id]
                    logger.info(f"No more subscribers for discussion {discussion_id}")

    async def publish(self, discussion_id: str, event_type: str, data: dict):
        """
        이벤트 발행

        Args:
            discussion_id: 토론 ID
            event_type: 이벤트 타입 (message, round_start, etc.)
            data: 이벤트 데이터
        """
        event = StreamEvent(
            discussion_id=discussion_id,
            event_type=event_type,
            data=data
        )

        async with self._lock:
            if discussion_id not in self.subscribers:
                logger.debug(f"No subscribers for discussion {discussion_id}")
                return

            # 모든 구독자에게 전송
            dead_queues = set()
            for queue in self.subscribers[discussion_id]:
                try:
                    # 논블로킹으로 전송
                    queue.put_nowait(event)
                except asyncio.QueueFull:
                    logger.warning(f"Queue full for discussion {discussion_id}, dropping event")
                    dead_queues.add(queue)
                except Exception as e:
                    logger.error(f"Error publishing to queue: {e}")
                    dead_queues.add(queue)

            # 죽은 큐 제거
            for queue in dead_queues:
                self.subscribers[discussion_id].discard(queue)

        logger.debug(f"Published {event_type} to {len(self.subscribers.get(discussion_id, []))} subscribers")

    def get_subscriber_count(self, discussion_id: str) -> int:
        """
        특정 토론의 구독자 수 조회

        Args:
            discussion_id: 토론 ID

        Returns:
            구독자 수
        """
        return len(self.subscribers.get(discussion_id, set()))

    def get_all_discussions(self) -> list:
        """
        현재 구독 중인 모든 토론 ID 목록

        Returns:
            토론 ID 리스트
        """
        return list(self.subscribers.keys())


# 싱글톤 인스턴스
event_broker = DiscussionEventBroker()
