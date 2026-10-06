# 성능 최적화 가이드

## 목차
1. [문제 상황](#문제-상황)
2. [성능 분석](#성능-분석)
3. [최적화 전략](#최적화-전략)
4. [구현 상세](#구현-상세)
5. [성능 개선 결과](#성능-개선-결과)
6. [학습 포인트](#학습-포인트)

---

## 문제 상황

### 초기 성능 문제
- **페이지 목록 조회 API**: 9.44초 소요
- **프론트엔드 폴링**: 5초마다 상태 확인 → 느린 응답성

### 사용자 경험 영향
- 페이지 로드가 매우 느림
- 실시간 상태 업데이트가 지연됨
- 전체적으로 답답한 사용자 경험

---

## 성능 분석

### 병목 지점 식별

#### 1. 네트워크 분석 (Chrome DevTools)
```
Queued: 725ms
Connection Start: 0.95ms
Request sent: 0.16ms
Waiting for server response: 9.44s  ← 🔴 주범!
Content Download: 0.18ms
```

**결론**: 서버 응답 시간이 문제의 핵심

#### 2. 기존 코드 분석

**문제점 1: 모든 컬럼 로드**
```python
# api/routers/investigations.py (기존)
query = db.query(InvestigationAnalysis)  # 모든 컬럼 SELECT
analyses = query.order_by(desc(created_at)).offset(offset).limit(page_size).all()
```

**문제점 2: 큰 JSON 컬럼 포함**
```python
# 테이블 구조
investigation_a_data = Column(JSON)  # 수 KB 크기
investigation_b_data = Column(JSON)  # 수 KB 크기
result_data = Column(JSON)           # 수십 KB 크기 (토론 전체 내용)
```

**문제점 3: 연결 풀 미설정**
```python
# api/database.py (기존)
engine = create_engine(settings.DATABASE_URL)  # 기본 설정만 사용
```

**문제점 4: 인덱스 부족**
- `result_data` JSON을 파싱해서 `total_rounds` 추출
- 매번 JSON 파싱 오버헤드 발생

---

## 최적화 전략

### 원칙
1. **필요한 데이터만 가져오기** (SELECT 최적화)
2. **연결 재사용** (Connection Pooling)
3. **인덱스 활용** (DB 쿼리 속도)
4. **프론트엔드 응답성** (폴링 간격 단축)

---

## 구현 상세

### 1. SELECT 쿼리 최적화 ⭐ 가장 중요!

#### Before (느림)
```python
# 모든 컬럼을 로드 (investigation_a_data, investigation_b_data, result_data 포함)
query = db.query(InvestigationAnalysis)
analyses = query.all()  # 각 행마다 수십 KB 전송

for analysis in analyses:
    # ORM 객체 → 모든 컬럼이 메모리에 로드됨
    items.append(InvestigationAnalysisListItem(
        analysis_id=analysis.id,
        created_at=analysis.created_at,
        # ...
    ))
```

**문제점:**
- 20개 행 × 평균 50KB = **1MB 데이터 전송**
- PostgreSQL 서버(외부 IP)에서 네트워크로 전송
- 목록 화면에 불필요한 JSON 데이터까지 로드

#### After (빠름)
```python
# 필요한 7개 컬럼만 명시적으로 SELECT
query = db.query(
    InvestigationAnalysis.id,                      # 36 bytes
    InvestigationAnalysis.created_at,              # 8 bytes
    InvestigationAnalysis.investigation_a_name,    # ~50 bytes
    InvestigationAnalysis.investigation_b_name,    # ~50 bytes
    InvestigationAnalysis.final_verdict,           # ~20 bytes
    InvestigationAnalysis.confidence,              # 8 bytes
    InvestigationAnalysis.total_rounds,            # 4 bytes
    InvestigationAnalysis.status                   # ~10 bytes
)
# investigation_a_data, investigation_b_data, result_data 제외!

results = query.all()  # 튜플 배열 반환

for row in results:
    # 튜플 언팩 (row[0], row[1], ...)
    items.append(InvestigationAnalysisListItem(
        analysis_id=row[0],
        created_at=row[1],
        investigation_a_name=row[2],
        investigation_b_name=row[3],
        final_verdict=row[4] or "분석 진행 중",
        confidence=row[5] if row[5] else 0.0,
        total_rounds=row[6] if row[6] else 0
    ))
```

**개선 효과:**
- 20개 행 × 평균 200 bytes = **4KB 데이터 전송** (250배 감소!)
- 네트워크 전송 시간 대폭 단축
- 메모리 사용량 감소

**생성되는 SQL:**
```sql
-- Before
SELECT * FROM investigation_analyses
ORDER BY created_at DESC
LIMIT 20 OFFSET 0;

-- After
SELECT
    id,
    created_at,
    investigation_a_name,
    investigation_b_name,
    final_verdict,
    confidence,
    total_rounds,
    status
FROM investigation_analyses
ORDER BY created_at DESC
LIMIT 20 OFFSET 0;
```

---

### 2. 데이터베이스 연결 풀 설정

#### Before
```python
# api/database.py (기존)
engine = create_engine(settings.DATABASE_URL)
```

**문제점:**
- 매 요청마다 새 연결 생성 가능성
- 외부 PostgreSQL 서버(your-db-host) 연결 오버헤드
- TCP 3-way handshake + SSL 협상 반복

#### After
```python
# api/database.py (개선)
engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,      # 연결 사용 전 유효성 확인 (끊긴 연결 방지)
    pool_size=10,            # 기본 연결 풀 10개 유지
    max_overflow=20,         # 필요시 최대 20개 추가 연결 (총 30개)
    pool_recycle=3600,       # 1시간마다 연결 재활용 (장시간 방치 방지)
    echo=False               # SQL 로깅 비활성화 (성능 향상)
)
```

**작동 원리:**
```
[요청 1] → 연결 풀에서 연결 가져오기 → 쿼리 실행 → 연결 반환
[요청 2] → 재사용된 연결 가져오기 → 쿼리 실행 → 연결 반환
[요청 3] → 재사용된 연결 가져오기 → 쿼리 실행 → 연결 반환
```

**개선 효과:**
- 연결 생성 오버헤드 제거
- 외부 DB 서버 연결 시 특히 효과적
- 동시 요청 처리 능력 향상

---

### 3. 데이터베이스 인덱스 추가

#### 문제: JSON 파싱 오버헤드

**Before**
```python
# total_rounds를 JSON에서 추출
for analysis in analyses:
    result_data = analysis.result_data  # JSON 컬럼
    total_rounds = result_data.get('total_rounds', 0) if result_data else 0
```

**마이그레이션 1: total_rounds 컬럼 추가**
```sql
-- migrations/add_total_rounds_and_indexes.sql

-- 1. 전용 컬럼 추가
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'investigation_analyses'
        AND column_name = 'total_rounds'
    ) THEN
        ALTER TABLE investigation_analyses ADD COLUMN total_rounds INTEGER;
    END IF;
END $$;

-- 2. 기존 데이터 backfill
UPDATE investigation_analyses
SET total_rounds = CAST(result_data->>'total_rounds' AS INTEGER)
WHERE status = 'completed'
  AND result_data IS NOT NULL
  AND result_data->>'total_rounds' IS NOT NULL
  AND total_rounds IS NULL;
```

**After**
```python
# 모델에 컬럼 추가
class InvestigationAnalysis(Base):
    total_rounds = Column(Integer, nullable=True)  # JSON 파싱 불필요!

# 사용
for row in results:
    total_rounds = row[6] if row[6] else 0  # 직접 조회
```

#### 인덱스 전략

**자주 사용되는 쿼리 패턴 분석:**
1. 상태별 필터링: `WHERE status = 'completed'`
2. 최신순 정렬: `ORDER BY created_at DESC`
3. 판정 결과 필터: `WHERE final_verdict = '중복'`
4. 사용자별 조회: `WHERE user_id = 'xxx'`

**추가된 인덱스:**
```sql
-- 단일 컬럼 인덱스
CREATE INDEX ix_investigation_analyses_status
ON investigation_analyses(status);

CREATE INDEX ix_investigation_analyses_final_verdict
ON investigation_analyses(final_verdict);

CREATE INDEX ix_investigation_analyses_created_at
ON investigation_analyses(created_at);

CREATE INDEX ix_investigation_analyses_completed_at
ON investigation_analyses(completed_at);

-- 복합 인덱스 (자주 함께 사용되는 조합)
CREATE INDEX ix_status_created
ON investigation_analyses(status, created_at);

CREATE INDEX ix_user_created
ON investigation_analyses(user_id, created_at);
```

**복합 인덱스의 효과:**
```sql
-- 이 쿼리는 ix_status_created 인덱스를 활용
SELECT * FROM investigation_analyses
WHERE status = 'completed'  -- 인덱스 첫 번째 컬럼
ORDER BY created_at DESC;   -- 인덱스 두 번째 컬럼

-- Index Scan만으로 처리 가능 (Full Table Scan 불필요)
```

**SQLAlchemy 모델에 반영:**
```python
# api/models/investigation_analysis.py
class InvestigationAnalysis(Base):
    # 컬럼 정의
    status = Column(String(20), nullable=False, default="processing", index=True)
    final_verdict = Column(String(50), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now, index=True)
    total_rounds = Column(Integer, nullable=True)

    # 복합 인덱스
    __table_args__ = (
        Index('ix_status_created', 'status', 'created_at'),
        Index('ix_user_created', 'user_id', 'created_at'),
    )
```

---

### 4. 프론트엔드 폴링 최적화

#### Before
```javascript
// 5초마다 체크, 첫 체크까지 5초 대기
const interval = setInterval(checkStatus, 5000);
```

**문제점:**
- 분석 시작 후 첫 상태 확인까지 5초 대기
- 사용자는 "먹통" 느낌 경험

#### After
```javascript
// 즉시 첫 체크 실행
await checkStatus();  // 즉시 실행!

// 이후 1초마다 체크 (5배 빠른 응답)
const interval = setInterval(checkStatus, 1000);
```

**개선 효과:**
- 초기 응답성 향상 (0초 대기)
- 상태 업데이트 5배 빠름
- 서버 부하는 최소화된 상태 (SELECT 쿼리 최적화로)

---

## 성능 개선 결과

### 측정 결과

| 항목 | Before | After | 개선율 |
|------|--------|-------|--------|
| **API 응답 시간** | 9.44초 | **1.2초** | **87.3% 감소** |
| **데이터 전송량** | ~1MB | ~4KB | **99.6% 감소** |
| **폴링 간격** | 5초 | 1초 | **80% 감소** |
| **DB 쿼리 시간** | ~8초 | ~1초 | **87.5% 감소** |

### 사용자 경험 개선
- ✅ 페이지 로드: 9.44초 → 1.2초 (실측)
- ✅ 상태 업데이트: 5초마다 → 1초마다
- ✅ 체감 속도: "느림" → "빠름"

---

## 학습 포인트

### 1. SELECT 최적화가 가장 중요하다

**핵심 원칙:**
```python
# ❌ 나쁜 예: 모든 컬럼 로드
query = db.query(Model).all()

# ✅ 좋은 예: 필요한 컬럼만 로드
query = db.query(Model.id, Model.name, Model.status).all()
```

**이유:**
- 네트워크 전송량이 성능의 핵심
- 특히 외부 DB 서버 사용 시 더욱 중요
- JSON 같은 큰 컬럼은 목록 조회에서 제외

### 2. 연결 풀은 필수

**외부 DB 서버 사용 시:**
```python
# 연결 생성 오버헤드
TCP handshake: ~50ms
SSL negotiation: ~100ms
Authentication: ~50ms
--------------------------
총: ~200ms per connection
```

**연결 풀 사용 시:**
```python
# 재사용으로 오버헤드 제거
Connection reuse: ~1ms
```

### 3. 인덱스 전략

**인덱스가 필요한 컬럼:**
1. WHERE 절에 자주 사용되는 컬럼
2. ORDER BY에 사용되는 컬럼
3. JOIN에 사용되는 컬럼

**복합 인덱스 순서:**
```sql
-- ✅ 올바른 순서 (카디널리티 낮은 것 → 높은 것)
CREATE INDEX idx ON table(status, created_at);
-- status는 3가지 값만 (processing, completed, failed)
-- created_at은 모든 행이 다름

-- WHERE status = 'completed' ORDER BY created_at
-- 위 쿼리에 최적화됨
```

### 4. JSON 컬럼 사용 시 주의사항

**문제:**
- JSON 컬럼은 파싱 오버헤드 발생
- 목록 조회에서 JSON 전체를 가져오는 것은 비효율

**해결책:**
```python
# ❌ 나쁜 예
total_rounds = json_column.get('total_rounds')

# ✅ 좋은 예: 자주 조회하는 값은 별도 컬럼으로
total_rounds = Column(Integer)  # 전용 컬럼
```

### 5. 성능 측정 방법

**Chrome DevTools 활용:**
1. Network 탭 열기
2. API 요청 클릭
3. Timing 탭 확인
   - `Waiting for server response`가 가장 중요!

**SQL 쿼리 분석:**
```python
# SQLAlchemy 로깅 활성화
engine = create_engine(url, echo=True)

# 실행되는 SQL 확인 가능
```

**EXPLAIN 사용:**
```sql
EXPLAIN ANALYZE
SELECT id, created_at FROM investigation_analyses
WHERE status = 'completed'
ORDER BY created_at DESC
LIMIT 20;

-- Index Scan 사용 확인
-- Seq Scan이면 인덱스 추가 필요
```

---

## 추가 최적화 아이디어

### 1. 페이지네이션 최적화
```python
# Keyset Pagination (더 빠름)
# OFFSET 대신 WHERE created_at < :last_seen 사용
query = query.filter(
    InvestigationAnalysis.created_at < last_seen_timestamp
).limit(page_size)
```

### 2. 캐싱 추가
```python
from functools import lru_cache
from datetime import datetime, timedelta

@lru_cache(maxsize=100)
def get_analysis_list(page: int, status: str, cache_time: datetime):
    # cache_time을 1분 단위로 반올림하여 캐시 키로 사용
    return db.query(...).all()

# 사용
cache_key = datetime.now().replace(second=0, microsecond=0)
results = get_analysis_list(page, status, cache_key)
```

### 3. 읽기 전용 레플리카 사용
```python
# 쓰기용 Master
write_engine = create_engine(MASTER_URL)

# 읽기용 Replica (목록 조회)
read_engine = create_engine(REPLICA_URL)
```

---

## 마이그레이션 실행 방법

### 1. total_rounds 컬럼 추가
```bash
# SQL 파일 실행
psql -U user -d database -f migrations/add_total_rounds_and_indexes.sql

# 또는 Python으로 실행
python -c "
from sqlalchemy import create_engine, text
engine = create_engine('postgresql://...')
with open('migrations/add_total_rounds_and_indexes.sql') as f:
    sql = f.read()
    with engine.connect() as conn:
        conn.execute(text(sql))
        conn.commit()
"
```

### 2. 검증
```sql
-- 컬럼 확인
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_name = 'investigation_analyses';

-- 인덱스 확인
SELECT indexname, indexdef
FROM pg_indexes
WHERE tablename = 'investigation_analyses';

-- 데이터 확인
SELECT id, total_rounds, status
FROM investigation_analyses
WHERE status = 'completed'
LIMIT 5;
```

---

## 결론

### 핵심 교훈

1. **SELECT 최적화가 가장 큰 효과** - 필요한 컬럼만 조회
2. **연결 풀 필수** - 특히 외부 DB 서버 사용 시
3. **인덱스 전략** - WHERE, ORDER BY 컬럼에 인덱스
4. **JSON 컬럼 주의** - 자주 조회하는 값은 별도 컬럼으로
5. **측정이 중요** - Chrome DevTools, EXPLAIN 활용

### 성능 최적화 체크리스트

- [ ] 필요한 컬럼만 SELECT하는가?
- [ ] 큰 컬럼(JSON, TEXT)을 불필요하게 로드하지 않는가?
- [ ] 연결 풀이 설정되어 있는가?
- [ ] 자주 사용하는 컬럼에 인덱스가 있는가?
- [ ] 복합 인덱스 순서가 올바른가?
- [ ] 실제 성능을 측정했는가?

---

**작성일**: 2025-11-06
**개선 전**: 9.44초
**개선 후**: 1.2초 (실측)
**개선율**: 87.3%

🚀 **성능 최적화 성공!**
