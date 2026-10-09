# Design Document

## Overview

G 循环剩余 9 条 entry（G1/G3/G8/G9/G10/G11/G12/G13/G14）的主受管明细表。
九条共用同一套 `RowTableSheetSpec` 范式，差异在**表头层级 1~3 级**与**五处形态特例**。

GC-1~GC-10 见 `g-cycle-sync-foundation-and-first-canary/design.md`（引用、不复述）。

九条相对 G4/G6/G5 三条 lane 的优势：**一册一 entry**（FC-3 在这九条上成立）、无 BP-8、
无 16384 列表、无转置形态。难点是**特例多而分散**，这也是它们合成一份 spec 的理由 ——
五处特例只有放在一起对照，才能判出「是特例还是通例」。

## 上游锚定

沿用 foundation spec 锚定表。额外：
- **F3 spec 裁决 F3-H4**（行级 mask 拆 spec）—— G8-2 与 G1-2 区①T 列的直接先例
- **F4-9 / F5-1 「小计相加」族** —— G1 R30 / G3 R30 / G13 R21 的 footer 形态
- **F5 除零的 `type_normalization_failure` 处置** —— 三处布尔校验列的容错范式
- **F2-55 footer SUM 起点异常** —— G12-2 的 `I=SUM(I7:I13)` 同族
- **`g6CrossHelpers` 派生别名** —— BP-10 收敛的正面样本

## Architecture

### 接入顺序（由易到难，特例后置）

```
G9（三区 + 真库唯一有载荷 605 B/2 wp + 无特例）      ← 首条
  → G10（单区 6 公式列，最规整）
  → G8（单区，但 R11/R12/R13 行级 mask）
  → G14（rowKey 固定行集 + 一处布尔列）
  → G11（单级表头 + 21 行最长 + 占比列引合计行 + 主表唯一命中裸 IF 44 格）
  → G13（父子行 + 布尔列 + 枚举相加 footer）
  → G12（无表头行 + 布尔列 + SUM 起点在数据区之上）
  → G3（三级表头 + 480 个 definedName）
  → G1（三区 + 区①跨表 T 列 + BP-5/7/9 + 未接 TB 门）      ← 最后
```

### 声明层结构

```
backend/app/services/workpaper_sync/
  phase5_g9_other_noncurrent.py   / phase5_g9_02_detail.py       ← 首条
  phase5_g10_trading_liabilities.py / phase5_g10_02_detail.py
  phase5_g8_other_equity.py       / phase5_g8_02_detail.py       ← 行级 mask
  phase5_g14_credit_impairment.py / phase5_g14_02_detail.py      ← rowKey
  phase5_g11_investment_income.py / phase5_g11_02_detail.py
  phase5_g13_fair_value_changes.py / phase5_g13_02_detail.py     ← 父子行
  phase5_g12_net_hedge_gains.py   / phase5_g12_02_detail.py      ← 无表头行
  phase5_g3_dividend_receivable.py / phase5_g3_02_detail.py      ← 三级表头
  phase5_g1_trading_financial_assets.py / phase5_g1_02_detail.py ← 最后
backend/data/workpaper_sync_contracts/g{1,3,8,9,10,11,12,13,14}.*.json
backend/scripts/e2e/seed_g_single_region_e2e.py   ← 🔴 八条需 seed（G9 除外）
```

🔴 **九条各自独立 entry 层模块**（一册一 entry，FC-3 在这九条成立）⇒ 不共用 entry 层，
与 `g4-g6` spec 的「三条共用一个 entry 层模块」形成对照。

### 受管区清单（逐格实测）

| sheet_key | entry | store_item_id | 身份 | 表头 | 数据 | footer | formula_columns | payload |
|---|---|---|---|---|---|---|---|---|
| `g902-r1/r2/r3` | G9 | `G9-detail-rows` | `rowId` | R9/R10 | R12-16 / R19-23 / R26-28 | 小计 R17/R24/R29 | E,H,I,J,L,P,Q,R,U,V,W,Y | remark |
| `g1002-managed` | G10 | `G10-detail-rows` | `rowId` | R9/R10 | R11-20 | R21 | E,G,K,L,M,O | remark |
| `g802-r11` / `g802-r12plus` | G8 | `G8-detail-rows` | `rowId` | R9/R10 | R11 / R12-20 | R21 | 见裁决 G1R-H3 | remark |
| `g1402-managed` | G14 | `G14-detail-rows` | 🔴 `rowKey` | R9/R10 | R11-19 | R20 | D,J,K,L | remark |
| `g1102-managed` | G11 | `G11-detail-rows` | `id` | **R9 单级** | R10-30 | R31 | F,G,J,K,L | remark |
| `g1302-managed` | G13 | `G13-detail-rows` | `rowId` | R9/R10 | R11-20 | R21（枚举相加） | B,C,D,I,J,K | remark |
| `g1202-managed` | G12 | `G12-hedge-detail-rows` | `rowId` | 🔴 **无** | R9-13 | R14 | G,I | remark |
| `g302-r1/r2` | G3 | `G3-2-detail-rows` | `id` | 🔴 **R9/R10/R11 三级** | R13-20 / R23-28 | 小计 R21/R29 | F,M,N,O,P,T,AA..AF | **conclusion** |
| `g102-r1/r2/r3` | G1 | `G1-2-rows` | `id` | R9/R10 | R12-16 / R19-23 / R26-28 | 小计 R17/R24/R29 | 区①含 **T**、区②③不含 | **conclusion** |

不受管：9 张审定表（后置 spec）· 9 张调整分录汇总（FC-6）· 各册附注披露 · 参考类 sheet ·
四张 `-修订前` hidden · 底稿目录 · 程序表。

## Data Models

不新增数据模型。三族行身份并存：`id`（G1/G3/G11）· `rowId`（G8/G9/G10/G12/G13）· **`rowKey`（G14）**。
payload 两形态：`conclusion_only`（G1/G3）· `remark_only`（其余七条）。

## 关键裁决

### 裁决 G1R-H1：首条选 G9，最后一条选 G1

| 维度 | G9 | G1 |
|---|---|---|
| 真库载荷 | **605 B / 2 wp**（九条唯一有真实数据） | 主表零行 |
| 几何 | 三区（与 G1 近同构） | 三区 |
| 跨表公式 | **无** | 🔴 区① T 列引 G1-6（行级 mask） |
| 专属 BP | 无 | 🔴 BP-5 + BP-7 + BP-9 |
| TB 门 | 已接 | 🔴 未接（GC-9 缺口） |
| 形态特例 | 无 | 行级 mask |

G9 是「有真实载荷 + 零特例」的唯一交集 ⇒ 首条（可不 seed，验收最可信）。
G1 三条 BP + 未接 TB 门 + 行级 mask ⇒ 最后（依赖 foundation 的 BP-5 修与 GC-9 裁决先落地）。

🔴 **G9 与 G1 几何近同构但 `formula_columns` 必不相同**（G1 区①多 T 列）⇒ 判据 SHALL 断言两者不等，
防「同构就复制」（FC-4 的禁推演铁律在列集上的体现）。

### 裁决 G1R-H2：G12 的「无表头行」显式声明，不伪造一行表头

`明细表G12-2` 的 R9 就是第一行数据（`A:预期销售和预期采购的外汇净头寸 | B:支付200万美元 | …`），
R1-R8 是标题/索引区。两方案：
- ①`header_row` 显式声明为「无」（引擎须支持 `header_row=None` 或等价语义）
- ②把 R8 当表头（**否决**：R8 不是表头，声明它会让 header_source_ref 指向非表头格，且 OO 侧会把 R8 锁成表头行）

默认①。若引擎不支持 `header_row=None` ⇒ 登记为框架层缺口 + G12 暂不受管，**不得**伪造一行表头。
同族：G6-5 也是无表头行（归 `g4-g6` spec）⇒ 两份 spec 的处置 SHALL 同源。

### 裁决 G1R-H3：G8-2 行级 mask 拆两个 spec

实测 R11/R12/R13 公式集互不相同：

| 行 | 公式列 | `M` 列区间 |
|---|---|---|
| R11 | E,H,M,O,P,Q,**R**,**T** | `SUM(I11:L11)`（含 L） |
| R12 | E,H,M,O,P,Q,**R** | `SUM(I12:K12)`（不含 L） |
| R13 | E,H,M,O,P,Q,**T** | `SUM(I13:K13)` |

矩形 mask 表达不了。裁决（照 F3-H4）：拆 `g802-r11`（单行）+ `g802-r12plus`（R12-20），
R12 与 R13 的差异（R 有无 / T 有无）按**并集取 formula、交集取 editable** 的保守策略处置，
并加判据证明 R13 的 R 列与 R12 的 T 列**不被误标 formula**（否则手填值会被覆盖）。
🔴 若保守策略导致可编辑面缩小到业务不可接受 ⇒ 改为三个 spec（`r11`/`r12`/`r13plus`）；Task 里留该分支。

### 裁决 G1R-H4：三处布尔校验列判 `mode=formula` + 容错三判据

`G12-2!G = =D9=SUM(E9:F9)` · `G13-2!K = =J11=D11` · `G14-2!L = =D11=K11` 求值为 TRUE/FALSE。
按值读 `excel_extract.py:3400-3431`：对 formula 格也读值并 `normalize_value`，失败记
`SchemaAnomalyKind.type_normalization_failure` 并保留原值；`PROTECTED_MODES={formula,auto_source}` 使其不入 store。
⇒ 判 `mode=formula` 即可，但判据须三条：①extract 不抛 ②异常类型为 `type_normalization_failure`
③store 中该字段不出现 `TRUE`/`FALSE` 字面量。与 F5 变动率除零（`#DIV/0!`）同族处置。

### 裁决 G1R-H5：G11-2 占比列的绝对引用须实测位移行为，不假设

`G/K = =IF(F10=0,0,F10/$F$31)` 引合计行 F31。插行后 Excel **会**调整 `$F$31` 的行号（绝对引用只锁
「不随填充变」，插行仍位移），但这是**须实测确认的行为**而不是可假设的。
裁决：Task 里显式做「插 3 行后 `$F$31` 是否变成 `$F$34`」的实测，并把结论写成判据。
🔴 若实测**不位移** ⇒ 占比列受管后会指向错行 ⇒ G11 的 G/K 两列改判 HTML-only。

### 裁决 G1R-H6：G13 父子行 —— 父行派生列不得 editable，合计行不受管

R11 父 = `B12+B13` 子（同理 R14/R17/R19/R20 是父行）；合计 R21 `=B11+B14+B17+B19+B20` 只加父行。
裁决：父行的 `B/C/D` 列判 `mode=formula`；受管区**不含**合计行 R21；
🔴 Task 2 SHALL 先按值实测前端是否有父子关系字段 —— 若无，则「哪些行是父行」只能靠模板行号硬编码，
须在 spec 里显式登记该耦合（插行会破）。

### 裁决 G1R-H7：BP-7 在五条的 `blocked_by` 里，但正文只展开 G6-sppi ⇒ 按值定位或登记不一致

slice 给 G3/G10/G11/G12/G13 五条列了 BP-7，而 BP-7 正文只展开 `useG6SppiFairValue.ts` 一处。
与 `g4-g6` spec 的 G4-main 同款。裁决：Task 2 按值 grep 五条的载入路径；
有缺陷 ⇒ 一并修（触类旁通一次修完五条）；**无缺陷 ⇒ 如实登记「slice `blocked_by` 与 BP 正文不一致」**，
🔴 不得为对齐 slice 伪造缺陷，也不得静默抹掉这五条的 BP-7。

## Error Handling

| 场景 | 处理 | 依据 |
|---|---|---|
| G1 与 G9 共用 `formula_columns` | G1 区①的 T 列漏声明 ⇒ 判据必红 | G1R-H1 |
| G12 伪造一行表头 | 丢第一行数据 / header_source_ref 指非表头 ⇒ 判据必红 | G1R-H2 |
| G8-2 用 R11 列集套全区 | R12 的 `M` 区间被误声明 ⇒ 判据必红 | G1R-H3 |
| 布尔列标 editable | TRUE/FALSE 进 store ⇒ 判据必红 | G1R-H4 |
| G11 占比列位移行为未实测 | 假设代替实测 ⇒ 判据必红（须有插行实测证据） | G1R-H5 |
| G13 合计行纳入受管区 | 只加父行的枚举式被当数据行 ⇒ 判据必红 | G1R-H6 |
| 为对齐 slice 伪造五条 BP-7 | 判据要求「有缺陷给行号、无缺陷给不一致登记」 | G1R-H7 |
| G14 的 `rowKey` 被判违规 | 判据必红（它是最稳一族，GC-6） | Req 1.2 |
| G1/G3 payload 写死 `remark` | 指向恒空列 ⇒ 判据必红 | Req 1.4 |
| G3 受管误伤 480 个 definedName | 判据必红（集合须逐项不变） | Req 4.4 |
| 八条空载荷直接验收 | 必须先 seed（G9 除外） | Req 4.8 |

## Correctness Properties

🔴 编号 spec-scoped：`Property N` 读作 `G1R-P{N}`。

### Property 1: 三族行身份逐条按值取，`rowKey` 不被判违规
**Validates: 1.1, 1.2**　`id` 3 条 / `rowId` 5 条 / `rowKey` 1 条（G14，行集取 `G14_LINE_ITEMS`）。
变异：白名单写死 `('rowId','id')` ⇒ G14 必红。

### Property 2: G1/G3 的 timestamp 型 id 有随机后缀（或已修）
**Validates: 1.3**　按值核 `useG1Detail` / `useG3Detail` 的 id 生成；纯 `Date.now()` ⇒ 构造同毫秒连加两行
证明撞 id 必红，修后转绿。

### Property 3: payload 两形态逐条断言
**Validates: 1.4**　G1/G3 指 `conclusion`、其余七条指 `remark`。变异：统一写死 `remark` ⇒ G1/G3 投影恒空必红。

### Property 4: BP-10 三键收敛为单一真源
**Validates: 1.5**　`G1-2-rows`(现 8 处) / `G10-detail-rows`(6) / `G11-adj-rows`(6) 的**声明处**计数各为 1，
其余改派生别名（照 `g6CrossHelpers`）。

### Property 5: 表头层级逐条实测（1~3 级 + 无表头）
**Validates: 2.1, 2.2, 2.3**　G3 三级 R9/R10/R11 · G11 单级 R9 · G12 **无** · 其余两级。
变异：G3 按两级声明 ⇒ 数据区起点错位必红；G12 把 R9 当表头 ⇒ 丢首行必红。

### Property 6: G1 与 G9 三区列集不等
**Validates: 2.4**　断言 `G1` 区① 含 `T` 而 `G9` 三区均不含；两条的 `formula_columns` 集合不相等。
变异：复制 G9 的列集给 G1 ⇒ T 列漏声明必红。

### Property 7: 枚举相加型 footer 被登记
**Validates: 2.5**　G1 R30 `=SUM(C17,C24,C29)` · G3 R30 `=C29+C21` · G13 R21 `=B11+B14+…` 三处登记为
「枚举相加」而非 SUM 区间（插行位移规则不同）。

### Property 8: G13 父子行处置
**Validates: 3.1**　父行 `B/C/D` 列 `mode=formula`；受管区不含 R21；
🔴 若前端无父子字段 ⇒ 证据须显式登记「父行靠模板行号硬编码」的耦合。

### Property 9: 三处布尔校验列容错三判据
**Validates: 3.2**　①extract 不抛 ②异常 `type_normalization_failure` ③store 无 `TRUE`/`FALSE` 字面量。
变异：任一列标 editable ⇒ 必红。

### Property 10: G11 占比列的插行位移行为已实测
**Validates: 3.3**　插 3 行后 `$F$31` 的实测结果（位移或不位移）被写成判据；
不位移 ⇒ G/K 两列改判 HTML-only。变异：以假设代替实测 ⇒ 证据缺失必红。

### Property 11: G12 合计 SUM 起点在数据区之上的位移行为已登记
**Validates: 3.4**　`I=SUM(I7:I13)` 插行后区间变化实测并登记（框架层扩张规则未覆盖该形态）。

### Property 12: G8-2 行级 mask 拆区且不误标
**Validates: 3.5**　`g802-r11` 与 `g802-r12plus` 两区；R13 的 `R` 列与 R12 的 `T` 列不被误标 formula。
变异：用 R11 列集套全区 ⇒ R12 的 `M` 区间被误声明必红。

### Property 13: TB 红线 + 损益类发生额口径
**Validates: 4.1, 4.2**　sync 路径 TB 写次数 0；八条已接 `publishToTb` 仍唯一入口；
G11/G12/G13/G14 口径为**本期发生额**。G1 受管前须有 foundation GC-9 裁决结论。

### Property 14: 九册挂中性化
**Validates: 4.3**　九条 `StoreMergePlan` 全带 `oo_crash_neutralization_fn`；
证据写明「主受管表自身只有 G11-2 命中 44 格，其余八张零命中，但中性化是 per-file」。

### Property 15: G3 的 definedName 集合逐项不变
**Validates: 4.4**　受管前后 `G3 应收股利.xlsx` 的约 480 个 definedName 集合相等。

### Property 16: 四张 `-修订前` hidden 逐字排除（空格不 strip）
**Validates: 4.5**　含 `信用减值损失审计程序表G14A -修订前`（**名中空格**）；变异：strip 后比较 ⇒ 漏排除必红。

### Property 17: prefill 两块 sheet 名不回归
**Validates: 4.6**　块 `[169]`/`[170]` 的 sheet 名仍为 `明细表G13-2`/`明细表G14-2`（foundation Task 7 已修）。

### Property 18: 零回归现算 + G9 不 seed 而其余八条 seed
**Validates: 4.7, 4.8**　非本 spec 的 digest 逐项不变（不断言集合大小）；
G9 验收断言载荷来自真库（605 B）；其余八条未 seed 时验收脚本显式失败。

### Property 19: BP-7 五条的处置完整
**Validates: 1.1**（并入）　G3/G10/G11/G12/G13 各有「实测有缺陷并已修」或「实测无缺陷 + slice 不一致登记」之一。

## Testing Strategy

红判据先行：阶段 0 先打红 P1 / P5 / P6 / P9 / P12（三族身份 / 表头层级 / G1-G9 列集不等 / 布尔列 / G8 行级 mask）。
后端 pytest（`$env:PYTHONIOENCODING='utf-8'`，PBT `max_examples=5`）；前端 vitest；
真栈 Playwright `--workers=1`，fixture 分九个 `e2e/fixtures/g{N}-l2-cases.json`。
🔴 **只有 G9 可不 seed**；其余八条前置 `seed_g_single_region_e2e.py`（P18 守护）。
🔴 P10 / P11 是**实测型判据**（插行后引用位移），不得用静态推断代替。

## 顺带发现（登记，不在本 spec 处理）

1. **G1-2 与 G9-2 几何近同构**（三区 R12-16/R19-23/R26-28、小计 R17/R24/R29、合计 R30 同式、
   表头 R9/R10 列名大段相同），差异只在 G1 区①多一个跨表 T 列与有效列数（27 vs 28）⇒
   若将来抽公共声明，这两条是最佳候选；但本 spec 默认各写一份（避免过早抽象 + P6 要求断言两者不等）。
2. **G13-2 与 G14-2 结构近同构**（都是 R9/R10 两级表头 + R11 起数据 + 一列布尔校验 + 对应科目列），
   差异在 G13 有父子行、G14 是固定行集 ⇒ 同上，登记不抽。
3. **G12 册的 `净敞口套期收益审计程序表G12A-修订前` 有 63 行 × 115 个合并单元格**，是四张 `-修订前`
   里最大的一张 ⇒ 模板治理时优先清理。
4. **G11-2 是九条里唯一主受管表自身命中裸 IF 的**（44 格，全是占比列的 `IF(F=0,0,…)`）⇒
   若将来 GC-2 的中性化策略细化到 sheet 级，G11-2 是第一个需要单独判定的表。
