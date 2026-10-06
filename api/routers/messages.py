"""
메시지 및 스트리밍 엔드포인트
"""
from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime, timedelta
import asyncio
import json
import math

from api.database import get_db, SessionLocal
from api.dependencies import get_current_user, get_optional_user
from api.utils.event_broker import event_broker
from api.models.user import User
from api.models.discussion import Discussion
from api.models.message import Message as DBMessage
from api.schemas.message import (
    MessageListResponse,
    MessageListItem,
    MessageDetailResponse,
    PersonaInfo,
    MessageStatistics,
    SentimentInfo,
    SourceInfo,
    PaginationResponse,
    MessageFilters,
    SSEEvent
)
from api.services.message_service import MessageService
from api.services.discussion_service import DiscussionService

router = APIRouter(tags=["메시지 및 스트리밍"])


@router.get(
    "/api/v1/discussions/{discussion_id}/stream",
    summary="토론 실시간 스트림 (게스트 지원)",
    description="SSE를 통해 토론의 실시간 이벤트를 스트리밍합니다. 로그인 선택사항."
)
async def stream_discussion(
    discussion_id: str,
    request: Request,
    current_user: Optional[User] = Depends(get_optional_user),
    db: Session = Depends(get_db)
):
    """
    토론 실시간 스트림 (Server-Sent Events)

    **Authorization 헤더 선택사항 (게스트 허용)**
    
    **헤더:**
    ```
    Accept: text/event-stream
    Cache-Control: no-cache
    Connection: keep-alive
    ```
    
    **이벤트 타입:**
    - `discussion_started`: 토론 시작
    - `round_start`: 라운드 시작
    - `round_end`: 라운드 종료
    - `rag_search`: RAG 검색
    - `message`: 새 메시지
    - `reflection`: 성찰
    - `persona_evolved`: 페르소나 진화
    - `subtopic_change`: 소주제 변경
    - `discussion_paused`: 일시정지
    - `discussion_resumed`: 재개
    - `discussion_completed`: 완료
    - `error`: 에러
    """
    # 토론 조회 (게스트는 created_by 체크 스킵)
    user_id = current_user.id if current_user else "guest"

    # 토론 존재 확인
    discussion = db.query(Discussion).filter(Discussion.id == discussion_id).first()
    if not discussion:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "NOT_FOUND", "message": "토론을 찾을 수 없습니다."}}
        )

    # 권한 확인 (게스트가 아닌 경우만)
    if current_user and discussion.created_by != user_id and discussion.created_by != "guest":
        from fastapi import HTTPException
        raise HTTPException(
            status_code=403,
            detail={"error": {"code": "FORBIDDEN", "message": "권한이 없습니다."}}
        )
    
    async def event_generator():
        """이벤트 브로커 기반 SSE 생성기"""
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
    "/api/v1/discussions/{discussion_id}/messages",
    response_model=MessageListResponse,
    status_code=status.HTTP_200_OK,
    summary="메시지 목록 조회 (게스트 지원)",
    description="토론의 메시지 목록을 조회합니다. 로그인 선택사항."
)
def list_messages(
    discussion_id: str,
    page: int = Query(1, ge=1, description="페이지 번호"),
    limit: int = Query(50, ge=1, le=200, description="페이지당 개수"),
    speaker: Optional[str] = Query(None, description="발언자 필터"),
    round: Optional[int] = Query(None, ge=1, description="라운드 필터"),
    search: Optional[str] = Query(None, description="내용 검색"),
    rag_only: Optional[bool] = Query(None, description="RAG 사용 메시지만"),
    from_time: Optional[datetime] = Query(None, description="시작 시간"),
    to_time: Optional[datetime] = Query(None, description="종료 시간"),
    sort: str = Query("timestamp", description="정렬 기준"),
    order: str = Query("asc", description="정렬 순서"),
    current_user: Optional[User] = Depends(get_optional_user),
    db: Session = Depends(get_db)
):
    """
    메시지 목록 조회
    
    **Query Parameters:**
    - **page**: 페이지 번호 (기본값: 1)
    - **limit**: 페이지당 개수 (기본값: 50, 최대: 200)
    - **speaker**: 특정 참가자 필터
    - **round**: 특정 라운드 필터
    - **search**: 내용 검색 키워드
    - **rag_only**: RAG 사용 메시지만 (true/false)
    - **from_time**: 시작 시간 (ISO 8601)
    - **to_time**: 종료 시간 (ISO 8601)
    - **sort**: 정렬 (timestamp)
    - **order**: 순서 (asc, desc)
    
    **Authorization 헤더 선택사항 (게스트 허용):**
    ```
    Authorization: Bearer {access_token}
    ```
    """
    user_id = current_user.id if current_user else "guest"
    messages, total = MessageService.list_messages(
        db=db,
        discussion_id=discussion_id,
        user_id=user_id,
        page=page,
        limit=limit,
        speaker=speaker,
        round_filter=round,
        search=search,
        rag_only=rag_only,
        from_time=from_time,
        to_time=to_time,
        sort=sort,
        order=order
    )
    
    # 메시지 변환
    message_items = []
    for msg in messages:
        sources = None
        if msg.sources:
            try:
                # sources가 딕셔너리 리스트인 경우
                if isinstance(msg.sources, list) and all(isinstance(src, dict) for src in msg.sources):
                    sources = [SourceInfo(**src) for src in msg.sources]
            except (TypeError, ValueError):
                # 형식이 맞지 않으면 None으로
                sources = None
        
        message_items.append(
            MessageListItem(
                id=msg.id,
                speaker=msg.speaker,
                content=msg.content,
                timestamp=msg.timestamp,
                round_number=msg.round_number,
                rag_used=msg.rag_used,
                rag_query=msg.rag_query,
                sources=sources,
                character_count=msg.character_count,
                word_count=msg.word_count
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
    filters = MessageFilters(
        speaker=speaker,
        round=round,
        rag_only=rag_only,
        search=search
    )
    
    return MessageListResponse(
        discussion_id=discussion_id,
        messages=message_items,
        pagination=pagination,
        filters=filters
    )


@router.get(
    "/api/v1/discussions/{discussion_id}/messages/{message_id}",
    response_model=MessageDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="메시지 상세 조회 (게스트 지원)",
    description="특정 메시지의 상세 정보를 조회합니다. 로그인 선택사항."
)
def get_message_detail(
    discussion_id: str,
    message_id: str,
    current_user: Optional[User] = Depends(get_optional_user),
    db: Session = Depends(get_db)
):
    """
    메시지 상세 조회
    
    **Authorization 헤더 선택사항 (게스트 허용):**
    ```
    Authorization: Bearer {access_token}
    ```
    """
    user_id = current_user.id if current_user else "guest"
    message, participant = MessageService.get_message_detail(
        db=db,
        discussion_id=discussion_id,
        message_id=message_id,
        user_id=user_id
    )
    
    # 페르소나 정보
    persona_data = participant.persona_data or {}
    current_beliefs = persona_data.get("personality", ["전문적"])
    
    persona = PersonaInfo(
        name=participant.name,
        role=participant.role,
        current_beliefs=current_beliefs,
        current_openness=participant.current_openness
    )
    
    # 출처 정보
    sources = None
    if message.sources:
        try:
            # sources가 딕셔너리 리스트인 경우
            if isinstance(message.sources, list) and all(isinstance(src, dict) for src in message.sources):
                sources = [SourceInfo(**src) for src in message.sources]
        except (TypeError, ValueError):
            # 형식이 맞지 않으면 None으로
            sources = None
    
    # 통계
    statistics = MessageStatistics(
        character_count=message.character_count,
        word_count=message.word_count,
        sentence_count=message.sentence_count
    )
    
    # 감정 정보
    sentiment = None
    if message.sentiment_label:
        sentiment = SentimentInfo(
            score=message.sentiment_score or 0.0,
            label=message.sentiment_label,
            confidence=message.sentiment_confidence or 0.85
        )
    
    return MessageDetailResponse(
        id=message.id,
        discussion_id=message.discussion_id,
        speaker=message.speaker,
        persona=persona,
        content=message.content,
        timestamp=message.timestamp,
        round=message.round_number,
        rag_used=message.rag_used,
        rag_query=message.rag_query,
        rag_classification=message.rag_classification,
        sources=sources,
        statistics=statistics,
        sentiment=sentiment
    )

