# Task 3~6 证据：红判据先行（G1R-P1/P3/P5/P6/P9/P10/P11/P12/P15/P16/P17/P18）

spec `g-cycle-single-region-detail-lanes` · Task 3~6　实测 2026-09-27

## 判据分类原则（本 spec 通用）

| 类 | 含义 | 本 Task 期望状态 |
|---|---|---|
| **A 类** | `EXPECTED` 期望表 ↔ 模板逐格实测 / 前端按值实测 的一致性 | **绿**（钉住 Task 2 的事实不漂移） |
| **B 类** | 九条 provider 模块存在 + adapter/plan 注册 + 声明与期望表一致 | **红**（Task 8~14 逐条转绿） |

🔴 **A 类必须现在就绿**：它绿了才证明期望表不是凭空写的。A 类如果也红，说明期望表与实测不符，
那 B 类转绿也没有意义（判据会把错的声明判成对的）。
🔴 **B 类不用 xfail**：xfail 会让「交付了但声明错」也算通过（记忆铁律：xfail 标 production bug = 根因修复信号）。

---

## Task 3：`test_g_single_region_p1_p3_p5_p6.py`

**结果：`18 failed, 36 passed`**（A 类 36 全绿 · B 类 18 全红）

### `EXPECTED` 期望表 = 本 spec 声明层唯一真源

九条逐条含 `entry_id` / `adapter_id` / `workbook` / `managed_sheet` / `store_item_id` /
`row_identity_key` / `payload_json_key` / `header` / `row_segments` / `footer_rows` /
`effective_cols` / `composable`，全部值出自 Task 2 逐格实测。

🔴 **`row_segments` 是行级 mask 的统一表达**：`((段名, 行号元组, 该段公式列), …)`。
九条里 **4 条是多段**（G1 三区 / G9 三区 / G3 两区 是「多区同型」；G8 三段 / G13 三段 / G12 两段
是「行级 mask 不同型」），5 条单段。用同一结构表达两种情形，避免为「多区」和「行级 mask」各造一套。

### A 类 36 条通过项（分组）

| 判据 | 断言要点 | 结果 |
|---|---|---|
| P1 三族分布 | `id={G1,G3,G11}` · `rowId={G8,G9,G10,G12,G13}` · `rowKey={G14}`（**逐条固定，不只数个数**） | ✅ |
| P1 按值核字段 | 九条各自 composable 的行接口里有 `{key}: string` 声明（9 参数化） | ✅ |
| P1 GC-6 变异 | 模拟 F 循环白名单 `('rowId','id')` ⇒ **恰好只有 G14** 被误判 | ✅ |
| P1 G14 固定行集 | `G14_LINE_ITEMS` 存在 + `.map(` 生成行 + **无 `addRow`** 三条 | ✅ |
| P1 map-index 区分 | 「下标派生 id 集合」⊊「map-index 集合」，且前者 == `{G1,G3}` | ✅ |
| P3 payload 两形态 | `conclusion=={G1,G3}` · `remark` 7 条 · 并集 == 九条 | ✅ |
| P3 变异 | 「统一写死 remark」**恰好**打到 G1/G3 | ✅ |
| P3 交叉验真库 | G1/G3 的 `store_payload_evidence` 确为 `max=0 / wp=0`（键不存在） | ✅ |
| P5 层级分布 | 单级 `{G11}` · 两级 7 条 · 三级 `{G3}` · **零条无表头** | ✅ |
| P5 表头行性质 | 声明的每个表头行**有文本且无公式**（9 参数化 ×N 行） | ✅ |
| P5 G12 发现 A | `A7=='项目'` + R8 有值无公式 + `R9 公式==('G','I')` + `A9` 是业务名 | ✅ |
| P5 G12 变异 | 「R9 当表头」**丢掉 R9 独有的布尔列 G** | ✅ |
| P5 G3 变异 | 「按两级」⇒ 起点算到 R11（三级表头，无公式）；R12 是区标题；真起点 R13 | ✅ |
| P6 T 列归属 | G1 区① 含 T · G1 区②③ 与 G9 三区全不含 | ✅ |
| P6 不等点唯一 | `g1_all - g9_all == {"T"}` 且 `g9_all - g1_all == set()` | ✅ |
| P6 跨表公式 | 区① 五行 T 列逐行 == `='公允价值测试表G1-6'!H{10+i}-'明细表G1-2'!R{row}` | ✅ |
| P6 复制变异 | 把 G9 列集给 G1 ⇒ 恰好丢 T，且 13 == 12+1 | ✅ |
| P6 三区几何 | G1/G9 行号元组相同 + R11/R18/R25 区标题无公式 + 小计三式 + 合计枚举相加 | ✅ |

### B 类 18 条红（分两组各 9）

```
test_provider_module_exists_and_declares_expected_ids[G9…G1]      9 红
    → phase5_g{9,10,8,14,11,13,12,3,1}_* 模块全部 ModuleNotFoundError
test_store_merge_plan_is_registered_with_oo_neutralization[G9…G1] 9 红
    → g{9,10,8,14,11,13,12,3,1}.* 全部未注册到 STORE_MERGE_REGISTRY
```
🔴 第二组同时钉 **GC-2**：plan 必须带 `oo_crash_neutralization_fn="neutralize_oo_crash_if_formulas"`
（per-file 保守策略，九条无例外）+ `items` 含期望的 `store_item_id`。

### 本 Task 建立的两条判据设计规则（后续 Task 沿用）

1. 🔴 **分布类断言逐条固定，不只数个数**：`{"id": {"G1","G3","G11"}, …}` 而非 `{"id": 3, …}`。
   只数个数时，把 G11 的 `id` 换成 `rowId`、同时把 G8 的 `rowId` 换成 `id` 会照样通过。
2. 🔴 **变异自检要断言「变异确实打中了目标」**：例如 P3 的变异不是「改完还能过吗」，
   而是 `changed == {"G1","G3"}` —— 若变异体一条都没改到，判据就是空转的。

---

## Task 4：`test_g_single_region_p9_p12.py`

**结果：`4 failed, 17 passed`**（A 类 17 全绿 · B 类 4 全红）

### 🔴 实测推翻 design 裁决 G1R-H4 的第②条判据（spec 偏差第七处）

裁决原文：「判据须三条：①extract 不抛 ②**异常类型为 `type_normalization_failure`** ③store 无 TRUE/FALSE」。

按值实测 `merge.normalize_value`（`ValueType` 十族 × 六种输入全跑）：

| 输入 → value_type | `boolean` | `amount` | `integer` | `rate`/`ratio` | `text` | `enum` | `json` |
|---|---|---|---|---|---|---|---|
| `True` (真 bool) | ✅ `True` | 🔴 RAISE | 🔴 RAISE | 🔴 RAISE | 🔴 RAISE | 🔴 RAISE | `b'{"v":true}'` |
| `'TRUE'` (大写串) | 🔴 **RAISE** | 🔴 RAISE | 🔴 RAISE | 🔴 RAISE | ✅ `'TRUE'` | ✅ `'TRUE'` | `b'{"v":"TRUE"}'` |
| `'true'` (小写串) | ✅ `True` | — | — | — | — | — | — |
| `1` / `0` | ✅ `True`/`False` | `Decimal` | `int` | `Decimal` | 🔴 RAISE | 🔴 RAISE | — |

⇒ **第②条描述的是「声明错误时的症状」，不是正确状态**：
- 正确声明（`value_type=boolean` + `mode=formula`）⇒ `normalize_value(True, boolean)` **成功** ⇒
  `type_normalization_failure` 应为 **0 条**。
- 声明成数值族（amount/integer/rate）⇒ **每行一条** `type_normalization_failure`。

**平台旁证（BP-22，`excel_materialize.py:1583-1587` 逐字）**：`boolean` 必须先于数值族判定并落
OOXML 真布尔格 `t="b"`；归到 `number_literal` 时落盘无 `t` ⇒ extract 用 openpyxl 读回 **int** ⇒
`normalize_value` 拒绝折叠 0/1 ⇒ 每行一条 `type_normalization_failure`。
**D2 实测 13/13 行全中，首版发布因此卡在 `roundtrip_verified`**。
⇒ 本 spec 四处布尔列若声明成数值族，会**原样重演** D2 那次失败。

**判据据此改写为双向**：
1. 正向：`normalize_value(True/False/1/0, boolean)` 全部成功 ⇒ 正确声明下零 anomaly
2. 反向（变异）：声明成 `amount`/`integer`/`rate` ⇒ **全部 22 行**都失败（断言 `failures == 22`，
   不是「还能过吗」）
3. 第③条保留：`FieldMode.formula ∈ PROTECTED_MODES` ⇒ 不入 store；
   变异自检断言 `FieldMode.editable ∉ PROTECTED_MODES`（这正是「标 editable」危险的机理）

### 🔴 新增边界登记：大写 `'TRUE'` 在 `boolean` 下也被拒

`normalize_value('TRUE', ValueType.boolean)` **抛** `ValueNormalizationError`（只接受真 bool /
`'true'`/`'false'` / `1`/`0`/`'1'`/`'0'`）。
⇒ 若某册的缓存值是**大写字符串**而非真 bool，即使声明 `boolean` 也会产生 anomaly。
措辞要精确：不是「字符串全被拒」——小写 `'true'` 是被接受的。Task 10/12/13 声明时须确认
materialize 侧走 `boolean_literal`（落 `t="b"`），extract 才读回真 bool。

### 布尔列现算：**三列 × 五个声明单元**（spec 只数了三处）

判据从模板现算（扫九条主表数据区 + footer，匹配 `^=[A-Z]+\d+=(?:[A-Z]+\d+|SUM\()`）：

| 位点 | 行 | 公式 | spec 是否提及 |
|---|---|---|---|
| `G12-2!G` | **只 R9 一行** | `=D9=SUM(E9:F9)` | ✅（但未提「只一行」⇒ 发现 H：也是行级 mask） |
| `G13-2!K` | R11-20 | `=J{r}=D{r}` | ✅ |
| `G13-2!K21` | footer | `=J21=D21` | ❌ **漏** |
| `G14-2!L` | R11-19 | `=D{r}=K{r}` | ✅ |
| `G14-2!L20` | footer | `=D20=K20` | ❌ **漏**（spec 写 footer 是 `SUM(B11:B19)`，那只对 B 列） |

现算集合断言 `{("G12","G"), ("G13","K"), ("G14","L")}`；footer 位点断言 `{("G13","K"), ("G14","L")}`。

### G8 三段的四处差异（spec 记了两处，实测三处 + 一处未记）

| | R11 | R12 | R13-20（八行同型） |
|---|---|---|---|
| `M` 区间 | `=SUM(I11:L11)` **含 L** | `=SUM(I12:K12)` | `=SUM(I13:K13)` |
| `P` 公式 | `=D11+J11` | `=D12+J12+`**`K12`** 🔴 spec 未记 | `=D13+J13` |
| `R` 列 | ✅ `=F11+J11+L11` | ✅ `=F12+J12+L12` | ❌ 手填（`R13 is None`） |
| `T` 列 | ✅ `=Q11+S11` | ❌ 手填（`T12 is None`） | ✅ `=Q13+S13` |

**三个变异自检共同证明「只有三段拆分可行」**：
- 变异①**并集**（`{E,H,M,O,P,Q,R,T}`）⇒ 在 R12 多标 `{T}`、在 R13+ 多标 `{R}` ⇒ 手填格被覆盖
- 变异②**交集**（`{E,H,M,O,P,Q}`）⇒ R12 丢 `{R}`、R13+ 丢 `{T}` ⇒ 可编辑面缩小
- 变异③spec 指定的「用 R11 列集套全区」⇒ R12 的 `M` 区间被按 `SUM(I12:L12)` 归一 ⇒ 多加一列

### B 类 4 条红

```
test_g8_provider_declares_three_sheet_specs                          → sheet_key 须 {g802-r11, g802-r12, g802-r13plus}
test_boolean_column_declared_as_formula_and_boolean_type[G12-G]      → mode=formula + value_type=boolean
test_boolean_column_declared_as_formula_and_boolean_type[G13-K]
test_boolean_column_declared_as_formula_and_boolean_type[G14-L]
```

---

## Task 5：`test_g_single_region_p10_p11_shift.py`（**实测型**，真跑 `shift_sheet_rows`）

**结果：`2 failed, 14 passed`**（A 类 14 全绿 · B 类 2 全红）

实测计划：G11 `RowShiftPlan(insert_at=31, count=3, style_from=30)` ·
G12 `RowShiftPlan(insert_at=14, count=3, style_from=13)`，`total_formula_rows` 各传 footer 行。
🔴 全部断言来自**真跑一次位移**后的 XML，无一条是静态推断（裁决 G1R-H5 明令）。

### P10 —— 裁决 G1R-H5 走「位移」分支，但**分三种情况**（spec 只预见两种）

| 对象 | before | after | 判定 |
|---|---|---|---|
| 既有数据行主格 `G10` | `IF(F10=0,0,F10/$F$31)` | `IF(F10=0,0,F10/`**`$F$34`**`)` | ✅ **位移** |
| 既有数据行主格 `K10` | `IF(J10=0,0,J10/$J$31)` | `IF(J10=0,0,J10/`**`$J$34`**`)` | ✅ **位移**（spec 只提 F31，漏了这个分母） |
| 合计行 `F31` → `F34` | `SUM(F10:F30)` | `SUM(F10:F33)` | ✅ 自身位移 + 区间扩张 |
| 合计行 `J31` → `J34` | `SUM(J10:J30)` | `SUM(J10:J33)` | ✅ |
| footer 的 `G31`/`K31` → `G34`/`K34` | `<f t="shared" si="1"/>`（**成员格无文本**） | 同 | ✅ 由主格 `G10` 承载，已位移 |
| **新插入行 `G31`/`G32`/`G33`** | —（fill-down 造） | `IF(F31=0,0,F31/`**`$F$31`**`)` … | 🔴 **不位移** |

#### 🔴 实测纠正①：footer 的占比格是 **shared formula 成员**，不是独立公式文本

首版判据假设 `G31` 有文本 ⇒ 实测 `_formula_of(before,"G31") is None`，格体是自闭合
`<f t="shared" si="1"/>`。**主格在 `G10`**。
⇒ **判断「占比列是否指向真实合计行」必须看 shared 组主格**；看成员格会拿到 `None` 而误判成「无公式」。
这条已固化为判据 `test_total_row_ratio_cells_are_shared_formula_members_not_literal_text`。

#### 🔴🔴 实测纠正②（本 Task 最重要）：框架层真实缺陷 —— 新插入行保留过期的绝对分母

位移后逐字：
```
R31: IF(F31=0,0,F31/$F$31)      ← 分母应为 $F$34
R32: IF(F32=0,0,F32/$F$31)
R33: IF(F33=0,0,F33/$F$31)
R34: SUM(F10:F33)               ← 真正的合计行在这里
R31 的 F 列: D31+E31            ← R31 现在是新行，不是合计行
```
**根因（按值定位）**：
- `excel_row_shift._build_inserted_row`（L1877）造新行时用 `translate_formula_rows(...)`（L1054）
- `translate_formula_rows` 固定 `freeze_absolute_rows=True`（L1095），注释逐字：「`$` 锁定的绝对行**不动**（那正是 `$` 的语义）」—— 这是 Excel **填充柄**的正确语义
- 但造出来的新行公式**随后没有再经过插行位移**那条路（`freeze_absolute_rows=False`，其注释 L1035-1036 逐字：「`$` 前缀的绝对行**同样**位移 …… 不位移会让绝对引用指向别的格」）

⇒ **两条语义各自都对，组合顺序错了**。Excel 自己的顺序是「**先插行**（`$F$31`→`$F$34`）**再填充**（`$F$34` 保持）」⇒ 结果 `$F$34`。框架层顺序相反，于是新行留下位移前的坐标。

**影响**：用户在新插入行填 D/E 列后，占比分母变成「第一个新行自己的 F 值」而非合计 ⇒ 占比算错。
新行刚插入时值为 0，`IF(F31=0,0,…)` 返回 0，**不立即显错** ⇒ 静默错误。

**处置（本 spec 范围内，诚实不扩大）**：
| # | 决定 |
|---|---|
| 1 | 判据**钉住当前行为**（不是期望行为）：`test_newly_inserted_rows_keep_the_stale_absolute_denominator`，且 `test_no_static_inference…` 精确断言「残留 `$F$31` 的行**恰为** {31,32,33}」（出现既有行 ≤30 则是更严重回归） |
| 2 | 🔴 **本 spec 不改 `excel_row_shift.py`**：跨循环影响面（任何「数据行引用 footer 绝对坐标」的表）+ 引擎核心。该文件当前未被并发会话占用（非 `M`），但修它属框架层另立项 |
| 3 | **G11 的 G/K 两列仍受管**（留在 `formula_columns`）：既有行位移正确；新行缺陷属**插行路径**的独立缺陷，不是受管声明缺陷，且**受管前就存在**（用户现在在 OO 里插行同样踩） ⇒ 非本 spec 引入的回归 |
| 4 | Task 11 的 G11 声明里显式登记该已知缺陷 |
| 5 | 最小修复方案（供后续立项）：`_build_inserted_row` 在 `translate_formula_rows` 之后，对新行公式的**绝对行引用**再套一次 `plan` 重映射；或给 `translate_formula_rows` 加「绝对行按 plan 重映射」开关。修好后本 spec 的 `test_newly_inserted_rows_keep_the_stale_absolute_denominator` 必红 —— 届时把断言改成 `$F$34` 并记修复 commit |

### P11 —— 框架层扩张规则实测：「起点不动 + 末行 = last_data_row」

| footer 格 | before | after（移到 R17） | 说明 |
|---|---|---|---|
| `I14` | `SUM(I7:I13)` | `SUM(I7:`**`I16`**`)` | 起点 `I7`（表头组行）**保持不动**，末行 13→16 |
| `C14` | `SUM(C9:C13)` | `SUM(C9:`**`C16`**`)` | 正常整区间，同规则 ⇒ 不是特例处理 |
| `B14` | `SUM(B9,B12,B13:B13)` | `SUM(B9,B12,B13:`**`B16`**`)` | 🔴 见下 |

#### 结论①：缺陷②（起点越到表头行）**数值上无害，插行后也不放大**

起点 `I7` 保持 ⇒ 区间仍含表头格。判据从模板取证 `I7` 是**字符串且非公式**（表头文本）⇒ SUM 忽略文本。
⇒ 只是**区间声明错**，不是数值错。框架层的「区间末行 = last_data_row」规则对它是安全的。

#### 🔴 结论②：缺陷①（`B14` 漏加 B10/B11）**插行后依然存在，不自愈**

末段区间 `B13:B13` 扩张为 `B13:B16`（吸收新行），但**枚举项 `B9`/`B12` 不变** ⇒
**`B10` / `B11` 仍然不在合计里**。判据逐项断言 `"B10" not in got and "B11" not in got`。
⇒ 用户在 R10（模板**预填**的第二行数据「预期销售和预期采购的外汇净头寸」）或 R11 填 B 列金额，
合计**永远**不计入 ⇒ **真实数值错**，且插行不会修好它 ⇒ 必须走覆盖层修（模板字节只读）。
对照：C 列的整区间形态天然覆盖 C10/C11。

#### 结论③：布尔列所在行不受 footer 侧插行影响

`G9 = D9=SUM(E9:F9)` / `I9` / `I10` 在位移后**逐字不变**（插入点 R14 在它们之后）⇒
P9（布尔列行级 mask）与 P11（插行）的交叉面无风险。

### B 类 2 条红

```
test_g11_provider_declares_footer_carries_total_formula      → G11 provider 未交付（footer_row=31 + carries_total_formula=True）
test_g12_provider_records_the_template_defects_in_its_docstring → G12 provider 未交付（docstring 须逐字登记两处模板缺陷）
```

---

## Task 6：`test_g_single_region_p15_p18.py`

**结果：`2 failed, 22 passed`**（A 类 22 全绿 · B 类 2 全红）

### 🔴 判据设计第三条规则：B 类红判据写**正向**，不写倒置

首版把 P18 的两条写成倒置（「九条**全不在** digest / 契约目录」）⇒ **现在是绿的**，
要等 Task 15 交付后才变红、再由人去反转。那等于把「该红的时候不红」制度化了。
改为正向（「九条**全在**」）后：Task 15 之前一直红、交付后自动转绿、**无需改判据**。

⇒ 规则固化：**红判据一律写成「交付后应成立的正向断言」**，靠它本身的红绿变化表达进度。

### P15：G3 definedName —— 按集合比对，不按数量

| 判据 | 断言 | 结果 |
|---|---|---|
| 数量级 + 对比 | G3 `> 300`（现算 **491**，spec 说「约 480」）；其余八册**全为 0** | ✅ |
| 三族残留并存 | `_xlnm.*`（Print_Area/Database）· `UFPrn*`（用友打印模板）· 中文名 三族各有命中 | ✅ |
| helper 可复算 | `defined_names_of(book)` 两次结果相等、返回 `frozenset` ⇒ Task 14/15 拿它做受管前后比对 | ✅ |
| 🔴 变异自检 | 构造「同量异名」集合：**数量比对通过而集合比对失败** ⇒ 证明按数量比会放过改名 | ✅ |

🔴 **不写死 491**（GC-10）：判据只断言 `> 300` 与「其余八册为 0」的对比关系，
确切集合由 helper 现算，供 Task 14/15 做同一次运行内的前后比对。

### P16：四张 `-修订前` 逐字排除

| code | 逐字名 | state | 行 | 合并 |
|---|---|---|---|---|
| G11 | `投资收益实质性程序表G11A-修订前` | hidden | 34 | 56 |
| G12 | `净敞口套期收益审计程序表G12A-修订前` | hidden | 63 | **115**（四张最大 ✅ design §顺带发现 3） |
| G13 | `公允价值变动收益审计程序表G13A-修订前` | hidden | 46 | 80 |
| G14 | `信用减值损失审计程序表G14A -修订前` | hidden | 46 | 78 |

🔴 **G14 的空格在名字中间**（`G14A` 之后、`-修订前` 之前）：
- `title.strip() == title` ✅（strip 去不掉中间的空格）
- `title.replace(" ", "") != title` ✅（去空格会得到**另一个名字**）
- **变异自检**：去空格名 `信用减值损失审计程序表G14A-修订前` **不在** G14 册的 `sheetnames` 里
  ⇒ 排除清单若写去空格版就会漏排除

另两条 A 类：四张全落在本 spec 的四册损益类里（其余五册零 `-修订前` 残留）。

### P17：prefill 不回归 —— 🔴 两处实测纠正

#### 纠正①：**同一个 `wp_code` 有多个 prefill 块**

首版判据对该 wp_code 的**所有**块断言主表名 ⇒ 被 `审定表G13-1` 打红。实测九条相关块共 **33 个**：

| 块类型 | 例 | 数量 |
|---|---|---|
| 审定表 | `[21] G1 审定表G1-1` … `[37] G14 审定表G14-1` | 9（九条各 1） |
| **主受管明细表** | `[161] G1 明细表G1-2` · `[167] G8 明细表G8-2` · `[168] G11 明细分析表G11-2` · `[169] G13 明细表G13-2` · `[170] G14 明细表G14-2` | **5** |
| 附注披露（上市/国企） | `[162]/[163]` `[225]/[226]` … | 18 |

⇒ 定位方式改为「该 entry 的 `managed_sheet`」并断言**恰好命中一块**；
另加逐字反证：错名 `明细分析表G13-2` / `明细分析表G14-2` 不得出现在任何块上。

#### 🔴 纠正②（顺带发现，登记不补）：九条里只有五条有主受管表 prefill 块

**有**：G1 / G8 / G11 / G13 / G14　　**无**：**G3 / G9 / G10 / G12**

⇒ P17 的「两块不回归」只覆盖 G13/G14；另外四条**根本没有**可回归的块。
这是 prefill **覆盖缺口**（不是错名），归模板/取数配置治理，本 spec 只登记 + 判据钉住现状
（`test_only_five_of_the_nine_have_a_main_table_prefill_block`，四条缺口被补上时本判据会红 ⇒ 届时更新登记）。

另有一条更强的判据（不只守两块）：本 spec 九条的**每个** prefill 块，其 `sheet` 名必须
真存在于对应模板（GC-8 sheet 存在性守卫在九条上的落地）——能抓住将来任何新增块的错名。

#### 顺带发现（登记不修）：`[171]` 的 `sheet` 是 `'明细表J1-2 '`（**尾部带空格**）

属 J 循环（本 spec 范围外）。登记在此，J 循环的 spec 不必重新发现。判据只断言该形态存在。

### P18：零回归现算 + seed 边界

#### 🔴 GC-10 的可执行论据：契约目录与 golden digest **本就不同步**

| 现算项 | 本次值 |
|---|---|
| 契约目录文件数 | **17**（16 生产契约 + `_example.candidate.json`） |
| golden digest 的 `providers` 条数 | **9** |
| `digest_count` 字段 | 105 |

⇒ 三个数互不相等。判据 `test_contract_dir_and_golden_digest_are_not_in_sync_so_counts_must_be_computed`
把「两者不相等」本身写成断言 —— 任何「断言两者相等」或「写死某个数」的判据都会在
并发会话加契约时假红（本轮并发会话已加 f3/f4/f5/g2 四个契约）。

#### 零回归基线的落地方式：逐项快照而非比数

`{adapter_id: (contract_payload_sha256, sorted(sheet_digests.items()), store_projection_sha256,
instrumentation_sha256)}` —— Task 15 复算时**逐项**比对，本 spec 未触及的条目须逐字节相等。
判据另断言「无重复 `adapter_id`」（否则快照会丢条目）+「每条都有 `contract_payload_sha256`」。

#### 🔴 术语纠正：G9 的「605 B / 2 wp」应读作「2 行 store 记录，其中 1 行非空」

`store_payload_evidence` 实测 `wp_count_with_payload = **1**`（不是 2）。note 逐字：
> G9-detail-rows 真库两行：一行 605 B（真实载荷…）、一行 2 B（空数组）

⇒ 该键在 **2 个 wp 上有 store 行**，但**只有 1 个 wp 的载荷非空**。两个数不是一回事；
seed 判据若按「2 wp 有载荷」写，会以为已有两份真数据。判据已断言 `== 1` 并在消息里写明区分。

#### G1/G3 的「键不存在」态与「空数组」态必须区分

| 态 | 条 | `(max_payload_bytes, wp_count_with_payload)` |
|---|---|---|
| 键不存在 | **G1 / G3** | `(0, 0)` |
| 空数组 2 B | G8 / G10 / G11 / G12 / G13 / G14 | `(2, 1)` |
| 有真实载荷 | **G9** | `(605, 1)` |

⇒ seed 对 G1/G3 须先**建键**；P18 的「未 seed 时验收脚本显式失败」必须能区分两态，
否则 G1/G3 会以「2 B 空数组」的假象通过。

### B 类 2 条红

```
test_all_nine_adapters_are_in_the_golden_digest   → 九条 adapter 全未进 digest（digest 现有 9 条）
test_all_nine_contracts_are_published             → 九条契约全未发布（目录现有 17 文件）
```
