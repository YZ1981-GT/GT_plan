# DSH Agent Panel Integration — 收口复盘

## 概览

| 维度 | 状态 |
|------|------|
| Spec 三件套诊断 | 零错误 |
| AC 覆盖率 | 120/120（所有 AC 被 task 引用） |
| Property 覆盖率 | 40/40（所有 Property 被 task 引用） |
| Task 依赖图 | 35 tasks / 21 waves / 无同波强依赖 |
| 变异 --check-anchors | **47/47 通过**（15 Task 33 + 12 假绿修复 + 8 MCP 取数 + 6 渲染宿主 + **6 引用完整性**） |
| 变异**实跑** | **47/47 全 RED**（15 + 12 + 8 + 6 + **6**，GREEN/MISS/WRONG 各 0） |
| 守卫实测 | backend **722 passed** / frontend **324 passed / 18 files**（2026-08-22；289/16 + 引用完整性 15 + 工时深链 10） |
| Playwright 实跑 | **37 passed / 4 failed / 19 skipped**（4 failed 中 **3 条是本 spec 自己的 AC**，归因已更正 → 「未完成项 §8」） |
| Clean-DB CI 引导实测 | 全新空库上 508 / 25 / 189 passed，0 skipped |
| 最新迁移号 | **V150**（V147 + V149 + **V150** 为本 spec 新增） |
| 迁移幂等性 | 三个迁移均幂等；V150 已连续应用三次实测无报错 |
| **干净环境端到端** | ✅ 干净 venv + 全新空库：三步引导全通（147 executed / 仅 V106 失败），189 + 25 passed / 0 skipped |
| **产物入库** | ✅ commit `55c5e0fe`（154 files），已推 origin |
| **AC↔Property 覆盖** | 🔴 Task 引用 120/120 但 **Property 仅覆盖 94/120** → 「未完成项 §10」 |
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

### 6. AC 1.5「新窗口打开平台聊天路由」在已入库的交付里是坏的（P0 收口，2026-08-22）

#### 实证

```
git show 55c5e0fe:audit-platform/frontend/src/router/index.ts
  → '/ai-chat' 的 path 声明数 = 0
  → 原文写着：// ── AIChatView / AIWorkpaperView routes removed (Phase 11) ──
              //    Do NOT re-add these routes.
```

而同一 commit 里 `DshPanel.openInNewWindow()` 执行的是
`window.open('/ai-chat', '_blank', 'width=1200,height=800')`
⇒ 点「在新窗口打开」落到 `NotFound`。

Task 9 标 `[x]` 且 Validates 列了 **1.5**；Task 34 的 Playwright 也声称覆盖 `new-window`。

#### 为什么全绿

e2e 那条用例（`dsh-agent-panel-acceptance.spec.ts`）的判据是四条 **URL 断言**：

```ts
expect(newPage.url()).toContain('/ai-chat')      // ← 对 404 恒真
expect(newPage.url()).not.toContain('3080')
```

**Vue Router 的 catch-all（`/:pathMatch(.*)*`）不改变 URL。** 所以新窗口渲染的是
404 页面时，四条断言全部照样通过。这是「断言我们请求了什么」而不是
「断言用户看到了什么」——与 memory 记的「grep 式守卫只查字符串存在」同族，
只不过换到了 e2e 层，因此更难察觉（谁都以为浏览器测试就是行为测试）。

**根因归类**：AC 1.5 属于**26 条「有 Task 引用但零 Property 覆盖」**的 AC 之一
（见「未完成项 §10」）。它被 Task 9 引用所以计入了 CLOSURE 声称的「AC 120/120」，
但 40 个 Property 里没有一条 `Validates 1.5` ⇒ 唯一判据就是那条有缺陷的 e2e。
**「AC 被 task 引用」只证明有人负责，不证明有可执行判据。**

#### 修复（四段）

| # | 落法 |
|---|------|
| ① 路由 | `router/index.ts` 注册顶层 `/ai-chat`（`name: 'AIChatWindow'`）。放顶层而非 `DefaultLayout` 子路由 —— 1200x800 弹窗里主布局侧栏/顶栏只会挤占对话区 |
| ② 上下文 | `openInNewWindow()` 带 `project_id` / `wp_id` query（取**原始 route 值**而非 `aiHost` 的派生结果，新窗口用同一个 `buildAmbientHost` 自行推导，保持单一真源）。不带参数会让新窗口无条件退回全局知识模式，丢掉用户正在看的项目/底稿 |
| ③ 视口 | `AIChatView.vue` 的 `height:100%` → `100vh/100dvh` + `overflow:hidden`。独立窗口不套 `DefaultLayout`，`html/body/#app` 没有高度链 ⇒ `100%` 塌成 `auto` |
| ④ 判据 | e2e 补**第二层**断言：`.gt-not-found` 计数为 0 **且** `.platform-ai-chat-panel` 可见。两条都要 —— 只查 404 不存在的话，白屏（组件加载失败）也会放过 |

#### 通用守卫：`FrontendReferenceIntegrity.spec.ts`（15 tests）

抓的是「**引用了不存在的目标**」这个**类**，不是 `/ai-chat` 这一个实例。
新建 `src/__tests__/_helpers/frontendSourceScan.ts` 作共享扫描工具
（`stripJsComments` 收敛到这里作单一真源，它那个坑不该有第二份副本）。

| 节 | 判据 | 防的形态 |
|---|------|---------|
| §1 模块引用 | 全仓生产源码（5112 个文件，已排除测试）的相对/别名 import 必须可解析 | import 深度错 ⇒ 整个 `vite build` 挂掉 |
| §2 路由导航 | 写死的 `window.open` / `router.push` / `router.replace` / `to=` 目标必须匹配到**非 catch-all** 的声明路由 | 路由孤儿 ⇒ 用户点击落 404 |

**关键设计 —— catch-all 必须显式排除**：若把它算进可达集合，任何路径都"匹配得上"，
判据恒真。这与 AC 1.5 那条 e2e 失效的机制完全相同，所以有一条测试专门锁它
（`判据自检：catch-all 不得参与匹配`，变异 MR2 验证有效）。

**豁免桶的语义**：当前有 6 个文件带坏 import（`components/ai/index.js` 死 barrel +
4 个 import 不存在的 `@/api` 的旧组件 + `views/ai/AIWorkpaperView.vue`），
登记在 `KNOWN_DEAD_MODULE_FILES`。语义是「**这是死代码待删**」而不是「这个错可以接受」，
因此配了三条约束：①清单**只减不增** ②每条必须给 >10 字的原因
③另有一条断言它们**确实零活消费方**（死代码内部互引与自动生成的 `components.d.ts` 不算）——
一旦有人给它们接上真实消费方，守卫打红要求先修 import。
`index.js` 指向的 `AIChatPanel.vue` 正是本 spec 删掉的，所以这条悬挂引用**属本 spec 责任**。

**判据不空洞的自检**：扫描面 >2000 个生产文件 · 路由声明 >100 条 · catch-all 必须被解析到 ·
`children:` 出现次数恰好 1（本仓库是单层嵌套，多一层就会让「子路由父路径 = `/`」的拼接失效，
必须打红而不是静默给出错误的可达集合）。

#### 守卫立刻抓到 2 个新缺陷（同形态，非本 spec 域）

它证明了「抓类而不抓实例」的价值 —— 第一次跑就发现两个已在生产的 404：

| 位置 | 原写法 | 真实路由 | 修法 |
|---|---|---|---|
| `ManagementDashboard.vue:58`「前往人员管理」按钮 | `$router.push('/staff')` | `settings/staff` | `'/settings/staff'` |
| `ManagerDashboard.vue:829` `goToWorkHoursApprove()` | `router.push('/work-hours/approve')` | 只有 `work-hours`，审批是 `WorkHoursPage` 里 `name="approve"` 的 tab | `{ path:'/work-hours', query:{ tab:'approve' } }`，并给 `WorkHoursPage.vue` 加 query 深链支持（tab 白名单 + `approve` 仍受 `can('approve_workhours')` 门控，无权用户手敲参数也只看到默认页） |

#### 同批修掉的 7 处 import 深度错

| 文件 | 错写 | 真源 |
|---|---|---|
| `alternativeF05/GtConfirmationAlternativeF05.vue` | `../../composables/f0MasterLabels` | `../composables/` |
| `alternativeF06/GtConfirmationAlternativeF06.vue` | 同上 | 同上 |
| `diffReconcile/GtConfirmationDiffReconcile.vue` | `../../composables/confirmationRiskPush` | `../composables/` |
| `fraudRisk/GtConfirmationFraudRisk.vue` | 同上 | 同上 |
| `g4-bond-investment-ecl/impairment/G4TabEclMeasurement.vue` | `../../composables/useG4EclFormulaEngine` | 真源在 `src/composables/`（跨 4 级）⇒ 改用 `@/composables/` 别名 |
| `alternativeF05/composables/useAlternativeF05Data.ts` | `../alternativeD05/alternativeD05Types` | `../../alternativeD05/` |
| `alternativeF06/composables/useAlternativeF06Data.ts` | 同上 | 同上 |

**共同成因**：照抄相邻 import 的深度。`G4TabEclMeasurement.vue` 里其余
`../../composables/xxx` 全部正确（指 `workpaper/composables/`），只有这一条的真源
在顶层 `src/composables/`；`useAlternativeF05Data.ts` 里 `../alternativeF05Types`
只上一级是对的，而 `alternativeD05` 是**兄弟目录**要上两级。
两处都已把「为什么深度不同」写进注释，防下一个人再照抄。

#### 验证

- **静态扫描**：0 条未登记坏 import（5112 个生产文件）
- **rollup 解析阶段**：8GB 堆下无 `Could not resolve`（完整 build 仍因本机内存 OOM 跑不完 ——
  项目 `package.json` 的 `build` 脚本本身没配 `NODE_OPTIONS`，属既有环境问题，非本次引入）
- **守卫**：15 tests 全 passed
- **变异**：锚点 **MR1–MR6，静态 6/6 命中恰好 1 次，实跑 6/6 全 RED**
  （GREEN / ANCHOR-MISS / WRONG-TEST 各 0），每条都精确打红预期那一条测试；
  文件 sha256 字节级复原已校验，无 `.bak` 残留。
  结果记 `mutation_results_reference_integrity.json`（未覆盖既有四份记录）

| 锚点 | 变异 | 打红的测试 |
|---|---|---|
| MR1 | 删掉 `/ai-chat` 路由声明（**精确复刻 AC 1.5 的原始缺陷形态**） | `AC 1.5：新窗口聊天路由 /ai-chat 已注册` |
| MR2 | 让 catch-all 参与匹配（判据恒真的核心形态） | `判据自检：catch-all 不得参与匹配` |
| MR3 | 把已修好的导航目标改回不存在的路由 | `所有写死的站内导航目标都能匹配到非 catch-all 路由` |
| MR4 | `stripJsComments` 换成朴素正则（会截断 `'https://x'`） | `判据自检：stripJsComments 不得截断含 // 的字符串` |
| MR5 | 把一个生产 import 改成不存在的路径 | `不存在未登记的坏 import` |
| MR6 | 路径匹配放宽成前缀式（段数不等也算匹配） | `判据自检：动态段匹配任意单段，段数必须相等` |

CI：`dsh-agent-panel-frontend` job 追加两步（守卫实跑 + 锚点静态检查）。
该 job 用**目录级** glob 收 `src/components/ai/__tests__/`，本守卫不在该目录内，
故必须显式列出。归因型验收：`governance-checks.yml` 相对 HEAD **单个纯插入 hunk、
13 行零删除、job 数 161 → 161 不变**，其余 160 个 job 一字未动。

#### 通用教训

**「浏览器测试」不等于「行为判据」。** 只要断言的是请求侧的量（URL、发出的参数、
调用了哪个函数），就仍然停在「我们打算做什么」，而没有触及「用户实际看到什么」。
本条的 URL 断言、G7 的 `column.group` 声明、Task 15 的组件孤岛，
三者是同一形状的三个层级：**声明/请求齐全 + 判据齐全 + 渲染结果为空**。

判据要求：任何「跳转 / 打开 / 渲染」类能力，守卫必须至少有一条断言**目标真的出现了**
（DOM 节点可见、或目标声明在真源里存在），而不只断言「我们朝那个方向发了个请求」。

---

### 7. 干净环境端到端复现：挖出 3 层依赖缺口 + 1 个真实生产缺陷（2026-08-22）

#### 方法

不再用 CI 迭代（一轮 10+ 分钟、只暴露一层）。改为本地建**干净 venv**
（只装 `backend/requirements.txt`）+ **全新空库** `audit_platform_dep_probe`
（`pgvector/pgvector:pg16`，与 CI service 同镜像），逐字复现 CI 的三步引导。
一轮 30 秒。

#### 挖出的 3 层依赖缺口

| 层 | 报错 | 根因 | 修法 |
|---|---|---|---|
| 1 | `TypeError: 'NoneType' object is not callable` @ `mapped_column(Vector(1024))` | `pgvector` 不在 requirements，而 `ai_models.py` 有 `except ImportError: Vector = None` 的 fail-open ⇒ 缺包被伪装成看不懂的 TypeError | `pgvector==0.4.2` |
| 2 | `ModuleNotFoundError: No module named 'psycopg2'` | `init_tables.py:31` 把 URL 的 `+asyncpg` 换成 `+psycopg2` 用同步 `create_engine`，而 requirements 只有 `asyncpg` | `psycopg2-binary==2.9.11` |
| 3 | `ModuleNotFoundError: No module named 'mcp'` → 装上后变 `No module named 'mcp.server.fastmcp'` | ① CI job 只装 `backend/requirements.txt`，漏了 `tools/audit-data-mcp/requirements.txt`（`test_audit_data_mcp_server.py` 的 17 条靠它）② 该文件写 `mcp>=1.14.0` **无上界**，clean checkout 装到 `mcp 2.0.0`，而 FastMCP 在 2.0 里被移出 `mcp.server` 命名空间 | CI 补装该文件 + 约束改 `mcp>=1.14.0,<2` |
| 4 | CI 上 `505 passed, 1 skipped` | **job 无 redis service**（实测整个 workflow 161 个 job 一个都没配）。`test_task5_run_coordinator.py:581` 有 `pytest.skip("need Redis (Stream 回放)")` —— `TestRedisStreamBackend` 覆盖 Req 4.12 的真实 Redis Stream 路径（TTL / MAXLEN / 跨实例回放），其余用例走 `_no_redis` 内存镜像。无 Redis ⇒ 该类整体 skip ⇒ ① 判据从未在 CI 执行 ② 本 job 的「出现任何 skipped 即打红」硬断言必红 | 补 `redis:7-alpine` service + `REDIS_URL`（键名已核对 `config.py`）。本地有 Redis 时实测该类 **1 passed**（不再 skip） |

> 🔴 **第 3 层是时间炸弹的教科书案例**：代码一行没改，上游发 2.0 就崩。
> 实测对比 —— 主环境 `mcp 1.28.1`（`import mcp.server.fastmcp` OK）
> vs 干净 venv 装最新 `mcp 2.0.0`（ModuleNotFoundError）。
> 这正是 memory 铁律「添加依赖用精确或固定版本，不用开放范围」要防的。
>
> 🔴 **静态扫描对第 2 层结构性失效**：我写脚本扫了引导路径 86 个文件的第三方顶层
> import 与 requirements 对账，`psycopg2` **一次都没出现** —— SQLAlchemy 是
> **按方言动态 import** 驱动的（`postgresql/psycopg2.py::import_dbapi`），
> 源码里没有任何一处直接 `import psycopg2`。
> ⇒ 「扫 import 对账」这类检查抓不到驱动类依赖，只有真在干净环境跑一次才暴露。

#### 挖出的真实生产缺陷：`ai_chat_message.seq` 的 BIGSERIAL 永不落地

**实证（两库 schema 逐列对比，`ai_chat_*` 全部列）**：

| 库 | `seq` 的 `column_default` | `is_nullable` |
|---|---|---|
| dev `audit_platform` | `nextval('ai_chat_message_seq_seq'::regclass)` | **NO** |
| 干净库 | **（无）** | **YES** |

且这是**唯一一处**「dev 有而 clean 无」的高危差异（范围收敛，不是一批）。

**根因**：V147:284 写的是

```sql
ALTER TABLE ai_chat_message ADD COLUMN IF NOT EXISTS seq BIGSERIAL;
```

`BIGSERIAL` 展开为「BIGINT + 建序列 + SET DEFAULT nextval + NOT NULL」，
但 `ADD COLUMN IF NOT EXISTS` 的语义是**整句跳过**。而 `seq` 在 ORM 里也声明了
⇒ 全新环境的标准引导顺序下：

```
① create_all()      ← 按 ORM 建出 nullable、无 default 的 seq 列
② run_pending()     ← V147 那句被 IF NOT EXISTS 跳过
⇒ 序列永不创建，seq 恒 NULL
```

**后果（已实测打红，不是理论）**：`load_recent_history()`（Req 4.10 / Property 10）
排序键是 `ORDER BY created_at DESC, seq DESC`。`created_at` 默认 `now()` =
**事务开始时刻**，同一事务内多条消息时间完全相同，全靠 `seq` 定序。
seq 恒 NULL ⇒ 二级排序失效 ⇒ **同一时间戳的消息返回顺序不确定**。
干净库上 `test_task3_chat_persistence.py` 的「全量取回顺序仍是插入序（含第 6/7 条
同一时间，靠 seq 定序）」打红（第 7 条排到第 6 条前面）；同一测试在 dev 库上是绿的。

> 🔴 **这是「已修复项 §3b」那个坑的第二种形态**。§3b 处理的是
> `CREATE TABLE IF NOT EXISTS`（解法：引导时 DROP 那 4 张表让 V147 自己建），
> 但 `ai_chat_message` 是**既有表**、V147 只 `ALTER` 它、不在 DROP 列表里
> ⇒ `ADD COLUMN IF NOT EXISTS` 这一类完全没被覆盖，同一个坑第二次生效。
>
> 更一般的形态：**ORM 声明追平了迁移 ⇒ 迁移变 no-op ⇒ 迁移独有的属性
> （序列 / DEFAULT / NOT NULL / CHECK）静默丢失**。凡是「ORM 与迁移同时声明同一列」
> 的地方都要问一句：迁移侧有没有 ORM 侧表达不了的属性？

**修法 —— 新增 V150 而不是改 V147**：V147 已在 dev/生产应用过，改它会触发
`MigrationRunner.detect_checksum_drift` 报漂移。V150 幂等补齐：
建序列 → 绑定 OWNED BY → setval 推游标 → SET DEFAULT → 回填历史 NULL 行
（按 `(created_at, id)` 定序，不能只按 created_at 也不能无 ORDER BY，
否则回填结果本身不确定）→ 再推游标 → 补 NOT NULL。

**验证**：
- 干净库应用 V150 → `executed: ['150']`，schema 与 dev 库**逐字一致**
- **幂等**：连续再应用两次无报错，schema 保持
- 打红的那条测试**转绿**

#### 干净环境的三个测试集实测

| 集合 | 结果 | 与声称值对比 |
|---|---|---|
| 其余 6 个后端文件 | **189 passed / 0 skipped** | ✅ 与 GUARD_MANIFEST 的 189 一致 |
| `test_ai_chat_mcp_tools_data.py` | **25 passed / 0 skipped** | ✅ 与声称的 25 一致 |
| `backend/tests/dsh_agent_panel/` | **520 passed / 1 failed** | 数字已增长（508 → 520）；那 1 条见下 |

**那 1 条 failed 已精确归因到并发会话的在途改动，不属本 spec 本次改动**：
`test_task23_address_mention.py::test_search_address_returns_proper_fields`
mock 的是 `address_registry.search`，而**工作树版本**的
`mention_service._search_address` 已被改成调 `address_registry.get_domain`
（该文件 `git diff` 为 **+598/−310**，属并发会话正在进行的 mention 域重构）。
**HEAD 版本用的是 `search`**，即该测试在 HEAD 上是绿的。
⇒ 需要那个会话同步测试的 mock 目标。本次遵守「同一文件禁与并发会话并行编辑」，只登记不改。

#### CI 侧的闭环确证（run 32582092281，含 pgvector + psycopg2）

| job | 结论 | 变化 |
|---|---|---|
| `dsh-agent-panel-frontend` | ✅ success | 三轮均绿（含 P0 新增的两个守卫） |
| `dsh-agent-panel-mcp-data` | ✅ **success** | **首次转绿** —— 25 tests 在 CI 上真跑通了 |
| `dsh-agent-panel-backend` | ❌ failure | **不再挂 Bootstrap**，前进到 `Phase A 守卫` |

Bootstrap 步骤日志：`migrations executed: 147 failed: ['106']` ——
与本地干净库**逐字一致**，证明那套三步引导在 runner 上成立。

Phase A 的实际结果是 `2 failed, 505 passed, 1 skipped`：

1. `test_task3_chat_persistence.py::test_history_returns_most_recent_n_ascending_with_real_metadata`
   —— **正是本地干净环境发现的 seq 缺陷，CI 独立复现** ⇒ V150 的必要性双重确认
   （V150 在下一个 commit 才提交，该轮尚未包含它）。
2. `test_task5_run_coordinator.py::TestReconnectAndDrain::test_drain_emits_identifiable_abort_frame_without_id`
   —— 本地（有 Redis）实测 drain 相关 **3 passed**，CI（无 Redis）红。
   该用例自身用 `_no_redis`，但 `coordinated` 是 **module-scope** 夹具，
   同 module 内的 Redis 环境差异会波及它。**补 redis service 后待下一轮验证**，
   不声称已修。
3. `1 skipped` = 第 4 层缺口（见上表）。

#### 附带发现（登记，不修）

1. **dev 库缺 V149 的全部产物** —— 干净库有 `ai_chat_mcp_call_log`（11 列）、
   `ai_chat_mcp_token_revocations`（5 列）、`ai_chat_runs.mcp_calls_used / mcp_token_issued /
   mcp_total_bytes`，dev 库**一个都没有** ⇒ V149 在 dev 库上从未成功应用
   （很可能是加了迁移后没重启后端）。含义：本 spec 的 MCP token 相关测试在 dev 库上
   跑的时候，那些表/列并不存在。建议重启后端让 V149 应用后复跑一次。
2. **`httpx>=0.27.0`** 在 `tools/audit-data-mcp/requirements.txt` 里同样无上界，
   属同类风险（本次只修了有实证的 `mcp`）。

---

### 8. 仓库级发现：106/160 failure job 的分类（挖 CI 时的副产品）

`gh run view 32575246116 --log-failed` 全量日志（158539 行）按 job 分组统计：

| 分类 | job 数 | 说明 |
|---|---|---|
| **pgvector 缺失同源** | **38** | 横跨 D/E/F/G/H/K/L/N 全部循环 + ACNR/报表/公式/x3/wp-import-export |
| **fakeredis 缺失** | **41** | 见下 |
| 断言失败 | 3 | 各自的业务问题 |
| baseline/门禁超限 | 2 | — |
| 未匹配特征 | 20 | 需逐个看 |

#### pgvector 那 38 个：本次修复对**全部**生效（已验证，不夸大）

先按「pip install 命令里有没有 `backend/requirements.txt`」分类，得出「14 个只装部分包
⇒ 修复无效」。**这个判据是错的** —— 复核发现那 14 个写的是
`pip install -r requirements.txt`（无 `backend/` 前缀）但配了
`defaults: working-directory: backend`，指的是同一个文件。修正判据后：

```
24 个  显式 -r backend/requirements.txt
 7 个  -r requirements.txt + defaults.working-directory: backend
 7 个  -r requirements.txt（step 无 wd，但既然挂在 pgvector 上说明 requirements 装成功了）
———
38 个  全部装完整 requirements ⇒ 修复全部生效
```

> 教训：判影响面时「命令字面量」不是判据，要把 `working-directory` /
> `defaults` 一起算进去。我第一版脚本就低估了 14 个。

#### fakeredis 那 41 个：**从写好起从未执行过任何测试断言**

`backend/tests/conftest.py:40` 有**顶层无兜底**的 `import fakeredis.aioredis`
（对比同文件里 hypothesis 那段是 `try/except`）。conftest 由 pytest 自动加载
⇒ 任何在 `backend/tests/` 下跑 pytest 的 job 都必须有 fakeredis。
而这 41 个 job 装的是 `pip install pytest==8.4.2`（或 `pytest hypothesis` 之类）
⇒ **在 collection 阶段就挂，一条断言都没跑过**。

同一文件紧接着还 import 了 `httpx` / `sqlalchemy` / `app.core.database` /
`app.models.base` —— 即「只装 pytest 就能跑纯静态测试」这个假设从一开始就不成立。

**不在本 spec 范围内修**（41 个 job 分属多个 spec，且让它们开始真跑会暴露各自积压的
真实失败，需要各负责人处理）。**移交建议**：把这些 job 的 install 步骤统一改成
`-r backend/requirements.txt`，并预期会暴露一批此前从未被执行的断言。

---

## 🔴 未完成 / 未验证项（诚实记录）

### 1. 产物未入版本控制 — ✅ **已解除**（2026-08-22）

原文记载「所有正式产物均为 `??` untracked」。**该状态已不成立**：

- commit **`55c5e0fe`**「feat(ai): DSH Agent 面板平台化集成（PlatformAiChatPanel 统一宿主）」
  一次性纳入 **154 个文件**，含整个 `.kiro/specs/dsh-agent-panel-integration/`、
  `backend/app/services/ai_chat/`、V147 + V149、`tools/audit-data-mcp/`、
  前端组件与 composable、后端 22 个测试文件、mutation runner、
  `governance-checks.yml` 的 3 个 job（+232 行）。
- 分支 `work/2026-08-22-dsh-agent-panel-integration` 已推到 `origin`。

> ⚠️ 本节与 `GUARD_MANIFEST.md` 的「Artifact Tracking Status」在入库后**过期了 6 天没人更新**，
> 期间任何接手方读到的都是「产物会蒸发、CI 必挂」的错误前提。
> **教训**：收口文档里的「阻塞项」必须在解除时立刻改，否则它从证据退化成误导 ——
> 判「某产物入没入库」的成本只有一条 `git status --porcelain -- <path>`，
> 没有理由让文档替代实测。

### 2. Clean Checkout 运行验证 — 🔴 **CI 已真跑，两个 job 失败（实证，已定位并修）**

原文写「三个 CI job 至今没有一次成功记录」。**说法不准确** —— 实测
`gh run list` 显示 `55c5e0fe` 的 push **已经触发过 workflow**
（`on: push: branches: ['work/**']`，不需要 PR），而且**两个 workflow 都 failure**。
不是「没跑过」，是**跑过、失败了、没人看**。

`gh run view 32575246116`（governance-checks，160 个 job）里三个 spec job 的真实结论：

| job | 结论 |
|---|---|
| `dsh-agent-panel-frontend` | ✅ **success** |
| `dsh-agent-panel-backend` | ❌ failure — 挂在 `Bootstrap schema` 步骤 |
| `dsh-agent-panel-mcp-data` | ❌ failure — 同一步骤、同一根因 |

> 附带事实：该 run 共 **106 / 160 个 job failure**。仓库 CI 整体是红的，
> 与本 spec 无关，但意味着「CI 绿」在本仓库当前不能作为任何判据。

#### 根因（完整 Traceback 已抓到）

```
File "backend/scripts/seed/init_tables.py", line 6, in <module>
  from app.models.base import Base
File "backend/app/models/__init__.py", line 96, in <module>
  from app.models.ai_models import ...
File "backend/app/models/ai_models.py", line 681, in KnowledgeIndex
  embedding_vec = mapped_column(Vector(1024), nullable=True)
                                ^^^^^^^^^^^^
TypeError: 'NoneType' object is not callable
```

**`pgvector` Python 包不在 `backend/requirements.txt` 里。**
而 `ai_models.py` 对它做了 fail-open 兜底：

```python
try:
    from pgvector.sqlalchemy import Vector
except ImportError:
    Vector = None
```

于是「依赖没装」**不在 import 处报错**，而是推迟到类定义时抛一个指向
`mapped_column` 的 `TypeError` —— 完全看不出是缺包。本地环境早已装了它
（实测 `pgvector 0.4.2`），所以这个缺失**只在 clean checkout 暴露**。

`set -euo pipefail` 让脚本在第 ② 步就退出，所以引导步骤里的 migration 命令
（第 ③ 步）根本没执行 —— 「已修复项 §3b」那套空库引导逻辑本身**尚未在 runner 上验证过**。

#### 修复（两层，逐层暴露）

**第一层 `pgvector==0.4.2`** —— 已验证生效：下一轮 CI 的日志出现
`Loaded 82 model modules, skipped 0`（此前在 import 阶段就崩），
说明 ORM 模型全部加载成功。

**第二层 `psycopg2-binary==2.9.11`** —— 同一轮暴露的下一个缺失：

```
File "backend/scripts/seed/init_tables.py", line 32, in <module>
  engine = create_engine(DB_URL)
File ".../sqlalchemy/dialects/postgresql/psycopg2.py", line 697, in import_dbapi
  import psycopg2
ModuleNotFoundError: No module named 'psycopg2'
```

`init_tables.py:31` 把 URL 的 `+asyncpg` 换成 `+psycopg2` 后用**同步**
`create_engine` 建表，而 requirements 里只有 `asyncpg`。

> 🔴 **这一条静态扫描抓不到**。我写了个脚本扫引导路径（86 个文件）的第三方
> 顶层 import 与 requirements 对账，结果只报了 `dotenv` / `pydantic`
> 两个传递依赖的误报，**psycopg2 一次都没出现** —— 因为 SQLAlchemy 是
> **按方言动态 import** 驱动的，源码里没有任何一处直接 `import psycopg2`。
> ⇒ 「扫 import 与 requirements 对账」这类检查对**驱动类依赖结构性失效**。
> 唯一可靠判据是**在干净环境真跑一次**。

**第三层 `mcp>=1.14.0,<2`（加上界）** —— 见下「已修复项 §7」。

#### 已在干净环境跑到底（不再依赖 CI 迭代）

按上面写的根治建议真做了：建干净 venv 只装 `backend/requirements.txt`，
指向全新空库 `audit_platform_dep_probe` 跑完整三步引导。结论见「已修复项 §7」——
**三步全通，`migrations executed: 147, failed: ['106']`**（V106 是早已登记的证据治理域问题），
V147 的 13 个 CHECK 约束全部落地，三个测试集在干净环境的实测数字也拿到了。

这个办法比「push → 等 10 分钟 → 看下一层报错」快一个数量级：
CI 一轮 10+ 分钟且只暴露一层，本地一轮 30 秒。

#### 通用教训

**「CI 绿」和「CI 跑过」是两件事，而「CI 没跑过」和「CI 跑了但没人看」是第三件事。**
本 spec 前一轮收口把状态记成「零成功记录」，语气上暗示「还没跑」，
于是没人去看已经存在的失败日志。判据应该是
`gh run list --branch <branch>` 的实际 conclusion，而不是「有没有 PR」。

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

### 7. `vite build` 在 HEAD 上整体失败 — ✅ **已修，且实测远不止一处（见「已修复项 §6」）**

原文只登记了 `GtConfirmationAlternativeF05.vue` 一处，并归为「函证域问题，只登记不修」。

**实测结论：同批共 7 处，横跨 3 个域**。rollup 一次只报一个 —— 修掉 F05 后立刻冒出
F06，修掉 F06 又冒出 diffReconcile ⇒ **靠 `vite build` 逐个试错要跑 7 轮**，
这也是它长期没人修的原因之一。改用静态扫描一次性列全，7 处一并修完。

> 教训：`vite build` 是**串行短路**的诊断手段（第一处失败即终止），
> 不能用它来判断「还剩几处」。同类问题必须先做全量静态扫描再动手。

详见「已修复项 §6」。

### 8. Playwright 全量跑仍有 4 条 failed（🔴 **归因已更正：3 条是本 spec 自己的 AC**）

2026-08-22 实测 `37 passed / 4 failed / 19 skipped`。接线前同一文件是 `36 / 6 / 18`，
差额就是 Task 15 接线修的两条。

原文把这 4 条归为「**均为本 spec 之外的既有问题**」，理由是「接线前后完全一致」。
**该归因不成立**：「接线前后一致」只证明**不是 Task 15 引入的**，
不等于**不属本 spec**。逐条对到 AC：

| 用例 | 对应 AC | 归属 | 备注 |
|------|---------|------|------|
| A · 面板打开后焦点进入输入区 | **1.7**（焦点在面板与触发元素间正确转移） | **本 spec** | Task 11 标 `[x]`，Property 37 声称覆盖 |
| B · 无项目上下文时项目工具禁用并显示中文原因 | **3.4**（无法解析项目上下文时禁用项目工具并显示原因） | **本 spec** | Task 2 标 `[x]`，Property 5 声称覆盖 |
| C · 对话 history 可加载且按时间正序 | **4.10**（返回最近 N 条后按时间正序） | **本 spec** | Task 3 标 `[x]`，Property 10 声称覆盖 |
| D · 非底稿宿主禁用复核模式 | — | helper | `openAiPanel` 点击被上层节点拦截（`subtree intercepts pointer events`），点击稳定性问题 |

**B / C 各有后端 Property 声称覆盖且后端全绿，浏览器却红** —— 这正是
「守卫层级不够」的信号，与 G7「三向守卫 39 例全绿 / DOM 0/38 渲染」同一形状。
不该记在别人账上。

**建议**：单独立任务逐条查 A/B/C，判据落到 DOM；D 修 helper 的点击目标。

### 9. Context Manifest **非空**路径仍未在浏览器验过

服务端本轮 `context_ready` 下发 `included: []`（全局宿主、无 mention/附件/RAG 命中），
所以「清单列出条目」这条路径只验到了空态。要真验非空：切**项目宿主** → `@` 引用
至少一份底稿/附注（或挂附件）→ 发问 → 断言条目数与 `token_estimate`。
同理 `@ 触发…键盘导航` 与 `多选 mention…可移除` 两条仍 skip 在「无可引用候选」上 ——
全局宿主下搜「审」实测返回 0 条。三条都需要**项目宿主 + 已授权候选**的夹具。
e2e 夹具已存在可用项目（`TEST_PROJECT_ID=2aa00f57-…`，含 FIX-F / FIX-I6 底稿），
但本文件目前**从不引用它**（`TEST_PROJECT_ID` 出现 0 次），全程在全局宿主下跑。
补一个「进项目再开面板」的 helper 即可让这三条转真跑 —— 建议作为下一步。

### 10. 🔴 26 条 AC 有 Task 引用但**零 Property 覆盖**（覆盖率口径修正）

本文件概览表写的「AC 覆盖率 120/120」是按**「被 task 的 Validates 引用」**统计的。
实扫三件套后的真实分布：

| 口径 | 数 |
|---|---|
| AC 总数 | 120 |
| 被 Task 引用 | 120（100%） |
| **被 Property 覆盖** | **94（78%）** |
| **有 Task 无 Property** | **26** |

```
1.1  1.4  1.5  1.10  3.5  3.6  4.2  4.9  5.1  5.9  6.4  7.1  7.3
8.5  8.8  8.9  9.4  9.5  10.2  10.6  10.7  12.3  14.1  14.2  14.3  14.7
```

**AC 1.5 就在这 26 条里** —— 这是它坏掉却全绿的完整死因（见「已修复项 §6」）。
「AC 被 task 引用」只证明**有人负责**，不证明**有可执行判据**。

同批里另有两条更该补：

- **AC 1.1**（面板用平台原生组件、不用 iframe）—— 整个 Requirement 1 的立论基础，零 Property。
- **AC 12.3**（运行时 egress 测试证明模型/MCP/OCR/embedding/plugin 均无公网连接）——
  全本地化的安全底线。Task 31 声称验过，但没有锚在 Property 上的可复跑判据。

**建议**：做一张 **AC → Property → 守卫文件 → 变异锚点** 四列表，26 个空格子即缺口清单。
这比继续增加守卫数量更有价值 —— 现有 722 + 324 条守卫密度已经很高，
问题不在密度而在**分布**。

## 后续行动（按优先级）

1. ~~将所有 `??` 产物 `git add` 并提交~~ ✅ **已完成**（commit `55c5e0fe`，154 files，已推 origin）
2. ~~向 governance-checks.yml 注册 CI job~~ ✅ **已完成**（3 个 job + P0 追加的 2 步）
2a. ~~开 PR 让这三个 job 真跑一次~~ ✅ **已完成（无需 PR，push 即触发）**。
   实证：`frontend` success，`backend` / `mcp-data` 挂在 Bootstrap schema，
   根因 = `pgvector` 漏在 requirements 外 + `ai_models.py` 的 fail-open 兜底
   把缺包伪装成 `TypeError`。已补 `pgvector==0.4.2`。见「未完成项 §2」。
2a-2. **下一轮 CI 待确认**：两个后端 job 走到测试步骤后的实际结论
   （508 / 189 / 25 passed、0 skipped），以及 §3b 那套三步空库引导在 runner 上是否成立
   —— 它此前从未执行到（第 ② 步就退出了）。
2b. ~~给 `dsh-agent-panel-backend` job 补 postgres service~~ ✅ **已完成**（见「已修复项 §3」）
2c. **移交建议**：空库上 `V106` 失败（`service_identities.id` 无 PG 默认值）属证据治理域的
   空库引导问题，与本 spec 无关，建议该域单独立任务
3. **近期**：补 26 条零 Property 覆盖的 AC 判据，优先 **1.1**（不用 iframe）与
   **12.3**（无 egress）—— 见「未完成项 §10」
4. **近期**：逐条查 Playwright 的 A/B/C 三条 failed（分别对应 AC 1.7 / 3.4 / 4.10，
   后端 Property 绿而浏览器红），D 修 helper 点击稳定性 —— 见「未完成项 §8」
5. **近期**：清理 `KNOWN_DEAD_MODULE_FILES` 里的 6 个死文件
   （`components/ai/index.js` + 4 个 `@/api` 旧组件 + `views/ai/AIWorkpaperView.vue`）。
   已实证零活消费方；其中 `index.js` 指向本 spec 删掉的 `AIChatPanel.vue`，按 Req 1.9 应删。
   删除属跨文件破坏性操作，需明确授权后执行
6. **近期**：给 e2e 补「进项目再开面板」的 helper —— `TEST_PROJECT_ID` 当前出现 **0 次**，
   全程在全局宿主下跑，Requirement 5（mention + Context Manifest）只验到了空态
7. **近期**：开展 6000 用户负载测试，校准配额配置；运维设定生产告警阈值
8. **后续**：按验收流程逐项目开放 DSH allowlist（当前 allowlist 为空 ⇒ Phase C 零生产流量）
9. **后续**：评估 ChatMessageList/ChatComposer 是否需拆分（当前 860 行可控）
10. **移交建议**：`package.json` 的 `build` 脚本未配 `NODE_OPTIONS`，
   本机 4GB 默认堆下 `vite build` 必 OOM ⇒ 全仓生产构建校验实际跑不通。
   建议加 `--max-old-space-size`（本次用 8192 可走过解析阶段）

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

**2026-08-22 P0 收口补第四处**：

4. **AC 1.5 在已入库的交付里是坏的** —— `/ai-chat` 路由不存在而 `DshPanel` 却
   `window.open('/ai-chat')`，点「新窗口打开」落 404。e2e 判据只断言 URL，
   而 Vue Router 的 catch-all 不改 URL ⇒ 恒绿。已修路由/上下文/视口/判据四段，
   并新增通用守卫 `FrontendReferenceIntegrity.spec.ts`（15 tests）抓「引用不存在的目标」
   这一整类，变异 MR1–MR6 全 RED。该守卫第一次跑就抓到 2 个新的生产 404
   与 7 处 import 深度错（后者让全仓 `vite build` 挂了 6 天）。见「已修复项 §6」。

> 这四处是同一个假绿家族的四种形态：①**被消费了但没人检查消费到了什么**
> ②**守卫存在但抓不到**（「静态检查通过」被当成「已验证」）
> ③**测试存在且 CI 绿但从未真跑** ④**判据停在请求侧，没有触及渲染结果**。
> 共同判据要求只有一条：判「某能力是否真生效」必须落到**真实执行的可观测结果**上 ——
> 不是字符存在、不是结构完整、不是退出码为 0、**也不是 URL 对不对**。

### 当前状态

**产物已入库**（commit `55c5e0fe`），Task 35 的原阻塞条款（"spec 目录若仍为 `??` SHALL 视为未完成"）
已满足，故标记 `[x]` 成立。

**剩余未证明项**（不再是「未完成」，而是「已交付待验证」）：

| 项 | 状态 |
|---|---|
| 三个 CI job 的真实运行结果 | 零成功记录 → 需开 PR |
| 26 条 AC 的 Property 判据 | 缺口已登记（§10） |
| Playwright A/B/C 三条 failed | 归因已更正为本 spec，待诊断（§8） |
| 6 个死代码文件 | 已实证零活消费方，待授权删除 |
| 6000 并发容量 | 配置值有界，未负载测试 |
| DSH allowlist | 空（Phase C 零生产流量） |
