-- completed_at 인덱스 추가 (정렬 최적화)
-- 생성일: 2025-11-06

CREATE INDEX IF NOT EXISTS ix_investigation_analyses_completed_at
ON investigation_analyses(completed_at);

-- 마이그레이션 완료
SELECT 'Index on completed_at created successfully!' AS status;
