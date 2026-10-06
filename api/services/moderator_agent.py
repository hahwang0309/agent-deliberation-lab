"""
행정조사 중복 판별 토론 모더레이터

토론 진행, 중재, 라운드 제어를 담당하는 AI 모더레이터
"""
from typing import Dict, Any, List, Optional, Tuple
from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum

from src.utils.llm_provider import LLMFactory
from src.models.personas import LLMProvider


class DiscussionPhase(str, Enum):
    """토론 단계"""
    OPENING = "opening"  # 개회 (라운드 1-2)
    ANALYSIS = "analysis"  # 초기 분석 (라운드 3-4)
    DEBATE = "debate"  # 심화 토론 (라운드 5-7)
    CONSENSUS = "consensus"  # 합의 도출 (라운드 8-10)
    CLOSING = "closing"  # 종료


class ModeratorDecision(BaseModel):
    """모더레이터 결정"""
    should_continue: bool = Field(description="토론 계속 여부")
    next_round: int = Field(description="다음 라운드 번호")
    reason: str = Field(description="결정 이유")
    guidance: str = Field(description="다음 라운드 가이드")
    phase: DiscussionPhase = Field(description="현재 토론 단계")
    estimated_remaining_rounds: int = Field(description="예상 남은 라운드")


class ConsensusStatus(BaseModel):
    """합의 상태"""
    has_consensus: bool = Field(description="합의 도달 여부")
    consensus_level: float = Field(ge=0.0, le=1.0, description="합의도")
    areas_of_agreement: List[str] = Field(description="합의 영역")
    areas_of_disagreement: List[str] = Field(description="불일치 영역")
    key_arguments: Dict[str, List[str]] = Field(description="페르소나별 핵심 주장")


class RoundSummary(BaseModel):
    """라운드 요약"""
    round_number: int
    phase: DiscussionPhase
    key_points: List[str]
    progress_made: str
    issues_remaining: List[str]


class ModeratorAgent:
    """행정조사 중복 판별 토론 모더레이터"""
    
    MODERATOR_SYSTEM_PROMPT = """당신은 행정조사 중복 판별 토론을 진행하는 전문 모더레이터입니다.

역할:
1. 토론을 공정하고 효율적으로 진행
2. 각 페르소나의 의견을 균형있게 청취
3. 쟁점을 명확히 정리하고 논의 방향 제시
4. 합의 도달 여부 판단 및 토론 종료 시점 결정
5. 최소 3라운드, 최대 10라운드 내에서 결론 도출

원칙:
- 중립적이고 객관적인 태도 유지
- 명확한 근거와 논리에 기반한 판단 유도
- 감정적 대립보다는 사실과 논거 중심으로 유도
- 중복 판별의 공식 기준(A형, C형)을 참고하되 강요하지 않음
- 정량적 평가를 위한 구체적 근거 수집에 집중
- 모든 페르소나의 의견을 존중하되, 반복적 주장은 정리

🎯 토론 목적:
**정확한 루브릭 점수 산출을 위한 근거 수집**

토론의 핵심은 다음 4가지 평가 항목에 대한 정확한 점수 산출입니다:
1. ①-1 조사 대상 모집단의 중복도 (30점 만점)
2. ①-2 실제 조사 대상의 중복 가능성 (20점 만점)
3. ②-1 조사 내용의 중복도 (30점 만점)
4. ②-2 제출 자료의 중복도 (20점 만점)

📚 중복조사 개념 참고:
**중복조사**란 동일한 조사대상자에게 반복적 또는 중첩적으로 시행되어 부담을 가중시키는 경우를 의미합니다.

주요 유형:
- **A형 (대상 중복형)**: 대상은 같으나 조사 내용이 다름
  예) 한 사업장에 근로기준, 산업안전, 직업훈련 조사를 각각 실시
  
- **C형 (복합 중복형)**: 대상과 내용 모두 겹침 (가장 명확한 중복)
  예) 중앙부처와 지자체가 같은 사업장에 유사한 안전점검을 각각 실시

⚠️ 중요: 조사대상이 다르면 내용이 같아도 중복조사로 보지 않음

✅ 토론 진행 원칙:
- 각 항목별로 구체적인 근거와 수치를 도출
- "얼마나 겹치는가?"를 정량적으로 평가 (예: 70% 겹침, 30% 독립적)
- 애매한 표현보다는 명확한 사실 관계 확인
- 최종 판정(중복/비중복)은 점수로 자동 결정되므로 토론에서는 점수 산출에만 집중
"""

    OPENING_PROMPT = """토론을 시작합니다.

<토론 주제>
행정조사 중복 여부 판별

📚 중복조사 판별 기준:
**중복조사**란 동일한 조사대상자에게 반복적 또는 중첩적으로 시행되어 부담을 가중시키는 경우입니다.

**핵심 판단 요소:**
1. ① 조사 대상의 중복성 (50점)
   - 조사 대상 모집단이 얼마나 겹치는가?
   - 실제로 동일 대상자가 두 조사를 모두 받을 가능성은?

2. ② 조사 내용의 중복성 (50점)
   - 조사 목적, 항목, 방법이 얼마나 유사한가?
   - 제출 요구 자료가 얼마나 겹치는가?

**중요 원칙:**
⚠️ 조사대상이 다르면, 내용이 같아도 중복조사로 보지 않습니다.

<행정조사 A>
{investigation_a}

<행정조사 B>
{investigation_b}

<참가자>
{personas}

개회사 및 쟁점 도출:
1. 토론 목적 및 중요성 설명 (중복조사 개념 간단히 언급)
2. 두 행정조사의 개요 소개
3. **주요 쟁점 3-5개 명확히 도출** - 루브릭 4대 평가 항목 중심으로:
   - 조사 대상 모집단의 중복도
   - 실제 조사 대상의 중복 가능성
   - 조사 내용의 중복도
   - 제출 자료의 중복도

JSON 형식으로 응답:
{{
  "opening_statement": "개회사 (3-5문단, 중복조사 개념 포함, 한국어)",
  "key_issues": [
    {{
      "issue_number": 1,
      "title": "쟁점 제목",
      "description": "쟁점 설명",
      "importance": "high/medium/low"
    }}
  ]
}}"""

    ROUND_GUIDANCE_PROMPT = """현재까지의 토론 내용을 검토하고 다음 라운드를 구체적으로 안내하세요.

<현재 상황>
- 라운드: {current_round}/{max_rounds}
- 단계: {phase}

<토론 내용>
{discussion_summary}

<각 페르소나 입장>
{persona_positions}

**중요**: 모더레이터로서 명확한 방향성을 제시하세요:
1. 지금까지 논의된 주요 내용을 3-4문장으로 요약
2. 합의된 사항과 여전히 논쟁 중인 사항을 명확히 구분
3. 다음 라운드에서 집중해야 할 쟁점을 구체적으로 제시
4. 각 페르소나가 고려해야 할 관점이나 질문 제공

JSON 형식으로 응답:
{{
  "summary": "토론 요약 (3-4문장, 구체적으로)",
  "agreements": ["합의사항1", "합의사항2"],
  "disagreements": ["논쟁사항1", "논쟁사항2"],
  "next_focus": "다음 라운드에서 반드시 집중해야 할 핵심 쟁점 (2-3문장, 구체적 질문 포함)",
  "questions": {{
    "persona_name": "이 페르소나가 답해야 할 구체적 질문"
  }}
}}"""

    CONSENSUS_CHECK_PROMPT = """현재 토론 상황에서 합의 도달 여부를 평가하세요.

<토론 내용>
{discussion_summary}

<각 페르소나 최종 입장>
{final_positions}

<평가 기준>
1. 중복 여부에 대한 명확한 입장 표명
2. 페르소나 간 의견 일치도
3. 주요 논거의 합리성 및 근거 충분성
4. 추가 논의 필요성

JSON 형식으로 응답:
{{
  "has_consensus": true/false,
  "consensus_level": 0.0~1.0,
  "duplication_verdict": "중복/비중복/부분중복",
  "areas_of_agreement": ["합의영역1", "합의영역2"],
  "areas_of_disagreement": ["불일치영역1"],
  "key_arguments": {{
    "persona_name": ["핵심주장1", "핵심주장2"]
  }},
  "needs_more_discussion": true/false,
  "reason": "판단 근거 (2-3문장)"
}}"""

    EARLY_TERMINATION_CHECK_PROMPT = """토론을 조기 종료해야 하는지 판단하세요.

<현재 상황>
- 라운드: {current_round}/{min_rounds} (최소) / {max_rounds} (최대)
- 단계: {phase}

<최근 토론>
{recent_discussion}

<조기 종료 조건>
1. 모든 페르소나가 명확한 입장 표명 완료
2. 더 이상 새로운 논점이 제시되지 않음
3. 합의 또는 명확한 의견 분립 확인
4. 반복적 주장만 계속됨

JSON 형식으로 응답:
{{
  "should_terminate": true/false,
  "reason": "판단 근거",
  "confidence": 0.0~1.0
}}"""

    def __init__(
        self,
        llm_provider: LLMProvider = LLMProvider.OPENAI,
        model: Optional[str] = None,
        temperature: float = 0.5,
        min_rounds: int = 3,
        max_rounds: int = 10
    ):
        """
        Args:
            llm_provider: LLM 프로바이더
            model: 모델 이름
            temperature: 생성 온도
            min_rounds: 최소 라운드 수
            max_rounds: 최대 라운드 수
        """
        self.llm_provider = llm_provider
        self.model = model
        self.temperature = temperature
        self.min_rounds = min_rounds
        self.max_rounds = max_rounds
        
        self.llm = LLMFactory.create_llm(
            provider=llm_provider,
            model=model,
            temperature=temperature,
            max_tokens=1500  # 가이드 JSON 생성을 위해 충분한 토큰
        )
        
        # 토론 상태
        self.current_round = 0
        self.round_summaries: List[RoundSummary] = []
        self.discussion_history: List[Dict[str, Any]] = []
    
    def start_discussion(
        self,
        investigation_a: Dict[str, Any],
        investigation_b: Dict[str, Any],
        personas: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        토론 시작 - 개회사 생성
        
        Args:
            investigation_a: 행정조사 A
            investigation_b: 행정조사 B
            personas: 참가 페르소나 목록
            
        Returns:
            개회사 텍스트
        """
        self.current_round = 0
        self.round_summaries = []
        self.discussion_history = []
        
        # 개회사 생성
        prompt = self.OPENING_PROMPT.format(
            investigation_a=self._format_investigation(investigation_a),
            investigation_b=self._format_investigation(investigation_b),
            personas=self._format_personas(personas)
        )
        
        response = self.llm.invoke(
            f"{self.MODERATOR_SYSTEM_PROMPT}\n\n{prompt}"
        )
        
        result = self._extract_json(response.content)
        
        # 기록
        self.discussion_history.append({
            "round": 0,
            "speaker": "모더레이터",
            "type": "opening",
            "content": result,
            "timestamp": datetime.utcnow()
        })
        
        return result
    
    def start_round_on_issue(
        self,
        round_number: int,
        issue: Dict[str, Any],
        previous_rounds_summary: str = ""
    ) -> str:
        """
        특정 쟁점에 대한 라운드 시작
        
        Args:
            round_number: 라운드 번호
            issue: 쟁점 정보 {"title": ..., "description": ..., "importance": ...}
            previous_rounds_summary: 이전 라운드들의 요약
            
        Returns:
            라운드 시작 안내문
        """
        prompt = f"""라운드 {round_number}를 시작합니다.

<이번 라운드 쟁점>
**{issue.get('title', '')}**
{issue.get('description', '')}

<이전 라운드 결론>
{previous_rounds_summary if previous_rounds_summary else '첫 라운드입니다.'}

이번 라운드에서 논의할 내용:
1. 이 쟁점에 대한 각 페르소나의 초기 입장
2. 근거와 논리의 타당성 검토
3. 의견 차이가 있다면 구체적으로 어떤 부분인지 파악
4. 이 쟁점에 대한 부분 합의 도출

라운드 시작 안내문을 3-4문장으로 작성하세요."""
        
        response = self.llm.invoke(
            f"{self.MODERATOR_SYSTEM_PROMPT}\n\n{prompt}"
        )
        
        return response.content
    
    def moderate_turn(
        self,
        round_number: int,
        turn_number: int,
        issue: Dict[str, Any],
        turn_history: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        턴 중재 및 다음 발언 가이드
        
        Args:
            round_number: 라운드 번호
            turn_number: 턴 번호
            issue: 현재 쟁점
            turn_history: 이번 라운드의 턴 히스토리
            
        Returns:
            중재 결과 {"moderation": ..., "questions": ..., "should_continue": bool}
        """
        turn_summary = "\n".join([
            f"[{t['speaker']}] {t['content'][:200]}..."
            for t in turn_history[-6:]  # 최근 6개 발언만
        ])
        
        prompt = f"""라운드 {round_number}, 턴 {turn_number} 중재

<현재 쟁점>
{issue.get('title', '')}

<최근 발언>
{turn_summary}

모더레이터로서:
1. 지금까지 나온 의견들을 2-3문장으로 요약
2. 합의 영역과 불일치 영역 파악
3. 추가 논의가 필요한지, 아니면 합의에 도달했는지 판단
4. 다음 턴에서 필요한 질문이나 요청사항 제시

JSON 형식으로 응답:
{{
  "moderation": "중재 발언 (2-3문장)",
  "agreements": ["합의된 점"],
  "disagreements": ["아직 불일치하는 점"],
  "should_continue_turn": true/false,
  "next_questions": ["다음 턴 질문1", "질문2"],
  "reason": "판단 근거"
}}"""
        
        response = self.llm.invoke(
            f"{self.MODERATOR_SYSTEM_PROMPT}\n\n{prompt}"
        )
        
        return self._extract_json(response.content)
    
    def check_round_consensus(
        self,
        round_number: int,
        issue: Dict[str, Any],
        round_discussion: str
    ) -> Dict[str, Any]:
        """
        라운드 합의 확인 및 결론 도출
        
        Args:
            round_number: 라운드 번호
            issue: 쟁점
            round_discussion: 라운드 전체 토론 내용
            
        Returns:
            라운드 결론
        """
        prompt = f"""라운드 {round_number} 결론 도출

📚 중복조사 개념 참고:
동일한 조사대상자에게 반복적 또는 중첩적으로 시행되어 부담을 가중시키는 경우가 중복조사입니다.

<쟁점>
{issue.get('title', '')}

<토론 내용>
{round_discussion}

이 쟁점에 대한 결론을 도출하세요:
1. 페르소나들의 합의 수준 (0.0~1.0)
2. 합의된 내용 (구체적 근거 포함)
3. 여전히 의견이 갈리는 부분
4. **정량적 평가**: 이 쟁점 항목에서 얼마나 겹치는가? (0-100% 또는 점수)
5. 종합 의견

✅ 평가 원칙:
- 구체적인 겹침 비율이나 정도를 명시
- 예: "대상 모집단의 70%가 겹침", "제출 자료 5개 중 3개가 동일"
- **조사대상이 다르면 내용이 같아도 중복 아님**
- 애매한 표현보다는 명확한 수치와 근거

JSON 형식으로 응답:
{{
  "verdict_for_this_issue": "이 쟁점에 대한 판정 (중복/비중복/부분중복 중 하나)",
  "consensus_level": 0.0~1.0,
  "conclusion": "이 쟁점에 대한 결론 (구체적 근거와 수치 포함, 2-3문장)",
  "agreed_points": ["합의점1 (수치 포함)", "합의점2"],
  "disagreed_points": ["불일치점1"],
  "overlap_percentage": "이 항목의 겹침 정도 (예: 70%, 또는 상/중/하)",
  "confidence": 0.0~1.0
}}"""
        
        response = self.llm.invoke(
            f"{self.MODERATOR_SYSTEM_PROMPT}\n\n{prompt}"
        )
        
        return self._extract_json(response.content)
    
    def guide_next_round(
        self,
        current_round: int,
        discussion_summary: str,
        persona_positions: Dict[str, str]
    ) -> Dict[str, Any]:
        """
        다음 라운드 가이드 생성
        
        Args:
            current_round: 현재 라운드 번호
            discussion_summary: 토론 요약
            persona_positions: 페르소나별 입장
            
        Returns:
            가이드 정보 (dict)
        """
        self.current_round = current_round
        
        # 현재 단계 결정
        phase = self._determine_phase(current_round)
        
        # 가이드 생성
        prompt = self.ROUND_GUIDANCE_PROMPT.format(
            current_round=current_round,
            max_rounds=self.max_rounds,
            phase=phase.value,
            discussion_summary=discussion_summary,
            persona_positions=self._format_positions(persona_positions)
        )
        
        response = self.llm.invoke(
            f"{self.MODERATOR_SYSTEM_PROMPT}\n\n{prompt}"
        )
        
        guidance = self._extract_json(response.content)
        guidance["phase"] = phase.value
        guidance["round"] = current_round
        
        # 기록
        self.discussion_history.append({
            "round": current_round,
            "speaker": "모더레이터",
            "type": "guidance",
            "content": guidance,
            "timestamp": datetime.utcnow()
        })
        
        return guidance
    
    def check_consensus(
        self,
        discussion_summary: str,
        final_positions: Dict[str, str]
    ) -> ConsensusStatus:
        """
        합의 상태 확인
        
        Args:
            discussion_summary: 전체 토론 요약
            final_positions: 페르소나별 최종 입장
            
        Returns:
            ConsensusStatus
        """
        prompt = self.CONSENSUS_CHECK_PROMPT.format(
            discussion_summary=discussion_summary,
            final_positions=self._format_positions(final_positions)
        )
        
        response = self.llm.invoke(
            f"{self.MODERATOR_SYSTEM_PROMPT}\n\n{prompt}"
        )
        
        result = self._extract_json(response.content)
        
        # 안전하게 리스트 처리 (중첩 리스트 flatten)
        def safe_list(items):
            """리스트를 안전하게 처리 (중첩 제거)"""
            if not items:
                return []
            safe_items = []
            for item in items:
                if isinstance(item, list):
                    # 중첩된 리스트면 첫 항목만 사용
                    safe_items.extend([str(x) for x in item if x])
                elif isinstance(item, str):
                    safe_items.append(item)
                else:
                    safe_items.append(str(item))
            return safe_items
        
        # key_arguments도 안전하게 처리
        def safe_key_arguments(args_dict):
            """key_arguments를 안전하게 처리"""
            if not args_dict or not isinstance(args_dict, dict):
                return {}
            result = {}
            for persona, args in args_dict.items():
                if isinstance(args, list):
                    result[persona] = [str(arg) for arg in args if arg]
                elif isinstance(args, str):
                    result[persona] = [args]
                else:
                    result[persona] = [str(args)]
            return result
        
        return ConsensusStatus(
            has_consensus=result.get("has_consensus", False),
            consensus_level=result.get("consensus_level", 0.0),
            areas_of_agreement=safe_list(result.get("areas_of_agreement", [])),
            areas_of_disagreement=safe_list(result.get("areas_of_disagreement", [])),
            key_arguments=safe_key_arguments(result.get("key_arguments", {}))
        )
    
    def should_continue(
        self,
        current_round: int,
        recent_discussion: str
    ) -> ModeratorDecision:
        """
        토론 계속 여부 결정
        
        Args:
            current_round: 현재 라운드
            recent_discussion: 최근 토론 내용
            
        Returns:
            ModeratorDecision
        """
        phase = self._determine_phase(current_round)
        
        # 최대 라운드 도달
        if current_round >= self.max_rounds:
            return ModeratorDecision(
                should_continue=False,
                next_round=current_round + 1,
                reason="최대 라운드 도달",
                guidance="토론을 종료하고 최종 결론을 도출합니다.",
                phase=DiscussionPhase.CLOSING,
                estimated_remaining_rounds=0
            )
        
        # 최소 라운드 미달
        if current_round < self.min_rounds:
            return ModeratorDecision(
                should_continue=True,
                next_round=current_round + 1,
                reason=f"최소 {self.min_rounds}라운드 필요",
                guidance=self._generate_phase_guidance(phase, current_round),
                phase=phase,
                estimated_remaining_rounds=self.min_rounds - current_round
            )
        
        # 조기 종료 검토 (최소 라운드 이상)
        termination_check = self._check_early_termination(
            current_round,
            recent_discussion
        )
        
        if termination_check["should_terminate"]:
            return ModeratorDecision(
                should_continue=False,
                next_round=current_round + 1,
                reason=termination_check["reason"],
                guidance="충분한 논의가 이루어졌습니다. 최종 결론을 도출합니다.",
                phase=DiscussionPhase.CLOSING,
                estimated_remaining_rounds=0
            )
        
        # 계속 진행
        return ModeratorDecision(
            should_continue=True,
            next_round=current_round + 1,
            reason="추가 논의 필요",
            guidance=self._generate_phase_guidance(phase, current_round),
            phase=phase,
            estimated_remaining_rounds=max(
                self.max_rounds - current_round,
                2  # 최소 2라운드 더
            )
        )
    
    def _check_early_termination(
        self,
        current_round: int,
        recent_discussion: str
    ) -> Dict[str, Any]:
        """조기 종료 여부 확인"""
        prompt = self.EARLY_TERMINATION_CHECK_PROMPT.format(
            current_round=current_round,
            min_rounds=self.min_rounds,
            max_rounds=self.max_rounds,
            phase=self._determine_phase(current_round).value,
            recent_discussion=recent_discussion
        )
        
        response = self.llm.invoke(
            f"{self.MODERATOR_SYSTEM_PROMPT}\n\n{prompt}"
        )
        
        return self._extract_json(response.content)
    
    def _determine_phase(self, round_number: int) -> DiscussionPhase:
        """라운드 번호에 따른 토론 단계 결정"""
        if round_number <= 2:
            return DiscussionPhase.OPENING
        elif round_number <= 4:
            return DiscussionPhase.ANALYSIS
        elif round_number <= 7:
            return DiscussionPhase.DEBATE
        elif round_number <= 10:
            return DiscussionPhase.CONSENSUS
        else:
            return DiscussionPhase.CLOSING
    
    def _generate_phase_guidance(
        self,
        phase: DiscussionPhase,
        round_number: int
    ) -> str:
        """단계별 가이드 메시지"""
        guidance_map = {
            DiscussionPhase.OPENING: f"라운드 {round_number}: 두 행정조사의 기본 정보를 분석하고 각자의 관점을 제시해주세요.",
            DiscussionPhase.ANALYSIS: f"라운드 {round_number}: 대상 동일성과 내용 유사성을 구체적으로 분석해주세요.",
            DiscussionPhase.DEBATE: f"라운드 {round_number}: 다른 페르소나의 의견에 대한 반론이나 보완 의견을 제시해주세요.",
            DiscussionPhase.CONSENSUS: f"라운드 {round_number}: 최종 입장을 정리하고 중복 여부에 대한 결론을 제시해주세요.",
            DiscussionPhase.CLOSING: "토론을 마무리하고 최종 합의안을 도출합니다."
        }
        return guidance_map.get(phase, "다음 라운드를 진행합니다.")
    
    def _format_investigation(self, inv: Dict[str, Any]) -> str:
        """행정조사 정보 포맷팅"""
        return f"""
- 이름: {inv.get('name', '')}
- 목적: {inv.get('purpose', '')}
- 대상: {inv.get('target', '')}
- 범위: {inv.get('scope', '')}
- 주관: {inv.get('department', '')}
""".strip()
    
    def _format_personas(self, personas: List[Dict[str, Any]]) -> str:
        """페르소나 목록 포맷팅"""
        result = []
        for p in personas:
            result.append(f"- {p.get('name', '')} ({p.get('role', '')})")
        return "\n".join(result)
    
    def _format_classification(self, classification: Optional[Dict[str, Any]]) -> str:
        """초기 분류 결과 포맷팅"""
        if not classification:
            return "초기 분류를 진행하지 않았습니다."
        
        return f"""
- 판별 결과: {classification.get('is_duplicate', 'N/A')}
- 유형: {classification.get('duplication_type', 'N/A')}
- 신뢰도: {classification.get('confidence', 0):.2%}
""".strip()
    
    def _format_positions(self, positions: Dict[str, str]) -> str:
        """페르소나별 입장 포맷팅"""
        result = []
        for persona, position in positions.items():
            result.append(f"[{persona}]\n{position}\n")
        return "\n".join(result)
    
    def _extract_json(self, content: str) -> Dict[str, Any]:
        """LLM 응답에서 JSON 추출 (robust)"""
        import json
        import re
        
        json_str = ""
        
        # 1단계: 코드 블록에서 JSON 추출
        if "```json" in content:
            match = re.search(r'```json\s*\n?(.*?)\n?```', content, re.DOTALL)
            if match:
                json_str = match.group(1).strip()
        elif "```" in content:
            match = re.search(r'```\s*\n?(.*?)\n?```', content, re.DOTALL)
            if match:
                json_str = match.group(1).strip()
        
        # 2단계: 코드 블록이 없으면 중괄호로 추출
        if not json_str:
            start = content.find("{")
            if start != -1:
                brace_count = 0
                for i in range(start, len(content)):
                    if content[i] == '{':
                        brace_count += 1
                    elif content[i] == '}':
                        brace_count -= 1
                        if brace_count == 0:
                            json_str = content[start:i+1]
                            break
        
        if not json_str:
            raise ValueError(f"JSON을 찾을 수 없습니다. Content: {content[:200]}")
        
        # 3단계: JSON 정리
        json_str = re.sub(r'^\s*//.*$', '', json_str, flags=re.MULTILINE)
        json_str = re.sub(r',(\s*[}\]])', r'\1', json_str)
        
        # 4단계: 파싱
        try:
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            try:
                return json.loads(json_str, strict=False)
            except:
                raise ValueError(f"JSON 파싱 실패: {str(e)}")
    
    def generate_closing_statement(
        self,
        consensus_status: ConsensusStatus,
        final_verdict: str
    ) -> str:
        """토론 종료 - 폐회사 생성"""
        prompt = f"""토론을 마무리하는 폐회사를 작성하세요.

<합의 상태>
- 합의 도달: {consensus_status.has_consensus}
- 합의도: {consensus_status.consensus_level:.2%}
- 최종 판정: {final_verdict}

<합의 영역>
{chr(10).join(f'- {area}' for area in consensus_status.areas_of_agreement)}

<불일치 영역>
{chr(10).join(f'- {area}' for area in consensus_status.areas_of_disagreement)}

폐회사에 포함할 내용:
1. 토론 과정 요약
2. 각 페르소나의 기여 인정
3. 도달한 결론 명확히 제시
4. 합의되지 않은 부분 언급 (있는 경우)
5. 향후 권고사항

한국어로 3-5문단, 격식있고 명확하게 작성하세요."""
        
        response = self.llm.invoke(
            f"{self.MODERATOR_SYSTEM_PROMPT}\n\n{prompt}"
        )
        
        return response.content

