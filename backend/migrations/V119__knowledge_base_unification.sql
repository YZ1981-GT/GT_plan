-- V119: Knowledge Base Unification
-- 索引状态列 + pgvector 向量列（pgvector 缺失时仅加状态列，不中断）

-- 1. knowledge_documents 扩展（不依赖 pgvector）
ALTER TABLE knowledge_documents ADD COLUMN IF NOT EXISTS index_status VARCHAR(30) DEFAULT 'pending';
ALTER TABLE knowledge_documents ADD COLUMN IF NOT EXISTS index_error TEXT;

-- 2. 复合过滤索引（不依赖 pgvector）
CREATE INDEX IF NOT EXISTS ix_ki_project_source_active
  ON knowledge_index (project_id, source_type)
  WHERE is_deleted = false;

-- 3. pgvector 相关（容错：扩展不存在则跳过向量列和 HNSW 索引）
DO $$
BEGIN
  -- 尝试创建 pgvector 扩展
  BEGIN
    CREATE EXTENSION IF NOT EXISTS vector;
  EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'pgvector extension not available, skipping vector columns';
    RETURN;
  END;

  -- 添加向量列
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name = 'knowledge_index' AND column_name = 'embedding_vec'
  ) THEN
    ALTER TABLE knowledge_index ADD COLUMN embedding_vec vector(1024);
  END IF;

  -- HNSW 索引
  IF NOT EXISTS (
    SELECT 1 FROM pg_indexes WHERE indexname = 'ix_ki_embedding_hnsw'
  ) THEN
    CREATE INDEX ix_ki_embedding_hnsw
      ON knowledge_index USING hnsw (embedding_vec vector_cosine_ops)
      WITH (m = 16, ef_construction = 200);
  END IF;
END $$;
