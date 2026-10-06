"""
토론 서비스 - 토론 생성·조회·시작·중지·삭제
"""
from typing import Optional, Tuple, List

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from api.models.discussion import Discussion, DiscussionStatus, Participant
from api.models.message import Message
from api.models.report import DiscussionReport
from api.runtime import registry
from api.runtime.registry import AlreadyRunningError, CapacityError
from api.schemas.discussion import CreateDiscussionRequest
from src.utils.llm_provider import LLMFactory
from src.models.personas import LLMProvider

PERSONA_FIELDS = ("name", "role", "background", "personality", "expertise", "communication_style", "beliefs")


def _error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"error": {"code": code, "message": message}})


class DiscussionService:

    @staticmethod
    def create(db: Session, request: CreateDiscussionRequest, created_by: str) -> Discussion:
        names = [p.name for p in request.personas]
        if len(set(names)) != len(names):
            raise _error(status.HTTP_400_BAD_REQUEST, "DUPLICATE_PERSONA_NAME", "페르소나 이름이 중복됩니다.")

        discussion = Discussion(
            topic=request.topic,
            description=request.description,
            language=request.language,
            status=DiscussionStatus.DRAFT,
            config={
                "max_statements": request.max_statements,
                "use_moderator": request.use_moderator,
                "enable_web_search": request.enable_web_search,
                "enable_belief_reasoning": request.enable_belief_reasoning,
            },
            created_by=created_by,
        )
        for p in request.personas:
            provider = LLMProvider(p.llm_provider) if p.llm_provider else LLMFactory.default_provider()
            discussion.participants.append(Participant(
                name=p.name,
                role=p.role,
                template_id=p.template_id,
                llm_provider=provider.value,
                model=p.model or LLMFactory._get_default_model(provider),
                persona_data=p.model_dump(include=set(PERSONA_FIELDS)),
            ))
        db.add(discussion)
        db.commit()
        db.refresh(discussion)
        return discussion

    @staticmethod
    def list(db: Session, page: int, page_size: int,
             status_filter: Optional[str] = None) -> Tuple[List[Discussion], int]:
        query = db.query(Discussion)
        if status_filter:
            query = query.filter(Discussion.status == status_filter)
        total = query.count()
        items = (query.order_by(Discussion.created_at.desc(), Discussion.id)
                 .offset((page - 1) * page_size).limit(page_size).all())
        return items, total

    @staticmethod
    def get(db: Session, discussion_id: str) -> Discussion:
        discussion = db.get(Discussion, discussion_id)
        if discussion is None:
            raise _error(status.HTTP_404_NOT_FOUND, "DISCUSSION_NOT_FOUND", "토론을 찾을 수 없습니다.")
        return discussion

    @staticmethod
    def start(db: Session, discussion_id: str) -> None:
        discussion = DiscussionService.get(db, discussion_id)
        if discussion.status != DiscussionStatus.DRAFT:
            raise _error(status.HTTP_409_CONFLICT, "INVALID_STATUS",
                         f"draft 상태의 토론만 시작할 수 있습니다. (현재: {discussion.status})")
        for p in discussion.participants:
            if not LLMFactory.get_available_providers().get(LLMProvider(p.llm_provider)):
                raise _error(status.HTTP_503_SERVICE_UNAVAILABLE, "LLM_UNAVAILABLE",
                             f"{p.llm_provider} API 키가 설정되지 않았습니다.")
        try:
            registry.start(discussion_id)
        except AlreadyRunningError:
            raise _error(status.HTTP_409_CONFLICT, "ALREADY_RUNNING", "이미 실행 중인 토론입니다.")
        except CapacityError as e:
            raise _error(status.HTTP_429_TOO_MANY_REQUESTS, "CAPACITY_EXCEEDED",
                         f"동시에 실행할 수 있는 토론 수({e.args[0]})를 초과했습니다.")

    @staticmethod
    async def stop(db: Session, discussion_id: str, by: str, reason: Optional[str]) -> None:
        DiscussionService.get(db, discussion_id)
        if not await registry.stop(discussion_id, by=by, reason=reason):
            raise _error(status.HTTP_409_CONFLICT, "NOT_RUNNING", "실행 중인 토론이 아닙니다.")

    @staticmethod
    def delete(db: Session, discussion_id: str) -> None:
        discussion = DiscussionService.get(db, discussion_id)
        if (registry.get(discussion_id) is not None or registry.report_running(discussion_id)
                or discussion.status in DiscussionStatus.ACTIVE):
            raise _error(status.HTTP_409_CONFLICT, "DISCUSSION_RUNNING", "실행 중인 토론은 삭제할 수 없습니다.")
        db.query(Message).filter(Message.discussion_id == discussion_id).delete(synchronize_session=False)
        db.query(DiscussionReport).filter(DiscussionReport.discussion_id == discussion_id).delete(synchronize_session=False)
        db.delete(discussion)
        db.commit()
