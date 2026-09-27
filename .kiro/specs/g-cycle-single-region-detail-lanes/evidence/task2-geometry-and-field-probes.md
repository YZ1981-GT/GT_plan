# Task 2 证据：逐条几何实测 + BP-7 五条按值定位 + 三处前端字段核

spec `g-cycle-single-region-detail-lanes` · Task 2 · _Requirements: 1.1, 1.3, 2.1, 2.2, 2.3, 2.4, 3.1, 3.5_
实测 2026-09-27 · openpyxl 逐格（`data_only=False`）+ 前端按值 grep
探针：`backend/scripts/analyze/_g_single_region_geometry.py`（几何）· `_g_bp7_row_identity_probe.py`（行身份）

---

## 🔴 结论摘要：六处推翻/修正 spec + 九处新发现

| # | spec 原文 | 实测事实 | 对后续 Task 的影响 |
|---|---|---|---|
| **A** | G12「**无表头行**（R9 即数据）」＋整套裁决 G1R-H2 | 🔴 **G12 是 R7/R8 两级表头 + R9 起数据**（整册上移两行） | 裁决 G1R-H2 **前提不成立**；框架层**无需**加 `has_header_row`；Task 0 §1.1 的缺口对 G12 不适用；Task 13 大幅简化 |
| **B** | G8 行级 mask 拆两段 `g802-r11` + `g802-r12plus`(R12-20) | 🔴 **三段**：R11 / R12 / R13-20；R12 与 R13-20 差 **R vs T 两列 + M 区间 + P 公式** | 裁决 G1R-H3 的**备选分支（三 spec）是唯一正确解** |
| **C** | G13 父行 = R11/R14/R17/**R19/R20** 五行 | 🔴 父行只有 **R11/R14/R17** 三行（B/C 为公式）；R19/R20 是**无子行的顶层行**（B/C 手填） | Task 12 的 `mode=formula` 只加三行；**G13 也有行级 mask** |
| **D** | 「BP-7 在 slice 的 blocked_by 里出现在 G3/G10/G11/G12/G13 **五条**」 | 🔴 slice 实际标**六条**（含 G1）；按值实测**只有 G1/G3 两条真命中**，G10/G11/G12/G13 **四条无缺陷** | Task 7 只修两条 + 登记四条 slice 误标 |
| **E** | G14 footer 「R20 `SUM(B11:B19)`」 | 🔴 **L20 = `=D20=K20` 是布尔**（不是 SUM）；B/C/D/F/G/H/I/J/K 才是 SUM | P9 须覆盖 **footer 行的布尔列** |
| **F** | G11 占比列「引合计行 **F31**」 | 🔴 G 引 `$F$31`、**K 引 `$J$31`**（两个不同分母） | P10 实测判据须覆盖两列各自分母 |

| # | 新发现（spec 未预见） |
|---|---|
| **G** | 🔴 **G12 两处模板真实缺陷**：`B14 = =SUM(B9,B12,B13:B13)` **漏加 B10/B11**；`I14 = =SUM(I7:I13)` 起点越到**表头行 R7** |
| **H** | 🔴 **G12 也有行级 mask**：R9 公式 `G+I`、R10 只有 `I` ⇒ 布尔校验列只在 **R9 一行** |
| **I** | 🔴 **G13 前端动态增删行 vs 模板固定 10 行业务项 + 父子结构** = 结构性错配（前端无父子字段、`instrumentName` 用户自填） |
| **J** | G11 是**混合形态**：骨架行 `id="g11d-sk-{rowKey}"`（确定性、`isSkeleton` 不可删）+ 用户增行 id 随机；`rowKey` 与 G11-1 审定表对齐 |
| **K** | G11 **R32 `本年利润总额`** 是 footer 之后的手填分析行（spec 未提），无公式、不在受管区 |
| **L** | G1/G3/G9 有**区标题行**（G1/G9 的 R11/R18/R25 · G3 的 R12/R22），不在受管区 |
| **M** | G3 definedNames 现算 **491**（spec 说「约 480」）；G1 现算 **0** |
| **N** | 顺带：`useG12FairValueTest.ts#L35 genId()` 无随机后缀（`G12-fv-test-rows`，非本 spec 主表）⇒ 登记不修 |
| **O** | G3 主表缺随机后缀，但**同册** `useG3OverdueCheck.ts#L134` / `useG3CalcCheck.ts#L265` 都带 `Math.random()` ⇒ 同册已有正确范式，**主表是偏离方** |

---

## 1. 九条主受管表几何逐格实测

| entry | sheet | max_row / max_col / merged | 表头 | 区标题行 | 数据区 | footer | 有效列 |
|---|---|---|---|---|---|---|---|
| G1 | `明细表G1-2` | 52 / 35 / 19 | R9 / R10 | R11 · R18 · R25 | **三区** R12-16 / R19-23 / R26-28 | 小计 R17/R24/R29 + 合计 R30 | A..AA = **27** ✅ |
| G3 | `明细表G3-2` | 38 / 33 / 24 | 🔴 **R9 / R10 / R11 三级** | R12 · R22 | 两区 R13-20 / R23-28 | 小计 R21/R29 + 合计 R30 | A..AF = **32**（spec 写 33/A-AG 偏大一列，AG 是 R3/R9 索引区） |
| G8 | `明细表G8-2` | 39 / 24 / 16 | R9 / R10 | 无 | R11-20 | R21 | A..W = **23** ✅ |
| G9 | `明细表G9-2` | 47 / 28 / 20 | R9 / R10 | R11 · R18 · R25 | 三区 R12-16 / R19-23 / R26-28 | 小计 R17/R24/R29 + 合计 R30 | A..AB = **28** ✅ |
| G10 | `明细表G10-2` | 38 / 24 / 11 | R9 / R10 | 无 | R11-20 | R21 | A..S = **19** ✅ |
| G11 | `明细分析表G11-2` | 39 / 13 / 4 | **R9 单级** | 无 | R10-30（21 行） | R31（+ 🔴 R32 手填分析行） | A..M = **13** ✅ |
| G12 | `明细表G12-2` | 25 / 15 / 9 | 🔴 **R7 / R8 两级**（非「无表头」） | 无 | **R9-13**（R9/R10 有预填、R11-13 空） | R14 | A..J = **10** ✅ |
| G13 | `明细表G13-2` | 34 / 12 / 8 | R9 / R10 | 无 | R11-20 | R21 | A..L = **12** ✅ |
| G14 | `明细表G14-2` | 36 / 13 / 8 | R9 / R10 | 无 | R11-19（9 行固定行集） | R20 | A..M = **13** ✅ |

### 1.1 🔴 发现 A：G12 不是「无表头行」，是 R7/R8 两级表头

逐格实测（`_g_single_region_geometry.py sum G12`）：

```
R7   A='项目'                        V[A,B,C,D,H,I,J]      ← 表头组行
R8   A=None                         V[D,E,F,G]            ← 表头叶子行
R9   A='预期销售和预期采购的外汇净头寸'   F[G,I]  V[A,B,C,D,E,F]  ← 第一行数据
R10  A='预期销售和预期采购的外汇净头寸'   F[I]    V[A,H]          ← 第二行数据
R11-13  全空                                                ← 预画空行
R14  A='合计'                        F[B,C,D,E,F,G,I,J]
```

**错因还原**：spec 假定 G 循环主表统一是「R9/R10 表头 + R11 起数据」，见到 G12 的 R9 有业务文本
就判「无表头行」。实际 G12 整册比同族**上移两行**（无「一、审计目标」的三行段，`R5='一、审计目标:'`
`R6='二、审计过程：'` 紧挨），表头落在 R7/R8。

**⇒ 对 G12 的正确声明（Task 13 用）**：
```python
header_group_row=7, header_leaf_row=8, first_data_row=9, last_data_row=13, footer_row=14
```
框架层 `spec_to_contract_sheet_payload` 的两级表头分支（`header_leaf_row - header_group_row + 1 = 2`）
**完全支持** ⇒ 🔴 **Task 0 §1.1 登记的「无表头语义静默回落」缺口对 G12 不再适用**，
`has_header_row` 字段**本 spec 不需要新增**（避免为不存在的问题改引擎核心文件，正好躲开并发冲突面）。

🔴 **对 `g4-g6` spec 的交棒**：G6-5 是否真「无表头行」**须同法逐格重测**（该 spec 的判断可能同源于
同一个「R9/R10 表头」假定）。本 spec 不代它裁决，只把方法与错因交出去。

---

## 2. 逐行公式集（行级 mask 判定的唯一依据）

### 2.1 G1：区① 含 T、区②③ 不含 —— ✅ 红基线 B2 完全验证

| 行 | 公式列 | T 列 |
|---|---|---|
| R12-16（区①） | `E,H,I,J,L,P,Q,R,`**`T`**`,U,V,W,Y` | 🔴 **有** |
| R19-23（区②） | `E,H,I,J,L,P,Q,R,U,V,W,Y` | 无 |
| R26-28（区③） | `E,H,I,J,L,P,Q,R,U,V,W,Y` | 无 |

跨表公式逐行递增（openpyxl 实测）：
```
T12 = ='公允价值测试表G1-6'!H10-'明细表G1-2'!R12
T13 = ='公允价值测试表G1-6'!H11-'明细表G1-2'!R13
T16 = ='公允价值测试表G1-6'!H14-'明细表G1-2'!R16
```
⇒ 区① 五行逐行对应 G1-6 的 H10..H14。**`公允价值测试表G1-6` 是 BP-5 修后的真名**（Task 0 §2.1 已证
该条 HEAD 上本就正确）⇒ 契约 `source_ref` 可信。

### 2.2 G9：三区列集完全一致，**无 T** —— ✅ P6 断言成立

三区（R12-16 / R19-23 / R26-28）公式列全为 `E,H,I,J,L,P,Q,R,U,V,W,Y`（12 列），逐行同型。

🔴 **G1 区②③ 的列集与 G9 三区完全相同**，差异**只在 G1 区① 多一个 T** ⇒
P6「两条 `formula_columns` 集合不相等」成立，且不等点是**唯一一个元素 T**（判据须精确到这一点，
不能只断言「集合不等」—— 那会被任何无关差异蒙混过关）。

### 2.3 🔴 G8：三段不是两段 —— 发现 B（推翻裁决 G1R-H3 的默认方案）

| 行 | 公式列 | `M` 列 | `P` 列 | `R` | `T` |
|---|---|---|---|---|---|
| **R11** | `E,H,M,O,P,Q,R,T` | `=SUM(I11:L11)` **含 L** | `=D11+J11` | ✅ | ✅ |
| **R12** | `E,H,M,O,P,Q,R` | `=SUM(I12:K12)` 不含 L | `=D12+J12+`**`K12`** 🔴 多一项 | ✅ | ❌ |
| **R13-20** | `E,H,M,O,P,Q,T` | `=SUM(I13:K13)` | `=D13+J13` | ❌ | ✅ |

spec 裁决 G1R-H3 只列了 R11/R12/R13 三行并据此拆 `r11` + `r12plus`(R12-20)，**漏了 R14-20 与 R13 同型**
（`summary` 实测 R13~R20 八行公式列全为 `E,H,M,O,P,Q,T`）。

**⇒ R12 是独立形态**（M 区间 + P 公式 + 无 T 三处都与 R11/R13 不同）。两段拆法的后果：
- 取并集 ⇒ R12 的 `T` 被误标 formula（手填值被覆盖）、R13-20 的 `R` 被误标 formula（同）
- 取交集 ⇒ R12 的 `R`、R13-20 的 `T` 都不受管（可编辑面缩小到业务不可接受）

🔴 **Task 9 直接走裁决 G1R-H3 里预留的备选分支：三个 spec `g802-r11` / `g802-r12` / `g802-r13plus`**。
不是「保守策略不可接受」，而是**几何本身就是三段**。

### 2.4 🔴 G13：父行三行不是五行 + 也有行级 mask —— 发现 C

| 行 | A 列 | 公式列 | 性质 |
|---|---|---|---|
| R11 | `交易性金融资产` | `B,C,D,I,J,K` | 🔴 **父行**（`B11==B12+B13`、`C11==C12+C13`） |
| R12 | `其中：指定为以公允价值计量…的金融资产` | `D,I,J,K` | 子行（B/C 手填） |
| R13 | `     衍生金融资产` | `D,I,J,K` | 子行 |
| R14 | `交易性金融负债` | `B,C,D,I,J,K` | 🔴 **父行** |
| R15 / R16 | `其中：…金融负债` / `     衍生金融负债` | `D,I,J,K` | 子行 |
| R17 | `其他非流动金融资产` | `B,C,D,I,J,K` | 🔴 **父行** |
| R18 | `其中：指定为…的金融资产` | `D,I,J,K` | 子行 |
| **R19** | `以公允价值计量的投资性房地产` | `D,I,J,K` | 🔴 **顶层独立行**（无子行，B/C **手填**） |
| **R20** | `其他` | `D,I,J,K` | 🔴 **顶层独立行** |
| R21 | `合计` | `B,C,D,I,J,K` | footer |

footer 公式逐字：
```
B21 = =B11+B14+B17+B19+B20      ← 五个顶层行（枚举相加，非 SUM 区间）✅ 与 spec 一致
C21 = =C11+C14+C17+C19+C20
D21 = =D11+D14+D17+D19+D20
I21 = =SUM(I11:I20)   J21 = =SUM(J11:J20)      ← I/J 是 SUM 区间
K21 = =J21=D21                                  ← 🔴 footer 也是布尔
```

⇒ **精确表述**：`B21` 加的是**五个顶层行**，其中 R11/R14/R17 是有子行的父行（B/C 为公式），
R19/R20 是无子行的顶层行（B/C 手填）。spec 说「父行 R11/R14/R17/R19/R20」把两类混了 ——
若照 spec 把 R19/R20 的 B/C 判 `mode=formula`，**用户手填值会被覆盖**（与 G8 误标同型危害）。

⇒ **G13 也需行级 mask**：`B,C` 两列只在 R11/R14/R17 三行是 formula ⇒ 三段
（`g1302-parents`={11,14,17} 非连续 / `g1302-children`={12,13,15,16,18} / `g1302-toplevel`={19,20}）
或按「B/C 列在 R11/R14/R17 为 formula」的行级掩码表达。Task 12 定。

### 2.5 G14：九行同型，无行级 mask —— 但 footer 的 L 列是布尔（发现 E）

| 行 | 公式列 |
|---|---|
| R11-19（9 行） | `D,J,K,L` 逐行同型 ✅ 与 spec 一致 |
| R20（footer） | `B,C,D,F,G,H,I,J,K` 为 SUM + 🔴 **`L20 = =D20=K20` 是布尔** |

逐格：`D11 = =B11+C11` · `J11 = =F11+G11-H11-I11` · `K11 = =G11+H11` · **`L11 = =D11=K11`**（布尔 ✅）

⇒ spec 写「R20 `SUM(B11:B19)`」只覆盖 B 列。**P9 的布尔容错三判据须同时覆盖 `L11:L19` 与 `L20`**
（footer 行虽不在受管区，但 materialize/verify 会读它，布尔值读回同样要容错）。

### 2.6 🔴 G12：布尔列只在 R9 一行 + 两处模板真实缺陷（发现 G / H）

```
R9 :  G9 = =D9=SUM(E9:F9)      ← 布尔校验列
      I9 = =E9+H9
R10:  I10 = =E10+H10            ← 🔴 无 G 列公式
R14:  B14 = =SUM(B9,B12,B13:B13)   🔴 漏加 B10 / B11
      C14 = =SUM(C9:C13)  D14 = =SUM(D9:D13)  E14 = =SUM(E9:E13)
      F14 = =SUM(F9:F13)  G14 = =SUM(G9:G13)  J14 = =SUM(J9:J13)
      I14 = =SUM(I7:I13)          🔴 起点 R7 = 表头组行
```

两处缺陷的性质（按「模板缺陷走覆盖层不改字节」规则，F 循环已立此例）：
1. **`B14` 漏加 B10/B11**：B 列合计跳过第二行数据（R10）与第一个空行（R11）⇒ 用户在 R10 填 B 列金额，
   合计不计入 ⇒ **数值错**。与 F5-7 的「引越界空区致审定数漏算」同族。
2. **`I14 = SUM(I7:I13)`**：起点越到表头组行 R7。R7 的 I 列是表头文本，SUM 忽略文本 ⇒ **数值上无害**，
   但**区间声明错**（框架层扩张规则按「区间末行 = last_data_row」判定，起点在表头之上是未覆盖形态）。
   Task 5 的 P11 实测插行后该区间变化。

⇒ 🔴 **G12 布尔列只在 R9** ⇒ 与 G8/G13 一样是行级 mask 形态。**三处布尔校验列里有两处（G12 / G13）
同时是行级 mask**，spec 只把 G8 当行级 mask 案例 ⇒ 行级 mask 在九条里是**通例（3/9）不是特例**。

### 2.7 G11：占比列两个分母 + footer 自引 + R32 手填行（发现 F / K）

```
R10:  F10 = =D10+E10
      G10 = =IF(F10=0,0,F10/$F$31)      ← 分母 $F$31
      J10 = =H10+I10
      K10 = =IF(J10=0,0,J10/$J$31)      ← 🔴 分母 $J$31（不是 F31）
      L10 = =F10-J10
R31:  D31..L31 = SUM(x10:x30)
      G31 = =IF(F31=0,0,F31/$F$31)      ← 自引
      K31 = =IF(J31=0,0,J31/$J$31)      ← 自引
R32:  A32='本年利润总额'  V[A,E,G,I,K,L]  F[]   ← 🔴 手填分析行，无公式，不在受管区
```

⇒ spec 只说「引合计行 F31」。**P10 的实测判据须分别验证 `$F$31` 与 `$J$31` 两个分母**在插行后的行为
（若只测 F31，K 列指向错行会漏检）。

### 2.8 G3：三级表头 + 两区 + 枚举相加 footer（✅ 与 spec 一致，一处列数修正）

```
R9   V[A,C,Q,AE,AG]                          ← 一级
R10  V[C,G,I,K,M,Q,U,W,Y,AA,AE]              ← 二级
R11  V[C..AF 全列]                            ← 三级（叶子）
R12  A='1、账龄一年以内的应收股利'              ← 区标题（不受管）
R13-20  F[F,M,N,O,P,T,AA,AB,AC,AD,AE,AF]     ← 区①（8 行同型）
R21  小计  C21 = =SUM(C13:C20)
R22  A='2、账龄一年以上的应收股利'              ← 区标题
R23-28  同上列集                               ← 区②（6 行同型）
R29  小计  C29 = =SUM(C23:C28)
R30  合计  C30 = =C29+C21                     ← 🔴 枚举相加 ✅ 与 spec 一致
```
逐格样例：`F13 = =SUM(C13:D13)-E13` · `M13 = =C13+G13+H13` · `AF13 = =P13-AD13`
`formula_columns` 实测 `F,M,N,O,P,T,AA,AB,AC,AD,AE,AF` ✅ 与 spec 逐列一致。
G3 **无行级 mask**（两区 14 行全同型）。

**definedName 现算（P15 基线）**：`G3 应收股利.xlsx` = **491**（spec 说「约 480」，现算值以本次为准，
🔴 P15 判据须**现算取集合**并逐项比对，不得写死 491 —— GC-10）；`G1 交易性金融资产.xlsx` = **0** ✅

---

## 3. 🔴 BP-7 五条按值定位（裁决 G1R-H7）—— 实测：六条标、两条真命中

探针 `_g_bp7_row_identity_probe.py` 对九条主表 composable 全文扫四类模式。

| entry | composable | slice 标 BP-7 | `ARRAY_INDEX_ID` | `ID_GEN_NO_RANDOM` | 判定 |
|---|---|---|---|---|---|
| **G1** | `useG1Detail.ts` (739 行) | ✅ | 🔴 **L442** | 🔴 **L704** | **真缺陷 ×2** |
| **G3** | `useG3Detail.ts` (388 行) | ✅ | 🔴 **L288** | 🔴 **L358** | **真缺陷 ×2** |
| G10 | `useG10Detail.ts` (654) | ✅ | 0 | 0 | ❌ **slice 误标** |
| G11 | `useG11DetailAnalysis.ts` (527) | ✅ | 0 | 0 | ❌ **slice 误标** |
| G12 | `useG12HedgeDetail.ts` (323) | ✅ | 0 | 0 | ❌ **slice 误标** |
| G13 | `useG13Detail.ts` (486) | ✅ | 0 | 0 | ❌ **slice 误标** |
| G8 | `useG8Detail.ts` (570) | ❌ | 0 | 0 | ✅ 一致 |
| G9 | `useG9Detail.ts` (466) | ❌ | 0 | 0 | ✅ 一致 |
| G14 | `useG14Detail.ts` (326) | ❌ | 0 | 0 | ✅ 一致 |

### 3.1 两条真命中的逐字取证

**G1 `useG1Detail.ts`**
```ts
L439:  return parsed.map((p, i) => {
L442:    ...emptyRow(migrated.id ?? String(i + 1), migrated.seq ?? i + 1),
L704:  enrichDetailRow({ ...emptyRow(`row-${Date.now()}`, seq), securityName: value }),
```
**G3 `useG3Detail.ts`**
```ts
L287:  return parsed.map((p, i) =>
L288:    enrich({ ...emptyRow(p.id ?? String(i + 1), p.seq ?? i + 1), ...p }),
L358:  enrich({ ...emptyRow(`row-${Date.now()}`, seq), investeeName: value }),
```

**两层病灶（同一处代码）**：
1. **载入路径（BP-7 本体）**：`id ?? String(i + 1)` ⇒ 存量缺 id 的行身份**就是数组下标**
   （`"1"` / `"2"` / …）。🔴 **比 BP-7 正文的 G6-sppi 更严重** —— G6-sppi 至少是 `fv-${Date.now()}-${seq}`
   （带时间戳前缀，跨会话不撞），G1/G3 是**纯下标字符串**，删中间一行后重载，其后所有缺 id 的行
   身份整体前移一位，且**不同底稿的第 1 行 id 都是 `"1"`**。
2. **新增路径（Req 1.3 本体）**：`` `row-${Date.now()}` `` **无随机后缀** ⇒ 同毫秒连加两行撞 id。

🔴 **发现 O（触类旁通旁证）**：同册的另两个 composable **都带随机后缀** ——
`useG3OverdueCheck.ts#L134` = `` `od-${Date.now()}-${Math.random().toString(36).slice(2,8)}` ``、
`useG3CalcCheck.ts#L265` = `` `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2,8)}` `` ⇒
**同册已有正确范式，主表是唯一偏离方**。Task 7 修主表时照同册范式即可，无需新造。

### 3.2 四条 slice 误标的逐字反证（无缺陷的正面证据）

| entry | 载入路径逐字 | 为什么不是 BP-7 |
|---|---|---|
| G10 | `L423: .map((r, i) => enrichG10DetailRow(r, i + 1))` | `i+1` **只喂 `seq`**；`rowId` 由 `raw.rowId` 透传，不参与下标派生 |
| G11 | `L162: parsed.map((r, i) => enrichRow(r, i + 1))` | 同上；`generateId()` = `` `g11d-${Date.now().toString(36)}${Math.random().toString(36).slice(2,6)}` `` 带随机 |
| G12 | `L114: arr.map((r, i) => …)` + `L50: rowId: String(raw.rowId ?? genId())` | `genId()` = `` `g12h-${Date.now().toString(36)}${Math.random()…slice(2,5)}` `` 带随机 |
| G13 | `L143: parsed.map((r,i)=> enrichRow({...r, rowId: r.rowId \|\| generateRowId(), seq: r.seq ?? i+1}))` | `generateRowId()` = `` `g13d-${Date.now().toString(36)}${Math.random()…slice(2,6)}` `` 带随机；`i+1` 只喂 `seq` |

⇒ 🔴 **登记「slice `capability_target_blocked_by` 与 BP-7 正文不一致」**：
BP-7 正文只展开 G6-sppi 一处，slice 把它横向套给了 **G1/G3/G10/G11/G12/G13 六条**；
按值实测只有 **G1 / G3** 命中（且 G1 本就另带 BP-5）。**未伪造缺陷，未静默抹掉四条标记** ——
四条的处置写入 Task 7：`blocked_by` 里的 BP-7 对 G10/G11/G12/G13 **不构成受管阻塞**，
理由是本节的逐字反证；`slice` 字节**不改**（它是别人的裁决取证）。

🔴 **对 `.map((r, i) =>` 这个模式的判据设计要点**：它在九条里**全部出现**（`i` 用于 `seq` 重排是正常业务），
单看模式命中会把九条全判违规。**判据必须看 `i` 的去向**：喂 `seq` = 正常，喂 `id`/`rowId` = 违规。
Task 3 的 P1 变异判据按此写。

---

## 4. 三处前端字段按值核

### 4.1 🔴 G13 父子关系字段 = **无**（裁决 G1R-H6 的「无字段」分支成立）+ 更根本的结构性错配（发现 I）

`useG13Detail.ts` 全文扫 `isParent` / `parentId` / `parentKey` / `children` / `isChild` / `indent` / `level`
⇒ **0 命中**。`G13DetailRow` 接口逐字（L28-35）：
```ts
export interface G13DetailRow {
  rowId: string
  seq: number
  instrumentName: string      // ← 用户自填的金融工具名称
  belongAccount: string
  instrumentType: string
  openingFairValue: number
  closingFairValue: number
  …
}
```
且有 `addRow` / `removeRow(rowId)`（L267-271）⇒ **动态增删行**。

🔴 **比「无父子字段」更根本的问题**：
- **模板侧**：R11-20 是**固定 10 行业务项**（交易性金融资产 / 其中：指定为… / 　衍生金融资产 / 交易性
  金融负债 / … / 以公允价值计量的投资性房地产 / 其他），带三层父子结构（`B11==B12+B13`）。
- **前端侧**：用户自由增删的金融工具明细行，`instrumentName` 自填，无骨架、无父子。

⇒ **两侧行模型不同构**。这不是「哪些行是父行只能靠模板行号硬编码」那么轻 ——
而是「前端的第 N 行**根本不对应**模板的第 N 行业务项」。

**Task 12 的三个候选（届时决策，本 Task 不预判）**：
| 方案 | 做法 | 代价 |
|---|---|---|
| ① 只受管子行区 | 受管区限定 R12/R13/R15/R16/R18（B/C 手填的子行）+ R19/R20，父行 R11/R14/R17 与 footer R21 全判 `mode=formula` 不受管 | 前端动态行仍无法对齐固定业务项 ⇒ 仍不同构 |
| ② 前端加骨架（照 G11 / G14 范式） | 给 G13 加 `G13_LINE_ITEMS` 骨架 + `rowKey`，`isSkeleton` 不可删 | 改前端数据模型 + 存量数据迁移，超出本 spec 声明层范围 |
| ③ G13 本轮只声明 HTML-only，登记结构性错配 | 不受管，出缺口登记 | 九条少一条，但诚实 |
🔴 同族先例：**G11 与 G14 都已是骨架行模型**（§4.3），G13 是同循环里唯一「动态行 vs 固定业务项」错配的。

### 4.2 🔴 G1 / G3 的 timestamp id **无随机后缀** —— Req 1.3 的缺陷确认命中

见 §3.1。两条逐字都是 `` `row-${Date.now()}` `` ⇒ 同毫秒连加两行必撞 id。
Task 7 修法（照同册范式）：`` `row-${Date.now().toString(36)}${Math.random().toString(36).slice(2,6)}` ``
或 `crypto.randomUUID()`。🔴 修后须**立即回写**（P2 转绿），且要处理存量：
载入路径的 `id ?? String(i+1)` 同时改掉，存量缺 id 行改用确定性稳定键（不得再用下标）。

### 4.3 G11 是混合骨架形态（发现 J）· G14 是纯固定行集（✅ spec 一致）

**G11 `useG11DetailAnalysis.ts`** 逐字：
```ts
L41-65: interface G11DetailRow { id: string; seq: number; rowKey: string; …; isSkeleton: boolean }
        //  L44 注释：/** 与 G11-1 rowKey 对齐，便于分项回写与勾稽 */
        //  L64 注释：/** 骨架行不可删 */
L71-73: function generateId() { return `g11d-${Date.now().toString(36)}${Math.random().toString(36).slice(2,6)}` }
L94-95: function buildSkeletonRows() { return G11_ADJUDICATION_ITEMS.map((def, i) => enrichRow({
L98-99:     id: `g11d-sk-${def.rowKey}`,        // ← 骨架行 id 确定性派生自 rowKey
            rowKey: def.rowKey, …
L169-177: function ensureSkeleton(parsed) {  // 空表 ⇒ buildSkeletonRows()；已有 rowKey ⇒ 原样返回
L219:   watch(remark) { rows.value = ensureSkeleton(parseRows(json)) }
```
⇒ **两种 id 生成并存**：骨架行 `g11d-sk-{rowKey}`（确定性、跨会话稳定、`isSkeleton` 不可删）
+ 用户增行 `g11d-{base36时间}{随机4}`。
**slice 的 `identity_field="id"` ✅ 正确**（`rowKey` 是与 G11-1 审定表对齐的业务键，不是行身份）。
⇒ G11 **无需修身份**，但声明时须知道受管区行数可变（骨架行数 = `G11_ADJUDICATION_ITEMS.length`，
待 Task 11 按值取；模板预画 21 行 R10-30）。

**G14 `useG14Detail.ts`** 逐字：
```ts
L29:  rowKey: string
L62:  return G14_LINE_ITEMS.map((def) => enrichRow({ ...def }, tb[def.rowKey] ?? null))
L69:  const def = G14_LINE_ITEMS.find((d) => d.rowKey === raw.rowKey)
```
⇒ **无 `.map((r, i) =>`、无 id 生成、无 addRow** ⇒ **纯固定行集**，`rowKey` 即身份 ✅
`stable_template_row_key` 确认。🔴 L62 的 `tb[def.rowKey]` 说明 **G14 从 TB 取数**（本期发生额，科目 6702）
⇒ Task 10 声明时须确认该读路径不被受管改动影响（读 TB 不是写 TB，不触 FC-9 红线）。

**G13 的 `rowKey` 命中 1 处**（L454 注释「按分类骨架 rowKey 筛选工具明细」）⇒ 是**跨表读取**用，
不是 G13 自身行身份 —— 与 G11/G14 的 `rowKey` 不同义，判据不得按名字混同。

---

## 5. Task 2 对后续 Task 的交棒清单

| 后续 Task | 本 Task 交出的硬结论 |
|---|---|
| Task 3（P1） | `.map((r,i)=>` 九条全命中，判据**必须看 `i` 的去向**（喂 `seq` 正常 / 喂 `id` 违规）；P6 的不等点精确到**唯一元素 T** |
| Task 4（P9/P12） | 布尔列**四处**不是三处（G12!G9 · G13!K11:K20 · G13!K21 footer · G14!L11:L19 + **L20 footer**）；G8 拆**三段** |
| Task 5（P10/P11） | P10 须测 **`$F$31` 与 `$J$31` 两个分母**；P11 的 `I14=SUM(I7:I13)` 起点是**表头组行 R7** |
| Task 6（P15） | G3 definedNames **现算 491**（不写死）；G1 = 0 |
| Task 7 | 只修 **G1/G3 两条**（两层病灶一并修，照同册 `Math.random()` 范式）+ 登记 **G10/G11/G12/G13 四条 slice 误标** |
| Task 9（G8） | 走**三段** `g802-r11` / `g802-r12` / `g802-r13plus` |
| Task 10（G14） | footer `L20` 是布尔；`tb[def.rowKey]` 是 TB **读**路径 |
| Task 11（G11） | 受管区 R10-30；骨架行数按值取 `G11_ADJUDICATION_ITEMS.length`；R32 手填行不受管 |
| Task 12（G13） | 父行**三行**（R11/R14/R17）；R19/R20 是顶层手填行**不得判 formula**；🔴 结构性错配三方案待决 |
| Task 13（G12） | 🔴 **不是无表头**：`header_group_row=7 / header_leaf_row=8 / first_data_row=9`；框架层**无需改**；布尔列只在 R9；两处模板缺陷走覆盖层 |
| Task 14（G1/G3） | G1 区① T 列逐行对应 `公允价值测试表G1-6!H10..H14`；G3 有效列 **A..AF=32**（非 33） |
| `g4-g6` spec | 🔴 G6-5 的「无表头行」判断**可能同源于同一个错误假定**，须同法逐格重测 |
