# DSH Agent Panel Integration — 收口复盘

## 概览

| 维度 | 状态 |
|------|------|
| Spec 三件套诊断 | 零错误 |
| AC 覆盖率 | 120/120（所有 AC 被 task 引用） |
| Property 覆盖率 | 40/40（所有 Property 被 task 引用） |
| Task 依赖图 | 35 tasks / 21 waves / 无同波强依赖 |
| 变异 --check-anchors | **41/41 通过**（15 Task 33 + 12 假绿修复 + 8 MCP 取数 + **6 渲染宿主**） |
| 变异**实跑** | **41/41 全 RED**（15 + 12 + 8 + **6**，GREEN/MISS/WRONG 各 0） |
| 守卫实测 | backend **722 passed** / frontend **289 passed / 16 files**（2026-08-22 实测，原 242/14） |
| Playwright 实跑 | **37 passed / 4 failed / 19 skipped**（2026-08-22；4 failed 均为本 spec 之外的既有问题，见「未完成项 §8」） |
| Clean-DB CI 引导实测 | 全新空库上 508 / 25 / 189 passed，0 skipped |
| 最新迁移号 | V149（V147 + V149 为本 spec 新增） |
| 迁移幂等性 | 两个迁移均使用 IF NOT EXISTS |
| tmp_*/wip_* 清理 | 已删 2 个，余 7 个属他人 |

## 已验证能力

### Phase A — 安全与单一 Chat Run 内核

- ResourceAccessResolver：公共权限适配层，五角色矩阵，拒绝在读取前
- HostContextResolver：6 种宿主，服务端反查，assertion 不一致拒绝
- AI Chat 持久化：ai_chat_sessions/messages/runs/tool_calls/attachments/action_receipts
- Typed Run Contract：ChatRunRequest/ChatEvent/ChatEventType/状态机/terminal CAS
- Run Coordinator：有界队列、Redis lease、Last-Event-ID replay、cancel/drain
- NativeEngine：复用 AIService/vLLM、熔断→typed error、无 fail-soft placeholder 残留
- Adopt fail-closed：server-authoritative content，receipt 防重，log 写失败回滚
- 前端 canonical transport：增强 sse.ts（跨 chunk buffer/CRLF/AbortSignal/Last-Event-ID）
- PlatformAiChatPanel：唯一核心面板，所有宿主作 HostRef adapter
- 不可信渲染：marked→useSanitize→v-html 统一路径
- 响应式/可访问性：三视口、keyboard、focus trap、aria-live 节流
- 限流/审计/指标：真实 route matcher、哈希链、结构化指标

### Phase B — 上下文能力

- Mention 聚合：7 类 MentionType，授权搜索，Context Manifest
- 附件/OCR：安全上传、五态状态机、cleanup 幂等、legal hold
- 项目笔记：幂等转存、receipt 防重、知识索引接入
- 复核模式：ReviewPromptService、single-system assembly、server session
- 地址坐标索引：AddressCoordinateIndexSource、ACNR invalidation、semantic_unavailable

### Phase C — DSH Experimental Agent

- MCP scoped REST：token 生命周期、五角色脱敏、budget/audit
- **MCP 工具真实取数**：7 个工具（wp_list / wp_read / tb_query / addr_lookup /
  kb_search / note_read / review_prompt）全部返回真实平台数据，工具内二次授权、
  按角色脱敏、typed error 分离、自带行数封顶 —— 见下「已修复项 §1」
- audit-data MCP server：stdio-only、零 DB、`MCP_READONLY_TOOLS` 校验
- DSH SDK discovery：精确 pin、custom Cordis smoke、JSON-RPC/MCP handshake
- DshEngine：per-run MCP process、有界 worker、cancel 传播、backpressure
- 脱敏/注入边界：deterministic fake agent 测试、数据定界
- Capability/local-only：effective route 校验、`local_only_violation`
- 双用户隔离：交换 token/run/project 拒绝、session 文件不串用

## 产物清单

### 后端实现（28 files in backend/app/services/ai_chat/）

access.py / address_index_source.py / address_mention.py / adopt.py /
attachment_service.py / audit.py / capability_endpoint.py / context_budget.py /
contracts.py / dsh_discovery.py / dsh_engine.py / dsh_masking.py / engine.py /
host_context.py / mcp_budget.py / mcp_token.py / **mcp_tools.py** / mention_service.py /
metrics.py / native_engine.py / note_service.py / persistence.py / review_mode.py /
run_contract.py / run_coordinator.py / run_events.py / run_service.py / startup_health.py / __init__.py

> `mcp_tools.py` 为 MCP 取数补口新增（29 files）。同时 `backend/app/routers/ai_chat_mcp.py`
> 的 7 个 dispatcher 改为委派该模块；`backend/app/services/knowledge_index_service.py`
> 纯增 58 行 `semantic_search_strict`（tracked 文件的 `M` 修改，已 diff 归因）。

### 迁移

- V147__ai_chat_persistence_runs_and_session_key.sql (18,884 chars / 442 lines)
- V149__ai_chat_mcp_scoped_tokens.sql (1,943 chars / 63 lines)

### MCP Server

- tools/audit-data-mcp/server.py

### 前端（audit-platform/frontend/src/）

- components/ai/PlatformAiChatPanel.vue（唯一核心面板，860 lines）
- components/ai/ChatMentionPicker.vue
- components/ai/ChatAttachmentPicker.vue
- components/ai/ChatContextInspector.vue
- components/ai/ChatReviewModeBar.vue
- composables/usePlatformAiChat.ts
- utils/sse.ts（增强，已跟踪 M）

### 后端测试（22 files，722 tests）

- backend/tests/dsh_agent_panel/（15 files，含 fixtures）
- backend/tests/test_ai_chat_mcp_router.py
- backend/tests/test_ai_chat_mcp_token.py
- **backend/tests/test_ai_chat_mcp_tools_data.py**（MCP 取数守卫，25 tests）
- backend/tests/test_ai_chat_task12_audit_metrics.py
- backend/tests/test_ai_chat_task29_dsh_masking.py
- backend/tests/test_audit_data_mcp_server.py
- backend/tests/test_dsh_discovery_task27.py

### 前端测试（14 files）

- Vitest unit/integration：sseEventTypes / useAiChat / chatRunState / PlatformAiChatPanel / PlatformAiChatPhaseA / PlatformAiChatXss / DshPanelA11y / ChatMentionPicker / ChatAttachmentPicker / ChatContextInspector / PhaseBGateGuards 等

### Playwright（4 files）

- dsh-agent-panel-acceptance.spec.ts
- dsh-phase-a-smoke.spec.ts
- dsh-phase-b-smoke.spec.ts
- doc-ai-chat.spec.ts

### 变异（35 条锚点，**35/35 实跑全 RED**）

- mutation_manifest.json（**35 条** = M01–M15 Task 33 + M16–M27 假绿修复 + **M28–M35 MCP 取数**）
- backend/scripts/diagnose/mutate_dsh_agent_panel_guards.py（runner）
- 结果记录三份互不覆盖：`mutation_results.json`（15）·
  `mutation_results_falsegreen_fix.json`（12）· `mutation_results_mcp_data.json`（8）

> 🔴 **2026-08-16 更正**：`mutation_results.json` 此前只有 **5/15 真跑**，另 10 条记的是
> `verdict="VERIFIED_ANCHOR_ONLY"`（只做了 `--check-anchors` 静态检查，note 写
> "full run reserved for CI or dedicated session"）。Task 33 子任务原文要求
> 「每个变异必须命中唯一锚点**并由预期测试打红**」—— 静态锚点检查不满足该条件，
> 因为按四态判定，**GREEN（守卫缺陷）恰恰只有真跑才暴露**。已把那 10 条全部真跑：
> 首轮 **RED 3 / GREEN 6 / WRONG-TEST 1**，即此前标「已验证」的 10 条里 **7 条实为缺陷**。
> 全部修复后复跑 **10/10 RED**。详见「已修复项 §2」。

## ✅ 已修复项（Task 35 之后发现并补口）

### 1. MCP 7 个工具的取数实现（原为空占位 → 已补真实取数）

**🔴 这一条此前既不在「已验证能力」也不在「未完成项」—— 它谁都不属于，
所以谁都没登记。这正是问题本身。**

`routers/ai_chat_mcp.py` 的 7 个 `_tool_*` dispatcher 原本全是空占位：
`wp_list` 返回 `{"items": []}`；`tb_query` 返回 `{"rows": []}`；
`kb_search` 返回 `{"results": []}`；`wp_read` / `addr_lookup` / `note_read` /
`review_prompt` 返回 `{"status": "placeholder"}`。注释写「实际在 Task 26 接通」。

**为什么全绿却没数据（责任真空）：**

- **Task 25** 的范围是 MCP REST **安全边界**（ResourceAccessResolver 接线、
  scoped token、脱敏映射、预算、哈希链审计）。它建好 dispatcher 骨架与签名，
  正文留占位。
- **Task 26** 建的是**调用方**（`tools/audit-data-mcp/server.py`）。
  按 Req 11.4 它**不得**直连数据库，因此按设计就不该包含平台侧取数。
- 两者的验收标准都能在「取数是空占位」的前提下全绿 ⇒ 取数实现**无归属**。

三层管道（REST → stdio server → DshEngine）全通、Phase C **207 测试全绿**，
根因只有一条：**没有一条测试断言过返回值**。守卫全落在「管道接没接通」，
没有一条落在「Agent 到底拿到了什么」。DSH Agent 实际取不到任何底稿 /
试算表 / 附注内容，而静态检查、`get_diagnostics`、CI 全都看不出来。

**修复内容：**

| 项 | 落法 |
|----|------|
| 取数实现 | 新建 `backend/app/services/ai_chat/mcp_tools.py`（放 service 层，守卫可直调不必起 HTTP） |
| 复用而非另写 | `filter_visible_resources`（可见集）· `get_active_filter` + `four_table` 叶子聚合（试算表）· `resolve_address_mention`（地址）· `KnowledgeIndexService`（知识库）· `ReviewPromptService`（复核） |
| 工具内二次授权 | 每个工具再过 `ResourceAccessResolver` + `cycle_scope` 裁剪；越权返回**拒绝**不返回空数据 |
| 脱敏调用链修正 | 实测确认裸 `ExportMaskService.apply_mask` 对「只含金额的结构」是**空操作** ⇒ 改走 `dsh_masking.mask_tool_result`（递归处理嵌套 dict/list 金额） |
| typed error | `tool_resource_not_found` / `access_denied` / `tool_invalid_argument` / `semantic_unavailable` / `tool_service_unavailable` 各自分码 |
| 工具自身封顶 | `MAX_WP_LIST=200` / `MAX_TB_ROWS=500` / `MAX_ADDR_ROWS=50` / `MAX_KB_HITS=20` / `MAX_NOTE_ROWS=200`，SQL 层下推 |
| 只读 | 只有 `select`；`TestReadOnlyGuarantee` 剥注释后断言无 insert/update/delete/commit |
| 禁伪降级 | 新增 `KnowledgeIndexService.semantic_search_strict`（embedding-only，58 行纯增）；embedding down 抛 `semantic_unavailable`，禁 BM25/ILIKE 冒充 |
| 死代码清理 | 切到 `mask_tool_result` 后，router 里 `_mask_service = ExportMaskService()` 单例零引用 ⇒ 已删（连带 `ExportMaskService` / `Request` / `settings` / `AiChatAction` / `HostRef` / `HostType` / `ResourceType` / `McpScopedToken` 8 个未使用导入 + `create_mcp_token` 内未使用的 `resolver` 局部）。用 AST 取值引用计数判定（非 grep 计数，避免注释污染），删后复验 707 passed + 35 锚点仍全命中 |

**守卫**：`backend/tests/test_ai_chat_mcp_tools_data.py`（**25 tests，全 passed**）——
非空断言 6 · 禁占位 4（含源码级判据 + **反向自检**）· 授权 6 · 脱敏 3 ·
typed error 5 · 只读 1。

**变异**：锚点 **M28–M35**，**8 条全 RED**（GREEN / ANCHOR-MISS / WRONG-TEST 各 0），
结果记 `mutation_results_mcp_data.json`（未覆盖 `mutation_results.json` 与
`mutation_results_falsegreen_fix.json`）。

**回归**：`backend/tests/dsh_agent_panel/` + `test_ai_chat_mcp_*.py` +
`test_audit_data_mcp_server.py` + `test_ai_chat_task{12,29}_*.py` +
`test_dsh_discovery_task27.py` = **707 passed**（原 682 + 新 25）。

⚠️ **一次不可复现的瞬时失败（诚实记录，未定位）**：回归过程中有**一轮**出现
`1 failed, 706 passed`，但未打印失败用例名即被输出截断。随后**15 轮复跑全部 707 passed**
（6 轮全子集 + 8 轮单跑 `test_task13_phase_a_guards.py` + 1 轮经 `rtk`），无法复现。

- **已排除**：`rtk` 包装（经 rtk 跑同样 707 passed）· 随机顺序（多轮不同顺序全通）·
  本次改动引入（`test_ai_chat_mcp_tools_data.py` 25 条在全部 15 轮中均通过）。
- **最可能成因**：夹具用**真实共享 dev PG**（`audit_platform`），并发会话同时跑 pytest
  时存在争用；嫌疑最大的是 `test_100_concurrent_same_session_produces_one_session`
  （100 并发 upsert，且该测试本身带 SAWarning
  「`Session.add()` during flush ⇒ Results may not be consistent」）。
- **结论**：不宣称「已修复」，也不宣称「不存在」。登记为**待观察的疑似并发脆弱守卫**；
  若在 CI（独立 PG 实例、无并发会话）复现，则说明是真实竞态，需修
  `persistence.py:353` 的 flush 期 `add`。

**通用教训**：「三层管道全通 + 测试全绿」不等于「有数据流过」。管道类守卫
（鉴权 / 白名单 / 预算 / 审计成对）与数据类守卫（返回值非空 / 结构符合声明 /
越权拒绝而非空 / 脱敏前后不相等）是**两个正交维度**；只做前者时，把每个 handler
正文换成 `return {}` 依然全绿。这是假绿第①源在**跨任务边界**上的新变体 ——
代码不是没被消费，而是**被消费了但没人检查消费到了什么**。

---

### 2. Task 33 的 10 条变异从「静态已验证」补成真跑（发现 6 个守卫缺陷 + 1 个脚本缺陷）

**问题**：`mutation_results.json` 里 10 条 verdict 是 `VERIFIED_ANCHOR_ONLY`，note 写
"full run reserved for CI or dedicated session"。但 Task 33 子任务原文是「每个变异必须
命中唯一锚点**并由预期测试打红**」—— 静态锚点检查只能证明「锚点还在、测试名还对」，
证明不了「守卫抓不抓得到」。**GREEN 按定义只有真跑才暴露**。该 task 此前被误标为完成。

**真跑首轮结果（10 条）**：RED 3 · **GREEN 6** · **WRONG-TEST 1** · ANCHOR-MISS 0。

| 锚点 | 首轮 | 根因 | 分类 | 修法 |
|------|------|------|------|------|
| M02 取消 host loader 调换 | RED | — | — | — |
| M05 取消不传 child | RED | — | — | — |
| M15 脱敏未知角色 | RED | — | — | — |
| M06 SSE 拆包 | GREEN | selector 指向 `sseEventTypes.spec.ts`（测 `@/types/sse` 的类型联合，与解析器无关）⇒ **跑错测试套**；真判据一直在 `utils/__tests__/sse.spec.ts`（41 例任意分片等价） | 脚本缺陷 | selector 改 `sse.spec`（实测唯一匹配），expect_test 改「每字节分片结果与基线一致」。**未改生产代码与守卫** |
| M07 放宽 attachment owner | GREEN | 守卫 **fail-open**：`validate_for_run(attachment_id=…, user_id=…, project_id=…)` 三个关键字都不在真实签名里 ⇒ 恒抛 `TypeError`，而断言是 `pytest.raises((…, Exception))` 把它兜住。且该函数**不抛异常**，它返回过滤后列表 | 守卫缺陷 | 改断言返回列表不含他人附件；补 session 维度反向自检 + **签名反向自检**（断言那三个错名不存在于签名） |
| M09 semantic fallback | GREEN | Property 16 判据是源码字符串且带**恒真 `or` 子句**（类正文写的是中文「回退」，第一子句恒 True）；`EmbeddingUnavailableError` 的两个消费方都是**函数体内惰性 import**，改类名只在调用期炸，Phase B 从未触达那两条路径 | 守卫缺陷 | 补 4 条：真调 `semantic_search_strict` 断言抛权威类型且保留 `__cause__` · 零命中≠不可用（反向自检）· 两消费方解析出**同一类对象** · `check_embedding_health` 失败返 False |
| M10 跨用户 token | WRONG | `expect_test="user_id"` 在测试源正文里存在（参数名），静态检查放行；真正打红的测试叫 `test_wrong_user_rejected` ⇒ 判成 WRONG-TEST。**守卫本身有效** | 脚本缺陷 | expect_test 改 `wrong_user_rejected`；并给 `--check-anchors` 加第 4 类判据（见下） |
| M12 恢复 localStorage 正文 | GREEN | Property 35 的 4 条判据全是 **grep 式**（`expect(src).toContain('clearLegacyAiChatCache')`）。把前缀改成 `'__never_match__'` 让清理函数一个 key 都不删，遗留对话正文全留在浏览器，4 条依旧全绿 | 守卫缺陷 | 补 3 条行为判据：真播种 3 条 `doc_ai_chat_*` 敏感正文 + 1 条非敏感偏好 → 调真实 `clearOnLogout/clearOnUpgrade` → 断言敏感 key 清空、非敏感偏好保留、敏感中文串不再出现在任何值里 |
| M13 DSH 失败降级 | GREEN | 判据只看**最终错误码**。`_run` 里 SDK 门（步骤②）之后的上下文创建④/MCP 进程⑥/DSH root⑦/handshake⑧ **失败也都抛 `engine_unavailable`**，detail 同样可能含「不可用」⇒ 去掉门只是换个地方失败，可观测结果不变 | 守卫缺陷 | 补 3 条门级判据：直调门必须抛且 detail 点名 `SDK`+`sdk_not_found`+discovery 原因 · discovery 可用时必须放行（防恒抛）· **门后副作用计数为 0**（`_create_run_context` / `spawn_mcp_process` 都不得被调用） |
| M14 切 cloud model | GREEN | 全部 local-only 判据打在 `startup_health` 上，而 `/capabilities` 的 `health` 走**另一套实现** `capability_endpoint._collect_service_health → _check_model_health`，后者零取值覆盖（唯一触达者只断言 `hasattr(h,'available')`） | 守卫缺陷 | 新增 `TestCapabilityEndpointLocalOnly` 5 条取值判据 + **两套实现对同一 settings 结论一致**（防「启动自检拦住了但前端仍放开入口」） |

**复跑结果**：**10/10 RED**（GREEN/MISS/WRONG 各 0）。合并入 `mutation_results.json`
后 Task 33 = **15/15 真跑全 RED**。生产代码字节级复原已用 sha256 逐文件校验（10/10 一致），
无 `.bak` 残留。

**守卫计数变化**：`backend/tests/dsh_agent_panel/` **493 → 508 passed**
（phase_b +7 · dsh_engine +3 · capabilities +5）；前端 `PlatformAiChatPhaseA` +3。
后端合计 707 → **722 passed**。

**变异脚本本身也加固了**：`--check-anchors` 新增第 4 类静态判据 ——
**expect_test 必须命中真实测试名/用例标题**（pytest `def test_*` / vitest
`it|test|describe('…')`），不能只是源码正文里的任意片段。已做**反向自检**：把 M10 的
expect_test 换回旧值 `user_id`，静态检查必须打红（已验证会打红）。这样同类漂移
不必等全量实跑就能暴露。

**通用教训**：`--check-anchors` 与变异实跑**不是强弱关系而是互不覆盖** —— 静态查
「锚点还在不在、测试名还对不对」，实跑查「守卫抓不抓得到」。把静态通过写成「已验证」
就是假绿。本次 6 个 GREEN 的形态**各不相同且都能通过静态检查**：跑错测试套 ·
调用签名写错被 `raises(Exception)` 兜住 · 恒真 `or` 子句 + 惰性 import 无人触达 ·
grep 式判据 · 多个不同根因共用同一错误码 · 判据打在另一套同名实现上。其中
「多个根因共用同一错误码」最隐蔽：`engine_unavailable` 被四处共用，只断言错误码
等于它等于什么都没断言 —— 门类判据必须落到「门后副作用一次都没发生」。

---

### 3. `dsh-agent-panel-backend` job 缺 postgres service（原「未完成项 §2b」，已修）

**先实测再动手**（结论不是推测）。同一工作树切换 `DATABASE_URL` 各跑一次
`backend/tests/dsh_agent_panel/`：

| `DATABASE_URL` | passed | skipped | exit code |
|---|---|---|---|
| `postgresql+asyncpg://…`（PG 可达） | **493** | 0 | 0 |
| `sqlite+aiosqlite:///…` | 310 | **183** | **0** |

⇒ **确有静默 skip**：无 PG 时 183/493（37%）被 `pytest.mark.skipif(not IS_PG)` 跳过，
**job 仍以 0 退出**。此前该 job 无 service ⇒ 那 183 条**从未在 CI 执行过**。
另 6 个后端测试文件（189 tests）实测 PG 无关（sqlite 下 189 passed / 0 skipped）。

**已做**：补 `services: postgres` + `DATABASE_URL` + schema 引导步骤，并加两条**硬断言**
（复跑 `-q -rs` 解析摘要，passed 低于实测基线或出现**任何** skipped 即打红；
基线 508 / 189，数值比较用 `python -c`，`>=508` 的 grep 正则不可维护）。
`dsh-agent-panel-mcp-data` 的同名断言形态照旧（≥25）。

#### 3b. 补 service 后本地实测该 job 测试集 —— 又抓出 3 个真实 CI 缺陷

按「加了 service 意味着此前被 skip 的测试首次真跑，失败面未知」的要求，不止跑 dev 库，
而是建了**全新空库** `audit_platform_ci_probe` / `…_probe2` 走 CI 的完整引导路径。
三个缺陷都**只在空库上出现**，dev 库上 508 全绿看不出来：

| # | 缺陷 | 表现 | 修法 |
|---|------|------|------|
| ① | service 镜像用了裸 `postgres:16` | `Base.metadata.create_all` 里有 `VECTOR(1024)` 列（knowledge 索引）⇒ `type "vector" does not exist`，**整个建表步骤失败** | 两个 job 的镜像均改 `pgvector/pgvector:pg16`（与本地 dev 一致） |
| ② | 只跑 `MigrationRunner.run_pending()`，缺 `create_all` 引导 | 平台基础 schema **由 ORM 建、不由迁移建**（`V*.sql` 绝大多数是 `ALTER TABLE` 增量）。空库直跑迁移 **124 个失败**（`relation "projects" does not exist`）**而 `run_pending()` 仍返回成功、步骤仍绿** —— 又一个静默失败 | 引导步骤改三段：`CREATE EXTENSION vector` → `scripts/seed/init_tables.py`（create_all，278 表）→ 迁移 |
| ③ | V147 的约束在空库上永远加不上 | V147 用 `CREATE TABLE IF NOT EXISTS` 建 4 张 `ai_chat_*` 表，并把 7 个 CHECK 约束与 `ON DELETE RESTRICT` 外键**写在建表语句内**（ORM 故意不重复声明，见 `ai_models.py` 注释）。create_all 先建出 ORM 形态后，V147 的 CREATE TABLE 整段被跳过 ⇒ 约束缺失 ⇒ `test_task3_chat_persistence.py` **10 条打红**。而 V147 又 `ALTER TABLE ai_chat_message / ai_chat_session`，所以它也**不能**在 create_all 之前跑（实测 pass1 时 V147 因这两张表不存在而失败）⇒ 两种顺序都不行 | 引导层加一步：create_all 之后 `DROP` V147 拥有的那 4 张表，再跑迁移，让 V147 自己完整建。**不改任何生产迁移**。另加一步对 DB 直接断言 7 个 CHECK 约束都在（否则 V147 静默变 no-op 时只表现为 test_task3 打红、根因极难查） |

**空库最终实测**（`audit_platform_ci_probe2`，走上述完整引导）：

| 测试集 | 结果 |
|---|---|
| `backend/tests/dsh_agent_panel/` | **508 passed / 0 skipped** |
| 其余 6 个后端文件 | **189 passed / 0 skipped** |
| `test_ai_chat_mcp_tools_data.py` | **25 passed / 0 skipped** |

⚠️ **缺陷 ①②③ 同样存在于此前已写好的 `dsh-agent-panel-mcp-data` job** —— 它也用裸
`postgres:16` + 只跑迁移。因为该 job 与整个 spec 一样是 `??` 未跟踪、**从未在 CI 真跑过**，
所以这三个缺陷此前没有机会暴露。已同步修正（两个 job 的引导步骤现在逐字一致）。

⚠️ **一处副作用，如实记录**：首次跑 `init_tables.py` 时忘了钉 `API_BASE_URL`，脚本末尾的
seed 端点回调打到了**本机在跑的 dev 后端**（连的是 `audit_platform`），向 dev 库写入了
幂等种子（`report-config/seed` 填了 153 行公式，其余为 "已加载 / 0 行"）。非破坏性、可重复，
但已在两个 job 与本地探针脚本里显式设 `API_BASE_URL=http://127.0.0.1:9` 阻断该回调。

⚠️ **一处与本 spec 无关的既有问题（只登记，不修）**：空库上 `V106__evidence_governance_attachment_versions.sql`
失败 —— `null value in column "id" of relation "service_identities"`（`create_all` 建出的
`service_identities.id` 没有 PG 侧默认值，而 V106 插入时不带 id）。不影响本 spec 的
722 条守卫，属证据治理域的空库引导问题，建议由该域单独立任务。

**归因型验收**（`governance-checks.yml` 是多 spec 共享文件，并发会话常同时改）：
改前后 job 数均 **160**，无增删；相对 HEAD 全文件**只有一个纯插入 hunk**
（HEAD 5292 行，零处 `dsh-agent-panel` 字样），插入块内恰好是本 spec 的 3 个
`dsh-agent-panel-*` job，插入块之外**逐行与 HEAD 完全一致** ⇒ 其余 157 个 job 一字未动。
（未用「其他 job 一个都没变」这类全局等值判据 —— 那在并发工作树下必假红。）

---

### 4. Task 15 的两个组件从未被挂载（最严重的一条假绿）

#### 实证

```
grep 'import Chat\w+ from' audit-platform/frontend/src/components/ai/*.vue
→ PlatformAiChatPanel.vue 只有：
    import ChatAttachmentPicker from './ChatAttachmentPicker.vue'
    import ChatReviewModeBar from './ChatReviewModeBar.vue'
```

`ChatMentionPicker.vue` 与 `ChatContextInspector.vue` **零宿主引用**：两个组件都存在、
各自的 vitest 全绿（23 条）、Task 15 标记 `[x]`，但**没有任何宿主 import 它们**。

#### 后果

浏览器里用户**打不出 `@`、看不到 Context Manifest**。Requirements 5.1 / 5.4 / 5.7 / 5.9
在运行产品里没实现，Properties 12 / 13 无浏览器落地 —— 交付的是「组件库」，不是「功能」。

#### 为什么 23 条 vitest 全绿也没发现

那 23 条直接 `mount(ChatMentionPicker)` / `mount(ChatContextInspector)`，
测的是「组件被挂载后行为对不对」，**从不问「有没有人挂载它」**。
挂载宿主是组件的**外部**事实，任何以组件自身为被测对象的单测都结构性看不见它。

这与 G7 的「模型声明 `column.group`、三向守卫 39 例全绿、任何 `.vue` 零引用
⇒ 两级表头 0/38 从未渲染」是同一形状：**声明齐全 + 单测全绿 + 零渲染宿主**。

#### 修复（三段缺一不可）

只加 import + 模板标签**不算修好** —— 那只是把死代码从「不渲染」变成「渲染了但没用」。

1. **`@` 触发链**：`watch(draft)` 按**活跃 `@` 词**（最后一个 `@` 之后不含空白）开关 picker。
   用 `watch` 而不是 `keydown`：程序化赋值（粘贴、Playwright 的 `fill()`）不产生按键事件。
   Escape（`stopPropagation`，否则 DshPanel 会把整个面板关掉）/ 点击输入区外 / `@` 词消失即关闭。
2. **已选项真的进入下一轮 run 的载荷**：`handleSend()` 把 `selectedMentions` 投成
   `{type, id}` 随 `POST /api/ai-chat/runs` 提交，发送后清空并 `mentionPickerEpoch += 1`
   强制重建 picker（否则上一轮高亮残留，用户以为引用还在）。
   同批补提交了此前同样收集完就丢的 `attachmentIds` / `reviewMode` / `sheetName`。
3. **manifest 投影**：store 存的是服务端**分组 dict**，组件契约要**扁平数组**，键名也不同
   （`status`/`used_tokens`/`reason`/`stale` ↔ `decision`/`token_estimate`/`reason_code`/`is_stale`）。
   直接绑上去 `v-for` 会遍历 dict 的值、渲染出 `manifest_version` 这类垃圾行，
   而 `manifest.length === 0` 的空态判断恒为 false。故新增 `utils/chatContextManifest.ts`
   做投影；**组件一行没动**（它有独立守卫锁着契约）。
   两条纪律：不发明数据（`jump_route` 服务端没给就是 `null`，前端不许自己拼路由 — Req 5.9）；
   不丢条目（未登记的分组键也落进结果，`decision` 退化为 `unavailable`）。

#### 通用守卫怎么防复发

新增 `src/components/ai/__tests__/AiRenderHostReachability.spec.ts`（**30 tests**）。
抓的是「**组件孤岛**」这个**类**，不是这两个具体组件 —— 按前缀扫 `src/components/ai/` 下
全部 `Chat*` / `Platform*` / `Dsh*`，以后新加组件忘接线会自动打红。三层判据缺一不可：

| 层 | 判据 | 防的是 |
|----|------|--------|
| 1 | 至少一个**非测试文件** import 它（`__tests__`/`*.spec.ts`/e2e 不算） | 完全的组件孤岛 |
| 2 | 引用方**真的把它当标签用**（`.vue`：`<Foo>`/`<foo-bar>`/`<component :is>`；`.ts`：出现在 import 语句之外，如注册表/懒加载） | import 了不用 —— 同样是死代码 |
| 3 | 判定基于**结构化解析**（注释感知的 import 解析 + 顶层 template 块提取），不是裸 grep 符号名 | 符号名出现在注释/字符串/import 行里被误判成"已使用" |

并附**反向自检**（判据自己不能恒真）：合成样本里「有 import 无标签」「注释里的标签」
「script 字符串里的标签」「`ChatMentionPickerV2` ≠ `ChatMentionPicker`」必须判为未使用；
PascalCase / kebab-case / `<component :is>` 必须放过。
另有两条判据自身不空洞的断言（扫到的组件清单 ≥6 且覆盖三类前缀；源文件集合 >200 且已排除测试文件）——
没有这两条，清单一旦扫空整个守卫会静默变成 0 条。

一个实现细节值得记：剥 JS 注释**不能**用 `src.replace(/\/\/.*$/gm, '')` ——
那会把 `'https://x'` 截断，于是同行后续的 import 被吃掉半行，解析结果静默变少。
必须写成识别引号状态的字符扫描（`stripJsComments`），并有一条专门守卫锁它。

#### 变异检验（M36–M41，前缀 `[渲染宿主]`，6/6 全 RED）

| 锚点 | 变异 | 结果 |
|------|------|------|
| M36 | 删 `PlatformAiChatPanel.vue` 里 `<ChatMentionPicker>` 模板标签（**保留 import**） | RED（点名判据 + 通用可达性判据各 1 条） |
| M37 | 同上，`<ChatContextInspector>` | RED（同上 2 条） |
| M38 | `@` 触发链断开（`watch(draft)` 不开 picker） | RED（4 条） |
| M39 | `handleSend` 丢弃已选 mention | RED（2 条） |
| M40 | `buildExtrasPayload` 不写 `mentions` 键 | RED（2 条） |
| M41 | `normalizeContextManifest` 投影恒空 | RED（4 条） |

M36/M37 是本条的**核心锚点**：它们精确复刻「import 在、标签没了」这个形态 ——
这正是只做一半接线的样子。`--check-anchors` 静态自检：**41/41 命中恰好 1 次**。

#### 浏览器实测（不看单测看 DOM）

Playwright 探针实证接线真的生效，而非"测试认为生效"：

- **mention**：`@` 后 **79ms** picker 可见，其搜索框**自动获得焦点**（`SEARCH_FOCUSED=true`）；
  填不存在的名字 → `mention-empty-state` 计数 1、文案「无匹配结果」（Property 13 三态互斥成立）。
- **manifest**：`context_ready` 真实载荷 =
  `{"manifest_version":"native-included-only-v1","token_estimate":0,"citation_count":0,`
  `"project_tools_enabled":false,"review_mode":false,"included":[]}` ——
  服务端**自己给了 0 条**（全局宿主、无 mention/附件/RAG 命中），投影如实返回 `[]`，
  组件如实渲染「暂无上下文信息」。**三层都对**。

⚠️ 由此发现 e2e 侧两个**判据缺陷**（不是产品缺陷），已一并修正，详见「已修复项 §5」。

#### 编译校验

`vite build` 走不通 —— HEAD 里一处**与本 spec 无关**的坏 import 挡住整张模块图
（见「未完成项 §7」）。改用 dev server 的 transform 管道逐模块校验（Vue 模板属性里的
中文引号 U+201C/U+201D 正是在这一步炸）：7 个模块全 **200**，三个 `.vue` 的 template
块内禁用字符**零命中**。

---

### 5. e2e 里 3 条 mention/manifest 用例的判据缺陷（接线后才暴露）

接线前这几条一直 skip 在「组件未挂载」上，**判据本身从未被执行过**，所以缺陷被 skip 挡住了。

| 用例 | 原判据 | 缺陷 | 修法 |
|------|--------|------|------|
| 搜索失败与空结果显示不同状态 | 把关键词填进**聊天 textarea** 后直接断言三态 | `ChatMentionPicker` 的 props 契约只有 `{host, open}`，**没有**接收查询词的 prop（宿主无权灌查询词）；组件打开时自己 `focusInput()` 等用户输入 ⇒ picker 恒停在 **idle 态**，三个 testid 一个都不在，`shown === 0` 恒红 | 改为往 **picker 自己的搜索框**填词（先断言它 `toBeFocused()`，把"打开即接管焦点"变成显式契约） |
| @ 触发 mention picker 且可键盘导航 | `@` 后直接对 `[role=option]` 按 ArrowDown | 同上：不搜就没有候选，等于测 idle 态（恒 0 条） | 先在 picker 搜索框搜词，再断言键盘导航 |
| 多选 mention 显示为 tag 并可移除 | 只断言 picker 内 `aria-selected` 翻转 | 只验了 picker 内部状态，**没验宿主是否真收到 `change`** —— 而"显示为 tag"正是宿主侧那一半 | 补断言宿主 `.platform-ai-chat-panel__mention-tags` 出现/消失（取消后必须归零，否则会把已取消的引用提交给下一轮 run） |

另外两处 `test.skip` 的前置判定用了 `locator.isVisible({timeout})` ——
该 API 是**即时判定**，`timeout` 不生效、不重试，等于没等。已改 `waitFor({state:'visible'})`。
skip 文案也换成实测过的可执行说明（原文案把"无候选"归因为"授权可见集为空"，
实测真因是**从未发起搜索**）。

---

## 🔴 未完成 / 未验证项（诚实记录）

### 1. 产物未入版本控制（CRITICAL）

**所有正式产物均为 `??` untracked 状态**，仅 `utils/sse.ts` 是 tracked（M）。

受影响产物：
- `.kiro/specs/dsh-agent-panel-integration/` 整个目录
- `backend/app/services/ai_chat/`（29 files，含 `mcp_tools.py`）
- `backend/app/routers/ai_chat_mcp.py`
- `backend/migrations/V147` + `V149`
- `tools/audit-data-mcp/`
- 前端 5 个新组件 + composable
- 后端全部测试文件（22 files，含 `test_ai_chat_mcp_tools_data.py`）
- Playwright 测试
- mutation runner（M01–M35）

> 例外：`backend/app/services/knowledge_index_service.py` 是**已跟踪**文件的 `M` 修改
> （纯增 `semantic_search_strict` 58 行 0 删），不在蒸发风险内，但需随同一 commit 提交，
> 否则 `test_ai_chat_mcp_tools_data.py` 的 `semantic_unavailable` 断言在 clean checkout 下会挂。

**风险**：工作树清理/重置将导致全部产物蒸发。CI 在 clean checkout 下**必定失败**（找不到文件）。

**建议**：尽快执行 `git add` 并提交到工作分支，或发起 PR。

### 2. Clean Checkout 运行验证（NOT VERIFIED）

由于产物未跟踪，clean checkout 下的 pytest/vitest/typecheck/lint/Playwright **无法在 CI 环境运行**。本地工作树验证通过，但 CI 层面未证明。

### 2b. `dsh-agent-panel-backend` job 缺 postgres service — ✅ **已修，见「已修复项 §3」**

原登记为「新发现，未修」。2026-08-16 已实测确认确有静默 skip
（sqlite 下 310 passed / **183 skipped** / exit **0**），并已补 service + 引导 + 硬断言。
补 service 后在**全新空库**上又抓出 3 个只在空库出现的 CI 缺陷（pgvector 镜像 /
缺 create_all 引导 / V147 约束静默 no-op），均已修复并实测
**508 + 189 + 25 passed，0 skipped**。详见「已修复项 §3」与 §3b。

唯一剩余的 CI 层面未证明项仍是**产物未入版本控制**（见 §1 / §2）——
job 定义写得再对，clean checkout 下找不到测试文件就还是跑不起来。

### 3. ChatMessageList.vue / ChatComposer.vue 独立文件

设计文档列出 `ChatMessageList.vue` 和 `ChatComposer.vue` 作为独立文件，实现中合并到 PlatformAiChatPanel.vue 内（860 行，功能完整）。这是合理实现决策，不影响功能。

### 4. DSH Project Allowlist 当前状态

DSH 通过 feature flag 控制，当前 allowlist 为空（实验阶段）。需经过：
- 双用户隔离测试通过
- 取消传播验证通过
- egress 监控确认无公网连接
- 运维签署后方可逐项目开放

### 5. 容量边界（配置值，非实测）

| 参数 | 配置值 | 实测 |
|------|--------|------|
| AI_CHAT_RATE_LIMIT_PER_MINUTE | 60 | 未负载测试 |
| AI_CHAT_MAX_ACTIVE_RUNS_PER_USER | 3 | 单元测试验证 |
| AI_DSH_MAX_ACTIVE_RUNS | 5 | 单元测试验证 |
| AI_DSH_QUEUE_LIMIT | 20 | 单元测试验证 |
| AI_DSH_RUN_TIMEOUT_SECONDS | 300 | 配置值 |
| AI_DSH_PROCESS_TTL_SECONDS | 600 | 配置值 |
| AI_MCP_MAX_CALLS_PER_RUN | 50 | 单元测试验证 |
| AI_MCP_MAX_BYTES_PER_CALL | 1MB | 单元测试验证 |

6000 并发用户目标需正式负载测试验证，当前仅逻辑层面有界。

### 6. 告警阈值

结构化指标已暴露（active runs / queue wait / latency / tokens / denials / cleanup failures），但告警阈值需 Ops 团队根据生产基线设定。

### 7. `vite build` 在 HEAD 上整体失败（**与本 spec 无关，只登记不修**）

```
error during build:
Could not resolve "../../composables/f0MasterLabels" from
  "src/components/workpaper/confirmation/alternativeF05/GtConfirmationAlternativeF05.vue"
```

真源在 `src/components/workpaper/confirmation/composables/f0MasterLabels.ts`，
从 `alternativeF05/` 出发正确写法是 `../composables/f0MasterLabels`（上一级），
现写成 `../../composables/`（**多上了一级**，指向不存在的 `workpaper/composables/`）。

- 该文件**已提交**、工作树干净，最后触碰它的是 `11c5309f`「…**6 Vue import 深度**…」——
  属那批 import 深度批改的回归，不是并发会话在途改动。
- 影响面：**整个前端生产构建挂掉**（rollup 解析整张模块图，任何一处解析失败即终止），
  于是任何人想用 `vite build` 验证自己的前端改动都会被这一条挡住。
- 属函证域（F0）而非本 spec，且遵守「同一文件禁与并发会话并行编辑」，故只登记。
  修法是一个字符级改动：`../../composables/` → `../composables/`。
  **建议由函证域立刻单独修**，它挡着所有人的构建校验。
- 本 spec 的编译校验因此改走 dev server transform 管道（见「已修复项 §4 · 编译校验」）。

### 8. Playwright 全量跑仍有 4 条 failed（**均为本 spec 之外的既有问题**）

2026-08-22 实测 `37 passed / 4 failed / 19 skipped`。接线前同一文件是 `36 / 6 / 18`，
差额就是本次修的两条（`搜索失败与空结果` failed→**passed**、`Context Manifest` failed→skip 并补了无条件真断言）。
剩下 4 条在接线前后**完全一致**，与 Task 15 无关：

| 用例 | 现象 |
|------|------|
| A · 面板打开后焦点进入输入区 | 焦点未落到输入区 |
| B · 无项目上下文时项目工具禁用并显示中文原因 | 断言未过 |
| C · 对话 history 可加载且按时间正序 | 断言未过 |
| D · 非底稿宿主禁用复核模式并显示中文原因 | `openAiPanel` 点击被上层节点拦截（`subtree intercepts pointer events`），属 helper 的点击稳定性问题 |

未在本任务内诊断（超出「Task 15 接线」范围），建议单独立任务逐条查。

### 9. Context Manifest **非空**路径仍未在浏览器验过

服务端本轮 `context_ready` 下发 `included: []`（全局宿主、无 mention/附件/RAG 命中），
所以「清单列出条目」这条路径只验到了空态。要真验非空：切**项目宿主** → `@` 引用
至少一份底稿/附注（或挂附件）→ 发问 → 断言条目数与 `token_estimate`。
同理 `@ 触发…键盘导航` 与 `多选 mention…可移除` 两条仍 skip 在「无可引用候选」上 ——
全局宿主下搜「审」实测返回 0 条。三条都需要**项目宿主 + 已授权候选**的夹具。
e2e 夹具已存在可用项目（`TEST_PROJECT_ID=2aa00f57-…`，含 FIX-F / FIX-I6 底稿），
但本文件目前**从不引用它**（`TEST_PROJECT_ID` 出现 0 次），全程在全局宿主下跑。
补一个「进项目再开面板」的 helper 即可让这三条转真跑 —— 建议作为下一步。

## 后续行动（按优先级）

1. **立即**：将所有 `??` 产物 `git add` 并提交到工作分支
2. **立即**：向 governance-checks.yml 注册 CI job（产物 tracked 后）
2b. ~~给 `dsh-agent-panel-backend` job 补 postgres service~~ ✅ **已完成**（见「已修复项 §3」）
2c. **移交建议**：空库上 `V106` 失败（`service_identities.id` 无 PG 默认值）属证据治理域的
   空库引导问题，与本 spec 无关，建议该域单独立任务
3. **近期**：开展 6000 用户负载测试，校准配额配置
4. **近期**：运维设定生产告警阈值
5. **后续**：按验收流程逐项目开放 DSH allowlist
6. **后续**：评估 ChatMessageList/ChatComposer 是否需拆分（当前 860 行可控）

## 结论

Task 35 验证维度全部通过（三件套零诊断 / AC 120/120 / Property 40/40 / 依赖图无冲突 /
变异 **35/35 实跑全 RED** / 迁移幂等 / 临时文件清理完毕），守卫实测
backend **722 passed** / frontend 239。

Task 35 之后共补三处：

1. **责任真空** —— MCP 7 个工具的取数实现（Task 25 与 Task 26 都不拥有它）已从空占位
   换成真实取数，补端到端数据流守卫 25 条 + 变异锚点 8 条（全 RED）。见「已修复项 §1」。
2. **Task 33 的 10 条变异从「静态已验证」补成真跑** —— 暴露 6 个守卫缺陷 + 1 个脚本缺陷，
   全部修复后 15/15 全 RED；变异脚本自身加固（expect_test 必须是真实测试名 + 反向自检）。
   见「已修复项 §2」。
3. **`dsh-agent-panel-backend` 的静默 skip** —— 实测确认无 PG 时 183 条静默跳过而 job 仍绿；
   补 service 后在**全新空库**上又抓出 3 个只在空库出现的 CI 缺陷（pgvector 镜像 /
   缺 create_all 引导 / V147 约束静默 no-op），均已修复并在空库实测
   508 + 189 + 25 passed、0 skipped。见「已修复项 §3」。

> 这三处是同一个假绿家族的三种形态：①**被消费了但没人检查消费到了什么**
> ②**守卫存在但抓不到**（且「静态检查通过」被当成了「已验证」）
> ③**测试存在且 CI 绿但从未真跑**。共同判据要求只有一条：判「某能力是否真生效」
> 必须落到**真实执行的可观测结果**上 —— 不是字符存在、不是结构完整、不是退出码为 0。

唯一未满足项仍是 **产物未入版本控制**。按 spec 自身条款（"spec 目录当前若仍为 `??`
SHALL 视为未完成"），**本 task 标记为 `[-]`（有条件完成）**，完全闭合需等待
git add + commit + CI 通过。

> 🔴 §3b 里那 3 个 CI 缺陷本身就是「产物未入库」的直接后果：`dsh-agent-panel-mcp-data`
> job 从写好起就带着裸 `postgres:16` + 缺引导两个错，但因为整个 spec 是 `??`、
> **CI 从未真跑过这个 job**，所以错了几天都没人知道。这条比任何论证都更能说明
> 「入库 + 让 CI 真跑一次」不是收尾流程而是验证手段本身。
