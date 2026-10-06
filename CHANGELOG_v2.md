# 행정조사 중복 판별 시스템 v2.0 업데이트

**날짜**: 2025-11-05  
**브랜치**: `feature/admin-investigation-system`

---

## 📋 주요 업데이트

### 1. 일관성 지침 통합 🎯

**파일**: `docs/CONSISTENCY_GUIDELINE.md`

AI 판정 일관성을 위한 구조화된 가이드라인 도입:

- **판정 라벨 정의**
  - 중복 (duplicate): 대상·내용·자료요구·절차 대부분 동일
  - 부분중복 (partially duplicate): 일부라도 겹치는 영역 존재
  - 비중복 (non-duplicate): 겹치는 영역 전혀 없음

- **핵심 규칙**
  - ✅ **하위집합 관계 = 부분중복**
  - ✅ **하나라도 부분중복 → 최종 부분중복**
  - ❌ "완전히 동일하지 않다" → 비중복 (금지)
  - ❌ "법적 근거가 다르다" → 자동 비중복 (금지)
  - ❌ "하위집합이므로 비중복" (금지)
  - ❌ "일부만 겹치므로 비중복" (금지)

- **적용 위치**
  - `ModeratorAgent`: 시스템 프롬프트에 규칙 명시
  - `InvestigationDiscussionService`: 페르소나 발언 프롬프트에 규칙 추가
  - `_synthesize_final_verdict`: 최종 판정 알고리즘에 규칙 적용

---

### 2. RAG 웹 검색 기능 통합 🔍

**기존 시스템 활용**: `src/services/rag_service.py` (Tavily API)

#### 지능형 검색 필요성 판단

**파일**: `api/services/investigation_discussion_service.py`

쟁점 특성에 따라 자동으로 웹 검색 필요 여부 판단:

**검색이 필요한 키워드**:
- 법령, 법률, 조항, 조문, 근거
- 판례, 판결, 선례
- 규정, 지침, 기준
- 통계, 사례, 실태
- 해석, 적용, 범위

**검색이 불필요한 키워드** (입력 데이터로 충분):
- 대상 동일, 대상자, 동일성
- 중복 여부, 중첩

#### 효율성 개선

- **라운드당 1회만 검색**
  - 첫 번째 페르소나가 대표로 검색
  - 모든 페르소나가 검색 결과 공유
  
- **API 비용 절감**
  - 이전: 3 페르소나 × 5 턴 × 3 라운드 = 45회 RAG 호출
  - 개선: 필요한 라운드만 × 1회 = 1~2회 RAG 호출

#### 웹페이지 통합

**파일**: `frontend/investigation_analysis.html`

- 🔍 웹 검색 활성화 체크박스 추가
- `enable_openness_adjustment` 파라미터와 연동
- 법령, 판례, 규정 등 실시간 검색 안내

---

### 3. 루브릭 기반 정량적 중복도 평가 📊

**파일**: `api/services/investigation_discussion_service.py`

#### 평가 기준 (총 100점)

| 평가 항목 | 배점 | 설명 |
|----------|------|------|
| ①-1 모집단 중복도 | 30점 | 조사 대상 모집단이 얼마나 겹치는가? |
| ①-2 실제 대상 중복 가능성 | 20점 | 동일 대상이 두 조사를 모두 받을 가능성 |
| ②-1 내용 중복도 | 30점 | 조사 항목, 질문, 검사 범위 유사성 |
| ②-2 제출 자료 중복도 | 20점 | 요구하는 제출 서류의 중복도 |

#### 자동 해석

| 대상 중복성 | 내용 중복성 | 해석 |
|-----------|-----------|------|
| 35점↑ | 35점↑ | **명백한 중복조사** - 불필요한 부담 발생 |
| 35점↑ | 35점↓ | **대상은 같으나 내용 다름** - 공동조사 필요 |
| 35점↓ | 35점↑ | **대상 일부 겹침** - 사전 조율 필요 |
| 35점↓ | 35점↓ | **중복 아님** - 별도 진행 가능 |

#### 보고서 통합

최종 보고서에 **"2. 정량적 중복도 평가 (루브릭)"** 섹션 자동 생성:
- 표 형식 평가 결과
- 각 항목별 점수 및 근거
- 자동 해석 및 권고사항

---

### 4. 토론 내용 원문 DB 저장 💾

**파일**: `api/routers/investigations.py`

#### 저장 데이터 구조

```json
{
  "personas": [...],
  "rounds": [
    {
      "round_number": 1,
      "phase": "debate",
      "summary": "라운드 요약",
      "messages": [
        {
          "speaker": "페르소나명",
          "content": "발언 내용 (원문)",
          "type": "statement",
          "round_number": 1
        }
      ]
    }
  ],
  "consensus_status": {...},
  "report": "..."
}
```

#### 한글 저장 문제 수정

- **문제**: `\ub3c4\uc2dc\uac1c\ubc1c` 형태로 유니코드 이스케이프 저장
- **해결**: `ensure_ascii=False` 옵션 사용
- **결과**: 한글 원문 그대로 DB 저장

---

### 5. 버그 수정 🐛

#### 5.1 `_extract_json` 메서드 누락
- **파일**: `api/services/investigation_discussion_service.py`
- **문제**: 루브릭 평가 시 JSON 파싱 실패
- **해결**: robust JSON 파싱 메서드 추가

#### 5.2 ConsensusStatus 필드명 불일치
- **파일**: `api/schemas/investigation.py`
- **변경**:
  - `is_consensus_reached` → `has_consensus`
  - `agreed_points` → `areas_of_agreement`
  - `disagreed_points` → `areas_of_disagreement`

#### 5.3 RoundSummary 스키마 불일치
- **파일**: `api/schemas/investigation.py`
- **변경**:
  - `moderator_guide`, `persona_statements` → Optional (deprecated)
  - `summary`, `messages` 필드 추가
  - `round_number` 제약: `ge=1` → `ge=0` (개회/폐회 라운드 허용)
  - `extra = "allow"` 설정으로 유연한 스키마

#### 5.4 Import 누락
- **파일**: `api/schemas/investigation.py`
- **해결**: `from typing import Any` 추가

---

## 📁 파일 변경 사항

### 신규 파일
- `docs/CONSISTENCY_GUIDELINE.md` - AI 판정 일관성 지침서
- `test_full_flow.py` - 전체 플로우 테스트 스크립트

### 수정된 파일
- `api/services/investigation_discussion_service.py` - 핵심 서비스 로직
- `api/services/moderator_agent.py` - 모더레이터 프롬프트 강화
- `api/routers/investigations.py` - DB 저장 로직 개선
- `api/schemas/investigation.py` - 스키마 수정
- `frontend/investigation_analysis.html` - 웹 검색 옵션 추가

### 삭제된 파일
- `api/services/duplication_classifier.py` - 불필요한 사전 판별 제거
- `tests/test_duplication_classifier.py` - 관련 테스트 제거

---

## 🧪 테스트

### 테스트 방법

```bash
# 전체 플로우 테스트
python test_full_flow.py

# 또는 API 직접 호출
curl -X POST "http://localhost:8000/api/v1/investigations" \
  -H "Content-Type: application/json" \
  -d @test_investigation_request.json
```

### 테스트 확인 사항
- ✅ 페르소나 생성 (3명)
- ✅ 토론 진행 (2 라운드)
- ✅ 웹 검색 필요성 자동 판단
- ✅ 루브릭 평가 수행 (0-100점)
- ✅ 보고서 생성 (한글 포함)
- ✅ DB 저장 (토론 원문 포함)
- ✅ 결과 조회 (422 에러 없음)

---

## 📊 성능 개선

### API 호출 최적화
- RAG 호출: **45회 → 1~2회** (약 95% 감소)
- 응답 시간: 더 빠른 토론 진행
- 비용 절감: Tavily API 호출 최소화

### 데이터 완정성
- 토론 원문 100% 보존
- 한글 인코딩 문제 해결
- 정량적 평가 지표 추가

---

## 🚀 배포 전 체크리스트

- [x] 서버 재시작 (uvicorn auto-reload)
- [x] DB 스키마 호환성 확인
- [x] 한글 인코딩 테스트
- [x] 루브릭 평가 정상 작동
- [x] 웹 검색 기능 테스트
- [x] 전체 플로우 End-to-End 테스트
- [x] Git 커밋 및 푸시

---

## 📝 향후 개선 사항

1. **페르소나 믿음 변화(openness) 기능 실제 로직 구현**
   - 현재는 플래그만 존재, 실제 동작 로직 미구현

2. **HTML/PDF 보고서 형식 지원**
   - 현재는 Markdown만 지원

3. **실시간 스트리밍 UI 개선**
   - 토큰 단위 출력 웹페이지 반영

4. **루브릭 평가 커스터마이징**
   - 사용자 정의 평가 기준 추가

---

## 👥 기여자
- AI Assistant (Claude Sonnet 4.5)
- User

**커밋 수**: 10개  
**변경된 파일**: 8개  
**추가된 줄**: ~700 lines  
**삭제된 줄**: ~150 lines

