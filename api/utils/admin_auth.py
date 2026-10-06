"""
관리자 HTTP Basic 인증 미들웨어
관리자 1인 전용 시스템이므로 API·프론트엔드·SSE 전체를 단일 계정으로 보호
"""
import base64
import binascii
import secrets
from typing import Iterable


class AdminBasicAuthMiddleware:
    """모든 HTTP 요청에 관리자 Basic 인증을 요구하는 ASGI 미들웨어 (SSE 스트리밍 호환)"""

    def __init__(self, app, username: str, password: str, exempt_paths: Iterable[str] = ()):
        self.app = app
        self.username = username.encode("utf-8")
        self.password = password.encode("utf-8")
        self.exempt_paths = set(exempt_paths)

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["path"] in self.exempt_paths:
            await self.app(scope, receive, send)
            return

        if self._is_authorized(scope):
            await self.app(scope, receive, send)
            return

        await send({
            "type": "http.response.start",
            "status": 401,
            "headers": [
                (b"www-authenticate", b'Basic realm="admin", charset="UTF-8"'),
                (b"content-type", b"application/json"),
            ],
        })
        await send({
            "type": "http.response.body",
            "body": b'{"error":{"code":"UNAUTHORIZED","message":"admin authentication required"}}',
        })

    def _is_authorized(self, scope) -> bool:
        header = dict(scope["headers"]).get(b"authorization", b"")
        scheme, _, encoded = header.partition(b" ")
        if scheme.lower() != b"basic":
            return False
        try:
            decoded = base64.b64decode(encoded.strip(), validate=True)
        except (binascii.Error, ValueError):
            return False
        username, sep, password = decoded.partition(b":")
        if not sep:
            return False
        # 타이밍 공격 방지: 두 비교를 모두 수행
        user_ok = secrets.compare_digest(username, self.username)
        pass_ok = secrets.compare_digest(password, self.password)
        return user_ok and pass_ok
