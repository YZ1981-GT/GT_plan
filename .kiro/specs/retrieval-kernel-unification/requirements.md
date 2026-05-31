# 需求文档：retrieval-kernel-unification（检索/知识层统一架构）

> 关联调研：#[[file:docs/proposals/global-modules-status-and-improvement-2026-05-31.md]]（§十六/§七/§21.3.1/§20.4）
> 工作流：Design-First（从 design.md 派生反推）
> 设计：#[[file:.kiro/specs/retrieval-kernel-unification/design.md]]

## 引言

平台知识/检索域当前三套并行（A 知识文件 ilike / B 文件系统旧 / C 业务数据向量 RAG），核心问题是 A 享受不到 C 已存在的向量检索，C 的向量存储用 PG 文本列+numpy 全扫（性能债），B 是旧尾巴。本需求把三套收敛为单一检索内核（C 升级），A 接入，B 删除，向量存储迁 pgvector。**关键：复用已有 C 引擎而非从零造。**

核心约束：检索失败降级 ilike（双保险）、权限继承、零回归、删 B 前 grep 确认仅 1 处调用方。

## 需求

### 需求 1：单一检索内核（三套收敛）

**用户故事**：作为平台维护者，我希望全平台只有一个检索内核，用户上传的知识文件也能享受向量语义检索。

#### 验收标准

1. WHEN KnowledgeDocument 被检索 THEN 走 `KnowledgeIndexService.semantic_search`（向量召回），不再仅 ilike
2. WHEN `_fetch_project_texts` 重构 THEN 6 类业务数据改为可注册 IndexSource 列表（非硬编码）
3. WHEN 知识文件接入 THEN 新增 `KnowledgeDocSource`（source_type=knowledge_doc）读 content_text 建向量
4. WHEN B（KnowledgeService）删除 THEN grep 确认仅 reference_doc_service 1 处降级调用后删 + 标 deprecated

### 需求 2：知识文件→向量索引联动（修 §21.3.1 断裂）

**用户故事**：作为审计师，我上传知识文件后立即能在 AI 对话中语义检索到它，不需要手动重建索引。

#### 验收标准

1. WHEN knowledge_folders upload/update 端点写 KnowledgeDocument THEN 触发 `incremental_update(source_type='knowledge_doc')` 建向量
2. WHEN KnowledgeDocument delete THEN 对应向量索引同步删除
3. WHEN `reference_doc_service.load_from_knowledge_base` 调用 THEN 改调 `semantic_search`，ilike 作降级
4. IF 同一 KnowledgeDocument 多次 incremental_update THEN 向量索引收敛一致（幂等可重建）

### 需求 3：可插拔向量存储 + pgvector 迁移

**用户故事**：作为开发者，我希望向量存储可插拔，从 PG 文本列+numpy 全扫迁到 pgvector 索引，支撑 6000 并发。

#### 验收标准

1. WHEN VectorStore 抽象 THEN 定义 Protocol（add/query/delete）+ PgTextStore（现状）+ PgVectorStore（pgvector ivfflat）
2. WHEN PgVectorStore 查询 THEN 用 `ORDER BY embedding <=> $1 LIMIT $k`（DB 内算余弦，替代全表 numpy）
3. WHEN pgvector 迁移 THEN feature flag 控制切换，PgTextStore 保留降级
4. IF PgTextStore 与 PgVectorStore 对同一 query THEN top_k 结果集一致（迁移零回归）
5. WHEN 迁移完成 THEN 产出 ADR-RETRIEVAL-001（pgvector vs ChromaDB 选型，ChromaDB 留 Plan B）

### 需求 4：检索降级与权限隔离

**用户故事**：作为系统，我要求向量召回失败时降级 ilike（不崩），且检索只返回用户有权访问的知识文件。

#### 验收标准

1. WHEN 向量召回失败（embedding 服务不可用等）THEN semantic_search 降级 ilike 返回非空
2. WHEN semantic_search 带 user THEN 只返回该 user 有权访问的知识文件（权限继承 KnowledgeDocument 权限模型）
3. WHEN embedding 计算 THEN 统一走 `AIService.embedding`

### 需求 5：分阶段迁移零回归

#### 验收标准

1. WHEN 迁移执行 THEN 按阶段 1（删 B）→ 2（A 接入 C + 联动钩子）→ 3（pgvector）顺序
2. WHEN 每阶段完成 THEN ai_chat_service / reference_doc_service 既有行为零回归
3. WHEN 删 B 代码 THEN 删前 grep 0 其他调用方 + 删前后测试全绿 + 独立 commit

### 非功能需求

- **NFR-1 零回归**：ai_chat_service（C 现有消费方）行为不变
- **NFR-2 双保险**：向量召回失败必降级 ilike
- **NFR-3 性能**：pgvector ivfflat 索引替代 O(N) 全表 numpy（6000 并发）
- **NFR-4 复用优先**：复用 C 引擎，禁止从零造 RAG

## 正确性属性（PBT 守护）

- **R1 召回降级**：向量召回失败时 semantic_search 降级 ilike 返非空
- **R2 权限隔离**：semantic_search 只返回 user 有权访问的知识文件
- **R3 联动幂等**：同一 KnowledgeDocument 多次 incremental_update 索引收敛一致
- **R4 VectorStore 等价**：PgTextStore 与 PgVectorStore 同 query top_k 一致
