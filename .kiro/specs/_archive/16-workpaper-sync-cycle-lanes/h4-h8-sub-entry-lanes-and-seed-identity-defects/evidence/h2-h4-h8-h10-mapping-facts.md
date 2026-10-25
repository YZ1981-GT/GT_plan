# H2 / H4 / H8 / H10 接线前置事实（现算，2026-09-27）

本文件固化四条 entry 的**现算底账**，避免下一轮重复 4 份探针的工作。
所有数字为 openpyxl 逐格实测 + 前端按值 grep，非推演。

## 0. 结论速览

| entry | 模板主表 | 表头级数 | 有效列 | 数据区 | 可否照 H6/H9 范式接线 |
|---|---|---|---|---|---|
| H2 | `明细表H2-2` | **4**（R9-R12） | ~30+（max_col=50，未全探） | R13-R20 | 可，但有 2 处列归属歧义待定 |
| H4 | `明细表H4-2` | **4**（R8-R11） | **49（A..AW）** | R12-R27 | **可**（歧义已从代码定死，见 §2） |
| H8 | `明细表H8-2` | **4**（R8-R11） | ~58（未全探） | R12-R25+ | 可（命名与模板四块 1:1，最规整） |
| H10 | `明细表H10-2` | **1**（R7） | 26（A..Z） | R8-R16 | 🔴 **不可** —— 结构性不匹配，见 §4 |

🔴 **修正先前判断**：上一轮报告说「H2/H4/H8/H10 没有映射障碍，可照 H6 的路子继续」——
**H10 不成立**（§4）。H2/H4/H8 成立，但都是 49~58 列四级表头三区块宽表，
每条需要一次独立的仔细映射，不是 H6/H9 那种一坐下就能写完的规模。

## 1. 四条共有身份事实（slice `independent_entries` 逐字）

| | H2 | H4 | H8 | H10 |
|---|---|---|---|---|
| entry_id | `xlsx/gt-h2-construction-in-progress` | `xlsx/gt-h4-engineering-materials` | `xlsx/gt-h8-right-of-use-assets` | `xlsx/gt-h10-asset-disposal-income` |
| wp_code_pattern | `H2C` | `H4E` | `H8R` | `H10A` |
| 模板 sha256 | `de9426a33e8d51e9351c8dd2393fe8502433d2cf810f30318f254a474ec480fe` | `c2c3ee61b33f4a7ca2603359810207bfb14f189c464135e0ede3e0a738c658cc` | `112053f0681642c371572998a559e4c5362f518265897a36fc90d7f84e666782` | `9f0d2a64dab1fd7661bb512194b4eba9a22f5afe28db38ec64fc22867421ac8a` |
| 模板字节 | 162,616 | 112,937 | 465,476 | 42,334 |
| 册内 sheet 数 | 21 | 13 | 20 | 9（含 `GT_Custom`） |
| write_carrier | `host_inline` | `formdata_composable` | `host_inline` | `formdata_composable` |
| read_carrier | snapshot 透传 | formdata | `host_inline_render_config_refetch` | formdata |
| payload 列 | `remark` / dual_write | 同 | 同 | 同 |
| 主表键 | `H2-2-rows` | `H4-2-rows` | `H8-2-rows` | `H10-detail-rows` |
| 行身份键 | `rowId` | `rowId` | `rowId` | **`id`** |
| 行身份生成式 | `row-${Date.now()...}` | 同 | 同 | `h10d-${Date.now()...}` |

🔴 **`H10A` 不是幻影码**（同 `H6A`）——它同时是真实程序表码
（册内 sheet `资产处置损益实质性程序表H10A`）⇒ provider 必须
`phantom_code_resolves_to_own_workbook=True`。`H2C` / `H4E` / `H8R` 是真幻影码。

🔴 **slice 的 `row_identity_is_positional` 对 H2/H4/H8 标 `True`，是过期快照**：
那三处下标身份（`GtH2#616` / `GtH8#578` / `h4DetailPrefill#50`）已在
commit `91933bd68`（BP-6 修复）改为按科目编码的 `buildHSeedRowId`。
接线时按现状复核，不要照 slice 的布尔值写判据。

## 2. H4 —— 事实最完整，可直接开写

几何：四级表头 **R8/R9/R10/R11** · 数据 **R12-R27（16 行）** · footer **R28 `合计`** ·
有效内容列 **49（A..AW）** · 数据行公式列 **25 个**。

🔴 **footer 之后还有第二区域 R29-R34**：`A29='其中：'` + 5 行按
`=SUMPRODUCT(($B$12:$B$27=$A30)*(E$12:E$27))` 做的**按类别小计**，
行标签取 `=底稿目录!A9..A13`。`RowTableSheetSpec` 只有一个 `footer_row`
⇒ 这 6 行既不是数据区也不是 footer，接线时必须显式声明为**不受管区域**，
否则 merge 可能把它们当数据行覆盖掉。

三区块：
- **原值 E..AH**（`E8:AH8`）：未审数 `E9:P9`（期初 E-G / 增加 H-J / 减少 K-M / 期末 N-P，
  每组皆 数量·单价·金额）· 期初调整 `Q9:R9`（数量 Q / 金额 R）·
  账项调整 `S9:V9`（增加 S-T / 减少 U-V）· 审定数 `W9:AH9`（期初 W-Y / 增加 Z-AB /
  减少 AC-AE / 期末 AF-AH）
- **减值准备 AI..AS**（`AI8:AS8`）：未审 AI-AL · 期初调整 AM · 账项调整 AN-AO · 审定 AP-AS
- **期末净值 AT..AU**（`AT8:AU9`）：未审净值 AT / 审定净值 AU
- 尾部两列：`AV 库龄`（`AV8:AV11`）· `AW 品质状况（正常、残次、毁损、滞销等）`

### 🔴 歧义已从代码定死（不是猜）

模板在调整/审定块是 **数量·单价·金额 三联列**，而前端 `H4DetailRow` 在这些位置
只有**单个标量**（`ajeBegin` / `auditedBegin` …）。判据来自代码本身：

- `useH4Detail.ts#L63` 注释：`// 调整（金额口径 AJE，对齐 Excel 核实情况）`
- `#L140`：`const auditedBegin = calcAuditedAmount(row.beginAmount, row.ajeBegin, 0)`
  —— 以 `beginAmount`（金额）为基，故 `ajeBegin` 必是**金额**口径

⇒ 调整/审定块的**数量列与单价列全部是 `template_only_columns`**（模板有列、HTML 无字段），
只有金额列进 `field_specs`：

| 模板列 | 含义 | store 字段 | mode |
|---|---|---|---|
| B / C / D | 类别 / 名称 / 计量单位 | `category` / `name` / `unit` | editable |
| E / F / G | 期初 数量 / 单价 / 金额 | `beginQty` / `beginUnitPrice`(f) / `beginAmount` | F 为公式 `=G/E` |
| H / I / J | 增加 数量 / 单价 / 金额 | `increaseQty` / `increaseUnitPrice`(f) / `increaseSubtotal` | I 为公式 |
| K / L / M | 减少 数量 / 单价 / 金额 | `decreaseQty` / `decreaseUnitPrice`(f) / `decreaseTotal` | L 为公式 |
| N / O / P | 期末 数量 / 单价 / 金额 | `endQty`(f) / `endUnitPrice`(f) / `endAmount`(f) | 全公式 |
| Q | 期初调整 **数量** | —— | **template-only** |
| R | 期初调整 **金额** | `ajeBegin` | editable |
| S / U | 账项调整 增加/减少 **数量** | —— | **template-only** |
| T / V | 账项调整 增加/减少 **金额** | `ajeIncrease` / `ajeDecrease` | editable |
| W X / Z AA / AC AD / AF AG | 审定块 数量·单价 | —— | **template-only**（皆公式） |
| Y / AB / AE / AH | 审定 期初/增加/减少/期末 **金额** | `auditedBegin` / `auditedIncrease` / `auditedDecrease` / `auditedEnd` | 全公式 |
| AI / AJ / AK / AL | 减值 期初/增加/减少/期末 | `impairBegin` / `impairIncrease` / `impairDecrease` / `impairEnd`(f) | AL 公式 |
| AM / AN / AO | 减值 期初调整 / 账项增加 / 账项减少 | —— | **template-only**（见下） |
| AP / AQ / AR | 减值审定 期初/增加/减少 | —— | **template-only**（皆公式） |
| AS | 减值审定 期末 | `auditedImpairEnd` | formula |
| AT / AU | 未审净值 / 审定净值 | `bookValueEnd`(f) / `auditedBookValue`(f) | 全公式 |
| AV / AW | 库龄 / 品质状况 | `aging` / `quality` | editable |
| A | 序号 | —— | **template-only** |

🔴 **`ajeImpair` 是 store-only（不映射任何格）**：前端把减值调整压成**一个** `ajeImpair`
（`auditedImpairEnd = calcAuditedAmount(impairEnd, ajeImpair, 0)`），模板却是
AM 期初调整 + AN 账项增加 + AO 账项减少**三列**，且 AS 走 `=AP+AQ-AR`。
一对三无法确定分摊 ⇒ 不映射，登记为 store-only + 在契约 note 里写明两侧口径差异。

store-only（HTML 有字段、模板无列）：`purchaseAmount` / `otherIncrease` /
`usageAmount` / `returnAmount` / `scrapAmount` / `otherDecrease` / `spec` / `supplier` /
`ajeImpair` / `bookValueBegin` / `bookValueDiff`
—— 前 6 个是前端把模板单列 `增加金额 J` / `减少金额 M` 细分成的组成项。

派生合计键（HC-6，不参与 roundtrip）：`H4-2-detail-total` / `H4-2-increase-total` /
`H4-2-decrease-total` / `H4-2-impair-total`；另有 `H4-3-rows`（调整分录，同模块但**另一张表**）。

子入口：**2 条 `H4T`**（`H4TabImpairment` / `H4TabRecoverable`），按 AC 1.6 复用本 entry 的 adapter。

## 3. H2 / H8 —— 可映射，但各有一处待定

**H8（最规整，建议下一条先做）**：模板 R8 `D8='使用权资产原值'` / `W8='累计折旧'`
（+ 减值块在 col 30 之后，未全探）。前端 `H8DetailRow` 78 字段的命名与模板**逐列 1:1**：
`costBeginUnadj`→D · `costIncLease`→E · `costIncReval`→F · `costIncOther`→G ·
`costDecSublease`→H · `costDecDisposal`→I · `costDecOther`→J · `costEndUnadj`→K(f) ·
`costOpenAdj`→L · `costAjeIncLease..costAjeDecOther`→M..R ·
`costBeginAud/costIncAud/costDecAud/costEndAud`→S..V(f)，`dep*` / `impair*` 同构。
⇒ **无需审计域裁决**。待补：col 30 之后的全宽探测（减值块列位）。
另有 3 条 `H8T` 子入口 + 7 个 `H8-1-*` 审定表键 + `H8-adj-tb-amount-{ending,opening}`
两个 TB 核对种子键。

**H2**：四级表头 R9-R12，数据 R13-R20（8 行），footer R21。
A..I 是工程属性列（工程项目名称/预算金额/资金来源/工程累计投入占预算比例%/
预计完工时间/工程进度/完工日期/批准文号/利息资本化率），J 起为金额块。
🔴 两处待定：
1. **`O 其他减少` 对应 `decrease` 还是 `transferOut`** —— 前端两个字段都在 `toPersist` 里，
   名称无法判别，需查 `useH2Detail` 的计算式（同 H4 的定死办法）。
2. 模板 `L 增加` 是**单列**，前端有 `increaseMaterial/Labor/Machinery/Interest/Other` 五项
   + `increaseTotal` ⇒ 只有 `increaseTotal` 映射 L，五项为 store-only。
   但 `increaseTotal` **不在 `toPersist`**（56 键里没有）⇒ 需确认它是否客户端重算。
`D13='=IF(AH13=0,0,AH13/B13)'` 引用 **AH**（col 34）⇒ 必须全宽探测才能定有效列数。

## 4. 🔴 H10 —— 结构性不匹配，**不可**照 H6/H9 接线

模板 `明细表H10-2` 是**固定 9 行 × 月度矩阵**：
- 单级表头 R7：`项目 | 1月..12月 | 本期合计 | 账项调整 | 重分类调整 | 期末审定数 |
  与相关科目勾稽 | 与相关科目勾稽金额 | 结构比 | 上年同期发生数 | 账项调整 | 重分类调整 |
  上年同期审定数 | 结构比 | 增长比例`（A..Z，26 列）
- 数据 R8-R16 的**行标签是模板写死的 9 类资产处置**（持有待售/固定资产/在建工程/
  生产性生物资产/无形资产/债务重组/非货币性资产交换/使用权资产/油气资产），
  且 R 列每行带**固定的勾稽说明文本**（如 `与H1固定资产处置/H6清理勾稽`）
- footer R17 `合计` + **R18 `各月比例`**（第二行 footer 型公式行）

前端 `H10DetailRow`（25 字段，键 `H10-detail-rows`，行身份 `id` 随机生成）是
**逐资产处置明细**：`assetName / assetType / sourceWp / originalCost /
accumulatedDepreciation / disposalIncome / disposalExpenses / disposalTax /
approvalDoc / appraisalReport / contractRef / invoiceRef / linkageId` …

⇒ 两者**没有任何列对应关系**：模板是按类别聚合的 12 月分布表，前端是按单项资产的
处置台账。行身份也对不上（模板行是固定类别标签，前端行是用户自增随机 id）。

**不是命名差异，是两张不同的表。** 接线前必须先裁决：
- (a) 前端这张明细该对应册内**另一个** sheet（如 `检查表H10-4`）？
- (b) 还是 `明细表H10-2` 的 HTML 对端应当是**另一个前端载体**（如 `useH10Adjudication` /
  `h10AdjStorage`，它们承载 H10-1 审定表）？
- (c) 还是该模板表按「固定行标签」形态走**另一套桥**（非 rows 桥，类似审定表逐格 mask）？

这三条都需要审计域 + 平台架构共同拍板，**不得由接线方猜**。
同类问题另见 H3/H5/H7（HTML 用 `costUnadj/costAje/costRje/costAudited` 四分，
与模板「未审数/期初调整/账项调整/审定数」不是同一套切分）。

## 5. 剩余 7 条的分组结论

| 分组 | entry | 状态 |
|---|---|---|
| 可直接开写 | **H4** | 事实完整（本文件 §2），歧义已从代码定死 |
| 需补全宽探测后开写 | **H8**（最规整）、**H2**（另有 2 处待定） | 无需域裁决 |
| **需域裁决，不得猜** | **H10**（表不对应）、**H3 / H5 / H7**（四分口径不同） | 阻塞 |

已落地：H9（canary，commit `d66b27b14`）· H6（发布链首例，commit `09fc4339c`）。

---

## 6. H8 全宽实测结果（已落地，commit `8628c6cc7`）

`明细表H8-2`：四级表头 **R8-R11**（51 个合并域）· 数据 **R12-R31（20 行）**· footer **R32**
`合计` · **有效内容列 58（A..BF，与 max_column 相等）**· 数据行公式列 **17** ·
footer 之下 **R33-R38** 按 **A 列**类别 SUMPRODUCT 小计（不受管）。

四区块：原值 `D8:V8` · 累计折旧 `W8:AM8` · 减值准备 `AN8:BD8` · 审定净值 `BE8:BF9`。

**58 列全部 1:1 映射、零 template-only** —— 全 H 唯一。四项闭合自检全绿。
三处易抄错（区块内增减去向数 3/3 vs 2/3 · 未审期末 SUM 端点 · BE/BF 是审定不是未审）
已逐条写进 sheet 声明。

## 7. H2 全宽实测 + 两处歧义的**代码级**结论

### 几何

`明细表H2-2`：四级表头 **R9-R12**（46 个合并域）· 数据 **R13-R20（8 行）**· footer **R21**
`合计` · **有效内容列 50（A..AX）**· 数据行公式列 **21**。

🔴 **与 H4/H8 的一处结构差异**：footer 之后**没有** `其中：` SUMPRODUCT 小计区
（R22 直接是「三、审计说明：」）⇒ H2 无 `unmanaged_regions`。
照 H4/H8 声明一个不受管区块会把「审计说明」误登记成小计区。

分区：
* **A..I 属性列**（皆 `R9:R12` 纵向合并）：A 工程项目名称 · B 预算金额 · C 资金来源 ·
  D 工程累计投入占预算比例%（**公式** `=IF(AH13=0,0,AH13/B13)`）· E 预计完工时间 ·
  F 工程进度 · G 完工日期 · H 批准文号 · I 利息资本化率
* **原值 `J9:AH9`**：未审数 `J10:R10`（期初 J-K / 增加 L-M / 减少 N-P / 期末 Q-R）·
  期初调整 `S10:T11` · 账项调整 `U10:Y10`（增加 U-V / 减少 W-Y）·
  审定数 `Z10:AH10`（期初 Z-AA / 增加 AB-AC / 减少 AD-AF / 期末 AG-AH）
  —— 每组都带「其中：累计资本化金额 / 本期利息资本化金额 / 利息资本化金额减少金额」子列
* **减值准备 `AI9:AS9`**：未审 AI-AL · 期初调整 AM · 账项调整 AN-AO · 审定 AP-AS
* **期初净值 `AT9:AU10`**（AT 未审 / AU 审定）· **期末净值 `AV9:AW10`**（AV 未审 / AW 审定）
  🔴 H2 有**两对**净值（期初 + 期末），H8 只有一对（`BE8:BF9`，期初/期末各一列）——
  两者列位形态不同，不能照抄。
* **AX 是否抵押**（`AX9:AX12`）

### 🔴 歧义①：`O 其他减少` 是 1 格对 2 字段，**不是**单字段映射

`useH2Detail.ts#L254`：

```ts
/** 其他减少口径：decrease + 旧字段 transferOut */
function _otherDecrease(row: Pick<H2DetailRow, 'decrease' | 'transferOut'>): number {
  return _getNum(row.decrease) + _getNum(row.transferOut)
}
```

⇒ 模板 `O` 对应的是 **`decrease + transferOut` 之和**，`transferOut` 是被折叠进来的旧字段。

**不得**简单映 `O → decrease`：若 store 里 `transferOut` 非零，
投影写进 O 的只有 `decrease`，而 HTML 侧显示 `decrease + transferOut` ⇒ **两侧静默不一致**。

裁决（同 H4 `ajeImpair` 的一对三处理）：
* `O → decrease`（主字段，mode editable）
* `transferOut` 登记为 **store-only + legacy_folded**，并在契约 note 里写明
  「非零时两侧会出现差额 = transferOut」
* 🔴 **登记为停下报告点**：真库 `H2-2-rows` **无行**，无法实证 `transferOut` 是否真的出现过。
  接线前应先跑一次真库扫描确认其恒零/恒缺；若真有非零值，正确做法是**先做一次数据迁移**
  把 `transferOut` 并进 `decrease` 再接线，而不是带着已知差额上线。

### 🔴 歧义②：`L 增加` 在模板可输入、在 HTML 是派生 ⇒ 方向性冲突

`useH2Detail.ts#L351 _recalcFormulas`：

```ts
row.increaseTotal =
  _getNum(row.increaseMaterial) + _getNum(row.increaseLabor) + ... (共 5 项)
row.cipEnd = calcCipEndBalance(_getNum(row.cipBegin), row.increaseTotal, ..., _getNum(row.transferAmount))
row.unadjustedEnd = row.cipEnd
```

⇒ `increaseTotal` **不落库**（不在 `toPersist` 的 56 键里），load 时由 5 个分项重算；
而模板 `L 增加` **没有公式**，是可输入格。

两侧权威方向相反：OO 侧改 `L` → 回写进 store 只能落到 `increaseTotal`（不落库）或某个分项
（不知该摊给哪一项）；HTML 侧 load 又会用 5 个分项把它覆盖。

裁决：**`L` 登记为 `template_only_columns`**，5 个分项（`increaseMaterial` / `increaseLabor`
/ `increaseMachinery` / `increaseInterest` / `increaseOther`）登记为 store-only。
即「原值·未审·本期增加」这一格**不参与双向同步**，是**声明出来的覆盖缺口**，
不是靠猜一个摊分规则蒙过去。同理 `unadjustedEnd` / `cipEnd` / `remainingCip` 皆派生。

🔴 **停下报告点**：若审计侧要求 `L` 必须双向，需先裁决摊分规则
（例如「OO 改 L ⇒ 差额全部计入 increaseOther」），那是审计域决定，不由接线方定。

### 结论

H2 **可以接线**，但比 H4/H8 多两处**声明出来的覆盖缺口**（`L` 与 `transferOut`），
且两处都带停下报告点。建议接线时把这两条写进契约 `review` 并配守卫，
而不是为了「列覆盖闭合」硬凑映射。
