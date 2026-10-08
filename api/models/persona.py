"""
페르소나 데이터베이스 모델
"""
from datetime import datetime
from sqlalchemy import Column, String, Float, Boolean, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from api.database import Base
from config.config_loader import config_loader


class CustomPersona(Base):
    """커스텀 페르소나 모델"""
    __tablename__ = "custom_personas"
    
    id = Column(String, primary_key=True, index=True)  # custom_abc123def
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    
    # 기본 정보
    name = Column(String(50), nullable=False)
    role = Column(String(100), nullable=False)
    background = Column(String(500), nullable=True)
    
    # JSON 필드로 리스트 저장
    expertise = Column(JSON, nullable=False)  # List[str]
    personality = Column(JSON, nullable=False)  # List[str]
    beliefs = Column(JSON, nullable=False)  # List[str]
    
    # 커뮤니케이션 스타일
    communication_style = Column(String(200), nullable=False)
    
    # LLM 설정
    # 기본값은 config.yaml (llm.default_provider와 그 프로바이더의 기본 모델)
    llm_provider = Column(String(50), nullable=False, default=lambda: config_loader.get_llm_config().default_provider)
    model = Column(String(100), nullable=False, default=lambda: config_loader.get_llm_config().default_models[
        config_loader.get_llm_config().default_provider])
    
    # 초기 개방성
    initial_openness = Column(Float, nullable=False, default=0.5)
    
    # 메타데이터
    is_custom = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # 관계
    user = relationship("User", back_populates="custom_personas")
    
    def __repr__(self):
        return f"<CustomPersona(id={self.id}, name={self.name}, user_id={self.user_id})>"

