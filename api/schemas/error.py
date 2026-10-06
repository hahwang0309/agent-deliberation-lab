"""
에러 응답 스키마
"""
from pydantic import BaseModel
from typing import Optional


class ErrorDetail(BaseModel):
    """에러 상세 정보"""
    code: str
    message: str
    field: Optional[str] = None
    retry_after: Optional[int] = None


class ErrorResponse(BaseModel):
    """에러 응답"""
    error: ErrorDetail
    
    class Config:
        json_schema_extra = {
            "example": {
                "error": {
                    "code": "INVALID_CREDENTIALS",
                    "message": "이메일 또는 비밀번호가 올바르지 않습니다."
                }
            }
        }

