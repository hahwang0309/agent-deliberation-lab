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
  core/         NaturalDiscussion(진행 계획·발언 선택), DebateState(토론 상태·입장 동역학), DiscussionAgent, DiscussionModerator
  services/     consensus_report(보고서), debate_dynamics(입장 변화 요약), rag_service·web_search(선택), belief_reasoning(선택)
  generators/   PersonaGenerator (구조화 출력)
  utils/        LLMFactory·LLMBundle, 언어 감지
config/         config.yaml, prompts.yaml, report_prompts.yaml, rag_prompts.yaml, persona_templates.yaml
alembic/        DB 마이그레이션
```

## 토론 실행 흐름

1. `POST /discussions`가 `draft` 토론과 참가자(페르소나·provider·model)를 저장합니다.
2. `POST /discussions/{id}/start`에서 권한·제한을 검사하고 `registry.start()`를 호출합니다. 토론은 uvicorn 메인 이벤트 루프의 `asyncio.Task`로 실행됩니다. 스레드는 쓰지 않고, DB 쓰기만 `asyncio.to_thread`로 처리합니다.
3. `DiscussionRuntime`이 `create_discussion()`으로 엔진을 조립합니다. 참가자별 LLM은 `LLMBundle`에서 받고, 사용량 콜백(`UsageCounter`)을 연결합니다.
4. `NaturalDiscussion.stream()`은 `EngineEvent`(subtopics / utterance_start / chunk / utterance / analysis)를 내보내기만 합니다. analysis는 발언 분석 결과로, 런타임이 해당 메시지 `meta`에 기록하고 SSE `analysis`로 발행합니다. 저장과 전송은 런타임이 맡습니다.
   - 완성된 발언에는 토론 안에서 1부터 늘어나는 `seq`를 붙입니다. 먼저 저장한 다음 발행합니다.
   - 스트리밍 조각(chunk)은 저장하지 않고 발행만 합니다.
5. 끝나면 AI 발언이 `report.min_ai_messages` 이상일 때 상태가 `reporting`으로 바뀌고 보고서를 만듭니다. 그다음 `completed`가 됩니다.

상태 흐름은 `draft → running ⇄ awaiting_human → reporting → completed`입니다. 언제든 `stopped`나 `failed`로 끝날 수 있습니다. 서버가 재시작되면 실행 중이던 토론은 `interrupted`가 되고, 생성자나 관리자가 `resume`으로 이어서 진행할 수 있습니다.

**단일 워커 필수:** 실행 중인 토론과 발언 대기열은 프로세스 메모리에 있습니다. uvicorn 워커를 여러 개 띄우면 안 됩니다.

## 토론 메커니즘

`src/core/natural_discussion.py`(진행)와 `src/core/debate_state.py`(상태)가 다음 이론을 코드로 옮긴 것입니다.

| 이론 | 적용 |
|---|---|
| 화용-변증법 단계(van Eemeren & Grootendorst) | 명제마다 전원 입장 표명 → 상호 논증, 토론 끝에 종결 라운드 |
| Pollock 반박·근거 공격, Dung 논증 공격 관계 | 반박(rebut)·근거 반박(undercut) 발화 행위, 공격·질문을 받은 참가자의 응답 의무 |
| 공약 저장소(Hamblin, Walton & Krabbe) | 참가자별 최근 주장 6개를 발언 프롬프트에 넣어 일관성·입장 변화를 표현 |
| Friedkin–Johnsen | 명제별 입장 x ∈ [−1, 1] 갱신 |
| 정교화 가능성 모델(Petty & Cacioppo), 반복 효과(Cacioppo & Petty), 출처 신뢰도(Hovland & Weiss), 도덕 재구성(Feinberg & Willer), 대화 수용성(Minson et al.) | 설득력을 질·새로움·가치 일치·신뢰도·인정 요인으로 분해 |
| 사회 판단 이론(Sherif & Hovland), 역효과 재현 실패(Wood & Porter) | 고집도에 따른 수용·비관여·거부 범위, 위협이 있을 때만 반발 |
| 신념 중심성(Rokeach), 상호 양보(Cialdini), ChangeMyView(Tan et al.) | 중심 입장과 별도로 주장 단위 양보를 기록, 양보에 따른 소폭 이동, 상대 양보를 다음 발언에 알림 |
| LLM 다중 에이전트 토론(Du et al. 2023, Liang et al. 2023, Chan et al. 2023) | 상대 발언 전문 전달, 성급한 합의 시 반대 검토(devil's advocate) |

**진행 계획** (`plan_debate`): N명, 발언 S개일 때 S − N ≥ N + 1이면 마지막 N개를 종결 라운드로 둡니다. 본론 = S − 종결, 명제 수 k = clamp(본론 // (N + 1), 1, `max_subtopics`), 본론을 k개로 고르게 나눕니다. 명제마다 전원 1회 + 상호 응답 1회 이상이 들어갑니다. 예: (3, 9) → 명제 1개(6발언) + 종결 3, (3, 12) → [5, 4] + 3. 모더레이터는 정확히 k개의 명제를 만듭니다.

**발언 선택** (`_select_turn`, 우선순위 순):
1. 사람 발언에 대한 응답
2. 종결 라운드: 최종 입장과 바뀐 점
3. 입장 표명: 이 명제에서 아직 말하지 않은 참가자
4. 교착: 두 참가자가 서로 반박을 `stalemate_exchanges`회 이상 주고받으면 제3자가 중재·제3안을 냅니다. 2명이면 모더레이터가 지목 질문을 하며, 명제 예산이 남았을 때만 합니다.
5. 응답 의무: 답하지 않은 반박·질문을 받은 참가자가 그 발언에 답합니다.
6. 성급한 합의: 반박 없이 입장 간격이 `consensus_spread` 미만이면 평균에서 가장 먼 참가자가 반대 검토(명제당 1회)
7. 기본: 덜 말한 참가자가 최근 발언에 입장 거리로 반응합니다. 0.4 미만이면 동조·확장 또는 사례, 아니면 반박 또는 근거 반박입니다.

**발언 분석** (발언당 LLM 1회, temperature 0, `UtteranceAnalysis` 구조화 출력): 주장, 대상 발언(seq)과 관계(support / attack / concede / question), 지목한 참가자, 상대 주장을 인정한 양보, 화자 입장, 청자별 설득 요인을 뽑습니다. 이 결과로 `DebateState`가 응답 의무, 교착 카운터, 공약 저장소, 입장을 갱신합니다. 분석이 실패하면 그 발언은 상태에 반영하지 않고 진행합니다.

**입장 동역학:** 화자의 입장은 분석에서 관찰한 값입니다. AI 청자는 x_i ← x_i + step·(1 − s_i)·q·(x_j − x_i) + s_i·anchor·(x_i0 − x_i)로 움직입니다.
- 설득력 q = quality × novelty × (0.5 + 0.5·value_match) × (0.5 + 0.5·credibility) × (0.7 + 0.3·receptive) × (1 − 0.5·threat). 요인은 분석 LLM이 청자별로 판정합니다(`debate_state.persuasion`). 반복된 논거는 novelty가 낮아 효과가 없습니다.
- 수용 범위 폭 = `accept_wide` − (`accept_wide` − `accept_narrow`)·s_i. 범위 밖 `noncommit_width`까지는 q × `noncommit_factor`, 그 너머(거부 범위)는 q × `reject_factor`입니다. 거부 범위에서 threat ≥ `boomerang_threshold`이면 화자 반대쪽으로 `boomerang_step`·threat·(1 − s_i)만큼 멀어집니다.
- 양보: 상대 주장을 인정한 AI 화자는 상대 쪽으로 `concession_step`·(1 − s_i)만큼, 명제당 `concession_cap`까지 이동합니다. 양보 목록은 명제마다 초기화되며, 양보받은 참가자의 다음 발언 프롬프트에 들어갑니다(상호성).
- 발언 프롬프트에는 다른 참가자의 이름·역할, 자신이 이미 한 논거 전체와 반복 금지 지시가 들어갑니다.
- s_i는 고집도로, 성격 키워드로 정합니다: 개방적 0.3, 원칙적·완고 0.75, 기본 0.5.
- 현재 입장과 최근 이동("A의 발언 뒤 +0.30")을 다음 발언 프롬프트에 넣습니다.
- 사람의 입장은 관찰만 하고 시뮬레이션하지 않습니다.

**고정 명제·배경 자료:** 토론 생성 시 `propositions`를 주면 모더레이터가 명제를 생성하지 않고 그 명제를 씁니다(`NaturalDiscussion(propositions=...)`). `materials`는 모든 참가자의 시스템 프롬프트에 구분자로 감싸 들어갑니다(`agent.materials_block`). 인간 토의와 같은 질문·같은 자료로 비교하기 위한 기능입니다.

**실험 조건:** `src/core/experiment.py`의 `engine_settings()`가 기본 설정(`config/discussion_config.py`) 사본에 토론별 조건을 덮어써 엔진·에이전트에 넘깁니다. 진행 장치 on/off, 동역학 파라미터, 참가자별 고집도·temperature, 분석 모델 분리를 지원합니다. 조건은 `discussions.config.experiment`에 저장됩니다.

**재개:** 상태는 매 분석 시 메시지 `meta.debate`에 스냅숏으로 저장되고, 재개 시 마지막 스냅숏으로 복원합니다. 스냅숏이 없는 이전 토론은 AI 발언 수를 진행 계획에 대입해 위치를 정합니다.

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
- 받은 발언은 저장되고, 엔진 대화에 들어갑니다. 바로 다음 AI 발언은 `respond_to_human`으로 그 발언에 응답하며 `meta.in_reply_to_seq`에 사람 발언 번호를 남깁니다. 이 응답은 명제 예산을 쓰고, 예산이 끝났으면 추가 발언으로 수행됩니다.
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
4. **입장 변화(코드, LLM 호출 없음):** `src/services/debate_dynamics.py`가 메시지 `meta.debate`·`meta.moves`·`meta.analysis`로 명제별 입장 궤적(시작 → 최종), 입장 간격, 누가 누구를 움직였는지, 대립 속 공통 기반(양보 목록), 반발 이동, 답하지 않은 반박을 정리해 보고서 `dynamics`에 넣습니다.

완료된 토론은 런타임 안에서 보고서를 만듭니다. 사용자가 중지한 토론과 재생성 요청은 `registry.start_report()`가 별도 작업으로 실행합니다.

## 인증·권한

- **인증 수단:** httpOnly 쿠키에 담은 JWT. access 30분, refresh 7일(refresh 쿠키는 `/api/v1/auth` 경로에만 전송).
- **CSRF:** 쿠키로 인증하는 쓰기 요청은 `X-CSRF-Token` 헤더가 `csrf_token` 쿠키와 같아야 하고, Origin도 일치해야 합니다.
- **유효한 사용자 조건:** 상태가 `active`이고 `token_version`이 일치해야 합니다. 정지되거나 비밀번호가 바뀌면 기존 세션이 즉시 무효가 됩니다.
- **권한:** 조회와 SSE와 발언 요청은 모든 활성 사용자가 할 수 있습니다(공동 참여). 시작·중지·삭제·재개·보고서 재생성·발언권 회수는 생성자나 관리자만 할 수 있습니다.
