# Requirements Document

## Introduction

G7 长期股权投资全链（底稿取数 ↔ 公式预设 ↔ 两张披露表 ↔ 附注模块）的**收口**。

本 spec 承接 2026-08-08 的只读全链调查，并于**建档核实轮**用实算探针把偏差台账逐条重算
（按 `(章节, 表名)` 二元组索引 seed 与运行时列定义，逐表比对 `is_label` / `flat` / `group` /
列 key / label / 列数六个维度）。**核实推翻了初稿的 5 处量化数字与 2 条基于错误前提的需求**，
本文已按实测重写；重算依据见 §附录 A。

调查已确认归档 spec `g7-four-table-extraction-and-disclosure-alignment`(26/26) 的成果
**真实在位**：真实库 8 个有 `1511` 数据的项目直跑，`_load_g7_leaves` + 4 个纯函数全部产出真值，
`parent_check.diff` 全部 `0.0`，6 个分类桶按科目名归类正确，宿主 6 个 Tab 全传
`:html-data`+`:project-id`，`blankRows` 35 处全部走 `dynamicRowCount`（不写死行数），
动态列已按稳定 key `{slot}_{seq}` 实现。

调查同时**已修复并验收**四个缺陷（不在本 spec 范围内，此处仅登记，避免重复立项）：

| 已修 | 内容 | 验收 |
| --- | --- | --- |
| 缺陷 1 | 公式预设 7 条点号子科目公式恒返 0 → `PLACEHOLDER` | 幂等双证 + 变异 5/5 RED |
| 缺陷 2 | `conflicts` 假冲突（`SemanticAccountSlot` 缺槽级 `row_code`） | 真实库 G7 由 7/8 恒亮 → 8/8 全空 + 变异 9/9 RED |
| 缺陷 3 | 国企附注 `八、18` 联营两表列压扁（3 列 vs 源模板 7 列） | 幂等 `--check` 0 欠账 |
| 缺陷 4 | `G7_FOUR_TABLE_EXTRACTION_ENABLED` 默认 False（4 个按钮永久禁用） | render 级真实库 8/8 三条判据全成立 + 变异 6/6 RED |

本 spec 覆盖**剩余**三类工作：

1. **列对齐偏差** —— seed 与运行时的列定义不一致。实测 38 张运行时表里 **37 张有偏差**，
   按**成因**分五类（见下表），合计 **56 个偏差点**。判据真源 = **源 xlsx**
   `backend/wp_templates/G/G7 长期股权投资.xlsx`。
2. **平台能力推广** —— 槽级 `row_code` 已在解析器落地并覆盖 G4/G7，其余 7 条待办
   （H2/H3/H7/D6/I3 + D1/D2）按登记表逐个落地或明确撤回。
3. **G7 待核 3 块** —— 权益法族/子公司族 render 零四表取数是否该补、`_removed_table_keys`
   覆盖面、源模板自身缺陷登记口径。

### 偏差台账（实算，按成因分类）

| 类 | 成因 | listed | soe | 合计 | 风险 |
| --- | --- | --- | --- | --- | --- |
| **A** | 运行时**丢了 `group`** ⇒ 两级表头被压扁（连带 `flat` 自动为真、label 带前缀） | 2 | 4 | **6 张** | 附注列结构错 |
| **B** | 标签列 key 分叉（seed 语义化英文 / 运行时硬编码 `'项目'`） | 7 | 9 | **16** | 无数据风险 |
| **C** | 数据列 key 命名分叉（含 5 处动态列 slot key） | 7 | 14 | **21** | **有数据风险** |
| **D** | label 文字不符（全半角括号 / 折衷合成） | 3 | 8 | **11**（含 A 连带 3） | 交付件用语错 |
| **E** | seed 多一个 `name`（公司名称）数据列 ⇒ 列数差 1 | 0 | 5 | **5** | 列数不一致 |

🔴 **上表归属 = 边②③（seed ↔ 运行时）**，由建档核实轮探针实算。三真源有**两条不同的边**，
计数不可混：边①（源 xlsx ↔ seed）由 `diagnose_g7_column_alignment.py` 实算，其台账与
本表**数字不同且都对**（例：B 类边① 38 处、边②③ 16 处；A 类边① 0、边②③ 6）。
**双台账见 §附录 A**，落地动作以附录 A 为准。

**已实测为绿、只需防回退的四项**（不是待修项）：`is_label` 表态两侧一致 **0 偏差** /
孤儿表 **0** / 运行时 `templateTableKey` 撞名 **0** / 同章节同名表 **0**。

### 术语

- **seed 路径**：`disclosure_notes.table_data._tables` 的模板骨架（新建项目 / 重新生成
  附注时可见），由 `backend/scripts/fix/fix_note_g7_*.py` 幂等脚本写入
  `note_template_{listed,soe}.json`。
- **运行时路径**：底稿披露 Tab 点「同步到附注」时 `sub_table_data` + `_sub_table_columns`
  推送的列定义，由 `buildG7{Listed,Soe}Columns()` 产出。
- **两路径必须同构**：平台铁律「`flat` 必须 seed 与推送两处都加」的一般化 —— 只改一侧会
  让「新建项目看到的列」与「同步后看到的列」不同。

## Requirements

### Requirement 1: 两级表头两路径一致（A 类 6 张）

投影器 `note_sub_table_projector._extract_column_groups` 是三态：`None`=未声明（回退
`_infer_groups_from_headers` **前缀推断**）/ `[]`=显式单级（任一列带 `flat`）/ 非空=显式分组。

🔴 **实测纠正初稿**：运行时侧的 `flat` 由 `buildG7*Columns()` 里
`...(hasGroup ? {} : { flat: true })` **自动加在标签列上**，故运行时**结构上不可能**出现
「既无 `flat` 又无 `group`」或「`flat` 与 `group` 并存」。⇒ 真实缺陷**不是「忘了标 flat」**
（初稿判为 ≈15 处），而是**那 6 张表的列定义丢了 `group`**（把两级表头压扁成带前缀的单级
label），`flat` 为真只是它的**症状**。

🔴 **本类 A 属边②③（seed ↔ 运行时）；边① 的 A 类实算为 0**（seed 的 group 结构与源 xlsx
逐表相符）—— 双台账见 §附录 A。落地时另有两条已裁决口径必须一并遵守：

- **裁决 1（探针缺陷已修，不是待修项）**：源模板的动态列矩阵（`重要联营企业主要财务信息`
  等 **5 张**）用「多个**独立**空白横向合并 + 下行叶子全填」表达「N 个实体槽 × 2 子列」。
  边① 探针首版给所有动态占位同一个名字 `<DYNAMIC>`，被运行段压缩按「相邻同名则合并」
  把 3 个跨 2 压成 1 个跨 6，与 seed 正确声明的 3 段不匹配 ⇒ **假偏差**。已改为按锚列区分
  身份（`<DYNAMIC:c2>` / `<DYNAMIC:c4>`），并配「同名必误合并」反向自检钉死。
  这 5 张表**不在** A 类待修清单内。
- **裁决 2（登记豁免，不重构）**：4 张合营表（listed `重要合营企业主要财务信息` A132:C133 /
  listed `续：重要合营企业本期及上期经营成果` A153:C154 / soe
  `重要合营企业的主要财务信息（划分为持有待售的除外）` A229:D230 / soe
  `续：重要合营企业本期及上期经营成果` A243:D244）源侧确有空白跨 2 合并，但**同表另两组
  合并的叶子行为空** ⇒ 源模板只填 1 槽，与联营表填满 3 槽**不同构**。裁决为**源模板占位
  形态、登记豁免**（`SOURCE_PLACEHOLDER_SINGLE_SLOT`，4 条上限只许缩短 + stale 检测），
  其 `flat` / `group` 偏差**转为豁免不计入偏差数**，报告单列一节如实打印。
  这 4 张表**不在** A 类待修清单内，也不得按「补 group」处理。

**User Story:** 作为审计师，我希望新建项目看到的附注列结构与底稿同步后的列结构完全一致，
这样我不会误以为"同步把表结构改坏了"。

#### Acceptance Criteria

1. WHEN 源 xlsx 判某表为两级表头 THEN 运行时列定义必须用 `group` 表达（同名同跨度），
   而非把父表头压进 label 前缀
2. WHEN 运行时某表带 `group` THEN seed `columns` 必须有**同名同跨度**的 `group`
3. WHEN 源 xlsx 判某表为单级表头 THEN 两路径都必须显式表态（seed 标 `flat`；运行时由
   `hasGroup` 三元表达式自动标）—— 不得任一侧留 `None` 让前缀推断介入
4. 运行时「`flat` 与 `group` 互斥」与「不留 `None`」由 `buildG7*Columns()` 的三元表达式
   结构性保证，守卫对该结构做**防回退**断言（改掉它必打红），不作为待修项
5. A 类 6 张落地后 `group` 与 `flat` 偏差清零：listed `重要非全资子公司主要财务信息—期末数`
   （源 `期末数` 6 列）、listed `续（1）`（源 `期初数` 6 列）、soe `本期发生的同一控制下企业合并情况`
   （源 `本年初至合并日的相关情况` 4 列）、soe `本期发生的非同一控制下企业合并情况`
   （源 `购买日被购买方` 3 列）、soe `结构化主体权益的账面价值和最大损失敞口`
   （源 `发起`/`期末数`/`期初数`）、soe `结构化主体获得收益及转移资产情况`
   （源 `当期从结构化主体获得的收益` 3 列）

### Requirement 2: 标签列 key 统一到平台惯例（B 类 16 处）

标签列**不承载数据** —— 行名真源是 `rows[].label`，`_cell_meta`/`_cell_modes` 按 value 列
索引键、标签列不算数据列。且投影器已有**双向兜底**：
`_project_row` 在 `label_key != "label"` 且行内无该键时从 `label` 复制过来（L67-68）；
反向 `label_val` 为空时回退 `r.get("label")`（L204-205）。

⇒ 改标签列 key **零数据风险**，是**单一裁决**而非 16 次迁移。

🔴 **实测裁决方向**：平台惯例是 `key: 'label'` —— 全平台 266 个标签列定义里 **241 个（91%）**
用 `'label'`，跨 70 个文件；G7 运行时硬编码的 `'项目'` 全平台仅 7 处且全在 G 循环文件里，
属少数派偏离，且**中文字面量当 key** 违反平台禁硬编码取向。

**User Story:** 作为审计师，我希望在附注里填过的数据在底稿同步后不会丢，反之亦然。

#### Acceptance Criteria

1. WHEN 统一标签列 key THEN 两路径都改为平台惯例 `'label'`（不是把运行时改成 seed 的
   `item`/`name`/`investee`/`type`/`seq`，也不是把 seed 改成 `'项目'`）
2. 改动后标签列必须仍带 `is_label: true`（投影器靠它选标签列并跳过它算 group 索引）
3. 本类**不需要**受影响记录量化闸（标签列不承载数据 + 投影器双向兜底）；量化闸只适用于
   Requirement 3 的数据列
4. B 类 16 处（listed 7 / soe 9）落地后标签列 key 偏差清零
5. 守卫必须断言「标签列 key == `'label'`」且**禁中文字面量当 key**，并配反向自检
   （改回 `'项目'` 必打红）

### Requirement 3: 数据列 key 两路径一致（C 类 21 处）

数据列 key 是真正的**数据键**（行对象按它取值），两路径不同 ⇒ seed 骨架的格与推送的值
互相取不到，表现为「同步后整表变空」或「新建项目的已填值同步后丢失」。

**User Story:** 作为审计助理，我希望列改名不会把我已经填好的数据弄丢。

#### Acceptance Criteria

1. WHEN 某表数据列 key 集合两路径不同 THEN 必须裁决以哪一侧为准，并把另一侧改齐
2. 裁决默认取向 = **以运行时侧为准**（动态列的运行时 key 已带稳定后缀 `{slot}_{seq}[_{sub}]`，
   是动态列的必要形态；seed 的 `c1Current`/`company1` 是写死序号，与动态列不兼容）
3. IF 改 seed 侧 key 会让**既有项目**已录数据失联 THEN 必须先量化受影响记录数，为 0 才允许改；
   非 0 时改运行时侧并保留 seed key
4. C 类 21 处含 **5 处动态列**（listed `未丧失控制权的所有者权益份额变动影响` /
   `重要联营企业主要财务信息`（含续）；soe `主要财务信息` / `本期出售的子公司出售日的财务状况` /
   `本期出售的子公司出售日的经营成果` / `母公司在子公司的所有者权益份额发生变化的情况`）
   与 **16 处静态列命名分叉**（如 `region` vs `principalPlace`、`endBookValue` vs `closingCarrying`、
   `priorUnrecognised` vs `priorCumulative`）
5. 落地后数据列 key 偏差清零，且**不得**通过「把 seed 与运行时都改成第三套 key」达成
   （那会同时丢两侧数据）—— 守卫断言落地后的 key 集合与改动前**某一侧**相等

### Requirement 4: 列 label 逐字取源 xlsx（D 类 11 处）

运行时多处用了「折衷化」label（把两张表的不同表头合成一个通用写法）或把父表头压进 label
前缀，与源 xlsx 不符。附注是**交付物**，列头是审计师与被审计单位共同看的东西，不得自拟。

**User Story:** 作为项目合伙人，我希望附注的列头与致同模板逐字一致，这样交付件不会被质疑。

#### Acceptance Criteria

1. WHEN 运行时 label 与源 xlsx 对应单元格不一致 THEN 以**源 xlsx 为准**改运行时侧
2. D 类**四**小类（第 4 小类由裁决 3 归入，见下文与 §附录 A）：
   - **全半角括号**（soe 5 处：`认缴持股比例（%）` vs `(%)`、`享有的表决权（%）`、
     `持股比例（%）`、`向结构化主体出售资产的利得（损失）`）
   - **折衷合成**（listed 合营 FS 表与其经营成果续表共用 `期末数/本期发生额`、
     `期初数/上期发生额`；listed 超额亏损三列名简写；soe `原因说明` vs 源
     `纳入合并范围原因`/`未纳入合并范围原因`；soe `发起规模` vs 源 `规模`；
     soe `享有的表决权(%)` vs 源 `享有的表决权`）
   - **group 压进 label 前缀**（与 A 类同源，随 A 类一并消除：soe `本年初至合并日-收入` →
     `收入` + group、`购买日至期末收入` → `购买日至期末被购买方的收入`）
   - 🔴 **父表头文字不符**（裁决 3，边① 实算 1 处）：listed `重要的共同经营` 的 group 名
     seed 写 `持股比例或享有的份额(%)`，而源 `E235` 是 `持股比例/享有的份额(%)`（**斜杠**
     不是「或」）。段数与 (start, span) 完全一致、**只有名字不符** ⇒ 归 **D 类**不归 A 类，
     由 Task 5/7 落地时改 seed。边① 探针为此单列 `group_label` 这个 kind（映射到 D 类），
     使 A 类只保留「结构性丢 group」。
3. 🔴 `IMPORTANT_ASSOCIATE_SUB` 被 FS 表（`A165:G187`）与 PL 表（`A188:G197`）**共用同一
   slot**，一个 sub 无法同时满足两表的源模板 label。WHEN 修此项 THEN 必须改成
   `associateMatrixColumnsFor(names, sub)` 让两表各传自己的 label，且**列 key 保持
   `current`/`prior` 不变**（key 由 `buildG7SlotColumns` 拼 slot+seq+sub.key，改 label 不动 key）
4. WHEN 源 xlsx 自身用了两种写法（如全半角混用） THEN 以该表所在单元格的原文为准，
   并在守卫里登记该表的原文，禁止「统一成好看的那种」

### Requirement 5: 列数一致（E 类 5 处）

soe 侧 5 张表 seed 比运行时多 **1** 列，实测差异列恒为 `name`（公司名称）。

🔴 **实测纠正初稿**：初稿判为「seq + name 两列、差 2」并要求裁决「序号是否行号派生」。
实测 seed 侧 **`seq`（序号）已是标签列**（`{"key":"seq","label":"序号","is_label":true,"flat":true}`），
运行时标签列是 `'项目'` ⇒ 两侧**各有 1 个** `is_label` 列（`is_label` 偏差为 0），
`seq` 归属属 Requirement 2 的 B 类而非列数问题。⇒ **「序号是否行号派生」这个待裁决问题不存在**；
真正的裁决是「**公司名称该作数据列（seed）还是由 `rows[].label` 承载（运行时）**」。

**User Story:** 作为审计助理，我希望子公司清单类表格的列数确定，不会在同步后少一列。

#### Acceptance Criteria

1. WHEN 某表 seed 与运行时列数不同 THEN 必须逐表读源 xlsx 判定差异列的归属
2. E 类 5 处（全在 soe）：`本期纳入合并报表范围的子公司基本情况`(13↔12)、
   `母公司拥有被投资单位表决权不足半数但能对被投资单位形成控制的原因`(8↔7)、
   `母公司直接或通过其他子公司间接拥有被投资单位半数以上的表决权但未能对其形成控制的原因`(8↔7)、
   `少数股东`(6↔5)、`原子公司的基本情况`(7↔6)
3. WHEN 判定「公司名称」由 `rows[].label` 承载 THEN seed 侧须把该列从 `columns` 移出，
   且 `headers` 同步减一列；运行时 `labelHeader` 必须逐字等于源 xlsx 的行标识列头
4. WHEN 判定「公司名称」是**数据列**（因源 xlsx 里序号才是行标识） THEN 运行时须补该数据列，
   且 `labelHeader` 取源 xlsx 的 `序号`
5. 无论走 4.3 还是 4.4，裁决必须带源 xlsx 单元格依据并入登记表；落地后列数偏差清零

### Requirement 6: 三向锁死守卫（源 xlsx ↔ 模板 seed ↔ 运行时载荷）

现有两个守卫各覆盖一条边，第三条边无守卫 —— 这是 56 个偏差点能长期存在的结构成因：

| 守卫 | `openpyxl` 引用 | 运行时模型引用 | 覆盖的边 |
| --- | --- | --- | --- |
| `backend/tests/test_note_g7_structure.py` | 3 | **0** | ① 源 xlsx ↔ seed |
| `composables/__tests__/_disclosureSubtableContract.helper.ts` | **0** | 有 P1~P6 | ② seed ↔ 运行时 |

且 ② 的 G7 契约**只覆盖主章节**（`五、18` / `八、18`，实测 11 张），跨章 `七、1` 与 soe
13 个 `七、…`（实测 27 张）完全在两守卫的交集之外。

**User Story:** 作为下一个接手 G7 的开发者，我希望列结构一旦被改歪就有测试打红，
而不是靠人肉逐表核对。

#### Acceptance Criteria

1. WHEN 三方任一侧的列 key / label / group / flat / `is_label` / 列数被改动且与另两侧不一致
   THEN 守卫必须打红
2. 守卫必须用 **openpyxl 直读源 xlsx**（含合并区 `merged_cells.ranges` 判两级表头），
   不得以任何派生 JSON 作为源模板真源；派生投影必须配 stale 检测
3. 🔴 三方索引必须用 **`(章节, 表名)` 二元组** —— 实测模板侧跨章节同名表 listed **63 个**
   表名出现 >1 次、soe **40 个**（`长期股权投资` 出现 3 次），按表名全局索引会匹配到
   别的章节的同名表并产出假结论（建档核实轮已复现一次：把会计政策章的空壳版当成主表）
4. 守卫必须配**反向自检**：断言扫描面非空（variant 数 == 2 / 运行时表数 ≥ 38 /
   各表列数 ≥ 2），防正则失效后变成空转
5. 源 xlsx 自身缺陷（见 R10）必须逐条登记豁免且写明依据，登记条目数设上限且只许缩短
6. 守卫必须覆盖**两条路径各自**的产出，不得只查其中一条
7. 守卫必须锁死已绿的四项（`is_label` 表态一致 / 孤儿表 0 / 运行时 `templateTableKey`
   撞名 0 / 同章节同名 0）作**防回退**断言 —— 尤其 `is_label`：投影器跳过它算 group 索引，
   两侧表态不一致会让 group 索引整体偏移一位

### Requirement 7: 槽级 `row_code` 推广（承接平台能力）

`SemanticAccountSlot.row_code` 已在 `semantic_account_resolver` 落地并覆盖 G4/G7。
守卫 `test_semantic_slot_row_code.PENDING_FALSE_CONFLICT_SPECS` 登记了 7 条待办。

**User Story:** 作为审计师，我希望溯源面板的科目冲突告警只在真有冲突时亮，
这样我不会因告警疲劳而忽略真正的错码。

#### Acceptance Criteria

1. WHEN 某 spec 的备抵槽在 `report_config` 里自成一行 THEN 该槽必须声明槽级 `row_code`
2. 登记表里 5 条（H2→`IMP-012`、H3→`IMP-010`、H7→`IMP-013`、D6→`IMP-004`、I3→`IMP-017`）
   落地后必须从 `PENDING_FALSE_CONFLICT_SPECS` 移出并进 `DECLARED_SLOT_ROW_CODES`
3. IF 某 `IMP-*` 行四准则公式全为 NULL THEN 声明后 basis 为空、走三态跳过 —— 这**也是**
   修好（假告警消除），不得因「没有公式可对照」而不声明
4. 🔴 D1 / D2 两条**不得**照抄声明：D1 的 `IMP-001 = TB('1231')` 是**宽口径**（与 `1231-01`
   集合无交集）、D2 的 `IMP-002 = TB('1231.02')` 用**点号**（标准码是横杠 `1231-02`，属
   `report_config` 已知错码）⇒ 声明后仍不匹配。WHEN 处置这两条 THEN 必须先修 `report_config`
   真源或明确撤回并写明依据
5. WHEN 落地任一条 THEN 必须做该循环的真实库 conflicts 前后对照 + 定位结果（`standard_codes`
   / `resolved_from`）逐字不变的零回归证明

### Requirement 8: G7 权益法族 / 子公司族 render 取数补齐判定

G7-13~G7-17（权益法族）与 G7-7~G7-12（子公司族）的 render **零四表取数** —— 实测
`_g7_long_term_equity_method.py` 与 `_g7_long_term_equity_subsidiary.py` 的
`four_table_prefill` / `tb_leaf_categories` / `adjudication_prefill` / `tb_source_codes`
命中数**全为 0**，只有 `client_name` / `audit_year` 各 4 次。

**User Story:** 作为审计师，我希望"四表入库后能刷新取数的底稿都有数据"这句话对 G7 的
每一张底稿都成立，或者明确知道哪几张按设计就是纯手工。

#### Acceptance Criteria

1. WHEN 判定某 sheet 该补取数 THEN 必须给出「四表里确实有可映射数据」的真实库实证
2. WHEN 判定某 sheet **不该**补 THEN 必须在守卫里登记「宁缺勿造」依据（四表无对应维度 /
   属会计判断 / 源模板本就是手工填），并配反向自检防登记变空壳
3. 🔴 不得为凑覆盖率而摊派总额 —— 平台已有 5 个 D 循环 render 明确写「TB 叶子无法干净映射到
   分类行 ⇒ 不臆造分类行未审数」的先例，G7 沿用同一口径
4. G7-2 逐户明细的取数真源已确定为 `tb_aux_balance` 的 `aux_type='客户'`（不在预设里写死
   客户码，见已修缺陷 1），本需求不得引入任何硬编码客户/项目编码

### Requirement 9: 披露载荷表名与 `_removed_table_keys` 覆盖面

`sub_table_data` 以**表名为键**，载荷表名与模板 `tables[].name` 不逐字一致即产生孤儿子表。

🔴 **实测纠正初稿**：初稿称「疑覆盖不全」并列了「2 组撞名」。实算 **孤儿表 0 / 章节缺失 0 /
运行时 `templateTableKey` 撞名 0 / 同章节同名 0** ⇒ 表名一致性**当前已绿**（前序调查修的
6 张已生效），本需求的价值是**防回退**与**覆盖面扩容**，不是修缺陷。

**User Story:** 作为审计师，我希望点了「同步到附注」之后，我在底稿里填的每一张表都能在
附注里看到，不会有表静默丢失。

#### Acceptance Criteria

1. WHEN 运行时载荷推送任一表名 THEN 该表名必须存在于对应变体 `note_template_*.json` 的
   **对应章节**里（按 `(章节, 表名)` 二元组，不是全局按表名）
2. 守卫必须覆盖 listed 15 + soe 23 = **38 张全部运行时表**（现有契约只覆盖主章节 11 张），
   不得只抽查
3. 守卫必须把「孤儿 0 / 撞名 0 / 同章节同名 0」锁成**防回退**断言，并配反向自检
   （改错一个表名必打红 + 表数下限）
4. soe 侧披露组件实推 **11 个章节**（`八、18` 10 张 + 10 个 `七、…` 各 1~3 张）而
   `_removed_table_keys` 只有 1 处 ⇒ 必须逐章节判定「该章节是否可能出现需清理的过时表」，
   并对「有录入区块的条件表」补 `_removed_table_keys`（平台铁律：有录入区块的条件表删空后
   不 removed 会让附注永久残留过时明细）；**无录入区块**的表只跳过、不进 removed
5. 🔴 soe 的 `七、…` 章节号是 **md 截断值（10 字符）**，属既有真源形态，守卫按截断值断言，
   **不得**"补全"

### Requirement 10: 源模板自身缺陷登记

源 xlsx 有多处自身缺陷，实现时须**按意图**而非照抄，且必须逐条登记以免下个会话"顺手修正"
后让三向守卫打红。

**User Story:** 作为下一个接手的开发者，我希望源模板的已知笔误有台账，
不会花时间重新发现同一个问题。

#### Acceptance Criteria

1. 已发现 5 处须登记：
   - soe r260 / r262~r269 联营主表「非流动资产」等行**引用合营列 C/D** 而非 E~H
   - soe r282~r286 合营汇总「上期数」引用**联营行** `I49~I53`
   - listed r187 公允价值引用与上一行 r186 **同一单元格**
   - soe 小节编号**缺 (2)**
   - soe「（四）2 主要财务信息」5 个公司名为空（动态列占位）
2. WHEN 登记任一条 THEN 必须写明「源模板原文 / 判定为缺陷的依据 / 本平台按什么意图实现」
3. 登记表必须配 stale 检测：该缺陷在源 xlsx 里已被修正时守卫打红，提醒移出登记

### Requirement 11: 收口与零回归

**User Story:** 作为项目负责人，我希望这轮改动不会打断已经跑通的 G7 其余链路。

#### Acceptance Criteria

1. WHEN 任一幂等脚本落地 THEN `--dry-run` → `--apply` → `--check` 必须 0 欠账（幂等双证）
2. WHEN 任一守卫落地 THEN 必须做变异检验并达到 100% RED（三态区分 RED / GREEN=守卫缺陷 /
   ANCHOR-MISS=脚本缺陷）
3. 广域回归 `backend/tests/four_table/` + `backend/tests/g7_extraction/` +
   前端 `vitest run g7` 不得新增失败；预存在失败必须逐条钉死归属
4. 🔴 零回归判据**禁用**「把改动文件换成 `git show HEAD:` 版跑同一组」——
   `prefill_formula_mapping.json` / `note_template_*.json` 都含并发会话未提交成果，
   换文件会抹掉它们。改用「前后对照」（幂等脚本天生可重放）
5. WHEN 改动涉及附注模板 JSON THEN 必须先 `git diff --stat` 确认并发改动面，
   落地后核对非本 spec 章节逐字未变
6. 浏览器实测：录 ≥2 行真实数据 → 目标区域真出数 → postgres 查落库 → **数据复原**
   （复原基线取「`parsed_data IS NULL` + `updated_at` 为初始值」而非"实测前那一刻的快照"）

## Glossary

| 术语 | 含义 |
| --- | --- |
| seed 路径 | `note_template_{listed,soe}.json` 的模板骨架 → `disclosure_notes.table_data._tables`；新建项目 / 重新生成附注时可见 |
| 运行时路径 | 底稿披露 Tab 点「同步到附注」时推送的 `sub_table_data` + `_sub_table_columns`，由 `buildG7{Listed,Soe}Columns()` 产出 |
| 三向锁死 | 源 xlsx（openpyxl 直读）↔ 模板 seed ↔ 运行时载荷，三方任一不一致即打红 |
| `is_label` | `ColumnDef.is_label` —— 标签列标记；投影器靠它选标签列（`_pick_label_def`）并**跳过它**算 group 索引（`header_idx` 从 1 起） |
| `flat` | `ColumnDef.flat` —— 显式声明该表单级表头，令 `_extract_column_groups` 返 `[]` 而不走前缀推断 |
| `group` | `ColumnDef.group` —— 两级表头的父表头名，只支持**单级**（含 `/` 会让前端渲染崩） |
| 槽级 `row_code` | `SemanticAccountSlot.row_code` —— 该语义槽自己的报表行，仅用于 `conflicts` 对照基准，不参与定位 |
| 孤儿子表 | 运行时推送的表名在附注模板对应章节里不存在 ⇒ 投影器不渲染 ⇒ 数据静默丢失 |
| `IMP-*` 行 | `report_config` 的减值准备专用报表段；实测仅 `soe_standalone` / `soe_consolidated` 两准则，且后者公式全 NULL、`listed_*` 无该段 |
| 宁缺勿造 | 四表无对应维度时返空并显示「本项目无此科目」，禁摊派总额或臆造分类行 |

## 附录 A：偏差双台账（按边分列）

### A.0 为什么必须拆成两张台账

三真源之间有**三条边**，本 spec 的三向锁死要同时守住：

```
             源 xlsx（唯一裁决者）
              /                 \
        边①  /                   \  边③
            /                     \
     模板 seed  ── 边② ──  运行时载荷
```

- **边①（源 xlsx ↔ seed）** —— 由 `backend/scripts/diagnose/diagnose_g7_column_alignment.py`
  **实算**（openpyxl 直读两张披露 sheet，按 `(variant, 章节, 表名)` 三元组索引，六维比对）。
- **边②③（seed ↔ 运行时 / 源 xlsx ↔ 运行时）** —— 由**建档核实轮探针**实算
  （按 `(章节, 表名)` 二元组比对 seed 与 `buildG7{Listed,Soe}Columns()`）。

🔴 **同一类偏差在两条边上的计数不同，且都对** —— 初稿把两条边的计数混在一张表里，
是本 spec 数字反复对不上的根因。判「某处该改哪一侧」必须先问「这是哪条边的偏差」。

### A.1 边① 台账：源 xlsx ↔ 模板 seed（本脚本实算）

复算命令：`python backend/scripts/diagnose/diagnose_g7_column_alignment.py --dry-run`
（`--check` 有计入偏差时 exit 2）。源模板 sha256
`6bf9e2ebcdf50a1c4a32f8733353dd1de994e7dc483232ad43680043577c3335`。

**计入偏差 43 个**（豁免 8 个另计，见 A.3）：

| variant | A | B | C | D | E | 合计 | 表数 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| listed | 0 | 15 | 0 | 1 | 0 | **16** | 15 |
| soe | 0 | 23 | 0 | 4 | 0 | **27** | 23 |
| **合计** | **0** | **38** | **0** | **5** | **0** | **43** | 38 |

按 kind 展开：

```
listed: flat=0 group=0 group_label=1 key_label_col=15 key_data_col=0 label=0 count=0
        is_label=0 table_missing=0 seed_no_cols=0
soe:    flat=0 group=0 group_label=0 key_label_col=23 key_data_col=0 label=4 count=0
        is_label=0 table_missing=0 seed_no_cols=0
```

逐类说明（**为什么边① 与边②③ 数字不同**）：

| 类 | 边① 实算 | 说明 |
| --- | --- | --- |
| **A** 结构性丢 group | **0** | seed 的 `group` 段数与每段 (start, span) 与源 xlsx 逐表相符。A 类 6 张是**运行时**丢 group，属边②③ |
| **B** 标签列 key | **38（全部 38 张表）** | 边① 判据 = 「seed 标签列 key != 平台惯例 `'label'`」；seed 用 `item`/`name`/`investee`/`type`/`seq`/`项目` 六种写法，一张不漏 |
| **C** 数据列 key | **恒为 0** | 源 xlsx 只有**列头文字**、没有数据键 ⇒ 该维**结构上不可由边① 裁决**，脚本明确不产出该 kind，归边②③ |
| **D** 文字不符 | **5**（label 4 + group_label 1） | 4 处列 label（soe 2 个标签列文字 + 2 个「（金额）」括号）+ 1 处 group 名（裁决 3 的 `重要的共同经营`） |
| **E** 列数 | **0** | seed 数据列数与源 xlsx 逐表相等 ⇒ E 类 5 处是**运行时少 1 列**，属边②③ |

### A.2 边②③ 台账：seed ↔ 运行时（建档核实轮探针实算）

原始实算输出（保留，标明归属 = **边②③**）：

```
listed: total=15  sectionMissing=0 tableMissing=0 seedNoCols=0 dupInSec=0
        isLabel=0 flat=2 group=2 keyLabelCol=7 keyDataCol=7 label=3 count=0 clean=1
soe:    total=23  sectionMissing=0 tableMissing=0 seedNoCols=0 dupInSec=0
        isLabel=0 flat=4 group=4 keyLabelCol=9 keyDataCol=14 label=8 count=5 clean=0
```

按成因分类（= Introduction 的「偏差台账」表，合计 **56 个偏差点 / 37 张表**）：

| 类 | listed | soe | 合计 | 待修侧 |
| --- | --- | --- | --- | --- |
| **A** 运行时丢 group ⇒ 两级表头压扁 | 2 | 4 | **6 张** | 运行时（Task 4） |
| **B** seed key != 运行时 key（标签列） | 7 | 9 | **16** | 两侧同改为 `'label'` |
| **C** 数据列 key 命名分叉（含 5 处动态列） | 7 | 14 | **21** | 默认取运行时侧 |
| **D** label 文字不符（含 A 连带 3） | 3 | 8 | **11** | 运行时 |
| **E** seed 多一个 `name` 数据列 ⇒ 差 1 | 0 | 5 | **5** | 逐表裁决归属 |

### A.3 豁免登记：源模板占位形态（单槽），4 条 / 8 个偏差点

🔴 **这是「已裁决豁免」不是「待修」**。真源 = 脚本里的 `SOURCE_PLACEHOLDER_SINGLE_SLOT`
（4 条，**上限 4 且只许缩短**，另存天花板常量防被改大）。

| variant | 章节 | 表名 | 源模板位置 | 豁免维度 |
| --- | --- | --- | --- | --- |
| listed | 七、1 | 重要合营企业主要财务信息 | A132:C133 | flat, group |
| listed | 七、1 | 续：重要合营企业本期及上期经营成果 | A153:C154 | flat, group |
| soe | 八、18 | 重要合营企业的主要财务信息（划分为持有待售的除外） | A229:D230 | flat, group |
| soe | 八、18 | 续：重要合营企业本期及上期经营成果 | A243:D244 | flat, group |

**判定依据四条**（每条登记项都逐条写明）：

1. 源侧 D/E、F/G（soe 为 E/F、G/H）合并的**叶子行为空** ⇒ 源模板只填了 1 个实体槽；
2. seed 与运行时**两侧独立**都判 `flat` + 2 数据列（两个独立实现结论一致）；
3. 改成动态多实体属**结构性变更**，超出 R1 明列的 6 张 A 类表；
4. 父表头是**实体名**、源 xlsx 留空 ⇒ 无从裁决，改了就是臆造（违「宁缺勿造」）。

**报告口径**：这 8 个 `flat`/`group` 偏差**不计入偏差数**，但报告必须单列「二、豁免登记」
一节如实打印「源模板 merge 结构暗示 3 槽、叶子只填 1 槽 —— 平台按单槽 flat 实现」。
**stale 检测**：`豁免仍单槽` 自检断言源侧 group 运行段数恒为 1；某天源 xlsx 把 D/E、F/G
的叶子填上了即打红，提醒**重新裁决**而非继续豁免。

### A.4 两条边共同的落地动作（B 类两个口径都对，动作不变）

B 类在两条边上的口径不同 —— 边① 是「seed 标签列 key != 平台惯例 `'label'`」= **38 张全部**；
边②③ 是「seed key != 运行时 key」= **16**。两者**不矛盾**（另 22 张是「两侧都不是 `'label'`
但恰好互相相等」），且**动作不变**：

- **Task 5 改全部 38 处 seed** 的标签列 key → `'label'`；
- **Task 4 改运行时那 1 个共享代码点** —— `buildG7{Listed,Soe}Columns()` 里的标签列构造
  （硬编码 `'项目'`，全平台仅 7 处且全在 G 循环），一处改完 38 张表同时受益。

### A.5 反向自检（钉死本轮三条裁决，防被「优化」回去）

`diagnose_g7_column_alignment.py` 的 `run_self_checks()`，**20 项全部通过**；任一不成立
`--check` 即 exit 2（自检失败先于偏差判定报告，因为判据本身失效时偏差数不可信）：

| 自检 | 条数 | 断言 |
| --- | --- | --- |
| 动态列段数 | 5 | 5 张动态表的**源侧段数 == seed 侧段数 == 期望实体槽数**（3/3/5/3/3） |
| 同名必误合并 | 5 | 把动态占位改成**同名**后必被运行段压缩坍缩成 **1 段**（跨 6/6/10/6/6）⇒ 证明「按锚列区分身份」是必要的 |
| 豁免仍单槽 | 4 | 4 张豁免表源侧 group 段数恒为 1（stale 检测） |
| 豁免登记表完整性 | 6 | 上限只许下调（另存天花板）/ 条目数 ≤ 4 / 键真实存在 / 只豁免 `flat`+`group` / 每条理由齐备（源原文 + 依据 ≥4 条 + 平台意图）/ 与动态列登记表互斥 |

### A.6 被推翻的初稿记载（勿再按初稿实现）

| 初稿 | 实测 | 纠正要点 |
| --- | --- | --- |
| flat 表态不一致 ≈15 处 | **6 处**（边②③），且与 group 偏差**完全同表共现** | 成因是丢 `group` 不是忘标 `flat`；运行时 `flat` 由三元表达式自动加 |
| 运行时压扁两级表头 5 处（实际列了 6 项） | **6 张** | 初稿自身数字与清单不一致 |
| 列 key 不一致 8 处 | **标签列 16 + 数据列 21**（边②③） | 两类风险完全不同：标签列零数据风险且是单一裁决 |
| 列数不一致（seq/name 两列，差 2） | **全差 1**，差异列恒为 `name` | `seq` 在 seed 已是标签列 ⇒「序号是否行号派生」的待裁决问题不存在 |
| 实测有 2 组 `templateTableKey` 撞名 | **0 组** | 孤儿 / 章节缺失 / 同章节同名亦全为 0，已绿 |
| 「32 处偏差」 | **56 个偏差点 / 37 张表**（边②③） | 初稿的 32 既非表数也非任一类计数 |
| 守卫覆盖面「疑不全」 | 主章节 11 张已覆盖、跨章 **27 张**未覆盖 | 缺口是精确可数的 |
| 边① 与边②③ 计数可混用 | **不可混** —— A 类 0 vs 6、B 类 38 vs 16、C 类 0 vs 21、E 类 0 vs 5 | 每条偏差先定「哪条边」再定「改哪一侧」 |
| 5 张动态列表 group 不一致 | **0**（探针缺陷产出的假偏差，见裁决 1） | 动态占位必须按锚列区分身份，否则运行段压缩跨合并边界误并 |
| 4 张合营表 flat/group 不一致 | **登记豁免**（源模板占位形态，见裁决 2） | 不是待修项；源 xlsx 填满多槽时自检打红重新裁决 |
