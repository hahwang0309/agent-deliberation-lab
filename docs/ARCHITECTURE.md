# System Architecture - Multi-Agent Discussion System v2

## Overview
리팩토링된 토론 시스템의 아키텍처 문서입니다. MSA(Microservice Architecture) 원칙에 따라 기능별로 모듈을 분리했습니다.

## 📁 Project Structure

```
config/                        # 설정 파일들
├── config.yaml              # 시스템 설정
├── prompts.yaml             # 프롬프트 템플릿
├── discussion_config.py     # 토론 런타임 설정
└── config_loader.py         # 설정 로더

src/
├── core/                     # 핵심 모듈
│   ├── agent.py             # 토론 에이전트
│   ├── moderator.py         # 모더레이터
│   └── natural_discussion.py # 자연스러운 토론 시스템
│
├── services/                 # 서비스 모듈
│   ├── belief_reasoning.py  # 신념 기반 추론 (Chain-of-Thought)
│   ├── discussion_manager.py # 토론 관리 서비스
│   ├── report_generator.py  # 리포트 생성 서비스
│   └── web_search.py        # 웹 검색 서비스
│
├── models/                   # 데이터 모델
│   ├── personas.py          # 페르소나 모델
│   ├── consensus_tracker.py # 합의 추적
│   └── persona_evolution.py # 페르소나 진화
│
├── utils/                    # 유틸리티
│   ├── language_detector.py # 언어 감지
│   ├── llm_provider.py      # LLM 프로바이더
│   └── logger.py            # 로깅
│
├── generators/               # 생성기
│   └── persona_generator.py # 페르소나 생성
│
└── discussion.py            # 메인 인터페이스
```

## 🏗️ Architecture Components

### 1. Core Modules

#### `core/agent.py` - Discussion Agent
- **책임**: 개별 토론 참가자 구현
- **주요 기능**:
  - 신념/가치관 기반 발화
  - Chain-of-Thought 추론
  - 페르소나 진화 추적
  - 스트리밍 응답

```python
class DiscussionAgent:
    - _build_system_prompt(): 신념 강조 프롬프트 생성
    - respond(): CoT 추론 기반 응답
    - process_other_argument(): 페르소나 진화 처리
```

#### `core/moderator.py` - Discussion Moderator
- **책임**: 토론 진행 및 소주제 관리
- **주요 기능**:
  - 소주제 생성 및 전환
  - 심화 질문 생성 (제한적)
  - 토론 깊이 추적
  - 종합 및 정리

```python
class DiscussionModerator:
    - generate_subtopics(): 4-5개 핵심 관점 생성
    - should_transition_subtopic(): 전환 시점 판단
    - generate_probing_question(): 심화 질문 (제한적)
    - synthesize_discussion(): 토론 종합
```

#### `core/natural_discussion.py` - Natural Discussion System
- **책임**: 자연스러운 토론 흐름 관리
- **주요 기능**:
  - 동적 턴 관리 (턴제 없음)
  - 액션 타입 기반 발화 선택
  - 진화 및 합의 추적
  - 모더레이터 개입 조정

```python
class NaturalDiscussion:
    ActionType: PRESENT, RESPOND, BUILD, CHALLENGE, EXAMPLE, SYNTHESIZE
    - _select_next_speaker(): 자연스러운 발언자 선택
    - _generate_prompt(): 액션별 프롬프트 생성
    - _process_evolution(): 페르소나 진화 처리
```

### 2. Service Modules

#### `services/belief_reasoning.py` - Belief-Based Reasoning
- **책임**: Chain-of-Thought 기반 신념 추론
- **주요 기능**:
  - 핵심 질문 생성
  - 신념 기반 추론
  - 일관성 검증

```python
class BeliefReasoningService:
    - reason_about_topic(): CoT 추론 수행
    - _generate_core_questions(): 핵심 질문 도출
    - check_belief_consistency(): 신념 일관성 검증
```

#### `services/discussion_manager.py` - Discussion Manager
- **책임**: 토론 흐름 관리 및 조정
- **주요 기능**:
  - 토론 진행 상태 관리
  - 참가자 발언 순서 조정
  - 토론 품질 모니터링

#### `services/report_generator.py` - Report Generator
- **책임**: 토론 결과 리포트 생성
- **주요 기능**:
  - 토론 요약 생성
  - 주요 인사이트 추출
  - 합의/불일치 포인트 분석

#### `services/web_search.py` - Web Search Service
- **책임**: 실시간 웹 정보 검색 (Tavily API)
- **주요 기능**:
  - 토론 중 팩트 체크
  - 최신 정보 제공
  - 근거 자료 검색

### 3. Configuration

#### `config/discussion_config.py`
```python
@dataclass
class DiscussionConfig:
    # 질문 제한
    max_questions_per_discussion: int = 3
    turns_between_questions: int = 5
    
    # 토론 성향
    prefer_building_over_challenging: float = 0.6
    
    # Chain-of-Thought
    use_cot_reasoning: bool = True
    
    # 진화 설정
    evolution_openness_default: float = 0.7
```

## 🔄 Discussion Flow

### 1. 초기화
```
1. 페르소나 생성/정의
2. 에이전트 생성 (신념 강조)
3. 모더레이터 생성
4. 소주제 프레임워크 생성
```

### 2. 토론 진행 (자연스러운 흐름)
```
while turn < max_turns:
    1. 발언자 선택 (최소 발언자 우선)
    2. 액션 타입 결정 (토론 진행도 기반)
    3. CoT 추론 수행
    4. 프롬프트 생성 (신념 기반)
    5. 응답 생성
    6. 페르소나 진화 처리
    7. 모더레이터 개입 체크
```

### 3. 액션 타입별 행동
- **PRESENT**: 새로운 관점 제시 (초반)
- **RESPOND**: 직접 응답 (중반)
- **BUILD**: 동의하며 확장 (중반)
- **CHALLENGE**: 도전/반박 (중반)
- **EXAMPLE**: 구체적 예시 (전체)
- **SYNTHESIZE**: 종합 (후반)

## 🎯 Key Features

### 1. 신념 기반 발화
- 각 에이전트는 자신의 신념/가치관에 충실
- Chain-of-Thought로 심화된 추론
- 페르소나별 고유한 관점 유지

### 2. 제한된 질문
- 모더레이터가 주로 질문 (최대 3개)
- 에이전트는 거의 질문하지 않음 (5% 확률)
- 질문 간 최소 5턴 간격

### 3. 소주제 관리
- 4-5개 핵심 관점 자동 생성
- 각 관점별 깊이 추적
- 자동 전환 및 커버리지 보장

### 4. 페르소나 진화
- 더 민감한 진화 파라미터
- 실시간 진화 표시
- 누적 효과 적용

### 5. 자연스러운 흐름
- 턴제 없음
- 토론 진행도에 따른 동적 행동
- 건설적 토론 우선

## 🚀 Usage

### Basic Usage
```python
from src.discussion import create_discussion
from src.generators.persona_generator import PersonaGenerator

# 페르소나 생성
personas = await generator.generate_multiple_personas(topic, 3)

# 토론 생성
discussion = create_discussion(personas, use_moderator=True)

# 토론 실행
messages = await discussion.run(
    topic=topic,
    streaming=True,
    max_statements=20
)
```

### Configuration
```python
from config.discussion_config import update_config

update_config(
    max_questions_per_discussion=2,
    prefer_building_over_challenging=0.7,
    use_cot_reasoning=True
)
```

## 📊 Improvements from v1

1. **모듈화**: 1785줄 단일 파일 → 기능별 모듈 분리
2. **자연스러운 토론**: 턴제 제거, 동적 흐름
3. **신념 기반 강화**: CoT 추론, 신념 일관성
4. **질문 제한**: 과도한 질문 방지
5. **소주제 관리**: 체계적인 토론 진행
6. **진화 개선**: 더 민감한 페르소나 변화

## 🔧 Configuration Files

- `config/config.yaml`: 시스템 설정
- `config/prompts.yaml`: 프롬프트 템플릿
- `config/discussion_config.py`: 토론 런타임 설정
- `config/config_loader.py`: 설정 로더
- `.env`: API 키 설정

## 📝 Notes

- `discussion.py`가 메인 인터페이스
- 모든 토론은 자연스러운 흐름으로 진행
- 턴제 관련 파라미터는 무시됨
- 모든 서비스는 필요에 따라 선택적으로 활성화 가능