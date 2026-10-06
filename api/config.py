"""
API 설정 및 YAML 기반 설정 통합
"""
from pydantic_settings import BaseSettings
from typing import Optional
from pathlib import Path
import sys

# config 모듈 경로 추가
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

# config.config_loader로 import하면 현재 파일과 충돌하므로 직접 import
import importlib.util
spec = importlib.util.spec_from_file_location(
    "config_loader_module",
    BASE_DIR / "config" / "config_loader.py"
)
config_loader_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(config_loader_module)

ConfigLoader = config_loader_module.ConfigLoader
AppConfig = config_loader_module.AppConfig
PromptManager = config_loader_module.PromptManager


class Settings(BaseSettings):
    """API 설정"""

    # 앱 설정
    APP_NAME: str = "Multi-Agent Discussion API"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    ENVIRONMENT: str = "production"  # development, production

    # 로그 레벨 (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    LOG_LEVEL: str = "INFO"

    # 서버 설정
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # 데이터베이스
    DATABASE_URL: str = "sqlite:///./discussion_api.db"
    # PostgreSQL 예시: "postgresql://user:password@localhost/dbname"

    # JWT 설정
    SECRET_KEY: str = "your-secret-key-change-this-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60  # 1시간
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7  # 7일

    # 보안 설정
    PASSWORD_MIN_LENGTH: int = 8
    MAX_LOGIN_ATTEMPTS: int = 5
    LOGIN_ATTEMPT_TIMEOUT: int = 300  # 5분 (초)

    # 관리자 Basic 인증 (전체 앱 보호, ADMIN_PASSWORD 미설정 시 서버 시작 불가)
    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD: str = ""

    # CORS 설정 (쉼표로 구분된 문자열)
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:8080"

    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"  # 추가 환경변수 무시

    @property
    def cors_origins_list(self) -> list[str]:
        """CORS origins를 리스트로 반환"""
        if self.CORS_ORIGINS == "*":
            return ["*"]
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",")]


# API 설정 인스턴스
settings = Settings()

# YAML 기반 설정 로더 (config.yaml, prompts.yaml 사용)
config_loader = ConfigLoader()

# 편의 함수들
def get_app_config() -> AppConfig:
    """전체 앱 설정 반환"""
    return config_loader.config

def get_prompts() -> PromptManager:
    """프롬프트 매니저 반환"""
    return config_loader.prompts

