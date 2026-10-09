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
from api.models.survey import SurveyResponse


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


def append_run_info(discussion_id: str, info: Dict[str, Any]) -> None:
    with session_scope() as db:
        d = db.get(Discussion, discussion_id)
        if d is not None:
            d.run_info = [*(d.run_info or []), info]


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


def add_usage(discussion_id: str, prompt_tokens: int, completion_tokens: int, llm_calls: int,
              by_model: Optional[Dict[str, Dict[str, int]]] = None) -> None:
    """누적 토큰·호출 수. 모델별 사용량은 이번 실행 기록(run_info 마지막 항목)에 남긴다 (참가자·분석 모델이 다를 때 비용 계산용)"""
    with session_scope() as db:
        d = db.get(Discussion, discussion_id)
        if d is None:
            return
        d.prompt_tokens = (d.prompt_tokens or 0) + prompt_tokens
        d.completion_tokens = (d.completion_tokens or 0) + completion_tokens
        d.llm_calls = (d.llm_calls or 0) + llm_calls
        if by_model and d.run_info:
            merged = {m: dict(u) for m, u in (d.run_info[-1].get("usage_by_model") or {}).items()}
            for model, u in by_model.items():  # 보고서 생성도 같은 실행 기록에 더한다
                cur = merged.setdefault(model, {"input_tokens": 0, "output_tokens": 0})
                cur["input_tokens"] += u.get("input_tokens", 0)
                cur["output_tokens"] += u.get("output_tokens", 0)
            d.run_info = [*d.run_info[:-1], {**d.run_info[-1], "usage_by_model": merged}]


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


def save_survey(discussion_id: str, phase: str, participant: str, participant_type: str,
                answers: List[Dict[str, Any]], user_id: Optional[str] = None) -> None:
    """참가자 1명의 설문 응답 저장 (문항마다 1행)"""
    with session_scope() as db:
        for a in answers:
            db.add(SurveyResponse(discussion_id=discussion_id, phase=phase, participant=participant,
                                  participant_type=participant_type, user_id=user_id, item_id=a["item_id"],
                                  score=a.get("score"), scale=a["scale"], scale_min=a.get("scale_min"),
                                  choices=a.get("choices"), correct=a.get("correct"), source=a.get("source"),
                                  reason=a.get("reason") or None))


def list_survey(discussion_id: str) -> List[Dict[str, Any]]:
    with session_scope() as db:
        rows = (db.query(SurveyResponse).filter(SurveyResponse.discussion_id == discussion_id)
                .order_by(SurveyResponse.created_at, SurveyResponse.participant, SurveyResponse.item_id).all())
        return [{"phase": r.phase, "participant": r.participant, "participant_type": r.participant_type,
                 "item_id": r.item_id, "score": r.score, "scale": r.scale,
                 "scale_min": r.scale_min if r.scale_min is not None else 1, "choices": r.choices,
                 "correct": r.correct, "source": r.source, "reason": r.reason} for r in rows]


def export_bundle(discussion_id: str) -> Dict[str, Any]:
    """분석용 추출 입력: 토론·참가자·실행 기록·사용량·보고서 점수·전체 메시지·설문"""
    with session_scope() as db:
        d = db.get(Discussion, discussion_id)
        if d is None:
            raise LookupError(discussion_id)
        report = db.get(DiscussionReport, discussion_id)
        participants = (db.query(Participant).filter(Participant.discussion_id == discussion_id)
                        .order_by(Participant.created_at, Participant.id).all())
        discussion = {
            "id": d.id, "topic": d.topic, "language": d.language, "status": d.status,
            "config": dict(d.config or {}), "run_info": d.run_info or [], "subtopics": d.subtopics or [],
            "prompt_tokens": d.prompt_tokens, "completion_tokens": d.completion_tokens, "llm_calls": d.llm_calls,
            "started_at": d.started_at.isoformat() if d.started_at else None,
            "completed_at": d.completed_at.isoformat() if d.completed_at else None,
            "participants": [{"name": p.name, "role": p.role, "provider": p.llm_provider, "model": p.model}
                             for p in participants],
            "report": ({"status": report.status, "consensus_score": report.consensus_score, "ai_score": report.ai_score,
                        "human_score": report.human_score, "ai_human_score": report.ai_human_score,
                        "label": report.consensus_label} if report else None),
        }
    return {"discussion": discussion, "messages": list_messages_after(discussion_id, 0, 100000),
            "survey": list_survey(discussion_id)}


def experiment_discussion_ids(label: Optional[str] = None, batch: Optional[str] = None) -> List[str]:
    """실험 조건 label·배치 이름으로 고른 토론 id (생성 순). 둘 다 주면 둘 다 맞는 것"""
    with session_scope() as db:
        # created_at은 초 단위라 같은 초에 만든 토론의 순서가 정해지지 않으므로 시작 시각(마이크로초)으로 보강
        rows = (db.query(Discussion.id, Discussion.config)
                .order_by(Discussion.created_at, Discussion.started_at, Discussion.id).all())
    result = []
    for discussion_id, config in rows:
        exp = (config or {}).get("experiment") or {}
        if exp and (label is None or exp.get("label") == label) and (batch is None or exp.get("batch") == batch):
            result.append(discussion_id)
    return result
