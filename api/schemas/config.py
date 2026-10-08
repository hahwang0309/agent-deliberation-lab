"""
설정 API 스키마
"""
from datetime import datetime
from typing import List, Dict, Optional
from pydantic import BaseModel


# ========================================
# 시스템 설정 스키마
# ========================================

class SystemInfo(BaseModel):
    """시스템 정보"""
    version: str
    environment: str
    api_version: str
    server_time: datetime
    uptime_seconds: int


class Features(BaseModel):
    """기능 활성화 여부"""
    rag_enabled: bool
    subtopics_enabled: bool
    reflection_enabled: bool
    persona_evolution_enabled: bool
    custom_personas_enabled: bool
    export_enabled: bool


class Limits(BaseModel):
    """시스템 제한"""
    max_discussions_per_user: int
    max_concurrent_discussions: int
    max_participants_per_discussion: int
    max_rounds: int
    max_message_length: int
    max_custom_personas: int


class RateLimits(BaseModel):
    """API 요청 제한"""
    auth_requests_per_minute: int
    discussion_create_per_hour: int
    api_requests_per_minute: int
    sse_connections: int


class SystemConfigResponse(BaseModel):
    """시스템 설정 응답"""
    system: SystemInfo
    features: Features
    limits: Limits
    rate_limits: RateLimits


# ========================================
# LLM 프로바이더 스키마
# ========================================

class LLMModelInfo(BaseModel):
    """LLM 모델 정보 (확인하지 않은 값은 null)"""
    id: str
    name: str
    version: Optional[str] = None
    context_window: Optional[int] = None
    max_tokens: Optional[int] = None
    cost_per_1k_input_tokens: Optional[float] = None
    cost_per_1k_output_tokens: Optional[float] = None
    available: bool


class LLMProviderStatus(BaseModel):
    """LLM 프로바이더 상태"""
    available: bool
    status: str  # operational, degraded, unavailable
    response_time_ms: Optional[int] = None
    reason: Optional[str] = None  # unavailable일 때 이유
    last_checked: datetime
    models: List[LLMModelInfo]


class LLMProvidersResponse(BaseModel):
    """LLM 프로바이더 목록 응답"""
    providers: Dict[str, LLMProviderStatus]
    total_available: int
    total_unavailable: int
    last_updated: datetime

