"""
토론 관련 스키마
"""
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Literal
from datetime import datetime


# ========================================
# 토론 설정
# ========================================

class DiscussionConfig(BaseModel):
    """토론 설정"""
    max_rounds: int = Field(10, ge=1, le=20, description="최대 라운드 수")
    min_rounds: int = Field(5, ge=1, le=20, description="최소 라운드 수")
    enable_rag: bool = Field(True, description="RAG 활성화")
    enable_subtopics: bool = Field(True, description="소주제 활성화")
    enable_reflection: bool = Field(True, description="성찰 활성화")
    reflection_interval: int = Field(3, ge=1, le=5, description="성찰 간격")
    enable_persona_evolution: bool = Field(True, description="페르소나 진화 활성화")
    
    @field_validator('min_rounds')
    @classmethod
    def validate_min_rounds(cls, v, info):
        """최소 라운드가 최대 라운드보다 작거나 같아야 함"""
        if 'max_rounds' in info.data and v > info.data['max_rounds']:
            raise ValueError('min_rounds는 max_rounds보다 작거나 같아야 합니다.')
        return v


class ParticipantRequest(BaseModel):
    """참가자 요청"""
    template_id: str = Field(..., description="페르소나 템플릿 ID")
    llm_provider: Literal["openai", "claude", "gemini", "mistral"] = Field(..., description="LLM 제공자")
    model: str = Field(..., description="모델명")
    
    class Config:
        json_schema_extra = {
            "example": {
                "template_id": "safety_researcher",
                "llm_provider": "openai",
                "model": "gpt-4"
            }
        }


# ========================================
# 토론 생성
# ========================================

class CreateDiscussionRequest(BaseModel):
    """토론 생성 요청"""
    topic: str = Field(..., min_length=10, max_length=200, description="토론 주제")
    description: Optional[str] = Field(None, max_length=1000, description="토론 설명")
    participants: List[ParticipantRequest] = Field(..., min_length=2, max_length=5, description="참가자 목록")
    config: DiscussionConfig = Field(default_factory=DiscussionConfig, description="토론 설정")
    
    class Config:
        json_schema_extra = {
            "example": {
                "topic": "AI 규제, 혁신과 안전의 균형점은?",
                "description": "AI 기술이 빠르게 발전하면서 규제의 필요성과 혁신의 자유 사이에서 최적의 균형점을 찾고자 합니다.",
                "participants": [
                    {
                        "template_id": "safety_researcher",
                        "llm_provider": "openai",
                        "model": "gpt-4"
                    },
                    {
                        "template_id": "tech_innovator",
                        "llm_provider": "claude",
                        "model": "claude-3-opus-20240229"
                    }
                ],
                "config": {
                    "max_rounds": 10,
                    "min_rounds": 5,
                    "enable_rag": True
                }
            }
        }


class ParticipantResponse(BaseModel):
    """참가자 응답"""
    id: str
    name: str
    role: str
    llm_provider: str
    model: str
    message_count: Optional[int] = 0
    current_openness: Optional[float] = None
    
    class Config:
        from_attributes = True


class CreateDiscussionResponse(BaseModel):
    """토론 생성 응답"""
    discussion_id: str
    status: str
    topic: str
    description: Optional[str]
    participants: List[ParticipantResponse]
    config: DiscussionConfig
    created_at: datetime
    created_by: str
    stream_url: str
    estimated_duration_minutes: int
    
    class Config:
        from_attributes = True


# ========================================
# 토론 상태 조회
# ========================================

class TimestampsResponse(BaseModel):
    """타임스탬프 응답"""
    created_at: datetime
    started_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    elapsed_seconds: Optional[int] = None
    estimated_remaining_seconds: Optional[int] = None
    duration_seconds: Optional[int] = None


class DiscussionStatusResponse(BaseModel):
    """토론 상태 응답"""
    discussion_id: str
    status: str
    topic: str
    description: Optional[str]
    current_round: int
    total_rounds: int
    total_messages: int
    current_subtopic: Optional[str]
    participants: List[ParticipantResponse]
    config: DiscussionConfig
    timestamps: TimestampsResponse
    created_by: str
    consensus_reached: Optional[bool] = None
    consensus_score: Optional[float] = None


# ========================================
# 토론 목록 조회
# ========================================

class DiscussionListItem(BaseModel):
    """토론 목록 아이템"""
    discussion_id: str
    topic: str
    status: str
    current_round: int
    total_rounds: int
    total_messages: int
    participant_count: int
    consensus_reached: Optional[bool] = None
    timestamps: TimestampsResponse


class PaginationResponse(BaseModel):
    """페이지네이션 응답"""
    page: int
    limit: int
    total: int
    total_pages: int
    has_next: bool
    has_prev: bool


class FiltersResponse(BaseModel):
    """필터 응답"""
    status: Optional[str] = None
    sort: str = "created_at"
    order: str = "desc"
    search: Optional[str] = None


class DiscussionListResponse(BaseModel):
    """토론 목록 응답"""
    discussions: List[DiscussionListItem]
    pagination: PaginationResponse
    filters: FiltersResponse


# ========================================
# 토론 제어 (시작, 일시정지, 재개, 종료)
# ========================================

class DiscussionStartResponse(BaseModel):
    """토론 시작 응답"""
    discussion_id: str
    status: str
    started_at: datetime
    estimated_completion: Optional[datetime]


class DiscussionPauseResponse(BaseModel):
    """토론 일시정지 응답"""
    discussion_id: str
    status: str
    previous_status: str
    paused_at: datetime
    current_round: int
    message: str


class DiscussionResumeResponse(BaseModel):
    """토론 재개 응답"""
    discussion_id: str
    status: str
    previous_status: str
    resumed_at: datetime
    message: str


class StopDiscussionRequest(BaseModel):
    """토론 종료 요청"""
    reason: Optional[str] = Field(None, max_length=500, description="종료 사유")


class DiscussionSummary(BaseModel):
    """토론 요약"""
    total_rounds: int
    total_messages: int
    duration_seconds: int
    consensus_reached: bool
    consensus_score: Optional[float]


class DiscussionStopResponse(BaseModel):
    """토론 종료 응답"""
    discussion_id: str
    status: str
    previous_status: str
    stopped_at: datetime
    summary: DiscussionSummary
    message: str

