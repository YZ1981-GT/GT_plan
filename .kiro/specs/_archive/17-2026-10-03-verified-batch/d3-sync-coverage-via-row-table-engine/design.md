# Design Document

## Overview

D3 预收账款受管覆盖 **1 → 8 个受管区**（6 张 sheet），并对 `调整分录汇总表D3-3` 只做可行性核。
本 spec 是纯**声明层**：引擎、注册表、`AdjudicationSheetSpec`、四态状态机全部由上游
`d1-sync-row-table-engine-and-d1-coverage` 交付，裁决与分波由
`d-cycle-sheet-bidirectional-expansion` 提供，这里只写 spec 实例化与宿主接线。

设计的每个参数都来自实测（模板 openpyxl 直读 + 按值 grep + 真库查），不照 D1/D2 推演 ——
D3 有两处与它们都不同：**store 键用语义缩写**、**adapter 在真库尚未注册**。

## Architecture

### 单册 + 一 entry（与 D1 同，不同于 D2 的三册）

```
backend/wp_templates/D/D3 预收账款.xlsx   单册 12 sheets
entry: xlsx/gt-d3-prepaid-accounts        （已存在，绑这一册）
contract: d3.prepaid_receipts_detail      受管 sheet 现仅 预收账款明细表D3-2 / d32-managed
```

D2 那次因三册 + `entry ↔ template blob` 1:1 而被迫只扩第一册；D3 是单册，**不受该约束**，
12 张 sheet 理论上都可进同一 entry 的 `sheets[]`。

### 声明层结构

```
backend/app/services/workpaper_sync/
  phase5_d3_prepaid_receipts.py     循环层：ENTRY_ID / 模板路径 / sheet 清单 / 灰度开关
                                    （现 847 行，上游 spec 阶段 3 收敛后 ≤150 行）
  phase5_d3_02_detail.py            已接 D3-2 的声明（上游拆出）
  phase5_d3_06_related_party.py     ✅ RowTableSheetSpec  store: D3-rp-rows
  phase5_d3_04_analysis.py          ✅ 双区 RowTableSheetSpec  store: D3-ana-credit-rows / -debit-rows
  phase5_d3_05_long_term.py         ✅ RowTableSheetSpec  store: D3-lt-rows
  phase5_d3_07_voucher_check.py     ✅ 双区 RowTableSheetSpec  store: D3-vc-current-rows / -post-rows
  phase5_d3_01_adjudication.py      ✅ AdjudicationSheetSpec（区块数待实测）
```

### 受管区增长路线

```
1 (D3-2 已接)
  → 2   阶段1  D3-6 关联关系及交易    +1   D3-rp-rows
  → 4   阶段2  D3-4 分析表双区        +2   D3-ana-credit-rows / -debit-rows
  → 5   阶段2  D3-5 账龄1年以上       +1   D3-lt-rows
  → 7   阶段3  D3-7 检查表双区        +2   D3-vc-current-rows / -post-rows
  → 8   阶段4  D3-1 审定表            +1   （区块数待实测，若 >1 则终值更高）
  —     阶段5  D3-3 调整分录          可行性核，不计入
```

顺序理由：D3-6 单区最简作首张（证明多受管 sheet 在 D3 上成立，失败面最小）→ D3-4 双区把同
sheet 多区位移链在 D3 上验通 → D3-7 双区结构同型可快速复制 → D3-1 审定表最后（依赖两个外部
前置且逐格 mask 形态）。

## Components and Interfaces

### 声明形态（示意，几何由 Task 1 实测填）

```python
# phase5_d3_06_related_party.py —— 最简单区样本
SPEC_D306 = RowTableSheetSpec(
    managed_sheet="关联关系及交易检查表D3-6",
    sheet_key="d36-managed",
    table_key="related_party_rows",
    store_item_id="D3-rp-rows",          # 🔴 实测值，不是 D3-6-rows
    store_kind=StoreKind.rows,
    aging_layout=None,
    formula_columns=(...),               # Task 1 实测（模板 16 公式主列 F6 D3 A2，需判数据行列向 vs footer）
    # first/last_data_row / footer_row / uuid_col / table_name 由 Task 1 填
)

# phase5_d3_04_analysis.py —— 双区，同 managed_sheet 不同行段与 UUID 列（形如 D4-9 双区）
SPEC_D304_CREDIT = RowTableSheetSpec(
    managed_sheet="预收账款分析表D3-4", sheet_key="d34-managed-credit",
    table_key="analysis_credit_rows", store_item_id="D3-ana-credit-rows", ...)
SPEC_D304_DEBIT  = RowTableSheetSpec(
    managed_sheet="预收账款分析表D3-4", sheet_key="d34-managed-debit",
    table_key="analysis_debit_rows",  store_item_id="D3-ana-debit-rows",  ...)
```

### 🔴 `store_item_id` 必须逐个实测的理由

D3 的键**用语义缩写，与 sheet 编号无对应关系**：

```
D3-2 明细      → D3-det-rows          （不是 D3-2-rows）
D3-3 调整分录  → D3-aje-rows          （不是 D3-3-rows）
D3-4 分析表    → D3-ana-credit-rows / D3-ana-debit-rows
D3-5 账龄      → D3-lt-rows           （long-term 缩写）
D3-6 关联方    → D3-rp-rows           （related-party 缩写）
D3-7 检查表    → D3-vc-current-rows / D3-vc-post-rows
```

对照 D5/D6/D7 大多用编号（`D5-2-rows` / `D6-3-rows` / `D7-4-credit-rows`）。⇒ 本 spec 的声明
**禁止按 `D3-{n}-rows` 推演**。这条有三次事故背书：D2-3 三键 / D1-15 双键 / D1-13 双键的遗漏
全部源于「按模式推演」而非按值 grep。

## Data Models

本 spec **不新增**任何数据模型类型 —— 三个 spec 类、四种 store 形态、行模型全部由上游 D1 spec
定义。这里只实例化。涉及的 store 载荷：

| sheet | store 键 | kind | 受管区 | 已知下游消费方 |
|---|---|---|---|---|
| D3-2（已接） | `D3-det-rows` | `rows` | 1 | `useD3Analysis` / `D3TabVoucherCheck` |
| D3-4 | `D3-ana-credit-rows` / `D3-ana-debit-rows` | `rows` ×2 | 2 | `D3TabIndex` 完成度 |
| D3-5 | `D3-lt-rows` | `rows` | 1 | `D3TabIndex` 完成度 |
| D3-6 | `D3-rp-rows` | `rows` | 1 | `D3TabIndex` 完成度 |
| D3-7 | `D3-vc-current-rows` / `D3-vc-post-rows` | `rows` ×2 | 2 | **`useD3CrossSheet`** 读 post-rows |
| D3-1 | 待实测（审定表可能是 per-cell 锚点） | — | 待实测 | 待 grep |
| D3-3 | `D3-aje-rows` | `rows` | 🔍 核 | `useAdjustmentCentralSync` → 后端 |

Task 1 必须把「已知下游消费方」这一列 grep 补全 —— 上游 spec 的 P18 教训：只验该 sheet 自身
读回等值会放过「下游看不到回写」。

## 关键裁决

### 裁决 F1：D3 是单册，12 张 sheet 可同 entry，不受 D2 的三册约束

D2 因三册 + `entry ↔ template blob` 1:1 + `_entry_id` 从宿主派生（带碰撞检查）而被迫只扩第一册。
D3 实测单册 ⇒ 本 spec 的范围裁剪只依据**形态可行性**（可行性核硬门），不依赖册数。

### 裁决 F2：`store_item_id` 逐个实测，禁止按编号推演

见上文。变异检验有专项（Property 2）。

### 裁决 F3：D3-1 审定表的区块数与行模型待实测，不照 D1-1/D2-1 推演

实测三个循环的审定表形态互不相同：D1-1 三区（gross/bd/net）× 动态票据种类 per-cell 锚点；
D2-1 一区 × 写死 4 行 + SUMIF；D4-1 两区（主营/其他）× 动态行 + 四态。D3 预收账款是负债类，
形态未知 ⇒ Task 1 实测后再定 `sections` 与 `row_mode`，**不得**在引擎里加 `if is_d3` 分支
（会让上游 spec 的框架层 AST 卡点打红）。

### 裁决 F4：D3-3 走可行性核，且建议六张调整分录汇总表统一裁决

实证六张全部同型（各自宿主均接 `useAdjustmentCentralSync`，D4-4 已判 `single_html`）。
本 spec 只对 D3-3 做核并留证；**统一裁决建议另立**
`d-cycle-adjustment-sheets-single-html-adjudication`，避免在 D3/D5/D6/D7 四个 spec 里重复四遍
同一套判据与证据。

### 裁决 F5：`adapter_registered=False` 是真实前置，真栈实测须先解除

D3 与 D1/D2 的一个实质差异：真库 `register_from_manifest()` 当前只注册 `{d2,d4,g7,h1}`，
D3 因 `D3-det-rows` 全库 0 行、无 current published representation 而**未注册成功**。
⇒ 「整册 materialize 实测」在真库跑不起来。本 spec 的处置：代码与合成判据照常推进，真栈判据
如实标 `[ ]*` 并写明「代码已改但未实测，卡 adapter 未注册」，**不得**以合成测试冒充真栈。

## Error Handling

| 场景 | 处理 | 依据 |
|---|---|---|
| 上游框架层未入库 | 阶段 0 fail-closed 停工，判定用 `git show HEAD:` | 需求 7.1；上游曾因读工作树误登记 |
| `adapter_registered=False` | 真栈判据标 `[ ]*` + 写明卡点，代码与合成判据继续 | 裁决 F5 |
| specs 数 ≠ 契约 sheets 数 | attach fail-closed + 精确报差集 | D4-35 事故（7 vs 8 打挂整个 entry） |
| `store_item_id` 按编号推演 | Property 2 打红 | 裁决 F2；三次事故背书 |
| D3-4 / D3-7 被误声明单区 | 对齐计数守卫打红 | 需求 2.1 / 3.1 |
| 整册 materialize 超软上限 | 显式 domain error + 停止接入 | 需求 6.2 |
| 非受管 sheet 切在线编辑 | 保持现状行为 + 中文原因，不落 legacy 假双向 | 需求 6.6 |

## Correctness Properties

判据面。每条都必须被变异打红，否则重写而非保留（需求 8.1）。

### Property 1: D3-2 与其余 7 contract 的 golden digest 在扩容前后不变

**Validates: Requirements 6.3**　变异：D3-6 声明串进 D3-2 的 `table_key`。

### Property 2: 每个 `store_item_id` 逐字等于按值 grep 实测值

**Validates: Requirements 1.2, 2.3**　钉住裁决 F2。变异：把 `D3-rp-rows` 写成 `D3-6-rows`
⇒ 投影恒空、回写丢失，必红。🔴 这是本 spec 最容易犯且最难发现的错（D1/D2 共三次）。

### Property 3: D3-4 是双区（受管区 2→4），两键各自读回等值

**Validates: Requirements 2.1**　变异：只声明一个受管区 ⇒ 另一键数据在 OO 里不可见。

### Property 4: D3-7 是双区（受管区 5→7），两键各自读回等值

**Validates: Requirements 3.1**　变异：同上。

### Property 5: `formula_mask` 由引擎 property 现算，≡ 实测公式列 × 数据行区间

**Validates: Requirements 1.3**　变异：`formula_columns` 少一列。

### Property 6: D3-1 的 `sections` / `row_mode` 取自实测，非照 D1-1/D2-1 推演

**Validates: Requirements 4.3**　变异：把区块数改成 D1-1 的 3 或 D2-1 的写死 4 行 ⇒ 与模板
实测几何不符，必红。

### Property 7: D3-1 逐格 mask 下受管金额字段仍判 `editable`

**Validates: Requirements 4.2, 7.2**　依赖 `merge._protection` 格级判定已入库。
变异：换回 `column_in_ranges` ⇒ 必红（钉住 D4-1 踩过的坑）。

### Property 8: 上游变化后纯派生格不得被标成人工覆盖

**Validates: Requirements 4.4**　反证式：只改 `derived` 不改 `stored`/`snap` ⇒ 覆盖标记数为 0。
🔴 另须有一条**跑同步器**的判据 —— 上游 spec 有 13 条纯函数判据全绿而生产坏掉（同步器把显示值
当派生值写回 snap ⇒ 覆盖标记自我擦除）。变异：用 `stored ≠ derived` 错法。

### Property 9: 每张接入 sheet 的 store 键下游 computed 在 OO 回写后仍正确重算

**Validates: Requirements 1.5, 3.4**　已知 `useD3CrossSheet` 读 `D3-vc-post-rows`、
`D3TabIndex` 读各键做完成度判定；完整清单由 Task 1 grep 补全。变异：回写只更新一个键。

### Property 10: 整册 materialize 200 + verify 全绿（每批次）

**Validates: Requirements 1.4, 6.1**　🔴 判据必须**穿过** `verify_unmanaged_regions` ——
上游教训：判据只覆盖 adapter 两方法 ⇒「判据绿而生产 500」。变异：去掉兄弟 Table ref 位移。

### Property 11: D3-3 可行性核只产裁决与证据，不改生产代码

**Validates: Requirements 5.3**　变异：在核阶段改了 provider ⇒ 违反上游诚实边界红线，必红。

### Property 12: 前端受管 sheet 集合从 provider 派生，`capability`/`flushHtml` 读 Ref

**Validates: Requirements 6.6**　变异：前端硬编码 sheet 字面量 / 改回构造时字面量。

## Testing Strategy

**红判据先行。** 阶段 0 先取 D3-2 的 golden digest 基线（必绿）+ 打红 Property 2 与 Property 3
（现状 D3-6/D3-4 未接入 ⇒ 必红），它们是后续「修好了」的唯一归因依据。

**禁止两端各自 mock。** 真链必须：真 contract + 真 provider + 真 materialize
（`build_workbook_bytes`）+ 真 extract + 真 merge + **穿过 `verify_unmanaged_regions`**。

**真库无数据 ⇒ 合成 payload 驱动，但不冒充真栈。** D3 的 store 全库 0 行且
`adapter_registered=False` ⇒ 零回归门与往返判据以合成 payload 跑；真栈判据如实标 `[ ]*`。
🔴 **不得**把合成测试写成「真栈已过」—— 这是上游 spec 反复强调的假绿源。

**真栈三陷阱沿用上游结论**：不能用 `page.on('response')` 判 callback；不能用 `asc_*` API 写格；
模式切换条选择器须实测确认（D3 的须现场读，照抄 D4 会找不到元素）。

## 不在本 spec 范围

见 requirements §不在本 spec 范围。摘要：D3A 程序表 / 两张附注披露 / 底稿目录 / GT_Custom；
六张调整分录汇总表的统一裁决（建议另立
`d-cycle-adjustment-sheets-single-html-adjudication`）；性能根因优化；发布链 seed。

## 顺带发现（登记，不在本 spec 处理）

**D6/D7 底稿目录完成度判定引用无写入方的聚合键**（与 D1 那个「拼错锚点恒死」同型）：
`D6TabIndex.vue:54` 读 `D6-6-rows`（真实写入方用 `D6-6-block1-rows`/`-block2-rows`）、
`:56` 读 `D6-8-rows`（真实 `D6-8-single-rows`）、`D7TabIndex.vue:50` 读 `D7-4-rows`
（真实 `D7-4-credit-rows`/`-debit-rows`）、`:56` 读 `D7-7-rows`（真实 `D7-7-period-rows`/`-post-rows`）。
四键全仓零写入点 ⇒ 这四张底稿在目录里完成度恒显示「未填」。D3 侧未见同类。
建议随 D5/D6/D7 spec 一并修。

## 上游锚定（2026-09-25 第三轮复盘补：首版缺这一节）

🔴 **本 spec 是 umbrella spec `workpaper-html-onlyoffice-bidirectional-writeback-closure` 的
Task 46「逐一迁移 D 循环 Excel 独立 entry」的下游 lane spec**，与 D4 lane 同型。首版零引用该
umbrella 与其已冻结的 D 循环 slice，属 spec 卫生缺陷。

| 产物 | 位置 | 已冻结内容 |
|---|---|---|
| D 循环 manifest slice | `backend/data/workpaper_sync_d_cycle_manifest_slice.json`（1137 行） | Task 46 冻结的 7 个 D 循环独立 entry 逐项裁决 |
| umbrella Property 面 | umbrella design.md（1993 行） | Property 1–71；Task 46 声明验证 Property 20 / 21 / 28 / 69 / 70 |

### ✅ slice 实测证实并加强本 spec 的裁决 F5

裁决 F5 原文：「`adapter_registered=False` 是 D1/D2 没有的真实卡点 —— 真库
`register_from_manifest()` 当前只注册 `{d2,d4,g7,h1}`」。slice 实测**完全一致，但需修正一处措辞**：

```
xlsx/gt-d3-prepaid-accounts       legacy_fake_bidirectional   adapter=None
  verification_state  UNVERIFIABLE
  unverifiable_reasons  no_registered_sync_adapter / no_published_result_representation /
                        no_non_null_approved_definition_bundle /
                        no_instrumentation_candidate_for_this_entry /
                        no_real_onlyoffice_94_probe_run_for_this_entry
```

🔴 **修正**：裁决 F5 说这是「D1/D2 没有的卡点」——**D2 确实没有（已注册 `d2.receivable_detail`），
但 D1 有**。slice 实测 `xlsx/gt-d1-notes-receivable` 同为 `legacy_fake_bidirectional` +
`adapter_id=None` + 同样五条 `unverifiable_reasons`。⇒ 该卡点覆盖 **D1/D3/D5/D6/D7 五家**，
7 家里只有 **D2/D4** 通过。裁决 F5 的处置（代码与合成判据照常推进、真栈判据如实标 `[ ]*`、
不得以合成测试冒充真栈）**不变且适用面更广**。

### 该卡点是平台级的，不是 D3 独有

umbrella 的 **BP-61-1** 实测 `working_paper_sync_entry_state` / `working_paper_content_version` /
`working_paper_content_representation` 三表近空，**186 个 planned entry 一个都注册不上**；
生产者是 `ContentMutationService.commit(...)` 与 umbrella Tasks 36/77 的 finalize gate。
⇒ D1/D3/D5/D6/D7 + E1 六个循环卡在同一供给缺口，**不该在六个 spec 里各自把发布链重做一遍**。

### Property 编号必须 spec-scoped

umbrella 自己踩过同号不同义的坑（Task 61 附注：全局 `BP-16`~`BP-22` 被 Tasks 60/63/64 重复占用，
修法是 task-scoped 前缀 + `re.fullmatch` 锁死）。⇒ 本 spec 的 `Property N` 一律读作
**`D3-P{N}`**，引用上游须写全 `umbrella Property N`。
