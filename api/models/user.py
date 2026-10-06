"""
사용자 데이터베이스 모델
"""
from sqlalchemy import Column, String, DateTime, Integer, Boolean, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from api.database import Base
import uuid


class UserRole:
    USER = "user"
    ADMIN = "admin"


class UserStatus:
    PENDING = "pending"      # 가입 신청 후 관리자 승인 대기
    ACTIVE = "active"
    SUSPENDED = "suspended"  # 관리자가 정지
    REJECTED = "rejected"    # 가입 신청 거절


class User(Base):
    """사용자 모델"""
    __tablename__ = "users"

    # 기본 정보
    id = Column(String, primary_key=True, default=lambda: f"user_{uuid.uuid4().hex[:8]}")
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    name = Column(String(50), nullable=False)
    organization = Column(String(100), nullable=True)

    # 권한·상태
    role = Column(String(20), nullable=False, default=UserRole.USER)
    status = Column(String(20), nullable=False, default=UserStatus.PENDING)
    must_change_password = Column(Boolean, nullable=False, default=False)
    token_version = Column(Integer, nullable=False, default=0)  # 증가하면 기존 토큰 무효화
    signup_note = Column(Text, nullable=True)
    approved_by = Column(String, nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)

    # 사용자별 실행 제한 (NULL이면 config.yaml limits 기본값)
    max_concurrent = Column(Integer, nullable=True)
    daily_limit = Column(Integer, nullable=True)

    # 로그인 제한
    login_attempts = Column(Integer, default=0)
    login_locked_until = Column(DateTime, nullable=True)

    # 타임스탬프
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    last_login_at = Column(DateTime(timezone=True), nullable=True)

    # 관계
    custom_personas = relationship("CustomPersona", back_populates="user", cascade="all, delete-orphan")

    @property
    def is_admin(self) -> bool:
        return self.role == UserRole.ADMIN

    def __repr__(self):
        return f"<User(id={self.id}, email={self.email}, role={self.role}, status={self.status})>"
