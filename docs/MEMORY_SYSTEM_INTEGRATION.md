# 페르소나 메모리 시스템 통합 가이드

> 페르소나별 대화 메모리를 관리하여 토론의 일관성과 상호작용을 강화하는 시스템

**작성일**: 2025-11-18
**버전**: 1.0.0

---

## 목차

- [1. 개요](#1-개요)
- [2. 메모리 시스템 구조](#2-메모리-시스템-구조)
- [3. 통합 방법](#3-통합-방법)
- [4. 사용 예시](#4-사용-예시)
- [5. 고급 기능](#5-고급-기능)
- [6. 테스트](#6-테스트)

---

## 1. 개요

### 1.1 왜 메모리가 필요한가?

**현재 문제점**:
- ❌ 페르소나가 이전 발언을 잊어버림
- ❌ 입장이 라운드마다 일관성 없이 변함
- ❌ 다른 페르소나와의 과거 대화를 기억하지 못함
- ❌ 토론 흐름이 단절됨

**메모리 시스템 도입 효과**:
- ✅ 페르소나가 자신의 이전 발언을 기억
- ✅ 입장 변화 시 이유를 설명할 수 있음
- ✅ 특정 페르소나와의 과거 대화를 참고하여 응답
- ✅ 토론이 자연스럽게 이어짐

### 1.2 메모리 종류

1. **자신의 발언 이력**: 내가 언제 무엇을 말했는지
2. **상호작용 기록**: 누구와 어떤 대화를 나눴는지, 동의도는?
3. **입장 변화 추적**: 쟁점별로 내 입장이 어떻게 변했는지
4. **동료 평가**: 다른 페르소나에 대한 신뢰도, 동의도
5. **단기/장기 메모리**: 최근 기억과 중요한 기억 구분

---

## 2. 메모리 시스템 구조

### 2.1 클래스 구조

```
src/models/persona_memory.py
├── PersonaMemory          # 개별 페르소나의 메모리
│   ├── my_statements      # 자신의 발언 목록
│   ├── interactions       # 다른 페르소나와의 대화 기록
│   ├── position_evolution # 쟁점별 입장 변화
│   ├── peer_impressions   # 동료 평가
│   ├── short_term_memory  # 단기 메모리 (최근 5개)
│   └── long_term_memory   # 장기 메모리 (중요 발언)

src/services/memory_manager.py
└── MemoryManager          # 모든 페르소나의 메모리 통합 관리
    ├── memories: Dict[str, PersonaMemory]
    ├── record_statement()      # 발언 기록
    ├── record_interaction()    # 상호작용 기록
    ├── get_context_for_persona()  # 컨텍스트 조회
    └── analyze_discussion_dynamics()  # 토론 분석
```

### 2.2 데이터 흐름

```
1. 페르소나 생성
   ↓
2. MemoryManager 초기화
   ↓
3. 토론 진행
   ├─ 발언 시 → record_statement()
   ├─ 응답 시 → get_context_for_persona()
   └─ 상호작용 → record_interaction()
   ↓
4. 라운드 종료
   ↓
5. 메모리 분석 → analyze_discussion_dynamics()
   ↓
6. 보고서 생성 → export_memory_for_report()
```

---

## 3. 통합 방법

### 3.1 investigation_discussion_service.py 수정

**Step 1: import 추가**

```python
# investigation_discussion_service.py 상단에 추가
from src.services.memory_manager import MemoryManager
```

**Step 2: __init__에 memory_manager 추가**

```python
class InvestigationDiscussionService:
    def __init__(self, ...):
        # ... 기존 코드 ...
        self.memory_manager = None  # 토론 시작 시 초기화
```

**Step 3: conduct_discussion에서 초기화**

```python
async def conduct_discussion(
    self,
    investigation_a: Dict[str, Any],
    investigation_b: Dict[str, Any],
    num_personas: Optional[int] = None,
    discussion_id: Optional[str] = None
) -> InvestigationDiscussionResult:
    # ... 페르소나 생성 코드 ...

    personas = persona_result.personas

    # 🆕 메모리 매니저 초기화
    self.memory_manager = MemoryManager(personas)

    # ... 토론 진행 ...
```

**Step 4: 발언 생성 시 메모리 활용**

`_generate_persona_statement_for_issue` 함수 수정:

```python
async def _generate_persona_statement_for_issue(
    self,
    persona: GeneratedPersona,
    round_number: int,
    turn_number: int,
    issue: Dict[str, Any],
    investigation_a: Dict[str, Any],
    investigation_b: Dict[str, Any],
    turn_history: List[Dict[str, Any]],
    shared_evidence: Optional[Dict[str, Any]] = None,
    target_persona: Optional[str] = None  # 🆕 추가
) -> Tuple[str, Optional[Dict[str, Any]]]:
    """메모리 기반 발언 생성"""
    from src.utils.llm_provider import LLMFactory

    # 🆕 메모리에서 컨텍스트 가져오기
    memory_context = ""
    if self.memory_manager:
        memory_context = self.memory_manager.get_context_for_persona(
            persona.name,
            issue.get('title'),
            target_persona
        )

    # ... 기존 LLM 설정 코드 ...

    inv_a_text = investigation_a.get('raw_text', '') or str(investigation_a)
    inv_b_text = investigation_b.get('raw_text', '') or str(investigation_b)

    # 최근 발언들
    recent_statements = "\n".join([
        f"[{t['speaker']}] {t['content'][:200]}..."
        for t in turn_history[-4:]
    ]) if turn_history else "첫 턴입니다."

    prompt = f"""당신은 {persona.name}({persona.role})입니다.

<당신의 전문성>
{persona.expertise}

<당신의 관점>
{persona.perspective}

📚 중복조사의 개념
...

<행정조사 A 상세>
{inv_a_text}

<행정조사 B 상세>
{inv_b_text}

<현재 논의 중인 쟁점>
**{issue.get('title', '')}**
{issue.get('description', '')}

🧠 **당신의 기억** (이전 토론 내용)
{memory_context if memory_context else "첫 발언입니다."}

<최근 다른 참가자들의 발언>
{recent_statements}

**발언 지침**:
1. 이번 라운드의 쟁점("{issue.get('title', '')}")에만 집중하세요
2. 조사 A, B의 구체적 내용을 근거로 제시
3. **🆕 당신의 기억을 활용하세요**:
   - 이전에 발언한 내용과 일관성 유지
   - 입장이 바뀌었다면 그 이유 설명
   - 다른 참가자와의 과거 대화 참고
"""

    if target_persona:
        prompt += f"\n4. {target_persona} 씨에게 직접 답변하는 형식으로 작성하세요.\n"

    prompt += "\n2-3문단으로 간결하게 작성하세요."

    # 🆕 RAG 증거 추가 (기존 코드)
    if shared_evidence:
        # ...

    # 토큰 단위 스트리밍 (기존 코드)
    full_content = ""
    for chunk in llm.stream(prompt):
        if hasattr(chunk, 'content'):
            token = chunk.content
            full_content += token

            self._emit_event('persona_token', {
                'name': persona.name,
                'token': token
            })

    # 🆕 메모리에 발언 기록
    if self.memory_manager:
        self.memory_manager.record_statement(
            persona.name,
            round_number,
            issue.get('title'),
            full_content,
            reasoning=""  # 추론 과정도 기록 가능
        )

    return full_content, rag_metadata
```

**Step 5: 상호작용 기록**

상호작용이 발생하는 곳에 추가 (예: reactor가 speaker에게 응답할 때):

```python
# 예시: _conduct_interactive_round 함수 내
for reactor in reactors:
    reaction, _ = await self._generate_persona_statement_for_issue(
        persona=reactor,
        round_number=round_number,
        turn_number=turn,
        issue=issue,
        investigation_a=investigation_a,
        investigation_b=investigation_b,
        turn_history=[{
            'speaker': speaker.name,
            'content': main_statement
        }],
        target_persona=speaker.name  # 🆕 타겟 명시
    )

    # 🆕 상호작용 기록
    if self.memory_manager:
        self.memory_manager.record_interaction(
            speaker.name,
            reactor.name,
            round_number,
            main_statement,
            reaction
        )
```

**Step 6: 보고서에 메모리 분석 추가**

```python
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
    """최종 보고서 생성 (메모리 분석 포함)"""

    # ... 기존 보고서 섹션 ...

    # 🆕 메모리 분석 섹션 추가
    if self.memory_manager:
        memory_report = self._generate_memory_analysis_section()
        report += f"\n\n---\n\n## 8. 토론 역학 분석 (메모리 기반)\n\n{memory_report}\n"

    return report

def _generate_memory_analysis_section(self) -> str:
    """메모리 분석 섹션 생성"""
    if not self.memory_manager:
        return ""

    dynamics = self.memory_manager.analyze_discussion_dynamics()
    memory_data = self.memory_manager.export_memory_for_report()

    analysis = "### 페르소나별 활동 요약\n\n"

    for persona_name, stats in dynamics['personas'].items():
        analysis += f"#### {persona_name}\n\n"
        analysis += f"- 발언 횟수: {stats['total_statements']}회\n"
        analysis += f"- 상호작용: {stats['interaction_count']}회\n"
        analysis += f"- 입장 변화: {stats['position_changes']}회\n"

        if stats['most_trusted_peer']:
            analysis += f"- 가장 신뢰하는 동료: {stats['most_trusted_peer']}\n"

        analysis += f"- 평균 동의도: {stats['avg_agreement_with_others']:.0%}\n"
        analysis += f"- 입장 안정성: {dynamics['position_stability'][persona_name]:.2f}\n\n"

    analysis += "\n### 상호작용 네트워크\n\n"
    analysis += "| 상호작용 | 횟수 | 평균 동의도 |\n"
    analysis += "|----------|------|-------------|\n"

    for interaction, data in dynamics['interaction_network'].items():
        analysis += f"| {interaction} | {data['count']}회 | {data['avg_agreement']:.0%} |\n"

    return analysis
```

---

## 4. 사용 예시

### 4.1 기본 사용

```python
# 토론 서비스 생성
service = InvestigationDiscussionService(
    llm_provider=LLMProvider.OPENAI,
    model="gpt-4o-mini",
    min_rounds=3,
    max_rounds=10
)

# 토론 실행 (메모리는 자동으로 관리됨)
result = await service.conduct_discussion(
    investigation_a=inv_a,
    investigation_b=inv_b
)

# 메모리 분석 확인
if service.memory_manager:
    dynamics = service.memory_manager.analyze_discussion_dynamics()
    print("토론 역학:", dynamics)
```

### 4.2 특정 페르소나의 메모리 확인

```python
# 특정 페르소나의 메모리 요약
summary = service.memory_manager.get_memory_summary("김지혜")
print(f"김지혜의 발언 횟수: {summary['total_statements']}")
print(f"상호작용: {summary['interactions_count']}")
print(f"입장 변화: {summary['position_changes']}")
```

### 4.3 보고서 데이터 추출

```python
# 보고서용 메모리 데이터
report_data = service.memory_manager.export_memory_for_report()

for persona_name, data in report_data['personas'].items():
    print(f"\n{persona_name}:")
    print(f"  발언: {data['발언_횟수']}회")

    if data['입장_변화']:
        print("  입장 변화:")
        for issue, changes in data['입장_변화'].items():
            print(f"    {issue}:")
            for change in changes:
                print(f"      라운드 {change['라운드']}: {change['입장']} ({change['신뢰도']})")
```

---

## 5. 고급 기능

### 5.1 LLM 기반 동의도 계산

현재는 키워드 기반으로 동의도를 계산하지만, LLM을 사용하면 더 정확합니다:

```python
# memory_manager.py의 _calculate_agreement 함수 수정

def _calculate_agreement_with_llm(self, stmt1: str, stmt2: str) -> float:
    """LLM 기반 동의도 계산"""
    from src.utils.llm_provider import LLMFactory

    llm = LLMFactory.create_llm(
        provider=LLMProvider.OPENAI,
        model="gpt-4o-mini",
        temperature=0.3
    )

    prompt = f"""다음 두 발언 간의 동의도를 0.0 ~ 1.0 사이의 숫자로 평가하세요.

발언 1:
{stmt1[:300]}

발언 2:
{stmt2[:300]}

평가 기준:
- 1.0: 완전히 동의
- 0.7-0.9: 대부분 동의
- 0.5-0.6: 부분 동의
- 0.3-0.4: 부분 반대
- 0.0-0.2: 완전 반대

숫자만 응답하세요:"""

    response = llm.invoke(prompt)

    try:
        agreement = float(response.content.strip())
        return max(0.0, min(1.0, agreement))
    except:
        return 0.5  # 파싱 실패 시 중립
```

### 5.2 입장 변화 자동 감지

페르소나의 입장 변화를 LLM으로 자동 감지:

```python
async def _detect_position_change(
    self,
    persona_name: str,
    issue: str,
    current_statement: str,
    round_num: int
):
    """입장 변화 자동 감지 및 기록"""
    if not self.memory_manager:
        return

    # 이전 입장 가져오기
    memory = self.memory_manager.memories[persona_name]

    if issue in memory.position_evolution:
        previous_positions = memory.position_evolution[issue]
        if previous_positions:
            last_position = previous_positions[-1]

            # LLM으로 입장 변화 감지
            position_info = await self._analyze_position(
                current_statement, last_position.position
            )

            if position_info['position'] != last_position.position:
                # 입장이 바뀌었음
                self.memory_manager.update_position(
                    persona_name,
                    issue,
                    round_num,
                    position_info['position'],
                    position_info['confidence'],
                    position_info['reasoning']
                )
```

### 5.3 핵심 논점 자동 추출

LLM으로 핵심 논점을 자동 추출하여 장기 메모리에 저장:

```python
async def _extract_key_takeaways(
    self,
    persona_name: str,
    round_messages: List[str]
):
    """핵심 논점 추출"""
    if not self.memory_manager:
        return

    from src.utils.llm_provider import LLMFactory

    llm = LLMFactory.create_llm(
        provider=LLMProvider.OPENAI,
        model="gpt-4o-mini"
    )

    discussion_text = "\n\n".join(round_messages)

    prompt = f"""다음 토론 내용에서 핵심 논점 3가지를 추출하세요.

{discussion_text[:1000]}

각 논점은 한 문장으로 요약하세요:
1.
2.
3."""

    response = llm.invoke(prompt)
    takeaways = response.content.strip().split('\n')

    memory = self.memory_manager.memories[persona_name]
    for takeaway in takeaways[:3]:
        if takeaway.strip():
            memory.extract_key_takeaway(takeaway.strip())
```

---

## 6. 테스트

### 6.1 단위 테스트

```python
# tests/test_memory_manager.py

import pytest
from src.services.memory_manager import MemoryManager
from api.services.persona_auto_generator import GeneratedPersona

def test_memory_manager_initialization():
    """메모리 매니저 초기화 테스트"""
    personas = [
        GeneratedPersona(
            name="김지혜",
            role="세무전문가",
            expertise="법인세",
            perspective="분석적",
            style="논리적",
            background=""
        ),
        GeneratedPersona(
            name="박민수",
            role="통계전문가",
            expertise="데이터 분석",
            perspective="객관적",
            style="수치 중심",
            background=""
        )
    ]

    manager = MemoryManager(personas)

    assert len(manager.memories) == 2
    assert "김지혜" in manager.memories
    assert "박민수" in manager.memories

def test_record_statement():
    """발언 기록 테스트"""
    # ... 페르소나 생성 ...

    manager = MemoryManager(personas)

    manager.record_statement(
        "김지혜",
        round_num=1,
        issue="조사대상 동일성",
        content="두 조사의 대상이 70% 정도 겹친다고 봅니다.",
        reasoning="법적 근거 분석 결과"
    )

    memory = manager.memories["김지혜"]
    assert len(memory.my_statements) == 1
    assert memory.my_statements[0]['issue'] == "조사대상 동일성"

def test_record_interaction():
    """상호작용 기록 테스트"""
    # ... 페르소나 생성 ...

    manager = MemoryManager(personas)

    manager.record_interaction(
        speaker="김지혜",
        responder="박민수",
        round_num=1,
        speaker_statement="대상이 70% 겹칩니다.",
        responder_statement="동의합니다. 통계적으로도 유의미한 중복입니다."
    )

    kim_memory = manager.memories["김지혜"]
    park_memory = manager.memories["박민수"]

    assert "박민수" in kim_memory.interactions
    assert "김지혜" in park_memory.interactions

    # 동의도 체크 (키워드 '동의'가 있으므로 높아야 함)
    interaction = park_memory.interactions["김지혜"][0]
    assert interaction.agreement_level > 0.6

def test_get_context():
    """컨텍스트 조회 테스트"""
    # ... 발언 및 상호작용 기록 ...

    context = manager.get_context_for_persona(
        "김지혜",
        current_issue="조사대상 동일성",
        target_persona="박민수"
    )

    assert "내 이전 입장" in context
    assert "박민수와의 과거 대화" in context
```

### 6.2 통합 테스트

```python
# tests/test_investigation_with_memory.py

import pytest
from api.services.investigation_discussion_service import InvestigationDiscussionService
from src.models.personas import LLMProvider

@pytest.mark.asyncio
async def test_discussion_with_memory():
    """메모리 시스템이 통합된 토론 테스트"""

    service = InvestigationDiscussionService(
        llm_provider=LLMProvider.OPENAI,
        model="gpt-4o-mini",
        min_rounds=2,
        max_rounds=3
    )

    inv_a = {
        "raw_text": "조사A: 서울시 식품제조업소 대상 위생 점검..."
    }

    inv_b = {
        "raw_text": "조사B: 서울시 식품업소 대상 안전 조사..."
    }

    result = await service.conduct_discussion(
        investigation_a=inv_a,
        investigation_b=inv_b,
        num_personas=3
    )

    # 메모리 매니저가 초기화되었는지 확인
    assert service.memory_manager is not None

    # 각 페르소나가 발언했는지 확인
    for persona in result.personas:
        summary = service.memory_manager.get_memory_summary(persona.name)
        assert summary['total_statements'] > 0

    # 상호작용이 기록되었는지 확인
    dynamics = service.memory_manager.analyze_discussion_dynamics()
    assert len(dynamics['interaction_network']) > 0
```

---

## 7. 성능 고려사항

### 7.1 메모리 크기 제한

메모리가 너무 커지면 프롬프트 길이가 증가하므로:

```python
# persona_memory.py에서 이미 구현됨
- 단기 메모리: 최대 5개
- 장기 메모리: 최대 10개
- 컨텍스트 최대 길이: 500자
```

### 7.2 메모리 압축

장기간 토론 시 메모리 압축:

```python
def compress_memory(self, persona_name: str):
    """메모리 압축 (LLM으로 요약)"""
    memory = self.memories[persona_name]

    # 오래된 발언들을 요약
    if len(memory.my_statements) > 20:
        old_statements = memory.my_statements[:10]

        # LLM으로 요약
        summary = await self._summarize_statements(old_statements)

        # 요약을 장기 메모리에 저장하고 원본 삭제
        memory.long_term_memory.append(MemoryItem(
            type="summary",
            round=old_statements[-1]['round'],
            content=summary
        ))

        memory.my_statements = memory.my_statements[10:]
```

---

## 8. 트러블슈팅

### 8.1 메모리가 비어있음

**증상**: `get_context_for_persona`가 빈 문자열 반환

**원인**: 메모리 매니저가 초기화되지 않았거나 발언이 기록되지 않음

**해결**:
```python
# conduct_discussion에서 memory_manager 초기화 확인
if self.memory_manager is None:
    self.memory_manager = MemoryManager(personas)
```

### 8.2 프롬프트가 너무 김

**증상**: LLM 토큰 제한 초과

**원인**: 메모리 컨텍스트가 너무 큼

**해결**:
```python
# get_context_for_response에서 max_context_length 조절
context = memory.get_context_for_response(
    issue, target_persona, max_context_length=300  # 줄임
)
```

### 8.3 동의도 계산이 부정확

**증상**: 명백히 동의하는데 낮은 점수

**원인**: 키워드 기반 계산의 한계

**해결**: LLM 기반 동의도 계산으로 변경 (5.1 참고)

---

## 9. 향후 개선 방향

### 9.1 벡터 DB 활용

현재는 메모리를 메모리(RAM)에만 저장하지만, 벡터 DB를 사용하면:

- ✅ 장기간 토론 지원
- ✅ 의미 기반 유사 발언 검색
- ✅ 대규모 토론 이력 관리

```python
# 예시: ChromaDB 사용
from chromadb import Client

class VectorMemoryManager(MemoryManager):
    def __init__(self, personas, vector_db_path):
        super().__init__(personas)
        self.chroma_client = Client(vector_db_path)
        self.collection = self.chroma_client.create_collection("persona_memories")

    def search_similar_statements(self, query: str, top_k=3):
        """의미 기반 유사 발언 검색"""
        results = self.collection.query(
            query_texts=[query],
            n_results=top_k
        )
        return results
```

### 9.2 감정 추적

페르소나의 감정 상태도 메모리에 추가:

```python
class EmotionalMemory(PersonaMemory):
    def __init__(self, ...):
        super().__init__(...)
        self.emotional_state = {
            "frustration": 0.0,  # 좌절감
            "confidence": 0.5,   # 자신감
            "agreement": 0.5     # 합의 의지
        }
```

### 9.3 메타 학습

여러 토론에서 학습:

```python
class MetaLearningMemory:
    """여러 토론에서 학습한 패턴"""

    def learn_from_discussion(self, discussion_result):
        """토론 결과에서 패턴 학습"""
        # 어떤 전문가 조합이 효과적이었는지
        # 어떤 논증 방식이 설득력 있었는지
        pass
```

---

## 10. 관련 문서

- [FEATURES.md](./FEATURES.md) - 전체 기능 목록
- [ARCHITECTURE.md](./ARCHITECTURE.md) - 시스템 아키텍처
- [API_REFERENCE.md](./API_REFERENCE.md) - API 명세

---

**문서 작성일**: 2025-11-18
**버전**: 1.0.0
**작성자**: Claude Code
