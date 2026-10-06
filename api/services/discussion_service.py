"""
토론 서비스
"""
from sqlalchemy.orm import Session
from sqlalchemy import desc, asc, or_
from fastapi import HTTPException, status
from datetime import datetime, timedelta
from typing import Optional, List, Tuple
import math
import asyncio
import sys
from pathlib import Path

# src 모듈 import
BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from api.models.discussion import Discussion, Participant
from api.models.message import Message as DBMessage
from api.utils.datetime_utils import utc_now, safe_subtract
from api.models.user import User
from api.schemas.discussion import (
    CreateDiscussionRequest,
    StopDiscussionRequest,
    DiscussionConfig
)
from src.models.personas import Persona, LLMProvider
from src.discussion import create_discussion
from api.database import SessionLocal
from api.utils.event_broker import event_broker
import threading


class DiscussionService:
    """토론 관련 비즈니스 로직"""
    
    # 페르소나 템플릿 (실제로는 DB나 설정 파일에서 로드)
    PERSONA_TEMPLATES = {
        "safety_researcher": {
            "name": "Dr. Safety",
            "role": "AI Safety Researcher",
            "background": "PhD in Computer Science with focus on AI alignment and safety research",
            "personality": ["cautious", "analytical", "risk-aware"],
            "expertise": ["AI safety", "machine learning", "ethics in AI"],
            "communication_style": "precise and evidence-based",
            "beliefs": ["AI development must prioritize safety", "We should proceed cautiously with AGI"]
        },
        "tech_innovator": {
            "name": "Mr. Innovation",
            "role": "Tech CEO",
            "background": "Serial entrepreneur with multiple successful AI startups",
            "personality": ["optimistic", "visionary", "pragmatic"],
            "expertise": ["business strategy", "product development", "emerging technologies"],
            "communication_style": "inspiring and forward-thinking",
            "beliefs": ["Innovation drives progress", "Move fast and build things", "Technology can solve major challenges"]
        },
        "ethics_professor": {
            "name": "Prof. Ethics",
            "role": "Philosophy Professor",
            "background": "Philosopher specializing in ethics and technology",
            "personality": ["thoughtful", "principled", "balanced"],
            "expertise": ["moral philosophy", "technology ethics", "social impact"],
            "communication_style": "thoughtful and nuanced",
            "beliefs": ["Technology must serve humanity", "Ethical considerations are paramount", "Balance progress with responsibility"]
        },
        "policy_maker": {
            "name": "Ms. Policy",
            "role": "Policy Expert",
            "background": "Former government official with expertise in tech policy",
            "personality": ["practical", "diplomatic", "systematic"],
            "expertise": ["public policy", "regulation", "stakeholder management"],
            "communication_style": "diplomatic and systematic",
            "beliefs": ["Good policy requires diverse input", "Regulation should enable innovation while protecting society"]
        },
        "data_scientist": {
            "name": "Dr. Data",
            "role": "Data Scientist",
            "background": "Research scientist with expertise in data analysis and ML",
            "personality": ["empirical", "quantitative", "objective"],
            "expertise": ["data analysis", "statistical modeling", "machine learning"],
            "communication_style": "data-driven and objective",
            "beliefs": ["Decisions should be based on evidence", "Let the data speak", "Correlation doesn't imply causation"]
        }
    }
    
    @staticmethod
    def validate_llm_availability(provider: str, model: str) -> Tuple[bool, Optional[str]]:
        """
        LLM 사용 가능 여부 확인
        
        Args:
            provider: LLM 제공자
            model: 모델명
            
        Returns:
            (사용 가능 여부, 에러 사유)
        """
        # TODO: 실제 API 키 확인 로직 구현
        # 현재는 단순히 True 반환
        return True, None
    
    @staticmethod
    def get_concurrent_discussions_count(db: Session, user_id: str) -> int:
        """
        사용자의 진행 중인 토론 수 조회
        
        Args:
            db: 데이터베이스 세션
            user_id: 사용자 ID
            
        Returns:
            진행 중인 토론 수
        """
        return db.query(Discussion).filter(
            Discussion.created_by == user_id,
            Discussion.status.in_(["initialized", "running", "paused"])
        ).count()
    
    @staticmethod
    def create_discussion(
        db: Session,
        user: User,
        request: CreateDiscussionRequest
    ) -> Discussion:
        """
        토론 생성
        
        Args:
            db: 데이터베이스 세션
            user: 사용자
            request: 토론 생성 요청
            
        Returns:
            생성된 토론
            
        Raises:
            HTTPException: 검증 실패 시
        """
        # 참가자 수 검증
        if len(request.participants) < 2:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": {
                        "code": "INSUFFICIENT_PARTICIPANTS",
                        "message": "최소 2명 이상의 참가자가 필요합니다.",
                        "field": "participants"
                    }
                }
            )

        # 동시 토론 제한 확인 (구독 플랜별) - 게스트는 스킵
        if user.id != "guest":
            plan_limits = {
                "free": 1,
                "pro": 5,
                "enterprise": 999
            }
            max_allowed = plan_limits.get(user.subscription_plan, 1)
            current_count = DiscussionService.get_concurrent_discussions_count(db, user.id)

            if current_count >= max_allowed:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail={
                        "error": {
                            "code": "CONCURRENT_LIMIT_EXCEEDED",
                            "message": f"동시에 진행할 수 있는 토론 수를 초과했습니다. (최대 {max_allowed}개)",
                            "current_count": current_count,
                            "max_allowed": max_allowed
                        }
                    }
                )
        
        # LLM 사용 가능 여부 확인
        for participant in request.participants:
            available, reason = DiscussionService.validate_llm_availability(
                participant.llm_provider,
                participant.model
            )
            if not available:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail={
                        "error": {
                            "code": "LLM_UNAVAILABLE",
                            "message": "선택한 LLM 모델을 사용할 수 없습니다.",
                            "provider": participant.llm_provider,
                            "reason": reason or "API key not configured"
                        }
                    }
                )
        
        # 토론 생성
        discussion = Discussion(
            topic=request.topic,
            description=request.description,
            status="initialized",
            total_rounds=request.config.max_rounds,
            config=request.config.model_dump(),
            created_by=user.id
        )
        
        db.add(discussion)
        db.flush()  # ID 생성을 위해 flush
        
        # 참가자 생성
        for idx, participant_req in enumerate(request.participants):
            template = DiscussionService.PERSONA_TEMPLATES.get(
                participant_req.template_id,
                {
                    "name": f"Agent {chr(65 + idx)}",
                    "role": "Expert",
                    "background": "General expert with broad knowledge",
                    "personality": ["professional", "analytical"],
                    "expertise": ["general knowledge", "critical thinking"],
                    "communication_style": "clear and professional",
                    "beliefs": ["Evidence-based reasoning is important"]
                }
            )
            
            participant = Participant(
                discussion_id=discussion.id,
                name=template["name"],
                role=template["role"],
                template_id=participant_req.template_id,
                llm_provider=participant_req.llm_provider,
                model=participant_req.model,
                persona_data=template
            )
            db.add(participant)
        
        db.commit()
        db.refresh(discussion)
        
        return discussion
    
    @staticmethod
    def get_discussion(db: Session, discussion_id: str, user_id: str) -> Discussion:
        """
        토론 조회 (권한 확인 포함)

        Args:
            db: 데이터베이스 세션
            discussion_id: 토론 ID
            user_id: 사용자 ID

        Returns:
            토론

        Raises:
            HTTPException: 토론 없음 또는 권한 없음
        """
        from api.utils.permissions import PermissionChecker
        return PermissionChecker.check_discussion_access(db, discussion_id, user_id)
    
    @staticmethod
    def start_discussion(db: Session, discussion_id: str, user_id: str) -> Discussion:
        """
        토론 시작
        
        Args:
            db: 데이터베이스 세션
            discussion_id: 토론 ID
            user_id: 사용자 ID
            
        Returns:
            시작된 토론
            
        Raises:
            HTTPException: 이미 시작됨 등
        """
        discussion = DiscussionService.get_discussion(db, discussion_id, user_id)
        
        # 이미 시작된 토론 체크
        if discussion.status != "initialized":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": {
                        "code": "ALREADY_STARTED",
                        "message": "이미 시작된 토론입니다.",
                        "current_status": discussion.status
                    }
                }
            )
        
        # 상태 업데이트
        discussion.status = "running"
        discussion.started_at = utc_now()
        discussion.updated_at = utc_now()

        db.commit()
        db.refresh(discussion)

        # 백그라운드 스레드로 토론 실행
        thread = threading.Thread(
            target=DiscussionService._run_discussion_sync,
            args=(discussion.id,),
            daemon=True
        )
        thread.start()

        return discussion
    
    @staticmethod
    def list_discussions(
        db: Session,
        user_id: str,
        page: int = 1,
        limit: int = 20,
        status_filter: Optional[str] = None,
        sort: str = "created_at",
        order: str = "desc",
        search: Optional[str] = None
    ) -> Tuple[List[Discussion], int]:
        """
        토론 목록 조회
        
        Args:
            db: 데이터베이스 세션
            user_id: 사용자 ID
            page: 페이지 번호
            limit: 페이지당 개수
            status_filter: 상태 필터
            sort: 정렬 기준
            order: 정렬 순서
            search: 검색 키워드
            
        Returns:
            (토론 목록, 전체 개수)
        """
        # 기본 쿼리
        query = db.query(Discussion).filter(Discussion.created_by == user_id)
        
        # 상태 필터
        if status_filter:
            query = query.filter(Discussion.status == status_filter)
        
        # 검색
        if search:
            query = query.filter(Discussion.topic.ilike(f"%{search}%"))
        
        # 정렬
        sort_column = getattr(Discussion, sort, Discussion.created_at)
        if order == "asc":
            query = query.order_by(asc(sort_column))
        else:
            query = query.order_by(desc(sort_column))
        
        # 전체 개수
        total = query.count()
        
        # 페이지네이션
        offset = (page - 1) * limit
        discussions = query.offset(offset).limit(limit).all()
        
        return discussions, total
    
    @staticmethod
    def pause_discussion(db: Session, discussion_id: str, user_id: str) -> Discussion:
        """
        토론 일시정지
        
        Args:
            db: 데이터베이스 세션
            discussion_id: 토론 ID
            user_id: 사용자 ID
            
        Returns:
            일시정지된 토론
            
        Raises:
            HTTPException: 일시정지 불가능한 상태
        """
        discussion = DiscussionService.get_discussion(db, discussion_id, user_id)
        
        # running 상태가 아니면 일시정지 불가
        if discussion.status != "running":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": {
                        "code": "CANNOT_PAUSE",
                        "message": "현재 상태에서는 일시정지할 수 없습니다.",
                        "current_status": discussion.status
                    }
                }
            )
        
        discussion.status = "paused"
        discussion.paused_at = utc_now()
        discussion.updated_at = utc_now()
        
        db.commit()
        db.refresh(discussion)
        
        return discussion
    
    @staticmethod
    def resume_discussion(db: Session, discussion_id: str, user_id: str) -> Discussion:
        """
        토론 재개
        
        Args:
            db: 데이터베이스 세션
            discussion_id: 토론 ID
            user_id: 사용자 ID
            
        Returns:
            재개된 토론
            
        Raises:
            HTTPException: 일시정지 상태가 아님
        """
        discussion = DiscussionService.get_discussion(db, discussion_id, user_id)
        
        # paused 상태가 아니면 재개 불가
        if discussion.status != "paused":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": {
                        "code": "NOT_PAUSED",
                        "message": "일시정지 상태가 아닙니다.",
                        "current_status": discussion.status
                    }
                }
            )
        
        discussion.status = "running"
        discussion.resumed_at = utc_now()
        discussion.updated_at = utc_now()
        
        db.commit()
        db.refresh(discussion)
        
        return discussion
    
    @staticmethod
    def stop_discussion(
        db: Session,
        discussion_id: str,
        user_id: str,
        request: Optional[StopDiscussionRequest] = None
    ) -> Discussion:
        """
        토론 종료
        
        Args:
            db: 데이터베이스 세션
            discussion_id: 토론 ID
            user_id: 사용자 ID
            request: 종료 요청 (사유 포함)
            
        Returns:
            종료된 토론
        """
        discussion = DiscussionService.get_discussion(db, discussion_id, user_id)
        
        previous_status = discussion.status
        discussion.status = "stopped"
        discussion.stopped_at = utc_now()
        discussion.updated_at = utc_now()
        
        # TODO: 합의도 계산
        discussion.consensus_score = 0.78  # 임시값
        discussion.consensus_reached = True
        
        db.commit()
        db.refresh(discussion)
        
        return discussion
    
    @staticmethod
    def calculate_elapsed_seconds(discussion: Discussion) -> Optional[int]:
        """경과 시간 계산 (초)"""
        if not discussion.started_at:
            return None
        
        end_time = discussion.completed_at or discussion.stopped_at or utc_now()
        return int(safe_subtract(end_time, discussion.started_at))
    
    @staticmethod
    def calculate_duration_seconds(discussion: Discussion) -> Optional[int]:
        """전체 소요 시간 계산 (초)"""
        if not discussion.started_at:
            return None
        
        end_time = discussion.completed_at or discussion.stopped_at
        if not end_time:
            return None
        
        return int(safe_subtract(end_time, discussion.started_at))
    
    @staticmethod
    def estimate_remaining_seconds(discussion: Discussion) -> Optional[int]:
        """남은 시간 추정 (초)"""
        if discussion.status not in ["running", "paused"]:
            return None

        if discussion.current_round == 0:
            return discussion.total_rounds * 90  # 라운드당 약 1.5분

        elapsed = DiscussionService.calculate_elapsed_seconds(discussion)
        if not elapsed:
            return None

        avg_per_round = elapsed / discussion.current_round
        remaining_rounds = discussion.total_rounds - discussion.current_round

        return int(avg_per_round * remaining_rounds)

    @staticmethod
    def get_estimated_completion(discussion: Discussion) -> Optional[datetime]:
        """
        토론 예상 완료 시간 계산

        Args:
            discussion: Discussion 모델 인스턴스

        Returns:
            예상 완료 시간 (datetime) 또는 None
        """
        if not discussion.started_at:
            return None

        estimated_duration_seconds = discussion.total_rounds * 90  # 라운드당 90초
        return discussion.started_at + timedelta(seconds=estimated_duration_seconds)

    @staticmethod
    def get_estimated_duration_minutes(discussion: Discussion) -> int:
        """
        토론 예상 소요 시간 계산 (분 단위)

        Args:
            discussion: Discussion 모델 인스턴스

        Returns:
            예상 소요 시간 (분)
        """
        return int(discussion.total_rounds * 1.5)  # 라운드당 1.5분

    @staticmethod
    def _run_discussion_sync(discussion_id: str):
        """
        동기 래퍼 - 새 이벤트 루프에서 async 함수 실행
        """
        import asyncio
        asyncio.run(DiscussionService._run_discussion_async(discussion_id))

    @staticmethod
    async def _run_discussion_async(discussion_id: str):
        """
        비동기로 실제 토론을 실행하는 메서드

        Args:
            discussion_id: 토론 ID
        """
        # 새로운 DB 세션 생성
        db = SessionLocal()

        try:
            # 토론 정보 조회
            discussion = db.query(Discussion).filter(Discussion.id == discussion_id).first()
            if not discussion:
                return

            # 참가자 정보에서 Persona 객체 생성
            personas = []
            for participant in discussion.participants:
                persona_data = participant.persona_data
                persona = Persona(
                    name=persona_data.get("name", participant.name),
                    role=persona_data.get("role", participant.role),
                    background=persona_data.get("background", ""),
                    personality=persona_data.get("personality", []),
                    expertise=persona_data.get("expertise", []),
                    communication_style=persona_data.get("communication_style", "professional"),
                    beliefs=persona_data.get("beliefs", [])
                )
                personas.append(persona)

            # LLM 프로바이더 설정 (첫 번째 참가자 기준)
            provider_str = discussion.participants[0].llm_provider
            provider = LLMProvider(provider_str)

            # 토론 설정
            config = discussion.config or {}
            max_statements = config.get("max_rounds", discussion.total_rounds)
            use_moderator = config.get("enable_moderation", True)

            # 토론 상태를 in_progress로 변경
            discussion.status = "in_progress"
            db.commit()

            # 메시지 카운터
            message_count = 0
            current_round = 0

            # 토론 인스턴스 생성
            discussion_instance = create_discussion(
                personas=personas,
                provider=provider,
                use_moderator=use_moderator,
                enable_web_search=True,
                max_statements=max_statements
            )

            # 토론 실행 - 스트리밍 모드
            current_message_id = None
            accumulated_text = ""

            async for message in discussion_instance.run_streaming(
                topic=discussion.topic,
                max_statements=max_statements
            ):
                # Moderator 메시지 처리
                if message.agent_name == "Moderator" or message.role == "moderator":
                    # Moderator 메시지는 참가자 없이 바로 전송
                    await event_broker.publish(
                        discussion_id=discussion.id,
                        event_type="moderator_message",
                        data={
                            "speaker": "Moderator",
                            "content": message.content,
                            "type": message.metadata.get("type", "question"),
                            "timestamp": message.timestamp.isoformat() + "Z"
                        }
                    )
                    continue

                # 참가자 찾기
                participant = None
                for p in discussion.participants:
                    if p.name == message.agent_name:
                        participant = p
                        break

                if not participant:
                    continue

                # 청크 메시지 처리
                if message.metadata.get("is_chunk"):
                    # 청크를 즉시 전송
                    if not current_message_id:
                        import uuid
                        current_message_id = f"temp_{uuid.uuid4().hex[:12]}"
                        accumulated_text = ""

                    accumulated_text = message.metadata.get("accumulated_text", accumulated_text + message.content)

                    await event_broker.publish(
                        discussion_id=discussion.id,
                        event_type="message_chunk",
                        data={
                            "temp_id": current_message_id,
                            "speaker": participant.name,
                            "chunk": message.content,
                            "accumulated_text": accumulated_text,
                            "is_complete": False,
                            "timestamp": message.timestamp.isoformat() + "Z"
                        }
                    )

                # 완성된 메시지 처리
                elif message.metadata.get("is_complete"):
                    # 라운드 계산
                    message_count += 1
                    current_round = (message_count // len(discussion.participants)) + 1

                    # 메시지를 DB에 저장
                    db_message = DBMessage(
                        discussion_id=discussion.id,
                        speaker_id=participant.id,
                        speaker=participant.name,
                        content=message.content,
                        round_number=current_round,
                        message_order=message_count,
                        rag_used=message.metadata.get("rag_used", False),
                        rag_query=message.metadata.get("rag_query"),
                        rag_classification=message.metadata.get("rag_classification"),
                        sources=message.metadata.get("sources"),
                        character_count=len(message.content),
                        word_count=len(message.content.split()),
                        timestamp=message.timestamp
                    )
                    db.add(db_message)

                    # 참가자 메시지 수 업데이트
                    participant.message_count += 1

                    # 토론 진행 상황 업데이트
                    discussion.current_round = current_round
                    discussion.total_messages = message_count

                    # 즉시 커밋
                    db.commit()

                    # ★ 완성된 메시지 전송
                    await event_broker.publish(
                        discussion_id=discussion.id,
                        event_type="message_complete",
                        data={
                            "temp_id": current_message_id,
                            "message_id": db_message.id,
                            "speaker": participant.name,
                            "content": message.content,
                            "round": current_round,
                            "rag_used": message.metadata.get("rag_used", False),
                            "sources": message.metadata.get("sources"),
                            "timestamp": message.timestamp.isoformat() + "Z"
                        }
                    )

                    # 리셋
                    current_message_id = None
                    accumulated_text = ""

            # 토론 완료 후 상태 업데이트
            discussion.status = "completed"
            discussion.completed_at = utc_now()
            discussion.updated_at = utc_now()

            # TODO: 합의도 계산 (실제 로직 필요)
            discussion.consensus_score = 0.78
            discussion.consensus_reached = True

            db.commit()

            # ★ 완료 이벤트 발행
            await event_broker.publish(
                discussion_id=discussion.id,
                event_type="discussion_completed",
                data={
                    "discussion_id": discussion.id,
                    "total_rounds": discussion.current_round or 0,
                    "total_messages": message_count,
                    "consensus_reached": discussion.consensus_reached,
                    "consensus_score": discussion.consensus_score,
                    "timestamp": discussion.completed_at.isoformat() + "Z"
                }
            )

        except Exception as e:
            # 에러 발생 시 토론 상태를 failed로 변경
            print(f"[ERROR] Discussion execution failed: {e}")
            try:
                discussion = db.query(Discussion).filter(Discussion.id == discussion_id).first()
                if discussion:
                    discussion.status = "failed"
                    discussion.updated_at = utc_now()
                    db.commit()
            except:
                pass

        finally:
            # DB 세션 종료
            db.close()

