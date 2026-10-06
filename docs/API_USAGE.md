# 행정조사 중복 판별 API 사용 가이드

## 📝 개요

행정조사 중복 판별 서비스는 두 개의 행정조사 정보를 입력받아 AI 기반 분석을 통해 중복 여부를 판정하는 API입니다.

**주요 기능**:
- ✅ 페르소나 자동 생성 (3~7명의 전문가)
- ✅ 사전 중복 판별 (A형, C형 분류)
- ✅ 다각도 토론 진행 (3~10 라운드)
- ✅ 최종 판정 및 상세 보고서 생성
- ✅ 분석 이력 관리

---

## 🚀 빠른 시작

### 1. 분석 요청

**엔드포인트**: `POST /api/v1/investigations`

**요청 예시**:
```bash
curl -X POST "http://localhost:8000/api/v1/investigations" \
  -H "Content-Type: application/json" \
  -d '{
    "investigation_a": {
      "name": "식품위생 정기조사",
      "purpose": "식품제조업소 위생상태 점검",
      "scope": "서울시 전체 식품제조업소",
      "target": "식품제조·가공업 영업허가 업소",
      "methods": "현장 방문 점검, 샘플 채취, 기록 검토",
      "period": "연 2회 (상반기, 하반기)",
      "legal_basis": "식품위생법 제22조",
      "department": "서울시 보건환경연구원"
    },
    "investigation_b": {
      "name": "HACCP 사후관리 조사",
      "purpose": "HACCP 인증업소 실태 점검",
      "scope": "서울시 HACCP 인증 업소",
      "target": "HACCP 인증 식품제조업소",
      "methods": "현장 실사, 서류 검토, 기록 확인",
      "period": "연 1회 이상",
      "legal_basis": "식품위생법 제48조",
      "department": "식품의약품안전처"
    },
    "min_rounds": 3,
    "max_rounds": 10
  }'
```

**응답 (즉시)**:
```json
{
  "analysis_id": "550e8400-e29b-41d4-a716-446655440000",
  "created_at": "2025-11-05T10:30:00Z",
  "status": "processing",
  "investigation_a_name": "식품위생 정기조사",
  "investigation_b_name": "HACCP 사후관리 조사",
  "personas": [],
  "preliminary_analysis": {
    "is_duplicate": false,
    "severity": "LOW",
    "confidence": 0.0,
    "similarity_scores": {...},
    "reasons": ["분석 진행 중..."]
  },
  "total_rounds": 0,
  "rounds": [],
  "final_verdict": "분석 진행 중",
  "consensus_status": {
    "is_consensus_reached": false,
    "consensus_level": 0.0
  },
  "report_preview": "분석이 진행 중입니다. 잠시 후 다시 조회해 주세요.",
  "report_url": null
}
```

⏱️ **예상 소요 시간**: 2~5분 (토론 라운드 수에 따라 다름)

---

### 2. 분석 결과 조회

**엔드포인트**: `GET /api/v1/investigations/{analysis_id}`

**요청 예시**:
```bash
curl -X GET "http://localhost:8000/api/v1/investigations/550e8400-e29b-41d4-a716-446655440000"
```

**응답 (완료 시)**:
```json
{
  "analysis_id": "550e8400-e29b-41d4-a716-446655440000",
  "created_at": "2025-11-05T10:30:00Z",
  "status": "completed",
  "investigation_a_name": "식품위생 정기조사",
  "investigation_b_name": "HACCP 사후관리 조사",
  
  "personas": [
    {
      "name": "김법률",
      "role": "행정법 전문가",
      "expertise": "행정법, 행정절차법, 정보공개",
      "perspective": "법적 근거와 절차적 적법성 중심",
      "style": "분석적이고 논리적",
      "background": "행정법 교수 15년",
      "key_concerns": ["법적 근거 충돌", "조사 권한 중복"]
    },
    {
      "name": "이실무",
      "role": "행정조사 실무자",
      "expertise": "현장 조사, 실무 운영",
      "perspective": "실무적 효율성과 조사대상자 부담 고려",
      "style": "실용적이고 경험 기반",
      "background": "행정조사 실무 20년",
      "key_concerns": ["중복 조사로 인한 민원", "업무 효율성"]
    },
    {
      "name": "박데이터",
      "role": "데이터 분석가",
      "expertise": "통계 분석, 데이터 기반 의사결정",
      "perspective": "정량적 지표와 객관적 근거 중시",
      "style": "객관적이고 수치 중심",
      "background": "데이터 사이언티스트 10년",
      "key_concerns": ["유사도 측정", "객관적 지표"]
    }
  ],
  
  "preliminary_analysis": {
    "is_duplicate": true,
    "duplication_type": "C-2",
    "type_description": "다기관 복합 중복",
    "severity": "HIGH",
    "confidence": 0.87,
    "similarity_scores": {
      "target_similarity": 0.92,
      "content_similarity": 0.78,
      "purpose_similarity": 0.85,
      "method_similarity": 0.80,
      "period_overlap": 0.65
    },
    "reasons": [
      "조사 대상이 92% 일치 (식품제조업소)",
      "조사 내용이 78% 유사 (위생/안전 점검)",
      "조사 방법이 80% 겹침 (현장 방문, 기록 검토)",
      "담당 기관이 상이 (서울시 vs 식약처)",
      "시기적 중첩 가능성 높음"
    ],
    "recommendations": [
      "두 기관 간 조사 일정 조율 필요",
      "공통 점검항목 통합 운영 검토",
      "조사 결과 공유 체계 구축"
    ]
  },
  
  "total_rounds": 5,
  "rounds": [
    {
      "round_number": 1,
      "phase": "OPENING",
      "moderator_guide": "안녕하십니까. 본 토론의 주제는...",
      "persona_statements": {
        "김법률": "법적 관점에서 볼 때...",
        "이실무": "현장 경험상...",
        "박데이터": "데이터 분석 결과..."
      },
      "key_points": [
        "대상 동일성 확인",
        "법적 근거 검토",
        "실무적 부담 논의"
      ]
    },
    ...
  ],
  
  "final_verdict": "중복",
  "consensus_status": {
    "is_consensus_reached": true,
    "consensus_level": 0.88,
    "agreed_points": [
      "조사 대상이 거의 동일함",
      "내용이 상당히 유사함",
      "중복으로 인한 부담 발생",
      "조정이 필요함"
    ],
    "disagreed_points": [
      "심각도 평가 (HIGH vs CRITICAL)"
    ],
    "key_arguments": {
      "김법률": "법적 근거가 다르나 실질적 중복",
      "이실무": "조사대상자 부담이 과도함",
      "박데이터": "유사도 지표가 모두 기준 초과"
    }
  },
  
  "report_preview": "# 행정조사 중복 판별 보고서\n\n## 요약\n\n**판정**: 중복\n**신뢰도**: 88%\n**유형**: C-2 (다기관 복합 중복)\n\n두 조사는...",
  "report_url": "/api/v1/investigations/550e8400-e29b-41d4-a716-446655440000/report"
}
```

---

### 3. 전체 보고서 다운로드

**엔드포인트**: `GET /api/v1/investigations/{analysis_id}/report`

**요청 예시**:
```bash
# Markdown 형식 (기본)
curl -X GET "http://localhost:8000/api/v1/investigations/550e8400-e29b-41d4-a716-446655440000/report?format=markdown" \
  -o report.md

# 또는
curl -X GET "http://localhost:8000/api/v1/investigations/550e8400-e29b-41d4-a716-446655440000/report" \
  -o report.md
```

**응답**: Markdown 파일 다운로드

---

### 4. 분석 목록 조회

**엔드포인트**: `GET /api/v1/investigations`

**요청 예시**:
```bash
# 기본 (1페이지, 20개씩)
curl -X GET "http://localhost:8000/api/v1/investigations"

# 페이징
curl -X GET "http://localhost:8000/api/v1/investigations?page=1&page_size=10"

# 상태 필터
curl -X GET "http://localhost:8000/api/v1/investigations?status=completed"
```

**응답**:
```json
{
  "total": 42,
  "items": [
    {
      "analysis_id": "550e8400-e29b-41d4-a716-446655440000",
      "created_at": "2025-11-05T10:30:00Z",
      "investigation_a_name": "식품위생 정기조사",
      "investigation_b_name": "HACCP 사후관리 조사",
      "final_verdict": "중복",
      "confidence": 0.88,
      "total_rounds": 5
    },
    ...
  ],
  "page": 1,
  "page_size": 20
}
```

---

### 5. 분석 결과 삭제

**엔드포인트**: `DELETE /api/v1/investigations/{analysis_id}`

**요청 예시**:
```bash
curl -X DELETE "http://localhost:8000/api/v1/investigations/550e8400-e29b-41d4-a716-446655440000"
```

**응답**:
```json
{
  "message": "분석 결과가 삭제되었습니다.",
  "analysis_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

---

## 📊 입력 필드 상세 설명

### InvestigationInput

| 필드 | 타입 | 필수 | 설명 | 예시 |
|------|------|------|------|------|
| `name` | string | ✅ | 조사명 (1~200자) | "식품위생 정기조사" |
| `purpose` | string | ✅ | 조사 목적 | "식품제조업소 위생상태 점검" |
| `scope` | string | ✅ | 조사 범위 | "서울시 전체 식품제조업소" |
| `target` | string | ✅ | 조사 대상 | "식품제조·가공업 영업허가 업소" |
| `methods` | string | ✅ | 조사 방법 | "현장 방문 점검, 샘플 채취" |
| `period` | string | ✅ | 조사 주기/기간 | "연 2회 (상반기, 하반기)" |
| `legal_basis` | string | ✅ | 법적 근거 | "식품위생법 제22조" |
| `department` | string | ✅ | 담당 부서/기관 | "서울시 보건환경연구원" |
| `start_date` | string | ❌ | 조사 시작일 (YYYY-MM-DD) | "2025-03-01" |
| `end_date` | string | ❌ | 조사 종료일 (YYYY-MM-DD) | "2025-11-30" |
| `contact` | string | ❌ | 담당자 연락처 | "02-1234-5678" |
| `notes` | string | ❌ | 비고 | "2024년부터 강화된 기준 적용" |

---

## ⚙️ 분석 옵션

### InvestigationAnalysisRequest

| 필드 | 타입 | 기본값 | 범위 | 설명 |
|------|------|--------|------|------|
| `investigation_a` | InvestigationInput | - | - | 첫 번째 행정조사 |
| `investigation_b` | InvestigationInput | - | - | 두 번째 행정조사 |
| `min_rounds` | integer | 3 | 2~5 | 최소 토론 라운드 수 |
| `max_rounds` | integer | 10 | 3~15 | 최대 토론 라운드 수 |
| `persona_count` | integer | null | 3~7 | 페르소나 개수 (null이면 자동) |
| `skip_discussion` | boolean | false | - | 토론 생략 (사전 분석만) |

**권장 설정**:
- 간단한 분석: `min_rounds=2, max_rounds=5`
- 표준 분석: `min_rounds=3, max_rounds=10` (기본)
- 심층 분석: `min_rounds=5, max_rounds=15`

---

## 📋 응답 상태 코드

| 코드 | 상태 | 의미 |
|------|------|------|
| `202` | Accepted | 분석 요청 접수 (백그라운드 처리 중) |
| `200` | OK | 조회 성공 |
| `404` | Not Found | 분석 결과를 찾을 수 없음 |
| `400` | Bad Request | 잘못된 요청 (분석 미완료 상태에서 보고서 요청 등) |
| `403` | Forbidden | 권한 없음 (다른 사용자의 분석 결과) |
| `422` | Unprocessable Entity | 입력값 검증 실패 |
| `500` | Internal Server Error | 서버 오류 |

---

## 🔄 비동기 처리 패턴

분석은 시간이 오래 걸리므로 **비동기 처리**됩니다.

### 폴링 패턴

```javascript
async function analyzeInvestigations(data) {
  // 1. 분석 요청
  const response = await fetch('/api/v1/investigations', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data)
  });
  
  const { analysis_id } = await response.json();
  
  // 2. 상태 폴링
  while (true) {
    await new Promise(resolve => setTimeout(resolve, 5000)); // 5초 대기
    
    const statusResponse = await fetch(`/api/v1/investigations/${analysis_id}`);
    const result = await statusResponse.json();
    
    if (result.status === 'completed') {
      console.log('분석 완료!');
      return result;
    } else if (result.status === 'failed') {
      throw new Error('분석 실패');
    }
    
    console.log('분석 진행 중...');
  }
}
```

### Python 예시

```python
import time
import requests

def analyze_investigations(data):
    # 1. 분석 요청
    response = requests.post(
        'http://localhost:8000/api/v1/investigations',
        json=data
    )
    analysis_id = response.json()['analysis_id']
    
    # 2. 상태 폴링
    while True:
        time.sleep(5)  # 5초 대기
        
        status_response = requests.get(
            f'http://localhost:8000/api/v1/investigations/{analysis_id}'
        )
        result = status_response.json()
        
        if result['status'] == 'completed':
            print('분석 완료!')
            return result
        elif result['status'] == 'failed':
            raise Exception('분석 실패')
        
        print('분석 진행 중...')

# 사용
data = {
    "investigation_a": {...},
    "investigation_b": {...}
}

result = analyze_investigations(data)
print(f"최종 판정: {result['final_verdict']}")
print(f"신뢰도: {result['consensus_status']['consensus_level']:.1%}")
```

---

## 🎯 사용 예시 시나리오

### 시나리오 1: 유사 조사 중복 여부 확인

**상황**: 동일 기관에서 비슷한 내용의 조사를 반복적으로 수행하는지 확인

```json
{
  "investigation_a": {
    "name": "교통안전 실태조사 (상반기)",
    "purpose": "운수업체 교통안전 실태 파악",
    "scope": "서울시 전체 운수업체",
    "target": "버스, 택시, 화물 운송업",
    "methods": "현장 점검, 서류 검토, 안전교육 이수 확인",
    "period": "연 2회 (상반기)",
    "legal_basis": "교통안전법 제15조",
    "department": "서울시 교통안전과"
  },
  "investigation_b": {
    "name": "교통안전 실태조사 (하반기)",
    "purpose": "운수업체 교통안전 실태 파악",
    "scope": "서울시 전체 운수업체",
    "target": "버스, 택시, 화물 운송업",
    "methods": "현장 점검, 서류 검토, 안전교육 이수 확인",
    "period": "연 2회 (하반기)",
    "legal_basis": "교통안전법 제15조",
    "department": "서울시 교통안전과"
  }
}
```

**예상 결과**: C-1 (단일기관 중복) - 동일 기관이 동일 내용을 반복 조사

---

### 시나리오 2: 다기관 중복 조사 확인

**상황**: 중앙부처와 지자체가 동일 대상에 대해 유사한 조사를 각각 실시

```json
{
  "investigation_a": {
    "name": "산업안전보건 정기점검",
    "purpose": "제조업체 안전보건 관리 실태 점검",
    "scope": "전국 제조업체 (종업원 50인 이상)",
    "target": "제조업 사업장",
    "methods": "현장 실사, 안전시설 점검, 교육 이수 확인",
    "period": "연 1회",
    "legal_basis": "산업안전보건법 제15조",
    "department": "고용노동부 지방관서"
  },
  "investigation_b": {
    "name": "산업재해예방 실태조사",
    "purpose": "제조업체 재해예방 활동 현황 조사",
    "scope": "경기도 제조업체",
    "target": "제조업 사업장 (50인 이상)",
    "methods": "현장 방문, 안전관리 점검, 교육 실시 여부 확인",
    "period": "연 1회",
    "legal_basis": "경기도 산업안전 조례",
    "department": "경기도 산업안전과"
  }
}
```

**예상 결과**: C-2 (다기관 중복) - 고용노동부와 경기도가 유사한 조사 실시

---

### 시나리오 3: 대상만 같고 내용이 다른 경우

**상황**: 동일 대상에게 여러 목적의 조사를 실시 (다목적 조사)

```json
{
  "investigation_a": {
    "name": "유치원 위생관리 실태조사",
    "purpose": "유치원 급식 위생 상태 점검",
    "scope": "서울시 전체 유치원",
    "target": "서울시 관내 유치원",
    "methods": "급식실 점검, 식자재 확인",
    "period": "연 1회",
    "legal_basis": "학교급식법 제5조",
    "department": "서울시 보건소"
  },
  "investigation_b": {
    "name": "유치원 고용 실태조사",
    "purpose": "유치원 근로자 고용 현황 파악",
    "scope": "서울시 전체 유치원",
    "target": "서울시 관내 유치원",
    "methods": "근로계약서 확인, 임금대장 검토",
    "period": "연 1회",
    "legal_basis": "근로기준법 제51조",
    "department": "서울시 고용센터"
  }
}
```

**예상 결과**: A-2 (다기관 다목적 조사) - 대상은 같으나 내용이 다름

---

## 🔐 인증

게스트 사용자도 API를 사용할 수 있지만, 인증된 사용자는 추가 기능을 이용할 수 있습니다.

### Bearer 토큰 인증

```bash
# 1. 로그인
curl -X POST "http://localhost:8000/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"username": "user@example.com", "password": "password"}'

# 응답: {"access_token": "eyJ...", "token_type": "bearer"}

# 2. 인증된 요청
curl -X POST "http://localhost:8000/api/v1/investigations" \
  -H "Authorization: Bearer eyJ..." \
  -H "Content-Type: application/json" \
  -d '{...}'
```

**인증 사용자 vs 게스트**:
- ✅ 공통: 분석 요청, 결과 조회, 보고서 다운로드
- ⚠️ 게스트 제한: 자신이 요청한 분석만 조회 가능, 타인의 분석 결과 접근 불가
- 🔐 인증 사용자: 모든 자신의 분석 이력 관리 가능

---

## 💡 팁

### 1. 효율적인 폴링
- 초기 30초: 5초 간격
- 이후: 10초 간격
- 5분 이상: 포기 또는 에러 처리

### 2. 입력 데이터 품질
- 가능한 상세하게 작성
- 약어보다 정식 명칭 사용
- 법적 근거는 정확한 조문 명시

### 3. 결과 해석
- `confidence >= 0.8`: 신뢰도 높음
- `confidence 0.6~0.8`: 추가 검토 권장
- `confidence < 0.6`: 재분석 고려

### 4. 성능 최적화
- 간단한 비교는 `skip_discussion=true` 사용
- 복잡한 케이스는 `max_rounds` 증가

---

## 🐛 문제 해결

### Q1: 분석이 5분 이상 진행 중
- **원인**: LLM API 응답 지연 또는 복잡한 케이스
- **해결**: 잠시 더 기다리거나, 새로 요청 (간단한 옵션으로)

### Q2: 분석 상태가 "failed"
- **원인**: LLM API 오류, 입력 데이터 문제
- **해결**: 결과에서 `error` 필드 확인, 입력 데이터 재검토

### Q3: 403 Forbidden 에러
- **원인**: 다른 사용자의 분석 결과에 접근
- **해결**: 자신이 요청한 `analysis_id`인지 확인

### Q4: 보고서 다운로드 실패
- **원인**: 분석이 아직 완료되지 않음
- **해결**: `status`가 `completed`인지 먼저 확인

---

## 📚 관련 문서

- [서비스 플로우](./SERVICE_FLOW.md) - 전체 프로세스 상세 설명
- [중복 판별 기준](./DUPLICATION_CRITERIA.md) - 공식 판별 기준
- [시스템 설계](./ADMIN_INVESTIGATION_DESIGN.md) - 아키텍처 및 설계
- [API 문서](http://localhost:8000/docs) - Swagger UI

---

## 📞 지원

문제가 발생하거나 질문이 있으시면:
- 📧 이메일: support@example.com
- 💬 이슈 트래커: [GitHub Issues](https://github.com/...)

