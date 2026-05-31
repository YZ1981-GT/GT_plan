-- R042: 回滚 V042 — knowledge_source_type_enum 移除 knowledge_doc
-- 注意: PG 不支持 ALTER TYPE DROP VALUE，需重建枚举类型
-- 仅在确认无 knowledge_index 行使用 knowledge_doc 时可执行

-- 1. 删除使用 knowledge_doc 的索引行
DELETE FROM knowledge_index WHERE source_type = 'knowledge_doc';

-- 2. 重建枚举（PG 不支持 DROP VALUE，需 rename → create → migrate → drop）
ALTER TYPE knowledge_source_type_enum RENAME TO knowledge_source_type_enum_old;

CREATE TYPE knowledge_source_type_enum AS ENUM (
    'trial_balance', 'journal', 'auxiliary', 'contract',
    'document_scan', 'workpaper', 'adjustment', 'elimination',
    'confirmation', 'review_comment', 'prior_year_summary'
);

ALTER TABLE knowledge_index
    ALTER COLUMN source_type TYPE knowledge_source_type_enum
    USING source_type::text::knowledge_source_type_enum;

DROP TYPE knowledge_source_type_enum_old;
