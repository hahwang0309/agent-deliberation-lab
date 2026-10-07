"""
토론 데이터베이스 모델
"""
from sqlalchemy import Column, String, DateTime, Integer, Text, ForeignKey, Float, JSON
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from api.database import Base
import uuid


class DiscussionStatus:
    """토론 상태 값"""
    DRAFT = "draft"
    RUNNING = "running"
    AWAITING_HUMAN = "awaiting_human"
    REPORTING = "reporting"
    COMPLETED = "completed"
    STOPPED = "stopped"
    FAILED = "failed"
    INTERRUPTED = "interrupted"  # 서버 재시작으로 중단됨

    ACTIVE = (RUNNING, AWAITING_HUMAN, REPORTING)
    TERMINAL = (COMPLETED, STOPPED, FAILED, INTERRUPTED)


class Discussion(Base):
    """토론 모델"""
    __tablename__ = "discussions"

    # 기본 정보
    id = Column(String, primary_key=True, default=lambda: f"disc_{uuid.uuid4().hex[:12]}")
    topic = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    language = Column(String(10), nullable=True)  # ko, en (없으면 주제로 자동 감지)

    # 상태 (DiscussionStatus)
    status = Column(String(20), default=DiscussionStatus.DRAFT)
    error = Column(Text, nullable=True)

    # 진행 상황
    total_messages = Column(Integer, default=0)
    last_seq = Column(Integer, default=0, nullable=False)  # 마지막 메시지 seq
    current_subtopic = Column(String(200), nullable=True)
    subtopics = Column(JSON, nullable=True)

    # 설정 (JSON): max_statements, use_moderator, enable_web_search, enable_belief_reasoning
    config = Column(JSON, nullable=False)
    run_info = Column(JSON, nullable=True)  # 실행 기록 목록 (시작·재개마다 1개, src/utils/run_info.py)

    # 결과
    consensus_score = Column(Float, nullable=True)

    # LLM 사용량
    prompt_tokens = Column(Integer, default=0, nullable=False)
    completion_tokens = Column(Integer, default=0, nullable=False)
    llm_calls = Column(Integer, default=0, nullable=False)

    # 소유자·중지 정보
    created_by = Column(String, nullable=False)
    stopped_by = Column(String, nullable=True)
    stop_reason = Column(Text, nullable=True)

    # 타임스탬프
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    started_at = Column(DateTime(timezone=True), nullable=True)
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
