"""
토론 엔드포인트
"""
from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.orm import Session
from typing import Optional, List
from datetime import datetime
import math

from api.database import get_db
from api.dependencies import get_current_user, get_optional_user
from api.models.user import User
from api.models.discussion import Discussion
from api.schemas.discussion import (
    CreateDiscussionRequest,
    CreateDiscussionResponse,
    DiscussionStatusResponse,
    DiscussionListResponse,
    DiscussionStartResponse,
    DiscussionPauseResponse,
    DiscussionResumeResponse,
    StopDiscussionRequest,
    DiscussionStopResponse,
    ParticipantResponse,
    TimestampsResponse,
    DiscussionListItem,
    PaginationResponse,
    FiltersResponse,
    DiscussionSummary,
    DiscussionConfig
)
from api.services.discussion_service import DiscussionService
from api.mappers.discussion_mapper import DiscussionMapper

router = APIRouter(prefix="/api/v1/discussions", tags=["토론"])


@router.post(
    "/guest/start",
    summary="게스트 토론 생성 + 실행 (GPT 스타일)",
    description="토론 생성부터 실시간 스트리밍까지 한 번에 처리합니다."
)
async def create_and_start_guest_discussion(
    request_data: CreateDiscussionRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    게스트 토론 생성 + 즉시 실행 (GPT 스타일)

    **Authorization 헤더 불필요**

    **Request Body:** CreateDiscussionRequest
    **Response:** Server-Sent Events (SSE) 스트림

    **이벤트 타입:**
    - `discussion_started`: 토론 시작
    - `message_chunk`: 메시지 청크 (실시간)
    - `message_complete`: 메시지 완성
    - `discussion_completed`: 토론 완료
    - `error`: 에러
    """
    from fastapi.responses import StreamingResponse
    from api.utils.event_broker import event_broker
    from api.schemas.message import SSEEvent
    import asyncio

    # 게스트 사용자 생성 (임시)
    class GuestUser:
        def __init__(self):
            self.id = "guest"
            self.name = "Guest"
            self.email = "guest@temp.com"
            self.subscription_plan = "free"

    guest_user = GuestUser()

    # 토론 생성
    discussion = DiscussionService.create_discussion(db, guest_user, request_data)
    discussion_id = discussion.id

    # 토론 시작 (백그라운드 스레드)
    discussion = DiscussionService.start_discussion(db, discussion_id, "guest")

    # SSE 이벤트 생성기
    async def event_generator():
        event_id = 0
        queue = None

        # 연결 메시지
        yield f": Connected to discussion {discussion_id}\n\n"

        try:
            # 이벤트 브로커 구독
            queue = await event_broker.subscribe(discussion_id)

            # 시작 이벤트
            event_id += 1
            start_event = SSEEvent(
                id=str(event_id),
                event="discussion_started",
                data={
                    "discussion_id": discussion_id,
                    "topic": discussion.topic,
                    "started_at": discussion.started_at.isoformat() + "Z" if discussion.started_at else None,
                    "timestamp": datetime.utcnow().isoformat() + "Z"
                }
            )
            yield start_event.to_sse()

            # 이벤트 수신 루프
            while True:
                # 클라이언트 연결 확인
                if await request.is_disconnected():
                    break

                try:
                    # 이벤트 대기 (타임아웃 30초)
                    stream_event = await asyncio.wait_for(queue.get(), timeout=30.0)

                    event_id += 1
                    sse_event = SSEEvent(
                        id=str(event_id),
                        event=stream_event.event_type,
                        data=stream_event.data
                    )
                    yield sse_event.to_sse()

                    # 토론 완료 시 종료
                    if stream_event.event_type == "discussion_completed":
                        break

                except asyncio.TimeoutError:
                    # 하트비트
                    yield ": heartbeat\n\n"
                    continue

        except asyncio.CancelledError:
            pass
        except Exception as e:
            # 에러 이벤트
            event_id += 1
            error_event = SSEEvent(
                id=str(event_id),
                event="error",
                data={
                    "code": "STREAM_ERROR",
                    "message": str(e),
                    "timestamp": datetime.utcnow().isoformat() + "Z"
                }
            )
            yield error_event.to_sse()
        finally:
            # 구독 해제
            if queue:
                await event_broker.unsubscribe(discussion_id, queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@router.get(
    "/guest/{discussion_id}/start",
    summary="게스트 토론 시작 (비로그인) - SSE 스트리밍",
    description="로그인 없이 토론을 시작하고 실시간 스트리밍으로 결과를 받습니다."
)
async def start_guest_discussion(
    discussion_id: str,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    게스트 토론 시작 + 실시간 스트리밍 (GPT 스타일)

    **Authorization 헤더 불필요**

    **응답:** Server-Sent Events (SSE) 스트림

    **이벤트 타입:**
    - `discussion_started`: 토론 시작
    - `message`: 새 메시지
    - `discussion_completed`: 토론 완료
    - `error`: 에러
    """
    from fastapi.responses import StreamingResponse
    from api.utils.event_broker import event_broker
    from api.schemas.message import SSEEvent
    import asyncio

    # 토론 시작 (백그라운드 스레드에서 실행)
    discussion = DiscussionService.start_discussion(db, discussion_id, "guest")

    # SSE 이벤트 생성기
    async def event_generator():
        event_id = 0
        queue = None

        # 연결 메시지
        yield f": Connected to discussion {discussion_id}\n\n"

        try:
            # 이벤트 브로커 구독
            queue = await event_broker.subscribe(discussion_id)

            # 시작 이벤트
            event_id += 1
            start_event = SSEEvent(
                id=str(event_id),
                event="discussion_started",
                data={
                    "discussion_id": discussion_id,
                    "started_at": discussion.started_at.isoformat() + "Z" if discussion.started_at else None,
                    "timestamp": datetime.utcnow().isoformat() + "Z"
                }
            )
            yield start_event.to_sse()

            # 이벤트 수신 루프
            while True:
                # 클라이언트 연결 확인
                if await request.is_disconnected():
                    break

                try:
                    # 이벤트 대기 (타임아웃 30초)
                    stream_event = await asyncio.wait_for(queue.get(), timeout=30.0)

                    event_id += 1
                    sse_event = SSEEvent(
                        id=str(event_id),
                        event=stream_event.event_type,
                        data=stream_event.data
                    )
                    yield sse_event.to_sse()

                    # 토론 완료 시 종료
                    if stream_event.event_type == "discussion_completed":
                        break

                except asyncio.TimeoutError:
                    # 하트비트
                    yield ": heartbeat\n\n"
                    continue

        except asyncio.CancelledError:
            pass
        except Exception as e:
            # 에러 이벤트
            event_id += 1
            error_event = SSEEvent(
                id=str(event_id),
                event="error",
                data={
                    "code": "STREAM_ERROR",
                    "message": str(e),
                    "timestamp": datetime.utcnow().isoformat() + "Z"
                }
            )
            yield error_event.to_sse()
        finally:
            # 구독 해제
            if queue:
                await event_broker.unsubscribe(discussion_id, queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@router.get(
    "/guest/{discussion_id}",
    response_model=DiscussionStatusResponse,
    status_code=status.HTTP_200_OK,
    summary="게스트 토론 상태 조회 (비로그인)",
    description="로그인 없이 토론 상태를 조회합니다."
)
def get_guest_discussion_status(
    discussion_id: str,
    db: Session = Depends(get_db)
):
    """
    게스트 토론 상태 조회 (비로그인)

    **Authorization 헤더 불필요**
    """
    discussion = DiscussionService.get_discussion(db, discussion_id, "guest")

    # 참가자 정보
    participants = DiscussionMapper.to_participants_response(discussion.participants)

    # 타임스탬프
    timestamps = DiscussionMapper.to_timestamps_response(discussion)

    return DiscussionStatusResponse(
        discussion_id=discussion.id,
        status=discussion.status,
        topic=discussion.topic,
        description=discussion.description,
        current_round=discussion.current_round,
        total_rounds=discussion.total_rounds,
        total_messages=discussion.total_messages,
        current_subtopic=discussion.current_subtopic,
        participants=participants,
        config=DiscussionConfig(**discussion.config),
        timestamps=timestamps,
        created_by=discussion.created_by,
        consensus_reached=discussion.consensus_reached,
        consensus_score=discussion.consensus_score
    )


@router.post(
    "",
    response_model=CreateDiscussionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="토론 생성 (게스트 지원)",
    description="새로운 토론을 생성합니다. 로그인 선택사항."
)
def create_discussion(
    request: CreateDiscussionRequest,
    current_user: Optional[User] = Depends(get_optional_user),
    db: Session = Depends(get_db)
):
    """
    토론 생성
    
    - **topic**: 토론 주제 (10-200자)
    - **description**: 토론 설명 (선택, 최대 1000자)
    - **participants**: 참가자 목록 (2-5명)
    - **config**: 토론 설정
    
    **Authorization 헤더 선택사항 (게스트 허용):**
    ```
    Authorization: Bearer {access_token}
    ```
    """
    # 게스트 사용자 처리
    if not current_user:
        class GuestUser:
            def __init__(self):
                self.id = "guest"
                self.name = "Guest"
                self.email = "guest@temp.com"
                self.subscription_plan = "free"
        current_user = GuestUser()
    
    discussion = DiscussionService.create_discussion(db, current_user, request)

    # 참가자 정보
    participants = DiscussionMapper.to_participants_response(discussion.participants)

    # 예상 소요 시간 계산
    estimated_duration = DiscussionService.get_estimated_duration_minutes(discussion)
    
    return CreateDiscussionResponse(
        discussion_id=discussion.id,
        status=discussion.status,
        topic=discussion.topic,
        description=discussion.description,
        participants=participants,
        config=DiscussionConfig(**discussion.config),
        created_at=discussion.created_at,
        created_by=discussion.created_by,
        stream_url=f"/api/v1/discussions/{discussion.id}/stream",
        estimated_duration_minutes=int(estimated_duration)
    )


@router.post(
    "/{discussion_id}/start",
    response_model=DiscussionStartResponse,
    status_code=status.HTTP_200_OK,
    summary="토론 시작 (게스트 지원)",
    description="토론을 시작합니다. 로그인 선택사항."
)
def start_discussion(
    discussion_id: str,
    current_user: Optional[User] = Depends(get_optional_user),
    db: Session = Depends(get_db)
):
    """
    토론 시작
    
    **Authorization 헤더 선택사항 (게스트 허용):**
    ```
    Authorization: Bearer {access_token}
    ```
    """
    user_id = current_user.id if current_user else "guest"
    discussion = DiscussionService.start_discussion(db, discussion_id, user_id)

    # 예상 완료 시간 계산
    estimated_completion = DiscussionService.get_estimated_completion(discussion)
    
    return DiscussionStartResponse(
        discussion_id=discussion.id,
        status=discussion.status,
        started_at=discussion.started_at,
        estimated_completion=estimated_completion
    )


@router.get(
    "/{discussion_id}",
    response_model=DiscussionStatusResponse,
    status_code=status.HTTP_200_OK,
    summary="토론 상태 조회 (게스트 지원)",
    description="토론의 현재 상태를 조회합니다. 로그인 선택사항."
)
def get_discussion_status(
    discussion_id: str,
    current_user: Optional[User] = Depends(get_optional_user),
    db: Session = Depends(get_db)
):
    """
    토론 상태 조회
    
    **Authorization 헤더 선택사항 (게스트 허용):**
    ```
    Authorization: Bearer {access_token}
    ```
    """
    user_id = current_user.id if current_user else "guest"
    discussion = DiscussionService.get_discussion(db, discussion_id, user_id)

    # 참가자 정보
    participants = DiscussionMapper.to_participants_response(discussion.participants)

    # 타임스탬프
    timestamps = DiscussionMapper.to_timestamps_response(discussion)
    
    return DiscussionStatusResponse(
        discussion_id=discussion.id,
        status=discussion.status,
        topic=discussion.topic,
        description=discussion.description,
        current_round=discussion.current_round,
        total_rounds=discussion.total_rounds,
        total_messages=discussion.total_messages,
        current_subtopic=discussion.current_subtopic,
        participants=participants,
        config=DiscussionConfig(**discussion.config),
        timestamps=timestamps,
        created_by=discussion.created_by,
        consensus_reached=discussion.consensus_reached,
        consensus_score=discussion.consensus_score
    )


@router.get(
    "",
    response_model=DiscussionListResponse,
    status_code=status.HTTP_200_OK,
    summary="토론 목록 조회 (게스트 지원)",
    description="사용자의 토론 목록을 조회합니다. 로그인 선택사항."
)
def list_discussions(
    page: int = Query(1, ge=1, description="페이지 번호"),
    limit: int = Query(20, ge=1, le=100, description="페이지당 개수"),
    status: Optional[str] = Query(None, description="상태 필터"),
    sort: str = Query("created_at", description="정렬 기준"),
    order: str = Query("desc", description="정렬 순서"),
    search: Optional[str] = Query(None, description="검색 키워드"),
    current_user: Optional[User] = Depends(get_optional_user),
    db: Session = Depends(get_db)
):
    """
    토론 목록 조회
    
    **Query Parameters:**
    - **page**: 페이지 번호 (기본값: 1)
    - **limit**: 페이지당 개수 (기본값: 20, 최대: 100)
    - **status**: 상태 필터 (initialized, running, paused, completed, stopped, failed)
    - **sort**: 정렬 기준 (created_at, updated_at, started_at)
    - **order**: 정렬 순서 (asc, desc)
    - **search**: 주제 검색 키워드
    
    **Authorization 헤더 선택사항 (게스트 허용):**
    ```
    Authorization: Bearer {access_token}
    ```
    """
    user_id = current_user.id if current_user else "guest"
    discussions, total = DiscussionService.list_discussions(
        db=db,
        user_id=user_id,
        page=page,
        limit=limit,
        status_filter=status,
        sort=sort,
        order=order,
        search=search
    )
    
    # 토론 목록 변환
    discussion_items = []
    for discussion in discussions:
        timestamps = DiscussionMapper.to_timestamps_response(discussion)

        discussion_items.append(
            DiscussionListItem(
                discussion_id=discussion.id,
                topic=discussion.topic,
                status=discussion.status,
                current_round=discussion.current_round,
                total_rounds=discussion.total_rounds,
                total_messages=discussion.total_messages,
                participant_count=len(discussion.participants),
                consensus_reached=discussion.consensus_reached,
                timestamps=timestamps
            )
        )
    
    # 페이지네이션
    total_pages = math.ceil(total / limit)
    pagination = PaginationResponse(
        page=page,
        limit=limit,
        total=total,
        total_pages=total_pages,
        has_next=page < total_pages,
        has_prev=page > 1
    )
    
    # 필터
    filters = FiltersResponse(
        status=status,
        sort=sort,
        order=order,
        search=search
    )
    
    return DiscussionListResponse(
        discussions=discussion_items,
        pagination=pagination,
        filters=filters
    )


@router.post(
    "/{discussion_id}/pause",
    response_model=DiscussionPauseResponse,
    status_code=status.HTTP_200_OK,
    summary="토론 일시정지 (게스트 지원)",
    description="진행 중인 토론을 일시정지합니다. 로그인 선택사항."
)
def pause_discussion(
    discussion_id: str,
    current_user: Optional[User] = Depends(get_optional_user),
    db: Session = Depends(get_db)
):
    """
    토론 일시정지
    
    **Authorization 헤더 선택사항 (게스트 허용):**
    ```
    Authorization: Bearer {access_token}
    ```
    """
    user_id = current_user.id if current_user else "guest"
    previous_status = "running"
    discussion = DiscussionService.pause_discussion(db, discussion_id, user_id)
    
    return DiscussionPauseResponse(
        discussion_id=discussion.id,
        status=discussion.status,
        previous_status=previous_status,
        paused_at=discussion.paused_at,
        current_round=discussion.current_round,
        message="토론이 일시정지되었습니다."
    )


@router.post(
    "/{discussion_id}/resume",
    response_model=DiscussionResumeResponse,
    status_code=status.HTTP_200_OK,
    summary="토론 재개 (게스트 지원)",
    description="일시정지된 토론을 재개합니다. 로그인 선택사항."
)
def resume_discussion(
    discussion_id: str,
    current_user: Optional[User] = Depends(get_optional_user),
    db: Session = Depends(get_db)
):
    """
    토론 재개
    
    **Authorization 헤더 선택사항 (게스트 허용):**
    ```
    Authorization: Bearer {access_token}
    ```
    """
    user_id = current_user.id if current_user else "guest"
    previous_status = "paused"
    discussion = DiscussionService.resume_discussion(db, discussion_id, user_id)
    
    return DiscussionResumeResponse(
        discussion_id=discussion.id,
        status=discussion.status,
        previous_status=previous_status,
        resumed_at=discussion.resumed_at,
        message="토론이 재개되었습니다."
    )


@router.post(
    "/{discussion_id}/stop",
    response_model=DiscussionStopResponse,
    status_code=status.HTTP_200_OK,
    summary="토론 종료 (게스트 지원)",
    description="토론을 종료합니다. 로그인 선택사항."
)
def stop_discussion(
    discussion_id: str,
    request: Optional[StopDiscussionRequest] = None,
    current_user: Optional[User] = Depends(get_optional_user),
    db: Session = Depends(get_db)
):
    """
    토론 종료
    
    **Authorization 헤더 선택사항 (게스트 허용):**
    ```
    Authorization: Bearer {access_token}
    ```
    """
    user_id = current_user.id if current_user else "guest"
    previous_status_query = db.query(Discussion).filter(Discussion.id == discussion_id).first()
    previous_status = previous_status_query.status if previous_status_query else "running"
    
    discussion = DiscussionService.stop_discussion(db, discussion_id, user_id, request)
    
    # 요약 정보
    duration = DiscussionService.calculate_duration_seconds(discussion) or 0
    summary = DiscussionSummary(
        total_rounds=discussion.current_round,
        total_messages=discussion.total_messages,
        duration_seconds=duration,
        consensus_reached=discussion.consensus_reached or False,
        consensus_score=discussion.consensus_score
    )
    
    return DiscussionStopResponse(
        discussion_id=discussion.id,
        status=discussion.status,
        previous_status=previous_status,
        stopped_at=discussion.stopped_at,
        summary=summary,
        message="토론이 종료되었습니다."
    )
