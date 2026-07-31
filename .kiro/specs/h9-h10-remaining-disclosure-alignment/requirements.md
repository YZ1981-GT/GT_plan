# Requirements Document

## Introduction

H 循环剩余两个有披露表的循环 —— **H9 租赁负债**（上市 §五、47 / 国企 §八、52）与
**H10 资产处置损益**（上市 `三、资产处置收益（损` / 国企 §八、75）—— 的附注结构与同步载荷从未与源模板对齐。

源模板权威 = `backend/wp_templates/H/H9 租赁负债.xlsx` / `H10 资产处置损益.xlsx`。实证欠账：

**H10 是重灾区，含两个 P0（当前皆为潜伏态，尚无项目同步过 → 不需存量清理）**：

1. **🔴 P0 上市章节号定位落空**：`H10_NOTE_SECTION.listed = '三、资产处置收益'`，而模板
   `section_number` 实为 **`'三、资产处置收益（损'`**（10 字符，md 重建截断，与 K11~K13 同款）。
   `sync_from_workpaper` 按 `(project_id, year, note_section)` 精确定位 → 一旦有上市项目点同步，
   会**新建垃圾章节**而非写入正确章节。
2. **🔴 P0 上市两张表同名 `项  目`**（皆为表头首格泄漏）→ `sub_table_data` 以表名为键，同名
   互相覆盖**丢整张表**。载荷现用 `项  目__trial` + `_trial_detail` 双写绕过，但
   `项  目__trial` 在模板里不存在 = **孤儿子表名**，试运行销售明细**永远进不了附注**。
3. **行集缺 3 行**：两版都缺源模板的 `债务重组中因处置非流动资产产生的利得` /
   `使用权资产处置利得` / `油气资产处置利得`（载荷 `H10_NOTE_TEMPLATE_LABEL` 早已备好这三条
   映射，只是模板无落点）；上市另有 `可无限量添加行` 纯占位行须删。
4. **上市试运行表两级表头被压扁**：源模板 R27/R28 是 `本期发生额{收入,成本}` /
   `上期发生额{收入,成本}` 共 5 列，模板压成 3 列且残留 `header_label` 假行；载荷已带
   `current_income`/`current_cost`/`prior_income`/`prior_cost` 四个字段，只是列定义未声明
   → 四列数据推过去无落点。
5. **国企 sheet 名漂移**：`H10_DISCLOSURE_SHEET_NAME.soe = '附注披露信息（国有企业）'`，
   源 xlsx tab 名实为 **`附注披露信息（国企）`** → 附注「打开同步底稿」深链落空。
6. 两版共 3 表 `columns=0` + 无 `guidance`；国企 `text_sections` 两段残留 `**` markdown 残迹。
7. `_note_texts` 缺中文 `title`。

**H9 结构本就与源模板一致**（上市 3 行 `小计`/`减：一年内到期的租赁负债`/`合计`，R8~R10 是空白
可扩明细区故不 seed；国企 5 行含 `……` 可扩行），欠账为：两版 `columns=0` + 无 `guidance`；
`_note_texts` 缺中文 `title`。

两循环的自动同步链路均已正确（`scheduleAutoSync` 在保存处理器里，非自调度），本 spec 只做
防回退断言。

## Requirements

### Requirement 1: H10 章节定位与表名正名（P0）

**User Story:** 作为审计助理，我在上市项目的 H10 披露表点「同步到附注」时，数据要落进
`三、资产处置收益（损` 这一既有章节，且主表与试运行明细表都要能收到数据。

#### Acceptance Criteria

1. WHEN 构造上市载荷 THEN `section_id` SHALL 逐字等于模板 `section_number`（`三、资产处置收益（损`）
2. WHEN 模板上市两张表原名皆为 `项  目` THEN 脚本 SHALL 分别正名为
   `资产处置收益（损失以“-”填列）` 与 `试运行销售损益`
3. WHEN 载荷推送上市子表 THEN 表名 SHALL 命中模板正名后的表名，且 SHALL NOT 使用
   `项  目__trial` / `_trial_detail` 这类绕过键
4. WHEN 表名改名 THEN 旧名 SHALL 进 `_removed_table_keys`（防附注残留孤儿表）
5. WHEN 构造国企载荷 THEN `sheet_name` SHALL 逐字等于源 xlsx tab 名 `附注披露信息（国企）`

### Requirement 2: H10 行集回归源模板

**User Story:** 作为项目经理，附注里的资产处置收益行项目要与源模板一致，不能少行也不能出现占位说明行。

#### Acceptance Criteria

1. WHEN 校验上市主表行集 THEN SHALL 为源模板 R9~R19 的 10 个项目行 + `合计`
2. WHEN 校验国企主表行集 THEN SHALL 为源模板 R9~R18 的 10 个项目行 + `合计`
3. WHEN 模板残留 `可无限量添加行` 或 `row_type=header_label` 假行 THEN 脚本 SHALL 删除
4. WHEN 载荷 `H10_NOTE_TEMPLATE_LABEL` 声明某 rowKey 的标签 THEN 该标签 SHALL 存在于对应变体模板行集

### Requirement 3: H10 上市试运行表两级表头

**User Story:** 作为审计助理，我在底稿录入的试运行销售收入与成本要能分列进附注，而不是被压成净额一列。

#### Acceptance Criteria

1. WHEN 校验上市试运行表 THEN `columns` SHALL 为 5 列：`项目` +
   `本期发生额{收入,成本}` + `上期发生额{收入,成本}`（`group` 承载父表头）
2. WHEN 投影该表 THEN `_column_groups` SHALL 为两个分组各 span 2
3. WHEN 载荷推送该表行 THEN SHALL 提供 `current_income`/`current_cost`/`prior_income`/`prior_cost`
   四个业务键，且键集 SHALL ⊆ `columns[].key`
4. WHEN 合计行 THEN SHALL 逐列求和且标 `is_total`

### Requirement 4: 两版列元数据与编制提示

**User Story:** 作为审计助理，附注 TAB 要能看到源模板口径的编制提示，金额列要按平台格式渲染。

#### Acceptance Criteria

1. WHEN 校验 H9 两版与 H10 三表 THEN 每表 `columns` SHALL 非空、首列 `is_label`、金额列
   `format=amount`，`columns[].label` 序列 SHALL 等于 `headers`
2. WHEN 表头为单行 THEN `columns` SHALL 显式 `flat`（禁前缀推断造凭空父表头）
3. WHEN 表头为两级（H10 上市试运行表）THEN SHALL 用 `group` 且 SHALL NOT 标 `flat`
4. WHEN 补 `guidance` THEN 内容 SHALL 只取源模板红字 / 15 号文条款 / 以「勾稽：」前缀标注的工具提示
5. WHEN 国企 H10 `text_sections` 残留 `**` markdown 标记 THEN 脚本 SHALL 剥离

### Requirement 5: `_note_texts` 中文标题与空过滤

**User Story:** 作为项目经理，附注正文不能出现 `【listed-interest】` 这类英文键。

#### Acceptance Criteria

1. WHEN 载荷产生 `_note_texts` 条目 THEN 每条 SHALL 带非空中文 `title`
2. WHEN 文本为空白 THEN SHALL 不产生该条目；全空时 SHALL 无 `_note_texts` 键
3. WHEN `_note_texts` 存在 THEN SHALL 位于 `sub_table_data` 内（顶层会被 pydantic 静默丢弃）

### Requirement 6: 双侧守卫与 CI

**User Story:** 作为质量控制复核合伙人，上述对齐必须被自动化守卫锁死，不能被 md 重建或并发会话改回去。

#### Acceptance Criteria

1. WHEN 运行后端守卫 THEN SHALL 以 openpyxl 直读源 xlsx 交叉比对行集与表头，并含反向自检
2. WHEN 运行前端契约 THEN SHALL 断言载荷表名/章节号逐字命中模板、列 key ≡ 模板列 key、
   两级表头 `group` 正确、无绕过键、`_removed_table_keys` 覆盖旧名
3. WHEN 运行前端契约 THEN SHALL 断言三个披露 Tab 的同步函数体内无 `scheduleAutoSync`（防自调度回退）
4. WHEN 提交 THEN CI SHALL 有 `note-h9-h10-structure` job 跑 `--check` + 后端守卫
5. WHEN 脚本连续运行两次 THEN 第二次 SHALL 为空操作（幂等）
