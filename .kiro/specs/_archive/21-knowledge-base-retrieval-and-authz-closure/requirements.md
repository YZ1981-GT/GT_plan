# 知识库检索与授权收口（方案 A：文档正文词法检索）— 需求

> 2026-09-29 新建。承接同日「新建文件夹后上传不了」修复（401 单一 token 入口 / 唯一落盘名 / 删除钩子 SAVEPOINT / V168 枚举），
> 本 spec 解决「上传之后，下游模块依然用不上知识库」。用户裁决：**方案 A**（下游直接对 `knowledge_documents.content_text`
> 做带权限的词法检索，`knowledge_index` 降为可选加速层）；方案 B（修索引写路径 + 恢复 embedding）暂缓。

## 一、现状实证（2026-09-29 真库 + 现读代码）

| # | 事实 | 后果 |
|---|------|------|
| E1 | `knowledge_index` **0 行**；embedding 服务（8101）返回 502 | 向量检索不可用 |
| E2 | 真库无 `knowledge_index.embedding_vec` 列（pgvector 未装，V119 跳过） | ORM `select(KnowledgeIndex)` 必抛 `UndefinedColumnError` |
| E3 | `_bm25_fallback` / `_ilike_fallback` / 内存向量兜底都 `select(KnowledgeIndex)` 且无 SAVEPOINT | 兜底失败 → **调用方会话 aborted**，其后语句全挂（ContextBuilder `_get_project_summary`、指导对话建会话） |
| E4 | `ON CONFLICT (project_id, source_id, chunk_index)` 无对应唯一索引；全局哨兵项目不在 `projects` 而 `knowledge_index.project_id` 有外键 | 索引写路径在当前环境**不可能**写入一行（方案 B 前置清单） |
| E5 | `_zh_tokenize` 顶层 `import jieba`，`.venv` 未装 | BM25 兜底 `ModuleNotFoundError` |
| E6 | `_filter_by_permission` 从 `KnowledgeIndex` 起联表；`_user_can_access_doc` 对 project_group **恒真**；`user=None` 时不过滤 | 越项目组可见；私有文档经全局哨兵索引可被任何调用方检索 |
| E7 | `_enrich_results` 的 `folder_path` 只是文件夹名；不滤已删 | 引用路径失真 |
| E8 | `indexing_pipeline` 用 `joinedload(KnowledgeDocument.folder)`，模型无此关系 | 后台流水线每次 `AttributeError` |
| E9 | 同名重传建版本链，旧版本 `is_deleted=false` 仍在 | 检索会同时召回 v1/v2 |

### 消费方断点（逐一现读）

| 消费方 | 断点 |
|--------|------|
| `ReferenceDocService.load_from_knowledge_base`（附注 AI / B1-4 / A17-1） | ILIKE 兜底**无权限过滤**（可读他人私有文档）；分类只精确匹配直属文件夹；主路径忽略分类 |
| `a17_llm_service._retrieve_rag_context` | 读 `title`/`file_name`，结果键是 `document_name` |
| `wp_guidance_chat_stream`（底稿指导对话） | 读 `source_name`/`id`；不传 user；E3 使后续建会话失败 |
| `ContextBuilder`（文档级 AI 对话，平台核心功能） | 丢弃 `document_name`；权限过滤不滤已删；全局模式不检索；extra_scopes 取「每文件夹前 5 篇、固定 0.5 分」与查询无关 |
| `NoteKnowledgeEnricher`（附注 RAG） | doc_filter 在 top_k 截断**之后**后置过滤；按文件夹名字符串匹配 |
| A17-1 `a171_ai_generate` | 指定文档读遗留表 `ai_knowledge_base` 的 `title/content`（**列不存在**，恒静默为空）；来源名丢失 |
| A17-3 `GtA173ConsultationRecord.vue` | 上传到不存在的 `/api/knowledge-base/projects/{pid}/documents`，恒失败 |
| AI 笔记转存 `ai_chat/note_service.py` | `KnowledgeFolder.project_id` 不存在 → 恒 `internal_error`；`create_document` 调错服务；`incremental_update` 错参；`db.rollback()` 回滚收据 |
| 跳转路由（笔记转存 / @提及） | `/knowledge/docs/{id}`、`/knowledge/folders/{id}` 前端无此路由 |
| 旧 `DocAiChatPanel.vue` | 仅测试引用；调用不存在的 `/api/knowledge/folders` |

### 授权断点（`routers/knowledge_folders.py`）

删除文件夹 / 删除文档 / 重命名文件夹 / 移动文档 / 预览 / 下载 / 搜索只校验登录；搜索无权限过滤（可枚举他人私有文档名）；
前端重命名文档调 `PUT /documents/{id}`，后端无此路由（405）；目录树 `doc_count` 统计含不可读文档。

## 二、术语

- **可读**：`KnowledgeAccessPolicy.can_read_document` 为真（access_level + 项目成员 + 创建者；角色不参与）。
- **生效三元组**：文档 `access_level` 非空取文档的 (级别, project_ids, 创建者)，否则**完整继承**所在文件夹三元组。
- **检索模式**：`browse`（知识库页面搜索）/ `project`（项目内 RAG）/ `global`（无项目的受限全局知识 RAG）。
- **检索可见**：在「可读」之上按检索模式再与项目范围求交（Requirement 3）。
- **最新版本**：版本链（`previous_version_id`）上没有任何**未删除**后继指向它的那一版。
- **restrict_to**：文档 ID 与文件夹 ID 的并集；文件夹含全部子孙文件夹。

## 三、需求

### Requirement 1：检索不得污染调用方会话

**User Story：** 作为调用 RAG 的服务（附注填充、文档对话、底稿指导对话），我要求知识检索无论成功失败都不破坏我的数据库会话。

1.1 `KnowledgeIndexService` 内每条读取 `knowledge_index` 的语句 SHALL 在 SAVEPOINT 内执行；失败只回滚该 SAVEPOINT。
1.2 除 pgvector 余弦检索语句外，读取 `knowledge_index` 的 ORM 查询 SHALL NOT 在 SELECT 中包含 `embedding_vec`。
1.3 WHEN `embedding_vec` 列不存在 THEN 向量检索 SHALL 降级为 `embedding_vector` 文本列的内存计算，不向调用方抛出。
1.4 `_zh_tokenize` SHALL 在 jieba 不可用时降级为「CJK 二元组 + ASCII 词」切分，不抛 `ImportError`。
1.5 CRUD 索引钩子（创建/上传后建索引）SHALL 使用独立会话；钩子失败不影响请求会话。
1.6 真库判据：在无 `embedding_vec` 列的真实 PostgreSQL 上、embedding 不可用时调用 `semantic_search` 后，同一会话再执行 SELECT SHALL 成功；并 SHALL 有反向对照证明旧实现在同一夹具下使会话 aborted。

### Requirement 2：文档正文词法检索

**User Story：** 作为审计助理，我上传到知识库的文档应立即能被各模块 AI 功能引用，而不依赖当前环境跑不起来的向量索引。

2.1 系统 SHALL 提供文档词法检索组件，直接在 `knowledge_documents`（name / content_text / tags）上检索，不读 `knowledge_index`。
2.2 检索词 SHALL 由查询分词得到（去停用词、去单字——整句仅一个字时保留、去重、最多 12 个，超出时优先保留长词）；LIKE 通配符 `%` `_` `\` SHALL 被转义。
2.3 候选 SHALL 排除已软删文档与所在文件夹已软删的文档；未给 restrict_to 时 SHALL 只保留每条版本链的最新版本。
2.4 每条命中 SHALL 返回：文档 ID、文件夹 ID、文档名、文件类型、大小、版本号、创建者、创建/更新时间、分数 ∈ [0,1]、≤500 字片段（命中最密集窗口）、`chunk_index = 片段起点 // 500`、命中词列表。
2.5 排序 SHALL 以检索词覆盖率为主、词频为辅、文档名命中加分；同分按更新时间倒序再按 ID；同输入同输出。
2.6 WHEN 查询为空（去空白后无字符）THEN 组件 SHALL 按更新时间倒序列出范围内检索可见文档（列表模式，分数只含分类加分，片段取正文开头）；WHEN 查询非空但分词后无有效检索词（纯标点 / 通配符 / 停用词）THEN SHALL 返回空，不得退化为列表模式。
2.7 restrict_to SHALL 在截断 top_k **之前**生效。
2.8 分类（预设 category）SHALL 仅作排序加分（该分类根文件夹子树内文档加分），SHALL NOT 作硬过滤；未知分类不加分。
2.9 权限判定 SHALL 先于正文读取：先取判权三元组 → 判定 → 只对通过者读 `content_text`。
2.10 候选截断上限命中时 SHALL 记 WARNING（规模切换点信号），不得静默。

### Requirement 3：检索可见性单一判定面

**User Story：** 作为合伙人，我要求 AI 引用的知识只来自当前用户有权看、且属于当前项目范围的文档，不能把 B 客户项目组资料注入 A 客户项目。

3.1 检索可见性 SHALL 只在 `knowledge_access_policy` 模块以纯函数实现；词法检索、向量结果过滤、索引源、知识库页面搜索 SHALL 共用。
3.2 `project` 模式、有用户：可读 ∧（生效级别 ≠ project_group ∨ 当前项目 ∈ 生效 project_ids）。
3.3 `project` 模式、无用户（后台/系统调用）：生效级别 = public ∨（project_group ∧ 当前项目 ∈ 生效 project_ids）；private 永不可见。
3.4 `global` 模式（必须有用户）：可读 ∧ 生效级别 ≠ project_group。
3.5 `browse` 模式（必须有用户）：可读。
3.6 未知 access_level SHALL fail-closed（按 private 处理）；模式与主体组合非法（如 browse 无用户）SHALL 抛 `ValueError`（编程错误，不静默放行）。
3.7 `semantic_search` / `semantic_search_strict` 返回的每条 knowledge_doc 命中（**含向量命中**）SHALL 满足 3.2/3.3，且剔除已删除、所在文件夹已删除、已被取代的版本（restrict_to 显式点名的旧版本除外）。
3.8 🔁 **契约反转**：`user=None` 时 knowledge_doc 结果不再「不过滤」，改按 3.3。旧契约的唯一消费方 `ai_chat_service` 已不存在；旧行为会把索引到全局哨兵的私有文档暴露给任何调用方。
3.9 `KnowledgeIndexService._user_can_access_doc`（project_group 恒真）与 `KnowledgeDocSource._is_accessible` SHALL 删除，调用方改用 3.1 的判定面。

### Requirement 4：semantic_search 集成

4.1 scope ∈ {knowledge_doc, all} 时 SHALL 始终执行文档词法检索，并与可用的向量命中合并：同 (source_id, chunk_index) 去重保留高分，按分数排序截断 top_k。
4.2 向量不可用时：knowledge_doc 部分只用词法检索（不再从索引的 knowledge_doc 分块兜底）；project_data 部分沿用 BM25/ILIKE（SAVEPOINT 内）。
4.3 空查询 SHALL 跳过向量检索，只走 2.6 列表模式（knowledge_doc 部分）。
4.4 每条结果 SHALL 带 `retrieval` ∈ {vector, lexical, bm25, ilike}。
4.5 knowledge_doc 结果 SHALL 附 `document_name`、`folder_id`、`folder_path`（`/根/…/当前`）、`folder_ancestor_ids`（根→当前）。
4.6 `semantic_search` 新增仅关键字参数 `restrict_to`、`category`，默认值保证现有调用方零改动。
4.7 SHALL 提供 `search_global_knowledge(query, *, user, top_k)`（global 模式、仅词法）与 `load_documents(doc_ids, *, user, project_id)`（按 ID 读检索可见文档正文，project 模式）。
4.8 `semantic_search_strict` SHALL 保持只走向量（dsh Property 16），不接入词法检索。

### Requirement 5：下游消费方接线

5.1 `ReferenceDocService`：删除无权限过滤的 ILIKE 兜底；有关键词走 `semantic_search`（带 category 加分）；无关键词走列表模式；异常返回 `[]` 并记 WARNING；`load_from_knowledge_base` 签名不变；新增结构化 `search_knowledge_base` 返回 dict（`document_name/content/score/source_id`）。
5.2 A17 LLM：片段标题取 `document_name`。
5.3 底稿指导对话：传入 user；引用取 `document_name` / `source_id`。
5.4 `ContextBuilder`：`semantic_search` 传 user；`SearchHit.source_name` 取 `document_name`；global 宿主走 `search_global_knowledge`；extra_scopes 改为 restrict_to 相关性检索；权限过滤补已删除过滤。
5.5 附注 RAG：doc_filter 下推为 restrict_to；后置过滤按 `source_id` / `folder_ancestor_ids`，不再按文件夹名字符串。
5.6 A17-1 AI 生成：指定文档经 `load_documents` 读取（当前用户 + 当前项目范围）；自动检索来源名取 `document_name`。
5.7 A17-3 相关文件上传：新增 `POST /api/knowledge-library/projects/{project_id}/upload`（项目 edit 权限），落到项目知识文件夹；前端改用该端点，从响应 `files[0]` 取文档 ID。
5.8 项目知识文件夹：`knowledge_folders.system_key` + 部分唯一索引；`ensure_project_folder(project_id, slot)` 幂等、系统所有（`created_by` 为空，仅管理员可管理）、并发冲突重查且不回滚调用方事务；AI 笔记转存与 A17-3 共用。
5.9 AI 笔记转存：修复 5 处断点（见一、消费方表）；索引交给词法检索（不再调错参的 `incremental_update`）。
5.10 跳转路由：`/knowledge?folder_id=…&doc_id=…`；`KnowledgeBase.vue` 支持该查询参数（选中文件夹、打开预览）；预览接口返回 `folder_id`。
5.11 索引流水线：去掉不存在的关系；私有文档不入全局索引（`index_status=skipped`）；失败如实记录 `index_status/index_error`，不阻断。
5.12 删除已无生产引用的旧 `DocAiChatPanel.vue` 及其专属测试；宿主页面形态守卫迁移保留。

### Requirement 6：知识库资源级授权

**User Story：** 作为质控合伙人，我要求知识库的删除/改名/移动只能由资料所有者或管理员执行，看不到的资料连存在性都不应暴露。

6.1 预览 / 下载 SHALL 要求可读；否则 404 同构（`资源不存在或不可访问`）。
6.2 删除/重命名文件夹、删除/重命名/移动文档 SHALL 要求：可读 ∧ 系统角色 ≠ readonly ∧（创建者本人 ∨ 系统管理员）；不可读 → 404；可读但无管理权 → 403 中文原因。
6.3 文档重命名/移动 SHALL 作用于整条版本链（同文件夹同名的未删除版本）；链内任一版本无管理权 → 403；目标位置已有同名文档 → 409；移动还 SHALL 要求对目标文件夹有创建权。
6.4 新建文件夹 / 上传 / 新建文档 / 初始化预设 SHALL 拒绝系统角色 readonly（403）。
6.5 新增 `PUT /api/knowledge-library/documents/{id}`（重命名，名称非空且 ≤500 字）。
6.6 知识库页面搜索 SHALL 走 browse 模式词法检索；`context` 参数保留为排序加分；响应形状向后兼容，追加 `snippet` / `score` / `can_manage`。
6.7 目录树与文档列表 SHALL 返回 `can_manage` / `can_create`；文件夹 `doc_count` SHALL 只统计当前用户可读的文档。
6.8 前端 SHALL 按 `can_manage` / `can_create` 与当前用户角色隐藏或禁用重命名、删除、移动、上传、新建按钮。

### Requirement 7：验证

7.1 真实 PostgreSQL scratch schema 测试覆盖 R1–R4 关键路径，每条带反向对照或变异证明。
7.2 PBT（hypothesis `max_examples=5`）：可见性判定与参考模型逐格等价；词法结果 ⊆ 检索可见集合；restrict_to 并集语义；片段 ≤500。
7.3 变异：逐条移除权限过滤 / SAVEPOINT / 最新版本过滤 / LIKE 转义 / restrict_to 下推，对应测试 SHALL 变红。
7.4 Playwright 真栈：上传 → 知识库搜索命中 → 附注「仅参照」模式引用该文档（document_name / folder_path 可见）→ 按钮按权限显示；A17-3 上传成功。
7.5 相关既有测试集全绿；本 spec 前已红的用例逐条归因（本轮基线：8 条，见 design §九）。
