"""
토론 API 라우터
"""
from typing import Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from api.database import get_db
from api.dependencies import get_actor_id
from api.schemas.discussion import (
    CreateDiscussionRequest,
    DiscussionListResponse,
    DiscussionResponse,
    StopDiscussionRequest,
)
from api.services.discussion_service import DiscussionService

router = APIRouter(prefix="/api/v1/discussions", tags=["Discussions"])


@router.post("", response_model=DiscussionResponse, status_code=status.HTTP_201_CREATED, summary="토론 생성 (draft)")
def create_discussion(request: CreateDiscussionRequest, db: Session = Depends(get_db),
                      actor_id: str = Depends(get_actor_id)):
    return DiscussionService.create(db, request, created_by=actor_id)


@router.get("", response_model=DiscussionListResponse, summary="토론 목록")
def list_discussions(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
                     status_filter: Optional[str] = Query(None, alias="status"),
                     db: Session = Depends(get_db)):
    items, total = DiscussionService.list(db, page, page_size, status_filter)
    return DiscussionListResponse(items=items, total=total, page=page, page_size=page_size)


@router.get("/{discussion_id}", response_model=DiscussionResponse, summary="토론 상세")
def get_discussion(discussion_id: str, db: Session = Depends(get_db)):
    return DiscussionService.get(db, discussion_id)


@router.post("/{discussion_id}/start", status_code=status.HTTP_202_ACCEPTED, summary="토론 시작")
async def start_discussion(discussion_id: str, db: Session = Depends(get_db)):
    DiscussionService.start(db, discussion_id)
    return {"id": discussion_id, "status": "running"}


@router.post("/{discussion_id}/stop", summary="토론 중지")
async def stop_discussion(discussion_id: str, request: Optional[StopDiscussionRequest] = None,
                          db: Session = Depends(get_db), actor_id: str = Depends(get_actor_id)):
    await DiscussionService.stop(db, discussion_id, by=actor_id, reason=request.reason if request else None)
    return {"id": discussion_id, "status": "stopped"}


@router.delete("/{discussion_id}", status_code=status.HTTP_204_NO_CONTENT, summary="토론 삭제")
def delete_discussion(discussion_id: str, db: Session = Depends(get_db)):
    DiscussionService.delete(db, discussion_id)
