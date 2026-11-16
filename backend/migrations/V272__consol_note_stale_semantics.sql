-- 合并附注待更新状态语义：记录原因与首次置位时间。
ALTER TABLE consol_note_data
    ADD COLUMN IF NOT EXISTS stale_reason VARCHAR(40);
ALTER TABLE consol_note_data
    ADD COLUMN IF NOT EXISTS stale_at TIMESTAMPTZ;

-- 存量待更新行没有历史原因，只能明确标记为 legacy；时间保持 NULL，避免伪造发生时间。
UPDATE consol_note_data
   SET stale_reason = 'legacy'
 WHERE is_stale = TRUE
   AND stale_reason IS NULL;
