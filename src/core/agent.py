"""
에이전트 핵심 모듈 - 개별 토론 참가자
"""
import logging
from typing import Optional, Dict, List, AsyncIterator
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.language_models import BaseChatModel
from src.models.personas import Persona, Message, LLMProvider
from src.utils.llm_provider import LLMFactory
from config.config_loader import config_loader
from src.models.persona_evolution import EvolvingPersona
from src.services.belief_reasoning import BeliefReasoningService
from src.services.rag_service import RAGService

logger = logging.getLogger(__name__)


class DiscussionAgent:
    """토론 에이전트 - 페르소나 기반 토론 참가자

    Args:
        llm: 발언 생성용 LLM (없으면 provider 기본 모델)
        aux_llm: CoT 추론·RAG 질의용 보조 LLM (없으면 llm 재사용)
    """

    def __init__(self, persona: Persona, llm: Optional[BaseChatModel] = None,
                 provider: Optional[LLMProvider] = None, track_evolution: bool = True,
                 enable_web_search: bool = False, enable_belief_reasoning: bool = False,
                 aux_llm: Optional[BaseChatModel] = None):
        self.persona = persona
        self.provider = provider or LLMFactory.default_provider()
        self.language = "auto"
        self.statement_count = 0
        self.total_position_shifts = 0

        self.llm = llm or LLMFactory.create_llm(self.provider, temperature=0.7)
        aux_llm = aux_llm or self.llm

        # 신념 추론 서비스 (선택)
        self.belief_reasoning = BeliefReasoningService(persona, llm=aux_llm) if enable_belief_reasoning else None

        # RAG 서비스 (선택)
        self.rag_service = RAGService(aux_llm) if enable_web_search else None
        self.last_rag_result = None  # 마지막 RAG 결과 저장

        # 진화하는 페르소나 설정
        if track_evolution:
            openness = 0.7
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
        belief_emphasis = prompts.render("agent.belief_emphasis", beliefs=beliefs_text)

        # 진화 상태 반영
        evolution_note = ""
        if self.evolving_persona and len(self.evolving_persona.position_shifts) > 0:
            evolution_note = prompts.render("agent.evolution_note")

        length_instruction = prompts.get_agent_length_instruction(min_sentences=3, max_sentences=8)
        language_instruction = prompts.get(f"language.instruction.{self.language}", "")

        return base_prompt + belief_emphasis + evolution_note + length_instruction + language_instruction

    async def _prepare_response(self, prompt: str, context: List[Message] = None):
        """응답 준비 - CoT, RAG, 프롬프트 생성 공통 로직"""
        prompts = config_loader.prompts

        reasoning = None
        if self.belief_reasoning:
            reasoning = await self.belief_reasoning.reason_about_topic(prompt, context)

        self.last_rag_result = None
        evidence_summary = None
        if self.rag_service:
            try:
                rag_result = await self.rag_service.process(prompt, self.persona, context)
                if rag_result.evidence:
                    self.last_rag_result = rag_result
                    evidence_summary = rag_result.summary
            except Exception:
                logger.exception("RAG error for %s", self.persona.name)

        system_prompt = self._build_system_prompt()
        if reasoning:
            system_prompt += prompts.render("agent.reasoning_block", reasoning=reasoning)
        if evidence_summary:
            system_prompt += prompts.render("agent.evidence_block", evidence=evidence_summary)

        messages = [SystemMessage(content=system_prompt)]

        # 컨텍스트 제공 (최근 발언 위주)
        if context:
            for msg in context[-5:]:
                messages.append(HumanMessage(content=f"{msg.agent_name}: {msg.content[:200]}"))

        messages.append(HumanMessage(content=prompt))
        return messages

    async def respond(self, prompt: str, context: List[Message] = None) -> str:
        """응답 생성 (비스트리밍)"""
        messages = await self._prepare_response(prompt, context)
        response = await self.llm.ainvoke(messages)
        self.statement_count += 1
        return response.content

    async def respond_stream(self, prompt: str, context: List[Message] = None) -> AsyncIterator[str]:
        """스트리밍 응답 생성"""
        messages = await self._prepare_response(prompt, context)
        async for chunk in self.llm.astream(messages):
            chunk_text = chunk.content if hasattr(chunk, 'content') else str(chunk)
            if chunk_text:
                yield chunk_text
        self.statement_count += 1

    def process_other_argument(self, argument: str, agent_name: str, topic: str) -> Optional[Dict]:
        """다른 에이전트의 논증 처리"""
        if not self.evolving_persona:
            return None

        change_info = self.evolving_persona.update_position(topic, argument, agent_name)
        self.total_position_shifts = len(self.evolving_persona.position_shifts)
        return change_info
