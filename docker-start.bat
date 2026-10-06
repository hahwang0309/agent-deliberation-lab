@echo off
REM Multi-Agent Investigation System - Docker 시작 스크립트 (Windows)

setlocal enabledelayedexpansion

echo ==========================================
echo   Multi-Agent Investigation System
echo   Docker 배포 스크립트 (Windows)
echo ==========================================
echo.

REM .env 파일 확인
if not exist .env (
    echo ❌ .env 파일이 없습니다!
    echo 📝 .env.example을 복사하여 .env 파일을 생성하세요.
    echo.
    echo 실행: copy .env.example .env
    echo 그 다음: .env 파일을 편집하여 필요한 값을 설정하세요.
    exit /b 1
)

echo ✅ .env 파일 확인 완료
echo.

REM Docker 설치 확인
where docker >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo ❌ Docker가 설치되어 있지 않습니다!
    echo 📝 https://docs.docker.com/desktop/windows/install/ 에서 Docker Desktop을 설치하세요.
    exit /b 1
)

where docker-compose >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo ❌ Docker Compose가 설치되어 있지 않습니다!
    exit /b 1
)

echo ✅ Docker 환경 확인 완료
echo.

REM 기존 컨테이너 확인
docker-compose ps -q >nul 2>nul
if %ERRORLEVEL% equ 0 (
    echo ⚠️  실행 중인 컨테이너가 있습니다.
    set /p cleanup="기존 컨테이너를 정리하시겠습니까? (y/N): "
    if /i "!cleanup!"=="y" (
        echo 🧹 기존 컨테이너 정리 중...
        docker-compose down
    )
)

echo.
echo 🔨 Docker 이미지 빌드 중...
docker-compose build

if %ERRORLEVEL% neq 0 (
    echo ❌ 빌드 실패!
    exit /b 1
)

echo.
echo 🚀 컨테이너 시작 중...
docker-compose up -d

if %ERRORLEVEL% neq 0 (
    echo ❌ 컨테이너 시작 실패!
    exit /b 1
)

echo.
echo ⏳ 서비스 시작 대기 중...
timeout /t 5 /nobreak >nul

REM 헬스체크
echo.
echo 🏥 헬스체크 진행 중...
set max_attempts=30
set attempt=0

:healthcheck_loop
if !attempt! geq !max_attempts! goto healthcheck_failed

curl -sf http://localhost:8106/health >nul 2>nul
if %ERRORLEVEL% equ 0 goto healthcheck_success

set /a attempt+=1
echo    대기 중... (!attempt!/!max_attempts!)
timeout /t 2 /nobreak >nul
goto healthcheck_loop

:healthcheck_failed
echo ❌ 서비스 시작에 실패했습니다.
echo 📋 로그를 확인하세요: docker-compose logs
exit /b 1

:healthcheck_success
echo ✅ 서비스가 정상적으로 시작되었습니다!

echo.
echo ==========================================
echo   🎉 배포 완료!
echo ==========================================
echo.
echo 📍 서비스 접속 정보:
echo    - 분석 페이지:   http://localhost:8106/investigation_analysis.html
echo    - API 문서:      http://localhost:8106/docs
echo    - 헬스체크:      http://localhost:8106/health
echo.
echo 📋 유용한 명령어:
echo    - 로그 확인:     docker-compose logs -f
echo    - 상태 확인:     docker-compose ps
echo    - 서비스 중지:   docker-compose stop
echo    - 완전 삭제:     docker-compose down
echo.
echo 📚 자세한 내용은 docs\docker-deployment.md를 참고하세요.
echo.

pause
