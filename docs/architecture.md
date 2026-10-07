# 아키텍처

## 구성

```
web/            바닐라 HTML/JS 화면 (FastAPI가 / 에 정적 마운트)
api/            FastAPI 서비스
  routers/      HTTP 엔드포인트 (인증·권한 의존성 적용)
  services/     비즈니스 로직 (토론, 보고서, 인증, 관리자, 개입)
  runtime/      토론 실행 런타임 (레지스트리, 브로커, 저장, 개입, 보고서 작업)
  models/       SQLAlchemy 모델 (Alembic으로 마이그레이션)
  schemas/      Pydantic 요청·응답
  utils/        보안(JWT·bcrypt), 인증 쿠키, CSRF 미들웨어
src/            토론 엔진 라이브러리 (api에 의존하지 않음)
  core/         NaturalDiscussion(턴 루프), DiscussionAgent, DiscussionModerator
  services/     consensus_report(보고서), rag_service·web_search(선택), belief_reasoning(선택)
  generators/   PersonaGenerator (구조화 출력)
  utils/        LLMFactory·LLMBundle, 언어 감지
config/         config.yaml, prompts.yaml, report_prompts.yaml, rag_prompts.yaml, persona_templates.yaml
alembic/        DB 마이그레이션
```

## 토론 실행 흐름

1. `POST /discussions`가 `draft` 토론과 참가자(페르소나·provider·model)를 저장합니다.
2. `POST /discussions/{id}/start`에서 권한·제한을 검사하고 `registry.start()`를 호출합니다. 토론은 uvicorn 메인 이벤트 루프의 `asyncio.Task`로 실행됩니다. 스레드는 쓰지 않고, DB 쓰기만 `asyncio.to_thread`로 처리합니다.
3. `DiscussionRuntime`이 `create_discussion()`으로 엔진을 조립합니다. 참가자별 LLM은 `LLMBundle`에서 받고, 사용량 콜백(`UsageCounter`)을 연결합니다.
4. `NaturalDiscussion.stream()`은 `EngineEvent`(subtopics / utterance_start / chunk / utterance)를 내보내기만 합니다. 저장과 전송은 런타임이 맡습니다.
   - 완성된 발언에는 토론 안에서 1부터 늘어나는 `seq`를 붙입니다. 먼저 저장한 다음 발행합니다.
   - 스트리밍 조각(chunk)은 저장하지 않고 발행만 합니다.
5. 끝나면 AI 발언이 `report.min_ai_messages` 이상일 때 상태가 `reporting`으로 바뀌고 보고서를 만듭니다. 그다음 `completed`가 됩니다.

상태 흐름은 `draft → running ⇄ awaiting_human → reporting → completed`입니다. 언제든 `stopped`나 `failed`로 끝날 수 있습니다. 서버가 재시작되면 실행 중이던 토론은 `interrupted`가 되고, 생성자나 관리자가 `resume`으로 이어서 진행할 수 있습니다.

**단일 워커 필수:** 실행 중인 토론과 발언 대기열은 프로세스 메모리에 있습니다. uvicorn 워커를 여러 개 띄우면 안 됩니다.

## 실시간 전송 (SSE)

`GET /discussions/{id}/events`는 다음 순서로 동작합니다.

1. 브로커를 구독합니다.
2. 놓친 메시지를 보냅니다(`seq > Last-Event-ID` 또는 `?since`).
3. `snapshot`으로 현재 상태, 진행 중인 발화, 발언 대기열을 보냅니다.
4. 실시간 이벤트를 보냅니다.

재생보다 구독을 먼저 하므로 그 사이에 생긴 이벤트도 잃지 않습니다. 중복은 seq로 걸러냅니다. 종료 상태가 되면 스트림을 닫습니다. 구독자 큐가 넘치면 연결을 끊고, 클라이언트는 `Last-Event-ID`로 다시 접속해 누락분을 받습니다.

## 사람 개입

`api/runtime/intervention.py`의 `HumanDesk`가 엔진의 `InterventionGate` 역할을 합니다.

- 엔진은 AI나 모더레이터 발화가 끝날 때마다 `after_utterance()`를 부릅니다.
- 대기열이 있으면 상태를 `awaiting_human`으로 기록한 뒤 첫 사람에게 발언권(`floor_id`)을 줍니다. 이후 제출·포기·회수·중지 중 하나가 일어날 때까지 **무기한** 기다립니다.
- 받은 발언은 저장되고, 엔진 대화에 들어갑니다. 바로 다음 AI 발언은 `respond_to_human`으로 그 발언에 응답하며 `meta.in_reply_to_seq`에 사람 발언 번호를 남깁니다. 이 응답은 AI 발언 예산을 넘어도 수행됩니다.
- 사람 발언은 프롬프트에서 구분자로 감싸 지시문으로 해석되지 않게 합니다.
- 사람의 표시 이름은 페르소나나 다른 사람과 겹치면 접미사를 붙입니다. 보고서가 이름으로 참가자를 구분하기 때문입니다.

## 종합보고서

`src/services/consensus_report.py`가 세 단계로 만듭니다.

1. **쟁점·입장 추출:** LLM 구조화 출력으로 쟁점(찬반이 가능한 명제)과 참가자별 입장(agree / partially_agree / disagree / no_position)과 근거 seq를 뽑습니다. 참가자 이름과 seq를 검증하고, 실패하면 오류 내용을 알려 주며 재시도합니다.
2. **점수 계산(코드): 쌍별 일치도**
   - 입장을 숫자로 바꿉니다: 찬성 1, 부분찬성 w(기본 0.7), 반대 0.
   - 두 참가자의 일치도 = 1 − |차이|. 같은 쪽으로 모이면 찬성이든 반대든 높게 나옵니다.
   - 쟁점마다 네 가지 평균을 냅니다.

     | 점수 | 계산 대상 | 계산하지 않는 경우 |
     |---|---|---|
     | 종합 | 모든 쌍 | 입장 2개 미만 |
     | AI간 | AI끼리의 쌍 | AI 입장 2개 미만 |
     | 인간간 | 사람끼리의 쌍 | 사람 1명 이하 |
     | AI-인간간 | AI × 사람 쌍 | 사람이 없음 |

   - 토론 전체 점수는 쟁점별 점수를 각 쌍의 개수로 가중 평균한 값입니다.
   - 라벨은 종합 점수 기준입니다(합의 ≥ 0.8, 부분 합의 ≥ 0.6). 입장을 밝힌 참가자가 2명 미만인 쟁점은 `insufficient`(판단 보류)입니다.
3. **서술:** 분류 결과를 바탕으로 요약, 열린 질문, 제언을 만듭니다.

완료된 토론은 런타임 안에서 보고서를 만듭니다. 사용자가 중지한 토론과 재생성 요청은 `registry.start_report()`가 별도 작업으로 실행합니다.

## 인증·권한

- **인증 수단:** httpOnly 쿠키에 담은 JWT. access 30분, refresh 7일(refresh 쿠키는 `/api/v1/auth` 경로에만 전송).
- **CSRF:** 쿠키로 인증하는 쓰기 요청은 `X-CSRF-Token` 헤더가 `csrf_token` 쿠키와 같아야 하고, Origin도 일치해야 합니다.
- **유효한 사용자 조건:** 상태가 `active`이고 `token_version`이 일치해야 합니다. 정지되거나 비밀번호가 바뀌면 기존 세션이 즉시 무효가 됩니다.
- **권한:** 조회와 SSE와 발언 요청은 모든 활성 사용자가 할 수 있습니다(공동 참여). 시작·중지·삭제·재개·보고서 재생성·발언권 회수는 생성자나 관리자만 할 수 있습니다.
