"""
인증 API - 가입 신청, 로그인/로그아웃, 토큰 갱신, 내 정보
"""
from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.orm import Session

from api.database import get_db
from api.dependencies import get_current_user
from api.models.user import User
from api.schemas.auth import LoginRequest, SignupRequest, UserResponse
from api.services.auth_service import AuthService
from api.utils.auth_cookies import REFRESH_COOKIE, clear_auth_cookies, set_auth_cookies

router = APIRouter(prefix="/api/v1/auth", tags=["Auth"])


@router.post("/signup-request", response_model=UserResponse, status_code=status.HTTP_201_CREATED,
             summary="가입 신청 (관리자 승인 후 로그인 가능)")
def signup_request(request: SignupRequest, db: Session = Depends(get_db)):
    return AuthService.signup_request(db, request)


@router.post("/login", response_model=UserResponse, summary="로그인 (인증 쿠키 발급)")
def login(request: LoginRequest, response: Response, db: Session = Depends(get_db)):
    user = AuthService.login(db, request)
    set_auth_cookies(response, user)
    return user


@router.post("/refresh", response_model=UserResponse, summary="access 토큰 갱신 (refresh 쿠키 사용)")
def refresh(request: Request, response: Response, db: Session = Depends(get_db)):
    user = AuthService.refresh(db, request.cookies.get(REFRESH_COOKIE, ""))
    set_auth_cookies(response, user)
    return user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, summary="로그아웃 (쿠키 삭제)")
def logout(response: Response):
    clear_auth_cookies(response)


@router.get("/me", response_model=UserResponse, summary="내 정보")
def me(user: User = Depends(get_current_user)):
    return user
