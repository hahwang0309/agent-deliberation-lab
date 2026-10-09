# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Setup
python3 -m venv venv && source venv/bin/activate
pip install -r requirements-dev.txt   # 런타임만: requirements.txt
cp .env.example .env            # SECRET_KEY(32자+)·ANTHROPIC_API_KEY·ADMIN_EMAIL/ADMIN_INITIAL_PASSWORD 필수

# API 서버 + 웹 UI(web/) — http://localhost:8000, 문서 /docs
python start_api.py             # DEBUG=True면 reload. 반드시 단일 워커 (런타임 레지스트리가 프로세스 메모리)

# Docker (호스트 8106 → 컨테이너 8000)
./docker-start.sh

# 테스트 (가짜 LLM, 임시 SQLite — API 키·서버 불필요)
pytest
pytest tests/test_runtime.py::test_stop_cancels_running_discussion   # 단일 테스트

# 연구용 배치 실험 (전용 DB 필수, docs/experiments.md)
python scripts/run_experiment.py config/experiments/example.yaml --db data/experiments.db --dry-run
python scripts/export_dataset.py --db data/experiments.db --batch <plan name> --out data/<폴더>
python scripts/build_cases.py wason --out data/cases/wason.yaml   # 연구 1 사례 생성 (원자료 data/raw/, docs/experiments.md)
python scripts/analyze_study1.py --db <DB> --plans <계획 YAML> --out <결과.json> [--blind]   # 연구 1 분석 (R lme4·lmerTest 필요)
```

DB 스키마는 Alembic으로 관리한다. 앱 시작 시 `init_db()`(`api/database.py`)가 `upgrade head`를 실행하며, Alembic 이력 없는 기존(create_all) DB는 기준 리비전으로 자동 stamp한다. 모델 변경 시:

```bash
alembic revision --autogenerate -m "설명"   # DATABASE_URL·SECRET_KEY 환경변수 필요
alembic upgrade head
alembic check                               # 모델과 마이그레이션 일치 확인
```

로그는 stdout으로만 출력되며 레벨은 `LOG_LEVEL`. LLM 타임아웃·재시도는 `config/config.yaml`의 `llm.*`, 동시 실행·발언 수 등 제한은 `limits.*`.

## Architecture

- **`src/` — 토론 엔진 (API에 의존하지 않음)**: `src/discussion.py`의 `create_discussion(ParticipantSpec[], LLMBundle)`이 참가자별 provider/model로 `DiscussionAgent`와 `DiscussionModerator`를 조립해 `NaturalDiscussion`을 만든다. `NaturalDiscussion.stream()`은 진행을 `EngineEvent`(subtopics / utterance_start / chunk / utterance / analysis)로 yield할 뿐 저장·전송하지 않는다. 토론 메커니즘: `plan_debate(N, S)`가 명제 수·예산·종결 라운드를 정하고, `_select_turn`이 상태(응답 의무·교착·성급한 합의·입장 거리)로 발언자와 발화 행위를 고른다. 발언마다 분석 LLM(temperature 0, `UtteranceAnalysis`)이 `src/core/debate_state.py`의 `DebateState`(공약 저장소, 열린 반박, Friedkin–Johnsen 입장 동역학)를 갱신한다. 상태 스냅숏은 메시지 `meta.debate`에 저장돼 재개에 쓰인다(상세: docs/architecture.md "토론 메커니즘"). `LLMBundle`(`src/utils/llm_provider.py`)은 토론 1건의 LLM 클라이언트를 캐시하고 사용량 콜백을 연결한다. 웹검색(RAG)·신념 추론은 토론별 플래그로 켜며 LLM 호출이 크게 늘어난다.
- **`api/runtime/` — 실행 런타임**: `registry.start()`가 토론을 uvicorn 메인 루프의 `asyncio.Task`로 실행한다(스레드 없음, DB 쓰기만 `asyncio.to_thread`). `runtime.py`는 완성 발언을 per-discussion `seq`로 **저장한 뒤 발행**하고, 청크는 발행만 한다. `broker.py`는 단일 루프 Pub/Sub. 서버 시작 시 실행 중이던 토론은 `interrupted`로 표시된다(`persistence.mark_active_as_interrupted`).
- **SSE** (`api/routers/messages.py` `GET /api/v1/discussions/{id}/events`): 구독 → `seq > Last-Event-ID(또는 ?since)` 메시지 재생 → `snapshot`(상태·진행 중 발화) → 실시간 이벤트 순서. 종료 상태(`DiscussionStatus.TERMINAL`)가 되면 스트림을 닫는다.
- **종합보고서**: `src/services/consensus_report.py`가 (1) 구조화 출력으로 쟁점(명제)·참가자별 입장을 추출하고 참가자명·seq를 검증해 재시도, (2) 합의 점수를 **코드로** 계산(참가자 쌍별 일치도 1 − |차이|, 찬성 1·부분찬성 w·반대 0; 종합·AI간·인간간·AI-인간간; 입장 2개 미만 쟁점은 `insufficient`), (3) 요약·열린 질문·제언을 생성한다. 입장 궤적은 `src/services/debate_dynamics.py`가 메시지 `meta`로 코드 계산해 `dynamics`에 넣는다. 실행은 `api/runtime/reports.py`(완료 시 런타임 안에서 `reporting` 단계, 중지 시 registry가 별도 태스크로 예약). 결과는 `discussion_reports` 테이블. 설정은 `config.yaml`의 `report.*`, 프롬프트는 `config/report_prompts.yaml`(`report.` 네임스페이스로 로드). 테스트는 `tests/report_stubs.py`의 가짜 LLM을 conftest가 자동 주입한다.
- **사람 개입**: `api/runtime/intervention.py`의 `HumanDesk`가 발언 대기열·발언권을 관리하며 엔진의 `InterventionGate` 역할을 한다. 엔진은 AI·모더레이터 발화가 끝날 때마다 `after_utterance()`를 호출하고, 대기열이 있으면 런타임은 `awaiting_human`으로 바뀌어 발언 제출·포기·회수·중지까지 **무기한** 기다린다. 받은 사람 발언은 다음 AI 발언(`respond_to_human`, `meta.in_reply_to_seq`)이 응답하며, 이 후속 응답은 명제 예산을 쓰고, 예산이 끝났으면 추가 발언으로 수행된다. 사람 발언은 프롬프트에서 구분자로 감싸 지시로 해석되지 않게 한다. 사람 표시 이름은 페르소나·다른 사람과 겹치면 접미사를 붙인다(보고서가 이름으로 참가자를 구분).
- **`api/`**: `routers/` → `services/` → `models/`(SQLAlchemy) / `schemas/`(Pydantic). 웹 UI는 `web/`(바닐라 HTML/JS)을 `/`에 마운트한다.
- **인증·권한**: httpOnly 쿠키 JWT(`api/utils/auth_cookies.py`, PyJWT) + double-submit CSRF(`api/utils/csrf.py`, 쿠키 인증 쓰기 요청에 `X-CSRF-Token` 필수). `api/dependencies.py`: `get_current_user`(서명·만료 + status=active + `token_version` 일치 → 정지·비밀번호 변경 시 즉시 무효), `require_active_user`(임시 비밀번호면 403), `require_admin`, `ensure_owner_or_admin`(시작·중지·삭제·보고서 재생성). 조회·SSE는 모든 활성 사용자(공동 참여). 계정은 가입 신청 → 관리자 승인 또는 관리자 발급. 최초 관리자는 시작 시 `ADMIN_EMAIL`/`ADMIN_INITIAL_PASSWORD`로 생성. 실행 제한은 `DiscussionService._check_user_limits`(관리자 제외). 웹 페이지(`web/`)는 공개, 데이터 API는 인증 필요. 테스트는 `tests/conftest.py`의 `create_user`/`LoggedInClient`를 쓴다.
- **설정 중앙화**: 모델명과 동작 파라미터(엔진·설문·분석·제한·보고서)는 `config/config.yaml`에만 둔다. 코드에 기본값·모델명을 쓰지 않는다(로더가 빠진/모르는 항목을 거부하고, `tests/test_config.py`가 코드 속 모델명을 잡는다). 엔진 설정 형식은 `config/discussion_config.py`.
- **설정/프롬프트**: 프롬프트는 코드에 쓰지 않고 `config/prompts.yaml`(엔진·모더레이터·페르소나 생성), `config/rag_prompts.yaml`에 둔다. 조회는 `config_loader.prompts.render("turn_actions.position", ...)` 형태. 페르소나 템플릿은 `config/persona_templates.yaml`.

상세 문서는 `docs/`(architecture, api-reference, configuration, deployment, development, testing, troubleshooting, changelog)에 있다. 중단된(`interrupted`) 토론은 `POST /discussions/{id}/resume`으로 재개하며, 엔진의 `NaturalDiscussion.restore()`가 저장된 발언과 마지막 `meta.debate` 스냅숏으로 턴 수·명제·토론 상태를 복원한다.

## Project Rules

### 1. 파일 관리

- 불필요한 파일은 즉시 삭제
- 사용하지 않는 코드와 의존성 제거
- **네이밍 규칙**:
    - 직관적이고 명확한 이름 사용
    - 기능을 설명하는 이름 선택
    - ❌ 금지: `_V2`, `_NEW`, `_OLD`, `_FINAL`, `_COPY` 등 버전 표시
    - ✅ 올바른 예: `user-service`, `auth-handler`, `payment-processor`
    - Git으로 버전 관리하므로 파일명에 버전 표시 불필요

### 2. 아키텍처 원칙

- **MSA(Microservice Architecture) 패턴 적용**
    - 기능별 모듈 분리
    - 단일 책임 원칙 준수
    - 다른 프로젝트에서 재사용 가능하도록 설계
    - 각 서비스/모듈 간 느슨한 결합 유지
- **AI 프롬프트 관리**
    - 프롬프트는 코드에 직접 작성 금지
    - YAML 파일로 분리하여 관리

### 3. 리팩토링 정책

- 전체 구조 개선이 필요한 경우 효율적으로 리팩토링
- 코드 중복 제거 및 재사용성 극대화
- 성능과 유지보수성 균형 고려

### 4. 작업 프로세스

**모든 작업 수행 전 필수 절차:**

1. 수행할 작업 내용 명확히 설명
2. 예상되는 변경사항 요약
3. 사용자 확인 및 승인 요청
4. 승인 후 작업 진행

### 5. 문서화 관리

- **문서 분리 원칙**:

    **README.md (빠른 시작 - 5분 이해)**

    - 프로젝트 개요 (한 문장 설명)
    - 주요 기능 (3-5개 핵심 기능)
    - Quick Start (복사 가능한 명령어)
    - 기본 사용 예제 (1-2개)
    - 요구사항 (Node 버전, 필수 의존성)
    - 라이센스 & 기여 방법
    - docs/ 링크

    **docs/ 폴더 (상세 문서)**

```other
docs/
├── architecture.md      # MSA 구조, 모듈 관계
├── api-reference.md     # API 상세 명세
├── configuration.md     # 환경변수, 설정 상세
├── deployment.md        # 배포, Docker, CI/CD
├── development.md       # 개발 환경, 컨벤션
├── testing.md          # 테스트 전략, 실행법
├── troubleshooting.md  # 문제 해결 가이드
└── changelog.md        # 버전별 변경사항
```

- **주요 변경 시 자동 업데이트**:
    - README.md: Quick Start나 주요 기능 변경 시
    - docs/: 상세 기술 문서가 필요한 변경 시

### 6. Git 푸시 정책

- **푸시 조건**: 코드에 주요한 변화가 발생했을 때만 푸시
- **푸시 전 필수 사항**:
    1. 모든 기능 테스트 실행
    2. 코드 안정성 검증
    3. 빌드 성공 여부 확인
    4. 런타임 에러 없음 확인
- **테스트 실패 시**: 문제 해결 후 재테스트 → 성공 시에만 푸시
- **커밋 메시지**: 변경사항을 명확하게 설명하는 의미있는 메시지 작성

## 예시 워크플로우

```other
1. "다음 작업을 수행하려고 합니다: [작업 내용]"
2. "변경될 사항: [파일명, 구조 변경 등]"
3. "진행해도 될까요?"
4. → 사용자 확인 후 진행
5. → 주요 변경 시 문서 업데이트
   - Quick Start 변경 → README.md
   - 기술적 상세 변경 → docs/
6. → Git 푸시 필요 시: 테스트 실행 → 안정성 확인 → 푸시
```