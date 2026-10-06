"""
메시지 데이터베이스 모델
"""
from sqlalchemy import Column, String, DateTime, Integer, Text, ForeignKey, Boolean, Float, JSON
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from api.database import Base
import uuid


class Message(Base):
    """메시지 모델"""
    __tablename__ = "messages"
    
    # 기본 정보
    id = Column(String, primary_key=True, default=lambda: f"msg_{uuid.uuid4().hex[:8]}")
    discussion_id = Column(String, ForeignKey("discussions.id"), nullable=False)
    
    # 발언자
    speaker_id = Column(String, ForeignKey("participants.id"), nullable=False)
    speaker = Column(String(100), nullable=False)  # 이름 (중복 저장)
    
    # 내용
    content = Column(Text, nullable=False)
    
    # 메타데이터
    round_number = Column(Integer, nullable=False)
    message_order = Column(Integer, nullable=False)  # 라운드 내 순서
    
    # RAG 정보
    rag_used = Column(Boolean, default=False)
    rag_query = Column(String(500), nullable=True)
    rag_classification = Column(String(50), nullable=True)  # factual, opinion, etc.
    sources = Column(JSON, nullable=True)  # [{url, title, relevance_score, ...}]
    
    # 통계
    character_count = Column(Integer, default=0)
    word_count = Column(Integer, default=0)
    sentence_count = Column(Integer, default=0)
    
    # 감정 분석
    sentiment_score = Column(Float, nullable=True)  # -1.0 ~ 1.0
    sentiment_label = Column(String(20), nullable=True)  # positive, negative, neutral
    sentiment_confidence = Column(Float, nullable=True)
    
    # 타임스탬프
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    
    # 관계
    discussion = relationship("Discussion")
    participant = relationship("Participant")
    
    def __repr__(self):
        return f"<Message(id={self.id}, speaker={self.speaker}, round={self.round_number})>"

