# Multi-Agent Discussion System API

FastAPI 기반 REST API 서버

## 🚀 빠른 시작

### 1. 의존성 설치

```bash
# 기존 패키지 + API 패키지 설치
pip install -r requirements.txt
pip install -r api_requirements.txt
```

### 2. 환경 설정

```bash
# .env 파일 생성
cp env_example .env

# SECRET_KEY 반드시 변경!
# .env 파일에서 SECRET_KEY를 강력한 랜덤 문자열로 변경하세요
```

### 3. 서버 실행

```bash
# 개발 모드 (자동 재시작)
python api/main.py

# 또는
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
```

### 4. API 문서 확인

서버 실행 후 브라우저에서 접속:

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

## 📋 API 엔드포인트

### 인증 (Authentication)

| 메서드 | 엔드포인트 | 설명 | 인증 필요 |
|--------|-----------|------|----------|
| POST | `/api/v1/auth/register` | 회원가입 | ❌ |
| POST | `/api/v1/auth/login` | 로그인 | ❌ |
| POST | `/api/v1/auth/refresh` | 토큰 갱신 | ❌ |

### 사용자 (Users)

| 메서드 | 엔드포인트 | 설명 | 인증 필요 |
|--------|-----------|------|----------|
| GET | `/api/v1/users/me` | 내 정보 조회 | ✅ |
| PUT | `/api/v1/users/me` | 내 정보 수정 | ✅ |
| PUT | `/api/v1/users/me/password` | 비밀번호 변경 | ✅ |

### 토론 (Discussions)

| 메서드 | 엔드포인트 | 설명 | 인증 필요 |
|--------|-----------|------|----------|
| POST | `/api/v1/discussions` | 토론 생성 | ✅ |
| POST | `/api/v1/discussions/{id}/start` | 토론 시작 | ✅ |
| GET | `/api/v1/discussions/{id}` | 토론 상태 조회 | ✅ |
| GET | `/api/v1/discussions` | 토론 목록 조회 | ✅ |
| POST | `/api/v1/discussions/{id}/pause` | 토론 일시정지 | ✅ |
| POST | `/api/v1/discussions/{id}/resume` | 토론 재개 | ✅ |
| POST | `/api/v1/discussions/{id}/stop` | 토론 종료 | ✅ |

### 메시지 및 스트리밍 (Messages & Streaming)

| 메서드 | 엔드포인트 | 설명 | 인증 필요 |
|--------|-----------|------|----------|
| GET | `/api/v1/discussions/{id}/stream` | 실시간 스트림 (SSE) | ✅ |
| GET | `/api/v1/discussions/{id}/messages` | 메시지 목록 조회 | ✅ |
| GET | `/api/v1/discussions/{id}/messages/{msg_id}` | 메시지 상세 조회 | ✅ |

### 분석 (Analytics)

| 메서드 | 엔드포인트 | 설명 | 인증 필요 |
|--------|-----------|------|----------|
| GET | `/api/v1/discussions/{id}/analytics` | 토론 종합 분석 | ✅ |
| GET | `/api/v1/discussions/{id}/analytics/summary` | 토론 요약 | ✅ |
| GET | `/api/v1/discussions/{id}/analytics/persona-evolution` | 페르소나 진화 추적 | ✅ |

### 페르소나 (Personas)

| 메서드 | 엔드포인트 | 설명 | 인증 필요 |
|--------|-----------|------|----------|
| GET | `/api/v1/personas/templates` | 페르소나 템플릿 목록 | ✅ |
| POST | `/api/v1/personas/custom` | 커스텀 페르소나 생성 | ✅ |

### 내보내기 (Export)

| 메서드 | 엔드포인트 | 설명 | 인증 필요 |
|--------|-----------|------|----------|
| GET | `/api/v1/discussions/{id}/export/json` | JSON 내보내기 | ✅ |
| GET | `/api/v1/discussions/{id}/export/markdown` | Markdown 내보내기 | ✅ |

### 설정 (Config)

| 메서드 | 엔드포인트 | 설명 | 인증 필요 |
|--------|-----------|------|----------|
| GET | `/api/v1/config` | 시스템 설정 조회 | ✅ |
| GET | `/api/v1/config/llm-providers` | LLM 프로바이더 상태 | ✅ |

## 🔐 인증 방법

### 1. 회원가입

```bash
curl -X POST "http://localhost:8000/api/v1/auth/register" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "password": "SecurePass123!",
    "name": "김철수",
    "organization": "테크 스타트업"
  }'
```

### 2. 로그인

```bash
curl -X POST "http://localhost:8000/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "password": "SecurePass123!"
  }'
```

응답:
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer",
  "expires_in": 3600,
  "user": {
    "id": "user_a1b2c3d4",
    "email": "user@example.com",
    "name": "김철수"
  }
}
```

### 3. 인증이 필요한 API 호출

```bash
curl -X GET "http://localhost:8000/api/v1/users/me" \
  -H "Authorization: Bearer {access_token}"
```

## 🗂️ 프로젝트 구조

```
api/
├── __init__.py
├── main.py              # FastAPI 앱 엔트리포인트
├── config.py            # 설정
├── database.py          # 데이터베이스 연결
├── dependencies.py      # 공통 의존성
├── models/              # SQLAlchemy 모델
│   ├── __init__.py
│   └── user.py
├── schemas/             # Pydantic 스키마
│   ├── __init__.py
│   ├── auth.py
│   ├── user.py
│   └── error.py
├── routers/             # API 라우터
│   ├── __init__.py
│   ├── auth.py
│   └── users.py
├── services/            # 비즈니스 로직
│   ├── __init__.py
│   ├── auth_service.py
│   └── user_service.py
└── utils/               # 유틸리티
    ├── __init__.py
    ├── security.py      # JWT, 비밀번호 해싱
    └── validators.py    # 유효성 검사
```

## 🔧 설정 옵션

`.env` 파일에서 설정 가능:

### JWT 설정
- `SECRET_KEY`: JWT 암호화 키 (반드시 변경!)
- `ALGORITHM`: 암호화 알고리즘 (기본: HS256)
- `ACCESS_TOKEN_EXPIRE_MINUTES`: Access Token 만료 시간 (기본: 60분)
- `REFRESH_TOKEN_EXPIRE_DAYS`: Refresh Token 만료 시간 (기본: 7일)

### 보안 설정
- `PASSWORD_MIN_LENGTH`: 최소 비밀번호 길이 (기본: 8)
- `MAX_LOGIN_ATTEMPTS`: 최대 로그인 시도 횟수 (기본: 5)
- `LOGIN_ATTEMPT_TIMEOUT`: 로그인 잠금 시간 (기본: 300초)

### 데이터베이스
- `DATABASE_URL`: 데이터베이스 연결 URL
  - SQLite: `sqlite:///./discussion_api.db`
  - PostgreSQL: `postgresql://user:password@localhost:5432/dbname`
  - MySQL: `mysql+pymysql://user:password@localhost:3306/dbname`

## 🧪 테스트

```bash
# API 테스트 스크립트 실행
python test_api.py
```

## 🎭 페르소나 API 사용

### 1. 페르소나 템플릿 조회

```bash
curl -X GET "http://localhost:8000/api/v1/personas/templates" \
  -H "Authorization: Bearer {access_token}"
```

### 2. 커스텀 페르소나 생성

```bash
curl -X POST "http://localhost:8000/api/v1/personas/custom" \
  -H "Authorization: Bearer {access_token}" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "환경 운동가",
    "role": "Environmental Activist",
    "background": "기후 변화 전문가, 환경 NGO 대표",
    "expertise": ["Climate Change", "Sustainability", "Policy"],
    "personality": ["열정적", "진취적", "실천적"],
    "communication_style": "감정적이고 설득력 있는",
    "beliefs": ["지속 가능성이 최우선", "행동이 말보다 중요"],
    "initial_openness": 0.60,
    "llm_provider": "openai",
    "model": "gpt-4"
  }'
```

## 📤 내보내기 API 사용

### 1. JSON 내보내기

```bash
curl -X GET "http://localhost:8000/api/v1/discussions/{discussion_id}/export/json" \
  -H "Authorization: Bearer {access_token}" \
  -o discussion.json
```

### 2. Markdown 내보내기

```bash
curl -X GET "http://localhost:8000/api/v1/discussions/{discussion_id}/export/markdown" \
  -H "Authorization: Bearer {access_token}" \
  -o discussion.md
```

## ⚙️ 설정 API 사용

### 1. 시스템 설정 조회

```bash
curl -X GET "http://localhost:8000/api/v1/config" \
  -H "Authorization: Bearer {access_token}"
```

### 2. LLM 프로바이더 상태 조회

```bash
curl -X GET "http://localhost:8000/api/v1/config/llm-providers" \
  -H "Authorization: Bearer {access_token}"
```

## 📝 에러 코드

| 코드 | 설명 |
|------|------|
| `EMAIL_ALREADY_EXISTS` | 이메일 중복 |
| `INVALID_PASSWORD` | 비밀번호 형식 오류 |
| `INVALID_CREDENTIALS` | 로그인 실패 |
| `TOO_MANY_ATTEMPTS` | 로그인 시도 초과 |
| `INVALID_REFRESH_TOKEN` | Refresh Token 무효 |
| `CURRENT_PASSWORD_INCORRECT` | 현재 비밀번호 불일치 |
| `INVALID_TOKEN` | Access Token 무효 |
| `USER_NOT_FOUND` | 사용자 없음 |
| `VALIDATION_ERROR` | 입력값 검증 오류 |

## 🔒 보안 고려사항

1. **SECRET_KEY 변경**: 프로덕션 환경에서 반드시 강력한 랜덤 키 사용
2. **HTTPS 사용**: 프로덕션 환경에서는 HTTPS 필수
3. **환경변수**: 민감한 정보는 환경변수로 관리
4. **비밀번호 정책**: 강력한 비밀번호 요구 (영문+숫자+특수문자)
5. **로그인 제한**: 무차별 대입 공격 방지
6. **토큰 만료**: 적절한 토큰 만료 시간 설정

## 📦 프로덕션 배포

### Docker 사용 (추천)

```bash
# Dockerfile 생성 후
docker build -t discussion-api .
docker run -p 8000:8000 discussion-api
```

### 일반 서버

```bash
# Gunicorn + Uvicorn workers
gunicorn api.main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

## 🤝 기여

버그 리포트 및 기능 제안은 이슈로 등록해주세요.

## 📄 라이선스

MIT License

