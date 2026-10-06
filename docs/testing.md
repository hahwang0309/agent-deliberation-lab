# 테스트

```bash
.venv/bin/python -m pytest                                    # 전체
.venv/bin/python -m pytest tests/test_intervention.py         # 파일 하나
.venv/bin/python -m pytest tests/test_resume.py::test_resume_permissions_status_and_concurrency  # 테스트 하나
```

API 키, 실행 중인 서버, 외부 DB가 필요 없습니다. 모든 LLM 호출은 가짜 구현으로 대체됩니다.

## 구성

| 파일 | 대상 |
|---|---|
| `tests/conftest.py` | 임시 SQLite·테스트 환경변수, 보고서 LLM 가짜 구현 자동 주입, `create_user()`, `update_user()`, `LoggedInClient`(로그인·CSRF 헤더 포함), `new_client()` |
| `tests/test_runtime.py` | 런타임 저장·발행 순서, 중지, 재시작 시 interrupted 표시. `FakeBundle`(빠름/느림) 정의 |
| `tests/test_events_api.py` | SSE 실시간 수신, 늦은 접속 재생, `Last-Event-ID` 재접속, 상태 규칙 |
| `tests/test_consensus_report.py` | 합의 점수 계산, 참가자·seq 검증과 재시도, 마크다운 |
| `tests/test_reports_api.py` | 보고서 자동 생성(완료·중지), 재생성, 실패 처리, 내보내기 |
| `tests/test_auth_api.py` | 가입 승인, 권한, 동시·일일 제한, CSRF, 세션 무효화, 임시 비밀번호, 잠금, 최초 관리자 |
| `tests/test_intervention.py` | 사람 개입 엔진 동작, 다중 사용자 대기열·발언권·제출·취소·회수·중지, 발언 횟수 제한, 보고서 반영 |
| `tests/test_resume.py` | 중단 토론 재개(seq 연속, 예산 유지, 소주제 유지), 권한·상태·제한 |
| `tests/test_rag_quick.py` | 웹 검색 수동 점검 스크립트 (pytest 수집 대상 아님, Tavily 키 필요) |

## 작성 요령

- **가짜 엔진:** `monkeypatch.setattr(runtime_module, "LLMBundle", FakeBundle)`. 진행 중 상태를 테스트할 때는 `FakeBundle(slow=True)`를 씁니다.
- **가짜 보고서 LLM:** 기본으로 자동 주입됩니다. 동작을 바꾸려면 `tests/report_stubs.py`의 `StubLLM`으로 `reports.create_report_llm`을 교체합니다.
- **상태 대기:** `asyncio.sleep`으로 고정 시간을 기다리지 말고 `tests/test_intervention.py`의 `wait_until()`을 씁니다.
- **실제 LLM 확인:** pytest에 넣지 않습니다. 임시 DB로 서버를 띄워 직접 확인합니다(비용 발생).
