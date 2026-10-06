"""
모더레이터 모듈 - 토론 진행자 및 소주제 관리
"""
from typing import List, Optional
from langchain_core.messages import HumanMessage
from langchain_core.language_models import BaseChatModel
from src.models.personas import Message, LLMProvider
from src.utils.llm_provider import LLMFactory
from src.utils.language_detector import LanguageDetector
import re


class DiscussionModerator:
    """토론 진행자 - 소주제 관리 및 심화 유도"""
    
    def __init__(self, llm: Optional[BaseChatModel] = None, language: str = "auto"):
        # LLM 설정
        if llm:
            self.llm = llm
        else:
            self.llm = LLMFactory.create_llm(LLMProvider.OPENAI, temperature=0.5)
        
        self.language = language
        
        # 소주제 관리 (최소한)
        self.subtopics = []
        self.current_subtopic_idx = 0
        
        # 질문 관리 (최소한)
        self.question_count = 0
        self.last_question_turn = 0
    
    async def generate_subtopics(self, topic: str) -> List[str]:
        """주제에 대한 핵심 관점/소주제 생성"""
        # config 가져오기
        from config.discussion_config import get_config
        config = get_config()
        
        lang_instruction = LanguageDetector.get_language_instruction(self.language)
        
        prompt = f"""
Main topic: {topic}

Identify 4-5 key perspectives that MUST be explored for a comprehensive discussion.
Consider:
- Practical/Implementation aspects
- Ethical/Value dimensions  
- Economic/Resource implications
- Social/Human impact
- Technical/Feasibility concerns
- Long-term consequences

{lang_instruction}

Format: Simple numbered list of specific subtopics.
Make each subtopic a clear, focused question or aspect.
"""
        
        response = await self.llm.ainvoke([HumanMessage(content=prompt)])
        content = response.content.strip()
        
        # 파싱
        parsed_subtopics = []
        lines = content.split('\n')
        for line in lines:
            line = line.strip()
            if line and any(char.isdigit() for char in line[:3]):
                subtopic = re.sub(r'^[\d.)\s]+', '', line).strip()
                if subtopic and len(subtopic) > 5:
                    parsed_subtopics.append(subtopic)
        
        # 소주제 저장
        max_subtopics = config.max_subtopics
        self.subtopics = parsed_subtopics[:max_subtopics]
        self.current_subtopic_idx = 0  # 첫 번째 주제부터 시작
        
        return self.subtopics
    
    def should_ask_question(self, turn_count: int) -> bool:
        """질문을 해야 하는지 판단"""
        # 5턴마다 한 번씩만 질문 (과도한 질문 방지)
        if turn_count - self.last_question_turn < 5:
            return False
        
        return True
    
    async def generate_probing_question(self, topic: str, messages: List[Message], 
                                       is_abstract: bool = False) -> str:
        """심화 질문 생성 - 추상적 발언에 대한 구체화 유도"""
        current_subtopic = self.subtopics[self.current_subtopic_idx] if self.current_subtopic_idx < len(self.subtopics) else None
        recent_points = [m.content[:100] for m in messages[-3:]]
        
        if is_abstract and messages:
            # 추상적 발언에 대한 구체화 질문
            last_msg = messages[-1]
            prompt = f"""
The following statement is too abstract and needs specifics:
"{last_msg.content[:200]}"

Generate ONE probing question that asks for:
- Specific examples or cases
- Concrete data or evidence  
- Measurable impacts or outcomes
- Real-world applications
- Detailed mechanisms or processes

Make it direct but respectful. Focus on getting concrete details.
"""
        else:
            # 일반적인 심화 질문
            prompt = f"""
Topic: {topic}
Current aspect: {current_subtopic}
Recent discussion: {' | '.join(recent_points)}

Generate ONE specific, probing question that:
1. Asks for SPECIFIC evidence, data, or examples
2. Explores concrete impacts or measurable outcomes
3. Challenges with "How exactly?" or "What specifically?"
4. Demands practical details, not theoretical concepts

Keep it concise and focused on getting concrete information.
"""
        
        response = await self.llm.ainvoke([HumanMessage(content=prompt)])
        question = response.content.strip()
        
        self.question_count += 1
        
        return question
    
    def should_transition_subtopic(self, messages: List[Message]) -> bool:
        """주제 전환 필요 여부 판단 (자체 완결)"""
        # config 가져오기
        from config.discussion_config import get_config
        config = get_config()
        
        # 1. 현재 주제 확인
        if self.current_subtopic_idx >= len(self.subtopics):
            return False  # 모든 주제 완료
        
        current_topic = self.subtopics[self.current_subtopic_idx]
        
        # 2. 논의 깊이 계산 (직접 계산)
        window = config.depth_analysis_window
        recent_messages = messages[-window:] if len(messages) >= window else messages
        keywords = current_topic.lower().split()[:2]  # 주제의 첫 2단어
        
        depth = 0
        for msg in recent_messages:
            if msg.role == "agent":
                content_lower = msg.content.lower()
                if any(keyword in content_lower for keyword in keywords):
                    depth += 1
        
        # 3. 충분히 논의됨
        if depth >= config.min_depth_per_subtopic:
            return True
        
        # 4. 최근 언급 없음 체크
        mention_window = config.recent_mention_window
        recent_n = messages[-mention_window:] if len(messages) >= mention_window else messages
        mentioned_recently = False
        
        for msg in recent_n:
            if msg.role == "agent":
                content_lower = msg.content.lower()
                if any(keyword in content_lower for keyword in keywords):
                    mentioned_recently = True
                    break
        
        # 최근 N개 메시지에 언급 없고, 전체 메시지가 충분하면 전환
        min_messages = config.min_messages_before_transition
        return not mentioned_recently and len(messages) > min_messages
    
    async def transition_to_next_subtopic(self, topic: str) -> str:
        """다음 소주제로 전환 (단순화)"""
        
        # 다음 주제로 이동
        self.current_subtopic_idx += 1
        
        # 다음 주제 확인
        if self.current_subtopic_idx < len(self.subtopics):
            next_topic = self.subtopics[self.current_subtopic_idx]
            
            # 전환 메시지
            return f"""
Building on our discussion so far, let's now examine another crucial perspective:

**{next_topic}**

This aspect is essential for a comprehensive understanding of {topic}.

Who would like to address this?
"""
        else:
            # 모든 주제 완료
            return "We've explored all the key perspectives. Let's begin synthesizing our discussion."
    
    async def synthesize_discussion(self, topic: str, messages: List[Message]) -> str:
        """토론 종합"""
        prompt = f"""
Topic: {topic}
Discussion covered {len(self.subtopics)} key perspectives:
{chr(10).join([f"- {s}" for s in self.subtopics])}

Based on the rich discussion, provide a brief synthesis that:
1. Highlights points of convergence
2. Notes remaining tensions
3. Suggests implications

Keep it to 3-4 sentences.
"""
        
        response = await self.llm.ainvoke([HumanMessage(content=prompt)])
        return response.content
