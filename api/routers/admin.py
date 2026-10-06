"""
관리자 API - 사용자 관리, 실행 현황
"""
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from api.database import get_db
from api.dependencies import require_admin
from api.models.user import User
from api.runtime import registry
from api.schemas.auth import AdminUserResponse, IssueUserRequest, TempPasswordResponse, UpdateUserRequest
from api.services.admin_service import AdminService

router = APIRouter(prefix="/api/v1/admin", tags=["Admin"], dependencies=[Depends(require_admin)])


@router.get("/users", response_model=List[AdminUserResponse], summary="사용자 목록")
def list_users(status_filter: Optional[str] = Query(None, alias="status"), db: Session = Depends(get_db)):
    return AdminService.list_users(db, status_filter)


@router.post("/users", response_model=TempPasswordResponse, status_code=201, summary="계정 발급 (임시 비밀번호)")
def issue_user(request: IssueUserRequest, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    user, temp_password = AdminService.issue_user(db, admin, request)
    return TempPasswordResponse(user=user, temp_password=temp_password)


@router.post("/users/{user_id}/reset-password", response_model=TempPasswordResponse,
             summary="비밀번호 초기화 (임시 비밀번호, 기존 세션 무효화)")
def reset_password(user_id: str, db: Session = Depends(get_db)):
    user, temp_password = AdminService.reset_password(db, user_id)
    return TempPasswordResponse(user=user, temp_password=temp_password)


@router.post("/users/{user_id}/{action}", response_model=AdminUserResponse,
             summary="승인·거절·정지·재활성화 (approve | reject | suspend | reactivate)")
def change_status(user_id: str, action: Literal["approve", "reject", "suspend", "reactivate"],
                  db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    return AdminService.transition(db, admin, user_id, action)


@router.patch("/users/{user_id}", response_model=AdminUserResponse, summary="권한·실행 제한 변경")
def update_user(user_id: str, request: UpdateUserRequest, db: Session = Depends(get_db),
                admin: User = Depends(require_admin)):
    return AdminService.update_user(db, admin, user_id, request)


@router.get("/runtime", summary="실행 중인 토론·보고서 작업")
def runtime_status():
    return {"running": registry.running_ids(), "reports": registry.report_ids(),
            "max_running": registry.max_running}
