"""
행정조사 중복 판별 토론 통합 서비스

페르소나 생성   토론 진행   보고서 생성까지의 전체 플로우 관리
"""
from typing import Dict, Any, List, Optional, Tuple
from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum

from api.services.persona_auto_generator import PersonaAutoGenerator, GeneratedPersona
from api.services.moderator_agent import ModeratorAgent, ConsensusStatus, DiscussionPhase
from src.models.personas import LLMProvider


class DiscussionStatus(str, Enum):
    """토론 상태"""
    INITIALIZING = "initializing"  # 초기화 중
    GENERATING_PERSONAS = "generating_personas"  # 페르소나 생성 중
    IN_PROGRESS = "in_progress"  # 토론 진행 중
    COMPLETED = "completed"  # 완료
    FAILED = "failed"  # 실패


class DiscussionMessage(BaseModel):
    """토론 메시지"""
    round_number: int
    speaker: str  # "moderator" 또는 페르소나 이름
    role: Optional[str] = None  # 페르소나 역할
    content: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    type: str = "statement"  # statement, guidance, question, response


class DiscussionRound(BaseModel):
    """라운드 정보"""
    round_number: int
    phase: DiscussionPhase
    messages: List[DiscussionMessage]
    summary: Optional[str] = None
    key_points: List[str] = []


class InvestigationDiscussionResult(BaseModel):
    """토론 결과"""
    discussion_id: str
    status: DiscussionStatus
    
    # 입력
    investigation_a: Dict[str, Any]
    investigation_b: Dict[str, Any]
    
    # 생성된 페르소나
    personas: List[GeneratedPersona]
    persona_generation_reason: str
    
    # 토론 내용
    rounds: List[DiscussionRound]
    total_rounds: int
    
    # 최종 결과
    consensus_status: Optional[ConsensusStatus] = None
    final_verdict: str  # "중복", "비중복", "부분중복"
    final_verdict_details: str
    
    # 정량적 평가 (루브릭)
    rubric_scores: Optional[Dict[str, Any]] = None  # 루브릭 평가 결과
    
    # 보고서
    report: str  # Markdown 형식
    
    # 메타데이터
    started_at: datetime
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None


class InvestigationDiscussionService:
    """행정조사 중복 판별 토론 통합 서비스"""
    
    def __init__(
        self,
        llm_provider: LLMProvider = LLMProvider.OPENAI,
        model: Optional[str] = None,
        min_rounds: int = 3,
        max_rounds: int = 10,
        event_callback: Optional[callable] = None,
        enable_openness_adjustment: bool = False
    ):
        """
        Args:
            llm_provider: LLM 프로바이더
            model: 모델 이름
            min_rounds: 최소 라운드
            max_rounds: 최대 라운드
            event_callback: 실시간 이벤트 콜백 함수
            enable_openness_adjustment: 페르소나 믿음 변화 기능 활성화
        """
        self.llm_provider = llm_provider
        self.model = model
        self.min_rounds = min_rounds
        self.max_rounds = max_rounds
        self.event_callback = event_callback
        self.enable_openness_adjustment = enable_openness_adjustment
        
        # 컴포넌트 초기화
        self.persona_generator = PersonaAutoGenerator(
            llm_provider=llm_provider,
            model=model
        )
        self.moderator = ModeratorAgent(
            llm_provider=llm_provider,
            model=model,
            min_rounds=min_rounds,
            max_rounds=max_rounds
        )
    
    def _emit_event(self, event_type: str, data: Dict[str, Any]):
        """이벤트 발생"""
        if self.event_callback:
            self.event_callback(event_type, data)
        
        # 예쁜 콘솔 출력
        self._print_event(event_type, data)
    
    def _print_event(self, event_type: str, data: Dict[str, Any]):
        """예쁜 콘솔 출력"""
        import sys
        # ANSI 색상 코드
        BLUE = '\033[94m'
        GREEN = '\033[92m'
        YELLOW = '\033[93m'
        RED = '\033[91m'
        CYAN = '\033[96m'
        MAGENTA = '\033[95m'
        BOLD = '\033[1m'
        RESET = '\033[0m'
        
        if event_type == 'phase_start':
            phase = data.get('phase', '')
            message = data.get('message', '')
            icon = {'persona_generation': '[PERSONAS]', 'discussion': '[CHAT]', 'rounds': '[ROUND]'}.get(phase, '[START]')
            print(f"\n{BOLD}{CYAN}{'='*60}{RESET}")
            print(f"{BOLD}{icon}  {message.upper()}{RESET}")
            print(f"{CYAN}{'='*60}{RESET}\n")
        
        elif event_type == 'personas_generated':
            count = data.get('count', 0)
            personas = data.get('personas', [])
            print(f"{GREEN}[OK] 페르소나 {count}명 생성 완료{RESET}")
            for p in personas:
                print(f"   - {BOLD}{p['name']}{RESET} ({p['role']})")
            print()
        
        elif event_type == 'round_start':
            round_num = data.get('round', 0)
            max_rounds = data.get('max_rounds', 0)
            print(f"\n{BOLD}{BLUE}    라운드 {round_num}/{max_rounds}    {RESET}")
        
        elif event_type == 'moderator_message':
            msg_type = data.get('type', '')
            content = data.get('content', '')
            print(f"\n{MAGENTA}{'='*60}{RESET}")
            print(f"{MAGENTA}[MOD] [모더레이터 - {msg_type}]{RESET}")
            print(f"{MAGENTA}{'='*60}{RESET}")
            # 전체 내용 출력 (자르지 않음)
            print(f"{content}")
            print(f"{MAGENTA}{'-'*60}{RESET}\n")
        
        elif event_type == 'persona_speaking':
            name = data.get('name', '')
            print(f"{YELLOW}[SPEAK]  {BOLD}{name}{RESET} 발언 중...")
            print(f"{GREEN}[CHAT] {BOLD}{name}{RESET}: ", end='', flush=True)  # 줄바꿈 없이 시작
        
        elif event_type == 'persona_token':
            # 토큰 단위로 실시간 출력 (ChatGPT 스타일)
            token = data.get('token', '')
            print(token, end='', flush=True)  # 줄바꿈 없이 바로바로 출력
        
        elif event_type == 'persona_statement_complete':
            # 발언 완료 (줄바꿈)
            print(f"\n{RESET}", flush=True)
        
        elif event_type == 'turn_start':
            turn = data.get('turn', 0)
            print(f"\n   {CYAN}  턴 {turn}{RESET}")
        
        elif event_type == 'round_complete':
            round_num = data.get('round', 0)
            issue = data.get('issue', '')
            verdict = data.get('verdict', '')
            consensus = data.get('consensus_level', 0)
            print(f"\n{GREEN}{'='*60}{RESET}")
            print(f"{GREEN}[OK] 라운드 {round_num} 완료: {issue}{RESET}")
            print(f"{GREEN}   판정: {verdict} | 합의도: {consensus:.1%}{RESET}")
            print(f"{GREEN}{'='*60}{RESET}\n")
        
        elif event_type == 'consensus_check':
            level = data.get('level', 0)
            print(f"\n{CYAN}[STATS] 합의도 체크: {level:.1%}{RESET}")
        
        elif event_type == 'discussion_complete':
            verdict = data.get('verdict', '')
            total_rounds = data.get('total_rounds', 0)
            consensus = data.get('consensus_level', 0)
            print(f"\n{BOLD}{GREEN}{'='*60}{RESET}")
            print(f"{BOLD}  토론 완료! 최종 판정: {verdict}{RESET}")
            print(f"{GREEN}   총 라운드: {total_rounds} | 합의도: {consensus:.1%}{RESET}")
            print(f"{GREEN}{'='*60}{RESET}\n")
        
        # 실시간 출력을 위해 flush
        sys.stdout.flush()
    
    async def conduct_discussion(
        self,
        investigation_a: Dict[str, Any],
        investigation_b: Dict[str, Any],
        num_personas: Optional[int] = None,
        discussion_id: Optional[str] = None
    ) -> InvestigationDiscussionResult:
        """
        전체 토론 프로세스 실행
        
        Args:
            investigation_a: 행정조사 A
            investigation_b: 행정조사 B
            num_personas: 페르소나 수 (None이면 자동)
            discussion_id: 토론 ID (None이면 자동 생성)
            
        Returns:
            InvestigationDiscussionResult
        """
        import uuid
        from time import time
        
        if not discussion_id:
            discussion_id = f"disc_{uuid.uuid4().hex[:12]}"
        
        started_at = datetime.utcnow()
        start_time = time()
        
        try:
            # 1. 페르소나 생성
            print(f"[{discussion_id}] 1/3 페르소나 생성 중...")
            self._emit_event('phase_start', {'phase': 'persona_generation', 'message': '페르소나 생성 중...'})
            
            print(f"\n  persona_generator.generate_personas() 호출 직전!")
            print(f"   investigation_a 타입: {type(investigation_a)}")
            print(f"   investigation_b 타입: {type(investigation_b)}")
            print(f"   num_personas: {num_personas}")
            
            persona_result = self.persona_generator.generate_personas(
                investigation_a=investigation_a,
                investigation_b=investigation_b,
                num_personas=num_personas
            )
            
            print(f"\n[OK] persona_generator.generate_personas() 완료!")
            print(f"   persona_result 타입: {type(persona_result)}")
            
            personas = persona_result.personas
            
            self._emit_event('personas_generated', {
                'count': len(personas),
                'personas': [{'name': p.name, 'role': p.role} for p in personas]
            })
            
            # 2. 토론 시작 - 개회 및 쟁점 도출
            print(f"[{discussion_id}] 2/5 개회 및 쟁점 도출...")
            self._emit_event('phase_start', {'phase': 'opening', 'message': '개회 및 쟁점 도출 중...'})
            rounds = []
            
            # 개회 - 쟁점 도출
            opening_result = self.moderator.start_discussion(
                investigation_a=investigation_a,
                investigation_b=investigation_b,
                personas=[p.dict() for p in personas]
            )
            
            opening_statement = opening_result.get('opening_statement', '')
            key_issues = opening_result.get('key_issues', [])
            
            print(f"\n[OK] {len(key_issues)}개 쟁점 도출:")
            for issue in key_issues:
                print(f"   - 쟁점 {issue.get('issue_number')}: {issue.get('title')}")
            
            self._emit_event('moderator_message', {
                'type': 'opening',
                'content': opening_statement,
                'issues': key_issues
            })
            
            # 라운드 0: 개회
            round_0 = DiscussionRound(
                round_number=0,
                phase=DiscussionPhase.OPENING,
                messages=[DiscussionMessage(
                    round_number=0,
                    speaker="모더레이터",
                    content=opening_statement,
                    type="opening"
                )]
            )
            rounds.append(round_0)
            
            # 3. 쟁점별 라운드 토론 진행
            print(f"[{discussion_id}] 3/5 쟁점별 라운드 토론...")
            self._emit_event('phase_start', {'phase': 'rounds', 'message': '쟁점별 라운드 토론 진행 중...'})
            
            round_conclusions = []  # 각 라운드의 결론 저장
            rounds_to_conduct = min(len(key_issues), self.max_rounds)
            
            for round_idx in range(rounds_to_conduct):
                issue = key_issues[round_idx]
                round_number = round_idx + 1
                
                print(f"\n{'='*70}")
                print(f"  라운드 {round_number}/{rounds_to_conduct}: {issue.get('title')}")
                print(f"{'='*70}\n")
                
                # 이전 라운드 요약
                previous_rounds_summary = "\n".join([
                    f"[라운드 {i+1}] {rc.get('conclusion', '')}"
                    for i, rc in enumerate(round_conclusions)
                ])
                
                # 라운드 진행
                round_result = await self._conduct_round_on_issue(
                    round_number=round_number,
                    issue=issue,
                    personas=personas,
                    investigation_a=investigation_a,
                    investigation_b=investigation_b,
                    previous_rounds_summary=previous_rounds_summary
                )
                
                rounds.append(round_result['round_object'])
                round_conclusions.append(round_result['conclusion'])
                
                print(f"\n[OK] 라운드 {round_number} 완료")
                print(f"   결론: {round_result['conclusion'].get('verdict_for_this_issue', 'N/A')}")
                print(f"   합의도: {round_result['conclusion'].get('consensus_level', 0):.1%}\n")
            
            # 4. 모든 라운드 결론 종합하여 최종 판정
            print(f"[{discussion_id}] 4/5 최종 판정 도출...")
            self._emit_event('phase_start', {'phase': 'final_verdict', 'message': '최종 판정 도출 중...'})
            
            # 라운드별 결론 요약
            all_conclusions_summary = "\n\n".join([
                f"【라운드 {i+1}: {key_issues[i].get('title')}】\n"
                f"- 결론: {rc.get('verdict_for_this_issue', 'N/A')}\n"
                f"- 합의도: {rc.get('consensus_level', 0):.1%}\n"
                f"- 상세: {rc.get('conclusion', '')[:200]}..."
                for i, rc in enumerate(round_conclusions)
            ])
            
            # 전체 합의도 계산
            avg_consensus = sum(rc.get('consensus_level', 0) for rc in round_conclusions) / len(round_conclusions) if round_conclusions else 0.0
            
            # ConsensusStatus 생성 (라운드 결론들을 종합)
            all_agreed_points = []
            all_disagreed_points = []
            for rc in round_conclusions:
                all_agreed_points.extend(rc.get('agreed_points', []))
                all_disagreed_points.extend(rc.get('disagreed_points', []))
            
            consensus_status = ConsensusStatus(
                has_consensus=(avg_consensus >= 0.7),
                consensus_level=avg_consensus,
                areas_of_agreement=all_agreed_points,
                areas_of_disagreement=all_disagreed_points,
                key_arguments={}
            )
            
            # [STATS] 루브릭 평가 (점수 기반 최종 판정)
            print(f"[{discussion_id}] [STATS] 루브릭 평가 수행 중...")
            self._emit_event('phase_start', {'phase': 'rubric', 'message': '정량적 중복도 평가 중...'})
            
            rubric_result = self._evaluate_rubric(
                investigation_a=investigation_a,
                investigation_b=investigation_b,
                final_verdict="",  # 아직 미정
                consensus_status=consensus_status
            )
            
            #   루브릭 점수로 최종 판정 결정
            total_score = rubric_result.get('total', 0)
            if total_score >= 80:
                final_verdict = "중복"
                verdict_reason = f"루브릭 총점 {total_score}점으로 명확한 중복으로 판정"
            else:
                final_verdict = "비중복"
                verdict_reason = f"루브릭 총점 {total_score}점으로 중복으로 보기 어려움"
            
            print(f"[{discussion_id}] [OK] 루브릭 평가 완료: {total_score}/100점   {final_verdict}")
            
            # 5. 폐회 - 최종 결론 발표
            print(f"[{discussion_id}] 5/5 폐회 및 보고서 생성...")
            self._emit_event('phase_start', {'phase': 'closing', 'message': '폐회 및 최종 결론 발표...'})
            
            # 폐회사 (루브릭 기반 최종 판정 포함)
            closing_statement = self._generate_closing_statement_with_rubric(
                round_conclusions=round_conclusions,
                key_issues=key_issues,
                final_verdict=final_verdict,
                verdict_reason=verdict_reason,
                rubric_result=rubric_result,
                avg_consensus=avg_consensus
            )
            
            # 모더레이터 폐회사 이벤트 (콘솔 출력!)
            self._emit_event('moderator_message', {
                'type': 'closing',
                'verdict': final_verdict,
                'content': closing_statement
            })
            
            # 토론 완료 이벤트
            self._emit_event('discussion_complete', {
                'verdict': final_verdict,
                'consensus_level': avg_consensus,
                'total_rounds': rounds_to_conduct
            })
            
            # 폐회 라운드 추가
            closing_round_number = rounds_to_conduct + 1
            rounds.append(DiscussionRound(
                round_number=closing_round_number,
                phase=DiscussionPhase.CLOSING,
                messages=[DiscussionMessage(
                    round_number=closing_round_number,
                    speaker="모더레이터",
                    content=closing_statement,
                    type="closing"
                )]
            ))
            
            # 보고서 생성 (루브릭 결과 재사용)
            report = self._generate_report_with_rubric(
                investigation_a=investigation_a,
                investigation_b=investigation_b,
                personas=personas,
                rounds=rounds,
                consensus_status=consensus_status,
                final_verdict=final_verdict,
                rubric_result=rubric_result
            )
            
            # 결과 생성
            completed_at = datetime.utcnow()
            duration = time() - start_time
            
            result = InvestigationDiscussionResult(
                discussion_id=discussion_id,
                status=DiscussionStatus.COMPLETED,
                investigation_a=investigation_a,
                investigation_b=investigation_b,
                personas=personas,
                persona_generation_reason=persona_result.generation_reason,
                rounds=rounds,
                total_rounds=len(rounds) - 1,  # 개회 제외
                consensus_status=consensus_status,
                final_verdict=final_verdict,
                final_verdict_details=closing_statement,
                rubric_scores=rubric_result,
                report=report,
                started_at=started_at,
                completed_at=completed_at,
                duration_seconds=duration
            )
            
            print(f"[{discussion_id}] [OK] 토론 완료! ({duration:.1f}초)")
            return result
            
        except Exception as e:
            print(f"[{discussion_id}] [ERROR] 에러 발생: {e}")
            raise
    
    def _generate_persona_statement(
        self,
        persona: GeneratedPersona,
        round_number: int,
        phase: str,
        guidance: Dict[str, Any],
        investigation_a: Dict[str, Any],
        investigation_b: Dict[str, Any],
        previous_discussion: str
    ) -> str:
        """페르소나의 발언 생성 (토큰 단위 스트리밍)"""
        from src.utils.llm_provider import LLMFactory
        
        llm = LLMFactory.create_llm(
            provider=self.llm_provider,
            model=self.model,
            temperature=0.7,
            streaming=True,  # 스트리밍 활성화
            max_tokens=3000  # 발언이 잘리지 않게
        )
        
        # 조사 내용 포맷팅
        inv_a_text = investigation_a.get('raw_text', '') or str(investigation_a)
        inv_b_text = investigation_b.get('raw_text', '') or str(investigation_b)

        # 디버깅: 조사 텍스트 길이 확인
        print(f"\n{'='*80}")
        print(f"  [페르소나 발언 생성] 행정조사 텍스트 확인")
        print(f"{'='*80}")
        print(f"  조사 A 길이: {len(inv_a_text)}자")
        print(f"  조사 B 길이: {len(inv_b_text)}자")
        print(f"\n  조사 A 내용 (처음 500자):")
        print(inv_a_text[:500])
        print(f"\n  조사 B 내용 (처음 500자):")
        print(inv_b_text[:500])
        print(f"{'='*80}\n")

        prompt = f"""당신은 {persona.name}({persona.role})입니다.

<당신의 전문성>
{persona.expertise}

<당신의 관점>
{persona.perspective}

<핵심 임무>
아래 두 행정조사가 중복인지 판단하는 것입니다. 구체적인 조사 내용을 바탕으로 의견을 제시하세요.

  중복조사 개념:
**중복조사**란 동일한 조사대상자에게 반복적 또는 중첩적으로 시행되어 부담을 가중시키는 경우입니다.

판단 기준:
-   조사 대상이 동일하거나 겹치는가? (모집단, 실제 대상자)
-   조사 내용이 유사한가? (조사 항목, 제출 자료)
- [WARN] 중요: 조사대상이 다르면 내용이 같아도 중복조사로 보지 않음

<행정조사 A 상세>
{inv_a_text}

<행정조사 B 상세>
{inv_b_text}

<현재 상황>
- 라운드: {round_number}/{guidance.get('max_rounds', 3)}
- 모더레이터 지시: {guidance.get('next_focus', '두 조사의 중복 여부를 판단하세요')}

<이전 토론 내용>
{previous_discussion[:1000] if previous_discussion else '첫 라운드입니다.'}

**발언 지침**: 
1. 위 두 조사의 구체적인 내용(대상, 주관기관, 법적근거, 조사내용 등)을 직접 언급하세요
2. 중복 여부에 대한 명확한 의견을 제시하세요 (중복이다/비중복이다)
3. 근거를 구체적으로 제시하세요 (대상 겹침 비율, 내용 유사도 등)

한국어로 2-3문단, 조사 내용에 초점을 맞춰 작성하세요."""
        
        # 토큰 단위 스트리밍
        full_content = ""
        for chunk in llm.stream(prompt):
            if hasattr(chunk, 'content'):
                token = chunk.content
                full_content += token
                
                # 토큰 단위로 이벤트 emit
                self._emit_event('persona_token', {
                    'name': persona.name,
                    'token': token
                })
        
        return full_content
    
    def _generate_discussion_summary(self, rounds: List[DiscussionRound]) -> str:
        """토론 요약 생성"""
        summary_parts = []
        for round in rounds[1:]:  # 개회 제외
            if round.summary:
                summary_parts.append(f"[라운드 {round.round_number}] {round.summary}")
        return "\n".join(summary_parts) if summary_parts else "토론 시작"
    
    def _get_persona_positions(
        self,
        rounds: List[DiscussionRound],
        personas: List[GeneratedPersona]
    ) -> Dict[str, str]:
        """페르소나별 최근 입장 추출"""
        positions = {}
        
        # 최근 라운드부터 역순으로 검색
        for round in reversed(rounds):
            for message in round.messages:
                if message.speaker != "모더레이터" and message.speaker not in positions:
                    positions[message.speaker] = message.content[:200] + "..."
        
        # 아직 발언하지 않은 페르소나
        for persona in personas:
            if persona.name not in positions:
                positions[persona.name] = "아직 발언하지 않음"
        
        return positions
    
    def _get_recent_discussion(self, rounds: List[DiscussionRound], last_n: int = 2) -> str:
        """최근 N개 라운드 내용"""
        recent_rounds = rounds[-last_n:] if len(rounds) > last_n else rounds
        content = []
        for round in recent_rounds:
            for msg in round.messages:
                content.append(f"[{msg.speaker}] {msg.content[:150]}...")
        return "\n\n".join(content)
    
    def _format_guidance(self, guidance: Dict[str, Any]) -> str:
        """가이드를 텍스트로 포맷팅"""
        parts = [f"라운드 가이드: {guidance.get('next_focus', '')}"]
        
        if guidance.get('agreements'):
            parts.append("\n합의된 사항:")
            for item in guidance['agreements']:
                parts.append(f"    {item}")
        
        if guidance.get('disagreements'):
            parts.append("\n논쟁 중인 사항:")
            for item in guidance['disagreements']:
                parts.append(f"  [WARN] {item}")
        
        return "\n".join(parts)
    
    def _determine_final_verdict(
        self,
        consensus_status: ConsensusStatus
    ) -> str:
        """최종 판정 결정 (순수하게 토론 결과로만 판별)"""
        # 합의 영역에서 판정 키워드 찾기
        agreement_text = " ".join(consensus_status.areas_of_agreement).lower()
        
        # 명확한 중복 판정
        if "중복" in agreement_text and "비중복" not in agreement_text:
            return "중복"
        
        # 명확한 비중복 판정
        if "비중복" in agreement_text and "중복" not in agreement_text:
            return "비중복"
        
        # 부분 중복 또는 애매한 경우
        if "부분" in agreement_text or ("중복" in agreement_text and "비중복" in agreement_text):
            return "부분중복"
        
        # 합의도 기반 판정
        if consensus_status.consensus_level >= 0.8:
            # 고도 합의인데 명확한 키워드 없으면 핵심 주장 분석
            key_args = " ".join(consensus_status.key_arguments.values()).lower()
            if "중복" in key_args:
                return "중복"
            elif "비중복" in key_args:
                return "비중복"
        
        # 기본값: 부분중복 (애매한 경우)
        return "부분중복"
    
    def _generate_report_with_rubric(
        self,
        investigation_a: Dict[str, Any],
        investigation_b: Dict[str, Any],
        personas: List[GeneratedPersona],
        rounds: List[DiscussionRound],
        consensus_status: ConsensusStatus,
        final_verdict: str,
        rubric_result: Dict[str, Any]
    ) -> str:
        """최종 보고서 생성 (Markdown) - 루브릭 결과 재사용"""
        # 해석 생성
        total_score = rubric_result['total']
        target_score = rubric_result.get('score_1_1', 0) + rubric_result.get('score_1_2', 0)
        content_score = rubric_result.get('score_2_1', 0) + rubric_result.get('score_2_2', 0)
        
        if target_score >= 35 and content_score >= 35:
            interpretation = "**명백한 중복조사** - 조사대상자에게 불필요한 부담 발생"
        elif target_score >= 35 and content_score < 35:
            interpretation = "**대상은 같으나 내용이 다름** - 공동조사 등으로 부담 완화 가능"
        elif target_score < 35 and content_score >= 35:
            interpretation = "**대상은 일부만 겹침** - 조사 설계 또는 사전 조율 필요"
        else:
            interpretation = "**중복 아님** - 별도 조사로 진행 가능"
        
        report = f"""# 행정조사 중복 판별 보고서

## 1. 요약

**판별 결과**: {final_verdict}  
**신뢰도**: {consensus_status.consensus_level:.1%}  
**토론 라운드**: {len(rounds) - 1}회  
**중복도 점수**: {rubric_result['total']}/100점

### 핵심 결론
{self._format_key_conclusions(consensus_status, final_verdict)}

---

## 2. 정량적 중복도 평가 (루브릭)

### [STATS] 총점: {rubric_result['total']}/100점

| 평가 항목 | 점수 | 근거 |
|----------|------|------|
|  -1 모집단 중복도 | {rubric_result.get('score_1_1', 0)}/30점 | {rubric_result.get('rationale_1_1', 'N/A')} |
|  -2 실제 대상 중복 가능성 | {rubric_result.get('score_1_2', 0)}/20점 | {rubric_result.get('rationale_1_2', 'N/A')} |
|  -1 내용 중복도 | {rubric_result.get('score_2_1', 0)}/30점 | {rubric_result.get('rationale_2_1', 'N/A')} |
|  -2 제출 자료 중복도 | {rubric_result.get('score_2_2', 0)}/20점 | {rubric_result.get('rationale_2_2', 'N/A')} |

**  조사 대상의 중복성**: {target_score}/50점  
**  조사 내용의 중복성**: {content_score}/50점

### 해석
{interpretation}
"""
        
        if rubric_result.get('additional_info_needed'):
            report += f"\n**추가 정보 필요**: {rubric_result['additional_info_needed']}\n"
        
        # 조사 원문 가져오기
        inv_a_raw = investigation_a.get('raw_text', '') or str(investigation_a)
        inv_b_raw = investigation_b.get('raw_text', '') or str(investigation_b)

        report += f"""
---

## 3. 조사 개요

### 행정조사 A (원문)

```
{inv_a_raw}
```

### 행정조사 B (원문)

```
{inv_b_raw}
```

---

## 4. 토론 참가자

{self._format_personas(personas)}

---

## 5. 토론 내용

{self._format_discussion_rounds(rounds)}

---

## 6. 종합 평가

### 합의된 사항
{self._format_list(consensus_status.areas_of_agreement)}

### 불일치 사항
{self._format_list(consensus_status.areas_of_disagreement)}

---

**보고서 생성일**: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC
"""
        return report
    
    def _generate_report(
        self,
        investigation_a: Dict[str, Any],
        investigation_b: Dict[str, Any],
        personas: List[GeneratedPersona],
        rounds: List[DiscussionRound],
        consensus_status: ConsensusStatus,
        final_verdict: str
    ) -> Tuple[str, Dict[str, Any]]:
        """최종 보고서 생성 (Markdown) 및 루브릭 점수 반환 (레거시)"""
        # 루브릭 평가 수행
        print("\n[STATS] 루브릭 평가 수행 중...")
        rubric_result = self._evaluate_rubric(
            investigation_a, investigation_b, final_verdict, consensus_status
        )
        print(f"[OK] 루브릭 평가 완료: 총점 {rubric_result['total']}/100점")
        
        # 해석 생성
        total_score = rubric_result['total']
        target_score = rubric_result.get('score_1_1', 0) + rubric_result.get('score_1_2', 0)
        content_score = rubric_result.get('score_2_1', 0) + rubric_result.get('score_2_2', 0)
        
        if target_score >= 35 and content_score >= 35:
            interpretation = "**명백한 중복조사** - 조사대상자에게 불필요한 부담 발생"
        elif target_score >= 35 and content_score < 35:
            interpretation = "**대상은 같으나 내용이 다름** - 공동조사 등으로 부담 완화 가능"
        elif target_score < 35 and content_score >= 35:
            interpretation = "**대상은 일부만 겹침** - 조사 설계 또는 사전 조율 필요"
        else:
            interpretation = "**중복 아님** - 별도 조사로 진행 가능"
        
        report = f"""# 행정조사 중복 판별 보고서

## 1. 요약

**판별 결과**: {final_verdict}  
**신뢰도**: {consensus_status.consensus_level:.1%}  
**토론 라운드**: {len(rounds) - 1}회  
**중복도 점수**: {rubric_result['total']}/100점

### 핵심 결론
{self._format_key_conclusions(consensus_status, final_verdict)}

---

## 2. 정량적 중복도 평가 (루브릭)

### [STATS] 총점: {rubric_result['total']}/100점

| 평가 항목 | 점수 | 근거 |
|----------|------|------|
|  -1 모집단 중복도 | {rubric_result.get('score_1_1', 0)}/30점 | {rubric_result.get('rationale_1_1', 'N/A')} |
|  -2 실제 대상 중복 가능성 | {rubric_result.get('score_1_2', 0)}/20점 | {rubric_result.get('rationale_1_2', 'N/A')} |
|  -1 내용 중복도 | {rubric_result.get('score_2_1', 0)}/30점 | {rubric_result.get('rationale_2_1', 'N/A')} |
|  -2 제출 자료 중복도 | {rubric_result.get('score_2_2', 0)}/20점 | {rubric_result.get('rationale_2_2', 'N/A')} |

**  조사 대상의 중복성**: {target_score}/50점  
**  조사 내용의 중복성**: {content_score}/50점

### 해석
{interpretation}
"""
        
        if rubric_result.get('additional_info_needed'):
            report += f"\n**추가 정보 필요**: {rubric_result['additional_info_needed']}\n"
        
        report += """
---

## 3. 조사 개요

### 행정조사 A
- **명칭**: {investigation_a.get('name', 'N/A')}
- **목적**: {investigation_a.get('purpose', 'N/A')}
- **대상**: {investigation_a.get('target', 'N/A')}
- **주관**: {investigation_a.get('department', 'N/A')}

### 행정조사 B
- **명칭**: {investigation_b.get('name', 'N/A')}
- **목적**: {investigation_b.get('purpose', 'N/A')}
- **대상**: {investigation_b.get('target', 'N/A')}
- **주관**: {investigation_b.get('department', 'N/A')}

---

## 4. 토론 참가자

{self._format_personas(personas)}

---

## 5. 토론 내용

{self._format_discussion_rounds(rounds)}

---

## 6. 종합 평가

### 합의 영역
{self._format_list(consensus_status.areas_of_agreement)}

### 불일치 영역
{self._format_list(consensus_status.areas_of_disagreement)}

### 페르소나별 핵심 주장
{self._format_key_arguments(consensus_status.key_arguments)}

---

## 7. 권고사항

{self._generate_recommendations(consensus_status, final_verdict)}

---

**보고서 생성일**: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC
"""
        return report, rubric_result
    
    def _format_key_conclusions(self, consensus: ConsensusStatus, verdict: str) -> str:
        if consensus.areas_of_agreement:
            return "\n".join(f"- {item}" for item in consensus.areas_of_agreement[:3])
        return f"- 최종 판정: {verdict}"
    
    def _format_personas(self, personas: List[GeneratedPersona]) -> str:
        result = []
        for p in personas:
            result.append(f"### {p.name} ({p.role})\n")
            result.append(f"- **전문 분야**: {p.expertise}")
            result.append(f"- **관점**: {p.perspective}")
            result.append("")
        return "\n".join(result)
    
    def _format_discussion_rounds(self, rounds: List[DiscussionRound]) -> str:
        result = []
        for round in rounds[1:-1]:  # 개회/폐회 제외
            result.append(f"### 라운드 {round.round_number} ({round.phase.value})")
            result.append("")
            if round.summary:
                result.append(f"**요약**: {round.summary}")
                result.append("")
        return "\n".join(result)
    
    def _format_list(self, items: List[str]) -> str:
        if not items:
            return "- 없음"
        # 리스트의 각 항목이 문자열인지 확인
        safe_items = []
        for item in items:
            if isinstance(item, str):
                safe_items.append(item)
            elif isinstance(item, list):
                # 리스트 안에 리스트가 있으면 첫 항목만 사용
                safe_items.append(str(item[0]) if item else "")
            else:
                safe_items.append(str(item))
        return "\n".join(f"- {item}" for item in safe_items if item)
    
    def _format_key_arguments(self, arguments: Dict[str, List[str]]) -> str:
        result = []
        for persona, args in arguments.items():
            result.append(f"**{persona}**")
            # args가 리스트인지 확인
            if isinstance(args, list):
                for arg in args:
                    # arg가 문자열인지 확인
                    if isinstance(arg, str):
                        result.append(f"  - {arg}")
                    else:
                        result.append(f"  - {str(arg)}")
            else:
                result.append(f"  - {str(args)}")
            result.append("")
        return "\n".join(result)
    
    def _generate_recommendations(self, consensus_status: ConsensusStatus, final_verdict: str) -> str:
        """토론 결과 기반으로 권고사항 생성"""
        recommendations = []
        
        if final_verdict == "중복":
            recommendations.append("두 조사의 통합 또는 조정을 권장합니다.")
            recommendations.append("조사 일정 조율 및 공동 수행 검토가 필요합니다.")
            recommendations.append("조사 대상자의 중복 부담을 최소화할 방안 마련이 시급합니다.")
        elif final_verdict == "부분중복":
            recommendations.append("중복 영역에 대한 세부 검토가 필요합니다.")
            recommendations.append("조사 항목 조정 및 정보 공유 체계 구축을 고려하십시오.")
        else:
            recommendations.append("현행 조사 체계를 유지해도 무방합니다.")
            recommendations.append("다만, 향후 조사 범위 변경 시 재검토를 권장합니다.")
        
        # 불일치 사항이 많으면 추가 검토 권고
        if len(consensus_status.areas_of_disagreement) > 2:
            recommendations.append("전문가 간 의견 차이가 존재하므로 추가적인 실무 검토가 필요합니다.")
        
        return "\n".join(f"{i}. {rec}" for i, rec in enumerate(recommendations, 1))
    
    def _extract_json(self, text: str) -> Dict[str, Any]:
        """LLM 응답에서 JSON 추출 (강력한 파싱)"""
        import re
        import json
        
        # 1. 코드 블록 내 JSON 찾기
        code_block_pattern = r'```(?:json)?\s*(\{.*?\})\s*```'
        match = re.search(code_block_pattern, text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1), strict=False)
            except:
                pass
        
        # 2. 중괄호로 감싸진 JSON 찾기
        brace_pattern = r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}'
        matches = re.finditer(brace_pattern, text, re.DOTALL)
        
        for match in matches:
            json_str = match.group(0)
            try:
                # 주석 제거
                json_str = re.sub(r'//.*?\n', '\n', json_str)
                json_str = re.sub(r'/\*.*?\*/', '', json_str, flags=re.DOTALL)
                # trailing comma 제거
                json_str = re.sub(r',(\s*[}\]])', r'\1', json_str)
                
                result = json.loads(json_str, strict=False)
                if isinstance(result, dict):
                    return result
            except:
                continue
        
        raise ValueError("JSON을 찾을 수 없습니다.")
    
    def _evaluate_rubric(
        self,
        investigation_a: Dict[str, Any],
        investigation_b: Dict[str, Any],
        final_verdict: str,
        consensus_status: ConsensusStatus
    ) -> Dict[str, Any]:
        """
        루브릭 기반 중복도 정량 평가 (0-100점)
        
        Returns:
            dict with scores and rationales for each criterion
        """
        from src.utils.llm_provider import LLMFactory
        
        llm = LLMFactory.create_llm(
            provider=self.llm_provider,
            model=self.model,
            temperature=0.3,  # 정량 평가이므로 낮은 temperature
            max_tokens=1500
        )
        
        inv_a_text = investigation_a.get('raw_text', '') or str(investigation_a)
        inv_b_text = investigation_b.get('raw_text', '') or str(investigation_b)
        
        # 토론 결과 요약
        discussion_summary = "\n".join([
            f"- {area}" for area in consensus_status.areas_of_agreement[:5]
        ])
        
        prompt = f"""당신은 행정조사 중복도 평가 전문가입니다. 다음 두 행정조사의 중복도를 정량적으로 평가하세요.

  중복조사 기본 개념:
**중복조사**란 동일한 조사대상자에게 반복적 또는 중첩적으로 시행되어 부담을 가중시키는 경우를 의미합니다.

**핵심 원칙:**
- [WARN] 조사대상이 다르면, 내용이 같아도 중복조사로 보지 않습니다
- 대상의 겹침 정도가 가장 중요한 판단 기준입니다
- 대상이 겹친다면, 내용 유사도에 따라 중복도가 결정됩니다

<행정조사 A>
{inv_a_text}

<행정조사 B>
{inv_b_text}

<토론 결과 요약>
{discussion_summary}

[STATS] 평가 기준 (총 100점)

**  조사 대상의 중복성 (50점)**

** -1 조사 대상 모집단의 중복도 (30점)**
- 조사 대상으로 명시된 모집단(업종, 기관, 지역, 자격 등)이 얼마나 겹치는가?
- 평가 방법: (겹치는 범위 / 전체 범위)   30점
  * 30점: 완전히 동일한 모집단 (예: 둘 다 "서울시 식품제조업소 전체")
  * 25-29점: 90% 이상 겹침 (예: A는 전국, B는 수도권)
  * 20-24점: 70-89% 겹침
  * 15-19점: 50-69% 겹침 (예: 하위집합 관계)
  * 10-14점: 30-49% 겹침
  * 5-9점: 10-29% 겹침
  * 1-4점: 10% 미만 겹침
  * 0점: 완전히 다른 모집단

** -2 실제 조사 대상의 중복 가능성 (20점)**
- 실무적으로 동일한 대상자가 두 조사를 모두 받을 가능성
- 법적 근거, 대상 요건, 실제 선정 방식을 고려
  * 20점: 거의 확실하게 중복 (예: 같은 법, 같은 요건)
  * 15-19점: 높은 가능성 (예: 상위-하위 법률 관계)
  * 10-14점: 중간 가능성 (예: 일부 요건 겹침)
  * 5-9점: 낮은 가능성
  * 1-4점: 매우 낮은 가능성
  * 0점: 불가능 (완전히 배타적 관계)

**  조사 내용의 중복성 (50점)**

** -1 조사 내용의 중복도 (30점)**
- 조사 목적, 조사 항목, 검사 방법, 조사 절차가 얼마나 유사한가?
- 평가 방법: (겹치는 항목 수 / 전체 항목 수)   30점
  * 30점: 거의 동일한 내용 (80% 이상 겹침)
  * 25-29점: 매우 유사 (60-79% 겹침)
  * 20-24점: 유사 (40-59% 겹침)
  * 15-19점: 일부 유사 (20-39% 겹침)
  * 10-14점: 약간 유사 (10-19% 겹침)
  * 1-9점: 거의 다름 (10% 미만)
  * 0점: 완전히 다른 내용

** -2 제출 자료의 중복도 (20점)**
- 대상자가 제출해야 하는 서류, 자료, 증빙이 얼마나 겹치는가?
- 평가 방법: (겹치는 자료 수 / 전체 자료 수)   20점
  * 20점: 거의 동일한 자료 요구 (80% 이상)
  * 15-19점: 대부분 겹침 (60-79%)
  * 10-14점: 많이 겹침 (40-59%)
  * 5-9점: 일부 겹침 (20-39%)
  * 1-4점: 조금 겹침 (20% 미만)
  * 0점: 완전히 다른 자료

[WARN] 채점 원칙:
1. 토론 내용에서 도출된 구체적 근거를 바탕으로 평가
2. 애매한 경우 보수적으로 평가 (의심스러우면 낮은 점수)
3. 각 항목별 근거를 명확하고 간결하게 작성
4. 정보가 불충분한 경우 그 사실을 명시

JSON 형식으로 응답하세요:
{{
  "score_1_1": 숫자(0-30),
  "rationale_1_1": "구체적 근거 (예: 두 조사 모두 서울시 식품제조업소 대상, 100% 겹침)",
  "score_1_2": 숫자(0-20),
  "rationale_1_2": "구체적 근거",
  "score_2_1": 숫자(0-30),
  "rationale_2_1": "구체적 근거",
  "score_2_2": 숫자(0-20),
  "rationale_2_2": "구체적 근거",
  "additional_info_needed": "추가로 필요한 정보 (없으면 빈 문자열)"
}}"""
        
        response = llm.invoke(prompt)
        result = self._extract_json(response.content)
        
        # 총점 계산
        result['total'] = (
            result.get('score_1_1', 0) +
            result.get('score_1_2', 0) +
            result.get('score_2_1', 0) +
            result.get('score_2_2', 0)
        )
        
        return result
    
    def _should_use_web_search(self, issue: Dict[str, Any]) -> bool:
        """
        웹 검색 필요 여부 판단

        [SEARCH] 모든 페르소나가 발언 전에 웹 검색을 수행하여
        주장의 근거를 찾고 이를 발언에 반영합니다.
        """
        # TAVILY API 키가 없으면 검색 불가
        if not self.enable_openness_adjustment:
            return False

        # 항상 웹 검색 수행
        return True
    
    async def _conduct_round_on_issue(
        self,
        round_number: int,
        issue: Dict[str, Any],
        personas: List[GeneratedPersona],
        investigation_a: Dict[str, Any],
        investigation_b: Dict[str, Any],
        previous_rounds_summary: str
    ) -> Dict[str, Any]:
        """
        특정 쟁점에 대한 완전한 라운드 진행 (여러 턴 포함)
        
        Args:
            round_number: 라운드 번호
            issue: 현재 쟁점
            personas: 참가자들
            investigation_a, investigation_b: 조사 데이터
            previous_rounds_summary: 이전 라운드들의 결론
            
        Returns:
            {'round_object': DiscussionRound, 'conclusion': dict}
        """
        # 라운드 시작 안내
        round_intro = self.moderator.start_round_on_issue(
            round_number=round_number,
            issue=issue,
            previous_rounds_summary=previous_rounds_summary
        )
        
        self._emit_event('round_start', {
            'round': round_number,
            'max_rounds': self.max_rounds,
            'issue': issue.get('title'),
            'intro': round_intro
        })
        
        self._emit_event('moderator_message', {
            'type': 'round_start',
            'content': f"쟁점: {issue.get('title')}\n\n{round_intro}"
        })
        
        # 웹 검색 필요 여부 판단 및 실행 (라운드당 1회, 모든 페르소나 공유)
        shared_evidence = None
        should_search = self._should_use_web_search(issue)
        
        if should_search:
            print(f"\n  [SEARCH] [라운드 {round_number}] 이 쟁점은 웹 검색이 필요합니다: {issue.get('title')}")
            try:
                from src.services.rag_service import RAGService
                from src.models.personas import Persona
                
                # 대표 페르소나로 검색 (첫 번째 페르소나)
                first_persona = personas[0]
                temp_persona = Persona(
                    name=first_persona.name,
                    role=first_persona.role,
                    background=first_persona.background or "",
                    expertise=first_persona.expertise.split(", ") if isinstance(first_persona.expertise, str) else [first_persona.expertise],
                    personality=["analytical"],
                    beliefs=[first_persona.perspective] if first_persona.perspective else [],
                    communication_style=first_persona.style or "professional"
                )
                
                rag_service = RAGService()
                search_topic = f"{issue.get('title')}: 행정조사 중복 판별"
                
                rag_result = await rag_service.process(
                    topic=search_topic,
                    persona=temp_persona,
                    context=None
                )
                
                if rag_result.evidence:
                    shared_evidence = {
                        'summary': rag_result.summary,
                        'query': rag_result.query,
                        'sources': rag_result.sources
                    }
                    print(f"  [OK] 웹 검색 완료: {rag_result.query}")
                    print(f"     결과: {len(rag_result.sources)}개 소스 발견")
                else:
                    print(f"  [INFO] 검색 결과 없음")
                    
            except Exception as e:
                print(f"  [WARN] 웹 검색 오류: {e}")
        else:
            print(f"\n  [INFO] [라운드 {round_number}] 이 쟁점은 입력 데이터로 판단 가능: {issue.get('title')}")
        
        # 라운드 메시지 저장
        round_messages = [
            DiscussionMessage(
                round_number=round_number,
                speaker="모더레이터",
                content=round_intro,
                type="round_start"
            )
        ]
        
        # 턴 히스토리
        turn_history = []
        max_turns = 5  # 최대 5턴
        
        # 턴 반복 (합의까지)
        for turn_number in range(1, max_turns + 1):
            print(f"  턴 {turn_number}/{max_turns}")
            
            self._emit_event('turn_start', {
                'round': round_number,
                'turn': turn_number
            })
            
            # 각 페르소나 발언
            for persona in personas:
                self._emit_event('persona_speaking', {
                    'name': persona.name,
                    'role': persona.role,
                    'turn': turn_number
                })
                
                statement, rag_metadata = await self._generate_persona_statement_for_issue(
                    persona=persona,
                    round_number=round_number,
                    turn_number=turn_number,
                    issue=issue,
                    investigation_a=investigation_a,
                    investigation_b=investigation_b,
                    turn_history=turn_history,
                    shared_evidence=shared_evidence  # 라운드 공유 검색 결과
                )
                
                self._emit_event('persona_statement_complete', {
                    'name': persona.name,
                    'content': statement,
                    'rag_metadata': rag_metadata
                })
                
                # 히스토리 및 메시지 저장
                turn_history.append({
                    'turn': turn_number,
                    'speaker': persona.name,
                    'content': statement
                })
                
                round_messages.append(DiscussionMessage(
                    round_number=round_number,
                    speaker=persona.name,
                    role=persona.role,
                    content=statement,
                    type="statement"
                ))
            
            # 모더레이터 중재
            moderation = self.moderator.moderate_turn(
                round_number=round_number,
                turn_number=turn_number,
                issue=issue,
                turn_history=turn_history
            )
            
            self._emit_event('moderator_message', {
                'type': 'moderation',
                'turn': turn_number,
                'content': moderation.get('moderation', ''),
                'agreements': moderation.get('agreements', []),
                'disagreements': moderation.get('disagreements', [])
            })
            
            round_messages.append(DiscussionMessage(
                round_number=round_number,
                speaker="모더레이터",
                content=moderation.get('moderation', ''),
                type="moderation"
            ))
            
            # 합의 도달 확인
            if not moderation.get('should_continue_turn', True):
                print(f"    합의 도달! (턴 {turn_number}에서 종료)")
                break
            
            if turn_number >= max_turns:
                print(f"  [WARN] 최대 턴 도달")
                break
        
        # 라운드 결론 도출
        round_discussion = "\n\n".join([
            f"[{t['speaker']}] {t['content'][:300]}..."
            for t in turn_history
        ])
        
        conclusion = self.moderator.check_round_consensus(
            round_number=round_number,
            issue=issue,
            round_discussion=round_discussion
        )
        
        self._emit_event('round_complete', {
            'round': round_number,
            'issue': issue.get('title'),
            'verdict': conclusion.get('verdict_for_this_issue', 'N/A'),
            'consensus_level': conclusion.get('consensus_level', 0.0)
        })
        
        self._emit_event('moderator_message', {
            'type': 'round_conclusion',
            'content': f"라운드 {round_number} 결론:\n{conclusion.get('conclusion', '')}"
        })
        
        # 라운드 객체 생성
        round_obj = DiscussionRound(
            round_number=round_number,
            phase=DiscussionPhase.ANALYSIS,
            messages=round_messages,
            summary=conclusion.get('conclusion', ''),
            key_points=conclusion.get('agreed_points', [])
        )
        
        return {
            'round_object': round_obj,
            'conclusion': conclusion
        }
    
    async def _generate_persona_statement_for_issue(
        self,
        persona: GeneratedPersona,
        round_number: int,
        turn_number: int,
        issue: Dict[str, Any],
        investigation_a: Dict[str, Any],
        investigation_b: Dict[str, Any],
        turn_history: List[Dict[str, Any]],
        shared_evidence: Optional[Dict[str, Any]] = None
    ) -> Tuple[str, Optional[Dict[str, Any]]]:
        """쟁점에 대한 페르소나 발언 생성 (페르소나별 개별 웹 검색)"""
        from src.utils.llm_provider import LLMFactory
        from src.services.rag_service import RAGService
        from src.models.personas import Persona

        # 페르소나별 개별 웹 검색 수행
        rag_metadata = None
        evidence_summary = None

        # 검색 필요 여부 판단
        should_search = self._should_use_web_search(issue)

        if should_search:
            print(f"  [SEARCH] [{persona.name}] 발언 전 웹 검색 중...")
            try:
                # 페르소나 객체 변환
                temp_persona = Persona(
                    name=persona.name,
                    role=persona.role,
                    background=persona.background or "",
                    expertise=persona.expertise.split(", ") if isinstance(persona.expertise, str) else [persona.expertise],
                    personality=["analytical"],
                    beliefs=[persona.perspective] if persona.perspective else [],
                    communication_style=persona.style or "professional"
                )

                # RAG 서비스로 검색
                rag_service = RAGService()

                # 페르소나별 맞춤형 검색 쿼리 생성
                # 페르소나의 전문성과 관점을 반영하여 다양한 검색 수행
                search_topic = f"{issue.get('title')}: {persona.role}의 관점에서 {persona.perspective}"
                print(f"    [QUERY] [{persona.name}] 검색 쿼리: {search_topic}")

                # 토론 컨텍스트 생성 (최근 발언들)
                from src.models.personas import Message
                context_messages = []
                for t in turn_history[-3:]:  # 최근 3개 발언
                    context_messages.append(Message(
                        role="assistant",  # 페르소나 발언은 assistant role
                        agent_name=t['speaker'],
                        content=t['content']
                    ))

                rag_result = await rag_service.process(
                    topic=search_topic,
                    persona=temp_persona,
                    context=context_messages if context_messages else None
                )

                if rag_result.evidence:
                    evidence_summary = rag_result.summary
                    rag_metadata = {
                        "rag_used": True,
                        "rag_query": rag_result.query,
                        "sources": rag_result.sources
                    }
                    print(f"    [OK] 검색 완료: {len(rag_result.sources)}개 소스")
                else:
                    print(f"    [INFO]  검색 결과 없음")
            except Exception as e:
                print(f"    [WARN]  검색 오류: {e}")
        else:
            print(f"  [INFO]  [{persona.name}] 웹 검색 불필요")
        
        llm = LLMFactory.create_llm(
            provider=self.llm_provider,
            model=self.model,
            temperature=0.7,
            streaming=True,
            max_tokens=2000  # 쟁점별 발언은 좀 더 짧게
        )
        
        # 조사 내용 포맷팅
        inv_a_text = investigation_a.get('raw_text', '') or str(investigation_a)
        inv_b_text = investigation_b.get('raw_text', '') or str(investigation_b)
        
        # 최근 발언들
        recent_statements = "\n".join([
            f"[{t['speaker']}] {t['content'][:200]}..."
            for t in turn_history[-4:]  # 최근 4개 발언
        ]) if turn_history else "첫 턴입니다."
        
        prompt = f"""당신은 {persona.name}({persona.role})입니다.

<당신의 전문성>
{persona.expertise}

<당신의 관점>
{persona.perspective}

  중복조사의 개념
중복조사란 동일한 조사대상자에게 반복적 또는 중첩적으로 시행되어 부담을 가중시키는 경우입니다.
- [WARN] 조사대상이 다르면, 내용이 같아도 중복조사가 아닙니다.

[OK] 중복조사는 다음 두 조건을 충족할 때 인정됩니다.
1) 조사대상이 동일하거나 상당 부분 겹치고,
2) 조사 내용이 동일하거나 유사하며,
3) 반복 중첩, 서류 재제출, 현장방문 증가 등 부담이 실제 발생한 경우

---

  **유형 분류** (A와 C만 중복조사로 인정)
- **A 유형(대상 중복형)**: 대상 동일 + 내용 상이
  - **A-1** 단일기관: 한 기관이 동일 대상에게 서로 다른 조사 반복
  - **A-2** 다기관: 여러 기관이 동일 대상에게 각각 조사 실시

- **C 유형(복합 중복형)**: 대상 동일 + 내용 동일 또는 유사
  - **C-1** 단일기관: 동일 내용 조사를 한 기관이 반복
  - **C-2** 다기관: 동일 내용 조사를 여러 기관이 실시

  **B 유형(내용만 동일, 대상이 다름)은 비효율이지만 중복조사가 아님**

---

[OK] 판별 로직
- 대상 동일 AND 내용 상이 AND 단일기관   A-1
- 대상 동일 AND 내용 상이 AND 다기관   A-2
- 대상 동일 AND 내용 유사/동일 AND 단일기관   C-1
- 대상 동일 AND 내용 유사/동일 AND 다기관   C-2
- 대상 상이   중복조사 아님

<행정조사 A 상세>
{inv_a_text}

<행정조사 B 상세>
{inv_b_text}

<현재 논의 중인 쟁점>
**{issue.get('title', '')}**
{issue.get('description', '')}

<라운드/턴 정보>
- 라운드 {round_number} (쟁점별 토론)
- 턴 {turn_number}

<최근 다른 참가자들의 발언>
{recent_statements}
"""

        # RAG 검색 결과가 있으면 프롬프트에 추가
        if evidence_summary:
            prompt += f"""
<[SEARCH] 당신이 검색한 참고자료>
{evidence_summary}

[IDEA] 이 자료를 활용하여 주장을 뒷받침하세요. 예: "판례에 따르면...", "통계 자료에 의하면...", "행정조사법 제OO조에서..."
"""

        prompt += f"""
**발언 지침**:
1. **토론 맥락을 고려**: 다른 참가자들의 발언을 언급하고 응답하세요
   예: "OOO 씨께서 말씀하신 대로...", "저는 XXX 씨 의견에 동의합니다만..."
2. 이번 쟁점("{issue.get('title', '')}")에만 집중
3. **검색한 자료를 자연스럽게 인용**: 법령, 판례, 통계 등을 근거로 활용
4. 조사 A, B의 구체적 내용을 근거로 제시
5. 명확한 입장 표명 (이 쟁점에 대해: 중복이다/비중복이다)
6. 정량적 표현 사용 (예: "70% 겹침", "절반 정도 중복")

2-3문단으로 간결하게 작성하세요."""
        
        # 토큰 단위 스트리밍
        full_content = ""
        for chunk in llm.stream(prompt):
            if hasattr(chunk, 'content'):
                token = chunk.content
                full_content += token
                
                self._emit_event('persona_token', {
                    'name': persona.name,
                    'token': token
                })
        
        return full_content, rag_metadata
    
    def _synthesize_final_verdict(self, round_conclusions: List[Dict[str, Any]]) -> str:
        """
        모든 라운드 결론을 종합하여 최종 판정
        
        [OK] 일관성 규칙 적용:
        - 하나라도 부분중복   부분중복
        - 세 쟁점 모두 중복   중복
        - 세 쟁점 모두 비중복   비중복
        """
        if not round_conclusions:
            return "판단보류"
        
        # 각 라운드의 판정 수집
        verdicts = [rc.get('verdict_for_this_issue', '') for rc in round_conclusions]
        
        # 판정 카운트
        dupl_count = verdicts.count('중복')
        partial_count = verdicts.count('부분중복')
        non_dupl_count = verdicts.count('비중복')
        total = len(verdicts)
        
        # [OK] 일관성 규칙: 하나라도 부분중복이면   부분중복
        if partial_count > 0:
            return "부분중복"
        
        # 모두 중복
        if dupl_count == total:
            return "중복"
        
        # 모두 비중복
        if non_dupl_count == total:
            return "비중복"
        
        # 혼합된 경우 (중복 + 비중복이 섞임)   부분중복으로 처리
        return "부분중복"
    
    def _generate_closing_statement_with_rubric(
        self,
        round_conclusions: List[Dict[str, Any]],
        key_issues: List[Dict[str, Any]],
        final_verdict: str,
        verdict_reason: str,
        rubric_result: Dict[str, Any],
        avg_consensus: float
    ) -> str:
        """루브릭 점수 기반 폐회사 생성"""
        total_score = rubric_result.get('total', 0)
        score_1 = rubric_result.get('score_1_1', 0) + rubric_result.get('score_1_2', 0)
        score_2 = rubric_result.get('score_2_1', 0) + rubric_result.get('score_2_2', 0)
        
        statement = f"""존경하는 참석자 여러분, 토론을 마무리하겠습니다.

우리는 총 {len(round_conclusions)}개의 주요 쟁점에 대해 심도 있는 논의를 진행했으며,
정량적 평가를 통해 다음과 같은 결론을 도출했습니다.

【정량적 중복도 평가】
[STATS] 총점: {total_score}/100점

  조사 대상의 중복성: {score_1}/50점
  - 모집단 중복도: {rubric_result.get('score_1_1', 0)}/30점
  - 실제 대상 중복 가능성: {rubric_result.get('score_1_2', 0)}/20점

  조사 내용의 중복성: {score_2}/50점
  - 내용 중복도: {rubric_result.get('score_2_1', 0)}/30점
  - 제출 자료 중복도: {rubric_result.get('score_2_2', 0)}/20점

【최종 판정】
두 행정조사는 **"{final_verdict}"**으로 판정됩니다.

- 판정 근거: {verdict_reason}
- 토론 합의도: {avg_consensus:.1%}

감사합니다."""
        
        return statement
    
    def _generate_closing_statement_with_rounds(
        self,
        round_conclusions: List[Dict[str, Any]],
        key_issues: List[Dict[str, Any]],
        final_verdict: str,
        avg_consensus: float
    ) -> str:
        """모든 라운드 결론을 포함한 폐회사 생성 (레거시)"""
        statement = f"""존경하는 참석자 여러분, 토론을 마무리하겠습니다.

우리는 총 {len(round_conclusions)}개의 주요 쟁점에 대해 심도 있는 논의를 진행했습니다.

【쟁점별 결론】
"""
        
        for i, (issue, conclusion) in enumerate(zip(key_issues, round_conclusions)):
            statement += f"""
{i+1}. {issue.get('title')}
     판정: {conclusion.get('verdict_for_this_issue', 'N/A')}
     합의도: {conclusion.get('consensus_level', 0):.1%}
     결론: {conclusion.get('conclusion', '')[:150]}...
"""
        
        statement += f"""

【최종 종합 판정】
모든 쟁점을 종합한 결과, 두 행정조사는 **"{final_verdict}"**으로 판단됩니다.

- 전체 평균 합의도: {avg_consensus:.1%}
- 근거: 각 쟁점별 분석 결과를 종합하여 도출

감사합니다."""
        
        return statement

