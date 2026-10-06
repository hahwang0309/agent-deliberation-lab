"""
내보내기 API 라우터
"""
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from sqlalchemy.orm import Session
from typing import Optional

from api.dependencies import get_db, get_current_user, get_optional_user
from api.models.user import User
from api.models.discussion import Discussion
from api.schemas.export import JSONExportResponse
from api.schemas.error import ErrorResponse
from api.services.export_service import ExportService


router = APIRouter(prefix="/api/v1/discussions", tags=["Export"])


@router.get(
    "/{discussion_id}/export/json",
    response_model=JSONExportResponse,
    summary="JSON 내보내기 (게스트 지원)",
    description="토론의 모든 정보를 JSON 형식으로 내보냅니다. 로그인 선택사항.",
    responses={
        200: {
            "description": "성공",
            "model": JSONExportResponse,
            "headers": {
                "Content-Disposition": {
                    "description": "파일 다운로드 헤더",
                    "schema": {"type": "string"}
                }
            }
        },
        404: {
            "description": "토론을 찾을 수 없음",
            "model": ErrorResponse
        }
    }
)
async def export_json(
    discussion_id: str,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user)
) -> Response:
    """
    토론을 JSON 형식으로 내보내기
    
    토론의 모든 정보를 포함한 JSON 파일을 생성합니다:
    - 토론 정보
    - 참가자 정보
    - 설정
    - 메시지
    - 분석 결과
    - 페르소나 진화 정보
    
    Args:
        discussion_id: 토론 ID
        db: 데이터베이스 세션
        current_user: 현재 로그인한 사용자 (선택사항)
        
    Returns:
        Response: JSON 응답 (파일 다운로드)
    """
    # 토론 존재 확인 및 권한 검증
    discussion = db.query(Discussion).filter(Discussion.id == discussion_id).first()
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
    
    # 소유자 확인 (게스트도 허용)
    user_id = current_user.id if current_user else "guest"
    if discussion.user_id != user_id and discussion.user_id != "guest":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": {
                    "code": "FORBIDDEN",
                    "message": "이 토론에 접근할 권한이 없습니다."
                }
            }
        )
    
    try:
        # JSON 생성
        json_export = ExportService.export_json(db, discussion_id)
        
        # 파일명 생성
        date_str = json_export.exported_at.strftime("%Y-%m-%d")
        filename = f"discussion-{discussion_id}-{date_str}.json"
        
        # JSON 응답 생성 (Content-Disposition 헤더 포함)
        return Response(
            content=json_export.json(ensure_ascii=False, indent=2),
            media_type="application/json",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"'
            }
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": {
                    "code": "DISCUSSION_NOT_FOUND",
                    "message": str(e)
                }
            }
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": {
                    "code": "EXPORT_ERROR",
                    "message": "내보내기 중 오류가 발생했습니다."
                }
            }
        )


@router.get(
    "/{discussion_id}/export/markdown",
    summary="Markdown 내보내기 (게스트 지원)",
    description="토론의 모든 정보를 Markdown 형식으로 내보냅니다. 로그인 선택사항.",
    responses={
        200: {
            "description": "성공",
            "content": {
                "text/markdown": {
                    "example": "# AI 규제, 혁신과 안전의 균형점은?\n\n**토론 ID**: disc_xyz789abc..."
                }
            },
            "headers": {
                "Content-Disposition": {
                    "description": "파일 다운로드 헤더",
                    "schema": {"type": "string"}
                }
            }
        },
        404: {
            "description": "토론을 찾을 수 없음",
            "model": ErrorResponse
        }
    }
)
async def export_markdown(
    discussion_id: str,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user)
) -> Response:
    """
    토론을 Markdown 형식으로 내보내기
    
    토론의 모든 정보를 읽기 쉬운 Markdown 형식으로 생성합니다:
    - 토론 개요
    - 참가자 정보 (신념 변화, 개방성 변화)
    - 토론 내용 (라운드별)
    - 통계
    - 참고 자료
    
    Args:
        discussion_id: 토론 ID
        db: 데이터베이스 세션
        current_user: 현재 로그인한 사용자 (선택사항)
        
    Returns:
        Response: Markdown 응답 (파일 다운로드)
    """
    # 토론 존재 확인 및 권한 검증
    discussion = db.query(Discussion).filter(Discussion.id == discussion_id).first()
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
    
    # 소유자 확인 (게스트도 허용)
    user_id = current_user.id if current_user else "guest"
    if discussion.user_id != user_id and discussion.user_id != "guest":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": {
                    "code": "FORBIDDEN",
                    "message": "이 토론에 접근할 권한이 없습니다."
                }
            }
        )
    
    try:
        # Markdown 생성
        markdown_content = ExportService.export_markdown(db, discussion_id)
        
        # 파일명 생성
        from datetime import datetime
        date_str = datetime.utcnow().strftime("%Y-%m-%d")
        filename = f"discussion-{discussion_id}-{date_str}.md"
        
        # Markdown 응답 생성 (Content-Disposition 헤더 포함)
        return Response(
            content=markdown_content,
            media_type="text/markdown; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"'
            }
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": {
                    "code": "DISCUSSION_NOT_FOUND",
                    "message": str(e)
                }
            }
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": {
                    "code": "EXPORT_ERROR",
                    "message": "내보내기 중 오류가 발생했습니다."
                }
            }
        )

