-- R263: 回滚 V263
-- pgvector 扩展与 embedding_vec 列 / HNSW 索引保留：它们同属 V119 的设计（V119 已登记为已应用），
-- 扩展也可能被其他对象使用（与 R043 同口径）。
DROP INDEX IF EXISTS uq_knowledge_index_chunk;
ALTER TABLE knowledge_index DROP COLUMN IF EXISTS embedding_model;

-- 外键恢复前先删掉指向非项目的分块（全局哨兵分区等派生数据）
DELETE FROM knowledge_index
WHERE project_id NOT IN (SELECT id FROM projects);
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'knowledge_index_project_id_fkey'
      AND conrelid = 'knowledge_index'::regclass
  ) THEN
    ALTER TABLE knowledge_index
      ADD CONSTRAINT knowledge_index_project_id_fkey
      FOREIGN KEY (project_id) REFERENCES projects(id);
  END IF;
END $$;

-- 超过 5000 字符的文本向量放不回 VARCHAR(5000)：置空后收窄（有 embedding_vec 的行仍可检索）
UPDATE knowledge_index SET embedding_vector = NULL WHERE length(embedding_vector) > 5000;
ALTER TABLE knowledge_index ALTER COLUMN embedding_vector TYPE VARCHAR(5000);
