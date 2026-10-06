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
    consensus_score = Column(Float, nullable=True)  # 종합
    ai_score = Column(Float, nullable=True)
    human_score = Column(Float, nullable=True)
    consensus_label = Column(String(20), nullable=True)  # agreed | partial | disagreed
    model = Column(String(100), nullable=True)
    error = Column(Text, nullable=True)
    requested_at = Column(DateTime(timezone=True), server_default=func.now())
    generated_at = Column(DateTime(timezone=True), nullable=True)
