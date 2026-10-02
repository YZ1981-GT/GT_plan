# C-6 · 余八条模板编制思路调研

spec: `g-cycle-single-region-detail-lanes` · C-6 · 2026-09-27

G9 已按选项 C 根治（`task8-option-c-g9-rootfix.md`）。本文对余八条
（G10 / G8 / G14 / G11 / G13 / G12 / G3 / G1）做同样的**先读模板再动代码**调研，
产出逐条处置方案与工作量重排建议。**本 Task 不改任何生产代码。**

## 0. 方法：三源取数，一源都不省

| 源 | 取法 | 为什么必需 |
|---|---|---|
| ① 模板列模型 | `_g_template_design_probe.py <CODE> geom` 逐格实测表头合并区 + 逐行公式 | 列的**层级归属**只有合并区能说清（`C9:E9 期初余额` 下挂 C/D/E 三分量） |
| ② 编制说明 | `_g_template_design_probe.py <CODE> notes` 倒受管表内文本块 + 册内说明 sheet | 决定「前端某列是缺列还是**会计错误**」—— G9 的 15 列就是靠 A38-A43 判的 |
| ③ 前端字段 | `_g_column_isomorphism_probe.py <CODE>` 解析行接口 | 与 ① 逐列语义对照 |

🔴 **几何不重复研究**：表头行 / 行区 / 行级 mask / footer / 公式列已由 Task 2 固化在
`test_g_single_region_p1_p3_p5_p6.EXPECTED`（本 spec 声明层唯一真源）。本文只做**列语义**。

🔴 **兄弟 sheet 必查**：判「前端独有字段」时不能只说「模板没有」，要给出**它到底属哪张表**。
用 `_g_sibling_sheet_probe.py <册> <sheet>` 落实。不查就会把真实业务字段当垃圾删掉。

---

## 1. 总览：错配分**四类**，不是一个量级

G9 的经验（「前端自研列 vs 模板列」）不能直接外推。实测八条落进四个不同的类：

| 类 | 特征 | 条目 | 处置动作 | 相对工作量 |
|---|---|---|---|---|
| **III 近同构** | 模板列全覆盖；前端多出的是**UI 派生 / 校验**字段（本地算出来的，不是第二份数据） | **G14**(+7) · **G11**(+4) · **G12**(+2) | 只需在后端 `field_specs` 里**不声明**这些派生字段（前端保留），另补模板有而前端缺的公式列 | 🟢 最轻 |
| **I 去范围** | 模板列全覆盖；前端多出的字段**属兄弟 sheet**（另一张底稿的权威列） | **G10**(+16) · **G13**(+9) · **G1**(+30) | 前端删除并登记归属；不受管 | 🟡 中 |
| **II 补分量拆分** | 前端用**单值列**表达模板的「成本 + 累计公允价值变动 + 合计」三分量 | **G8** | 前端行模型拆列（同 G9 的做法），但 G8 是 **FVOCI**，OCI 列**必须保留** | 🟠 重 |
| **IV 整表错位** | 前端整张表做的**不是**受管表的内容，而是兄弟 sheet 的内容 | **G3** | 按模板重建 33 列矩阵；原 30 字段登记移交 G3-4 / G3-5 | 🔴 最重 |

🔴 **关键前提：G1 / G3 两条真库零载荷**（`max_payload_bytes=0`、`wp_count_with_payload=0`，
键根本不存在 —— Task 1 取证 §「G1/G3 是键不存在」）。⇒ 这两条**没有存量数据迁移包袱**：
可直接按模板重建行模型，不必像 G9 那样写 `migrateLegacyRow` + 丢弃计数 + fallback 链。
其余六条有 2 B 空数组载荷，同样无真实行数据。**只有 G9 一条有真实载荷（605 B）** ——
所以「迁移 + fallback 链」那套只在 G9 需要，八条都不需要。这是本次调研最省工的发现。

---

## 2. G10 交易性金融负债（类 I · 19 列 vs 35 字段）

### 2.1 模板列模型：三分量 × 三阶段（比 G9 少一阶段）

```
A 类别   B 项目【按明细项目列示，如债券名称】
C9:E9  期初余额 : C 初始确认金额 · D 累计公允价值变动 · E 公允价值【=C+D】
       F 期初调整数 · G 期初审定数【=E+F】        ← 🔴 调整与审定都是**单列**
H9:J9  本期变动（增加"+"/减少"—"）: H 初始确认金额 · I 本期公允价值变动 · J 计入财务费用的利息
K9:O9  期末余额 : K 初始确认金额【=C+H】 · L 累计公允价值变动【=D+I+J】 · M 公允价值【=K+L】
       N 调整数 · O 审定数【=M+N】
P 到期日  Q 票面利率  R 期末应付利息  S 发行文件索引
```

与 G9 的三处结构差异（照抄 G9 会错）：

1. **调整/审定不拆分量**：G9 是 `F/G 两分量调整 → H/I/J 三分量审定`；G10 是 `F 单列调整 → G 单列审定`。
   负债侧的账项调整不区分成本与公允价值变动。
2. **`L = D + I + J`**（三项相加，含利息 J）。G9 的对应列是 `Q = D + N`（两项）。
   🔴 J「计入财务费用的利息」**进累计公允价值变动**，这是负债特有的：
   交易性金融负债的利息计入财务费用同时增加负债账面价值。
3. **本期变动是净额列**（表头明写「增加"+"/减少"—"」）⇒ 不存在「本期增加 / 本期减少」两列。

编制说明（A31-A34）：「1．编制时应列入交易性金融负债的每一明细账户。2．外币交易性金融负债
应列明原币金额及折合汇率（**自行添加项目**）。」
⇒ 外币列是模板授权的扩展位，但**不在受管列内**（自行添加 = 用户改模板，不是前端字段）。

### 2.2 前端现状：13 个核心列**已经对上**，多出 16 个

`useG10Detail.G10DetailRow` 的 `opening*/movement*/closing*` 命名与模板 C..O **逐列对应**：

| 模板 | 前端 | | 模板 | 前端 |
|---|---|---|---|---|
| A | `liabilityCategory` | | K | `closingInitialAmount` |
| B | `liabilityName` | | L | `closingFvAccum` |
| C | `openingInitialAmount` | | M | `closingFairValue` |
| D | `openingFvAccum` | | N | `closingAdjustment` |
| E | `openingFairValue` | | O | `closingAdjusted` |
| F | `openingAdjustment` | | P | `maturityDate` |
| G | `openingAdjusted` | | Q | `couponRate` |
| H | `movementInitialAmount` | | R | `accruedInterest` |
| I | `movementFvChange` | | S | `issuanceDocIndex` |
| J | `interestExpense` | | | |

**19/19 全覆盖** —— G10 的前端是按模板设计的，只是长期堆积了 16 个冗余字段。

### 2.3 16 个多余字段的逐条归属

| 组 | 字段 | 归属裁决 |
|---|---|---|
| legacy 单值重复（4） | `initialAmount` `openingBalance` `currentIncrease` `closingBalance` | 三分量模型下的旧单值残留，与 C/E/H/M 重复 ⇒ **删** |
| 模板显式无（1） | `currentDecrease` | 模板 H 是净额列（增加"+"/减少"—"）⇒ **删**（拆增减会与 H 双源） |
| 属 `公允价值测试表G10-5` / `第三层次公允价值计量的调节表G10-6`（2） | `fairValueLevel` `valuationMethod` | 权威源在那两张表 ⇒ **删**（同 G9 的同名两列） |
| 属 `衍生金融工具核查表G10-8`（3） | `isDerivative` `hostContractDesc` `embeddedDerivativeJudgment` | 嵌入衍生工具判断是 G10-8 的作业面 ⇒ **删** |
| 模板无且无兄弟表归属（6） | `liabilityType` `counterparty` `contractDate` `profitLossAmount` `confirmationStatus` `remark` | `confirmationStatus`：G10 是**负债**不对外发函（G9 的 AB「发函情况」是资产侧函证）⇒ **删**；余五条为自研补充信息，模板既无列也无「自行添加」授权 ⇒ **删**，需要时走 S 发行文件索引 |

结论：G10 **不需要重建行模型**，只做「删 16 列 + 后端声明 19 列」。
`formula_columns=("E","G","K","L","M","O")`（Task 2 已实测，与本文 §2.1 的公式一致）。

---

## 3. G8 其他权益工具投资（类 II · 23 列 vs 24 字段）

### 3.1 🔴 与 G9 口径**相反**：G8 是 FVOCI，OCI 列是对的

受管表内注释逐字：

- **注1**：「权益工具投资一般不符合本金加利息的合同现金流量特征，因此应当分类为以公允价值
  计量且其变动计入当期损益的金融资产。然而在初始确认时，企业可以将非交易性权益工具投资
  **指定为以公允价值计量且其变动计入其他综合收益**的金融资产。该指定一经作出，**不得撤销**。」
- **注2**：股利收入三个确认条件（权利确立 / 经济利益很可能流入 / 金额可靠计量）。
- **注3**：「终止确认时（包括处置、转为长期股权投资），之前计入其他综合收益的累计利得或损失
  应当**从其他综合收益中转出，计入留存收益**（盈余公积、未分配利润）。」

⇒ G8 模板有三个 OCI 列（F 期初累计 / L 本期转留存 / R 期末累计）是**准则要求**。
🔴 **绝不可照抄 G9 的移除清单**（G9 删 OCI 是因为 G9 全 FVTPL）。同理 G6（其他债权投资）也是
FVOCI 口径，C-6 之后若触及 G6 同样保留 OCI。

### 3.2 模板列模型：三分量 + OCI 旁列 × 四阶段

```
A 被投资单位名称   B 投资比例
C9:F10 期初余额 : C 成本 · D 累计公允价值变动 · E 合计【=SUM(C:D)】 · F 计入OCI的累计利得或损失
       G 期初调整数 · H 期初审定数【=E+G】
I9:N10 本期变动 : I 成本 · J 本期公允价值变动 · K 处置时公允价值变动结转
                  L 其他综合收益转入留存收益 · M 合计【=SUM(I:K) 或 SUM(I:L)，见 §3.3】
                  N 本期确认的股利收入
O9:R10 期末余额 : O 成本【=C+I】 · P 累计公允价值变动【=D+J 或 D+J+K，见 §3.3】
                  Q 合计【=SUM(O:P)】 · R 计入OCI的累计利得或损失【=F+J+L】
       S 调整数 · T 审定数【=Q+S】
U 指定为FVOCI的原因   V 其他综合收益转入留存收益的原因   W 发函情况
```

`N 本期确认的股利收入`是**损益项**，与 G9 的 `O 计入投资收益的股息` 同理：不进任何余额公式。

### 3.3 🔴 模板自身的行级不一致（Task 2 已实测为三段，本文给出会计判读）

| 行 | M（本期变动合计） | P（期末累计公允价值变动） | T（审定数） |
|---|---|---|---|
| R11 | `=SUM(I11:L11)` ← **含 L** | `=D11+J11` | 有 |
| R12 | `=SUM(I12:K12)` | `=D12+J12+K12` ← **含 K** | **缺** |
| R13..R20 | `=SUM(I:K)` | `=D+J` | 有 |

会计上判读：

- **M 应含 L**（本期变动合计 = 成本变动 + 公允价值变动 + 处置结转 + OCI 转留存）⇒ R11 对、其余漏 L；
- **P 应含 K**（期末累计公允价值变动 = 期初累计 + 本期变动 + 处置结转，K 为负）⇒ R12 对、其余漏 K；
- **T 每行都该有** ⇒ R12 缺 T 是遗漏。

即 **R11 与 R12 各对一半，R13..R20 两处都漏**。这与 G5 的「三段合计各漏加一个小计」同族
（本 spec 已确立的规则：**模板真实缺陷走覆盖层，不改模板字节**；FC-5「以模板为权威」
只适用于两边都对、口径不同的情形）。

⇒ 处置：Task 9（C-7）按 Task 2 的三段 `row_segments` 声明受管区，**并在覆盖层补齐**
`M=SUM(I:L)` 与 `P=D+J+K` 到全部 R11-R20；同时给 R12 补 T。三段 mask 仍按实测声明
（判据 P12 要求证明「R13 的 R 列与 R12 的 T 列不被误标」）。

### 3.4 前端现状：三分量**没有拆**

| 模板 | 前端 | 判定 |
|---|---|---|
| A / B | `investeeName` / `investmentRatio` | ✅ |
| C 成本 · D 累计FV变动 · E 合计 | `openingBalance`（**单值**） | 🔴 缺拆分量 ⇒ 补 3 列 |
| F 期初 OCI 累计 | `ociOpeningCumulative` | ✅ |
| G / H | `openingAdjustment` / `openingAdjusted` | ✅ |
| I 成本 | `increaseAmount` + `decreaseAmount`（**拆了增减**） | 🔴 模板 I 是净额单列 ⇒ 合并成一列 |
| J 本期FV变动 | `fvChangeAmount` | ✅ |
| K 处置时公允价值变动结转 | — | 🔴 **缺列** ⇒ 补 |
| L OCI 转留存 | `ociToRetainedEarnings` | ✅ |
| M 本期变动合计 | — | 公式列，引擎声明 |
| N 本期确认的股利收入 | — | 🔴 **缺列** ⇒ 补 |
| O 成本 · P 累计FV变动 · Q 合计 | `closingBalance`（**单值**） | 🔴 缺拆分量 ⇒ 补 3 列 |
| R 期末 OCI 累计 | `ociCumulativeChange` / `ociCurrentChange` 语义含混 | 🔴 需对齐：R 是**期末累计**（`=F+J+L`），前端两字段名无一对应 |
| S / T | `closingAdjustment` / `closingAdjusted` | ✅ |
| U / V / W | `designationReason` / `transferReason` / `confirmationStatus` | ✅ |
| — | `fairValueLevel` `valuationMethod` `shareCount` `pricePerShare` `fairValueTotal` | 属 `公允价值测试表G8-4` ⇒ **删 5** |
| — | `remark` | 模板无 ⇒ 删 |

⇒ G8 需要**真重建**（补 3+3+2=8 列、合并 1 组、改名对齐 1 列、删 6 列），是八条里唯一
与 G9 同量级的。`23 vs 24` 的接近同样是巧合。

---

## 4. G14 信用减值损失（类 III · 13 列 vs 19 字段）

### 4.1 模板列模型：损益表项 + 减值准备滚动表

```
A 项目                                  ← 🔴 固定行集（G14_LINE_ITEMS），用户不增删
B 本期数/未审数 · C 调整数 · D 审定数【=B+C】
E 对应科目
F9:J10 对应科目-减值准备 : F 期初余额 · G 本期计提 · H 本期转回 · I 本期转销 · J 期末余额【=F+G-H-I】
K 计入损益   L 核对【布尔】   M 索引号
```

结构特点：**左半是损益表（B/C/D）、右半是准备金滚动表（F..J）**，L 核对列就是两侧勾稽
（`K 计入损益` 应等于 `D 审定数`，或 `G-H` 与 D 的关系）。这是全 G 循环唯一的
「一行两套口径 + 布尔勾稽列」形态，也是 `row_identity_key="rowKey"` 的由来
（行集由模板固定 ⇒ 身份是模板行键，不是生成的 uuid，GC-6 已裁决这是**最稳**一族）。

### 4.2 前端现状：13 列基本全覆盖，多出 7 个**派生校验**

| 组 | 字段 | 判定 |
|---|---|---|
| 与模板对应（12） | `provisionAccount`(E) `currentUnadjusted`(B) `currentAdjustment`(C) `currentAudited`(D) `openingProvision`(F) `currentProvision`(G) `currentReversal`(H) `currentWriteoff`(I) `closingProvision`(J) `profitLoss`(K) `reconciled`(L) `indexRef`(M) | ✅（A 列由固定行集的 label 承载，不是数据字段） |
| 🔴 派生校验，**不是第二份数据**（5） | `closingComputed`（按 F+G-H-I 现算，用于与用户填的 `closingProvision` 比对）· `rollForwardVariance` · `rollForwardBalanced` · `tbClosingMatched` · `tbClosingVariance` | 前端本地算出来的校验量 ⇒ **保留在前端，后端 `field_specs` 不声明** |
| 🟡 外部取数（2） | `tbClosing`（从 `trial_balance` 拉的期末余额，只读对比用）· `otherMovement` | `tbClosing` 是跨源比对值不是本表数据 ⇒ 不受管；`otherMovement`（其他变动）模板无对应列 ⇒ **删**或并入 I |

⇒ G14 处置最轻：**不删数据列**，只需
①把 5 个派生 + 1 个外部取数标为不受管（后端不声明即可，前端零改动）；
②裁决 `otherMovement` 去留（模板 J 的公式 `=F+G-H-I` 不含它 ⇒ 留着会让 J 算不平，倾向**删**）。

🔴 布尔列 L 的声明：Task 2 已定 `formula_columns=("D","J","K","L")` 且 L 是布尔公式列
（P9 的三条容错判据守着「布尔列声明为 formula + value_type=boolean」）。

---

## 5. G11 投资收益（类 III · 13 列 vs 16 字段）

### 5.1 模板列模型：本期 / 上年两期对比 + 占比 + 变动

```
A 序号   B 项目   C 被投资单位
D 本期未审数 · E 本期调整 · F 本期审定数【=D+E】 · G 各项目占比【引合计行】
H 上年未审数 · I 上期调整 · J 上年审定数【=H+I】 · K 各项目占比【引合计行】
L 变动额【=F-J】   M 变动原因/索引号
```

🔴 **G/K 占比列引合计行**（`=F10/F$31` 形态）—— Task 5 的 P10 已就「插入行时 `$31` 是否位移」
做过实测裁决；本文不复述，处置沿用 Task 5 结论。

单级表头 R9（全 G 循环唯一）+ 21 行数据区 R10-R30（九条最长）+ R31 合计。
R32「本年利润总额」是手填分析行，**既不是 footer 也不受管**（Task 2 已登记）。

### 5.2 前端现状：近同构，多出 4 个

| 组 | 字段 | 判定 |
|---|---|---|
| 与模板对应（11） | `itemName`(B) `investeeName`(C) `currentUnadjusted`(D) `currentAdjustment`(E) `currentAudited`(F) `currentShare`(G) `priorUnadjusted`(H) `priorAdjustment`(I) `priorAudited`(J) `priorShare`(K) `reasonIndex`(M) | ✅（A 序号由 `seq` 承载） |
| 模板 L 变动额 | `changeAmount` | ✅ |
| 🔴 UI 派生（3） | `changeRate`（变动率，模板**只有变动额没有变动率**）· `changeRateHighlight` · `reasonRequired` | 保留在前端，不受管 |
| 🟡 自研分类（1） | `tradingDisposeSubtype` | 模板无对应列；语义是「交易性金融资产处置子类」⇒ 与 B 项目列重复表达 ⇒ **删**（需要细分走 B 列文本） |

⇒ G11 处置：3 个 UI 派生不受管 + 删 1 个自研分类。核心 13 列直接声明。

---

## 6. G12 净敞口套期收益（类 III · 10 列 vs 10 字段 —— 八条中最接近）

### 6.1 模板列模型

```
A 项目   B 净头寸   C 套期工具
D 套期工具公允价值 / 套期工具累计公允价值变动
E 对应预期销售的部分（计入净敞口套期损益）
F 对应预期采购的部分（套期调整）
G 校验【布尔】
H 套期调整摊销（计入净敞口套期损益）
I 净敞口套期损益【公式】
J 索引号
```

几何三个特例（Task 2 已实测，本文只标注不复述）：表头是 **R7/R8**（不是 R9/R10，整册上移两行）·
布尔校验列 **G 只在 R9 一行**（行级 mask）· 数据区 R9-R13 + footer R14。

### 6.2 前端现状

| 模板 | 前端 | 判定 |
|---|---|---|
| A / B / C | `item` / `netPosition` / `hedgingInstrument` | ✅ |
| D | `instrumentFvCumulative` | ✅ |
| E / F | `salesPortion` / `purchasePortion` | ✅ |
| G 校验 | — | 公式列（布尔），引擎声明，前端无需字段 |
| H | `hedgeAdjAmortization` | ✅ |
| I 净敞口套期损益 | — | 公式列，引擎声明 |
| J | `indexRef` | ✅ |
| — | `rowKind` | 前端行类型标记（UI 分组）⇒ 不受管 |
| — | `remark` | 模板无 ⇒ 删 |

⇒ G12 **零列改动**：8 个数据列直接对上，2 个公式列由引擎声明，`rowKind` 不受管、`remark` 删。
是八条里最快能接的一条。

---

## 7. G13 公允价值变动收益（类 I · 12 列 vs 21 字段）

### 7.1 模板列模型：与 G14 同构（损益表项 + 对应科目明细）

```
A 项目
B 本期数/未审数 · C 调整数 · D 审定数【=B+C】
E 对应科目
F9:I10 对应科目-公允价值变动 : F 成本 · G 本期公允价值变动 · H 累计公允价值变动 · I 公允价值【=F+H】
J 计入损益   K 核对【布尔】   L 索引号
```

🔴 G13 与 G14 是**同一张骨架**（`A/B/C/D/E + 明细块 + 计入损益 + 核对 + 索引号`），
差别只在明细块：G14 是准备金滚动（期初/计提/转回/转销/期末），G13 是公允价值三分量。
⇒ 两条的后端声明可共用同一套结构性理解，但**不可共用 formula_columns**。

几何特例（Task 2 已实测）：**父子行三段** —— 父行只有 R11/R14/R17（B/C 为公式，汇总子行）·
子行 R12/R13/R15/R16/R18 · R19/R20 是**无子行的顶层手填行**（把它们的 B/C 判成 formula
会覆盖用户手填值）。

### 7.2 前端现状：12 列全覆盖，多出 9 个

| 组 | 字段 | 判定 |
|---|---|---|
| 与模板对应（12） | `instrumentName`(A) `currentUnadjusted`(B) `adjustment`(C) `currentAudited`(D) `belongAccount`(E) `cost`(F) `periodFvChange`(G) `cumulativeFvChange`(H) `fairValue`(I) `amountInPl`(J) `crossVerification`(K) `sourceIndex`(L) | ✅ |
| 🔴 legacy 单值三连（3） | `openingFairValue` `closingFairValue` `fvChange` | 与 F/G/H/I 表达同一事实的旧形态 ⇒ **删**（留着就是第二真源） |
| 🔴 UI 派生（4） | `fvReconciled` `bsReconciled` `plReconciled` `allReconciled` | 模板只有 **K 一个**核对列；前端拆四个是本地分项校验 ⇒ 保留不受管，K 由引擎声明 |
| 🟡 自研（2） | `instrumentType` `remark` | 模板无 ⇒ 删 |

⇒ G13 处置：删 5（legacy 3 + 自研 2）+ 4 个 UI 派生不受管。

---

## 8. G3 应收股利（类 IV · 33 列 vs 32 字段 —— 整表错位，最严重）

### 8.1 模板列模型：**三块 × 四阶段 × 四时点**矩阵（G 循环最复杂的列模型）

```
A 项目   B （空列，模板保留）
账面余额块：
  C9:F   未审数   : C 期初数 · D 本期增加 · E 本期减少 · F 期末数
  G/H    期初调整 : G 账项调整 · H 重分类调整
  I/J    账项调整 : I 本期增加 · J 本期减少
  K/L    重分类调整: K 本期增加 · L 本期减少
  M9:P   审定数   : M 期初数 · N 本期增加 · O 本期减少 · P 期末数
减值准备块：
  Q9:T   未审数   : Q 期初数 · R 本期增加 · S 本期减少 · T 期末数
  U/V    期初调整 : U 账项调整 · V 重分类调整
  W/X    账项调整 : W 本期增加 · X 本期减少
  Y/Z    重分类调整: Y 本期增加 · Z 本期减少
  AA9:AD 审定数   : AA 期初数 · AB 本期增加 · AC 本期减少 · AD 期末数
账面价值块：
  AE 审定数/期初数 · AF 期末数
AG 备注
```

三级表头 R9/R10/R11（全 G 循环唯一）· 两个受管区 R13-R20 与 R23-R28 · footer R21/R29/R30。
有效列 **A..AF = 32**（`AG` 属 R3/R9 索引区，Task 2 已把 spec 原写的 33 修正为 32）。

### 8.2 🔴 前端做的是**另外两张表**的内容

`useG3Detail.DividendDetailRow` 32 个字段里，与模板列**能对上的只有 2 个**：
`investeeName`↔A（且模板 A 叫「项目」不是被投资单位）与 `remark`↔AG。

其余 30 个字段实测归属（`_g_sibling_sheet_probe.py` 逐格核）：

| 前端字段 | 真实归属 | 兄弟表实测列 |
|---|---|---|
| `shareholdingRatio` | **测算及检查表G3-4** | `C 持股比例①` |
| `declarationDate` | 同上 | `D 宣告分派股利日` |
| `dividendPlan` | 同上 | `E 主要股利分配政策` |
| `totalDividend` | 同上 | `F 被投资项目股利分配总额②` |
| `dividendReceivable` | 同上 | `G 按持股比例计算应计股利③＝①*②`（公式列） |
| `payoutRatio` / `dps` | 同上（派生） | G3-4 用 ①*② 直算，不设每股股利列 |
| `receivedAmount` `receiptDate` `receiptMethod` | **长期未收回款项检查表G3-5** | `L 期后收款金额` / `C 本期借方发生额` 等 |
| `isOverdue` `overdueDays` | 同上 | `F 账龄` + `H 未收回或未结转的原因` + `I 是否无法收回` |
| `socialCreditCode` `registeredCapital` `industry` `investType` `initialCost` `investDate` `sharesHeld` `investeeNetProfit` `investeeNetAssets` `equityShare` `bookValue` `accountingMethod` `isListed` `listingCode` `resolutionDate` `recordDate` `exDividendDate` `netReceivable` | **G3 册内无对应表** | 属长期股权投资台账口径（G 循环 G3 不含），模板三张表都没有 |

⇒ 结论：**前端 G3-2 tab 实际是一张自研的「应收股利台账」，而不是模板的应收股利明细表。**

### 8.3 处置裁决

1. 真库 `G3-2-detail-rows` **键不存在**（0 载荷）⇒ 这张自研台账**从未被使用过**，
   重建**无数据迁移风险**、也无用户存量工作成果需要保护。
2. `useG3Detail` 按模板 32 列重建（三块 × 四阶段矩阵 + 两区）。
3. 30 个自研字段里，**7 个有兄弟表归属**（G3-4 的 5 个 + G3-5 的 2 组）⇒ 登记给
   后置 spec（G3-4 / G3-5 两张表本身不在本 spec 受管范围）；其余 18 个无归属者直接删。
4. 🔴 **这一条的 UI 变化最大**（32 个字段的表单整体换掉）。虽然零载荷说明没人在用，
   但它是**用户可见 UI 的整体替换**，建议在 C-10 动手前向用户单独确认一次。

---

## 9. G1 交易性金融资产（类 I · 27 列 vs 56 字段）

### 9.1 模板列模型：与 G9 **近同构**（同为三分量 × 四阶段 + 三区）

```
A 类别   B 投资项目【按明细项目列示，如证券名称或被投资单位名称】
C/D/E    期初余额     : 成本 · 累计公允价值变动 · 公允价值【=C+D】
F/G      期初账项调整 : 成本 · 公允价值变动
H/I/J    期初审定数   : 成本【=C+F】· 累计公允价值变动【=D+G】· 公允价值【=H+I】
K        减：期初超过一年到期的部分          ← 🔴 G9 无此列（G9 的 K 是「期初重分类数」）
L        期初报表数【=J+K 或 =E+K】
M/N/O    本期变动（增加为正数）: 成本 · 本期公允价值变动 · 计入投资收益的股息
P/Q/R    期末余额     : 成本【=C+M】· 累计公允价值变动【=D+N】· 公允价值【=P+Q】
S/T      账项调整     : 成本 · 公允价值变动   ← 🔴 区① 的 T 引 `公允价值测试表G1-6`（跨表）
U/V/W    期末审定数   : 成本 · 累计公允价值变动 · 公允价值
X        减：超过一年到期的部分
Y        期末报表数
Z        变现是否存在限制      AA 是否函证
```

与 G9 的差异（三条，照抄 G9 会错）：

1. **K/X 是「超过一年到期的部分」而不是 G9 的「重分类数」** —— 语义完全不同：
   G1 是流动/非流动划分（一年期），G9 是重分类。
2. **G1 无「期末应收利息」列**（G9 有 Z）。原因在注1 逐字：
   「相关金融工具已到期可收取但于资产负债表日尚未收到的利息在**"应收利息"**反映」
   ⇒ G1 把它推给 G2 应收利息底稿。
3. **区① 多一个跨表 T 列**（引 `公允价值测试表G1-6`），区②③ 不含 ⇒ 行级 mask
   （Task 2 已实测为 `r1` 13 列含 T / `r2`·`r3` 12 列）。P6 断言 G1 与 G9 的
   `formula_columns` **不得相等**，就是钉这一条。

三区标题逐字（与 G9 三区同构）：R11 区① 交易性金融资产 · **R18**「划分为以公允价值计量且其变动
计入当期损益的金融资产」· **R25**「指定为以公允价值计量且其变动计入当期损益的金融资产」。
编制说明 A44-A48 列出五类全 FVTPL（与 G9 的 A38-A43 同源）⇒ **G1 同样不确认 OCI、不计提减值**。
A40 另有附注合并披露提示（区①与区② 在附注合并披露为一项）。

### 9.2 前端现状：27 列**已全覆盖**，多出约 30 个

前端 `TradingDetailRow` 的四阶段命名与模板逐列对应（10 + 3 + 10 + 2 ≈ 25 列）：
`openingCost`(C) `openingCumulativeFv`(D) `openingFairValue`(E) `openingCostAdj`(F) `openingFvAdj`(G)
`auditedOpeningCost`(H) `auditedOpeningCumulativeFv`(I) `auditedOpeningFvTotal`(J) `openingLtDeduction`(K)
`openingReported`(L) · `addedCost`(M) `periodFvChange`(N) `dividendIncome`(O) ·
`closingCost`(P) `cumulativeFVChange`(Q) `closingFairValue`(R) `closingCostAdj`(S) `closingFvAdj`(T)
`auditedClosingCost`(U) `auditedClosingCumulativeFv`(V) `auditedClosingFvTotal`(W) `closingLtDeduction`(X)
`closingReported`(Y) · `acctClass`(A) `securityName`(B) `realizationRestricted`(Z)。
AA「是否函证」前端缺（`pledged` 不是它）⇒ **补 1 列**。

多出的字段按归属分五族：

| 族 | 字段 | 归属 |
|---|---|---|
| 数量与单价（5） | `openingQuantity` `boughtQuantity` `soldQuantity` `closingQuantity` `unitFairValue` | `有价证券监盘表G1-11` / `有价证券盘点倒轧表G1-12` / `公允价值测试表G1-6` |
| 处置与收益测算（5） | `disposalProceeds` `disposalCost` `realizedGain` `totalIncome` `fvChangeInPL` | `收益测算表G1-5` |
| 调整与勾稽（6） | `unadjusted` `aje` `rje` `adjusted` `variance` `rollForwardDiff` | `调整分录汇总G1-3` + `审定表G1-1` |
| 公允价值来源（3） | `fairValueSource` `fairValueChange` `quoteDate` | `公允价值测试表G1-6`（T 列已经是引它的跨表列） |
| 基本信息（8） | `securityCode` `investType` `market` `acquisitionDate` `initialCost` `originalCurrency` `exchangeRate` `pledged` | 模板无列；`originalCurrency`/`exchangeRate` 属编制说明「外币…自行添加项目」授权位，但那是用户改模板 ⇒ 不受管 |
| 其他（2） | `reducedCost`（模板 M 是净额「增加为正数」单列）· `remark` | 删 |

⇒ G1 与 G10 同类：**不需要重建**，做「删约 29 列 + 补 AA 列 + 后端声明 27 列（区① 13 / 区②③ 12）」。
真库零载荷 ⇒ 无迁移包袱。

---

## 10. 工作量重排：原 lane 顺序按几何复杂度，本文按**处置类别**建议重排

原顺序（design §Architecture，由**几何**易到难）：`G9 → G10 → G8 → G14 → G11 → G13 → G12 → G3 → G1`。
按**列模型处置量**重排后（G9 已完成，不动）：

| 新序 | 条 | 类 | 前端动作 | 后端动作 |
|---|---|---|---|---|
| 1 | **G12** | III | 删 1（`remark`）· `rowKind` 不受管 | 10 列声明 + 2 公式列（含布尔 G，行级 mask r9/r10plus） |
| 2 | **G14** | III | 删 1（`otherMovement`）· 6 个派生不受管 | 13 列 + `rowKey` 固定行集 + 布尔列 L |
| 3 | **G11** | III | 删 1（`tradingDisposeSubtype`）· 3 个派生不受管 | 13 列 + 单级表头 + 21 行 + G/K 占比列（按 Task 5 P10 结论） |
| 4 | **G10** | I | 删 16 | 19 列 + 6 公式列 |
| 5 | **G13** | I | 删 5 · 4 个派生不受管 | 12 列 + 父子行三段 |
| 6 | **G1** | I | 删 ~29 + 补 1（AA 是否函证） | 27 列 + 三区 + 区① 跨表 T 列 |
| 7 | **G8** | II | 补 8 · 合并 1 组 · 改名 1 · 删 6 | 23 列 + 三段行级 mask + **模板缺陷覆盖层**（M/P/T） |
| 8 | **G3** | IV | **整表重建** 32 列 · 30 字段登记移交 | 32 列 + 三级表头 + 两区 |

🔴 **是否真的重排需要用户拍板**：重排能让「一次就能完整做完一条」的轻量条先落地、
先把范式打磨稳（类 III 三条几乎不改前端，能快速验证后端多区/布尔列/占比列三个未验通的点），
但会打乱 tasks.md 里 Task 9~14 的既有编号与 `_Requirements_` 对应关系。
保守做法是**保留原 tasks.md 顺序**（G10+G8 → G14+G11 → G13+G12 → G3+G1），
代价是第二步就撞上最重的 G8（类 II）。

本文**不擅自改 tasks.md 的任务顺序**，只把两种走法与代价摆出来。

---

## 11. 逐条处置一览（供 C-7~C-10 直接取用）

| 条 | 模板列 | 前端字段 | 删 | 补 | 改名/合并 | 派生不受管 | 是否重建 |
|---|---|---|---|---|---|---|---|
| G12 | 10 | 10 | 1 | 0 | 0 | 1 | 否 |
| G14 | 13 | 19 | 1 | 0 | 0 | 6 | 否 |
| G11 | 13 | 16 | 1 | 0 | 0 | 3 | 否 |
| G10 | 19 | 35 | 16 | 0 | 0 | 0 | 否 |
| G13 | 12 | 21 | 5 | 0 | 0 | 4 | 否 |
| G1 | 27 | 56 | ~29 | 1 | 0 | 0 | 否 |
| G8 | 23 | 24 | 6 | 8 | 2 | 0 | **是** |
| G3 | 32 | 32 | 30（7 条登记移交） | 32 | — | 0 | **是（整表）** |
| *(G9 已完成)* | 28 | 30→28 | 15 | 13 | — | 0 | 是 |

---

## 12. 与 G9 相比要**反向**注意的四条

1. 🔴 **G8 是 FVOCI，OCI 列必须保留**。G9 删 OCI 的依据是「五类全 FVTPL」，
   G8 的注1/注3 明确 FVOCI 指定与 OCI 转留存 ⇒ 依据相反，结论相反。G6 同理。
2. 🔴 **只有 G9 有真实载荷（605 B）**。八条中 G1/G3 是键不存在、其余六条 2 B 空数组
   ⇒ `migrateLegacyRow` + `DROPPED_LEGACY_FIELDS` + 跨表 fallback 链那一整套**只在 G9 需要**。
   八条直接按模板定义行模型即可，别照抄 G9 的迁移层（那是为保 605 B 存量数据写的）。
3. 🔴 **「删列」前必须落实兄弟表归属**。本文 30+16+9+5 条删除项里，绝大多数能指名归属
   （G1-5/G1-6/G1-11/G1-12/G1-3、G10-5/G10-6/G10-8、G8-4、G13 无、G3-4/G3-5）。
   指不出归属的才是真冗余。不查就删会把真实作业面删掉。
4. 🔴 **「派生校验」与「第二真源」要分清**。G14 的 `closingComputed`、G13 的四个 `*Reconciled`、
   G11 的 `changeRate` 都是前端本地现算的校验量 ⇒ **保留在前端但不受管**（后端不声明即可，
   前端零改动）。而 G13 的 `openingFairValue/closingFairValue/fvChange` 与 G10 的
   `openingBalance/closingBalance` 是**存了一份同事实的旧列** ⇒ 必须删。
   判据：能否由本表其它受管列**纯函数算出**。能 ⇒ 派生；不能且与某受管列表达同一事实 ⇒ 旧列。

---

## 13. 复用件

- `backend/scripts/analyze/_g_template_design_probe.py`（新建，C-7~C-10 每条都要用）
  - 无参 = 列九册 sheet 名与受管表标记
  - `<CODE> notes` = 倒编制说明 + 受管表内文本块（判会计口径）
  - `<CODE> geom` = 合并区 + 逐行摘要 + 公式列聚合
- `backend/scripts/analyze/_g_sibling_sheet_probe.py`（新建）：倒兄弟 sheet 表头，落实字段归属
- `backend/scripts/analyze/_g_column_isomorphism_probe.py`（Task 8 留存）：列数普查 + 逐条对照

三个都是 `_` 前缀一次性件，**C-11 收口时一并删除**。
