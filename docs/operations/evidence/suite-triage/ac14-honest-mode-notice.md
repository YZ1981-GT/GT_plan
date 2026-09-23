# Cluster C4 — AC14「诚实模式」提示组件（GtEntrySyncCapabilityNotice）

一个缺陷，多个见证人。结论先说：**没有任何面向审计师的披露真的缺失** —— 7 个 D 循环宿主
全部挂了通知、全部传了正确 entry-id、全部挂在模式工具栏内。6 个红都是**检测器按旧形态解析
真源**或**登记计数陈旧**。

## 0. 目标节点与文件数修正

任务单写「6 failures across 5 files」，实测是 **6 failures across 4 files**（task46 出 3 个）：

| # | 文件 | 节点 | 结果 |
|---|------|------|------|
| 1 | test_task46_d_cycle_migration.py | TestAc14HonestModeVisibility::test_every_pending_entry_host_mounts_the_notice | ✅ 绿 |
| 2 | test_task46_d_cycle_migration.py | TestAc14HonestModeVisibility::test_notice_mount_sits_inside_the_mode_toolbar | ✅ 绿 |
| 3 | test_task46_d_cycle_migration.py | TestAc14HonestModeVisibility::test_hosts_do_not_claim_bidirectional_writeback | ✅ 绿 |
| 4 | test_task52_j_cycle_migration.py | TestProperty3And20::test_ac14_notice_single_source_exists_and_is_not_duplicated | ✅ 绿 |
| 5 | test_task56_n_cycle_migration.py | TestAdjudicationLegality::test_ac14_notice_single_source_exists_and_is_consumed | ✅ 绿 |
| 6 | test_task57_abcs_and_shared_migration.py | TestAdjudicationLegality::test_ac14_notice_single_source_exists_and_is_consumed_out_of_scope | ✅ 绿 |

### 第 7 个见证人（任务单未列，读同一事实）

`test_task46::TestAc14HonestModeVisibility::test_registered_entry_ids_agree_with_the_slice`
原报 `找不到 SYNC_ADAPTER_REGISTERED_ENTRY_IDS 的声明`（与节点 5 逐字同一条消息）。它读的是
同一个共享事实，不修它等于留一个「找不到自己要查的东西」的检测器。修完解析后它**仍红**，
但消息变成真话：

```
xlsx/gt-d2-accounts-receivable 在 slice 里没有 adapter，却被前端登记为已注册
```

这是 **manifest ↔ D-slice 漂移**，属另一簇（见 §8 移交）。修改前后都红，不算新增失败。

### 同文件属其它簇的失败（记录以免重复计数）

- test_task46：`test_no_d_entry_has_a_registered_adapter_and_pilot_evidence_exists`、
  `test_entries_without_contract_have_no_contract_file`、
  `test_authoritative_templates_digests_recompute`、
  `test_every_entry_template_ref_is_registered_with_digest`、
  `test_slice_scope_is_recomputable_from_the_manifest`、
  `test_parent_duplicates_not_counted_as_independent`、
  `test_source_backed_profile_fields_match_the_manifest`、
  `test_manifest_capability_divergence_is_registered`
- test_task52：`TestOrphanDualModeInventory::test_pseudo_string_edges_exist_but_are_not_import_edges`
- test_task57：`TestSliceScopeIsRecomputable::test_parent_duplicate_section_is_absent_because_in_scope_count_is_zero`
- test_task46：`TestSourceCodeStructure::test_hosts_exist_and_import_legacy_composable`
  —— 复现时红，复跑时绿。**并行 agent 在我工作期间重写了该判据**（D2 是 pilot，legacy
  composable 已随 commit `42d2f6e6f` 删除）。非本簇、非我改动。

## 1. 复现（verbatim，修改前）

```
# test_task46（-k Ac14）
tests\workpaper_sync\test_task46_d_cycle_migration.py:1106: in test_every_pending_entry_host_mounts_the_notice
E   AssertionError: GtD4OperatingRevenue.vue 挂了组件但没传 entry-id
tests\workpaper_sync\test_task46_d_cycle_migration.py:1122: in test_notice_mount_sits_inside_the_mode_toolbar
E   AssertionError: GtD4OperatingRevenue.vue 找不到 showModeToolbar 工具栏区块
tests\workpaper_sync\test_task46_d_cycle_migration.py:1134: in test_registered_entry_ids_agree_with_the_slice
E   AssertionError: 找不到 SYNC_ADAPTER_REGISTERED_ENTRY_IDS 的声明
tests\workpaper_sync\test_task46_d_cycle_migration.py:1155: in test_hosts_do_not_claim_bidirectional_writeback
E   AssertionError: GtD2AccountsReceivable.vue 出现 '已同步' —— 未注册 adapter 的入口不得宣称双向/同步成功
4 failed, 2 passed, 66 deselected
```

```
# test_task52
tests\workpaper_sync\test_task52_j_cycle_migration.py:2288: in test_ac14_notice_single_source_exists_and_is_not_duplicated
E   AssertionError: 读不出已注册 entry 集合
2 failed, 130 passed
```

```
# test_task56
tests\workpaper_sync\test_task56_n_cycle_migration.py:913: in test_ac14_notice_single_source_exists_and_is_consumed
E   AssertionError: 找不到 SYNC_ADAPTER_REGISTERED_ENTRY_IDS 的声明
1 failed, 122 passed
```

```
# test_task57
tests\workpaper_sync\test_task57_abcs_and_shared_migration.py:1170: in test_ac14_notice_single_source_exists_and_is_consumed_out_of_scope
E   AssertionError: 声明 42 现算 46
E   assert 42 == 46
2 failed, 128 passed
```

## 2. 每个断言读取的共享事实

| 事实 | 内容 | 读它的节点 |
|------|------|-----------|
| **F1** | `workpaperEntrySyncNotice.ts` 里 `SYNC_ADAPTER_REGISTERED_ENTRY_IDS` 的**声明形态**，以及它解析出的 entry_id 集合 | 4、5、第 7 见证人 |
| **F2** | 7 个 D 宿主的通知**挂载形态**：`<GtEntrySyncCapabilityNotice entry-id="…">` 的属性布局 + 它是否在 `showModeToolbar` 工具栏内 | 1、2 |
| **F3** | 宿主模板里是否出现成功态文案 | 3 |
| **F4** | 通知 `.vue` 的**生产消费边条数**，与 slice 登记值是否相等 | 6（及 5 的 `production_consumers`） |

## 3. 六个检测器是否互相一致？—— 对 F1 一致，对 F2/F3 有偏差

**F1：三个检测器完全一致**（它们都要求值是「引号 id 的字面量数组」），因此真源形态一变，
三个一起红。它们的**下游断言也一致**（集合非空 + 每项含 `/`），所以不存在互相矛盾。

**F2：两个检测器把「属性布局」当成了判据的一部分** ——

```python
# 节点 1（旧）：entry-id 必须紧邻组件名
re.compile(r"<GtEntrySyncCapabilityNotice\s+entry-id=\"([^\"]+)\"\s*/?>")
# 节点 2（旧）：v-if 必须**恰好**等于 showModeToolbar，且工具栏块用非贪婪 </div> 截断
re.search(r'<div v-if="showModeToolbar"[\s\S]*?</div>', template)
```

这不是「披露缺失」判据，而是「代码长相」判据 —— 它把「多了一个合法属性」误报成
「没传 entry-id」，把「复合条件」误报成「找不到工具栏」。

**F3：检测器的 docstring/消息与循环体自相矛盾** —— 消息写「**未注册 adapter 的**入口不得
宣称」，循环体却对全部 7 条 entry 一律扫词，无 `adapter_id is None` 过滤；且扫描范围是**整个
文件**（含 `<script>`），把标识符与运行时状态标签一并当作对用户的宣称。

## 4. 根因

**AC 1.4 的「已注册 adapter」真源在 2026-09-22 从手写数组改成了 manifest 现算，检测器还按
字面量数组解析；另有两条判据把宿主的合法属性布局当成判据。** 真源现状：

```ts
export const SYNC_ADAPTER_REGISTERED_ENTRY_IDS: readonly string[] =
  Object.freeze(
    WORKPAPER_SYNC_MANIFEST.filter((e) => e.capability === 'bidirectional').map(
      (e) => e.entryId,
    ),
  )
```

这个改动本身是**对的**，而且修的正是一个真实的失真披露：手写数组是第二真源，D4/G7/H1
接通双向后没人补行，于是**真双向底稿上继续显示「两侧数据未互通」**（用户在 D4-2 实测撞到）。
把真能力说成假的，同样违反 AC 1.4。

三个检测器的正则 `=\s*\[` / `=\s*(\[[^\]]*\])` 因此匹配不到，报的却是
「找不到 SYNC_ADAPTER_REGISTERED_ENTRY_IDS 的声明」—— **把「形态变了」误报成「东西没了」**，
恰恰是这条判据最该区分的两件事。

### 关键实证：这 6 个红全部先于本工作树存在

| 文件 | `git status` |
|------|-------------|
| 4 个测试文件 | 干净（== HEAD） |
| `workpaperEntrySyncNotice.ts` / `GtEntrySyncCapabilityNotice.vue` | 干净（== HEAD） |
| 两个 slice JSON | 干净（== HEAD） |
| `workpaperSyncManifest.generated.ts` | **M**（并行 agent 在改） |

46 个消费方文件**在 HEAD 时就已全部 import 通知组件**（逐文件 `git show HEAD:` 核对，
delta = 0），两个 slice 的登记值**在 HEAD 时就是 42**。所以 `42 vs 46` 不是并行 agent 新引入的。

## 5. 逐节点修复

| 节点 | 归类 | 修了什么 |
|------|------|---------|
| 1 | (b) 真源形态 | 挂载正则改为「先整体取标签、再在属性串里找 `entry-id`」。属性顺序自由，但 **entry-id 必须存在且等于该 entry 自己的 id** 一条不放宽。D4 的 `v-if="!isD4DedicatedSyncSheet"` 是**正确**的（dedicated sheet 由子页签自管工具栏）。 |
| 2 | (b) 真源形态 | 新增 `_mode_toolbar_block()`：`v-if` 容复合条件（`showModeToolbar && !isD4DedicatedSyncSheet`），且 `<div>` **真配平**（原非贪婪 `</div>` 会在第一个内层 div 截断）。 |
| 3 | (b) 判据自相矛盾 | 禁词分两类：**能力宣称**（「可双向回写」「双向同步」）模板内任何位置禁止；**运行时结果**（「同步成功」「已同步」）只在被**同步态** `v-if/v-else-if` 门控时合法。判据范围收进 `<template>`。新增 `_ancestor_open_tags()` 用 tag 栈真解析祖先链（D2 的门控挂在**父** `<el-tooltip v-else-if="syncFeedbackOk">` 上，只看自身开标签会误判）。并补 `checked == 7` 分母断言。 |
| 4、5、第 7 | (b) 真源形态 | 新增 `_initializer_of()`（括号配平取完整初始化表达式）+ `_registered_entry_ids()`（**双形态解析**：字面量数组 ⇒ 取引号 id；manifest 现算 ⇒ 按同一 filter 谓词在 generated manifest 上**复算**）。两条路径都产出**具体 id 列表**，下游「非空 / 形如 entry_id / 与 slice 互锁 / 有消费方」逐条判据全部保留。声明整体缺失 ⇒ 断言失败（fail-closed）。 |
| 5 的死常量检测 | 顺手修的真缺陷 | `body_after = ts[m.end():]` 改为从**初始化表达式结束处**切。常量名首次出现在模块 docstring 的 `{@link …}` 里，从那儿切会把声明自己算成消费方 ⇒ 死常量检测恒真。 |
| 6（及 5 的计数） | (c) 登记陈旧 | 两个 slice 的 `42` → `46`，并补 breakdown 字段说明构成。 |

### 判据没有被弱化的三点保证

1. 「single source」仍是「**唯一一份实现**」—— 未改成「存在于某处即可」；`_registered_entry_ids()`
   缺声明就抛断言，删掉通知照样红（§6 变异 3 实测）。
2. 挂载判据仍要求 entry-id 存在且**值正确**；工具栏判据仍要求通知**在**工具栏块内（§6 变异 1/2）。
3. 禁词判据从「整文件裸子串」升级为「模板内 + 区分宣称语义 + 祖先链门控」，裸挂成功态标签
   照样红（§6 变异 5）。

## 6. 变异验证（kill-test）

每次变异后**按字节还原**（只从字节备份写回，不做反向 replace —— 删除型变异的反向锚点是空串，
反向 replace 会静默不还原，且 `read_text/write_text` 往返会把 CRLF 抹成 LF）。每次还原后用
`git diff --stat` 确认空。

| # | 变异 | 预期被杀 | 实测 |
|---|------|---------|------|
| 1 | 删 `GtD4OperatingRevenue.vue` 的通知挂载行 | 节点 1、2 | ✅ 双红：`GtD4OperatingRevenue.vue 的模板里没有挂 <GtEntrySyncCapabilityNotice> ⇒ 结构性死代码` / `…的通知没挂在模式工具栏里` |
| 2 | 把 `GtD1NotesReceivable.vue` 的通知**挪到工具栏外**（仍挂着、仍传 entry-id） | 仅节点 2 | ✅ 精确单杀：节点 2 红 `GtD1NotesReceivable.vue 的通知没挂在模式工具栏里`，节点 1 **保持绿** ⇒ 工具栏位置判据与「是否挂了」判据互相独立，不是重复判据 |
| 3 | 把 `SYNC_ADAPTER_REGISTERED_ENTRY_IDS` 声明改名（等价于删除） | 节点 4、5、第 7 见证人 | ✅ 三红并且 fail-closed：task46 `找不到…声明` / task52 `读不出已注册 entry 集合` / task56 `找不到…声明` |
| 4 | 删 `GtD2AccountsReceivable.vue` 的 **import** 行（消费边 46→45） | 节点 6 及 task56 计数 | ✅ 双红：task56 `AssertionError: (46, 45)` / task57 `声明 46 现算 45` |
| 5 | 去掉 D2「已同步」标签的 `v-else-if="syncFeedbackOk"` 门控（变成裸挂常驻宣称） | 节点 3 | ✅ 红，且消息带完整祖先链：`GtD2AccountsReceivable.vue 的 '已同步' 没有任何同步态 v-if/v-else-if 门控 ⇒ 它是常驻成功态宣称，不是逐操作结果；祖先链=[…]` |

还原后核对：7 个 D 宿主 + `workpaperEntrySyncNotice.ts` + `GtEntrySyncCapabilityNotice.vue`
的 `git status --porcelain` **全部无输出**（字节级一致，D4 的 SHA256 与变异前逐字符相同：
`318ACD9A2F0D5620CC2253EF489EB7DD92325C4366886976D1F37C03759545CB`）。

## 7. 42 vs 46 的裁定 —— 判 46，理由如下

**结论：登记值 42 陈旧，改 46。那 4 个消费方不是错加的，而是 4 个 sheet 唯一的 AC 1.4 披露点。**

46 条 statement-position 生产边的构成：

- **41** 个循环入口宿主（D1~D7 / F1~F5 / G1~G14 / H2~H10）
- **4** 个 D4 子页签自管工具栏：`D4TabCustomerStructure` / `D4TabMarginMonthly` /
  `D4TabOtherContract` / `D4TabOtherCutoff`
- **1** 条 `components.d.ts` 全局组件类型声明

判「46 合法」的三条实证：

1. **4 个子页签在 HEAD 时就已挂载**（`git show HEAD:` 逐文件确认），不是本轮新加的。
   「四个 consumer 被加错了」这个假设与事实不符。
2. **它们各自有独立的模式切换器**，例如 `D4TabOtherContract` 的工具栏里是
   `<el-segmented v-model="editorMode" :options="modeOptions">`。AC 1.4 的义务落在「切换器旁
   必须有可操作原因」，有几个切换器就得有几处披露。
3. **宿主工具栏对这些 sheet 根本不渲染** —— D4-9/D4-10/D4-34/D4-36 全在
   `isD4DedicatedSyncSheet` 名单里，而宿主工具栏的条件是
   `v-if="showModeToolbar && !isD4DedicatedSyncSheet"`。也就是说**删掉这 4 个挂载，这 4 个
   sheet 就变成有切换器却零披露** —— 那才是真缺陷。

另外，旧登记本身就自相矛盾：字段写 `42`，同一节点的 `why_non_vacuous` 散文写「41 个」，
现算是 `46` —— 三个数并存。已在新增的 breakdown 字段里点明。

「single source」不受影响：46 是**挂载点**数量，不是实现份数。通知只有一份实现
（`GtEntrySyncCapabilityNotice.vue` + `workpaperEntrySyncNotice.ts`），46 个消费方全部 import
同一份。判「不得抄第二份」的判据（task52/53/54/55）本来就绿，未被触碰。

**计数稳定性**：连续 3 轮复算（间隔 2s）两个检测器都稳定给 `prod=46, test=1`，
不是抖动中的输入，可以定案。

## 8. 面向审计师的披露：有没有真缺失？—— 没有

7 个 D 循环宿主逐一实测（挂载形态 + 工具栏区块 + 禁词分布）：

| 宿主 | 工具栏 | 挂载 | 传的 entry-id |
|------|--------|------|--------------|
| GtD1NotesReceivable.vue | `v-if="showModeToolbar"` | ✅ 工具栏内 | `xlsx/gt-d1-notes-receivable` ✓ |
| GtD2AccountsReceivable.vue | `v-if="showModeToolbar"` | ✅ 工具栏内 | `xlsx/gt-d2-accounts-receivable` ✓ |
| GtD3PrepaidAccounts.vue | `v-if="showModeToolbar"` | ✅ 工具栏内 | `xlsx/gt-d3-prepaid-accounts` ✓ |
| GtD4OperatingRevenue.vue | `v-if="showModeToolbar && !isD4DedicatedSyncSheet"` | ✅ 工具栏内 | `xlsx/gt-d4-operating-revenue` ✓ |
| GtD5ReceivablesFinancing.vue | `v-if="showModeToolbar"` | ✅ 工具栏内 | `xlsx/gt-d5-receivables-financing` ✓ |
| GtD6ContractAssets.vue | `v-if="showModeToolbar"` | ✅ 工具栏内 | `xlsx/gt-d6-contract-assets` ✓ |
| GtD7ContractLiabilities.vue | `v-if="showModeToolbar"` | ✅ 工具栏内 | `xlsx/gt-d7-contract-liabilities` ✓ |

D2 的「已同步」不是能力宣称：

```html
<el-tooltip v-else-if="syncFeedbackOk" :content="syncFeedbackOk" placement="bottom">
  <el-tag type="success" size="small">已同步</el-tag>
</el-tooltip>
```

它与 `同步中…`（`v-if="syncBusy"`）/ `在线编辑不可用`（`v-else-if="syncUnavailableReason"`）
三者并列，说的是「刚才那次操作的结果」，正是 AC 11.3 要求的**分状态文案**（不得统一成一句
成功态）。同一工具栏里 AC 1.4 的静态披露由通知组件独立承担。D4 的「双向同步」两处命中都在
`//` 注释里，`_strip_ts_comments` 已剥。

**一处反向失真已由真源改动修好**（不是本次改的，但要记下来）：D4/G7/H1 已是
`capability=bidirectional` + `adapter_registered`，改成 manifest 现算后
`entrySyncNotice()` 对它们返回 `null` ⇒ 真双向底稿上不再挂「两侧数据未互通」的假警告。

### 移交给「manifest ↔ slice 漂移」簇

`test_task46::test_registered_entry_ids_agree_with_the_slice` 现在报真话：

- **generated manifest**：`xlsx/gt-d2-accounts-receivable` 与 `xlsx/gt-d4-operating-revenue`
  均为 `capability=bidirectional` + `migrationState=adapter_registered`
- **`workpaper_sync_d_cycle_manifest_slice.json`**：7 条 D entry 的 `adapter_id` 全为 `null`

同簇兄弟：`test_no_d_entry_has_a_registered_adapter_and_pilot_evidence_exists`
（`assert 'd2.receivable_detail' is None`）、`test_source_backed_profile_fields_match_the_manifest`
（`legacy_sheet_onlyoffice_router` vs `workpaper_sync_published_representation`）、
`test_manifest_capability_divergence_is_registered`（`single_onlyoffice` vs `bidirectional`）。
**用户可见影响：无**（通知按 manifest 现算，呈现是对的）；问题在 slice 登记陈旧。
本簇不动它，只把误导性消息换成真消息。

## 9. 每文件前后计数

| 文件 | 修改前 | 修改后 | 变化 |
|------|--------|--------|------|
| test_task46_d_cycle_migration.py | 13 failed / 59 passed | **9 failed / 63 passed** | AC14 三个目标节点转绿；另 1 条（`test_hosts_exist_and_import_legacy_composable`）由**并行 agent**改绿，非本簇 |
| test_task52_j_cycle_migration.py | 2 failed / 130 passed | **1 failed / 131 passed** | 目标节点转绿 |
| test_task56_n_cycle_migration.py | 1 failed / 122 passed | **0 failed / 123 passed** | 全绿 |
| test_task57_abcs_and_shared_migration.py | 2 failed / 128 passed | **1 failed / 129 passed** | 目标节点转绿 |

无新增失败。前端 vitest：
`src/components/workpaper/sync/__tests__/workpaperEntrySyncNotice.spec.ts` → **11 passed / 1 file**。

## 10. 改动清单

- `backend/tests/workpaper_sync/test_task46_d_cycle_migration.py`
  新增 `SYNC_MANIFEST_TS`、`_initializer_of`、`_generated_manifest_entries`、
  `_registered_entry_ids`、`_mode_toolbar_block`、`_VOID_TAGS`、`_TAG_RX`、
  `_ancestor_open_tags`；改 4 条 AC14 判据。
- `backend/tests/workpaper_sync/test_task52_j_cycle_migration.py`
  新增 `SYNC_MANIFEST_TS`、`_initializer_of`、`_registered_entry_ids`；改 1 条判据。
- `backend/tests/workpaper_sync/test_task56_n_cycle_migration.py`
  新增 `SYNC_MANIFEST_TS`、`_initializer_of`、`_registered_entry_ids`；改 1 条判据
  （含死常量检测的切点修正）。
- `backend/data/workpaper_sync_n_cycle_manifest_slice.json`
  `production_consumers` 42→46，补 `production_consumers_breakdown`，修正 4 条
  `*_source_ref` 行号（L52/55/58/67 → L68/76/79/88，旧值指到注释行）。
- `backend/data/workpaper_sync_abcs_cycle_manifest_slice.json`
  `out_of_scope_consumer_count` 42→46，补 `out_of_scope_consumer_breakdown`。

**前端源码零改动** —— 所有 `.vue` / `.ts` 宿主与通知组件 `git status` 干净，变异全部字节还原。
