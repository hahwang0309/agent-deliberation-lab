"""
FastAPI 메인 애플리케이션
"""
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from pathlib import Path
from api.config import settings
from api.database import init_db
from api.utils.admin_auth import AdminBasicAuthMiddleware
from src.utils.logger import setup_logging

setup_logging(settings.LOG_LEVEL)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """앱 시작/종료 처리"""
    init_db()
    logger.info("%s v%s started (docs: /docs)", settings.APP_NAME, settings.APP_VERSION)
    yield
    logger.info("API server shutting down...")

from api.routers import auth_router, users_router, discussions_router, messages_router, analytics_router, personas_router, export_router, config_router, investigations_router
from api.routers.batch_analyses import router as batch_analyses_router

# FastAPI 앱 생성
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="""
    Multi-Agent Discussion System API
    
    ## 기능
    
    ### 행정조사 중복 판별 ⭐ NEW
    * 두 행정조사의 중복 여부 분석
    * AI 페르소나 자동 생성 및 토론
    * 종합 보고서 생성 (Markdown)
    * 분석 이력 조회 및 관리
    
    ### 인증
    * 회원가입
    * 로그인
    * 토큰 갱신
    
    ### 사용자
    * 내 정보 조회
    * 내 정보 수정
    * 비밀번호 변경
    
    ### 토론
    * 토론 생성 및 관리
    * 토론 시작/일시정지/재개/종료
    * 토론 목록 및 상태 조회
    
    ### 메시지
    * 메시지 목록 조회
    * 메시지 상세 조회
    * 실시간 스트리밍 (SSE)
    
    ### 분석
    * 토론 종합 분석
    * 토론 요약
    * 페르소나 진화 추적
    
    ### 페르소나
    * 페르소나 템플릿 목록
    * 커스텀 페르소나 생성
    
    ### 내보내기
    * JSON 내보내기
    * Markdown 내보내기
    
    ### 설정
    * 시스템 설정 조회
    * LLM 프로바이더 상태
    """,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# 관리자 인증 (CORS보다 먼저 등록 → CORS가 바깥에서 preflight 처리)
if not settings.ADMIN_PASSWORD:
    raise RuntimeError("ADMIN_PASSWORD가 설정되지 않았습니다. .env에 ADMIN_PASSWORD를 설정하세요.")
app.add_middleware(
    AdminBasicAuthMiddleware,
    username=settings.ADMIN_USERNAME,
    password=settings.ADMIN_PASSWORD,
    exempt_paths=["/health"],
)

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 라우터 등록
app.include_router(auth_router)
app.include_router(users_router)
app.include_router(discussions_router)
app.include_router(messages_router)
app.include_router(analytics_router)
app.include_router(personas_router)
app.include_router(export_router)
app.include_router(config_router)
app.include_router(investigations_router)
app.include_router(batch_analyses_router)

# 정적 파일 서빙 (프론트엔드)
frontend_path = Path(__file__).parent.parent / "frontend"
if frontend_path.exists():
    # 정적 파일 (CSS, JS, 이미지 등)
    app.mount("/static", StaticFiles(directory=str(frontend_path)), name="static")

    @app.get("/", tags=["프론트엔드"], include_in_schema=False)
    async def serve_index():
        """메인 페이지"""
        file_path = frontend_path / "index.html"
        if file_path.exists():
            return FileResponse(str(file_path))
        return JSONResponse(status_code=404, content={"error": "Page not found"})

    @app.get("/investigation_analysis.html", tags=["프론트엔드"], include_in_schema=False)
    async def serve_investigation_analysis():
        """행정조사 분석 페이지"""
        file_path = frontend_path / "investigation_analysis.html"
        if file_path.exists():
            return FileResponse(str(file_path))
        return JSONResponse(status_code=404, content={"error": "Page not found"})


@app.get("/api", tags=["헬스체크"])
def root():
    """API 루트 엔드포인트"""
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "running",
        "docs": "/docs"
    }


@app.get("/health", tags=["헬스체크"])
def health_check():
    """헬스 체크 엔드포인트"""
    return {
        "status": "healthy",
        "version": settings.APP_VERSION
    }


# 에러 핸들러
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Pydantic 유효성 검사 에러 핸들러"""
    errors = exc.errors()
    
    if errors:
        first_error = errors[0]
        field = ".".join(str(x) for x in first_error["loc"][1:])
        message = first_error["msg"]
        
        # 비밀번호 관련 에러 처리
        if "password" in field.lower():
            return JSONResponse(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                content={
                    "error": {
                        "code": "INVALID_PASSWORD",
                        "message": message,
                        "field": field
                    }
                }
            )
        
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": message,
                    "field": field
                }
            }
        )
    
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "입력값이 올바르지 않습니다."
            }
        }
    )


@app.exception_handler(ValidationError)
async def pydantic_validation_exception_handler(request: Request, exc: ValidationError):
    """Pydantic ValidationError 핸들러"""
    errors = exc.errors()
    
    if errors:
        first_error = errors[0]
        field = ".".join(str(x) for x in first_error["loc"])
        message = first_error["msg"]
        
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": message,
                    "field": field
                }
            }
        )
    
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "입력값이 올바르지 않습니다."
            }
        }
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """일반 예외 핸들러"""
    print(f"❌ Unhandled exception: {exc}")
    
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": {
                "code": "INTERNAL_SERVER_ERROR",
                "message": "서버 오류가 발생했습니다."
            }
        }
    )


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "api.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG
    )

