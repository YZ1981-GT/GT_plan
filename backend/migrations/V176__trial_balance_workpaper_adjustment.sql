-- V176：试算表保留底稿发布产生的审定数增量
--
-- wp_adjustment 是增量分量，不是冻结的审定数：后续四表重导入或调整重算时，
-- audited_amount = 未审数 + RJE + AJE + wp_adjustment。
-- 所有 DDL 和回填均可重复执行；回填只修正历史审定数与三项旧分量不一致的行。

ALTER TABLE trial_balance
    ADD COLUMN IF NOT EXISTS wp_adjustment NUMERIC(20, 2) NOT NULL DEFAULT 0;

ALTER TABLE trial_balance
    ADD COLUMN IF NOT EXISTS wp_publish_base NUMERIC(20, 2);

ALTER TABLE trial_balance
    ADD COLUMN IF NOT EXISTS wp_published_at TIMESTAMPTZ;

UPDATE trial_balance
SET wp_adjustment = audited_amount
    - (
        COALESCE(unadjusted_amount, 0)
        + COALESCE(rje_adjustment, 0)
        + COALESCE(aje_adjustment, 0)
    )
WHERE audited_amount IS NOT NULL
  AND audited_amount <> (
        COALESCE(unadjusted_amount, 0)
        + COALESCE(rje_adjustment, 0)
        + COALESCE(aje_adjustment, 0)
    );
