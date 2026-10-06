"""행정조사 분석 결과 모델"""
from sqlalchemy import Column, String, DateTime, Text, JSON, Float, Integer, Index
from api.database import Base
from api.utils.datetime_utils import utc_now


class InvestigationAnalysis(Base):
    """행정조사 중복 판별 분석 결과"""
    __tablename__ = "investigation_analyses"

    id = Column(String(36), primary_key=True, index=True)  # UUID
    user_id = Column(String(36), index=True, nullable=False)  # 요청한 사용자

    # 입력 정보
    investigation_a_name = Column(String(200), nullable=False)
    investigation_b_name = Column(String(200), nullable=False)
    investigation_a_data = Column(JSON, nullable=False)  # 전체 조사 A 정보
    investigation_b_data = Column(JSON, nullable=False)  # 전체 조사 B 정보

    # 상태
    status = Column(String(20), nullable=False, default="processing", index=True)  # processing, completed, failed

    # 결과 (완료 시)
    result_data = Column(JSON, nullable=True)  # 전체 분석 결과 (페르소나, 토론, 보고서 등)
    final_verdict = Column(String(50), nullable=True, index=True)  # 최종 판정
    confidence = Column(Float, nullable=True)  # 신뢰도
    total_rounds = Column(Integer, nullable=True)  # 총 라운드 수 (빠른 조회용)

    # 타임스탬프
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now, index=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # 복합 인덱스 (자주 사용되는 쿼리 패턴)
    __table_args__ = (
        Index('ix_status_created', 'status', 'created_at'),
        Index('ix_user_created', 'user_id', 'created_at'),
    )
    
    def __repr__(self):
        return f"<InvestigationAnalysis {self.id}: {self.investigation_a_name} vs {self.investigation_b_name}>"

