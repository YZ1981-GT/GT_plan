# 实施计划：retrieval-kernel-unification（检索/知识层统一架构）

> 设计：#[[file:.kiro/specs/retrieval-kernel-unification/design.md]]
> 需求：#[[file:.kiro/specs/retrieval-kernel-unification/requirements.md]]
> 工作流：Design-First | 分 3 阶段 ~4 天 | 复用 C 引擎非从零造
> 铁律：删 B 前 grep 0 其他调用方；检索失败降级 ilike；零回归

## 阶段 1 — 删旧轨 B（~0.5 天）

- [ ] 1. 清理 KnowledgeService（旧文件系统）
  - grep 确认 `KnowledgeService` 全仓仅 `reference_doc_service` 1 处降级调用
  - reference_doc_service 删文件系统降级分支
  - KnowledgeService 标 deprecated（建限期删除 task，不留永久 deprecated）
  - 删前后 reference_doc_service 测试全绿 + 独立 commit
  - _需求: 1.4, 5.3_

## 阶段 2 — A 接入 C 引擎 + 联动（~1.5 天）

- [ ] 2. _fetch_project_texts 重构为 IndexSource 注册表
  - 定义 IndexSource Protocol（source_type + fetch_texts）
  - 11 类 KnowledgeSourceType 业务数据重构为 BusinessDataSource（注册式，行为不变）
  - _需求: 1.2_ _属性: R1_

- [ ] 3. 新增 KnowledgeDocSource 接入知识文件
  - **前置**：`ai_models.py` 的 `KnowledgeSourceType` 枚举加 `knowledge_doc = "knowledge_doc"`（现 11 成员无此项）；readCode 确认 KnowledgeIndex.source_type 列类型决定是否需 enum 迁移
  - source_type=knowledge_doc，fetch_texts 读 KnowledgeDocument.content_text
  - 注册到内核 IndexSource 列表
  - _需求: 1.3_ _属性: R2_

- [ ] 4. semantic_search 加 scope + 权限过滤
  - **现签名 `(project_id, query, top_k=10)` 无 scope/user** → 新增 2 个 kwarg（默认值保 ai_chat_service 零改）
  - scope=project_data｜knowledge_doc｜cross_year｜all
  - 带 user 时按权限过滤（继承 KnowledgeDocument 权限模型）
  - 向量召回失败降级 ilike
  - _需求: 1.1, 4.1, 4.2_ _属性: R1, R2_

- [ ] 5. 知识文件 CRUD 联动钩子（修 §21.3.1）
  - knowledge_folders upload/update 端点末尾调 `incremental_update(project_id, source_type="knowledge_doc", source_id=doc.id, content=...)`（参数名是 source_id 非 doc_id）
  - delete 端点同步删向量
  - _需求: 2.1, 2.2_ _属性: R3_

- [ ] 6. reference_doc_service 改调 semantic_search
  - load_from_knowledge_base 改调 semantic_search(scope=knowledge_doc)，ilike 降级
  - _需求: 2.3_ _属性: R1_

- [ ] 7. 阶段 2 PBT + 回归
  - R1 召回降级 + R2 权限隔离 + R3 联动幂等
  - ai_chat_service 既有行为零回归（C 现有消费方）
  - hypothesis max_examples 10~15
  - _需求: 5.2_ _属性: R1, R2, R3_

## 阶段 3 — 向量存储迁 pgvector（~2 天）

- [ ] 8. 抽 VectorStore Protocol
  - 定义 Protocol（add/query/delete）
  - PgTextStore 包装现状（逗号串 + numpy 全扫，保留降级）
  - _需求: 3.1_ _属性: R4_

- [ ] 9. PgVectorStore（pgvector 扩展）
  - V0XX 迁移：CREATE EXTENSION vector + KnowledgeIndex 加 embedding vector 列 + ivfflat 索引
  - query 用 `ORDER BY embedding <=> $1 LIMIT $k`（DB 内余弦）
  - 配套 R0XX 回滚
  - _需求: 3.2_ _属性: R4_

- [ ] 10. feature flag 切换 + 等价验证
  - feature flag 控制 PgTextStore ↔ PgVectorStore
  - 等价测试：同 query top_k 结果集一致（R4 零回归）
  - _需求: 3.3, 3.4_ _属性: R4_

- [ ] 11. ADR-RETRIEVAL-001 + 收尾
  - pgvector vs ChromaDB 选型记录（ChromaDB 留 Plan B）
  - 更新 INDEX.md + memory 完成记录
  - 单 commit（git status 确认无其他 staged）
  - _需求: 3.5_

- [ ]* 12. 真实环境验证（待 start-dev.bat）
  - 上传知识文件 → AI 对话语义检索到它 端到端
  - pgvector 性能基准（大库召回延迟）
  - 显式标"待环境"不伪绿
  - _需求: 2.1, 3.2_
