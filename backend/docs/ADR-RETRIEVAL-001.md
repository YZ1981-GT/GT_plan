# ADR-RETRIEVAL-001: 向量存储选型 — pgvector vs ChromaDB

| 字段 | 值 |
|------|---|
| **状态** | Accepted |
| **日期** | 2026-05-31 |
| **决策者** | 平台架构组 |
| **关联 spec** | `retrieval-kernel-unification`（需求 3.5） |

## 背景（Context）

平台检索内核（`KnowledgeIndexService`）原向量存储方案：
- PG 文本列存 embedding（逗号分隔浮点串）
- 查询时 numpy 全表扫描计算余弦相似度（O(N)）
- 数据规模：数千条向量（11 类业务数据 + 知识文件）

需迁移到支持 DB 内向量运算的方案，以支撑 6000 并发目标。

候选方案：
1. **pgvector**：PostgreSQL 扩展，`vector` 列类型 + ivfflat/HNSW 索引
2. **ChromaDB**：独立向量数据库，Python 客户端已集成（当前仅 health check 闲置）

## 决策（Decision）

选择 **pgvector** 作为向量存储后端。

## 理由（Rationale）

| 维度 | pgvector | ChromaDB |
|------|----------|----------|
| 基础设施 | 同一 PostgreSQL 实例，零额外部署 | 独立进程/容器，需额外运维 |
| 事务一致性 | 与业务数据同库同事务 | 跨库最终一致，需补偿逻辑 |
| 索引能力 | ivfflat（当前规模足够）/ HNSW（未来可升级） | 内置 HNSW |
| 数据规模适配 | 数千~数十万条性能充裕 | 优势在百万级以上 |
| 查询方式 | `ORDER BY embedding <=> $1 LIMIT k`（余弦距离） | 客户端 API 调用 |
| 迁移成本 | 加扩展 + 加列 + 建索引（1 条迁移 SQL） | 数据双写 + 客户端切换 |
| 降级方案 | PgTextStore（逗号串+numpy）保留作 fallback | 需回退到 PG 方案 |

关键判断：
- 当前数据量为**数千条**（非百万），ivfflat 索引绰绰有余
- 同库事务一致性避免了分布式一致性问题
- 零额外基础设施 = 零额外运维负担
- ChromaDB 客户端已就绪但闲置，切换成本不为零但也不高

## 后果（Consequences）

### 正面
- 向量查询从 O(N) numpy 全扫降为 DB 内 ivfflat 索引扫描
- 业务数据与向量索引同事务提交，无一致性窗口
- 运维复杂度不增加（同一 PG 实例）
- feature flag 控制切换，PgTextStore 保留降级

### 负面 / 风险
- pgvector 扩展需 PG 超级用户权限安装（`CREATE EXTENSION vector`）
- 若数据量未来超百万条，ivfflat 召回精度下降需评估 HNSW 或外迁

### Plan B：ChromaDB
- ChromaDB 客户端已集成（`chromadb_service.py` 仅 health check）
- 当数据量超百万条且 pgvector HNSW 仍不满足时，启用 ChromaDB
- 届时通过 `VectorStore` Protocol 切换，业务层零改动

## 实现要点

- 迁移 SQL：`CREATE EXTENSION IF NOT EXISTS vector` + `ALTER TABLE knowledge_index ADD COLUMN embedding vector(1536)` + ivfflat 索引
- 查询：`ORDER BY embedding <=> $1 LIMIT $k`
- feature flag：`VECTOR_STORE_BACKEND=pgvector|legacy`（默认 pgvector）
- 等价验证：PgTextStore 与 PgVectorStore 同 query top_k 结果集一致（R4 属性）
