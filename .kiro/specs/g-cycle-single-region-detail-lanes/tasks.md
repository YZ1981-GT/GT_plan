# Implementation Plan

## Overview

**spec**：`g-cycle-single-region-detail-lanes`　**创建**：2026-09-26　**状态**：1/16（Task 0~15），实施中

🔴 **Task 0 实测已修正三处 spec 偏差**（详见 `evidence/task0-prerequisites.md`，按「历史档案不回填」铁律不改上文正文）：
① **红基线 B5 不成立** —— foundation GC-9 裁决 G1 的 TB 门在**组件层** `G1TabAdjudication.vue`（活代码 + 中文二次确认），
B5 只查了 composable 层 ⇒ 九条**全已接** TB 门（非「已接 8 条」）；Task 14 的 BP-5 / GC-9 两项阻塞**清零**。
② **`header_row=None` 是「字段支持 + 契约投影静默回落」**，不是裁决 G1R-H2 假设的「引擎不支持」 ——
`spec_to_contract_sheet_payload` 三个 `or` 链把 `None` 吞成 `first_data_row-1`，G12 会被**无报错地**投影成 R8 表头
（= G1R-H2 明确否决的方案②）⇒ Task 13 必须先加显式语义，否则不得声明。
③ foundation 实际交付到 **Task 14**（其 tasks.md 勾选状态全 `[ ]` 不可信，判定以产物 + evidence 为准）；
BP-5 修与 G2 canary 产物**均在工作树未提交**，commit 前不得据此宣称收口。

🔴 **并发会话冲突面**（Task 0 新增登记）：`store_item_registry.py` / `adapters/registry.py` /
`phase5_row_table_sheet.py` / `entry_manifest.json` / `_overlay.json` / `_sync_provider_golden_digest.json`
六个共享文件处于并发 `M` 状态 ⇒ 只做追加式最小编辑、每次编辑前重读当前内容、不碰 D/E/F 循环在途文件、
零回归基线一律现算。
**上游**：**`g-cycle-sync-foundation-and-first-canary`（GC-1~GC-10 + BP-5 修 + GC-9 裁决，硬前置）** ·
FC-1~FC-13 · F3 spec 裁决 F3-H4（行级 mask）· F5 spec（布尔/错误值容错）· `g4-g6` spec（G12 无表头行须同源）

`[ ]*` = 依赖外部供给（BP-1~BP-4 / OO 真栈 / foundation GC-9 裁决）。

覆盖 9 条：**G9 → G10 → G8 → G14 → G11 → G13 → G12 → G3 → G1**（由易到难，特例后置）。

## Tasks

### 阶段 0：前置门 + 逐条几何实测 + 红判据

- [x] 0. 前置依赖核查（`git show HEAD:`）
  - `RowTableSheetSpec` · **`header_row=None`（或等价「无表头」语义）是否支持**（G12 依赖，裁决 G1R-H2）·
    `StoreMergePlan.oo_crash_neutralization_fn` · 兄弟 Table ref 位移（G1/G9/G3 多区依赖）
  - foundation 的 **BP-5 修**（G1 sheet 标签）与 **GC-9 三家 TB 裁决**交付状态（G1 收口依赖）
  - `g4-g6` spec 对 G6-5「无表头行」的处置（Req 与 G12 须同源）
  - 证据 `evidence/task0-prerequisites.md`
  - _Requirements: 2.3, 4.1, 4.3_

- [x] 1. slice 复核 + 九条 wp_code 裁决条目
  - 逐条核 `blocked_by`：G1 多 **BP-5+BP-7+BP-9** · G3/G10/G11/G12/G13 多 **BP-7** · G8/G9/G14 仅 BP-1~4
  - `wp_code_adjudication` 九条（foundation Task 1 已建）补 `store_payload_evidence`：
    `G9-detail-rows` 605 B / 2 wp（唯一真实载荷）· 其余七条各 2 B 空数组 · G1/G3 主表零行
  - _Requirements: 1.1_
  - ✅ 证据 `evidence/task1-slice-review-and-adjudication.md`。🔴 实测四项修正：
    ①**`store_payload_evidence` 九条已由 foundation Task 1 补齐**（`measured_at 2026-09-27`）⇒ 本 Task 未改任何 slice/adjudication 字节，转为复核；
    ②**偏差④ BP-9 是范畴错误** —— BP-9 的 `blocks` 字段逐字是「legacy 删除（Task 66/72）与 E 循环延后登记的解除」，**不阻塞 bidirectional**，故不在 G1 的 `capability_target_blocked_by`（实测只有 BP-1~4 + BP-5 + BP-7）⇒ G1 受管不被 BP-9 阻塞，但 🔴 **Task 15 不得删 `useG1DualMode.ts`**（E1 宿主 `GtE1MonetaryFund.vue#L166` 共用，且并发会话在途）；
    ③🔴 **G1/G3 是「键不存在」（`max_payload_bytes=0` / `wp_count_with_payload=0`）而非「空数组 2 B」** ⇒ seed 须先建键，P18 须能区分两态；
    ④slice 自身 `entries_with_positional_row_identity_defect=1` + 行身份表仅 `G6-5-fair-value-data` 一条 `array_index_fallback` ⇒ **BP-7 五条无缺陷的强旁证**（Task 2 仍按值 grep，不得据此跳过）
  - 九条 `contract_id`（= `ADAPTER_ID`，Task 8~14 直接取）：`g1.trading_financial_assets_detail` / `g3.dividend_receivable_detail` /
    `g8.other_equity_detail` / `g9.other_noncurrent_detail` / `g10.trading_liabilities_detail` / `g11.investment_income_detail` /
    `g12.net_hedge_detail` / `g13.fair_value_changes_detail` / `g14.credit_impairment_detail`；九条 sha256 全 64 位见证据 §5

- [x] 2. 🔴 逐条几何实测 + BP-7 五条按值定位 + 三处前端字段核
  - 九条主表逐格复核（表头层级 / 数据区 / footer / 有效列 / 公式列）；**G1 区① T 列 vs 区②③ 无** 逐行确认
  - 🔴 **BP-7 在 G3/G10/G11/G12/G13 五条按值 grep 定位**（裁决 G1R-H7）：有缺陷给行号；
    **无缺陷则如实登记「slice `blocked_by` 与 BP 正文不一致」**，不得伪造
  - 🔴 **G13 父子关系字段**按值实测（无字段 ⇒ 父行靠模板行号硬编码，须显式登记耦合，裁决 G1R-H6）
  - 🔴 **G1/G3 的 timestamp 型 id 是否带随机后缀**按值核（纯 `Date.now()` ⇒ 同毫秒撞 id）
  - G8-2 的 R11/R12/R13 公式集逐行核（R 有无 / T 有无 / `M` 区间差异）
  - 证据 `evidence/task2-geometry-and-field-probes.md`
  - _Requirements: 1.1, 1.3, 2.1, 2.2, 2.3, 2.4, 3.1, 3.5_
  - ✅ **六处推翻/修正 spec**：
    **A** 🔴 **G12 不是「无表头行」** —— 实测 **R7/R8 两级表头 + R9 起数据**（整册上移两行）⇒ 裁决 G1R-H2 前提**不成立**，
    框架层**无需**加 `has_header_row`（Task 0 §1.1 缺口对 G12 不适用），Task 13 大幅简化；🔴 `g4-g6` 的 G6-5 判断**可能同源于同一错误假定**，须同法重测；
    **B** 🔴 **G8 是三段不是两段** —— R13-20 八行与 R13 同型，R12 独立（`M` 区间 + `P` 公式 `=D12+J12+K12` 多一项 + 无 T 三处都不同）⇒ 走裁决 G1R-H3 备选分支 **`r11`/`r12`/`r13plus`**；
    **C** 🔴 **G13 父行只有 R11/R14/R17 三行**（B/C 为公式），**R19/R20 是无子行的顶层手填行**（照 spec 判 formula 会覆盖用户手填）⇒ G13 **也有行级 mask**；
    **D** 🔴 **BP-7 slice 实际标六条（含 G1），按值只 G1/G3 两条真命中**，G10/G11/G12/G13 四条误标（逐字反证：`i+1` 只喂 `seq`，id 生成均带 `Math.random()`）；
    **E** 🔴 **G14 footer `L20 = =D20=K20` 是布尔**不是 SUM ⇒ 布尔列**四处**不是三处（含 G13 footer `K21`）；
    **F** 🔴 **G11 占比列两个分母**：G 引 `$F$31`、**K 引 `$J$31`**
  - ✅ **九处新发现**：**G** G12 两处模板真实缺陷（`B14=SUM(B9,B12,B13:B13)` 漏加 B10/B11 **数值错** · `I14=SUM(I7:I13)` 起点越到表头组行 R7）·
    **H** G12 布尔列只在 R9 一行（也是行级 mask）⇒ **行级 mask 在九条是通例 3/9 非特例** · **I** 🔴 **G13 前端动态增删行 vs 模板固定 10 行业务项 = 结构性错配**（前端无骨架无父子字段，`instrumentName` 自填）⇒ Task 12 三方案待决 ·
    **J** G11 是混合骨架形态（骨架行 `id="g11d-sk-{rowKey}"` 确定性 + `isSkeleton` 不可删 + 增行随机；`rowKey` 是与 G11-1 对齐的业务键非行身份，slice 的 `identity_field="id"` 正确）·
    **K** G11 **R32「本年利润总额」**手填分析行（spec 未提，不受管）· **L** G1/G9 的 R11/R18/R25 与 G3 的 R12/R22 是区标题行（不受管）·
    **M** G3 definedNames 现算 **491**（spec 说约 480，P15 须现算取集合不写死）/ G1 = 0 · **N** 顺带 `useG12FairValueTest.ts#L35 genId()` 无随机后缀（非本 spec 主表，登记不修）·
    **O** G3 主表缺随机后缀但**同册** `useG3OverdueCheck.ts#L134`/`useG3CalcCheck.ts#L265` 都带 ⇒ 同册已有正确范式，主表是唯一偏离方
  - ✅ 有效列修正：G3 实测 **A..AF = 32**（spec 写「33(A-AG)」偏大一列，AG 属 R3/R9 索引区）；其余八条与 spec 一致
  - 🔴 判据设计要点：`.map((r,i)=>` 在九条**全部命中**（`i` 喂 `seq` 是正常业务）⇒ P1 判据**必须看 `i` 的去向**，不得按模式命中判违规；
    P6 的「G1≠G9 列集」不等点精确到**唯一元素 `T`**（只断言集合不等会被无关差异蒙混）

- [x] 3. G1R-P1 / P3 / P5 / P6 红判据（身份三族 / payload 两形态 / 表头层级 / G1≠G9）
  - P1 变异「白名单写死 `('rowId','id')`」⇒ G14 的 `rowKey` 必红
  - P3 变异「统一写死 `remark`」⇒ G1/G3 投影恒空必红
  - P5 变异「G3 按两级表头」「G12 把 R9 当表头」各必红
  - P6 变异「复制 G9 列集给 G1」⇒ T 列漏声明必红
  - _Requirements: 1.1, 1.2, 1.4, 2.1, 2.2, 2.3, 2.4_
  - ✅ `backend/tests/workpaper_sync/test_g_single_region_p1_p3_p5_p6.py`：**18 failed, 36 passed**
    （A 类 36 全绿 = 期望表↔模板/前端实测一致，判据不空转；B 类 18 全红 = 九条 provider + plan 未交付，Task 8~14 逐条转绿，**不用 xfail**）
  - 🔴 文件内 `EXPECTED` 是**本 spec 声明层唯一真源**（Task 8~14 从它取，不得反向迁就 provider）；
    `row_segments = ((段名, 行号元组, 该段公式列), …)` 统一表达「多区同型」（G1/G9 三区 · G3 两区）与「行级 mask 不同型」（G8 三段 · G13 三段 · G12 两段）
  - 🔴 两条判据设计规则（后续 Task 沿用）：①分布类断言**逐条固定不只数个数**（`{"id":{"G1","G3","G11"}}` 而非 `{"id":3}`，后者互换两条仍会通过）
    ②变异自检须断言**变异确实打中目标**（`changed == {"G1","G3"}`，而非「改完还能过吗」）
  - 证据 `evidence/task3-task6-red-baselines.md`

- [x] 4. G1R-P9 / P12 红判据（布尔校验列 / G8 行级 mask）
  - P9 三列（`G12-2!G` / `G13-2!K` / `G14-2!L`）容错三判据；变异「标 editable」必红
  - P12 变异「用 R11 列集套全区」⇒ R12 的 `M` 区间被误声明必红
  - _Requirements: 3.2, 3.5_
  - ✅ `backend/tests/workpaper_sync/test_g_single_region_p9_p12.py`：**4 failed, 17 passed**（A 类 17 绿 · B 类 4 红）
  - 🔴 **偏差第七处：裁决 G1R-H4 的第②条判据不成立** —— 按值实测 `normalize_value(True, boolean)` **成功**（⇒ 正确声明下 `type_normalization_failure` 应为 **0 条**，
    而非「异常类型为它」）；只有声明成数值族（amount/integer/rate）才每行一条。第②条描述的是**声明错误的症状**。
    平台旁证 `excel_materialize.py:1583-1587`（BP-22）：`boolean` 必须落 OOXML 真布尔格 `t="b"`，归 `number_literal` 会让 extract 读回 int ⇒
    **D2 实测 13/13 行全中、首版发布卡在 `roundtrip_verified`** ⇒ 本 spec 四处布尔列声明成数值族会原样重演。
    判据已改写为**双向**：正向零 anomaly + 反向变异断言 **22 行全失败**（`failures == 22` 而非「还能过吗」）
  - 🔴 **新增边界**：`normalize_value('TRUE', boolean)` **抛**（只接受真 bool / `'true'`/`'false'` / `1`/`0`/`'1'`/`'0'`）⇒ 大写串形态会产生 anomaly；
    措辞须精确（小写 `'true'` 被接受）。Task 10/12/13 须确认 materialize 走 `boolean_literal`
  - 🔴 布尔列现算 = **三列 × 五个声明单元**：spec 漏了 **`G13-2!K21`** 与 **`G14-2!L20`** 两个 footer 位点；且 `G12-2!G` **只在 R9 一行**（发现 H：也是行级 mask）
  - 🔴 G8 三段差异实测**四处**（spec 记两处）：`M` 区间 · 🔴 **`P12 = =D12+J12+K12` 多一项**（spec 未记）· `R` 列属 R11/R12 · `T` 列属 R11/R13+；
    三个变异（并集多标 `{T}`/`{R}` · 交集缩面 · R11 列集套全区改宽 `M` 区间）共同证明**只有三段拆分可行**

- [x] 5. 🔴 G1R-P10 / P11 **实测型**红判据（插行后引用位移，不得静态推断）
  - P10：G11-2 插 3 行后 `$F$31` 的实测结果（→`$F$34`？）；**不位移 ⇒ G/K 两列改判 HTML-only**
  - P11：G12-2 的 `I=SUM(I7:I13)`（起点在数据区之上）插行后区间变化实测并登记
  - _Requirements: 3.3, 3.4_
  - ✅ `backend/tests/workpaper_sync/test_g_single_region_p10_p11_shift.py`：**2 failed, 14 passed**（全部断言来自真跑 `shift_sheet_rows`，零静态推断）
  - **P10 实测分三种情况（spec 只预见两种）**：既有行主格 `G10 $F$31→$F$34` ✅ 位移 · `K10 $J$31→$J$34` ✅（spec 漏了第二个分母）·
    合计行 `F31→F34` 且区间 `SUM(F10:F30)→SUM(F10:F33)` ✅ ⇒ **裁决 G1R-H5 走「位移」分支，G/K 两列受管不改判 HTML-only**
  - 🔴 **实测纠正①**：footer 的 `G31`/`K31` 是 **shared formula 成员**（`<f t="shared" si="1"/>` 自闭合无文本），主格在 `G10`
    ⇒ 判断「占比列是否指向真实合计行」**必须看 shared 组主格**，看成员格会拿到 `None` 而误判「无公式」
  - 🔴🔴 **实测纠正②（框架层真实缺陷，spec 未预见）**：**新插入行的 fill-down 公式保留过期绝对分母** ——
    `R31/R32/R33` 位移后是 `IF(F31=0,0,F31/$F$31)`，而合计行已移到 `R34` ⇒ 分母指向「第一个新行自己」⇒ **占比静默算错**（新行值为 0 时 `IF` 返 0 不显错）。
    根因：`_build_inserted_row`(L1877) → `translate_formula_rows`(L1054) 固定 `freeze_absolute_rows=True`（Excel 填充柄的正确语义），
    但造出的新行公式**随后未再经插行位移**那条路（L1035-1036 注释明写绝对行「同样位移」）⇒ **两条语义各自都对，组合顺序错了**；
    **Excel 自己是「先插行再填充」**（`$F$31→$F$34` 后填充保持）⇒ 框架层顺序相反。
    处置：①判据钉住**当前行为** + 精确断言残留行**恰为** {31,32,33}（出现 ≤30 的既有行则是更严重回归）
    ②🔴 **本 spec 不改 `excel_row_shift.py`**（跨循环影响面 + 引擎核心，另立项）
    ③G11 的 G/K **仍受管**（既有行正确；新行缺陷属插行路径且**受管前就存在**，非本 spec 引入的回归）
    ④Task 11 的 G11 声明须显式登记该已知缺陷
    ⑤最小修复方案：`_build_inserted_row` 在 fill-down 之后对绝对行引用再套一次 `plan` 重映射（修好后本判据必红，届时改断言为 `$F$34`）
  - **P11 实测**：框架层扩张规则 = **「起点不动 + 末行 = last_data_row」**。`I14 SUM(I7:I13)→SUM(I7:I16)` 起点 R7 保持
    ⇒ 缺陷②（起点越到表头行）**数值上无害也不放大**（判据取证 `I7` 是字符串非公式，SUM 忽略文本，只是区间声明错）；
    🔴 但 `B14 SUM(B9,B12,B13:B13)→SUM(B9,B12,B13:B16)` ⇒ 末段区间吸收新行但**枚举项 B9/B12 不变** ⇒
    **B10/B11 插行后仍漏加**（判据逐项断言 `"B10" not in got`）⇒ 用户在 R10（模板**预填**的第二行数据）填 B 列金额永远不进合计 = **真实数值错、不自愈**，必须走覆盖层修；
    对照 C 列整区间形态天然覆盖 C10/C11。另：布尔列所在 R9/R10 在 footer 侧插行后**逐字不变** ⇒ P9×P11 交叉面无风险

- [x] 6. G1R-P15 / P16 / P17 / P18 红判据（definedName / hidden 排除 / prefill 不回归 / 零回归现算）
  - P15 现算 G3 的约 480 个 definedName 集合作基线
  - P16 变异「strip 后比较」⇒ `信用减值损失审计程序表G14A -修订前`（名中空格）漏排除必红
  - P17 断言 foundation Task 7 已修的两块 sheet 名；P18 零回归**现算逐项**（不断言集合大小）
  - _Requirements: 4.4, 4.5, 4.6, 4.7_
  - ✅ `backend/tests/workpaper_sync/test_g_single_region_p15_p18.py`：**2 failed, 22 passed**（A 类 22 绿 · B 类 2 红）
  - 🔴 **判据设计第三条规则（本 Task 立）：B 类红判据写正向不写倒置** —— 首版把 P18 写成「九条**全不在** digest」⇒ 现在是绿的，
    要等 Task 15 后变红再由人反转，等于把「该红的时候不红」制度化。改为正向「九条**全在**」后：交付前一直红、交付后自动转绿、**无需改判据**
  - **P15**：G3 definedName 现算 **491**（spec 说约 480）；🔴 **不写死**，只断言 `>300` + 其余八册**全为 0** 的对比关系；
    三族残留并存（`_xlnm.*` / `UFPrn*` / 中文名）；helper `defined_names_of(book)` 可复算供 Task 14/15 做受管前后集合比对；
    变异自检构造「同量异名」证明**按数量比会放过改名**
  - **P16**：四张逐字名 + hidden + 行/合并数实测（G11 34/56 · G12 63/**115 最大** · G13 46/80 · G14 46/78）；
    🔴 G14 的空格在名字**中间**（`title.strip()==title` 但 `replace(" ","")!=title`），变异自检证明**去空格名不在 sheetnames 里**；其余五册零残留
  - 🔴 **P17 两处实测纠正**：①**同一 `wp_code` 有多个 prefill 块**（九条相关共 33 块 = 审定表 9 + 主受管明细表 **5** + 附注披露 18）⇒
    首版对「所有块」断言主表名被 `审定表G13-1` 打红，改为按 `managed_sheet` 定位并断言**恰好一块** + 逐字反证错名不得出现；
    ②🔴 **顺带发现（登记不补）：九条里只有 G1/G8/G11/G13/G14 五条有主受管表 prefill 块，G3/G9/G10/G12 四条没有** ⇒
    P17 的「两块不回归」只覆盖 G13/G14，另四条**根本没有**可回归的块（prefill 覆盖缺口，归模板/取数治理）；
    另加更强判据：九条的**每个** prefill 块 `sheet` 名须真存在于对应模板（GC-8 落地）；
    顺带 `[171]` 的 `'明细表J1-2 '` **尾部带空格**（J 循环，登记不修）
  - 🔴 **P18 现算实证 GC-10**：契约目录 **17** 文件 / digest `providers` **9** 条 / `digest_count` 字段 **105** —— 三数互不相等，
    判据把「两者不同步」本身写成断言；零回归基线落成**逐项快照** `{adapter_id: (contract_sha, sheet_digests, store_sha, instr_sha)}` 而非比数
  - 🔴 **术语纠正**：G9 的「605 B / 2 wp」实测 `wp_count_with_payload=**1**` ⇒ 应读作「**2 行 store 记录，其中 1 行非空**」；
    seed 判据若按「2 wp 有载荷」写会以为已有两份真数据。三态区分固化：键不存在 `(0,0)`=G1/G3 · 空数组 `(2,1)`=六条 · 真实载荷 `(605,1)`=G9

### 阶段 1：BP-7 五条处置 + 行身份修复

- [x] 7. BP-7 五条处置 + G1/G3 timestamp id 修复（按 Task 2 结论）
  - 五条有缺陷的一并修（触类旁通一次修完）；无缺陷的落 slice 不一致登记
  - 🔴 G1/G3 若为纯 `Date.now()` ⇒ 改带随机后缀或 UUID 并**立即回写**；P2 转绿
  - 旧载荷迁移判据
  - _Requirements: 1.3_
  - ✅ 证据 `evidence/task7-bp7-and-row-identity-fix.md`。**只修两条（G1/G3）+ 登记四条误标（G10/G11/G12/G13）**；
    slice 字节**未改**（别人的裁决取证），判据反向钉住四条源码「仍带 `Math.random()` 且未引入 `g1g3RowIdentity`」= 没被顺手改动
  - 产物：**新建** `composables/g1g3RowIdentity.ts`（单点铸造：`resolveStableRowIds` 批量 + `newRowId` + `mintStableRowId` 优先 `crypto.randomUUID()` +
    `isOrdinalRowId`/`isBareTimestampRowId` + `RowIdentityMintStats{minted,deduped}`）· 改 `useG1Detail.ts`/`useG3Detail.ts` ·
    **新建** `__tests__/g1g3RowIdentityBp7.spec.ts`（**17 passed**，六组）· 新建 `tsconfig._g-single-region.json`（`vue-tsc` **0 错**）
  - 🔴 **与 F5 同族修复的关键差异**：F5 把旧形态**一律重铸**（它三处旧形态都含下标）；G1/G3 的 `` `row-${Date.now()}` `` **不含下标**，
    唯一风险是同毫秒撞 id ⇒ 照抄 F5 会让**每次载入身份都变**（比原缺陷更糟）⇒ 修法拆两半：**生成端**加随机后缀 + **载入端**只在同载荷内撞 id 时对后来者重铸
  - 🔴 `resolveStableRowIds` 必须是**批量** API：去重要看到同载荷其它 id，逐行 API（F5 的 `resolveStableRowId`）**发现不了**同毫秒撞出的两个相同 id
  - 🔴 **TDZ 坑**：不能在 `ref(loadRows(...))` 初始化表达式里调 `persistAll()`（它读 `rows.value`，而 `rows` 尚未完成初始化）⇒
    改「先记账（`initialMint`）、`persistAll` 定义后再回写」；另两处载入点走 `loadRowsAndPersistIfMinted()`
  - 🔴 **判据自身修正（前后端同一口径）**：「源码形态防护」首版扫全文 ⇒ 被**修复说明注释里逐字引用的旧写法**打红 ⇒
    改为「旧写法不得出现在**代码行**」+ 剥离注释行（前端 `stripCommentLines` / 后端 `_code_lines_of`），并自检注释里确实还留着逐字记录；
    Task 3 的 `test_map_with_index_alone_is_not_a_violation_signal` 同步改为断言**空集**并已转绿
  - 验证：`vue-tsc` 0 错 · 新判据 17 passed · **零回归**（既有 G1/G3 相关 8 spec + 新判据共 **9 个 test file 全绿**）·
    四文件后端判据 **26 failed（全 B 类）/ 89 passed（A 类全绿）** 与 Task 6 末持平（未引入 A 类回归）
  - 🔴 **2026-09-27 追加修正（Task 8 期间发现，append 不回填上文）**：首版把前缀常量表 `G_ROW_ID_PREFIX = {g1Detail:'g1d', g3Detail:'g3d'}`
    放在共享模块 `g1g3RowIdentity.ts`，消费方只剩 `newRowId(G_ROW_ID_PREFIX.g1Detail)` ⇒ **行身份形态回不了源**：
    `test_task49_g_cycle_migration.py::test_row_identity_key_and_generator_are_source_backed` 要求
    ①`row_identity_generator_source` 指向声明 `{key}: string` 行模型的那个文件、②生成器形态在该文件里**逐字**出现、
    ③非 uuid 族要能提出 `` `<前缀>-${ `` 并在同文件找到该前缀 —— 三条同时要求「前缀内联在消费方」。
    连改三轮 slice 都改不对，根因是**代码形态本身不满足判据**而不是取证写错。
    修法：共享模块只出**不含前缀的后缀** `mintRowIdSuffix()`（随机性仍单点），
    `resolveStableRowIds(rawList, mint, stats)` 第二参改成**铸造器回调**，
    前缀落到消费方本文件的 `genRowId()`（`` `g1d-${mintRowIdSuffix()}` `` / `` `g3d-${…}` ``）；
    删 `newRowId` / `mintStableRowId` / `G_ROW_ID_PREFIX` 三个导出。
    附带收益：消掉了「同一个 `'g1d'` 字面量两处声明」（常量表 vs 铸造点）的漂移面。
    slice 取证改由工具 `backend/scripts/fix/resync_g_slice_source_refs.py --check/--apply` 按值现取（行号一律 grep，不手写）。
    验证：`g1g3RowIdentityBp7.spec.ts` 17 passed（其中两条改为验 `mintRowIdSuffix` 与 `genRowId` 形态）· `test_task49_g_cycle_migration.py` 97 passed

### 阶段 2：九条 lane 逐条接入（由易到难）

- [x]🔴 8. G9（**首条**，裁决 G1R-H1）：`phase5_g9_other_noncurrent.py` + `phase5_g9_02_detail.py`
  - ✅ **阻塞已解除：用户拍板选项 C（改前端对齐模板）**，2026-09-27 落地。取证 `evidence/task8-option-c-g9-rootfix.md`
    （C-0 模板编制思路 → `evidence/task8-template-design-logic.md`；阻塞原文保留在 `evidence/task8-blocker-column-model-mismatch.md` 不回填）
  - 🔴🔴 **原阻塞（已解除，原文保留）**：实测发现**前端列体系 ≠ 模板列体系**，证据 `evidence/task8-blocker-column-model-mismatch.md`。
    G9 模板 28 列的骨架是「**成本 / 累计公允价值变动 / 公允价值**」三联（在期初余额/期初账项调整/期初审定数/期末余额/账项调整/期末审定数 六处重复），
    前端 `useG9Detail.G9DetailRow` 28 字段是**单值列 + 10 列基本信息**（`instrumentType`/`initialInvestDate`/`maturityDate`/`holdingQuantity`/`measurementAttribute`/…）。
    逐列对照：**明确对应仅 3 列**（`classification`↔A · `assetName`↔B · `confirmationStatus`↔AB）· 模板独有 **~11 列**（D/E/G/I/J/K/L/X/Y/Z/AA）· 前端独有 **15 列** ·
    多处一对多（`openingBalance` 对 C/D/E？`closingBalance`/`closingAdjustment`/`closingAdjusted` 三字段对 P..W 八列？）
    ⇒ **`28 == 28` 是巧合**（3 真对上 + 15 前端独有 + 11 模板独有恰好凑成同数）
  - 🔴 九条列数普查（`_g_column_isomorphism_probe.py`）：G9 28/28 · G12 10/10 · G3 33/32 · G8 23/24 · G11 13/16 · G14 13/19 · G13 12/21 · G10 19/35 · **G1 27/56**
    ⇒ 列数一致 ≠ 语义同构（G9 反例）；列数不一致一定不是 1:1。定性须逐列语义对照（语义判断，非机械比对）
  - 🔴 **为什么 G2 canary 能成**：`phase5_g2_02_detail.py` 的 13 个 `field_specs` 与模板 13 列**逐列语义对应**，foundation 只需处置 L/M 两列措辞（FC-5）⇒
    **G2 的前端是按模板列设计的**，而 G9/G1/G10/G13/G14 的前端是**自研列** ⇒ G 循环前端实现质量不一致，slice 与三份 lane spec 均未登记
  - 🔴 **不属既有任何裁决可覆盖的范围**：此前处置的三类差异（FC-5 措辞 / 行级 mask / payload 形态）都在**同一套列体系内**；本次是**列体系本身不同**
  - 处置选项（详见 evidence §5）：**A** 逐条语义对照后只接入真同构的条 · **B** 立「前端列体系↔模板列体系」映射设计 spec（需审计专业复核） ·
    **C** 改前端对齐模板（改可见 UI） · **D** 部分受管（G9 只受管 3 列，双向回写价值极低）
    🔴 **不可选**：硬凑猜测映射 —— 现有判据只校验「声明与模板几何一致」、**不校验**「前端字段语义与模板列语义一致」，
    猜测映射会全绿通过却**把 A 列的值写进 B 列**，比不做更糟
  - 阻塞期产出（保留）：普查脚本 + 九条列数基线 + G9 逐列对照；当时**未产出** provider 两文件（写了就是猜测映射）
  - `ENTRY_ID="xlsx/gt-g9-other-noncurrent-financial"` / `ADAPTER_ID="g9.other_noncurrent_detail"` /
    `WP_CODES={"G9O"}`（幻影码；真码 `G9`）/ `TEMPLATE_SHA256="264322c0ed1b4bf6…2379"`（88,636 B）
  - 三区 R12-16/R19-23/R26-28、小计 R17/R24/R29、合计 R30 `=SUM(C17,C24,C29)`（枚举相加）；`rowId`；
    `formula_columns=("E","H","I","J","L","P","Q","R","U","V","W","Y")`（**无 T**）；payload `remark`
  - 🔴 挂 `oo_crash_neutralization_fn`；**裸 IF 现算 42 格**（全在 `审定表G9-1`，受管表零命中）——
    tasks.md 原写的「84 格」是 `findall` 出现次数不是**格数**，权威口径同 G2 的 21 vs 40（已按生产函数 `neutralize_oo_crash_if_formulas` 正则重算）
  - 真库 605 B ⇒ **不 seed**，但断言载荷非空
  - **C 方案五步落地**（细节见 evidence）：
    - **C-1** `useG9Detail.ts` 完全重写：`G9DetailRow` 28 字段按模板列序 A..AB 逐列对应「三分量 × 四阶段」，
      12 条模板公式由 `enrichG9DetailRow` 重算（🔴 `P=C+M`/`Q=D+N` 走**未审线**；`O` 股息是损益项不进余额）；
      带 `migrateLegacyG9Row` + `G9MigrationStats` + 13 项 `DROPPED_LEGACY_FIELDS`
    - **C-2** `G9TabDetail.vue` 四 tab（期初/变动/期末/补充）+ 嵌套 `el-table-column` 表达模板两级表头；移除 FVOCI 按钮与 L3 标记
    - **C-3** 跨表消费方 6 处改 fallback 链（`closingAuditedFairValue ?? closingAdjusted ?? closingBalance`，存量数据迁移前仍可读）；
      🔴 删 `g9FvCrossHelpers.pushG9FvToDetail`（G9-4→G9-2 回写方向错，G9-2 无层次/估值方法列）
    - **C-4** `useG9Detail.spec.ts` 重写 35 tests（12 公式 / 未审线 / O 列 / 迁移丢弃计数 / 完整性四类 / 集成）
    - **C-5** 后端两文件 + 注册 + 契约（见下）
  - 🔴 **移除 15 列的依据不是「模板没有」而是会计口径**：模板编制说明 A38-A43 五类全 **FVTPL**，CAS22 下不确认 OCI、不计提减值 ⇒
    `ociChange`/`ociCumulative`/`impairmentLoss`/`impairmentProvision` 是**会计错误**不是缺列；
    `fairValueLevel`/`valuationMethod` 的权威源是 G9-4/G9-5 两张表（留在 G9-2 是第二真源）
  - 🔴 **全库首例「一个 store 键 × 三个受管区」**：三区行同在一个 `G9-detail-rows` 数组、区归属走行的 `section` 字段。
    既有多区范式 `phase5_d3_04_analysis` 是「一区一个 store_item_id」（要求前端拆键）—— 这里**不拆**：
    该键有真库 605 B 载荷 + 8 个跨表消费方 + BP-10 登记键，拆键波及面远大于在引擎加一层可选过滤。
    ⇒ 引擎加 `row_section_field`/`row_section_value`（`iter_store_rows` 过滤 **放在重复身份校验之前**，
    否则三段各自会把另两段的行算进 `seen` 而误报重复；`merge_projection_into_store_rows` 给新增行补该字段，两处成对）
  - 🔴 `template_id` **逐区不同**（`G92R1/R2/R3`）而 `sheet_key` **共享**（`g902-managed`）：
    instrumentation 的 definedName 按 template_id 命名（实测抛「多 sheet instrumentation 的 template_id 必须唯一，实得 ['G92','G92','G92']」），
    而契约层同 `excel_name` 两个 sheet_key 会产出重复 sheet 条目 ⇒ 一张 sheet + 三条 tables。先例 `phase5_d3_04_analysis`（D34DEBIT/D34CREDIT）
  - 🔴 `ghost_row_anchor_index=1`（**B 列投资项目**，不是默认的 A 列类别）：A 列是枚举且模板 R12/R19 本就有预填值，
    用它当锚点会让「只填类别的空行」通不过幽灵行防护、「只填投资项目的真行」被当幽灵行剔除。与引擎注释里 D5 的同型例外一致
  - 🔴 provider 的三个 store 门面按「**遍历三段**」组合（不是单段薄转发）：投影合并三段 · 回写**顺序穿线**（上段 merged 喂下段 base_rows，
    三次独立 merge 再拼会互相覆盖）· iter 串联三段。生产调用点（`store_projection_response.py:233` /
    `projection_first_publication.py:1117`）只传一份 payload 无段参数 ⇒ 缺省只投区①会静默丢三分之二的行且 digest 照样算得出来（假绿）
  - 🔴 顺带修零回归门一处同族假绿：`check_sync_provider_golden_digest._synthetic_rows` 造的合成行不带 `section`，
    会被引擎按段过滤掉全部行 ⇒ projection 空而 digest 仍可算。改为**从 spec 现取**段值盖章（不按 provider 名硬编码）
  - 交付物：`phase5_g9_02_detail.py`（三段 sheet 声明）· `phase5_g9_other_noncurrent.py`（entry 层）·
    `scripts/gen/generate_phase5_g9_contract.py` · `data/workpaper_sync_contracts/g9.other_noncurrent_detail.json`
    （canonical `95a6ae0ca66cbf7b…`）· `store_item_registry` 挂 plan · `adapters/registry` 登记交付行 ·
    `check_sync_provider_golden_digest` 加 `("g9", …, True, True)` · 判据 `test_g9_column_isomorphism.py`
  - 验证：`test_g9_column_isomorphism.py` **60 passed** · `test_task49_g_cycle_migration.py` **97 passed**
    （含对新契约的 Property 20/21 字段级核验）· G9 的两条 B 类红判据转绿 · 前端 16 个 G9/G1/G3 相关 spec 全绿
  - 🟡 **未完成（外部依赖，不伪造）**：G9 进 golden digest **基线文件**要等 F1 修掉 `build_store_projection(store_item_id, payload, …)`
    两位置参签名 —— 该门现在跑到 f1 就 `TypeError` 中断（既存缺陷，属 `f1-sync-coverage-and-first-canary` 作业面，并发会话在改）。
    G9 单家经 `_digests_for` 实测可算（contract `95a6ae0ca66c` / projection `60fac0ffbde3` / sheets 1）。
    P18 的两条「九条全在 digest / 全发契约」按设计要到 Task 15 才转绿
  - _Requirements: 1.1, 1.4, 2.4, 4.3, 4.8_

- [x]🔴 8b（C-6）. 余八条模板编制思路调研（**不改生产代码**）
  - 取证 `evidence/task8-c6-remaining-eight-template-logic.md`（13 节，逐条模板列模型 + 编制说明会计口径 + 前端对照 + 处置方案）
  - 三源取数：①`_g_template_design_probe.py <CODE> geom`（合并区 + 逐行公式）②`… notes`（编制说明，判会计口径）
    ③`_g_column_isomorphism_probe.py <CODE>`（前端字段）；④兄弟表归属用 `_g_sibling_sheet_probe.py`
  - 🔴 **错配分四类，不是一个量级**（G9 的经验不能外推）：
    - **III 近同构**（前端多的是 UI 派生/校验）：**G12**(+2) · **G14**(+7) · **G11**(+4) ⇒ 只需「后端不声明派生字段」，前端近零改动
    - **I 去范围**（前端多的字段属兄弟 sheet）：**G10**(+16) · **G13**(+9) · **G1**(+30) ⇒ 删列不重建
    - **II 补分量拆分**（前端单值列 vs 模板三分量）：**G8** ⇒ 真重建（补 8 删 6 合 1 改名 1）
    - **IV 整表错位**（前端整张表做的是兄弟表内容）：**G3** ⇒ 整表重建 32 列
  - 🔴 **最省工的发现：只有 G9 有真实载荷（605 B）**。G1/G3 是**键不存在**（0 载荷）、其余六条 2 B 空数组
    ⇒ `migrateLegacyRow` + `DROPPED_LEGACY_FIELDS` + 跨表 fallback 链**只在 G9 需要**，八条别照抄
  - 🔴 **G8 与 G9 口径相反**：G8 是 FVOCI（受管表注1「指定为 FVOCI 一经作出不得撤销」/ 注3「终止确认时
    OCI 转留存收益」）⇒ **OCI 三列 F/L/R 是准则要求，必须保留**。G9 删 OCI 的依据（五类全 FVTPL）在 G8 不成立；G6 同理
  - 🔴 **G8 模板自身行级不一致的会计判读**（Task 2 已实测三段，本次给出哪一半是对的）：
    `M` 应含 L（R11 对、其余漏）· `P` 应含 K（R12 对、其余漏）· `T` 每行都该有（R12 缺）
    ⇒ 走**覆盖层补齐**不改模板字节（同 G5 漏加小计一族；FC-5「以模板为权威」只适用于两边都对、口径不同）
  - 🔴 **G3 是整表错位**：前端 `DividendDetailRow` 32 字段里与模板能对上的**只有 2 个**（`investeeName`↔A / `remark`↔AG）；
    其余 30 个逐条查到归属 —— `shareholdingRatio`/`declarationDate`/`dividendPlan`/`totalDividend`/`dividendReceivable`
    属 **测算及检查表G3-4**（实测 `C 持股比例① / D 宣告分派股利日 / E 主要股利分配政策 / F 股利分配总额② / G =①*②`）；
    `receivedAmount`/`receiptDate`/`isOverdue`/`overdueDays` 属 **长期未收回款项检查表G3-5**（`F 账龄 / L 期后收款金额`）；
    余 18 个属长期股权投资台账口径，G3 册三张表都没有。零载荷 ⇒ 重建无迁移风险，但**是用户可见 UI 整体替换**，C-10 动手前建议再确认一次
  - 🔴 **G1 与 G9 近同构但三处不同**（照抄 G9 会错）：①`K`/`X` 是「超过一年到期的部分」（流动性划分）而非 G9 的「重分类数」
    ②G1 **无期末应收利息列** —— 注1 逐字「已到期可收取但尚未收到的利息在'应收利息'反映」⇒ 推给 G2 底稿
    ③区① 多一个引 `公允价值测试表G1-6` 的跨表 `T` 列（区②③ 不含）⇒ P6 断言两条 `formula_columns` 不得相等
  - 🔴 **「派生校验」vs「第二真源」判据**：能由本表其它受管列**纯函数算出** ⇒ 派生（保留在前端、后端不声明）；
    算不出且与某受管列表达同一事实 ⇒ 旧列（必须删）。据此 G14 的 `closingComputed`/`rollForward*`/`tbClosing*` 与
    G13 的四个 `*Reconciled`、G11 的 `changeRate*` 判派生；G13 的 `openingFairValue/closingFairValue/fvChange` 与
    G10 的 `openingBalance/closingBalance/initialAmount/currentIncrease` 判旧列
  - 🟡 **lane 顺序重排建议（未擅自改）**：按处置量应为 `G12 → G14 → G11 → G10 → G13 → G1 → G8 → G3`
    （原序按几何复杂度，第二步就撞最重的 G8）。重排能让类 III 三条先把「多区 / 布尔列 / 占比列」三个未验通的点跑稳，
    但会打乱 Task 9~14 的编号与 `_Requirements_` 对应 ⇒ **留待拍板**，本 Task 保持原序不动
  - _Requirements: 1.1, 2.1, 2.2, 3.2, 3.3, 3.5_

- [ ] 9. G10 + G8（单区 + 行级 mask）
  - G10：`G10-detail-rows` / `rowId` / R9/R10 / R11-20 / R21 / `formula_columns=("E","G","K","L","M","O")`
  - G8：🔴 拆 `g802-r11`（单行）+ `g802-r12plus`（R12-20），按裁决 G1R-H3 的「并集取 formula、交集取 editable」
    保守策略；判据证明 R13 的 R 列与 R12 的 T 列不被误标（P12）；
    🔴 若保守策略让可编辑面缩到业务不可接受 ⇒ 改三 spec（`r11`/`r12`/`r13plus`）
  - _Requirements: 2.1, 3.5_

- [ ] 10. G14（`rowKey` 固定行集 + 一处布尔列）
  - `G14-detail-rows` / **`row_identity_key="rowKey"`** / 行集取 `useG14Detail.ts#L61` 的 `G14_LINE_ITEMS` /
    R9/R10 / R11-19 / R20 `SUM(B11:B19)` / `formula_columns=("D","J","K","L")`（**L 是布尔列** `=D11=K11`）
  - P1 / P9（L 列容错三判据）；TB 口径**本期发生额**（科目 6702）
  - _Requirements: 1.2, 3.2, 4.2_

- [ ] 11. G11（单级表头 + 21 行 + 占比列引合计行）
  - `G11-detail-rows` / `id` / **R9 单级** / R10-30（九条最长）/ R31 `SUM(D10:D30)` /
    `formula_columns=("F","G","J","K","L")`
  - 🔴 G/K 占比列按 Task 5 的 P10 实测结论处置（位移 ⇒ 受管；不位移 ⇒ 改判 HTML-only）
  - 🔴 G11-2 是九条唯一主表自身命中裸 IF 的（44 格）⇒ 证据登记
  - _Requirements: 2.2, 3.3, 4.3_

- [ ] 12. G13（父子行 + 布尔列 + 枚举相加 footer）
  - `G13-detail-rows` / `rowId` / R9/R10 / R11-20 / footer R21 `=B11+B14+B17+B19+B20`（**枚举相加**，
    受管区不含该行）/ `formula_columns=("B","C","D","I","J","K")`（**K 是布尔列**）
  - 🔴 父行（R11/R14/R17/R19/R20）的 B/C/D 判 `mode=formula`；无父子字段时显式登记模板行号耦合（P8）
  - _Requirements: 2.5, 3.1, 3.2_

- [ ] 13. G12（无表头行 + 布尔列 + SUM 起点异常）
  - `G12-hedge-detail-rows` / `rowId` / 🔴 **`header_row` 声明为「无」**（裁决 G1R-H2 方案①；
    引擎不支持 ⇒ 登记框架层缺口 + G12 暂不受管，**不得伪造一行表头**）/ R9-13 / R14 /
    `formula_columns=("G","I")`（**G 是布尔列** `=D9=SUM(E9:F9)`）
  - 🔴 与 `g4-g6` spec 对 G6-5「无表头行」的处置**同源**；P11 的 SUM 起点结论落地
  - _Requirements: 2.3, 3.2, 3.4_

- [ ] 14. G3（三级表头 + 480 definedName）+ G1（三区 + 跨表 T 列，**最后一条**）
  - G3：`G3-2-detail-rows` / `id` / 🔴 **三级表头 R9/R10/R11**（G 循环唯一）/ 两区 R13-20 / R23-28 /
    小计 R21/R29 + 合计 R30 `=C29+C21`（枚举相加）/ payload **`conclusion`** /
    `formula_columns=("F","M","N","O","P","T","AA","AB","AC","AD","AE","AF")`；P15 definedName 不变
  - G1：`G1-2-rows` / `id` / R9/R10 / 三区 R12-16/R19-23/R26-28 / 小计 R17/R24/R29 + 合计 R30 `=SUM(C17,C24,C29)` /
    payload **`conclusion`**；🔴 **区① 含 T 列（跨表引 G1-6）而区②③ 不含** ⇒ 行级 mask，P6 断言 G1≠G9
  - 🔴 G1 收口依赖 foundation 的 **BP-5 已修** + **GC-9 TB 裁决已出**
  - _Requirements: 1.4, 2.1, 2.4, 2.5, 4.1_

### 阶段 3：发布链 + 收口

- [ ]* 15. 九条发布链五环 + 宿主接桥 + seed + 收口
  - 九条各走五环 + 六个登记点；九个宿主各引入 `useWorkpaperSyncBridge` + `WorkpaperSyncEditorHost`，
    保留 legacy(4) + notice(3)
  - `backend/scripts/e2e/seed_g_single_region_e2e.py`（幂等、`--dry-run`）+ 九个 fixture，`--workers=1`；
    🔴 **只有 G9 不 seed**，其余八条未 seed 时验收脚本显式失败（P18）
  - 🔴 BP-10 三键收敛（`G1-2-rows` 8 处 / `G10-detail-rows` 6 / `G11-adj-rows` 6 → 各 1 处 + 派生别名，P4）
  - TB 红线 P13（九条 sync 路径 TB 写 0；损益类四条发生额口径）；九册挂中性化 P14；
    四张 `-修订前` 逐字排除 P16；prefill 不回归 P17；零回归 P18；全部变异复跑 + 九册 materialize/verify
  - _Requirements: 1.5, 4.1, 4.2, 4.3, 4.5, 4.6, 4.7, 4.8_

## Task Dependency Graph

```json
{
  "waves": [
    { "wave": 0, "tasks": ["0"], "rationale": "前置门：header_row=None 支持度决定 G12 能否受管；foundation 的 BP-5 修与 GC-9 裁决决定 G1 能否收口" },
    { "wave": 1, "tasks": ["1", "2"], "rationale": "🔴 Task 2 最承重：BP-7 五条按值定位 + G13 父子字段 + G1/G3 timestamp id 三项前端实测，结论决定 Task 7/12 的范围" },
    { "wave": 2, "tasks": ["3", "4", "6"], "rationale": "静态红判据并行（身份/payload/表头/布尔/mask/definedName/排除/零回归）" },
    { "wave": 3, "tasks": ["5"], "rationale": "🔴 实测型红判据（插行后引用位移）单独成波：它要真跑插行，不能与静态判据混批" },
    { "wave": 4, "tasks": ["7"], "rationale": "BP-7 五条 + G1/G3 timestamp id 修复，是受管硬前置" },
    { "wave": 5, "tasks": ["8"], "rationale": "G9 首条（唯一有真实载荷、零特例，可不 seed）" },
    { "wave": 6, "tasks": ["9", "10"], "rationale": "G10+G8 与 G14 互不依赖" },
    { "wave": 7, "tasks": ["11", "12", "13"], "rationale": "G11（依赖 Task 5 的 P10 结论）· G13 · G12（依赖 Task 0 的 header_row 支持度）" },
    { "wave": 8, "tasks": ["14"], "rationale": "G3 + G1 最后：G3 带 480 definedName、G1 带三条 BP + 未接 TB 门 + 行级 mask" },
    { "wave": 9, "tasks": ["15"], "rationale": "九条发布链 + seed + BP-10 收敛 + 全量收口" }
  ],
  "blocking": {
    "0": "header_row=None 不支持 ⇒ G12 暂不受管（Task 13 只出框架层缺口登记）；foundation BP-5 未修 ⇒ G1 的契约 source_ref 不可信（Task 14 阻塞）；foundation GC-9 未裁 ⇒ G1 不得收口",
    "2": "BP-7 五条未定位 ⇒ Task 7 范围不清；G13 父子字段未核 ⇒ Task 12 的父行判定只能硬编码行号（须显式登记）；G1/G3 id 生成未核 ⇒ 撞 id 风险未知",
    "5": "G11 占比列位移行为未实测 ⇒ Task 11 不得声明 G/K 两列（可能指向错行）",
    "7": "BP-7 未修 ⇒ 对应 entry 不得受管、不得发布 contract",
    "14": "G1 依赖 foundation 的 BP-5 修 + GC-9 裁决；两者未完成时 G1 只能停在声明层",
    "15": "published representation / approved bundle 供给（BP-1~BP-3）⇒ 九条 adapter 注册与真栈验收阻塞；seed 脚本未交付 ⇒ 八条空载荷验收是假绿"
  }
}
```

## Notes

- 🔴 **九条合一份的理由不是省事**：五处形态特例（G12 无表头 / G13 父子行 / 三处布尔列 / G11 占比列引合计行 /
  G8 行级 mask）只有放在同一份 spec 里对照，才能判出「是特例还是通例」。拆九份会让每份都以为自己是通例。
- 🔴 **G1 与 G9 几何近同构但列集必不相同**（G1 区①多跨表 T 列）⇒ P6 专门断言两者不等，
  防「同构就复制」（FC-4 禁推演在列集上的体现）。
- 🔴 **G14 的 `rowKey` 是全 G 循环唯一的 `stable_template_row_key`**，且是**最稳**的一族；
  F 的守卫写死 `('rowId','id')` 会把它判违规（GC-6）。
- 🔴 **Task 5 是实测型判据**（插 3 行后看 `$F$31` 变不变），不得用静态推断代替。
  若 G11 的占比列不随插行位移 ⇒ G/K 两列改判 HTML-only（裁决 G1R-H5 已写明该分支）。
- 🔴 **G12 不得伪造一行表头**：R9 就是第一行数据，把 R8 当表头会让 `header_source_ref` 指向非表头格
  且 OO 侧锁错行。引擎不支持「无表头」⇒ 登记框架层缺口 + 暂不受管（裁决 G1R-H2）。
- 🔴 **BP-7 在五条的 `blocked_by` 里但正文只展开 G6-sppi**（`g4-g6` spec 的 G4-main 同款）⇒
  按值定位，无缺陷就登记「slice 内部不一致」，**不得**伪造缺陷也不得静默抹掉。
- 🔴 **只有 G9 可不 seed**（真库 605 B / 2 wp，九条唯一有真实载荷）。
