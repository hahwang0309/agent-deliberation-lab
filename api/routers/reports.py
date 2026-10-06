"""
종합보고서 API 라우터
"""
from typing import Literal

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import JSONResponse, PlainTextResponse
from sqlalchemy.orm import Session

from api.database import get_db
from api.dependencies import require_active_user
from api.models.user import User
from api.schemas.report import ReportResponse
from api.services.report_service import ReportService

router = APIRouter(prefix="/api/v1/discussions", tags=["Reports"])
# 조회·내보내기: 모든 활성 사용자 / 재생성: 생성자 또는 관리자


@router.get("/{discussion_id}/report", response_model=ReportResponse, summary="종합보고서 조회")
def get_report(discussion_id: str, db: Session = Depends(get_db), _user: User = Depends(require_active_user)):
    return ReportService.get(db, discussion_id)


@router.post("/{discussion_id}/report", status_code=status.HTTP_202_ACCEPTED, summary="종합보고서 (재)생성")
async def regenerate_report(discussion_id: str, db: Session = Depends(get_db),
                            user: User = Depends(require_active_user)):
    ReportService.regenerate(db, discussion_id, user)
    return {"discussion_id": discussion_id, "status": "pending"}


@router.get("/{discussion_id}/report/export", summary="종합보고서 내보내기 (md | json)")
def export_report(discussion_id: str, fmt: Literal["md", "json"] = Query("md", alias="format"),
                  db: Session = Depends(get_db), _user: User = Depends(require_active_user)):
    body = ReportService.export(db, discussion_id, fmt)
    headers = {"Content-Disposition": f'attachment; filename="report_{discussion_id}.{fmt}"'}
    if fmt == "md":
        return PlainTextResponse(body, media_type="text/markdown; charset=utf-8", headers=headers)
    return JSONResponse(body, headers=headers)
