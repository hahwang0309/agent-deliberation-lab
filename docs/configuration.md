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
| `OPENAI_BASE_URL` | | provider `openai`의 요청을 OpenAI 호환 서버(로컬 vLLM·llama.cpp·Ollama 등)로 보냄. 설정하면 `OPENAI_API_KEY` 없이도 쓸 수 있고, 모델명은 그 서버의 이름(예: `mistral-7b-instruct-v0.3`). 모든 `openai` 호출에 적용되므로 OpenAI와 로컬 서버를 한 토론에 섞을 수는 없음 |
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

**모델명과 동작 파라미터는 이 파일에만 둡니다.** 코드에는 기본값이 없어서, 항목이 빠지거나 모르는 항목이 있으면 시작할 때 오류가 납니다(`config/config_loader.py`). 코드에 모델명을 직접 쓰면 `tests/test_config.py`가 실패합니다. 각 항목의 의미는 파일 안의 주석에 있습니다.

| 섹션 | 담는 것 | 읽는 곳 |
|---|---|---|
| `llm` | 기본 provider, provider별 기본 모델(`default_models`), temperature를 받지 않는 모델 접두어(`fixed_sampling_prefixes`), 기본·보조 작업별 temperature, 토큰 상한, 타임아웃·재시도 | `src/utils/llm_provider.py` 등 |
| `persona_generation` | 페르소나 자동 생성 시도 횟수 | `src/generators/persona_generator.py` |
| `engine` | 토론 엔진 전체: 발언 길이, 명제 수, 맥락 길이, 진행 규칙 기준, 입장 라벨 기준, 분석 맥락·temperature, 입장 동역학과 설득력 가중치, 고집도, 엔진 모드, 진행 장치, 참가자·모더레이터 temperature, 사람 개입 | `config/discussion_config.py`(형식만) → 토론별 사본 `engine_settings()` |
| `survey` | 사후 설문에 넣는 토론 기록 길이, 시도 횟수 | `src/services/survey.py` |
| `analysis` | 반복 지표 기준, 입장 궤적의 '변화 없음' 기준 | 데이터 추출, 입장 궤적 |
| `experiment_runner` | 배치 실행기 사전 추정용 발언당 토큰, `build_cases.py` 계획의 토큰 안전 상한(`plan_max_total_tokens`) | `api/services/experiment_runner.py` |
| `limits` | 서버 실행 제한(동시 실행, 발언 수, 참가자 수, 사용자 제한, 사람 발언) | API·런타임 |
| `report` | 보고서 모델·temperature·토큰·시도 횟수, 합의 점수 기준 | 보고서 |

- `engine`의 모든 값은 실행 기록(`run_info.settings`)에 남고, 실험 조건(아래)으로 토론마다 덮어쓸 수 있는 항목이 있습니다. 동작은 [architecture.md](architecture.md#토론-메커니즘)를 보세요.
- `default_models`를 바꾸면 모델을 지정하지 않은 모든 호출(참가자, 모더레이터, 분석, 보고서, 페르소나 생성, RAG)이 바뀝니다. 실험 계획은 페르소나마다 모델을 적어 두는 것을 권장합니다.
- `/config/llm-providers` 응답은 키 설정 여부와 이 기본 모델만 보여 줍니다. 실제 호출로 확인한 상태가 아니며, 단가·문맥 길이는 비워 둡니다.

## 프롬프트·템플릿

프롬프트는 코드에 쓰지 않습니다. 코드에서는 `config_loader.prompts.render("경로", ...)`로 불러옵니다.

| 파일 | 내용 |
|---|---|
| `config/prompts.yaml` | 페르소나 생성, 에이전트 시스템 프롬프트, 발언 액션별 프롬프트(`turn_actions.*`, 사람 발언 응답 포함), 모더레이터, 신념 추론, 언어 지시 |
| `config/report_prompts.yaml` | 쟁점 추출, 재시도 피드백, 요약 (`report.` 네임스페이스로 로드) |
| `config/rag_prompts.yaml` | 웹 검색용 질의 생성·분류·증거 추출 |
| `config/persona_templates.yaml` | 화면의 페르소나 템플릿 목록 |

프롬프트를 바꾸면 서버를 재시작해야 적용됩니다.

## 실험 조건 (토론별)

토론 생성 요청의 `experiment`로 이 토론에만 적용할 조건을 지정합니다(`src/core/experiment.py`). 엔진은 기본 설정의 **사본**에 조건을 덮어써서 사용하므로, 조건이 다른 토론을 동시에 실행해도 서로 간섭하지 않고 전역 설정도 바뀌지 않습니다. 비운 항목은 위 기본값을 씁니다.

| 키 | 의미 |
|---|---|
| `label` | 조건 이름 (분석 시 구분용) |
| `mode` | `stateful`(기본, 상태 기반 진행), `baseline`, 또는 `survey_only`(토론 없음: 사전 설문 뒤 토론 기록 없이 혼자 다시 답하는 사후 설문만 함, 설문 필수, 보고서 없음). baseline은 참가자가 순서대로 돌아가며 앞 발언에 답하는 단순 토론으로, 발화 행위 지정·응답 의무·중재·반대 검토·입장 안내·공약·상호 양보 안내가 없습니다. 명제, 발언 수, 종결 라운드, 맥락 길이, 설문은 같게 적용되고, 발언 분석은 측정용으로만 기록됩니다 |
| `mechanisms.analysis` | 발언 분석. 끄면 토론 상태와 입장 동역학이 모두 없음 |
| `mechanisms.reply_obligation` | 반박·질문을 받은 참가자의 응답 의무 |
| `mechanisms.stalemate_mediation` | 교착 시 제3자 중재·제3안 (2명이면 모더레이터 지목 질문) |
| `mechanisms.devils_advocate` | 성급한 합의 시 반대 검토 |
| `mechanisms.closing_round` | 종결 라운드. 끄면 발언 수 전체가 본론에 쓰임 |
| `mechanisms.latitude` | 수용·거부 범위. 끄면 거리와 무관하게 수용하고 반발이 없음 (순수 Friedkin–Johnsen) |
| `mechanisms.concession_shift` | 양보에 따른 입장 이동. 끄면 양보는 기록만 함 |
| `dynamics.*` | 위 표의 동역학 파라미터 (`dynamics_step`, `dynamics_anchor`, `accept_wide` 등) |
| `stalemate_exchanges`, `consensus_spread`, `max_subtopics`, `context_messages`, `context_chars` | 위 표의 같은 이름 값 |
| `agent_temperature` / `moderator_temperature` | 참가자 기본 / 모더레이터 temperature (기본 0.7 / 0.5). 발언 분석은 항상 0 |
| `analyzer` | 발언 분석 모델 `{provider, model}`. 비우면 첫 참가자의 모델 (판정자와 참가자 모델을 분리할 때 사용) |
| `record_prompts` | 발언마다 최종 지시 프롬프트를 메시지 `meta.prompt`에 저장 (실험 조건이 있으면 기본 켬) |
| `report` | `false`면 끝난 뒤 종합보고서를 자동으로 만들지 않음 (보고서 LLM 비용 절약, 기본 `true`). 필요하면 나중에 수동 생성 |
| `participants.{이름}` | 참가자별 `stubbornness`(0~1, 비우면 성격 키워드로 정함), `temperature`, `seed`(설문 문항별 초기 응답. 사전 설문 대신 기록되고 시스템 프롬프트에 들어감, [api-reference](api-reference.md) 설문 참고), `script`(정해진 발언 목록, 실험 공모자: `mode: baseline`에서만. 차례마다 LLM 없이 다음 줄을 말하고, 다 쓰면 이후 차례와 종결 라운드에서 빠짐. 설문 대상이 아니고 `seed`를 줄 수 없음. 발언 `meta.scripted = true`) |
| `turn_order` | `mode: baseline`의 발언 순서(참가자 이름 목록, 같은 이름 반복 가능). 이 순서를 되풀이하며 대본을 다 쓴 참가자는 건너뜀. 재개 시 저장된 발언으로 위치를 복원 |

`mechanisms.latitude`나 `concession_shift`를 끄면 `dynamics`의 해당 값보다 우선합니다. 알 수 없는 키는 거부되므로 오타로 조건이 무시되지 않습니다.
