"""
로깅 시스템
"""
import logging
from datetime import datetime
import os

# 로그 디렉토리 생성
log_dir = "logs"
if not os.path.exists(log_dir):
    os.makedirs(log_dir)

# 로그 파일명 (날짜 포함)
log_filename = f"{log_dir}/app_{datetime.now().strftime('%Y%m%d')}.log"

# 로거 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_filename, encoding='utf-8')
        # logging.StreamHandler()  # 콘솔 출력 제거
    ]
)

# 로거 인스턴스
logger = logging.getLogger("MultiAgentSystem")

# 로그 레벨 설정 함수
def set_log_level(level: str):
    """로그 레벨 변경"""
    level_map = {
        'DEBUG': logging.DEBUG,
        'INFO': logging.INFO,
        'WARNING': logging.WARNING,
        'ERROR': logging.ERROR,
        'CRITICAL': logging.CRITICAL
    }
    if level.upper() in level_map:
        logger.setLevel(level_map[level.upper()])
        logger.info(f"Log level changed to {level.upper()}")

# 에러 로깅 데코레이터
def log_errors(func):
    """함수 에러를 자동으로 로깅하는 데코레이터"""
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            logger.error(f"Error in {func.__name__}: {str(e)}", exc_info=True)
            raise
    return wrapper

# 시작 메시지 (파일에만 기록)
logger.info("=" * 50)
logger.info("Multi-Agent System Started")
logger.info(f"Log file: {log_filename}")
logger.info("=" * 50)