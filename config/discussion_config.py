"""
토론 엔진 설정 - 값은 config/config.yaml의 engine 섹션에만 둔다 (여기는 형식만)

토론마다 실험 조건을 덮어쓴 사본을 만든다(src/core/experiment.py의 engine_settings).
값의 의미는 config.yaml 주석과 docs/configuration.md를 본다.
"""
from dataclasses import dataclass


@dataclass
class DiscussionConfig:
    # 발언 길이 (프롬프트 지시)
    min_response_sentences: int
    max_response_sentences: int

    # 웹 검색(RAG) 기본 활성화
    enable_web_search: bool

    # 진행 설계: 명제 수 상한, 상대 발언 전달 범위
    max_subtopics: int
    context_messages: int
    context_chars: int

    # 토론 상태 기반 진행
    stalemate_exchanges: int
    consensus_spread: float
    close_stance_distance: float      # 입장 거리가 이보다 가까우면 동의·확장/예시, 아니면 반박/근거 공격
    stance_strong: float              # 입장 라벨: |x| ≥ 이 값이면 '강한'
    stance_lean: float                # 입장 라벨: |x| ≥ 이 값이면 찬성/반대, 아니면 유보
    stance_note_min_shift: float      # 발언자에게 알리는 입장 이동의 최소 크기
    commitments_kept: int             # 참가자별로 기억하는 최근 주장 수

    # 발언 분석
    analyzer_temperature: float
    analysis_context_messages: int    # 분석에 함께 넣는 직전 발언 수
    analysis_context_chars: int       # 그 발언들의 글자 수 상한

    # 입장 동역학 (Friedkin-Johnsen + 제한 신뢰, src/core/debate_state.py)
    dynamics_step: float
    dynamics_anchor: float
    accept_wide: float
    accept_narrow: float
    noncommit_width: float
    noncommit_factor: float
    reject_factor: float
    threat_dampen: float
    boomerang_threshold: float
    boomerang_step: float
    concession_step: float
    concession_cap: float
    value_match_weight: float         # 설득력 = 질 × 새로움 × (1−w + w×가치 일치) × ...
    credibility_weight: float
    receptive_weight: float
    grounds_max: int
    undermine_self: float
    undermine_other: float
    undermine_unanswered: float
    switch_theta_min: float
    switch_theta_max: float
    low_involvement: float
    continuous_gain: float
    bolster_step: float
    switch_base: float
    switch_gain: float
    use_threshold_switch: bool
    stubbornness_default: float
    stubbornness_open: float
    stubbornness_firm: float

    # 엔진 모드와 기록
    engine_mode: str
    record_prompts: bool

    # 진행 장치 on/off
    use_reply_obligation: bool
    use_stalemate_mediation: bool
    use_devils_advocate: bool
    use_closing_round: bool

    # LLM temperature
    agent_temperature: float
    moderator_temperature: float

    # 사람 개입
    human_followup_responses: int


def get_config() -> DiscussionConfig:
    """config.yaml engine 섹션의 기본 설정 (토론별 사본은 engine_settings로 만든다)"""
    from config.config_loader import config_loader
    return config_loader.config.engine
