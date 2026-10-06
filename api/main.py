"""
FastAPI 메인 애플리케이션
"""
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
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
    interrupted = mark_active_as_interrupted()
    if interrupted:
        logger.warning("Marked %d discussions from previous process as interrupted", interrupted)
    logger.info("%s v%s started (docs: /docs)", settings.APP_NAME, settings.APP_VERSION)
    yield
    logger.info("API server shutting down...")
    await registry.shutdown()

from api.routers import auth_router, users_router, discussions_router, messages_router, personas_router, config_router
from api.runtime import registry
from api.runtime.persistence import mark_active_as_interrupted

# FastAPI 앱 생성
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="멀티 에이전트 페르소나 토론 API",
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
app.include_router(personas_router)
app.include_router(config_router)


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
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": {
                "code": "INTERNAL_SERVER_ERROR",
                "message": "서버 오류가 발생했습니다."
            }
        }
    )


# 웹 UI (API 라우트 뒤에 마운트해야 /api, /docs 등이 우선 매칭됨)
web_path = Path(__file__).parent.parent / "web"
app.mount("/", StaticFiles(directory=str(web_path), html=True), name="web")


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "api.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG
    )

