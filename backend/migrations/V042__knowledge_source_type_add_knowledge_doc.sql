-- V042: KnowledgeSourceType 枚举新增 knowledge_doc 成员
-- 关联: retrieval-kernel-unification spec (Task 3: KnowledgeDocSource 接入)
-- 说明: KnowledgeIndex.source_type 列使用 PG ENUM (knowledge_source_type_enum)，
--       新增枚举值需 ALTER TYPE ADD VALUE（不可事务内即用，但 ADD VALUE 本身幂等）

-- ALTER TYPE ADD VALUE 是幂等的（PG 9.3+ IF NOT EXISTS）
ALTER TYPE knowledge_source_type_enum ADD VALUE IF NOT EXISTS 'knowledge_doc';
