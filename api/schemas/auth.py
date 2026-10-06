"""
인증·계정 스키마
"""
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str
    name: str
    organization: Optional[str] = None
    role: str
    status: str
    must_change_password: bool = False
    created_at: Optional[datetime] = None
    last_login_at: Optional[datetime] = None


class SignupRequest(BaseModel):
    email: EmailStr = Field(..., max_length=255)
    password: str = Field(..., max_length=200)
    name: str = Field(..., min_length=1, max_length=50)
    organization: Optional[str] = Field(None, max_length=100)
    note: Optional[str] = Field(None, max_length=1000, description="가입 사유 (관리자 승인 참고)")


class LoginRequest(BaseModel):
    # 등록된 이메일을 조회만 하므로 형식 검사 없음 (ADMIN_EMAIL에 예약 도메인을 쓴 경우에도 로그인 가능)
    email: str = Field(..., min_length=3, max_length=255)
    password: str = Field(..., max_length=200)


class UpdateMeRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=50)
    organization: Optional[str] = Field(None, max_length=100)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(..., max_length=200)
    new_password: str = Field(..., max_length=200)


# ---------- 관리자 ----------

class AdminUserResponse(UserResponse):
    signup_note: Optional[str] = None
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None
    max_concurrent: Optional[int] = None
    daily_limit: Optional[int] = None


class IssueUserRequest(BaseModel):
    email: EmailStr = Field(..., max_length=255)
    name: str = Field(..., min_length=1, max_length=50)
    organization: Optional[str] = Field(None, max_length=100)
    role: Literal["user", "admin"] = "user"


class UpdateUserRequest(BaseModel):
    role: Optional[Literal["user", "admin"]] = None
    max_concurrent: Optional[int] = Field(None, ge=0, le=100, description="NULL이면 기본값")
    daily_limit: Optional[int] = Field(None, ge=0, le=1000, description="NULL이면 기본값")
    clear_limits: bool = Field(False, description="true면 사용자별 제한을 지우고 기본값 사용")


class TempPasswordResponse(BaseModel):
    user: AdminUserResponse
    temp_password: str = Field(description="1회만 표시. 사용자는 첫 로그인 후 변경해야 함")
