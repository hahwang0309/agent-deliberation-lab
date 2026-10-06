"""
분석 관련 스키마
"""
from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Literal
from datetime import datetime


# ========================================
# 토론 종합 분석
# ========================================

class MessagesPerParticipant(BaseModel):
    """참가자별 메시지 수"""
    pass  # 동적 필드 사용


class TopQuery(BaseModel):
    """인기 쿼리"""
    query: str
    count: int
    speaker: str


class RAGUsageStats(BaseModel):
    """RAG 사용 통계"""
    total_searches: int
    successful_searches: int
    failed_searches: int
    usage_rate: float
    avg_search_time_seconds: float
    top_queries: List[TopQuery]


class DiscussionStatistics(BaseModel):
    """토론 통계"""
    duration_seconds: int
    total_rounds: int
    total_messages: int
    messages_per_round: float
    messages_per_participant: Dict[str, int]
    avg_message_length: int
    total_characters: int
    total_words: int
    rag_usage: RAGUsageStats


class OverallSentiment(BaseModel):
    """전체 감정"""
    positive: float
    neutral: float
    negative: float


class SentimentTrend(BaseModel):
    """감정 변화"""
    round: int
    score: float


class ParticipantSentiment(BaseModel):
    """참가자 감정 분석"""
    positive: float
    neutral: float
    negative: float
    trend: Literal["increasingly_positive", "increasingly_negative", "stable", "slightly_positive", "slightly_negative"]
    change_over_time: Optional[List[SentimentTrend]] = None


class SentimentAnalysis(BaseModel):
    """감정 분석"""
    overall: OverallSentiment
    by_participant: Dict[str, ParticipantSentiment]


class KeyTopic(BaseModel):
    """핵심 주제"""
    topic: str
    frequency: int
    sentiment: float
    main_discussants: List[str]


class AgreementArea(BaseModel):
    """합의 영역"""
    area: str
    support_level: float
    supporters: List[str]


class DisagreementArea(BaseModel):
    """불일치 영역"""
    area: str
    positions: Dict[str, str]
    gap_score: float


class ConsensusInfo(BaseModel):
    """합의 정보"""
    score: float
    reached: bool
    confidence: float
    main_agreement: str
    agreement_areas: List[AgreementArea]
    disagreement_areas: List[DisagreementArea]


class QualityMetrics(BaseModel):
    """품질 지표"""
    evidence_based_score: float
    constructive_dialogue_score: float
    open_mindedness_score: float
    argument_diversity_score: float
    overall_quality: float


class InteractionNetwork(BaseModel):
    """상호작용 네트워크"""
    direct_responses: Dict[str, int]
    influence_scores: Dict[str, float]


class DiscussionAnalyticsResponse(BaseModel):
    """토론 종합 분석 응답"""
    discussion_id: str
    topic: str
    status: str
    statistics: DiscussionStatistics
    sentiment_analysis: SentimentAnalysis
    key_topics: List[KeyTopic]
    consensus: ConsensusInfo
    quality_metrics: QualityMetrics
    interaction_network: InteractionNetwork
    generated_at: datetime


# ========================================
# 토론 요약
# ========================================

class KeyArguments(BaseModel):
    """핵심 논점 (참가자별)"""
    pass  # 동적 필드


class ConsensusDetail(BaseModel):
    """합의 상세"""
    main_agreement: str
    details: List[str]
    confidence: float


class PhaseKeyMoment(BaseModel):
    """단계별 주요 순간"""
    pass  # 문자열 리스트


class DiscussionPhase(BaseModel):
    """토론 단계"""
    phase: str
    description: str
    consensus_score: float
    key_moments: List[str]


class TopSource(BaseModel):
    """주요 출처"""
    url: str
    title: str
    citation_count: int
    relevance: Literal["high", "medium", "low"]


class QualityAssessment(BaseModel):
    """품질 평가"""
    overall_score: float
    strengths: List[str]
    areas_for_improvement: List[str]


class DiscussionSummaryResponse(BaseModel):
    """토론 요약 응답"""
    discussion_id: str
    topic: str
    status: str
    executive_summary: str
    key_arguments: Dict[str, List[str]]
    consensus: ConsensusDetail
    discussion_progression: List[DiscussionPhase]
    top_sources: List[TopSource]
    quality_assessment: QualityAssessment
    generated_at: datetime


# ========================================
# 페르소나 진화 추적
# ========================================

class PersonaState(BaseModel):
    """페르소나 상태"""
    beliefs: List[str]
    openness_score: float
    flexibility_score: float
    timestamp: Optional[datetime] = None


class PersonaChanges(BaseModel):
    """페르소나 변화"""
    beliefs_added: List[str]
    beliefs_removed: List[str]
    openness_change: float
    flexibility_change: float


class EvolutionEvent(BaseModel):
    """진화 이벤트"""
    round: int
    timestamp: datetime
    event: str
    openness: float
    flexibility: float
    key_moment: str
    influenced_by: Optional[str] = None
    reflection: Optional[str] = None
    new_belief: Optional[str] = None
    message_id: Optional[str] = None


class KeyInfluence(BaseModel):
    """주요 영향"""
    from_: str = Field(..., alias="from")
    round: int
    message: str
    impact_score: float
    impact_type: Literal["perspective_shift", "value_addition", "belief_challenge", "reinforcement"]
    resulted_in: str
    
    class Config:
        populate_by_name = True


class InteractionPattern(BaseModel):
    """상호작용 패턴"""
    most_engaged_with: str
    engagement_count: int
    agreement_rate: float
    challenge_rate: float


class PersonaEvolution(BaseModel):
    """페르소나 진화"""
    name: str
    role: str
    initial_state: PersonaState
    final_state: PersonaState
    changes: PersonaChanges
    evolution_history: List[EvolutionEvent]
    key_influences: List[KeyInfluence]
    interaction_patterns: InteractionPattern


class OverallTrends(BaseModel):
    """전체 트렌드"""
    average_openness_increase: float
    average_flexibility_increase: float
    consensus_correlation: float
    evolution_rate: Literal["slow", "moderate", "fast", "very_fast"]


class PersonaEvolutionResponse(BaseModel):
    """페르소나 진화 추적 응답"""
    discussion_id: str
    topic: str
    personas: List[PersonaEvolution]
    overall_trends: OverallTrends
    generated_at: datetime

