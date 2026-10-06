# 배포

## Docker

```bash
cp .env.example .env   # SECRET_KEY, ANTHROPIC_API_KEY, ADMIN_EMAIL, ADMIN_INITIAL_PASSWORD 설정
./docker-start.sh      # Windows: docker-start.bat
```

- 호스트 포트 8106에서 컨테이너 포트 8000으로 연결됩니다. 접속은 http://localhost:8106 입니다.
- `.env`는 이미지에 넣지 않습니다(`.dockerignore`). 실행할 때 `env_file`로 주입합니다.
- SQLite를 쓰면 `DATABASE_URL=sqlite:////app/data/app.db`로 설정하세요. `./data:/app/data` 볼륨에 저장되어 컨테이너를 다시 만들어도 유지됩니다.
- 헬스체크는 `/health`(인증 불필요)를 씁니다.

## 운영 시 주의

| 항목 | 내용 |
|---|---|
| 단일 워커 | 실행 중인 토론·발언 대기열이 프로세스 메모리에 있습니다. `uvicorn --workers`를 2 이상으로 쓰거나 여러 컨테이너로 나누면 안 됩니다 |
| HTTPS | 인증 쿠키를 보호하려면 리버스 프록시(nginx, Caddy 등)로 TLS를 적용하고 `COOKIE_SECURE=true`를 설정하세요 |
| SSE 프록시 | 프록시가 응답을 버퍼링하지 않게 하세요. 서버는 `X-Accel-Buffering: no`를 보냅니다. 연결 유지 시간은 길게 잡으세요 (15초마다 heartbeat 전송) |
| DB 마이그레이션 | 서버 시작 시 `alembic upgrade head`가 자동 실행됩니다. Alembic 이전의 DB는 기준 버전으로 자동 표시(stamp)한 뒤 업그레이드합니다 |
| 재시작 | 실행 중이던 토론은 `interrupted`로 표시되고, 화면의 "이어서 진행"으로 재개할 수 있습니다 (페르소나 진화 상태는 복원되지 않음) |
| 비용 | 토론 1회(페르소나 3명, AI 발언 6회 + 보고서)는 Claude Haiku 4.5 기준 입력 약 2만, 출력 약 8천 토큰이 듭니다(실측). 사용자별 한도는 관리자 화면에서 조정합니다 |
| 로그 | stdout으로만 출력합니다(`LOG_LEVEL`). `docker compose logs`로 확인하세요 |

## 기존 데이터

행정조사 분석 시절의 테이블(`investigation_analyses`, `batch_analyses`, `batch_analysis_items`)이 있는 DB는 마이그레이션할 때 `data/legacy_export/*.json`으로 내보낸 뒤 테이블을 삭제합니다.
