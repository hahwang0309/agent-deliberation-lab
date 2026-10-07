# API 레퍼런스

기본 경로는 `/api/v1`입니다. 실제 스키마는 실행 중인 서버의 `/docs`(Swagger)에서 볼 수 있습니다.

## 공통 규칙

- **인증:** 로그인하면 `access_token` 쿠키가 발급됩니다. 스크립트에서는 `Authorization: Bearer <access token>`도 쓸 수 있습니다.
- **CSRF:** 쿠키로 인증하는 POST/PUT/PATCH/DELETE 요청은 `X-CSRF-Token` 헤더에 `csrf_token` 쿠키 값을 넣어야 합니다. 로그인, 가입 신청, 토큰 갱신, 로그아웃은 예외입니다.
- **오류 형식:** `{"detail": {"error": {"code": "...", "message": "..."}}}`
- **인증·권한 관련 응답:**

| 상황 | 응답 |
|---|---|
| 로그인 안 함 | 401 `AUTH_REQUIRED` |
| 임시 비밀번호 상태 | 403 `PASSWORD_CHANGE_REQUIRED` |
| 관리자 권한 필요 | 403 `ADMIN_REQUIRED` |
| 생성자·관리자가 아님 | 403 `FORBIDDEN` |

## 인증·계정

| 메서드 | 경로 | 설명 |
|---|---|---|
| POST | `/auth/signup-request` | 가입 신청 `{email, password, name, organization?, note?}` → `pending` 상태로 생성 |
| POST | `/auth/login` | `{email, password}`. 승인 대기·정지·거절 계정은 403 (`ACCOUNT_PENDING` 등), 5회 실패 시 잠시 잠김(429) |
| POST | `/auth/refresh` | refresh 쿠키로 access 토큰 재발급 |
| POST | `/auth/logout` | 인증 쿠키 삭제 |
| GET | `/auth/me` | 내 정보 (임시 비밀번호 상태에서도 가능) |
| PUT | `/users/me` | `{name?, organization?}` |
| PUT | `/users/me/password` | `{current_password, new_password}`. 다른 세션은 로그아웃되고, 현재 세션 쿠키는 재발급됨 |

## 토론

| 메서드 | 경로 | 권한 | 설명 |
|---|---|---|---|
| POST | `/discussions` | 활성 사용자 | `draft` 토론 생성 (요청 본문은 아래) |
| GET | `/discussions?page=&page_size=&status=&mine=` | 활성 사용자 | 목록 (생성자 이름, 토큰 사용량 포함) |
| GET | `/discussions/{id}` | 활성 사용자 | 상세 (참가자, 소주제, 사용량) |
| POST | `/discussions/{id}/start` | 생성자·관리자 | `draft` → 실행. 사용자 제한 초과 시 403/429 |
| POST | `/discussions/{id}/resume` | 생성자·관리자 | `interrupted` → 이어서 실행 (일일 시작 수에 포함 안 됨) |
| POST | `/discussions/{id}/stop` | 생성자·관리자 | `{reason?}`. AI 발언이 충분하면 보고서 자동 생성 |
| DELETE | `/discussions/{id}` | 생성자·관리자 | 실행 중이면 409 |

**토론 생성 요청 본문**

```json
{
  "topic": "주 4일제를 도입해야 하는가?",
  "description": "배경 설명 (선택)",
  "language": "ko",
  "max_statements": 12,
  "use_moderator": true,
  "enable_web_search": false,
  "enable_belief_reasoning": false,
  "personas": [
    {"name": "...", "role": "...", "background": "...", "personality": ["..."], "expertise": ["..."],
     "communication_style": "...", "beliefs": ["..."], "llm_provider": null, "model": null}
  ]
}
```

- 페르소나는 2~5명입니다. `llm_provider`와 `model`을 비우면 `config.yaml` 기본값이 쓰입니다.
- 일반 사용자는 `enable_web_search`와 `enable_belief_reasoning`을 켤 수 없습니다(403 `FEATURE_RESTRICTED`).

## 메시지·실시간 이벤트

| 메서드 | 경로 | 설명 |
|---|---|---|
| GET | `/discussions/{id}/messages?after_seq=&limit=` | 완성된 발언 목록 |
| GET | `/discussions/{id}/events?since=` | SSE. 재접속 시 브라우저가 보내는 `Last-Event-ID` 이후 메시지부터 다시 보냄 |

**SSE 이벤트**

| event | data | 설명 |
|---|---|---|
| `message` (id=seq) | 메시지 객체 | 완성된 발언 (ai / moderator / human) |
| `snapshot` | `{status, last_seq, current_utterance, hands}` | 접속 직후 현재 상태 |
| `utterance_start` | `{speaker, speaker_type, action}` | 발화 시작 |
| `chunk` | `{speaker, delta}` | 스트리밍 조각 |
| `utterance_aborted` | `{speaker}` | 중지로 발화 폐기 |
| `subtopics` | `{subtopics}` | 소주제 생성 |
| `status` | `{status, error?}` | 상태 변경 (종료 상태면 스트림 종료) |
| `hand_queue` | `{queue, floor}` | 발언 대기열·발언권 변경 |
| `floor_granted` | `{user_id, name, floor_id}` | 발언권 부여 |
| `floor_released` | `{user_id, name, reason}` | 발언 없이 종료 (cancelled / revoked / stopped) |
| `report_status` | `{status, error?}` | 보고서 생성 시작·실패 |
| `report_ready` | `{status, scores, label}` | 보고서 완료 |

## 사람 개입

| 메서드 | 경로 | 권한 | 설명 |
|---|---|---|---|
| GET | `/discussions/{id}/hand` | 활성 사용자 | `{queue, floor}` |
| POST | `/discussions/{id}/hand` | 활성 사용자 | 발언 요청. `{position, queue, floor}` (position 0이면 발언권 보유) |
| DELETE | `/discussions/{id}/hand` | 본인 | 요청 취소 또는 발언권 포기 |
| POST | `/discussions/{id}/speech` | 발언권 보유자 | `{floor_id, content}` (아래 표 참고) |
| POST | `/discussions/{id}/floor/revoke` | 생성자·관리자 | 현재 발언권 회수 |

**발언 제출(`/speech`) 응답**

| 상황 | 응답 |
|---|---|
| 내 차례가 아님 | 403 `NOT_YOUR_TURN` |
| 이미 끝난 발언권 | 409 `STALE_FLOOR` |
| 글자 수 초과 | 422 `SPEECH_TOO_LONG` |

실행 중이 아닌 토론에서 개입하면 409 `NOT_RUNNING`, 1인당 발언 횟수를 넘으면 429 `HUMAN_TURN_LIMIT`가 반환됩니다.

## 종합보고서

| 메서드 | 경로 | 권한 | 설명 |
|---|---|---|---|
| GET | `/discussions/{id}/report` | 활성 사용자 | `{status: pending\|ready\|failed, consensus_score(종합), ai_score(AI간), human_score(인간간, 사람 2명 이상), ai_human_score(AI-인간간, 사람 참여 시), consensus_label, content}`. 없으면 404 |
| POST | `/discussions/{id}/report` | 생성자·관리자 | 종료된 토론의 보고서 (재)생성. AI 발언이 부족하면 409 `INSUFFICIENT_MESSAGES` |
| GET | `/discussions/{id}/report/export?format=md\|json` | 활성 사용자 | 첨부 파일로 내려받기 |

## 페르소나·설정

| 메서드 | 경로 | 설명 |
|---|---|---|
| GET | `/personas/templates` | `config/persona_templates.yaml` |
| POST | `/personas/generate` | `{topic, count, language?}` → 페르소나 자동 생성 (LLM 출력 형식 오류 시 502) |
| GET | `/config`, `/config/llm-providers` | 시스템 설정, 프로바이더 사용 가능 여부 |

## 관리자 (`require_admin`)

| 메서드 | 경로 | 설명 |
|---|---|---|
| GET | `/admin/users?status=` | 사용자 목록 |
| POST | `/admin/users` | 계정 발급 `{email, name, organization?, role}` → `temp_password` (1회만 표시) |
| POST | `/admin/users/{id}/approve\|reject\|suspend\|reactivate` | 상태 변경 (자기 계정은 불가, 정지하면 세션 즉시 무효) |
| POST | `/admin/users/{id}/reset-password` | 임시 비밀번호 재발급 |
| PATCH | `/admin/users/{id}` | `{role?, max_concurrent?, daily_limit?, clear_limits?}` |
| GET | `/admin/runtime` | 실행 중인 토론과 보고서 작업 |

## 기타

- `GET /health`: 인증이 필요 없는 헬스체크
