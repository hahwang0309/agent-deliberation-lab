"""
내 계정 API - 정보 수정, 비밀번호 변경
"""
from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from api.database import get_db
from api.dependencies import get_current_user, require_active_user
from api.models.user import User
from api.schemas.auth import ChangePasswordRequest, UpdateMeRequest, UserResponse
from api.services.auth_service import AuthService
from api.utils.auth_cookies import set_auth_cookies

router = APIRouter(prefix="/api/v1/users", tags=["Users"])


@router.put("/me", response_model=UserResponse, summary="내 정보 수정")
def update_me(request: UpdateMeRequest, db: Session = Depends(get_db), user: User = Depends(require_active_user)):
    return AuthService.update_me(db, user, request)


@router.put("/me/password", response_model=UserResponse,
            summary="비밀번호 변경 (임시 비밀번호 상태에서도 가능, 다른 세션은 로그아웃됨)")
def change_password(request: ChangePasswordRequest, response: Response, db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)):
    user = AuthService.change_password(db, user, request)
    set_auth_cookies(response, user)  # 토큰 버전이 바뀌었으므로 현재 세션 쿠키 재발급
    return user
