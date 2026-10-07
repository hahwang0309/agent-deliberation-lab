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
from api.models.message import Message, SpeakerType
from api.models.report import DiscussionReport, ReportStatus


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
            "subtopics": d.subtopics or [],
            "current_subtopic": d.current_subtopic,
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


def update_message_meta(discussion_id: str, seq: int, extra: Dict[str, Any]) -> None:
    """메시지 meta에 키를 추가·갱신 (발언 분석 결과 등)"""
    with session_scope() as db:
        msg = (db.query(Message).filter(Message.discussion_id == discussion_id, Message.seq == seq).first())
        if msg is not None:
            msg.meta = {**(msg.meta or {}), **extra}


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
    """서버 시작 시: 이전 프로세스에서 실행 중이던 토론은 interrupted, 생성 중이던 보고서는 failed로 표시"""
    with session_scope() as db:
        (db.query(DiscussionReport)
         .filter(DiscussionReport.status == ReportStatus.PENDING)
         .update({DiscussionReport.status: ReportStatus.FAILED, DiscussionReport.error: "server restarted"},
                 synchronize_session=False))
        return (db.query(Discussion)
                .filter(Discussion.status.in_(DiscussionStatus.ACTIVE))
                .update({Discussion.status: DiscussionStatus.INTERRUPTED,
                         Discussion.error: "server restarted"},
                        synchronize_session=False))


def count_ai_messages(discussion_id: str) -> int:
    with session_scope() as db:
        return (db.query(func.count(Message.id))
                .filter(Message.discussion_id == discussion_id, Message.speaker_type == SpeakerType.AI)
                .scalar())


def load_transcript(discussion_id: str) -> Dict[str, Any]:
    """보고서 생성 입력: 주제·언어·참가자(이름→ai|human)·전체 발언"""
    with session_scope() as db:
        d = db.get(Discussion, discussion_id)
        messages = (db.query(Message).filter(Message.discussion_id == discussion_id)
                    .order_by(Message.seq).all())
        participants = {p.name: "ai" for p in
                        db.query(Participant).filter(Participant.discussion_id == discussion_id)
                        .order_by(Participant.created_at, Participant.id)}
        for m in messages:
            if m.speaker_type == SpeakerType.HUMAN:
                participants.setdefault(m.speaker, "human")
        return {
            "topic": d.topic,
            "language": d.language,
            "participants": participants,
            "transcript": [{"seq": m.seq, "speaker": m.speaker, "speaker_type": m.speaker_type,
                            "content": m.content} for m in messages],
            # 입장 동역학 요약 입력 (발언별 토론 상태)
            "subtopics": list(d.subtopics or []),
            "records": [{"seq": m.seq, "speaker": m.speaker, "speaker_type": m.speaker_type,
                         "action": m.action, "meta": m.meta or {}} for m in messages],
        }


def mark_report_pending(discussion_id: str) -> None:
    with session_scope() as db:
        report = db.get(DiscussionReport, discussion_id) or DiscussionReport(discussion_id=discussion_id)
        report.status = ReportStatus.PENDING
        report.error = None
        report.requested_at = utcnow()
        db.add(report)


def save_report(discussion_id: str, content: Dict[str, Any], model: Optional[str]) -> None:
    scores = content["scores"]
    with session_scope() as db:
        report = db.get(DiscussionReport, discussion_id)
        report.status = ReportStatus.READY
        report.content = content
        report.consensus_score = scores["overall"]
        report.ai_score = scores["ai"]
        report.human_score = scores["human"]
        report.ai_human_score = scores.get("ai_human")
        report.consensus_label = content.get("label")
        report.model = model
        report.error = None
        report.generated_at = utcnow()
        db.get(Discussion, discussion_id).consensus_score = scores["overall"]


def fail_report(discussion_id: str, error: str) -> None:
    with session_scope() as db:
        report = db.get(DiscussionReport, discussion_id)
        if report is not None:
            report.status = ReportStatus.FAILED
            report.error = error
