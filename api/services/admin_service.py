"""
관리자 서비스 - 사용자 승인·발급·정지·비밀번호 초기화·제한 설정
"""
from datetime import datetime, timezone
from typing import List, Optional, Tuple

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from api.models.user import User, UserRole, UserStatus
from api.schemas.auth import IssueUserRequest, UpdateUserRequest
from api.utils.security import generate_temp_password, hash_password


def _error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"error": {"code": code, "message": message}})


# 상태 전이: 동작 → (허용되는 현재 상태, 다음 상태)
TRANSITIONS = {
    "approve": ({UserStatus.PENDING, UserStatus.REJECTED}, UserStatus.ACTIVE),
    "reject": ({UserStatus.PENDING}, UserStatus.REJECTED),
    "suspend": ({UserStatus.ACTIVE}, UserStatus.SUSPENDED),
    "reactivate": ({UserStatus.SUSPENDED}, UserStatus.ACTIVE),
}


class AdminService:

    @staticmethod
    def list_users(db: Session, status_filter: Optional[str]) -> List[User]:
        query = db.query(User)
        if status_filter:
            query = query.filter(User.status == status_filter)
        return query.order_by(User.created_at.desc(), User.id).all()

    @staticmethod
    def get_user(db: Session, user_id: str) -> User:
        user = db.get(User, user_id)
        if user is None:
            raise _error(status.HTTP_404_NOT_FOUND, "USER_NOT_FOUND", "사용자를 찾을 수 없습니다.")
        return user

    @staticmethod
    def issue_user(db: Session, admin: User, request: IssueUserRequest) -> Tuple[User, str]:
        email = request.email.lower()
        if db.query(User).filter(User.email == email).first():
            raise _error(status.HTTP_409_CONFLICT, "EMAIL_EXISTS", "이미 등록된 이메일입니다.")
        temp_password = generate_temp_password()
        user = User(email=email, name=request.name, organization=request.organization, role=request.role,
                    status=UserStatus.ACTIVE, password_hash=hash_password(temp_password),
                    must_change_password=True, approved_by=admin.id, approved_at=datetime.now(timezone.utc))
        db.add(user)
        db.commit()
        db.refresh(user)
        return user, temp_password

    @staticmethod
    def transition(db: Session, admin: User, user_id: str, action: str) -> User:
        user = AdminService.get_user(db, user_id)
        allowed, next_status = TRANSITIONS[action]
        if user.status not in allowed:
            raise _error(status.HTTP_409_CONFLICT, "INVALID_STATUS",
                         f"현재 상태({user.status})에서는 '{action}'을(를) 할 수 없습니다.")
        if user.id == admin.id:
            raise _error(status.HTTP_400_BAD_REQUEST, "SELF_ACTION", "자기 계정의 상태는 바꿀 수 없습니다.")
        user.status = next_status
        if action == "approve":
            user.approved_by = admin.id
            user.approved_at = datetime.now(timezone.utc)
        if action == "suspend":
            user.token_version += 1  # 로그인 중인 세션 즉시 무효화
        db.commit()
        db.refresh(user)
        return user

    @staticmethod
    def reset_password(db: Session, user_id: str) -> Tuple[User, str]:
        user = AdminService.get_user(db, user_id)
        temp_password = generate_temp_password()
        user.password_hash = hash_password(temp_password)
        user.must_change_password = True
        user.token_version += 1
        user.login_attempts = 0
        user.login_locked_until = None
        db.commit()
        db.refresh(user)
        return user, temp_password

    @staticmethod
    def update_user(db: Session, admin: User, user_id: str, request: UpdateUserRequest) -> User:
        user = AdminService.get_user(db, user_id)
        if request.role is not None and request.role != user.role:
            if user.id == admin.id:
                raise _error(status.HTTP_400_BAD_REQUEST, "SELF_ACTION", "자기 권한은 바꿀 수 없습니다.")
            user.role = request.role
            user.token_version += 1
        if request.clear_limits:
            user.max_concurrent = None
            user.daily_limit = None
        else:
            if request.max_concurrent is not None:
                user.max_concurrent = request.max_concurrent
            if request.daily_limit is not None:
                user.daily_limit = request.daily_limit
        db.commit()
        db.refresh(user)
        return user
