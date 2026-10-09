# Requirements Document

## Introduction

本 spec 覆盖 **G5 长期应收款**一条 entry。它单独成 spec 的理由不是规模，而是三件**只在 G5 出现**的事：
① 主受管表 `余额明细表G5-2` 是 **115 行 / 三段 × 每段四子区 / 12 个小计 + 3 个合计**的嵌套结构，
G 循环最深；② 该册带**两处模板真实金额错误**（FC-5 的第三、第四个例外）；
③ 它是 FD-1 `dual_write` 形态在真库里**唯一被字节数证实**的 entry（remark 与 conclusion 字节完全相等）。

上游：**`g-cycle-sync-foundation-and-first-canary`** 的 **GC-1 ~ GC-10**（引用、不复述）+ FC-1~FC-13
（FC-3 / FC-8 / FC-11 在 G 不成立或不命中，见 foundation design §FC 适用性重裁）。

🔴 **Property 编号 spec-scoped**：本 spec `Property N` 读作 **`G5-P{N}`**。

### G5 现状实测（slice + manifest + 真库，2026-09-26）

```
entry_id            xlsx/gt-g5-long-term-receivable
host_path           audit-platform/frontend/src/components/workpaper/GtG5LongTermReceivable.vue
wp_code_pattern     G5L        真码 G5        科目 1531（余额口径）
capability          null       capability_target  bidirectional
migration_state     legacy_fake_bidirectional      adapter_id  None
mount_count         2          html_counterpart_verdict  exists
blocked_by          ["BP-1","BP-2","BP-3","BP-4","BP-6"]      ← 🔴 无 BP-5/7/8，是 G 循环较干净的一条
template_ref        G/G5 长期应收款.xlsx   sha256 c59bba69789eba3f…   398,912 B / 16 sheets
payload 列（FD-1）   dual_write_remark_and_conclusion
HTTP 客户端（FD-2）  api（apiProxy）
行身份（FD-4）       generated_uuid，字段 id，`useG5BalanceDetail.ts#L232`
```

| 事实 | 实测 |
|---|---|
| provider / 契约 | ❌ 无 `phase5_g5_*.py`、无 `g5.*.json` |
| 宿主接桥 | `bridge=0` / `legacyOO=4` / `notice=3` |
| TB 发布门 | ✅ 已接（`useG5Adjudication.ts` `publishToTb`=**4**，G 循环最多；`trial-balance`×3 / `writeback`×11） |
| 调整分录 | ✅ `G5TabAdjustment.vue` `useAdjustmentCentralSync`=3 ⇒ G5-4 是 hub（FC-6） |
| 公式管理预设 | ✅ 14 条生效（`workpaper:G5`）；块 `[25]` 审定表G5-1 / `[26]` **余额明细表G5-2** / `[27]`/`[28]` 披露 |
| 裸 IF | 122 格，**全部集中在 `审定表G5-1`**（主受管表 G5-2 **零**命中）⇒ 仍须按 GC-2 per-file 挂中性化 |
| definedName | 0（G5 册干净；对比 G3 约 480 个 / G4 29 个） |
| 真库载荷 | ✅ **G 循环最多**：8 行 / remark 12,952 B + conclusion 2,844 B |

**真库逐键（本 spec 相关）**：`G5-note-listed-rows` 5,580 B · `G5-note-soe-rows` 4,528 ·
`G5-4-rows` 1,209+1,209 · `G5-5-rows` 798+798 · **`G5-2-rows` 572+572** · `G5-3-rows` 254+254 ·
`G5-2-aging-preset` 9+9。
🔴 **五个键的 remark 与 conclusion 字节数完全相等** ⇒ FD-1 的 `dual_write` 形态在真库被字节数证实
（全 G 循环唯一有此证据的 entry；其余 dual_write entry 主表零载荷）。

### 16 sheets 几何（openpyxl 实测）

| sheet | 尺寸 | 公式 | 本 spec |
|---|---|---|---|
| 底稿目录 / 长期应收款实质性程序表G5A | 27r×8c / 31r×14c | 0 / 7 | 不接 |
| **审定表G5-1** | 87r×13c | **501** | 🔴 后置（`g-cycle-adjudication-sheets-coverage`）；但 **B35 越界缺陷在本 spec 登记** |
| 附注披露信息（上市公司）/（国企） | 113r×11c / 109r×12c | 225 / 189 | 不接 |
| **余额明细表G5-2** | **115r×22c** | **692** | ✅ **主受管表** |
| 坏账准备明细表G5-3 | 27r×20c | 65 | 🔍 核（真库 254+254 B） |
| 调整分录汇总G5-4 | 24r×10c | 7 | 🔍 FC-6 |
| 未实现融资收益测算表（租赁）G5-5 | 48r×18c | 46 | 🔍 核（真库 798+798 B） |
| 未实现融资收益测算表（销售）G5-6 | 43r×11c | 29 | 🔍 核 |
| 长期应收款保理核查表G5-7 | 38r×9c | 13 | 🔍 核 |
| 信用减值损失会计政策检查G5-8 | 46r×15c | 7 | 🔍 核（候选 `paragraph_block_bidirectional`，D4-5 范式） |
| **长期应收款三阶段划分G5-9** | 58r×**16384c** | 7 | 🔴 转置 + 16384（同 G4-9/G6-11 族）⇒ 见需求 4 |
| 长期应收款坏账准备测算G5-10 | 62r×19c | 74 | 🔍 核 |
| 减值准备转回（收回）、核销检查表G5-11 | 22r×20c | 10 | 🔍 核 |
| 凭证检查表G5-12 | 99r×21c | 15 | 🔍 核 |

### 主受管表 `余额明细表G5-2` 逐格几何（115 行，三段嵌套）

**段（一）原值**（R9 段标题）：表头 **R10/R11**（R11 是 N-R 账龄段 `未逾期|1年以内|1-2年|2-3年|3年以上`）
```
R12 子区标题「应收融资租赁款」      R13-17 数据(5 行)   小计 R18  =SUM(D13:D17)
R19 子区标题「应收分期收款销售商品款」 R20-24 数据(5 行)   小计 R25  =SUM(D20:D24)
R26 子区标题「应收分期收款提供劳务款」 R27-31 数据(5 行)   小计 R32  =SUM(D27:D31)
R33 子区标题「其他」                R34-38 数据(5 行)   小计 R39  =SUM(D34:D38)
R40 合计  =D18+D25+D39            🔴 漏 D32
```
**段（二）未确认融资收益**（R41 段标题）：表头 R42/R43，结构同段（一）；小计 R50/R57/R64/R71，
合计 **R72 `=D50+D57+D71` 🔴 漏 D64**。
**段（三）**：小计 R82/R89/R96/R103，合计 **R104 🔴 漏 R96**。

公式列 **G, J, M**（`G=D+E+F` 期初审定数 · `J=D+H-I` 期末余额 · `M=J+K+L` 审定数）；
段（二）另有 `B45=B13`（跨段引用同行债务人名称）。行身份 `id`（uuid），A 列是序号 1~5（不是身份）。

### 🔴 红基线（实测，非本 spec 引入）

**B1 · G5-2 三处合计漏加小计 —— 真实金额错误（FC-5 第三个例外）**

```
G5-2!{D..R}40  = =X18+X25+X39        🔴 段（一）四小计 18/25/32/39 只加三个，漏 R32
G5-2!{D..R}72  = =X50+X57+X71        🔴 段（二）漏 R64
G5-2!{D..R}104 = …                   🔴 段（三）漏 R96
```
影响 **D~R 共 15 列 × 3 段 = 45 格**；三段**都漏第三个子区** ⇒ 模式一致，是复制粘贴错误而非口径分歧。
业务后果：客户在「应收分期收款提供劳务款」（及段二/段三对应子区）填数时，合计行少算该子区全额。
触类旁通扫全 G 目录（判据：合计行公式引用的小计行集 ⊂ 同段小计行集）：本 spec 范围内**仅 G5 命中**。

**B2 · G5-1!B35 越界引用（FC-5 第四个例外）**

`审定表G5-1!B35 = =B9-B225`，而该 sheet 仅 **87 行** ⇒ `B225` 是空白越界格，求值恒 0 ⇒ B35 恒等于 B9。
全 G 目录越界引用仅 2 格，另一格是已排除的 `G0-1!E24`。
🔴 审定表本体归后置 spec，但**该缺陷在本 spec 登记并给出裁决**（同册缺陷不应分散到两份 spec 各查一遍）。

**B3 · G5-9 是第三张 16384 列转置表**

`长期应收款三阶段划分G5-9` 58r × **16384c**（有效内容列同族为 11），与 G4-9 / G6-11 同型。
G4/G6 那两张归 `g4-g6-shared-workbook-three-entry-lanes`；**G5-9 归本 spec**。

**B4 · 三段嵌套的 footer 语义：12 个小计 + 3 个合计，且合计是「小计相加」不是 SUM 区间**

框架层 `footer_anchor` 的单 footer 模型表达不了「段内四小计 + 段合计 + 三段并列」。
且合计行形态是 `=X18+X25+X39`（枚举相加）而非 `SUM(X13:X38)` ⇒ 插行后位移规则与 SUM 区间不同
（同 F4-9 / F5-1 的「小计相加」族）。

**B5 · 真库 dual_write 已发生，且是唯一被字节数证实的**

`G5-2-rows` 572+572 B 等五个键 remark 与 conclusion 字节完全相等 ⇒ 受管后若只写一列，
另一列会与之分叉（旧数据仍在）。契约 SHALL 明确双写语义，不得单写。

**B6 · `useG5Adjudication.ts` 的 `writeback` 出现 11 次（G 循环最多）**

它已接 `publishToTb`（4 处，也是最多）⇒ 两者并存。受管前 SHALL 逐处核 11 处 `writeback`
是否全部已收敛到显式发布门内部，不得有绕过门的第二条路（FC-9）。

## Requirements

### Requirement 1: 主受管表 G5-2 的三段嵌套声明

1. WHEN 声明 `余额明细表G5-2` THEN `store_item_id` SHALL 为 **`G5-2-rows`**、行身份 `id`
   （`generated_uuid`，`useG5BalanceDetail.ts#L232`）、表头 **R10/R11**（R11 是 N-R 账龄段）、
   公式列 **`("G","J","M")`**（`G=D+E+F` · `J=D+H-I` · `M=J+K+L`）、有效列 22(A-V)。
2. 🔴 WHEN 处置三段 × 四子区 THEN SHALL 二选一并给出证据，默认①：
   ①**每个子区一个 `RowTableSheetSpec`**（共 12 个 sheet_key，`g502-s1r1` … `g502-s3r4`），
   段合计行与段标题行不受管；②框架层扩 `footer_anchor` 支持「多小计 + 段合计」（改框架层，代价高）。
   判据 SHALL 断言 12 个受管区两两不相交、且不覆盖任何小计/合计/段标题行。
3. WHEN A 列是序号 1~5 THEN SHALL **不**把它当行身份（行身份是 `id`）；判据变异「用 A 列序号作身份」⇒
   插行后错位必红。
4. WHEN 段（二）含跨段引用 `B45=B13` THEN 该列 SHALL 判 `mode=formula`（模板派生），不得 editable。
5. WHEN 声明 payload THEN SHALL 是 **双写**（`remark` + `conclusion` 逐字相同，B5）；
   判据断言两列字节数相等，且变异「只写 remark」⇒ conclusion 与之分叉必红。

### Requirement 2: 两处模板真实金额错误的处置（FC-5 第三、第四例外）

1. 🔴 WHEN 处置 G5-2 三处漏加小计（B1）THEN SHALL 二选一，**不得**以模板为权威：
   ①经**模板覆盖层**把三个合计行改为含全部四个小计（`=X18+X25+X32+X39` 等三处）
   ②三个合计行整行判 HTML-only（不受管）并在 UI 中文提示「合计行模板公式存在已知缺陷，已由系统重算」。
   默认①（覆盖层可用时）。判据 SHALL 证明修复后 OO 与 HTML 的三个合计值相等，
   且**构造「只有第三个子区有数」的载荷**证明修复前后差异非零（否则判据空转）。
2. 🔴 WHEN 处置 G5-1!B35 越界（B2）THEN 本 spec SHALL 只**登记裁决与证据**（审定表本体归后置 spec）：
   记录 `=B9-B225` 原文、sheet 仅 87 行、求值恒等于 B9 的推论；并在后置 spec 的交棒清单里列明。
3. WHEN 走模板覆盖层 THEN SHALL **不改** `backend/wp_templates/G/G5 长期应收款.xlsx` 字节
   （运行时只读 + sha 冻结进契约）；覆盖后契约的 `template_sha256` 指向覆盖后字节。
4. WHEN 覆盖层未交付 THEN SHALL 走方案②降级并如实登记 `upstream_gap`，不得静默以错误模板受管。

### Requirement 3: 其余 sheet 的可行性核（不改生产代码）

1. WHEN 核 G5-3 / G5-5 / G5-6 / G5-7 / G5-10 / G5-11 / G5-12 THEN SHALL 逐张出形态判定（前端三元组 +
   store 键按值 grep + 模板几何），只产裁决与证据；真库已有载荷的两张（G5-3 254+254 B / G5-5 798+798 B）
   SHALL 优先给出接入可行性结论。
2. WHEN 核 G5-8（信用减值损失会计政策检查，46r×15c / 仅 7 公式）THEN 候选 `paragraph_block_bidirectional`
   （D4-5 范式）或 `single_html`；只产裁决。
3. WHEN 核 G5-4 THEN 照 FC-6 默认 `single_html`（`G5TabAdjustment.vue` `useAdjustmentCentralSync`=3）。
4. WHEN 核披露两张 THEN 不接；但 SHALL 确认 `g5NoteSectionMap` 的 `*_DISCLOSURE_SHEET_NAME` 命中真实 tab
   （slice 已实测 26 个声明全命中，本 spec 只做不回归断言）。

### Requirement 4: G5-9 三阶段划分（第三张 16384 列转置表）

1. WHEN 声明 G5-9 THEN SHALL 用 **`TransposedSheetSpec`**（同 G4-9 / G6-11，D4-29 先例），
   实体列与三块锚行由 Task 2 逐格实测（**不得**照抄 G4-9 的行号）。
2. 🔴 WHEN 处置 16384 列 THEN SHALL 与 `g4-g6-shared-workbook-three-entry-lanes` 的裁决**保持一致**
   （UUID 放有效内容列 +1，不放 `max_col+1`）；判据断言两份 spec 的策略同源，不各出一套。
3. WHERE `TransposedSheetSpec` 未入 HEAD THE G5-9 SHALL 登记为 HTML-only 并写明解锁条件。

### Requirement 5: TB 红线、中性化与零回归

1. 🔴 WHEN G5 受管 THEN SHALL 先逐处核 `useG5Adjudication.ts` 的 **11 处 `writeback`**（B6）是否全部
   收敛在 `publishToTb`（4 处）内部；发现绕过门的路径 SHALL 登记并立门，本 spec **不改造**（属
   `tb-writeback-explicit-publish-gate` 作业面）。
2. WHEN G5 受管 THEN FC-9 红线：sync 路径对 `trial_balance` 写次数为 **0**；`publishToTb`（科目 **1531**、
   余额口径）仍是唯一入口；变异「sync 回写里调 publishToTb」必红。
3. WHEN G5 册 materialize THEN SHALL 按 GC-2 挂 `oo_crash_neutralization_fn`（122 格裸 IF，
   🔴 **全部在 `审定表G5-1`**、主受管表 G5-2 零命中 —— 但中性化是 per-file，仍须挂）。
4. WHEN 零回归 THEN 照 GC-10 现算逐项比对，**不断言 digest 集合大小**。
5. WHEN 验收 THEN 真库 `G5-2-rows` 已有 572+572 B 真实载荷 ⇒ **不需要 seed**，
   但判据 SHALL 断言参与 roundtrip 的行数 > 0 且来自真库（同 foundation 的 GF-H2）。

### 不在本 spec 范围

- GC-1~GC-10 裁决本体（foundation spec）· 13 张审定表本体（`g-cycle-adjudication-sheets-coverage`，
  含 G5-1 —— 但 B2 的缺陷证据在本 spec 登记并交棒）。
- G4-9 / G6-11 两张 16384 列转置表（`g4-g6-shared-workbook-three-entry-lanes`）。
- `tb-writeback-explicit-publish-gate` 对 11 处 `writeback` 的改造（本 spec 只核与立门）。
- 模板覆盖层本身；平台级供给 BP-1~BP-4。
- G5-4 调整分录接入（FC-6 默认 `single_html`，只核）。
