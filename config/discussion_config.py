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
    
    # 소주제 설정
    max_subtopics: int = 5  # 최대 소주제 개수

    # 진행 설계: 명제 수 k = clamp(본론 발언 수 // (참가자 수 + 1), 1, max_subtopics)
    #            본론 발언 수 = 전체 - 종결 라운드(참가자 수, 본론이 참가자 수+1 이상 남을 때만)

    # 상대 발언 전달 범위 (최근 N개, 발언당 최대 글자 수)
    context_messages: int = 8
    context_chars: int = 1200

    # 토론 상태 기반 진행
    stalemate_exchanges: int = 1      # 두 참가자가 서로 이만큼 반박을 주고받으면 교착 → 제3자 중재·제3안 (명제당 예산이 작아 1)
    consensus_spread: float = 0.3     # 첫 입장들의 차이가 이보다 작으면 성급한 합의 → 반대 검토

    # 입장 동역학 (Friedkin-Johnsen + 제한 신뢰, src/core/debate_state.py)
    dynamics_step: float = 0.5
    dynamics_anchor: float = 0.1
    # 수용·거부 범위 (Sherif & Hovland): 수용 범위 폭 = accept_wide − (accept_wide − accept_narrow) × 고집도
    accept_wide: float = 1.2
    accept_narrow: float = 0.4
    noncommit_width: float = 0.4      # 수용 범위 바깥 비관여 범위 폭 (그 너머는 거부 범위)
    noncommit_factor: float = 0.5     # 비관여 범위 설득력 배수
    reject_factor: float = 0.15       # 거부 범위 설득력 배수
    threat_dampen: float = 0.5        # 정체성 위협이 설득력을 줄이는 정도
    boomerang_threshold: float = 0.5  # 거부 범위에서 위협이 이 이상이면 반대로 멀어짐
    boomerang_step: float = 0.1
    # 양보에 따른 일관성 이동 (양보 1건당 × (1 − 고집도), 명제당 상한)
    concession_step: float = 0.05
    concession_cap: float = 0.2
    stubbornness_default: float = 0.5
    stubbornness_open: float = 0.3    # 성격에 개방적·유연 등이 있으면
    stubbornness_firm: float = 0.75   # 성격에 완고·원칙적 등이 있으면

    # 엔진 모드: stateful(상태 기반 진행) | baseline(순서대로 앞 발언에 답하는 단순 토론, 비교 기준선)
    engine_mode: str = "stateful"
    record_prompts: bool = False  # 발언마다 최종 지시 프롬프트를 메시지 meta에 저장 (실험 조건이 있으면 기본 켬)

    # 진행 장치 on/off (실험 조건으로 끌 수 있음, src/core/experiment.py)
    use_reply_obligation: bool = True     # 반박·질문을 받은 참가자의 응답 의무
    use_stalemate_mediation: bool = True  # 교착 시 제3자 중재·제3안 (2명이면 모더레이터 지목 질문)
    use_devils_advocate: bool = True      # 성급한 합의 시 반대 검토
    use_closing_round: bool = True        # 마지막 종결 라운드

    # LLM temperature
    agent_temperature: float = 0.7
    moderator_temperature: float = 0.5

    # 사람 개입
    human_followup_responses: int = 1  # 사람 발언 직후 그 발언에 응답하는 AI 발언 수 (명제 예산을 쓰고, 예산이 끝났으면 추가 발언)


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