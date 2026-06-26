-- V094: A13 错报评价自动聚合 - 扩展 unadjusted_misstatements 表
-- 新增 prior_year_status (上年结转状态) 和 source_wp_code (来源底稿编码)

ALTER TABLE unadjusted_misstatements
  ADD COLUMN IF NOT EXISTS prior_year_status VARCHAR(20)
    DEFAULT 'new'
    CHECK (prior_year_status IN ('new', 'continuing', 'reversed'));

ALTER TABLE unadjusted_misstatements
  ADD COLUMN IF NOT EXISTS source_wp_code VARCHAR(20);

COMMENT ON COLUMN unadjusted_misstatements.prior_year_status IS
  '上年结转状态: new=本年新增, continuing=延续, reversed=已转回';
COMMENT ON COLUMN unadjusted_misstatements.source_wp_code IS
  '来源底稿编码 (如 D2-1, F3A)，用于 ref_chip 跳转';
