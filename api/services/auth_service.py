"""
인증·계정 서비스 - 가입 신청, 로그인, 토큰 갱신, 내 정보, 비밀번호 변경, 최초 관리자 생성
"""
import logging
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from api.config import settings
from api.models.user import User, UserRole, UserStatus
from api.schemas.auth import ChangePasswordRequest, LoginRequest, SignupRequest, UpdateMeRequest
from api.utils.security import decode_token, hash_password, password_problem, verify_password

logger = logging.getLogger(__name__)


def _error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"error": {"code": code, "message": message}})


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _naive(dt: datetime) -> datetime:
    """SQLite는 tz 정보를 저장하지 않으므로 비교 전 UTC naive로 맞춘다"""
    return dt.replace(tzinfo=None) if dt.tzinfo else dt


def validate_password(password: str, email: str) -> None:
    problem = password_problem(password, email)
    if problem:
        raise _error(status.HTTP_422_UNPROCESSABLE_ENTITY, "INVALID_PASSWORD", problem)


STATUS_ERRORS = {
    UserStatus.PENDING: ("ACCOUNT_PENDING", "관리자 승인을 기다리는 계정입니다."),
    UserStatus.SUSPENDED: ("ACCOUNT_SUSPENDED", "정지된 계정입니다. 관리자에게 문의하세요."),
    UserStatus.REJECTED: ("ACCOUNT_REJECTED", "가입 신청이 거절된 계정입니다."),
}


class AuthService:

    @staticmethod
    def signup_request(db: Session, request: SignupRequest) -> User:
        email = request.email.lower()
        if db.query(User).filter(User.email == email).first():
            raise _error(status.HTTP_409_CONFLICT, "EMAIL_EXISTS", "이미 등록된 이메일입니다.")
        validate_password(request.password, email)
        user = User(email=email, password_hash=hash_password(request.password), name=request.name,
                    organization=request.organization, signup_note=request.note,
                    role=UserRole.USER, status=UserStatus.PENDING)
        db.add(user)
        db.commit()
        db.refresh(user)
        return user

    @staticmethod
    def login(db: Session, request: LoginRequest) -> User:
        user = db.query(User).filter(User.email == request.email.lower()).first()
        now = _naive(_now())

        if user and user.login_locked_until and user.login_locked_until > now:
            retry_after = int((user.login_locked_until - now).total_seconds())
            raise _error(status.HTTP_429_TOO_MANY_REQUESTS, "TOO_MANY_ATTEMPTS",
                         f"로그인 시도 횟수를 초과했습니다. {retry_after}초 후 다시 시도하세요.")

        if not user or not verify_password(request.password, user.password_hash):
            if user:
                user.login_attempts = (user.login_attempts or 0) + 1
                if user.login_attempts >= settings.MAX_LOGIN_ATTEMPTS:
                    user.login_locked_until = now + timedelta(seconds=settings.LOGIN_ATTEMPT_TIMEOUT)
                    user.login_attempts = 0
                db.commit()
            raise _error(status.HTTP_401_UNAUTHORIZED, "INVALID_CREDENTIALS", "이메일 또는 비밀번호가 올바르지 않습니다.")

        if user.status in STATUS_ERRORS:
            code, message = STATUS_ERRORS[user.status]
            raise _error(status.HTTP_403_FORBIDDEN, code, message)

        user.login_attempts = 0
        user.login_locked_until = None
        user.last_login_at = _now()
        db.commit()
        db.refresh(user)
        return user

    @staticmethod
    def refresh(db: Session, refresh_token: str) -> User:
        payload = decode_token(refresh_token, "refresh") if refresh_token else None
        user = db.get(User, payload["sub"]) if payload else None
        if user is None or user.status != UserStatus.ACTIVE or user.token_version != payload.get("ver"):
            raise _error(status.HTTP_401_UNAUTHORIZED, "AUTH_REQUIRED", "다시 로그인해 주세요.")
        return user

    @staticmethod
    def update_me(db: Session, user: User, request: UpdateMeRequest) -> User:
        for field, value in request.model_dump(exclude_unset=True).items():
            setattr(user, field, value)
        db.commit()
        db.refresh(user)
        return user

    @staticmethod
    def change_password(db: Session, user: User, request: ChangePasswordRequest) -> User:
        if not verify_password(request.current_password, user.password_hash):
            raise _error(status.HTTP_400_BAD_REQUEST, "INVALID_PASSWORD", "현재 비밀번호가 올바르지 않습니다.")
        if request.current_password == request.new_password:
            raise _error(status.HTTP_400_BAD_REQUEST, "INVALID_PASSWORD", "새 비밀번호가 현재 비밀번호와 같습니다.")
        validate_password(request.new_password, user.email)
        user.password_hash = hash_password(request.new_password)
        user.must_change_password = False
        user.token_version += 1  # 다른 기기의 기존 세션 무효화
        db.commit()
        db.refresh(user)
        return user

    @staticmethod
    def ensure_initial_admin(db: Session) -> None:
        """관리자가 한 명도 없으면 ADMIN_EMAIL/ADMIN_INITIAL_PASSWORD로 생성 (비밀번호 변경 강제)"""
        if db.query(User).filter(User.role == UserRole.ADMIN).first():
            return
        if not (settings.ADMIN_EMAIL and settings.ADMIN_INITIAL_PASSWORD):
            logger.warning("관리자 계정이 없습니다. ADMIN_EMAIL과 ADMIN_INITIAL_PASSWORD를 설정하고 재시작하세요.")
            return
        email = settings.ADMIN_EMAIL.lower()
        user = db.query(User).filter(User.email == email).first()
        if user is None:
            user = User(email=email, name="관리자")
            db.add(user)
        user.password_hash = hash_password(settings.ADMIN_INITIAL_PASSWORD)
        user.role = UserRole.ADMIN
        user.status = UserStatus.ACTIVE
        user.must_change_password = True
        user.approved_at = _now()
        db.commit()
        logger.warning("최초 관리자 계정 생성: %s (첫 로그인 후 비밀번호 변경 필요)", email)
