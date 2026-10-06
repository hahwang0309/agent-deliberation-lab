# 행정조사 중복 판별 서비스 플로우

## 🔄 전체 프로세스

```
┌─────────────────────────────────────────────────────────────┐
│ 1. 입력: 두 개의 행정조사 정보                                │
│    - 행정조사 A (이름, 목적, 대상, 범위, 방법, 주기, 법적근거) │
│    - 행정조사 B (동일 구조)                                   │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│ 2. 페르소나 자동 생성 (PersonaAutoGenerator)                  │
│    - LLM이 조사 내용 분석                                     │
│    - 최적의 전문가 페르소나 3~5명 생성                        │
│    - 예: 법률전문가, 행정실무자, 데이터분석가 등              │
│    - 품질 체크 (다양성 점수, 역할 중복 검사)                  │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│ 3. 사전 중복 판별 (DuplicationClassifier)                     │
│    - 대상 유사도 분석 (80% 이상 → 동일)                      │
│    - 내용 유사도 분석 (70% 이상 → 유사)                      │
│    - 목적, 방법, 시기 등 종합 분석                           │
│    - 공식 기준 적용하여 유형 분류:                           │
│      * A-1: 단일기관 다목적 조사                             │
│      * A-2: 다기관 다목적 조사                               │
│      * C-1: 단일기관 중복                                    │
│      * C-2: 다기관 중복                                      │
│      * NONE: 중복 아님                                       │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│ 4. 토론 시작 (ModeratorAgent)                                 │
│    - 모더레이터가 개회사 작성                                 │
│    - 토론 주제 및 쟁점 제시                                   │
│    - 초기 판별 결과 공유                                     │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│ 5. 라운드별 토론 진행 (3~10 라운드)                          │
│                                                              │
│ [라운드 1-2] OPENING - 초기 분석                             │
│   - 모더레이터: 라운드 가이드 제공                           │
│   - 각 페르소나: 자신의 관점에서 초기 분석 발표               │
│                                                              │
│ [라운드 3-4] ANALYSIS - 심화 분석                            │
│   - 대상 동일성 구체적 분석                                  │
│   - 내용 유사성 상세 검토                                    │
│   - 법적/실무적 관점 제시                                    │
│                                                              │
│ [라운드 5-7] DEBATE - 토론 및 반론                           │
│   - 다른 페르소나 의견에 대한 반론                           │
│   - 쟁점 심화                                               │
│   - 근거 강화                                               │
│                                                              │
│ [라운드 8-10] CONSENSUS - 합의 도출                          │
│   - 최종 입장 정리                                          │
│   - 중복 여부 결론                                          │
│   - 권고사항 제시                                           │
│                                                              │
│ ※ 조기 종료 조건 (최소 3라운드 이후):                        │
│   - 명확한 합의 도달                                        │
│   - 새로운 논점 없음                                        │
│   - 반복적 주장만 계속                                      │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│ 6. 합의 상태 확인 (ModeratorAgent)                            │
│    - 합의 도달 여부 판단                                     │
│    - 합의도 계산 (0.0 ~ 1.0)                                 │
│    - 합의/불일치 영역 정리                                   │
│    - 페르소나별 핵심 주장 요약                               │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│ 7. 최종 판정 결정                                            │
│    - 토론 합의 결과 + 사전 판별 결과 종합                     │
│    - 최종 판정: "중복" / "비중복" / "부분중복"               │
│    - 신뢰도 점수 산출                                        │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│ 8. 보고서 생성                                               │
│    - Markdown 형식의 종합 보고서                             │
│    - 포함 내용:                                             │
│      * 요약 (판별 결과, 신뢰도)                              │
│      * 조사 개요                                            │
│      * 사전 분석 결과                                        │
│      * 토론 참가자 소개                                      │
│      * 라운드별 토론 내용                                    │
│      * 종합 평가 (합의/불일치 영역)                          │
│      * 권고사항                                             │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│ 9. 출력: 분석 결과                                           │
│    - discussion_id                                           │
│    - 최종 판정 (중복/비중복/부분중복)                         │
│    - 판정 근거 및 상세 분석                                  │
│    - 전체 보고서 (Markdown)                                  │
│    - 페르소나 정보                                           │
│    - 라운드별 토론 기록                                      │
└─────────────────────────────────────────────────────────────┘
```

---

## 🎯 주요 컴포넌트

### 1. PersonaAutoGenerator
**역할**: 조사 특성에 맞는 전문가 페르소나 자동 생성

**입력**:
```python
{
  "investigation_a": {...},
  "investigation_b": {...}
}
```

**출력**:
```python
{
  "personas": [
    {
      "name": "김법률",
      "role": "행정법 전문가",
      "expertise": "행정법, 행정절차법, 정보공개",
      "perspective": "법적 근거와 절차적 적법성 중심",
      "style": "분석적이고 논리적",
      "background": "행정법 교수 15년",
      "key_concerns": ["법적 근거 충돌", "조사 권한 중복"],
      "openness": 0.7
    },
    ...
  ],
  "diversity_score": 0.85,
  "generation_reason": "..."
}
```

### 2. DuplicationClassifier
**역할**: 공식 기준에 따른 중복 여부 판별

**프로세스**:
1. LLM으로 유사도 분석
   - target_similarity (대상)
   - content_similarity (내용)
   - purpose_similarity (목적)
   - method_similarity (방법)
   - period_overlap (시기)

2. 규칙 기반 분류
   ```python
   IF target >= 0.5 AND content >= 0.7:
       IF same_agency: C-1
       ELSE: C-2
   ELIF target >= 0.5 AND content < 0.4:
       IF same_agency: A-1
       ELSE: A-2
   ELSE:
       NONE
   ```

**출력**:
```python
{
  "is_duplicate": true,
  "duplication_type": "C-2",
  "type_description": "다기관 복합 중복",
  "severity": "CRITICAL",
  "confidence": 0.92,
  "similarity_scores": {...},
  "reasons": [...],
  "recommendations": [...]
}
```

### 3. ModeratorAgent
**역할**: 토론 진행 및 제어

**주요 메서드**:
- `start_discussion()`: 개회사 생성
- `guide_next_round()`: 라운드별 가이드
- `check_consensus()`: 합의 상태 확인
- `should_continue()`: 토론 계속 여부 결정
- `generate_closing_statement()`: 폐회사 생성

**라운드 제어**:
```python
min_rounds = 3  # 최소 보장
max_rounds = 10  # 절대 한계

# 조기 종료 조건 (round >= 3):
- 합의 도달 (consensus_level >= 0.8)
- 새로운 논점 없음
- 반복적 주장만 계속
```

### 4. InvestigationDiscussionService
**역할**: 전체 플로우 통합 관리

**메인 메서드**: `conduct_discussion()`

**프로세스**:
```python
1. 페르소나 생성 (3~5명)
2. 사전 분류 (A/C형 판별)
3. 토론 개회
4. 라운드별 진행:
   - 모더레이터 가이드 생성
   - 각 페르소나 발언 생성
   - 계속 여부 판단
5. 합의 확인
6. 최종 판정
7. 보고서 생성
8. 결과 반환
```

---

## 📊 데이터 흐름

```
Investigation A, B
       ↓
PersonaAutoGenerator.generate_personas()
       ↓
[GeneratedPersona × 3~5]
       ↓
DuplicationClassifier.classify()
       ↓
[DuplicationResult]
       ↓
ModeratorAgent.start_discussion()
       ↓
FOR round = 1 TO max_rounds:
    ModeratorAgent.guide_next_round()
    FOR EACH persona:
        generate_persona_statement()
    ModeratorAgent.should_continue()
    IF NOT continue: BREAK
       ↓
ModeratorAgent.check_consensus()
       ↓
_determine_final_verdict()
       ↓
_generate_report()
       ↓
[InvestigationDiscussionResult]
```

---

## 🔑 핵심 특징

### 1. 완전 자동화
- 페르소나부터 보고서까지 사람 개입 없이 자동 생성
- LLM 기반 지능형 분석

### 2. 공식 기준 준수
- 행정조사 중복 판별 공식 기준(A형, C형) 엄격 적용
- 유사도 임계값 명확 (대상 50%, 내용 70%)

### 3. 다각도 분석
- 법률, 행정, 기술, 정책 등 다양한 관점
- 페르소나 간 토론으로 종합적 판단

### 4. 적응적 제어
- 3~10라운드 사이에서 상황에 맞게 조정
- 조기 종료로 효율성 확보

### 5. 추적 가능성
- 모든 판단 과정 기록
- 페르소나별 주장 및 근거 명확히 제시

---

## 💡 사용 예시

```python
from api.services.investigation_discussion_service import InvestigationDiscussionService

service = InvestigationDiscussionService(
    min_rounds=3,
    max_rounds=10
)

result = await service.conduct_discussion(
    investigation_a={
        "name": "식품위생 정기조사",
        "purpose": "식품제조업소 위생상태 점검",
        "scope": "서울시 전체 식품제조업소",
        "target": "식품제조·가공업 영업허가 업소",
        "methods": "현장 방문 점검, 샘플 채취",
        "period": "연 2회",
        "legal_basis": "식품위생법 제22조",
        "department": "서울시 보건환경연구원"
    },
    investigation_b={
        "name": "HACCP 사후관리 조사",
        "purpose": "HACCP 인증업소 실태 점검",
        "scope": "서울시 HACCP 인증 업소",
        "target": "HACCP 인증 식품제조업소",
        "methods": "현장 실사, 기록 검토",
        "period": "연 1회 이상",
        "legal_basis": "식품위생법 제48조",
        "department": "식품의약품안전처"
    }
)

print(f"판정: {result.final_verdict}")
print(f"신뢰도: {result.consensus_status.consensus_level:.1%}")
print(f"라운드: {result.total_rounds}회")
print(result.report)  # Markdown 보고서
```

---

## ⚙️ 설정 옵션

```python
service = InvestigationDiscussionService(
    llm_provider=LLMProvider.OPENAI,  # or CLAUDE, GEMINI
    model="gpt-4",  # 모델 지정
    min_rounds=3,   # 최소 라운드
    max_rounds=10   # 최대 라운드
)
```

