# Design Document

## Overview

F4 应付账款从 legacy 假双向接成真双向：canary 取 F4-6（关联方，与 F1-6/F3-6 三家同型），再扩到 F4-5 → F4-8（双区）
→ F4-7（**五区**）→ F4-2（明细 + nested 账龄 ×2）→ [F4-9 容量裁决] → F4-1（审定表两区）；F4-3 / F4-4 只做可行性核。

F4 是四个 F spec 里**工程阻塞最少**的一个：无 FC-10 命中（红基线 B6，百分比格列全是公式列）、无模板公式缺陷、
BP-7 只有 F4-1 的 `custom-${index}` 且有 `defaults[index]` 兜底、明细表前端已主动对齐模板（B8）。
主要难点是**规模**（五区 + 双区 + 两区审定表 = 9 个受管区）与**两处容量/口径裁决**（F4-9 分组、F4-1 取数）。

F 循环共同裁决 FC-1~FC-13 见 `f1-sync-coverage-and-first-canary/design.md`。

## 上游锚定

沿用 F1 spec 上游锚定表。额外：
- **F1 spec**（F4 与 F1 借贷镜像，几何近乎同构）—— F4-1/F4-2/F4-5/F4-6 的裁决直接对照 F1-1/F1-2/F1-5/F1-6
- **F3 spec** —— FC-11 工具链根因修复由它负责，本 spec 依赖其完成
- `phase5_d3_07_voucher_check.py`（双区）与 `phase5_d4_*`（多区同 sheet）—— F4-7 五区 / F4-8 双区的兄弟 Table ref 先例

## Architecture

### 接入顺序（形态驱动）

```
F4-6 关联方（canary：单级表头 / 1 公式列 / 零跨 sheet / 无 FC-10）
  → F4-5 长期挂账（数据区零公式；验证「第二张复用框架层零改动」+ FC-7 派生列核）
  → F4-8 双区（兄弟 Table ref 首验）
  → F4-7 五区（同 sheet 最多区数；含除零公式列）
  → F4-2 明细（两级表头 + nested 账龄 ×2；前端已对齐模板）
  → [F4-9 容量裁决] F4-9 分组表（限额内受管）
  → [F4-1 口径评估三家统一] F4-1 审定表两区
F4-3 / F4-4：可行性核（FC-6 / 非行表两区）
```

### 声明层结构

```
backend/app/services/workpaper_sync/
  phase5_f4_accounts_payable.py     ← entry 层 provider
  phase5_f4_06_related_party.py     ← canary
  phase5_f4_05_long_outstanding.py
  phase5_f4_08_voucher_check.py     ← 两个 spec（debit / credit）
  phase5_f4_07_unrecorded.py        ← 五个 spec（payment-window / estimated-inbound / unprocessed-invoice /
                                        subsequent-payment / subsequent-increase）
  phase5_f4_02_detail.py
  phase5_f4_09_supplier_financing.py
  phase5_f4_01_adjudication.py      ← 两个 spec（nature / aging），RowTableSheetSpec 稳定 rowKey
backend/data/workpaper_sync_contracts/f4.accounts_payable_detail.json
backend/scripts/gen/generate_phase5_f4_contract.py
```

sheet 层文件只含常量与 spec 实例（无 `def` / 无 `class`）。

### 受管区清单（逐格实测几何，共 9 区 + 1 待裁决）

| sheet_key | managed_sheet | store_item_id | 表头 | 数据 | footer | UUID | formula_columns |
|---|---|---|---|---|---|---|---|
| `f46-managed` | 关联方及交易检查表F4-6 | `F4-6-rows` | R6 | R7-11 | R12「合计」 | M | F |
| `f45-managed` | 长期挂账检查表F4-5 | `F4-5-rows` | R8 | R9-14 | R15「合计」 | L | （无；I 列待 FC-7 核） |
| `f48-debit` | 应付账款检查表F4-8 | `F4-8-debit-rows` | R15/R16 | R17-37 | R38「合计」 | S | （Task 2 实测） |
| `f48-credit` | 同上 | `F4-8-credit-rows` | R40/R41 | R42-57 | R58「合计」 | S | （Task 2 实测） |
| `f47-payment-window` | 未入账检查表F4-7 | `F4-7-payment-window-rows` | R14（单级） | R15-24 | R25「合计」 | L | F, G, I |
| `f47-estimated-inbound` | 同上 | `F4-7-estimated-inbound-rows` | R27/R28 | R29-44 | R45「合计」 | L | F |
| `f47-unprocessed-invoice` | 同上 | `F4-7-unprocessed-invoice-rows` | R47/R48 | R49-59 | R60「合计」 | L | （无） |
| `f47-subsequent-payment` | 同上 | `F4-7-subsequent-payment-rows` | R62/R63 | R64-75 | R76「合计」 | L | （无） |
| `f47-subsequent-increase` | 同上 | `F4-7-subsequent-increase-rows` | R78/R79 | R80-91 | R92「合计」 | L | （无） |
| `f42-managed` | 明细表F4-2 | `F4-2-rows` | R9/R10 | R11-31 | R32「合计」 | AB | H, K, M, T |
| `f41-nature` | 审定表F4-1 | `F4-1-adj-nature-rows` | R6/R7 | R8-12 | R13「合计」 | M | E,F,G,H,I,J,K |
| `f41-aging` | 同上 | `F4-1-adj-aging-rows` | R15/R16 | R17-21 | R22「合计」 | M | E,F,G,I,J,K |
| `f49-managed` | 供应商融资检查表F4-9 | `F4-9-rows` | R11 | R12-25（三组） | R27「合计」 | P | （小计行不受管） |

🔴 F4-1 两区的 `formula_columns` **不同**（性质区 F/G/H 是 SUMIF、账龄区 F/I 是直引 `明细表F4-2!N32`/`!U32`、G 是倒挤）
⇒ 两区各自实测，不得共用（需求 7.3）。F4-1 空槽行（R21 等）若公式集合与 R17-20 不同，按 **F3-H4** 同款处置（拆 spec）。

## Data Models

不新增数据模型。store 形态：`rows`（11 个受管区）、稳定 `rowKey` rows（F4-1 两区）、dict + 覆盖数组（F4-4，不受管）。
无 per-cell、无 `static_region`（F4-4 区①是候选，核后再定）。

## 关键裁决

### 裁决 F4-H1：canary 选 F4-6，与 F1-6/F3-6 共用同一形态验证

三家同型（单级表头 + 期末余额 1 个公式列 + footer 合计 + `rowId` + 零跨 sheet + 无 FC-10）。F4-6 的模板公式
`F=C+E-D`（期初 + 贷方 − 借方，负债类）与 F1-6 的 `F=C+D-E`（资产类借方在前）互为镜像 ⇒ 声明层写法可复用、
公式模板需按借贷方向各自实测。**不得**因为「F1-6 已验过」就跳过 F4-6 的逐格实测（FC-4）。

### 裁决 F4-H2：`F4A` 幻影码撞真码，用「三条隔离判据」而非改码

manifest 的 `wp_code_patterns=["F4A"]` 与 `wp_code_overrides.json:549` 的程序表路由码 `F4A` **字面相同**。
不改任何一侧（改 manifest 要动生成器、改 overrides 会断程序表路由），而是用三条判据钉死隔离（需求 1.3）：
①`_index.json` 无 `F4A`（finder 零命中，按值实测）②`assert_no_implicit_template_fallback` 对 `F4A` 通过
③provisioner 用裁决真码 `["F4"]`。这是 D3P/D4O/D5R 同款处置 + F4 特有的「撞码」加强判据。

### 裁决 F4-H3：F4-7 五区各自声明 field_specs，不抽公共元组

五区列集与表头层级都不同（区①单级 11 列、区②~⑤两级 10~11 列，语义各异：入库单 / 购货发票 / 银行付款凭单 / 记账凭证）。
虽然区③④⑤的列数接近，但语义不同（「购货发票日期/编号」vs「银行付款凭单日期/编号」）⇒ 抽公共元组会让表头文本与
`header_source_ref` 错配。裁决：**五份独立 `field_specs`**；共享的只有 footer marker 与 UUID 列常量。

### 裁决 F4-H4：F4-9 限额受管，超限降级（不改模板合计公式）

模板合计 `F27=F26+F21+F16` 是**三个小计相加**而非 SUM 区间 ⇒ 插入第 4 组后合计不会纳入，这是模板的结构性限制。
裁决同 F3-H5：限额内（≤3 组、各组 ≤4 行）受管，超限整表降级 legacy + 中文提示。否决「改模板合计为 SUM(F12:F26)」——
那会把小计行也计入（重复计数），需要重构模板结构，超出本 spec 范围。

### 裁决 F4-H5：F4-4 两区不进行表引擎

三元组实证：无 `-rows` 键（只有 `F4-4-turnover` dict 与 `F4-4-creditor-overrides` 覆盖数组）、无 addRow/removeRow。
区①（周转率 12 固定行、`inputs: Record<key,number>`）候选 `static_region`（绝对坐标直写，绕开位移链）；
区②（前十名，模板写死 10 行、前端派生自 F4-2 + 只存 `reason`）是**派生只读 + 局部覆盖**，行数据不属本表所有 ⇒
受管它等于把派生值物化进 Excel 后再读回，会与 F4-2 形成双源。默认两区都 HTML-only，核后如确有需要再单独立 task。

### 裁决 F4-H6：三家审定表口径一次统一裁决

F1-1 / F3-1 / F4-1 的口径分歧同型（模板按明细汇总 vs 前端手填 AJE/RJE + 以审定口径作未审数）。三份 spec 各裁一次
会出现「F1 改了、F3 没改」的不一致。裁决：**影响评估与方向裁决在 F1 spec 需求 7.3 一次做完并覆盖三家**，
各 spec 的审定表任务只负责按统一结论落地自己那张。本 spec 需求 6.3 明写该依赖。

## Error Handling

| 场景 | 处理 | 依据 |
|---|---|---|
| 幻影码被当业务码用 | 三条隔离判据必红 | F4-H2 |
| F4-7 区① E=0 除零 | extract 记 `type_normalization_failure` + 保留原值 + 不入 store（PROTECTED_MODES） | 红基线 B7 |
| F4-9 组数 >3 或组内 >4 | 整表降级 legacy + 中文原因 | F4-H4 |
| F4-1 行缺 `rowKey` | 重铸并回写；不得残留 `custom-<下标>` | 需求 6.2 |
| legacy 别名键被声明为受管 | 一区两 binding ⇒ 判据必红 | 需求 2.3 |
| 账龄口径非 THREE_YEAR | 受管关闭 + 中文原因 | 需求 3.3 |
| 发布链第③环缺供给 | 如实 `upstream_gap` | BP-61-1 |
| sync 路径触发 TB 写 | 判据必红 + CI 守卫 | FC-9 |

## Correctness Properties

### Property 1: canary 打通后 migration_state 与 legacy_reasons 正确变更
**Validates: 1.5**　变异：跳过发布链任一环 ⇒ 状态不变。

### Property 2: `F4A` 幻影码与真实程序表码隔离（三条子判据）
**Validates: 1.3**　①`_index.json` 无 `F4A` ②`assert_no_implicit_template_fallback('F4A')` 通过
③provisioner JOIN `wp_index` 用 `["F4"]`。变异：用 `F4A` 查 finder / wp_index ⇒ 必红。

### Property 3: `store_item_id` 取主键不取 legacy 别名
**Validates: 2.2, 2.3**　变异 ①`F4-7-estimated-inbound-rows → F4-7-receipt` ②`F4-9-rows → F4-9-factoring-rows`
⇒ 投影恒空必红；另断言受管区总数 == 9（+F4-9 裁决后 10），别名不产生额外 binding。

### Property 4: `binding_kind` / `row_identity_key` 取自三元组
**Validates: 2.1**　F4-1 两区 `rowKey`、其余 `rowId`、F4-4 两区不在受管清单。
变异：把 F4-4 声明为行表 ⇒ 无 `-rows` 键 ⇒ 投影恒空必红。

### Property 5: F4-7 五区列集互不串用 + 兄弟 Table 位移
**Validates: 4.3, 4.5**　五区 `field_specs` 两两不等；区①插 5 行后区②~⑤ footer SUM 区间随位移、数据不变。

### Property 6: F4-7 区① 除零行为符合实测语义
**Validates: 4.4**　构造 E=0 行 ⇒ ①extract 不抛 ②异常 `type_normalization_failure` ③store 无 `#DIV/0!`。
变异：把 G 列标 `editable` ⇒ 错误值进入 store，必红。

### Property 7: F4-2 双模式派生列等价（FC-5 正面样本）
**Validates: 3.1**　hypothesis（`max_examples=5`）：前端 `computeF4DetailRow` 的 H/K/M/T 等于模板公式求值
（前端已对齐，预期**直接绿** —— 作为 F1-2 修复的参照基线）。

### Property 8: 账龄非 THREE_YEAR 时受管关闭、第 5 段起金额不丢
**Validates: 3.3**

### Property 9: F4-9 限额内受管、超限降级且不丢数据
**Validates: 5.1, 5.2, 5.3**　构造 4 组载荷 ⇒ 受管判定为关 + legacy 读到全 4 组；限额内组小计行不受管。

### Property 10: F4-4 两区不进行表引擎
**Validates: 5.4**　断言 F4-4 不在 `all_store_item_ids()`；证据含 `static_region` / 派生只读的核结论。

### Property 11: F4-1 行身份重铸后无 `custom-` 前缀
**Validates: 6.2**　变异：恢复 `custom-${index}` ⇒ 旧载荷行序变化后身份错位，必红。

### Property 12: F4-1 两区 formula_columns 各自实测、不互串
**Validates: 6.1, 7.3**　变异：把性质区列集套到账龄区 ⇒ 账龄区 H 列（重分类调整，模板无公式）被误标 formula，必红。

### Property 13: F4-1 取数口径按三家统一裁决落地
**Validates: 6.3**　依赖 F1 spec 的统一评估结论；本 spec 只断言 F4-1 与结论一致。

### Property 14: F4-1 受管后 sync 路径 TB 写次数为 0
**Validates: 6.4**　变异：sync 回写里调 `publishToTb` ⇒ 必红。

### Property 15: FC-11 数据侧 —— F4 三块只用 `cells`、无重复块
**Validates: 7.2**　①F4 块 `items` 键数为 0 ②`附注披露信息（国企）`（全角）块不存在 ③`test_sheet_exists_in_source_xlsx[F4]` 绿。

### Property 16: FC-10 在 F4 不命中（结论须有证据）
**Validates: 7.6**　逐列断言：模板所有百分比格式列（F4-1 K / F4-4 E / F4-8 G）均为 `mode=formula`。
变异：把任一列标 `editable` ⇒ 命中 FC-10 风险，必红。

### Property 17: 其余 10 个 contract golden digest 不变
**Validates: 7.4**

### Property 18: 零写入键登记而不误接
**Validates: 2.4**　`F4-8-debit-note` / `-credit-note` 不在 `all_store_item_ids()`，且证据记录其为兼容回退。

## Testing Strategy

红判据先行：阶段 0 先打红 P1 / P2 / P3 / P15 / P16。后端 pytest（`$env:PYTHONIOENCODING='utf-8'`，PBT `max_examples=5`）；
前端 vitest；真栈 Playwright `--workers=1`，fixture `e2e/fixtures/f4-l2-cases.json`（真库 `F4-2-rows` 4 行可作真数据样本）。
F4-7 五区 + F4-8 双区共 7 个同 sheet 区 ⇒ 兄弟 Table ref 位移的 e2e 用例须覆盖「在最靠前的区插行」与「在最靠后的区插行」两向。

## 顺带发现（登记，不在本 spec 处理）

1. **F4-2 前端已主动对齐模板**（`useF4Detail.ts:301` 注释 + 代码）是 F 循环唯一正面样本 ⇒ 建议 F1-2 修复
   （F1 红基线 B1）直接照它的写法与注释风格。
2. `修订说明`（hidden，13r×C）与 F1 的 `预付账款实质性程序表G1A-修订前`（hidden，96r×O）同属模板治理债 ——
   F 循环五册中共 4 张 hidden 残留（F1 一张、F2 三张：`修订说明` / `同行业存货跌价计提情况G2-9-3-删除` / 计价册六张）。
3. F4-9 的 7 个 legacy 键与 F4-7 的 6 个 legacy 别名共 13 个兼容键 —— 建议 F 循环收口后统一做一次「legacy 键退役」
   （需数据迁移，另立 spec）。
4. F4-8 两个零写入读键（`F4-8-debit-note` / `-credit-note`）与 F5 读 D4 零写入键（`D4-1-adj-main-rows`）同型 ⇒
   建议加一条全局 CI 守卫「store 键读方必有写方（或显式登记为兼容回退）」。
