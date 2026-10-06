"""
토론 데이터베이스 모델
"""
from sqlalchemy import Column, String, DateTime, Integer, Boolean, Text, ForeignKey, Float, JSON
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from api.database import Base
import uuid


class Discussion(Base):
    """토론 모델"""
    __tablename__ = "discussions"
    
    # 기본 정보
    id = Column(String, primary_key=True, default=lambda: f"disc_{uuid.uuid4().hex[:12]}")
    topic = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    
    # 상태
    status = Column(String(20), default="initialized")  # initialized, running, paused, completed, stopped, failed
    
    # 진행 상황
    current_round = Column(Integer, default=0)
    total_rounds = Column(Integer, default=10)
    total_messages = Column(Integer, default=0)
    current_subtopic = Column(String(200), nullable=True)
    
    # 설정 (JSON)
    config = Column(JSON, nullable=False)
    
    # 결과
    consensus_reached = Column(Boolean, default=False)
    consensus_score = Column(Float, nullable=True)
    
    # 소유자 (외래키 제약 제거 - 게스트 지원)
    created_by = Column(String, nullable=False)

    # 타임스탬프
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    started_at = Column(DateTime(timezone=True), nullable=True)
    paused_at = Column(DateTime(timezone=True), nullable=True)
    resumed_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    stopped_at = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # 관계
    participants = relationship("Participant", back_populates="discussion", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Discussion(id={self.id}, topic={self.topic}, status={self.status})>"


class Participant(Base):
    """토론 참가자 모델"""
    __tablename__ = "participants"
    
    # 기본 정보
    id = Column(String, primary_key=True, default=lambda: f"part_{uuid.uuid4().hex[:8]}")
    discussion_id = Column(String, ForeignKey("discussions.id"), nullable=False)
    
    # 페르소나 정보
    name = Column(String(100), nullable=False)
    role = Column(String(200), nullable=False)
    template_id = Column(String(50), nullable=True)
    
    # LLM 설정
    llm_provider = Column(String(50), nullable=False)
    model = Column(String(100), nullable=False)
    
    # 진행 상황
    message_count = Column(Integer, default=0)
    current_openness = Column(Float, default=0.7)
    
    # 페르소나 데이터 (JSON)
    persona_data = Column(JSON, nullable=True)
    
    # 타임스탬프
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # 관계
    discussion = relationship("Discussion", back_populates="participants")
    
    def __repr__(self):
        return f"<Participant(id={self.id}, name={self.name}, role={self.role})>"

