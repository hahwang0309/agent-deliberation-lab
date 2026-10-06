"""
토론 합의점과 차이점 추적 시스템
"""
from typing import List, Dict, Set, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class AgreementLevel(Enum):
    """합의 수준"""
    FULL_CONSENSUS = "완전 합의"
    PARTIAL_AGREEMENT = "부분 합의"
    ACKNOWLEDGED_DIFFERENCE = "인정된 차이"
    FUNDAMENTAL_DISAGREEMENT = "근본적 불일치"
    UNRESOLVED = "미해결"


@dataclass
class ConsensusPoint:
    """합의점"""
    topic: str
    content: str
    agreed_by: Set[str]  # 동의한 에이전트들
    level: AgreementLevel
    timestamp: datetime = field(default_factory=datetime.now)
    evidence: List[str] = field(default_factory=list)  # 근거
    
    def add_agreement(self, agent_name: str, evidence: Optional[str] = None):
        """에이전트 동의 추가"""
        self.agreed_by.add(agent_name)
        if evidence:
            self.evidence.append(f"{agent_name}: {evidence}")


@dataclass
class DisagreementPoint:
    """차이점"""
    topic: str
    issue: str
    positions: Dict[str, str]  # {agent_name: position}
    underlying_assumptions: Dict[str, List[str]]  # {agent_name: [assumptions]}
    level: AgreementLevel
    timestamp: datetime = field(default_factory=datetime.now)
    fact_checkable: bool = False  # 팩트체크 가능 여부
    fact_check_queries: List[str] = field(default_factory=list)  # 팩트체크용 쿼리
    
    def add_position(self, agent_name: str, position: str, assumptions: Optional[List[str]] = None):
        """에이전트 입장 추가"""
        self.positions[agent_name] = position
        if assumptions:
            self.underlying_assumptions[agent_name] = assumptions


class ConsensusTracker:
    """토론 합의/차이 추적기"""
    
    def __init__(self):
        self.consensus_points: List[ConsensusPoint] = []
        self.disagreement_points: List[DisagreementPoint] = []
        self.topic_evolution: Dict[str, List[Tuple[datetime, str]]] = {}  # 주제별 진화 추적
        self.agent_positions: Dict[str, Dict[str, str]] = {}  # {agent: {topic: position}}
        
    def track_statement(self, agent_name: str, statement: str, topic: str) -> None:
        """발언 추적 및 분석"""
        # 합의 표현 감지
        agreement_phrases = [
            "동의합니다", "맞습니다", "agree", "correct", "그렇습니다",
            "같은 의견", "동감", "indeed", "absolutely", "확실히"
        ]
        
        # 부분 합의 표현
        partial_phrases = [
            "부분적으로", "어느 정도", "partially", "to some extent",
            "일리가 있지만", "맞는 부분도 있지만"
        ]
        
        # 불일치 표현
        disagreement_phrases = [
            "동의할 수 없", "반대", "disagree", "however", "그러나",
            "하지만", "문제는", "오히려", "contrary"
        ]
        
        # 인정 표현 (차이를 인정)
        acknowledgment_phrases = [
            "관점의 차이", "입장 차이", "different perspective",
            "각자의 입장", "서로 다른 전제"
        ]
        
        statement_lower = statement.lower()
        
        # 합의 수준 판단
        if any(phrase in statement_lower for phrase in agreement_phrases):
            self._process_agreement(agent_name, statement, topic, AgreementLevel.FULL_CONSENSUS)
        elif any(phrase in statement_lower for phrase in partial_phrases):
            self._process_agreement(agent_name, statement, topic, AgreementLevel.PARTIAL_AGREEMENT)
        elif any(phrase in statement_lower for phrase in acknowledgment_phrases):
            self._process_acknowledged_difference(agent_name, statement, topic)
        elif any(phrase in statement_lower for phrase in disagreement_phrases):
            self._process_disagreement(agent_name, statement, topic)
            
        # 에이전트 입장 업데이트
        if agent_name not in self.agent_positions:
            self.agent_positions[agent_name] = {}
        self.agent_positions[agent_name][topic] = statement[:200]  # 요약 저장
    
    def _process_agreement(self, agent_name: str, statement: str, topic: str, level: AgreementLevel):
        """합의 처리"""
        # 기존 합의점 찾기 또는 새로 생성
        for consensus in self.consensus_points:
            if consensus.topic == topic and level == consensus.level:
                consensus.add_agreement(agent_name, statement[:100])
                return
                
        # 새 합의점 생성
        new_consensus = ConsensusPoint(
            topic=topic,
            content=statement[:200],
            agreed_by={agent_name},
            level=level
        )
        self.consensus_points.append(new_consensus)
    
    def _process_disagreement(self, agent_name: str, statement: str, topic: str):
        """불일치 처리"""
        # 전제/가정 추출 (간단한 휴리스틱)
        assumption_keywords = ["assuming", "based on", "premise", "전제", "가정", "바탕으로"]
        assumptions = []
        
        for keyword in assumption_keywords:
            if keyword in statement.lower():
                # 키워드 주변 텍스트 추출
                idx = statement.lower().index(keyword)
                assumption_text = statement[idx:min(idx+100, len(statement))]
                assumptions.append(assumption_text)
        
        # 기존 불일치점 찾기 또는 새로 생성
        for disagreement in self.disagreement_points:
            if disagreement.topic == topic:
                disagreement.add_position(agent_name, statement[:200], assumptions)
                return
                
        # 새 불일치점 생성
        new_disagreement = DisagreementPoint(
            topic=topic,
            issue=f"Different views on {topic}",
            positions={agent_name: statement[:200]},
            underlying_assumptions={agent_name: assumptions} if assumptions else {},
            level=AgreementLevel.FUNDAMENTAL_DISAGREEMENT
        )
        
        # 팩트체크 가능 여부 판단
        fact_keywords = ["data", "statistics", "research", "study", "숫자", "통계", "연구"]
        if any(keyword in statement.lower() for keyword in fact_keywords):
            new_disagreement.fact_checkable = True
            new_disagreement.fact_check_queries.append(f"verify: {statement[:100]}")
            
        self.disagreement_points.append(new_disagreement)
    
    def _process_acknowledged_difference(self, agent_name: str, statement: str, topic: str):
        """인정된 차이 처리"""
        for disagreement in self.disagreement_points:
            if disagreement.topic == topic:
                disagreement.level = AgreementLevel.ACKNOWLEDGED_DIFFERENCE
                disagreement.add_position(agent_name, f"Acknowledges difference: {statement[:100]}", [])
                return
                
        # 새로 생성
        new_disagreement = DisagreementPoint(
            topic=topic,
            issue=f"Acknowledged differences on {topic}",
            positions={agent_name: statement[:200]},
            underlying_assumptions={},
            level=AgreementLevel.ACKNOWLEDGED_DIFFERENCE
        )
        self.disagreement_points.append(new_disagreement)
    
    def get_consensus_summary(self) -> Dict[str, any]:
        """합의 요약"""
        total_agents = len(self.agent_positions)
        
        # 완전 합의 (모든 에이전트가 동의)
        full_consensus = [
            cp for cp in self.consensus_points 
            if cp.level == AgreementLevel.FULL_CONSENSUS and len(cp.agreed_by) >= total_agents - 1
        ]
        
        # 부분 합의
        partial_consensus = [
            cp for cp in self.consensus_points 
            if cp.level == AgreementLevel.PARTIAL_AGREEMENT
        ]
        
        # 근본적 차이
        fundamental_differences = [
            dp for dp in self.disagreement_points 
            if dp.level == AgreementLevel.FUNDAMENTAL_DISAGREEMENT
        ]
        
        # 인정된 차이
        acknowledged_differences = [
            dp for dp in self.disagreement_points 
            if dp.level == AgreementLevel.ACKNOWLEDGED_DIFFERENCE
        ]
        
        return {
            "full_consensus": full_consensus,
            "partial_consensus": partial_consensus,
            "fundamental_differences": fundamental_differences,
            "acknowledged_differences": acknowledged_differences,
            "fact_checkable_items": [
                dp for dp in self.disagreement_points if dp.fact_checkable
            ],
            "statistics": {
                "total_consensus_points": len(self.consensus_points),
                "total_disagreement_points": len(self.disagreement_points),
                "consensus_ratio": len(self.consensus_points) / max(1, len(self.consensus_points) + len(self.disagreement_points))
            }
        }
    
    def generate_summary_report(self, language: str = "en") -> str:
        """최종 요약 보고서 생성"""
        summary = self.get_consensus_summary()
        
        if language == "ko":
            report = "📊 토론 합의/차이 분석 보고서\n"
            report += "=" * 50 + "\n\n"
            
            # 완전 합의
            if summary["full_consensus"]:
                report += "✅ 완전 합의 사항:\n"
                for cp in summary["full_consensus"]:
                    report += f"  • {cp.topic}: {cp.content}\n"
                    report += f"    동의: {', '.join(cp.agreed_by)}\n"
                report += "\n"
            
            # 부분 합의
            if summary["partial_consensus"]:
                report += "🤝 부분 합의 사항:\n"
                for cp in summary["partial_consensus"]:
                    report += f"  • {cp.topic}: {cp.content}\n"
                    report += f"    동의: {', '.join(cp.agreed_by)}\n"
                report += "\n"
            
            # 인정된 차이
            if summary["acknowledged_differences"]:
                report += "🔄 상호 인정된 관점 차이:\n"
                for dp in summary["acknowledged_differences"]:
                    report += f"  • {dp.topic}:\n"
                    for agent, position in dp.positions.items():
                        report += f"    - {agent}: {position}\n"
                report += "\n"
            
            # 근본적 차이
            if summary["fundamental_differences"]:
                report += "⚔️ 근본적 입장 차이:\n"
                for dp in summary["fundamental_differences"]:
                    report += f"  • {dp.issue}:\n"
                    for agent, position in dp.positions.items():
                        report += f"    - {agent}: {position}\n"
                    if dp.underlying_assumptions:
                        report += "    전제/가정:\n"
                        for agent, assumptions in dp.underlying_assumptions.items():
                            if assumptions:
                                report += f"      {agent}: {', '.join(assumptions)}\n"
                report += "\n"
            
            # 팩트체크 필요 항목
            if summary["fact_checkable_items"]:
                report += "🔍 팩트체크 필요 항목:\n"
                for dp in summary["fact_checkable_items"]:
                    report += f"  • {dp.topic}: {', '.join(dp.fact_check_queries)}\n"
                report += "\n"
            
            # 통계
            stats = summary["statistics"]
            report += f"📈 통계:\n"
            report += f"  • 합의점: {stats['total_consensus_points']}개\n"
            report += f"  • 차이점: {stats['total_disagreement_points']}개\n"
            report += f"  • 합의율: {stats['consensus_ratio']*100:.1f}%\n"
            
        else:  # English
            report = "📊 Discussion Consensus/Disagreement Analysis\n"
            report += "=" * 50 + "\n\n"
            
            # Full consensus
            if summary["full_consensus"]:
                report += "✅ Full Consensus:\n"
                for cp in summary["full_consensus"]:
                    report += f"  • {cp.topic}: {cp.content}\n"
                    report += f"    Agreed by: {', '.join(cp.agreed_by)}\n"
                report += "\n"
            
            # Partial consensus
            if summary["partial_consensus"]:
                report += "🤝 Partial Agreement:\n"
                for cp in summary["partial_consensus"]:
                    report += f"  • {cp.topic}: {cp.content}\n"
                    report += f"    Agreed by: {', '.join(cp.agreed_by)}\n"
                report += "\n"
            
            # Acknowledged differences
            if summary["acknowledged_differences"]:
                report += "🔄 Acknowledged Differences:\n"
                for dp in summary["acknowledged_differences"]:
                    report += f"  • {dp.topic}:\n"
                    for agent, position in dp.positions.items():
                        report += f"    - {agent}: {position}\n"
                report += "\n"
            
            # Fundamental differences
            if summary["fundamental_differences"]:
                report += "⚔️ Fundamental Disagreements:\n"
                for dp in summary["fundamental_differences"]:
                    report += f"  • {dp.issue}:\n"
                    for agent, position in dp.positions.items():
                        report += f"    - {agent}: {position}\n"
                    if dp.underlying_assumptions:
                        report += "    Underlying assumptions:\n"
                        for agent, assumptions in dp.underlying_assumptions.items():
                            if assumptions:
                                report += f"      {agent}: {', '.join(assumptions)}\n"
                report += "\n"
            
            # Fact-checkable items
            if summary["fact_checkable_items"]:
                report += "🔍 Fact-checkable Items:\n"
                for dp in summary["fact_checkable_items"]:
                    report += f"  • {dp.topic}: {', '.join(dp.fact_check_queries)}\n"
                report += "\n"
            
            # Statistics
            stats = summary["statistics"]
            report += f"📈 Statistics:\n"
            report += f"  • Consensus points: {stats['total_consensus_points']}\n"
            report += f"  • Disagreement points: {stats['total_disagreement_points']}\n"
            report += f"  • Consensus ratio: {stats['consensus_ratio']*100:.1f}%\n"
        
        return report