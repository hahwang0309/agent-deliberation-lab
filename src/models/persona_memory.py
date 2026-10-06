"""
페르소나별 메모리 시스템

각 페르소나가 토론 중 기억하는 내용을 관리:
- 자신의 발언 이력
- 다른 페르소나와의 상호작용
- 쟁점별 입장 변화
- 동료 평가
"""
from typing import Dict, List, Optional, Any
from datetime import datetime
from pydantic import BaseModel, Field


class InteractionRecord(BaseModel):
    """상호작용 기록"""
    round: int
    their_point: str  # 상대방 발언 (요약)
    my_response: str  # 내 응답 (요약)
    agreement_level: float  # 0.0 ~ 1.0
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class PositionRecord(BaseModel):
    """입장 기록"""
    round: int
    position: str  # "중복", "비중복", "부분중복" 등
    confidence: float  # 0.0 ~ 1.0
    reasoning: str  # 근거


class PeerImpression(BaseModel):
    """동료에 대한 인상"""
    expertise_trust: float = 0.5  # 전문성 신뢰도
    agreement_rate: float = 0.5  # 의견 일치도
    key_disagreements: List[str] = Field(default_factory=list)  # 주요 불일치 사항


class MemoryItem(BaseModel):
    """메모리 아이템"""
    type: str  # "my_statement", "interaction", "position_change"
    round: int
    content: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


class PersonaMemory:
    """페르소나의 개인 메모리 - 토론 중 누적되는 기억"""

    def __init__(self, persona_name: str, persona_role: str):
        self.persona_name = persona_name
        self.persona_role = persona_role

        # 1) 자신의 발언 이력
        self.my_statements: List[Dict[str, Any]] = []

        # 2) 다른 페르소나와의 상호작용 기록
        self.interactions: Dict[str, List[InteractionRecord]] = {}

        # 3) 쟁점별 입장 변화
        self.position_evolution: Dict[str, List[PositionRecord]] = {}

        # 4) 핵심 논점 요약
        self.key_takeaways: List[str] = []

        # 5) 다른 페르소나에 대한 평가
        self.peer_impressions: Dict[str, PeerImpression] = {}

        # 6) 단기/장기 메모리 구분
        self.short_term_memory: List[MemoryItem] = []  # 최근 3-5개 발언
        self.long_term_memory: List[MemoryItem] = []   # 중요 발언만 요약

    def add_my_statement(self, round_num: int, issue: str, content: str, reasoning: str = ""):
        """자신의 발언 기록"""
        self.my_statements.append({
            "round": round_num,
            "issue": issue,
            "content": content,
            "reasoning": reasoning,
            "timestamp": datetime.utcnow()
        })

        # 단기 메모리 업데이트
        self.short_term_memory.append(MemoryItem(
            type="my_statement",
            round=round_num,
            content=content[:200],
            metadata={"issue": issue}
        ))

        # 단기 메모리 크기 제한 (최근 5개)
        if len(self.short_term_memory) > 5:
            old_memory = self.short_term_memory.pop(0)
            self._archive_to_long_term(old_memory)

    def record_interaction(
        self,
        round_num: int,
        other_persona: str,
        their_statement: str,
        my_response: str,
        agreement_level: float
    ):
        """다른 페르소나와의 상호작용 기록"""
        if other_persona not in self.interactions:
            self.interactions[other_persona] = []

        interaction = InteractionRecord(
            round=round_num,
            their_point=their_statement[:300],
            my_response=my_response[:300],
            agreement_level=agreement_level
        )

        self.interactions[other_persona].append(interaction)

        # 단기 메모리 업데이트
        self.short_term_memory.append(MemoryItem(
            type="interaction",
            round=round_num,
            content=f"{other_persona}와 대화: 동의도 {agreement_level:.0%}",
            metadata={
                "peer": other_persona,
                "agreement": agreement_level
            }
        ))

        # 크기 제한
        if len(self.short_term_memory) > 5:
            old_memory = self.short_term_memory.pop(0)
            self._archive_to_long_term(old_memory)

    def update_position(
        self,
        issue: str,
        round_num: int,
        new_position: str,
        confidence: float,
        reasoning: str
    ):
        """쟁점별 입장 변화 기록"""
        if issue not in self.position_evolution:
            self.position_evolution[issue] = []

        position_record = PositionRecord(
            round=round_num,
            position=new_position,
            confidence=confidence,
            reasoning=reasoning
        )

        self.position_evolution[issue].append(position_record)

        # 입장 변화는 중요하므로 바로 장기 메모리에 추가
        self.long_term_memory.append(MemoryItem(
            type="position_change",
            round=round_num,
            content=f"{issue}: {new_position} (신뢰도 {confidence:.0%})",
            metadata={
                "issue": issue,
                "position": new_position,
                "confidence": confidence
            }
        ))

    def update_peer_impression(
        self,
        peer_name: str,
        expertise_trust: Optional[float] = None,
        agreement_rate: Optional[float] = None,
        new_disagreement: Optional[str] = None
    ):
        """다른 페르소나에 대한 평가 업데이트"""
        if peer_name not in self.peer_impressions:
            self.peer_impressions[peer_name] = PeerImpression()

        impression = self.peer_impressions[peer_name]

        if expertise_trust is not None:
            impression.expertise_trust = expertise_trust

        if agreement_rate is not None:
            impression.agreement_rate = agreement_rate

        if new_disagreement:
            impression.key_disagreements.append(new_disagreement)

    def get_context_for_response(
        self,
        current_issue: str,
        target_persona: Optional[str] = None,
        max_context_length: int = 500
    ) -> str:
        """응답 생성 시 활용할 컨텍스트 정리"""
        context_parts = []

        # 1) 현재 쟁점에 대한 내 입장 이력
        if current_issue in self.position_evolution:
            positions = self.position_evolution[current_issue]
            if positions:
                last_pos = positions[-1]
                context_parts.append(
                    f"<내 이전 입장> {last_pos.position} (신뢰도: {last_pos.confidence:.0%})"
                )

                # 입장 변화가 있었다면
                if len(positions) > 1:
                    prev_pos = positions[-2]
                    if prev_pos.position != last_pos.position:
                        context_parts.append(
                            f"  ※ 이전에는 '{prev_pos.position}'였으나 입장 변경됨"
                        )

        # 2) 특정 페르소나와의 과거 대화
        if target_persona and target_persona in self.interactions:
            past_interactions = self.interactions[target_persona][-2:]  # 최근 2개
            if past_interactions:
                context_parts.append(f"\n<{target_persona}와의 과거 대화>")
                for interaction in past_interactions:
                    context_parts.append(
                        f"- 라운드 {interaction.round}: "
                        f"동의도 {interaction.agreement_level:.0%}"
                    )

                # 상대방에 대한 인상
                if target_persona in self.peer_impressions:
                    impression = self.peer_impressions[target_persona]
                    context_parts.append(
                        f"  (전문성 신뢰: {impression.expertise_trust:.0%}, "
                        f"전체 동의도: {impression.agreement_rate:.0%})"
                    )

        # 3) 단기 메모리 (최근 기억)
        if self.short_term_memory:
            context_parts.append("\n<최근 기억>")
            for mem in self.short_term_memory[-3:]:
                if mem.type == 'my_statement':
                    context_parts.append(
                        f"- 라운드 {mem.round}: 내가 '{mem.content[:100]}...'"
                    )
                elif mem.type == 'interaction':
                    context_parts.append(
                        f"- 라운드 {mem.round}: {mem.content}"
                    )

        # 4) 핵심 논점 (장기 메모리)
        if self.key_takeaways:
            context_parts.append("\n<핵심 논점 (내 관점)>")
            for takeaway in self.key_takeaways[-3:]:
                context_parts.append(f"- {takeaway}")

        # 컨텍스트 길이 제한
        full_context = "\n".join(context_parts)
        if len(full_context) > max_context_length:
            # 중요한 부분만 남기기 (입장 + 최근 기억)
            important_parts = [context_parts[0]] if context_parts else []
            if len(context_parts) > 2:
                important_parts.extend(context_parts[-2:])
            full_context = "\n".join(important_parts)

        return full_context

    def _archive_to_long_term(self, short_memory: MemoryItem):
        """단기 메모리를 장기 메모리로 이동"""
        # 중요도 판단 (간단 버전 - 실제로는 더 정교한 로직 가능)
        is_important = False

        if short_memory.type == 'interaction':
            # 강한 동의/반대만 장기 메모리에 보관
            agreement = short_memory.metadata.get('agreement', 0.5)
            if agreement >= 0.8 or agreement <= 0.2:
                is_important = True

        if is_important:
            self.long_term_memory.append(short_memory)

        # 장기 메모리도 크기 제한
        if len(self.long_term_memory) > 10:
            self.long_term_memory.pop(0)

    def extract_key_takeaway(self, content: str):
        """핵심 논점 추출"""
        # 간단한 버전: 직접 추가 (나중에 LLM으로 요약 가능)
        if content:
            self.key_takeaways.append(content[:150])

        # 크기 제한
        if len(self.key_takeaways) > 5:
            self.key_takeaways.pop(0)

    def get_summary(self) -> Dict[str, Any]:
        """메모리 요약"""
        return {
            "persona": self.persona_name,
            "total_statements": len(self.my_statements),
            "interactions_count": sum(len(v) for v in self.interactions.values()),
            "position_changes": {
                issue: len(positions)
                for issue, positions in self.position_evolution.items()
            },
            "peer_trust": {
                name: impression.expertise_trust
                for name, impression in self.peer_impressions.items()
            },
            "key_takeaways": self.key_takeaways
        }
