"""
내보내기 API 스키마
"""
from datetime import datetime
from typing import List, Dict, Any, Optional
from pydantic import BaseModel


# ========================================
# JSON 내보내기 스키마
# ========================================

class ExportDiscussionInfo(BaseModel):
    """내보내기용 토론 정보"""
    id: str
    topic: str
    description: Optional[str]
    status: str
    created_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    duration_seconds: Optional[int]
    created_by: str


class ExportParticipant(BaseModel):
    """내보내기용 참가자 정보"""
    id: str
    name: str
    role: str
    template_id: Optional[str]
    llm_provider: str
    model: str


class ExportConfig(BaseModel):
    """내보내기용 설정 정보"""
    max_rounds: int
    min_rounds: int
    enable_rag: bool
    enable_subtopics: bool
    enable_reflection: bool
    reflection_interval: int
    enable_persona_evolution: bool


class ExportSource(BaseModel):
    """내보내기용 출처 정보"""
    url: str
    title: str


class ExportMessage(BaseModel):
    """내보내기용 메시지 정보"""
    id: str
    speaker: str
    content: str
    timestamp: datetime
    round: int
    rag_used: bool
    rag_query: Optional[str]
    sources: List[ExportSource]


class JSONExportResponse(BaseModel):
    """JSON 내보내기 응답"""
    discussion: ExportDiscussionInfo
    participants: List[ExportParticipant]
    config: ExportConfig
    messages: List[ExportMessage]
    analytics: Dict[str, Any]  # AnalyticsResponse와 동일한 구조
    persona_evolution: Dict[str, Any]  # PersonaEvolutionResponse와 동일한 구조
    exported_at: datetime
    export_version: str = "1.0"

