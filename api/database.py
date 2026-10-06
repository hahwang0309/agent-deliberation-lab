"""
데이터베이스 연결 및 세션 관리
"""
import logging
from pathlib import Path
from sqlalchemy import create_engine, inspect
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from api.config import settings

# 데이터베이스 엔진
engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {},
    pool_pre_ping=True,  # 연결 유효성 확인
    pool_size=10,  # 연결 풀 크기
    max_overflow=20,  # 최대 추가 연결
    pool_recycle=3600,  # 1시간마다 연결 재활용
    echo=False  # SQL 로깅 비활성화 (성능을 위해)
)

# 세션 팩토리
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base 클래스
Base = declarative_base()


def get_db():
    """데이터베이스 세션 의존성"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


logger = logging.getLogger(__name__)

# create_all 시절 스키마에 해당하는 Alembic 기준 리비전
BASELINE_REVISION = "115ef33629d0"


def init_db():
    """데이터베이스 마이그레이션을 최신(head)으로 적용

    Alembic 도입 전 create_all로 만들어진 DB는 기준 리비전으로 stamp 후 업그레이드한다.
    """
    from alembic import command
    from alembic.config import Config

    alembic_cfg = Config(str(Path(__file__).resolve().parent.parent / "alembic.ini"))
    alembic_cfg.attributes["configure_logger"] = False

    tables = set(inspect(engine).get_table_names())
    if "alembic_version" not in tables and tables:
        logger.warning("Alembic 이력이 없는 기존 DB 감지 → 기준 리비전 %s로 stamp", BASELINE_REVISION)
        command.stamp(alembic_cfg, BASELINE_REVISION)

    command.upgrade(alembic_cfg, "head")

