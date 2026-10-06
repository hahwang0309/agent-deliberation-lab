"""
토론 메시지 조회 및 실시간 이벤트(SSE) 라우터
"""
import asyncio
import json
from typing import Optional

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from api.database import get_db
from api.dependencies import require_active_user
from api.models.discussion import DiscussionStatus
from api.runtime import broker, registry
from api.runtime import persistence
from api.schemas.message import MessageListResponse
from api.services.discussion_service import DiscussionService

router = APIRouter(prefix="/api/v1/discussions", tags=["Messages"], dependencies=[Depends(require_active_user)])

HEARTBEAT_SECONDS = 15


def _sse(event: str, data: dict, event_id: Optional[int] = None) -> str:
    lines = []
    if event_id is not None:
        lines.append(f"id: {event_id}")
    lines.append(f"event: {event}")
    lines.append(f"data: {json.dumps(data, ensure_ascii=False, default=str)}")
    return "\n".join(lines) + "\n\n"


@router.get("/{discussion_id}/messages", response_model=MessageListResponse, summary="메시지 목록 (seq 이후)")
def list_messages(discussion_id: str, after_seq: int = Query(0, ge=0), limit: int = Query(200, ge=1, le=1000),
                  db: Session = Depends(get_db)):
    discussion = DiscussionService.get(db, discussion_id)
    items = persistence.list_messages_after(discussion_id, after_seq, limit)
    return MessageListResponse(items=items, last_seq=discussion.last_seq or 0)


@router.get("/{discussion_id}/events", summary="실시간 토론 이벤트 (SSE)")
async def stream_events(discussion_id: str, request: Request,
                        since: int = Query(0, ge=0, description="이 seq 이후 메시지부터 재생"),
                        last_event_id: Optional[str] = Header(None, alias="Last-Event-ID"),
                        db: Session = Depends(get_db)):
    """연결 시: (1) 구독 → (2) 놓친 메시지 재생 → (3) 현재 상태 snapshot → (4) 실시간 이벤트.

    재접속 시 브라우저가 보내는 Last-Event-ID(마지막으로 받은 메시지 seq)부터 이어 받는다.
    """
    DiscussionService.get(db, discussion_id)
    start_after = int(last_event_id) if last_event_id and last_event_id.isdigit() else since

    async def generate():
        sub = broker.subscribe(discussion_id)  # 재생 전에 구독해 사이 이벤트 유실 방지
        try:
            last_sent = start_after
            for message in await asyncio.to_thread(persistence.list_messages_after, discussion_id, start_after, 10000):
                yield _sse("message", message, message["seq"])
                last_sent = message["seq"]

            runtime = registry.get(discussion_id)
            if runtime is not None:
                snapshot = runtime.snapshot()
            else:
                snapshot = {"status": await asyncio.to_thread(persistence.get_status, discussion_id),
                            "last_seq": last_sent, "current_utterance": None}
            yield _sse("snapshot", snapshot)
            if runtime is None and snapshot["status"] in DiscussionStatus.TERMINAL:
                return

            while True:
                if await request.is_disconnected():
                    return
                try:
                    item = await asyncio.wait_for(sub.queue.get(), timeout=HEARTBEAT_SECONDS)
                except asyncio.TimeoutError:
                    if sub.dropped:
                        return
                    yield ": ping\n\n"
                    continue
                if item.event == "message":
                    if item.id <= last_sent:
                        continue
                    last_sent = item.id
                yield _sse(item.event, item.data, item.id)
                if item.event == "status" and item.data.get("status") in DiscussionStatus.TERMINAL:
                    return
        finally:
            broker.unsubscribe(discussion_id, sub)

    return StreamingResponse(generate(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
