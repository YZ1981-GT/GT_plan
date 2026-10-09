# 任务清单：知识库检索与授权收口（方案 A）

> 需求：#[[file:.kiro/specs/knowledge-base-retrieval-and-authz-closure/requirements.md]]
> 设计：#[[file:.kiro/specs/knowledge-base-retrieval-and-authz-closure/design.md]]
> 顺序：判定面（1）→ 会话安全（2）→ 词法检索（3）→ 内核集成（4）→ 消费方（5~8）→ 授权（9~10）→ 清理（11）→ 验证（12~13）。
> 纪律：每个任务开始前现读相关文件（工作树有并发会话改动）；标完成必须有代码与测试证据；PBT `max_examples=5`；
> 迁移号实施前重扫；探针 `_` 前缀用完即删。

- [x] 1. 检索可见性判定面（`knowledge_access_policy.py`）
  - [x] 1.1 `KnowledgeRetrievalMode` + `effective_resource` + `can_retrieve`（判定表见 design §二），非法组合抛 `ValueError`
  - [x] 1.2 `KnowledgeWritePolicy`：`role_allows_write` / `can_create` / `can_manage`
  - [x] 1.3 PBT：`can_retrieve`、`can_manage` 与独立参考模型逐格等价（P2 / P11）
  - 证据：`test_knowledge_retrieval_visibility_pbt.py` 10 例（网格 >3 万格逐格等价 + 三类结果都出现的反空转断言 + PBT）；`test_permission_filter_pbt.py` 5 条原性质迁到判定面
  - _需求：3.1–3.6, 6.2, 6.4_

- [x] 2. 会话安全
  - [x] 2.1 `_zh_tokenize`：jieba 缺失降级（CJK 二元组 + ASCII 词）+ `query_terms`
  - [x] 2.2 `KnowledgeIndexService`：读 `knowledge_index` 的语句全部 SAVEPOINT；`select(KnowledgeIndex)` 带 `defer(embedding_vec)`；pgvector 列 information_schema 探测（按引擎缓存）
  - [x] 2.3 CRUD 索引钩子 `_trigger_index_update` 改独立会话（签名去掉请求会话；失败回滚的是钩子自己的会话）
  - [x] 2.4 真库 P1：无 `embedding_vec` 列时旧式查询把会话毒化（反向对照红）；新实现在向量路径 / 词法层内部 SQL 故障注入两种情形下会话均可用
  - 证据：`test_knowledge_doc_search_pg.py::test_p1_*` 2 例 + `test_knowledge_crud_hooks.py`（独立会话断言）
  - _需求：1.1–1.6_

- [x] 3. 文档词法检索（`knowledge_doc_search.py`）
  - [x] 3.1 `DocSearchRequest` / `DocHit` / `KnowledgeDocSearch.search`：范围解析（递归 CTE）、候选 SQL（转义 + 最新版本 + 截断 WARNING）、判定、读正文、打分、片段
  - [x] 3.2 `visible_documents` / `folder_paths`
  - [x] 3.3 纯函数单测 + PBT：`score_document` / `best_window`（P7）
  - [x] 3.4 真库：P3 / P4 / P5 / P6 / P8
  - 证据：`test_knowledge_doc_search_pure.py` 12 例 —— PBT 抓到真缺陷「正文 lower 而检索词不 lower，大写词永远定位不到片段」已修（`best_window`/`score_document` 同时折叠大小写）；`test_knowledge_doc_search_pg.py` 19 例真库全绿（首跑 1 红为夹具自身含字面量 a_b，已改夹具）；另修正需求 2.6：非空但无有效检索词（如 `%`）返回空，不退化成列表模式
  - _需求：2.1–2.10_

- [x] 4. `semantic_search` 集成与权限收敛
  - [x] 4.1 合并向量 / 词法 / 业务数据兜底；`retrieval` 字段；空查询列表模式；`restrict_to` / `category`
  - [x] 4.2 `_filter_by_permission` / `_enrich_results` 重写；删 `_user_can_access_doc`；`semantic_search_strict` 仍只走向量
  - [x] 4.3 `search_global_knowledge` / `load_documents`
  - [x] 4.4 `index_source.KnowledgeDocSource` 改用判定面、删 `_is_accessible`（并只索引最新版本）
  - [x] 4.5 真库 P9 / P10；单元 P14；evidence_governance 适配器契约测试通过
  - [x] 4.6 既有 mock 测试按 design §9.1 逐条归因改写（保留原意图）
  - 证据：真库 P9（注入 8 条向量命中只放行 2 条可见）/ P10 / 全局 / load_documents；`TestSemanticSearchStrictStaysSemanticOnly` 2 例（含对照）；`evidence_governance/test_engine_adapter_contracts.py` + `test_frozen_contracts.py` 通过；mock 夹具统一用 `tests/_kb_mock_session.py`（只补 SAVEPOINT/get_bind 形状）；R2/AIChat 用例改为断言内核用判定结果裁剪（C1 反转写入用例 docstring）
  - _需求：3.7–3.9, 4.1–4.8_

- [x] 5. 参照文档与 A17 / 指导对话
  - [x] 5.1 `ReferenceDocService`：删无权限 ILIKE 兜底、category 加分、列表模式、`search_knowledge_base`
  - [x] 5.2 `a17_llm_service` 取 `document_name`；`wp_guidance_chat_stream` 传 user + 正确键名
  - [x] 5.3 测试：`test_reference_doc_service` / `test_rag_consumer_integration` / `test_a17_llm_service` / `test_wp_ai_chat_pbt`
  - 证据：49 例全绿；顺带（同一消费方链路）：指导对话端点改以底稿自身项目为准，客户端 project_id 不一致 → 422（`test_wp_guidance_chat_project_binding.py`），`WpAiChatRequest.project_id` 补 `min_length=1`（原 PBT 在随机样本下偶发红，根因是模型允许空串）
  - _需求：5.1–5.3_

- [x] 6. 文档级 AI 对话与附注 RAG
  - [x] 6.1 `ContextBuilder`：传 user、`source_name ← document_name`、global 宿主检索、extra_scopes 相关性检索、过滤补已删除
  - [x] 6.2 `NoteKnowledgeEnricher`：doc_filter 下推 restrict_to；后置过滤按 ID / 祖先链
  - [x] 6.3 测试：`test_doc_ai_context_builder` / `test_doc_ai_chat_pbt` / `test_note_knowledge_enricher` / dsh 相关守卫
  - 证据：新增 extra_scopes 相关性 / 列表兜底 / 全局宿主 / 内核失败 4 例 + enricher 下推 / 祖先链 / 无法解析过滤值 3 例；顺带修 `_truncate_knowledge_hits` 逐字段重建 `SearchHit` 丢 `doc_version`/`is_stale`（改 `dataclasses.replace`，用例断言截断后 citation 仍带版本）；dsh 全目录 + 文档对话相关 666 例中 663 过，3 红为 **预存**：`test_task4_run_contract::TestContractMatchesDesign` 读 `.kiro/specs/dsh-agent-panel-integration/design.md`，该 spec 已于 2026-09-08（82e30d7ca）归档到 `_archive/04-infra-architecture/`，与本 spec 无关
  - _需求：5.4, 5.5_

- [x] 7. 项目知识文件夹 + AI 笔记转存 + 跳转路由
  - [x] 7.1 迁移 V170 / R170（实施前重扫号）+ ORM `system_key`；真库执行并现查列与索引
  - [x] 7.2 `ensure_project_folder`（SAVEPOINT + IntegrityError 重查）；真库 P13
  - [x] 7.3 `note_service`：修 5 处断点；`jump_route` 改真实路由；`mention_service` 两处路由
  - [x] 7.4 测试：笔记转存真库端到端（建文件夹 → 写文档 → 可被词法检索召回）
  - 证据：重扫时 V169 已被并行会话占用（`formula_push_engine`，纯新增两表，runner 一并执行）→ 本 spec 用 V170；真库 `executed ['169','170']`，现查 `system_key` 列与部分唯一索引存在。`test_ai_note_capture_pg.py` 11 例：首跑**全红**，暴露设计阶段漏列的第 6 处缺陷 —— `_load_messages` 用 `.join(sa.text(...))`，SQLAlchemy 2.0 下抛 `AttributeError`（转存在读消息这一步就恒失败），已改 ORM join；另修 `_assemble_note_content` 读不存在的 `content/text`（笔记只有标题）、引用标签读 `label` 而负载键是 `source_name`、重放时用 document ID 冒充 folder_id。P13 竞态真实制造（确认第二会话 INSERT 阻塞在锁上后才提交第一会话）+ 反向对照（旧式 `db.rollback()` 丢收据）
  - _需求：5.8–5.10_

- [x] 8. A17-1 / A17-3 / 索引流水线
  - [x] 8.1 `a171_ai_generate`：`load_documents` + `search_knowledge_base`；传 current_user
  - [x] 8.2 `POST /api/knowledge-library/projects/{project_id}/upload`（抽出共享上传实现）；`GtA173ConsultationRecord.vue` 改端点与回调
  - [x] 8.3 `indexing_pipeline`：去 joinedload、private 跳过、状态如实
  - [x] 8.4 测试：a171 指定文档越权过滤、项目上传端点、流水线不再 AttributeError
  - 证据：项目上传端点 3 例（真发请求：建系统文件夹 + 复用 + 目录树可见 / readonly 成员与非成员 403 且不预建文件夹 / 未知槽位 422）；a171 越权过滤由 `load_documents` 真库用例覆盖（`test_knowledge_doc_search_pg::test_global_knowledge_and_load_documents`：点名 4 篇只返回可见 2 篇且保序）；流水线 3 例（继承文件夹项目组分区 / 私有跳过不调索引服务 / AST 判据无 `folder` 属性访问 —— 首版文本判据被自己的注释误伤，按铁律 ㉖ 改 AST）；前端 A17-3 回调按 `data.files[0]` 取 ID，保存失败不再提示「已存入」
  - _需求：5.6, 5.7, 5.11_

- [x] 9. 知识库端点资源级授权
  - [x] 9.1 预览/下载可读判定（404 同构）；预览返回 `folder_id`
  - [x] 9.2 删除/重命名文件夹、删除/移动文档：管理权（404/403 分流）；新建/上传/初始化预设拒 readonly
  - [x] 9.3 新增 `PUT /documents/{id}` 重命名；重命名/移动作用于版本链 + 同名 409
  - [x] 9.4 搜索改 browse 词法检索；目录树/列表 `can_manage` / `can_create`、`doc_count` 只计可读
  - [x] 9.5 端点级测试（真发请求）：P11 / P12 + 越权矩阵
  - 证据：`test_knowledge_endpoint_authz.py` 18 例（TestClient 真发请求，override 内层 `get_current_user`/`get_db` 让真实判定跑）：私有文档对非属主预览/下载/改名/移动/删除一律 404 且响应体逐字节同构（P12）；可见但非属主 → 403；readonly 新建/上传/初始化预设 → 403；改名作用于整条版本链、同名 409、非法名 422；移动到不可见目标 404、不可管理目标 403；搜索只返回可读文档并带 `folder_path`/`snippet`；目录树 `doc_count` 不计不可读文档、系统文件夹 `can_manage` 只对管理员为真。与 `test_knowledge_folder_create_upload.py` 合跑 31/31；与检索/笔记真库套件合跑 67 passed。`tests/security/test_task1_baseline_and_evidence.py` 3 红为**预存**（迁移头期望 V112/V115 而磁盘在本 spec 之前已到 V169；另读一份不存在的 evidence schema），与本任务无关
  - _需求：6.1–6.7_

- [x] 10. 知识库前端
  - [x] 10.1 `KnowledgeBase.vue` 深链 `?folder_id=` / `?doc_id=`
  - [x] 10.2 按钮按 `can_manage` / `can_create` / 角色门控；批量删除 403 单独提示
  - [x] 10.3 `apiPaths/system.ts` 补 `projectUpload`；vitest 覆盖深链与门控
  - 证据：深链在目录树加载后处理（`onMounted`）并 `watch` 同页链接变化；只给 `doc_id` 时以 `_silent` 调预览取 `folder_id`，不可读 →「文档不存在或无权访问」、文件夹不在树 →「文件夹不存在或无权访问」，文档可读但文件夹不在树（公开文档放在他人私有文件夹）→ 只开预览并说明。门控 = 系统角色兜底 `canWriteKb`（`normalizeRole`；readonly / 未知 / 用户信息缺失一律隐藏，与后端白名单同口径）∧ 节点 `can_manage`（文件夹改名/删除）/ `can_create`（上传到此、默认父级、「位置」下拉只列可创建）∧ 行 `can_manage`（改名/删除、可勾选）。批量删除逐条 `_silent`，403 / 404 / 其他分开计数。搜索视图显示 `folder_path` + `snippet`。顺带修 2 个旧缺陷：①搜索视图下改名/删除/上传后拿无 id 的视图对象去列目录（请求 `/folders/undefined/documents`）→ `refreshDocView` 按 id 在新树重定位或重跑搜索；②AI 笔记文档名无后缀（`file_type=md`），旧分流只看文件名 → 预览面板恒「不支持预览」，深链打开笔记看不到内容 → `docExt` 已知后缀优先、否则用 `file_type`。`KnowledgeBase.deepLinkAndGating.spec.ts` 17 例全绿（element-plus 用行为替身：真插槽 / 可选列 / 节点点击，断言落在真实 DOM 上）。
  - 证据（实跑时抓到的并发会话改线脚本缺陷，均已修）：跑 A17-3 回归时 `GtA173ConsultationRecord.spec.ts` 11 红，根因不在本 spec —— 并发会话批量插入 `<GtEntrySyncCapabilityNotice>` 的脚本造成三类语法错误：①插进多行开标签属性区（5 个：A115/A1731/A173/A174/A176；Vue 编译器把 `<GtEntry…` 收成属性名、不报错，运行时 `setAttribute` 抛 `InvalidCharacterError`）②`import { …, toRef, toRef }` / `computed` 重复绑定（6 个：A101/A121/A1721/A177/A271/A38）③`import { useXxx }` 与下一条 import 粘连（9 个 M 类底稿）④把 `<GtOnlyOfficeSheet v-else-if="ooReady">` 换成 `<template v-else>` 致其后「生成失败」`v-else` 悬空（2 个：A171/A177，模板编译错误，已恢复三态 `v-else-if="ooReady"`）。另有 2 个预存：B60 工时面板块注释里的 `/rows/*/rowUuid` 让 `*/` 提前闭合注释（**HEAD 已有**，`compileScript` 实测 `Missing semicolon`）、ConfirmationAIPanel 孤立 `</script>` + 逐字重复的第二段 `<style scoped>`；以及 ManagementLetterPanel 属性值内半角双引号截断说明文字。新增守卫 `src/__tests__/vueSfcSyntax.spec.ts`（全仓 2410 个 .vue：SFC 解析错误 + 静态属性名合法 + `compileTemplate` 无错误 + 每个 script 块 babel 可解析；6 种坏形态变异自检 + 文件数 >1000 防空转），修复前 25 处、修复后 0 处；受影响组件既有 spec 13 文件 153 例全绿。6 个组件缺 `toRef`/`defineAsyncComponent` 显式导入只影响 vitest（应用里由 unplugin-auto-import 注入），已补齐但不纳入守卫
  - _需求：5.10, 6.8_

- [x] 11. 清理旧 `DocAiChatPanel.vue`
  - [x] 11.1 删前 grep 生产引用为 0；删组件与专属 spec，宿主页面模板形态判据迁移保留；`components.d.ts` 条目移除
  - [x] 11.2 前端相关测试全绿
  - 证据：删前全仓 grep 生产引用 0（仅 3 个专属 spec + `components.d.ts` + 3 处过期注释）。删 `DocAiChatPanel.vue` + `DocAiChatPanel.spec.ts` / `.citation.spec.ts` / `.host.spec.ts`；宿主守卫意图逐条迁到 `components/ai/__tests__/PlatformAiChatPanel.host.spec.ts`（真实 mount 统一内核面板、不 mock composable：宿主不可用零请求 + 中文原因、全局模式与无项目知识库不带 `project_id`、底稿打开即拉历史作非恒真对照；三个宿主页模板形态；DshPanel / 独立窗口只经 `:host`）。**变异 4/4 RED 且还原 sha256 一致**：宿主不可用照发请求 / 不可用也拉历史 / 无项目仍发空 `project_id` / 知识库把项目 ID 塞文档位 —— 首版对第一条判 **GREEN**，根因是输入框禁用时 `setValue` 不派发事件、草稿为空，`sendMessage` 在「空文本」处就返回，根本到不了宿主判定；改为直写草稿并断言会话里是宿主不可用原因而非用户消息后转 RED。迁移时发现旧 host spec 已**整文件收集失败多日**（WorkpaperEditor 自 2026-09-09 按 workpaper-page-formula-toolbar-closure Req 4 改由全局 DshPanel 承载 AI 对话，`describe.each` 同步体找不到标签即抛错 ⇒ 整文件零执行），其中 DshPanel / 独立窗口两条判据描述的是已被统一面板取代的形态，按现行形态改写并在用例里写明；`PlatformAiChatPanel.spec` 的 WorkpaperEditor「应含面板」改为「不得裸挂第二条链 + DshPanel 以路由 wpId 构造底稿宿主」。同步：`components.d.ts` 条目、ReportView / DisclosureEditor / KnowledgeBase / useAiHostContext.spec 过期注释、`vue_file_lines_baseline.json` 条目、`mutate_dsh_task2/task7` 两个正式变异脚本的守卫清单与 M17 锚点（改锚 `usePlatformAiChat.sendMessage`，基线待首跑回填已注明）。AI 相关前端 23 文件 386 例全绿
  - _需求：5.12_

- [x] 12. 变异证明
  - [x] 12.1 `_kb_mutation_check.py` 跑 M1–M8（design §9.4），每条目标测试变红、还原后 sha256 一致；结果记入本任务证据
  - 证据（2026-09-29 实跑；基线 3 文件 46 passed 且零失败才开跑，否则差集判定不可信直接中止；锚点逐条先 `--check-anchors` 确认恰好命中 1 次）：
    | M | 变异 | 判定 | 命中的目标测试 |
    |---|------|------|----------------|
    | M1 | 词法检索不调 `can_retrieve`（全放行） | RED 5 failed | `test_p3_project_mode_with_user`、`test_p10_project_mode_without_user_never_returns_private` |
    | M2 | 词法层去掉 SAVEPOINT | RED 1 failed | `test_p1_semantic_search_keeps_session_usable` |
    | M3 | 去掉最新版本 `NOT EXISTS` | RED 4 failed | `test_p4_superseded_version_hidden_unless_named` |
    | M4 | LIKE 通配符不转义 | RED 1 failed | `test_p6_like_wildcards_are_literal` |
    | M5 | `restrict_to` 不下推 SQL、改为 top_k 截断后过滤 | RED 2 failed | `test_p5_restriction_applies_before_top_k` |
    | M6 | `user=None` 恢复不过滤 | RED 4 failed | `test_p10_…`、`test_system_caller_never_sees_private_documents` |
    | M7 | 管理权去掉所有者判断 | RED 9 failed | `test_delete_document_matrix[other-403]`、`test_can_manage_matches_reference_on_full_grid` |
    | M8 | 重命名只改锚点那一行 | RED 1 failed | `test_rename_document_renames_whole_version_chain` |

    8/8 RED，每条还原后 sha256 与变异前逐字节一致，事后现查生产文件 `MUTATED` 残留 0、三文件复跑 46 passed。🔴 首版 M5 写成「候选后过滤」（仍在截断前）只打红 P4 不打红 P5 —— 那不是 design 要的「top_k 后过滤」，改为两处替换（范围不下推 + 截断后过滤）才命中 P5；教训：变异要按规格原文构造，打红了「某个」测试不等于打红了「该打红的」测试
  - _需求：7.3_

- [x] 13. 真栈与回归
  - [x] 13.1 Playwright（design §9.5）全流程 + 截图证据；测试数据清理
    - 证据（2026-10-05 Playwright MCP 实跑）：
      ① admin 登录 → 知识库页面（截图 `evidence/01-kb-page-admin.png`）
      ② 新建公开文件夹「Playwright测试文件夹」→ 上传 `_playwright_test_kb_doc.txt`（含独特词
         `XYLOPHONE_ZEBRA_2026`）→ 文件夹显示 (1)（截图 `02-kb-folder-with-doc.png`）
      ③ 搜索 `XYLOPHONE_ZEBRA_2026` → 命中 1 条，显示 `📁 /Playwright测试文件夹` 路径 +
         正文片段含关键词 + admin 视角有预览/重命名/删除三按钮（截图 `03-kb-search-hit-with-snippet.png`）
      ④ readonly 用户（`_kb_readonly_test`，DB 强制 `role=readonly`）登录 → 知识库页面：
         工具栏**隐藏**新建文件夹/上传文档/上传文件夹/初始化预设四按钮（只剩搜索+刷新）；
         文件夹树节点**无** ✏️🗑️ 管理按钮；文档行**无** selection 列（checkbox 不渲染）、
         操作列**只有预览**（无重命名/删除）；**无**「上传到此文件夹」按钮
         （截图 `04-kb-readonly-no-write-buttons.png`）
      ⑤ 测试数据已清理（文件夹 + 文档 + readonly 测试用户 + 探针脚本 + 临时 txt 全删）
  - [x] 13.2 相关后端/前端测试集全绿；预存红逐条归因
    - 证据（2026-09-30 复跑）：后端 18 个知识库/检索测试文件 **242 passed / 2 failed**；
      前端 19 个 spec 文件 **332 passed / 0 failed**（`components/ai/__tests__` 全目录 +
      `useDocAiChat.spec.ts` / `.d4.spec.ts` / `KnowledgeBase.deepLinkAndGating.spec.ts` /
      `useAiChat.spec.ts`）。
    - **2 红逐条归因 = 预存，且用 HEAD 字节实测而非推断**：
      `test_knowledge_index.py::TestKnowledgeIndexService::test_service_instantiation`
      断言 `service.db is mock_db` 而 `KnowledgeIndexService` 无 `db` 属性；
      `::test_chunk_text` 断言 `KnowledgeIndexService._chunk_text` 而 `_chunk_text` 是
      **模块级函数**不是类方法（现算：类方法只有 `__init__` / `_vector_to_str` /
      `_str_to_vector` / `_cosine_similarity` / `_upsert_chunk` / `_batch_upsert_chunks` /
      `_index_sources` / `_get_store`）。
      🔴 **不能凭「测试文件旧」直接判预存**：`knowledge_index_service.py` 在工作树里是 ` M`
      （54005 B vs HEAD 43305 B，**被改过**）。故写探针把该文件换成 HEAD 字节复跑 ——
      **HEAD 版本同样这 2 条红**（14 passed 不变），仅工作树红 = 空集 ⇒ 预存确认，
      还原后 sha256 逐字节一致。根因是服务在 2026-08-22 重构（commit `55c5e0fe5`）而
      测试文件自 2026-04-12（commit `da7ff7c09`）未跟。
  - [x] 13.3 INDEX.md / memory.md 更新；探针删除
    - INDEX.md：本 spec 进度格 `0/13（Design-First，实施中）` → **`55/58`**（现扫）。
      顺带一并纠正 6 条同样过期的进度格（它们与本 spec 同为「表里的数字比磁盘旧」）：
      `tb-adjustment-column-formula-closure` 0/44→23/44 · `l-cycle-true-adapter-registration`
      7/17→9/17 · `consol-tree-three-code-autobuild` 0/14→56/70 ·
      `workpaper-sync-pure-static-lane-…` 50/52→69/72 ·
      `excel-template-override-layer-…` 25/27→26/27 · `oo-html-writeback-performance` 9/13→11/13。
      改动只动第 2 格（进度），一句话描述格一字未动；改后「每行恰 4 个未转义 pipe」校验 0 异常。
    - memory.md（186 行，限 200）：把「🔴 下游 RAG 全部看不到知识文档（待 spec + 用户决策）」
      改为「✅ 已通（方案 A）」并保留方案 B 仍暂缓的 5 断点；同时**纠正一条已被推翻的记录** ——
      原记「confirmation_risk_level_enum 缺 pass、workpaper_task_status_enum 缺 4 值」经
      `migration-integrity-and-enum-drift-closure` 现场核验为**误报**（旧实现比较 `.value`，
      而 public 标签正是成员名）。总行数未增。
    - 探针删除：**35 个 `_kb_*`**（`analyze/` 23 + `diagnose/` 11 + 1 个 pyc）。
      删前逐个 `git ls-files --error-unmatch` 确认**被跟踪数 = 0**；删后 `backend/scripts` 的
      git `D` 项数 **15 → 15 不变** ⇒ 零 git 影响。其中 6 个（`_kb_drift_history` /
      `_kb_enum_probe` / `_kb_evgov_codes` / `_kb_migration_probe` / `_kb_v128_history` /
      `_kb_drift_effects`）内容属 migration spec 但落在 `_kb_*` 命名空间，按其 Task 6.3
      的移交约定在本任务一并清理。
  - _需求：7.1, 7.2, 7.4, 7.5_
