"""배치 분석 관련 스키마"""
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any, Union
from datetime import datetime


class BatchAnalysisItemInput(BaseModel):
    """배치 항목 입력"""
    investigation_a: Union[str, Dict[str, Any]] = Field(..., description="행정조사 A 데이터 (텍스트 또는 구조화된 데이터)")
    investigation_b: Union[str, Dict[str, Any]] = Field(..., description="행정조사 B 데이터 (텍스트 또는 구조화된 데이터)")
    item_name: Optional[str] = Field(None, description="항목 이름 (선택)")


class BatchAnalysisCreateRequest(BaseModel):
    """배치 분석 생성 요청"""
    name: str = Field(..., description="배치 이름", min_length=1, max_length=200)
    description: Optional[str] = Field(None, description="설명", max_length=500)
    items: List[BatchAnalysisItemInput] = Field(..., description="분석 항목 목록", min_items=1, max_items=500)
    
    # 분석 설정
    persona_count: Optional[int] = Field(None, description="페르소나 수 (자동이면 None)", ge=3, le=10)
    min_rounds: Optional[int] = Field(3, description="최소 라운드", ge=1, le=10)
    max_rounds: Optional[int] = Field(10, description="최대 라운드", ge=1, le=20)
    enable_openness_adjustment: Optional[bool] = Field(False, description="개방성 조정 활성화")


class BatchAnalysisItemInfo(BaseModel):
    """배치 항목 정보"""
    id: str
    sequence: int
    item_name: Optional[str]
    investigation_a_name: str
    investigation_b_name: str
    status: str
    analysis_id: Optional[str]
    final_verdict: Optional[str]
    confidence: Optional[float]
    error_message: Optional[str]
    created_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]


class BatchAnalysisInfo(BaseModel):
    """배치 분석 정보 (목록용)"""
    id: str
    name: str
    description: Optional[str]
    status: str
    total_count: int
    completed_count: int
    failed_count: int
    progress_percentage: float
    created_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]


class BatchAnalysisDetail(BaseModel):
    """배치 분석 상세 정보"""
    id: str
    name: str
    description: Optional[str]
    status: str
    total_count: int
    completed_count: int
    failed_count: int
    progress_percentage: float
    config: Optional[Dict[str, Any]]
    items: List[BatchAnalysisItemInfo]
    created_at: datetime
    started_at: Optional[datetime]
    paused_at: Optional[datetime]
    completed_at: Optional[datetime]


class BatchAnalysisListResponse(BaseModel):
    """배치 분석 목록 응답"""
    total: int
    items: List[BatchAnalysisInfo]
    page: int
    page_size: int

