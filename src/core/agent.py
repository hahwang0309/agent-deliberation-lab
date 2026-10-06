"""
에이전트 핵심 모듈 - 개별 토론 참가자
"""

# ============================================
# CONSTANTS
# ============================================

BELIEF_EMPHASIS_PROMPT = """

IMPORTANT INSTRUCTIONS:
- Let your beliefs and values GUIDE your arguments naturally
- NEVER explicitly state "I believe..." or "My belief is..." or "As someone who values..."
- Your perspective should EMERGE from your reasoning, not be declared
- Speak through evidence, examples, and logical arguments that reflect your worldview
- Show your values through what you emphasize and prioritize, not through direct statements

Your core values for reference (DO NOT mention these directly):
{beliefs}

Express these values IMPLICITLY through:
- The evidence and examples you choose to highlight
- The aspects of the topic you focus on
- The solutions or approaches you advocate for
- The concerns and priorities you emphasize
- Your reasoning and logical framework

Remember: Sophisticated discourse shows beliefs through argument structure, not declarations.
"""

from typing import Optional, Dict, List, AsyncIterator
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.language_models import BaseChatModel
from src.models.personas import Persona, Message, LLMProvider
from src.utils.llm_provider import LLMFactory
from config.config_loader import config_loader
from src.models.persona_evolution import EvolvingPersona
from src.services.belief_reasoning import BeliefReasoningService
from src.services.rag_service import RAGService
from rich.console import Console

console = Console()


class DiscussionAgent:
    """토론 에이전트 - 페르소나 기반 토론 참가자"""
    
    def __init__(self, persona: Persona, llm: Optional[BaseChatModel] = None, 
                provider: LLMProvider = LLMProvider.OPENAI, track_evolution: bool = True,
                enable_web_search: bool = True):
        self.persona = persona
        self.provider = provider
        self.language = "auto"
        self.statement_count = 0
        self.total_position_shifts = 0
        
        # 신념 추론 서비스
        self.belief_reasoning = BeliefReasoningService(persona)
                
        # RAG 서비스
        self.rag_service = RAGService() if enable_web_search else None
        self.last_rag_result = None  # 마지막 RAG 결과 저장
        
        # LLM 설정
        if llm:
            self.llm = llm
        else:
            self.llm = LLMFactory.create_llm(provider, temperature=0.7)
        
        # 진화하는 페르소나 설정
        if track_evolution:
            openness = 0.7  # 기본값 상향
            if 'open-minded' in persona.personality:
                openness = 0.8
            elif 'flexible' in persona.personality:
                openness = 0.75
            elif 'stubborn' in persona.personality:
                openness = 0.3
            
            self.evolving_persona = EvolvingPersona(
                base_persona=persona,
                openness_to_change=openness
            )
        else:
            self.evolving_persona = None
    
    def _build_system_prompt(self) -> str:
        """시스템 프롬프트 생성 - 신념과 가치관 강조"""
        prompts = config_loader.prompts
        
        # 진화된 페르소나 사용
        current_persona = self.evolving_persona.get_evolved_persona() if self.evolving_persona else self.persona
        
        # 기본 페르소나 프롬프트
        persona_dict = {
            'name': current_persona.name,
            'role': current_persona.role,
            'background': current_persona.background,
            'personality': ', '.join(current_persona.personality),
            'expertise': ', '.join(current_persona.expertise),
            'communication_style': current_persona.communication_style,
            'beliefs': ', '.join(current_persona.beliefs)
        }
        
        base_prompt = prompts.get_agent_base_prompt(persona_dict)
        
        # 신념 기반 추론 강화 (암묵적)
        beliefs_text = '\n'.join([f"- {belief}" for belief in current_persona.beliefs[:3]])
        belief_emphasis = BELIEF_EMPHASIS_PROMPT.format(beliefs=beliefs_text)
        
        # 진화 상태 반영
        evolution_note = ""
        if self.evolving_persona and len(self.evolving_persona.position_shifts) > 0:
            evolution_note = "\n\nNote: Your views have evolved through this discussion. Reflect your current understanding."
        
        # 길이 지시
        length_instruction = prompts.get_agent_length_instruction(
            min_sentences=3,
            max_sentences=8
        )
        
        return base_prompt + belief_emphasis + evolution_note + length_instruction
    
    async def _prepare_response(self, prompt: str, context: List[Message] = None):
        """응답 준비 - CoT, RAG, 프롬프트 생성 공통 로직"""
        # 신념 기반 추론 (Chain-of-Thought)
        reasoning = await self.belief_reasoning.reason_about_topic(prompt, context)
        
        # RAG를 통한 증거 수집
        self.last_rag_result = None
        evidence_summary = None
        
        if self.rag_service:
            try:
                rag_result = await self.rag_service.process(prompt, self.persona, context)
                if rag_result.evidence:
                    self.last_rag_result = rag_result  # 나중에 표시할 수 있도록 저장
                    evidence_summary = rag_result.summary
            except Exception as e:
                print(f"RAG error for {self.persona.name}: {e}")
        
        # 시스템 프롬프트 생성
        system_prompt = self._build_system_prompt()
        
        # CoT 추론 추가
        if reasoning:
            system_prompt += f"\n\nYour reasoning process:\n{reasoning}\n\nNow provide your response based on this reasoning."
        
        # RAG 증거 추가
        if evidence_summary:
            system_prompt += f"\n\nRelevant evidence from research:\n{evidence_summary}\n\nIncorporate this evidence naturally into your response."
        
        # 메시지 구성
        messages = [SystemMessage(content=system_prompt)]
        
        # 컨텍스트 제공 (최근 발언 위주)
        if context:
            for msg in context[-5:]:
                messages.append(HumanMessage(
                    content=f"{msg.agent_name}: {msg.content[:200]}"
                ))
        
        messages.append(HumanMessage(content=prompt))
        
        return messages
    
    async def respond(self, prompt: str, context: List[Message] = None) -> str:
        """응답 생성 - RAG 및 Chain-of-Thought 적용"""
        # 공통 로직
        messages = await self._prepare_response(prompt, context)
        
        # LLM 호출
        response = await self.llm.ainvoke(messages)
        self.statement_count += 1
        
        return response.content
    
    async def respond_stream(self, prompt: str, context: List[Message] = None) -> AsyncIterator[str]:
        """스트리밍 응답 생성"""
        # 공통 로직
        messages = await self._prepare_response(prompt, context)
        
        # 스트리밍 LLM 호출
        async for chunk in self.llm.astream(messages):
            chunk_text = chunk.content if hasattr(chunk, 'content') else str(chunk)
            yield chunk_text
        
        self.statement_count += 1
    
    def process_other_argument(self, argument: str, agent_name: str, topic: str) -> Optional[Dict]:
        """다른 에이전트의 논증 처리"""
        if not self.evolving_persona:
            return None
        
        change_info = self.evolving_persona.update_position(topic, argument, agent_name)
        self.total_position_shifts = len(self.evolving_persona.position_shifts)
        
        return change_info
    