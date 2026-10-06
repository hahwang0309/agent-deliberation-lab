#!/bin/bash

# Multi-Agent Investigation System - Docker 시작 스크립트

set -e

echo "=========================================="
echo "  Multi-Agent Investigation System"
echo "  Docker 배포 스크립트"
echo "=========================================="
echo ""

# .env 파일 확인
if [ ! -f .env ]; then
    echo "❌ .env 파일이 없습니다!"
    echo "📝 .env.example을 복사하여 .env 파일을 생성하세요."
    echo ""
    echo "실행: cp .env.example .env"
    echo "그 다음: .env 파일을 편집하여 필요한 값을 설정하세요."
    exit 1
fi

# 환경변수 로드
source .env

# 필수 환경변수 확인
if [ -z "$OPENAI_API_KEY" ] || [ "$OPENAI_API_KEY" = "your-openai-api-key-here" ]; then
    echo "❌ OPENAI_API_KEY가 설정되지 않았습니다!"
    echo "📝 .env 파일에서 OPENAI_API_KEY를 설정하세요."
    exit 1
fi

if [ -z "$ADMIN_PASSWORD" ]; then
    echo "❌ ADMIN_PASSWORD가 설정되지 않았습니다!"
    echo "📝 .env 파일에서 ADMIN_PASSWORD를 설정하세요."
    exit 1
fi

if [ -z "$DATABASE_URL" ]; then
    echo "❌ DATABASE_URL이 설정되지 않았습니다!"
    echo "📝 .env 파일에서 DATABASE_URL을 설정하세요."
    exit 1
fi

echo "✅ 환경변수 확인 완료"
echo ""

# Docker 실행 확인
if ! command -v docker &> /dev/null; then
    echo "❌ Docker가 설치되어 있지 않습니다!"
    echo "📝 https://docs.docker.com/get-docker/ 에서 Docker를 설치하세요."
    exit 1
fi

if ! command -v docker-compose &> /dev/null; then
    echo "❌ Docker Compose가 설치되어 있지 않습니다!"
    echo "📝 https://docs.docker.com/compose/install/ 에서 Docker Compose를 설치하세요."
    exit 1
fi

echo "✅ Docker 환경 확인 완료"
echo ""

# 기존 컨테이너 정리 여부 확인
if [ "$(docker-compose ps -q)" ]; then
    echo "⚠️  실행 중인 컨테이너가 있습니다."
    read -p "기존 컨테이너를 정리하시겠습니까? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "🧹 기존 컨테이너 정리 중..."
        docker-compose down
    fi
fi

echo ""
echo "🔨 Docker 이미지 빌드 중..."
docker-compose build

echo ""
echo "🚀 컨테이너 시작 중..."
docker-compose up -d

echo ""
echo "⏳ 서비스 시작 대기 중..."
sleep 5

# 헬스체크
echo ""
echo "🏥 헬스체크 진행 중..."
max_attempts=30
attempt=0

while [ $attempt -lt $max_attempts ]; do
    if curl -sf http://localhost:8106/health > /dev/null 2>&1; then
        echo "✅ 서비스가 정상적으로 시작되었습니다!"
        break
    fi
    attempt=$((attempt + 1))
    echo "   대기 중... ($attempt/$max_attempts)"
    sleep 2
done

if [ $attempt -eq $max_attempts ]; then
    echo "❌ 서비스 시작에 실패했습니다."
    echo "📋 로그를 확인하세요: docker-compose logs"
    exit 1
fi

echo ""
echo "=========================================="
echo "  🎉 배포 완료!"
echo "=========================================="
echo ""
echo "📍 서비스 접속 정보:"
echo "   - 메인 페이지:   http://localhost:8106/  (관리자 인증 필요)"
echo "   - API 문서:      http://localhost:8106/docs"
echo "   - 헬스체크:      http://localhost:8106/health"
echo ""
echo "📋 유용한 명령어:"
echo "   - 로그 확인:     docker-compose logs -f"
echo "   - 상태 확인:     docker-compose ps"
echo "   - 서비스 중지:   docker-compose stop"
echo "   - 완전 삭제:     docker-compose down"
echo ""
echo "📚 자세한 내용은 docs/docker-deployment.md를 참고하세요."
echo ""
