"""
Discussion Manager Service
토론 시간과 주제 진행을 관리하는 서비스
"""
from typing import List, Dict, Optional, Tuple
from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import asyncio


class DiscussionPhase(Enum):
    """토론 단계"""
    OPENING = "opening"          # 도입 (10%)
    EXPLORATION = "exploration"  # 탐색 (30%)
    DEEP_DIVE = "deep_dive"      # 심화 (40%)
    SYNTHESIS = "synthesis"      # 종합 (15%)
    CLOSING = "closing"          # 마무리 (5%)


@dataclass
class TopicStatus:
    """주제 상태"""
    topic: str
    depth_score: float = 0.0  # 0-1, 논의 깊이
    coverage: float = 0.0      # 0-1, 커버리지
    time_spent: int = 0        # 소요 시간 (턴 수)
    key_points: List[str] = field(default_factory=list)
    needs_probing: bool = False
    is_complete: bool = False


@dataclass 
class TimeAllocation:
    """시간 배분"""
    total_statements: int
    phase_allocations: Dict[DiscussionPhase, int]
    statements_used: int = 0
    current_phase: DiscussionPhase = DiscussionPhase.OPENING
    

class DiscussionManager:
    """토론 관리자"""
    
    def __init__(self, max_statements: int = 20):
        """
        Args:
            max_statements: 최대 발언 수
        """
        self.max_statements = max_statements
        self.current_statement = 0
        self.subtopics: List[str] = []
        self.topic_status: Dict[str, TopicStatus] = {}
        self.current_subtopic_idx = 0
        self.time_allocation = self._calculate_time_allocation()
        self.abstract_statements_count = 0
        self.last_probing_turn = -5  # 마지막 probing 질문 턴
        
    def _calculate_time_allocation(self) -> TimeAllocation:
        """단계별 시간 배분 계산"""
        allocations = {
            DiscussionPhase.OPENING: int(self.max_statements * 0.10),
            DiscussionPhase.EXPLORATION: int(self.max_statements * 0.30),
            DiscussionPhase.DEEP_DIVE: int(self.max_statements * 0.40),
            DiscussionPhase.SYNTHESIS: int(self.max_statements * 0.15),
            DiscussionPhase.CLOSING: int(self.max_statements * 0.05)
        }
        
        # 반올림 오차 조정
        total_allocated = sum(allocations.values())
        if total_allocated < self.max_statements:
            allocations[DiscussionPhase.DEEP_DIVE] += self.max_statements - total_allocated
            
        return TimeAllocation(
            total_statements=self.max_statements,
            phase_allocations=allocations
        )
    
    def set_subtopics(self, subtopics: List[str]):
        """서브토픽 설정"""
        self.subtopics = subtopics
        for topic in subtopics:
            self.topic_status[topic] = TopicStatus(topic=topic)
    
    def get_current_phase(self) -> DiscussionPhase:
        """현재 토론 단계 반환"""
        progress = self.current_statement / self.max_statements
        
        if progress < 0.1:
            return DiscussionPhase.OPENING
        elif progress < 0.4:
            return DiscussionPhase.EXPLORATION
        elif progress < 0.8:
            return DiscussionPhase.DEEP_DIVE
        elif progress < 0.95:
            return DiscussionPhase.SYNTHESIS
        else:
            return DiscussionPhase.CLOSING
    
    def should_transition_topic(self) -> bool:
        """주제 전환 필요 여부"""
        if not self.subtopics:
            return False
            
        current_phase = self.get_current_phase()
        
        # 마무리 단계에서는 전환 안함
        if current_phase == DiscussionPhase.CLOSING:
            return False
        
        # 현재 주제 상태 확인
        if self.current_subtopic_idx < len(self.subtopics):
            current_topic = self.subtopics[self.current_subtopic_idx]
            status = self.topic_status.get(current_topic)
            
            if status:
                # 충분히 논의됨 (깊이 > 0.7 또는 시간 > 3턴)
                if status.depth_score > 0.7 or status.time_spent > 3:
                    return True
                
                # 논의가 정체됨 (2턴 이상 깊이 증가 없음)
                if status.time_spent > 2 and status.depth_score < 0.3:
                    return True
        
        # 시간 기반 전환 (전체의 20% 이상을 한 주제에 사용)
        turns_per_topic = self.max_statements / max(len(self.subtopics), 1)
        if self.current_statement > (self.current_subtopic_idx + 1) * turns_per_topic:
            return True
            
        return False
    
    def get_next_subtopic(self) -> Optional[str]:
        """다음 서브토픽 반환"""
        # 가장 적게 다뤄진 주제 우선
        if self.topic_status:
            incomplete_topics = [
                (topic, status) 
                for topic, status in self.topic_status.items() 
                if not status.is_complete
            ]
            
            if incomplete_topics:
                # 가장 적게 다뤄진 주제 선택
                next_topic = min(incomplete_topics, key=lambda x: x[1].coverage)
                return next_topic[0]
        
        # 순차적 진행
        if self.current_subtopic_idx < len(self.subtopics) - 1:
            self.current_subtopic_idx += 1
            return self.subtopics[self.current_subtopic_idx]
            
        return None
    
    def update_topic_status(self, topic: str, message_content: str, is_abstract: bool = False):
        """주제 상태 업데이트"""
        if topic not in self.topic_status:
            self.topic_status[topic] = TopicStatus(topic=topic)
            
        status = self.topic_status[topic]
        status.time_spent += 1
        
        # 추상성 체크
        if is_abstract:
            self.abstract_statements_count += 1
            status.needs_probing = True
        else:
            # 구체적인 내용이면 깊이 증가
            status.depth_score = min(1.0, status.depth_score + 0.2)
            status.needs_probing = False
        
        # 커버리지 업데이트
        status.coverage = min(1.0, status.time_spent * 0.25)
        
        # 완료 체크
        if status.depth_score > 0.8 and status.coverage > 0.6:
            status.is_complete = True
    
    def check_statement_abstractness(self, content: str) -> bool:
        """발언의 추상성 체크"""
        # 구체성 지표들
        concrete_indicators = [
            # 숫자와 수치
            r'\d+%', r'\d+\s*(million|billion|thousand|hundred)',
            # 구체적 예시
            r'for example', r'for instance', r'specifically',
            r'such as', r'including', r'case study',
            # 시간 참조
            r'in \d{4}', r'last year', r'this year', r'recently',
            # 구체적 장소/조직
            r'[A-Z][a-z]+\s+(Company|Corporation|Institute|University)',
            # 데이터 참조
            r'according to', r'study shows', r'research indicates',
            r'data suggests', r'survey found'
        ]
        
        import re
        concrete_count = sum(1 for pattern in concrete_indicators 
                           if re.search(pattern, content, re.IGNORECASE))
        
        # 추상적 지표들
        abstract_indicators = [
            r'\b(might|maybe|perhaps|possibly|generally|usually|often)\b',
            r'\b(concept|idea|theory|principle|philosophy)\b',
            r'\b(important|significant|crucial|vital|essential)\b',
            r'\b(should|could|would)\b',
            r'\b(believe|think|feel|seem)\b'
        ]
        
        abstract_count = sum(1 for pattern in abstract_indicators 
                           if re.search(pattern, content, re.IGNORECASE))
        
        # 길이 대비 구체성 비율
        word_count = len(content.split())
        if word_count < 30:  # 너무 짧은 발언
            return True
            
        # 구체성 점수 계산
        concreteness_score = concrete_count - (abstract_count * 0.5)
        
        return concreteness_score < 1  # 구체성이 낮으면 추상적
    
    def should_probe_for_specifics(self) -> bool:
        """구체화를 위한 probing 필요 여부"""
        # 너무 자주 하지 않기 (최소 3턴 간격)
        if self.current_statement - self.last_probing_turn < 3:
            return False
            
        # 최근 추상적 발언이 많으면
        if self.abstract_statements_count > 2:
            return True
            
        # 현재 주제가 깊이가 부족하면
        current_topic = self.subtopics[self.current_subtopic_idx] if self.subtopics else None
        if current_topic and current_topic in self.topic_status:
            status = self.topic_status[current_topic]
            if status.needs_probing and status.depth_score < 0.5:
                return True
                
        return False
    
    def record_probing_question(self):
        """Probing 질문 기록"""
        self.last_probing_turn = self.current_statement
        self.abstract_statements_count = max(0, self.abstract_statements_count - 1)
    
    def increment_turn(self):
        """턴 증가"""
        self.current_statement += 1
        self.time_allocation.statements_used += 1
        
        # 단계 업데이트
        self.time_allocation.current_phase = self.get_current_phase()
    
    def get_remaining_statements(self) -> int:
        """남은 발언 수"""
        return max(0, self.max_statements - self.current_statement)
    
    def get_progress_percentage(self) -> float:
        """진행률 (%)"""
        return (self.current_statement / self.max_statements) * 100
    
    def should_start_closing(self) -> bool:
        """마무리 시작 여부"""
        return self.get_remaining_statements() <= 2
    
    def get_phase_guidance(self) -> str:
        """현재 단계별 가이드"""
        phase = self.get_current_phase()
        
        guidance = {
            DiscussionPhase.OPENING: "Introduce perspectives and frame the discussion",
            DiscussionPhase.EXPLORATION: "Explore different angles and viewpoints",
            DiscussionPhase.DEEP_DIVE: "Dive deep into specifics with evidence and examples",
            DiscussionPhase.SYNTHESIS: "Connect ideas and find common ground",
            DiscussionPhase.CLOSING: "Summarize key insights and conclusions"
        }
        
        return guidance.get(phase, "Continue discussion")
    
    def get_topic_coverage_report(self) -> Dict:
        """주제 커버리지 리포트"""
        total_topics = len(self.subtopics)
        covered_topics = sum(1 for status in self.topic_status.values() 
                           if status.coverage > 0)
        well_covered = sum(1 for status in self.topic_status.values() 
                          if status.is_complete)
        
        avg_depth = sum(s.depth_score for s in self.topic_status.values()) / max(len(self.topic_status), 1)
        
        return {
            "total_topics": total_topics,
            "topics_touched": covered_topics,
            "topics_completed": well_covered,
            "average_depth": avg_depth,
            "current_phase": self.get_current_phase().value,
            "progress": self.get_progress_percentage(),
            "remaining_statements": self.get_remaining_statements()
        }
    
    def get_time_pressure_level(self) -> str:
        """시간 압박 수준"""
        remaining_ratio = self.get_remaining_statements() / self.max_statements
        
        if remaining_ratio > 0.5:
            return "relaxed"
        elif remaining_ratio > 0.2:
            return "moderate"
        elif remaining_ratio > 0.1:
            return "urgent"
        else:
            return "critical"