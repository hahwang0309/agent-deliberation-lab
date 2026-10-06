"""
설정 서비스
"""
import time
import os
from datetime import datetime

from api.config import settings
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
            max_concurrent_discussions=5,
            max_participants_per_discussion=5,
            max_rounds=20,
            max_message_length=1000,
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
        """
        LLM 프로바이더 상태 조회
        
        Returns:
            LLMProvidersResponse: LLM 프로바이더 상태
        """
        current_time = datetime.utcnow()
        providers = {}
        
        # OpenAI
        openai_available = bool(os.getenv("OPENAI_API_KEY"))
        providers["openai"] = LLMProviderStatus(
            available=openai_available,
            status="operational" if openai_available else "unavailable",
            response_time_ms=450 if openai_available else None,
            reason=None if openai_available else "API key not configured",
            last_checked=current_time,
            models=[
                LLMModelInfo(
                    id="gpt-4",
                    name="GPT-4",
                    version="gpt-4-0613",
                    context_window=8192,
                    max_tokens=4096,
                    cost_per_1k_input_tokens=0.03,
                    cost_per_1k_output_tokens=0.06,
                    available=openai_available
                ),
                LLMModelInfo(
                    id="gpt-3.5-turbo",
                    name="GPT-3.5 Turbo",
                    version="gpt-3.5-turbo-0125",
                    context_window=16384,
                    max_tokens=4096,
                    cost_per_1k_input_tokens=0.0005,
                    cost_per_1k_output_tokens=0.0015,
                    available=openai_available
                )
            ] if openai_available else []
        )
        
        # Claude (Anthropic)
        claude_available = bool(os.getenv("ANTHROPIC_API_KEY"))
        providers["claude"] = LLMProviderStatus(
            available=claude_available,
            status="operational" if claude_available else "unavailable",
            response_time_ms=520 if claude_available else None,
            reason=None if claude_available else "API key not configured",
            last_checked=current_time,
            models=[
                LLMModelInfo(
                    id="claude-3-opus-20240229",
                    name="Claude 3 Opus",
                    context_window=200000,
                    max_tokens=4096,
                    cost_per_1k_input_tokens=0.015,
                    cost_per_1k_output_tokens=0.075,
                    available=claude_available
                ),
                LLMModelInfo(
                    id="claude-3-sonnet-20240229",
                    name="Claude 3 Sonnet",
                    context_window=200000,
                    max_tokens=4096,
                    cost_per_1k_input_tokens=0.003,
                    cost_per_1k_output_tokens=0.015,
                    available=claude_available
                )
            ] if claude_available else []
        )
        
        # Gemini
        gemini_available = bool(os.getenv("GOOGLE_API_KEY"))
        providers["gemini"] = LLMProviderStatus(
            available=gemini_available,
            status="operational" if gemini_available else "unavailable",
            response_time_ms=400 if gemini_available else None,
            reason=None if gemini_available else "API key not configured",
            last_checked=current_time,
            models=[
                LLMModelInfo(
                    id="gemini-pro",
                    name="Gemini Pro",
                    context_window=32760,
                    max_tokens=8192,
                    cost_per_1k_input_tokens=0.00025,
                    cost_per_1k_output_tokens=0.0005,
                    available=gemini_available
                )
            ] if gemini_available else []
        )
        
        # Mistral
        mistral_available = bool(os.getenv("MISTRAL_API_KEY"))
        providers["mistral"] = LLMProviderStatus(
            available=mistral_available,
            status="operational" if mistral_available else "unavailable",
            response_time_ms=380 if mistral_available else None,
            reason=None if mistral_available else "API key not configured",
            last_checked=current_time,
            models=[
                LLMModelInfo(
                    id="mistral-large-latest",
                    name="Mistral Large",
                    context_window=32000,
                    max_tokens=8192,
                    cost_per_1k_input_tokens=0.008,
                    cost_per_1k_output_tokens=0.024,
                    available=mistral_available
                )
            ] if mistral_available else []
        )
        
        # 통계 계산
        total_available = sum(1 for p in providers.values() if p.available)
        total_unavailable = len(providers) - total_available
        
        return LLMProvidersResponse(
            providers=providers,
            total_available=total_available,
            total_unavailable=total_unavailable,
            last_updated=current_time
        )

