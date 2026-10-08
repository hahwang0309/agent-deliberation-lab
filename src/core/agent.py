"""
에이전트 핵심 모듈 - 개별 토론 참가자

입장 변화는 이 클래스가 아니라 src/core/debate_state.py(입장 동역학)가 관리하고,
현재 입장·자기 주장 기록은 토론 엔진이 발언 프롬프트에 넣어 준다.
"""
import logging
from typing import AsyncIterator, List, Optional

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from config.config_loader import config_loader
from config.discussion_config import DiscussionConfig, get_config
from src.models.personas import LLMProvider, Message, Persona
from src.services.belief_reasoning import BeliefReasoningService
from src.services.rag_service import RAGService
from src.utils.llm_provider import LLMFactory

logger = logging.getLogger(__name__)

OPEN_TRAITS = ("open-minded", "flexible", "curious", "개방", "유연", "수용", "호기심")
FIRM_TRAITS = ("stubborn", "principled", "uncompromising", "dogmatic", "완고", "고집", "원칙", "단호", "강경")


class DiscussionAgent:
    """토론 에이전트 - 페르소나 기반 토론 참가자

    Args:
        llm: 발언 생성용 LLM (없으면 provider 기본 모델)
        aux_llm: CoT 추론·RAG 질의용 보조 LLM (없으면 llm 재사용)
    """

    def __init__(self, persona: Persona, llm: Optional[BaseChatModel] = None,
                 provider: Optional[LLMProvider] = None,
                 enable_web_search: bool = False, enable_belief_reasoning: bool = False,
                 aux_llm: Optional[BaseChatModel] = None, config: Optional[DiscussionConfig] = None,
                 stubbornness: Optional[float] = None, materials: Optional[str] = None,
                 seed: Optional[dict] = None, initial_position: str = ""):
        self.persona = persona
        self.config = config or get_config()  # 토론별 설정 (실험 조건 반영)
        self.stubbornness_override = stubbornness
        self.materials = materials  # 모든 참가자에게 같은 배경 자료집 (인간 숙의의 자료집에 대응)
        self.seed = seed or {}  # 심은 사전 설문 응답 {문항 id: 값} (사전 설문은 묻지 않고 이 값으로 기록)
        self.initial_position = initial_position  # 심은 응답을 시스템 프롬프트에 넣을 문장
        self.provider = provider or LLMFactory.default_provider()
        self.language = "auto"
        self.statement_count = 0

        self.llm = llm or LLMFactory.create_llm(self.provider, temperature=0.7)
        aux_llm = aux_llm or self.llm

        # 신념 추론 서비스 (선택)
        self.belief_reasoning = BeliefReasoningService(persona, llm=aux_llm) if enable_belief_reasoning else None

        # RAG 서비스 (선택)
        self.rag_service = RAGService(aux_llm) if enable_web_search else None
        self.last_rag_result = None  # 마지막 RAG 결과 저장

    @property
    def stubbornness(self) -> float:
        """입장 동역학의 고집도 s: 실험 조건으로 지정했으면 그 값, 아니면 성격 특성으로 정함
        (개방적이면 낮게, 원칙적·완고하면 높게)"""
        if self.stubbornness_override is not None:
            return self.stubbornness_override
        config = self.config
        traits = " ".join(self.persona.personality).lower()
        if any(t in traits for t in FIRM_TRAITS):
            return config.stubbornness_firm
        if any(t in traits for t in OPEN_TRAITS):
            return config.stubbornness_open
        return config.stubbornness_default

    def _build_system_prompt(self) -> str:
        """시스템 프롬프트 - 페르소나, 암묵적 신념 표현, 길이·언어 지시"""
        prompts = config_loader.prompts
        persona = self.persona
        base_prompt = prompts.get_agent_base_prompt({
            'name': persona.name,
            'role': persona.role,
            'background': persona.background,
            'personality': ', '.join(persona.personality),
            'expertise': ', '.join(persona.expertise),
            'communication_style': persona.communication_style,
            'beliefs': ', '.join(persona.beliefs),
        })
        beliefs_text = '\n'.join([f"- {belief}" for belief in persona.beliefs[:3]])
        belief_emphasis = prompts.render("agent.belief_emphasis", beliefs=beliefs_text)
        length_instruction = prompts.get_agent_length_instruction(min_sentences=3, max_sentences=8)
        language_instruction = prompts.get(f"language.instruction.{self.language}", "")
        materials = prompts.render("agent.materials_block", materials=self.materials) if self.materials else ""
        return (base_prompt + belief_emphasis + self.initial_position + materials
                + length_instruction + language_instruction)

    async def _prepare_response(self, prompt: str, context: List[Message] = None):
        """응답 준비 - CoT, RAG, 프롬프트 생성 공통 로직"""
        prompts = config_loader.prompts
        config = self.config

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

        # 최근 발언을 충분히 길게 전달 (짧게 자르면 상대 논지의 근거·결론을 볼 수 없음)
        if context:
            for msg in context[-config.context_messages:]:
                seq = msg.metadata.get("seq")
                label = f"{msg.agent_name} (#{seq})" if seq else msg.agent_name
                messages.append(HumanMessage(content=f"{label}: {msg.content[:config.context_chars]}"))

        messages.append(HumanMessage(content=prompt))
        return messages

    async def respond(self, prompt: str, context: List[Message] = None) -> str:
        """응답 생성 (비스트리밍)"""
        messages = await self._prepare_response(prompt, context)
        response = await self.llm.ainvoke(messages)
        self.statement_count += 1
        return response.text  # 텍스트만 (적응형 사고 모델은 content가 블록 목록)

    async def respond_stream(self, prompt: str, context: List[Message] = None) -> AsyncIterator[str]:
        """스트리밍 응답 생성"""
        messages = await self._prepare_response(prompt, context)
        async for chunk in self.llm.astream(messages):
            chunk_text = chunk.text  # 텍스트 조각만 (thinking 블록 제외)
            if chunk_text:
                yield chunk_text
        self.statement_count += 1
