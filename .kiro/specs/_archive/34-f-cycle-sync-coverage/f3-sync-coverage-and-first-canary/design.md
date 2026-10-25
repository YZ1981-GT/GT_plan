# Design Document

## Overview

F3 应付票据从 legacy 假双向接成真双向：canary 取 F3-5（逾期检查，数据区零公式 + 真库唯一有载荷），再按形态驱动扩到
F3-6 → F3-7（三区）→ F3-2（明细）→ F3-4（利息测算），最后接 F3-1 审定表；F3-3 只做可行性核。

F3 的特点是**三处必须先裁决才能受管**，且都不是工程问题而是口径/容量问题：
1. **F3-1 类别槽位 5 > 4**（模板 R7-R10 四槽 vs 前端五类别）
2. **F3-1 取数口径**（模板 SUMPRODUCT 汇总 vs 前端手填 AJE/RJE，双写入源）
3. **F3-4 应计利息口径**（模板不含天数 vs 前端含 `days/360`）——「以模板为权威」在此会**降低审计精度**，是 FC-5 的首个例外候选

F 循环共同裁决 FC-1~FC-13 见 `f1-sync-coverage-and-first-canary/design.md`；**FC-11 由本 spec 提出**（prefill `items` 型块死配置）。

## 上游锚定

沿用 F1 spec 上游锚定表。F3 与 D1（应收票据）互为借贷镜像 ⇒ `phase5_d1_notes_receivable.py` 与
`phase5_d1_07_memo.py`（票据备忘 dict 双区）是 F3-2 / F3-7 的直接参照；F3-1 的稳定 `rowKey` 固定行参照 D2-1
（`fixed_rows`）与 D4-6。

## Architecture

### 接入顺序（形态驱动 + 前置驱动）

```
F3-5 逾期检查（canary：零公式数据区 / 真库有载荷 / 单区；I 列 FC-10 暂 HTML-only）
  → F3-6 关联方（单区 + 1 公式列，验证「第二张复用框架层零改动」）
  → F3-7 三区（兄弟 Table ref 位移；三区列集不同）
  → F3-2 明细（两级表头；J/U 两列 FC-10 待换算）
  → F3-4 利息测算（B5 口径裁决落地后；默认先只接非 H 列）
  → F3-1 审定表（B3 槽位 + B4 口径两处裁决落地后）
F3-3：可行性核（FC-6 默认 single_html）
```

### 声明层结构

```
backend/app/services/workpaper_sync/
  phase5_f3_notes_payable.py        ← entry 层 provider（开关 / 登记 / 契约 / attach）
  phase5_f3_05_overdue.py           ← canary
  phase5_f3_06_related_party.py
  phase5_f3_07_voucher_check.py     ← 三个 spec（debit / credit / subsequent）
  phase5_f3_02_detail.py
  phase5_f3_04_interest.py
  phase5_f3_01_adjudication.py      ← RowTableSheetSpec（稳定 rowKey），非 AdjudicationSheetSpec
backend/data/workpaper_sync_contracts/f3.notes_payable_detail.json
backend/scripts/gen/generate_phase5_f3_contract.py
```

sheet 层声明文件只含常量与 spec 实例（无 `def` / 无 `class`）。

### 受管区清单（逐格实测几何）

| sheet_key | managed_sheet | store_item_id | 表头 | 数据 | footer | UUID | formula_columns |
|---|---|---|---|---|---|---|---|
| `f35-managed` | 逾期票据检查F3-5 | `F3-5-rows` | R5/R6 | R7-21 | R22「合计」 | P | （无） |
| `f36-managed` | 关联方及交易检查表F3-6 | `F3-6-rows` | R6 | R7-12 | R13「合计」 | N | G |
| `f37-debit` | 应付票据检查表F3-7 | `F3-7-debit-rows` | R15/R16 | R17-36 | R37「合计」 | S | （无） |
| `f37-credit` | 同上 | `F3-7-credit-rows` | R39/R40 | R41-58 | R59「合计」 | S | （无） |
| `f37-subsequent` | 同上 | `F3-7-subsequent-rows` | R61/R62 | R63-79 | R80「合计」 | S | （无） |
| `f32-managed` | 明细表F3-2 | `F3-2-rows` | R13/R14 | R15-30 | R31「合␠␠计」 | X | O, R |
| `f34-managed` | 应付票据（带息）利息测算表F3-4 | `F3-4-rows` | R9/R10 | R11-31 | R32「合␠␠计」 | L | H, J |
| `f31-managed` | 审定表F3-1 | `F3-1-adj-rows` | R6 | R7-10 | R11「合计」 | （见裁决 F3-H4） | B,E,F,G,H,I（**行级差异**） |

## Data Models

不新增数据模型。store 形态：`rows`（全部 7 张，含 F3-1 的稳定 `rowKey` 行数组）。无 dict、无 per-cell、无 `static_region`。

## 关键裁决

### 裁决 F3-H1：canary 选 F3-5，不选明细表 F3-2

| 候选 | 数据区公式 | FC-10 | 真库载荷 | 跨 sheet 消费方 | 结论 |
|---|---|---|---|---|---|
| F3-2 明细 | 2 列（O/R） | 🔴 J/U 两列 | 0 行 | 6 处 | 面太大 |
| **F3-5 逾期** | **0**（footer 才有 SUM） | 🔴 I 列（可 HTML-only 绕开） | **675 B（全 F3 唯一）** | 0 | ✅ |
| F3-6 关联方 | 1 列（G） | 无 | 0 行 | 0 | 次选 |

canary 的职责是验证**发布链**（FC-1），有真数据可做 roundtrip 比无数据的「空表往返」更有说服力；I 列 FC-10 可通过
「暂不进 field_specs」绕开，不阻塞链路。

### 裁决 F3-H2：F3-4 应计利息是 FC-5 的首个例外候选 —— 默认不受管 H 列

FC-5 的一般规则是「以模板为权威修前端」，但 F3-4 的模板式 `ROUND(F*G,2)` **缺天数折算**，而前端式
`F*G/100*days/360` 是审计上正确的应计利息算法。以模板为权威会让 HTML 侧也丢掉天数 ⇒ 精度下降、业务倒退。
故本裁决把三个方向并列，默认取③：

| 方向 | 代价 |
|---|---|
| ① 改前端对齐模板 | 业务精度下降（用户可见数值变化），需业务确认 |
| ② 模板覆盖层把 H 改为含天数 | 改权威模板语义，须审计方法论确认 + 覆盖层依赖 |
| ③ **H 列判 HTML-only、其余列受管**（默认） | OO 侧 H 列仍按模板算、HTML 侧按天数算 —— 但 H 是 `mode=formula` 不回写，**不产生数据分歧**，只产生「两侧显示值不同」的观感问题，须在 UI 中文提示 |

⇒ 本 spec 交付时选③并在证据中记录三方向；①②需业务确认，登记为 follow-up。

### 裁决 F3-H3：F3-1 用 RowTableSheetSpec（稳定 rowKey），不用 AdjudicationSheetSpec

F3-1 的 store 是**行数组**（`F3-1-adj-rows`，按 `rowKey` 索引），而 `AdjudicationSheetSpec` 面向 per-cell mask
（F1-1 / D1-1 那种 `F1-adj-${section}-${rowKey}-${field}` 形态）。F3-1 的行身份是稳定业务键、行不增删（只按需 push 类别），
与 D2-1 `fixed_rows` / D4-6「稳定 key 固定行」同型 ⇒ 用 `RowTableSheetSpec` + `row_identity_key="rowKey"` + `excel_table`
binding（仍注入 UUID 列）。🔴 不得因为「它叫审定表」就照 F1-1 用 `AdjudicationSheetSpec`（形态由前端三元组决定，FC-4）。

### 裁决 F3-H4：F3-1 的 mask 是行级不是矩形 —— 拆两个 spec

实测 R7/R8 有 6 个公式列（B/E/F/G/H/I），R9/R10 只有 2 个（E/I，因为空槽行无 SUMPRODUCT）。引擎的 `formula_mask` 是
`formula_columns × [first_data_row, last_data_row]` 的**矩形**（`phase5_row_table_sheet.RowTableSheetSpec.formula_mask`
property）⇒ 若声明 6 列会把 R9/R10 的 B/F/G/H 误标为 formula（实际可编辑），导致用户在 OO 里填这四格被判受保护冲突。
裁决：**拆两个 spec**（`f31-seed`：R7-8，6 公式列；`f31-slot`：R9-10，2 公式列），同 sheet 走兄弟 Table ref 路径
（F3-7 三区同机制，先在 F3-7 验通）。否决「给引擎加行级 mask 声明位」——框架层改动面大，且拆 spec 已有先例。

### 裁决 F3-H5：类别槽位超限时降级，不改模板

模板 4 槽 vs 前端 5 类别（B3）。默认取「实际类别数 ≤4 时启用受管，超限时整表降级为 legacy + 中文提示」：
理由是超限是**低频业务场景**（同时存在信用证 + 供应链 + 其他三类非承兑票据），而扩模板槽位要动权威模板、
限制前端类别会丢业务信息。降级判据须可观测（`capability` 说明文案含「票据类别超过 4 类」）。

### 裁决 F3-H6：FC-11 的修复在本 spec 内做完 F3 部分，并修工具链根因

`items` 型块的产生机制在 `fix_f_cycle_prefill_presets.py._ensure_cells`（L418-L423）。本 spec 修 F3 的三块 +
**改工具链只写 `cells`**（根因），F4/F5 的块由各自 spec 迁移（数据改动分 spec、工具链改一次）。
`--check` 同步改为只认 `cells`，否则「工具绿 / 运行时死」的矛盾会再现。

## Error Handling

| 场景 | 处理 | 依据 |
|---|---|---|
| footer 标记写成「合计」而模板是「合␠␠计」 | footer 定位失败 ⇒ 构造期/验收期报错，不静默 | 需求 2.4 |
| F3-1 类别数 > 4 | 整表降级 legacy + 中文原因 | F3-H5 |
| F3-1 空槽行 B/F/G/H 被标 formula | 拆两 spec 避免；判据钉住 R9/R10 这四列为 editable | F3-H4 |
| FC-10 列未换算 | 该列不进 `field_specs`，OO 侧填写不回写并中文登记 | 需求 3.3 |
| F3-4 H 列 | `mode=formula` 不回写；UI 提示两侧算法差异 | F3-H2 |
| store 行缺 `rowId` | fail-closed，不静默跳过 | FC-4 |
| 发布链第③环缺供给 | 如实 `upstream_gap` | BP-61-1 |
| sync 路径触发 TB 写 | 判据必红 + CI 守卫 | FC-9 |

## Correctness Properties

### Property 1: canary 打通后 migration_state 与 legacy_reasons 正确变更
**Validates: 1.5**　变异：跳过发布链任一环 ⇒ 状态不变。

### Property 2: `store_item_id` 逐字等于按值实测值
**Validates: 2.2**　变异 ①`subsequent → post` ②`F3-5-rows → F3-overdue-rows` ⇒ 投影恒空必红。

### Property 3: `binding_kind` / `row_identity_key` 取自三元组
**Validates: 2.1**　F3-1 是 `rowKey`、其余六张是 `rowId`。变异：F3-1 用 `rowId` ⇒ 稳定类别行身份丢失、每次载入换 id，必红。

### Property 4: footer marker 逐字含空格
**Validates: 2.4**　F3-2「合␠␠计」/ F3-4「合␠␠计」/ 其余「合计」。变异：统一写「合计」⇒ 两张定位失败必红。

### Property 5: F3-1 空槽行的 B/F/G/H 判 editable
**Validates: 6.1**　变异：单 spec 声明 6 公式列 ⇒ R9/R10 四列被误标 formula，必红。

### Property 6: F3-1 类别数 > 4 时降级且不丢数据
**Validates: 6.2**　构造 5 类别载荷 ⇒ 受管判定为关 + legacy 路径读到全 5 行。

### Property 7: F3-1 取数口径与模板一致（B4 落地后）
**Validates: 6.3**　B/F/G/H/I 等于按类别 SUMPRODUCT 明细 L/O/P/Q/R。

### Property 8: F3-4 H 列不回写且两侧算法差异被显式登记
**Validates: 4.2**　H 为 `mode=formula`；OO 改 H 产生受保护冲突；证据含三方向裁决记录。

### Property 9: FC-10 列在换算落地前不受管
**Validates: 3.3, 4.3**　F3-2 J/U、F3-4 G、F3-5 I 不在 `field_specs`。变异：纳入 ⇒ OO 显示放大 100 倍，必红。

### Property 10: F3-7 三区列集互不串用 + 兄弟 Table 位移
**Validates: 5.2, 5.3**　区①插 5 行后区②③ footer SUM 区间与数据验证随位移、数据不变。

### Property 11: F3-6 下拉源区随位移同步
**Validates: 2.3**　插行后 `B7:B12` 的 `formula1=$B$19:$B$26` 指向正确（位移链已支持 `formula1`）。

### Property 12: FC-11 —— prefill 块只用 `cells`，工具链不再造 `items`
**Validates: 7.2**　①`prefill_formula_mapping.json` 中 F3 块 `items` 键数为 0 ②`_ensure_cells` 源码不含
`block["items"] = []` ③`--check` 对「块只有 items」必红 ④`convert_prefill_presets()` 的 `workpaper:F3` 预设数 > 18（迁入后增加）。

### Property 13: 已修缺陷不回归（B7）
**Validates: 7.4**　累加器键集合 == `F3_CATEGORY_META` 键集合；无明细时附注期末 == 审定表 `computeRow` 期末。

### Property 14: F3-4 → F3-3 注入幂等
**Validates: 4.4**　同一 variance 连续两次回写后 `F3-3-rows` 条数不变。

### Property 15: 其余 10 个 contract golden digest 不变
**Validates: 7.5**

### Property 16: F3-1 受管后 sync 路径 TB 写次数为 0
**Validates: 6.4**　变异：sync 回写里调 `publishToTb` ⇒ 必红。

## Testing Strategy

红判据先行：阶段 0 先打红 P1 / P2 / P4 / P9 / P12。后端 pytest（`$env:PYTHONIOENCODING='utf-8'`，PBT `max_examples=5`）；
前端 vitest（F3 现基线 14 文件 206 passed，任何改动后须复跑）；真栈 Playwright `--workers=1`，fixture
`e2e/fixtures/f3-l2-cases.json`，七态结果枚举沿用 D4 lane。

## 顺带发现（登记，不在本 spec 处理）

1. **FC-11 的工具链根因**影响三个 F 脚本（`fix_f1/f2/f_cycle_prefill_presets.py`）；本 spec 只改 `fix_f_cycle`，
   建议另立一条全局 CI 守卫「`prefill_formula_mapping.json` 任何块的 `cells` 非空且无 `items` 键」，一次兜住整类。
2. `应付票据实质性程序表F3A␠` sheet 名末尾空格 —— 模板治理债，宿主正则 `/(F3A|F3-\d+)/` 恰好不受影响，但任何
   按 sheet 名精确匹配的新代码都会踩（同类：`F2-38至F2-44␠␠` 文件名双空格）。
3. F3 模板**零 definedName** —— 与 F1（40 个含 `#REF!` 残留）对比，F3 更干净，`static_region` 将来若需要须自建锚点。
4. F3-2 DV 只允许「银行承兑汇票,商业承兑汇票」两枚举，而前端 `F3_NOTE_TYPE_OPTIONS` 有 4 项（含供应链票据/其他）、
   `F3_CATEGORY_META` 有 5 类 ⇒ **模板 DV 与前端枚举三方不一致**（2 vs 4 vs 5），受管后 OO 侧下拉选不到供应链/信用证。
   与 B3 同源，归 F3-H5 的降级裁决覆盖，但 DV 本身的扩充须走模板覆盖层。
