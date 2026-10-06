# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Setup
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # OPENAI_API_KEY·ADMIN_PASSWORD 필수, DATABASE_URL 기본 sqlite:///./discussion_api.db

# API 서버 (frontend/ 정적 파일도 함께 서빙) — http://localhost:8000, 문서 /docs
python start_api.py             # DEBUG=True면 reload

# Docker (호스트 8106 → 컨테이너 8000)
./docker-start.sh
```

테스트는 pytest 스위트가 아니라 **실행 스크립트**다. 대부분 실행 중인 서버(`http://localhost:8000`)나 실제 LLM API 키가 필요하다.

```bash
python tests/test_rag_quick.py          # 단일 테스트 실행 예시
python test_full_flow.py                # 루트의 test_*.py: API 엔드투엔드 흐름 (서버 기동 필요)
```

`migrations/*.sql`은 DB에 수동 적용하는 SQL이다(Alembic 미사용). 테이블은 앱 시작 시 `init_db()`가 생성한다.

## Architecture

두 계층으로 나뉜다.

- **`src/` — 토론 엔진(라이브러리)**: `core/`(DiscussionAgent, DiscussionModerator, natural_discussion), `services/`(rag_service, web_search, belief_reasoning, memory_manager, report_generator), `models/`(Persona, consensus/evolution 추적), `utils/llm_provider.py`(`LLMFactory` — OpenAI/Anthropic/Google/Mistral를 LangChain으로 추상화). 진입 인터페이스는 `src/discussion.py`.
- **`api/` — FastAPI 서비스**: `routers/` → `services/` → `models/`(SQLAlchemy) / `schemas/`(Pydantic) / `mappers/` 계층. `api/main.py`가 모든 라우터를 등록하고 `frontend/*.html`을 서빙한다. API 서비스는 `src.utils.llm_provider`, `src.models.personas`, `src.services.rag_service`를 import해 엔진을 재사용한다.

핵심 흐름:
- **인증**: 관리자 1인 전용 시스템. `api/utils/admin_auth.py`의 ASGI 미들웨어가 `/health`를 제외한 전체(API·프론트·SSE)에 HTTP Basic 인증을 요구한다. 라우터 내부의 `"guest"` 사용자 처리는 레거시이며, 인증 경계는 이 미들웨어다.
- **행정조사(investigation) 분석**: `api/services/investigation_discussion_service.py`가 페르소나 자동 생성(`persona_auto_generator.py`) → 이슈별 라운드 토론(필요 시 RAG 웹검색) → 루브릭 평가 → 최종 판정/보고서 생성을 수행한다. `moderator_agent.py`가 진행을 담당한다.
- **실시간 스트리밍**: 서비스가 이벤트를 `api/utils/event_broker.py`(싱글톤 Pub/Sub)에 발행하고, 라우터가 SSE(`sse-starlette`)로 클라이언트에 전달한다.
- **설정/프롬프트**: 프롬프트는 코드에 쓰지 않고 `config/prompts.yaml`, `config/rag_prompts.yaml`에 둔다. `config/config_loader.py`가 `config.yaml`(llm/discussion/advanced_discussion/ui/system)과 프롬프트를 로드하며, `api/config.py`의 `get_prompts()`로 API에서 접근한다. 환경변수 설정은 `api/config.py`(pydantic-settings)가 `.env`에서 읽는다.

README의 `python main.py` CLI 사용법은 오래된 내용이다(`main.py`는 제거됨). 상세 설계는 `docs/ARCHITECTURE.md`, `docs/SERVICE_FLOW.md` 참고.

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