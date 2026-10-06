"""
권한 확인 유틸리티
"""
from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from api.models.discussion import Discussion


class PermissionChecker:
    """권한 확인 헬퍼 클래스"""

    @staticmethod
    def check_discussion_access(
        db: Session,
        discussion_id: str,
        user_id: str
    ) -> Discussion:
        """
        토론 접근 권한 확인

        Args:
            db: 데이터베이스 세션
            discussion_id: 토론 ID
            user_id: 사용자 ID

        Returns:
            Discussion 인스턴스

        Raises:
            HTTPException: 토론이 없거나 권한이 없는 경우
        """
        discussion = db.query(Discussion).filter(
            Discussion.id == discussion_id
        ).first()

        if not discussion:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "error": {
                        "code": "DISCUSSION_NOT_FOUND",
                        "message": "토론을 찾을 수 없습니다."
                    }
                }
            )

        # 게스트 모드인 경우 권한 확인 스킵
        if user_id != "guest" and discussion.created_by != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error": {
                        "code": "FORBIDDEN",
                        "message": "이 토론에 접근할 권한이 없습니다."
                    }
                }
            )

        return discussion
