# Discussion API 리팩토링 지시서

## 📋 개요
**목적**: Discussion API의 결합도 감소 및 응집도 향상  
**대상 모듈**: `api/routers/discussions.py`, `api/services/discussion_service.py`, `api/services/message_service.py`  
**예상 효과**: 코드 품질 7.2/10 → 8.3/10

---

## 🎯 작업 목표

### 1. 응답 변환 로직 통합 (우선순위: 높음)
- **문제**: Router에서 동일한 변환 로직이 3-4곳에 중복
- **해결**: Mapper 클래스 도입

### 2. 시간 계산 로직 Service 이동 (우선순위: 높음)
- **문제**: 비즈니스 로직이 Router에 누출
- **해결**: DiscussionService로 이동

### 3. 권한 확인 로직 통합 (우선순위: 중간)
- **문제**: DiscussionService, MessageService에 중복 코드
- **해결**: 공통 권한 확인 함수 또는 Decorator

---

## 📝 작업 1: Mapper 클래스 생성

### 1-1. 파일 생성
```
경로: api/mappers/discussion_mapper.py
```

### 1-2. 구현 내용
```python
"""
Discussion 관련 응답 변환 Mapper
"""
from typing import List
from api.models.discussion import Discussion, Participant
from api.schemas.discussion import (
    ParticipantResponse,
    TimestampsResponse
)
from api.services.discussion_service import DiscussionService


class DiscussionMapper:
    """토론 관련 데이터 변환 클래스"""
    
    @staticmethod
    def to_participant_response(participant: Participant) -> ParticipantResponse:
        """
        Participant 모델 → ParticipantResponse 스키마 변환
        
        Args:
            participant: Participant 모델 인스턴스
            
        Returns:
            ParticipantResponse 스키마 인스턴스
        """
        return ParticipantResponse(
            id=participant.id,
            name=participant.name,
            role=participant.role,
            llm_provider=participant.llm_provider,
            model=participant.model,
            message_count=participant.message_count,
            current_openness=participant.current_openness
        )
    
    @staticmethod
    def to_participants_response(participants: List[Participant]) -> List[ParticipantResponse]:
        """
        Participant 리스트 → ParticipantResponse 리스트 변환
        
        Args:
            participants: Participant 모델 리스트
            
        Returns:
            ParticipantResponse 스키마 리스트
        """
        return [
            DiscussionMapper.to_participant_response(p)
            for p in participants
        ]
    
    @staticmethod
    def to_timestamps_response(discussion: Discussion) -> TimestampsResponse:
        """
        Discussion 모델 → TimestampsResponse 스키마 변환
        
        Args:
            discussion: Discussion 모델 인스턴스
            
        Returns:
            TimestampsResponse 스키마 인스턴스
        """
        return TimestampsResponse(
            created_at=discussion.created_at,
            started_at=discussion.started_at,
            updated_at=discussion.updated_at,
            completed_at=discussion.completed_at,
            elapsed_seconds=DiscussionService.calculate_elapsed_seconds(discussion),
            estimated_remaining_seconds=DiscussionService.estimate_remaining_seconds(discussion),
            duration_seconds=DiscussionService.calculate_duration_seconds(discussion)
        )
```

### 1-3. __init__.py 생성
```
경로: api/mappers/__init__.py
```

```python
"""
응답 변환 Mapper 모듈
"""
from api.mappers.discussion_mapper import DiscussionMapper

__all__ = ["DiscussionMapper"]
```

---

## 📝 작업 2: DiscussionService 시간 계산 메서드 추가

### 2-1. 대상 파일
```
경로: api/services/discussion_service.py
```

### 2-2. 추가할 메서드
```python
class DiscussionService:
    # ... 기존 메서드들 ...
    
    @staticmethod
    def get_estimated_completion(discussion: Discussion) -> Optional[datetime]:
        """
        토론 예상 완료 시간 계산
        
        Args:
            discussion: Discussion 모델 인스턴스
            
        Returns:
            예상 완료 시간 (datetime) 또는 None
        """
        if not discussion.started_at:
            return None
        
        estimated_duration_seconds = discussion.total_rounds * 90  # 라운드당 90초
        return discussion.started_at + timedelta(seconds=estimated_duration_seconds)
    
    @staticmethod
    def get_estimated_duration_minutes(discussion: Discussion) -> int:
        """
        토론 예상 소요 시간 계산 (분 단위)
        
        Args:
            discussion: Discussion 모델 인스턴스
            
        Returns:
            예상 소요 시간 (분)
        """
        return int(discussion.total_rounds * 1.5)  # 라운드당 1.5분
```

### 2-3. Import 추가
```python
from typing import Optional
from datetime import datetime, timedelta
```

---

## 📝 작업 3: discussions.py Router 리팩토링

### 3-1. 대상 파일
```
경로: api/routers/discussions.py
```

### 3-2. Import 추가
```python
from api.mappers.discussion_mapper import DiscussionMapper
```

### 3-3. 수정할 엔드포인트

#### 3-3-1. create_discussion() 수정

**기존 코드 (삭제):**
```python
# 참가자 정보
participants = [
    ParticipantResponse(
        id=p.id,
        name=p.name,
        role=p.role,
        llm_provider=p.llm_provider,
        model=p.model,
        message_count=p.message_count,
        current_openness=p.current_openness
    )
    for p in discussion.participants
]

# 예상 소요 시간 계산 (라운드당 약 1.5분)
estimated_duration = discussion.total_rounds * 1.5
```

**새로운 코드:**
```python
# 참가자 정보
participants = DiscussionMapper.to_participants_response(discussion.participants)

# 예상 소요 시간 계산
estimated_duration = DiscussionService.get_estimated_duration_minutes(discussion)
```

---

#### 3-3-2. start_discussion() 수정

**기존 코드 (삭제):**
```python
# 예상 완료 시간 계산
estimated_duration = discussion.total_rounds * 90  # 라운드당 90초
estimated_completion = discussion.started_at + timedelta(seconds=estimated_duration)
```

**새로운 코드:**
```python
# 예상 완료 시간 계산
estimated_completion = DiscussionService.get_estimated_completion(discussion)
```

**Import 삭제:**
```python
from datetime import timedelta  # 이 줄 삭제 (더 이상 Router에서 사용 안 함)
```

---

#### 3-3-3. get_discussion_status() 수정

**기존 코드 (삭제):**
```python
# 참가자 정보
participants = [
    ParticipantResponse(
        id=p.id,
        name=p.name,
        role=p.role,
        llm_provider=p.llm_provider,
        model=p.model,
        message_count=p.message_count,
        current_openness=p.current_openness
    )
    for p in discussion.participants
]

# 타임스탬프
timestamps = TimestampsResponse(
    created_at=discussion.created_at,
    started_at=discussion.started_at,
    updated_at=discussion.updated_at,
    completed_at=discussion.completed_at,
    elapsed_seconds=DiscussionService.calculate_elapsed_seconds(discussion),
    estimated_remaining_seconds=DiscussionService.estimate_remaining_seconds(discussion),
    duration_seconds=DiscussionService.calculate_duration_seconds(discussion)
)
```

**새로운 코드:**
```python
# 참가자 정보
participants = DiscussionMapper.to_participants_response(discussion.participants)

# 타임스탬프
timestamps = DiscussionMapper.to_timestamps_response(discussion)
```

---

#### 3-3-4. list_discussions() 수정

**기존 코드 (삭제):**
```python
for discussion in discussions:
    timestamps = TimestampsResponse(
        created_at=discussion.created_at,
        started_at=discussion.started_at,
        updated_at=discussion.updated_at,
        completed_at=discussion.completed_at,
        elapsed_seconds=DiscussionService.calculate_elapsed_seconds(discussion),
        duration_seconds=DiscussionService.calculate_duration_seconds(discussion)
    )
```

**새로운 코드:**
```python
for discussion in discussions:
    timestamps = DiscussionMapper.to_timestamps_response(discussion)
```

---

#### 3-3-5. 게스트 엔드포인트들도 동일하게 수정

- `create_guest_discussion()`
- `start_guest_discussion()`
- `get_guest_discussion_status()`

위와 동일한 패턴으로 Mapper와 Service 메서드 사용

---

## 📝 작업 4: 권한 확인 로직 통합 (선택 사항)

### 4-1. 파일 생성
```
경로: api/utils/permissions.py
```

### 4-2. 구현 내용
```python
"""
권한 확인 유틸리티
"""
from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from api.models.discussion import Discussion


class PermissionChecker:
    """권한 확인 헬퍼 클래스"""
    
    @staticmethod
    def check_discussion_access(
        db: Session,
        discussion_id: str,
        user_id: str
    ) -> Discussion:
        """
        토론 접근 권한 확인
        
        Args:
            db: 데이터베이스 세션
            discussion_id: 토론 ID
            user_id: 사용자 ID
            
        Returns:
            Discussion 인스턴스
            
        Raises:
            HTTPException: 토론이 없거나 권한이 없는 경우
        """
        discussion = db.query(Discussion).filter(
            Discussion.id == discussion_id
        ).first()
        
        if not discussion:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "error": {
                        "code": "DISCUSSION_NOT_FOUND",
                        "message": "토론을 찾을 수 없습니다."
                    }
                }
            )
        
        # 게스트 모드인 경우 권한 확인 스킵
        if user_id != "guest" and discussion.created_by != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error": {
                        "code": "FORBIDDEN",
                        "message": "이 토론에 접근할 권한이 없습니다."
                    }
                }
            )
        
        return discussion
```

### 4-3. DiscussionService 수정

**get_discussion() 메서드 수정:**
```python
@staticmethod
def get_discussion(db: Session, discussion_id: str, user_id: str) -> Discussion:
    """
    토론 조회 (권한 확인 포함)
    """
    from api.utils.permissions import PermissionChecker
    return PermissionChecker.check_discussion_access(db, discussion_id, user_id)
```

### 4-4. MessageService 수정

**list_messages(), get_message_detail() 메서드에서 권한 확인 부분:**
```python
# 기존 코드 (삭제)
discussion = db.query(Discussion).filter(Discussion.id == discussion_id).first()
if not discussion:
    raise HTTPException(...)
if discussion.created_by != user_id:
    raise HTTPException(...)

# 새로운 코드
from api.utils.permissions import PermissionChecker
discussion = PermissionChecker.check_discussion_access(db, discussion_id, user_id)
```

---

## 📝 작업 5: 테스트 및 검증

### 5-1. 단위 테스트 실행
```bash
# Mapper 테스트
pytest tests/test_discussion_mapper.py -v

# Service 테스트
pytest tests/test_discussion_service.py -v

# Router 테스트
pytest tests/test_discussions_router.py -v
```

### 5-2. 수동 테스트 시나리오

#### 시나리오 1: 토론 생성
```bash
curl -X POST "http://localhost:8000/api/v1/discussions" \
  -H "Authorization: Bearer {token}" \
  -H "Content-Type: application/json" \
  -d '{
    "topic": "AI 윤리",
    "participants": [...]
  }'
```

**확인 사항:**
- ✅ participants 필드가 정상적으로 반환되는지
- ✅ estimated_duration_minutes가 정확한지

#### 시나리오 2: 토론 시작
```bash
curl -X POST "http://localhost:8000/api/v1/discussions/{id}/start" \
  -H "Authorization: Bearer {token}"
```

**확인 사항:**
- ✅ estimated_completion이 정상적으로 계산되는지
- ✅ 시간대가 올바른지

#### 시나리오 3: 토론 상태 조회
```bash
curl -X GET "http://localhost:8000/api/v1/discussions/{id}" \
  -H "Authorization: Bearer {token}"
```

**확인 사항:**
- ✅ timestamps 객체가 모든 필드를 포함하는지
- ✅ 계산된 시간이 정확한지

---

## 📊 작업 완료 체크리스트

### Phase 1: 파일 생성
- [ ] `api/mappers/discussion_mapper.py` 생성
- [ ] `api/mappers/__init__.py` 생성
- [ ] `api/utils/permissions.py` 생성 (선택)

### Phase 2: Service 수정
- [ ] `discussion_service.py`에 `get_estimated_completion()` 추가
- [ ] `discussion_service.py`에 `get_estimated_duration_minutes()` 추가
- [ ] Import 문 추가 확인

### Phase 3: Router 리팩토링
- [ ] `discussions.py`에 Mapper import 추가
- [ ] `create_discussion()` 수정
- [ ] `start_discussion()` 수정
- [ ] `get_discussion_status()` 수정
- [ ] `list_discussions()` 수정
- [ ] 게스트 엔드포인트 수정
- [ ] 불필요한 import 제거 (timedelta)

### Phase 4: 권한 확인 통합 (선택)
- [ ] `PermissionChecker` 구현
- [ ] `DiscussionService.get_discussion()` 수정
- [ ] `MessageService` 메서드들 수정

### Phase 5: 테스트
- [ ] 단위 테스트 작성
- [ ] 통합 테스트 실행
- [ ] 수동 테스트 시나리오 검증

---

## 🎯 예상 결과

### 코드 품질 개선
- **결합도**: 6.3/10 → 8.0/10 (+1.7)
- **응집도**: 8.0/10 → 8.5/10 (+0.5)
- **종합**: 7.2/10 → 8.3/10 (+1.1)

### 구체적 개선 사항
1. ✅ Router의 중복 코드 제거 (약 100줄 감소)
2. ✅ 비즈니스 로직이 Service로 이동
3. ✅ 단일 책임 원칙 준수
4. ✅ 유지보수성 향상
5. ✅ 테스트 용이성 증가

---

## ⚠️ 주의사항

### 1. 하위 호환성
- 기존 API 응답 구조는 변경하지 말것
- 외부 클라이언트에 영향 없어야 함

### 2. 성능
- Mapper 사용으로 인한 성능 저하 없어야 함
- 필요시 프로파일링 수행

### 3. 에러 처리
- 모든 예외 상황 처리 확인
- 에러 메시지 일관성 유지

### 4. 문서화
- 새로운 클래스/메서드 모두 docstring 작성
- README 업데이트 (필요시)

---

## 📚 참고 자료

### 설계 패턴
- **Mapper Pattern**: DTO ↔ Entity 변환
- **Service Layer Pattern**: 비즈니스 로직 분리
- **Repository Pattern**: 데이터 접근 추상화

### SOLID 원칙
- **SRP**: 각 클래스가 하나의 책임만
- **OCP**: 확장에 열려있고 수정에 닫혀있음
- **DIP**: 추상화에 의존

---

## 🔄 롤백 계획

만약 문제 발생 시:

```bash
# Git 백업 브랜치 생성
git checkout -b backup/before-discussion-refactoring

# 리팩토링 브랜치
git checkout -b refactor/discussion-api

# 작업 수행
# ...

# 문제 발생 시 롤백
git checkout main
git branch -D refactor/discussion-api
```

---

**작성일**: 2025-10-23  
**작성자**: AI Assistant  
**버전**: 1.0