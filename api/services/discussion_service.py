"""
토론 서비스 - 토론 생성·조회·시작·중지·삭제
"""
import os
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from api.models.discussion import Discussion, DiscussionStatus, Participant
from api.models.message import Message
from api.models.report import DiscussionReport
from api.models.user import User
from api.dependencies import ensure_owner_or_admin
from config.config_loader import config_loader
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
    def create(db: Session, request: CreateDiscussionRequest, user: User) -> Discussion:
        limits = config_loader.config.limits
        if (not user.is_admin and not limits.user_expensive_features
                and (request.enable_web_search or request.enable_belief_reasoning)):
            raise _error(status.HTTP_403_FORBIDDEN, "FEATURE_RESTRICTED",
                         "웹 검색·신념 추론은 관리자만 켤 수 있습니다.")
        if request.enable_web_search and not os.getenv("TAVILY_API_KEY"):
            # 키 없이 켜면 근거는 0건인데 검색 질의용 LLM 호출 비용만 발생함
            raise _error(status.HTTP_422_UNPROCESSABLE_ENTITY, "WEB_SEARCH_UNAVAILABLE",
                         "웹 검색을 쓰려면 서버에 TAVILY_API_KEY를 설정해야 합니다.")
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
            created_by=user.id,
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
    def list(db: Session, page: int, page_size: int, status_filter: Optional[str] = None,
             owner_id: Optional[str] = None) -> Tuple[List[Discussion], int]:
        query = db.query(Discussion)
        if owner_id:
            query = query.filter(Discussion.created_by == owner_id)
        if status_filter:
            query = query.filter(Discussion.status == status_filter)
        total = query.count()
        items = (query.order_by(Discussion.created_at.desc(), Discussion.id)
                 .offset((page - 1) * page_size).limit(page_size).all())
        return items, total

    @staticmethod
    def creator_names(db: Session, discussions: List[Discussion]) -> Dict[str, str]:
        ids = {d.created_by for d in discussions}
        return {u.id: u.name for u in db.query(User).filter(User.id.in_(ids))} if ids else {}

    @staticmethod
    def get(db: Session, discussion_id: str) -> Discussion:
        discussion = db.get(Discussion, discussion_id)
        if discussion is None:
            raise _error(status.HTTP_404_NOT_FOUND, "DISCUSSION_NOT_FOUND", "토론을 찾을 수 없습니다.")
        return discussion

    @staticmethod
    def start(db: Session, discussion_id: str, user: User) -> None:
        DiscussionService._launch(db, discussion_id, user, resume=False)

    @staticmethod
    def resume(db: Session, discussion_id: str, user: User) -> None:
        """서버 재시작으로 중단된(interrupted) 토론을 저장된 발언에서 이어서 진행 (일일 시작 수에는 미포함)"""
        DiscussionService._launch(db, discussion_id, user, resume=True)

    @staticmethod
    def _launch(db: Session, discussion_id: str, user: User, resume: bool) -> None:
        discussion = DiscussionService.get(db, discussion_id)
        ensure_owner_or_admin(discussion.created_by, user)
        required = DiscussionStatus.INTERRUPTED if resume else DiscussionStatus.DRAFT
        if discussion.status != required:
            action = "이어서 진행" if resume else "시작"
            raise _error(status.HTTP_409_CONFLICT, "INVALID_STATUS",
                         f"{required} 상태의 토론만 {action}할 수 있습니다. (현재: {discussion.status})")
        for p in discussion.participants:
            if not LLMFactory.get_available_providers().get(LLMProvider(p.llm_provider)):
                raise _error(status.HTTP_503_SERVICE_UNAVAILABLE, "LLM_UNAVAILABLE",
                             f"{p.llm_provider} API 키가 설정되지 않았습니다.")
        if not user.is_admin:
            DiscussionService._check_user_limits(db, discussion.created_by, user, check_daily=not resume)
        if registry.running_count() >= registry.max_running:
            raise _error(status.HTTP_429_TOO_MANY_REQUESTS, "CAPACITY_EXCEEDED",
                         f"동시에 실행할 수 있는 토론 수({registry.max_running})를 초과했습니다.")

        # 제한 계산이 즉시 반영되도록 상태·시작 시각을 먼저 기록 (런타임이 다시 갱신)
        discussion.status = DiscussionStatus.RUNNING
        if not resume:
            discussion.started_at = datetime.now(timezone.utc)
        db.commit()
        try:
            registry.start(discussion_id, resume=resume)
        except AlreadyRunningError:
            raise _error(status.HTTP_409_CONFLICT, "ALREADY_RUNNING", "이미 실행 중인 토론입니다.")
        except CapacityError as e:
            raise _error(status.HTTP_429_TOO_MANY_REQUESTS, "CAPACITY_EXCEEDED",
                         f"동시에 실행할 수 있는 토론 수({e.args[0]})를 초과했습니다.")

    @staticmethod
    def _check_user_limits(db: Session, owner_id: str, user: User, check_daily: bool = True) -> None:
        limits = config_loader.config.limits
        max_concurrent = user.max_concurrent if user.max_concurrent is not None else limits.user_max_concurrent
        daily_limit = user.daily_limit if user.daily_limit is not None else limits.user_daily_starts

        running = (db.query(Discussion)
                   .filter(Discussion.created_by == owner_id, Discussion.status.in_(DiscussionStatus.ACTIVE))
                   .count())
        if running >= max_concurrent:
            raise _error(status.HTTP_403_FORBIDDEN, "CONCURRENT_LIMIT_EXCEEDED",
                         f"동시에 실행할 수 있는 토론은 {max_concurrent}개입니다.")

        if not check_daily:
            return
        today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        started_today = (db.query(Discussion)
                         .filter(Discussion.created_by == owner_id, Discussion.started_at >= today)
                         .count())
        if started_today >= daily_limit:
            raise _error(status.HTTP_429_TOO_MANY_REQUESTS, "DAILY_LIMIT_EXCEEDED",
                         f"오늘(UTC) 시작할 수 있는 토론 {daily_limit}개를 모두 사용했습니다.")

    @staticmethod
    async def stop(db: Session, discussion_id: str, user: User, reason: Optional[str]) -> None:
        discussion = DiscussionService.get(db, discussion_id)
        ensure_owner_or_admin(discussion.created_by, user)
        if not await registry.stop(discussion_id, by=user.id, reason=reason):
            raise _error(status.HTTP_409_CONFLICT, "NOT_RUNNING", "실행 중인 토론이 아닙니다.")

    @staticmethod
    def delete(db: Session, discussion_id: str, user: User) -> None:
        discussion = DiscussionService.get(db, discussion_id)
        ensure_owner_or_admin(discussion.created_by, user)
        if (registry.get(discussion_id) is not None or registry.report_running(discussion_id)
                or discussion.status in DiscussionStatus.ACTIVE):
            raise _error(status.HTTP_409_CONFLICT, "DISCUSSION_RUNNING", "실행 중인 토론은 삭제할 수 없습니다.")
        db.query(Message).filter(Message.discussion_id == discussion_id).delete(synchronize_session=False)
        db.query(DiscussionReport).filter(DiscussionReport.discussion_id == discussion_id).delete(synchronize_session=False)
        db.delete(discussion)
        db.commit()
