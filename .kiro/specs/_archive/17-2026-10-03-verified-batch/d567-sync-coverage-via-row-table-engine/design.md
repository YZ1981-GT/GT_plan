# Design Document

## Overview

D5/D6/D7 三循环受管覆盖 **各 1 → 合计 20 个受管区**（D5 3 / D6 9 / D7 8），外加修一个跨循环的
底稿目录聚合键缺陷。本 spec 是纯**声明层** + 一处 bugfix：引擎、注册表、`AdjudicationSheetSpec`、
四态状态机全部由上游 `d1-sync-row-table-engine-and-d1-coverage` 交付，裁决与分波由
`d-cycle-sheet-bidirectional-expansion` 提供。

**三家合一个 spec 的依据**（用户 B 方案裁决）：provider 同构度实测最高的一组 —— 33 个函数名
逐字相同、`FORMULA_MASK` 均列向、差异只在 `aging_layout` 一个参数（nested/flat/无）。分三份写
会有八成样板重复，且它们恰好构成引擎三条账龄路径的完整样本集。

## Architecture

### 三 entry 并行，互不影响

```
D5  xlsx/gt-d5-receivables-financing   contract d5.receivables_financing_detail   d52-managed
D6  xlsx/gt-d6-contract-assets         contract d6.contract_assets_detail         d62-managed
D7  xlsx/gt-d7-contract-liabilities    contract d7.contract_liabilities_detail    d72-managed
```

三家各自单册、各自一 entry ⇒ **整册 materialize 的爆炸半径彼此隔离**，一家挂了不影响另两家。
这是「不合并 entry」裁决在本 spec 的直接红利：三条接入链可并行推进、独立回滚。

### 声明层结构（三家同构，只差 aging 参数）

```
phase5_d5_receivables_financing.py   循环层（781 → ≤150 行）   aging_layout=None
  phase5_d5_02_detail.py             已接
  phase5_d5_04_fair_value.py         ✅ D5-4-rows
  phase5_d5_01_adjudication.py       ✅ managed_sheet="审定表D5"（🔴 无 -1 后缀）

phase5_d6_contract_assets.py         循环层（849 → ≤150 行）   aging_layout=flat
  phase5_d6_02_detail.py             已接
  phase5_d6_03_impairment.py         ✅ D6-3-rows
  phase5_d6_05_related_party.py      ✅ D6-5-rows
  phase5_d6_06_inspection.py         ✅ 双区 D6-6-block1-rows / -block2-rows
  phase5_d6_08_ecl.py                ✅ D6-8-single-rows（不是 D6-8-rows）
  phase5_d6_09_writeoff.py           ✅ 双区 D6-9-reversal-rows / -writeoff-rows
  phase5_d6_01_adjudication.py       ✅ 177 公式逐格

phase5_d7_contract_liabilities.py    循环层（844 → ≤150 行）   aging_layout=nested
  phase5_d7_02_detail.py             已接
  phase5_d7_04_analysis.py           ✅ 双区 D7-4-credit-rows / -debit-rows
  phase5_d7_05_long_term.py          ✅ D7-5-rows（与 D3-5 同型，骨架可复制）
  phase5_d7_06_related_party.py      ✅ D7-6-rows
  phase5_d7_07_inspection.py         ✅ 双区 D7-7-period-rows / -post-rows
  phase5_d7_01_adjudication.py       ✅ 84 公式逐格
```

### 受管区增长路线（三家独立计数）

```
D5:  1 → 2 (D5-4)  → 3 (审定表D5)                                  D5-3 可行性核
D6:  1 → 2 (D6-3) → 3 (D6-5) → 5 (D6-6 双区) → 6 (D6-8)
       → 8 (D6-9 双区) → 9 (D6-1)                                  D6-4 可行性核 / D6-7 形态核
D7:  1 → 3 (D7-4 双区) → 4 (D7-5) → 5 (D7-6) → 7 (D7-7 双区) → 8 (D7-1)   D7-3 可行性核
```

顺序理由：每家都**先单区后双区最后审定表** —— 单区证明多受管 sheet 通路、双区验位移链、
审定表依赖两个外部前置且形态最复杂。三家可并行，但 D6 的 flat 与 D7 的 nested 建议**同批推进**，
这样上游引擎的两条账龄路径在同一轮里对照验证（差异一旦出现能立即归因到 `aging_layout` 参数）。

## Components and Interfaces

### 声明形态（几何由 Task 1 实测填，此处只示意差异面）

```python
# D5：aging_layout=None，引擎「无分组」路径基准
SPEC_D504 = RowTableSheetSpec(
    managed_sheet="应收款项融资公允价值测算表D5-4", sheet_key="d54-managed",
    table_key="fair_value_rows", store_item_id="D5-4-rows",
    aging_layout=None, formula_columns=(...),  # Task 1 实测（18 公式主列 K6 I4）
)
SPEC_D501 = AdjudicationSheetSpec(
    managed_sheet="审定表D5",        # 🔴 实测名无 -1 后缀，推演会 sheet 找不到
    sections=(...), row_mode=...,    # Task 1 实测，不照 D1-1/D2-1/D3-1 推演
)

# D6：aging_layout=flat，引擎 flat 路径唯一样本；双区形如 D4-9
SPEC_D606_BLOCK1 = RowTableSheetSpec(
    managed_sheet="合同资产检查表D6-6", sheet_key="d66-managed-b1",
    table_key="inspection_block1_rows", store_item_id="D6-6-block1-rows", ...)
SPEC_D606_BLOCK2 = RowTableSheetSpec(..., store_item_id="D6-6-block2-rows", ...)
SPEC_D608 = RowTableSheetSpec(..., store_item_id="D6-8-single-rows", ...)  # 🔴 不是 D6-8-rows

# D7：aging_layout=nested（与 D3 同路径）
SPEC_D704_CREDIT = RowTableSheetSpec(..., store_item_id="D7-4-credit-rows", ...)
SPEC_D704_DEBIT  = RowTableSheetSpec(..., store_item_id="D7-4-debit-rows", ...)
```

### 🔴 三处「按模式推演必错」的实测值

| 推演值（错） | 实测值（对） | 后果 |
|---|---|---|
| `审定表D5-1` | **`审定表D5`** | sheet 找不到，attach fail-closed |
| `D6-8-rows` | **`D6-8-single-rows`** | 投影恒空、回写丢失（前者全仓零写入点） |
| `D6-6-rows` / `D7-4-rows` / `D7-7-rows` | 各自的 block/credit/debit/period/post 键 | 同上 |

这四个聚合键（`D6-6-rows` / `D6-8-rows` / `D7-4-rows` / `D7-7-rows`）**全仓零写入点**，只在
`D*TabIndex.vue` 的完成度判定里被读 —— 那正是需求 5 要修的缺陷。声明时误用它们会让整个受管区
投影恒空。

## Data Models

本 spec **不新增**任何数据模型类型。涉及的 store 载荷（全部 `StoreKind.rows`）：

| 循环 | sheet | store 键 | 受管区 | 已知下游消费方 |
|---|---|---|---|---|
| D5 | D5-2（已接） | `D5-2-rows` | 1 | `useD5CrossSheet` |
| D5 | D5-4 | `D5-4-rows` | 1 | `useD5CrossSheet` / `useD5FairValue` |
| D5 | 审定表D5 | 待实测 | 待实测 | 待 grep |
| D6 | D6-2（已接） | `D6-2-rows` | 1 | `useD6CrossSheet` / `useD6Detail` |
| D6 | D6-3 | `D6-3-rows` | 1 | `useD6CrossSheet` / `D6TabWriteoffCheck` |
| D6 | D6-5 | `D6-5-rows` | 1 | `useD6RelatedParty` |
| D6 | D6-6 | `D6-6-block1-rows` / `-block2-rows` | 2 | `D6TabInspection` / `useD6Inspection` |
| D6 | D6-8 | `D6-8-single-rows` | 1 | `useD6CrossSheet` / `useD6EclCalculation` |
| D6 | D6-9 | `D6-9-reversal-rows` / `-writeoff-rows` | 2 | `useD6WriteoffCheck` |
| D7 | D7-2（已接） | `D7-2-rows` | 1 | `D7TabLongTerm` / `useD7Analysis` |
| D7 | D7-4 | `D7-4-credit-rows` / `-debit-rows` | 2 | `useD7Analysis` |
| D7 | D7-5 | `D7-5-rows` | 1 | `useD7Disclosure` / `useD7LongTerm` |
| D7 | D7-6 | `D7-6-rows` | 1 | `D7TabDetail` / `useD7RelatedParty` |
| D7 | D7-7 | `D7-7-period-rows` / `-post-rows` | 2 | **`useD7CrossSheet` / `useD7Detail`** |

Task 1 必须把「已知下游消费方」grep 补全 —— 上游 P18 教训：只验该 sheet 自身读回等值会放过
「下游看不到回写」。

## 关键裁决

### 裁决 G1：三家合一 spec，但三条接入链独立计数、独立回滚

合一是为了消除样板重复（provider 同构度最高的一组）；但受管区计数、materialize 实测、灰度开关
三者**按循环独立**，因为三家是三个 entry、爆炸半径天然隔离。⇒ D6 挂了不阻塞 D5/D7。

### 裁决 G2：D6 的 flat 与 D7 的 nested 同批推进，作引擎两条账龄路径的对照

上游引擎把四家（D2/D3/D6/D7）逐字相同的 `sorted(SCALAR + _aging(), key=_col_index)` 收进
`managed_field_specs()`，并用 `aging_layout` 分派 nested/flat 两种 key 派生。D6 是 flat 的
**唯一**样本、D7 是 nested 的样本之一。同批推进使两条路径在同一轮对照验证 —— 一旦输出有差异，
能立即归因到 `aging_layout` 参数而不是别处。

### 裁决 G3：`store_item_id` 与 `managed_sheet` 逐个实测，禁止按模式推演

三处实证必错（见上表）。这条有四次事故背书：D2-3 三键 / D1-15 双键 / D1-13 双键的遗漏 + D3 的
语义缩写键名，全部源于「按模式推演」。Property 2 专项钉住。

### 裁决 G4：聚合键缺陷（需求 5）独立交付，不与受管扩容耦合

`D6-6-rows` / `D6-8-rows` / `D7-4-rows` / `D7-7-rows` 四个无写入方聚合键导致底稿目录完成度恒
「未填」。它是纯前端 bugfix、不依赖任何前置 ⇒ 排在阶段 0 独立交付。这样做还有个副作用红利：
修完之后，后续声明里误用这些聚合键会更容易被发现（它们已从代码里消失）。

🔴 **判据不得镜像错误键名**。D1 那次事故的形态是「三个消费方的单测都镜像了同款错误锚点，
故测试恒绿而生产恒死」。本需求的判据必须以**真实写入方的键**播种、断言完成度为已填。

### 裁决 G5：三张审定表的 `sections`/`row_mode` 全部待实测

已实测四个循环的审定表形态互不相同：D1-1 三区 × 动态票据种类 per-cell；D2-1 一区 × 写死 4 行
+ SUMIF；D4-1 两区 × 动态行 + 四态；D3-1 待实测。D5/D6-1/D7-1 公式数分别 52 / **177** / 84，
密度差异大（D6-1 达 32%）⇒ 形态大概率也不同。**不得**在引擎里加 `if is_d5/d6/d7` 分支。

### 裁决 G6：`adapter_registered=False`（三家全 False）是真实前置

真库 `register_from_manifest()` 只注册 `{d2,d4,g7,h1}`。D5/D6 的 store 全库 0 行、无 current
published representation ⇒ 真栈整册 materialize 跑不起来。处置同 D3 spec：代码与合成判据照常
推进，真栈判据如实标 `[ ]*` 写明卡点，**不得**以合成测试冒充真栈。

## Error Handling

| 场景 | 处理 | 依据 |
|---|---|---|
| 上游框架层 / `aging_layout` 参数化未入库 | 阶段 0 fail-closed 停工，判定用 `git show HEAD:` | 需求 7.1 |
| 三家 `adapter_registered=False` | 真栈判据标 `[ ]*` + 写明卡点，代码与合成判据继续 | 裁决 G6 |
| `managed_sheet` 按模式推演（`审定表D5-1`） | attach fail-closed，sheet 找不到 | 裁决 G3 |
| `store_item_id` 用聚合键（`D6-8-rows`） | 投影恒空、回写丢失 ⇒ Property 2 打红 | 裁决 G3 |
| specs 数 ≠ 契约 sheets 数 | attach fail-closed + 精确报差集 | D4-35 事故（7 vs 8 打挂整个 entry） |
| 四组双区被误声明单区 | 对齐计数守卫打红 | 需求 2.3/2.5/3.1/3.4 |
| flat 走 nested 派生（或反之） | 上游引擎 Property 4 打红（D6 必红） | 裁决 G2 |
| 历史残留 sheet 被误纳入 | 声明时显式排除 + 确认分派正则 | 需求 6.6 |
| 整册 materialize 超软上限 | 显式 domain error + 停止该循环接入 | 需求 6.2 |

## Correctness Properties

判据面。每条都必须被变异打红，否则重写而非保留（需求 8.1）。

### Property 1: 三张已接明细与其余 contract 的 golden digest 在扩容前后不变

**Validates: Requirements 6.3**　变异：新 sheet 声明串进已接明细的 `table_key`。

### Property 2: 每个 `store_item_id` 与 `managed_sheet` 逐字等于实测值

**Validates: Requirements 1.1, 1.2, 2.1, 2.4, 3.1**　钉住裁决 G3。变异三例：`审定表D5` 写成
`审定表D5-1`（sheet 找不到）/ `D6-8-single-rows` 写成 `D6-8-rows`（零写入点键 ⇒ 投影恒空）/
`D7-4-credit-rows` 写成 `D7-4-rows`。🔴 四次事故背书，本 spec 最易犯的错。

### Property 3: 四组双区各自受管区数正确，两键均读回等值

**Validates: Requirements 2.3, 2.5, 3.1, 3.4**　D6-6 / D6-9 / D7-4 / D7-7。
变异：只声明一个受管区 ⇒ 另一键数据在 OO 里不可见。

### Property 4: 同 sheet 双区位移链成立（上区插行 ⇒ 下区 Table ref 下移）

**Validates: Requirements 7.4**　四组双区各自实证：兄弟 Table ref 位移 + `_GT_SYNC` footer
重冻结 + verify 累积归一化。变异：去掉兄弟 Table ref 位移。

### Property 5: D6 的 flat 与 D7 的 nested 键派生各自等于原写法

**Validates: Requirements 2.9, 3.7**　钉住裁决 G2。变异：把 flat 走 nested 派生 ⇒ D6 必红。

### Property 6: 三张审定表的 `sections`/`row_mode` 取自实测，非照其他循环推演

**Validates: Requirements 1.2, 2.6, 3.5**　变异：把 D6-1 的区块数改成 D1-1 的 3 区。

### Property 7: 逐格 mask 下受管金额字段仍判 `editable`

**Validates: Requirements 7.2**　依赖 `merge._protection` 格级判定已入库。
变异：换回 `column_in_ranges` ⇒ 必红（钉住 D4-1 踩过的坑）。

### Property 8: 上游变化后纯派生格不得被标成人工覆盖

**Validates: Requirements 1.2, 2.6, 3.5**　反证式：只改 `derived` 不改 `stored`/`snap` ⇒ 覆盖
标记数为 0。🔴 另须一条**跑同步器**的判据（上游 13 条纯函数判据全绿而生产坏掉的教训）。

### Property 9: 每个 store 键的下游 computed 在 OO 回写后仍正确重算

**Validates: Requirements 1.5, 3.8**　已知 `useD7CrossSheet`/`useD7Detail` 读 `D7-7-post-rows`、
`useD6CrossSheet` 读多键；完整清单由 Task 1 grep 补全。变异：回写只更新一个键。

### Property 10: 聚合键缺陷修复后完成度正确，且判据不镜像错误键名

**Validates: Requirements 5.1, 5.2, 5.3**　以**真实写入方的键**播种 ⇒ 断言完成度为已填。
变异：改回聚合键 ⇒ 必红。🔴 D1 那次「单测镜像同款错误锚点、测试恒绿而生产恒死」是同源事故。

### Property 11: 四个聚合键在全仓零残留引用

**Validates: Requirements 5.4**　变异：留一处 ⇒ 必红。

### Property 12: 历史残留 sheet 被显式排除且分派正则不误判

**Validates: Requirements 6.6**　D6 册的 `合同资产实质性程序表 D7A（原）`（104 行）与 D7 册的
`合同负债实质性程序表 D8A（原）`（66 行）。变异：让它们进受管清单。

### Property 13: 三家整册 materialize 200 + verify 全绿（每批次，按循环独立）

**Validates: Requirements 6.1**　🔴 判据必须**穿过** `verify_unmanaged_regions`。
变异：去掉 sibling 受管坐标并入 `extra_managed_coords`。

### Property 14: 三张调整分录汇总表可行性核只产裁决与证据，不改生产代码

**Validates: Requirements 4.3**　变异：核阶段改了 provider ⇒ 违反上游诚实边界红线。

### Property 15: 前端受管 sheet 集合从 provider 派生，`capability`/`flushHtml` 读 Ref

**Validates: Requirements 6.5**　三家宿主同形（均单张写死）。变异：前端硬编码字面量。

## Testing Strategy

**红判据先行。** 阶段 0 先取三家 golden digest 基线（必绿）+ 打红 Property 2 / 3 / 10/11
（现状新 sheet 未接入、聚合键缺陷未修 ⇒ 必红）。

**禁止两端各自 mock。** 真链必须：真 contract + 真 provider + 真 materialize + 真 extract +
真 merge + **穿过 `verify_unmanaged_regions`**。

**真库无数据 ⇒ 合成 payload 驱动，但不冒充真栈。** D5/D6 的 store 全库 0 行且三家
`adapter_registered=False` ⇒ 零回归门与往返判据以合成 payload 跑；真栈判据如实标 `[ ]*`。
🔴 **不得**把合成测试写成「真栈已过」。

**三家独立分母。** 每个循环的回归集与耗时基线各自记，不混算 —— 三家是三个 entry，混算会让
「哪家退化了」无法归因。

**真栈三陷阱沿用上游结论**，且模式切换条选择器**须逐循环实测**（D5/D6/D7 各自的宿主不同，
照抄任一家都可能找不到元素）。

## 不在本 spec 范围

见 requirements §不在本 spec 范围。摘要：三家程序表 / 两张历史残留 / 六张附注披露 / 底稿目录 /
GT_Custom；七张调整分录汇总表的统一裁决（建议另立
`d-cycle-adjustment-sheets-single-html-adjudication`）；D6-7 政策检查的接入（本 spec 只做形态核）；
性能根因优化；发布链 seed（三家 `adapter_registered=False` 解除）。

## 上游锚定（2026-09-25 第三轮复盘补：首版缺这一节）

🔴 **本 spec 是 umbrella spec `workpaper-html-onlyoffice-bidirectional-writeback-closure` 的
Task 46「逐一迁移 D 循环 Excel 独立 entry」的下游 lane spec**，与 D4 lane 同型。首版零引用该
umbrella 与其已冻结的 D 循环 slice，属 spec 卫生缺陷。

| 产物 | 位置 | 已冻结内容 |
|---|---|---|
| D 循环 manifest slice | `backend/data/workpaper_sync_d_cycle_manifest_slice.json`（1137 行） | Task 46 冻结的 7 个 D 循环独立 entry 逐项裁决 |
| umbrella Property 面 | umbrella design.md（1993 行） | Property 1–71；Task 46 声明验证 Property 20 / 21 / 28 / 69 / 70 |

### ✅ slice 实测证实裁决 G6（三家 `adapter_registered` 全 False）

```
xlsx/gt-d5-receivables-financing  legacy_fake_bidirectional   adapter=None
xlsx/gt-d6-contract-assets        legacy_fake_bidirectional   adapter=None
xlsx/gt-d7-contract-liabilities   legacy_fake_bidirectional   adapter=None
  三家 verification_state 均 UNVERIFIABLE，五条 unverifiable_reasons 含 no_registered_sync_adapter
```

裁决 G6 的处置（代码与合成判据照常推进、真栈判据如实标 `[ ]*` 写明卡点、不得以合成测试冒充真栈）
**得到 slice 独立确认**。

🔴 **但适用面比裁决 G6 写的更广**：G6 把这描述为 D5/D6/D7 三家的卡点，slice 实测
**D1 与 D3 同态**（同为 `legacy_fake_bidirectional` + `adapter_id=None` + 同样五条 reasons）
⇒ 7 家 D 循环 entry 里只有 **D2/D4** 通过，卡点覆盖 **D1/D3/D5/D6/D7 五家**，再加 E1 共六个循环。

### 该卡点是平台级的，不是 D5/D6/D7 独有

umbrella 的 **BP-61-1** 实测 `working_paper_sync_entry_state` / `working_paper_content_version` /
`working_paper_content_representation` 三表近空，**186 个 planned entry 一个都注册不上**，
连供给最完整的 Excel pilot 也一样；生产者是 `ContentMutationService.commit(...)` 与 umbrella
Tasks 36/77 的 finalize gate。

⇒ 六个循环卡在同一供给缺口，**不该在六个 spec 里各自把发布链重做一遍**。本 spec 只负责
provider 侧就绪 + 判据先行；发布链归 umbrella。这也意味着本 spec 的「真栈段全卡」**不是本 spec
的实现缺陷**，登记时须写 `upstream_gap` 而非 `failed`。

### Property 编号必须 spec-scoped

umbrella 自己踩过同号不同义的坑（Task 61 附注：全局 `BP-16`~`BP-22` 被 Tasks 60/63/64 重复占用，
修法是 task-scoped 前缀 `BP-61-x` + `re.fullmatch` 锁死）。⇒ 本 spec 的 `Property N` 一律读作
**`D567-P{N}`**，引用上游须写全 `umbrella Property N`。
