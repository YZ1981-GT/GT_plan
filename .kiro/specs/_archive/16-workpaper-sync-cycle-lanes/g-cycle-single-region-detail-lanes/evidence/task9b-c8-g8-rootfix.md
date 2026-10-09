# Task 9b / C-8：G8 其他权益工具投资 —— FVOCI 23 列对齐 + 模板四处行级缺陷

spec `g-cycle-single-region-detail-lanes` 九条 lane 的**第三条**。commit `8d241089a`（22 文件）。

原 Task 9 是「G10 + G8」。已拆 9 / 9b —— 行级 mask 与 G10 无共享代码，绑一条会让 G10 的
完成度无法诚实表达。

---

## 1. 模板逐格实测

`G/G8 其他权益工具投资.xlsx`：450,079 B / sha256 `5c8d3de7ee60ffef8677768c6c3966a313d4210ebc96b19a12c56721954b83b6` / 11 sheets。
受管 sheet `明细表G8-2`：`max_row=39` / `max_column=24` / **0 个 definedName**。

### 1.1 表头几何

R9 的**横向**合并区恰三个：`C9:F9` 期初余额 · `I9:N9` 本期变动 · `O9:R9` 期末余额。
另有九个跨两行的单列合并（A/B/G/H/S/T/U/V/W）。

有效内容列 **23**（A..W），`X` 空 ⇒ `uuid_col="X"`（有效列右移一列，同 G10 的口径）。

🔴 `R22` 是「三、审计说明：」且 `N22 = =A22`（模板怪癖，在受管区之外，判据断言它在 footer 之下不受管）。

### 1.2 🔴 四处行级公式缺陷

| 行 | `M` 本期变动合计 | `P` 期末累计FV变动 | `R` 期末OCI累计 | `T` 审定数 |
|---|---|---|---|---|
| R11 | `=SUM(I11:L11)` ✅含 L | `=D11+J11` ❌漏 K | ✅ `=F+J+L` | ✅ `=Q+S` |
| R12 | `=SUM(I12:K12)` ❌漏 L | `=D12+J12+K12` ✅含 K | ✅ `=F+J+L` | ❌**整格无公式** |
| R13..R20 | `=SUM(I:K)` ❌漏 L | `=D+J` ❌漏 K | ❌**整格无公式** | ✅ `=Q+S` |

会计判读：`M` 应含 L（本期变动合计 = 成本变动 + 公允价值变动 + 处置结转 + OCI 转留存）·
`P` 应含 K（期末累计 = 期初累计 + 本期变动 + 处置结转）· `R`(=F+J+L) 与 `T`(=Q+S) 都是
恒等式、每行都该有。即 **R11 与 R12 各对一半、R13-R20 两处都漏**。

与 G5「三段合计各漏加一个小计」同族。本 spec 已确立：**模板真实缺陷走覆盖层，不改模板字节**。

### 1.3 裸 IF 12 格

`审定表G8-1` **12** 格（全 G 循环最少），其余 10 张 sheet 零命中，受管表干净。
仍按 per-file 保守策略挂 `oo_crash_neutralization_fn`。

---

## 2. 🔴 与 G9/G10 **反向**：G8 是 FVOCI，OCI 列不可删

受管表内注释逐字：

> 在初始确认时，企业可以将非交易性权益工具投资**指定为以公允价值计量且其变动计入其他
> 综合收益**的金融资产。该指定一经作出，**不得撤销**。

⇒ 模板的三个 OCI 列（`F` 期初累计 / `L` 本期转留存 / `R` 期末累计）是 CAS22 要求的。

G9/G10 的前端根治**删掉**了 OCI/减值四列，依据是「那两张表五类全 FVTPL，CAS22 下不确认
OCI 与减值」。这条依据对 G8 **反向**成立 —— 照抄它们的移除清单会把准则要求的列删掉。
同理 G6（其他债权投资）也是 FVOCI。C-6 evidence §12 把这条列为「与 G9 相比要反向注意
的四条」之首。

判据 `TestFvociColumnsAreRequiredNotRemovable` 四条钉住：
三列都在受管面 · header 逐格取自模板（F 与 R **同名**，靠列位区分，两格都核）·
**按值搜整册确认「不得撤销」那句注释仍在**（模板若真改口径，保留依据要重新论证）·
移除清单里不得出现 OCI 列。

### 2.1 前端真重建：24 字段 → 23 字段

| 动作 | 内容 |
|---|---|
| 拆 3+3 分量 | `openingBalance` → C 成本 / D 累计公允价值变动 / E 合计；`closingBalance` → O / P / Q |
| 补 2 列 | K 处置时公允价值变动结转 · N 本期确认的股利收入 |
| 合并 1 组 | `increaseAmount` + `decreaseAmount` → I（模板 I 是**净额**单列） |
| 改名对齐 2 列 | `ociOpeningCumulative` → F `openingOciCumulative`；`ociCumulativeChange` → R `closingOciCumulative`（原两名无一对应模板语义） |
| 删 8 列 | 见下 |

删除的 8 列（台账落 `DROPPED_LEGACY_G8_FIELDS`，判据断言 8 条且每条 reason 非空）：

* `fairValueLevel` / `valuationMethod` / `shareCount` / `pricePerShare` / `fairValueTotal`
  —— 权威源是 `公允价值测试表G8-4`
* `decreaseAmount` —— 模板 I 是净额单列，拆增减会与 I 双源
* 🔴 `ociCurrentChange` —— **FVOCI 下「本期 OCI」就是模板 J 列「本期公允价值变动」**。
  改造前这两个字段并存，还专门写了一条校验「本期 OCI 变动与 FV 变动不一致（FVOCI 通常
  应对等）」—— 那条校验本身就是双源的证据。合并成 J 一列后这条校验不再存在（不可能不一致）。
* `remark` —— 模板无此列

### 2.2 跨表消费方

| 消费方 | 原行为 | 处置 |
|---|---|---|
| `g8CrossHelpers.pushG8FvToDetail` | G8-4 往 G8-2 回写层次/数量/单价/FV合计/估值方法五列 | **停用**恒返 0 不写 store（权威源就是 G8-4，且 G8-2 重构后没有这五列） |
| `useG8FairValueTest.syncFromDetail` | 从 G8-2 倒灌数量/单价/层次/估值方法 | 只取「名单 + 期末审定金额」，数量/单价以本表为准 |
| `useG8FairValueTest.detailClosingAdjustedTotal` | `closingAdjusted ?? closingBalance` 回退链 | 一律取模板 T 列 |
| `g8DisclosureFromDetail` | 读 `openingBalance`/`closingBalance`/`fairValueTotal`/`ociCurrentChange`/`ociCumulativeChange` | 改取 E/Q/J/R 四列 |

`pushG8FvToDesignation`（G8-4 → G8-5 层次同步）方向是对的，**未动**。
与 G9 的 `pushG9FvToDetail`、G10 的 `pushG10FvToDetail` 同族错误 —— 三条同批处置。

---

## 3. 🔴 处置由框架层两条硬约束唯一确定（不是风格选择）

本轮的核心发现：`mode` 的取值不是自由裁量，而被两条现成的校验夹死。

| # | 约束 | 位置 |
|---|---|---|
| ① | `mode=formula` 的列必须落在 `formula_mask` 覆盖的列跨度内（**CS-13**） | `contracts._parse_table` |
| ② | 写受保护格时要求 `view.has_formula`，否则抛 `ProtectedRegionWriteError` | `excel_materialize` |

⇒ 逐列裁决：

* **`M`/`P`**：模板每行**都有**公式（只是口径逐行不同）⇒ 可判 `formula`，进
  `FORMULA_COLUMNS_G802`（受 `formula_mask` 保护，OO 侧改不了）。但**不进**
  `FORMULA_TEMPLATES_G802` —— 它们逐行不同形，单条模板表达不了；逐行实测落
  `TEMPLATE_ROW_FORMULAS_G802`（20 格），判据逐格比对。
* **`R`/`T`**：模板在 R13-R20 / R12 **整格无公式** ⇒ 判 `formula` 会在 materialize 阶段
  直接抛 ⇒ 只能判 **`editable`**。

### 3.1 判据 P12 的技术根据 = 约束②

P12 原文「判据证明 R13 的 R 列与 R12 的 T 列不被误标」。本轮才找到它的硬根据：
就是 `ProtectedRegionWriteError`。判据 `test_p12_r_and_t_are_not_mislabeled_as_formula`
把这条写成可复核的断言（mode == editable + 不在 formula_columns + 派生公式登记齐备）。

🔴 **首版实现踩过这个坑**：我最初按「两个机制分开取值」把 `M/P/R/T` 全判 formula 而
`formula_columns` 只放 `E/H/O/Q` 四列 —— `parse_contract` 当场被 CS-13 拒。
契约生成器「写盘前先跑 parse_contract」这道门把错形态拦在了落盘之前（G2 立的规矩）。

### 3.2 如实登记的欠账：R/T 双向同步会被前端重算覆盖

`R`/`T` 判 `editable` ⇒ OO 侧可填 → 回写 store → 前端 `enrichG8DetailRow` 按恒等式
（`R=F+J+L` / `T=Q+S`）**重算覆盖**。

这是模板漏公式的直接后果，不是实现缺陷。修根因的两条路都不在本 lane：
① 改模板字节 —— `backend/wp_templates/` 运行时只读 + sha 冻结，**禁止**；
② 走覆盖层 —— 框架层尚无该机制，且补 M/P 的漏项会改变审计数字，需会计专业复核。

三处如实登记：`phase5_g8_02_detail` 模块头 · 交付台账 reason · **前端编制提示**
（新增一段「与 Excel 联动」，明确告知用户在本页填分量、不要在 Excel 侧改这两列）。

### 3.3 🔴 裁决 G1R-H3 两处措辞已修正

① 「拆 `g802-r11`/`g802-r12plus`（或三 spec）」**不可行**：`RowTableSheetSpec` 的分段
能力只有 `row_section_field`（按**行对象的字段值**过滤，见 `iter_store_rows`）。G8 是
**连续** R11-R20 里逐行公式不同，前端 store 是顺序数组、没有也不该有区归属字段 ——
行的物理位置不是业务属性，写进持久化数据就是 BP-11「语义耦合行身份」的同族问题
（插行即错）。引擎不支持按数组下标切段，硬造三段只会让区②③恒空。
② 「并集取 formula、交集取 editable」按字面会让 R/T 撞 `ProtectedRegionWriteError`。
正确口径是「**模板每行都有公式**才可判 formula」。

⇒ 原判据 `test_g8_provider_declares_three_sheet_specs` 已按实测改写为
`test_g8_row_level_formula_mask_is_expressed_without_faking_sections`：前提被推翻，
但**不放宽** —— 改为断言「单 spec + 不得声明 row_section_field + 逐行台账齐备（M/P × 10 行
= 20 格、缺陷台账覆盖四列）+ P12 三条」。改写理由逐条写在该判据的 docstring 里。

---

## 4. 验证

| 判据 | 结果 |
|---|---|
| `test_g8_column_isomorphism.py`（新建） | **95 passed** |
| `useG8Detail.spec.ts`（重写 46 条） | **46 passed** |
| G8 全部 18 个前端 spec | **212 passed / 0 failed** |
| 六 lane 判据文件 | 22 failed → **19 failed** |
| `vue-tsc -p tsconfig._g8.json` | 64 → **14 error**，我改的三个文件零条 |
| 零回归门逐 provider 现算 | 15 家里 14 家算出三个 digest，唯一 FAIL 仍是 f1 |
| 文件行数门禁 | 全过（entry 720 < 800；test_task49 压到 3299 = 阈值上限） |

### 4.1 顺带修掉的真缺陷（触类旁通）

`test_task49` 的 `test_registry_delivered_contracts_match_the_declared_slice_delivery`
按 `registry.py` **源码正则**读台账。并发会话把台账抽到伴生模块
`adapters/delivered_contracts_ledger.py`（行数门禁的合理处置）后，正则当即失配成
「0 条 entry_id」—— 判据自己有条「≥4 条否则恒真」的自保，所以是打红而不是假绿。
改为**模块属性现读**，对搬文件免疫。

这类「文件一搬判据就瞎」的耦合不是 G8 引入的，但撞在本轮判据面上，一并消掉。

### 4.2 另一个教训：门禁必须从仓库根跑

`check_file_size.py` 的 whitelist 键是仓库相对路径（`backend/tests/...`）。
从 `backend/` 目录传 `tests/...` 会**匹配不到 whitelist 也匹配不到默认上限**，
rc=0 假绿 —— 本轮实测：同一个 3300 行文件，从 backend 跑 rc=0、从仓库根跑 rc=2。
⇒ 自查行数一律 `cd` 仓库根（或直接看 pre-commit 的输出）。

---

## 5. 后续 lane 可复用的结论

1. `mode` 的取值不是自由裁量：先查 **CS-13** 与 **`ProtectedRegionWriteError`** 两条约束，
   再决定某列判 formula 还是 editable。判据要把约束写进 docstring，不然下一条会重踩。
2. 「模板逐行公式不同」不等于「要拆多段」—— 引擎只支持按字段值分段；逐行差异用
   **实测台账 + 逐格判据**表达，比伪造分段诚实且不会恒空。
3. 遇到「FVOCI vs FVTPL」这类**会计口径反向**的相邻科目，移除清单绝不可照抄；
   判据要按值回源到模板注释（如本条搜「不得撤销」）。
4. 前端字段「成对出现且有一条校验提醒它们应相等」= **双源信号**，应合并成一列而不是
   保留校验（本条的 `ociCurrentChange` vs `movementFvChange`）。
5. 契约生成器「写盘前先跑 `parse_contract`」这道门是真在拦错的 —— 本轮首版错形态就是
   它拦下的。新 lane 一律照 G2/G9/G10 的生成器写法，不要只写不校验。
