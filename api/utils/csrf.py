"""
CSRF 방어 미들웨어 (double-submit cookie + Origin 검사)

쿠키로 인증하는 상태 변경 요청(POST/PUT/PATCH/DELETE)은 X-CSRF-Token 헤더가 csrf_token 쿠키와 같아야 한다.
Bearer 헤더로 인증하는 요청(스크립트·테스트)은 쿠키가 없으므로 검사 대상이 아니다.
"""
import json
import secrets
from http.cookies import SimpleCookie
from typing import Iterable
from urllib.parse import urlparse

from api.utils.auth_cookies import ACCESS_COOKIE, CSRF_COOKIE, CSRF_HEADER, REFRESH_COOKIE

UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


class CSRFMiddleware:
    def __init__(self, app, exempt_paths: Iterable[str] = ()):
        self.app = app
        self.exempt_paths = set(exempt_paths)

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope["method"] in UNSAFE_METHODS and scope["path"] not in self.exempt_paths:
            error = self._check(scope)
            if error:
                await self._reject(send, error)
                return
        await self.app(scope, receive, send)

    @staticmethod
    def _check(scope):
        headers = {k.decode("latin-1"): v.decode("latin-1") for k, v in scope["headers"]}
        cookie = SimpleCookie()
        cookie.load(headers.get("cookie", ""))
        if ACCESS_COOKIE not in cookie and REFRESH_COOKIE not in cookie:
            return None  # 쿠키 인증이 아님

        origin = headers.get("origin")
        if origin and urlparse(origin).netloc != headers.get("host"):
            return "요청 출처(Origin)가 일치하지 않습니다."

        expected = cookie[CSRF_COOKIE].value if CSRF_COOKIE in cookie else ""
        provided = headers.get(CSRF_HEADER, "")
        if not expected or not secrets.compare_digest(expected, provided):
            return "CSRF 토큰이 없거나 일치하지 않습니다."
        return None

    @staticmethod
    async def _reject(send, message: str):
        body = json.dumps({"detail": {"error": {"code": "CSRF_FAILED", "message": message}}},
                          ensure_ascii=False).encode("utf-8")
        await send({"type": "http.response.start", "status": 403,
                    "headers": [(b"content-type", b"application/json")]})
        await send({"type": "http.response.body", "body": body})
