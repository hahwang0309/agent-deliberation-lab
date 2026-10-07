# Multi-Agent Persona Discussion System

서로 다른 배경과 신념을 가진 AI 페르소나들이 주제를 토론하고, 사람이 중간에 끼어들 수 있으며, 끝나면 합의된 내용과 합의되지 않은 내용을 정리한 종합보고서를 만드는 웹 서비스입니다.

## 주요 기능

- **페르소나 토론**: 템플릿 또는 주제 기반 자동 생성 페르소나가 모더레이터 진행 아래 토론 (기본 모델 Claude Haiku 4.5)
- **실시간 스트리밍**: 발언이 생성되는 대로 브라우저에 표시, 늦게 들어와도 이전 발언부터 이어 보기
- **사람 개입**: AI 발언 중 "발언 요청" → 그 발언이 끝나면 토론이 멈추고 입력을 기다림 → 다음 AI가 그 발언에 응답
- **종합보고서**: 쟁점별 입장과 합의 정도(종합·AI·사람 점수), 요약·열린 질문·제언, Markdown/JSON 내보내기
- **계정·관리자**: 가입 신청 → 관리자 승인 또는 관리자 발급, 사용자별 실행 제한으로 LLM 비용 통제

## Quick Start

요구사항: Python 3.12, Anthropic API 키

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
```

`.env`에서 다음 값을 채웁니다.

```bash
ANTHROPIC_API_KEY=sk-ant-...
SECRET_KEY=        # python3 -c "import secrets; print(secrets.token_urlsafe(48))"
ADMIN_EMAIL=you@example.com
ADMIN_INITIAL_PASSWORD=첫-로그인용-임시-비밀번호
```

```bash
.venv/bin/python start_api.py
```

http://localhost:8000 에 접속해 `ADMIN_EMAIL`과 임시 비밀번호로 로그인하면 비밀번호 변경 후 바로 사용할 수 있습니다. Docker 실행은 [docs/deployment.md](docs/deployment.md)를 참고하세요.

## 사용 예

1. 메인 화면에서 주제 입력 → "주제로 자동 생성"으로 페르소나 3명 생성 → "생성 후 시작"
2. 토론 화면에서 AI 발언을 보다가 "발언 요청" → 차례가 오면 의견 입력 → AI가 응답 → 토론이 끝나면 아래에 종합보고서 표시

API로 토론을 만들고 시작하는 예 (로그인 쿠키와 `X-CSRF-Token` 헤더 필요, 자세한 내용은 [API 문서](docs/api-reference.md)):

```bash
curl -b cookies.txt -H "X-CSRF-Token: $CSRF" -H "Content-Type: application/json" \
  -d '{"topic":"주 4일제를 도입해야 하는가?","personas":[...]}' \
  http://localhost:8000/api/v1/discussions
```

## 문서

| 문서 | 내용 |
|---|---|
| [architecture.md](docs/architecture.md) | 엔진·런타임·SSE·사람 개입·보고서 구조 |
| [api-reference.md](docs/api-reference.md) | REST API와 SSE 이벤트 |
| [configuration.md](docs/configuration.md) | `.env`, `config.yaml`, 프롬프트 YAML |
| [deployment.md](docs/deployment.md) | Docker, HTTPS, 운영 시 주의점 |
| [development.md](docs/development.md) | 개발 환경, 규칙, DB 마이그레이션 |
| [testing.md](docs/testing.md) | 테스트 구성과 실행 |
| [troubleshooting.md](docs/troubleshooting.md) | 자주 겪는 문제 |
| [experiments.md](docs/experiments.md) | 연구용 배치 실험 실행과 데이터 추출 |
| [changelog.md](docs/changelog.md) | 변경 이력 |

## 라이선스와 기여

라이선스 파일은 아직 없습니다. 기여 시 [development.md](docs/development.md)의 규칙(프롬프트는 YAML에만, 파일명에 버전 표기 금지, 커밋 전 테스트 통과)을 따라 주세요.
