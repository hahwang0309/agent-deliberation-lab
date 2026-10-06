"""
신념 기반 추론 서비스 - Chain-of-Thought 기법 적용
"""
from typing import List, Optional
from src.models.personas import Persona, Message, LLMProvider
from src.utils.llm_provider import LLMFactory
from langchain_core.messages import HumanMessage


class BeliefReasoningService:
    """신념과 가치관 기반 추론 서비스"""
    
    def __init__(self, persona: Persona):
        self.persona = persona
        self.llm = LLMFactory.create_llm(LLMProvider.OPENAI, temperature=0.3)
    
    async def reason_about_topic(self, topic: str, context: List[Message] = None) -> str:
        """주제에 대한 신념 기반 추론 (Chain-of-Thought)"""
        
        # 핵심 질문 생성
        core_questions = self._generate_core_questions(topic)
        
        # 신념 기반 답변 도출 (암묵적)
        reasoning_prompt = f"""
As {self.persona.name}, a {self.persona.role} with {self.persona.background}

Topic/Question: {topic}

Internal reasoning (these values guide you but DON'T state them):
{', '.join(self.persona.beliefs[:3])}

Analyze the topic considering:
1. What specific DATA or EVIDENCE from your field supports your position?
2. What PRACTICAL EXAMPLES from your experience are relevant?
3. What CONCRETE IMPACTS or CONSEQUENCES concern you most?

Generate reasoning that naturally reflects your worldview WITHOUT declaring beliefs.
Focus on facts, evidence, and logical arguments that implicitly show your values.
Provide 2-3 sentences of reasoning that guides a sophisticated, implicit response.
"""
        
        response = await self.llm.ainvoke([HumanMessage(content=reasoning_prompt)])
        return response.content
    
    def _generate_core_questions(self, topic: str) -> str:
        """토론 주제에 대한 핵심 질문 생성 (암묵적 접근)"""
        
        # 실질적이고 구체적인 질문들
        questions = []
        
        # 전문성 기반 실질적 질문
        if self.persona.expertise:
            questions.append(f"What specific data or cases from {self.persona.expertise[0]} apply here?")
        
        # 경험 기반 구체적 질문  
        questions.append("What concrete examples or outcomes have I witnessed in similar situations?")
        
        # 영향력 분석 질문
        questions.append("What measurable impacts or consequences should be prioritized?")
        
        return '\n'.join(questions)
    
    def check_belief_consistency(self, statement: str) -> float:
        """발언이 신념과 일치하는지 확인 (0.0 ~ 1.0)"""
        
        # 신념 키워드와 매칭
        consistency_score = 0.0
        
        for belief in self.persona.beliefs:
            belief_keywords = belief.lower().split()
            statement_lower = statement.lower()
            
            matches = sum(1 for keyword in belief_keywords if keyword in statement_lower)
            consistency_score += matches / len(belief_keywords) if belief_keywords else 0
        
        return min(1.0, consistency_score / len(self.persona.beliefs)) if self.persona.beliefs else 0.5