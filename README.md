# Agent Deliberation Lab

서로 다른 배경과 신념을 가진 AI 페르소나들이 토론하고, 사람이 중간에 참여할 수 있으며, 토론 과정에서 입장이 어떻게 움직이고 어디까지 합의되는지를 기록·분석하는 연구용 토론 플랫폼입니다.

## 주요 기능

- **이론 기반 토론 진행**: 참가자 수와 발언 수로 명제·예산을 정하고, 응답 의무·교착 중재·반대 검토 같은 규칙으로 발언자와 발화 행위(반박, 근거 반박, 동조, 사례, 양보 등)를 고릅니다. 입장은 Friedkin–Johnsen 동역학, 수용·거부 범위, 설득 요인(논증의 질·새로움·가치 일치 등)으로 갱신됩니다.
- **사람 개입**: AI 발언 중 "발언 요청" → 그 발언이 끝나면 토론이 멈추고 입력을 기다림 → 다음 AI가 그 발언에 응답합니다.
- **종합보고서**: 쟁점별 합의 정도(종합, AI간, 인간간, AI-인간간), 입장 궤적, 누가 누구를 움직였는지, 대립 속 공통 기반(양보), 답하지 않은 반박을 정리합니다.
- **연구용 실험 도구**: 토론별 실험 조건(진행 장치 on/off, 동역학 파라미터, 참가자별 고집도·temperature, 분석 모델 분리), 기준선 모드, 고정 명제·배경 자료, 사전·사후 설문, 배치 실행(주제 × 조건 × 반복), 재현성 기록, 분석용 데이터셋과 사람 코딩 표본 추출을 지원합니다.
- **계정·관리자**: 가입 신청 → 관리자 승인 또는 발급, 사용자별 실행 제한으로 LLM 비용을 통제합니다.

## Quick Start

요구사항: Python 3.12, Anthropic API 키 (기본 모델 Claude Haiku 4.5)

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

http://localhost:8000 에 접속해 `ADMIN_EMAIL`과 임시 비밀번호로 로그인하면 비밀번호를 바꾼 뒤 바로 사용할 수 있습니다. Docker 실행은 [docs/deployment.md](docs/deployment.md)를 참고하세요.

## 사용 예

**웹에서 토론하기**

1. 메인 화면에서 주제를 입력하고 "주제로 자동 생성"으로 페르소나 3명을 만든 뒤 "생성 후 시작"을 누릅니다.
2. 토론 화면에서 현재 입장 패널을 보며 발언을 읽다가 "발언 요청"으로 참여할 수 있습니다. 끝나면 아래에 종합보고서가 표시됩니다.

**배치 실험 돌리기** (전용 DB 필수, 자세한 내용은 [docs/experiments.md](docs/experiments.md))

```bash
.venv/bin/python scripts/run_experiment.py config/experiments/example.yaml --db data/experiments.db --dry-run
```

```bash
.venv/bin/python scripts/run_experiment.py config/experiments/example.yaml --db data/experiments.db
```

```bash
.venv/bin/python scripts/export_dataset.py --db data/experiments.db --batch example-death-penalty --out data/example
```

## 문서

| 문서 | 내용 |
|---|---|
| [architecture.md](docs/architecture.md) | 엔진·런타임·SSE·사람 개입·보고서 구조, 토론 메커니즘과 이론 |
| [experiments.md](docs/experiments.md) | 연구용 배치 실험 실행과 데이터 추출 |
| [api-reference.md](docs/api-reference.md) | REST API와 SSE 이벤트 |
| [configuration.md](docs/configuration.md) | `.env`, `config.yaml`, 토론·실험 조건 파라미터 |
| [deployment.md](docs/deployment.md) | Docker, HTTPS, 운영 시 주의점 |
| [development.md](docs/development.md) | 개발 환경, 규칙, DB 마이그레이션 |
| [testing.md](docs/testing.md) | 테스트 구성과 실행 |
| [troubleshooting.md](docs/troubleshooting.md) | 자주 겪는 문제 |
| [changelog.md](docs/changelog.md) | 변경 이력 |

## 라이선스와 기여

라이선스 파일은 아직 없습니다. 기여할 때는 [development.md](docs/development.md)의 규칙(프롬프트는 YAML에만, 파일명에 버전 표기 금지, 커밋 전 테스트 통과)을 따라 주세요.
