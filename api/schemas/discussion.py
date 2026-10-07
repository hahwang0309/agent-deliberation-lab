"""
토론 관련 스키마
"""
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from config.config_loader import config_loader
from src.core.experiment import ExperimentConfig
from src.services.survey import SurveyConfig

_limits = config_loader.config.limits

LLMProviderName = Literal["openai", "claude", "gemini", "mistral"]


class PersonaInput(BaseModel):
    """토론 참가 페르소나 (템플릿·자동 생성 결과를 그대로 넣거나 직접 작성)"""
    name: str = Field(..., min_length=1, max_length=100)
    role: str = Field(..., min_length=1, max_length=200)
    background: str = Field("", max_length=2000)
    personality: List[str] = Field(default_factory=list)
    expertise: List[str] = Field(default_factory=list)
    communication_style: str = Field("", max_length=500)
    beliefs: List[str] = Field(default_factory=list)
    template_id: Optional[str] = Field(None, max_length=50)
    llm_provider: Optional[LLMProviderName] = Field(None, description="비우면 config.yaml llm.default_provider")
    model: Optional[str] = Field(None, max_length=100, description="비우면 config.yaml 기본 모델")


class CreateDiscussionRequest(BaseModel):
    """토론 생성 요청"""
    topic: str = Field(..., min_length=2, max_length=200)
    description: Optional[str] = Field(None, max_length=2000)
    language: Optional[Literal["ko", "en"]] = Field(None, description="비우면 주제로 자동 감지")
    personas: List[PersonaInput] = Field(..., min_length=_limits.min_personas, max_length=_limits.max_personas)
    max_statements: int = Field(_limits.default_statements, ge=2, le=_limits.max_statements,
                                description="AI 발언 수 (모더레이터 발언 제외)")
    use_moderator: bool = True
    enable_web_search: bool = False
    enable_belief_reasoning: bool = False
    propositions: Optional[List[str]] = Field(
        None, max_length=5, description="고정 명제 (지정하면 모더레이터가 명제를 만들지 않음)")
    materials: Optional[str] = Field(None, max_length=20000, description="모든 참가자에게 주는 배경 자료집")
    survey: Optional[SurveyConfig] = Field(
        None, description="사전·사후 설문 문항 (AI 참가자에게 토론 전후로 독립 호출로 묻는다)")
    experiment: Optional[ExperimentConfig] = Field(
        None, description="실험 조건 (진행 장치 on/off, 동역학 파라미터, 참가자별 고집도·temperature, 분석 모델)")


class ParticipantResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    role: str
    llm_provider: str
    model: str
    message_count: int = 0
    persona_data: Optional[Dict[str, Any]] = None


class DiscussionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    topic: str
    description: Optional[str] = None
    language: Optional[str] = None
    status: str
    error: Optional[str] = None
    config: Dict[str, Any]
    subtopics: Optional[List[str]] = None
    current_subtopic: Optional[str] = None
    total_messages: int = 0
    last_seq: int = 0
    consensus_score: Optional[float] = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    llm_calls: int = 0
    created_by: str
    created_by_name: Optional[str] = None
    stopped_by: Optional[str] = None
    stop_reason: Optional[str] = None
    created_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    stopped_at: Optional[datetime] = None
    participants: List[ParticipantResponse] = Field(default_factory=list)


class DiscussionListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    topic: str
    status: str
    total_messages: int = 0
    consensus_score: Optional[float] = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    created_by: str
    created_by_name: Optional[str] = None
    created_at: Optional[datetime] = None


class DiscussionListResponse(BaseModel):
    items: List[DiscussionListItem]
    total: int
    page: int
    page_size: int


class StopDiscussionRequest(BaseModel):
    reason: Optional[str] = Field(None, max_length=500)
