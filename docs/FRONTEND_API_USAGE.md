# Frontend API 사용 목록

> 프론트엔드 페이지별로 사용하는 API 엔드포인트 정리

**마지막 업데이트**: 2025-11-18

---

## 목차

- [1. index.html (메인 UI)](#1-indexhtml-메인-ui)
- [2. investigation_analysis.html (간소화 UI)](#2-investigation_analysishtml-간소화-ui)
- [3. discussion.html (일반 토론 UI)](#3-discussionhtml-일반-토론-ui)
- [4. API 엔드포인트 요약](#4-api-엔드포인트-요약)

---

## 1. index.html (메인 UI)

**파일 위치**: `frontend/index.html`
**주요 기능**: 행정조사 중복 판별 분석 (SSE 스트리밍, 배치 분석, 분석 이력)

### 1.1 헬스 체크

```javascript
// API 연결 상태 확인
GET /health
```

**사용 위치**:
- Line 492: `checkAPIHealth()`
- 30초마다 자동 실행 (Line 1600)

**응답 예시**:
```json
{
  "status": "healthy"
}
```

---

### 1.2 행정조사 중복 판별 분석

#### 1.2.1 SSE 스트리밍 분석 (메인)

```javascript
// SSE 스트리밍으로 실시간 분석
POST /api/v1/investigations/stream
Content-Type: application/json

{
  "investigation_a": "조사A 내용",
  "investigation_b": "조사B 내용",
  "min_rounds": 2,
  "max_rounds": 5,
  "persona_count": 5,  // null이면 자동
  "enable_openness_adjustment": false  // RAG 웹 검색
}
```

**사용 위치**:
- Line 566: 분석 시작 버튼 클릭 시

**SSE 이벤트 타입** (Line 627-722):

| 이벤트 | 설명 | 데이터 필드 |
|--------|------|-----------|
| `analysis_started` | 분석 시작 | `analysis_id`, `investigation_a`, `investigation_b` |
| `phase_start` | 페이즈 시작 | `message` |
| `personas_generated` | 페르소나 생성 완료 | `count`, `personas[]` |
| `round_start` | 라운드 시작 | `round`, `max_rounds` |
| `turn_start` | 턴 시작 | `turn` |
| `moderator_message` | 모더레이터 메시지 | `type`, `content` |
| `persona_speaking` | 페르소나 발언 시작 | `name` |
| `persona_token` | 토큰 단위 스트리밍 | `token` |
| `persona_statement_complete` | 페르소나 발언 완료 | - |
| `round_complete` | 라운드 완료 | `round`, `issue`, `verdict`, `consensus_level` |
| `consensus_check` | 합의도 체크 | `level` |
| `discussion_complete` | 토론 완료 | `verdict`, `total_rounds`, `consensus_level` |
| `analysis_complete` | 분석 완료 | `analysis_id`, `verdict`, `total_rounds`, `consensus_level` |
| `error` | 에러 발생 | `message` |

**응답 형식** (SSE):
```
event: analysis_started
data: {"analysis_id": "abc123", "investigation_a": "...", "investigation_b": "..."}

event: persona_token
data: {"token": "안녕"}

event: analysis_complete
data: {"analysis_id": "abc123", "verdict": "중복", "total_rounds": 5, "consensus_level": 0.85}
```

---

#### 1.2.2 분석 이력 조회

```javascript
// 페이지네이션으로 분석 이력 조회
GET /api/v1/investigations?page={page}&page_size=10
```

**사용 위치**:
- Line 790: `loadHistory(page)`
- 분석 이력 탭 클릭 시 자동 로딩

**응답 예시**:
```json
{
  "items": [
    {
      "analysis_id": "abc123",
      "investigation_a_name": "조사A",
      "investigation_b_name": "조사B",
      "final_verdict": "중복",
      "confidence": 0.85,
      "total_rounds": 5,
      "created_at": "2025-11-18T10:00:00Z"
    }
  ],
  "total": 100,
  "page": 1,
  "page_size": 10
}
```

---

#### 1.2.3 분석 상세 조회

```javascript
// 특정 분석의 상세 정보 조회
GET /api/v1/investigations/{analysisId}
```

**사용 위치**:
- Line 851: `viewDetail(analysisId)`
- 분석 이력 항목 클릭 시

**응답 예시**:
```json
{
  "analysis_id": "abc123",
  "final_verdict": "중복",
  "final_verdict_details": "...",
  "personas": [
    {
      "name": "김지혜",
      "role": "세무전문가",
      "expertise": "법인세"
    }
  ],
  "rubric_scores": {
    "score_1_1": 25,
    "rationale_1_1": "...",
    "score_1_2": 15,
    "rationale_1_2": "...",
    "score_2_1": 22,
    "rationale_2_1": "...",
    "score_2_2": 18,
    "rationale_2_2": "...",
    "total": 80
  },
  "consensus_status": {
    "consensus_level": 0.85,
    "areas_of_agreement": ["항목1", "항목2"],
    "areas_of_disagreement": ["항목3"]
  },
  "rounds": [
    {
      "round_number": 1,
      "phase": "opening",
      "summary": "...",
      "messages": [
        {
          "speaker": "김지혜",
          "content": "..."
        }
      ]
    }
  ],
  "total_rounds": 5,
  "report_preview": "# 보고서..."
}
```

---

#### 1.2.4 보고서 다운로드

```javascript
// Markdown 보고서 다운로드
GET /api/v1/investigations/{analysisId}/report?format=markdown
```

**사용 위치**:
- Line 758: 새 분석 보고서 다운로드
- Line 1192: 상세보기 모달에서 다운로드

**응답**: Markdown 파일 (application/octet-stream)

---

### 1.3 배치 분석

#### 1.3.1 배치 생성 및 시작

```javascript
// 배치 분석 생성 및 자동 시작
POST /api/v1/batch-analyses
Content-Type: application/json

{
  "name": "배치 분석 2025-11-18",
  "description": "설명 (선택)",
  "items": [
    {
      "item_name": "비교 1",
      "investigation_a": "조사A 내용",
      "investigation_b": "조사B 내용"
    }
  ],
  "persona_count": 5,  // null이면 자동
  "min_rounds": 3,
  "max_rounds": 10,
  "enable_openness_adjustment": false
}
```

**사용 위치**:
- Line 1304: `createBatch()`

**응답 예시**:
```json
{
  "id": "batch-xyz",
  "name": "배치 분석 2025-11-18",
  "status": "processing",
  "total_count": 10,
  "completed_count": 0,
  "failed_count": 0,
  "progress_percentage": 0.0
}
```

---

#### 1.3.2 배치 목록 조회

```javascript
// 배치 목록 조회
GET /api/v1/batch-analyses?page=1&page_size=100
```

**사용 위치**:
- Line 1344: `loadBatchList()`

**응답 예시**:
```json
{
  "items": [
    {
      "id": "batch-xyz",
      "name": "배치 분석 2025-11-18",
      "description": "...",
      "status": "processing",
      "total_count": 10,
      "completed_count": 5,
      "failed_count": 1,
      "progress_percentage": 50.0,
      "created_at": "2025-11-18T10:00:00Z"
    }
  ],
  "total": 50,
  "page": 1,
  "page_size": 100
}
```

---

#### 1.3.3 배치 상세 조회

```javascript
// 배치 상세 정보 및 항목별 상태 조회
GET /api/v1/batch-analyses/{batchId}
```

**사용 위치**:
- Line 1442: `viewBatchDetail(batchId)`

**응답 예시**:
```json
{
  "id": "batch-xyz",
  "name": "배치 분석 2025-11-18",
  "description": "...",
  "status": "processing",
  "total_count": 10,
  "completed_count": 5,
  "failed_count": 1,
  "progress_percentage": 50.0,
  "items": [
    {
      "sequence": 1,
      "investigation_a_name": "조사A",
      "investigation_b_name": "조사B",
      "status": "completed",
      "analysis_id": "abc123",
      "final_verdict": "중복",
      "error_message": null
    },
    {
      "sequence": 2,
      "investigation_a_name": "조사C",
      "investigation_b_name": "조사D",
      "status": "failed",
      "analysis_id": null,
      "final_verdict": null,
      "error_message": "타임아웃"
    }
  ]
}
```

---

#### 1.3.4 배치 일시정지

```javascript
// 배치 분석 일시정지
POST /api/v1/batch-analyses/{batchId}/pause
```

**사용 위치**:
- Line 1544: `pauseBatch(batchId)`

**응답 예시**:
```json
{
  "id": "batch-xyz",
  "status": "paused"
}
```

---

#### 1.3.5 배치 재개

```javascript
// 배치 분석 재개
POST /api/v1/batch-analyses/{batchId}/resume
```

**사용 위치**:
- Line 1562: `resumeBatch(batchId)`

**응답 예시**:
```json
{
  "id": "batch-xyz",
  "status": "processing"
}
```

---

#### 1.3.6 배치 보고서 ZIP 다운로드

```javascript
// 완료된 분석들의 보고서를 ZIP으로 다운로드
GET /api/v1/batch-analyses/{batchId}/download-reports
```

**사용 위치**:
- Line 1578: `downloadBatchReports(batchId, batchName)`

**응답**: ZIP 파일 (application/zip)

---

## 2. investigation_analysis.html (간소화 UI)

**파일 위치**: `frontend/investigation_analysis.html`
**주요 기능**: 폴링 방식 분석 (SSE 미지원 환경용)

### 2.1 헬스 체크

```javascript
// API 연결 상태 확인
GET /health
```

**사용 위치**:
- Line 176: `checkHealth()`

---

### 2.2 분석 생성 (비SSE)

```javascript
// 백그라운드 분석 생성 (SSE 없음)
POST /api/v1/investigations
Content-Type: application/json

{
  "investigation_a": "조사A 내용",
  "investigation_b": "조사B 내용",
  "min_rounds": 3,
  "max_rounds": 8,
  "persona_count": null,  // 자동
  "enable_openness_adjustment": false
}
```

**사용 위치**:
- Line 210: `startAnalysis()`

**응답 예시**:
```json
{
  "analysis_id": "abc123",
  "status": "processing"
}
```

---

### 2.3 분석 상태 폴링

```javascript
// 분석 상태 주기적 조회 (1초마다)
GET /api/v1/investigations/{analysisId}
```

**사용 위치**:
- Line 254: `pollAnalysisStatus()`
- 분석 완료될 때까지 반복

**응답 예시**:
```json
{
  "analysis_id": "abc123",
  "status": "completed",  // or "processing", "failed"
  "final_verdict": "중복",
  // ... (나머지 필드는 1.2.3과 동일)
}
```

---

### 2.4 보고서 다운로드

```javascript
// Markdown 보고서 다운로드
GET /api/v1/investigations/{analysisId}/report?format=markdown
```

**사용 위치**:
- Line 390: `downloadReport()`

---

## 3. discussion.html (일반 토론 UI)

**파일 위치**: `frontend/discussion.html`
**주요 기능**: 일반 주제 토론 (게스트 모드)

### 3.1 게스트 토론 생성 + 스트리밍

```javascript
// 게스트 모드로 토론 생성 + SSE 스트리밍 (GPT 스타일)
POST /api/v1/discussions/guest/start
Content-Type: application/json

{
  "topic": "인공지능의 윤리적 문제",
  "description": "게스트 모드 토론",
  "participants": [
    {
      "template_id": "optimist",
      "llm_provider": "openai",
      "model": "gpt-4o-mini"
    },
    {
      "template_id": "pessimist",
      "llm_provider": "openai",
      "model": "gpt-4o-mini"
    },
    {
      "template_id": "neutral",
      "llm_provider": "openai",
      "model": "gpt-4o-mini"
    }
  ],
  "config": {
    "max_rounds": 5,
    "min_rounds": 3,
    "enable_rag": false,
    "enable_subtopics": true,
    "enable_reflection": false,
    "enable_moderation": true
  }
}
```

**사용 위치**:
- Line 120: 토론 시작 버튼 클릭 시

**SSE 이벤트 타입** (Line 216-268):

| 이벤트 | 설명 | 데이터 필드 |
|--------|------|-----------|
| `discussion_started` | 토론 시작 | `discussion_id` |
| `round_start` | 라운드 시작 | `round_number`, `current_subtopic` |
| `message` | 완성된 메시지 | `speaker`, `content`, `round` |
| `message_chunk` | 실시간 스트리밍 청크 | `temp_id`, `speaker`, `accumulated_text`, `round` |
| `moderator_message` | 모더레이터 메시지 | `type`, `content` |
| `discussion_completed` | 토론 완료 | `total_rounds`, `total_messages` |
| `error` | 에러 발생 | `message` |

**응답 형식** (SSE):
```
event: discussion_started
data: {"discussion_id": "disc-123"}

event: message_chunk
data: {"temp_id": "temp-1", "speaker": "낙관주의자", "accumulated_text": "저는...", "round": 1}

event: discussion_completed
data: {"total_rounds": 5, "total_messages": 15}
```

---

## 4. API 엔드포인트 요약

### 4.1 index.html 사용 API (11개)

| 메서드 | 엔드포인트 | 용도 | 사용 횟수 |
|--------|-----------|------|----------|
| GET | `/health` | 헬스 체크 | 매 30초 |
| POST | `/api/v1/investigations/stream` | SSE 분석 시작 | 1회 |
| GET | `/api/v1/investigations?page={page}&page_size=10` | 분석 이력 조회 | 탭 전환 시 |
| GET | `/api/v1/investigations/{id}` | 분석 상세 조회 | 클릭 시 |
| GET | `/api/v1/investigations/{id}/report` | 보고서 다운로드 | 클릭 시 |
| POST | `/api/v1/batch-analyses` | 배치 생성 | 1회 |
| GET | `/api/v1/batch-analyses?page=1&page_size=100` | 배치 목록 | 탭 전환 시 |
| GET | `/api/v1/batch-analyses/{id}` | 배치 상세 | 클릭 시 |
| POST | `/api/v1/batch-analyses/{id}/pause` | 배치 일시정지 | 클릭 시 |
| POST | `/api/v1/batch-analyses/{id}/resume` | 배치 재개 | 클릭 시 |
| GET | `/api/v1/batch-analyses/{id}/download-reports` | 배치 보고서 ZIP | 클릭 시 |

### 4.2 investigation_analysis.html 사용 API (3개)

| 메서드 | 엔드포인트 | 용도 | 사용 횟수 |
|--------|-----------|------|----------|
| GET | `/health` | 헬스 체크 | 매 30초 |
| POST | `/api/v1/investigations` | 분석 생성 (비SSE) | 1회 |
| GET | `/api/v1/investigations/{id}` | 분석 상태 폴링 | 1초마다 (완료까지) |
| GET | `/api/v1/investigations/{id}/report` | 보고서 다운로드 | 클릭 시 |

### 4.3 discussion.html 사용 API (1개)

| 메서드 | 엔드포인트 | 용도 | 사용 횟수 |
|--------|-----------|------|----------|
| POST | `/api/v1/discussions/guest/start` | 게스트 토론 생성 + SSE | 1회 |

---

## 5. 데이터 흐름도

### 5.1 행정조사 분석 흐름 (index.html)

```
사용자 입력
    ↓
POST /api/v1/investigations/stream (SSE 시작)
    ↓
SSE 이벤트 수신:
  - analysis_started
  - personas_generated
  - round_start
  - persona_token (실시간)
  - round_complete
  - analysis_complete
    ↓
분석 완료 → 결과 표시
    ↓
GET /api/v1/investigations/{id}/report (다운로드)
```

### 5.2 배치 분석 흐름 (index.html)

```
텍스트 파일 업로드 (클라이언트에서 파싱)
    ↓
POST /api/v1/batch-analyses (배치 생성)
    ↓
자동 시작 (백그라운드)
    ↓
GET /api/v1/batch-analyses/{id} (폴링으로 진행률 확인)
    ↓
완료 후 GET /api/v1/batch-analyses/{id}/download-reports (ZIP)
```

### 5.3 일반 토론 흐름 (discussion.html)

```
사용자 주제 입력
    ↓
POST /api/v1/discussions/guest/start (SSE 시작)
    ↓
SSE 이벤트 수신:
  - discussion_started
  - message_chunk (실시간 스트리밍)
  - moderator_message
  - discussion_completed
    ↓
토론 완료 → UI 리셋
```

---

## 6. SSE 이벤트 처리 상세

### 6.1 index.html SSE 처리 (행정조사)

**이벤트 루프** (Line 590-616):

```javascript
const reader = response.body.getReader();
const decoder = new TextDecoder();
let buffer = '';

while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop();

    for (const line of lines) {
        if (line.startsWith('event:')) {
            currentEvent = line.substring(6).trim();
        } else if (line.startsWith('data:')) {
            const data = JSON.parse(line.substring(5).trim());
            handleStreamEvent(currentEvent, data);
        }
    }
}
```

**토큰 스트리밍 처리** (Line 673-681):

```javascript
case 'persona_token':
    const logsContainer = document.getElementById('logsContainer');
    const lastLog = logsContainer.lastElementChild;
    if (lastLog && lastLog.classList.contains('log-token')) {
        lastLog.textContent += data.token;  // 토큰 추가
        logsContainer.scrollTop = logsContainer.scrollHeight;  // 자동 스크롤
    }
    break;
```

### 6.2 discussion.html SSE 처리 (일반 토론)

**이벤트 루프** (Line 170-196):

```javascript
const reader = response.body.getReader();
const decoder = new TextDecoder();
let buffer = '';

while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop();

    for (const line of lines) {
        if (line.startsWith('event:')) {
            currentEvent = line.substring(6).trim();
        } else if (line.startsWith('data:')) {
            const data = JSON.parse(line.substring(5).trim());
            handleStreamData(currentEvent, data);
        }
    }
}
```

**메시지 청크 처리** (Line 235-243):

```javascript
case 'message_chunk':
    addOrUpdateMessage({
        temp_id: data.temp_id,
        speaker: data.speaker,
        content: data.accumulated_text,  // 누적된 텍스트
        round: data.round || 1
    });
    break;
```

---

## 7. 에러 처리

### 7.1 HTTP 에러

**index.html** (Line 579-581):

```javascript
if (!response.ok) {
    throw new Error(`HTTP ${response.status}: ${response.statusText}`);
}
```

### 7.2 SSE 에러

**index.html** (Line 713-717):

```javascript
case 'error':
    addLog(`\n❌ 오류: ${data.message}`, 'log-error');
    document.getElementById('analyzeBtn').disabled = false;
    document.getElementById('analysisStatusCard').classList.add('hidden');
    break;
```

### 7.3 네트워크 에러

**index.html** (Line 618-623):

```javascript
} catch (error) {
    console.error('Error:', error);
    addLog(`\n❌ 오류 발생: ${error.message}`, 'log-error');
    document.getElementById('analyzeBtn').disabled = false;
    document.getElementById('analysisStatusCard').classList.add('hidden');
}
```

---

## 8. 특이사항 및 주의사항

### 8.1 API Base URL

모든 프론트엔드는 **상대 경로**를 사용합니다:

```javascript
const API_BASE_URL = window.location.origin;
// 예: http://localhost:8106
```

이유: FastAPI가 정적 파일과 API를 동일한 서버에서 서빙하므로 CORS 문제 없음.

### 8.2 SSE 타임아웃

**index.html**: 타임아웃 없음 (분석 완료까지 대기)
**investigation_analysis.html**: 폴링 최대 600초 (10분)

### 8.3 페르소나 수 자동 결정

`persona_count`를 `null`로 보내면 서버에서 조사 내용 분석 후 자동 결정 (3-7명).

### 8.4 배치 파일 파싱

배치 분석의 텍스트 파일은 **클라이언트에서 파싱**합니다:

```javascript
// "===" 로 쌍 구분, "---"로 A-B 구분
const pairs = text.split(/={3,}/).map(p => p.trim()).filter(p => p.length > 0);

for (let i = 0; i < pairs.length; i++) {
    const parts = pairs[i].split(/\-{3,}/).map(p => p.trim()).filter(p => p.length > 0);

    items.push({
        item_name: `비교 ${i + 1}`,
        investigation_a: parts[0],
        investigation_b: parts[1]
    });
}
```

---

## 9. 성능 최적화

### 9.1 폴링 간격

- **헬스 체크**: 30초 (Line 1600)
- **분석 상태 폴링**: 1초 (investigation_analysis.html Line 284)

### 9.2 페이지네이션

- **분석 이력**: 페이지당 10개 (Line 790)
- **배치 목록**: 페이지당 100개 (Line 1344)

### 9.3 자동 스크롤

SSE 이벤트 수신 시 자동으로 최신 로그로 스크롤:

```javascript
logsContainer.scrollTop = logsContainer.scrollHeight;
```

---

## 10. 관련 문서

- [FEATURES.md](./FEATURES.md) - 전체 기능 목록
- [ARCHITECTURE.md](./ARCHITECTURE.md) - 아키텍처 상세
- API 문서: http://localhost:8106/docs (Swagger UI)

---

**문서 작성일**: 2025-11-18
**버전**: 1.0.0
