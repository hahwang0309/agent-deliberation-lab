"""행정조사 관련 스키마 정의"""
from typing import Optional, List, Dict, Union, Any
from pydantic import BaseModel, Field
from datetime import datetime


class InvestigationInput(BaseModel):
    """행정조사 입력 정보"""
    name: str = Field(..., description="조사명", min_length=1, max_length=200)
    purpose: str = Field(..., description="조사 목적", min_length=1)
    scope: str = Field(..., description="조사 범위", min_length=1)
    target: str = Field(..., description="조사 대상", min_length=1)
    methods: str = Field(..., description="조사 방법", min_length=1)
    period: str = Field(..., description="조사 주기/기간", min_length=1)
    legal_basis: str = Field(..., description="법적 근거", min_length=1)
    department: str = Field(..., description="담당 부서/기관", min_length=1)
    
    # 선택적 추가 정보
    start_date: Optional[str] = Field(None, description="조사 시작일 (YYYY-MM-DD)")
    end_date: Optional[str] = Field(None, description="조사 종료일 (YYYY-MM-DD)")
    contact: Optional[str] = Field(None, description="담당자 연락처")
    notes: Optional[str] = Field(None, description="비고")

    class Config:
        schema_extra = {
            "example": {
                "name": "식품위생 정기조사",
                "purpose": "식품제조업소 위생상태 점검",
                "scope": "서울시 전체 식품제조업소",
                "target": "식품제조·가공업 영업허가 업소",
                "methods": "현장 방문 점검, 샘플 채취, 기록 검토",
                "period": "연 2회 (상반기, 하반기)",
                "legal_basis": "식품위생법 제22조",
                "department": "서울시 보건환경연구원",
                "start_date": "2025-03-01",
                "end_date": "2025-11-30"
            }
        }


class InvestigationAnalysisRequest(BaseModel):
    """중복 판별 분석 요청"""
    # 간단한 방식: raw text로 전체 조사 정보 입력
    investigation_a: Union[str, InvestigationInput] = Field(..., description="첫 번째 행정조사 (전체 텍스트 또는 구조화된 데이터)")
    investigation_b: Union[str, InvestigationInput] = Field(..., description="두 번째 행정조사 (전체 텍스트 또는 구조화된 데이터)")
    
    # 분석 옵션
    min_rounds: Optional[int] = Field(3, ge=1, le=5, description="최소 토론 라운드 수")
    max_rounds: Optional[int] = Field(10, ge=1, le=15, description="최대 토론 라운드 수")
    persona_count: Optional[int] = Field(None, ge=3, le=7, description="페르소나 개수 (기본: 자동 결정)")
    skip_discussion: Optional[bool] = Field(False, description="토론 생략하고 사전 분석만 수행")
    enable_openness_adjustment: Optional[bool] = Field(False, description="페르소나 믿음 변화(openness) 기능 활성화")

    class Config:
        schema_extra = {
            "example": {
                "investigation_a": "조사번호: 7-34-1\n부처: 국토부\n조사명: 도시개발사업 시행 관련 보고 및 검사\n법령근거: 도시개발법 제74조제1항\n법령내용:\n① 지정권자나 특별자치도지사ㆍ시장(대도시 시장은 제외한다)ㆍ군수 또는 구청장은 도시개발사업의 시행과 관련하여 필요하다고 인정하면 시행자에게 필요한 보고를 하게 하거나 자료를 제출하도록 명할 수 있으며, 소속 공무원에게 도시개발사업에 관한 업무와 회계에 관한 사항을 검사하게 할 수 있다.",
                "investigation_b": "조사번호: 7-34-2\n부처: 국토부\n조사명: 민관 공동 도시개발사업 시행 관련 보고 및 검사\n법령근거: 도시개발법 제74조제2항\n법령내용:\n② 국토교통부장관은 도시개발사업의 관리ㆍ감독을 위하여 필요하다고 인정하면 민간참여자 선정, 시행 및 운영실태에 대하여 지정권자에게 필요한 보고를 하게 하거나 자료를 제출하도록 명할 수 있다.",
                "min_rounds": 3,
                "max_rounds": 10
            }
        }


class PersonaInfo(BaseModel):
    """페르소나 정보"""
    name: str = Field(..., description="페르소나 이름")
    role: str = Field(..., description="역할")
    expertise: str = Field(..., description="전문 분야")
    perspective: str = Field(..., description="관점")
    style: str = Field(..., description="발언 스타일")
    background: Optional[str] = Field(None, description="배경")
    key_concerns: List[str] = Field(default_factory=list, description="주요 관심사")


class ConsensusStatus(BaseModel):
    """합의 상태"""
    has_consensus: bool = Field(..., description="합의 도달 여부")
    consensus_level: float = Field(..., ge=0, le=1, description="합의도")
    areas_of_agreement: List[str] = Field(default_factory=list, description="합의된 사항")
    areas_of_disagreement: List[str] = Field(default_factory=list, description="불일치 사항")
    key_arguments: Dict[str, str] = Field(default_factory=dict, description="페르소나별 핵심 주장")


class RoundSummary(BaseModel):
    """라운드 요약"""
    round_number: int = Field(..., ge=0, description="라운드 번호 (0=개회, 마지막=폐회)")
    phase: str = Field(..., description="단계 (OPENING/ANALYSIS/DEBATE/CONSENSUS)")
    key_points: List[str] = Field(default_factory=list, description="주요 논점")
    summary: Optional[str] = Field(None, description="라운드 요약")
    messages: List[Dict[str, Any]] = Field(default_factory=list, description="토론 메시지 원문")
    
    # 하위 호환성을 위해 optional로 유지
    moderator_guide: Optional[str] = Field(None, description="모더레이터 가이드 (deprecated)")
    persona_statements: Optional[Dict[str, str]] = Field(None, description="페르소나별 발언 (deprecated)")
    
    class Config:
        extra = "allow"  # 추가 필드 허용


class InvestigationAnalysisResponse(BaseModel):
    """중복 판별 분석 응답"""
    analysis_id: str = Field(..., description="분석 ID")
    created_at: datetime = Field(..., description="생성 시각")
    status: str = Field(..., description="상태 (processing/completed/failed)")
    
    # 입력 정보
    investigation_a_name: str = Field(..., description="조사 A 이름")
    investigation_b_name: str = Field(..., description="조사 B 이름")
    
    # 페르소나 정보
    personas: List[PersonaInfo] = Field(default_factory=list, description="참여 페르소나")
    
    # 토론 결과
    total_rounds: int = Field(0, description="총 라운드 수")
    rounds: List[RoundSummary] = Field(default_factory=list, description="라운드별 요약")
    
    # 최종 결과
    final_verdict: str = Field(..., description="최종 판정 (중복/비중복/부분중복)")
    final_verdict_details: Optional[str] = Field(None, description="판정 상세 설명")
    consensus_status: Optional[ConsensusStatus] = Field(None, description="합의 상태")
    
    # 루브릭 점수
    rubric_scores: Optional[Dict[str, Any]] = Field(None, description="정량적 중복도 평가 (루브릭)")
    
    # 보고서
    report_preview: str = Field(..., description="보고서 미리보기 (처음 500자)")
    report_url: Optional[str] = Field(None, description="전체 보고서 다운로드 URL")


class InvestigationAnalysisListItem(BaseModel):
    """분석 목록 항목"""
    analysis_id: str
    created_at: datetime
    investigation_a_name: str
    investigation_b_name: str
    final_verdict: str
    confidence: float
    total_rounds: int


class InvestigationAnalysisListResponse(BaseModel):
    """분석 목록 응답"""
    total: int = Field(..., description="전체 개수")
    items: List[InvestigationAnalysisListItem] = Field(..., description="분석 목록")
    page: int = Field(..., ge=1, description="현재 페이지")
    page_size: int = Field(..., ge=1, description="페이지 크기")

