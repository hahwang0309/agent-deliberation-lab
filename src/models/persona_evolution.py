"""
진화하는 페르소나 시스템
논리적 설득에 따라 점진적으로 입장이 변화하는 페르소나
"""
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field, asdict
from src.models.personas import Persona
import json
from copy import deepcopy


@dataclass
class Belief:
    """개별 신념/믿음"""
    content: str
    strength: float = 1.0  # 0.0 ~ 1.0 (신념의 강도)
    flexibility: float = 0.3  # 0.0 ~ 1.0 (변화 가능성)
    evidence_against: List[str] = field(default_factory=list)
    evidence_for: List[str] = field(default_factory=list)
    
    def challenge(self, counter_evidence: str, strength: float = 0.2) -> float:
        """신념에 도전하는 증거 제시
        
        Returns:
            변화된 신념 강도
        """
        self.evidence_against.append(counter_evidence)
        
        # 변화량 = 도전 강도 * 유연성 * 감쇠 계수
        # 반복된 도전은 오히려 효과 증가 (설득 누적)
        accumulation_factor = 1.0 + (len(self.evidence_against) * 0.15)
        change = strength * self.flexibility * accumulation_factor
        
        # 신념 강도 감소 (최소 0.1 유지)
        self.strength = max(0.1, self.strength - change)
        
        return self.strength
    
    def reinforce(self, supporting_evidence: str, strength: float = 0.1) -> float:
        """신념을 강화하는 증거 제시
        
        Returns:
            변화된 신념 강도
        """
        self.evidence_for.append(supporting_evidence)
        
        # 강화는 약하게 (확증 편향 방지)
        change = strength * 0.5
        self.strength = min(1.0, self.strength + change)
        
        return self.strength


@dataclass
class EvolvingPersona:
    """진화하는 페르소나"""
    base_persona: Persona
    beliefs: Dict[str, Belief] = field(default_factory=dict)
    position_shifts: List[Dict[str, any]] = field(default_factory=list)  # 입장 변화 기록
    openness_to_change: float = 0.7  # 0.0 ~ 1.0 (변화에 대한 개방성) - 더 상향
    conviction_threshold: float = 0.5  # 신념 강도가 이 이하로 떨어지면 입장 재고 - 더 완화
    cumulative_impact: float = 0.0  # 누적된 논증 영향력
    
    def __post_init__(self):
        """초기 신념 설정"""
        # config 가져오기
        from config.discussion_config import get_config
        config = get_config()
        
        if not self.beliefs:
            for belief_str in self.base_persona.beliefs:
                # 핵심 신념도 어느 정도 유연하게
                is_core = any(word in belief_str.lower() for word in ['essential', 'fundamental', 'core'])
                
                # 설정값 사용
                strength = config.core_belief_strength if is_core else config.normal_belief_strength
                flexibility = config.core_belief_flexibility if is_core else config.normal_belief_flexibility
                
                self.beliefs[belief_str] = Belief(
                    content=belief_str,
                    strength=strength,
                    flexibility=flexibility
                )
    
    def evaluate_argument(self, argument: str, context: str) -> Tuple[bool, float, str]:
        """논증 평가
        
        Returns:
            (설득력 있음, 영향도, 반응 유형)
        """
        # config 가져오기
        from config.discussion_config import get_config
        config = get_config()
        
        # 강력한 증거 키워드
        strong_evidence = ['data', 'research', 'study', 'experiment', 'evidence', 'statistic', 
                          'analysis', 'survey', 'empirical', 'proven', 'demonstrated']
        logical_keywords = ['therefore', 'because', 'however', 'thus', 'consequently', 'moreover']
        specific_numbers = sum(1 for char in argument if char.isdigit()) > 5  # 구체적 수치 포함
        
        # 증거 점수 계산 - 설정값 사용
        evidence_count = sum(1 for keyword in strong_evidence if keyword in argument.lower())
        logic_count = sum(1 for keyword in logical_keywords if keyword in argument.lower())
        
        evidence_score = min(config.evidence_score_max, evidence_count * config.evidence_score_weight)
        logic_score = min(config.logic_score_max, logic_count * config.logic_score_weight)
        specificity_bonus = config.specificity_bonus if specific_numbers else 0
        
        # 논증 강도 (0.0 ~ 1.0)
        argument_strength = min(1.0, evidence_score + logic_score + specificity_bonus + 0.25)  # 기본값 상향
        
        # 여러 번 노출되면 저항력 감소 (설득 누적 효과) - 더 강한 효과
        self.cumulative_impact = min(1.0, self.cumulative_impact + 0.1)  # 누적 효과
        exposure_factor = 1.0 + (len(self.position_shifts) * 0.2) + self.cumulative_impact
        adjusted_strength = min(1.0, argument_strength * self.openness_to_change * exposure_factor)
        
        # 설득력 임계값 - 설정값 사용
        is_persuasive = adjusted_strength > config.persuasion_threshold
        
        # 반응 유형 결정
        if adjusted_strength < 0.2:
            reaction = "dismissive"  # 무시
        elif adjusted_strength < 0.35:
            reaction = "defensive"   # 방어적
        elif adjusted_strength < 0.5:
            reaction = "considering"  # 고려 중
        else:
            reaction = "receptive"    # 수용적
        
        return is_persuasive, adjusted_strength, reaction
    
    def update_position(self, topic: str, argument: str, agent_name: str) -> Dict[str, any]:
        """입장 업데이트
        
        Returns:
            변화 정보
        """
        is_persuasive, impact, reaction = self.evaluate_argument(argument, topic)
        
        change_info = {
            "topic": topic,
            "argument_from": agent_name,
            "argument": argument[:100],
            "impact": impact,
            "reaction": reaction,
            "beliefs_affected": [],
            "position_changed": False
        }
        
        if is_persuasive:
            # 모든 신념이 어느 정도 영향받도록 (토론은 전체적 영향)
            affected_beliefs = []
            for belief_key, belief in self.beliefs.items():
                # 주제와 직접 관련이 있거나, 논증에 언급된 키워드가 있으면 더 강한 영향
                topic_words = topic.lower().split()
                argument_words = argument.lower().split()
                belief_words = belief_key.lower().split()
                
                # 관련도 계산
                direct_match = any(word in belief_words for word in topic_words)
                indirect_match = any(word in belief_words for word in argument_words[:20])  # 논증 앞부분
                
                if direct_match or indirect_match or reaction == "receptive":  # 수용적이면 모든 신념 영향
                    old_strength = belief.strength
                    
                    # 반대 논증이면 도전, 지지 논증이면 강화
                    if "not" in argument.lower() or "however" in argument.lower():
                        new_strength = belief.challenge(argument, impact)
                    else:
                        new_strength = belief.reinforce(argument, impact * 0.5)
                    
                    if abs(new_strength - old_strength) > 0.05:
                        affected_beliefs.append({
                            "belief": belief_key[:50],
                            "old_strength": old_strength,
                            "new_strength": new_strength
                        })
                    
                    # 신념이 임계값 아래로 떨어지면 입장 변화
                    if old_strength >= self.conviction_threshold and new_strength < self.conviction_threshold:
                        change_info["position_changed"] = True
            
            change_info["beliefs_affected"] = affected_beliefs
        
        # 변화 기록
        if change_info["beliefs_affected"] or change_info["position_changed"]:
            self.position_shifts.append(change_info)
        
        return change_info
    
    def get_evolved_persona(self) -> Persona:
        """현재 상태의 페르소나 반환"""
        evolved = deepcopy(self.base_persona)
        
        # 약화된 신념은 수정하거나 제거
        new_beliefs = []
        for belief_key, belief in self.beliefs.items():
            if belief.strength > 0.3:
                # 강도에 따라 표현 조정
                if belief.strength > 0.8:
                    new_beliefs.append(belief.content)
                elif belief.strength > 0.5:
                    new_beliefs.append(f"Generally believes that {belief.content.lower()}")
                else:
                    new_beliefs.append(f"Questions whether {belief.content.lower()}")
        
        evolved.beliefs = new_beliefs
        
        # 성격에 변화 반영
        if len(self.position_shifts) > 3:
            if "thoughtful" not in evolved.personality:
                evolved.personality.append("thoughtful")
            if "open-minded" not in evolved.personality and self.openness_to_change > 0.5:
                evolved.personality.append("open-minded")
        
        return evolved
    
    def get_evolution_summary(self) -> str:
        """페르소나 진화 요약"""
        if not self.position_shifts:
            return "No significant changes in position."
        
        summary = f"Position evolved through {len(self.position_shifts)} significant interactions:\n"
        
        # 가장 영향력 있었던 논증들
        major_shifts = sorted(self.position_shifts, key=lambda x: x['impact'], reverse=True)[:3]
        
        for shift in major_shifts:
            summary += f"- {shift['reaction'].capitalize()} to {shift['argument_from']}'s argument "
            summary += f"(impact: {shift['impact']:.2f})\n"
            
            if shift['position_changed']:
                summary += "  → Major position shift occurred\n"
            
            for belief_change in shift['beliefs_affected'][:2]:
                summary += f"  → {belief_change['belief']}... "
                summary += f"({belief_change['old_strength']:.2f} → {belief_change['new_strength']:.2f})\n"
        
        # 전체적인 변화 방향
        total_openness_change = len([s for s in self.position_shifts if s['reaction'] in ['considering', 'receptive']])
        if total_openness_change > 3:
            summary += f"\nOverall: Became more open to alternative viewpoints."
        elif len(self.position_shifts) > 5:
            summary += f"\nOverall: Maintained core beliefs while engaging with challenges."
        
        return summary
    
    def compare_with_initial(self) -> Dict[str, any]:
        """초기 페르소나와 비교"""
        evolved = self.get_evolved_persona()
        
        comparison = {
            "beliefs_changed": [],
            "beliefs_maintained": [],
            "new_traits": [],
            "overall_shift": 0.0
        }
        
        # 신념 비교
        original_beliefs = set(self.base_persona.beliefs)
        current_beliefs = set(evolved.beliefs)
        
        for belief in original_beliefs:
            if belief in current_beliefs:
                comparison["beliefs_maintained"].append(belief)
            else:
                comparison["beliefs_changed"].append(f"Lost: {belief}")
        
        for belief in current_beliefs - original_beliefs:
            comparison["beliefs_changed"].append(f"New: {belief}")
        
        # 성격 특성 비교
        original_traits = set(self.base_persona.personality)
        current_traits = set(evolved.personality)
        comparison["new_traits"] = list(current_traits - original_traits)
        
        # 전체 변화도 계산
        if len(original_beliefs) > 0:
            comparison["overall_shift"] = len(comparison["beliefs_changed"]) / len(original_beliefs)
        
        return comparison