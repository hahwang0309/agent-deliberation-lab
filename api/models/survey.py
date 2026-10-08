"""
사전·사후 설문 응답 모델 (참가자 × 문항 × 시점 1행)
"""
import uuid

from sqlalchemy import JSON, Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.sql import func

from api.database import Base


class SurveyResponse(Base):
    __tablename__ = "survey_responses"

    id = Column(String, primary_key=True, default=lambda: f"srv_{uuid.uuid4().hex[:12]}")
    discussion_id = Column(String, ForeignKey("discussions.id", ondelete="CASCADE"), nullable=False, index=True)
    phase = Column(String(10), nullable=False)             # pre | post
    participant = Column(String(100), nullable=False)      # 참가자 이름 (AI 페르소나 또는 사람 표시 이름)
    participant_type = Column(String(10), nullable=False)  # ai | human
    user_id = Column(String, nullable=True)                # 사람 참가자
    item_id = Column(String(30), nullable=False)
    score = Column(Integer, nullable=True)                 # likert 점수. 답하지 않았으면 NULL
    scale = Column(Integer, nullable=False)                # likert 최댓값
    scale_min = Column(Integer, nullable=True)             # likert 최솟값 (NULL은 이전 기록 = 1)
    choices = Column(JSON, nullable=True)                  # choice 문항의 선택 보기
    correct = Column(Boolean, nullable=True)               # 정답이 지정된 choice 문항의 정답 여부
    source = Column(String(10), nullable=True)             # answered | seeded | missing
    reason = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
