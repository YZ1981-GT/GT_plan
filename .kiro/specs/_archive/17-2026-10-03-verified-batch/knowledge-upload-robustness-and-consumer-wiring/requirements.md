# 知识库上传健壮性与下游消费方接线 — 需求

> 2026-09-30 新建。承接 `knowledge-base-retrieval-and-authz-closure`（其 design §十一 把 `note_ai` 双路由登记给后续 spec）。
> 缘起：用户报告「新建文件夹后上传不了文档，走不下去；后面很多模块要调用知识库文档」。

## 一、现状实证（2026-09-30：现跑前后端 + Playwright + 真库）

| # | 事实 | 后果 |
|---|------|------|
| U1 | 公开文件夹「新建 → 自动选中 → 上传 txt/docx/xlsx」走通（200，正文 58 / 11442 / 41836 字），页面搜索即时命中 | 主链路在**工作区**代码下可用 |
| U2 | 用户的「1」文件夹建于 09-28（401 期间），存储目录不存在、0 文档 | 用户所见源于原生上传自读 localStorage；本 spec 已将知识库上传切到 `utils/authToken`（sessionStorage / auth store）并随本次提交入库 |
| U3 | UTF-16（记事本「Unicode」另存）与含 NUL 的 txt：`decode('utf-8', errors='ignore')` 保留 `\x00` → PG `CharacterNotInRepertoireError` | 整个请求 500 |
| U4 | 文件名「扩展名」超 20 字（`审计报告.final-reviewed-by-partner-v2`）→ `file_type VARCHAR(20)` 溢出 | 整个请求 500 |
| U5 | 逐文件 `try/except` 只吞 Python 异常；flush 失败后会话已 aborted，后续文件 `PendingRollbackError`，末尾 commit 抛出 | 单文件问题放大为**整批丢失**；已落盘文件成孤儿（实测 3 个） |
| U6 | GBK 编码 txt（中文 Windows 常见）按 UTF-8 忽略错误解码 → 正文成 12 字乱码 | 上传「成功」但 AI 检索不到，静默损坏 |
| U7 | 扫描件 PDF（`MINERU_ENABLED=False`）正文为空，界面无提示 | 用户以为已入库，AI 永远检索不到 |
| U8 | 前端上传失败只提示「N 失败」，原因只在浏览器控制台 | 用户无从排查 |
| U9 | 拖拽文件夹：`readEntries` 只调一次（Chromium 每次最多 100 条）；`entry.file()` 得到的 File 无 `webkitRelativePath` | 超 100 个文件静默丢失；子文件夹结构被压平 |

### 消费方（真库逐个调用；`knowledge_index` 0 行、embedding 8101 不可达）

| 入口 | 结果 |
|------|------|
| `semantic_search`（有/无用户）、`search_global_knowledge`、`ReferenceDocService`、`NoteKnowledgeEnricher`、A17 RAG、@引用 | ✅ 均召回刚上传的文档（文档词法层） |
| DSH Agent `kb_search`（`semantic_search_strict`） | ❌ `EmbeddingUnavailableError`（dsh Property 16 规定只走向量；本 spec 不改，见 §三 D1） |
| 附注 / 审计报告编辑器「📚 知识库」选择器（`useKnowledge.search`） | ❌ 调 `/api/knowledge/search` → 404，恒「未找到匹配的文档」 |
| `useKnowledge.getDocContent` | ❌ `/api/knowledge/{cat}/{id}` → 404 |
| 附注 AI 续写 / 改写携带的 `knowledge_context` | ❌ 后端请求模型无此字段，被静默丢弃 |
| 附注 AI 续写 `POST /api/disclosure-notes/{pid}/ai/complete` | ❌ 同路径注册两次，query 参数版遮蔽 body 版 → 前端 JSON 请求恒 422 |
| 审计报告编辑器「已加载 N 篇参考文档」 | ❌ 无任何 AI 调用消费该上下文（空壳） |

## 二、需求

### Requirement 1：单个文件的问题不得拖垮整批上传

**User Story：** 作为审计助理，一次上传多份资料时，其中一份格式特殊不应让其它资料一起丢失。

1.1 每个文件的写库 SHALL 在独立 SAVEPOINT 内执行；一个文件失败只回滚它自己，同批其它文件照常提交。
1.2 上传端点对「单文件失败」SHALL 返回 200 与结果明细，不得 500；响应 SHALL 保留既有字段（`uploaded` / `files` / `folder_id`）并追加 `failed: [{filename, reason}]`，`reason` 为中文可读原因，不含 SQL / 堆栈。
1.3 写库失败的文件 SHALL 删除已落盘的物理文件（不留孤儿）。
1.4 真库判据：同一请求含 [正常, file_type 超长, 正常] 三个文件 → 两个正常文件入库、`failed` 恰 1 条；反向对照：去掉 SAVEPOINT 的旧实现在同一夹具下三个文件全部丢失。

### Requirement 2：写入知识库的文本必须能被 PostgreSQL 存储

2.1 `knowledge_documents` 的 `name` / `content_text` / `content_summary` 在 ORM 层 SHALL 剔除 NUL（`\x00`）——覆盖所有写入方（上传、手工建文档、AI 笔记、版本回滚），而非只修上传入口。
2.2 `file_type` SHALL 规范化为「小写扩展名」；超过列宽（20）或含非法字符时置空，不得让写库失败。
2.3 真库判据：含 NUL 的正文与名称可写入并读回（NUL 已剔除）；反向对照：同一文本绕过 ORM 清洗直接写入必失败。

### Requirement 3：纯文本按真实编码解码

3.1 `.txt` / `.md` / `.csv` SHALL 依次识别：BOM（UTF-8 / UTF-16 LE/BE）→ 无 BOM 时启发式识别 UTF-16（NUL 字节分布）→ 严格 UTF-8 → GB18030（GBK 超集）→ 最后才 UTF-8 替换解码。
3.2 判据：GBK、UTF-16（带 BOM）、UTF-8-BOM 三种样本解码后与原文逐字相等且不含 BOM 字符。

### Requirement 4：上传结果如实告知用户

4.1 上传结果 SHALL 逐文件给出失败原因（界面可见，不只在控制台）。
4.2 正文为空（`text_extracted=false`）的文件 SHALL 在界面提示「未提取到正文，AI 无法引用」，并区分扫描件（需 OCR）。
4.3 A17-3「相关文件」上传：部分失败 / 全部失败 SHALL 显示后端给出的原因。

### Requirement 5：拖拽文件夹不丢文件、不丢结构

5.1 拖拽目录 SHALL 反复调用 `readEntries` 直到返回空（Chromium 每次最多 100 条）。
5.2 拖拽得到的文件 SHALL 保留相对路径（来自 `FileSystemEntry.fullPath`），与「选择文件夹」同样按子目录建文件夹。
5.3 判据：vitest 用 250 个条目的目录替身证明全部取回；嵌套路径与 `webkitRelativePath` 同形。

### Requirement 6：编辑器「📚 知识库」选择器接到真实检索

**User Story：** 作为审计助理，我在附注编辑器里选中知识库文档后，AI 续写 / 改写应真的参考它们。

6.1 `useKnowledge.search` SHALL 调 `GET /api/knowledge-library/search`（带权限的词法检索），结果含 `snippet` / `folder_name`。
6.2 附注 AI 续写 / 改写 SHALL 传所选文档 ID（`knowledge_doc_ids`），**不传前端拼好的正文**；后端经 `KnowledgeIndexService.load_documents(ids, user, project_id)` 逐篇过判定面后注入 LLM（客户端传的 ID 不可信；不可见者静默跳过）。
6.3 `POST /{project_id}/ai/complete` SHALL 只保留一个实现（JSON body 版，前端与 e2e 的现行调用形态）；删除被遮蔽的 query 版。
6.4 附注 AI 续写 / 改写端点 SHALL 挂 `require_project_access("readonly")`（与同业务域 `ai-fill` 一致；知识文档判定需要真实用户）。
6.5 响应 SHALL 追加 `knowledge_count`（实际注入的知识文档篇数），前端据此提示「已参考 N 篇」；所选文档全部不可见时如实提示。
6.6 审计报告编辑器没有任何 AI 生成动作消费参考文档：「📚 知识库」按钮 SHALL 标为开发中（点击给出说明），不再展示「已加载 N 篇参考文档」这一无效果的状态。

### Requirement 7：同类缺陷不再复发

7.1 全应用 (method, path) 重复注册 SHALL 有棘轮守卫：现存 10 组冻结为基线，只许减少；本 spec 修掉的 `ai/complete` 不得回归。
7.2 前端 SHALL 不再引用后端不存在的 `/api/knowledge/search`、`/api/knowledge/{cat}/{id}`、`/api/knowledge/{cat}/upload`（守卫：`apiPaths.knowledge` 中每个路径都能在后端路由表找到）。

### Requirement 8：验证

8.1 R1–R3 真库 scratch schema 测试（SQLite 不校验 NUL 与 VARCHAR 长度，内存库测不出 U3/U4）。
8.2 关键守卫逐条变异打红、还原 sha256 一致。
8.3 Playwright 真栈复测：U3/U4 样本重传、知识库选择器搜索命中、附注续写请求携带 `knowledge_doc_ids` 且不再 422；测试数据清理。

## 三、范围外（显式登记）

- **D1** DSH Agent `kb_search` 只走向量：dsh-agent-panel-integration Property 16 的有意设计（区分「服务坏了」与「没搜到」）；embedding 恢复前该工具对知识文档恒 `semantic_unavailable`。是否让它接词法层属 dsh 域决策，不在本 spec 擅改。
- **D2** 扫描件 OCR：`MINERU_ENABLED=False` 是部署配置；本 spec 只保证界面如实提示，不开启 MinerU。
- **D3** 其余 10 组重复路由（aging / b60 / a16 / issue-hints / export-word / workpaper-summaries / ledger retry）：跨 6 个业务域，逐个需判断哪一份是活实现，本 spec 只冻结基线。
- **D4** `note_ai` 其余端点（generate-policy 等）仍仅登录校验、`check-completeness` 年度写死 2025：已计入平台鉴权棘轮，本 spec 只修被本需求触及的续写 / 改写两个端点。
- **D5** 旧 `/api/knowledge/{category}/*` 文件系统式路由（`knowledge_base.py`）与 `commonApi` 中 5 个无调用方的旧知识库函数：删除属「删旧代码」流程（需逐一确认 0 调用方 + 独立提交），另行处理。

## 四、实施勘误（2026-10-01 收尾时登记；上文原文不改）

- **D5 部分被 R7.2 取代**：`commonApi` 里 5 个旧知识库函数（`listKnowledgeDocuments` / `uploadKnowledgeDocument` / `deleteKnowledgeDocument` / `searchKnowledge` / `listProjectKnowledge`）**已在本 spec 删除**。理由：R7.2 删掉 `apiPaths.knowledge` 的死路径后，这 5 个函数引用的路径常量随之消失，留着会编译失败或指回不存在的路由；删前全仓 grep 确认 0 调用方（含 e2e），并在 `commonApi.ts` 原位留了删除说明。D5 的其余部分仍在范围外：后端旧 `/api/knowledge/{category}/*` 路由（`routers/knowledge_base.py`，`router_registry/system.py` 仍注册）与 `KnowledgeBasePanel.vue` 零挂载死链（5 个路径登记在 `test_frontend_knowledge_paths_exist.py::_KNOWN_DEAD_PATHS`，且有「仍零挂载」的可伪证断言）。
- **R4.2 首版未达标**：见 design §九-6。修正后列表与结束汇总均区分「扫描件 PDF（需 OCR）」与其余无正文原因。
- **D6（新增，范围外）**：`auth_service.login` / `refresh` / `logout` 在 Redis 不可达（`get_redis` 返回 `None`）时直接调用 `redis.get` → `AttributeError` 500。Task 9 实测时因 Docker 端口转发陈旧触发（登录全挂）。属 auth 域，本 spec 不改。
