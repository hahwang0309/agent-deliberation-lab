"""배치 분석 모델"""
from sqlalchemy import Column, String, DateTime, Integer, Float, ForeignKey, JSON
from sqlalchemy.orm import relationship
from api.database import Base
from api.utils.datetime_utils import utc_now


class BatchAnalysis(Base):
    """배치 분석 작업"""
    __tablename__ = "batch_analyses"

    id = Column(String(36), primary_key=True, index=True)  # UUID
    user_id = Column(String(36), index=True, nullable=False)  # 요청한 사용자
    
    # 배치 정보
    name = Column(String(200), nullable=False)  # 배치 이름
    description = Column(String(500), nullable=True)  # 설명
    
    # 상태
    status = Column(String(20), nullable=False, default="pending")  # pending, processing, paused, completed, failed
    
    # 진행 상황
    total_count = Column(Integer, nullable=False, default=0)  # 전체 항목 수
    completed_count = Column(Integer, nullable=False, default=0)  # 완료된 항목 수
    failed_count = Column(Integer, nullable=False, default=0)  # 실패한 항목 수
    
    # 설정
    config = Column(JSON, nullable=True)  # 분석 설정 (persona_count, min_rounds, max_rounds 등)
    
    # 타임스탬프
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    started_at = Column(DateTime(timezone=True), nullable=True)
    paused_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    
    # 관계
    items = relationship("BatchAnalysisItem", back_populates="batch", cascade="all, delete-orphan")
    
    @property
    def progress_percentage(self) -> float:
        """진행률 (%)"""
        if self.total_count == 0:
            return 0.0
        return (self.completed_count / self.total_count) * 100
    
    def __repr__(self):
        return f"<BatchAnalysis {self.id}: {self.name} ({self.completed_count}/{self.total_count})>"


class BatchAnalysisItem(Base):
    """배치 분석 항목"""
    __tablename__ = "batch_analysis_items"

    id = Column(String(36), primary_key=True, index=True)  # UUID
    batch_id = Column(String(36), ForeignKey("batch_analyses.id"), nullable=False, index=True)
    
    # 순서 및 식별
    sequence = Column(Integer, nullable=False)  # 배치 내 순서
    item_name = Column(String(200), nullable=True)  # 항목 이름 (선택)
    
    # 입력 데이터
    investigation_a_data = Column(JSON, nullable=False)
    investigation_b_data = Column(JSON, nullable=False)
    investigation_a_name = Column(String(200), nullable=False)
    investigation_b_name = Column(String(200), nullable=False)
    
    # 상태
    status = Column(String(20), nullable=False, default="pending")  # pending, processing, completed, failed, skipped
    
    # 결과
    analysis_id = Column(String(36), nullable=True, index=True)  # InvestigationAnalysis.id 참조
    final_verdict = Column(String(50), nullable=True)
    confidence = Column(Float, nullable=True)
    error_message = Column(String(500), nullable=True)  # 실패 시 에러 메시지
    
    # 타임스탬프
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    
    # 관계
    batch = relationship("BatchAnalysis", back_populates="items")
    
    def __repr__(self):
        return f"<BatchAnalysisItem {self.id}: {self.investigation_a_name} vs {self.investigation_b_name} ({self.status})>"

