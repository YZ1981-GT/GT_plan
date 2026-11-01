# Phase 0 勘误：重写 requirements.md / tasks.md 打坏了 7 个机器消费方

日期：2026-11-01　｜　探针：`tmp_workpaper_sync_impl/probe_tasksmd_breakage.py`
（17 个同族脚本逐个 `--check`，按错误文本分三类）

## 1. 起因

跑 `generate_task66_legacy_deletion_plan.py --check` 想拿 Task 5.5 的基线，得到：

```
Task66GeneratorError: 从 tasks.md 只解析出 0 个 cycle→task 映射 —— 标题形态变了
```

该生成器的 `cycle_owner_tasks()` 显式写着「禁手抄 46..57 —— 任务号漂移时必须打红」，
按 `^- \[[ x~-]\] (\d+)\. …(\w)/?… 循环` 解析。我把 tasks.md 重写成 Phase 0~7 /
两级编号（`4.2 对账并收口 D/E entries`）之后，这条正则一条都匹配不到 ⇒ 门如设计所愿
打红了，红的原因是**我改了它依赖的契约**。

按「触类旁通」把同族全部读这两份文档的脚本跑一遍。

## 2. 普查结果（17 个脚本，`ok = 0`）

### 2.1 与 spec 文档形态相关的 —— 7 个

> 🔴 **归因已于同日更正，见 §5。**本节原标题是「我改坏的 —— 7 个」，那个结论是错的：
> 这 7 个在基线 `de31e7bf6` 上**就已经全红**（active spec 路径当时不存在，直接
> `FileNotFoundError`）。下表的「坏在」列读作「当前这一层的失败成因」，不是「本轮引入」。

| # | 脚本 | 失败文本（尾行） | 坏在 |
|---|---|---|---|
| 1 | `gen/generate_task66_legacy_deletion_plan.py` | 从 tasks.md 只解析出 0 个 cycle→task 映射 | tasks.md 标题形态 |
| 2 | `gen/generate_workpaper_sync_program_milestones.py` | `wave id must be an integer` | tasks.md：原 `Wave N` → 我写成 `Phase N` |
| 3 | `check/check_task68_backend_chain_independent_regression.py` | `tasks.md 里找不到 Task 68` | 任务号整套重编，68 不再存在 |
| 4 | `check/check_task69_frontend_independent_regression.py` | `tasks.md 里找不到任务 69` | 同上 |
| 5 | `gen/generate_workpaper_ac_coverage_matrix.py` | `AC 1.3 at L22 precedes any requirement heading` | requirements.md 结构 |
| 6 | `gen/generate_workpaper_word_template_adjudication.py` | `requirements.md 的 AC 7.7 原文形态变了，抠不出声明数字` | requirements.md AC 重编号 |
| 7 | `check/check_task71_mutation_capacity_recovery_gate.py` | `requirements.md 里找不到 AC 14.10 —— 容量 profile 的真源不可读，fail closed` | 同上 |

### 2.2 与本次无关 —— 10 个

**探针自己的错（3 + 2）**：`check_task61_oo94_word_pilot_gate.py` /
`check_task44_oo94_excel_pilot_gate.py` / `check_workpaper_ac_coverage_gate.py` 不收
`--check` 参数；`generate_workpaper_task61_word_pilot_probe_registry.py` /
`generate_workpaper_task44_pilot_probe_registry.py` 报
`ModuleNotFoundError: No module named '_spec_dir'`（要在 `backend/scripts/gen` 下跑）。
⇒ 这 5 条不计入破坏面，但说明**本探针的口径需要按脚本的真实 CLI 走**，不能一律 `--check`。

**预存的真实红（5）**：`generate_workpaper_resolver_migration_matrix.py`（digest 漂移）、
`generate_task64_dedicated_word_chain.py`（popup source digest 不可取）、
`generate_workpaper_task63_subcode_adjudication.py`（产物与现算不一致）、
`check_task70_oo94_full_entry_scenario_gate.py`（`docx/gt-a10-bundle` capability 未登记
`None`，封闭四态）、`check_task72_pre_delete_eligibility_gate.py`（overlay 裁决了源码里
已不存在的 writer：`n2_taxes_payable::n2_import_data` 等）。⇒ 各自归属别的 owner，
本 spec 只登记不代修。

## 3. 由此确认的两处我自己的假绿

### 3.1 Task 0.2「spec 引用闭合」标 `[x]` 是假绿 —— 已退回

我建的 `backend/tests/workpaper_sync/test_umbrella_spec_reference_closure.py`（14 例）
只查了 spec 三件套**内部**的互引（AC ↔ task ↔ property ↔ requirement）。它对「仓库里有
脚本把 requirements.md / tasks.md 当**机器可读契约**解析」这一类消费方**零覆盖**。
14 条判据里没有一条会因为上面 7 个脚本全红而打红。

这正是方法论铁律 ㉗① 说的情形：判据存在但对象从未被看过。闭合性必须包含**外部消费方**，
否则「引用闭合」只是文档自洽。

### 3.2 Task 5.5 的上游是死的

`workpaper_sync_task66_legacy_deletion_plan.json` 冻结在 `plan_commit d330d7cea6bb…`，
现在既不能 `--check` 也不能 `--write`。顺带现算它的腐坏程度（`probe_t66b.py`，
按 item 的 `path` + `sha256` 逐条核盘）：

| 现盘状态 | 唯一 path 数 | 说明 |
|---|---|---|
| 已不在盘上 | **28** | `useK1~K7DualMode.ts` / `useL2~L8DualMode.ts` / `useJ2,J3EntryDualMode.ts` / `useG7LonTer` / `useH5` / `useH7` / `useM9` 等 —— 被别的 spec 真删了 |
| 内容已变（sha 不符） | **28** | 含 `usePilotBridgeAdapter.ts`、`workpaperSyncModeStorage.ts`、`wp_onlyoffice_router.py`、`useD1/D2/D4`、`useK8~K13`、`useM2/M3/M4/M7/M10` 等 |
| 未变 | 70 | |
| 合计 | 126 | 计划声称 `items_disposition_pending_delete: 207`（215 item / 126 path） |

⇒ 计划里 **56/126 ≈ 44%** 的条目已失效。它当前报的 `pending_delete 207` 不是现状，
是 `d330d7cea6bb` 时点的快照。这恰好是 5.5 要求的「失效项自动移除」所针对的病。

## 4. 处置

1. **tasks.md 把 0.2 退回 `[ ]`**，并把「外部机器消费方闭合」写进它的验收判据。
2. **新增一项**收口这 7 个脚本：对「任务/AC 仍存在、只是编号或标题形态变了」的，改解析器
   按新形态取（仍从文档现算，不手抄编号）；对「被引用的任务在新计划里真的不存在了」的
   （Task 68 / 69 的义务已折进 7.x），要么retarget 到新任务号，要么显式登记退役并断言
   它真的退役 —— 不留永红门禁。
3. **5.5 的前置**改为「先让 Task 66 生成器可运行」，之后才谈升级为可收缩执行账；
   执行账的「失效项自动移除」口径按本文 §3.2 的三态（landed / drifted / intact）现算。
4. 探针口径修正：同族脚本的 CLI 不统一，普查必须按各自真实参数跑，否则会把「参数不对」
   误报成「门禁红」（本次 5 条即此）。

## 5. 归因更正（同日）：这 7 个在基线上就已经红，不是本轮引入

§2.1 原来写「我改坏的 7 个」。按方法论铁律「跑既有回归见红先回滚本轮改动复跑，不把别人的
红算到自己头上也不把自己的红推给别人」，拿基线 worktree 复跑后该结论**不成立**，现更正。

### 5.1 三条现算证据

| # | 事实 | 验证方式 |
|---|---|---|
| 1 | 基线 `de31e7bf6` 上 active spec 路径 `.kiro/specs/workpaper-html-onlyoffice-bidirectional-writeback-closure/` **整个不存在**，该 spec 当时只在 `.kiro/specs/_archive/17-2026-10-03-verified-batch/` 下 | 在 `tmp_workpaper_sync_impl/baseline_wt` 里跑生成器 `--check` → `FileNotFoundError: …\baseline_wt\.kiro\specs\workpaper-html-…\tasks.md`；`git ls-tree -r --name-only de31e7bf6` 过滤该 spec 名，全部命中 `_archive/17-…` 前缀 |
| 2 | **归档版** requirements.md 有 **170 条** AC 行（`^\d+\.\d+\.`），含 `11.5.`（L254，事件清单）、`7.7.`（L183，声明数字）、`14.10.`（L316，容量门） | 归档文件现读 |
| 3 | **active 版** requirements.md 只有 **7 条** AC（`1.3 / 1.4 / 1.5 / 1.7 / 12.1 / 12.8 / 12.9`），是 `workpaper_sync_migration_paradigm.json` 的 `adjudication_criteria.acceptance_criteria[].text` 投影；形态是 `1.3. …`，**不带 `AC ` 前缀** | 现读 + 真源 JSON 现算（真源里也只有这 7 条，11.5 / 7.7 / 14.10 在真源里**不存在**） |

### 5.2 真实的因果链

1. `239eb9a89`（归档 24 个 spec）把本 umbrella spec 整体移进 `_archive/17-…`。所有按
   `SPEC_DIR` 指向 **active** 路径的脚本从那一刻起就死了 —— 失败形态是 `FileNotFoundError`，
   **与文档内容无关**。这不是本轮引入的。
2. 本轮重建了 active spec 目录，但写的是一份**范围更窄**的新文档：7 条 AC 的投影 +
   Phase 0~7 两级任务编号。于是这些脚本从「文件找不到」前进到「文件找到了但解析不出」。
   失败形态变了，红没变。
3. ⇒ 处置责任仍在本轮（我是 active 权威文档的作者），但**不能记成「本轮打坏」**。

### 5.3 由此定下的修法（两份文档各管一段）

- **active tasks.md** 是「谁在做什么」的真源 ⇒ `cycle_owner_tasks()` /
  `tasks_md_task_ids()` / Word lane owner 这类**归属派生**读 active（已按新形态改完，
  现算 15 个循环字母、49 个两级任务号、Word lane owner `4.8`）。
- **归档 requirements.md** 是 Wave 6 那一轮**已冻结义务**的权威源（归档 spec append-only、
  不回填修改）⇒ AC 11.5 的事件清单、AC 7.7 的声明数字、AC 14.10 的容量门这类**冻结常量**
  读归档件。它们不在本轮 7 条 AC 的范围内，把它们塞回 active 投影会污染本轮真源
  （而且 `TestAcceptanceCriteriaVerbatim` 会逐字打红）。
- 两处都**不手抄**：路径显式、解析现算、形态变了就打红。

### 5.4 §2.1 表格的「坏在」列应如何读

读作「当前这一层的失败成因」。完整形态序列是：
`FileNotFoundError（239eb9a89 起）` → `解析不出 / AC 不存在（本轮重建 active 文档后）` →
`修完`。把中间那一层误记成「本轮引入」就会把一个预存债算到本轮账上，也会让读者以为
回退本轮改动就能恢复绿 —— 回退只会退回到第一层的红。

## 6. Task 66 生成器：从「复活」改判为「冻结 + 显式退役」

### 6.1 实修到哪一步

按「仍从文档现算、禁手抄编号」的口径，已真修三处解析层并逐层验证通过：

| 修的函数 | 原故障 | 修法 | 现算结果 |
|---|---|---|---|
| `cycle_owner_tasks()` | 两级编号 `4.2` 整行不匹配 ⇒ 映射 0 条 | 新增 `_TASK_LINE`（`\d+(?:\.\d+)+\|\d+` 两种都认）+ `_CYCLE_OWNER_TITLE_FORMS`（新旧两种标题形态）+ 按 `/` 与 `、` 切段只取单个 A-Z | 15 个字母全绑对：A/B/C→4.7、D/E→4.2、F→4.3、G/H/I→4.4、J/K/L→4.5、M/N→4.6、S→4.8 |
| `tasks_md_task_ids()` | 旧正则对 `4.2` **静默**只捕到 `4` ⇒ 整份清单退化成 `{"0".."7"}`，不抛异常只给错结论 | 改走 `_TASK_LINE` | 49 个两级任务号，与标题 `23/49` 一致 |
| `_word_lane_owner_task()` | 同一正则 + `sorted(hits, key=int)` 对两级编号会 `ValueError`；且多候选时 `[0]` **静默**挑一个 | 改走 `_TASK_LINE` + `_task_id_sort_key` 按段比较；候选不唯一改**抛错**而不是猜 | Word lane owner = `4.8`（唯一命中） |
| `ac_11_5_required_events()` | active 投影只有 7 条 AC，11.5 不在 | 新增 `ARCHIVED_REQUIREMENTS_PATH` 读归档件（Wave 6 冻结义务的权威源），缺文件时报明「不要退回去读 active 投影」 | 事件清单可现读 |

顺带修掉两个**静默错**（比直接报错更危险，列在这里备查）：两级编号被截断成一位数、
多候选时静默取首个。

### 6.2 为什么不继续往下复活

继续跑，错误逐层前移到 owner 校验：

```
Task66GeneratorError: owner task '72' 在 tasks.md 里不存在 —— owner 是编的   ← 已修（legacy→current 解析）
Task66GeneratorError: owner task '71' 在 tasks.md 里不存在 —— owner 是编的   ← 下一层
```

`'72'` 这一层我按同样口径修掉了：新增 `resolve_current_deletion_executor()`，锚点取
「标题同时含 `Task 66` 与 `删除计划`」，现算唯一命中 `5.5`，不手抄 `"72"→"5.5"`。

但 `'71'` 暴露出这是**整族**问题，不是三五处：Wave-6 的任务号（66 / 71 / 72 / …）被嵌在
多个**已冻结的数据文件**里（resolver 迁移矩阵、各 per-cycle 删除计划），而生成器会把每个
owner 都对当前 tasks.md 校验。要全部复活，就得为每个 legacy 号配一条 legacy→current 映射
—— 那正是「手抄编号」，只是摊开成了一张表。而且这张表一旦写下，就再没有东西能证明它对。

### 6.3 改判

**把 Wave-6 的 Task 66 计划当冻结输入，不再重生成；执行账另建生成器。**

依据：

1. 它本身就是**计划**产物（`why_this_task_only_plans`：「本任务只生成计划：不 feature-disable、
   不删除、不改调用点」），`plan_commit` 钉在 `d330d7cea6bb` —— 性质上是历史记录。
2. Task 5.5 的要求是「**升级为**可收缩执行账：已满足 entry 从 pending 进入物理删除并重验、
   失效项自动移除、计划外新增立即打红」。这三件事都只需要把冻结计划当**输入**，然后对现盘
   现算，不需要重跑 Wave-6 的生成算法。
3. 现算已证明冻结计划有 **56/126 ≈ 44%** 的条目失效（§3.2），所以「重生成得到一份新快照」
   本来也不是想要的东西 —— 想要的是**三态现算 + 棘轮**。

执行方式按 0.6 写的「显式登记退役 + 断言它真的退役」：把该生成器登记为「冻结产物、生成器
退役、由执行账取代」，并给冻结产物钉 digest 断言它**真的没再变**；**不**把它的 `--check`
留在任何门禁里当永红项。三处解析层的修复**保留**（它们本身是真缺陷，且执行账要复用
`_TASK_LINE` / `cycle_owner_tasks` / `_task_id_sort_key` 这些现算件）。

## 7. 消费方 #2 `generate_workpaper_sync_program_milestones.py`：wave 图已修，里程碑归属待拍板

### 7.1 已修（可验证）

原报 `wave id must be an integer`。查清后**不是**标题解析问题：该生成器从 tasks.md 里
`## Task Dependency Graph` 下的 ` ```json ` 块现读依赖图，要求

* 每个 wave 的键名是 **`wave`**（我重写时写成了 `id`）；
* wave 覆盖的任务集合与 tasks.md 的任务号**恰好相等**（我新增 0.6 后忘了进 wave ⇒ 会报
  `wave/task denominator differs`）；
* 同 wave 内不得依赖编号不更小的任务，也不得依赖更后 wave 的任务。

已改 tasks.md：`id` → `wave`（20 条）、`0.6` 纳入 wave 0（它是 `0.5` 的前置，必须在更早的
wave，否则 `0.5 → 0.6` 会触发 same-wave non-earlier 规则）、显式加 `dependencies: {"0.5": ["0.6"]}`，
并在 §Notes 写明这块是机器可读契约与三条约束。改完 wave 图这一层通过。

### 7.2 下一层：里程碑归属引用的是旧任务号（**需拍板**）

错误前移到 `SYNC-ENTRY-NAMESPACE: producer task does not exist: …:1`。源头是
`backend/data/workpaper_sync_program_milestone_definitions.json`，`review_status: "reviewed"`，
是**跨 8 个 spec 的程序级契约**。其中 6 条里程碑引用本 spec，共 **26 个失效 producer 任务号**；
`HOST-CONSUMES-UNIFIED-PATH` 的 **consumers** 也引用本 spec 的旧号 `40/41/42/43/70/72`
⇒ 重映射是**双向**的。

一条重要事实：**里程碑闭合由 `predicates` 判定，不由 producer 任务是否勾选判定**
（现读每条的 predicates：`manifest_integrity` / `python_symbols` / `database_readonly_schema` /
`runtime_evidence_required` / `host_path_entry_fact`）。所以改 `producers` 是**归属更新**，
不松动也不收紧任何门禁 —— 这一点降低了风险，但不解除「该归给谁」这个判断。

按 predicates 语义逐条对新计划：

| 里程碑 | 判据 | 旧 producer | 新计划里真正承接的任务 | 是否有诚实对应 |
|---|---|---|---|---|
| SYNC-ENTRY-NAMESPACE | manifest 完整性 + registry 三个符号 + request-path runtime evidence | 1/13/28/73/75 | `1.1` manifest 终态 · `1.7` 原子生成 · `2.7` closure checker 动态注册口径 · `6.2` runtime evidence 当前投影 | **有** |
| PUBLISHED-ENTRY-READY | manifest 完整性 + `PublishedIdentityObserver.observe` + registry 符号 + per-entry request-path evidence | 75/76 | `1.1` · `1.7` · `6.1` required scenario set · `6.2` | **有** |
| SYNC-DURABLE-APPLICATION | `CallbackDeliveryService` / `RequestApplicationService` / `OoToHtmlCoordinator` + DB schema + 真实回调 evidence | 22/23/26/29/30 | `6.3` 真实 OnlyOffice scenarios · `7.3` schema 与迁移边界 | **有**（但原始交付在归档轮，新计划只负责复验） |
| SYNC-UNIFIED-ROOM | `RoomService` / `CommandServiceClient` / `MaterializeCoordinator` + DB schema + 真实 room forcesave/close evidence | 21–30（10 个） | `6.3` · `7.3` | **有**（同上） |
| HOST-CONSUMES-UNIFIED-PATH（per_entry，8 条 host_path_entry_fact） | 宿主走统一路径的 8 条事实 | producer `33`；consumer 本 spec `40/41/42/43/70/72` | producer → `3.5` 宿主迁到共享 presentation 门；consumer → `4.2`~`4.8` 逐 entry 收口 | **有** |
| **SYNC-MULTI-RESOLVER** | `writer_gate_issue_zero` + `CanonicalResolutionService` 符号 | 12/71/74 | **新计划没有专任承接项**。最接近的是 `2.7`（closure checker 口径）与 `7.1`/`7.2`（全量与辐射面回归），但那是「复验」不是「生产」 | **没有** |

### 7.3 为什么停在这里问

1. 这份文件 `review_status: "reviewed"`，且是**跨 spec** 契约：`custom-workpaper-template-ingestion-and-sync-closure`
   的任务 10 / 14 以它为前置。改它影响另一份 spec 的读数，不该由本 spec 单方面定。
2. **SYNC-MULTI-RESOLVER 在新计划里没有诚实对应**。硬塞给 `7.1`/`7.2` 就是把「复验」写成
   「生产」—— 属于伪造归属，正是本 spec 要消灭的那类事。
3. 另四条的「原始交付在归档轮、新计划只负责复验」同样需要确认：是否接受把 producer 改成
   复验方，还是应当保留对归档轮的指向（若保留，`specs` 清单里没有归档 spec 名，需要先决定
   是否允许 producer 指向已归档 spec）。

三个可选方向（按我的推荐排序）：

* **A（推荐）**：按上表改 5 条有诚实对应的；`SYNC-MULTI-RESOLVER` **新增一项任务**承接
  writer gate zero 与 CanonicalResolutionService 的收口，再把 producer 指向它。代价是任务数
  49 → 50，但归属全部真实。
* **B**：按上表改 5 条；`SYNC-MULTI-RESOLVER` 的 producer 显式标注为「原始交付在归档轮，
  本轮无承接项」—— 需要 schema 支持这种表达（当前 `producers` 只有 `spec` + `tasks`，
  要加字段就得动 reviewed schema）。
* **C**：整份定义文件按「程序级契约随 spec 重编一并重审」处理，由上游 owner 统一改，
  本 spec 只登记阻塞。

未经拍板不动这份 reviewed 文件。
