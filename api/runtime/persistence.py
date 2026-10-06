"""
토론 런타임 DB 접근 (동기 함수)

런타임은 asyncio.to_thread로 호출한다. 각 함수는 자체 세션으로 짧은 트랜잭션을 수행한다.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Dict, Iterator, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from api.database import SessionLocal
from api.models.discussion import Discussion, DiscussionStatus, Participant
from api.models.message import Message


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@contextmanager
def session_scope() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def serialize_message(m: Message) -> Dict[str, Any]:
    return {
        "id": m.id,
        "seq": m.seq,
        "speaker_type": m.speaker_type,
        "speaker": m.speaker,
        "participant_id": m.speaker_id,
        "user_id": m.user_id,
        "content": m.content,
        "action": m.action,
        "meta": m.meta or {},
        "rag_used": bool(m.rag_used),
        "sources": m.sources or [],
        "timestamp": m.timestamp.isoformat() if m.timestamp else None,
    }


def load_discussion(discussion_id: str) -> Dict[str, Any]:
    """런타임 시작에 필요한 토론·참가자 정보"""
    with session_scope() as db:
        d = db.get(Discussion, discussion_id)
        if d is None:
            raise LookupError(discussion_id)
        participants = (db.query(Participant)
                        .filter(Participant.discussion_id == discussion_id)
                        .order_by(Participant.created_at, Participant.id).all())
        return {
            "id": d.id,
            "topic": d.topic,
            "description": d.description,
            "language": d.language,
            "status": d.status,
            "config": dict(d.config or {}),
            "last_seq": d.last_seq or 0,
            "participants": [
                {"id": p.id, "name": p.name, "provider": p.llm_provider, "model": p.model,
                 "persona": p.persona_data or {}}
                for p in participants
            ],
        }


def get_status(discussion_id: str) -> Optional[str]:
    with session_scope() as db:
        d = db.get(Discussion, discussion_id)
        return d.status if d else None


def update_discussion(discussion_id: str, **fields: Any) -> None:
    with session_scope() as db:
        d = db.get(Discussion, discussion_id)
        if d is None:
            return
        for key, value in fields.items():
            setattr(d, key, value)


def save_message(discussion_id: str, seq: int, speaker_type: str, speaker: str, content: str,
                 action: Optional[str] = None, meta: Optional[Dict[str, Any]] = None,
                 participant_id: Optional[str] = None, user_id: Optional[str] = None) -> Dict[str, Any]:
    """완성된 발언 저장 + 토론의 last_seq/total_messages 갱신"""
    meta = dict(meta or {})
    with session_scope() as db:
        msg = Message(
            discussion_id=discussion_id, seq=seq, speaker_type=speaker_type,
            speaker_id=participant_id, user_id=user_id, speaker=speaker,
            content=content, action=action, meta=meta,
            rag_used=bool(meta.get("rag_used")), rag_query=meta.get("rag_query"),
            sources=meta.get("sources"), timestamp=utcnow(),
        )
        db.add(msg)
        d = db.get(Discussion, discussion_id)
        d.last_seq = seq
        d.total_messages = (d.total_messages or 0) + 1
        if participant_id:
            p = db.get(Participant, participant_id)
            if p:
                p.message_count = (p.message_count or 0) + 1
        db.flush()
        return serialize_message(msg)


def list_messages_after(discussion_id: str, after_seq: int = 0, limit: int = 1000) -> List[Dict[str, Any]]:
    with session_scope() as db:
        rows = (db.query(Message)
                .filter(Message.discussion_id == discussion_id, Message.seq > after_seq)
                .order_by(Message.seq).limit(limit).all())
        return [serialize_message(m) for m in rows]


def add_usage(discussion_id: str, prompt_tokens: int, completion_tokens: int, llm_calls: int) -> None:
    with session_scope() as db:
        d = db.get(Discussion, discussion_id)
        if d is None:
            return
        d.prompt_tokens = (d.prompt_tokens or 0) + prompt_tokens
        d.completion_tokens = (d.completion_tokens or 0) + completion_tokens
        d.llm_calls = (d.llm_calls or 0) + llm_calls


def mark_active_as_interrupted() -> int:
    """서버 시작 시: 이전 프로세스에서 실행 중이던 토론을 interrupted로 표시"""
    with session_scope() as db:
        return (db.query(Discussion)
                .filter(Discussion.status.in_(DiscussionStatus.ACTIVE))
                .update({Discussion.status: DiscussionStatus.INTERRUPTED,
                         Discussion.error: "server restarted"},
                        synchronize_session=False))


def count_active() -> int:
    with session_scope() as db:
        return db.query(func.count(Discussion.id)).filter(Discussion.status.in_(DiscussionStatus.ACTIVE)).scalar()
