"""
페르소나 API 라우터
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import Optional

from api.dependencies import get_db, get_current_user, get_optional_user
from api.models.user import User
from api.schemas.persona import (
    PersonaTemplateListResponse,
    CustomPersonaCreateRequest,
    CustomPersonaResponse
)
from api.schemas.error import ErrorResponse
from api.services.persona_service import PersonaService


router = APIRouter(prefix="/api/v1/personas", tags=["Personas"])


@router.get(
    "/templates",
    response_model=PersonaTemplateListResponse,
    summary="페르소나 템플릿 목록 (게스트 지원)",
    description="사전 정의된 페르소나 템플릿 목록을 조회합니다. 로그인 선택사항.",
    responses={
        200: {
            "description": "성공",
            "model": PersonaTemplateListResponse
        }
    }
)
async def get_persona_templates(
    _current_user: Optional[User] = Depends(get_optional_user)
) -> PersonaTemplateListResponse:
    """
    페르소나 템플릿 목록 조회
    
    사전 정의된 페르소나 템플릿 목록을 반환합니다.
    토론 생성 시 이 템플릿들을 사용할 수 있습니다.
    
    Args:
        _current_user: 현재 로그인한 사용자 (선택사항)
        
    Returns:
        PersonaTemplateListResponse: 템플릿 목록
    """
    return PersonaService.get_templates()


@router.post(
    "/custom",
    response_model=CustomPersonaResponse,
    status_code=status.HTTP_201_CREATED,
    summary="커스텀 페르소나 생성 (게스트 지원)",
    description="사용자 정의 페르소나를 생성합니다. 로그인 선택사항.",
    responses={
        201: {
            "description": "생성 성공",
            "model": CustomPersonaResponse
        },
        422: {
            "description": "유효성 검증 실패",
            "model": ErrorResponse
        }
    }
)
async def create_custom_persona(
    persona_data: CustomPersonaCreateRequest,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user)
) -> CustomPersonaResponse:
    """
    커스텀 페르소나 생성
    
    사용자가 직접 정의한 페르소나를 생성합니다.
    생성된 페르소나는 토론에서 사용할 수 있습니다.
    
    Args:
        persona_data: 페르소나 데이터
        db: 데이터베이스 세션
        current_user: 현재 로그인한 사용자 (선택사항)
        
    Returns:
        CustomPersonaResponse: 생성된 페르소나
    """
    try:
        user_id = current_user.id if current_user else "guest"
        return PersonaService.create_custom_persona(
            db=db,
            user_id=user_id,
            persona_data=persona_data
        )
    except ValueError as e:
        # 유효성 검증 오류
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": str(e),
                    "field": "persona_data"
                }
            }
        )
    except Exception as e:
        # 기타 오류
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "페르소나 생성 중 오류가 발생했습니다."
                }
            }
        )

