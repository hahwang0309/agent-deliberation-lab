"""
페르소나 API 스키마
"""
from typing import List, Literal, Optional

from pydantic import BaseModel, Field

from config.config_loader import config_loader

_limits = config_loader.config.limits


class PersonaData(BaseModel):
    """페르소나 본문 (src.models.personas.Persona와 동일 필드)"""
    name: str
    role: str
    background: str
    personality: List[str]
    expertise: List[str]
    communication_style: str
    beliefs: List[str]


class PersonaTemplate(PersonaData):
    id: str = Field(..., description="템플릿 ID")


class PersonaTemplateListResponse(BaseModel):
    templates: List[PersonaTemplate]


class GeneratePersonasRequest(BaseModel):
    topic: str = Field(..., min_length=2, max_length=200)
    count: int = Field(3, ge=_limits.min_personas, le=_limits.max_personas)
    language: Optional[Literal["ko", "en"]] = None


class GeneratePersonasResponse(BaseModel):
    personas: List[PersonaData]
