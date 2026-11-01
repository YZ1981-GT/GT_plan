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

### 2.1 我改坏的 —— 7 个

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
