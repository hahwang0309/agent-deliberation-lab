"""
RAG (Retrieval-Augmented Generation) Service
페르소나 기반 질문 생성, 라우팅, 검색, 요약을 통합 관리
"""
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from enum import Enum
import yaml
from pathlib import Path
from src.models.personas import Persona, Message
from src.utils.llm_provider import LLMFactory
from src.services.web_search import WebSearchService
from langchain_core.messages import SystemMessage, HumanMessage
import os
import logging


logger = logging.getLogger(__name__)


class QueryType(Enum):
    """질문 유형 분류"""
    FACTUAL = "factual"      # 사실 확인 필요
    OPINION = "opinion"       # 의견/철학적 질문
    

@dataclass
class QueryResult:
    """질문 생성 결과"""
    query: str
    query_type: QueryType
    persona_context: str


@dataclass
class RAGResult:
    """RAG 처리 결과"""
    query: str
    evidence: Optional[str]
    sources: List[str]
    summary: str


class RAGPromptLoader:
    """RAG 프롬프트 로더"""
    
    def __init__(self, prompts_path: str = None):
        if prompts_path is None:
            base_dir = Path(__file__).parent.parent.parent
            prompts_path = base_dir / 'config' / 'rag_prompts.yaml'
        
        with open(prompts_path, 'r', encoding='utf-8') as f:
            self.prompts = yaml.safe_load(f)
    
    def get_query_generation_prompts(self):
        """질문 생성 프롬프트 반환"""
        return (
            self.prompts['query_generation']['system'],
            self.prompts['query_generation']['user_template']
        )
    
    def get_classification_prompts(self):
        """분류 프롬프트 반환"""
        return (
            self.prompts['query_classification']['system'],
            self.prompts['query_classification']['user_template']
        )
    
    def get_extraction_prompts(self):
        """추출 프롬프트 반환"""
        return (
            self.prompts['evidence_extraction']['system'],
            self.prompts['evidence_extraction']['user_template']
        )
    
    def get_response_text(self, key: str, **kwargs):
        """응답 텍스트 반환"""
        text = self.prompts['rag_responses'].get(key, "")
        return text.format(**kwargs) if kwargs else text
    
    def get_context_settings(self):
        """컨텍스트 설정 반환"""
        return self.prompts['context_settings']


class QueryGenerator:
    """페르소나 기반 질문 생성기"""
    
    def __init__(self, llm=None):
        from src.models.personas import LLMProvider
        self.llm = llm or LLMFactory.create_llm(None, temperature=0.3)
        self.prompt_loader = RAGPromptLoader()
    
    async def generate_persona_query(
        self, 
        topic: str, 
        persona: Persona,
        context: Optional[List[Message]] = None
    ) -> QueryResult:
        """페르소나의 관점에서 핵심 질문 생성"""
        
        settings = self.prompt_loader.get_context_settings()
        
        # 컨텍스트 요약
        context_summary = "This is the beginning of the discussion."
        if context and len(context) > 0:
            recent = context[-settings['max_recent_messages']:]
            context_summary = "\n".join([
                f"- {m.agent_name or 'Unknown'}: {m.content[:settings['max_message_length']]}..."
                for m in recent
            ])
        
        # 프롬프트 템플릿 가져오기
        system_prompt, user_template = self.prompt_loader.get_query_generation_prompts()
        
        # 템플릿 채우기
        user_prompt = user_template.format(
            name=persona.name,
            role=persona.role,
            expertise=', '.join(persona.expertise),
            background=persona.background,
            beliefs=', '.join(persona.beliefs[:2]),
            topic=topic,
            context_summary=context_summary
        )

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt)
        ]
        
        response = await self.llm.ainvoke(messages)
        content = response.text
        
        # Parse response
        query = ""
        query_type = QueryType.OPINION
        rationale = ""
        
        if "QUESTION:" in content:
            query = content.split("QUESTION:")[1].split("\n")[0].strip()
        if "TYPE:" in content:
            type_str = content.split("TYPE:")[1].split("\n")[0].strip().upper()
            query_type = QueryType.FACTUAL if "FACT" in type_str else QueryType.OPINION
        if "RATIONALE:" in content:
            rationale = content.split("RATIONALE:")[1].strip()
        
        return QueryResult(
            query=query,
            query_type=query_type,
            persona_context=rationale
        )


class QueryRouter:
    """질문 라우터 - LLM 기반 지능적 분류"""
    
    def __init__(self, llm=None):
        from src.models.personas import LLMProvider
        self.llm = llm or LLMFactory.create_llm(None, temperature=0.1)  # 낮은 temperature로 일관성 확보
        self.prompt_loader = RAGPromptLoader()
    
    async def classify_query(self, query: str, topic: str = "") -> QueryType:
        """LLM을 사용한 질문 유형 분류"""
        
        system_prompt, user_template = self.prompt_loader.get_classification_prompts()
        
        user_prompt = user_template.format(
            query=query,
            topic=topic if topic else "general discussion"
        )
        
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt)
        ]
        
        response = await self.llm.ainvoke(messages)
        result = response.text.strip().upper()
        
        # 분류 결과 파싱
        if "FACTUAL" in result:
            return QueryType.FACTUAL
        else:
            return QueryType.OPINION
    
    async def needs_search(self, query_result: QueryResult, topic: str = "") -> bool:
        """웹 검색 필요 여부"""
        # QueryGenerator의 분류를 우선 신뢰
        if query_result.query_type == QueryType.FACTUAL:
            return True
        
        # 불확실한 경우 재분류
        classification = await self.classify_query(query_result.query, topic)
        return classification == QueryType.FACTUAL


class RAGService:
    """통합 RAG 서비스"""
    
    def __init__(self, llm=None):
        self.query_generator = QueryGenerator(llm)
        self.query_router = QueryRouter(llm)
        self.web_search = WebSearchService() if os.getenv("TAVILY_API_KEY") else None
        from src.models.personas import LLMProvider
        self.llm = llm or LLMFactory.create_llm(None, temperature=0.3)
        self.prompt_loader = RAGPromptLoader()
        self.cache = RAGCache()  # 캐싱 활성화
        
    async def process(
        self,
        topic: str,
        persona: Persona,
        context: Optional[List[Message]] = None
    ) -> RAGResult:
        """RAG 파이프라인 실행"""
        
        # 1. 페르소나 기반 질문 생성
        query_result = await self.query_generator.generate_persona_query(
            topic, persona, context
        )
        
        # 캐시 확인
        cached = self.cache.get(query_result.query)
        if cached:
            return cached
        
        # 2. 라우팅 결정
        needs_search = await self.query_router.needs_search(query_result, topic)
        
        if not needs_search:
            # 검색 불필요 - 빈 결과 반환
            result = RAGResult(
                query=query_result.query,
                evidence=None,
                sources=[],
                summary=self.prompt_loader.get_response_text('no_search_needed')
            )
            self.cache.set(query_result.query, result)
            return result
        
        # 3. 웹 검색 실행
        if not self.web_search or not self.web_search.enabled:
            result = RAGResult(
                query=query_result.query,
                evidence=None,
                sources=[],
                summary=self.prompt_loader.get_response_text('no_api_key')
            )
            self.cache.set(query_result.query, result)
            return result
        
        try:
            settings = self.prompt_loader.get_context_settings()
            search_results = await self.web_search.search(
                query_result.query, 
                max_results=settings['max_search_results']
            )
            
            if not search_results:
                result = RAGResult(
                    query=query_result.query,
                    evidence=None,
                    sources=[],
                    summary=self.prompt_loader.get_response_text('no_results')
                )
                self.cache.set(query_result.query, result)
                return result
            
            # 4. 결과 필터링 및 요약
            evidence = await self._extract_and_summarize(
                search_results,
                query_result.query,
                persona
            )
            
            # 5. 소스 추출 - SearchResult 객체 처리
            sources = []
            for result in search_results:
                if hasattr(result, 'url'):
                    sources.append(result.url)
                elif isinstance(result, dict):
                    sources.append(result.get('url', 'Unknown source'))
                else:
                    sources.append('Unknown source')
            
            result = RAGResult(
                query=query_result.query,
                evidence=evidence,
                sources=sources,
                summary=evidence if evidence else self.prompt_loader.get_response_text('no_results')
            )
            
            self.cache.set(query_result.query, result)
            return result
            
        except Exception as e:
            logger.warning("RAG search error: %s", e)
            return RAGResult(
                query=query_result.query,
                evidence=None,
                sources=[],
                summary=self.prompt_loader.get_response_text('search_error', error=str(e))
            )
    
    async def _extract_and_summarize(
        self,
        search_results: List[Dict],
        query: str,
        persona: Persona
    ) -> str:
        """검색 결과에서 핵심 정보 추출 및 요약"""
        
        settings = self.prompt_loader.get_context_settings()
        
        # 검색 결과 텍스트 결합 - SearchResult 객체 처리
        combined_text = ""
        for r in search_results[:settings['max_search_results']]:
            if hasattr(r, 'title') and hasattr(r, 'content'):
                # SearchResult 객체
                title = r.title or 'Unknown'
                content = r.content[:settings['max_result_content']] if r.content else ''
            elif isinstance(r, dict):
                # Dictionary
                title = r.get('title', 'Unknown')
                content = r.get('content', '')[:settings['max_result_content']]
            else:
                continue
            combined_text += f"Source: {title}\n{content}\n\n"
        
        # 프롬프트 템플릿 가져오기
        system_prompt, user_template = self.prompt_loader.get_extraction_prompts()
        
        user_prompt = user_template.format(
            name=persona.name,
            role=persona.role,
            query=query,
            search_results=combined_text
        )

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt)
        ]
        
        response = await self.llm.ainvoke(messages)
        return response.text


class RAGCache:
    """RAG 결과 캐싱"""
    
    def __init__(self, ttl_seconds: int = 300):
        self.cache: Dict[str, RAGResult] = {}
        self.timestamps: Dict[str, float] = {}
        self.ttl = ttl_seconds
    
    def get(self, query: str) -> Optional[RAGResult]:
        """캐시에서 결과 조회"""
        import time
        
        if query in self.cache:
            # TTL 확인
            if time.time() - self.timestamps[query] < self.ttl:
                return self.cache[query]
            else:
                # 만료된 캐시 삭제
                del self.cache[query]
                del self.timestamps[query]
        return None
    
    def set(self, query: str, result: RAGResult):
        """캐시에 결과 저장"""
        import time
        self.cache[query] = result
        self.timestamps[query] = time.time()
    
    def clear(self):
        """캐시 전체 삭제"""
        self.cache.clear()
        self.timestamps.clear()