"""
설정 API 라우터
"""
from fastapi import APIRouter, Depends
from typing import Optional

from api.dependencies import get_current_user, get_optional_user
from api.models.user import User
from api.schemas.config import SystemConfigResponse, LLMProvidersResponse
from api.schemas.error import ErrorResponse
from api.services.config_service import ConfigService


router = APIRouter(prefix="/api/v1/config", tags=["Config"])


@router.get(
    "",
    response_model=SystemConfigResponse,
    summary="시스템 설정 조회 (게스트 지원)",
    description="시스템 설정, 기능, 제한 사항, API 요청 제한을 조회합니다. 로그인 선택사항.",
    responses={
        200: {
            "description": "성공",
            "model": SystemConfigResponse
        }
    }
)
async def get_system_config(
    _current_user: Optional[User] = Depends(get_optional_user)
) -> SystemConfigResponse:
    """
    시스템 설정 조회
    
    시스템의 전반적인 설정 정보를 조회합니다:
    - **system**: 버전, 환경, API 버전, 서버 시간, 업타임
    - **features**: 사용 가능한 기능 목록 (RAG, Subtopics, Reflection 등)
    - **limits**: 시스템 제한 (최대 토론 수, 참가자 수 등)
    - **rate_limits**: API 요청 제한 (분당/시간당 요청 수)
    
    Args:
        _current_user: 현재 로그인한 사용자 (선택사항)
        
    Returns:
        SystemConfigResponse: 시스템 설정
    """
    return ConfigService.get_system_config()


@router.get(
    "/llm-providers",
    response_model=LLMProvidersResponse,
    summary="LLM 프로바이더 상태 (게스트 지원)",
    description="사용 가능한 LLM 프로바이더 및 모델 목록을 조회합니다. 로그인 선택사항.",
    responses={
        200: {
            "description": "성공",
            "model": LLMProvidersResponse
        }
    }
)
async def get_llm_providers_status(
    _current_user: Optional[User] = Depends(get_optional_user)
) -> LLMProvidersResponse:
    """
    LLM 프로바이더 상태 조회
    
    사용 가능한 LLM 프로바이더와 모델 정보를 조회합니다:
    - **providers**: 각 프로바이더별 상태 및 모델 목록
      - OpenAI (GPT-4, GPT-3.5 Turbo)
      - Claude (Claude 3 Opus, Claude 3 Sonnet)
      - Gemini (Gemini Pro)
      - Mistral (Mistral Large)
    - **total_available**: 사용 가능한 프로바이더 수
    - **total_unavailable**: 사용 불가능한 프로바이더 수
    
    각 프로바이더의 모델 정보:
    - Context window 크기
    - 최대 토큰 수
    - 입력/출력 토큰당 비용
    - 사용 가능 여부
    
    Args:
        _current_user: 현재 로그인한 사용자 (선택사항)
        
    Returns:
        LLMProvidersResponse: LLM 프로바이더 상태
    """
    return ConfigService.get_llm_providers_status()

