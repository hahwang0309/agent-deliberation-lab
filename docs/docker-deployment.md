# Docker 배포 가이드

## 목차
1. [개요](#개요)
2. [아키텍처](#아키텍처)
3. [빠른 시작](#빠른-시작)
4. [상세 설정](#상세-설정)
5. [운영 가이드](#운영-가이드)
6. [문제 해결](#문제-해결)

---

## 개요

### Docker 구성
- **api**: FastAPI 백엔드 (Python 3.11)
- **nginx**: 웹 서버 + 리버스 프록시 (Alpine)
- **네트워크**: app-network (bridge)

### 특징
- ✅ Multi-stage build로 이미지 크기 최소화
- ✅ Non-root 사용자로 보안 강화
- ✅ Health check 자동 모니터링
- ✅ 리소스 제한으로 안정성 확보
- ✅ Nginx로 정적 파일 서빙 + API 프록시
- ✅ SSE 스트리밍 지원

---

## 아키텍처

```
┌─────────────────────────────────────────────────┐
│               사용자 브라우저                      │
└──────────────────┬──────────────────────────────┘
                   │ HTTP
                   ▼
         ┌─────────────────┐
         │  Nginx (Port 80)│
         │                 │
         │ - 정적 파일 서빙 │
         │ - 리버스 프록시  │
         └────────┬────────┘
                  │
         ┌────────┴────────┐
         │                 │
    정적 파일         API 요청
    (HTML/CSS/JS)    (프록시)
         │                 │
         ▼                 ▼
    /frontend/      ┌─────────────┐
                    │ FastAPI     │
                    │ (Port 8000) │
                    │             │
                    │ - 토론 진행  │
                    │ - SSE 스트림 │
                    └──────┬──────┘
                           │
                           ▼
                  ┌────────────────┐
                  │  PostgreSQL    │
                  │ (외부 DB 서버)  │
                  │ your-db-host   │
                  └────────────────┘
```

---

## 빠른 시작

### 1. 사전 준비

**필수 설치:**
- Docker (20.10 이상)
- Docker Compose (2.0 이상)

**확인:**
```bash
docker --version
docker-compose --version
```

### 2. 환경변수 설정

```bash
# .env 파일 생성
cp .env.example .env

# .env 파일 수정 (필수!)
# - OPENAI_API_KEY: OpenAI API 키
# - SECRET_KEY: JWT 시크릿 (운영 환경에서는 반드시 변경)
```

**.env 예시:**
```env
# OpenAI API
OPENAI_API_KEY=sk-your-key-here

# 보안
SECRET_KEY=your-super-secret-key-min-32-chars

# 데이터베이스 (기존 외부 PostgreSQL 사용)
DATABASE_URL=postgresql://persona_admin:your_password@your-db-host:5432/personadb

# CORS
CORS_ORIGINS=http://localhost
```

### 3. 빌드 및 실행

```bash
# 빌드 및 백그라운드 실행
docker-compose up -d --build

# 로그 확인
docker-compose logs -f

# 특정 서비스 로그만
docker-compose logs -f api
docker-compose logs -f nginx
```

### 4. 접속 확인

```bash
# 헬스체크
curl http://localhost/health

# API 문서
open http://localhost/docs

# 프론트엔드
open http://localhost
```

### 5. 중지 및 삭제

```bash
# 중지
docker-compose stop

# 중지 + 삭제
docker-compose down

# 볼륨까지 삭제 (데이터 완전 삭제)
docker-compose down -v
```

---

## 상세 설정

### Dockerfile 설명

```dockerfile
# Multi-stage build
FROM python:3.11-slim as builder
# Stage 1: 빌드 의존성 설치 (gcc, postgresql-client)
# Python 패키지를 /root/.local에 설치

FROM python:3.11-slim
# Stage 2: 런타임 이미지 (최소한의 패키지만)
# builder에서 설치된 패키지 복사
# non-root 사용자 생성 (보안)
```

**특징:**
- 최종 이미지 크기: ~500MB (단일 스테이지 대비 40% 감소)
- 보안: non-root 사용자 (appuser)
- 헬스체크: 30초마다 자동 확인

### docker-compose.yml 주요 설정

#### API 서비스
```yaml
api:
  build: .
  ports:
    - "8000:8000"
  environment:
    - DATABASE_URL=...
    - OPENAI_API_KEY=...
  volumes:
    - ./config:/app/config:ro   # 읽기 전용
    - ./logs:/app/logs           # 로그 저장
  deploy:
    resources:
      limits:
        cpus: '2'      # CPU 2코어 제한
        memory: 2G     # 메모리 2GB 제한
      reservations:
        cpus: '0.5'    # 최소 0.5코어 보장
        memory: 512M   # 최소 512MB 보장
```

#### Nginx 서비스
```yaml
nginx:
  image: nginx:alpine
  ports:
    - "80:80"
    - "443:443"  # HTTPS (SSL 설정 시)
  volumes:
    - ./frontend:/usr/share/nginx/html:ro
    - ./nginx/nginx.conf:/etc/nginx/nginx.conf:ro
  depends_on:
    - api  # API 서비스가 먼저 시작됨
```

### Nginx 설정

#### nginx.conf (메인 설정)
```nginx
worker_processes  auto;  # CPU 코어 수만큼 자동 설정
events {
    worker_connections  1024;  # 동시 연결 1024개
}
http {
    gzip  on;  # 압축 활성화
    gzip_types text/plain text/css application/json;
    client_max_body_size 10M;  # 업로드 크기 제한
}
```

#### default.conf (사이트 설정)
```nginx
# API 백엔드 upstream
upstream api_backend {
    server api:8000;
    keepalive 32;  # Keep-alive 연결 32개 유지
}

server {
    listen 80;

    # 정적 파일
    location / {
        root /usr/share/nginx/html;
        try_files $uri $uri/ /index.html;
    }

    # API 프록시
    location /api/ {
        proxy_pass http://api_backend;
        proxy_buffering off;  # SSE 스트리밍을 위해 버퍼링 비활성화
        proxy_read_timeout 3600s;  # 1시간 타임아웃
    }
}
```

**SSE 스트리밍 지원:**
- `proxy_buffering off`: 버퍼링 비활성화
- `proxy_cache off`: 캐싱 비활성화
- `proxy_read_timeout 3600s`: 긴 타임아웃 설정

---

## 운영 가이드

### 1. 로그 관리

```bash
# 실시간 로그 확인
docker-compose logs -f

# 최근 100줄만
docker-compose logs --tail=100

# 특정 시간 이후
docker-compose logs --since="2025-11-06T10:00:00"

# 로그 파일로 저장
docker-compose logs > app.log
```

**로그 위치:**
- API 로그: `./logs/` (호스트 마운트)
- Nginx 로그: 컨테이너 내부 `/var/log/nginx/`

### 2. 컨테이너 관리

```bash
# 상태 확인
docker-compose ps

# 재시작
docker-compose restart api
docker-compose restart nginx

# 리소스 사용량
docker stats

# 컨테이너 접속
docker-compose exec api bash
docker-compose exec nginx sh
```

### 3. 이미지 업데이트

```bash
# 코드 변경 후 재배포
docker-compose down
docker-compose up -d --build

# 이미지만 재빌드
docker-compose build --no-cache api

# 무중단 재배포 (blue-green)
docker-compose up -d --scale api=2  # 새 컨테이너 추가
docker-compose up -d --scale api=1  # 기존 컨테이너 제거
```

### 4. 데이터베이스 마이그레이션

```bash
# 컨테이너 내부에서 실행
docker-compose exec api bash

# 마이그레이션 실행
python -c "
from sqlalchemy import create_engine, text
import os

engine = create_engine(os.environ['DATABASE_URL'])
with open('migrations/add_total_rounds_and_indexes.sql') as f:
    with engine.connect() as conn:
        conn.execute(text(f.read()))
        conn.commit()
"
```

### 5. 백업 및 복원

**설정 파일 백업:**
```bash
# 백업
tar -czf backup-$(date +%Y%m%d).tar.gz \
    .env \
    config/ \
    nginx/

# 복원
tar -xzf backup-20251106.tar.gz
```

**데이터베이스 백업:** (외부 PostgreSQL 사용 시)
```bash
# 백업
docker-compose exec api pg_dump \
    -h your-db-host \
    -U persona_admin \
    -d personadb \
    > backup.sql

# 복원
docker-compose exec -T api psql \
    -h your-db-host \
    -U persona_admin \
    -d personadb \
    < backup.sql
```

### 6. 모니터링

**헬스체크:**
```bash
# API 헬스
curl http://localhost/health

# 컨테이너 헬스 상태
docker-compose ps
# healthy, unhealthy, starting 확인
```

**리소스 모니터링:**
```bash
# 실시간 리소스 사용량
docker stats

# 특정 컨테이너만
docker stats investigation-api
```

---

## 프로덕션 배포

### 1. HTTPS 설정 (SSL/TLS)

#### Let's Encrypt 사용
```bash
# Certbot 컨테이너 추가
docker run -it --rm \
    -v ./nginx/ssl:/etc/letsencrypt \
    certbot/certbot certonly \
    --webroot \
    --webroot-path=/var/www/certbot \
    -d yourdomain.com
```

#### Nginx SSL 설정
```nginx
server {
    listen 443 ssl http2;
    server_name yourdomain.com;

    ssl_certificate /etc/nginx/ssl/fullchain.pem;
    ssl_certificate_key /etc/nginx/ssl/privkey.pem;

    # 나머지 설정...
}

# HTTP → HTTPS 리다이렉트
server {
    listen 80;
    server_name yourdomain.com;
    return 301 https://$server_name$request_uri;
}
```

### 2. 환경변수 보안

```bash
# Docker Secrets 사용 (Swarm 모드)
echo "your-secret-key" | docker secret create api_secret_key -

# docker-compose.yml
services:
  api:
    secrets:
      - api_secret_key
    environment:
      - SECRET_KEY_FILE=/run/secrets/api_secret_key

secrets:
  api_secret_key:
    external: true
```

### 3. 리소스 제한 조정

```yaml
# 프로덕션용 리소스 설정
deploy:
  resources:
    limits:
      cpus: '4'       # CPU 4코어
      memory: 4G      # 메모리 4GB
    reservations:
      cpus: '1'       # 최소 1코어
      memory: 1G      # 최소 1GB
```

### 4. 로그 로테이션

**docker-compose.yml에 추가:**
```yaml
logging:
  driver: "json-file"
  options:
    max-size: "10m"     # 파일당 최대 10MB
    max-file: "5"       # 최대 5개 파일 유지
```

### 5. Auto-scaling (Docker Swarm)

```bash
# Swarm 모드 초기화
docker swarm init

# Stack 배포
docker stack deploy -c docker-compose.yml investigation

# 스케일링
docker service scale investigation_api=3  # API 3개 인스턴스
```

---

## 문제 해결

### 컨테이너가 시작되지 않음

```bash
# 로그 확인
docker-compose logs api

# 일반적인 원인:
# 1. 환경변수 누락 (.env 파일 확인)
# 2. 포트 충돌 (8000, 80 포트 사용 중)
# 3. 의존성 문제 (requirements.txt)
```

### 데이터베이스 연결 실패

```bash
# 컨테이너에서 DB 연결 테스트
docker-compose exec api python -c "
from sqlalchemy import create_engine
import os
engine = create_engine(os.environ['DATABASE_URL'])
conn = engine.connect()
print('DB 연결 성공!')
"

# 방화벽 확인
# your-db-host:5432 포트가 열려 있는지 확인
```

### Nginx 502 Bad Gateway

```bash
# API 서비스 상태 확인
docker-compose ps api
# State가 Up (healthy)인지 확인

# API 로그 확인
docker-compose logs api

# Nginx 로그 확인
docker-compose logs nginx
```

### 메모리 부족

```bash
# 리소스 제한 조정
# docker-compose.yml에서 memory 값 증가

deploy:
  resources:
    limits:
      memory: 4G  # 2G → 4G로 증가
```

### SSE 스트리밍이 작동하지 않음

```nginx
# nginx/conf.d/default.conf 확인
location /api/ {
    proxy_buffering off;       # 필수!
    proxy_cache off;           # 필수!
    proxy_read_timeout 3600s;  # 긴 타임아웃
}
```

---

## 성능 튜닝

### 1. Nginx Worker 프로세스

```nginx
# nginx.conf
worker_processes  auto;  # CPU 코어 수만큼
worker_connections  1024;  # 동시 연결 수
```

### 2. Keep-Alive 최적화

```nginx
# upstream keep-alive
upstream api_backend {
    server api:8000;
    keepalive 64;  # 연결 재사용
}

# 클라이언트 keep-alive
keepalive_timeout  65;
```

### 3. Gzip 압축

```nginx
gzip  on;
gzip_vary on;
gzip_min_length 1000;
gzip_types text/plain text/css application/json application/javascript;
```

### 4. 정적 파일 캐싱

```nginx
location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg)$ {
    expires 1y;
    add_header Cache-Control "public, immutable";
}
```

### 5. Connection Pool 설정

```python
# api/database.py (이미 적용됨)
engine = create_engine(
    DATABASE_URL,
    pool_size=10,        # 기본 10개
    max_overflow=20,     # 최대 30개
    pool_recycle=3600,   # 1시간마다 재활용
)
```

---

## 체크리스트

### 배포 전
- [ ] .env 파일 생성 및 설정
- [ ] OPENAI_API_KEY 설정
- [ ] SECRET_KEY 변경 (운영 환경)
- [ ] CORS_ORIGINS 설정
- [ ] 데이터베이스 연결 테스트

### 배포 후
- [ ] 헬스체크 확인 (http://localhost/health)
- [ ] API 문서 접속 (http://localhost/docs)
- [ ] 프론트엔드 접속 (http://localhost)
- [ ] 토론 생성 테스트
- [ ] SSE 스트리밍 작동 확인

### 운영 중
- [ ] 로그 모니터링
- [ ] 리소스 사용량 확인
- [ ] 헬스체크 정기 확인
- [ ] 디스크 공간 확인

---

## 참고 자료

### Docker 명령어
```bash
# 이미지 목록
docker images

# 컨테이너 목록
docker ps -a

# 사용하지 않는 리소스 정리
docker system prune -a

# 볼륨 정리
docker volume prune
```

### Docker Compose 명령어
```bash
# 전체 명령어
docker-compose --help

# 특정 서비스만 시작
docker-compose up api

# 스케일링
docker-compose up -d --scale api=3
```

---

**작성일**: 2025-11-06
**Docker 버전**: 20.10+
**Docker Compose 버전**: 2.0+
