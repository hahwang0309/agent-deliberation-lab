# 현재 사용 중인 기능 목록

> 마지막 업데이트: 2025-11-18

## 목차

- [1. 핵심 기능 개요](#1-핵심-기능-개요)
- [2. API 엔드포인트](#2-api-엔드포인트)
- [3. 프론트엔드 페이지](#3-프론트엔드-페이지)
- [4. 핵심 서비스 및 모듈](#4-핵심-서비스-및-모듈)
- [5. 데이터베이스 모델](#5-데이터베이스-모델)
- [6. 설정 시스템](#6-설정-시스템)
- [7. 배포 환경](#7-배포-환경)
- [8. 워크플로우](#8-워크플로우)
- [9. 기술 스택](#9-기술-스택)

---

## 1. 핵심 기능 개요

### 1.1 행정조사 중복 판별 시스템 ⭐ 메인 기능

**목적**: 두 개의 행정조사가 중복되는지 AI 멀티 에이전트 토론을 통해 판별

**주요 특징**:
- AI가 자동으로 전문가 페르소나 생성 (3-7명)
- 실시간 SSE 스트리밍으로 토론 과정 가시화
- 루브릭 기반 객관적 점수 산출 (4개 기준, 총 100점)
- Markdown 형식 보고서 자동 생성
- 게스트 모드 지원 (로그인 불필요)

**판정 기준** (루브릭):
1. **①-1 모집단 중복도** (30점): 조사대상 범위의 중복 정도
2. **①-2 실제 대상 중복 가능성** (20점): 실제로 중복 조사받을 가능성
3. **②-1 내용 중복도** (30점): 조사 항목 및 내용의 중복
4. **②-2 제출 자료 중복도** (20점): 제출 서류의 중복

**최종 판정**: 총점 60점 이상 시 "중복"

### 1.2 배치 분석

**목적**: 여러 개의 조사 쌍을 한 번에 분석

**주요 특징**:
- 텍스트 파일 업로드로 여러 쌍 입력
- 순차 분석 및 진행률 추적
- 일시정지/재개 지원
- ZIP 파일로 보고서 일괄 다운로드

### 1.3 일반 토론 시스템

**목적**: 범용 멀티 에이전트 토론

**주요 특징**:
- 커스텀 주제 및 페르소나 설정
- 토론 단계별 시간 관리 (OPENING, EXPLORATION, DEEP_DIVE, SYNTHESIS, CLOSING)
- 합의도 추적
- 토론 분석 및 요약

### 1.4 RAG 웹 검색 (옵션)

**목적**: 최신 법령, 판례 검색을 통한 근거 강화

**주요 특징**:
- Tavily API 사용
- 검색 결과를 페르소나 발언에 반영
- 선택적 활성화 가능

---

## 2. API 엔드포인트

### 2.1 행정조사 분석 (`/api/v1/investigations`)

| 메서드 | 엔드포인트 | 설명 | 주요 기능 |
|--------|-----------|------|----------|
| POST | `/stream` | SSE 스트리밍 분석 | 실시간 토론 과정 전송 |
| POST | `/` | 백그라운드 분석 | 비동기 분석 (결과는 ID로 조회) |
| GET | `/{id}` | 분석 결과 조회 | JSON 형식 결과 반환 |
| GET | `/{id}/report` | 보고서 다운로드 | Markdown 파일 다운로드 |
| GET | `/` | 분석 이력 목록 | 페이지네이션 지원 |
| DELETE | `/{id}` | 분석 삭제 | 완전 삭제 또는 소프트 삭제 |

**주요 파라미터**:
```json
{
  "investigation_a_name": "조사A 제목",
  "investigation_a_data": "조사A 상세 내용",
  "investigation_b_name": "조사B 제목",
  "investigation_b_data": "조사B 상세 내용",
  "config": {
    "min_rounds": 3,
    "max_rounds": 10,
    "num_personas": 5,
    "enable_rag": false
  }
}
```

**SSE 이벤트 타입**:
- `analysis_started`: 분석 시작
- `phase_start`: 페이즈 시작 (persona_generation, discussion, scoring 등)
- `personas_generated`: 페르소나 생성 완료
- `round_start`: 라운드 시작
- `moderator_message`: 모더레이터 메시지
- `persona_token`: 페르소나 발언 토큰 (실시간 스트리밍)
- `consensus_check`: 합의도 체크
- `scoring_complete`: 루브릭 점수 계산 완료
- `analysis_complete`: 분석 완료
- `error`: 에러 발생

### 2.2 배치 분석 (`/api/v1/batch-analyses`)

| 메서드 | 엔드포인트 | 설명 |
|--------|-----------|------|
| POST | `/` | 배치 생성 및 시작 |
| GET | `/{id}` | 배치 상태 조회 |
| POST | `/{id}/pause` | 배치 일시정지 |
| POST | `/{id}/resume` | 배치 재개 |
| GET | `/{id}/download` | ZIP 다운로드 |
| GET | `/` | 배치 목록 |
| DELETE | `/{id}` | 배치 삭제 |

**텍스트 파일 형식**:
```
조사A 제목1
---
조사A 내용1
---
조사B 제목1
---
조사B 내용1
===
조사A 제목2
---
조사A 내용2
...
```

### 2.3 일반 토론 (`/api/v1/discussions`)

| 메서드 | 엔드포인트 | 설명 |
|--------|-----------|------|
| POST | `/` | 토론 생성 |
| POST | `/{id}/start` | 토론 시작 |
| POST | `/{id}/pause` | 일시정지 |
| POST | `/{id}/resume` | 재개 |
| POST | `/{id}/stop` | 종료 |
| GET | `/{id}/stream` | SSE 스트리밍 |
| GET | `/` | 토론 목록 |
| GET | `/{id}` | 토론 상세 |

### 2.4 메시지 (`/api/v1/messages`)

| 메서드 | 엔드포인트 | 설명 |
|--------|-----------|------|
| GET | `/discussions/{id}/messages` | 토론 메시지 조회 |

### 2.5 분석 (`/api/v1/analytics`)

| 메서드 | 엔드포인트 | 설명 |
|--------|-----------|------|
| GET | `/discussions/{id}/summary` | 토론 요약 |
| GET | `/discussions/{id}/persona-evolution` | 페르소나 진화 추적 |

### 2.6 페르소나 (`/api/v1/personas`)

| 메서드 | 엔드포인트 | 설명 |
|--------|-----------|------|
| GET | `/templates` | 템플릿 목록 |
| POST | `/custom` | 커스텀 페르소나 생성 |
| GET | `/` | 사용자 페르소나 목록 |

### 2.7 내보내기 (`/api/v1/export`)

| 메서드 | 엔드포인트 | 설명 |
|--------|-----------|------|
| GET | `/discussions/{id}/json` | JSON 내보내기 |
| GET | `/discussions/{id}/markdown` | Markdown 내보내기 |

### 2.8 설정 (`/api/v1/config`)

| 메서드 | 엔드포인트 | 설명 |
|--------|-----------|------|
| GET | `/llm-providers` | LLM 프로바이더 상태 |
| GET | `/system` | 시스템 설정 |

### 2.9 인증 (`/api/v1/auth`)

| 메서드 | 엔드포인트 | 설명 |
|--------|-----------|------|
| POST | `/register` | 회원가입 |
| POST | `/login` | 로그인 |
| POST | `/refresh` | 토큰 갱신 |

### 2.10 사용자 (`/api/v1/users`)

| 메서드 | 엔드포인트 | 설명 |
|--------|-----------|------|
| GET | `/me` | 내 정보 조회 |
| PUT | `/me` | 정보 수정 |
| PUT | `/me/password` | 비밀번호 변경 |

---

## 3. 프론트엔드 페이지

### 3.1 메인 UI (`frontend/index.html`) ⭐

**접근 경로**: `http://localhost:8106/`

**주요 기능**:
1. **새 분석 탭**
   - 조사 A, B 텍스트 입력
   - 설정: 최소/최대 라운드, 페르소나 수, RAG 활성화
   - 실시간 SSE 스트리밍 로그
   - 토큰 단위 출력 (타이핑 효과)
   - 페르소나별 색상 구분

2. **분석 이력 탭**
   - 과거 분석 목록
   - 상세 보기 (토론 내역, 루브릭 점수)
   - Markdown 보고서 다운로드
   - 삭제 기능

3. **배치 분석 탭**
   - 텍스트 파일 업로드
   - 진행률 표시 (프로그레스 바)
   - ZIP 다운로드

**UI 특징**:
- Tailwind CSS 기반 반응형 디자인
- 다크 모드 기본 적용
- 루브릭 점수 시각화 (프로그레스 바)
- 페르소나별 아바타 및 색상

### 3.2 간소화 UI (`frontend/investigation_analysis.html`)

**접근 경로**: `http://localhost:8106/investigation_analysis.html`

**주요 기능**:
- 폴링 방식 상태 확인 (비SSE)
- Marked.js로 Markdown 렌더링
- 보고서 미리보기

**용도**: SSE를 지원하지 않는 환경에서 사용

### 3.3 일반 토론 UI (`frontend/discussion.html`)

**접근 경로**: `http://localhost:8106/discussion.html`

**주요 기능**:
- 커스텀 토론 주제 입력
- 페르소나 선택
- 토론 시작/일시정지/재개/종료
- 메시지 실시간 표시

**활성화 여부**: 파일은 존재하나 메인 워크플로우에서 사용 빈도 낮음

---

## 4. 핵심 서비스 및 모듈

### 4.1 코어 서비스 (`src/services/`)

#### 4.1.1 `discussion_manager.py`

**역할**: 토론 시간 및 주제 관리

**클래스**: `DiscussionManager`

**주요 메서드**:
```python
def allocate_time_for_phase(phase: str) -> int
def select_next_subtopic() -> str
def track_coverage(subtopic: str) -> float
```

**토론 단계**:
- `OPENING`: 주제 소개 및 초기 입장 공유
- `EXPLORATION`: 다양한 관점 탐색
- `DEEP_DIVE`: 핵심 쟁점 깊이 분석
- `SYNTHESIS`: 의견 종합 및 합의 도출
- `CLOSING`: 결론 및 정리

#### 4.1.2 `belief_reasoning.py`

**역할**: 페르소나의 신념 수정 (Belief Revision)

**주요 기능**:
- 새로운 정보 수용 시 기존 신념 업데이트
- 논리적 일관성 유지
- 의견 변화 추적

#### 4.1.3 `report_generator.py`

**역할**: Markdown 보고서 생성

**주요 메서드**:
```python
def generate_investigation_report(
    analysis_data: dict,
    verdict: str,
    confidence: float
) -> str
```

**보고서 섹션**:
1. 개요
2. 참여 페르소나
3. 토론 과정 (라운드별)
4. 루브릭 점수 상세
5. 최종 판정
6. 권고사항

#### 4.1.4 `web_search.py`

**역할**: RAG 웹 검색 (Tavily API)

**주요 기능**:
- 법령, 판례 검색
- 검색 결과 요약
- 페르소나 발언에 근거 제공

**환경변수**: `TAVILY_API_KEY`

### 4.2 API 서비스 (`api/services/`)

#### 4.2.1 `investigation_discussion_service.py` ⭐ 핵심

**역할**: 행정조사 중복 판별 토론 전체 프로세스 관리

**클래스**: `InvestigationDiscussionService`

**주요 메서드**:

```python
async def conduct_discussion(
    investigation_a: dict,
    investigation_b: dict,
    config: dict,
    event_callback: Optional[Callable] = None
) -> dict
```

**프로세스**:
1. 페르소나 자동 생성 (3-7명)
2. 사전 중복 판별
3. 모더레이터 가이드 생성
4. 라운드별 토론 진행 (3-10 라운드)
5. 합의도 체크 (70% 이상 시 조기 종료)
6. 루브릭 점수 계산
7. 보고서 생성

**이벤트 발행**:
- SSE를 통한 실시간 진행 상황 전송
- 토큰 단위 스트리밍 지원

#### 4.2.2 `persona_auto_generator.py`

**역할**: 조사 내용에 맞는 전문가 페르소나 자동 생성

**주요 메서드**:

```python
async def generate_personas(
    investigation_a: str,
    investigation_b: str,
    num_personas: int = 5
) -> List[dict]
```

**생성 과정**:
1. 조사 내용 분석 (LLM)
2. 필요한 전문 분야 식별
3. 페르소나 프로파일 생성
   - 이름 (한국어)
   - 역할 (예: 세무전문가, 통계전문가, 법률전문가)
   - 전문성 영역
   - 의사결정 스타일
   - 초기 관점

**예시 페르소나**:
```json
{
  "name": "김지혜",
  "role": "세무전문가",
  "expertise": ["법인세", "부가가치세", "조세조약"],
  "style": "분석적이고 논리적",
  "initial_stance": "조사대상의 법적 정의를 명확히 해야 함"
}
```

#### 4.2.3 `moderator_agent.py`

**역할**: 토론 모더레이터 AI

**주요 기능**:
- Opening: 토론 안내 및 규칙 설명
- 라운드별 가이드 생성 (핵심 쟁점 제시)
- 합의 유도
- Closing: 결론 종합

**프롬프트 예시**:
```
당신은 공정하고 전문적인 토론 모더레이터입니다.
현재 라운드 {round_num}에서 다음 쟁점을 다룹니다:
- {key_point}

각 참여자가 균형있게 의견을 제시하도록 유도하세요.
```

#### 4.2.4 `discussion_service.py`

**역할**: 일반 토론 CRUD 및 상태 관리

**주요 메서드**:
```python
async def create_discussion(topic: str, config: dict) -> Discussion
async def start_discussion(discussion_id: int)
async def pause_discussion(discussion_id: int)
async def resume_discussion(discussion_id: int)
async def stop_discussion(discussion_id: int)
```

**상태 관리**:
- `pending`: 생성됨
- `in_progress`: 진행 중
- `paused`: 일시정지
- `completed`: 완료
- `failed`: 실패

#### 4.2.5 기타 서비스

- **auth_service.py**: JWT 토큰 발급, 검증
- **user_service.py**: 사용자 CRUD
- **message_service.py**: 메시지 저장 및 조회
- **analytics_service.py**: 토론 분석, 통계
- **export_service.py**: JSON/Markdown 내보내기
- **config_service.py**: 설정 관리

### 4.3 유틸리티 (`src/utils/`, `api/utils/`)

#### 4.3.1 `llm_provider.py` (src/utils/)

**역할**: 멀티 LLM 프로바이더 통합

**지원 프로바이더**:
- OpenAI (GPT-4o-mini, GPT-4o, GPT-4-turbo) ⭐ 기본
- Anthropic (Claude 3.5 Sonnet, Claude 3 Opus)
- Google (Gemini Pro, Gemini 1.5 Pro)
- Mistral (Mistral Large, Mistral Medium)

**주요 메서드**:
```python
async def generate_response(
    prompt: str,
    provider: str = "openai",
    model: str = "gpt-4o-mini",
    temperature: float = 0.7,
    stream: bool = False
) -> Union[str, AsyncIterator[str]]
```

**스트리밍 지원**: 모든 프로바이더에서 토큰 단위 스트리밍 가능

#### 4.3.2 `language_detector.py`

**역할**: 언어 감지 및 프롬프트 자동 번역

**주요 기능**:
- 입력 텍스트 언어 자동 감지
- 한국어 입력 시 프롬프트 한국어로 조정
- 다국어 지원 준비

#### 4.3.3 `event_broker.py` (api/utils/)

**역할**: SSE 이벤트 Pub/Sub 브로커

**주요 메서드**:
```python
async def publish(channel: str, event: dict)
async def subscribe(channel: str) -> AsyncIterator[dict]
```

**채널 예시**:
- `investigation:{analysis_id}`: 분석별 이벤트
- `discussion:{discussion_id}`: 토론별 이벤트

#### 4.3.4 기타 유틸리티

- **security.py**: 비밀번호 해싱, JWT 토큰
- **validators.py**: 입력 검증
- **permissions.py**: 권한 관리
- **datetime_utils.py**: UTC 시간 처리
- **logger.py**: 로깅 설정

---

## 5. 데이터베이스 모델

**ORM**: SQLAlchemy
**데이터베이스**: PostgreSQL (운영), SQLite (개발)

### 5.1 `InvestigationAnalysis` ⭐ 핵심

**테이블**: `investigation_analyses`

**필드**:

| 필드 | 타입 | 설명 |
|------|------|------|
| id | Integer (PK) | 분석 ID |
| user_id | Integer (FK) | 사용자 ID (nullable, 게스트 지원) |
| status | String | processing / completed / failed |
| investigation_a_name | String | 조사A 제목 |
| investigation_b_name | String | 조사B 제목 |
| investigation_a_data | Text | 조사A 상세 내용 |
| investigation_b_data | Text | 조사B 상세 내용 |
| result_data | JSON | 분석 결과 (페르소나, 라운드, 메시지, 보고서) |
| final_verdict | String | duplicate / not_duplicate |
| confidence | Float | 신뢰도 (0.0 ~ 1.0) |
| total_rounds | Integer | 총 라운드 수 |
| created_at | DateTime | 생성 시간 (UTC) |
| completed_at | DateTime | 완료 시간 (UTC) |

**result_data 구조**:
```json
{
  "personas": [
    {
      "name": "김지혜",
      "role": "세무전문가",
      "expertise": ["법인세"],
      "style": "분석적"
    }
  ],
  "rounds": [
    {
      "round_number": 1,
      "moderator_guide": "조사대상의 범위를 먼저 논의합시다.",
      "messages": [
        {
          "speaker": "김지혜",
          "content": "법적 정의를 명확히 해야 합니다.",
          "timestamp": "2025-11-18T10:00:00Z"
        }
      ],
      "consensus_level": 0.45
    }
  ],
  "rubric_scores": {
    "모집단_중복도": {
      "score": 25,
      "max_score": 30,
      "reasoning": "조사대상 범위가 80% 중복됨"
    },
    "실제_대상_중복_가능성": {
      "score": 15,
      "max_score": 20,
      "reasoning": "..."
    },
    "내용_중복도": {
      "score": 22,
      "max_score": 30,
      "reasoning": "..."
    },
    "제출_자료_중복도": {
      "score": 18,
      "max_score": 20,
      "reasoning": "..."
    }
  },
  "total_score": 80,
  "report_markdown": "# 행정조사 중복 판별 보고서\n\n..."
}
```

### 5.2 `BatchAnalysis`

**테이블**: `batch_analyses`

**필드**:

| 필드 | 타입 | 설명 |
|------|------|------|
| id | Integer (PK) | 배치 ID |
| user_id | Integer (FK) | 사용자 ID |
| name | String | 배치 이름 |
| status | String | pending / processing / completed / paused / failed |
| items | JSON | 분석 항목 목록 |
| progress | Integer | 진행률 (0-100) |
| created_at | DateTime | 생성 시간 |
| completed_at | DateTime | 완료 시간 |

**items 구조**:
```json
[
  {
    "index": 0,
    "investigation_a_name": "...",
    "investigation_a_data": "...",
    "investigation_b_name": "...",
    "investigation_b_data": "...",
    "analysis_id": 123,
    "status": "completed"
  }
]
```

### 5.3 `Discussion`

**테이블**: `discussions`

**필드**:

| 필드 | 타입 | 설명 |
|------|------|------|
| id | Integer (PK) | 토론 ID |
| topic | String | 토론 주제 |
| status | String | pending / in_progress / paused / completed |
| config | JSON | 토론 설정 |
| participants | JSON | 페르소나 목록 |
| created_by | Integer (FK) | 생성자 ID |
| started_at | DateTime | 시작 시간 |
| completed_at | DateTime | 완료 시간 |

### 5.4 `Message`

**테이블**: `messages`

**필드**:

| 필드 | 타입 | 설명 |
|------|------|------|
| id | Integer (PK) | 메시지 ID |
| discussion_id | Integer (FK) | 토론 ID |
| speaker | String | 발언자 (페르소나 이름 또는 "moderator") |
| content | Text | 메시지 내용 |
| created_at | DateTime | 생성 시간 |

### 5.5 `Persona`

**테이블**: `personas`

**필드**:

| 필드 | 타입 | 설명 |
|------|------|------|
| id | Integer (PK) | 페르소나 ID |
| user_id | Integer (FK) | 생성자 ID |
| name | String | 이름 |
| role | String | 역할 |
| expertise | JSON | 전문 분야 목록 |
| style | String | 의사결정 스타일 |
| template_id | String | 템플릿 ID (nullable) |

### 5.6 `User`

**테이블**: `users`

**필드**:

| 필드 | 타입 | 설명 |
|------|------|------|
| id | Integer (PK) | 사용자 ID |
| name | String | 이름 |
| email | String (Unique) | 이메일 |
| hashed_password | String | 해시된 비밀번호 |
| subscription_plan | String | basic / premium / enterprise |
| created_at | DateTime | 가입 시간 |

---

## 6. 설정 시스템

### 6.1 환경변수 (`.env`)

```bash
# 데이터베이스
DATABASE_URL=postgresql://persona_admin:your_password@your-db-host:5432/personadb

# LLM API 키
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
GOOGLE_API_KEY=...
MISTRAL_API_KEY=...

# RAG (옵션)
TAVILY_API_KEY=tvly-...

# 보안
SECRET_KEY=<auto-generated>

# API 설정
API_HOST=0.0.0.0
API_PORT=8000
CORS_ORIGINS=http://localhost:3000,http://localhost:8106

# 로깅
LOG_LEVEL=INFO
```

### 6.2 YAML 설정 (`config/config.yaml`)

```yaml
llm:
  default_provider: openai
  default_model: gpt-4o-mini
  temperature: 0.7
  max_tokens: 2000

discussion:
  min_rounds: 3
  max_rounds: 10
  consensus_threshold: 0.7
  time_per_round: 300

investigation:
  default_num_personas: 5
  rubric_weights:
    모집단_중복도: 30
    실제_대상_중복_가능성: 20
    내용_중복도: 30
    제출_자료_중복도: 20
  pass_threshold: 60

rag:
  enabled: false
  max_results: 5
```

### 6.3 프롬프트 설정 (`config/prompts.yaml`)

**용도**: 일반 토론용 시스템 프롬프트

**예시**:
```yaml
moderator:
  opening: |
    당신은 공정하고 전문적인 토론 모더레이터입니다.
    주제: {topic}
    참여자들이 균형있게 의견을 제시하도록 안내하세요.

persona:
  system: |
    당신은 {role}입니다.
    전문 분야: {expertise}
    의사결정 스타일: {style}
```

### 6.4 RAG 프롬프트 (`config/rag_prompts.yaml`)

**용도**: 웹 검색 결과 요약 프롬프트

---

## 7. 배포 환경

### 7.1 Docker 구성

**Dockerfile**:
- Base: `python:3.11-slim`
- Multi-stage build (builder + runtime)
- 비루트 사용자 (appuser:1000)
- 헬스체크 포함 (`/health`)
- 타임존: Asia/Seoul

**docker-compose.yml**:
```yaml
services:
  api:
    build: .
    ports:
      - "8106:8000"
    environment:
      DATABASE_URL: postgresql://...
      OPENAI_API_KEY: ${OPENAI_API_KEY}
    volumes:
      - ./config:/app/config:ro
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 2G
```

**포트**:
- 내부: 8000 (Uvicorn)
- 외부: 8106 (호스트)

**접근**:
- API: `http://localhost:8106/api/v1/`
- 프론트엔드: `http://localhost:8106/`
- API 문서: `http://localhost:8106/docs`

### 7.2 실행 방법

**Docker Compose**:
```bash
# 빌드 및 실행
docker-compose up -d --build

# 로그 확인
docker-compose logs -f

# 중지
docker-compose down
```

**로컬 개발**:
```bash
# 의존성 설치
pip install -r requirements.txt

# 환경변수 설정
cp .env.example .env
# .env 파일 편집

# DB 마이그레이션
alembic upgrade head

# API 서버 실행
python start_api.py
# 또는
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
```

### 7.3 데이터베이스

**운영 환경**:
- 호스트: your-db-host:5432
- 데이터베이스: personadb
- 사용자: persona_admin
- 비밀번호: your_password

**개발 환경** (옵션):
- SQLite: `sqlite:///./multi_persona_discussion.db`

---

## 8. 워크플로우

### 8.1 행정조사 중복 판별 워크플로우

```
┌─────────────────────────────────────────────────────────────┐
│ 1. 사용자 입력 (index.html)                                  │
│    - 조사 A, B 텍스트 입력                                   │
│    - 설정: 최소/최대 라운드, 페르소나 수, RAG 활성화          │
└────────────────────┬────────────────────────────────────────┘
                     ↓
┌─────────────────────────────────────────────────────────────┐
│ 2. API 요청 (POST /api/v1/investigations/stream)            │
│    - SSE 스트리밍 연결                                       │
└────────────────────┬────────────────────────────────────────┘
                     ↓
┌─────────────────────────────────────────────────────────────┐
│ 3. 백그라운드 분석 (investigation_discussion_service.py)     │
│                                                              │
│    a. 페르소나 자동 생성 (persona_auto_generator.py)         │
│       - 조사 내용 분석 → LLM으로 전문 분야 식별              │
│       - 3-7명 전문가 생성                                    │
│       - 이벤트: personas_generated                          │
│                                                              │
│    b. 사전 판별 (preliminary_check)                         │
│       - 조사대상 비교                                        │
│       - 초기 중복도 예측                                     │
│       - 이벤트: phase_start (preliminary)                   │
│                                                              │
│    c. 토론 진행 (3-10 라운드)                               │
│       ┌─────────────────────────────────────────┐          │
│       │ Opening (모더레이터)                     │          │
│       │  - 토론 안내 및 규칙 설명                │          │
│       │  - 이벤트: moderator_message            │          │
│       └─────────────────┬───────────────────────┘          │
│                         ↓                                   │
│       ┌─────────────────────────────────────────┐          │
│       │ 각 라운드 (Round 1, 2, 3...)             │          │
│       │                                          │          │
│       │  1) 모더레이터 가이드 생성                │          │
│       │     - 이전 라운드 요약                   │          │
│       │     - 핵심 쟁점 제시                     │          │
│       │     - 이벤트: moderator_message         │          │
│       │                                          │          │
│       │  2) 페르소나별 발언 (순차)               │          │
│       │     - LLM 호출 (스트리밍)                │          │
│       │     - 토큰 단위 전송                     │          │
│       │     - 이벤트: persona_token             │          │
│       │     - Message DB 저장                   │          │
│       │                                          │          │
│       │  3) 합의도 체크                          │          │
│       │     - 페르소나 간 의견 일치도 계산        │          │
│       │     - 70% 이상 시 조기 종료 고려         │          │
│       │     - 이벤트: consensus_check           │          │
│       └─────────────────┬───────────────────────┘          │
│                         ↓                                   │
│       ┌─────────────────────────────────────────┐          │
│       │ Closing (모더레이터)                     │          │
│       │  - 토론 내용 종합                        │          │
│       │  - 합의 사항 정리                        │          │
│       └─────────────────────────────────────────┘          │
│                                                              │
│    d. 루브릭 점수 계산 (scoring_phase)                       │
│       - ①-1 모집단 중복도 (30점)                            │
│       - ①-2 실제 대상 중복 가능성 (20점)                    │
│       - ②-1 내용 중복도 (30점)                              │
│       - ②-2 제출 자료 중복도 (20점)                         │
│       - 총점 계산 (60점 이상 = 중복)                        │
│       - 이벤트: scoring_complete                            │
│                                                              │
│    e. 보고서 생성 (report_generator.py)                      │
│       - Markdown 형식 보고서                                │
│       - 섹션: 개요, 페르소나, 토론, 루브릭, 판정, 권고       │
└────────────────────┬────────────────────────────────────────┘
                     ↓
┌─────────────────────────────────────────────────────────────┐
│ 4. 실시간 스트리밍 (SSE)                                     │
│    - 이벤트 타입별 처리                                      │
│    - 프론트엔드에서 동적 UI 업데이트                          │
└────────────────────┬────────────────────────────────────────┘
                     ↓
┌─────────────────────────────────────────────────────────────┐
│ 5. DB 저장 (InvestigationAnalysis)                           │
│    - status: completed                                       │
│    - result_data: JSON (페르소나, 라운드, 메시지, 보고서)     │
│    - final_verdict: duplicate / not_duplicate                │
│    - confidence: 0.0 ~ 1.0                                   │
└────────────────────┬────────────────────────────────────────┘
                     ↓
┌─────────────────────────────────────────────────────────────┐
│ 6. 사용자 조회 및 다운로드                                   │
│    - 분석 이력 탭에서 결과 확인                              │
│    - 보고서 다운로드 (Markdown)                              │
│    - 삭제 기능                                               │
└─────────────────────────────────────────────────────────────┘
```

### 8.2 배치 분석 워크플로우

```
┌─────────────────────────────────────────────────────────────┐
│ 1. 텍스트 파일 업로드 (index.html - 배치 분석 탭)            │
│    - 형식: "===" 구분자로 쌍 구분, "---"로 A-B 구분         │
└────────────────────┬────────────────────────────────────────┘
                     ↓
┌─────────────────────────────────────────────────────────────┐
│ 2. 배치 생성 (POST /api/v1/batch-analyses)                  │
│    - BatchAnalysis 모델 생성                                │
│    - items 배열에 각 쌍 저장                                 │
│    - status: pending                                        │
└────────────────────┬────────────────────────────────────────┘
                     ↓
┌─────────────────────────────────────────────────────────────┐
│ 3. 순차 분석 (백그라운드 태스크)                             │
│    - 각 항목마다:                                            │
│      1) InvestigationAnalysis 생성                          │
│      2) conduct_discussion() 호출                           │
│      3) 결과 저장                                            │
│      4) BatchAnalysis.items[i].status = completed           │
│      5) BatchAnalysis.progress 업데이트                     │
└────────────────────┬────────────────────────────────────────┘
                     ↓
┌─────────────────────────────────────────────────────────────┐
│ 4. 진행률 추적 (GET /api/v1/batch-analyses/{id})            │
│    - 프론트엔드에서 폴링                                     │
│    - 프로그레스 바 업데이트                                  │
└────────────────────┬────────────────────────────────────────┘
                     ↓
┌─────────────────────────────────────────────────────────────┐
│ 5. ZIP 다운로드 (GET /api/v1/batch-analyses/{id}/download)  │
│    - 각 분석의 Markdown 보고서를 ZIP으로 묶음                │
│    - 파일명: {investigation_a_name}_vs_{b_name}.md          │
└─────────────────────────────────────────────────────────────┘
```

---

## 9. 기술 스택

### 9.1 백엔드

| 카테고리 | 기술 | 용도 |
|---------|------|------|
| 웹 프레임워크 | FastAPI | RESTful API, 비동기 처리 |
| ORM | SQLAlchemy | 데이터베이스 모델링 |
| 마이그레이션 | Alembic | DB 스키마 버전 관리 |
| 인증 | JWT (python-jose) | 토큰 기반 인증 |
| 비동기 | asyncio, aiohttp | 비동기 I/O |
| 스트리밍 | SSE-Starlette | Server-Sent Events |
| 검증 | Pydantic | 데이터 검증 |
| 설정 | python-dotenv, PyYAML | 환경변수, YAML 설정 |

### 9.2 AI/ML

| 카테고리 | 기술 | 용도 |
|---------|------|------|
| LLM 체인 | LangChain, LangGraph | AI 워크플로우 관리 |
| OpenAI | openai (SDK) | GPT-4o-mini (메인 LLM) ⭐ |
| Anthropic | anthropic (SDK) | Claude 3.5 Sonnet (옵션) |
| Google | google-generativeai | Gemini Pro (옵션) |
| Mistral | mistralai (SDK) | Mistral Large (옵션) |
| 웹 검색 | Tavily | RAG 웹 검색 |
| 언어 감지 | langdetect | 자동 언어 감지 |

### 9.3 프론트엔드

| 카테고리 | 기술 | 용도 |
|---------|------|------|
| JavaScript | Vanilla JS | 동적 UI |
| CSS | Tailwind CSS | 스타일링 |
| Markdown | Marked.js | Markdown 렌더링 |
| SSE | EventSource API | 실시간 스트리밍 수신 |

### 9.4 데이터베이스

| 카테고리 | 기술 | 용도 |
|---------|------|------|
| 운영 DB | PostgreSQL | 관계형 데이터베이스 |
| 개발 DB | SQLite | 로컬 개발 |
| 드라이버 | psycopg2-binary | PostgreSQL 연결 |

### 9.5 배포 및 인프라

| 카테고리 | 기술 | 용도 |
|---------|------|------|
| 컨테이너 | Docker | 애플리케이션 격리 |
| 오케스트레이션 | Docker Compose | 다중 컨테이너 관리 |
| ASGI 서버 | Uvicorn | FastAPI 실행 |
| 프로세스 관리 | Gunicorn (옵션) | 프로덕션 배포 |

### 9.6 개발 도구

| 카테고리 | 기술 | 용도 |
|---------|------|------|
| 로깅 | logging (Python 표준) | 로그 관리 |
| 데이터 처리 | pandas, openpyxl | Excel 처리 (배치 분석 옵션) |
| 타입 힌팅 | typing (Python 표준) | 타입 안정성 |
| 비밀번호 | passlib, bcrypt | 비밀번호 해싱 |

### 9.7 의존성 요약 (requirements.txt)

**핵심 의존성**:
```
fastapi==0.115.6
uvicorn[standard]==0.34.0
sqlalchemy==2.0.36
alembic==1.14.0
langchain==0.3.13
langchain-openai==0.2.14
openai==1.59.3
sse-starlette==2.2.1
pydantic==2.10.3
python-jose[cryptography]==3.3.0
passlib[bcrypt]==1.7.4
psycopg2-binary==2.9.10
python-dotenv==1.0.1
```

**전체 목록**: [requirements.txt](../requirements.txt)

---

## 10. 주요 설정 및 파라미터

### 10.1 행정조사 분석 설정

| 파라미터 | 기본값 | 범위 | 설명 |
|---------|--------|------|------|
| min_rounds | 3 | 1-20 | 최소 토론 라운드 |
| max_rounds | 10 | 1-20 | 최대 토론 라운드 |
| num_personas | 5 | 3-7 | 생성할 페르소나 수 |
| consensus_threshold | 0.7 | 0.0-1.0 | 조기 종료 합의도 임계값 |
| enable_rag | false | true/false | RAG 웹 검색 활성화 |

### 10.2 LLM 설정

| 파라미터 | 기본값 | 설명 |
|---------|--------|------|
| provider | openai | LLM 프로바이더 |
| model | gpt-4o-mini | 모델명 |
| temperature | 0.7 | 창의성 (0.0-2.0) |
| max_tokens | 2000 | 최대 토큰 수 |
| stream | true | 스트리밍 활성화 |

### 10.3 루브릭 가중치

| 기준 | 배점 |
|------|------|
| ①-1 모집단 중복도 | 30점 |
| ①-2 실제 대상 중복 가능성 | 20점 |
| ②-1 내용 중복도 | 30점 |
| ②-2 제출 자료 중복도 | 20점 |
| **총점** | **100점** |
| **중복 판정 기준** | **60점 이상** |

---

## 11. 보안 및 제한사항

### 11.1 보안 기능

1. **JWT 토큰 인증**
   - Access Token (15분 유효)
   - Refresh Token (7일 유효)

2. **비밀번호 해싱**
   - bcrypt 알고리즘
   - 솔트 자동 생성

3. **CORS 설정**
   - 허용된 오리진만 접근 가능
   - 환경변수로 관리

4. **SQL Injection 방지**
   - SQLAlchemy ORM 사용
   - 파라미터화된 쿼리

5. **입력 검증**
   - Pydantic 스키마 검증
   - 길이 제한, 타입 체크

### 11.2 제한사항

| 제한 항목 | 값 | 설명 |
|----------|-----|------|
| 조사 텍스트 최대 길이 | 10,000자 | 너무 긴 텍스트 방지 |
| 페르소나 최대 수 | 7명 | LLM 컨텍스트 제한 |
| 토론 최대 라운드 | 20 | 무한 루프 방지 |
| 배치 분석 최대 항목 | 100개 | 서버 부하 제한 |
| SSE 타임아웃 | 30분 | 연결 유지 시간 |

---

## 12. 에러 처리

### 12.1 주요 에러 코드

| HTTP 코드 | 설명 | 처리 방법 |
|-----------|------|----------|
| 400 | 잘못된 요청 | 입력 검증 실패 메시지 반환 |
| 401 | 인증 실패 | 로그인 필요 |
| 403 | 권한 없음 | 접근 거부 메시지 |
| 404 | 리소스 없음 | 존재하지 않는 분석/토론 |
| 422 | 검증 실패 | Pydantic 검증 상세 메시지 |
| 500 | 서버 오류 | LLM API 오류, DB 연결 오류 등 |

### 12.2 에러 응답 형식

```json
{
  "detail": "에러 메시지",
  "error_code": "INVALID_INPUT",
  "timestamp": "2025-11-18T10:00:00Z"
}
```

---

## 13. 로깅

### 13.1 로그 레벨

| 레벨 | 용도 |
|------|------|
| DEBUG | 개발 디버깅 (LLM 프롬프트, 응답) |
| INFO | 일반 정보 (API 요청, 분석 시작/완료) |
| WARNING | 경고 (합의 실패, 재시도) |
| ERROR | 오류 (LLM API 실패, DB 오류) |
| CRITICAL | 치명적 오류 (서버 다운) |

### 13.2 로그 형식

```
2025-11-18 10:00:00,000 - INFO - [investigation_discussion_service.py:123] - Analysis 456 started
2025-11-18 10:00:05,123 - INFO - [persona_auto_generator.py:45] - Generated 5 personas
2025-11-18 10:00:30,456 - ERROR - [llm_provider.py:89] - OpenAI API error: Rate limit exceeded
```

---

## 14. 향후 확장 가능성

### 14.1 계획된 기능 (Roadmap)

1. **실시간 협업**
   - 여러 사용자가 동시에 토론 관찰
   - WebSocket 기반 실시간 채팅

2. **커스텀 루브릭**
   - 사용자 정의 평가 기준
   - 가중치 조정 UI

3. **다국어 지원**
   - 영어, 중국어, 일본어 프롬프트
   - 자동 번역

4. **통계 대시보드**
   - 분석 이력 통계
   - 평균 중복도, 자주 사용된 페르소나 등

5. **API 키 관리**
   - 사용자별 API 키 설정
   - 사용량 추적

### 14.2 기술 부채

- [ ] 테스트 커버리지 확대 (현재 < 50%)
- [ ] API 문서 자동화 (OpenAPI 스키마 완성도 향상)
- [ ] 성능 최적화 (DB 쿼리 최적화, 캐싱)
- [ ] 에러 핸들링 표준화

---

## 15. 관련 문서

- [README.md](../README.md) - 빠른 시작 가이드
- [ARCHITECTURE.md](./ARCHITECTURE.md) - 아키텍처 상세
- [API_REFERENCE.md](./API_REFERENCE.md) - API 명세 (TODO)
- [DEPLOYMENT.md](./DEPLOYMENT.md) - 배포 가이드 (TODO)

---

**문서 작성일**: 2025-11-18
**버전**: 1.0.0
**작성자**: Claude Code
