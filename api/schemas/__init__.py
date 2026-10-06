"""
Pydantic 스키마 (요청/응답 모델)
"""
from api.schemas.auth import *
from api.schemas.user import *
from api.schemas.error import *
from api.schemas.discussion import *
from api.schemas.message import *
from api.schemas.analytics import *
from api.schemas.persona import *
from api.schemas.export import *
from api.schemas.config import *

__all__ = [
    # Auth
    "RegisterRequest",
    "RegisterResponse",
    "LoginRequest",
    "LoginResponse",
    "TokenRefreshRequest",
    "TokenRefreshResponse",
    # User
    "UserResponse",
    "UserUpdateRequest",
    "PasswordChangeRequest",
    "UserStatistics",
    "SubscriptionInfo",
    # Error
    "ErrorResponse",
    "ErrorDetail",
    # Discussion
    "CreateDiscussionRequest",
    "CreateDiscussionResponse",
    "DiscussionStatusResponse",
    "DiscussionListResponse",
    "DiscussionStartResponse",
    "DiscussionPauseResponse",
    "DiscussionResumeResponse",
    "StopDiscussionRequest",
    "DiscussionStopResponse",
    # Persona
    "PersonaTemplateResponse",
    "PersonaTemplateListResponse",
    "CustomPersonaCreateRequest",
    "CustomPersonaResponse",
    # Export
    "JSONExportResponse",
    # Config
    "SystemConfigResponse",
    "LLMProvidersResponse",
]

