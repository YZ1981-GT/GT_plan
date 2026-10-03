# 知识库检索与授权收口 — 设计

## 一、总体结构

```
消费方（ReferenceDoc / A17 / 指导对话 / ContextBuilder / 附注 RAG / A17-1 / KB 页面搜索）
        │  只调检索内核，不自己拼 SQL
        ▼
KnowledgeIndexService（检索内核，evidence_governance 冻结的委托引擎，公开方法不减）
   ├─ 向量层（可选加速）：_vector_search —— SAVEPOINT + pgvector 列探测 + 内存兜底
   ├─ 业务数据兜底：_bm25_fallback / _ilike_fallback —— SAVEPOINT + defer(embedding_vec)
   └─ 文档词法层（新，权威）：KnowledgeDocSearch（knowledge_doc_search.py）
             │ 判定一律调用
             ▼
KnowledgeAccessPolicy（单一判定面，纯函数）
   ├─ can_read_document（既有，角色无关）
   ├─ can_retrieve(mode, subject, project_id, doc, folder)（新）
   └─ KnowledgeWritePolicy（新：角色上界 + 所有权，只用于写/管理）
```

原则：**文档表是知识正文唯一真源**；索引只是召回加速，缺席时检索照样成立。判定只写一份，所有入口调用同一函数。

## 二、判定面扩展（`knowledge_access_policy.py`）

```python
class KnowledgeRetrievalMode(str, Enum):
    browse = "browse"    # 知识库页面搜索：可读即可
    project = "project"  # 项目内 RAG：可读 ∩ 项目范围
    global_ = "global"   # 无项目 RAG：可读且非 project_group

def effective_resource(doc: KnowledgeResource, folder: KnowledgeResource | None) -> KnowledgeResource | None:
    """文档级别非空取文档三元组，否则完整继承文件夹；继承但父级未知 → None（fail-closed）。"""

KnowledgeAccessPolicy.can_retrieve(mode, subject | None, project_id | None, doc, folder) -> bool
```

判定表（`eff` = 生效三元组，`P` = 当前项目）：

| 模式 | 主体 | 条件 |
|------|------|------|
| project | 有用户 | `can_read_document` ∧ (`eff.level ≠ project_group` ∨ `P ∈ eff.project_ids`) |
| project | 无用户 | `eff.level = public` ∨ (`eff.level = project_group` ∧ `P ∈ eff.project_ids`) |
| global | 有用户 | `can_read_document` ∧ `eff.level ≠ project_group` |
| browse | 有用户 | `can_read_document` |
| browse / global | 无用户 | `ValueError`（编程错误） |
| project | `P is None` | `ValueError` |

`KnowledgeWritePolicy`（角色只在这里出现，作为动作上界；可见性仍由上面角色无关的判定决定）：

```python
role_allows_write(role) = role is not None and role != readonly
can_create(subject, folder, role) = role_allows_write(role) and can_create_in_folder(subject, folder)
can_manage(subject, resource_visible: bool, owner_id, role) =
    resource_visible and role_allows_write(role) and (role == admin or owner_id == subject.user_id)
```

管理权的 `owner_id`：文件夹取 `folder.created_by`；文档取 `document.created_by`（**不**继承文件夹）。系统文件夹（预设、项目文件夹）`created_by` 为空 ⇒ 仅管理员可管理。

## 三、文档词法检索（`knowledge_doc_search.py`）

```python
@dataclass(frozen=True)
class DocSearchRequest:
    query: str
    mode: KnowledgeRetrievalMode
    subject: KnowledgeAccessSubject | None
    project_id: UUID | None
    top_k: int = 10
    restrict_to: tuple[UUID, ...] = ()      # 文档/文件夹 ID 并集，文件夹含子树
    category: str | None = None             # 排序加分
    boost_terms: tuple[str, ...] = ()       # 上下文词（wp_code / 科目名）排序加分

class KnowledgeDocSearch:
    async def search(req) -> list[DocHit]
    async def visible_documents(doc_ids, *, mode, subject, project_id, allow_superseded) -> dict[UUID, DocMeta]
    async def folder_paths(folder_ids) -> dict[UUID, FolderPath]   # 路径 + 祖先链
```

### 3.1 算法

1. **分词**：`_zh_tokenize.query_terms(query)` —— jieba（缺失时 CJK 二元组 + ASCII 词）→ 小写 → 去停用词/纯标点 → 去单字（整句仅一个字时保留）→ 去重 → 超过 12 个时按长度保留长词、再按原序输出。
2. **范围解析**：restrict_to 中的 ID 先查 `knowledge_folders`，命中者用递归 CTE（`UNION` 防环）展开子孙；最终 `doc_id IN 显式文档 ∪ folder_id IN 子树`（并集）。category 用同一 CTE 展开「该分类根文件夹」子树，仅用于加分。
3. **候选 SQL（只取判权三元组 + 元数据，不取正文）**：
   - `knowledge_documents d JOIN knowledge_folders f`，`d.is_deleted = false AND f.is_deleted = false`
   - 每个检索词 `t`：`m_t = (d.name ILIKE p_t OR d.content_text ILIKE p_t OR CAST(d.tags AS TEXT) ILIKE p_t)`，`p_t = '%' || escape(t) || '%'`，`ESCAPE '\'`
   - `WHERE OR(m_t)`；`hits = Σ CASE WHEN m_t THEN 1 ELSE 0 END`
   - 未给 restrict_to：`NOT EXISTS (SELECT 1 FROM knowledge_documents n WHERE n.previous_version_id = d.id AND n.is_deleted = false)`
   - `ORDER BY hits DESC, d.updated_at DESC, d.id` `LIMIT 1000`（`CANDIDATE_CAP`，命中上限记 WARNING）
   - 列表模式（**查询为空**）：去掉 ILIKE 与 hits，`ORDER BY d.updated_at DESC, d.id`；查询非空但无有效检索词（如 `%`）→ 直接返回空（否则通配符查询会把最近全部文档注入上下文）
4. **判定**：逐行 `can_retrieve(...)`（纯函数，同一真源）。
5. **读正文**：对通过者按 hits 取前 `max(top_k*3, top_k)` 条，`SELECT id, content_text WHERE id IN (...)`。
6. **打分**（纯函数 `score_document`）：
   - `coverage = 命中词数 / 检索词数`；`tf = Σ log1p(count_t)`，`tf_norm = min(1, tf / (n·log1p(8)))`
   - `score = min(1, 0.7·coverage + 0.2·tf_norm + 0.1·[文档名命中])`
   - 加分：category 子树内 `+0.15`；每个命中的 boost 词 `+0.05`（合计 ≤0.15）；最终 `min(1, …)`，保留 4 位小数
7. **片段**（纯函数 `best_window`）：收集各检索词在正文中的出现位置（每词最多 200 处），找 500 字窗口内**不同检索词数最多**（其次总出现次数最多、再次最靠前）的窗口，起点左移 50 字留上下文、夹在 `[0, len-500]`；无位置（只命中文件名/标签）取开头。`chunk_index = 起点 // 500`。
8. 按 `(score desc, updated_at desc, id)` 排序截断 top_k。

### 3.2 规模与切换点

ILIKE 对长文本是顺序扫描；平台知识文档当前为个位数、预期数千（`content_text` 上传截断 50,000 字）。候选只取三元组，正文只对 ≤3·top_k 条读取。切换点：候选截断 WARNING 出现、或单次检索 p95 > 500 ms ⇒ 启用方案 B（向量）或 pg_trgm。本 spec 不建 trigram 索引（2 字中文词无法利用 trigram，收益不确定）。

## 四、semantic_search 集成与会话安全

```python
async def semantic_search(self, project_id, query, top_k=10, *, scope="all", user=None,
                          wp_code=None, account_code=None, audit_area=None,
                          restrict_to=None, category=None) -> list[dict]:
    subject = await resolve_subject(db, user) if user is not None else None
    vector_hits, vector_ok = [], False
    if query.strip():
        try: vector_hits = await self._vector_search(...); vector_ok = True
        except Exception: log WARNING
    doc_hits = await self._doc_search.search(DocSearchRequest(mode=project, ...)) if scope in (knowledge_doc, all) else []
    index_hits = (await self._index_lexical_fallback(scope="project_data")) if (not vector_ok and scope in (project_data, all)) else []
    vector_doc_hits = 过滤(vector_hits 中 knowledge_doc 部分, visible_documents(...), restrict_to)
    merged = 去重合并(vector 非文档部分 + vector_doc_hits + doc_hits + index_hits)
    上下文加权（既有 _apply_context_boost）→ 排序 → top_k → _enrich_results
```

- **SAVEPOINT**：新增 `_guarded_read(label, fn)`：`async with self._db.begin_nested(): return await fn()`；异常只记 WARNING 并按调用点语义返回空/抛给上层降级判断。
- **`embedding_vec`**：所有 `select(KnowledgeIndex)` 带 `.options(defer(KnowledgeIndex.embedding_vec))`；pgvector 语句只在进程级探测「列存在」后执行（首次失败置 `False`，本进程不再尝试），执行仍在 SAVEPOINT 内。
- **scope=knowledge_doc 且向量失败**：不再走 BM25/ILIKE（其结果是索引分块的旧副本，与文档词法重复且可能过期）。
- `_filter_by_permission` 重写为基于 `visible_documents`（起点是 `knowledge_documents` 而不是 `knowledge_index`），`semantic_search_strict` 同样使用；`user=None` ⇒ project 模式无用户判定（3.3）。
- `_enrich_results` 重写：从 `visible_documents` 的元数据与 `folder_paths` 取 `document_name/folder_id/folder_path/folder_ancestor_ids`；非文档结果补 `None`。
- 新增 `search_global_knowledge(query, *, user, top_k)` 与 `load_documents(doc_ids, *, user, project_id)`；`load_documents` 允许显式点名旧版本（restrict_to 语义）。

## 五、消费方改造

| 消费方 | 改法 | 用户上下文 |
|--------|------|-----------|
| `ReferenceDocService.load_from_knowledge_base` | 有关键词 → `semantic_search(scope=knowledge_doc, category=…)`；无关键词 → 空查询列表模式；删 ILIKE 兜底；异常 → `[]` + WARNING；格式 `【知识库 - {document_name}】\n{content[:2000]}` 不变 | 无（签名钉死）⇒ project 无用户判定 |
| `ReferenceDocService.search_knowledge_base`（新） | 同上，返回 `list[dict]`，供需要来源名的调用方 | 可选 `user` |
| `a17_llm_service._retrieve_rag_context` | 标题取 `document_name` | 无 |
| `wp_guidance_chat_stream` | `semantic_search(..., user=user)`；引用 `document_name` / `source_id` | 有 |
| `ContextBuilder._search_related_knowledge` | 传 user；`source_name ← document_name`；`project_id is None` → `search_global_knowledge`；extra_scopes → 同一检索加 `restrict_to=folder_ids`；`_filter_hits_by_permission` 补 `d.is_deleted/f.is_deleted` | 有 |
| `NoteKnowledgeEnricher.retrieve` | doc_filter（可解析为 UUID 者）→ `restrict_to`；后置过滤：`source_id ∈ F ∨ folder_ancestor_ids ∩ F ≠ ∅` | 有 |
| `a171_ai_generate` | 指定文档 → `load_documents(ids, user, project_id)`；自动 → `search_knowledge_base` 取来源名；上限 5 篇、每篇 4000 字不变 | 有 |
| `GtA173ConsultationRecord.vue` | `action` → `/api/knowledge-library/projects/{pid}/upload`、`name="files"`；成功回调读 `data.files[0]` | — |
| `ai_chat/note_service.py` | `ensure_project_folder(..., slot="ai_notes")`；`KnowledgeDocumentService.create_document`；删错参 `incremental_update`；删 `db.rollback()`；`jump_route` 改真实路由 | 有 |
| `ai_chat/mention_service.py` | 两处 `jump_route` 改 `/knowledge?doc_id=` / `/knowledge?folder_id=` | — |
| `indexing_pipeline` | 去 `joinedload`；单独取文件夹算生效级别；private → `index_status=skipped`（原因写入 `index_error`） | — |
| `index_source.KnowledgeDocSource` | 用 `can_retrieve(project, None, P, …)`，删 `_is_accessible` | — |
| 旧 `DocAiChatPanel.vue` | 删组件与 3 个专属 spec；`DocAiChatPanel.host.spec.ts` 中「宿主页面模板形态」判据迁到 `PlatformAiChatPanel` 侧保留 | — |

## 六、项目知识文件夹（迁移）

- 迁移号：撰写时现扫最高为 **V169**（并行会话的 `formula_push_engine`），本 spec 预定 **V170 / R170**；🔴 **实施前必须重扫**，撞号会被 `scan_migrations` 同号检测直接拒启动。
- `V170__knowledge_folder_system_key.sql`：`ALTER TABLE knowledge_folders ADD COLUMN IF NOT EXISTS system_key VARCHAR(120)`；`CREATE UNIQUE INDEX IF NOT EXISTS uq_knowledge_folders_system_key ON knowledge_folders (system_key) WHERE system_key IS NOT NULL AND is_deleted = false`。R170 反向删除。
- ORM：`KnowledgeFolder.system_key: Mapped[str | None]`。
- `ensure_project_folder(db, project_id, slot)`：
  - 键：根 `project:{pid}`，子槽 `project:{pid}:{slot}`；`slot ∈ {ai_notes, consultation}`（名称「AI 对话笔记」「A17-3 咨询附件」），根名 `{项目名}（项目资料）`。
  - 访问级别均为 `project_group`、`project_ids=[pid]`；`created_by = NULL`（系统所有，仅管理员可改名/删除）。
  - 先查未删除同键；无则在 SAVEPOINT 内插入并 flush；`IntegrityError` → SAVEPOINT 回滚后重查（**不**回滚调用方事务）。
  - 用户删除系统文件夹（管理员）后，下次 ensure 会新建（部分唯一索引只约束未删除行）。

## 七、端点授权矩阵（`routers/knowledge_folders.py`）

| 端点 | 读判定 | 写判定 | 失败 |
|------|--------|--------|------|
| `GET /tree` | 既有 policy | — | 追加 `can_manage/can_create`；`doc_count` 只计可读 |
| `GET /folders/{id}/documents` | 既有 | — | 追加每行 `can_manage` |
| `POST /folders` | 父文件夹创建权 | readonly → 403 | 422 入参 |
| `POST /folders/{id}/documents`、`/upload` | 创建权 | readonly → 403 | 404 同构 |
| `POST /projects/{pid}/upload`（新） | 项目 `edit` 权限 | readonly → 403 | 403/404 |
| `POST /init-presets` | — | readonly → 403 | — |
| `GET /search` | browse 词法检索 | — | — |
| `GET /documents/{id}/preview`、`/download` | `can_read_document` | — | 404 同构；preview 追加 `folder_id` |
| `DELETE /folders/{id}`、`PUT /folders/{id}/rename` | 可读 | `can_manage(folder)` | 404 / 403 |
| `DELETE /documents/{id}` | 可读 | `can_manage(doc)` | 404 / 403 |
| `PUT /documents/{id}`（新，重命名） | 可读 | 链内全部 `can_manage` | 404 / 403 / 409 同名 / 422 |
| `PUT /documents/{id}/move` | 可读 + 目标文件夹创建权 | 链内全部 `can_manage` | 404 / 403 / 409 |

404 一律 `ExternalNotFound`（与 dsh Req 2.5 同构）；403 用中文 `detail`（资源对用户可见，不构成枚举）。

## 八、前端

- `KnowledgeBase.vue`：
  - 深链：挂载与 `route.query` 变化时处理 `folder_id` / `doc_id`（仅有 `doc_id` 时先调预览取 `folder_id`）→ 选中树节点、加载文档、打开预览；找不到给中文提示「文件夹不存在或无权访问」。
  - 按钮门控：文件夹「重命名/删除」看 `node.can_manage`；「上传到此文件夹/新建子文件夹」看 `node.can_create`；文档「重命名/删除/移动」看 `row.can_manage`；系统角色 `readonly` 隐藏全部写按钮；批量删除对 403 单独计数提示。
- `services/apiPaths/system.ts`：新增 `projectUpload(pid)`；`documentDetail` 已存在（PUT 重命名 / DELETE 删除共用）。
- `GtA173ConsultationRecord.vue`：见第五节。
- 删除 `components/DocAiChatPanel.vue` 与 `components.d.ts` 中对应条目。

## 九、测试策略

### 9.1 本 spec 前的红基线（2026-09-29 现跑，17 个相关测试文件 280 例：272 过 / 8 红）

| # | 用例 | 根因 | 本 spec 处置 |
|---|------|------|-------------|
| 1 | `test_knowledge_index_service::test_semantic_search_returns_results` | mock 的 pgvector 分支 `result.all()` 返回空 MagicMock | 夹具补 SAVEPOINT 与 pgvector 探测后按内存路径断言 |
| 2–3 | `test_retrieval_phase2_pbt::TestR1RecallFallback` ×2 | `.venv` 无 jieba | R1.4 分词降级后应转绿（环境同步另在平台 spec 处理） |
| 4 | `…::TestR2PermissionIsolation::test_public_docs_visible_to_any_user` | 同 #1 mock 形态 | 改为基于 `visible_documents` 的判定断言 |
| 5–6 | `…::TestAIChatServiceRegression` ×2 | 同 #1；且 #6 钉的是「无用户不过滤」旧契约 | #5 保留语义；#6 按 3.8 契约反转改写（断言 private 不返回） |
| 7–8 | `test_rag_consumer_integration` ×2 | patch 目标 `reference_doc_service.KnowledgeIndexService` 不存在（函数内延迟 import）；且期望 dict 而生产契约是 `list[str]` | 改指向新结构化 API `search_knowledge_base` |

### 9.2 真库 scratch schema（新 `tests/_kb_pg_scratch.py` 共享夹具）

沿用 `test_knowledge_delete_hook_isolation_pg.py` 的做法：ORM 派生表（去外键、去 `embedding_vec`）、`search_path` 只含自己、结束 `DROP SCHEMA CASCADE`（`finally` 内，失败计入 harness_errors 让守卫红）；非 PostgreSQL 直接失败不 skip。需要的表：`knowledge_folders`、`knowledge_documents`、`knowledge_index`、`project_users`。

### 9.3 Property

| P | 内容 | 层级 |
|---|------|------|
| P1 | embedding 失败 + 无 `embedding_vec` 列时 `semantic_search` 后会话可用；旧实现反向对照会话 aborted | 真库 |
| P2 | `can_retrieve` 与独立参考模型在（模式 × 主体 × 级别 × 继承 × 成员 × 当前项目）全组合上逐格等价 | 纯函数 PBT |
| P3 | 词法结果 ⊆ 检索可见集合；private 他人文档、他项目组文档、已删除、已删文件夹下文档一律不出现 | 真库 |
| P4 | 未给 restrict_to 时不返回被取代版本；点名旧版本时可返回 | 真库 |
| P5 | restrict_to 为并集且在 top_k 前生效（目标文档排名靠后仍能返回） | 真库 |
| P6 | 查询 `%` / `_` 不匹配全部文档 | 真库 |
| P7 | 片段 ≤500 字且（正文命中时）含至少一个检索词；分数 ∈ [0,1] | PBT |
| P8 | 同输入同输出（排序稳定） | 真库 |
| P9 | `semantic_search` 的 knowledge_doc 结果（含注入的向量命中）全部满足 3.2/3.3 | 真库 |
| P10 | `user=None` 永不返回 private | 真库 |
| P11 | 管理权判定与参考模型等价；端点 404/403 分流正确 | PBT + 端点 |
| P12 | 重命名/移动作用于整条版本链；同名冲突 409 | 真库端点 |
| P13 | `ensure_project_folder` 两次调用同一文件夹；并发冲突不回滚调用方已 flush 的写 | 真库 |
| P14 | `semantic_search_strict` 在 embedding 不可用时仍抛 `EmbeddingUnavailableError`（不走词法） | 单元 |

### 9.4 变异清单（每条须让对应测试变红，结果记入 tasks 证据）

M1 去掉 `can_retrieve` 调用（全放行）→ P3/P9 红 · M2 去掉 SAVEPOINT → P1 红 · M3 去掉最新版本 `NOT EXISTS` → P4 红 · M4 去掉 LIKE 转义 → P6 红 · M5 restrict_to 改为 top_k 后过滤 → P5 红 · M6 `user=None` 恢复不过滤 → P10 红 · M7 管理权去掉所有者判断 → P11 红 · M8 重命名只改单行 → P12 红。

变异脚本用一次性 `backend/scripts/diagnose/_kb_mutation_check.py`（`_` 前缀，用完即删），逐条改源码 → 跑目标测试 → 还原并校验 sha256 一致。

### 9.5 真栈（Playwright）

登录 admin → 知识库新建公开文件夹 → 上传含独特词的 txt → 页面搜索命中且显示片段 → 附注编辑器打开 AI 填充「仅参照」模式、参照范围勾选该文档 → 引用列表显示文档名与 `/文件夹` 路径 → 普通用户视角（readonly 或非所有者）看不到删除/重命名按钮 → A17-3 上传附件成功 → 清理数据。

## 十、契约变化清单（均为有意变更）

| # | 旧 | 新 | 理由 |
|---|----|----|------|
| C1 | `semantic_search(user=None)` 对 knowledge_doc 不过滤 | 按 3.3（public + 当前项目组；private 永不） | 私有文档经全局哨兵索引泄露；旧消费方已删 |
| C2 | project_group 文档对任意用户可见（`_user_can_access_doc` 恒真） | 须项目成员且当前项目在其项目组内 | 跨客户注入 |
| C3 | `ReferenceDocService` 分类 = 直属文件夹精确过滤（仅兜底生效） | 分类 = 子树加分（两条路径一致） | 旧行为使「把准则放进自建子文件夹」恒检索不到 |
| C4 | `ReferenceDocService` 语义空/异常 → 无权限 ILIKE | → 词法检索已内含；异常返回 `[]` | 越权读取 |
| C5 | 附注 doc_filter 在 top_k 后过滤、按文件夹名 | 下推 restrict_to；按 ID / 祖先链 | 选中文档因截断丢失；同名文件夹歧义 |
| C6 | 删除/改名/移动任何登录用户可执行 | 所有者或管理员；readonly 禁写 | IDOR |
| C7 | 知识库搜索不过滤 | browse 模式判定 | 枚举他人私有文档名 |
| C8 | 文档改名/移动只改单行 | 作用于整条版本链 | 单行改名会把旧版本留在原链、下次同名上传挂错链 |
| C9 | 检索会召回同一文档的全部历史版本 | 默认只召回最新版本 | 同一内容重复注入、引用旧版 |

## 十一、范围外（显式登记）

- **方案 B 前置清单**（用户暂缓；启用前必须先做）：① `knowledge_index (project_id, source_id, chunk_index)` 唯一索引（`ON CONFLICT` 依赖）② 全局哨兵项目与外键的处理（建哨兵行会污染项目列表 ⇒ 更倾向改为 `project_id NULL` 表示全局）③ 安装 pgvector 或确认内存向量规模可接受 ④ embedding 服务恢复 ⑤ 回填 `build_index`。
- `note_ai.py` 两个同为 `POST /{project_id}/ai/complete` 的路由（后者被遮蔽）与写死的 `2025` 年度：属附注 AI 域，不属知识库，登记给后续 spec。
- `b14_ai_generate` 端点仅登录校验：已计入平台 `project_endpoint_authorization_baseline` 棘轮，不在本 spec 扩面。
- 知识库回收站：删除仍为软删 + 二次确认，本 spec 不新增回收站视图。

## 十二、风险

| 风险 | 缓解 |
|------|------|
| ILIKE 顺序扫描在文档量增长后变慢 | 候选截断 WARNING + p95 切换点（§3.2）；正文只读 ≤3·top_k 条 |
| 词法召回不理解同义表述 | 方案 B 恢复后自动与向量合并（4.1），无需改消费方 |
| 契约反转打红既有 mock 测试 | 逐条归因（§9.1），改写须保留原测试意图并补真库判据，禁降级成恒绿 |
| `evidence_governance` 冻结 `KnowledgeIndexService` 公开方法与 fork 标记 | 只增不减公开方法；新模块不使用 `_vector_search/_bm25_fallback/_chunk_text` 等 fork 标记名；跑其契约测试 |
| 并行会话同时占用迁移号 | 实施前重扫 `backend/migrations`；R 文件同批提交 |
