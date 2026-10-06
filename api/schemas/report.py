"""
종합보고서 스키마
"""
from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict


class ReportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    discussion_id: str
    status: str  # pending | ready | failed
    consensus_score: Optional[float] = None
    ai_score: Optional[float] = None
    human_score: Optional[float] = None
    consensus_label: Optional[str] = None  # agreed | partial | disagreed
    model: Optional[str] = None
    error: Optional[str] = None
    requested_at: Optional[datetime] = None
    generated_at: Optional[datetime] = None
    content: Optional[Dict[str, Any]] = None
