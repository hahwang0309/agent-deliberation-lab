"""
메시지 데이터베이스 모델
"""
from sqlalchemy import Column, String, DateTime, Integer, Text, ForeignKey, Boolean, JSON, Index
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from api.database import Base
import uuid


class SpeakerType:
    """발언자 유형"""
    AI = "ai"
    MODERATOR = "moderator"
    HUMAN = "human"
    SYSTEM = "system"


class Message(Base):
    """메시지 모델 - 토론 내 완성된 발언 1건"""
    __tablename__ = "messages"
    __table_args__ = (
        Index("ux_messages_discussion_seq", "discussion_id", "seq", unique=True),
    )

    # 기본 정보
    id = Column(String, primary_key=True, default=lambda: f"msg_{uuid.uuid4().hex[:8]}")
    discussion_id = Column(String, ForeignKey("discussions.id"), nullable=False)
    seq = Column(Integer, nullable=False)  # 토론 내 1부터 증가하는 순번 (SSE 이벤트 id)

    # 발언자
    speaker_type = Column(String(20), nullable=False, default=SpeakerType.AI)
    speaker_id = Column(String, ForeignKey("participants.id"), nullable=True)  # AI 참가자
    user_id = Column(String, nullable=True)  # 사람 참가자
    speaker = Column(String(100), nullable=False)  # 표시 이름

    # 내용
    content = Column(Text, nullable=False)
    action = Column(String(30), nullable=True)  # position, rebut, ..., transition, closing_announce
    meta = Column(JSON, nullable=True)

    # RAG 정보
    rag_used = Column(Boolean, default=False)
    rag_query = Column(String(500), nullable=True)
    sources = Column(JSON, nullable=True)

    # 타임스탬프
    timestamp = Column(DateTime(timezone=True), server_default=func.now())

    # 관계
    discussion = relationship("Discussion")
    participant = relationship("Participant")

    def __repr__(self):
        return f"<Message(id={self.id}, seq={self.seq}, speaker={self.speaker})>"
