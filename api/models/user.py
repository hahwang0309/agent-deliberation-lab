"""
사용자 데이터베이스 모델
"""
from sqlalchemy import Column, String, DateTime, Integer, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from api.database import Base
import uuid


class User(Base):
    """사용자 모델"""
    __tablename__ = "users"
    
    # 기본 정보
    id = Column(String, primary_key=True, default=lambda: f"user_{uuid.uuid4().hex[:8]}")
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    name = Column(String(50), nullable=False)
    organization = Column(String(100), nullable=True)
    
    # 구독 정보
    subscription_plan = Column(String(20), default="free")  # free, pro, enterprise
    subscription_expires_at = Column(DateTime, nullable=True)
    
    # 로그인 제한
    login_attempts = Column(Integer, default=0)
    login_locked_until = Column(DateTime, nullable=True)
    
    # 활성화 상태
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)
    
    # 타임스탬프
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    last_login_at = Column(DateTime(timezone=True), nullable=True)
    
    # 관계
    custom_personas = relationship("CustomPersona", back_populates="user", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<User(id={self.id}, email={self.email}, name={self.name})>"

