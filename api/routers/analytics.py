"""
분석 엔드포인트
"""
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime

from api.database import get_db
from api.dependencies import get_current_user, get_optional_user
from api.models.user import User
from api.schemas.analytics import (
    DiscussionAnalyticsResponse,
    DiscussionSummaryResponse,
    PersonaEvolutionResponse
)
from api.services.discussion_service import DiscussionService
from api.services.analytics_service import AnalyticsService

router = APIRouter(prefix="/api/v1/discussions", tags=["분석"])


@router.get(
    "/{discussion_id}/analytics",
    response_model=DiscussionAnalyticsResponse,
    status_code=status.HTTP_200_OK,
    summary="토론 종합 분석 (게스트 지원)",
    description="토론의 종합 분석 결과를 조회합니다. 로그인 선택사항."
)
def get_discussion_analytics(
    discussion_id: str,
    current_user: Optional[User] = Depends(get_optional_user),
    db: Session = Depends(get_db)
):
    """
    토론 종합 분석
    
    **포함 내용:**
    - 통계 (메시지 수, 참가자별 통계, RAG 사용률 등)
    - 감정 분석 (전체 및 참가자별)
    - 핵심 주제
    - 합의 정보
    - 품질 지표
    - 상호작용 네트워크
    
    **Authorization 헤더 선택사항 (게스트 허용):**
    ```
    Authorization: Bearer {access_token}
    ```
    """
    # 권한 확인
    user_id = current_user.id if current_user else "guest"
    discussion = DiscussionService.get_discussion(db, discussion_id, user_id)
    
    # 통계 계산
    statistics = AnalyticsService.calculate_discussion_statistics(db, discussion)
    
    # 감정 분석
    sentiment_analysis = AnalyticsService.analyze_sentiment(db, discussion)
    
    # 핵심 주제
    key_topics = AnalyticsService.extract_key_topics(db, discussion)
    
    # 합의 정보
    consensus = AnalyticsService.calculate_consensus(db, discussion)
    
    # 품질 지표
    quality_metrics = AnalyticsService.calculate_quality_metrics(db, discussion)
    
    # 상호작용 네트워크
    interaction_network = AnalyticsService.analyze_interaction_network(db, discussion)
    
    return DiscussionAnalyticsResponse(
        discussion_id=discussion.id,
        topic=discussion.topic,
        status=discussion.status,
        statistics=statistics,
        sentiment_analysis=sentiment_analysis,
        key_topics=key_topics,
        consensus=consensus,
        quality_metrics=quality_metrics,
        interaction_network=interaction_network,
        generated_at=datetime.utcnow()
    )


@router.get(
    "/{discussion_id}/analytics/summary",
    response_model=DiscussionSummaryResponse,
    status_code=status.HTTP_200_OK,
    summary="토론 요약 (게스트 지원)",
    description="토론의 요약 정보를 조회합니다. 로그인 선택사항."
)
def get_discussion_summary(
    discussion_id: str,
    current_user: Optional[User] = Depends(get_optional_user),
    db: Session = Depends(get_db)
):
    """
    토론 요약
    
    **포함 내용:**
    - 요약 (executive summary)
    - 핵심 논점 (참가자별)
    - 합의 내용
    - 토론 진행 단계
    - 주요 출처
    - 품질 평가
    
    **Authorization 헤더 선택사항 (게스트 허용):**
    ```
    Authorization: Bearer {access_token}
    ```
    """
    # 권한 확인
    user_id = current_user.id if current_user else "guest"
    discussion = DiscussionService.get_discussion(db, discussion_id, user_id)
    
    # 요약 생성
    summary_data = AnalyticsService.generate_discussion_summary(db, discussion)
    
    return DiscussionSummaryResponse(
        discussion_id=discussion.id,
        topic=discussion.topic,
        status=discussion.status,
        executive_summary=summary_data["executive_summary"],
        key_arguments=summary_data["key_arguments"],
        consensus=summary_data["consensus"],
        discussion_progression=summary_data["discussion_progression"],
        top_sources=summary_data["top_sources"],
        quality_assessment=summary_data["quality_assessment"],
        generated_at=datetime.utcnow()
    )


@router.get(
    "/{discussion_id}/analytics/persona-evolution",
    response_model=PersonaEvolutionResponse,
    status_code=status.HTTP_200_OK,
    summary="페르소나 진화 추적 (게스트 지원)",
    description="토론 중 페르소나의 진화 과정을 추적합니다. 로그인 선택사항."
)
def get_persona_evolution(
    discussion_id: str,
    persona: Optional[str] = Query(None, description="특정 페르소나 필터"),
    current_user: Optional[User] = Depends(get_optional_user),
    db: Session = Depends(get_db)
):
    """
    페르소나 진화 추적
    
    **포함 내용:**
    - 초기/최종 상태 (beliefs, openness, flexibility)
    - 변화 내역
    - 진화 히스토리 (라운드별)
    - 주요 영향
    - 상호작용 패턴
    - 전체 트렌드
    
    **Query Parameters:**
    - **persona**: 특정 페르소나 이름 (선택)
    
    **Authorization 헤더 선택사항 (게스트 허용):**
    ```
    Authorization: Bearer {access_token}
    ```
    """
    # 권한 확인
    user_id = current_user.id if current_user else "guest"
    discussion = DiscussionService.get_discussion(db, discussion_id, user_id)
    
    # 페르소나 진화 추적
    evolution_data = AnalyticsService.track_persona_evolution(db, discussion, persona)
    
    return PersonaEvolutionResponse(
        discussion_id=discussion.id,
        topic=discussion.topic,
        personas=evolution_data["personas"],
        overall_trends=evolution_data["overall_trends"],
        generated_at=datetime.utcnow()
    )

