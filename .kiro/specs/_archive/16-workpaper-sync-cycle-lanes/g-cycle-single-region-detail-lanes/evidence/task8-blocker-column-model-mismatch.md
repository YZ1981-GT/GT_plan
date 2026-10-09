# Task 8 阻塞证据：🔴 前端列体系 ≠ 模板列体系（九条共性，spec 未预见）

spec `g-cycle-single-region-detail-lanes` · Task 8 · 实测 2026-09-27
探针 `backend/scripts/analyze/_g_column_isomorphism_probe.py`

---

## 0. 结论先行

**G9（裁决 G1R-H1 选定的「最容易的首条、零特例」）的前端明细表与权威模板不是同一套列。**
逐列对照后能明确对应的只有 **3 列**（A/B/AB），模板独有约 **10 列**、前端独有 **15 列**。
`RowTableSheetSpec` 要求「一个 `stable_field_key` ↔ 一个模板列 ↔ 一个 store `json_key`」三者一一对应 ——
在这种错配下**无法诚实声明**，硬凑等于产出一份「看着能跑但字段指向错列」的契约。

⇒ **Task 8~14 的前提需要重新裁决**，本 Task 就此停在证据层，不写任何猜测性映射。

## 1. 列数普查（九条，机械比对）

| code | 模板有效列 | 前端受管字段 | 差 |
|---|---|---|---|
| **G9** | 28 | 28 | **0**（🔴 纯属巧合，见 §2） |
| **G12** | 10 | 10 | **0**（待逐列核） |
| G3 | 33 | 32 | +1 |
| G8 | 23 | 24 | −1 |
| G11 | 13 | 16 | −3 |
| G14 | 13 | 19 | −6 |
| G13 | 12 | 21 | −9 |
| G14 | 13 | 19 | −6 |
| G10 | 19 | 35 | −16 |
| G1 | 27 | 56 | −29 |

口径：模板有效列 = 表头行（G12 取 R7/R8、G3 取 R9-R11、G11 取 R9、其余 R9/R10）里有文本的最右列；
前端受管字段 = 行接口字段数，已剔除 `rowId`/`id`/`rowKey`/`seq`/`isSkeleton`/`label`/`group` 七个非受管项。

🔴 **列数一致不等于语义同构**（G9 是反例）；但**列数不一致一定不是 1:1**。
前端字段里还混着派生字段（如 `allReconciled`），所以「差 N」也不能直接当错配规模 ——
**要定性必须逐列做语义对照**，那是语义判断而非机械比对。

## 2. G9 逐列对照（决定性证据）

### 模板 28 列（`明细表G9-2` R9/R10 逐字）

```
A  类别                                    O  计入投资收益的股息
B  投资项目【按明细项目列示，如证券名称或被投资单位名称】   P  期末余额 / 成本
C  期初余额 / 成本                           Q  累计公允价值变动
D  累计公允价值变动                           R  公允价值            （=P+Q）
E  公允价值            （=C+D）              S  账项调整 / 成本
F  期初账项调整 / 成本                        T  公允价值变动
G  公允价值变动                              U  期末审定数 / 成本      （=P+S）
H  期初审定数 / 成本      （=C+F）            V  累计公允价值变动       （=Q+T）
I  累计公允价值变动       （=D+G）            W  公允价值            （=U+V）
J  公允价值            （=H+I）              X  期末重分类数
K  期初重分类数                              Y  期末报表数           （=R+X）
L  期初报表数           （=E+K）              Z  期末应收利息
M  本期变动（借方发生填正数）/ 成本              AA 变现是否存在限制
N  本期公允价值变动                           AB 发函情况
```

模板的骨架是**「成本 / 累计公允价值变动 / 公允价值」三联列**，在期初余额、期初账项调整（二联）、
期初审定数、期末余额、账项调整（二联）、期末审定数 六处重复。

### 前端 28 字段（`useG9Detail.G9DetailRow`，`G9TabDetail.vue` 分三段渲染 32 个 `el-table-column`）

```
段① 基本信息：assetName classification instrumentType isDesignated initialInvestDate
              maturityDate holdingQuantity faceValueOrCost measurementAttribute isRelatedParty
段② 变动：    openingBalance openingAdjustment openingAdjusted increaseAmount decreaseAmount
              fvChangeAmount interestIncome impairmentLoss ociChange
段③ 期末：    closingBalance closingAdjustment closingAdjusted fairValueLevel valuationMethod
              ociCumulative impairmentProvision confirmationStatus remark
```

前端的骨架是**单值列 + 10 列基本信息**，没有三联结构。

### 对照判定

| 关系 | 列 | 数量 |
|---|---|---|
| ✅ **明确对应** | `classification`↔A · `assetName`↔B · `confirmationStatus`↔AB | **3** |
| 🟡 可能对应但**不可判** | `fvChangeAmount`↔N？ · `interestIncome`↔O「计入投资收益的股息」还是 Z「期末应收利息」？ | 2 |
| 🔴 **模板有 / 前端无** | D E G I J K L X Y Z AA（三联的「累计公允价值变动」「公允价值」分量 + 重分类数 + 报表数 + 期末应收利息 + 变现限制） | **~11** |
| 🔴 **前端有 / 模板无** | instrumentType isDesignated initialInvestDate maturityDate holdingQuantity faceValueOrCost measurementAttribute isRelatedParty impairmentLoss ociChange fairValueLevel valuationMethod ociCumulative impairmentProvision remark | **15** |
| 🔴 **一对多 / 多对一** | `openingBalance` 对 C/D/E 三列？`openingAdjusted` 对 H/I/J 三列？`increaseAmount`+`decreaseAmount` 两字段对 M 一列？`closingBalance`/`closingAdjustment`/`closingAdjusted` 三字段对 P..W 八列？ | 多处 |

⇒ **28 == 28 是巧合**：3 列真对上 + 15 列前端独有 + ~11 列模板独有，恰好凑成相同总数。

## 3. 为什么 G2 canary 能成、G9 不能

`phase5_g2_02_detail.py` 的 13 个 `field_specs` 与 `明细表G2-2` 的 13 列**逐列语义对应**
（`investType`↔投资种类 · `investTarget`↔投资项目 · `openingUnadjusted`↔期初余额 · … ·
`collectionStatus`↔发函或期后收款情况），foundation 只需处置 L/M 两列的**措辞差异**（FC-5 以模板为权威）。

⇒ **G2 的前端是按模板列设计的**；G9/G1/G10/G13/G14 的前端是**自研列**（更细、更多、语义体系不同）。
G 循环前端实现质量**不一致**，这一点 slice 与三份 lane spec 都没有登记。

## 4. 这不是「措辞差异」，也不是「行级 mask」

本 spec 此前处置过的三类差异都在**同一套列体系内**：
- FC-5 措辞差异（G2 的 L/M）——「同一列，两边叫法不同」
- 行级 mask（G8 三段 / G13 父子 / G12 布尔列）——「同一列，不同行的 mode 不同」
- payload 形态（`conclusion` vs `remark`）——「同一列，存哪个字段」

本次是**列体系本身不同**：模板的「累计公允价值变动」在前端**没有任何字段承载**，
前端的「持有数量/到期日/估值方法」在模板里**没有任何列承载**。
⇒ 不属既有任何一类裁决可覆盖的范围。

## 5. 处置选项（需拍板，本 Task 不自行决定）

| # | 方案 | 代价 | 产出质量 |
|---|---|---|---|
| **A** | 先把九条逐列语义对照做完，只接入真同构的条 | 中（9 条 × 平均 25 列的语义判断） | 诚实；但本 spec 的「九条接入」可能缩到 0~2 条 |
| **B** | 立「前端列体系 ↔ 模板列体系」映射设计 spec（含审计专业复核：前端 `impairmentLoss` 落模板哪列、模板「期初重分类数」前端要不要加） | 大，且需审计专业判断 | 根治；本 spec 变成它的下游 |
| **C** | 改前端对齐模板（九条明细表按模板列重构） | 最大，且改用户可见 UI | 根治；违反「不改可见文案/UI 属另一作业面」的既有纪律 |
| **D** | **部分受管**：只声明能明确对应的列，其余判 HTML-only | 小 | G9 只受管 3 列 ⇒ 双向回写价值极低，且 OO 侧用户看到的大部分列不受管、编辑会被丢弃 |

🔴 **不可选**：硬凑一套猜测映射。它会产出通过所有现有判据（判据只校验「声明与模板几何一致」，
不校验「前端字段语义与模板列语义一致」）但**把 A 列的值写进 B 列**的契约 —— 比不做更糟。

## 6. 本 Task 已产出 / 未产出

| 项 | 状态 |
|---|---|
| 列同构性普查脚本 + 九条列数基线 | ✅ `_g_column_isomorphism_probe.py` |
| G9 逐列对照（决定性证据） | ✅ 本文件 §2 |
| `phase5_g9_other_noncurrent.py` / `phase5_g9_02_detail.py` | ❌ **未写**（写了就是猜测映射） |
| Task 3~6 的 B 类红判据 | 仍红（26 条），这正是「未交付」的诚实状态 |
