# ADR-031: 知识库真源与索引生命周期

> 状态：已采纳  
> 日期：2026-06-07  
> 决策者：杨志  
> 关联 Spec：`platform-evidence-knowledge-ai-governance` P2-1

## 背景

知识库系统涉及三个存储层次：

1. **关系型数据库**（`knowledge_documents` 表）—— 元数据、版本链、权限
2. **文件系统/对象存储**（`STORAGE_ROOT/knowledge/{folder_id}/`）—— 原始文件
3. **向量索引**（`knowledge_index` 表）—— 文本 chunk + embedding 向量

当前存在以下隐患：
- 文档更新后向量索引不一定同步（仅 `incremental_update` 在 CRUD 钩子中触发，embedding 404 时无法重建）
- AI 引用返回的 citation 只含 `source_id` + `chunk_index`，无文档版本信息
- 无法判断 citation 对应的索引是否仍与最新文档内容一致

## 决策

### 1. 真源层次定义

| 层次 | 角色 | 说明 |
|------|------|------|
| `knowledge_documents` 表 | **主源 (Source of Truth)** | 文档 ID、名称、版本号、content_text、权限、创建时间 |
| 文件存储 `storage_path` | **原文存储** | 不可变文件；新版本创建新文件路径而非覆盖 |
| `knowledge_index` 表 | **派生缓存** | 可重建、可标记失效；丢失不影响主数据完整性 |

### 2. 版本管理

`KnowledgeDocument` 已有 `version` (int) 和 `previous_version_id` 字段。每次重新上传同名文档，`KnowledgeDocumentService.create_document` 自动建版本链（`_resolve_version_chain`）。

### 3. 索引生命周期

```
文档创建/上传
    → _trigger_index_update (知识文件夹 router 钩子)
    → KnowledgeIndexService.incremental_update (upsert chunk)
    → 索引状态 = FRESH

文档更新（新版本创建）
    → 旧索引标记 is_stale = True（新增字段）
    → 触发新版本 incremental_update
    → 新索引 is_stale = False
    → 旧索引可异步清理或保留审计追溯

文档删除
    → _trigger_index_delete (soft delete 索引)
    → 索引状态 = DELETED (is_deleted = True)

索引重建 (build_index)
    → 删除旧索引 → 全量重建 → is_stale = False
```

### 4. Stale 标记规则

- **何时标记 stale**：文档内容变更（`content_text` 或 `storage_path` 变更、新版本创建）
- **何时解除 stale**：`incremental_update` 或 `build_index` 成功写入新 chunk
- **stale 索引的影响**：AI 引用时标记 `is_stale_source=True`，不可作为 `confirmed` 状态 AI 内容的唯一证据来源

### 5. 调用方盘点

| 调用方 | 文件 | 使用方式 |
|--------|------|----------|
| `doc_ai_context_builder.ContextBuilder` | `doc_ai_context_builder.py` | `KnowledgeIndexService(db)` → `semantic_search` 构建 AI 对话上下文 |
| `reference_doc_service.load_from_knowledge_base` | `reference_doc_service.py` | `KnowledgeIndexService(db)` → `semantic_search(scope=knowledge_doc)` |
| `knowledge_folders.router._trigger_index_update` | `routers/knowledge_folders.py` | `KnowledgeIndexService(db)` → `incremental_update` CRUD 钩子 |
| `knowledge_folders.router._trigger_index_delete` | `routers/knowledge_folders.py` | 直接 UPDATE `knowledge_index` soft delete |
| `KnowledgeDocSource.fetch_texts` | `index_source.py` | 读 `KnowledgeDocument.content_text` 供 `build_index` |
| `BusinessDataSource.fetch_texts` | `index_source.py` | 读业务数据供 `build_index` |

### 6. AI Citation 增强

AI 引用（`doc_ai_chat` 返回的 SSE `citations` 事件）新增字段：
- `doc_version`: 引用时文档版本号
- `is_stale`: 索引是否 stale
- `chunk_index` / `paragraph_index`: 精确段落定位（已有）

## 后果

- **正面**：索引失效可见、AI 引用可追溯到版本、confirmed AI 内容不依赖过期索引
- **负面**：新增 `is_stale` 列需 migration；embedding 404 时 stale 无法自动解除（需人工重建或等 embedding 恢复）
- **风险缓解**：embedding 不可用时 ilike 降级路径仍工作；stale 标记仅影响 `confirmed` 门控，不阻断普通 AI 对话

## 替代方案（已否决）

1. **不标记 stale，每次 AI 调用实时重建索引** —— 性能不可接受
2. **用 content_hash 替代版本号** —— 额外计算成本且 KnowledgeDocument 已有版本链

## 实施步骤

1. `KnowledgeIndex` 模型新增 `is_stale` + `doc_version` 列
2. `knowledge_folders.router` 文档更新钩子标记旧索引 stale
3. `incremental_update` / `build_index` 成功后清除 stale
4. `Citation` dataclass 增加 `doc_version` + `is_stale` 字段
5. AI 确认门控拒绝仅依赖 stale 来源的 confirmed 状态
