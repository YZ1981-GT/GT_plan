-- V069: 报表行次映射递减项(contra)支持 — report_line_mapping 加 mapping_sign 列
-- 背景: v2 符号约定下 tb 余额按科目自然方向存正数，备抵科目(累计折旧/摊销/各类减值/
--       存货跌价/库存股等)也存正数。报表行次聚合(get_summary_with_adjustments 的
--       line_accounts 分支)原为纯求和，会把备抵项错误加上去 → 固定资产/投资性房地产/
--       无形资产净值虚增。本列标记每条映射在行次聚合时是加项(add)还是减项(subtract)。
-- 默认 'add'，存量数据行为不变；备抵科目由 seed/迁移标 'subtract'。
-- DDL 幂等可重入。

ALTER TABLE report_line_mapping
    ADD COLUMN IF NOT EXISTS mapping_sign VARCHAR(10) NOT NULL DEFAULT 'add';
