"""
사람 개입 API (공동 참여: 모든 활성 사용자가 발언 요청 가능, 발언권 회수는 생성자·관리자)
"""
from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from api.database import get_db
from api.dependencies import require_active_user
from api.models.user import User
from api.services.intervention_service import InterventionService

router = APIRouter(prefix="/api/v1/discussions", tags=["Interventions"])


class SpeechRequest(BaseModel):
    floor_id: str = Field(..., min_length=1, max_length=64)
    content: str = Field(..., min_length=1, max_length=5000)  # 실제 상한은 config limits.max_human_chars


@router.get("/{discussion_id}/hand", summary="발언 대기열·발언권 현황")
def hand_state(discussion_id: str, db: Session = Depends(get_db), _user: User = Depends(require_active_user)):
    return InterventionService.state(db, discussion_id)


@router.post("/{discussion_id}/hand", summary="발언 요청 (진행 중인 발화가 끝나면 차례대로 발언권)")
def raise_hand(discussion_id: str, db: Session = Depends(get_db), user: User = Depends(require_active_user)):
    return InterventionService.raise_hand(db, discussion_id, user)


@router.delete("/{discussion_id}/hand", status_code=status.HTTP_204_NO_CONTENT, summary="발언 요청 취소·발언권 포기")
def cancel_hand(discussion_id: str, db: Session = Depends(get_db), user: User = Depends(require_active_user)):
    InterventionService.cancel(db, discussion_id, user)


@router.post("/{discussion_id}/speech", status_code=status.HTTP_202_ACCEPTED, summary="발언 제출 (발언권 보유자)")
def submit_speech(discussion_id: str, request: SpeechRequest, db: Session = Depends(get_db),
                  user: User = Depends(require_active_user)):
    InterventionService.submit(db, discussion_id, user, request.floor_id, request.content)
    return {"status": "accepted"}


@router.post("/{discussion_id}/floor/revoke", status_code=status.HTTP_204_NO_CONTENT,
             summary="발언권 회수 (생성자·관리자)")
def revoke_floor(discussion_id: str, db: Session = Depends(get_db), user: User = Depends(require_active_user)):
    InterventionService.revoke(db, discussion_id, user)
