"""
인증 쿠키 발급·삭제

- access_token: httpOnly, SameSite=Lax, 모든 경로 (EventSource도 쿠키로 인증)
- refresh_token: httpOnly, SameSite=Strict, /api/v1/auth 경로에만 전송
- csrf_token: JS가 읽어 X-CSRF-Token 헤더로 보내는 double-submit 토큰 (httpOnly 아님)
"""
from fastapi import Response

from api.config import settings
from api.models.user import User
from api.utils.security import create_access_token, create_refresh_token, new_csrf_token

ACCESS_COOKIE = "access_token"
REFRESH_COOKIE = "refresh_token"
CSRF_COOKIE = "csrf_token"
CSRF_HEADER = "x-csrf-token"
REFRESH_PATH = "/api/v1/auth"


def set_auth_cookies(response: Response, user: User) -> None:
    secure = settings.COOKIE_SECURE
    response.set_cookie(ACCESS_COOKIE, create_access_token(user.id, user.token_version),
                        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60, httponly=True,
                        secure=secure, samesite="lax", path="/")
    response.set_cookie(REFRESH_COOKIE, create_refresh_token(user.id, user.token_version),
                        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400, httponly=True,
                        secure=secure, samesite="strict", path=REFRESH_PATH)
    response.set_cookie(CSRF_COOKIE, new_csrf_token(),
                        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400, httponly=False,
                        secure=secure, samesite="strict", path="/")


def clear_auth_cookies(response: Response) -> None:
    response.delete_cookie(ACCESS_COOKIE, path="/")
    response.delete_cookie(REFRESH_COOKIE, path=REFRESH_PATH)
    response.delete_cookie(CSRF_COOKIE, path="/")
