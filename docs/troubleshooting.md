# 문제 해결

| 증상 | 원인 | 해결 |
|---|---|---|
| 서버 시작 시 `RuntimeError: SECRET_KEY가 설정되지 않았거나 안전하지 않습니다` | `SECRET_KEY`가 비었거나, 예시값이거나, 32자 미만 | `python3 -c "import secrets; print(secrets.token_urlsafe(48))"`로 만든 값을 `.env`에 넣기 |
| 관리자 계정으로 로그인할 수 없음 | 서버 시작 전에 `ADMIN_EMAIL`/`ADMIN_INITIAL_PASSWORD`를 넣지 않았음 | 값을 넣고 재시작. 관리자가 이미 있으면 다시 만들지 않으므로, 다른 관리자가 비밀번호를 초기화해야 함 |
| 로그인 후 모든 화면이 비밀번호 변경으로 이동 | 임시 비밀번호 상태(`must_change_password`) | 비밀번호를 변경하면 해제됨 |
| `ModuleNotFoundError: jwt` 또는 실행 중 import 오류 | 예전 의존성으로 만든 가상환경 | `.venv/bin/pip install -r requirements-dev.txt` |
| 토론이 바로 `failed`, 오류에 `AuthenticationError` | 참가자 provider의 API 키가 없거나 예시값 | `.env`의 해당 키 확인. 시작 시에는 키가 있는지만 검사함 |
| 페르소나 자동 생성이 502 `LLM_INVALID_OUTPUT` | 모델 출력이 잘렸거나 형식이 다름 | `llm.structured_max_tokens`를 늘림. 목록 필드를 문자열로 주는 경우는 자동 변환됨 |
| 발언이 문장 중간에 끊김 | `llm.max_tokens`가 너무 작음 (한국어는 토큰이 많이 듦) | 1500 이상 유지 |
| 브라우저에서 403 `CSRF_FAILED` | `X-CSRF-Token` 헤더가 없거나, 다른 출처에서 요청 | 웹 UI는 `web/js/api.js`가 자동으로 붙임. 직접 호출할 때는 `csrf_token` 쿠키 값을 헤더에 넣기 |
| 시작 시 403 `CONCURRENT_LIMIT_EXCEEDED` / 429 `DAILY_LIMIT_EXCEEDED` | 사용자 실행 제한 | 관리자 화면 → 사용자 → 동시·일일 값 조정 |
| 실시간 화면이 멈추거나 끊김 | 프록시 버퍼링, 또는 access 토큰 만료 | 프록시 버퍼링을 끄기([deployment.md](deployment.md)). 토큰 만료는 화면이 자동으로 갱신 후 재접속함 |
| 토론 상태가 `interrupted` | 실행 중 서버가 재시작됨 | 토론 화면에서 "이어서 진행" (생성자·관리자) |
| "발언 요청"을 눌렀는데 바로 차례가 오지 않음 | 정상 동작. 진행 중인 AI 발언이 끝나야 발언권이 옴 | 차례가 오면 입력창이 열리고 토론은 무기한 기다림 |
| 보고서에 인간간 또는 AI-인간간 점수가 없음 | 인간간은 입장을 밝힌 사람이 2명 이상, AI-인간간은 1명 이상일 때만 계산함 | 정상 동작 |
| 보고서 생성이 409 `INSUFFICIENT_MESSAGES` | AI 발언이 `report.min_ai_messages`(기본 4)보다 적음 | 더 긴 토론으로 진행하거나 설정값 조정 |
| 토론 생성이 422 `WEB_SEARCH_UNAVAILABLE` | 웹 검색을 켰는데 `TAVILY_API_KEY`가 없음 | 키를 설정하거나 웹 검색을 끔 (키 없이 켜면 근거 없이 비용만 들기 때문에 거부함) |
| 보고서에 "출처 없음" 표시 | 해당 입장이 출처를 확인할 수 없는 수치·사례에 기댐 | 사실이 아니라 참가자의 주장으로 읽기. 근거가 필요하면 웹 검색(Tavily 키)을 켜고 토론 |
| 이메일 형식 오류로 가입·발급 실패 | 가입·발급 시 이메일 형식을 검사함 (`.local` 같은 예약 도메인은 거부) | 실제 도메인 이메일 사용. 로그인은 형식 검사를 하지 않음 |

## 최신 Claude 모델에서 "`temperature` is not supported" 또는 발언이 깨짐

`claude-sonnet-5-5`, `claude-fable-5*`는 기본값 외의 temperature를 받지 않고, 응답 내용이 사고(thinking)·텍스트 블록 목록으로 옵니다. 앱은 이 모델에 temperature를 넣지 않고(실행 기록에 `null`), 응답에서 텍스트 블록만 읽으며, 구조화 출력은 json_schema 방식을 씁니다(`src/utils/llm_provider.py`의 `FIXED_SAMPLING_PREFIXES`). 같은 제약을 가진 새 모델이 나오면 이 목록에 접두어를 추가하세요.
