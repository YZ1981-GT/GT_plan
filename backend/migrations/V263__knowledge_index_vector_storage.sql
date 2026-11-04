-- V263: 知识库向量索引存储修复（spec enterprise-embedding-rerank-closure R4 / R5）
-- 现状（2026-11-04）：knowledge_index 0 行，写入从未成功过 ——
--   文本向量列 VARCHAR(5000) 写不下真实维度（1024 维逗号串约 2 万字符）
--   分块 upsert 的 ON CONFLICT (project_id, source_id, chunk_index) 没有唯一索引承接
--   公共文档的全局哨兵分区（全零 UUID）不是真实项目，被 projects 外键挡住
--   pgvector 列从未落地（V119 执行时扩展不可用而跳过）

-- 1) 文本向量列放宽为 TEXT
ALTER TABLE knowledge_index ALTER COLUMN embedding_vector TYPE TEXT;

-- 2) 向量模型签名「模型名@维度」：检索只比同签名分块，不同模型的向量不混比
ALTER TABLE knowledge_index ADD COLUMN IF NOT EXISTS embedding_model VARCHAR(200);

-- 3) 去掉 project_id 外键：索引是可重建的派生层，哨兵分区不是项目
ALTER TABLE knowledge_index DROP CONSTRAINT IF EXISTS knowledge_index_project_id_fkey;

-- 4) upsert 冲突目标：同键分块先去重（派生数据，保留最新一条），再建唯一索引
DELETE FROM knowledge_index a
USING knowledge_index b
WHERE a.project_id = b.project_id
  AND a.source_id = b.source_id
  AND a.chunk_index = b.chunk_index
  AND (a.updated_at, a.id) < (b.updated_at, b.id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_knowledge_index_chunk
    ON knowledge_index (project_id, source_id, chunk_index);

-- 5) pgvector（容错：扩展不可用时整段跳过，写入与检索退回文本列）
DO $$
BEGIN
  BEGIN
    CREATE EXTENSION IF NOT EXISTS vector;
  EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'pgvector extension not available, skipping embedding_vec';
    RETURN;
  END;

  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = current_schema()
      AND table_name = 'knowledge_index' AND column_name = 'embedding_vec'
  ) THEN
    ALTER TABLE knowledge_index ADD COLUMN embedding_vec vector(1024);
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_indexes
    WHERE schemaname = current_schema() AND indexname = 'ix_ki_embedding_hnsw'
  ) THEN
    CREATE INDEX ix_ki_embedding_hnsw
      ON knowledge_index USING hnsw (embedding_vec vector_cosine_ops)
      WITH (m = 16, ef_construction = 200);
  END IF;
END $$;
