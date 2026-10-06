"""
Discussion 관련 응답 변환 Mapper
"""
from typing import List
from api.models.discussion import Discussion, Participant
from api.schemas.discussion import (
    ParticipantResponse,
    TimestampsResponse
)


class DiscussionMapper:
    """토론 관련 데이터 변환 클래스"""

    @staticmethod
    def to_participant_response(participant: Participant) -> ParticipantResponse:
        """
        Participant 모델 → ParticipantResponse 스키마 변환

        Args:
            participant: Participant 모델 인스턴스

        Returns:
            ParticipantResponse 스키마 인스턴스
        """
        return ParticipantResponse(
            id=participant.id,
            name=participant.name,
            role=participant.role,
            llm_provider=participant.llm_provider,
            model=participant.model,
            message_count=participant.message_count,
            current_openness=participant.current_openness
        )

    @staticmethod
    def to_participants_response(participants: List[Participant]) -> List[ParticipantResponse]:
        """
        Participant 리스트 → ParticipantResponse 리스트 변환

        Args:
            participants: Participant 모델 리스트

        Returns:
            ParticipantResponse 스키마 리스트
        """
        return [
            DiscussionMapper.to_participant_response(p)
            for p in participants
        ]

    @staticmethod
    def to_timestamps_response(discussion: Discussion) -> TimestampsResponse:
        """
        Discussion 모델 → TimestampsResponse 스키마 변환

        Args:
            discussion: Discussion 모델 인스턴스

        Returns:
            TimestampsResponse 스키마 인스턴스
        """
        # DiscussionService를 지연 import하여 순환 참조 방지
        from api.services.discussion_service import DiscussionService

        return TimestampsResponse(
            created_at=discussion.created_at,
            started_at=discussion.started_at,
            updated_at=discussion.updated_at,
            completed_at=discussion.completed_at,
            elapsed_seconds=DiscussionService.calculate_elapsed_seconds(discussion),
            estimated_remaining_seconds=DiscussionService.estimate_remaining_seconds(discussion),
            duration_seconds=DiscussionService.calculate_duration_seconds(discussion)
        )
