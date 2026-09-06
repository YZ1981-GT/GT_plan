# BP-21 交接件：受管区末行的「……」排版占位行

> 提请人 A（L1 首版发布泳道）· 落地人 **B**（L2a 结构性插行泳道）· 2026-09-04
> 前置阅读：`docs/operations/oo-html-bidirectional-writeback-5-lane-assignment.md` §11.3
> 本件自包含 —— 不必回读上游即可开工。

---

## 1. 一句话

受管区的行范围是**派生**的（`anchor` + `header_rows` → 首行，footer 锚点「合计」→ 末行），
派生规则「表头与合计之间都是数据行」把中文审计模板的**续行省略号行**一并吞进了受管区，
于是首版发布试图把 `……` 当业务数据写回 `integer` 字段。

**它挡着两个 entry**：H1 现在就挡着；D2 在你接完插行后会撞同一处。

## 2. 现场

H1 权威模板 `H/H1 固定资产.xlsx` 的受管 sheet「减少检查表H1-8」：

```
A13..A26 = 1 .. 14      整数 seq，合法业务数据
A27      = ……            ← 排版占位（U+2026 ×2，模板里写成 &#8230;&#8230;）
A28      = 合计          footer 锚点
```

契约 `h1.disposal_check` 把 `seq` 声明为 `mode=auto_source` / `value_type=integer` /
`cell.row_from=row_identity` / 列 A。受管区派生成 **13..27（15 行）**，第 27 行也就被当成
第 15 条业务行。首版发布实测：

```
EditableCellWriteError
  受管格 A27（disposal_check_rows/{row_uuid}/seq）的值 '……' 无法按 integer 规范化
  error_code = excel_materialize_editable_write_failed
```

H1 的整份 projection 只有 **15 个值**（空表单，全是 `seq` 列的预印序号）：14 个合法整数
+ 1 个 `……`。**整条首版链被一格排版符号卡住。**

## 3. 为什么判定为平台级规则，而不是逐契约排除

全模板库实测（349 份 xlsx / 2602 张 sheet，0 失败，1.4 秒）：

| 事实 | 值 |
|---|---|
整格为纯省略号的 A/B/C 列格 | **842** |
「`……` 行紧跟合计/小计/总计行」 | **170** |
涉及模板 | **37 份** |
涉及 wp_code | **35 个**（A1 A3 A5 D0 D1 D2 D4 E1 F1 F2 G1 G5 H1 H2 H3 H4 H5 H7 H8 H9 I1 I2 I5 K1 K10 K13 K3 K6 K8 K9 L5 M9 N1 N5 S21） |
H1 自身命中 | **5 处** |
pilot 契约声明了**行级**排除的 | **0 / 4** |
pilot 契约声明了**列级**排除且理由引用 `……` 的 | **1 / 4** |

最后两行是关键：契约体系对 `……` 的**列**方向**已有先例** —— `h1.disposal_check` 的
`review.excluded_columns` 排除了 X 列，理由「模板的扩展占位列（表头文本恰为 `……`），没有业务
语义也没有对应前端字段 —— 按 Requirement 6.1「禁止无来源自造字段」不声明为受管字段」。
缺的只是**行**方向的对应物。

逐契约写 `excluded_rows` 等于要写 170 条声明，且每份新契约都得记得写 —— 那是必然遗漏的形态。
故裁决为**平台级派生规则**。

被否的另外三个方案与理由：

| 方案 | 否决理由 |
|---|---|
`seq` 的 `value_type` 改 `text` | 掩盖问题：`……` 仍被当业务行，OO 里审计师能往省略号行里填数据。语义错 |
换别的 entry 做首版 | 四个 pilot 里 G7 已发布，H1/D2 被挡，B60 卡 OOXML 门 —— 无处可换 |
在 A 的叠加层里剔掉该字段 | 剔了 materialize 不写，但 `extract` 仍读得到 ⇒ `_assert_roundtrip_equivalent` 判「反读出未提交的受管字段」。单侧剔除解决不了 |

## 4. 请你做的事

**改动点**：`backend/app/services/workpaper_sync/excel_extract.py` 的
`resolve_managed_region` —— 派生 `last_row` 时，从末行往上剔除「该行在受管区首列上的取值是
**纯排版省略号**」的行。

「纯排版省略号」的口径（与 A 的清册脚本同源，见 §5）：单元格文本含至少一个 U+2026，
且除 `U+2026` / `.` / `。` / 空格外无其它字符。

预期效果：H1 受管区 `13..27`（15 行）→ `13..26`（14 行）；D2 `13..25`（13 行）→ `13..24`
（12 行）；G7 `79..83` 不变。

### 🔴 两件必须由你确认的事（A 无法代判，因为要动你的文件）

1. **收缩 `last_row` 后 `table_ref` 与 `row_uuids` 仍覆盖旧区间**。实测现状：
   H1 `table_ref=A13:AB27`、`identity_inventory.row_uuids` 含 13..27 **共 15 项**
   （`GTROW-H18-0013` … `GTROW-H18-0027`）。收缩 region 而不动这两处会不会触发既有
   identity 断言（`assert_identity_inventory_usable` / `IdentityRetentionError` /
   `RowIdentityWriteError`）？三种可能的处置，请你裁决：
   * 只收 region，`table_ref`/`row_uuids` 保留冗余项（最小改动，但要证明冗余项不致害）
   * region 与 instrumentation 同步收缩（要改 `excel_instrumentation`，波及 digest）
   * region 收缩 + 把被剔除行的 uuid 显式登记为「非业务行」
2. **该规则与你 spec 的位移清单/`_SHEET_STRUCTURE_BLOCKS` 是否相容**。你的 `RowShiftPlan`
   的 `insert_at` 通常取「最后一个既有数据行 +1」；受管区末行从 27 变 26 后，插入点与
   `style_from` 都会平移一行，且新行会插在 `……` 行**之前**（这正是业务上想要的：续行占位符
   应当留在数据行之后）。请确认你 Wave 4 的 Task 16 算 `RowShiftPlan` 时用的是收缩后的区间。

## 5. 验收判据（已入库，别重造）

```
python backend/scripts/check/check_managed_region_typography_rows.py --expect-managed-region-hits 0
```

该脚本两段：

* **§A 全库清册** —— 裁决证据（170 / 37 份 / 35 个 wp_code）。🔴 **这个数不随你的修复变化**，
  模板里的 `……` 行还在，变的只是它是否落进受管区。别拿它当验收。
* **§B 逐 pilot 受管区扫描** —— **这才是验收判据**。它现读你的
  `resolve_managed_region` 的**真实返回值**（不是照 anchor/header_rows 再推一份副本 ——
  副本会让「修了也不变绿」），再看区间内有没有占位行。

**落地前实测（现在的基线，退出码 1）**：

```
=== §B 逐 pilot 受管区扫描（BP-21 验收判据）===
  entry 登记 4 个 · 实扫 3 个 · 因 OOXML 门不可验 1 个
  区内含排版占位行的 entry: 2 个（占位行共 2 行）
    ⊘ xlsx/b60/gt-b60-bundle status=unverifiable_ooxml_gate gate=external_relationships
    🔴 xlsx/gt-d2-accounts-receivable 明细表D2-2 A13..25（13 行，table_ref=A13:AN25）
        区内占位行: A25
    🔴 xlsx/gt-h1-fixed-assets 减少检查表H1-8 A13..27（15 行，table_ref=A13:AB27）
        区内占位行: A27
    ✅ xlsx/gt-g7-long-term-equity-main 附注披露信息（国企） A79..83（5 行，table_ref=A79:N83）
🔴 BP-21 验收未过：受管区内排版占位行期望 0 行，实测 2 行
```

**落地后应为**：H1 与 D2 两行变 ✅，`placeholder_rows_in_regions = 0`，退出码 **0**。

脚本零数据库（`stage_instrumented_substrate` 签名里没有 session），1.4 秒跑完，可挂 CI。
B60 在 OOXML 安全门被拒属既有事实，脚本把它记 `unverifiable_ooxml_gate` 并**从分母剔除且把
剔除数写出来**（不静默当成通过）。

### 还要做一条反向自检

按仓库纪律，写完守卫必做变异检验。建议的变异：把你的剔除条件短路（`if False and …`），
断言 §B 重新打红且**打红的正是 H1 与 D2 那两条**。没打红 = 守卫有缺陷，不是代码没问题。

## 6. A 已经做完、你不必重做的部分

* **裁决与取证**：170 / 37 份 / 35 个 wp_code 的全库实测，含「pilot 契约 0/4 声明行级排除、
  1/4 声明列级排除且理由引用 `……`」这条对照。
* **验收判据脚本**：`backend/scripts/check/check_managed_region_typography_rows.py`
  （§A 清册 + §B 受管区扫描 + `--expect-managed-region-hits`）。
* **首版链上的其它四处缺陷**：已全部修完并用 G7 验证（`projection_contract` lane 的首版
  representation 已落库，10/10 全链通过、幂等已验）。所以 H1 现在**只剩** BP-21 这一处；
  它一变绿，H1 的首版就能发。
* **诊断可读性**：首版宿主的封闭结算词表已扩到 11 格，H1 现在落
  `blocked_template_contract_drift` 并带解除方，不再被误报成「契约未复核」。

## 7. 一条通用教训（值得进 `#conventions`）

取证脚本第一版只解了 `&#8230;` 一个数字字符引用。H1 权威模板把中文**全部**写成
`&#21512;&#35745;` 形态（`sharedStrings` 为 **0** 条），于是「合计」认不出来，**H1 自己反而
漏计**，读数偏低成 162 处 / 35 份。解全部 `&#NNNN;` / `&#xHH;` 后是 170 处 / 37 份。

⇒ **任何对 xlsx 做文本判据的脚本，必须解全部数字字符引用**；只解自己关心的那一个，会让判据
在恰好用实体编码的模板上静默失效 —— 而那种模板恰恰是被 openpyxl 之类工具重写过的，也就是最
需要判据的那批。
