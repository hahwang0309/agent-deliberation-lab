# 설정

설정은 세 곳에 나뉩니다.

| 위치 | 담는 내용 |
|---|---|
| `.env` | 비밀값과 환경별 값 |
| `config/config.yaml` | 동작 파라미터 |
| `config/*.yaml` | 프롬프트와 템플릿 |

## `.env`

| 변수 | 필수 | 설명 |
|---|---|---|
| `ANTHROPIC_API_KEY` | ✓ (기본 provider) | Claude API 키 |
| `OPENAI_API_KEY`, `GOOGLE_API_KEY`, `MISTRAL_API_KEY` | | 해당 provider를 참가자 LLM으로 쓸 때만 |
| `SECRET_KEY` | ✓ | JWT 서명 키, 32자 이상 무작위 값. 비었거나 예시값이면 서버가 시작되지 않음 |
| `ADMIN_EMAIL`, `ADMIN_INITIAL_PASSWORD` | 최초 1회 | 관리자가 한 명도 없을 때 시작 시 관리자 생성 (첫 로그인 후 비밀번호 변경 강제) |
| `DATABASE_URL` | | 기본 `sqlite:///./discussion_api.db`. 운영은 PostgreSQL 권장 |
| `COOKIE_SECURE` | | HTTPS 운영 시 `true` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` / `REFRESH_TOKEN_EXPIRE_DAYS` | | 기본 30분 / 7일 |
| `PASSWORD_MIN_LENGTH`, `MAX_LOGIN_ATTEMPTS`, `LOGIN_ATTEMPT_TIMEOUT` | | 기본 10자 / 5회 / 300초 |
| `CORS_ORIGINS` | | 웹 UI가 같은 출처라 보통 비워 둠. 다른 출처의 프론트가 있을 때만 쉼표로 지정 |
| `LOG_LEVEL` | | 로그 레벨 (stdout 출력) |
| `TAVILY_API_KEY` | | 웹 검색(RAG)을 켤 때만. 없으면 웹 검색은 증거 없이 진행 |

## `config/config.yaml`

### `llm`

| 키 | 기본값 | 설명 |
|---|---|---|
| `default_provider` | `claude` | 참가자·페르소나 생성·보고서에서 provider를 지정하지 않을 때 사용 |
| `default_models` | `claude: claude-haiku-4-5-20251001` 등 | provider별 기본 모델 |
| `max_tokens` | 1500 | 발언 응답 상한. 실제 길이는 프롬프트의 3~8문장 지시가 정하며, 한국어는 500이면 잘림 |
| `structured_max_tokens` | 2000 | 페르소나 생성 같은 구조화 출력 상한 |
| `timeout_seconds` / `max_retries` | 60 / 2 | 모든 provider 호출에 적용 |

### `limits`

| 키 | 기본값 | 설명 |
|---|---|---|
| `max_global_running` | 5 | 서버 전체 동시 실행 토론 수 |
| `default_statements` / `max_statements` | 12 / 30 | AI 발언 수 기본값 / 상한 |
| `min_personas` / `max_personas` | 2 / 5 | 참가 페르소나 수 범위 |
| `user_max_concurrent` | 1 | 일반 사용자 동시 실행 수 (관리자 무제한, 사용자별 덮어쓰기 가능) |
| `user_daily_starts` | 5 | 일반 사용자 하루(UTC) 시작 수 (재개는 포함하지 않음) |
| `user_expensive_features` | false | 일반 사용자에게 웹 검색·신념 추론 허용 여부 (LLM 호출 수가 크게 늘어남) |
| `max_human_turns_per_user` | 5 | 토론 1건에서 1인당 발언 횟수 |
| `max_human_chars` | 1000 | 사람 발언 최대 글자 수 |

### `report`

| 키 | 기본값 | 설명 |
|---|---|---|
| `model` | null | 보고서 모델 (null이면 기본 provider의 기본 모델) |
| `max_tokens` | 4000 | 보고서 출력 상한 |
| `max_attempts` | 3 | 검증 실패 시 총 시도 횟수 |
| `min_ai_messages` | 4 | 보고서를 만들 최소 AI 발언 수 |
| `partial_weight` | 0.7 | 부분 찬성이 지지 쪽에 기여하는 비율 |
| `thresholds.agreed` / `thresholds.partial` | 0.8 / 0.6 | 수렴도 → 합의 / 부분 합의 / 이견 라벨 기준 |

### 기타

`discussion`, `system` 등 나머지 섹션은 엔진의 세부 동작 값입니다. 토론 흐름 세부값은 `config/discussion_config.py`에 있습니다. 예: 소주제 수, 모더레이터 개입 주기 `moderator_every_statements`(기본 3), 확장 선호도 `prefer_building_over_challenging`(기본 0.5), 사람 발언 후 AI 응답 수 `human_followup_responses`.

## 프롬프트·템플릿

프롬프트는 코드에 쓰지 않습니다. 코드에서는 `config_loader.prompts.render("경로", ...)`로 불러옵니다.

| 파일 | 내용 |
|---|---|
| `config/prompts.yaml` | 페르소나 생성, 에이전트 시스템 프롬프트, 발언 액션별 프롬프트(`turn_actions.*`, 사람 발언 응답 포함), 모더레이터, 신념 추론, 언어 지시 |
| `config/report_prompts.yaml` | 쟁점 추출, 재시도 피드백, 요약 (`report.` 네임스페이스로 로드) |
| `config/rag_prompts.yaml` | 웹 검색용 질의 생성·분류·증거 추출 |
| `config/persona_templates.yaml` | 화면의 페르소나 템플릿 목록 |

프롬프트를 바꾸면 서버를 재시작해야 적용됩니다.
