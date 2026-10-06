"""
메모리 관리자 - 모든 페르소나의 메모리를 통합 관리
"""
from typing import Dict, List, Optional, Any
from src.models.persona_memory import PersonaMemory
from api.services.persona_auto_generator import GeneratedPersona


class MemoryManager:
    """모든 페르소나의 메모리를 관리하는 중앙 관리자"""

    def __init__(self, personas: List[GeneratedPersona]):
        """
        Args:
            personas: 토론 참가 페르소나 목록
        """
        self.memories: Dict[str, PersonaMemory] = {}

        for persona in personas:
            self.memories[persona.name] = PersonaMemory(
                persona_name=persona.name,
                persona_role=persona.role
            )

    def record_statement(
        self,
        persona_name: str,
        round_num: int,
        issue: str,
        content: str,
        reasoning: str = ""
    ):
        """페르소나 발언 기록"""
        if persona_name not in self.memories:
            raise ValueError(f"Unknown persona: {persona_name}")

        self.memories[persona_name].add_my_statement(
            round_num, issue, content, reasoning
        )

    def record_interaction(
        self,
        speaker: str,
        responder: str,
        round_num: int,
        speaker_statement: str,
        responder_statement: str
    ):
        """
        두 페르소나 간 상호작용 기록

        Args:
            speaker: 발언자
            responder: 응답자
            round_num: 라운드 번호
            speaker_statement: 발언 내용
            responder_statement: 응답 내용
        """
        if speaker not in self.memories or responder not in self.memories:
            raise ValueError(f"Unknown persona: {speaker} or {responder}")

        # 동의도 계산
        agreement_level = self._calculate_agreement(
            speaker_statement, responder_statement
        )

        # 양쪽 모두 기록
        self.memories[speaker].record_interaction(
            round_num, responder, responder_statement,
            speaker_statement, agreement_level
        )

        self.memories[responder].record_interaction(
            round_num, speaker, speaker_statement,
            responder_statement, agreement_level
        )

        # 상대방에 대한 평가 업데이트
        self.memories[speaker].update_peer_impression(
            responder, agreement_rate=agreement_level
        )
        self.memories[responder].update_peer_impression(
            speaker, agreement_rate=agreement_level
        )

    def update_position(
        self,
        persona_name: str,
        issue: str,
        round_num: int,
        new_position: str,
        confidence: float,
        reasoning: str
    ):
        """페르소나의 입장 변화 기록"""
        if persona_name not in self.memories:
            raise ValueError(f"Unknown persona: {persona_name}")

        self.memories[persona_name].update_position(
            issue, round_num, new_position, confidence, reasoning
        )

    def get_context_for_persona(
        self,
        persona_name: str,
        current_issue: str,
        target_persona: Optional[str] = None
    ) -> str:
        """
        특정 페르소나의 컨텍스트 가져오기

        Args:
            persona_name: 페르소나 이름
            current_issue: 현재 논의 중인 쟁점
            target_persona: 응답 대상 페르소나 (있으면 해당 페르소나와의 상호작용 이력 포함)

        Returns:
            페르소나가 응답 시 활용할 컨텍스트 문자열
        """
        if persona_name not in self.memories:
            return ""

        return self.memories[persona_name].get_context_for_response(
            current_issue, target_persona
        )

    def _calculate_agreement(self, stmt1: str, stmt2: str) -> float:
        """
        두 발언 간 동의도 계산 (키워드 기반 간단 버전)

        Args:
            stmt1: 첫 번째 발언
            stmt2: 두 번째 발언

        Returns:
            동의도 (0.0 ~ 1.0)
        """
        # 동의 키워드
        agree_keywords = [
            '동의', '맞습니다', '같은 의견', '찬성', '옳습니다',
            '그렇습니다', '공감', '정확', '맞아', '동감'
        ]

        # 반대 키워드
        disagree_keywords = [
            '반대', '다릅니다', '아닙니다', '틀렸', '아니',
            '문제', '우려', '의문', '동의하지', '다르게'
        ]

        stmt2_lower = stmt2.lower()

        agree_count = sum(1 for kw in agree_keywords if kw in stmt2_lower)
        disagree_count = sum(1 for kw in disagree_keywords if kw in stmt2_lower)

        # 동의 키워드가 많으면 높은 점수
        if agree_count > disagree_count:
            return min(0.7 + (agree_count * 0.1), 1.0)
        # 반대 키워드가 많으면 낮은 점수
        elif disagree_count > agree_count:
            return max(0.3 - (disagree_count * 0.1), 0.0)
        else:
            # 중립
            return 0.5

    def get_memory_summary(self, persona_name: str) -> Dict[str, Any]:
        """
        페르소나의 메모리 요약

        Args:
            persona_name: 페르소나 이름

        Returns:
            메모리 요약 딕셔너리
        """
        if persona_name not in self.memories:
            return {}

        return self.memories[persona_name].get_summary()

    def get_all_summaries(self) -> Dict[str, Dict[str, Any]]:
        """모든 페르소나의 메모리 요약"""
        return {
            name: memory.get_summary()
            for name, memory in self.memories.items()
        }

    def analyze_discussion_dynamics(self) -> Dict[str, Any]:
        """
        토론 역학 분석

        Returns:
            분석 결과 딕셔너리
        """
        analysis = {
            "personas": {},
            "interaction_network": {},
            "position_stability": {}
        }

        # 페르소나별 분석
        for persona_name, memory in self.memories.items():
            analysis["personas"][persona_name] = {
                "total_statements": len(memory.my_statements),
                "interaction_count": sum(
                    len(interactions)
                    for interactions in memory.interactions.values()
                ),
                "position_changes": sum(
                    len(positions)
                    for positions in memory.position_evolution.values()
                ),
                "most_trusted_peer": self._get_most_trusted_peer(memory),
                "avg_agreement_with_others": self._calculate_avg_agreement(memory)
            }

            # 입장 안정성
            analysis["position_stability"][persona_name] = self._calculate_position_stability(memory)

        # 상호작용 네트워크
        for persona_name, memory in self.memories.items():
            for peer, interactions in memory.interactions.items():
                key = f"{persona_name}-{peer}"
                if key not in analysis["interaction_network"]:
                    avg_agreement = sum(
                        i.agreement_level for i in interactions
                    ) / len(interactions) if interactions else 0.5

                    analysis["interaction_network"][key] = {
                        "count": len(interactions),
                        "avg_agreement": avg_agreement
                    }

        return analysis

    def _calculate_position_stability(self, memory: PersonaMemory) -> float:
        """
        입장 변화의 안정성 계산

        Returns:
            안정성 점수 (0.0 ~ 1.0, 높을수록 안정적)
        """
        total_changes = sum(
            len(positions) for positions in memory.position_evolution.values()
        )

        if total_changes <= 1:
            return 1.0  # 변화 없음 = 완전히 안정적

        # 변화가 많을수록 낮은 점수
        return 1.0 / total_changes

    def _get_most_trusted_peer(self, memory: PersonaMemory) -> Optional[str]:
        """가장 신뢰하는 동료"""
        if not memory.peer_impressions:
            return None

        return max(
            memory.peer_impressions.items(),
            key=lambda x: x[1].expertise_trust
        )[0]

    def _calculate_avg_agreement(self, memory: PersonaMemory) -> float:
        """다른 사람들과의 평균 동의도"""
        if not memory.peer_impressions:
            return 0.5

        total_agreement = sum(
            impression.agreement_rate
            for impression in memory.peer_impressions.values()
        )

        return total_agreement / len(memory.peer_impressions)

    def export_memory_for_report(self) -> Dict[str, Any]:
        """보고서 생성용 메모리 데이터 추출"""
        report_data = {
            "personas": {},
            "interaction_summary": {},
            "discussion_dynamics": self.analyze_discussion_dynamics()
        }

        for persona_name, memory in self.memories.items():
            report_data["personas"][persona_name] = {
                "발언_횟수": len(memory.my_statements),
                "입장_변화": {
                    issue: [
                        {
                            "라운드": pos.round,
                            "입장": pos.position,
                            "신뢰도": f"{pos.confidence:.0%}"
                        }
                        for pos in positions
                    ]
                    for issue, positions in memory.position_evolution.items()
                },
                "핵심_논점": memory.key_takeaways,
                "동료_평가": {
                    peer: {
                        "전문성_신뢰": f"{imp.expertise_trust:.0%}",
                        "동의도": f"{imp.agreement_rate:.0%}",
                        "주요_불일치": imp.key_disagreements
                    }
                    for peer, imp in memory.peer_impressions.items()
                }
            }

        return report_data
