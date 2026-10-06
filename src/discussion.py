"""
토론 시스템 v2 - 리팩토링된 버전
자연스러운 토론만 지원, 모듈화된 구조
"""
from typing import List, Optional
from src.models.personas import Message, Persona, LLMProvider
from src.core.agent import DiscussionAgent
from src.core.moderator import DiscussionModerator
from src.core.natural_discussion import NaturalDiscussion


class Discussion:
    """토론 시스템 메인 클래스 (호환성 유지)"""
    
    def __init__(self, agents: List[DiscussionAgent], use_moderator: bool = True,
                 max_statements: int = 20):
        """
        Args:
            agents: 토론 참가자 리스트
            use_moderator: 모더레이터 사용 여부
            max_statements: 최대 발언 수
        """
        self.agents = agents
        self.use_moderator = use_moderator
        self.max_statements = max_statements
        
        # 모더레이터 생성
        self.moderator = DiscussionModerator() if use_moderator else None
        
        # 자연스러운 토론 시스템 (max_statements 전달)
        self.discussion_system = NaturalDiscussion(agents, self.moderator, max_statements)
        
        # 호환성을 위한 속성
        self.discussion_history = []
    
    async def run(self, 
                  topic: str, 
                  rounds: Optional[int] = None,  # 무시됨 (자연스러운 흐름)
                  streaming: bool = True,
                  language: Optional[str] = None,
                  contexts: Optional[List[str]] = None,
                  dynamic_mode: bool = True,  # 항상 동적 모드
                  max_statements: int = 20) -> List[Message]:
        """
        토론 실행
        
        Args:
            topic: 토론 주제
            rounds: (무시됨) 자연스러운 흐름으로 진행
            streaming: 스트리밍 출력 여부
            language: 언어 설정
            contexts: 배경 정보
            dynamic_mode: (무시됨) 항상 자연스러운 모드
            max_statements: 최대 발언 수
            
        Returns:
            토론 메시지 리스트
        """
        
        # 자연스러운 토론 실행 (이미 초기화 시 max_statements 설정됨)
        messages = await self.discussion_system.run(
            topic=topic,
            max_turns=max_statements or self.max_statements,
            language=language,
            contexts=contexts,
            streaming=streaming
        )
        
        self.discussion_history = messages
        return messages

    async def run_streaming(self,
                  topic: str,
                  max_statements: int = 20,
                  language: Optional[str] = None,
                  contexts: Optional[List[str]] = None):
        """
        토론 실행 - 스트리밍 버전 (메시지를 yield)

        Args:
            topic: 토론 주제
            max_statements: 최대 발언 수
            language: 언어 설정
            contexts: 배경 정보

        Yields:
            메시지 (Message 객체)
        """
        # 자연스러운 토론 실행 - 스트리밍 모드
        async for message in self.discussion_system.run_streaming(
            topic=topic,
            max_statements=max_statements or self.max_statements,
            language=language,
            contexts=contexts
        ):
            self.discussion_history.append(message)
            yield message


# 기존 코드와 호환성을 위한 별칭
DiscussionAgent = DiscussionAgent  # 이미 정의됨


def create_discussion(personas: List[Persona], 
                     provider: LLMProvider = LLMProvider.OPENAI,
                     use_moderator: bool = True,
                     enable_web_search: bool = True,
                     max_statements: int = 20) -> Discussion:
    """
    페르소나 리스트로부터 토론 생성 (헬퍼 함수)
    
    Args:
        personas: 페르소나 리스트
        provider: LLM 제공자
        use_moderator: 모더레이터 사용 여부
        enable_web_search: 웹 검색 활성화 여부
        max_statements: 최대 발언 수
        
    Returns:
        Discussion 인스턴스
    """
    agents = [
        DiscussionAgent(
            persona, 
            provider=provider, 
            track_evolution=True,
            enable_web_search=enable_web_search
        )
        for persona in personas
    ]
    
    return Discussion(agents, use_moderator=use_moderator, max_statements=max_statements)