# 업데이트 내역 (2025년 1월)

## 개요
토론 시스템의 프론트엔드 구현 및 모더레이터 기능 개선 업데이트

---

## 1. 프론트엔드 구현

### 1.1 토론 실시간 뷰어 페이지 생성
**파일**: `frontend/discussion.html`

#### 주요 기능
- **실시간 SSE 스트리밍**: 토론 진행 과정을 실시간으로 화면에 표시
- **페르소나별 색상 구분**: 각 AI 에이전트를 시각적으로 구분
- **모더레이터 메시지 표시**: 토론 진행자의 개입을 오렌지색 박스로 강조
- **설정 옵션**: 라운드 수, RAG, 모더레이터 활성화 여부 조절 가능

#### 색상 매핑
```javascript
'낙관주의자': 초록색 (green)
'비관주의자': 빨간색 (red)
'중립주의자': 파란색 (blue)
'실용주의자': 노란색 (yellow)
'이상주의자': 보라색 (purple)
'Moderator': 오렌지색 (orange)
```

#### API 연동
- **엔드포인트**: `POST /api/v1/discussions/guest/start`
- **SSE 이벤트 타입**:
  - `discussion_started`: 토론 시작
  - `message_chunk`: 실시간 메시지 청크
  - `message_complete`: 메시지 완성
  - `moderator_message`: 모더레이터 개입
  - `discussion_completed`: 토론 완료
  - `error`: 오류

#### 사용 방법
1. API 서버 실행: `python start_api.py`
2. 브라우저에서 `frontend/discussion.html` 열기
3. 주제 입력 및 설정 조정
4. "토론 시작" 버튼 클릭

---

## 2. 모더레이터 기능 개선

### 2.1 개입 조건 완화
**파일**: `src/core/natural_discussion.py`

#### 변경 전
- 최소 3턴 이후 개입
- 5턴마다 개입

#### 변경 후
- 최소 2턴 이후 개입
- **2턴마다 개입** (Turn 2, 4, 6, 8, ...)
- 추상적 발언 감지 시 즉시 개입
- 주제 전환 필요 시 개입
- 기타 경우 50% 확률로 개입

### 2.2 스트리밍 지원 추가

#### 문제점
- 기존: 모더레이터 메시지가 `self.messages`에만 추가되고 yield되지 않음
- 결과: 터미널에는 표시되지만 프론트엔드로 전송되지 않음

#### 해결책
**새 함수 추가**: `_moderator_intervention_streaming()`
```python
async def _moderator_intervention_streaming(self, topic: str) -> Optional[Message]:
    """모더레이터 개입 - 스트리밍 버전 (Message 객체 반환)"""
    # 조건 체크 및 메시지 생성
    # Message 객체로 반환하여 yield 가능
```

**스트리밍 루프 수정**:
```python
if self.moderator and should_intervene:
    moderator_msg = await self._moderator_intervention_streaming(topic)
    if moderator_msg:
        yield moderator_msg  # SSE로 전송
```

### 2.3 모더레이터 개입 타입
1. **transition**: 주제 전환
2. **probing**: 구체화 요청 (추상적 발언 대응)
3. **question**: 일반 심화 질문
4. **forced**: 조건 미충족 시 강제 질문

---

## 3. 백엔드 수정

### 3.1 모더레이터 메시지 SSE 전송
**파일**: `api/services/discussion_service.py`

#### 추가 코드
```python
# Moderator 메시지 처리
if message.agent_name == "Moderator" or message.role == "moderator":
    await event_broker.publish(
        discussion_id=discussion.id,
        event_type="moderator_message",
        data={
            "speaker": "Moderator",
            "content": message.content,
            "type": message.metadata.get("type", "question"),
            "timestamp": message.timestamp.isoformat() + "Z"
        }
    )
    continue
```

#### 이전 문제
- 모더레이터 메시지가 `discussion.participants`에 없어서 `continue`로 건너뛰어짐
- SSE 이벤트로 전송되지 않음

#### 해결
- 모더레이터 메시지를 별도로 감지하여 `moderator_message` 이벤트로 전송

---

## 4. 프론트엔드 UI/UX 개선

### 4.1 설정 패널 추가
```html
<div class="flex items-center gap-4">
    <label>라운드 수: <input type="number" min="3" max="20" value="5"></label>
    <label><input type="checkbox" id="enableRAG"> 웹 검색 (RAG)</label>
    <label><input type="checkbox" id="enableModerator" checked> 모더레이터</label>
</div>
```

### 4.2 모더레이터 메시지 UI
```javascript
function addModeratorMessage(data) {
    const messageDiv = document.createElement('div');
    messageDiv.className = 'bg-orange-100 border-l-4 border-orange-500 text-orange-900 ...';

    const typeLabel = {
        'transition': '주제 전환',
        'probing': '구체화 요청',
        'question': '심화 질문'
    }[data.type] || '개입';

    messageDiv.innerHTML = `
        <div>📢 MODERATOR</div>
        <span>${typeLabel}</span>
        <p>${data.content}</p>
    `;
}
```

### 4.3 실시간 메시지 업데이트
- `temp_id` 기반으로 메시지 식별
- `accumulated_text`로 누적된 텍스트 표시
- 청크 단위로 실시간 업데이트

---

## 5. 디버깅 로그 추가

### 5.1 모더레이터 개입 로그
```python
console.print(f"Turn {self.turn_count}: Moderator check = {should_intervene}")
console.print("🎙️  MODERATOR INTERVENING...")
console.print("Checking moderator intervention conditions...")
console.print(f"  1. Should transition subtopic? {should_transition}")
console.print(f"  2. Should probe for specifics? {should_probe}")
console.print(f"  3. Should ask question? {should_ask}")
```

### 5.2 개입 조건 체크 로그
```python
if self.turn_count < 2:
    console.print(f"Turn {self.turn_count} < 2, skipping")
if self.turn_count % 2 == 0:
    console.print(f"Turn {self.turn_count} is even, should intervene!")
```

---

## 6. API 스키마 확인 및 수정

### 6.1 페르소나 템플릿 ID
프론트엔드에서 사용하는 템플릿:
- `optimist` (낙관주의자)
- `pessimist` (비관주의자)
- `neutral` (중립주의자)

### 6.2 요청 Body 구조
```json
{
  "topic": "토론 주제",
  "description": "게스트 모드 토론",
  "participants": [
    {
      "template_id": "optimist",
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

---

## 7. 주요 버그 수정

### 7.1 SSE 이벤트 파싱 오류
**문제**: `data:` 라인만 파싱하고 `event:` 라인을 무시
**해결**:
```javascript
let currentEvent = null;
if (line.startsWith('event:')) {
    currentEvent = line.substring(6).trim();
} else if (line.startsWith('data:')) {
    const data = JSON.parse(line.substring(5).trim());
    handleStreamData(currentEvent, data);
}
```

### 7.2 필드 이름 불일치
**문제**: 프론트엔드 `agent_name` vs API `speaker`
**해결**: API 스키마 확인 후 `speaker` 사용

### 7.3 모더레이터 메시지 미전송
**문제**: 스트리밍 루프에서 yield 누락
**해결**: `_moderator_intervention_streaming()` 추가 및 yield

---

## 8. 테스트 결과

### 8.1 성공 케이스
✅ 프론트엔드에서 토론 실시간 표시
✅ 각 페르소나별 색상 구분
✅ 모더레이터 메시지 오렌지색 박스로 표시
✅ 2턴, 4턴마다 모더레이터 개입
✅ SSE 스트리밍 정상 작동
✅ 설정 옵션 (라운드 수, RAG, 모더레이터) 정상 작동

### 8.2 확인된 동작
- Turn 0-1: 에이전트 발언만
- Turn 2: 모더레이터 개입 (질문 생성)
- Turn 3: 에이전트 발언
- Turn 4: 모더레이터 개입 (질문 생성)
- ...

---

## 9. 향후 개선 사항

### 9.1 프론트엔드
- [ ] 토론 일시정지/재개 기능
- [ ] 메시지 검색 기능
- [ ] 토론 내보내기 (JSON/Markdown)
- [ ] 토론 기록 저장/로드

### 9.2 모더레이터
- [ ] 개입 조건 커스터마이징 UI
- [ ] 모더레이터 스타일 선택 (적극적/소극적)
- [ ] 토론 품질 실시간 평가

### 9.3 백엔드
- [ ] 토론 진행 상태 저장 (중단 후 재개 가능)
- [ ] 다중 토론 세션 지원
- [ ] WebSocket 지원 (양방향 통신)

---

## 10. 파일 변경 목록

### 신규 파일
- `frontend/discussion.html` - 토론 실시간 뷰어

### 수정 파일
- `src/core/natural_discussion.py` - 모더레이터 개입 조건 완화, 스트리밍 지원
- `api/services/discussion_service.py` - 모더레이터 메시지 SSE 전송
- `docs/UPDATES_2025_01.md` - 업데이트 문서 (이 파일)

### 변경 라인 수
- `natural_discussion.py`: +120 lines
- `discussion_service.py`: +15 lines
- `discussion.html`: +350 lines (신규)

---

## 11. 설치 및 실행

### 요구사항
- Python 3.8+
- FastAPI
- OpenAI API Key
- 최신 브라우저 (Chrome, Firefox, Edge)

### 실행 방법
```bash
# 1. API 서버 시작
python start_api.py

# 2. 브라우저에서 프론트엔드 열기
# frontend/discussion.html 파일을 브라우저에서 열기
# 또는
start frontend/discussion.html  # Windows
open frontend/discussion.html   # macOS
xdg-open frontend/discussion.html  # Linux

# 3. 토론 주제 입력 후 시작
```

---

## 12. 문의 및 피드백

문제가 발생하거나 개선 아이디어가 있으시면 이슈를 등록해주세요.

**문서 작성일**: 2025년 1월
**버전**: v1.1.0
**작성자**: Claude Code Assistant
