"""
종합보고서 서비스 - 조회·재생성·내보내기
"""
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from api.models.discussion import DiscussionStatus
from api.models.report import DiscussionReport, ReportStatus
from api.runtime import persistence, registry
from api.runtime.registry import AlreadyRunningError
from api.services.discussion_service import DiscussionService
from config.config_loader import config_loader
from src.services.consensus_report import to_markdown


def _error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"error": {"code": code, "message": message}})


class ReportService:

    @staticmethod
    def get(db: Session, discussion_id: str) -> DiscussionReport:
        DiscussionService.get(db, discussion_id)
        report = db.get(DiscussionReport, discussion_id)
        if report is None:
            raise _error(status.HTTP_404_NOT_FOUND, "REPORT_NOT_FOUND", "아직 생성된 보고서가 없습니다.")
        return report

    @staticmethod
    def regenerate(db: Session, discussion_id: str) -> None:
        discussion = DiscussionService.get(db, discussion_id)
        if discussion.status not in DiscussionStatus.TERMINAL:
            raise _error(status.HTTP_409_CONFLICT, "INVALID_STATUS",
                         f"종료된 토론만 보고서를 생성할 수 있습니다. (현재: {discussion.status})")
        minimum = config_loader.config.report.min_ai_messages
        if persistence.count_ai_messages(discussion_id) < minimum:
            raise _error(status.HTTP_409_CONFLICT, "INSUFFICIENT_MESSAGES",
                         f"AI 발언이 {minimum}개 이상이어야 보고서를 생성할 수 있습니다.")
        try:
            registry.start_report(discussion_id)
        except AlreadyRunningError:
            raise _error(status.HTTP_409_CONFLICT, "REPORT_RUNNING", "보고서를 생성하는 중입니다.")

    @staticmethod
    def export(db: Session, discussion_id: str, fmt: str):
        report = ReportService.get(db, discussion_id)
        if report.status != ReportStatus.READY:
            raise _error(status.HTTP_409_CONFLICT, "REPORT_NOT_READY", f"보고서 상태: {report.status}")
        return to_markdown(report.content) if fmt == "md" else report.content
