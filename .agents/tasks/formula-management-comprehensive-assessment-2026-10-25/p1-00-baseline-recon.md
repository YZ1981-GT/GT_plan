# 阶段一 · P1-00 基线重建与 spec 现状核查

> 2026-10-25 · 只读调查（git 只读 + `git fetch --prune`、源码读、PG `SELECT`）。本文件是本步唯一写入；探针放 `C:\gt_wt\_probes\`，用完已删。
> 结论口径：spec 勾选只算「历史声称」；凡写「已确认」的都回到当前磁盘源码 / live PG 复核过。

## 1. Git 基线

| 项 | 现值 |
|---|---|
| 主工作树分支 | `spec/disclosure-note-doc-upload-and-batch-fill`（符合预期） |
| HEAD | `072cb8459cbf4d876923e87d6ae900ad4bcb4da9` |
| 审计基线 | `779d8b43619c5946c198e11ca35b1ad9330c5dfa` |
| `origin/spec/disclosure-note-doc-upload-and-batch-fill`（fetch 后） | `779d8b436…` = 审计基线；本地 **ahead 5 / behind 0**（5 个 S-cycle 提交未推送） |
| `origin/main` | `cd9592ff5`，本分支领先 582、落后 0（与公式修复无关） |
| 远端公式相关分支 | 仅 5 条 8~9 月旧分支（adj-formula / l-cycle / row-name / d4 两条），无进行中的公式远端分支 |
| 其他 worktree | `D:/GT_plan_ip_wt`（L 循环，detached）、`D:/GT_plan_wt/note-seed-tables`、WorkBuddy main —— 都不碰公式内核 |
| 迁移 | 仓库 203 个 `V*.sql`，最高 **V205**；live `schema_version` 最高 205。新 spec 的迁移号实施时动态取（目前下一个是 V206） |

### 1.1 基线 → HEAD 的 5 个提交（全是 S-cycle）

`e383f4069`（FEAT-001 applicable_when 生成链 + IPO 工具收敛）→ `1517804a3`（FEAT-002 12 个 s-checklist 组件接线）→ `0da7d5905`（S 段侧栏路由）→ `f0fdf7c92`（12 个 componentType 进白名单 / manifest / TS 投影）→ `072cb8459`（GtWpRenderer computed 修复）。27 个文件，+1448/-17。

和公式沾边的只有下面几处，**都不触及公式内核的语义**：

| 文件 | 改了什么 | 对公式修复的影响 |
|---|---|---|
| `frontend/.../composables/useD4FormulaEngine.ts` | `isIpoGroupVisible` 改为委托 `utils/ipoProjectUtils.isIpoProject`（+fraud_risk） | 只是 D4 的 IPO 可见性，和公式求值无关 |
| `backend/app/services/chain_orchestrator.py` | SELECT 加 `Project.business_category`，project_flags 加 `biz_ipo/listed/neeq/refinancing` | 底稿生成链，不是公式 |
| `backend/app/services/wp_generation_matching.py` | 加 `applicable_when` 分支 | 同上 |
| `backend/app/routers/wp_render_config.py` | 白名单加 12 个 s-checklist 类型；响应加 `applicable_when` | render-config 输出，不碰 prefill / formula |
| `useAProgramData.ts` / `useF2SpecialFormData.ts` | applicable_when dict 分支 / 注释 | 无 |

公式内核路径（`formula_engine.py`、`formula_management/**`、`formula_runtime/**`、`formula_settings/**`、`report_engine.py`、`unified_lineage_service.py`、`formula_timeline_service.py`、`routers/formula*.py`、`report_config.py`、`consol_note_formulas.py`、`components/formula/**`、`audit_log_helper.py`）在基线..HEAD 与 HEAD..工作树两段 diff 里**都没有出现**，评估报告的源码结论可以按 HEAD 沿用。

### 1.2 工作树未提交改动（并发 S-cycle 会话，非本任务）

`M` s-cycle spec 三件套、`components.d.ts`、`GtWpRenderer.vue`、`wp_render_config.py`（响应加 `business_category`）；`??` 本评估目录、`s-cycle-investigation/`、`s-cycle-p0-impl-2026-10-25/` 若干文件、s-cycle `tasks.meta.json`。
收尾时又多了 `M backend/app/services/wp_generation_matching.py` 和 `?? backend/scripts/analyze/_s_cycle_task03_probe.py`，都是并发 S-cycle 会话在本步执行期间加的（本步没写仓库文件）。
🔴 并发会话在本步执行期间仍在改 s-cycle `tasks.md`（两次读取之间勾选标记从 `[ ]` 变成 `[-]`/`[~]`），阶段二动共享文件（INDEX.md / memory.md / components.d.ts / wp_render_config.py）前要重新核对。

### 1.3 live PG 复核（只读）

`formula_setting / formula_sync_item / formula_publish / formula_template / formula_template_version / formula_template_subscription` = **0/0/0/0/0/0**；`wp_formula` 29；`financial_report` stale 8/2464；`disclosure_notes` stale 227/1090；`formula_push_run` 3、`formula_push_state` 171；`audit_log_entries(formula.changed)` 1。和评估报告的数字一致，live 状态在调查后没有变化。

### 1.4 P0 / 关键 P1 现读复核（当前磁盘 = HEAD）

| ID | 复核点 | 结果 |
|---|---|---|
| P0-1 Runtime | `formula_management/engine.py` 预载值只放 `kernel_ctx.row_cache[addr_id]`（L599~606）；`_topological_sort_formulas` 注释「循环依赖的公式保留原序」（L596~597） | 仍在 |
| P0-2 中央 execute | `formula_engine.py` L1778~1788 只取 `unadjusted_amount` 后 `from_simple_map` | 仍在 |
| P0-3 Draft Refresh | `formula_management/draft_refresh_orchestrator.py::_dispatch` 四个 scope 全走 `FormulaRuntimeCoordinator`；无 mutation 时走「marker-only 治理路径」（L251） | 仍在 |
| P0-4 report 三路语义 | `report_engine.py` 全量 L1381 / affected L2240 用 `parser_current.execute`，stale 重算 L2078 用 `execute_with_status` | 仍在 |
| P0-5 附件隔离 | `unified_lineage_service._query_attachments` SQL 只有 `target_type` + `target_ref LIKE` | 仍在 |
| P0-6 project-origin 陈旧决策 | `apply_ops.py` L145 `upstream_version=None`；`project_ops.py` L187~188 只在 expected 非空时比较 | 仍在 |
| P1-1 lineage 少参 | `unified_lineage_service` L119/L133 三参调用；`wp_trace_service.trace_upstream/downstream` 四参 | 仍在 |
| P1-2 timeline | `formula_timeline_service.py` 用 `AuditLogEntry.project_id/created_at`、`status=="applied"`、`FormulaPublish.created_at`、`FormulaTemplateVersion.created_at`，5 个 `except Exception: return []` | 仍在 |
| P2-1 合并附注角色 | `routers/consol_note_formulas.py` `EDITOR_ROLES=["admin","partner","manager"]` | 仍在 |
| P3-1 wired 常量 | `routers/formula_settings.py` `WIRED_DOMAINS` 七域常量 | 仍在 |

### 1.5 阶段二要知道的行数门（Python `split('\n')` 口径，对照 `backend/scripts/file_size_whitelist.txt`）

- `backend/app/routers/report_config.py` **801 行、未在白名单** ⇒ 改一行就被 pre-commit 拦；要改先抽伴生模块，或按先例以 HEAD 真实行数登记。
- `formula_engine.py` 2198 / 基线 2137（+5% 上限约 2243，**还剩约 45 行**）⇒ P0-2 的修复放进新模块，别往内核里加。
- `report_engine.py` 2625 / 2693、`FormulaManagerDialog.vue` 4216 / 4502：有余量，但不大。
- 其余（engine 757、orchestrator 475、coordinator 538、lineage 215、timeline 246、audit_log_helper 288、formula_settings/* ≤448）都在 800 以内。

## 2. 相关 spec 现状与交集

完成度用探针逐行数 checkbox（`- [x]` / `- [ ]` / `[-]` / `[~]` / 带 `*` 的可选项）。

| spec（位置） | 完成度 | 和公式修复的交集 | 冲突？ | 已覆盖本轮哪些 P0/P1 |
|---|---|---|---|---|
| `formula-fetch-followup-defect-closure`（active） | 30/34；没勾的是 3.6、4.2、4.3、4.5 | 3.6 附注模板绑定按新映射重生成（note_section 口径待拍板）；4.2/4.3 生成底稿 / 模板清单后端鉴权；4.5 鉴权基线下调。已完成的 R1~R9 碰过 `formula_ref_preload`、`report_engine`（删半成品开关）、formula debug 预载、PREV 三参、`formula_ref_check` | 没有语义冲突。**3.6 和 P1-6（附注 ownership）相邻**，本轮不碰附注模板绑定生成器。4.2/4.3 不是公式文件 | 都没覆盖。它修的是取数口径、引用存在性、地址库鉴权，基线评估已经把这些算进去了 |
| 　└ 依赖 `procedure-trim-generation-delegation-chain` | **在 `.kiro/specs`（含 `_archive`）、INDEX.md、三个其他 worktree 里都找不到** | 4.2/4.3 的说法是「门禁在该 spec 未入库的工作树改动里」 | — | 🔴 依赖物找不到，4.2/4.3/4.5 现在没人能推进；不归本轮，但要请用户确认它去哪了 |
| `formula-global-settings-sync`（`_archive/55-…`） | 勾选 36/36（8.2 `[x]*`），但文首写「35/36 必做 + 8.2 登录态 UI 走查未做」 | 就是 V199 治理内核本身；交付勘误 S5：「底稿旧保存路径 `wp_formula_service.save` 接入同步内核暂缓」 | 已归档、不回填（append-only）。本轮改的就是它的产物 ⇒ 新 spec 要登记对它的勘误 | 一个都没覆盖：P0-6、P1-5（wp effective / S5）、P1-7（outbox）、P2-2、P3-1 都是它留下的缺口 |
| `formula-governance-coverage-closure`（`_archive/67-…`） | 36/36 | 鉴权第三维、严格取数 R7a、push 预设层、校对目录、挂载守卫、底稿函数补齐。范围外登记：`consistency_gate` 82 处 `passed=True`（要拍板、另立 spec）、L1 `_handle_report` 不看期间、`_handle_prev` 不看列名、预填非严格 | 已归档。范围外第 2、3 条和本轮 P1-4（语法 / 语义统一）重叠 ⇒ 归本轮的候选 | 覆盖了公式路由的项目级鉴权（公式命名路由在两维扫描里已清零）；P0/P1 一个都没覆盖 |
| `formula-fetch-and-wp-generation-defect-closure`（`_archive/71-…`） | 19/19（`d9f08b55c` 是 HEAD 祖先） | 推送科目单源、PREV 三参、地址库整库、生成保留裁剪 | 无 | 无 |
| `formula-execution-path-convergence`（`_archive/60-…`） | 13/14（17 `[ ]*` start-dev 实测） | 早期一轮执行路径收敛；P0-4 / P1-4 说明它没收干净 | 无（已归档） | 无，本轮在它上面续做 |
| `formula-manager-runtime-integrity-closure`（`_archive/55-…`） | 29/30（7.2b `[ ]*`） | Draft Refresh 事务 owner、runtime outbox（`draft_refresh_service.py` 登记 2383 行） | 无（已归档）。P0-3 要改它留下的编排 | 无 |
| formula-push 系列（`_archive/23` / `41` / `63`） | phase2 18/18；all-subjects 26/26（正文有「待实施」，K1 导入后不自动推送，属历史假绿）；skip-reduction 30 + 2×`[-]`；row-matching 39/39；subtable 19/19 | Formula Push 是本轮要保留的样板；`note_writer` 是附注写方之一 | 无 | 无。K1 导入不自动推送可登记为 P2 候选，不进本轮 |
| `disclosure-payload-authority-source`（`_archive/08-…`） | 25/26（2.5 `[ ]*` Playwright） | 裁定：附注载荷权威源**留在前端** `build*SyncPayload`；否决后端重建 / 声明式下沉 | 🔴 **约束本轮**：P1-6 不能做「后端重建载荷」或把 builder 迁走；memory「全链打通阶段三」②附注权威源仍待拍板 | 无 |
| `consol-note-header-library-and-node-reaggregate`（active） | 84/87（22 `[ ]` 待用户确认；59.1 `[ ]` 清理） | 碰 `consol_note_formula_service`、`formula_push/note_writer`；task 22 = `note_writer.legacy_value_keys` 改调标题行库（待用户确认接手方式） | **文件级冲突风险**：本轮不碰 `note_writer.legacy_value_keys`。P2-1（合并附注 scope / 角色）它没涉及（`EDITOR_ROLES` / `scope_of` 0 命中） | 无 |
| `s-cycle-linkage-trimming-and-component-wiring`（active，三件套未提交、正被并发改） | 39 项，探针那一刻 0 勾选（4×`[-]`、32×`[~]`、3×`[ ]*`）；文首：「FEAT-001~003 须按 D1~D8 重新验收」 | 碰 `useS34FormulaEngine.ts`（前端 S34 子表公式）、`wp_account_mapping.json` 的 S 条目、`auto_data_resolvers` 新增 3 个 S resolver、`chain_orchestrator` / `wp_generation_matching` / `wp_render_config` / `GtWpRenderer` / `useD4FormulaEngine` | 语义上和本轮正交：它自己声明「S34 前端引擎是运行时计算层，与 `formula_settings` 正交；S 类不进 `formula_push_rules.json`（0 条）」。`formula-impact-analysis.md` 也确认 resolver 签名、`cycle_audited_amounts`、push 规则都不受公式模块影响（注意：那份分析写于 FEAT-001 提交之前，Q6/Q8 说的「未实现」已被 HEAD 的 `e383f4069` 改变） | 无。本轮**不得碰**上面列的 S-cycle 文件 |
| `audit-year-calendar-fallback-ratchet`（active，3/18） | 守卫已入库；R2 起「逐处判定 340+130 处年度兜底」未开工 | 前端各页的年度兜底可能包括公式中心 | 文件级风险：本轮新增代码如果用 `new Date().getFullYear()` / `year=2025` 兜底，会被它的棘轮拦；年度一律走既有单一来源 | 无 |
| 其余 active（d2-skeleton / oo-return / save-path-cpu / writeback-followup） | — | 底稿同步 / 回写，不碰公式内核 | 无 | 无 |

**小结**：没有哪个进行中或已归档的 spec 覆盖评估报告里的任何一条 P0（P0-1~P0-6）或 P1（P1-1~P1-9）。重叠只在相邻区域：附注写方 ownership、`note_writer`、底稿生成鉴权、年度兜底、S-cycle 底稿文件。

## 3. 评估材料要点

已读：`00-ground-truth.md`、`10-architecture.md`、`12-global-conflict-edit-template.md`、`13-lineage-governance-tests.md`、`draft-report.md`、`report.md`、`review-doc.md`、`review.json`。`11-coverage-matrix.md` 不存在（报告已如实披露）。

### 3.1 总判断（取自 report.md）

「统一治理框架（V199）+ 多运行时 + 局部已运行链路」，还不是贯穿全平台的单一公式中枢。结构评分 41/100（草稿是 54，按固定 25 项口径重算后下调）。Formula Push 是已运行的最佳样板；live V199 六表全是 0，模板没有任何真实采用。

### 3.2 P0 清单摘要（6 条，均已在 §1.4 复核仍在）

| ID | 一句话 | 关键证据 |
|---|---|---|
| P0-1 | Formula Runtime：addr_id 值只进 row_cache，函数照读空 map；遇到环按原顺序追加 | 真实 18 个 `WP()` 引用和严格求值器 18/18 不一致 |
| P0-2 | 中央 `/api/formula/execute` 拿未审数冒充审定数 / 余额；未知函数、除零、缺引用都返回 0 / ok | 华氏 1001 审定应 100、返回 0 |
| P0-3 | Draft Refresh 四个域都走错误的 Runtime，preset 只写 marker | 和平药房 report 0/7、note 0/0、adj 0/0、wp:D 0/4 |
| P0-4 | 报表全量 / affected / stale 三条重算路径语义不同 ⇒ false-fresh | 410 行里 50 行漂移、49 行标 fresh，最大差额约 39.3 亿 |
| P0-5 | lineage 附件查询不按项目过滤 | `_query_attachments` SQL；`attachment_lineage` 表没有 project_id |
| P0-6 | 项目→项目推送的 pending 没有 revision，旧弹窗会采用后来才推过来的定义 | `apply_ops` 写 None + `resolve_items` 只在非空时比较 |

### 3.3 P1 清单摘要（9 条）

P1-1 UnifiedLineage 少传 source，broad catch 吞成空 · P1-2 timeline 5 个来源里 3 个字段漂移、吞异常 · P1-3 `append_audit_log`（41 处调用 / 25 个文件）没有项目链锁，查询失败退回 genesis · P1-4 语法 / 参数个数 / PREV·PRIOR / 错误语义 / 精度多套各自为政 · P1-5 wp 的有效定义没被全部执行路径消费（含 S5 旧保存路径）；tb_detail 被标 wired 但没有消费者 · P1-6 附注多写方，stale 不收敛（227 条 stale_source 全空）· P1-7 settings 传播没有 durable outbox · P1-8 validator / 资源预算 / 回滚不统一（timeout 配置无人消费；回滚接受客户端传来的 `target_formula`；删除不带 expected_version）· P1-9 最终值没绑定计算版本（provenance）。

P2（5 条）：合并附注 scope / 角色 · 应用范围只接了 3/7 域 · 预设 4 处挂载有 3 处假保存、reference 主流程不可达 · 模板产品链缺口 · 发布记录可见性过宽 / 订阅按钮不看权限 / 删除策略。P3（3 条）：`wired` 常量与命名混用、`specAReady=false` 写死、spec 假绿门禁。

### 3.4 复核意见（review.json：CHANGES_REQUESTED，3 条阻断 + 1 条非阻断）还没收口

- F-01：「早期受控试点级」靠的是还没落地的冻结 / 隔离 / UAT ⇒ 建议把 41 分写成「结构评分」，风险调整后的档位定为「集成原型级」。
- F-02：第 21 项把调试器和 push 合并成一项计 3 分，正好决定 41 还是 40。
- F-03：lineage / timeline「确定性假空」按报告自己的 P0 文字标准应算 P0，却列在 P1。
- F-04：`11-coverage-matrix.md` 缺失。

**本步的处理建议**（阶段二用，不改 report.md）：采纳 F-03 的「收窄 P0」写法 —— P0 = 确定性影响**业务数值 / 权威写入 / 安全隔离**；lineage / timeline 假空属于「审计可观测性」，维持 P1，但放进第一批与 P0 一起修（改动小、风险低）。成熟度对外口径按 F-01 写成「结构评分 41 / 风险档位：集成原型级」。

## 4. 边界裁定

### 4.1 本轮（新 spec）负责

P0-1~P0-6 全部；P1-1、P1-2、P1-3、P1-8 里的「回滚目标由服务端取 + 删除带 CAS」；P1-5 里的「wp 执行路径只读 effective + S5 旧保存路径接同步内核」；P1-7（settings outbox）；P2-1、P2-3、P2-5；P3-1、P3-2。另外要给 `formula-global-settings-sync`（S5、8.2）和 `formula-governance-coverage-closure`（范围外 L1 期间 / 列名）登记勘误承接。

### 4.2 不归本轮（留在原 spec，或要用户拍板后另立）

| 事项 | 归属 | 本轮的做法 |
|---|---|---|
| 附注模板绑定重生成（note_section 口径） | formula-fetch-followup 3.6 | 不碰附注绑定生成器 / 映射表 |
| 生成底稿 / 模板清单后端鉴权、鉴权基线下调 | formula-fetch-followup 4.2/4.3/4.5（依赖的 spec 找不到） | 不碰；请用户确认 `procedure-trim-generation-delegation-chain` 的下落 |
| `note_writer.legacy_value_keys` | consol-note-header-library task 22 | 不碰这个函数 |
| S 类底稿 S34 前端公式 / resolver / mapping / applicable_when / render-config | s-cycle spec | 不碰它列出的文件（`useS34FormulaEngine.ts`、`wp_account_mapping.json` S 段、`chain_orchestrator.py`、`wp_generation_matching.py`、`wp_render_config.py`、`GtWpRenderer.vue`、`useD4FormulaEngine.ts`、`ipoProjectUtils.ts`） |
| 年度兜底 | audit-year-calendar-fallback-ratchet | 新代码不加日历年 / 写死年度兜底 |
| 附注权威源迁移（载荷后端化） | 待用户拍板（disclosure-payload ADR + 全链打通②） | 本轮最多产出字段级 ownership 只读矩阵，不迁写方 |
| `consistency_gate` 82 处 `passed=True` | 待拍板，另立 spec（governance 范围外） | 不碰 |
| tb_detail 定位（改名为预览，还是做成 TB 权威层） | 待拍板 | 第一批只做「不再标 wired / 不再给全部底稿标 stale」这类止血；写 TB 另立专项 |
| 统一 grammar / Resolver / Execution Contract 大迁移（P1-4、M1~M2）、provenance envelope（P1-9）、附注 writer ownership 收敛（P1-6）、模板双项目 UAT（M6）、自定义函数去留 | 下一个 spec（中期） | 本轮只给 P0 修复必需的最小 typed resolver / status 合同，不做全域迁移 |

## 5. 阶段二 spec 候选范围

按 memory 的膨胀控制（任务按交付单元合并到 40~50 个以内、三件套 ≤1500 行），建议**拆成两个 spec**。第一个只做「止错写 + 隔离 + 可信度」，第二个做「统一执行 / 传播 / 溯源」。

### 5.1 Spec A（本轮建议立项）：`formula-runtime-correctness-and-trust-closure`（暂名）

| 批 | 内容 | 主要文件 | 验收要点 |
|---|---|---|---|
| A1 冻结 / 安全闸 | 服务端拒绝 Runtime mutation apply，或在 P0-1 修好前只允许 dry-run；Draft Refresh 的 marker-only 不再报成功 | `formula_management/draft_refresh_orchestrator.py`、`draft_refresh_service.py`（在白名单，2383） | 修复前写入路径必须被服务端拒绝（端点测试 + 变异） |
| A2 Runtime 上下文与环 | TB/WP/NOTE/REPORT 引用走 typed resolver（复用 `TrialBalanceResolver` / `formula_ref_preload` / `evaluate_wp_formula_expression`）；遇到环返回 blocked | `formula_management/engine.py`、`formula_runtime/coordinator.py` + adapters（report enum / note rows 真实形状） | 真实 29 条 wp_formula：Runtime、严格轨、预览、写入四方一致；另外每类引用拿权威输入独立核算 |
| A3 中央 execute | 改用统一 resolver / status；错误不再 ok；trace 来自同一次求值 | `routers/formula.py`、新的伴生模块（`formula_engine.py` 只剩约 45 行余量） | 审定 100 返回 100；`EVIL()` / `1/0` / 缺 ROW 都不是 ok；value 与 trace 一致 |
| A4 报表三路统一 | 全量 / affected 也用 `execute_with_status` 的语义；失败保留旧值并标 blocked / stale | `report_engine.py`、`report_config.py`（**801 行未登记，要先抽模块**） | 【测试】项目逐值对账；false-fresh = 0；真实项目只做只读重算比对 |
| A5 lineage / timeline / 审计链 | 附件按项目隔离（join 反查，或 V206 补列）；`object_type→source` 映射；子源失败回 `partial/errors`；timeline 改用真实字段 + `unavailable_sources`；`append_audit_log` 加 advisory xact lock，查询失败 fail-closed；去掉 `specAReady=false` | `unified_lineage_service.py`、`formula_timeline_service.py`、`audit_log_helper.py`、`FormulaHistoryTab.vue` | 双项目同 ref 不串读；真 ORM 行能进时间轴；并发测试不分叉 |
| A6 冲突 CAS 与身份 | project-origin pending 带 revision；决策键改成 project + domain + slot 三段（兼容旧的两段键）；回滚目标由服务端从日志取，强制 CAS；删除带 expected_version | `formula_settings/apply_ops.py`、`project_ops.py`、`engine.py`、`template_sync.py`、`formula_settings/rollback.py`、wp 删除端点、前端 `FormulaPendingSyncDialog` / 回滚门 | 来源二次推送后旧决策 409；跨域同名 slot 不碰撞 |
| A7 范围 / 权限 / 假入口止血 | 合并附注只列 consolidated、全局写只给 admin（或拍板）；`wired` 拆成能力状态；预设 3 处没有 handler 的挂载改只读；发布记录按项目过滤；订阅按钮看 edit 权限 | `consol_note_formulas.py`、`formula_settings/*`、`routers/formula_settings.py`、`GtFormulaPresetDialog` 宿主、`FormulaSettingsToolbar` | 角色放行 / 拒绝表驱动测试；界面不再出现假成功 |
| A8 真实门禁 | 生产函数 + 真 PG 形状 + 逐值断言；Playwright 只在【测试】项目做写入验收 | tests | 删掉接线或制造错值时必须打红 |

### 5.2 Spec B（下一轮）：统一执行合同与 provenance

P1-4 统一 grammar / arity / status / Decimal（含 governance 范围外 L1 `_handle_report` 期间、`_handle_prev` 列名、前端 `PRIOR`）· P1-5 wp 全部执行路径读 effective + S5 · P1-6 附注 field ownership（在拍板之后）· P1-7 settings outbox · P1-9 provenance envelope + 最终值组件挂载 · P2-2 应用范围补齐 7 域 · P2-4 模板产品链 + 双项目 UAT。

### 5.3 立项前要用户拍板

1. P0 定义按 F-03 收窄（lineage / timeline 算 P1，但放进第一批修），还是把它们升为 P0。
2. A1 冻结方式：服务端直接拒绝（推荐，能被证伪），还是 feature flag 默认关。
3. 附件项目归属：join 反查（不加迁移），还是 V206 补 `project_id` 并回填（推荐后者，查询简单、能加索引）。
4. tb_detail 第一批只止血（不标 wired、不标全部底稿 stale），写 TB 另立专项 —— 是否同意。
5. 合并附注全局写权限：统一只给 admin，还是保留 partner / manager（要同步改统一规则）。
6. `procedure-trim-generation-delegation-chain` 现在在哪（formula-fetch-followup 4.2/4.3/4.5 卡在它上面）。

## 6. 本步没核实的

- 没重跑评估报告里的 Runtime 18/18 对拍、报表 410 行重算、lineage 探针（源码复核确认这些代码路径没变；live 计数复核过）。
- 没跑 pytest / vitest（本步只读，现有测试运行结果见评估报告 §11）。
- `procedure-trim-generation-delegation-chain` 只查了本仓 `.kiro/specs`、INDEX.md 和三个 worktree；git 全历史 `-S` 搜索超时（180 秒）没跑完。
