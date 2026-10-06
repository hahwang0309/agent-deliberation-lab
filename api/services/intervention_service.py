"""
사람 개입 서비스 - 발언 요청·취소·제출·발언권 회수
"""
from fastapi import HTTPException
from sqlalchemy.orm import Session

from api.dependencies import ensure_owner_or_admin
from api.models.user import User
from api.runtime import registry
from api.runtime.intervention import HumanDesk, InterventionError
from api.services.discussion_service import DiscussionService


def _http(e: InterventionError) -> HTTPException:
    return HTTPException(status_code=e.status_code, detail={"error": {"code": e.code, "message": e.message}})


def _desk(db: Session, discussion_id: str) -> HumanDesk:
    DiscussionService.get(db, discussion_id)
    runtime = registry.get(discussion_id)
    if runtime is None:
        raise HTTPException(status_code=409, detail={"error": {"code": "NOT_RUNNING",
                                                               "message": "진행 중인 토론이 아닙니다."}})
    return runtime.desk


class InterventionService:

    @staticmethod
    def raise_hand(db: Session, discussion_id: str, user: User) -> dict:
        desk = _desk(db, discussion_id)
        try:
            position = desk.raise_hand(user.id, user.name)
        except InterventionError as e:
            raise _http(e)
        return {"position": position, **desk.state()}

    @staticmethod
    def cancel(db: Session, discussion_id: str, user: User) -> None:
        try:
            _desk(db, discussion_id).cancel(user.id)
        except InterventionError as e:
            raise _http(e)

    @staticmethod
    def submit(db: Session, discussion_id: str, user: User, floor_id: str, content: str) -> None:
        try:
            _desk(db, discussion_id).submit(user.id, floor_id, content)
        except InterventionError as e:
            raise _http(e)

    @staticmethod
    def revoke(db: Session, discussion_id: str, user: User) -> None:
        discussion = DiscussionService.get(db, discussion_id)
        ensure_owner_or_admin(discussion.created_by, user)
        try:
            _desk(db, discussion_id).revoke()
        except InterventionError as e:
            raise _http(e)

    @staticmethod
    def state(db: Session, discussion_id: str) -> dict:
        return _desk(db, discussion_id).state()
