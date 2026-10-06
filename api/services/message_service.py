"""
메시지 서비스
"""
from sqlalchemy.orm import Session
from sqlalchemy import desc, asc, or_, and_
from fastapi import HTTPException, status
from typing import Optional, List, Tuple
from datetime import datetime
from api.models.message import Message
from api.models.discussion import Discussion, Participant
import math


class MessageService:
    """메시지 관련 비즈니스 로직"""
    
    @staticmethod
    def list_messages(
        db: Session,
        discussion_id: str,
        user_id: str,
        page: int = 1,
        limit: int = 50,
        speaker: Optional[str] = None,
        round_filter: Optional[int] = None,
        search: Optional[str] = None,
        rag_only: Optional[bool] = None,
        from_time: Optional[datetime] = None,
        to_time: Optional[datetime] = None,
        sort: str = "timestamp",
        order: str = "asc"
    ) -> Tuple[List[Message], int]:
        """
        메시지 목록 조회
        
        Args:
            db: 데이터베이스 세션
            discussion_id: 토론 ID
            user_id: 사용자 ID
            page: 페이지 번호
            limit: 페이지당 개수
            speaker: 발언자 필터
            round_filter: 라운드 필터
            search: 검색 키워드
            rag_only: RAG 사용 메시지만
            from_time: 시작 시간
            to_time: 종료 시간
            sort: 정렬 기준
            order: 정렬 순서
            
        Returns:
            (메시지 목록, 전체 개수)
        """
        # 권한 확인
        from api.utils.permissions import PermissionChecker
        discussion = PermissionChecker.check_discussion_access(db, discussion_id, user_id)
        
        # 기본 쿼리
        query = db.query(Message).filter(Message.discussion_id == discussion_id)
        
        # 필터 적용
        if speaker:
            query = query.filter(Message.speaker == speaker)
        
        if round_filter is not None:
            query = query.filter(Message.round_number == round_filter)
        
        if search:
            query = query.filter(Message.content.ilike(f"%{search}%"))
        
        if rag_only:
            query = query.filter(Message.rag_used == True)
        
        if from_time:
            query = query.filter(Message.timestamp >= from_time)
        
        if to_time:
            query = query.filter(Message.timestamp <= to_time)
        
        # 정렬
        sort_column = getattr(Message, sort, Message.timestamp)
        if order == "asc":
            query = query.order_by(asc(sort_column))
        else:
            query = query.order_by(desc(sort_column))
        
        # 전체 개수
        total = query.count()
        
        # 페이지네이션
        offset = (page - 1) * limit
        messages = query.offset(offset).limit(limit).all()
        
        return messages, total
    
    @staticmethod
    def get_message_detail(
        db: Session,
        discussion_id: str,
        message_id: str,
        user_id: str
    ) -> Tuple[Message, Participant]:
        """
        메시지 상세 조회
        
        Args:
            db: 데이터베이스 세션
            discussion_id: 토론 ID
            message_id: 메시지 ID
            user_id: 사용자 ID
            
        Returns:
            (메시지, 참가자)
        """
        # 권한 확인
        from api.utils.permissions import PermissionChecker
        discussion = PermissionChecker.check_discussion_access(db, discussion_id, user_id)
        
        # 메시지 조회
        message = db.query(Message).filter(
            Message.discussion_id == discussion_id,
            Message.id == message_id
        ).first()
        
        if not message:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "error": {
                        "code": "MESSAGE_NOT_FOUND",
                        "message": "메시지를 찾을 수 없습니다."
                    }
                }
            )
        
        # 참가자 정보
        participant = db.query(Participant).filter(
            Participant.id == message.speaker_id
        ).first()
        
        return message, participant
    
    @staticmethod
    def create_message(
        db: Session,
        discussion_id: str,
        speaker_id: str,
        speaker_name: str,
        content: str,
        round_number: int,
        message_order: int,
        rag_used: bool = False,
        rag_query: Optional[str] = None,
        rag_classification: Optional[str] = None,
        sources: Optional[List[dict]] = None
    ) -> Message:
        """
        메시지 생성
        
        Args:
            db: 데이터베이스 세션
            discussion_id: 토론 ID
            speaker_id: 발언자 ID
            speaker_name: 발언자 이름
            content: 내용
            round_number: 라운드 번호
            message_order: 메시지 순서
            rag_used: RAG 사용 여부
            rag_query: RAG 쿼리
            rag_classification: RAG 분류
            sources: 출처 목록
            
        Returns:
            생성된 메시지
        """
        # 통계 계산
        character_count = len(content)
        word_count = len(content.split())
        sentence_count = content.count('.') + content.count('!') + content.count('?')
        
        # 감정 분석 (TODO: 실제 감정 분석 로직)
        sentiment_score = 0.0
        sentiment_label = "neutral"
        sentiment_confidence = 0.85
        
        message = Message(
            discussion_id=discussion_id,
            speaker_id=speaker_id,
            speaker=speaker_name,
            content=content,
            round_number=round_number,
            message_order=message_order,
            rag_used=rag_used,
            rag_query=rag_query,
            rag_classification=rag_classification,
            sources=sources,
            character_count=character_count,
            word_count=word_count,
            sentence_count=sentence_count,
            sentiment_score=sentiment_score,
            sentiment_label=sentiment_label,
            sentiment_confidence=sentiment_confidence
        )
        
        db.add(message)
        db.commit()
        db.refresh(message)
        
        return message

