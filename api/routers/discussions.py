"""
토론 API 라우터 (조회는 모든 활성 사용자, 시작·중지·삭제는 생성자 또는 관리자)
"""
from typing import Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from api.database import get_db
from api.dependencies import require_active_user
from api.models.user import User
from api.schemas.discussion import (
    CreateDiscussionRequest,
    DiscussionListItem,
    DiscussionListResponse,
    DiscussionResponse,
    StopDiscussionRequest,
)
from api.services.discussion_service import DiscussionService

router = APIRouter(prefix="/api/v1/discussions", tags=["Discussions"])


def _with_creator(db: Session, discussion, schema):
    names = DiscussionService.creator_names(db, [discussion])
    return schema.model_validate(discussion).model_copy(update={"created_by_name": names.get(discussion.created_by)})


@router.post("", response_model=DiscussionResponse, status_code=status.HTTP_201_CREATED, summary="토론 생성 (draft)")
def create_discussion(request: CreateDiscussionRequest, db: Session = Depends(get_db),
                      user: User = Depends(require_active_user)):
    return _with_creator(db, DiscussionService.create(db, request, user), DiscussionResponse)


@router.get("", response_model=DiscussionListResponse, summary="토론 목록")
def list_discussions(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
                     status_filter: Optional[str] = Query(None, alias="status"),
                     mine: bool = Query(False, description="내가 만든 토론만"),
                     db: Session = Depends(get_db), user: User = Depends(require_active_user)):
    items, total = DiscussionService.list(db, page, page_size, status_filter, owner_id=user.id if mine else None)
    names = DiscussionService.creator_names(db, items)
    return DiscussionListResponse(
        items=[DiscussionListItem.model_validate(d).model_copy(update={"created_by_name": names.get(d.created_by)})
               for d in items],
        total=total, page=page, page_size=page_size)


@router.get("/{discussion_id}", response_model=DiscussionResponse, summary="토론 상세")
def get_discussion(discussion_id: str, db: Session = Depends(get_db), _user: User = Depends(require_active_user)):
    return _with_creator(db, DiscussionService.get(db, discussion_id), DiscussionResponse)


@router.post("/{discussion_id}/start", status_code=status.HTTP_202_ACCEPTED, summary="토론 시작")
async def start_discussion(discussion_id: str, db: Session = Depends(get_db),
                           user: User = Depends(require_active_user)):
    DiscussionService.start(db, discussion_id, user)
    return {"id": discussion_id, "status": "running"}


@router.post("/{discussion_id}/stop", summary="토론 중지")
async def stop_discussion(discussion_id: str, request: Optional[StopDiscussionRequest] = None,
                          db: Session = Depends(get_db), user: User = Depends(require_active_user)):
    await DiscussionService.stop(db, discussion_id, user, reason=request.reason if request else None)
    return {"id": discussion_id, "status": "stopped"}


@router.delete("/{discussion_id}", status_code=status.HTTP_204_NO_CONTENT, summary="토론 삭제")
def delete_discussion(discussion_id: str, db: Session = Depends(get_db), user: User = Depends(require_active_user)):
    DiscussionService.delete(db, discussion_id, user)
