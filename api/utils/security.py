"""
보안 유틸리티 - 비밀번호 해싱(bcrypt), JWT(PyJWT), 비밀번호 정책, 임시 비밀번호
"""
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
import jwt

from api.config import settings

BCRYPT_MAX_BYTES = 72
INSECURE_SECRET_MARKERS = ("your-secret-key", "change-this", "change-me")


def check_secret_key() -> None:
    """서버 시작 시 SECRET_KEY 검사 (미설정·예시값·32자 미만이면 시작 불가)"""
    key = settings.SECRET_KEY
    if len(key) < 32 or any(marker in key.lower() for marker in INSECURE_SECRET_MARKERS):
        raise RuntimeError(
            "SECRET_KEY가 설정되지 않았거나 안전하지 않습니다. .env에 32자 이상 무작위 값을 설정하세요 "
            "(예: python -c \"import secrets; print(secrets.token_urlsafe(48))\")."
        )


def password_problem(password: str, email: Optional[str] = None) -> Optional[str]:
    """비밀번호 정책 위반 사유 (문제 없으면 None)"""
    if len(password) < settings.PASSWORD_MIN_LENGTH:
        return f"비밀번호는 {settings.PASSWORD_MIN_LENGTH}자 이상이어야 합니다."
    if len(password.encode("utf-8")) > BCRYPT_MAX_BYTES:
        return f"비밀번호는 {BCRYPT_MAX_BYTES}바이트 이하여야 합니다."
    if email:
        local = email.split("@")[0].lower()
        if len(local) >= 3 and local in password.lower():
            return "비밀번호에 이메일 아이디를 포함할 수 없습니다."
    if len(set(password)) < 4:
        return "비밀번호가 너무 단순합니다."
    return None


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8")[:BCRYPT_MAX_BYTES], hashed_password.encode("utf-8"))
    except ValueError:
        return False


def generate_temp_password() -> str:
    return secrets.token_urlsafe(12)


def _encode(user_id: str, token_version: int, token_type: str, expires: timedelta) -> str:
    now = datetime.now(timezone.utc)
    payload = {"sub": user_id, "ver": token_version, "type": token_type, "iat": now, "exp": now + expires}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_access_token(user_id: str, token_version: int) -> str:
    return _encode(user_id, token_version, "access", timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))


def create_refresh_token(user_id: str, token_version: int) -> str:
    return _encode(user_id, token_version, "refresh", timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS))


def decode_token(token: str, expected_type: str) -> Optional[dict]:
    """서명·만료·종류가 맞으면 payload, 아니면 None"""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except jwt.PyJWTError:
        return None
    if payload.get("type") != expected_type or not payload.get("sub"):
        return None
    return payload


def new_csrf_token() -> str:
    return secrets.token_urlsafe(32)
