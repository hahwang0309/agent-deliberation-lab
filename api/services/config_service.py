"""
설정 서비스
"""
import time
import os
from datetime import datetime

from api.config import settings
from config.config_loader import config_loader
from src.models.personas import LLMProvider
from src.utils.llm_provider import LLMFactory
from api.schemas.config import (
    SystemConfigResponse,
    SystemInfo,
    Features,
    Limits,
    RateLimits,
    LLMProvidersResponse,
    LLMProviderStatus,
    LLMModelInfo
)


# 서버 시작 시간 (업타임 계산용)
SERVER_START_TIME = time.time()


class ConfigService:
    """설정 서비스"""
    
    @staticmethod
    def get_system_config() -> SystemConfigResponse:
        """
        시스템 설정 조회
        
        Returns:
            SystemConfigResponse: 시스템 설정
        """
        # 업타임 계산
        uptime_seconds = int(time.time() - SERVER_START_TIME)
        
        # 시스템 정보
        system = SystemInfo(
            version="1.0.0",
            environment=settings.ENVIRONMENT,
            api_version="v1",
            server_time=datetime.utcnow(),
            uptime_seconds=uptime_seconds
        )
        
        # 기능 활성화 여부
        features = Features(
            rag_enabled=True,
            subtopics_enabled=True,
            reflection_enabled=True,
            persona_evolution_enabled=True,
            custom_personas_enabled=True,
            export_enabled=True
        )
        
        # 시스템 제한
        limits = Limits(
            max_discussions_per_user=100,
            max_concurrent_discussions=config_loader.config.limits.max_global_running,
            max_participants_per_discussion=config_loader.config.limits.max_personas,
            max_rounds=20,
            max_message_length=config_loader.config.limits.max_human_chars,
            max_custom_personas=10
        )
        
        # API 요청 제한
        rate_limits = RateLimits(
            auth_requests_per_minute=10,
            discussion_create_per_hour=20,
            api_requests_per_minute=60,
            sse_connections=5
        )
        
        return SystemConfigResponse(
            system=system,
            features=features,
            limits=limits,
            rate_limits=rate_limits
        )
    
    @staticmethod
    def get_llm_providers_status() -> LLMProvidersResponse:
        """프로바이더별 키 설정 여부와 기본 모델 (config.yaml llm.default_models).
        실제 호출로 상태를 확인하지 않으므로 응답 시간·모델 메타데이터·단가는 비워 둔다"""
        current_time = datetime.utcnow()
        llm = config_loader.get_llm_config()
        available = LLMFactory.get_available_providers()
        providers = {}
        for provider in LLMProvider:
            ok = bool(available.get(provider))
            model = llm.default_models.get(provider.value)
            providers[provider.value] = LLMProviderStatus(
                available=ok,
                status="configured" if ok else "unavailable",
                reason=None if ok else "API key not configured",
                last_checked=current_time,
                models=[LLMModelInfo(id=model, name=model, max_tokens=llm.max_tokens, available=ok)] if ok and model else [],
            )
        total_available = sum(1 for p in providers.values() if p.available)
        return LLMProvidersResponse(
            providers=providers,
            total_available=total_available,
            total_unavailable=len(providers) - total_available,
            last_updated=current_time
        )
