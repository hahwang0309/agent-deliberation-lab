"""
자연스러운 토론 시스템 - 동적 턴 관리
"""
from typing import List, Optional
from enum import Enum
import random
from src.models.personas import Message
from src.core.agent import DiscussionAgent
from src.core.moderator import DiscussionModerator
from src.models.consensus_tracker import ConsensusTracker
from src.utils.language_detector import LanguageDetector
from src.services.discussion_manager import DiscussionManager
from src.services.report_generator import ReportGenerator
from rich.console import Console
from rich.panel import Panel
from rich.live import Live
from config.discussion_config import get_config

console = Console()


class ActionType(Enum):
    """발화 액션 타입"""
    PRESENT = "present"        # 새로운 관점 제시
    RESPOND = "respond"        # 직접 응답
    BUILD = "build"           # 동의하며 확장
    CHALLENGE = "challenge"    # 도전/반박
    EXAMPLE = "example"       # 구체적 예시
    SYNTHESIZE = "synthesize" # 종합
    # QUESTION 제거 - 질문은 모더레이터만 하도록


class NaturalDiscussion:
    """자연스러운 토론 시스템"""
    
    def __init__(self, agents: List[DiscussionAgent], moderator: Optional[DiscussionModerator] = None,
                 max_statements: int = 20):
        self.agents = agents
        self.moderator = moderator
        self.messages = []
        
        # 토론 상태 추적
        self.turn_count = 0
        self.agent_turn_count = {agent.persona.name: 0 for agent in agents}
        self.last_speakers = []  # 최근 발언자 추적
        
        # 토론 품질 추적
        self.consensus_tracker = ConsensusTracker()
        self.discussion_depth = 0
        self.key_insights = []
        
        # 설정 로드
        self.config = get_config()
        
        # 토론 관리자
        self.discussion_manager = DiscussionManager(max_statements)
        
        # 보고서 생성기
        self.report_generator = ReportGenerator()
        
    async def run(self, topic: str, max_turns: int = 20, 
                  language: Optional[str] = None, 
                  contexts: Optional[List[str]] = None,
                  streaming: bool = True) -> List[Message]:
        """자연스러운 토론 실행"""
        
        # 언어 설정
        if not language:
            language = LanguageDetector.detect_language(topic)
        
        for agent in self.agents:
            agent.language = language
        
        # 모더레이터 설정 및 소주제 생성
        subtopics_discussed = []
        if self.moderator:
            self.moderator.language = language
            subtopics = await self.moderator.generate_subtopics(topic)
            
            # Discussion Manager에 소주제 설정
            if subtopics:
                self.discussion_manager.set_subtopics(subtopics)
                console.print("\n[bold cyan]📋 Discussion Framework:[/bold cyan]")
                for i, sub in enumerate(subtopics, 1):
                    console.print(f"  {i}. {sub}")
                console.print()
        
        # 컨텍스트 표시
        if contexts:
            console.print("[bold yellow]📚 Background Context:[/bold yellow]")
            for ctx in contexts[:2]:
                console.print(f"  • {ctx[:100]}...")
            console.print()
        
        console.print(f"\n[bold cyan]💬 Natural Discussion Starting[/bold cyan]")
        console.print(f"Topic: {topic}")
        console.print(f"Participants: {', '.join([a.persona.name for a in self.agents])}\n")
        
        # 메인 토론 루프
        while self.turn_count < max_turns and self.discussion_manager.get_remaining_statements() > 0:
            # 다음 발언자와 액션 결정
            speaker, action = await self._select_next_speaker()
            
            if not speaker:
                break
            
            # 프롬프트 생성
            prompt = await self._generate_prompt(topic, speaker, action)
            
            # 응답 생성
            response = await self._generate_response(speaker, prompt, action, streaming)
            
            # 메시지 저장
            msg = Message(
                role="assistant",
                content=response,
                agent_name=speaker.persona.name,
                metadata={"action": action.value, "turn": self.turn_count}
            )
            self.messages.append(msg)
            
            # 상태 업데이트
            self._update_state(speaker, response)
            
            # Discussion Manager 업데이트
            if self.moderator and self.moderator.current_subtopic_idx < len(self.moderator.subtopics):
                current_sub = self.moderator.subtopics[self.moderator.current_subtopic_idx]
                is_abstract = self.discussion_manager.check_statement_abstractness(response)
                self.discussion_manager.update_topic_status(current_sub, response, is_abstract)
                if current_sub not in subtopics_discussed:
                    subtopics_discussed.append(current_sub)
            self.discussion_manager.increment_turn()
            
            # 진화 처리
            await self._process_evolution(speaker, response, topic)
            
            # 모더레이터 개입 체크
            if self.moderator and await self._should_moderator_intervene():
                await self._moderator_intervention(topic)
            
            self.turn_count += 1
        
        # 마무리
        console.print("\n" + "="*80)
        console.print("[bold magenta]🎬 DISCUSSION COMPLETED[/bold magenta]")
        console.print("="*80 + "\n")
        
        # 간단한 통계만
        console.print("[bold green]✅ Discussion concluded successfully[/bold green]")
        console.print(f"📊 Total turns: {self.turn_count}")
        console.print(f"💬 Total messages: {len(self.messages)}")
        console.print(f"🎯 Topics covered: {len(self.moderator.subtopics) if self.moderator else 0}")
        
        return self.messages

    async def run_streaming(self, topic: str, max_statements: int = 20,
                  language: Optional[str] = None,
                  contexts: Optional[List[str]] = None):
        """자연스러운 토론 실행 - 스트리밍 버전 (메시지를 yield)"""
        max_turns = max_statements

        # 언어 설정
        if not language:
            language = LanguageDetector.detect_language(topic)

        for agent in self.agents:
            agent.language = language

        # 모더레이터 설정 및 소주제 생성
        subtopics_discussed = []
        if self.moderator:
            self.moderator.language = language
            subtopics = await self.moderator.generate_subtopics(topic)

            # Discussion Manager에 소주제 설정
            if subtopics:
                self.discussion_manager.set_subtopics(subtopics)
                console.print("\n[bold cyan]📋 Discussion Framework:[/bold cyan]")
                for i, sub in enumerate(subtopics, 1):
                    console.print(f"  {i}. {sub}")
                console.print()

        # 컨텍스트 표시
        if contexts:
            console.print("[bold yellow]📚 Background Context:[/bold yellow]")
            for ctx in contexts[:2]:
                console.print(f"  • {ctx[:100]}...")
            console.print()

        console.print(f"\n[bold cyan]💬 Natural Discussion Starting[/bold cyan]")
        console.print(f"Topic: {topic}")
        console.print(f"Participants: {', '.join([a.persona.name for a in self.agents])}\n")

        # 메인 토론 루프
        while self.turn_count < max_turns and self.discussion_manager.get_remaining_statements() > 0:
            # 다음 발언자와 액션 결정
            speaker, action = await self._select_next_speaker()

            if not speaker:
                break

            # 프롬프트 생성
            prompt = await self._generate_prompt(topic, speaker, action)

            # 응답 생성 - 청크 단위로 yield
            response_text = ""
            async for chunk_data in self._generate_response_chunks(speaker, prompt, action):
                if chunk_data["type"] == "chunk":
                    response_text += chunk_data["chunk"]
                    # 청크를 즉시 yield
                    chunk_msg = Message(
                        role="assistant",
                        content=chunk_data["chunk"],
                        agent_name=speaker.persona.name,
                        metadata={
                            "is_chunk": True,
                            "accumulated_text": response_text,
                            "action": action.value,
                            "turn": self.turn_count
                        }
                    )
                    yield chunk_msg
                elif chunk_data["type"] == "complete":
                    # 최종 완성 메시지
                    final_msg = Message(
                        role="assistant",
                        content=response_text,
                        agent_name=speaker.persona.name,
                        metadata={
                            "is_chunk": False,
                            "is_complete": True,
                            "action": action.value,
                            "turn": self.turn_count,
                            "rag_used": speaker.last_rag_result is not None if hasattr(speaker, 'last_rag_result') else False,
                            "rag_query": speaker.last_rag_result.query if hasattr(speaker, 'last_rag_result') and speaker.last_rag_result else None,
                            "sources": speaker.last_rag_result.sources if hasattr(speaker, 'last_rag_result') and speaker.last_rag_result else None
                        }
                    )
                    self.messages.append(final_msg)
                    yield final_msg
                    response = response_text

            # 상태 업데이트
            self._update_state(speaker, response)

            # Discussion Manager 업데이트
            if self.moderator and self.moderator.current_subtopic_idx < len(self.moderator.subtopics):
                current_sub = self.moderator.subtopics[self.moderator.current_subtopic_idx]
                is_abstract = self.discussion_manager.check_statement_abstractness(response)
                self.discussion_manager.update_topic_status(current_sub, response, is_abstract)
                if current_sub not in subtopics_discussed:
                    subtopics_discussed.append(current_sub)
            self.discussion_manager.increment_turn()

            # 진화 처리
            await self._process_evolution(speaker, response, topic)

            # 모더레이터 개입 체크
            should_intervene = await self._should_moderator_intervene()
            console.print(f"[dim]Turn {self.turn_count}: Moderator check = {should_intervene}[/dim]")

            if self.moderator and should_intervene:
                console.print("[yellow]🎙️  MODERATOR INTERVENING...[/yellow]")
                moderator_msg = await self._moderator_intervention_streaming(topic)
                if moderator_msg:
                    yield moderator_msg

            self.turn_count += 1

        # 마무리
        console.print("\n" + "="*80)
        console.print("[bold magenta]🎬 DISCUSSION COMPLETED[/bold magenta]")
        console.print("="*80 + "\n")

        # 간단한 통계만
        console.print("[bold green]✅ Discussion concluded successfully[/bold green]")
        console.print(f"📊 Total turns: {self.turn_count}")
        console.print(f"💬 Total messages: {len(self.messages)}")
        console.print(f"🎯 Topics covered: {len(self.moderator.subtopics) if self.moderator else 0}")

    async def _select_next_speaker(self) -> tuple[Optional[DiscussionAgent], Optional[ActionType]]:
        """다음 발언자와 액션 선택 - 자연스러운 흐름"""
        
        # 발언 가능한 에이전트
        eligible = [a for a in self.agents 
                   if self.agent_turn_count[a.persona.name] < self.config.max_turns_per_agent]
        
        if not eligible:
            return None, None
        
        # 최근 발언자 제외 (연속 발언 방지)
        if self.last_speakers:
            eligible = [a for a in eligible 
                       if a.persona.name not in self.last_speakers[-1:]]
        
        if not eligible:
            eligible = self.agents
        
        # 토론 진행도에 따른 액션 결정
        max_turns = self.discussion_manager.max_statements
        progress = self.turn_count / max_turns if max_turns > 0 else 0
        
        if self.turn_count == 0:
            # 첫 발언
            action = ActionType.PRESENT
            speaker = random.choice(eligible)
        elif progress < 0.3:
            # 초반: 다양한 관점 제시
            action = random.choices(
                [ActionType.PRESENT, ActionType.EXAMPLE],
                weights=[0.7, 0.3]
            )[0]
            speaker = min(eligible, key=lambda a: self.agent_turn_count[a.persona.name])
        elif progress < 0.7:
            # 중반: 상호작용과 심화
            # 건설적 확장 선호 (설정에 따라)
            build_weight = self.config.prefer_building_over_challenging
            challenge_weight = 1.0 - build_weight
            action = random.choices(
                [ActionType.RESPOND, ActionType.BUILD, ActionType.CHALLENGE, ActionType.EXAMPLE],
                weights=[0.3, build_weight * 0.4, challenge_weight * 0.2, 0.2]
            )[0]
            
            # 가장 적게 말한 사람 우선
            speaker = min(eligible, key=lambda a: self.agent_turn_count[a.persona.name])
        else:
            # 후반: 종합과 정리
            action = random.choices(
                [ActionType.SYNTHESIZE, ActionType.BUILD],
                weights=[0.6, 0.4]
            )[0]
            speaker = random.choice(eligible)
        
        return speaker, action
    
    async def _generate_prompt(self, topic: str, speaker: DiscussionAgent, action: ActionType) -> str:
        """액션에 맞는 프롬프트 생성"""
        
        # 현재 소주제
        current_sub = ""
        if self.moderator and self.moderator.current_subtopic_idx < len(self.moderator.subtopics):
            current_sub = self.moderator.subtopics[self.moderator.current_subtopic_idx]
        
        # 최근 발언 요약
        recent_context = ""
        if self.messages:
            recent = self.messages[-2:]
            recent_context = "\nRecent points:\n"
            for msg in recent:
                recent_context += f"- {msg.agent_name}: {msg.content[:100]}...\n"
        
        # 액션별 프롬프트
        if action == ActionType.PRESENT:
            prompt = f"""Topic: {topic}
{f"Current focus: {current_sub}" if current_sub else ""}

Share YOUR unique perspective based on your expertise and experience.
What specific insight do you bring that others might not see?
Be concrete and grounded in your professional background."""
            
        elif action == ActionType.RESPOND:
            target = self.messages[-1] if self.messages else None
            prompt = f"""{target.agent_name if target else "Someone"} said: "{target.content[:150] if target else topic}..."

Directly address this point from YOUR perspective.
How does your background lead you to agree or disagree?"""
            
        elif action == ActionType.BUILD:
            target = self.messages[-1] if self.messages else None
            prompt = f"""{target.agent_name if target else "The group"}'s point about "{target.content[:100] if target else topic}..." is valuable.

Agree with this and extend it further based on your expertise.
What additional dimension or implication do you see?"""
            
        elif action == ActionType.CHALLENGE:
            target = self._find_challengeable_point()
            prompt = f"""Consider {target.agent_name if target else "the"} claim: "{target.content[:100] if target else topic}..."

What specific concerns, risks, or limitations do you identify based on your expertise?
Respectfully challenge this with evidence-based reasoning."""
            
        elif action == ActionType.EXAMPLE:
            prompt = f"""Topic: {topic}
{recent_context}

Provide a SPECIFIC example or case from your experience/expertise.
Make it concrete and detailed, not abstract."""
            
        else:  # SYNTHESIZE
            prompt = f"""Topic: {topic}

Synthesize the discussion so far from YOUR perspective.
What patterns do you see? What remains unresolved?
What evidence and reasoning lead to your conclusion?"""
        
        return prompt
    
    def _update_state(self, speaker: DiscussionAgent, response: str):
        """토론 상태 업데이트"""
        self.agent_turn_count[speaker.persona.name] += 1
        self.last_speakers.append(speaker.persona.name)
        if len(self.last_speakers) > 3:
            self.last_speakers.pop(0)
        
        # 모더레이터 업데이트 (제거됨 - discussion_manager가 관리)
        
        # 합의 추적
        self.consensus_tracker.track_statement(speaker.persona.name, response, "")
        
        # 깊이 추적
        if any(marker in response.lower() for marker in 
               ["specifically", "for example", "research shows", "구체적으로"]):
            self.discussion_depth += 1
    
    async def _process_evolution(self, speaker: DiscussionAgent, response: str, topic: str):
        """페르소나 진화 처리"""
        evolution_log = []
        
        for agent in self.agents:
            if agent != speaker:
                change = agent.process_other_argument(response[:500], speaker.persona.name, topic)
                if change and change.get('position_changed'):
                    evolution_log.append(f"[yellow]🔄 {agent.persona.name} shifted position[/yellow]")
                elif change and change.get('reaction') == 'receptive':
                    evolution_log.append(f"[dim]💭 {agent.persona.name} considering[/dim]")
        
        if evolution_log:
            for log in evolution_log:
                console.print(f"  {log}")
    
    async def _should_moderator_intervene(self) -> bool:
        """모더레이터 개입 필요 판단 (완화된 조건)"""
        if not self.moderator:
            console.print("[dim red]No moderator available[/dim red]")
            return False

        # 최소 2턴만 진행되면 개입 가능
        if self.turn_count < 2:
            console.print(f"[dim yellow]Turn {self.turn_count} < 2, skipping[/dim yellow]")
            return False

        # 2턴마다 개입 (더 자주)
        if self.turn_count % 2 == 0:
            console.print(f"[dim green]Turn {self.turn_count} is even, should intervene![/dim green]")
            return True

        # 추상적 발언이 있으면 즉시
        if self._should_probe_for_specifics():
            console.print("[dim green]Abstract statement detected, should intervene![/dim green]")
            return True

        # 주제 전환 필요
        if self.moderator.should_transition_subtopic(self.messages):
            console.print("[dim green]Topic transition needed, should intervene![/dim green]")
            return True

        # 기타 경우에도 50% 확률로 개입
        import random
        random_check = random.random() > 0.5
        console.print(f"[dim cyan]Random check: {random_check}[/dim cyan]")
        return random_check
    
    async def _moderator_intervention(self, topic: str):
        """모더레이터 개입 - 주제 전환, 심화 질문 (통합)"""

        console.print("[cyan]Checking moderator intervention conditions...[/cyan]")

        # 1. 주제 전환 필요 여부 확인
        should_transition = self.moderator.should_transition_subtopic(self.messages)
        console.print(f"  1. Should transition subtopic? {should_transition}")
        if should_transition:
            transition_msg = await self.moderator.transition_to_next_subtopic(topic)
            self._add_moderator_message(transition_msg, "transition")
            return

        # 2. 구체화 필요 (추상적 발언 감지)
        should_probe = self._should_probe_for_specifics()
        console.print(f"  2. Should probe for specifics? {should_probe}")
        if should_probe:
            question = await self.moderator.generate_probing_question(
                topic,
                self.messages,
                is_abstract=True
            )
            self._add_moderator_message(question, "probing")
            return

        # 3. 일반 심화 질문
        should_ask = self.moderator.should_ask_question(self.turn_count)
        console.print(f"  3. Should ask question? {should_ask}")
        if should_ask:
            question = await self.moderator.generate_probing_question(
                topic,
                self.messages
            )
            self._add_moderator_message(question, "question")
            self.moderator.last_question_turn = self.turn_count
            return

        # 4. 아무 조건도 만족하지 않으면 강제로 질문 생성
        console.print("[yellow]  No condition met, forcing question generation...[/yellow]")
        question = await self.moderator.generate_probing_question(topic, self.messages)
        self._add_moderator_message(question, "forced")
        self.moderator.last_question_turn = self.turn_count

    async def _moderator_intervention_streaming(self, topic: str) -> Optional[Message]:
        """모더레이터 개입 - 스트리밍 버전 (Message 객체 반환)"""

        console.print("[cyan]Checking moderator intervention conditions...[/cyan]")

        msg_type = "question"
        content = None

        # 1. 주제 전환 필요 여부 확인
        should_transition = self.moderator.should_transition_subtopic(self.messages)
        console.print(f"  1. Should transition subtopic? {should_transition}")
        if should_transition:
            content = await self.moderator.transition_to_next_subtopic(topic)
            msg_type = "transition"

        # 2. 구체화 필요 (추상적 발언 감지)
        elif self._should_probe_for_specifics():
            console.print(f"  2. Should probe for specifics? True")
            content = await self.moderator.generate_probing_question(
                topic,
                self.messages,
                is_abstract=True
            )
            msg_type = "probing"

        # 3. 일반 심화 질문
        elif self.moderator.should_ask_question(self.turn_count):
            console.print(f"  3. Should ask question? True")
            content = await self.moderator.generate_probing_question(
                topic,
                self.messages
            )
            msg_type = "question"
            self.moderator.last_question_turn = self.turn_count

        # 4. 아무 조건도 만족하지 않으면 강제로 질문 생성
        else:
            console.print("[yellow]  No condition met, forcing question generation...[/yellow]")
            content = await self.moderator.generate_probing_question(topic, self.messages)
            msg_type = "forced"
            self.moderator.last_question_turn = self.turn_count

        if content:
            # 콘솔 출력
            console.print(f"\n[bold yellow]📢 MODERATOR:[/bold yellow]")
            from rich.panel import Panel
            console.print(Panel(content, border_style="yellow", expand=False))

            # Message 객체 생성 및 추가
            moderator_msg = Message(
                role="moderator",
                content=content,
                agent_name="Moderator",
                metadata={
                    "type": msg_type,
                    "is_complete": True
                }
            )
            self.messages.append(moderator_msg)
            return moderator_msg

        return None
    
    def _add_moderator_message(self, content: str, msg_type: str):
        """모더레이터 메시지 추가 및 출력"""
        # 콘솔 출력
        console.print(f"\n[bold yellow]📢 MODERATOR:[/bold yellow]")
        console.print(Panel(content, border_style="yellow", expand=False))
        
        # 메시지 추가
        self.messages.append(Message(
            role="moderator",
            content=content,
            agent_name="Moderator",
            metadata={"type": msg_type}
        ))
    
    def _should_probe_for_specifics(self) -> bool:
        """추상적 발언 감지 - 구체화 필요 판단"""
        if len(self.messages) < 2:
            return False
        
        # 최근 2개 메시지 확인
        recent = self.messages[-2:]
        abstract_count = 0
        
        abstract_keywords = [
            "in general", "overall", "basically", "essentially",
            "theoretically", "conceptually", "abstractly",
            "일반적으로", "전반적으로", "기본적으로", "이론적으로"
        ]
        
        for msg in recent:
            if msg.role == "agent" or msg.role == "assistant":
                content_lower = msg.content.lower()
                if any(kw in content_lower for kw in abstract_keywords):
                    abstract_count += 1
        
        return abstract_count >= 2
    
    async def _generate_response_chunks(self, speaker, prompt: str, action: ActionType):
        """에이전트 응답 생성 - 청크 단위로 yield"""
        action_emoji = {
            ActionType.PRESENT: "💡",
            ActionType.RESPOND: "↩️",
            ActionType.BUILD: "🤝",
            ActionType.CHALLENGE: "⚡",
            ActionType.EXAMPLE: "📌",
            ActionType.SYNTHESIZE: "🔄"
        }

        console.print(f"\n{action_emoji[action]} [cyan]{speaker.persona.name}[/cyan] ({action.value})")

        response_text = ""
        with Live(
            Panel("", title=f"[cyan]{speaker.persona.name}[/cyan]", border_style="green", expand=False),
            console=console,
            refresh_per_second=10
        ) as live:
            async for chunk in speaker.respond_stream(prompt, self.messages):
                response_text += chunk
                live.update(
                    Panel(response_text, title=f"[cyan]{speaker.persona.name}[/cyan]",
                          border_style="green", expand=False)
                )
                # 청크를 즉시 yield
                yield {"type": "chunk", "chunk": chunk}

        # RAG 결과 표시 (있는 경우)
        if speaker.last_rag_result and speaker.last_rag_result.evidence:
            console.print(f"\n[dim cyan]  📚 Research Query: {speaker.last_rag_result.query}[/dim cyan]")
            console.print(f"[dim cyan]  📊 Evidence: {speaker.last_rag_result.summary[:150]}...[/dim cyan]")
            if speaker.last_rag_result.sources:
                console.print(f"[dim cyan]  🔗 Sources: {', '.join(speaker.last_rag_result.sources[:2])}[/dim cyan]")

        # 완성 신호
        yield {"type": "complete", "text": response_text}

    async def _generate_response(self, speaker, prompt: str, action: ActionType, streaming: bool = True) -> str:
        """에이전트 응답 생성 (스트리밍 여부에 따라)"""
        if streaming:
            # 스트리밍 출력
            action_emoji = {
                ActionType.PRESENT: "💡",
                ActionType.RESPOND: "↩️",
                ActionType.BUILD: "🤝",
                ActionType.CHALLENGE: "⚡",
                ActionType.EXAMPLE: "📌",
                ActionType.SYNTHESIZE: "🔄"
            }
            
            console.print(f"\n{action_emoji[action]} [cyan]{speaker.persona.name}[/cyan] ({action.value})")
            
            response_text = ""
            with Live(
                Panel("", title=f"[cyan]{speaker.persona.name}[/cyan]", border_style="green", expand=False),
                console=console,
                refresh_per_second=10
            ) as live:
                async for chunk in speaker.respond_stream(prompt, self.messages):
                    response_text += chunk
                    live.update(
                        Panel(response_text, title=f"[cyan]{speaker.persona.name}[/cyan]", 
                              border_style="green", expand=False)
                    )
            
            # RAG 결과 표시 (있는 경우)
            if speaker.last_rag_result and speaker.last_rag_result.evidence:
                console.print(f"\n[dim cyan]  📚 Research Query: {speaker.last_rag_result.query}[/dim cyan]")
                console.print(f"[dim cyan]  📊 Evidence: {speaker.last_rag_result.summary[:150]}...[/dim cyan]")
                if speaker.last_rag_result.sources:
                    console.print(f"[dim cyan]  🔗 Sources: {', '.join(speaker.last_rag_result.sources[:2])}[/dim cyan]")
            
            return response_text
        else:
            # 일반 출력
            response = await speaker.respond(prompt, self.messages)
            console.print(f"\n[bold cyan]{speaker.persona.name}:[/bold cyan]")
            console.print(response)
            return response
    
    def _find_challengeable_point(self) -> Optional[Message]:
        """도전할 만한 포인트 찾기"""
        # 강한 주장 찾기
        for msg in reversed(self.messages[-5:]):
            if any(word in msg.content.lower() for word in ["must", "always", "never", "clearly"]):
                return msg
        return self.messages[-1] if self.messages else None