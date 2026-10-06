"""
인증 엔드포인트
"""
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from api.database import get_db
from api.schemas.auth import (
    RegisterRequest,
    RegisterResponse,
    LoginRequest,
    LoginResponse,
    TokenRefreshRequest,
    TokenRefreshResponse,
    UserInfo
)
from api.services.auth_service import AuthService
from api.config import settings

router = APIRouter(prefix="/api/v1/auth", tags=["인증"])


@router.post(
    "/register",
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
    summary="회원가입",
    description="새로운 사용자를 등록합니다."
)
def register(
    request: RegisterRequest,
    db: Session = Depends(get_db)
):
    """
    회원가입
    
    - **email**: 이메일 주소 (중복 불가)
    - **password**: 비밀번호 (최소 8자, 영문+숫자+특수문자)
    - **name**: 이름 (2-50자)
    - **organization**: 조직/회사명 (선택)
    """
    user = AuthService.register_user(db, request)
    
    return RegisterResponse(
        user_id=user.id,
        email=user.email,
        name=user.name,
        organization=user.organization,
        created_at=user.created_at
    )


@router.post(
    "/login",
    response_model=LoginResponse,
    status_code=status.HTTP_200_OK,
    summary="로그인",
    description="이메일과 비밀번호로 로그인하고 토큰을 발급받습니다."
)
def login(
    request: LoginRequest,
    db: Session = Depends(get_db)
):
    """
    로그인
    
    - **email**: 등록된 이메일 주소
    - **password**: 비밀번호
    
    성공 시 access_token과 refresh_token을 반환합니다.
    - access_token: 1시간 유효
    - refresh_token: 7일 유효
    """
    user, access_token, refresh_token = AuthService.authenticate_user(db, request)
    
    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=UserInfo(
            id=user.id,
            email=user.email,
            name=user.name,
            organization=user.organization
        )
    )


@router.post(
    "/refresh",
    response_model=TokenRefreshResponse,
    status_code=status.HTTP_200_OK,
    summary="토큰 갱신",
    description="Refresh Token으로 새로운 Access Token을 발급받습니다."
)
def refresh_token(
    request: TokenRefreshRequest,
    db: Session = Depends(get_db)
):
    """
    토큰 갱신
    
    - **refresh_token**: 로그인 시 발급받은 Refresh Token
    
    새로운 Access Token을 반환합니다.
    """
    new_access_token = AuthService.refresh_access_token(db, request.refresh_token)
    
    return TokenRefreshResponse(
        access_token=new_access_token,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )

