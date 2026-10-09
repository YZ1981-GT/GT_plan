# Task 0 证据：前置依赖核查

spec `g-cycle-single-region-detail-lanes` · Task 0 · _Requirements: 2.3, 4.1, 4.3_
实测时间 2026-09-27 · 判定基准 `git show HEAD:`（HEAD = `b69481836`）**并**逐项标注工作树增量

---

## 0. 判定方式说明（为什么不能只看 HEAD）

tasks.md Task 0 要求「`git show HEAD:` 判定」。实测发现 **foundation spec 的产物全部在工作树未提交**
（`.kiro/specs/g-cycle-sync-foundation-and-first-canary/` 整目录 untracked、`phase5_g2_*.py` untracked、
`g1SheetLabels.ts` 为 `M`）。只读 HEAD 会把两条已交付的硬前置误判为「未交付」并错误阻塞 Task 14。

⇒ 本证据**两列并列**：`HEAD` 列是提交态事实，`工作树` 列是未提交增量。任何依赖工作树增量的判定，
在本文件里显式标注 **「依赖未提交增量」**，commit 前不得据此宣称收口。

---

## 1. 框架层能力（四项）

| 前置项 | HEAD | 工作树 | 位置 | 结论 |
|---|---|---|---|---|
| `RowTableSheetSpec` | ✅ | ✅ | `phase5_row_table_sheet.py:101` | 交付 |
| `header_row: int \| None = None` **字段** | ✅ | ✅ | 同上 `:114` | 字段层支持 None |
| **「无表头」语义** | 🔴 **缺** | 🔴 **缺** | 同上 `:280` / `:289` | 见 §1.1 |
| `StoreMergePlan.oo_crash_neutralization_fn` | ✅ | ✅ | `store_item_registry.py:164` | 交付 |
| 框架层解析器（零 adapter_id 字面量分支） | ✅ | ✅ | `adapters/excel.py:94` `_resolve_oo_crash_neutralization_fn` | 交付 |
| 兄弟 Table ref 位移 | ✅ | ✅ | `phase5_row_table_sheet.py:494` `attach_sibling_bindings` | 交付（G1/G9/G3 多区可用） |

### 1.1 🔴 `header_row=None` 是「字段支持 + 语义静默回落」，比裁决 G1R-H2 假设的情形更危险

裁决 G1R-H2 的措辞是「引擎须支持 `header_row=None` 或等价语义；**若引擎不支持** ⇒ 登记框架层缺口 +
G12 暂不受管」。实测结论要修正这个二分：**字段接受 `None`，但契约投影层会静默回落，不报错。**

`spec_to_contract_sheet_payload` 逐字（`phase5_row_table_sheet.py`）：

```python
# L280
"header_source_ref": f"源xlsx!{spec.managed_sheet}!{col}{spec.header_row or spec.header_leaf_row or spec.first_data_row - 1}",
# L285-287
header_row_count = 1
if spec.header_group_row is not None and spec.header_leaf_row is not None:
    header_row_count = spec.header_leaf_row - spec.header_group_row + 1
# L289
anchor_row = spec.header_row or spec.header_group_row or (spec.first_data_row - 1)
```

代入 G12（`first_data_row=9`、三个 header 字段全 `None`）：

| 投影字段 | 实际产出 | 应有语义 | 后果 |
|---|---|---|---|
| `header_source_ref` | `源xlsx!明细表G12-2!{col}8` | 无表头 ⇒ 不应有该 ref | 指向 R8（标题/索引区），非表头格 |
| `header_rows` | `1` | `0` | OO 侧把 R8 锁成表头行 |
| `anchor` | `A8` | `A9`（数据首行）或等价锚定 | 受管区锚点偏移一行 |

⇒ **等价于裁决 G1R-H2 明确否决的方案②，且无任何报错**。三个 `or` 链把 `None` 当 falsy 吞掉，
`header_rows` 的分支只认「两级表头」，没有「零表头」分支。

**裁决 G1R-H2 的分支判定据此改写为**：
- 不是「引擎不支持 ⇒ 暂不受管」，而是「引擎会**静默做错** ⇒ 必须先加显式语义，否则不得声明」。
- Task 13 的处置二选一（届时决策，本 Task 不预判）：
  - **①框架层加显式字段**（如 `has_header_row: bool = True`），`False` 时 `header_rows=0`、
    `anchor` 取数据首行、`header_source_ref` 省略。改动面：`phase5_row_table_sheet.py` 单文件 + 契约投影判据。
    🔴 该文件当前是并发会话的 `M` 状态（见 §4），改前须重新核。
  - **②G12 暂不受管** + 登记框架层缺口。
- 🔴 无论走哪条，**都不得**让 G12 用默认值声明（默认值不会报错，会静默产出 R8 表头）。
  Task 13 SHALL 有一条判据钉住「G12 的 contract 投影里 `header_rows != 1` 或 `anchor != A8`」。

### 1.2 与 `g4-g6` spec 的 G6-5 同源性（Req 2.3 要求）

`g4-g6-shared-workbook-three-entry-lanes` 对 G6-5 的处置逐字：
- `design.md:30` 「G6-sppi（G6-5 无表头行 + 行级 mask，依赖 BP-7 已修）」
- `design.md:85` 表格「G6-sppi (G6-5) | 3 列 | **无表头行** | 合计 | 🔴 有 | 无 | 两处特殊」
- `tasks.md:117-120` 「`phase5_g6_05_sppi_fair_value.py`（无表头行 + 行级 mask）… **无独立表头行**（R9 即数据）/ R9-18」

⇒ 两份 spec 的**形态认定同源**（都是 R9 即数据、都不伪造表头）。但 `g4-g6` **同样未实施**
（无 evidence 目录、无 `phase5_g6_*` 产物）⇒ 🔴 **G12 是首个落地该形态的 entry**，
§1.1 的框架层处置由本 spec 先做，`g4-g6` 的 G6-5 后续复用。两边不得各做一套。

---

## 2. foundation spec 的两条硬前置

### 2.1 BP-5 修（G1 sheet 标签 5 条错名）—— ✅ 已交付，**依赖未提交增量**

`audit-platform/frontend/src/components/workpaper/composables/g1SheetLabels.ts`
HEAD **未修**，工作树已修（`git diff` 实证，五条逐字）：

| 编码 | HEAD（错） | 工作树（模板真名） |
|---|---|---|
| `G1A` | `交易性金融资产实质性程序表G1A` | `交易性金融资产实质性程序表G1A `（🔴 **尾部一个空格**，源模板事实，不得 trim） |
| `G1-8` | `业务模式评估问卷G1-8` | `业务模式分析G1-8` |
| `G1-10` | `合同现金流量特征测试表G1-10` | `合同现金流量特征分析G1-10` |
| `G1-12` | `盘点倒轧表G1-12` | `有价证券盘点倒轧表G1-12` |
| `附注国企` | `附注披露信息（国有企业）` | `附注披露信息（国企）` |

本 spec 关心的 `G1-2` / `G1-6` 两条 **HEAD 上本就正确**（`明细表G1-2` / `公允价值测试表G1-6`）⇒
Task 14 的 G1 声明（`managed_sheet="明细表G1-2"`、区①T 列跨表引 `公允价值测试表G1-6`）
**不受 BP-5 影响**；BP-5 影响的是宿主 sheet 分发映射的另外五条。

⇒ 结论：**Task 14 的 G1 不被 BP-5 阻塞**。但 `source_ref` 可信性依赖该未提交修改，
commit 前不得宣称 G1 收口（对应 tasks.md `blocking.14`）。

### 2.2 GC-9 三家 TB 裁决 —— ✅ 已交付，且 🔴 **反驳本 spec 的红基线 B5**

`.kiro/specs/g-cycke-sync-foundation-and-first-canary/evidence/task8-tb-gate-adjudication.md`
（实际路径 `g-cycle-sync-foundation-and-first-canary`）裁决结论逐字：

> 🔴 裁决结论：缺口是**两家**，不是三家 —— spec RG-6 误判了 G1
> …TB 显式发布门在 G 循环实际分布在四层，G1 的门在**组件层**。
> | **G1** | ✅ **已接，不是缺口** |
> ⇒ **裁决：注释/死代码记录，非活路径。G1 不进硬门，可以受管。**

四层按值分布（foundation 实测）：

| 层 | 文件 | `publishToTb` 命中 | 性质 |
|---|---|---|---|
| composable | `useG1Adjudication.ts` | ×1（L487 JSDoc） | 注释 |
| FormData | `useG1TraFinFormData.ts:107-108` | ×2 | 注释 |
| **组件** | `G1TabAdjudication.vue` | ×4 | 🔴 **活代码**：L251 `@click` · L356 `async function handlePublishToTb()` · L376 端点 · L360 中文二次确认 |
| 宿主 | `GtG1TradingFinancialAssets.vue:475` | ×1 | 注释 |

### 🔴 本 spec 需登记的偏差（不回填改 requirements.md 正文，按「历史档案不回填」铁律登记在此）

| 位置 | spec 原文 | 实测/裁决事实 |
|---|---|---|
| `requirements.md` 九条实测表尾注 | 「TB 发布门**已接 8 条**（G1 未接，见红基线 B5）」 | **九条全已接**；G1 的门在组件层 `G1TabAdjudication.vue`（活代码 + 中文二次确认） |
| `requirements.md` 红基线 **B5** 标题 | 「G1 未接 TB 显式发布门（= foundation RG-6 的三家之一）」 | 🔴 **不成立**。B5 的证据只查了 composable 层（`useG1Adjudication.ts` 673 行 `publishToTb=0`），漏了组件层 —— 与 H 循环「slice 冻结快照不可照抄」同型的**单层取证偏差** |
| `requirements.md` Req 4.1 | 「WHEN G1 受管 THEN SHALL 先有 foundation GC-9 裁决结论；本 spec 不独立裁决」 | ✅ **已满足**，结论 = 「G1 不进硬门，可以受管」 |
| `design.md` 裁决 G1R-H1 表格「TB 门」行 | G1 = 「🔴 未接（GC-9 缺口）」 | 应读作「已接（门在组件层）」；G1 仍排最后，理由降为「BP-5/7/9 三条 + 区①跨表 T 列行级 mask」两项 |

⇒ **Task 14 的 G1 阻塞项由两项（BP-5 + GC-9）降为零项**，但 §2.1 的未提交依赖仍在。
P13（TB 红线）的断言措辞随之修正：**九条**均以 `publishToTb` 为唯一入口（不是「八条」），
G1 的入口在组件层而非 composable 层 —— 若判据只扫 composable 会把 G1 误判成「无门」。

### 2.3 顺带发现（登记，不在本 spec 处理）

foundation Task 8 §五同时登记了 **G1 科目错码**：`useG1Adjustment.G1_ACCOUNT_CODE` 与
`useG1Disclosure.G1_ACCOUNT_CODE` 为 `'1501'`（旧准则持有至到期投资），真码 `1101`；
`G1TabAdjudication.vue:360` 的二次确认**文案**也写「科目 1501」⇒ 🔴 **已到用户可见层**。
归属 foundation（已登记）；本 spec Task 14 做 G1 时**不得**沿用 `1501` 作为任何声明的科目依据。

---

## 3. foundation spec 实际交付进度（tasks.md 勾选状态不可信）

foundation `tasks.md` 的 19 条全为 `- [ ]` **未勾选**，但产物与 evidence 已到 Task 14。
⇒ 勾选状态与事实不一致，判定**以产物为准**：

| foundation Task | evidence | 产物 | 判定 |
|---|---|---|---|
| 0 / 1 | `task0-prerequisites.md` · `task1-slice-review-and-adjudication.md` | — | ✅ |
| 2 / 3 / 4 | `task2-task4-red-baselines.md` | `test_g_foundation_p1_p3_*` / `p4_p8_p17_p18_*` / `p5_gc1_*` / `p20_golden_digest_*` 四个测试文件 | ✅ |
| 5 / 6 / 7 | `task5-task7-fixes.md` | `g1SheetLabels.ts`(BP-5) · `fix_g_cycle_prefill_presets.py` · `fix_g_slice_bp5_status_and_registry_alias.py` | ✅ |
| 8 | `task8-tb-gate-adjudication.md` | 判据 `test_gate_presence_by_layer` | ✅（含 §2.2 裁决） |
| 9 / 10 | `task9-task10-registrations-and-pointer.md` | — | ✅ |
| 11 / 12 | — | `phase5_g2_interest_receivable.py` · `phase5_g2_02_detail.py` | ✅ 产物在 |
| 13 | — | `g2StorageContract.ts` · `g2CrossHelpers.ts`(M) | ✅ 产物在 |
| 14 | — | `workpaper_sync_contracts/g2.interest_receivable_detail.json` · `generate_phase5_g2_contract.py` · `registry.py:1508` 注释「G2 canary … Task 14」 | ✅ 产物在 |
| 15 ~ 18 | — | 未见宿主接桥/真栈验收/收口产物 | ⏳ 未完成或进行中 |

**对本 spec 的影响**：本 spec 依赖的是 foundation 的 **Task 5（BP-5）与 Task 8（GC-9）**，两者均已交付
⇒ 本 spec 阶段 0~2 全部可开工。foundation Task 15~18 未完成**不阻塞**本 spec 的声明层与判据层；
只在 Task 15（本 spec 发布链五环）时需要 foundation 的宿主接桥范式作参照。

---

## 4. 🔴 并发会话冲突面（本 Task 新增登记，spec 未预见）

`git status` 实测：工作树有 **90+ 个 `M` 文件 + 大量 untracked**，覆盖 D3/D5/D6/D7/E1/F3/F4/F5/G2
多个 spec 的在途实施。本 spec 需要写入的共享文件中，以下**当前已是 `M` 状态**：

| 共享文件 | 本 spec 用途 | 冲突风险 |
|---|---|---|
| `backend/app/services/workpaper_sync/store_item_registry.py` | 加 9 个 `StoreMergePlan` | 🔴 高（G2 plan 刚加在文件尾部同一区间） |
| `backend/app/services/workpaper_sync/adapters/registry.py` | 注册 9 条 contract | 🔴 高（G2 条目刚加在 `:1508`） |
| `backend/app/services/workpaper_sync/phase5_row_table_sheet.py` | §1.1 的 `has_header_row` 扩展（若走方案①） | 🔴 高（引擎核心，多 spec 共改） |
| `backend/data/workpaper_sync_entry_manifest.json` / `_overlay.json` | 九条 capability 翻转 | 🔴 高 |
| `backend/scripts/check/_sync_provider_golden_digest.json` | 零回归基线现算 | 🔴 高（digest 目录数并发变动，GC-10 已要求现算不写死） |

**本 spec 的协作纪律**（写入本证据，后续 Task 逐条遵守）：
1. 新建文件（`phase5_g{N}_*.py` / 契约 JSON / 测试 / seed 脚本）**零冲突**，优先推进。
2. 上述五个共享文件**只做追加式最小编辑**，每次编辑前重新读该文件当前内容（不依赖本 Task 的快照）。
3. 🔴 **不碰** D3/D2/D5/D6/D7/E1/F3/F4/F5 的任何文件（并发会话在途）。
4. 零回归基线一律**现算**（GC-10），不写死 digest 数量 —— 并发会话正在增加契约目录条目。

---

## 5. 九条 entry 的 adapter / plan 现状（基线确认）

实测 `STORE_MERGE_REGISTRY`（`store_item_registry.py`）G 循环仅两条：

| adapter_id | 范式 | provider_module | 归属 |
|---|---|---|---|
| `g7.soe_subsidiary_disclosure` | 🔴 `pilot_*`（形态早于行表引擎） | `pilot_g7_two_level_dynamic` | 既有先例，**不复用其范式**（GF-H3） |
| `g2.interest_receivable_detail` | `phase5_*` | `phase5_g2_interest_receivable` | foundation canary |

本 spec 九条（G1/G3/G8/G9/G10/G11/G12/G13/G14）**全部未注册、无 plan、无 provider** ⇒ 与 requirements
「九条全 `capability=null` / `legacy_fake_bidirectional` / `adapter_id=None`」一致，基线确认。
新建九条一律 `phase5_*` 范式（照 `phase5_g2_interest_receivable` 而非 `pilot_g7_*`），
唯一复用 G7 的是 `oo_crash_neutralization_fn="neutralize_oo_crash_if_formulas"`（GC-2，per-file 缓解件）。

---

## 6. Task 0 结论

| # | 判定 | 后续动作 |
|---|---|---|
| 1 | 框架层四项能力已交付（`RowTableSheetSpec` / `oo_crash_neutralization_fn` + 解析器 / 兄弟 Table ref 位移） | 阶段 2 可直接声明 |
| 2 | 🔴 **「无表头」语义是静默回落缺口**，不是「不支持」 | Task 13 二选一，判据钉住 `header_rows != 1` |
| 3 | foundation BP-5 已修（**未提交**），且 G1-2/G1-6 两条 HEAD 本就正确 | Task 14 不被 BP-5 阻塞 |
| 4 | foundation GC-9 已裁决，🔴 **G1 已接 TB 门（组件层）** | **B5 不成立**；Task 14 阻塞项清零；P13 断言改「九条」 |
| 5 | foundation 实际到 Task 14（勾选状态不可信） | 本 spec 阶段 0~2 可开工 |
| 6 | 🔴 五个共享文件处于并发 `M` 状态 | 按 §4 四条纪律推进 |
| 7 | 九条 adapter/plan 全未注册 | 基线确认，`phase5_*` 范式 |
| 8 | `g4-g6` 的 G6-5 同源但未实施 | G12 是首个落地「无表头行」，框架层处置本 spec 先做 |

🔴 **未解除的阻塞**：无（Task 0 的四个 `blocking` 条件中，`header_row` 转为「需先加语义」、
BP-5 与 GC-9 均已交付）。tasks.md `blocking.0` 与 `blocking.14` 据本证据失效，
`blocking.13` 改为「必须先加显式无表头语义，否则 G12 不得声明」。
