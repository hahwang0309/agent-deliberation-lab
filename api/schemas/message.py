"""
메시지 관련 스키마
"""
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class MessageResponse(BaseModel):
    """토론 메시지 (SSE 'message' 이벤트 data와 동일 구조)"""
    id: str
    seq: int
    speaker_type: str = Field(description="ai | moderator | human | system")
    speaker: str
    participant_id: Optional[str] = None
    user_id: Optional[str] = None
    content: str
    action: Optional[str] = None
    meta: Dict[str, Any] = Field(default_factory=dict)
    rag_used: bool = False
    sources: List[Any] = Field(default_factory=list)
    timestamp: Optional[str] = None


class MessageListResponse(BaseModel):
    items: List[MessageResponse]
    last_seq: int
