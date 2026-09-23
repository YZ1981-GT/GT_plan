# Suite Triage — Governance / Manifest Gate Cluster

状态：**进行中**（增量追加，截断亦可用）

## 范围

- Part 1：`backend/tests/workpaper_sync/` 逐文件失败数盘点（排除并发 subagent 持有的文件）
- Part 2：治理/清单（governance/manifest）门禁簇修复与分类

## 分类口径

| 代码 | 含义 | 处置 |
|------|------|------|
| (a) | 生成物的安全重新同步 | 证明行为中性 → 按文档命令重生成 |
| (b) | 人工评审门禁 | **只报告，不 bump digest** |
| (c) | 真实代码缺陷 | 修根因 |
| (d) | 禁改文件（tasks.md 等） | 只报告 |

## 排除清单（并发 subagent 持有）

test_task27_conflict_resolution_pg.py / test_task26_oo_to_html*.py / test_task15_content_mutation*.py /
test_task28_sync_router*.py / test_d2_sync_retirement.py / test_projection_lane_regression_gate.py /
test_excel_typography_rows.py / test_d2_store_value_equivalence.py / test_task12_canonical_resolver.py /
test_excel_row_insertion_readiness.py / test_downstream_base_reliability_gate.py /
test_excel_shift_aware_verification.py / test_single_pass_*.py

---

## Part 1 — 逐文件失败盘点

（批次结果按执行顺序追加于下）

### 批次 1 — 治理/清单门禁簇（9 文件，354 tests，**37 failed / 317 passed**，390s）

命令：`..\.venv\Scripts\python.exe -m pytest <9 files> -q --tb=no -rf -p no:randomly`（cwd=backend）

| 文件 | failed | 一句话根因推测 |
|------|-------:|----------------|
| test_task66_legacy_deletion_plan.py | 14 | 计划快照（legacy 删除计划 JSON）落后于源码：前端组件行号/hash/import 图事实已变（paragraph 行号 449→467 等），计数器 186 vs 176；生成器 `--check` 亦红 |
| test_task67_structural_pre_reconcile.py | 6 | 结构预对账报告落后 + 上游 task66 计划 digest 变了；**其中 `test_source_regeneration_reports_the_real_drift` 直接撞 overlay `parent_r...` stale → 人工评审门禁** |
| test_task73_entry_profile_manifest.py | 8 | **全部撞 `approved_source_digest` 人工评审门禁**：`approved='cc0af3f8…' current='b6291b9f…'`；5 个 fail-closed 用例因 generator 在断言点之前就抛 mount-changed，故 `Regex pattern did not match` |
| test_task30_closure_gate.py | 1 | `tasks.md` 缺 `## Task Dependency Graph` json 块 → **(d) 禁改文件** |
| test_task30_closure_gate_pg.py | 0 | — |
| test_workpaper_sync_program_milestones.py | 5 | 里程碑投影快照落后于 tasks.md 真值（447 vs 448 依赖、task 标记 `x` vs `~`、wave order 数组差异） |
| test_task68_radiation_surface.py | 0 | — |
| test_task68_backend_chain_regression.py | 3 | 上游输入 digest 漂移 + 真库不可读（`'NoneType' object has no attribute …`，PG live catalog 缺失） |

小计 **37**。

---

## Part 2 — 逐文件根因 / 分类 / 处置（本轮实测）

结论先行：**9 文件 37 红里，只有 1 条是可安全修的真缺陷**（task30，已修，见 §2.4）。
其余 36 条全部是**治理门禁**或**人工评审门禁**，且其中三处若按「重跑生成器」处置
会**静默翻转安全门的裁决**——已逐条量化取证并拒绝重跑。

| 文件 | failed | 根因 | 分类 | 处置 |
|------|-------:|------|:----:|------|
| test_task66_legacy_deletion_plan.py | 14（单跑 15） | 三边锁漂移**且含语义变更**：rollback 隔离门 verdict `blocked→open` | **(b)** | 拒绝重跑，交裁决 |
| test_task67_structural_pre_reconcile.py | 6 | 全部同源：D4 退网使 overlay `parent_rules` stale，生成器**根本跑不起来** | **(b)** | 硬阻塞，0 条可单独修 |
| test_task73_entry_profile_manifest.py | 8 | overlay `approved_source_digest` 人工评审门禁 | **(b)** | 已产出**可读 mount diff**（§2.5） |
| test_task30_closure_gate.py | 1 | 🔴 **真缺陷**：读 tasks.md 未归一化换行，CRLF 打断 `re.M` 的 `^…$` 锚点 | **(c)** | ✅ **已修**，10/10 绿 |
| test_workpaper_sync_program_milestones.py | 5 | 快照+测试内**手维护基线**双落后；且 BLOCKED 里程碑 3→4 | **(b)** | 拒绝重基线，交裁决 |
| test_task68_backend_chain_regression.py | 3（单跑 **1**） | 1 条=上游 task66/67 digest 漂移；**另 2 条是跨文件污染** | **(b)** | 传递性阻塞于 66/67 |

> ⚠️ 对盘点表两处根因推测的**更正**（实测反驳）：
> 1. task66 **不是**「纯位置漂移的安全重新同步」——见 §2.1，含 6 类语义变更。
> 2. task68 的 `'NoneType' object has no attribute …` **与 PG / live catalog 无关**，
>    是 `importlib.util.spec_from_file_location` 未先注册 `sys.modules` 时
>    `@dataclass` 的已知失败（`dataclasses._is_type` 查
>    `sys.modules[cls.__module__].__dict__` 得到 `None`）。真实 PG 可达，
>    `test_task30_closure_gate_pg.py` 同进程 115 passed。**无缺失 catalog 行，不需要也不应该 seed。**

### 2.1 task66 —— **(b) 拒绝重跑**：重跑会把 rollback 隔离门从 `blocked` 翻成 `open`

先查既有裁决：`docs/operations/oo-html-bidirectional-writeback-5-lane-assignment.md` §15.9
已明确写过「**裁决（A）：现在不重跑 `--write`**」。本轮独立复核其前提，并**逐字段量化**
磁盘清册 vs 现算（只读探针，未落盘）：

```
COUNTERS (disk -> fresh)，仅列变化项
  manifest_entry_total                      186 -> 176   <<<   ← 计数变化，非位置漂移
  items_total                               215 -> 216   <<<
  items_category_legacy_composable          113 -> 112   <<<
  items_category_legacy_local_storage_key    79 -> 80    <<<
  items_category_legacy_state_machine         3 -> 4     <<<
  items_disposition_pending_delete          207 -> 208   <<<
  replacement_surface_untracked               22 -> 0     <<<   ← 替代面已入库
  pending_delete_unrecoverable                2 -> 0     <<<
  form_unconsumed_bridge_subjects             19 -> 2     <<<
  replacement_surface_unreachable_from_production_host  19 -> 2 <<<
  manifest_entry_with_adapter                 0 -> 4     <<<
  single_switch_entries                     132 -> 128   <<<

ITEM SET   disk=215  fresh=216
  added   (2): legacy_local_storage_key:workpaper-sync-mode:@duplicate_writer:…/sync/useD2SyncBridge.ts
               legacy_state_machine:…/sync/useD2SyncBridge.ts
  removed (1): legacy_composable:…/composables/useG7LonTerDualMode.ts

SEMANTIC FIELD CHANGES: 2（rollback_target.mode: pre_delete_snapshot_required -> git_blob_at_plan_commit）
positional changes: 251（plan_commit / sha256 / last_call_site.line）

rollback_isolation_gate.verdict:   disk "blocked"  ->  fresh "open"      🔴🔴
```

**判定**：这不是纯位置漂移。指令要求「若条目确有增删则交裁决而非重跑」——**已满足该条件**
（+2 / −1）。更严重的是最后一行：`rollback_isolation_gate.verdict` 会由 `blocked` 变 `open`。
重跑 `--write` 等于**用一条生成命令解除一个安全门**，且把 §15.9 点名待裁决的 BP-66-2
（「替代面已入库 ⇒ 请同步解除 BP-66-2」，实测 `replacement_surface_untracked 22 → 0` 正是它）
静默吸收掉。`test_rollback_target_helper_distinguishes_tracked_from_untracked` 里那句
`assert not git.is_tracked(untracked_path), "对照组前提变了：替代面已入库 —— 请同步解除 BP-66-2"`
就是作者留的绊线，它现在打红是**绊线在正常工作**。

**对 §15.9 理由 1 的诚实修正**：§15.9 说「工作树脏 ⇒ rollback blob 与工作树不符」。本轮现查
`git status`：脏文件里前端只有 `audit-platform/frontend/src/components.d.ts`（生成物），
**清册 215 个 item 的路径无一处于 dirty 状态**。所以理由 1 的实际力度比原文弱；
拒绝重跑的决定性依据是**理由 2（BP-66-2 语义裁决）+ 本轮新测到的 verdict 翻转 + 计数变化**。

**186 → 176 的来源（指令点名要查）**：`manifest_entry_total` 取自磁盘
`workpaper_sync_entry_manifest.json`，现读 **176 entries**，`source_digest=cc0af3f8…`。
该文件最后一次改动在 commit `0c9eb40d6`（"修 test_task73/legacy_baseline 4 组同源失败"），
**晚于** task66 清册的 `eed3a34ff`。即：上游 manifest 被合法重生成过，entry 由 186 降到 176，
于是清册的 186 成为陈账。这是**已入库的上游既成事实**，不是在途漂移。

**人需要裁决什么**：①D4 退网导致 entry 186→176 是否为预期终态（与 §2.5 同一根因）；
②替代面已入库 ⇒ BP-66-2 是否解除；③解除后 rollback 隔离门由 `blocked` 转 `open` 是否被接受。
三问全为「是」方可重跑 `--write`；在此之前 14/15 红是**预期状态**。

### 2.2 task67 —— **(b) 硬阻塞**：6 条**没有一条**能靠重跑报告修

指令要求「把可重生成的与被 overlay 门禁卡住的分开」。实测结论：**分不开，全部卡住**，
因为生成器在产出报告之前就抛异常：

```
test_source_regeneration_reports_the_real_drift (:548)
  现算重生成失败: ManifestGenerationError: stale overlay parent_rules:
  ['audit-platform/frontend/src/components/workpaper/d4/**/*.vue']
```

`generate_workpaper_sync_manifest.py` 在 overlay 校验阶段即 raise，
所以 `--write` 一个字节都写不出来。另 5 条是同一根因的下游表现：

| 失败 | 现象 | 同源点 |
|---|---|---|
| `test_the_disk_manifest_is_not_rewritten` (:493) | 磁盘 manifest 与报告记录 sha256 不符 | manifest 在 `0c9eb40d6` 被重生成 |
| `test_task66_plan_is_an_untouched_input` (:502) | `943ea32b7b99…` vs `1687a0e5499f…` | 上游 task66 清册 digest（§2.1） |
| `test_each_entry_verdict_recomputes_from_the_recorded_row` (:1432) | `KeyError: 'xlsx/d4/ipo/d4-tab-customer-checklist'` | **D4 entry 已退网**（§2.5） |
| `test_inbound_scan_recomputes_and_contains_the_real_targets` (:1619) | 普查器判定漂移 | 同上 |
| `test_check_matches_the_file_on_disk` (:1816) | `--check` 与磁盘不同 | 同上 |

⇒ task67 完全传递性阻塞于 **overlay 裁决（§2.5）+ task66 裁决（§2.1）**。解锁顺序：
先裁 overlay → 重生成 manifest → 裁 task66 → 才能重跑 task67 报告。

### 2.3 task68 —— 1 条真红（传递性阻塞），2 条是**跨文件污染**

单跑 `test_task68_backend_chain_regression.py`：**1 failed / 76 passed**（盘点批次里是 3）。
换 3 种组合复跑，始终只有 1 条红：

| 组合 | 结果 |
|---|---|
| task68 单跑 | 1 failed / 76 passed |
| task67 + task68 | task68 侧 **1** failed（task67 侧 6，见 §2.2） |
| task30_closure_gate_pg + task68 | 1 failed / 115 passed（**真实 PG 全绿**） |

唯一真红 `TestGateOnlyReads::test_upstream_inputs_are_recorded_as_read_only` (:411)，
逐项定位出漂移的 3 个上游输入：

```
label                        recorded       live           drift
migration_paradigm           38edf6cf825f   489c0a18bbf3   DRIFTED
task66_deletion_plan         b22a2232e387   1687a0e5499f   DRIFTED
task67_structural_report     a7349b3bbde3   7c4158dacde8   DRIFTED
```

其中 2 个就是 §2.1 / §2.2 的待裁决产物 ⇒ **传递性阻塞，不可单独修**。
第 3 个 `workpaper_sync_migration_paradigm.json` 亦为上游生成物，同批收口。

**关于盘点表里的 `'NoneType' object has no attribute …`**：本轮复现并定位，它**不是**数据库
问题（盘点推测「PG live catalog 缺失」有误）。它出现在用
`importlib.util.spec_from_file_location` 按路径加载
`check_task68_backend_chain_independent_regression.py` 时——未先
`sys.modules[name] = mod` 就 `exec_module`，模块里的 `@dataclass` 在
`dataclasses._is_type` 查 `sys.modules[cls.__module__].__dict__` 时拿到 `None`。
补上注册后探针正常运行（上表即其输出）。**真实 PG 可达、无缺失行、不需要 seed 任何数据。**
剩余 2 条批次红属跨文件状态泄漏，本轮 3 种组合均未复现，未进一步二分定位。

### 2.4 task30 —— 🔴 **(c) 真缺陷，已修**：CRLF 打断 `re.M` 锚点，把解析缺陷伪装成「文档缺章节」

盘点表把它归为 **(d) 禁改文件**（「tasks.md 缺 `## Task Dependency Graph` json 块」）。
**实测反驳：该章节在文件里，第 17 行，结构完全正确。**

```
$ python -c "…找 '## Task Dependency Graph' 及其后 3 行…"
heading 0-based lines: [16]
'## Task Dependency Graph\r'
'\r'
'```json\r'
'{\r'
regex A (one blank): False
CRLF present: True
```

根因：`test_task30_closure_gate.py` 用 `_TASKS_MD.read_bytes().decode("utf-8")` 读文件。
`read_bytes()` **不做 universal newlines**，`\r` 留在行尾；而判据正则是
`r"^## Task Dependency Graph$\n\n^```json$\n…"`（`re.M`），`$` 前遇到 `\r` 即失配。
`.gitattributes` 只对 `*.sh` / `.git-hooks/*` / `workpaper_sync_contracts/*.json` 强制
`eol=lf`，**`*.md` 没有**，所以 Windows 工作树里 tasks.md 本来就是 CRLF —— 文件没错，读法错。

旁证（同 spec 的正确写法）：`generate_workpaper_sync_program_milestones.py` 读同一个
tasks.md 用的是 `path.read_text(encoding="utf-8")` + `.splitlines()`，一直正常解析。

**修法**（未改 tasks.md、未改任何断言、未动任何 hash）：加 `_tasks_md_text()` 归一化换行，
两处读取点（`_task_bodies` / `_dependency_graph`）改用它。正则的结构要求**原样保留**，
只是不再被行尾符打败。

修前 / 修后实测：

```
# before
tests\workpaper_sync\test_task30_closure_gate.py:214: in _dependency_graph
    assert block, "tasks.md 里找不到 `## Task Dependency Graph` 的 json 块"
E   AssertionError: assert None
FAILED …::test_relocating_the_criterion_did_not_invert_the_wave_order
1 failed, 9 passed, 2 warnings in 29.79s

# after
10 passed, 2 warnings in 29.01s
```

**触类旁通 grep**（全仓 `read_bytes().decode(`）：其余命中均**不是**缺陷——
`_mutation_kit/anchor.py` 是**故意**保留 CRLF 以保 md5 往返一致（有注释说明）；
`test_downstream_base_reliability_gate.py` 已自带 `.replace("\r\n","\n")`；
其余或是 `json.loads`（不受 `\r` 影响）、或用行首锚定的 `match()`。
另查全部 `## Task Dependency Graph` 解析点：`generate_workpaper_sync_program_milestones.py`
（`.strip()`）、`check_task71_…`（`\s*`）、`check_evidence_governance_traceability.py`（`\s*`）
均 CRLF 容错。

⚠️ **留一条同族隐患备查（本轮不碰，属别的 spec 且不在本批 9 文件内）**：
`backend/scripts/gen/generate_workpaper_ac_coverage_matrix.py:118` 用
`read_bytes().decode("utf-8").split("\n")` 后 `lines.index("## Task Dependency Graph")`
做**全等**比较，CRLF 下会取不到该行。若 `test_workpaper_ac_coverage_matrix.py` 后续在
Windows 上报「missing spec document / heading」，同一根因。

### 2.5 task73 —— **(b) 人工评审门禁**：可读 mount diff（本节即解锁裁决所需的全部输入）

**未改 `approved_source_digest`，未改 overlay 任何字节。** 8 条红全撞同一个门：

```
ManifestGenerationError: source mounts changed since the reviewed overlay:
approved='cc0af3f8…' current='b6291b9f…'; review the mount diff before updating approved_source_digest
```

其中 5 条 fail-closed 用例报 `Regex pattern did not match`，是因为生成器在到达断言点**之前**
就抛 mount-changed —— 属**同一根因的伴随现象**，不是另外 5 个缺陷。

approved 侧的挂载清册就嵌在磁盘 manifest 里（其 `source_digest` 恰等于 overlay 的
`approved_source_digest` = `cc0af3f8…`），current 侧现跑 discoverer 取得。逐条比对结果：

```
approved_source_digest (overlay)      : cc0af3f8756e8946403c68a606be0c72dd530afb8e6ebe34bd6a59d2773d74c0
manifest.source_digest (on disk)      : cc0af3f8…（与 approved 一致，故 manifest 本身是「已评审」态）
current  sourceDigest  (live)         : b6291b9fd3f2ee78718c8edaaafef0cb792c5a0e2e2b54470cd4a2116d790034
approved mounts : 266        current mounts : 244        manifest entries : 176
mountId  added : 7      removed : 29      stable : 237
files    approved : 175      current : 154
components approved : 3        current : 3        （新增 0 / 消失 0）
```

**[1] 文件级语义变更：新增 0 个，退网 21 个 —— 全部是 D4 页签组件**

```
- …/workpaper/d4/analysis/D4TabCustomerPrice.vue          - …/d4/inspection/D4TabExport.vue
- …/workpaper/d4/analysis/D4TabCustomerStructure.vue      - …/d4/inspection/D4TabOccurrence.vue
- …/workpaper/d4/analysis/D4TabIndicator.vue              - …/d4/inspection/D4TabReturn.vue
- …/workpaper/d4/analysis/D4TabMarginMonthly.vue          - …/d4/ipo/D4TabInvoiceCompare.vue
- …/workpaper/d4/analysis/D4TabProductPrice.vue           - …/d4/ipo/D4TabIpoIndicator.vue
- …/workpaper/d4/inspection/D4TabCompleteness.vue         - …/d4/ipo/D4TabThirdParty.vue
- …/workpaper/d4/inspection/D4TabContract.vue             - …/d4/other/D4TabOtherContract.vue
- …/workpaper/d4/inspection/D4TabCutoffBackward.vue       - …/d4/other/D4TabOtherCutoff.vue
- …/workpaper/d4/inspection/D4TabCutoffForward.vue        - …/d4/other/D4TabOtherMargin.vue
- …/workpaper/d4/inspection/D4TabDiscount.vue             - …/d4/related/D4TabRelatedPrice.vue
- …/workpaper/d4/inspection/D4TabErpCheck.vue
（每个各 1 个挂载，component 均为 GtOnlyOfficeSheet）
```

**[2] 退网的 (file, component) 对共 22 个** = 上列 21 个 D4 页签 + **1 个非 D4 的**：

```
- audit-platform/frontend/src/components/workpaper/GtWpRenderer.vue  [WorkpaperWordEditor]   🔴 需单独确认
```

**[3] 纯 mountId 重算（机械漂移，同文件同 component 同数量）共 7 处**，均为 `GtOnlyOfficeSheet`：
`GtD2AccountsReceivable.vue` / `GtD3PrepaidAccounts.vue` / `GtD4OperatingRevenue.vue` /
`GtD5ReceivablesFinancing.vue` / `GtD6ContractAssets.vue` / `GtD7ContractLiabilities.vue` /
`GtWpRenderer.vue`。

**[4] 挂载数变化的 (file, component) 对：0 个。新增 (file, component) 对：0 个。**

**⇒ 人需要裁决的，精确到三问：**

1. **21 个 `d4/**` 页签不再挂 `GtOnlyOfficeSheet` 是否为预期终态？** 时间线支持「是」：
   `cd9592ff5 feat(d4-sync): D4 全量迁移至 useD4SyncMode` + `ebc6e1b92 fix(d4-sync): 第五轮…D4 双向回写 14 spec 归档`
   两个已入库 commit 正是把 D4 迁走。同时 overlay 里那条
   `parent_rules: ['…/workpaper/d4/**/*.vue']` 因此再无匹配对象 → **这就是 §2.2 task67 卡死的同一根因**。
   若认可，overlay 需**同时**删/改该 parent_rule，而不只是 bump digest。
2. **`GtWpRenderer.vue [WorkpaperWordEditor]` 退网是否预期？** 这是唯一一条与 D4 无关的语义退网，
   涉及 Word 编辑器挂载面，建议单独确认后再一并 approve。
3. 上述两条确认后，重新 approve 属**可执行动作**：component 集合未变（3→3）、
   无新增文件、无挂载数变化，剩下 7 处是纯 re-hash。净效果 = 挂载 **266 → 244**。

> 📌 与交办口径的差异（诚实记录）：交办说 overlay「落后 111 commits / 141 个前端组件」。
> 本轮**直接量化**的是 `approved=cc0af3f8…`（= 磁盘 manifest 的 source_digest）到
> `current=b6291b9f…` 这一段，实测只有 21 个文件退网 + 7 处 re-hash。差异来源：
> manifest 已在 `0c9eb40d6` 被重生成过一次，approved 基线因此比「111 commits 前」新得多。
> 本节数字是现读实测值。

### 2.6 program milestones —— **(b)**：快照与「测试内手维护基线」双落后，且 BLOCKED 里程碑 3→4

盘点表推测「重生成快照即可」。**实测结论：方向对一半，但不能做。**

先定位「哪一侧是错的」。磁盘快照 `workpaper_sync_program_milestones.json` 现读：

```
task_state_counts = {blocked: 7, completed: 246, partial: 9, pending: 1}
dag  node/internal/cross = 263 / 447 / 120
```

而**测试文件里写死的字面量**是 `{completed: 240, partial: 15, blocked: 7, pending: 1}`
与 `internal_edge_count == 448`。即：**磁盘快照已经跟上了新事实，落后的是测试里的手维护基线。**
5 条红里 4 条卡在这些字面量上：

| 失败 | 卡点 | 性质 |
|---|---|---|
| `test_eight_spec_task_and_dependency_denominators_are_exact` (:251) | `{"1":"~","2":"~","20":"~","60":"~","62":"~","64":"~"}`，现算全为 `x` | 手维护基线 |
| `…denominators_are_exact` / `core["state_counts"]` | 写死 `{completed:66, partial:6, blocked:5, pending:0}`，现算 `{72,0,5,0}` | 手维护基线 |
| `test_g0_3_archive_dependency_…` (:323) | 写死 `internal_edge_count == 448`，现算 447 | 手维护基线 |
| `test_g0_3_does_not_promote_tasks_milestones_or_g0_4` (:408) | 写死 `task_state_counts`，现算 246/9/7/1 | 手维护基线 |
| `test_generated_projection_is_current_and_self_digest_bound` (:62) | `on_disk == registry` 仍不等（630 处叶子差异） | 派生快照 |

tasks.md 侧是**已入库的合法变更**（`ebc6e1b92` 把若干任务由 `~` 标成 `x`），且现查
`git status -- "*tasks.md"` **无脏文件**。tasks.md 禁改，所以「改 tasks.md 迁就基线」不在选项内。

那么「重生成快照」呢？——**也不行，它同样不是纯重新同步。** 630 处差异里有两处是语义的：

```
.manifest_facts.source_current   : True  -> False        ← 下游于 §2.5 的 overlay 门禁
.manifest_facts.source_reason    : None  -> <str>
.manifest_facts.entry_count      : 185   -> 176          ← 同 §2.1 的 D4 退网
.milestones[5]…stale_reasons     : LEN 12 -> 13
fresh milestone_state_counts = {BLOCKED: 4, IMPLEMENTED: 3, REQUEST_PATH_VERIFIED: 0,
                                ONLYOFFICE_VERIFIED: 0, CLOSED: 0, STALE: 9}
```

`test_g0_3_does_not_promote_tasks_milestones_or_g0_4` 里有 `assert counts["BLOCKED"] <= 3`
（报错文案：「BLOCKED 由 3 升到 N」）。现算 **BLOCKED = 4**。
⇒ **有一个里程碑新近退化成 BLOCKED**。该测试的注释逐字写明：作者已刻意把终态桶改成
**方向感知**，正是为了「一次合法降级不该逼人去改基线，因为改基线会把『推进』那一侧一起放开」。
把字面量 bump 到 246/9/7/1、把 448 改成 447、把 `~` 改成 `x`，等于**顺手吸收掉一个 BLOCKED 回归**，
与该守卫的设计意图直接冲突；重生成快照则会把 `source_current: False`（未裁决的上游 stale 态）
写进已入库的治理产物。两条都属「绝不悄悄放开门禁」的红线，故**本轮不做**。

**人需要裁决什么**：①`ebc6e1b92` 把 1/2/20/60/62/64 由 `~` 升 `x` 是否已有证据支撑（这是
`completed 240→246`、`partial 15→9` 的全部来源）；②少了 1 条 internal 依赖边（448→447）是
谁删的、是否预期；③**BLOCKED 3→4 是哪个里程碑、为何退化**——这条最要紧，建议先答它。
三问定案后，快照重生成与测试基线上调应**在同一个 commit 里一次做完**，并在测试里写明新基线的依据。

---

## Part 2 小结

| 分类 | 条数 | 文件 |
|------|-----:|------|
| (a) 安全重新同步 | **0** | —（原以为 task66/milestones 属此，实测均含语义变更，已改判 b） |
| (b) 人工评审门禁 | **36** | task66(14) · task67(6) · task73(8) · milestones(5) · task68(3) |
| (c) 真实代码缺陷 | **1** | task30 ✅ 已修（CRLF 归一化，10/10 绿） |
| (d) 禁改文件 | **0** | —（task30 原被误归此类，实测章节存在，见 §2.4） |

**未做且刻意不做**：未 bump 任何 digest / 未改 overlay / 未重跑 task66·task67·manifest·milestones
生成器 / 未改 tasks.md / 未加任何 skip·xfail / 未放宽任何断言。
**解锁总顺序**：`§2.5 overlay 裁决（含删 d4 parent_rule）` → 重生成 manifest →
`§2.1 task66 裁决（BP-66-2 + rollback 门）` → task67 报告 → task68 →
`§2.6 milestones 基线（先答 BLOCKED 3→4）`。
