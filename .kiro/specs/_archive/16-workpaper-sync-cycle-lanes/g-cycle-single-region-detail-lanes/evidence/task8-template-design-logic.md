# Task 8 设计依据：G9-2 模板的编制思路与前端对齐方案

spec `g-cycle-single-region-detail-lanes` · Task 8（用户拍板**选项 C：改前端对齐模板**）
实测 2026-09-27 · 依据 = 权威模板 `backend/wp_templates/G/G9 其他非流动金融资产.xlsx` 逐格 + 其**编制说明**

---

## 1. 模板的业务定义（编制说明 A37-A43 逐字）

> 1．编制时应列入其他非流动金融资产的**每一明细账户**。2．外币其他非流动金融资产应列明原币金额及折合汇率（**自行添加项目**）。
> 2.本项目可能包括：
> （1）未能通过 SPPI 测试的、到期日不超过一年或预期持有不超过一年的债务工具投资（含嵌入衍生工具），例如非保本理财产品、保本浮动收益理财产品（结构性存款）等；
> （2）以其他业务模式持有的债务工具投资（含嵌入衍生工具）；
> （3）未指定为有效套期工具的衍生工具；
> （4）到期日不超过一年或预期持有不超过一年的权益工具投资（不包括指定为 FVOCI 的）；
> （5）到期日不超过一年或预期持有不超过一年的、直接指定为 FVTPL 的债务工具投资（含嵌入衍生工具）。

🔴 **五类全部是 FVTPL 口径**（公允价值计量且其变动计入当期损益），明文排除 FVOCI。
⇒ 这条是判定前端若干列「不是缺映射而是会计错误」的依据（见 §4）。

## 2. 列结构 = 「三分量 × 四阶段」（合并单元格实测）

一级表头（R9）的合并区间逐字：

| 合并区 | 一级标题 | 分量数 |
|---|---|---|
| `A9:A10` | 类别 | 跨两行单列 |
| `B9:B10` | 投资项目【按明细项目列示，如证券名称或被投资单位名称】 | 跨两行单列 |
| `C9:E9` | **期初余额** | 3（成本 / 累计公允价值变动 / 公允价值） |
| `F9:G9` | **期初账项调整** | 2（成本 / 公允价值变动） |
| `H9:J9` | **期初审定数** | 3 |
| `K9:K10` | 期初重分类数 | 1 |
| `L9:L10` | 期初报表数 | 1 |
| `M9:O9` | **本期变动（借方发生填正数）** | 3（成本 / 本期公允价值变动 / 计入投资收益的股息） |
| `P9:R9` | **期末余额** | 3 |
| `S9:T9` | **账项调整** | 2 |
| `U9:W9` | **期末审定数** | 3 |
| `X9:X10` | 期末重分类数 | 1 |
| `Y9:Y10` | 期末报表数 | 1 |
| `Z9:Z10` | 期末应收利息 | 1 |
| `AA9:AA10` | 变现是否存在限制 | 1 |
| `AB9:AB10` | 发函情况 | 1 |

### 2.1 三分量的会计含义（CAS 22 公允价值计量模型）

**公允价值 = 成本 + 累计公允价值变动**

- **成本**：初始投资成本（取得时的对价）
- **累计公允价值变动**：自取得日至资产负债表日**累计**的 FV 变动（FVTPL 口径下历年已计入损益的累计数）
- **公允价值**：资产负债表上的**账面价值**

⇒ 模板的 `E = C+D` · `J = H+I` · `R = P+Q` · `W = U+V` 四处都是这个恒等式。

### 2.2 四阶段的审计含义（未审 → 调整 → 审定 → 重分类 → 报表）

```
期初线：  期初余额(C/D/E) ──+期初账项调整(F/G)──→ 期初审定数(H/I/J) ──+期初重分类数(K)──→ 期初报表数(L)
                │
                │ +本期变动(M/N/O)
                ↓
期末线：  期末余额(P/Q/R) ──+账项调整(S/T)────→ 期末审定数(U/V/W) ──+期末重分类数(X)──→ 期末报表数(Y)
```

逐格公式实测（R12 行）与上图逐条对应：

| 公式 | 会计含义 |
|---|---|
| `E = C+D` | 期初公允价值 = 期初成本 + 期初累计 FV 变动 |
| `H = C+F` | 期初审定成本 = 期初成本 + 期初调整成本 |
| `I = D+G` | 期初审定累计 FV 变动 = 期初累计 FV 变动 + 期初调整 FV 变动 |
| `J = H+I` | 期初审定公允价值（三分量恒等式） |
| `L = E+K` | 期初报表数 = 期初公允价值 + 期初重分类 |
| `P = C+M` | 🔴 **期末成本 = 期初（未审）成本 + 本期成本变动** |
| `Q = D+N` | 🔴 **期末累计 FV 变动 = 期初（未审）累计 FV 变动 + 本期 FV 变动** |
| `R = P+Q` | 期末公允价值（三分量恒等式） |
| `U = P+S` · `V = Q+T` | 期末审定 = 期末 + 账项调整 |
| `W = U+V` | 期末审定公允价值（三分量恒等式） |
| `Y = R+X` | 期末报表数 = 期末公允价值 + 期末重分类 |

🔴 **关键设计意图**：`P = C+M` 走的是**未审线**（期初未审 + 本期变动 = 期末未审），
**不是** `P = H+M`（审定线）。两条线并行：被审计单位账面数一条线、审计调整一条线，
最后在「审定数」列汇合。前端若把期末算成「期初审定 + 本期变动」就破坏了这个模型。

### 2.3 三个区 = CAS 22 的金融资产分类（区标题行，不受管）

| 行 | 区标题 | 分类依据 |
|---|---|---|
| R11 | `其他非流动金融资产` | 大类 |
| R18 | `划分为以公允价值计量且其变动计入当期损益的金融资产` | **强制** FVTPL（未通过 SPPI / 其他业务模式） |
| R25 | `指定为以公允价值计量且其变动计入当期损益的金融资产` | **指定** FVTPL（消除会计错配而指定） |

⇒ 前端的 `isDesignated`（是否指定 FVTPL）字段在模板里是**用区位置表达**的，不是一个列。

### 2.4 三列补充信息的用途

| 列 | 用途 |
|---|---|
| Z 期末应收利息 | 金融资产的**应收未收利息**单列（资产项，不是损益） |
| AA 变现是否存在限制 | 附注披露要求（受限资产） |
| AB 发函情况 | 函证程序的执行记录 |

🔴 **O「计入投资收益的股息」与 Z「期末应收利息」是两个不同概念**：
O 是本期计入损益的股息（损益类）、Z 是期末尚未收到的利息（资产类）。
前端只有一个 `interestIncome` 字段 ⇒ 两个概念被合并成一个，必须拆开。

---

## 3. 前端现状与模板的对齐方案（28 → 28，但语义全改）

### 3.1 新行模型（严格按模板列序，字段名带列号注释）

| 列 | 模板表头 | 新字段名 | mode |
|---|---|---|---|
| A | 类别 | `category` | editable |
| B | 投资项目【…】 | `investTarget` | editable |
| C | 期初余额/成本 | `openingCost` | editable |
| D | 期初余额/累计公允价值变动 | `openingCumulativeFv` | editable |
| E | 期初余额/公允价值 | `openingFairValue` | **formula** `=C+D` |
| F | 期初账项调整/成本 | `openingAdjCost` | editable |
| G | 期初账项调整/公允价值变动 | `openingAdjFvChange` | editable |
| H | 期初审定数/成本 | `openingAuditedCost` | **formula** `=C+F` |
| I | 期初审定数/累计公允价值变动 | `openingAuditedCumulativeFv` | **formula** `=D+G` |
| J | 期初审定数/公允价值 | `openingAuditedFairValue` | **formula** `=H+I` |
| K | 期初重分类数 | `openingReclass` | editable |
| L | 期初报表数 | `openingReported` | **formula** `=E+K` |
| M | 本期变动/成本 | `periodCost` | editable |
| N | 本期变动/本期公允价值变动 | `periodFvChange` | editable |
| O | 本期变动/计入投资收益的股息 | `periodDividendIncome` | editable |
| P | 期末余额/成本 | `closingCost` | **formula** `=C+M` |
| Q | 期末余额/累计公允价值变动 | `closingCumulativeFv` | **formula** `=D+N` |
| R | 期末余额/公允价值 | `closingFairValue` | **formula** `=P+Q` |
| S | 账项调整/成本 | `closingAdjCost` | editable |
| T | 账项调整/公允价值变动 | `closingAdjFvChange` | editable |
| U | 期末审定数/成本 | `closingAuditedCost` | **formula** `=P+S` |
| V | 期末审定数/累计公允价值变动 | `closingAuditedCumulativeFv` | **formula** `=Q+T` |
| W | 期末审定数/公允价值 | `closingAuditedFairValue` | **formula** `=U+V` |
| X | 期末重分类数 | `closingReclass` | editable |
| Y | 期末报表数 | `closingReported` | **formula** `=R+X` |
| Z | 期末应收利息 | `closingInterestReceivable` | editable |
| AA | 变现是否存在限制 | `realizationRestricted` | editable |
| AB | 发函情况 | `confirmationStatus` | editable |

公式列 **12 个** = `E,H,I,J,L,P,Q,R,U,V,W,Y` ✅ 与 Task 2 逐格实测一致。

### 3.2 旧字段的迁移映射（能映的映，不能映的登记丢弃）

| 旧字段 | 处置 | 依据 |
|---|---|---|
| `assetName` | → `investTarget`（B） | 同义 |
| `classification` | → `category`（A） | 同义 |
| `confirmationStatus` | → `confirmationStatus`（AB） | 原样 |
| `openingBalance` | → `openingCost`（C） | 旧单值列按「成本」口径落位（旧数据无三分量拆分信息，落成本是唯一不造假的选择） |
| `openingAdjustment` | → `openingAdjCost`（F） | 同上 |
| `increaseAmount` − `decreaseAmount` | → `periodCost`（M） | 模板 M 列「**借方发生填正数**」⇒ 净额 = 增 − 减 |
| `fvChangeAmount` | → `periodFvChange`（N） | 语义对应 |
| `closingAdjustment` | → `closingAdjCost`（S） | 同 F |
| `openingAdjusted` / `closingBalance` / `closingAdjusted` | **丢弃** | 它们在新模型里是**公式列**（J/R/W 由 C..T 算出）⇒ 迁移时不写入，由公式重算 |
| `interestIncome` | → `closingInterestReceivable`（Z） | 🔴 前端把「股息（损益）」与「应收利息（资产）」合成一个字段；字段名是 `interestIncome`（利息）⇒ 落 Z 更贴近原义，O 列留空由用户补 |

### 3.3 🔴 五组字段**移除**（不是缺映射，是模板体系里不存在）

| 旧字段 | 移除理由 |
|---|---|
| `impairmentLoss` · `impairmentProvision` | 🔴 **会计错误**：G9 是 FVTPL 口径（编制说明 §2 五类全 FVTPL），CAS 22 下 FVTPL **不适用减值模型**（减值属摊余成本与 FVOCI） |
| `ociChange` · `ociCumulative` | 🔴 **会计错误**：FVTPL 的公允价值变动计入**当期损益**，不走 OCI（编制说明明文排除「指定为 FVOCI 的」） |
| `fairValueLevel` · `valuationMethod` | 属**另外两张 sheet**：`公允价值测试表G9-4` 与 `第三层次公允价值计量的调节表G9-5` |
| `instrumentType` · `isDesignated` | 模板用**区标题**表达（R18 强制 FVTPL / R25 指定 FVTPL）+ A 列「类别」 |
| `initialInvestDate` · `maturityDate` · `holdingQuantity` · `faceValueOrCost` · `measurementAttribute` · `isRelatedParty` · `remark` | 模板 G9-2 无这些列。编制说明允许「自行添加项目」但仅举例**外币原币金额与折合汇率**；这些信息属程序表 G9A / 附注披露 / 凭证检查表 G9-6 |

🔴 **移除是破坏性变更**：真库 G9 有 605 B / 1 wp 真实载荷。迁移函数按 §3.2 映射可映射项、
对移除项**在 console 与迁移统计里显式登记丢弃计数**，不静默吞。

---

## 4. 本方案对其余八条的意义

G9 暴露的是**共性问题**：G 循环前端明细表普遍缺「三分量 × 四阶段」这个模板核心模型
（G1 27 列模板 vs 56 前端字段、G10 19 vs 35 是同型）。
⇒ 本 Task 先把 G9 做成范式（行模型 + 两级表头渲染 + 公式引擎 + 迁移 + provider 声明 + 判据），
Task 9~14 逐条照此推。每条都必须**先读该册模板的编制说明**再改前端 —— 各册业务口径不同
（如 G6 其他债权投资是 FVOCI 口径，**有** OCI 与减值列；G9 没有）。
