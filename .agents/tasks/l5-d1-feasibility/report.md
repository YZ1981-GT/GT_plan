# L5 长期应付款 真双向改线 — D1 摊平可行性报告（只读调查）

> 任务 `l5-d1-feasibility`。全程中文。只读调查，不改代码、不提交、不重启服务。
> 调查用 openpyxl 逐格实读 `backend/wp_templates/L/L5 长期应付款.xlsx`
> （**SHA256 = `09380626107dc1b975662eaa60fa99ec541901c0729bb0d2b35bbb60807a9b68`**，作后续 `TEMPLATE_SHA256` 冻结哨兵；若需 sanitize 另算），并查了只读 PG `audit_platform`、前端 composable、框架层引擎、D3/F1 账龄范例。
> ⚠️ 关于 brief 里引用的 `.agents/tasks/l5-managed-table-choice/report.md`：**该文件在仓库中不存在**（`.agents/tasks` 下只有 `l8-true-bidirectional-2026-10-01`）。本报告的全部 L5-2/L5-3 几何与 HTML 列模型均由本轮 openpyxl 实读 + 源码实读重新取证，未依赖那份不存在的报告。

---

## 零、摘要答案（先给结论）

| 问题 | 结论 |
|---|---|
| **1. D1 摊平可行性** | ✅ **可行，且比 L8 更干净**。L5-2 的 3 分组标题行（A10/A17/A24）+ 3 小计/合计行（R16/R23/R25）全作模板静态骨架不进 store；受管区只覆盖 **11 个输入行**（R11–R15 售后租回 5 行 + R18–R22 分期付款 5 行 + R24「…」占位 1 行）。**关键优势：输入行的 7 个公式列 E/L/M/N/O/R/S 在全部 11 行逐行同形**（实测逐格确认），**没有 L8 R11/R13/R20 那种「列里夹跨行派生公式」的异形**——所以 `RowTableSheetSpec.formula_columns` 的「整列同形」模型直接适用，不需要任何引擎扩展，也不触发 L8 顶部那条「若引擎层不成立就停下报 warning」的架构风险。 |
| **2. HTML 列重做范围** | ✅ **推荐 (b)**：只把受管区对齐 Excel 核心 roll-forward 列，L5DetailRow 的融资属性列（nominalAmount/discountRate/presentValue/startDate/maturityDate/category/currency/guaranteeType）退为 **HTML-only（不进受管区、不进契约）**。(a) 整体重做列模型工作量大且会与 useL5FormulaEngine/useL5CrossSheet/useL5Adjudication/L5-5 摊销联动全面冲突，收益不成比例。 |
| **3. 账龄桶 AgingLayout** | ✅ **可表达，选 `flat`**。L5-2 的 T~X（6个月以内/6-12月/1~2年/２~3年/3年以上，5 桶）是**单组、无子前缀**的平铺桶，没有「期初/期末/审定」三套账龄，用 `AgingLayout.flat` + 1 个 `AgingGroupSpec`（三元 segments）声明最贴切。D6 是现成的 flat 范例。 |
| **4. L5-3 处理** | ✅ **本轮只受管 L5-2，L5-3 留后续**。L5-3 的 A 列整列是 `='明细表L5-2'!A10` 这类跨 sheet 引用（名称列不是录入、是镜像 L5-2），且 L5-3 与 L5-2 行一一对应、科目 2702 是备抵——它是 L5-2 的下游派生视图，接线它需要额外一张受管表 + 跨 sheet 名称镜像的处置，复杂度≈再做半个 L5。先把 L5-2 真双向闭环，L5-3 作独立后续条目。 |
| **5. 工作量** | ≈ **L8 的 1.3~1.5x**（即 L6/L7 的 ~1.5x）。比 L8 省掉了「跨行派生公式架构裁决」这个最大风险点，但多了「首次启用 AgingLayout（5 桶 flat）」+「HTML 列模型是融资属性、与 Excel roll-forward 完全不同口径，需裁 HTML-only 子集并新增 roll-forward 字段映射」两项 L8 没有的工作。拆 7 子步见 §六。 |

**一句话**：D1 摊平对 L5-2 不仅可行、而且比 L8 风险更低（无异形公式列）；真正的新工作量集中在「HTML 列与 Excel roll-forward 的口径鸿沟」和「首次用 AgingLayout」，两者都有现成范式（F1-2 / D6），无架构级障碍。


## 一、问题1：D1 摊平可行性 + 输入行映射表

### 1.1 L5-2 完整几何（openpyxl 逐格实读）

- sheet 名 `明细表L5-2`，`max_row=35`，`max_col=30(AD)`，merged 21 处。
- **两级表头**：
  - 行 8（组标题，merged）：`A8=债权人名称` / `B8:E8=未审数` / `F8:G8=期初调整` / `H8:I8=账项调整` / `J8:K8=重分类调整` / `L8:O8=审定数` / `P8=减：期初一年内到期长期应付款` / `Q8:Q9=减：期末一年内到期长期应付款` / `R8:S8=披露审定数` / **`T8:X8=期末到期日分析`（账龄组标题）** / `Y8:Y9=是否是关联方` / `Z8:Z9=发函情况` / `AA8:AA9=期后付款` / `AB8:AB9=合同索引号` / `AC8:AC9=备注`。
  - 行 9（叶子子标题）：`B9=期初余额 C9=借方发生 D9=贷方发生 E9=期末余额`（未审区）/ `F9=账项调整 G9=重分类调整`（期初调整）/ `H9=借方发生 I9=贷方发生`（账项调整）/ `J9=借方发生 K9=贷方发生`（重分类）/ `L9=期初余额 M9=借方发生 N9=贷方发生 O9=期末余额`（审定）/ `R9=期初余额 S9=期末余额`（披露）/ **`T9=6个月以内 U9=6-12月 V9=1～2年 W9=２～3年 X9=3年以上`（5 账龄桶）**。
- **数据区结构（3 段分组 + 3 小计/合计）**：
  - 分组标题行：`A10=售后租回业务形成的融资`、`A17=分期付款方式购入固定资产`、`A24='…'`（占位省略号）。
  - 小计/合计行：`A16=小计`（SUM 11:15）、`A23=小计`（SUM 18:22）、`A25=合计`（`=SUM(B16,B23,B24)`）。
  - 输入行：`R11–R15`（售后租回 5 行，在 A10 标题下）、`R18–R22`（分期付款 5 行，在 A17 标题下）、`R24`（「…」行自身也带 roll-forward 公式，是第 3 段唯一数据行）。
- **bare IF 计数 = 0**（整张 sheet 无 `=IF(` 公式）⇒ **不需要 `neutralize_oo_crash_if_formulas`，无 L8 补课③那条「R 列被中性化、不做公式幸存断言」的复杂度**。

### 1.2 输入行公式列同形性（🔴 决定 D1 可行性的核心证据）

逐列实测 11 个输入行（R11–R15 / R18–R22 / R24）的单元格状态（f=公式 / v=值 / .=空）：

| 列 | 11 行状态 | 结论 |
|---|---|---|
| A（债权人名称） | `..........v`（仅 R24 有值「…」） | editable text，R11–R22 待录入、R24 模板占位 |
| E（期末余额=未审） | `fffffffffff` | **formula，全 11 行同形** `=B{r}-C{r}+D{r}` |
| L（审定期初） | `fffffffffff` | **formula，全 11 行同形** `=B{r}+F{r}+G{r}` |
| M（审定借方） | `fffffffffff` | **formula，全 11 行同形** `=C{r}+H{r}+J{r}` |
| N（审定贷方） | `fffffffffff` | **formula，全 11 行同形** `=D{r}+I{r}+K{r}` |
| O（审定期末） | `fffffffffff` | **formula，全 11 行同形** `=L{r}-M{r}+N{r}` |
| R（披露期初审定） | `fffffffffff` | **formula，全 11 行同形** `=L{r}-P{r}` |
| S（披露期末审定） | `fffffffffff` | **formula，全 11 行同形** `=O{r}-Q{r}` |

抽验 R11 / R18 / R24 三行逐字相同的公式骨架（只换行号）：
```
E = =B{r}-C{r}+D{r}      L = =B{r}+F{r}+G{r}    M = =C{r}+H{r}+J{r}
N = =D{r}+I{r}+K{r}      O = =L{r}-M{r}+N{r}    R = =L{r}-P{r}
S = =O{r}-Q{r}
```

🔴 **这是 L5 相对 L8 的关键优势**：L8-2 的 B~M 列在 R11/R13/R20 三行是跨行减法派生公式（`=B9-B10` 等），导致「同一列既有可编辑输入格又有公式格」，无法用 `formula_columns` 的整列区间表达——L8 为此走了「B~M 全列 editable + 派生公式作模板预置格幸存」的架构裁决并留了 warning 退路。**L5-2 没有这个问题**：E/L/M/N/O/R/S 这 7 列在**全部**输入行都是同形本行算术公式，没有任何一个输入行在这些列里是「可编辑输入」；而所有可编辑的输入格（B/C/D/F/G/H/I/J/K/P/Q + 账龄 T~X）在这 7 个公式列里一个都没有。⇒ `formula_columns=("E","L","M","N","O","R","S")` 的整列区间 mask（`E11:E24` 等）完全成立，`RowTableSheetSpec.formula_mask` property 直接可用，**无需引擎扩展、无需 warning 退路**。

### 1.3 分组标题行 / 小计行作静态骨架（D1 摊平）

- **3 分组标题行 A10/A17/A24**：A10/A17 是纯中文标签（无公式），A24 的 A 列是「…」占位但其 E24/L24/… 带 roll-forward 公式——A24 本质是「第 3 分组的唯一数据输入行」，不是纯标题。处置：**A10/A17 作模板静态标签行**（不进 store、`is_template_skeleton_identity` 保护）；**A24 作输入行纳入受管数据区**（见 §1.4）。
- **3 小计/合计行 R16/R23/R25**：全是 SUM 聚合（`B16=SUM(B11:B15)` / `B23=SUM(B18:B22)` / `B25=SUM(B16,B23,B24)`），是模板公式小计，用户不该编辑。处置：**全作模板静态骨架行**，不进受管数据区、不进 footer 公式区（引擎单 `footer_row` 模型只认一行 footer；这里有 2 个段小计 + 1 个合计，共 3 个聚合行）。

🔴 **这正是 D1 范式**：派生/小计/标题行不进 store 载荷、靠 `is_template_skeleton_identity` 不被当 stale 删、`_emit` 不碰、模板 SUM 公式全幸存。L8 的 D1 已在真 OO 往返坐实（commit `8b643501a`/`55bd1d1d4`）。引擎 `merge_projection_into_store_rows` 的 docstring 明文把「L8-2 的派生行 R11/R13/R20」列为该机制的典型用例，L5-2 的小计/标题行是同一机制。

### 1.4 推荐输入行映射（受管数据区 = 11 行，但有一个几何障碍，见 §1.5）

| 分组 | 分组标题行（静态） | 输入行（受管） | 小计行（静态） |
|---|---|---|---|
| 售后租回业务形成的融资 | A10 | **R11, R12, R13, R14, R15** | R16（小计 SUM11:15） |
| 分期付款方式购入固定资产 | A17 | **R18, R19, R20, R21, R22** | R23（小计 SUM18:22） |
| 「…」第三段 | A24（兼输入行） | **R24** | — |
| 合计 | — | — | R25（合计 SUM16,23,24） |

### 1.5 🔴 D1 摊平的唯一真实障碍：数据区被小计行物理分段（非连续）

**现有 `RowTableSheetSpec` 的数据区是单一连续区间 `first_data_row..last_data_row`**（如 F1-2 的 14..34）。但 L5-2 的输入行被小计行**物理切断**成三段：R11–R15 | (R16 小计) | R18–R22 | (R23 小计) | R24 | (R25 合计)。若声明 `first_data_row=11, last_data_row=24`，这个区间里**夹着 R16/R17/R23 三个非输入行**（R16 小计、R17 空行=A17 标题的下一物理行、R23 小计），引擎按连续区间扩行/注入 UUID/materialize 时会把小计行也当成数据行处理。

这是本次 L5 接线**最需要在实施期第一步坐实**的点（类似 L8 顶部的架构裁决点），有三条候选处置，推荐**候选 C**：

- **候选 A（折叠成单段，不推荐）**：像 `l2-l3-l4-orphan-twins-and-sheet-granularity-collapse` spec 的「sheet 粒度折叠」那样把 3 段压成 1 段连续数据区——需要改模板删小计行，破坏审计师熟悉的「售后租回/分期付款分段 + 分段小计」结构，不可接受。
- **候选 B（多受管区，一段一个 store_item_id）**：照 `phase5_d3_04_analysis` 的双区范式，把三段声明为三个 `RowTableSheetSpec`（三个 table_key / 三个 UUID 列），每段一个连续区间。缺点：前端 `L5-L5-2-rows` 是单 JSON 数组、单一存储键，拆成三键要动前端持久化契约（牵连 useL5CrossSheet/useL5FormulaEngine），波及面大。
- **候选 C（单键 + `row_section_field` 多区过滤，✅ 推荐，已验证同构）**：引擎已内建 `row_section_field` / `row_section_value`（`g-cycle-single-region-detail-lanes` spec，`phase5_g9_02_detail.py` + `phase5_g9_other_noncurrent.py`）。把 L5-2 声明成**三个 `RowTableSheetSpec`**（R11:15 / R18:22 / R24:24），三者 **共享同一 `store_item_id='L5-L5-2-rows'`**，用 `row_section_field='section'` + 各段 `row_section_value`（如 `saleLeaseback` / `installment` / `other`）区分；`iter_store_rows` 只 yield 本段行、`merge_projection_into_store_rows` 给新增行补段归属。

🔴 **此路径已由 G9 实证可行、且与 L5-2 几何完全同构**（本轮实读 `phase5_g9_02_detail.py` 确认）：G9-2 的三区**也是物理分段**——R12:16（footer 17）/ R19:23（footer 24）/ R26:28（footer 29），每区独立 UUID 列（AC/AD/AE）、独立 `template_id` 后缀（`G92R1/R2/R3`）、独立 footer，三区共享单 store 键 `G9-detail-rows`（有真库载荷、被 8 个跨表消费方读取）。L5-2 的 R11:15（小计 16）/ R18:22（小计 23）/ R24（合计 25）与此逐项对应。⇒ **候选 C 不是新架构裁决点，是照抄 G9 范式**：三 spec 各带独立 `uuid_col` / `template_id` 后缀（如 `L52R1/R2/R3`）/ `footer_row`（16/23/25）/ `row_section_value`，共享 `store_item_id`。
  - 🔴 实施期仍须现算核对两点（非障碍、是精度）：① L5-2 第 3 段只有 R24 单行数据 + R25 合计，G9-2 第 3 段是 R26:28 三行 + footer 29——单行数据区是否触发引擎的「数据区至少 N 行」假设需实读确认（G9 第 3 段 last-first=2，L5 第 3 段 last-first=0）；② R25 合计是 `=SUM(B16,B23,B24)`（跨三段小计求和，不是连续区间 SUM），footer 公式区归一化（`_grow_managed_table_ref`）对「非连续 SUM footer」的行为须在真 OO 往返坐实。若任一不成立，退候选 B（三独立 store 键），**不得退成候选 A（删小计折叠）**。
  - 🔴 **三区 UUID 列选位**：L5-2 物理 max_col=30(AD)，业务列用到 AC（备注），AD 空。三区各需一个隐藏 UUID 列（G9 用 AC/AD/AE 三连列）。L5-2 可用 `AD/AE/AF`（AD 之后的 3 个空列，实读确认 AD~AF 在数据区全空再定）。


## 二、问题2：HTML 列重做范围（推荐 (b)）

### 2.1 现有 L5DetailRow 列模型（`useL5Detail.ts` 实读）

HTML 侧 `L5DetailRow` 20 个字段，存储键 `L5-L5-2-rows`（双前缀，与 L7 同型），单 JSON 数组通道（`debouncedSave(ITEM_ROWS, {remark: JSON.stringify(payload)})`），行身份字段 `key`（不是 `rowId`）：

```
key, payableName, creditor, startDate, maturityDate, category,
nominalAmount, discountRate, presentValue,          ← 融资属性列（Excel L5-2 无对应）
beginning, periodIncrease, periodRepayment, endBalance,  ← roll-forward 核心（≈Excel B/C/D/E）
unadjusted, aje, rje, audited,                       ← 调整区（≈Excel 的 账项/重分类/审定，但口径不同）
currency, guaranteeType, remark                      ← 附加列
```

### 2.2 口径鸿沟（🔴 HTML 列与 Excel roll-forward 根本对不上）

| Excel L5-2 列 | 语义 | HTML L5DetailRow 对应 | 匹配度 |
|---|---|---|---|
| A 债权人名称 | 名称 | payableName | ✅ |
| B 期初余额 | 未审期初 | beginning | ✅ |
| C 借方发生 | 未审借方 | periodRepayment | ⚠️（语义近似，HTML 叫「偿还」） |
| D 贷方发生 | 未审贷方 | periodIncrease | ⚠️（HTML 叫「增加」） |
| E 期末余额=公式 | 未审期末 | endBalance（HTML 公式） | ✅（都是公式） |
| F/G 期初调整/重分类 | 期初账项/重分类调整 | **无** | ❌ |
| H/I 账项借/贷 | 账项调整借贷 | aje（标量，非借贷拆分） | ❌ 口径不同 |
| J/K 重分类借/贷 | 重分类借贷 | rje（标量） | ❌ 口径不同 |
| L/M/N/O 审定期初/借/贷/期末 | 审定区（公式） | audited（标量） | ❌ 口径不同 |
| P/Q 减一年内到期 | 重分类披露 | **无** | ❌ |
| R/S 披露期初/期末审定 | 披露（公式） | **无** | ❌ |
| T~X 账龄 5 桶 | 到期日分析 | **无** | ❌ |
| nominalAmount/discountRate/presentValue | 名义/折现率/现值 | 有 | Excel L5-2 **无**对应列 |
| startDate/maturityDate/category/currency/guaranteeType | 融资属性 | 有 | Excel L5-2 **无**对应列（部分在别的 sheet） |

结论：HTML 列模型是**按「融资租赁/分期付款业务属性」设计的**（名义金额/折现率/现值/起止日/担保），与 Excel L5-2 的**「roll-forward + 多栏调整 + 账龄」会计明细表**是两套完全不同的数据模型。两者**只有 payableName / beginning / periodIncrease / periodRepayment / endBalance 五个字段真正对得上**。

### 2.3 两条路工作量与冲突点

**(a) 整体重做 L5DetailRow 忠于 Excel roll-forward**
- 改文件：`useL5Detail.ts`（重写 20 字段 → ~15 roll-forward 列 + 5 账龄桶）、`L5TabDetail.vue`（重写 3 区段 Tab + el-table 列定义 + 列显隐偏好）、`useL5FormulaEngine.ts`（`calcLiabilityEndBalance` 等要重新对齐 Excel 的 E=B-C+D / L=B+F+G / O=L-M+N 多级公式）、`useL5CrossSheet.ts`（L5-2↔L5-1 勾稽按新列重接）、`useL5Adjudication.ts`（审定表取数口径变）、`L5-3 备抵联动`（L5-3 的 A 列镜像 L5-2 名称，列变则镜像变）。
- 冲突点：融资属性列（nominalAmount/discountRate/presentValue）是 **L5-5 未确认融资费用测算表（实际利率法摊销）的输入源**（`useL5AmortizationEngine.ts`），删掉会断掉 L5-5 的摊销链；category/startDate/maturityDate 是 L5-6 关联方检查、L5-7 检查表的数据源。**(a) 等于重写整个 L5 前端数据层**，波及 6+ composable，与「只给 L5-2 接真双向」的目标严重不成比例。

**(b) 只受管核心 roll-forward 列、融资属性列退 OO 非受管（✅ 推荐）**
- 受管区只覆盖 Excel L5-2 的 roll-forward 核心列：A(payableName) / B(beginning) / C(periodRepayment) / D(periodIncrease) / E(endBalance 公式) + 调整/审定列 + 账龄 T~X。
- 融资属性列（nominalAmount/discountRate/presentValue/startDate/maturityDate/category/currency/guaranteeType）**声明为 HTML-only**（`RowTableSheetSpec.html_only_item_ids` 机制，D4-5 范式）——它们继续存在 `L5-L5-2-rows` 的 JSON 里、继续喂 L5-5/L5-6/L5-7，但**不进契约、不进受管区、OO 侧不渲染这些列**。真双向只在 roll-forward 列上成立。
- 需新增的 HTML 字段：Excel 有而 HTML 当前缺的 F/G/H/I/J/K/L/M/N/O/P/Q/R/S + T~X 账龄桶。这些要么作公式列（L/M/N/O/R/S/E 由契约标 formula、HTML 侧也应有对应只读派生字段），要么作新 editable 字段（F/G/H/I/J/K/P/Q + 5 账龄桶）加进 `L5DetailRow`。
- 🔴 **(b) 的本质**：`L5DetailRow` = {现有融资属性列（HTML-only 保留）} ∪ {Excel roll-forward 受管列（部分已有如 beginning/endBalance，部分新增如 F/G/H/I/J/K/P/Q/账龄）}。现有的 unadjusted/aje/rje/audited 四个标量调整列与 Excel 的借贷拆分列（H/I/J/K）口径不同——**接线期须裁决**：是把 Excel 的 H/I/J/K 作新受管列（HTML 新增 4 字段），还是把 HTML 的 aje/rje 映射到 Excel 某列。推荐前者（忠于 Excel），把 aje/rje/audited/unadjusted 退为 HTML-only（它们是 HTML 自有的简化调整模型，与 Excel 多栏不冲突）。

**推荐 (b) 的理由**：工作量集中在「给 `L5DetailRow` 加 Excel roll-forward 受管字段 + 标 html_only_item_ids」，不动 L5-5/L5-6/L5-7 的融资属性消费链，不重写 useL5FormulaEngine/CrossSheet 的既有逻辑。真双向覆盖面是「会计师在 OO 里改 roll-forward 数会回流 HTML」，这正是 L 循环真双向的核心诉求；融资属性是 HTML 结构化录入的增值功能，退 OO 非受管不损失它（HTML 侧照常编辑）。

🔴 **(b) 的代价须明示**：L5DetailRow 要新增约 10~14 个受管字段（F/G/H/I/J/K/P/Q + T/U/V/W/X 账龄 + 可能的 L/M/N/O/R/S 只读派生），这是比 L7/L8「HTML 列已基本对齐 Excel」更重的一步。但仍远轻于 (a) 的「重写整个数据层」。

## 三、问题3：账龄桶 AgingLayout 声明方案（选 flat）

### 3.1 引擎 AgingLayout 定义（`phase5_row_table_sheet.py` 实读）

- `AgingLayout.nested`（D3/D7/F1）：`{agingPrior: {within1: …}, agingAudited: {…}}`，有「期初/期末/审定」多套账龄组，每组一个 `json_prefix` 子对象 + `leaf_labels`。
- `AgingLayout.flat`（D6）：段键直接平铺顶层（无 `json_prefix`），`AgingGroupSpec(json_prefix="", group_header_cell=…, segments=三元(flat_key, column, leaf_label))`。
- `expand_aging_fields()` 对 flat 把每段展开成 `(snake(flat_key), column, "editable", "amount", flat_key, leaf_label, group_header_cell)`。

### 3.2 L5-2 账龄实读 → 选 flat

L5-2 的账龄是**单组 5 桶**，merged 组标题 `T8:X8=期末到期日分析`，叶子行 9：`T9=6个月以内 / U9=6-12月 / V9=1～2年 / W9=２～3年 / X9=3年以上`。**没有「期初/期末/审定」多套账龄**（nested 的用途），就是一组到期日分布。⇒ **用 `AgingLayout.flat` + 单个 `AgingGroupSpec`** 最贴切（nested 会强行要求 json_prefix 子对象、语义多余）。

### 3.3 声明方案（照 D6 flat 范式）

```python
AGING_GROUPS_L52 = (
    AgingGroupSpec(
        json_prefix="",                       # flat 不用
        group_header_cell="T8",               # 组标题 T8:X8 的锚格
        segments=(                            # 三元：(flat_key, 列标, 叶子标签)
            ("agingWithin6m", "T", "6个月以内"),
            ("aging6to12m",   "U", "6-12月"),
            ("aging1to2y",    "V", "1～2年"),
            ("aging2to3y",    "W", "２～3年"),   # 🔴 全角「２」，照模板实测字符
            ("agingOver3y",   "X", "3年以上"),
        ),
    ),
)
# spec 里：aging_layout=AgingLayout.flat, aging_groups=AGING_GROUPS_L52
```

- flat_key 用 camelCase（会成 HTML json 顶层键，前端 `L5DetailRow` 要加这 5 个 editable 字段）。
- 叶子标签用模板实测的全角字符（`２～3年` 的「２」是全角，`1～2年` 的「～」是全角波浪号）——照 D3 的教训，禁用半角替换。
- 🔴 **三区同键下账龄声明**：候选 C 的三个 spec 各自都要带这组账龄声明（三区账龄列相同 T~X），`expand_aging_fields` 对每区展开——与 G9 三区各带相同字段集同构。
- 🔴 **小计行的账龄 SUM 不全**：实读 R16/R23/R25 小计只对 V/W/X（1~2年/2~3年/3年以上）有 SUM，**T/U（6个月以内/6-12月）两列小计行无公式**（`T16/U16` 空）。这是模板既有不对称，账龄列作 editable、小计行作静态骨架即可，不影响受管区（小计 SUM 残缺是模板的事，不是接线要补的）。

## 四、问题4：L5-3 备抵科目处理（本轮只管 L5-2）

### 4.1 L5-3 实读事实

- sheet `未确认融资费用明细表L5-3`，max_col=30，两级表头行 9+10，数据 R12~R25，小计 R17/R24、合计 R26。
- **A 列整列是跨 sheet 引用**：`A11='明细表L5-2'!A10`、`A12='明细表L5-2'!A11`…`A25='明细表L5-2'!A24`——名称列**不是录入，是镜像 L5-2 的分组/行名称**。
- roll-forward 公式骨架与 L5-2 完全相同（E=B-C+D / L=B+F+G / O=L-M+N / R=L-P / S=O-Q）。
- 账龄 T~Y 是 **6 桶**（比 L5-2 多一桶）：`T10=6个月以内 U10=6-12月 V10=1年以下 W10=1～2年 X10=２～3年 Y10=3年以上`。
- 前端 `useL5UnrecognizedDetail.ts` 存储键 `L5-L5-3-rows`，行身份 `key`，列模型是另一套（initialUnrecognized/cumulativeAmortization/periodAmortization/effectiveRate 等摊销属性，与 L5-2 又不同）。
- 科目 2702（未确认融资费用，备抵）。真库 `L5-3` 命名空间 0 行（`L5-L5-3-rows` 不存在）。

### 4.2 建议：本轮只受管 L5-2，L5-3 作独立后续条目

理由：
1. **L5-3 是 L5-2 的下游派生视图**：A 列整列镜像 L5-2 名称（`='明细表L5-2'!A{n}`）。受管 L5-3 要么把这些跨 sheet 引用作模板公式幸存（名称列不受管），要么处理「L5-2 行增删 → L5-3 镜像行同步」的联动——后者是额外一层跨 sheet 行身份对齐，复杂度不低。
2. **L5-3 HTML 列模型又是第三套**（摊销属性），受管它要再做一遍问题2 的「HTML 列 vs Excel roll-forward 口径裁决」。
3. **一一对应关系靠行身份**：L5-3 行与 L5-2 行一一对应，接线须保证两表行身份映射稳定——这是 L5-2 单表接线稳定后才好叠加的工作。
4. L8 的先例是**单受管表**（只 L8-2）。L5 本轮比照，先把 L5-2 真双向闭环（7/8→真·8/8 的最后一条先落地核心表），L5-3 作 `l5-unrecognized-finance-charge` 独立后续条目。

🔴 **接线 L5-2 时须注意 L5-3 的只读依赖**：L5-3 的 A 列 `='明细表L5-2'!A{n}` 依赖 L5-2 的物理行位置。若 L5-2 接真双向后发生结构性插行（受管区扩行），L5-3 的跨 sheet 引用会漂（R11 引 A10、R12 引 A11…是硬行号）。实施期须在真 OO 往返里**专门断言 L5-2 受管区扩行不破坏 L5-3 的 A 列镜像引用**（即便本轮不受管 L5-3，也不能让 L5-2 的改动打坏 L5-3 的既有公式）。


## 五、问题5：工作量估计（≈ L8 的 1.3~1.5x）

以 L6/L7 = 1x（HTML 列已基本对齐 Excel、单段数据区、无账龄）、L8 = 1.5~2x（跨行派生公式架构裁决 + 双 footer + 28 裸 IF 中性化）为基准。

**L5 相对 L8 省掉的（降风险）**：
- ✅ 无跨行派生公式异形：7 个公式列全 11 行同形，`formula_columns` 直接适用，无 L8 顶部那条架构 warning 退路。
- ✅ 无裸 IF：bare_IF=0，不需要 `neutralize_oo_crash_if_formulas`、不需要「R 列中性化、不做公式幸存断言」的补课。

**L5 相对 L8 多出的（增工作）**：
- ➕ **三区物理分段（候选 C）**：三个 `RowTableSheetSpec` + `row_section_field='section'` + 三 UUID 列 + 三 template_id 后缀，照 G9 范式但 L5 是首次在 L 循环用。
- ➕ **首次启用 AgingLayout（5 桶 flat）**：L 循环所有已完成条目 aging_layout=None，L5 首个。有 D6 flat 范例，低风险但要新写账龄声明 + 前端加 5 个账龄字段。
- ➕ **HTML 列口径鸿沟（问题2）**：L5DetailRow 是融资属性模型，与 Excel roll-forward 完全不同，须裁 html_only + 新增约 10~14 个受管字段。这是比 L7/L8 重的一步（L7/L8 的 HTML 列已对齐 Excel）。

**综合估计：≈ L8 的 1.3~1.5x**（省掉的风险点 ≈ 抵消一半新增工作；HTML 列重做 + 三区 + 账龄三项新工作把总量推到 L8 之上一点）。

### 子步骤工作量拆分

| 子步 | 内容 | 相对工作量 | 风险 |
|---|---|---|---|
| T1 几何坐实 + 三区 Spec 架构裁决 | 实读确认候选 C（三区同键）在 L5 单行第三段 + 非连续合计 footer 下可行；UUID 列选位（AD/AE/AF）；若不成立退候选 B | 1.0x | 🔴 中（新架构裁决点，但有 G9 实证） |
| T2 前端行身份 + HTML 列 (b) | key 换 `newRowIdentity('l52det')`；L5DetailRow 加 roll-forward 受管字段 + 5 账龄桶；标 html_only 融资属性列；加 section 字段 | 1.3x | 🟡 中（动列模型，须不碰 L5-5/6/7 消费链） |
| T3 host 双模式切换器 | GtL5LongTermPayables.vue 的 L5A 程序表加 HTML↔OO segmented + GtEntrySyncCapabilityNotice，照 L7 范式 | 0.7x | 🟢 低 |
| T4 provider + sheets + 三处注册 + 裁决表 + 测试 | phase5_l5_sheets.py（三区 spec + flat 账龄）+ phase5_l5_long_term_payables.py（委派 l_cycle_common）+ registry/ledger/store_item_registry 三处 + fix_l_cycle 裁决表 + 契约生成 + test_l5_adapter_registration.py | 1.5x | 🟡 中（三区 + 账龄首次，测试面大） |
| T5 五环发布（真库 Docker up） | sanitize 预判（共享公式组朝向）+ provision + first publication；查 DB 不看退出码 | 0.8x | 🟡 中（三区 provision 对齐） |
| T6 overlay + 干净 worktree 翻 manifest | 加 L5 override + 干净 worktree 重算 approved_source_digest + mount-diff 零能力损失复核 | 0.8x | 🟡 中（并发热点，须干净 worktree） |
| T7 真 OO 往返验证 + 回归归因 + 提交 | verify_l5_oo94_roundtrip.py（三区 section 对齐 + 账龄桶往返 + 小计/标题行静态骨架幸存 + 🔴 L5-3 A 列镜像引用不被打坏）+ 逐文件 add 不 -A | 1.2x | 🔴 中（三区往返 + L5-3 旁路断言） |

## 六、逐步实施计划（照 L8 plan 范式，7 步）

> 范式照 `.agents/tasks/l8-true-bidirectional-2026-10-01/plan.md`（L7/L6 同系）。身份常量速查见 §七。
> 全程中文、不 push、绝不 `git add -A/.`、三处注册只在 L 块末尾追加 L5 一行/一块。

**T1 — 三区 Spec 架构坐实（🔴 第一步必做，不成立即停报 warning）**
- 实读 `phase5_g9_02_detail.py` + `phase5_g9_other_noncurrent.py` 的三区同键全链路（section_specs / 三门面遍历 / attach 对齐）。
- openpyxl 现算：L5-2 的 AD/AE/AF 三列在数据区（R11~R25）全空（作三区 UUID 列）；R24 单行第三段 + R25 `=SUM(B16,B23,B24)` 非连续 footer 在引擎下的行为。
- 若三区同键在「单行第三段 / 非连续 SUM footer」不成立 → 停下 `send_message` warning，给候选 B（三独立 store 键）替代，**不得退候选 A（删小计折叠）**。
- 验证：探针脚本 `backend/scripts/analyze/_l5p_*.py`（用完即删）打印三区几何 + G9 对齐确认。

**T2 — 前端行身份 + HTML 列 (b)（`useL5Detail.ts` + `L5TabDetail.vue`）**
- `key` 生成器换 `newRowIdentity('l52det')`（addRow + 默认行 + hydrate 补铸，保留字段名 `key`）。
- L5DetailRow 加 Excel roll-forward 受管字段（priorAdjustment F / priorReclass G / ajeDebit H / ajeCredit I / rjeDebit J / rjeCredit K / minusPriorDue P / minusEndDue Q + 账龄 agingWithin6m/aging6to12m/aging1to2y/aging2to3y/agingOver3y）+ `section` 字段。
- 融资属性列（nominalAmount/discountRate/presentValue/startDate/maturityDate/category/currency/guaranteeType/unadjusted/aje/rje/audited）标 html_only（provider 侧 `html_only_item_ids`），前端照常编辑、不进契约。
- 验证：vitest（key 前缀 + 新字段默认值 + section 归属）+ 限定范围 tsc + 变异证明。

**T3 — host 双模式切换器（`GtL5LongTermPayables.vue`）**
- L5A 程序表从直接渲染 GtAProgramConsole 升级为 HTML↔OO segmented 切换器，照 L7 `useCycleHtmlOoDualMode`（storagePrefix `'l5-proc:'`）+ GtEntrySyncCapabilityNotice（entry-id `xlsx/gt-l5-long-term-payables`）+ OO 挂载块；v-if/v-else 链核。
- 验证：限定范围 vue-tsc + v-if 链人工核 + 浏览器实测（dev server 起则做）。

**T4 — provider + sheets + 三处注册 + 裁决表 + 测试（后端）**
- `phase5_l5_sheets.py`：三个 `RowTableSheetSpec`（R11:15 / R18:22 / R24:24，共享 store_item_id `L5-L5-2-rows`，各带 uuid_col AD/AE/AF + template_id L52R1/R2/R3 + footer 16/23/25 + row_section_value saleLeaseback/installment/other），`formula_columns=("E","L","M","N","O","R","S")`，`aging_layout=AgingLayout.flat` + `AGING_GROUPS_L52`，`header_group_row=8 header_leaf_row=9`，`row_identity_key='key'`。
- `phase5_l5_long_term_payables.py`：委派 `phase5_l_cycle_common`（照 L7），`SPECS=(SPEC_L52_R1, R2, R3)`，`derived_readonly_sheet={审定表L5-1}`，`extra_review` 登记三区同键 + 账龄 flat + 小计/标题静态骨架 + L5-3 旁路。
- 契约生成（`generate_phase5_l_contracts.py` 加 `_l5`，`--only l5.long_term_payables --apply`）。
- 三处注册（registry 白名单 / delivered_contracts_ledger / store_item_registry 的 STORE_MERGE_REGISTRY，均 L 块末尾追加）+ 裁决表（`fix_l_cycle_wp_code_adjudication.py` 加 L5 条，wp_codes=["L5"]，heuristic L5L 幻影码）。
- `test_l5_adapter_registration.py`：三区几何 + flat 账龄 5 桶 + 公式列同形 + 小计/标题静态骨架断言 + 契约 parse + 配对不变式（L 域白名单==ledger，现 7→8）+ 真库 `L5-L5-2-rows` 0 行。
- 验证：pytest 该测试全绿 + 契约 `--check` OK + L7/l_cycle_common 未回归。

**T5 — 五环发布（真库 Docker up）**
- sanitize 预判（`_l5p_shared.py` 探针查 L5-2 共享公式组朝向；有横向组则照 `sanitize_l7_template_external_links.py` 展开）。
- provision（`fix_task76_provision_projection_definitions.py --check` → `--apply`）+ first publication（`fix_projection_first_publication.py --check` → `--apply --entry xlsx/gt-l5-long-term-payables`）；长命令后台跑防 ^C。
- 验证：查 DB（entry_state + representation generation≥1），不看退出码。

**T6 — overlay + 干净 worktree 翻 manifest**
- overlay 加 L5 override（capability bidirectional / migration_state adapter_registered / adapter_id l5.long_term_payables / html_store checklist_responses_... / canonical_resolver workpaper_sync_published_representation）。
- 干净 worktree（基于最新主 HEAD）只叠加 host + overlay 两处改动，重算 approved_source_digest，`generate_workpaper_sync_manifest.py --apply` + legacy baseline。
- mount-diff 零能力损失复核：唯一翻转 = L5，capability single_onlyoffice→bidirectional、byComponent 仅 GtOnlyOfficeSheet +1。
- 回拷主树 + 写 flip-diff 报告。清理 worktree。

**T7 — 真 OO 往返验证 + 回归归因 + 提交**
- `verify_l5_oo94_roundtrip.py`（照 verify_l7，`_row` 用 `"key": rid` + section 归属；跳过公式列 E/L/M/N/O/R/S；三区分别往返）：①attach 返 `('l5.long_term_payables',)`；②~⑥ substrate/projection/materialize/OO ConvertService/等值门；⑦merge 回 store 逐字段（三区 section 对齐、无幽灵行）；⑧公式列往返仍是 `=`（E/L/M/N/O/R/S 本行算术，无 IF 中性化问题）；⑨不写库。
- 🔴 L5 专项断言：小计行 R16/R23/R25 + 标题行 A10/A17 作静态骨架未被位移/清空（模板 SUM 幸存）；账龄桶 T~X editable 往返；**L5-3 的 A 列 `='明细表L5-2'!A{n}` 镜像引用未被 L5-2 受管区扩行打坏**。
- 回归归因（git stash 分预存红 vs 本任务红）；逐文件 add（禁 -A）；单 commit 中文 message；清探针 + worktree + 临时分支；不 push。

## 七、关键身份常量速查（现算，待 T1/T4 最终坐实）

| 项 | 值 | 来源 |
|---|---|---|
| ENTRY_ID | `xlsx/gt-l5-long-term-payables` | manifest 实测 |
| ADAPTER_ID | `l5.long_term_payables`（建议，照 l7.other_noncurrent_liabilities 命名） | — |
| WP_CODES（幻影码） | `{"L5L"}` | slice `wp_code_pattern="L5L"` 实测 |
| 裁决表 wp_codes | `["L5"]`（底稿码，非幻影码） | 照 L1~L7 |
| TEMPLATE_RELATIVE_PATH | `L/L5 长期应付款.xlsx` | — |
| TEMPLATE_SHA256 | `09380626107dc1b975662eaa60fa99ec541901c0729bb0d2b35bbb60807a9b68` | 现算（PRE_SANITIZE，若 T5 需净化另算） |
| MANAGED_SHEET | `明细表L5-2` | — |
| HEADER_GROUP_ROW / HEADER_LEAF_ROW | `8` / `9`（两级表头） | 现算 |
| 三区数据/footer | R1: 11~15 / 16 · R2: 18~22 / 23 · R3: 24~24 / 25 | 现算 |
| 分组标题静态行 | A10 售后租回 · A17 分期付款（A24 兼输入行） | 现算 |
| UUID 列（三区） | 建议 AD / AE / AF（待 T1 实读确认空列） | 待坐实 |
| template_id（三区） | 建议 L52R1 / L52R2 / L52R3（照 G9 的 G92R1/R2/R3） | — |
| formula_columns | `("E","L","M","N","O","R","S")`（全 11 行同形，无 IF） | 现算 |
| aging_layout | `AgingLayout.flat`，单组 5 桶 T~X | 现算 |
| STORE_ITEM_ID（三区共享） | `L5-L5-2-rows`（双前缀，照 L7） | `useL5Detail.ts` 实测 |
| ROW_IDENTITY_STORE_KEY | `key`（非 rowId，照 L8） | `useL5Detail.ts` 实测 |
| row_section_field | `section`（新增前端字段），values saleLeaseback/installment/other | 建议（照 G9） |
| bare_IF | 0（受管 sheet 无 IF，不需 neutralize） | 现算 |
| 真库 `L5-L5-2-rows` | 0 行（canary 仅 L5-adj-*/L5-*-note/L5-chk-conclusion 共 7 行，属 L5-1/L5-4） | 现算（docker exec psql） |
| amount_kind | `balance`（余额口径，负债类 期末=期初+贷-借，非 L8 的 occurrence） | `useL5Detail.ts` 口径 |

## 八、风险与未查到项

- 🔴 **T1 三区架构裁决**是本任务最大风险点（替代 L8 的「跨行派生公式裁决」）。虽有 G9 实证，但 L5 第三段单行 + 非连续 SUM footer 是 G9 没有的几何边角，须实施期坐实。
- 🟡 **问题2 的 (b) 新增字段**要在接线期敲定 Excel H/I/J/K（借贷拆分）与 HTML aje/rje（标量）的映射裁决——本报告推荐「Excel 列作新受管字段 + HTML 旧标量退 html_only」，但最终要对齐前端 L5-1 审定表取数口径（`useL5Adjudication.ts`）确认不断勾稽。
- 🟡 **L5-5 实际利率法摊销链**依赖融资属性列（nominalAmount/discountRate/presentValue）——(b) 把这些退 html_only 后，须确认 L5-5 仍从 `L5-L5-2-rows` JSON 读到它们（它们还在载荷里、只是不进契约），接线期回归 L5-5。
- **未查到**：L5A 程序表当前是否已有任何 OO/HTML 双模式痕迹（本报告按「照 L7 新增切换器」规划，未逐行读 host 的 script 段）；`useL5FormulaEngine.ts` / `useL5CrossSheet.ts` 的完整勾稽逻辑未逐行读（问题2 的冲突点基于列模型推断 + 文件名职责，接线期须逐行核）。
- **引用修正**：brief 所引 `.agents/tasks/l5-managed-table-choice/report.md` 不存在；本报告几何/列模型为本轮重新取证。
