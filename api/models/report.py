"""
토론 종합보고서 모델 (토론과 1:1)
"""
from sqlalchemy import Column, String, DateTime, Text, ForeignKey, Float, JSON
from sqlalchemy.sql import func
from api.database import Base


class ReportStatus:
    PENDING = "pending"
    READY = "ready"
    FAILED = "failed"


class DiscussionReport(Base):
    __tablename__ = "discussion_reports"

    discussion_id = Column(String, ForeignKey("discussions.id", ondelete="CASCADE"), primary_key=True)
    status = Column(String(20), nullable=False, default=ReportStatus.PENDING)
    content = Column(JSON, nullable=True)  # src.services.consensus_report 보고서 본문
    consensus_score = Column(Float, nullable=True)  # 종합 (모든 참가자 쌍)
    ai_score = Column(Float, nullable=True)         # AI간
    human_score = Column(Float, nullable=True)      # 인간간 (사람 2명 이상일 때만)
    ai_human_score = Column(Float, nullable=True)   # AI-인간간 (사람이 참여했을 때만)
    consensus_label = Column(String(20), nullable=True)  # agreed | partial | disagreed
    model = Column(String(100), nullable=True)
    error = Column(Text, nullable=True)
    requested_at = Column(DateTime(timezone=True), server_default=func.now())
    generated_at = Column(DateTime(timezone=True), nullable=True)
