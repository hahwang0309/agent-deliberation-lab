# 개발

## 환경

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
cp .env.example .env
.venv/bin/python start_api.py          # DEBUG=true면 코드 변경 시 자동 재시작
```

구조는 [architecture.md](architecture.md)를 참고하세요.

## 규칙

- **프롬프트는 YAML에만 둡니다.** `config/prompts.yaml`, `report_prompts.yaml`, `rag_prompts.yaml`에 쓰고, 코드에서는 `config_loader.prompts.render("경로", ...)`로 불러옵니다.
- **`src/`는 `api/`를 import하지 않습니다.** 엔진은 이벤트만 내보내고, 저장·전송·권한은 `api/`가 맡습니다.
- **LLM 클라이언트는 `LLMFactory` 또는 `LLMBundle`로만 만듭니다.** 그래야 타임아웃·재시도·사용량 집계가 함께 적용됩니다.
- **LLM의 구조화 출력은 `with_structured_output`과 Pydantic으로 검증합니다.** 실패하면 재시도하고, JSON 문자열을 직접 파싱하지 않습니다.
- **파일명에 버전 표기(`_V2`, `_NEW` 등)를 쓰지 않습니다.**
- **커밋 전에 `pytest`가 통과(종료 코드 0)해야 합니다.**

## DB 스키마 변경

1. `api/models/`의 모델을 고칩니다. 새 모델은 `api/models/__init__.py`에 등록합니다.
2. 마이그레이션을 만들고 검토합니다. SQLite 호환을 위해 `batch_alter_table`을 쓰고, 데이터 변환이 필요하면 직접 작성합니다.

```bash
DATABASE_URL=sqlite:///./scratch.db SECRET_KEY=$(python3 -c "print('x'*40)") alembic upgrade head
DATABASE_URL=sqlite:///./scratch.db SECRET_KEY=$(python3 -c "print('x'*40)") alembic revision --autogenerate -m "설명"
```

3. 모델과 마이그레이션이 일치하는지 확인합니다. 새 DB에 `upgrade head`를 적용한 뒤 아래 명령에서 "No new upgrade operations"가 나와야 합니다.

```bash
alembic check
```

## 새 LLM 기능을 추가할 때

- 엔진 기능은 `src/`에 구현합니다. 실행 중 상태가 필요하면 `api/runtime/`에 둡니다.
- 비용이 큰 기능은 토론별 플래그로 만들고, `limits.user_expensive_features`로 일반 사용자 사용을 막습니다.
- 실제 LLM 동작은 짧은 토론(AI 발언 4~6회)으로 확인합니다. 응답이 잘리지 않았는지(`stop_reason`)와 출력 형식(Haiku는 목록 필드를 문자열로 줄 때가 있음)을 확인하세요.
