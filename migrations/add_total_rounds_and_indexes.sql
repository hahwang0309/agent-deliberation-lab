-- 페이지 조회 성능 개선을 위한 마이그레이션
-- 생성일: 2025-11-06

-- 1. total_rounds 컬럼 추가
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

-- 2. 인덱스 추가 (이미 있으면 무시됨)
CREATE INDEX IF NOT EXISTS ix_investigation_analyses_status
ON investigation_analyses(status);

CREATE INDEX IF NOT EXISTS ix_investigation_analyses_final_verdict
ON investigation_analyses(final_verdict);

CREATE INDEX IF NOT EXISTS ix_investigation_analyses_created_at
ON investigation_analyses(created_at);

-- 3. 복합 인덱스 추가 (자주 사용되는 쿼리 패턴)
CREATE INDEX IF NOT EXISTS ix_status_created
ON investigation_analyses(status, created_at);

CREATE INDEX IF NOT EXISTS ix_user_created
ON investigation_analyses(user_id, created_at);

-- 4. 기존 데이터의 total_rounds 업데이트 (result_data에서 추출)
UPDATE investigation_analyses
SET total_rounds = CAST(result_data->>'total_rounds' AS INTEGER)
WHERE status = 'completed'
  AND result_data IS NOT NULL
  AND result_data->>'total_rounds' IS NOT NULL
  AND total_rounds IS NULL;

-- 마이그레이션 완료
SELECT 'Migration completed successfully!' AS status;
