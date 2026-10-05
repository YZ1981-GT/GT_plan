-- V179：report_config 增加调整列公式字段
--
-- 为试算平衡表的审计调整列（AJE）和重分类调整列（RJE）各增加一个公式字段。
-- 有值时以公式为准求值；无值（NULL）时退回现有"从未审数公式反解科目码汇总"路径。
-- 字段存储净额公式（如 ADJ('6001','aje_net')），借贷拆分由展示层按符号决定。
-- 所有 DDL 幂等；回滚见 R179。

ALTER TABLE report_config
    ADD COLUMN IF NOT EXISTS aje_formula TEXT;

ALTER TABLE report_config
    ADD COLUMN IF NOT EXISTS rje_formula TEXT;
