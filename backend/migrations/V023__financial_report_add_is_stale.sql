-- V023: Add is_stale column to financial_report
-- Required by:
-- - stale_propagation_engine.py (UPDATE financial_report SET is_stale=true)
-- - stale_summary_aggregate.py (COUNT(*) FILTER (WHERE is_stale=true))
-- - report_stale_service.py (US-2 mark_if_mapped)

ALTER TABLE financial_report ADD COLUMN IF NOT EXISTS is_stale BOOLEAN NOT NULL DEFAULT false;

CREATE INDEX IF NOT EXISTS idx_financial_report_stale
    ON financial_report(project_id, year, is_stale)
    WHERE is_stale = true AND is_deleted = false;
