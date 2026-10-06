"""
FastAPI 인증·권한 의존성

인증 수단: access_token 쿠키 (브라우저) 또는 Authorization: Bearer (스크립트)
유효 조건: 서명·만료 정상 + 사용자 status=active + token_version 일치 (정지·비밀번호 변경 시 즉시 무효)
"""
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from api.database import get_db
from api.models.user import User, UserStatus
from api.utils.auth_cookies import ACCESS_COOKIE
from api.utils.security import decode_token


def _error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"error": {"code": code, "message": message}})


def _token_from_request(request: Request) -> Optional[str]:
    token = request.cookies.get(ACCESS_COOKIE)
    if token:
        return token
    scheme, _, credentials = request.headers.get("authorization", "").partition(" ")
    return credentials if scheme.lower() == "bearer" and credentials else None


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    """로그인한 활성 사용자 (비밀번호 변경이 필요한 상태도 허용)"""
    token = _token_from_request(request)
    payload = decode_token(token, "access") if token else None
    user = db.get(User, payload["sub"]) if payload else None
    if user is None or user.status != UserStatus.ACTIVE or user.token_version != payload.get("ver"):
        raise _error(status.HTTP_401_UNAUTHORIZED, "AUTH_REQUIRED", "로그인이 필요합니다.")
    return user


def require_active_user(user: User = Depends(get_current_user)) -> User:
    """일반 기능 사용 가능 사용자 (임시 비밀번호 상태면 변경 먼저)"""
    if user.must_change_password:
        raise _error(status.HTTP_403_FORBIDDEN, "PASSWORD_CHANGE_REQUIRED", "비밀번호를 먼저 변경해야 합니다.")
    return user


def require_admin(user: User = Depends(require_active_user)) -> User:
    if not user.is_admin:
        raise _error(status.HTTP_403_FORBIDDEN, "ADMIN_REQUIRED", "관리자 권한이 필요합니다.")
    return user


def ensure_owner_or_admin(owner_id: str, user: User) -> None:
    """토론 시작·중지·삭제·보고서 재생성: 생성자 또는 관리자만"""
    if owner_id != user.id and not user.is_admin:
        raise _error(status.HTTP_403_FORBIDDEN, "FORBIDDEN", "토론 생성자 또는 관리자만 할 수 있습니다.")
