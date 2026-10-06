"""
Web Search Service using Tavily API
에이전트와 모더레이터가 웹에서 실제 정보를 검색하여 활용
"""
import os
import asyncio
from typing import List, Dict, Optional
from dataclasses import dataclass
import aiohttp
import json
from datetime import datetime
import hashlib


@dataclass
class SearchResult:
    """검색 결과"""
    title: str
    url: str
    content: str
    score: float
    published_date: Optional[str] = None


class WebSearchService:
    """웹 검색 서비스 - Tavily API 사용"""
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Args:
            api_key: Tavily API key
        """
        self.api_key = api_key or os.getenv("TAVILY_API_KEY")
        if not self.api_key:
            print("Warning: TAVILY_API_KEY not found. Web search will be disabled.")
            self.enabled = False
        else:
            self.enabled = True
            
        self.base_url = "https://api.tavily.com"
        self.search_cache = {}  # 간단한 캐시
        
    async def search(
        self, 
        query: str, 
        max_results: int = 3,
        search_depth: str = "basic",  # basic or advanced
        include_domains: List[str] = None,
        exclude_domains: List[str] = None
    ) -> List[SearchResult]:
        """
        웹 검색 수행
        
        Args:
            query: 검색 쿼리
            max_results: 최대 결과 수
            search_depth: 검색 깊이 (basic/advanced)
            include_domains: 포함할 도메인
            exclude_domains: 제외할 도메인
            
        Returns:
            검색 결과 리스트
        """
        if not self.enabled:
            return []
            
        # 캐시 확인
        cache_key = self._get_cache_key(query, max_results)
        if cache_key in self.search_cache:
            cached_time, cached_results = self.search_cache[cache_key]
            # 5분 이내 캐시는 재사용
            if (datetime.now() - cached_time).seconds < 300:
                return cached_results
        
        try:
            # Tavily API 호출
            async with aiohttp.ClientSession() as session:
                payload = {
                    "api_key": self.api_key,
                    "query": query,
                    "max_results": max_results,
                    "search_depth": search_depth,
                    "include_answer": True,
                    "include_raw_content": False,
                    "include_images": False
                }
                
                if include_domains:
                    payload["include_domains"] = include_domains
                if exclude_domains:
                    payload["exclude_domains"] = exclude_domains
                
                async with session.post(
                    f"{self.base_url}/search",
                    json=payload,
                    headers={"Content-Type": "application/json"}
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        results = self._parse_results(data)
                        
                        # 캐시 저장
                        self.search_cache[cache_key] = (datetime.now(), results)
                        
                        return results
                    else:
                        print(f"Search API error: {response.status}")
                        return []
                        
        except Exception as e:
            print(f"Search error: {e}")
            return []
    
    async def fact_check(self, statement: str) -> Dict:
        """
        사실 확인
        
        Args:
            statement: 확인할 진술
            
        Returns:
            사실 확인 결과
        """
        if not self.enabled:
            return {
                "verified": False,
                "confidence": 0.0,
                "sources": [],
                "summary": "Web search disabled"
            }
        
        # 사실 확인을 위한 쿼리 구성
        query = f"fact check verify {statement}"
        
        results = await self.search(
            query, 
            max_results=5,
            search_depth="advanced",
            include_domains=["snopes.com", "factcheck.org", "politifact.com", 
                           "reuters.com", "apnews.com", "bbc.com", "npr.org"]
        )
        
        if not results:
            return {
                "verified": False,
                "confidence": 0.0,
                "sources": [],
                "summary": "No reliable sources found"
            }
        
        # 결과 분석
        supporting = 0
        refuting = 0
        sources = []
        
        for result in results:
            content_lower = result.content.lower()
            
            # 지지/반박 키워드 분석
            support_keywords = ["true", "verified", "correct", "confirmed", "accurate", "fact"]
            refute_keywords = ["false", "incorrect", "misleading", "debunked", "myth", "unfounded"]
            
            support_score = sum(1 for kw in support_keywords if kw in content_lower)
            refute_score = sum(1 for kw in refute_keywords if kw in content_lower)
            
            if support_score > refute_score:
                supporting += 1
            elif refute_score > support_score:
                refuting += 1
                
            sources.append({
                "title": result.title,
                "url": result.url,
                "excerpt": result.content[:200]
            })
        
        # 신뢰도 계산
        total = supporting + refuting
        if total > 0:
            confidence = supporting / total
            verified = confidence > 0.6
        else:
            confidence = 0.5
            verified = False
        
        summary = f"Found {supporting} supporting and {refuting} refuting sources."
        if verified:
            summary += " Statement appears to be accurate based on available sources."
        elif refuting > supporting:
            summary += " Statement appears to be questionable or false based on available sources."
        else:
            summary += " Unable to definitively verify the statement."
        
        return {
            "verified": verified,
            "confidence": confidence,
            "sources": sources[:3],
            "summary": summary
        }
    
    async def get_expert_info(self, topic: str, aspect: str = None) -> Dict:
        """
        전문가 정보 및 연구 검색
        
        Args:
            topic: 주제
            aspect: 특정 측면
            
        Returns:
            전문 정보
        """
        if not self.enabled:
            return {
                "studies": [],
                "statistics": [],
                "expert_views": []
            }
        
        # 학술/전문 소스 우선 검색
        query = f"{topic} research study statistics data"
        if aspect:
            query = f"{topic} {aspect} research study data"
        
        results = await self.search(
            query,
            max_results=5,
            search_depth="advanced",
            include_domains=["scholar.google.com", "pubmed.ncbi.nlm.nih.gov", 
                           "nature.com", "science.org", "pew.org", "brookings.edu",
                           "rand.org", "nber.org", "worldbank.org"]
        )
        
        studies = []
        statistics = []
        expert_views = []
        
        for result in results:
            content = result.content
            
            # 연구/통계 추출
            import re
            
            # 퍼센트 데이터
            percent_matches = re.findall(r'(\d+(?:\.\d+)?%[^.]*\.)', content)
            for match in percent_matches[:2]:
                statistics.append(match.strip())
            
            # 연구 언급
            if any(kw in content.lower() for kw in ["study", "research", "survey", "analysis"]):
                studies.append({
                    "source": result.title,
                    "finding": content[:200],
                    "url": result.url
                })
            
            # 전문가 의견
            if any(kw in content.lower() for kw in ["expert", "professor", "researcher", "analyst"]):
                expert_views.append({
                    "source": result.title,
                    "view": content[:150]
                })
        
        return {
            "studies": studies[:3],
            "statistics": statistics[:5],
            "expert_views": expert_views[:2]
        }
    
    async def search_for_examples(self, concept: str, context: str = None) -> List[str]:
        """
        구체적 예시 검색
        
        Args:
            concept: 개념
            context: 맥락
            
        Returns:
            예시 리스트
        """
        if not self.enabled:
            return []
        
        query = f"{concept} real world examples cases"
        if context:
            query = f"{concept} {context} examples cases implementation"
        
        results = await self.search(query, max_results=3)
        
        examples = []
        for result in results:
            # 예시 패턴 찾기
            content = result.content
            
            # "For example", "For instance", "Such as" 등으로 시작하는 문장
            import re
            example_patterns = [
                r'[Ff]or example[,:]([^.]+)',
                r'[Ff]or instance[,:]([^.]+)',
                r'[Ss]uch as([^.]+)',
                r'[Ii]ncluding([^.]+)',
                r'[Cc]ase study[:]([^.]+)'
            ]
            
            for pattern in example_patterns:
                matches = re.findall(pattern, content)
                for match in matches:
                    example = match.strip()
                    if len(example) > 20 and example not in examples:
                        examples.append(example)
        
        return examples[:5]
    
    def _parse_results(self, data: Dict) -> List[SearchResult]:
        """API 응답 파싱"""
        results = []
        
        if "results" in data:
            for item in data["results"]:
                result = SearchResult(
                    title=item.get("title", ""),
                    url=item.get("url", ""),
                    content=item.get("content", ""),
                    score=item.get("score", 0.0),
                    published_date=item.get("published_date")
                )
                results.append(result)
        
        return results
    
    def _get_cache_key(self, query: str, max_results: int) -> str:
        """캐시 키 생성"""
        key_str = f"{query}_{max_results}"
        return hashlib.md5(key_str.encode()).hexdigest()
    
    def format_search_results(self, results: List[SearchResult]) -> str:
        """검색 결과 포맷팅"""
        if not results:
            return "No search results found."
        
        formatted = []
        for i, result in enumerate(results, 1):
            formatted.append(f"{i}. {result.title}")
            formatted.append(f"   {result.content[:150]}...")
            formatted.append(f"   Source: {result.url}")
            formatted.append("")
        
        return "\n".join(formatted)