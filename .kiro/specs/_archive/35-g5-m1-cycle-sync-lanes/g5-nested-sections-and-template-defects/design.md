# Design Document

## Overview

G5 长期应收款一条 entry 单独成 spec，因为它集中了三件 G 循环独有的难点：
**115 行三段嵌套（12 小计 + 3 合计）** · **两处模板真实金额错误** · **真库唯一被字节数证实的 dual_write**。

GC-1~GC-10 见 `g-cycle-sync-foundation-and-first-canary/design.md`（引用、不复述）。

G5 同时是 G 循环**较干净**的一条：`blocked_by` 只有 `BP-1~4 + BP-6`（无 BP-5/7/8）、definedName 为 0、
主受管表裸 IF 为 0、TB 发布门已接。⇒ 它的难点全在**模板结构与模板缺陷**，不在平台前置。

## 上游锚定

沿用 foundation spec 锚定表。额外：
- **F5 spec 裁决 F5-H2**（F5-7!G31 走覆盖层）+ **F2 spec**（F2-26!J9 走覆盖层）—— 模板缺陷处置的两个先例；
  G5 的两处是第三、第四例（GC-3）
- **F4-9 / F5-1 的「小计相加」族** —— 合计行是 `=X18+X25+X39` 而非 SUM 区间，插行位移规则不同
- **D4-5 `paragraph_block_bidirectional`** —— G5-8 会计政策检查的候选形态
- **`g5StorageContract.ts`**（2,324 B）—— FD-1 的 dual_write 实现

## Architecture

### 接入顺序

```
[模板覆盖层裁决] 三处合计漏加小计 → 修或降级
G5-2 段（一）四子区（R13-17 / R20-24 / R27-31 / R34-38）   ← 首批，验通嵌套声明
  → G5-2 段（二）四子区（含跨段引用 B45=B13）
  → G5-2 段（三）四子区
  → [16384 裁决与 g4-g6 同源] G5-9 转置
G5-3 / G5-5 / G5-6 / G5-7 / G5-10 / G5-11 / G5-12 / G5-8：可行性核
G5-4：FC-6 核　G5-1：后置 spec（B2 缺陷证据在本 spec 交棒）
```

### 声明层结构

```
backend/app/services/workpaper_sync/
  phase5_g5_long_term_receivable.py    ← entry 层 provider
  phase5_g5_02_balance_detail.py       ← 12 个子区声明（裁决 G5-H1 方案①）
  phase5_g5_09_ecl_stage.py            ← 转置 + 16384（与 g4-g6 同源策略）
backend/data/workpaper_sync_contracts/g5.long_term_receivable_detail.json
backend/scripts/gen/generate_phase5_g5_contract.py
```

### 受管区清单（裁决 G5-H1 方案①：一子区一 spec）

| sheet_key | 段 | 子区标题 | 数据行 | 段内小计 | formula_columns |
|---|---|---|---|---|---|
| `g502-s1r1` | 一 原值 | 应收融资租赁款 | R13-17 | R18 | G, J, M |
| `g502-s1r2` | 一 | 应收分期收款销售商品款 | R20-24 | R25 | G, J, M |
| `g502-s1r3` | 一 | 应收分期收款提供劳务款 | R27-31 | R32 | G, J, M |
| `g502-s1r4` | 一 | 其他 | R34-38 | R39 | G, J, M |
| `g502-s2r1`~`s2r4` | 二 未确认融资收益 | 同上四类 | R45-49 / R52-56 / R59-63 / R66-70 | R50/R57/R64/R71 | G, J, M（+`B` 跨段派生） |
| `g502-s3r1`~`s3r4` | 三 | 同上四类（Task 2 逐格补全行号） | R77-81 / R84-88 / R91-95 / R98-102 | R82/R89/R96/R103 | G, J, M |

不受管：三个段标题行（R9/R41/R74）· 12 个小计行 · 3 个合计行（R40/R72/R104）· 两级表头（R10/R11 等）。
🔴 段（三）的行号 Task 2 须逐格补全（本轮只实测到小计位置 R82/R89/R96/R103，数据行区间按段（一）(二)
的 5 行规律推断 —— **推断不得直接写进声明**）。

## Data Models

不新增数据模型。store 形态：`rows` + `id`（uuid），**双写** `remark` 与 `conclusion`（逐字相同）。
12 个子区共享同一个 `store_item_id`（`G5-2-rows`）⇒ 需要**子区内行归属**的判定方式，见裁决 G5-H2。

## 关键裁决

### 裁决 G5-H1：三段 × 四子区 = 12 个 `RowTableSheetSpec`，不改框架层

框架层 `footer_anchor` 是单 footer 模型，表达不了「段内四小计 + 段合计 + 三段并列」。两方案：

| 方案 | 做法 | 代价 | 裁定 |
|---|---|---|---|
| ① | 12 个 `RowTableSheetSpec`，各自 footer 指本子区小计行；段合计/段标题不受管 | 声明变长（12 条），但**零框架层改动** | ✅ 默认 |
| ② | 框架层扩 `footer_anchor` 支持「多小计 + 段合计」 | 改全平台共用件，影响 D/E/F 已验通的 9 家 | 否决 |

方案①与 D1-4（三区）/ F4-7（五区）/ F3-7（三区）同族，只是区数更多（12）。
🔴 判据须断言 12 个受管区**两两不相交**且**不覆盖任何小计/合计/段标题行** —— 区数多时最易出的错是区间重叠。

### 裁决 G5-H2：12 子区共享一个 `store_item_id`，行归属靠子区字段不靠行号

前端 `G5-2-rows` 是**一个** store 键承载全部三段（真库 572 B 单行载荷证实）。
⇒ 12 个受管区的行必须能从 store 行本身判出归属，不能靠 Excel 行号（插行会变）。
裁决：Task 2 **按值实测** `useG5BalanceDetail` 的行接口里承载「段 + 子区」的字段名
（候选：`section` / `category` / `subType` 之类），并用它做区内过滤。
🔴 若实测**没有**这样的字段 ⇒ 说明前端靠数组顺序区分段，那么**12 子区方案不成立**，须改为
「整表一个受管区 + 小计/合计行按 mask 排除」并在 spec 里改裁 —— 不得在无字段时硬套 12 区。

### 裁决 G5-H3：三处漏加小计走模板覆盖层；判据必须构造「只有第三子区有数」的载荷

GC-3 的规则：模板缺陷走覆盖层，FC-5「以模板为权威」只适用于「两边都对、口径不同」。
本例是**纯模板 bug**（段内四个小计只加三个，三段模式一致）⇒ 覆盖层修为含全部四个小计。

🔴 **判据设计的关键**：若用「四个子区都有数」的载荷，修复前后合计都错但差值可能被其他子区掩盖；
必须构造**只有第三个子区（R27-31 / R59-63 / R91-95）有数**的载荷 —— 此时修复前合计恒为 0、
修复后等于该子区小计，差异最大且不可能空转。否则判据会在「碰巧相等」时假绿。

### 裁决 G5-H4：G5-1!B35 越界在本 spec 登记、在后置 spec 修

审定表本体归 `g-cycle-adjudication-sheets-coverage`（GF-H5）。但缺陷证据在本 spec 登记，理由：
同册缺陷不应分散到两份 spec 各查一遍（F 循环的教训：F1-1/F3-1/F4-1 三家口径分歧分散在三份 spec，
最后不得不统一裁决在 F1 需求 7.3）。
⇒ 本 spec 产出：`=B9-B225` 原文 + sheet 仅 87 行 + 求值恒等于 B9 的推论 + 后置 spec 交棒清单条目。

### 裁决 G5-H5：G5-9 的 16384 策略与 `g4-g6` spec **同源**，不各出一套

三张 16384 列表（G4-9 / G5-9 / G6-11）是同一族缺陷。裁决：UUID 放**有效内容列 +1**（不放 `max_col+1`），
与 `g4-g6-shared-workbook-three-entry-lanes` 裁决 G46-H3 完全一致；
判据 SHALL 断言两份 spec 的策略同源（引用同一个常量或同一条规则），**不得**各写一套阈值。

### 裁决 G5-H6：不需要 seed，但须断言载荷非空

真库 `G5-2-rows` 有 572+572 B 真实载荷（且是 dual_write 的唯一字节级证据）⇒ 不交付 seed 脚本。
但判据 SHALL 断言「参与 roundtrip 的行数 > 0 且来自真库」（同 foundation GF-H2）。
🔴 另须断言**两列字节数相等**，把 dual_write 语义锁死 —— 这是全 G 循环唯一能做此断言的 entry。

## Error Handling

| 场景 | 处理 | 依据 |
|---|---|---|
| 12 受管区区间重叠或覆盖小计行 | 判据必红 | G5-H1 |
| 前端无「段+子区」字段却硬套 12 区 | 改裁为「整表一区 + mask 排除」并在 spec 改写 | G5-H2 |
| 漏加小计判据用「四子区都有数」载荷 | 可能碰巧相等 ⇒ 判据必须用「只有第三子区有数」 | G5-H3 |
| 覆盖层未交付就受管 | 走降级②（合计行 HTML-only + 中文提示）+ `upstream_gap` | Req 2.4 |
| 改 `backend/wp_templates/` 字节 | 判据必红（运行时只读 + sha 冻结） | Req 2.3 |
| G5-9 的 16384 策略与 g4-g6 不一致 | 判据必红（须同源） | G5-H5 |
| 只写 remark 不写 conclusion | 与真库旧数据分叉 ⇒ 判据必红 | B5 |
| 用 A 列序号作行身份 | 插行后错位 ⇒ 判据必红 | Req 1.3 |
| 11 处 `writeback` 有绕过发布门的 | 登记 + 立门，本 spec 不改造 | Req 5.1 |

## Correctness Properties

🔴 编号 spec-scoped：`Property N` 读作 `G5-P{N}`。

### Property 1: 12 个受管区两两不相交且不覆盖小计/合计/段标题
**Validates: 1.2**　12 个 `(first_data_row, last_data_row)` 区间两两无交集；
12 个小计行（18/25/32/39 · 50/57/64/71 · 82/89/96/103）、3 个合计行（40/72/104）、
3 个段标题行（9/41/74）均不在任何受管区内。变异：把段合计行纳入某区 ⇒ 必红。

### Property 2: 行归属靠子区字段不靠行号
**Validates: 1.1, 1.2**　store 行含 Task 2 实测到的「段+子区」字段，12 区按该字段过滤；
变异：按数组下标切 12 段 ⇒ 插行后归属错位必红。
🔴 若实测无该字段 ⇒ 本 Property 改为「整表一区 + mask 排除」形态并在 design 改裁（G5-H2）。

### Property 3: 行身份用 `id` 而非 A 列序号
**Validates: 1.3**　`row_identity_key == "id"`（`generated_uuid`）；变异用 A 列序号 ⇒ 插行错位必红。

### Property 4: 跨段派生列不得 editable
**Validates: 1.4**　段（二）的 `B45=B13` 所在列 `mode=formula`。变异标 editable ⇒ 必红。

### Property 5: payload 双写且两列字节相等
**Validates: 1.5**　roundtrip 后 `remark` 与 `conclusion` 字节数相等（真库现状 572+572 已证实）。
变异：只写 `remark` ⇒ 两列分叉必红。

### Property 6: 三处漏加小计修复后 OO 与 HTML 合计相等（判据用「只有第三子区有数」载荷）
**Validates: 2.1**　🔴 构造仅 R27-31（及 R59-63 / R91-95）有数的载荷 ⇒ 修复前合计恒 0、修复后等于该子区小计；
修复后三个合计的 OO 求值 == HTML 计算值。变异：用四子区都有数的载荷 ⇒ 差异可能为 0，判据空转必红。

### Property 7: 不改权威模板字节
**Validates: 2.3**　`G5 长期应收款.xlsx` 的 sha256 == `c59bba69789eba3f…`（覆盖发生在覆盖层，不改源文件）。

### Property 8: G5-1!B35 缺陷已登记并交棒
**Validates: 2.2**　证据含 `=B9-B225` 原文 + sheet `max_row == 87` + 「恒等于 B9」推论；
后置 spec 交棒清单含该条目。变异：把该缺陷在本 spec 直接修 ⇒ 越界到后置 spec 的作业面，必红。

### Property 9: 其余 sheet 的可行性核结论完整
**Validates: 3.1, 3.2, 3.3, 3.4**　G5-3/5/6/7/8/10/11/12 + G5-4 各有形态判定与证据；
真库有载荷的两张（G5-3 / G5-5）有接入可行性结论；`g5NoteSectionMap` 的披露 sheet 名不回归。

### Property 10: G5-9 用 TransposedSheetSpec 且 16384 策略与 g4-g6 同源
**Validates: 4.1, 4.2, 4.3**　实体列与三块锚行**逐格实测**（不照抄 G4-9 行号）；
UUID 列 == 有效内容列 + 1，且与 `g4-g6` spec 引用同一条规则。
变异：各写一套阈值 ⇒ 必红；`TransposedSheetSpec` 未入 HEAD 时须有 HTML-only 登记。

### Property 11: TB 红线 + 11 处 writeback 已核
**Validates: 5.1, 5.2**　sync 路径 TB 写次数 0；`publishToTb`（科目 1531、余额口径）唯一入口；
11 处 `writeback` 逐处有「已收敛 / 绕过门（已立门）」结论。变异：sync 回写里调 `publishToTb` ⇒ 必红。

### Property 12: G5 册挂中性化
**Validates: 5.3**　`StoreMergePlan` 带 `oo_crash_neutralization_fn`；
🔴 证据须写明「122 格裸 IF 全在 `审定表G5-1`、主受管表 G5-2 零命中，但中性化是 per-file 故仍挂」。

### Property 13: 零回归现算 + 验收用真实载荷
**Validates: 5.4, 5.5**　非 G5 的 contract golden digest 逐项不变（不断言集合大小）；
roundtrip 行数 > 0 且来自真库。变异：允许空载荷通过 ⇒ 假绿必红。

## Testing Strategy

红判据先行：阶段 0 先打红 P1 / P6 / P10（12 区不相交 / 漏加小计 / 16384）。
后端 pytest（`$env:PYTHONIOENCODING='utf-8'`，PBT `max_examples=5`）；前端 vitest；
真栈 Playwright `--workers=1`，fixture `e2e/fixtures/g5-l2-cases.json`。
🔴 G5 真库有载荷 ⇒ **不 seed**，但先断言载荷非空 + 两列字节相等（P5 / P13）。
🔴 P6 的载荷构造是本 spec 最易写空的判据，须在 Task 里显式写明「只有第三子区有数」。

## 顺带发现（登记，不在本 spec 处理）

1. **G5 是 G 循环真库载荷最多的 entry**（8 行 / 12,952 + 2,844 B），且披露键 `G5-note-listed-rows`(5,580 B)
   / `G5-note-soe-rows`(4,528 B) 是两个最大单键 ⇒ 若将来接披露 sheet，G5 是性能基线的首选样本。
2. **`useG5Adjudication.ts` 的 `writeback` 出现 11 次是 G 循环最多**（其次 G10 的 12 次、G3 的 10 次）⇒
   建议 `tb-writeback-explicit-publish-gate` 复查这三家的收敛完整性（本 spec 只核 G5）。
3. **段（二）的 `B45=B13` 是跨段同行引用**（债务人名称从段一带到段二）⇒ 若段一插行，段二的对应引用
   是否随之位移取决于 Excel 的相对引用行为；建议 Task 实施时把「段一插行 → 段二 B 列仍指同一债务人」
   写成显式 e2e 用例（本 spec 的 P4 只锁「不得 editable」，不锁位移正确性）。
