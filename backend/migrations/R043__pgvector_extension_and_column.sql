-- R043: 回滚 V043 — 移除 pgvector embedding 列和索引
-- 注意: 不 DROP EXTENSION vector（其他表可能使用）

-- 1. 删除 ivfflat 索引
DROP INDEX IF EXISTS ix_knowledge_index_embedding_ivfflat;

-- 2. 删除 embedding vector 列
ALTER TABLE knowledge_index DROP COLUMN IF EXISTS embedding;
