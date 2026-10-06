"""
사용자 관련 스키마
"""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class UserStatistics(BaseModel):
    """사용자 통계"""
    total_discussions: int = 0
    completed_discussions: int = 0
    active_discussions: int = 0


class SubscriptionFeatures(BaseModel):
    """구독 기능"""
    max_concurrent_discussions: int
    max_participants: int
    enable_rag: bool


class SubscriptionInfo(BaseModel):
    """구독 정보"""
    plan: str
    expires_at: Optional[datetime] = None
    features: SubscriptionFeatures


class UserResponse(BaseModel):
    """사용자 정보 응답"""
    id: str
    email: str
    name: str
    organization: Optional[str] = None
    created_at: datetime
    statistics: UserStatistics
    subscription: SubscriptionInfo
    
    class Config:
        from_attributes = True


class UserUpdateRequest(BaseModel):
    """사용자 정보 수정 요청"""
    name: Optional[str] = Field(None, min_length=2, max_length=50)
    organization: Optional[str] = Field(None, max_length=100)
    
    class Config:
        json_schema_extra = {
            "example": {
                "name": "김철수",
                "organization": "새로운 회사"
            }
        }


class PasswordChangeRequest(BaseModel):
    """비밀번호 변경 요청"""
    current_password: str
    new_password: str = Field(..., min_length=8)
    
    class Config:
        json_schema_extra = {
            "example": {
                "current_password": "OldPass123!",
                "new_password": "NewPass456!"
            }
        }


class MessageResponse(BaseModel):
    """일반 메시지 응답"""
    message: str
    updated_at: Optional[datetime] = None

