"""
토론 시스템 설정
"""
from dataclasses import dataclass


@dataclass
class DiscussionConfig:
    """토론 설정"""
    
    # 질문 관련 설정
    max_questions_per_discussion: int = 3  # 토론당 최대 질문 수
    turns_between_questions: int = 5  # 질문 간 최소 턴 수
    agent_question_probability: float = 0.05  # 에이전트가 질문할 확률 (5%)
    moderator_question_probability: float = 0.8  # 모더레이터가 질문할 확률 (80%)
    
    # 토론 깊이 설정
    min_depth_per_subtopic: int = 3  # 소주제당 최소 깊이
    max_depth_per_subtopic: int = 6  # 소주제당 최대 깊이
    
    # 진화 설정
    evolution_openness_default: float = 0.7  # 기본 변화 개방성
    evolution_threshold: float = 0.5  # 신념 변화 임계값
    
    # 발언 설정
    min_response_sentences: int = 3  # 최소 응답 문장 수
    max_response_sentences: int = 8  # 최대 응답 문장 수
    
    # Chain-of-Thought 설정
    use_cot_reasoning: bool = True  # CoT 추론 사용
    cot_depth: int = 3  # CoT 추론 깊이 (질문 수)
    
    # 자연스러운 토론 설정
    prefer_building_over_challenging: float = 0.6  # 건설적 확장 선호도
    require_evidence_probability: float = 0.3  # 증거 요구 확률
    
    # 모더레이터 설정
    moderator_intervention_threshold: int = 8  # 개입 전 최소 발언 수
    moderator_synthesis_frequency: int = 10  # 종합 빈도
    
    # 웹 검색 설정
    enable_web_search: bool = True  # 웹 검색 활성화
    max_searches_per_agent: int = 3  # 에이전트당 최대 검색 횟수
    fact_check_enabled: bool = True  # 팩트체크 활성화
    search_trigger_probability: float = 0.2  # 랜덤 검색 확률
    
    # ========================================
    # 🆕 토론 흐름 및 진화 관련 설정
    # ========================================
    
    # 토론 흐름 제어
    max_turns_per_agent: int = 10  # 에이전트당 최대 발언 횟수
    
    # 모더레이터 분석 윈도우
    depth_analysis_window: int = 10  # 깊이 분석 시 최근 N개 메시지
    recent_mention_window: int = 5   # 최근 언급 체크 시 N개 메시지
    min_messages_before_transition: int = 8  # 주제 전환 전 최소 메시지
    
    # 소주제 설정
    max_subtopics: int = 5  # 최대 소주제 개수
    
    # 페르소나 진화 가중치
    evidence_score_max: float = 0.6      # 증거 점수 최대값
    evidence_score_weight: float = 0.2   # 증거 키워드당 가중치
    logic_score_max: float = 0.3         # 논리 점수 최대값
    logic_score_weight: float = 0.15     # 논리 키워드당 가중치
    specificity_bonus: float = 0.25      # 구체적 숫자 보너스
    persuasion_threshold: float = 0.25   # 설득력 최소 임계값
    
    # 신념 강도 설정
    core_belief_strength: float = 0.85       # 핵심 신념 초기 강도
    core_belief_flexibility: float = 0.2     # 핵심 신념 유연성
    normal_belief_strength: float = 0.65     # 일반 신념 초기 강도
    normal_belief_flexibility: float = 0.5   # 일반 신념 유연성


# 기본 설정 인스턴스
default_config = DiscussionConfig()


def get_config() -> DiscussionConfig:
    """현재 설정 반환"""
    return default_config


def update_config(**kwargs) -> DiscussionConfig:
    """설정 업데이트"""
    for key, value in kwargs.items():
        if hasattr(default_config, key):
            setattr(default_config, key, value)
    return default_config