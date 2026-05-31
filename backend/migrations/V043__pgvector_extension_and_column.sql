-- V043: pgvector 扩展 + KnowledgeIndex embedding vector 列 + ivfflat 索引
-- 关联: retrieval-kernel-unification spec (Task 9: PgVectorStore)
-- 说明: 启用 pgvector 扩展，为 knowledge_index 表添加原生 vector(768) 列，
--       创建 ivfflat 索引支持高效余弦相似度检索（替代 numpy 全表扫描）
-- 维度: 768（匹配 AIService.embedding 输出）
-- 索引: ivfflat with lists=100（适合数千条向量）
--
-- ⚠️ 容错设计：pgvector 是可选扩展，标准 postgres 镜像不含。
--   若扩展不可用，整个迁移优雅跳过（不硬失败），由 feature flag
--   VECTOR_STORE_BACKEND 默认 pgtext 降级（PgTextStore numpy 全扫）。
--   待运维在 PG 安装 pgvector 后，重跑本迁移即可启用 PgVectorStore。

DO $pgvector$
BEGIN
    -- 1. 尝试启用 pgvector 扩展；不可用时捕获异常并跳过整个迁移
    BEGIN
        CREATE EXTENSION IF NOT EXISTS vector;
    EXCEPTION WHEN OTHERS THEN
        RAISE NOTICE 'pgvector 扩展不可用，跳过 V043（VECTOR_STORE_BACKEND 走 pgtext 降级）：%', SQLERRM;
        RETURN;
    END;

    -- 2. 添加原生 vector 列（768 维，与 AIService.embedding 输出一致）
    ALTER TABLE knowledge_index ADD COLUMN IF NOT EXISTS embedding vector(768);

    -- 3. 创建 ivfflat 索引（余弦距离，lists=100 适合数千~数万条向量）
    CREATE INDEX IF NOT EXISTS ix_knowledge_index_embedding_ivfflat
        ON knowledge_index USING ivfflat (embedding vector_cosine_ops)
        WITH (lists = 100);
END
$pgvector$;
