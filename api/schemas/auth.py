"""
인증 관련 스키마
"""
from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import Optional
from datetime import datetime
import re


class RegisterRequest(BaseModel):
    """회원가입 요청"""
    email: EmailStr = Field(..., max_length=255, description="이메일 주소")
    password: str = Field(..., min_length=8, description="비밀번호 (최소 8자, 영문+숫자+특수문자)")
    name: str = Field(..., min_length=2, max_length=50, description="이름")
    organization: Optional[str] = Field(None, max_length=100, description="조직/회사명")
    
    @field_validator('password')
    @classmethod
    def validate_password(cls, v: str) -> str:
        """비밀번호 유효성 검사"""
        if len(v) < 8:
            raise ValueError('비밀번호는 최소 8자 이상이어야 합니다.')
        if not re.search(r'[A-Za-z]', v):
            raise ValueError('비밀번호는 영문자를 포함해야 합니다.')
        if not re.search(r'\d', v):
            raise ValueError('비밀번호는 숫자를 포함해야 합니다.')
        if not re.search(r'[!@#$%^&*(),.?":{}|<>]', v):
            raise ValueError('비밀번호는 특수문자를 포함해야 합니다.')
        return v
    
    class Config:
        json_schema_extra = {
            "example": {
                "email": "user@example.com",
                "password": "SecurePass123!",
                "name": "김철수",
                "organization": "테크 스타트업"
            }
        }


class RegisterResponse(BaseModel):
    """회원가입 응답"""
    user_id: str
    email: str
    name: str
    organization: Optional[str] = None
    created_at: datetime
    
    class Config:
        from_attributes = True


class LoginRequest(BaseModel):
    """로그인 요청"""
    email: EmailStr
    password: str
    
    class Config:
        json_schema_extra = {
            "example": {
                "email": "user@example.com",
                "password": "SecurePass123!"
            }
        }


class UserInfo(BaseModel):
    """사용자 정보 (로그인 응답용)"""
    id: str
    email: str
    name: str
    organization: Optional[str] = None
    
    class Config:
        from_attributes = True


class LoginResponse(BaseModel):
    """로그인 응답"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = 3600
    user: UserInfo


class TokenRefreshRequest(BaseModel):
    """토큰 갱신 요청"""
    refresh_token: str


class TokenRefreshResponse(BaseModel):
    """토큰 갱신 응답"""
    access_token: str
    token_type: str = "bearer"
    expires_in: int = 3600

