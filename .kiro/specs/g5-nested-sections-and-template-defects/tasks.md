# Implementation Plan

## Overview

**spec**：`g5-nested-sections-and-template-defects`　**创建**：2026-09-26　**状态**：0/14（Task 0~13），Design-First 未实施
**上游**：**`g-cycle-sync-foundation-and-first-canary`（GC-1~GC-10，硬前置）** · FC-1~FC-13 ·
F5 spec 裁决 F5-H2 + F2 spec（模板缺陷走覆盖层的两个先例）· D4-29 转置引擎 ·
`g4-g6-shared-workbook-three-entry-lanes`（16384 策略须同源）

`[ ]*` = 依赖外部供给（BP-1~BP-4 / 模板覆盖层 / OO 真栈）。

🔴 **G5 的难点全在模板结构与模板缺陷，不在平台前置**：`blocked_by` 只有 `BP-1~4 + BP-6`
（无 BP-5/7/8）、definedName 0、主受管表裸 IF 0、TB 发布门已接。

## Tasks

### 阶段 0：前置门 + 几何补测 + 红判据

- [ ] 0. 前置依赖核查（`git show HEAD:`）
  - `RowTableSheetSpec`（12 子区依赖）· `phase5_transposed_sheet.TransposedSheetSpec`（G5-9 依赖）·
    `StoreMergePlan.oo_crash_neutralization_fn`（GC-2）· **模板覆盖层交付状态**（Req 2 的默认①依赖它）
  - foundation 的 GC-1~GC-10 交付状态；`g4-g6` spec 的 16384 裁决是否已定（Req 4.2 须同源）
  - 证据 `evidence/task0-prerequisites.md`
  - _Requirements: 1.2, 2.1, 4.1, 4.2, 5.3_

- [ ] 1. slice 复核 + wp_code 裁决条目
  - 核 `blocked_by == ["BP-1","BP-2","BP-3","BP-4","BP-6"]`（逐元素，🔴 断言**不含** BP-5/7/8）
  - `wp_code_adjudication` 的 G5 条目（foundation Task 1 已建）补 `store_payload_evidence`：
    真库 8 行 / remark 12,952 B + conclusion 2,844 B（G 循环最多），逐键字节见 requirements
  - _Requirements: 1.1_

- [ ] 2. 🔴 几何补测 + 段/子区字段按值定位（本 spec 最承重的一步）
  - **段（三）行号逐格补全**：本轮只实测到小计位置 R82/R89/R96/R103，数据行区间按 5 行规律**推断**为
    R77-81/R84-88/R91-95/R98-102 ⇒ **推断不得写进声明**，须逐格确认
  - 🔴 **按值实测 `useG5BalanceDetail` 行接口里承载「段 + 子区」的字段名**（裁决 G5-H2）：
    有字段 ⇒ 12 区方案成立；**无字段 ⇒ 改裁为「整表一区 + mask 排除小计/合计/段标题」并改写 design**
  - G5-9 实体列与三块锚行逐格实测（**不得照抄 G4-9 行号**）+ 有效内容列数
  - 段（二）`B45=B13` 跨段引用逐格核；A 列序号 1~5 确认不是行身份
  - 其余 8 张 sheet 的形态判定（含 G5-8 的 `paragraph_block_bidirectional` 候选）
  - 证据 `evidence/task2-geometry-and-section-field.md`
  - _Requirements: 1.1, 1.3, 1.4, 3.1, 3.2, 4.1_

- [ ] 3. G5-P1 / P2 / P3 红判据（12 区结构，现状必红）
  - P1 区间两两不相交 + 不覆盖 12 小计 / 3 合计 / 3 段标题；变异「把段合计纳入某区」
  - P2 行归属按子区字段（依赖 Task 2 结论）；变异「按数组下标切 12 段」
  - P3 行身份 `id`；变异「用 A 列序号」
  - _Requirements: 1.1, 1.2, 1.3_

- [ ] 4. 🔴 G5-P6 红判据（三处漏加小计）—— **载荷必须是「只有第三子区有数」**
  - 现算三处合计公式原文（`=D18+D25+D39` / `=D50+D57+D71` / R104），断言各漏一个小计
  - 构造仅 R27-31（段一第三子区）有数的载荷 ⇒ 断言**修复前合计恒 0**；同法构造段二 R59-63、段三 R91-95
  - 🔴 反向自检变异：把载荷改成「四子区都有数」⇒ 差异可能为 0 ⇒ 该变异本身必须让判据打红（证明判据不空转）
  - _Requirements: 2.1_

- [ ] 5. G5-P5 / P10 / P13 红判据（双写 / 16384 同源 / 零回归现算）
  - P5 现算真库 `G5-2-rows` remark 与 conclusion 字节相等（572+572）；变异「只写 remark」
  - P10 变异「16384 策略与 g4-g6 各写一套阈值」必红
  - P13 零回归**现算逐项**（不断言集合大小，GC-10）
  - _Requirements: 1.5, 4.2, 5.4_

### 阶段 1：模板缺陷处置

- [ ]* 6. 三处漏加小计处置（裁决 G5-H3，FC-5 第三个例外）
  - 默认①：经**模板覆盖层**把三个合计行改为含全部四小计（`=X18+X25+X32+X39` / `=X50+X57+X64+X71` /
    段三对应式），D~R 共 15 列 × 3 段 = 45 格
  - 备选②（覆盖层缺位）：三个合计行整行 HTML-only + UI 中文提示「合计行模板公式存在已知缺陷，已由系统重算」
  - P6 转绿 + P7（`G5 长期应收款.xlsx` sha256 仍为 `c59bba69789eba3f…`，**不改源文件字节**）
  - _Requirements: 2.1, 2.3, 2.4_

- [ ] 7. G5-1!B35 越界缺陷登记 + 交棒（裁决 G5-H4，本 spec **不修**）
  - 证据：`=B9-B225` 原文 + `审定表G5-1` `max_row == 87` + 「B225 空白越界、求值恒 0 ⇒ B35 恒等于 B9」推论
  - 写入 `g-cycle-adjudication-sheets-coverage` 的交棒清单；P8（变异「在本 spec 直接修」⇒ 越界必红）
  - _Requirements: 2.2_

### 阶段 2：主受管表 G5-2 三段接入

- [ ] 8. `phase5_g5_long_term_receivable.py` entry 层从零建
  - `ENTRY_ID="xlsx/gt-g5-long-term-receivable"` / `ADAPTER_ID="g5.long_term_receivable_detail"` /
    `WP_CODES={"G5L"}`（幻影码）/ `TEMPLATE_RELATIVE_PATH="G/G5 长期应收款.xlsx"` /
    `TEMPLATE_SHA256="c59bba69789eba3f…"`（Task 1 逐字补全 64 位）
  - `assert_entry_selectable` 照 D3 同签名 + `build_registration` 照 `phase5_d3_prepaid_receipts.py:830` + 真构造判据
  - 🔴 `StoreMergePlan` 带 `oo_crash_neutralization_fn`（P12；证据须写明「122 格全在 G5-1、主表零命中，
    但中性化是 per-file 故仍挂」）；HTTP 客户端 `api`（FD-2）
  - _Requirements: 5.3_

- [ ] 9. `phase5_g5_02_balance_detail.py` 段（一）四子区（首批，验通嵌套声明）
  - `g502-s1r1`~`s1r4`：R13-17 / R20-24 / R27-31 / R34-38，各自 footer 指本子区小计（R18/R25/R32/R39）
  - 共享 `store_item_id="G5-2-rows"`；行身份 `id`(uuid)；`formula_columns=("G","J","M")`
    （`G=D+E+F` · `J=D+H-I` · `M=J+K+L`）；表头 R10/R11（R11 是 N-R 账龄段）
  - payload **双写**（`remark` + `conclusion` 逐字相同）；P1 / P2 / P3 / P5 转绿
  - _Requirements: 1.1, 1.2, 1.3, 1.5_

- [ ] 10. 段（二）四子区 + 段（三）四子区
  - 段（二）R45-49 / R52-56 / R59-63 / R66-70，小计 R50/R57/R64/R71；🔴 `B45=B13` 跨段派生列
    判 `mode=formula` 不得 editable（P4）
  - 段（三）行号取 Task 2 逐格补测结果（**不用推断值**），小计 R82/R89/R96/R103
  - _Requirements: 1.2, 1.4_

- [ ]* 11. G5-9 转置声明（16384 策略与 g4-g6 同源）
  - `phase5_g5_09_ecl_stage.py`：`TransposedSheetSpec`，实体列/三块锚行取 Task 2 实测值
  - 🔴 UUID 放**有效内容列 +1**，与 `g4-g6` 裁决 G46-H3 **引用同一条规则**（P10）
  - `TransposedSheetSpec` 未入 HEAD ⇒ 登记 HTML-only + 解锁条件
  - _Requirements: 4.1, 4.2, 4.3_

### 阶段 3：发布链 + 核 + 收口

- [ ]* 12. 契约发布链五环 + 六登记点 + 宿主接桥 + 真栈验收（**不 seed**）
  - `generate_phase5_g5_contract.py --apply` → `g5.long_term_receivable_detail.json` → 五环
  - `GtG5LongTermReceivable.vue` 引入 `useWorkpaperSyncBridge` + `WorkpaperSyncEditorHost`，保留 legacy(4) + notice(3)
  - `e2e/fixtures/g5-l2-cases.json`，`--workers=1`；🔴 真库已有 572+572 B ⇒ **不交付 seed**，
    但先断言「roundtrip 行数 > 0 且来自真库」+「两列字节相等」（P5 / P13）
  - _Requirements: 5.4, 5.5_

- [ ] 13. 其余 sheet 可行性核 + TB 红线 + 收口
  - G5-3 / G5-5 / G5-6 / G5-7 / G5-10 / G5-11 / G5-12 / G5-8 逐张形态判定（**不改生产代码**）；
    真库有载荷的 G5-3(254+254) / G5-5(798+798) 优先给接入可行性结论；G5-4 照 FC-6；
    `g5NoteSectionMap` 披露 sheet 名不回归（P9）
  - 🔴 TB 红线 P11：逐处核 `useG5Adjudication.ts` 的 **11 处 `writeback`**（G 循环最多）是否全收敛在
    `publishToTb`(4 处) 内部；发现绕过门的 ⇒ 登记 + 立门，**本 spec 不改造**；
    sync 路径 TB 写次数 0（科目 **1531** 余额口径）
  - 全部变异复跑 + 整册 materialize/verify
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 5.1, 5.2_

## Task Dependency Graph

```json
{
  "waves": [
    { "wave": 0, "tasks": ["0"], "rationale": "前置门：模板覆盖层交付状态决定 Task 6 走①还是②；TransposedSheetSpec 决定 Task 11；g4-g6 的 16384 裁决须已定（Req 4.2 同源）" },
    { "wave": 1, "tasks": ["1", "2"], "rationale": "🔴 Task 2 最承重：段（三）行号逐格补全 + 段/子区字段按值定位（无字段则 12 区方案不成立、须改裁）" },
    { "wave": 2, "tasks": ["3", "4", "5"], "rationale": "三组红判据并行；Task 4 的载荷构造是本 spec 最易空转的判据" },
    { "wave": 3, "tasks": ["6", "7"], "rationale": "两处模板缺陷处置：三处漏加小计走覆盖层（修）· G5-1!B35 登记交棒（不修）" },
    { "wave": 4, "tasks": ["8"], "rationale": "entry 层 provider（含 per-file 中性化声明）" },
    { "wave": 5, "tasks": ["9"], "rationale": "段（一）四子区首批，验通嵌套声明" },
    { "wave": 6, "tasks": ["10", "11"], "rationale": "段（二）(三) 八子区 与 G5-9 转置互不依赖" },
    { "wave": 7, "tasks": ["12"], "rationale": "发布链 + 接桥 + 真栈（不 seed 但先断言载荷非空与两列字节相等）" },
    { "wave": 8, "tasks": ["13"], "rationale": "其余 8 张核 + TB 红线 11 处 writeback 核 + 收口" }
  ],
  "blocking": {
    "0": "模板覆盖层未交付 ⇒ Task 6 只能走备选②（三个合计行 HTML-only）；TransposedSheetSpec 未入 HEAD ⇒ Task 11 只能登记 HTML-only；g4-g6 的 16384 裁决未定 ⇒ Req 4.2 的同源断言无对照",
    "2": "🔴 段/子区字段未定位 ⇒ 12 区方案成立性未知，Task 9/10 不得开工；段（三）行号未逐格补全 ⇒ 不得用推断值写声明",
    "4": "判据载荷若不是「只有第三子区有数」⇒ 修复前后差异可能为 0，Task 6 的验收会空转",
    "6": "三处漏加小计未处置 ⇒ 受管后 OO 侧合计行仍错数（客户在第三子区填数时少算全额）",
    "12": "published representation / approved bundle 供给（BP-1~BP-3）⇒ adapter 注册与真栈验收阻塞",
    "13": "11 处 writeback 未核 ⇒ 可能存在绕过显式发布门的第二条 TB 写入路径（FC-9 红线）"
  }
}
```

## Notes

- 🔴 **Task 2 是本 spec 的成立性前提**：12 子区方案依赖前端行接口里有「段 + 子区」字段。
  若实测没有（前端靠数组顺序区分段）⇒ 12 区方案**不成立**，须改裁为「整表一区 + mask 排除」并改写 design
  （裁决 G5-H2 已写明这条退路，不是事后补救）。
- 🔴 **三处漏加小计的判据必须用「只有第三子区有数」的载荷**（裁决 G5-H3）。用「四子区都有数」时
  修复前后合计差异可能为 0 ⇒ 判据空转假绿。Task 4 已把反向自检变异写成显式子项。
- 🔴 **G5-2 的三处漏加小计是三段同模式**（都漏第三个子区）⇒ 修一处的同时必须修三处，
  且判据三段各一条（不得只验段一）。
- 🔴 **G5 是全 G 循环唯一能对 dual_write 做字节级断言的 entry**（真库五个键 remark 与 conclusion 字节完全相等）
  ⇒ P5 的价值超出本 spec，是 FD-1 `dual_write` 形态的唯一实证锚点。
- 🔴 **G5-9 的 16384 策略必须与 `g4-g6` spec 同源**（引用同一条规则，不各写阈值）——
  三张表是同族缺陷，两份 spec 各出一套会在将来第四张出现时分叉。
- 🔴 **G5-1!B35 在本 spec 登记、在后置 spec 修**：同册缺陷不分散到两份 spec 各查一遍
  （F 循环三家审定表口径分歧分散在三份 spec、最后不得不统一裁决在 F1 需求 7.3 的教训）。
