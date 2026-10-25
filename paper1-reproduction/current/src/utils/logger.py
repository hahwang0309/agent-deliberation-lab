"""
로깅 시스템
stdout 단일 핸들러 (Docker/uvicorn 로그와 함께 수집됨). 레벨은 LOG_LEVEL 환경변수.
"""
import logging
import os

LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'


def setup_logging(level: str = None) -> None:
    """루트 로거 설정 (앱 시작 시 1회 호출)"""
    level_name = (level or os.getenv("LOG_LEVEL", "INFO")).upper()
    logging.basicConfig(
        level=getattr(logging, level_name, logging.INFO),
        format=LOG_FORMAT,
        force=True
    )


# 로거 인스턴스
logger = logging.getLogger("MultiAgentSystem")


def set_log_level(level: str):
    """로그 레벨 변경"""
    logging.getLogger().setLevel(getattr(logging, level.upper(), logging.INFO))


def log_errors(func):
    """함수 에러를 자동으로 로깅하는 데코레이터"""
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            logger.error(f"Error in {func.__name__}: {str(e)}", exc_info=True)
            raise
    return wrapper
