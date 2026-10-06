"""
메시지 관련 스키마
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Literal
from datetime import datetime


# ========================================
# 소스 정보
# ========================================

class SourceInfo(BaseModel):
    """출처 정보"""
    url: str
    title: str
    relevance_score: float
    content_snippet: Optional[str] = None
    published_date: Optional[str] = None


# ========================================
# 메시지 목록 조회
# ========================================

class MessageListItem(BaseModel):
    """메시지 목록 아이템"""
    id: str
    speaker: str
    content: str
    timestamp: datetime
    round: int = Field(..., alias="round_number")
    rag_used: bool
    rag_query: Optional[str] = None
    sources: Optional[List[SourceInfo]] = None
    character_count: int
    word_count: int
    
    class Config:
        from_attributes = True
        populate_by_name = True


class MessageFilters(BaseModel):
    """메시지 필터"""
    speaker: Optional[str] = None
    round: Optional[int] = None
    rag_only: Optional[bool] = None
    search: Optional[str] = None


class PaginationResponse(BaseModel):
    """페이지네이션 응답"""
    page: int
    limit: int
    total: int
    total_pages: int
    has_next: bool
    has_prev: bool


class MessageListResponse(BaseModel):
    """메시지 목록 응답"""
    discussion_id: str
    messages: List[MessageListItem]
    pagination: PaginationResponse
    filters: MessageFilters


# ========================================
# 메시지 상세 조회
# ========================================

class PersonaInfo(BaseModel):
    """페르소나 정보"""
    name: str
    role: str
    current_beliefs: List[str]
    current_openness: float


class MessageStatistics(BaseModel):
    """메시지 통계"""
    character_count: int
    word_count: int
    sentence_count: int


class SentimentInfo(BaseModel):
    """감정 분석"""
    score: float
    label: Literal["positive", "negative", "neutral"]
    confidence: float


class MessageDetailResponse(BaseModel):
    """메시지 상세 응답"""
    id: str
    discussion_id: str
    speaker: str
    persona: PersonaInfo
    content: str
    timestamp: datetime
    round: int
    rag_used: bool
    rag_query: Optional[str] = None
    rag_classification: Optional[str] = None
    sources: Optional[List[SourceInfo]] = None
    statistics: MessageStatistics
    sentiment: Optional[SentimentInfo] = None


# ========================================
# SSE 이벤트
# ========================================

class SSEEvent(BaseModel):
    """SSE 이벤트"""
    id: str
    event: str
    data: dict
    
    def to_sse(self) -> str:
        """SSE 형식으로 변환"""
        import json
        lines = []
        lines.append(f"id: {self.id}")
        lines.append(f"event: {self.event}")
        lines.append(f"data: {json.dumps(self.data, ensure_ascii=False)}")
        lines.append("")
        return "\n".join(lines) + "\n"


# 각 이벤트별 데이터 스키마
class DiscussionStartedData(BaseModel):
    discussion_id: str
    timestamp: datetime


class RoundStartData(BaseModel):
    round_number: int
    current_subtopic: str
    timestamp: datetime


class RoundEndData(BaseModel):
    round_number: int
    total_messages: int
    timestamp: datetime


class RAGSearchData(BaseModel):
    speaker: str
    query: str
    status: str
    timestamp: datetime


class MessageData(BaseModel):
    message_id: str
    speaker: str
    content: str
    round: int
    rag_used: bool
    sources: Optional[List[str]] = None
    timestamp: datetime


class ReflectionItem(BaseModel):
    speaker: str
    reflection: str


class ReflectionData(BaseModel):
    round_number: int
    reflections: List[ReflectionItem]
    timestamp: datetime


class PersonaEvolvedData(BaseModel):
    persona: str
    changes: dict
    timestamp: datetime


class SubtopicChangeData(BaseModel):
    previous_subtopic: str
    new_subtopic: str
    round_number: int
    timestamp: datetime


class DiscussionPausedData(BaseModel):
    reason: str
    timestamp: datetime


class DiscussionResumedData(BaseModel):
    timestamp: datetime


class DiscussionCompletedData(BaseModel):
    discussion_id: str
    total_rounds: int
    total_messages: int
    duration_seconds: int
    consensus_reached: bool
    consensus_summary: str
    timestamp: datetime


class ErrorData(BaseModel):
    code: str
    message: str
    retry_count: int
    timestamp: datetime

