# DSH Agent Panel Integration — Guard Manifest

> 本清单映射 Design 文档 Property 1–40 到具体测试文件。
> Task 32 产物。所有守卫已验证通过（**backend 722 / frontend 242**）。
>
> **计数实测（2026-08-16 复核，逐条真跑而非照抄）**：
>
> | 集合 | 命令 | 实测 |
> |------|------|------|
> | Backend（`mutation_manifest.guard_files.backend` 全 20 文件） | `python -m pytest <20 文件> --collect-only -q` | **722** tests |
> | Backend 子集 `dsh_agent_panel/`（21 文件，CI 第一步 + 防静默 skip 基线） | `python -m pytest backend/tests/dsh_agent_panel/ --collect-only -q` | **508** tests |
> | Backend 子集 其余 6 文件（CI 第二步基线） | 见 CI Job 段落的文件清单 | **189** tests |
> | Frontend（= `dsh-agent-panel-frontend` job 实跑集合：`src/components/ai/__tests__/` 全目录 + `stores/__tests__/chatRunState.spec.ts` + `__tests__/sseEventTypes.spec.ts` + `__tests__/useAiChat.spec.ts`） | `npx vitest run <上述四组>` | **242** tests / **14** files |
>
> 508 + 189 + 25（`test_ai_chat_mcp_tools_data.py`）= 722，与 Backend 全集一致。
>
> ⚠️ 前端「14 files」指的是**上表那个 job 集合**（含 `AiContentBadge` / `AiContentPendingBanner` /
> `AiContentTag` 三个同目录 spec），不是下表 Frontend Guards 表格列出的 11 个 Property 映射文件
> （那 11 个单独跑 = 217 tests）。报数时别把两个集合混起来。
>
> backend 679 → 682 的 +3 来自 Property 14 假绿修复（原 1 条零断言测试拆成否定半 /
> 肯定半 / 判据自检 / 豁免范围最小化 4 条），见文末「假绿守卫修复记录」。
> backend 682 → 707 的 +25 来自 **MCP 取数责任真空补口**（7 个 `_tool_*` 空占位换真实取数
> 并补端到端数据流守卫），见文末「MCP 取数守卫（责任真空补口）」。
> backend 707 → 722 的 +15 与前端 239 → 242 的 +3 见 Coverage Summary 下方注。

## Backend Guards (722 tests)

| Property | 测试文件 | 测试类/方法 |
|----------|---------|------------|
| 1 (授权拒绝前零读取) | `tests/dsh_agent_panel/test_task1_resource_access.py` | `TestProperty1DenyBeforeRead` |
| 1 (Phase A 综合) | `tests/dsh_agent_panel/test_task13_phase_a_guards.py` | §5 五角色验证 |
| 2 (HostContext 断言一致性) | `tests/dsh_agent_panel/test_task2_host_context.py` | `TestProperty2AssertionConsistency` |
| 2 (Phase A 综合) | `tests/dsh_agent_panel/test_task13_phase_a_guards.py` | §6 |
| 3 (五角色权限交集) | `tests/dsh_agent_panel/test_task1_resource_access.py` | `TestProperty3RoleIntersection` |
| 3 (Phase A 综合) | `tests/dsh_agent_panel/test_task13_phase_a_guards.py` | §5 |
| 4 (全端点授权一致性) | `tests/dsh_agent_panel/test_task1_resource_access.py` | `TestProperty4CrossEndpointConsistency` |
| 4 (Phase A 综合) | `tests/dsh_agent_panel/test_task13_phase_a_guards.py` | §5 |
| 5 (宿主加载器唯一映射) | `tests/dsh_agent_panel/test_task2_host_context.py` | `TestProperty5UniqueHostLoader` |
| 5 (Phase A 综合) | `tests/dsh_agent_panel/test_task13_phase_a_guards.py` | §7 |
| 6 (会话与 Run 并发幂等) | `tests/dsh_agent_panel/test_task3_chat_persistence.py` | Property 6 section |
| 6 (API 侧) | `tests/dsh_agent_panel/test_task4_run_contract.py` | run creation idempotency |
| 6 (Phase A 综合) | `tests/dsh_agent_panel/test_task13_phase_a_guards.py` | §1 |
| 7 (Run 唯一终态) | `tests/dsh_agent_panel/test_task4_run_contract.py` | Property 7 CAS section |
| 7 (Coordinator) | `tests/dsh_agent_panel/test_task5_run_coordinator.py` | terminal race |
| 7 (NativeEngine) | `tests/dsh_agent_panel/test_task6_native_engine.py` | Group F |
| 7 (Phase A 综合) | `tests/dsh_agent_panel/test_task13_phase_a_guards.py` | §2 |
| 8 (取消传播到全部后代) | `tests/dsh_agent_panel/test_task5_run_coordinator.py` | Property 8 section |
| 8 (DshEngine) | `tests/dsh_agent_panel/test_task28_dsh_engine.py` | Property 8 |
| 8 (Phase A 综合) | `tests/dsh_agent_panel/test_task13_phase_a_guards.py` | §3 |
| 8 (Phase C gate) | `tests/dsh_agent_panel/test_task31_phase_c_gate.py` | §2 |
| 9 (SSE 任意分片与续传等价) | `tests/dsh_agent_panel/test_task5_run_coordinator.py` | `test_property9_*` |
| 9 (Phase A 综合) | `tests/dsh_agent_panel/test_task13_phase_a_guards.py` | §4 |
| 10 (最近历史顺序与元数据) | `tests/dsh_agent_panel/test_task3_chat_persistence.py` | Property 10 section |
| 10 (Phase A 综合) | `tests/dsh_agent_panel/test_task13_phase_a_guards.py` | §8 |
| 11 (Mention Schema 与候选授权一致) | `tests/dsh_agent_panel/test_task24_phase_b_guards.py` | `TestProperty11MentionSchemaConsistency` |
| 12 (预算与 Context Manifest 一致) | `tests/dsh_agent_panel/test_task24_phase_b_guards.py` | `TestProperty12BudgetManifestConsistency` |
| 13 (搜索错误态与空态可区分) | `tests/dsh_agent_panel/test_task24_phase_b_guards.py` | `TestProperty13SearchErrorVsEmpty` |
| 14 (extra_scopes 双轨彻底收敛) | `tests/dsh_agent_panel/test_task24_phase_b_guards.py` | `TestProperty14ExtraScopesRemoved` — 否定半：全包 AST 扫描零真实取值（属性读/名称读写/kwargs/函数参数/字符串键/pydantic alias 六形态，字符串常量落拒绝名单豁免桶）；肯定半：`PRIVILEGED_REQUEST_FIELDS` 仍点名该字段且 `ChatRunRequest` 提交时 `ValidationError` 点名拒绝；另含判据反向自检（六形态必检出 / 三合法形态必放过）与豁免范围最小化（仅 `run_contract.py` 1 处）。变异 M18/M19 全 RED |
| 15 (地址索引真源与失效联动) | `tests/dsh_agent_panel/test_task23_address_mention.py` | Property 15 assertions |
| 15 (Phase B) | `tests/dsh_agent_panel/test_task24_phase_b_guards.py` | `TestProperty15AddressIndexSourceIntegrity` |
| 16 (语义不可用不伪降级) | `tests/dsh_agent_panel/test_task24_phase_b_guards.py` | `TestProperty16SemanticUnavailableNoDegradation` |
| 16 (MCP kb_search 侧) | `tests/test_ai_chat_mcp_tools_data.py` | `TestTypedErrorSeparation` — embedding down 时 `kb_search` 返 `semantic_unavailable`（**不是**空 results），且「零命中」仍是 `success` ⇒ 空态与错误态可区分。变异 M35 RED |
| 17 (地址权限与脱敏一致) | `tests/dsh_agent_panel/test_task23_address_mention.py` | Property 17 section |
| 17 (Phase B) | `tests/dsh_agent_panel/test_task24_phase_b_guards.py` | `TestProperty17AddressPermissionAndMasking` |
| 18 (附件安全校验先于 OCR) | `tests/dsh_agent_panel/test_task24_phase_b_guards.py` | `TestProperty18AttachmentSecurityBeforeOCR` |
| 19 (OCR 五态互斥且可见) | `tests/dsh_agent_panel/test_task24_phase_b_guards.py` | `TestProperty19OCRFiveStates` |
| 20 (附件清理幂等可重试) | `tests/dsh_agent_panel/test_task24_phase_b_guards.py` | `TestProperty20AttachmentCleanupIdempotent` |
| 21 (项目笔记并发幂等) | `tests/dsh_agent_panel/test_task3_chat_persistence.py` | Property 21 section |
| 21 (Phase B) | `tests/dsh_agent_panel/test_task24_phase_b_guards.py` | `TestProperty21NoteConcurrentIdempotent` |
| 22 (采纳权威正文与失败回滚) | `tests/dsh_agent_panel/test_task7_adopt_fail_closed.py` | Property 22 section |
| 22 (Phase A 综合) | `tests/dsh_agent_panel/test_task13_phase_a_guards.py` | §9 |
| 23 (复核模式宿主与单 System) | `tests/dsh_agent_panel/test_task24_phase_b_guards.py` | `TestProperty23ReviewModeConstraints` |
| 24 (引擎能力与 UI 一致) | `tests/dsh_agent_panel/test_task6_native_engine.py` | Group B + capability |
| 24 (Capabilities API) | `tests/dsh_agent_panel/test_task30_capabilities.py` | full file |
| 24 (Phase A 综合) | `tests/dsh_agent_panel/test_task13_phase_a_guards.py` | §10 |
| 25 (DSH 失败不降级) | `tests/dsh_agent_panel/test_task28_dsh_engine.py` | Property 25 |
| 25 (Discovery) | `tests/test_dsh_discovery_task27.py` | `TestDshFailureNoDegradation` |
| 25 (Capabilities) | `tests/dsh_agent_panel/test_task30_capabilities.py` | DSH disabled |
| 25 (Phase C gate) | `tests/dsh_agent_panel/test_task31_phase_c_gate.py` | §7 |
| 26 (Effective Cordis 与工具目录受控) | `tests/test_dsh_discovery_task27.py` | tool catalog tests |
| 26 (MCP server) | `tests/test_audit_data_mcp_server.py` | `TestToolCatalogProperty` |
| 26 (Phase C gate) | `tests/dsh_agent_panel/test_task31_phase_c_gate.py` | §4 |
| 26 (**工具真的返回数据**) | `tests/test_ai_chat_mcp_tools_data.py` | `TestRealDataNonEmpty` + `TestNoPlaceholderRemains` — 🔴 前三处 Property 26 守卫只证明「目录集合不多不少」，**不证明工具返回内容**。本类补：给定真实底稿/试算表/附注 fixture，`wp_list.items` / `wp_read.content` / `tb_query.rows` / `note_read.rows` 必须非空且字段结构符合声明；`MCP_TOOL_IMPLEMENTATIONS` 与 `MCP_READONLY_TOOLS` 等势且全为协程；运行时无 `status="placeholder"`、无空壳 `content=={}`；源码级 `_tool_*` 函数体内无 `placeholder` 字面量（**先 `stripComments` 再检查** + 反向自检 `test_placeholder_detector_is_not_vacuous`）。变异 M28–M31 全 RED |
| 26 (只读保证) | `tests/test_ai_chat_mcp_tools_data.py` | `TestReadOnlyGuarantee` — `mcp_tools.py` 剥注释后无 `insert`/`update`/`delete`/`commit` |
| 27 (MCP 零数据库与零监听端口) | `tests/test_audit_data_mcp_server.py` | `TestZeroDatabaseProperty` |
| 27 (Phase C gate) | `tests/dsh_agent_panel/test_task31_phase_c_gate.py` | §4 |
| 28 (DSH 跨用户隔离) | `tests/dsh_agent_panel/test_task28_dsh_engine.py` | Property 28 |
| 28 (MCP token) | `tests/test_ai_chat_mcp_token.py` | Property 28 section |
| 28 (Phase C gate) | `tests/dsh_agent_panel/test_task31_phase_c_gate.py` | §1 |
| 28 (**取数层越权**) | `tests/test_ai_chat_mcp_tools_data.py` | `TestToolAuthorization` — token 校验通过后**工具内部再过** `ResourceAccessResolver`：另一 project 的 token 读本 project `wp_id` → 拒绝；跨项目 `note_id` → 拒绝而非空 items；未授权 cycle 的底稿不出现在 `wp_list`、直读 `wp_read` 亦拒绝（Req 2.6 共用上界）；非项目成员查 `tb_query` → 拒绝。**越权一律返回拒绝，不返回空数据伪装「无结果」**。变异 M32/M33 全 RED |
| 29 (子 Agent 权限只收窄) | `tests/test_ai_chat_mcp_token.py` | Property 29 section |
| 29 (MCP server budget) | `tests/test_audit_data_mcp_server.py` | `TestBudgetEnforcementProperty` |
| 29 (Phase C gate) | `tests/dsh_agent_panel/test_task31_phase_c_gate.py` | §7 |
| 30 (五角色脱敏一致) | `tests/test_ai_chat_task29_dsh_masking.py` | §1 五角色脱敏 |
| 30 (MCP token) | `tests/test_ai_chat_mcp_token.py` | Property 30 section |
| 30 (Phase C gate) | `tests/dsh_agent_panel/test_task31_phase_c_gate.py` | §7 |
| 30 (**新返回结构真脱敏**) | `tests/test_ai_chat_mcp_tools_data.py` | `TestRoleMasking` — 同一份含大额金额数据，`auditor`(strict) 与 `partner`(none) 调**同一 endpoint**，断言两者结果**不相等**（相等即脱敏未生效）；`manager`(partial) 拿区间描述而非原值或 `***`；未触阈值金额保持数值类型。🔴 这条同时锁死「外层脱敏对**嵌套 dict/list 里的金额**真的生效」——裸 `ExportMaskService.apply_mask` 规则表只有联系方式/银行账号/身份证号，对纯金额结构是空操作，故调用方已改走 `dsh_masking.mask_tool_result`。变异 M34 RED |
| 31 (提示注入不能扩大权限) | `tests/test_ai_chat_task29_dsh_masking.py` | §2+§3 数据定界+fake agent |
| 32 (哈希链事件成对完整) | `tests/test_ai_chat_task12_audit_metrics.py` | `TestProperty32HashChainPaired` |
| 32 (采纳) | `tests/dsh_agent_panel/test_task7_adopt_fail_closed.py` | Property 32 section |
| 32 (MCP router) | `tests/test_ai_chat_mcp_router.py` | audit trail assertions |
| 32 (DSH masking) | `tests/test_ai_chat_task29_dsh_masking.py` | §4+§5 工具审计+内容扫描 |
| 32 (Phase A/C) | `tests/dsh_agent_panel/test_task13_phase_a_guards.py` + `test_task31_phase_c_gate.py` | §11 / §7 |
| 33 (下游故障不产生假成功) | `tests/dsh_agent_panel/test_task6_native_engine.py` | `TestProperty33NoFalseSuccess` |
| 33 (采纳) | `tests/dsh_agent_panel/test_task7_adopt_fail_closed.py` | Property 33 section |
| 33 (Phase A) | `tests/dsh_agent_panel/test_task13_phase_a_guards.py` | §11 |
| 34 (不可信 HTML 统一净化 — **后端侧职责**) | `tests/dsh_agent_panel/test_task24_phase_b_guards.py` | `TestProperty34UntrustedDataBoundary` — **净化边界唯一且在前端**（`useSanitize.sanitizeHtml`），后端在这条链上**不转义**。本类断言后端真实职责：`ContextManifestEntry.as_dict()` 可安全 JSON round-trip、恶意 label **原样透传**（不截断/不丢弃/不二次转义）、`source_type`/`source_id`/`status`/`reason` 不被污染、manifest 分组不吞条目；OCR 文本经数据定界块。DOM 层「净化后不含 on*」由前端守卫负责，后端不重复声称。变异 M16/M17 全 RED |
| 36 (AI Chat 真实限流) | `tests/test_ai_chat_task12_audit_metrics.py` | `TestProperty36RateLimitAccess` |
| 38 (DSH Backpressure 有界) | `tests/dsh_agent_panel/test_task28_dsh_engine.py` | Property 38 |
| 38 (Phase C gate) | `tests/dsh_agent_panel/test_task31_phase_c_gate.py` | §3 |

## Frontend Guards (13 files / 264 tests；CI job 集合 16 files / 289 tests)

> 下表是 **Property → 文件** 的映射（13 个文件，单独跑实测 264 tests）。
> CI 的 `dsh-agent-panel-frontend` job 跑的是**整个** `src/components/ai/__tests__/` 目录，
> 多带 `AiContentBadge` / `AiContentPendingBanner` / `AiContentTag` 三个 spec（+25）⇒ 289。
> 两个数都对，指的集合不同。
>
> **2026-08-22 实测**（`npx vitest run src/components/ai/__tests__ + chatRunState + sseEventTypes + useAiChat`）：
> **16 files / 289 tests passed**。242 → 289 的 **+47** 全部来自 Task 15 接线补口新增的两个文件：
> `AiRenderHostReachability.spec.ts` **30** + `PlatformAiChatRunPayload.spec.ts` **17**（逐文件单跑实测，30+17=47 与总量差额一致）。
> 两个新文件都落在 `src/components/ai/__tests__/` 目录内 ⇒ 已被 `governance-checks.yml` 的
> `dsh-agent-panel-frontend` job 的目录级 glob 自动纳入，**无需改 CI 配置**（已核对该 job 的路径写法）。

| Property | 测试文件 | 范围 |
|----------|---------|------|
| 9 (SSE 分片与续传) | `src/__tests__/sseEventTypes.spec.ts` | SSE typed contract |
| 9 (chatRunState) | `src/stores/__tests__/chatRunState.spec.ts` | event dispatch + state machine |
| 9, 39 (PlatformAiChat) | `src/__tests__/useAiChat.spec.ts` | composable 行为 |
| 13 (搜索错误态可区分) | `src/components/ai/__tests__/ChatMentionPicker.spec.ts` | error vs empty DOM |
| 19 (OCR 五态) | `src/components/ai/__tests__/ChatAttachmentPicker.spec.ts` | upload+OCR status |
| 20 (附件清理交互) | `src/components/ai/__tests__/ChatAttachmentPicker.spec.ts` | cleanup retry |
| 21 (笔记 UI 幂等) | `src/components/ai/__tests__/PlatformAiChatPanel.spec.ts` | note save guard |
| 23 (复核模式条) | `src/components/ai/__tests__/PlatformAiChatPanel.spec.ts` | review mode bar |
| 24 (capability gate) | `src/components/ai/__tests__/PlatformAiChatPanel.spec.ts` | capability 禁用 |
| 34 (XSS 统一净化) | `src/components/ai/__tests__/PlatformAiChatXss.spec.ts` | 5 source sanitize |
| 35 (浏览器敏感缓存) | `src/components/ai/__tests__/PlatformAiChatXss.spec.ts` | localStorage scrubber |
| 34–39 (Phase A 综合) | `src/components/ai/__tests__/PlatformAiChatPhaseA.spec.ts` | 全属性 + 死代码 |
| 37 (三视口+可访问) | `src/components/ai/__tests__/DshPanelA11y.spec.ts` | responsive + ARIA |
| 39 (单一内核) | `src/components/ai/__tests__/PlatformAiChatPhaseA.spec.ts` | 宿主迁移完整 |
| 12, 21, 23, 34 (Phase B 门) | `src/components/ai/__tests__/PhaseBGateGuards.spec.ts` | 跨组件门控不变量，全部落到真实 mount / 真实调用 / 真实 DOM：**P23** `ChatReviewModeBar` 五种宿主逐一 mount（workpaper 可用且真取模板 / 非 workpaper disabled + 逐类型可区分中文原因 / 宿主切走自动关闭）；**P21** `useAiNoteCapture` 真调用 + mock fetch 查请求体（重试复用同一 `idempotency_key`、选择集变化换新 key、名称必经确认框）；**P12** `ChatContextInspector` 真 mount，四态各自渲染 + 中文原因 + 摘要计数；**P34** 真调 `sanitizeHtml`（载体刻意选白名单标签 a/p/strong/blockquote，否则放宽 `ALLOWED_ATTR` 打不红）。变异 M20–M27 全 RED。单组件细节不在此重复（见 `ChatMentionPicker`/`ChatAttachmentPicker`/`ChatContextInspector`/`PlatformAiChatXss` 各自 spec） |
| 12 (Context Inspector) | `src/components/ai/__tests__/ChatContextInspector.spec.ts` | manifest 展示 |
| **12, 13（渲染宿主可达性 / 组件孤岛）** | `src/components/ai/__tests__/AiRenderHostReachability.spec.ts` | **30 tests。抓「声明齐全 + 单测全绿 + 零渲染宿主」这一整类假绿**，不点名具体组件：按前缀扫 `src/components/ai/` 下全部 `Chat*`/`Platform*`/`Dsh*`（≥6 个），每个都要过三层 —— ① 至少一个**非测试文件** import 它 ② 引用方**真把它当标签/注册项用**（`.vue`：PascalCase / kebab-case / `<component :is>`；`.ts`：出现在 import 语句之外）③ 判定基于**结构化解析**（注释感知的 import 解析 + 顶层 template 块提取），不是裸 grep 符号名。另含 12 条**反向自检**（有 import 无标签 / 模板注释里的标签 / script 字符串里的标签 / `ChatMentionPickerV2`≠`ChatMentionPicker` / 注释掉的 import 必须判为未使用；三种合法用法必须放过；`stripJsComments` 不得截断含 `//` 的字符串；kebab 转换对连续大写正确；顶层 template 提取不被嵌套 `<template #slot>` 打断）+ 2 条判据自身不空洞断言（清单 ≥6 且覆盖三类前缀 / 源文件集合 >200 且已排除测试文件）。变异 **M36/M37 全 RED** |
| **5.5, 12（mention 真进请求体 + manifest 投影）** | `src/components/ai/__tests__/PlatformAiChatRunPayload.spec.ts` | **17 tests。锁「收集完不提交」与「投影吞条目」两类死代码变体**：`@` 触发链（活跃 `@` 词开/关、Escape 关闭且 `stopPropagation` 不冒泡给 DshPanel、点输入区外关闭而点 picker 内不关）；已选引用**真出现在 `POST /api/ai-chat/runs` 请求体**且只含 `type`+稳定 ID、发送后清空不跟到下一轮；`normalizeContextManifest` 投影四态齐全、不吞未登记分组键（退化 `unavailable`）、**不发明 `jump_route`**（Req 5.9）、native `char_estimate` 与 budget `used_tokens` 两套口径都能读。变异 **M38–M41 全 RED** |

## Coverage Summary

| Phase | Backend Tests | Frontend Tests | Properties Covered |
|-------|--------------|----------------|-------------------|
| A (安全基线) | 490 | 146 | 1–10, 22, 24, 32–39 |
| B (上下文) | 96 | 119 | 11–23, 34 |
| C (DSH Agent) | 136 | 24 | 16, 25–32, 38 |
| **Total** | **722** | **289** | **1–40 全覆盖** |

> Phase C 的 103 → 128 = MCP 取数守卫 25 条（`test_ai_chat_mcp_tools_data.py`）；
> 128 → **136** 的 +8 = 下面那批 Task 33 变异后补的守卫里落在 Phase C 的部分
> （`test_task28_dsh_engine.py` +3 / `test_task30_capabilities.py` +5）。
>
> 707 → **722**（+15）= Task 33 那 10 条变异真跑后补的守卫：
> Phase B `test_task24_phase_b_guards.py` **+7**（attachment owner 行为判据 3 条 + 签名
> 反向自检 1 条 −原 fail-open 1 条 · semantic_unavailable 行为判据 4 条）·
> Phase C `test_task28_dsh_engine.py` **+3**（SDK 门级判据）·
> `test_task30_capabilities.py` **+5**（`/capabilities` 自身 local-only 取值判据）。
> 前端 239 → **242**（+3）= `PlatformAiChatPhaseA.spec.ts` 的 localStorage 清理行为判据。
> 根因逐条见 `CLOSURE.md`「已修复项 §2」与 `mutation_results.json`。
>
> 前端 242 → **289**（+47）= Task 15 接线补口（`CLOSURE.md`「已修复项 §4」）：
> Phase B `AiRenderHostReachability.spec.ts` **+30** + `PlatformAiChatRunPayload.spec.ts` **+17**。
> 两文件均属 Phase B（Property 12/13），故 Phase B 前端 72 → **119**；Phase A / C 不变。
> 变异结果见 `mutation_results_render_host.json`（M36–M41 **6/6 全 RED**）。

## CI Job Names

> 下列 tests 数均为 2026-08-16 实测（`--collect-only -q` / `vitest run`），
> 与 job 实际跑的文件集合一一对应。

- `dsh-agent-panel-backend` — 后端 **697** tests = `dsh_agent_panel/` **508** + 其余 6 文件 **189**
  （access/host/run/context/attachment/note/review/MCP/DSH）
  **带 pgvector/pgvector:pg16 service + schema 引导 + 两条防静默 skip 硬断言**
- `dsh-agent-panel-frontend` — 前端 **324** tests / 18 files（2026-08-22 P0 收口后；原 289/16、242/14）
  （`src/components/ai/__tests__/` 全目录 + `chatRunState` + `sseEventTypes` + `useAiChat`
  + **`FrontendReferenceIntegrity`**；transport/core/sanitize/a11y/mention/OCR/note/review/
  capability/渲染宿主可达性/run 载荷/**引用完整性**）
  目录级 glob 会自动收 `src/components/ai/__tests__/` 下的新 spec；
  但 `FrontendReferenceIntegrity`（`src/__tests__/`）与 `workHoursTabDeepLink`（`src/views/__tests__/`）
  不在该目录内，**已显式加三步**（两个守卫实跑 + 锚点静态检查）
- `dsh-agent-panel-mcp-data` — MCP 取数 **25** tests（**带 pgvector/pgvector:pg16 service + 同一套 schema 引导**）

> 697 + 25 = 722 = Backend Guards 全集。三个 job 无重叠、无遗漏。

> 🔴 **两个后端 job 都必须带 postgres service，这是实测结论不是偏好**。
> `backend/tests/dsh_agent_panel/_fixtures.py` 用
> `IS_PG = app_settings.DATABASE_URL.startswith("postgresql")` + `pytest.mark.skipif`
> 门控 PG 依赖用例。同一工作树两次实测（2026-08-16）：
>
> | `DATABASE_URL` | passed | skipped | exit |
> |---|---|---|---|
> | `postgresql+asyncpg://…` | **508** | 0 | 0 |
> | `sqlite+aiosqlite:///…` | 325 | **183** | **0** |
>
> （508 = 修完 M07/M09/M13/M14 守卫后的基线；修前为 493 / 310+183。）
>
> ⇒ 无 PG 时 **183/508 静默 skip 且 job 仍绿**。「测试存在且 CI 绿」≠「测试真跑过」。
> `dsh-agent-panel-backend` 此前无 service ⇒ 那 183 条**从未在 CI 执行过**。已补
> `services: pgvector/pgvector:pg16` + `DATABASE_URL` + schema 引导步骤。
> 其余 6 个后端测试文件（189 tests）实测 PG 无关（sqlite 下 189 passed / 0 skipped），
> 与 PG 依赖那批共用同一 service，不再分拆。

> 🔴 **空库引导顺序是三步，不能省也不能换序**（在全新库上实测得出，最终
> 508 + 189 + 25 passed / 0 skipped）：
> ① `CREATE EXTENSION vector` —— `create_all` 有 `VECTOR(1024)` 列，裸 `postgres:16`
> 会报 `type "vector" does not exist` 而整个建表失败，故 service 镜像必须是 pgvector 版。
> ② `scripts/seed/init_tables.py`（= `Base.metadata.create_all`，278 表）—— 平台基础
> schema **由 ORM 建、不由迁移建**；空库直跑迁移有 **124 个失败**
> （`relation "projects" does not exist`）**而 `run_pending()` 仍返回成功、步骤仍绿**。
> ③ `DROP` V147 拥有的 4 张 `ai_chat_*` 表再跑迁移 —— V147 用
> `CREATE TABLE IF NOT EXISTS` 建它们并把 7 个 CHECK 与 `ON DELETE RESTRICT` 外键
> **写在建表语句内**（ORM 故意不重复声明）；create_all 先建出 ORM 形态后 V147 整段被跳过
> ⇒ 约束永不落地 ⇒ `test_task3_chat_persistence.py` 10 条打红。V147 又
> `ALTER TABLE ai_chat_message / ai_chat_session`，所以它也不能在 create_all 之前跑。
> 引导层另加一步**直接对 DB 断言那 7 个 CHECK 都在**，否则 V147 静默变 no-op 时
> 只表现为 test_task3 打红、根因极难查。
>
> ⚠️ `init_tables.py` 末尾会回调 seed 端点；必须钉 `API_BASE_URL=http://127.0.0.1:9`
> 阻断（否则会打到恰好在跑的后端，把种子写进**它连的那个库**——本地已实测发生过一次）。

> 🔴 **为什么 MCP 取数守卫仍单开一个 job**：判据核心是「给定真实数据，工具返回非空」，
> 依赖 migrations 后的四表 schema（叶子聚合 / JSONB `parsed_data` /
> 可见集 `UNION ALL` 在 sqlite 上给假绿），与 Phase A/B/C 守卫的失败面互相独立，
> 分开更易定位。两个 job 现在形态一致（service + migrations + `-rs` + 硬断言）。

> **防静默 skip 硬断言**（三条，形态统一）：复跑 `-q -rs` 解析摘要，
> `passed` 低于实测基线或出现**任何** `skipped` 即打红。
> 基线：`dsh_agent_panel/` ≥ 508 · 其余 6 文件 ≥ 189 · `mcp_tools_data` ≥ 25。
> 数值比较用 `python -c`（`>=493` 的 grep 正则不可维护）。


## 假绿守卫修复记录（三处，含变异检验）

三处守卫此前**登记为已覆盖但实际零覆盖**，已修复并逐处做变异检验。

| # | 位置 | 假绿形态 | 修法 | 变异 → 打红的测试 |
|---|------|---------|------|------------------|
| 1 | `test_task24_phase_b_guards.py::TestProperty34UntrustedDataBoundary` | 恒真断言 `assert ... or True`（Property 34 后端侧零覆盖） | 先核 `ContextManifestEntry.as_dict()` 真实职责 = **不转义**（净化边界唯一且在前端），故断言改为「安全序列化 + label 原样透传 + 结构字段不被污染 + manifest 不吞条目」，测试名与 docstring 同步改成描述这个真实职责，不再声称 sanitize | M16（后端二次转义 label）/ M17（静默截断 label）→ `test_manifest_entry_passes_untrusted_label_through_unmodified` |
| 2 | `test_task24_phase_b_guards.py::TestProperty14ExtraScopesRemoved` | 零断言：算完 `code_only` / `non_comment_uses` 后注释「这里不做断言」，全函数无 `assert` | 改 `ast` 遍历（`Attribute`/`Name`/`Subscript`/`keyword`/`arg`/pydantic `alias`）区分**真实取值**与**拒绝名单字符串字面量**；否定半（零真实取值）+ 肯定半（拒绝名单点名 + 提交被 `ValidationError` 拒）+ 判据反向自检（六形态必检出、三合法形态必放过）+ 豁免范围最小化 | M18（恢复 `extra_scopes` 属性读）→ `test_no_extra_scopes_consumption_in_ai_chat_package`；M19（拒绝名单移除）→ `test_client_submitted_extra_scopes_is_rejected` + `test_only_run_contract_deny_list_holds_the_literal` |
| 3 | `PhaseBGateGuards.spec.ts` | ① 断言输入字面量（`expect(malicious).toContain('onerror')` 与 sanitize 无关）② 7 处 `toBeDefined()` 把「文件能 import」当 Property 12/21/23 的证据 | 全部重写为真实 mount / 真实调用 / 真实 DOM 行为断言（见上表 Phase B 门一行）；单组件细节交回各自 spec，不留空壳 | M20（`ALLOWED_ATTR` 放宽 on*）· M21–M24（复核门控四态）· M25/M26（笔记幂等键）· M27（manifest 四态塌缩）→ 各自预期测试，见 `mutation_results_falsegreen_fix.json` |

**变异检验结论**：12 条全 RED（GREEN/MISS/WRONG 各 0），生产代码字节级复原已校验。

复现（四态判定，只看退出码会把 GREEN/MISS/WRONG 误判成 RED）：

```powershell
python backend/scripts/diagnose/mutate_dsh_agent_panel_guards.py --check-anchors
python backend/scripts/diagnose/mutate_dsh_agent_panel_guards.py --pick "假绿修复" --only be --out tmp_be.json
python backend/scripts/diagnose/mutate_dsh_agent_panel_guards.py --pick "假绿修复" --only fe --out tmp_fe.json
```

> `--out` 必须另指定，否则会覆盖 Task 33 的全量 15 条记录 `mutation_results.json`。
> 锚点登记见 `mutation_manifest.json` 的 M16–M27（`falsegreen_fix` 段落）。

**关键教训**：`useSanitize` 的 on* 剥离要用**白名单标签**当载体（`a`/`p`/`strong`/`blockquote`）才测得到 `ALLOWED_ATTR`；本条最初用 `img`/`script` 当载体，那类标签本就被整体删除，放宽 `ALLOWED_ATTR` 打不红 —— 变异检验时才暴露，属「守卫看着有断言其实测的是别的机制」。

## Artifact Tracking Status (git status --porcelain)

> 运行日期：Task 32 执行时刻
> 状态：所有本 spec 新增的产物均为 `??`（未跟踪），与 memory 记载的"在办 spec 目录全 `??`"一致。

### 未跟踪产物清单 (须入库)

**后端实现:**
- `backend/app/services/ai_chat/` (整个目录，含 MCP 取数补口的 `mcp_tools.py`)
- `backend/app/routers/ai_chat_mcp.py`

**后端测试:**
- `backend/tests/dsh_agent_panel/` (整个目录，21 文件)
- `backend/tests/test_ai_chat_mcp_router.py`
- `backend/tests/test_ai_chat_mcp_token.py`
- `backend/tests/test_ai_chat_mcp_tools_data.py` ← MCP 取数守卫（25 tests）
- `backend/tests/test_ai_chat_task12_audit_metrics.py`
- `backend/tests/test_ai_chat_task29_dsh_masking.py`
- `backend/tests/test_audit_data_mcp_server.py`
- `backend/tests/test_dsh_discovery_task27.py`

**变异脚本:**
- `backend/scripts/diagnose/mutate_dsh_agent_panel_guards.py` (M01–**M41**，含渲染宿主 6 条)

**前端实现:**
- `audit-platform/frontend/src/components/ai/PlatformAiChatPanel.vue`
- `audit-platform/frontend/src/components/ai/ChatAttachmentPicker.vue`
- `audit-platform/frontend/src/components/ai/ChatContextInspector.vue`
- `audit-platform/frontend/src/components/ai/ChatMentionPicker.vue`
- `audit-platform/frontend/src/components/ai/ChatReviewModeBar.vue`
- `audit-platform/frontend/src/components/ai/DshPanel.vue`
- `audit-platform/frontend/src/composables/usePlatformAiChat.ts`
- `audit-platform/frontend/src/composables/useAiMention.ts`
- `audit-platform/frontend/src/stores/chatRunState.ts`
- `audit-platform/frontend/src/utils/aiChatCacheCleanup.ts`
- `audit-platform/frontend/src/utils/chatContextManifest.ts` ← **Task 15 接线补口**（manifest 投影层）

**前端测试:**
- `audit-platform/frontend/src/components/ai/__tests__/` (**13 files**，2026-08-22 实测)
  - 其中 **2 个为 Task 15 接线补口新增**：
    `AiRenderHostReachability.spec.ts`（30 tests，渲染宿主可达性 / 组件孤岛）·
    `PlatformAiChatRunPayload.spec.ts`（17 tests，`@` 触发链 + mention 进请求体 + manifest 投影）
- `audit-platform/frontend/src/stores/__tests__/chatRunState.spec.ts`

**Playwright:**
- `audit-platform/frontend/e2e/dsh-agent-panel-acceptance.spec.ts`
  （2026-08-22 修了 3 条 mention/manifest 用例的判据缺陷，见 `CLOSURE.md`「已修复项 §5」）

**工具:**
- `tools/audit-data-mcp/` (整个目录)

**Spec 产物:**
- `.kiro/specs/dsh-agent-panel-integration/GUARD_MANIFEST.md` (本文件)

### 已跟踪但已修改

- `.github/workflows/governance-checks.yml` (新增 2 个 CI job)
- `audit-platform/frontend/src/utils/sse.ts` (增强 SSE transport)
- `audit-platform/frontend/src/components/ai/AIChatPanel.vue` (已删除 — `D` 状态)
- `backend/app/services/knowledge_index_service.py` (**纯增 58 行 0 删**：新增
  `semantic_search_strict` —— embedding-only 版本，失败即抛 `EmbeddingUnavailableError`。
  已 diff 归因确认属本次 MCP 取数补口，非并发会话改动；消费方 = `mcp_tools.tool_kb_search`，
  变异 M35 RED 证明在活路径上，不是 additive 死代码)

### 结论 — ✅ **已入库（2026-08-22 实测更正）**

上面整节「未跟踪产物清单」**已过期**。实测 `git status --porcelain`：

- commit **`55c5e0fe`**「feat(ai): DSH Agent 面板平台化集成（PlatformAiChatPanel 统一宿主）」
  纳入 **154 个文件** —— 上述清单中的每一项均已 tracked。
- 分支 `work/2026-08-22-dsh-agent-panel-integration` 已推到 `origin`。
- 「丢工作树即蒸发」与「clean checkout 必挂」两个风险已解除。

**仍未证明的是**：三个 CI job 至今**零成功记录**。产物入库只是让它们**能**跑，
不等于**跑过**。见 `CLOSURE.md`「未完成项 §2」。

> ⚠️ 本节与 `CLOSURE.md`「未完成项 §1」在入库后**过期了 6 天**，
> 期间接手方读到的都是错误前提。判「产物入没入库」只需一条
> `git status --porcelain -- <path>` —— 别让文档替代实测。

---

## P0 收口新增守卫（2026-08-22）

### `FrontendReferenceIntegrity.spec.ts`（15 tests）

**抓的是「引用了不存在的目标」这一整类**，不点名具体实例。
位置 `src/__tests__/FrontendReferenceIntegrity.spec.ts`，
共享扫描工具在 `src/__tests__/_helpers/frontendSourceScan.ts`
（`stripJsComments` 收敛到这里作单一真源 —— 它那个「朴素正则会截断
`'https://x'` 导致同行后续 import 被吃掉」的坑不该有第二份副本）。

| Property / AC | 判据 | 防的形态 |
|---|---|---|
| **AC 1.5** | 写死的 `window.open` / `router.push` / `router.replace` / `to=` 目标必须匹配到**非 catch-all** 的声明路由；另有一条点名断言 `/ai-chat` 已注册（不依赖调用方存在） | **路由孤儿** —— `window.open('/ai-chat')` 而路由未注册 ⇒ 落 404。原 e2e 只断言 URL，而 catch-all **不改 URL** ⇒ 判据恒绿 |
| **AC 1.9** | 全仓生产源码（5112 个文件，已排除测试）的相对/别名 import 必须可解析；6 个死代码文件登记在 `KNOWN_DEAD_MODULE_FILES` 且**只减不增** | **模块孤儿** —— import 深度写错 ⇒ 整个 `vite build` 挂掉（实测同批 **7 处**，横跨 3 个域，rollup 一次只报一个） |

**核心设计 —— catch-all 必须显式排除**：若把它算进可达集合，任何路径都"匹配得上"，
判据恒真。这与 AC 1.5 那条 e2e 失效的机制完全相同，故有专门一条锁它
（变异 MR2 验证有效）。

**豁免桶的语义是「死代码待删」而非「这个错可以接受」**，配三条约束：
①清单只减不增 ②每条必须给 >10 字原因 ③断言它们**确实零活消费方**
（死代码内部互引与自动生成的 `components.d.ts` 不算）。

**判据不空洞的自检**：扫描面 >2000 个生产文件 · 路由声明 >100 条 ·
catch-all 必须被解析到 · `children:` 恰好出现 1 次（单层嵌套假设，
多一层会让「子路由父路径 = `/`」的拼接静默失效）。

**首跑即抓到 3 类真缺陷**：AC 1.5 本身 · 2 个新的生产 404
（`ManagementDashboard` 的 `/staff`、`ManagerDashboard` 的 `/work-hours/approve`）·
7 处 import 深度错。

**变异**：锚点 **MR1–MR6**，静态 6/6 命中恰好 1 次，**实跑 6/6 全 RED**
（GREEN / ANCHOR-MISS / WRONG-TEST 各 0），sha256 字节级复原已校验。
runner = `backend/scripts/diagnose/mutate_frontend_reference_integrity.py`，
结果记 `mutation_results_reference_integrity.json`（未覆盖既有四份）。

### `workHoursTabDeepLink.spec.ts`（10 tests，路由孤儿的连带修复）

上面那条守卫抓出 `ManagerDashboard` 跳 `/work-hours/approve`（无此路由，
审批是 `WorkHoursPage` 里 `name="approve"` 的 tab）。改成
`{ path:'/work-hours', query:{ tab:'approve' } }` 后**必须有行为判据** ——
否则「跳到了页面但停在默认 tab」既没人看得出来，也没有任何测试会红。

判据两组：①「query → 初始 tab」规则（白名单 / 无权用户手敲 `tab=approve` 退回默认 /
非字符串与数组形态 / 合法值放行）②**接线判据**（页面真的读 `route.query.tab`、
`activeTab` 由 `initialTab()` 初始化而非硬编码、`approve` 仍受
`can('approve_workhours')` 门控、dashboard 不再含旧路径）。

> 🔴 **本文件踩过一次「注释污染 grep 判据」**：首版直接对原始源码断言
> `not.toContain("'/work-hours/approve'")`，被**修复时写的说明注释**打红（注释正文
> 引用了旧路径）。反向同样成立 —— 正向 `toContain` 会被注释里的字面量喂成假绿。
> 现已统一走 `stripJsComments(stripHtmlComments(...))`，并加一条
> **剥注释确实生效**的自检（注释原文在 raw 里、剥后不在）。
> 这就是 memory 记的「守卫读源码前必 `stripComments()` + 反向自检」。

复现：

```powershell
python backend/scripts/diagnose/mutate_frontend_reference_integrity.py --check-anchors
python backend/scripts/diagnose/mutate_frontend_reference_integrity.py --run `
  --out .kiro/specs/dsh-agent-panel-integration/mutation_results_reference_integrity.json
```

**CI**：`dsh-agent-panel-frontend` job 追加两步（守卫实跑 + 锚点静态检查）。
该 job 用**目录级** glob 收 `src/components/ai/__tests__/`，本守卫不在该目录内，
**必须显式列出**。锚点检查步骤在 ubuntu runner 上用 `python3`（不是 `python`）。
归因型验收：`governance-checks.yml` 相对 HEAD **单个纯插入 hunk、13 行零删除、
job 数 161 → 161 不变**。

**前端守卫计数**：289 / 16 files → **324 / 18 files**（+35 / +2 —— 引用完整性 15 + 工时 tab 深链 10，另 10 条为深链守卫的接线判据与自检）。

---

## MCP 取数守卫（责任真空补口）

### 这次补的是**责任真空**，不是漏做的子任务

`routers/ai_chat_mcp.py` 的 7 个 `_tool_*` dispatcher 原本全是空占位：

| 工具 | 原返回 |
|------|--------|
| `wp_list` | `{"items": []}` |
| `tb_query` | `{"rows": []}` |
| `kb_search` | `{"results": []}` |
| `wp_read` / `addr_lookup` / `note_read` / `review_prompt` | `{"status": "placeholder"}` |

三层管道 —— REST endpoint → `tools/audit-data-mcp/server.py` → `DshEngine` —— **全通**，
Phase C 207 个测试**全绿**。原因只有一条：**没有一条测试断言过返回值**。
守卫全落在「管道接没接通」（token 校验、白名单、预算、审计成对），
没有一条落在「Agent 到底拿到了什么」。于是 DSH Agent 实际取不到任何底稿、
试算表、附注内容，而任何静态检查、`get_diagnostics`、CI 都看不出来。

**为什么两个任务都不拥有它：**

- **Task 25**（MCP scoped REST endpoints）范围是**安全边界** ——
  ResourceAccessResolver 接线、scoped token 生命周期、脱敏映射、预算、哈希链审计。
  它把 `_dispatch_tool` 的骨架和 7 个 dispatcher 的**签名**建好，
  正文留了注释「实际在 Task 26 接通」。
- **Task 26**（`audit-data` MCP stdio server）范围是**调用方** ——
  工具 schema 与 `MCP_READONLY_TOOLS` 对账、stdio only 不监听 TCP、
  零 DB / 零 ORM import、预算超限即停。它调的是平台 REST，
  按设计**不该**、也不能包含平台侧取数（Req 11.4 明令禁止 MCP server 直连数据库）。

两个任务的验收标准都能在「取数是空占位」的前提下全绿 ⇒ **谁都不拥有取数实现**。
这不是某个任务被跳过，而是任务边界之间掉下去的一块。因此本次补口既补实现，
也补上唯一能证伪它的判据（返回值断言），并把锚点永久登记进变异清单。

### 守卫构成（`backend/tests/test_ai_chat_mcp_tools_data.py`，25 tests）

| 类 | 条数 | 判据 | 防的假绿形态 |
|----|------|------|-------------|
| `TestRealDataNonEmpty` | 6 | 真实 fixture 下 `items`/`rows`/`content` 非空且字段结构符合声明；`tb_query` 叶子模式只含叶子行、父行被排除、合计按 `closing_direction` 定符号 | **回退到空占位**（本次根因） |
| `TestNoPlaceholderRemains` | 4 | 运行时无 `status="placeholder"`、无空壳 `content=={}`；源码级 `_tool_*` 函数体内无 `placeholder` 字面量；`MCP_TOOL_IMPLEMENTATIONS` 与 `MCP_READONLY_TOOLS` 等势且全为协程 | 占位残留 / 只改注释不改行为 |
| `TestToolAuthorization` | 6 | 跨 project token、跨 project note_id、越 cycle 底稿（`wp_list` 隐藏 + `wp_read` 拒绝）、非成员 `tb_query` 一律**拒绝**而非空数据 | 「越权返回空」伪装成「无结果」 |
| `TestRoleMasking` | 3 | strict 与 none 两角色同 endpoint 结果**不相等**；partial 拿区间描述；未触阈值金额保持数值类型 | 脱敏对新返回结构是空操作 |
| `TestTypedErrorSeparation` | 5 | `semantic_unavailable` ≠ 空 results；零命中仍是 `success`；不存在 → `tool_resource_not_found`；非法参数 → `tool_invalid_argument`；endpoint 原样映射 error_code 不塌缩 | 三类错误都塌缩成空 dict |
| `TestReadOnlyGuarantee` | 1 | `mcp_tools.py` 剥注释后无 `insert`/`update`/`delete`/`commit` | 只读承诺失守 |

**「禁占位」源码判据的两道自检**（否则它自己就是假绿）：

1. **先剥注释再检查** —— 本模块的 docstring 大量引用「原本是 placeholder」，
   不剥注释会被自己的说明文字打红。
2. **反向自检** `test_placeholder_detector_is_not_vacuous` —— 故意向函数体插一个
   `placeholder` 字面量，判据**必须**抓到；同时故意插到注释里，判据**必须**放过。
   没有这条，判据可能已经因为剥注释太狠而变成恒真。

### 复用而非另写一套

| 工具 | 复用的平台能力 |
|------|---------------|
| `wp_list` | `ResourceAccessResolver.filter_visible_resources`（与 `MentionSearchService._search_workpapers` 同一可见集语义）+ `working_paper JOIN wp_index` |
| `wp_read` | 同上 JOIN（🔴 `working_paper` 表无 `wp_code`）+ `parsed_data` 为内容真源 |
| `tb_query` | `dataset_query.get_active_filter`（禁裸写 `is_deleted==False`）+ `four_table.tb_query.fetch_tb_subtree` + `leaf_aggregation.select_leaves`/`resolve_leaf_totals`（只汇总叶子；`tb_balance` 无符号绝对值 + 方向列，求和按方向带符号） |
| `addr_lookup` | `ai_chat.address_mention.resolve_address_mention`（已含授权 + 脱敏 + stale） |
| `kb_search` | `KnowledgeIndexService.semantic_search_strict`（embedding-only；平台原 `semantic_search` 自带 BM25/ILIKE 兜底，故新增严格版而非在 MCP 侧另写检索） |
| `note_read` | `DisclosureNote`；附注行真源 = `table_data.rows[].label` + `rows[].values` |
| `review_prompt` | `ReviewPromptService.load_prompt`（三级降级；只返回结构化字段不返回正文） |

**工具自身封顶**（Req 11.8：别先造 10 万行再被外层字节预算拒）：
`MAX_WP_LIST=200` / `MAX_TB_ROWS=500` / `MAX_ADDR_ROWS=50` / `MAX_KB_HITS=20` /
`MAX_NOTE_ROWS=200`，并在 SQL 层就下推 `cycle_scope` 与 `limit`。

### 脱敏调用链的实测修正

任务要求「**实测确认**外层 `_mask_service.apply_mask` 对新返回结构（含嵌套 dict/list
里的金额）真的生效，不生效就修调用」。实测结论：**不生效，已修调用**。

裸 `ExportMaskService.apply_mask` 的规则表只覆盖联系方式 / 银行账号 / 身份证号，
对「只含金额的试算表结构」是**空操作** —— `auditor`(strict) 与 `partner`(none)
会拿到逐字节相同的结果。故 endpoint 的脱敏步骤改走
`ai_chat.dsh_masking.mask_tool_result`（按 role + mask_policy 递归处理嵌套
dict/list 中的金额）。`TestRoleMasking::test_strict_and_none_role_results_differ`
就是这条修正的判据，变异 M34（跳过 `_mask_amounts_in_place`）RED 证明它有效。

### 变异检验（8 条全 RED）

锚点 **M28–M35**，登记在 `mutation_manifest.json` 的 `mcp_data_backfill` 段落。

| 锚点 | 变异 | 打红的预期测试 |
|------|------|---------------|
| M28 | `wp_list` 回到 `{"items": []}` | `test_wp_list_returns_real_workpapers` |
| M29 | `wp_read` 回到空 `content` | `test_wp_read_returns_real_parsed_data` |
| M30 | `tb_query` 回到空 `rows` | `test_tb_query_leaf_mode_aggregates_only_leaves` |
| M31 | `note_read` 回到 `status="placeholder"` | `test_note_read_returns_rows_from_table_data`（同时打红「禁占位」源码守卫） |
| M32 | 放宽工具内 `ResourceAccessResolver` 判定 | `test_out_of_scope_cycle_workpaper_is_denied` |
| M33 | token `cycle_scope` 裁剪恒放行 | `test_wp_read_denied_when_cycle_outside_token_cycle_scope` |
| M34 | `mask_tool_result` 跳过金额脱敏 | `test_strict_and_none_role_results_differ` |
| M35 | `semantic_search_strict` 恢复词法伪降级 | `test_kb_search_embedding_down_returns_semantic_unavailable` |

任务点名要求的三条对应：**非空** = M28（M29–M31 同类）· **授权** = M32（M33 同类）·
**脱敏** = M34。

**结论：8 条全 RED**（GREEN / ANCHOR-MISS / WRONG-TEST 各 0），生产代码字节级复原已校验，
无 `.bak` 残留。

复现（四态判定，只看退出码会把 GREEN/MISS/WRONG 误判成 RED）：

```powershell
python backend/scripts/diagnose/mutate_dsh_agent_panel_guards.py --check-anchors
python backend/scripts/diagnose/mutate_dsh_agent_panel_guards.py --pick "MCP取数" `
  --out .kiro/specs/dsh-agent-panel-integration/mutation_results_mcp_data.json
```

> `--out` 必须另指定：`mutation_results.json`（Task 33 全量 15 条）与
> `mutation_results_falsegreen_fix.json`（假绿修复 12 条）都不能被子集跑覆盖。

### 通用教训

**「三层管道全通 + 测试全绿」不等于「有数据流过」。** 管道类守卫（鉴权、白名单、
预算、审计成对）与数据类守卫（返回值非空、结构符合声明、越权拒绝而非空、
脱敏前后不相等）是**两个正交维度**；只做前者时，把每个 handler 的正文换成
`return {}` 依然全绿。这是 memory 记载的假绿第①源（additive 注入即死代码）
在**跨任务边界**上的新变体：代码不是没被消费，而是**被消费了但没人检查消费到了什么**。

判据要求：任何「取数 / 取值 / 检索」类实现，守卫必须有至少一条断言**返回内容本身**
（非空 + 字段结构 + 与输入数据的对应关系），而不只断言「调用成功」「状态码 200」
「字段存在」。
