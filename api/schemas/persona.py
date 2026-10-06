"""
페르소나 API 스키마
"""
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field, field_validator


# ========================================
# 템플릿 페르소나 스키마
# ========================================

class PersonaTemplateResponse(BaseModel):
    """페르소나 템플릿 응답"""
    id: str = Field(..., description="템플릿 ID")
    name: str = Field(..., description="페르소나 이름")
    role: str = Field(..., description="역할")
    background: str = Field(..., description="배경")
    expertise: List[str] = Field(..., description="전문 분야")
    personality: List[str] = Field(..., description="성격 특성")
    communication_style: str = Field(..., description="커뮤니케이션 스타일")
    beliefs: List[str] = Field(..., description="신념/가치관")
    default_llm: str = Field(..., description="기본 LLM 제공자")
    default_model: str = Field(..., description="기본 모델")
    initial_openness: float = Field(..., ge=0.0, le=1.0, description="초기 개방성")
    tags: List[str] = Field(..., description="태그")


class PersonaTemplateListResponse(BaseModel):
    """페르소나 템플릿 목록 응답"""
    templates: List[PersonaTemplateResponse]
    total_count: int


# ========================================
# 커스텀 페르소나 스키마
# ========================================

class CustomPersonaCreateRequest(BaseModel):
    """커스텀 페르소나 생성 요청"""
    name: str = Field(..., min_length=2, max_length=50, description="페르소나 이름")
    role: str = Field(..., min_length=2, max_length=100, description="역할")
    background: Optional[str] = Field(None, max_length=500, description="배경")
    expertise: List[str] = Field(..., min_length=1, max_length=10, description="전문 분야")
    personality: List[str] = Field(..., min_length=1, max_length=5, description="성격 특성")
    communication_style: str = Field(..., description="커뮤니케이션 스타일")
    beliefs: List[str] = Field(..., min_length=1, max_length=5, description="신념/가치관")
    initial_openness: float = Field(0.5, ge=0.0, le=1.0, description="초기 개방성")
    llm_provider: str = Field("openai", description="LLM 제공자")
    model: str = Field("gpt-4", description="모델")
    
    @field_validator('expertise')
    @classmethod
    def validate_expertise(cls, v):
        """전문 분야 검증"""
        if not v or len(v) < 1:
            raise ValueError('expertise는 최소 1개 이상이어야 합니다.')
        if len(v) > 10:
            raise ValueError('expertise는 최대 10개까지 가능합니다.')
        return v
    
    @field_validator('personality')
    @classmethod
    def validate_personality(cls, v):
        """성격 특성 검증"""
        if not v or len(v) < 1:
            raise ValueError('personality는 최소 1개 이상이어야 합니다.')
        if len(v) > 5:
            raise ValueError('personality는 최대 5개까지 가능합니다.')
        return v
    
    @field_validator('beliefs')
    @classmethod
    def validate_beliefs(cls, v):
        """신념 검증"""
        if not v or len(v) < 1:
            raise ValueError('beliefs는 최소 1개 이상이어야 합니다.')
        if len(v) > 5:
            raise ValueError('beliefs는 최대 5개까지 가능합니다.')
        return v


class CustomPersonaResponse(BaseModel):
    """커스텀 페르소나 응답"""
    id: str = Field(..., description="페르소나 ID")
    name: str = Field(..., description="페르소나 이름")
    role: str = Field(..., description="역할")
    background: Optional[str] = Field(None, description="배경")
    expertise: List[str] = Field(..., description="전문 분야")
    personality: List[str] = Field(..., description="성격 특성")
    communication_style: str = Field(..., description="커뮤니케이션 스타일")
    beliefs: List[str] = Field(..., description="신념/가치관")
    initial_openness: float = Field(..., description="초기 개방성")
    llm_provider: str = Field(..., description="LLM 제공자")
    model: str = Field(..., description="모델")
    is_custom: bool = Field(..., description="커스텀 여부")
    created_by: str = Field(..., description="생성자 ID")
    created_at: datetime = Field(..., description="생성 시간")
    
    class Config:
        from_attributes = True

