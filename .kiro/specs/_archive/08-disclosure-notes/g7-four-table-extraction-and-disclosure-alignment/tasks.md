# Implementation Plan: G7 四表取数补全 + 两版披露表与附注结构对齐

## Overview

四条主线：
- **A 取数**（Wave 1→2）：后端改走 `four_table` 共享件 + 报表行 `BS-024`/`IMP-009`，
  新增 `adjudication_prefill`，前端 G7-1 与披露表消费。
- **B 公式预设**（Wave 3）：G7-1 补 1512 + WP 联动；G7-2 删项目专属客户码污染。
- **C 附注模板**（Wave 4）：幂等脚本对齐 4 个作用域（上市 五、18 / 七、1，国企 八、18 / 七、*）。
- **D 披露表**（Wave 5→6）：两级表头、行集纠偏、上市改多章节 payload、registry 登记、勾稽面板、UI 铁律。

Wave 7 实测收口。**G1~G6 / G8~G14 不在本 spec 范围**。

## Task Dependency Graph

```json
{
  "waves": [
    {
      "wave": 1,
      "name": "后端四表取数纠偏 + 分类桶单一真源（纯函数 + 单测）",
      "tasks": ["1.1", "1.2", "1.3", "1.4", "1.5", "1.6"],
      "depends_on": []
    },
    {
      "wave": 2,
      "name": "前端消费：科目单一真源 + 审定表预填 + 溯源面板 + 披露表四表带入",
      "tasks": ["2.1", "2.2", "2.3", "2.4", "2.5"],
      "depends_on": [1]
    },
    {
      "wave": 3,
      "name": "公式预设修订与守卫",
      "tasks": ["3.1", "3.2", "3.3"],
      "depends_on": []
    },
    {
      "wave": 4,
      "name": "附注模板结构对齐（幂等脚本 + 后端守卫）",
      "tasks": ["4.1", "4.2", "4.3", "4.4", "4.5"],
      "depends_on": []
    },
    {
      "wave": 5,
      "name": "披露映射：两级表头 / 行集纠偏 / 动态列行 / 多章节 payload",
      "tasks": ["5.1", "5.2", "5.3", "5.4", "5.5", "5.6"],
      "depends_on": [4]
    },
    {
      "wave": 6,
      "name": "registry 登记 / 勾稽面板 / UI 铁律 / 反硬编码守卫 / CI",
      "tasks": ["6.1", "6.2", "6.3", "6.4", "6.5", "6.6"],
      "depends_on": [5]
    },
    {
      "wave": 7,
      "name": "实测收口（真实 DB render + 浏览器 + postgres 复核）",
      "tasks": ["7.1", "7.2", "7.3"],
      "depends_on": [2, 3, 5, 6]
    }
  ]
}
```

## Tasks

- [x] 1.1 `_g7_long_term_equity_main.py`：声明 `G7_ACCOUNT_SPEC`（`row_code='BS-024'`、
  `fallback_gross=('1511',)`、`provision_row_code='IMP-009'`、`fallback_provision=('1512',)`），
  render 改用 `resolve_report_line_accounts` + `select_leaves` + `filter_by_prefixes` +
  `aggregate_leaves`；**删除**自造 `_is_leaf` / `_sum_leaf_by_prefix`（前缀判定缺点号边界）
  与 `_G7_CATEGORY_MAP` / `_classify_leaf`（死代码直接删，不留 DEPRECATED 注释）。
  `tb_values` 现有键名（`opening`/`closing`/`impairment`/`impairment_opening`）保持不变（前端已在读）。
  - Requirements: 1.1, 1.2, 1.3, 1.7
  - Properties: 1, 2, 7

- [x] 1.2 备抵 `1512` 聚合改 `absolute=True`（对聚合结果取 abs，不在行级翻转），
  使 `impairment` / `impairment_opening` 为正数；补注释说明活体为负值存储
  （项目 `2aa00f57` 期末 −4,790,032.97）。
  - Requirements: 1.4
  - Properties: 3

- [x] 1.3 新增纯函数 `classify_g7_leaf(name, code)`：名称优先、编码兜底，判定顺序
  `其他综合收益 → 其他权益变动 → 损益调整 → 减值准备 → 子公司 → 合营 → 联营`
  （`其他综合收益` 必须早于 `其他权益变动`，因 `.04.01` 名称同时含两者）；
  重写 `build_g7_leaf_categories` 消费它，无命中进 `unmapped`。
  - Requirements: 1.5
  - Properties: 4

- [x] 1.4 新增纯函数 `build_g7_adjudication_prefill(leaves, accounts)`：
  原值段输出 `subsidiary` / `jv` / `associate` / `other` 四桶（`other` 承载
  `equity_profit`/`oci`/`other_equity`/`unmapped` —— 它们是**变动性质**不是被投资单位类别，
  落到源模板每块第 4 行空白可扩行）；减值段按 `1512`，无子科目只给合计层；
  无叶子返 `{}`（宁缺勿造）；`closing` 与 `opening+increase−decrease` 不等时置
  `roll_forward_ok: False` 暴露而非掩盖。render 输出 `adjudication_prefill`。
  - Requirements: 2.1, 2.2, 2.3, 2.4
  - Properties: 5, 6

- [x] 1.5 `tb_source_codes` 扩展为含 `report_row` / `provision_report_row` /
  `gross_standard` / `provision_standard` / `gross` / `provision` / `provision_exact` /
  `parent_check`；修正 render 下发 `sheetName` `审定表G7-1` → `长期股权投资审定表G7-1`
  （源 xlsx 逐字），前端分发保留旧名兼容。
  新建 `backend/tests/four_table/test_g7_account_scope.py`：报表行解析 / 点号边界
  （含反向自检「旧 `startswith` 口径确实会误命中 `15110`」）/ abs 归一 / 名称优先分类 /
  预填宁缺勿造 / 变动性质不摊入 / fail-open 四种组合 / `tb_source_codes` 形态 /
  sheetName 与 openpyxl 直读一致。
  - Requirements: 1.6, 1.8, 4.4, 10.1
  - Properties: 1, 2, 3, 4, 5, 6, 7, 14

- [x] 1.6 新建分类桶单一真源 `backend/app/services/four_table/g7_investment_buckets.py`
  （`G7Bucket` dataclass + `G7_INVESTMENT_BUCKETS`，每项含 `bucket`/`label`/`source_ref`/
  `name_keywords`/`code_fallback`/`priority`/`is_movement_nature`；纯数据 + 纯函数零 IO）。
  Task 1.3 的 `classify_g7_leaf` 与 1.4 的 prefill 行标签**改读它**，不各写一份中文标签；
  render 下发 `bucket_defs` 供前端消费（前端**不抄第二份**）。
  render 输出的 `project_context.account_code` / 顶层 `account_code` 改为**报表行解析结果**，
  不再是常量 `_G7_ACCOUNT_PREFIX`。
  守卫：每个 `label` 用 openpyxl 直读 `source_ref` 所指单元格交叉比对；`bucket` 无重复、
  `priority` 全序唯一；`is_movement_nature=True` 的桶金额只出现在 `other`。
  - Requirements: 11.2, 11.3
  - Properties: 4, 6, 16

- [x] 2.1 新建 `composables/g7FourTableSeed.ts`（零 Vue 依赖纯函数）：
  `seedG7AdjudicationFromPrefill(rows, prefill, {overwrite})` /
  `previewSeedG7Adjudication(...)` / `seedG7MovementFromLeafCategories(rows, cats, {overwrite})`；
  手工优先（已有非空值不覆盖，除显式 overwrite），行 `source` 标注 `四表库 tb_balance 1511.xx`。
  - Requirements: 2.5, 3.2
  - Properties: 5, 6

- [x] 2.2 `useG7FormData` 从 render 抽 `adjudication_prefill` / `tb_source_codes`；
  `GtG7LongTermEquityMain.vue` 透传（读 `project_context.tb_source_codes` snake_case，
  兼容 camelCase 回退）；`G7TabAdjudication.vue` 加「从四表库带入未审数」按钮
  （与既有「从明细表带入」并列）+ 顶部挂 `WpFourTableSourcePanel`
  （`provisionLabel='长期股权投资减值准备'`）。
  - Requirements: 2.5, 2.6, 1.6
  - Properties: 5

- [x] 2.3 `g7DisclosureCrossSheet.ts` 增四表库来源：`applyMovementFromFourTable(rows, cats)`
  写主表 期初/期末/权益法损益/OCI/其他权益变动/减值期初·期末 各列；
  两个披露 Tab 工具栏加「从四表库带入」按钮，灰度关闭时 `disabled` + tooltip 明示原因
  （不静默无反应）。
  - Requirements: 3.1, 3.2, 3.3
  - Properties: 5

- [x] 2.4 前端单测 `g7FourTableSeed.spec.ts`（含 PBT：手工优先幂等、overwrite 语义、
  空 prefill 零改动）+ `g7FourTableWiring.spec.ts`（溯源面板挂载 / 按钮存在 /
  灰度关闭态 / 宿主 snake_case 取值）。
  - Requirements: 10.2
  - Properties: 5, 6

- [x] 2.5 新建科目单一真源 `composables/g7AccountScope.ts`（`G7_REPORT_ROW_CODE='BS-024'` /
  `G7_PROVISION_REPORT_ROW_CODE='IMP-009'` / `G7_GROSS_FALLBACK_STANDARD` /
  `G7_PROVISION_FALLBACK_STANDARD` / `g7GrossQueryCodes` / `g7ProvisionQueryCodes` /
  `g7AccountCode` / `g7ImpairmentAccountCode`，对齐已验证的 `k2AccountScope.ts` 范式）；
  **运行态一律取 render 下发的 `tb_source_codes`，常量只作兜底与展示**。
  清零散落字面量：`GtG7LongTermEquityMain.vue` 的 `G7_ACCOUNT_CODE='1511'` /
  `G7_IMPAIRMENT_CODE='1512'`（`writebackTB` + `substantive:adjudicated` 事件过滤在用）、
  `G7TabDisclosureListed.vue` 与 `G7TabDisclosureSOE.vue` 各自的 `ACCOUNT_CODE='1511'`。
  - Requirements: 11.1
  - Properties: 15

- [x] 3.1 `prefill_formula_mapping.json` G7-1 块：补 `TB('1512','期初余额')` /
  `TB('1512','期末余额')` 两条（审定表有减值准备段且 `writebackTB` 会写 1512）；
  补 `WP('G7','明细表G7-2',…)` 联动（审定表可用 `WP`）。
  - Requirements: 4.1
  - Properties: 13

- [x] 3.2 G7-2 明细表块：**删除 5 条硬编码客户编码的 AUX 公式**
  （`AUX('1511.01','客户','007960'…)` 等，属某项目实测污染）；补 `1511.04.01` /
  `1511.04.02` / `1512` 子科目条目；块内保持无 `WP(`（防循环）。
  - Requirements: 4.2, 4.3
  - Properties: 13

- [x] 3.3 守卫 `backend/tests/four_table/test_g7_formula_presets.py`：
  禁项目专属数字字面量（正则 `'\d{6}'` 作 AUX 维度值）、`cell_ref` 在
  `page_key='workpaper:G7'` 内唯一、明细块无 `WP(`、`sheet` 字段与 openpyxl 直读
  `wb.sheetnames` 逐字一致、`validate_formula` 返回空错误列表（注意它返回**错误列表**不是 bool，
  且用的是 prefill 引擎词汇表）。
  - Requirements: 4.5, 10.1
  - Properties: 13, 14

- [x] 4.1 新建 `backend/scripts/fix/fix_note_g7_long_term_equity_structure.py`
  （`--dry-run` / `--check` / `--apply`，复用 `_note_structure_kit`）——
  **上市 `五、18`**：主表 headers 5→13 列（`本期增减变动` 作 8 子列父分组，
  其余列不给 group = 混合分组）、补 `columns` / `guidance`（取源模板 R24 的 15 号文第十九条（十九）
  括注）、删 `row_type: header_label` 假行、`…` 占位行按 R7.2 处理、
  `ensure_text_sections` 补缺段（**不整表替换**）。
  - Requirements: 6.1, 6.5, 6.6, 6.7, 7.2
  - Properties: 9, 10

- [x] 4.2 同脚本 **上市 `七、1 在其他主体中的权益`**：现状 `tables=0` / `text_sections=187`
  → 重建为源模板 R26:R243 的 14 张表（企业集团构成 / 重要非全资子公司 / 主要财务信息
  期末·期初·经营成果 3 张 / 未丧失控制权权益变动影响 / 重要合营联营 / 合营 FS+续 /
  联营 FS+续 / 不重要汇总 / 超额亏损 / 共同经营）+ 文本段（剔除示例与【提示】）。
  逐表补 `columns`（含 `持股比例%` 的 `直接`/`间接` 分组、财务信息的
  `期末数`/`期初数`/`本期发生额`/`上期发生额` 分组）与 `guidance`。
  - Requirements: 6.2, 6.5, 6.6
  - Properties: 8, 9, 10

- [x] 4.3 同脚本 **国企 `八、18`**：分类表 rows 5→6（补源模板 R203「对子公司投资」）；
  两张**同名** `续：` 正名为「续：重要合营企业经营成果」/「续：重要联营企业经营成果」
  （`sub_table_data` 以表名为键，同名互相覆盖会丢整张表）；
  表[8]/[9] 的段落文本泄漏名正名（`C.在财务报表中确认的…比较。` → 「未纳入合并范围结构化主体权益的账面价值与最大损失敞口」；
  `本公司发起多个结构化主体…如下表所示：` → 「作为发起人从结构化主体获得的收益及转移资产」）；
  10 表补 `columns`（明细表两级 group）/ `guidance`；剥离 `<br/>`。
  **改名走 `rule(aliases=)` 不能进 `drop_tables`**（drop 在 apply_plan 前执行会连行删掉）。
  - Requirements: 6.3, 6.5, 6.6, 6.7
  - Properties: 8, 9

- [x] 4.4 同脚本 **国企 `七、*` 15 节**：表名正名（表头首格泄漏的 `序号` / `公司名称` /
  `项  目`）、补 `columns`（`flat` 或 group 按源模板）/ `guidance`。
  - Requirements: 6.4, 6.5, 6.6
  - Properties: 8, 9

- [x] 4.5 后端守卫 `backend/tests/services/test_note_g7_structure.py`：
  openpyxl 直读源 xlsx ↔ 模板 `headers` ↔ 同步 `columns` **三向比对**
  （行集逐字、两级表头分组、`flat` 表态、无 HTML、无 `header_label`、
  两张 `续：` 不复活、上市联营 FS 17 行且不含现金行）+ 反向自检
  （断言压扁前的 5 列 headers 确实会被判红）。
  - Requirements: 10.1, 5.4
  - Properties: 8, 9, 10, 12

- [x] 5.1 `g7ListedDisclosureModel.ts`：给每个 section 增 `noteSectionId` / `noteSectionTitle`
  （`A5:M24` → `五、18`；`A26:M243` → `七、1`）；新增
  `buildG7ListedSyncPayloads(state): G7ListedSyncPayload[]` 按章聚合（对齐国企侧已有范式）；
  `_note_texts` 放 `sub_table_data` 内、带中文 `title`、空文本过滤。
  - Requirements: 8.1, 8.2, 8.3
  - Properties: 8

- [x] 5.2 两版 `columns` 加 `group`：上市主表 + 国企明细表的 `本期增减变动`（8 子列）、
  `持股比例%` 的 `直接`/`间接`、非全资子公司财务信息的期间分组；
  单行表头的表显式标 `flat`。**`key` 一律不动**（载荷行对象用的就是这些键）。
  - Requirements: 5.1, 5.2, 5.3, 6.6
  - Properties: 9, 10

- [x] 5.3 行集纠偏：上市 `important-associate-balance` 删「其中：现金和现金等价物」
  （源 R171:R187 为 17 行，该行只在合营表 R135 存在）；主表补
  `①合营企业` / `②联营企业` 分组标签行；行型判定先去空白（源模板字面 `小  计` / `合  计`）；
  国企联营 FS 末两行沿用附注模板已修正的「对联营企业权益投资的账面价值」
  （源模板 R268 字面为「对合营企业…」属笔误，代码注释与守卫留证）。
  - Requirements: 5.4, 5.5, 5.6
  - Properties: 12

- [x] 5.4 表名对齐 Task 4.1~4.4 正名后的模板 `tables[].name`（消孤儿子表）；
  `G7TabDisclosureListed.vue` 改调 `sync-batch-from-workpaper`（与国企侧一致）。
  - Requirements: 8.1, 8.2
  - Properties: 8

- [x] 5.5 动态行：逐表登记 `dynamic`（依据源模板 `…` / `……` / 空白可扩行）；
  接 `disclosureSyncedTables` 的 `buildRemovedTableKeys`（与 `previouslySyncedTables`
  求交集，未曾推送过的同名表不删）；`…` 作列头丢弃、作纯占位行删除、
  作真实可扩明细行保留。
  - Requirements: 7.1, 7.2, 7.3, 7.4
  - Properties: 11

- [x] 5.6 **固定列数改动态列**：新增 `buildG7SlotColumns(slot, names, sub?)`（稳定 key
  `{slot}_{seq}`，改名只改 `label` 不动 `key` —— 🔴 列 key 不能用 label，源模板四个槽位默认叶子名
  相同会撞键，H7 已踩）；替换写死项：上市 `companyColumns`(6) / `associateMatrixColumns`(3)，
  国企 `multiCompanyCurrentPriorColumns`(5) / `soldFsPositionColumns`(2) /
  `soldFsResultColumns`(5) / `ownershipChangeImpactColumns`(3) / `associateFsMatrixColumns`(3) /
  `associatePlMatrixColumns`(3)；列可增删改名（`ElMessageBox.prompt` 先输名称再建列）。
  **骨架行数不写死**：`blankRows(prefix, 3|5|10, …)` 的 count 改
  `max(seedRowCount(fourTableRows, g72Rows), 1)`，无数据只给 1 行空行
  （预置 3~10 行空占位会被推成占位披露行）。
  - Requirements: 11.6, 11.7
  - Properties: 18

- [x] 6.1 新建 `composables/g7NoteSectionMap.ts` 薄壳（章节号内联字面量、对象体内无注释、
  `G7_DISCLOSURE_SHEET_NAME` 写成单个对象），重跑
  `backend/scripts/gen/gen_note_wp_sync_registry.py --write` 并核 diff
  （只应新增 G7 条目；若带入并发会话改动须逐条确认）。
  - Requirements: 8.4, 8.5
  - Properties: 14

- [x] 6.2 新建勾稽引擎 `g7DisclosureConsistency.ts`（纯函数，6 条规则见 design）
  + 面板复用 `WpDisclosureConsistencyPanel`，两个 Tab 接入。
  - Requirements: 5.9
  - Properties: —

- [x] 6.3 UI 铁律：两个披露 Tab 的 `el-input-number` 全量换 `WpAmountInput`
  （改完 **grep 确认归零**，比例/持股比例列不得套用）；自造
  `fmtAmount`/`toLocaleString('zh-CN')` 改
  `inject(DisplayPrefsKey) ?? useDisplayPrefsStore()` 后 `displayPrefs.fmtAmount(v)`
  （🔴 `fmtAmount` 是 store 成员，不是模块级导出）。
  - Requirements: 5.7, 5.8
  - Properties: —

- [x] 6.4 前端契约 `g7NoteSubtableContract.spec.ts`（复用
  `_disclosureSubtableContract.helper` 的 P1~P6）+ `disclosureColumnsCoverage.spec.ts`
  的 `P1_ROUTE` 登记 `buildG7ListedColumns` / `buildG7SoeColumns`
  （🔴 必须零入参可调，否则 sweep 判「flat/group 未表态」）。
  - Requirements: 10.2
  - Properties: 8, 9

- [x] 6.5 CI：`governance-checks.yml` 新增 job `g7-four-table-extraction`
  （后端 `four_table/test_g7_*`）与 `note-g7-structure`
  （脚本 `--check` + `test_note_g7_structure.py` + 前端契约）。
  - Requirements: 10.4
  - Properties: —

- [x] 6.6 反硬编码守卫 `g7NoHardcode.spec.ts`（读源码，必先 `stripComments()` 且加反向自检）：
  ①`'1511'` / `'1512'` 字面量只许出现在 `g7AccountScope.ts` 与测试 fixture
  ②`G7_NOTE_SECTION` 两个值逐字等于 `note_template_variant_matrix.json` 对应 variant
  ③国企 15 个 `noteSectionId` 逐条存在于 `note_template_soe.json` 的 `section_number` 集合
  （含 md 截断值原样）
  ④两个披露模型内**不得**出现 `公司1`..`公司N` / 固定 `length: 6` 式列构造
  ⑤`blankRows(` 调用的 count 实参不得为字面量数字
  ⑥中文分类标签不在前端重复定义（只读 render 下发的 `bucket_defs`）。
  同步在后端 `test_g7_account_scope.py` 加：`_G7_ACCOUNT_PREFIX` 不得再被 render 用作输出值。
  - Requirements: 11.1, 11.3, 11.4, 11.5, 11.6, 11.7, 11.8
  - Properties: 15, 16, 17, 18

- [x] 7.1 真实 DB 直跑 render（项目 `2aa00f57` 有 1511/1512 活体）：验证
  ①叶子和 == 父科目 `1511` 期初 40,459,060.60 ②`impairment` 为正
  （期初 2,840,032.97 / 期末 4,790,032.97）③`tb_source_codes` 含 `BS-024`/`IMP-009`
  ④`adjudication_prefill` 的 `other` 桶 = 损益调整 + 其他权益变动之和，且不摊入前三类。
  - Requirements: 10.3
  - Properties: 1, 3, 6

- [x] 7.2 浏览器实测（chrome-devtools + postgres 只读）：两版披露 Tab 渲染两级表头、
  `el-input-number` 计数 0、`1234567.5` → `1,234,567.50`、动态行增删、
  推送后复核落库表数 / 列元数据 / `_column_groups` / `_last_sync_sheet` / `_note_texts` title；
  上市侧确认 `五、18` 与 `七、1` **各自落表**（不再是 14 张孤儿）。**实测数据用后完整复原**。
  - Requirements: 10.3, 8.1
  - Properties: 8, 9, 10, 11

- [x] 7.3 向用户确认 `G7_FOUR_TABLE_EXTRACTION_ENABLED` 的处置（本环境 opt-in vs 全局翻默认，
  该开关默认 `False` 使 `tb_leaf_categories` 与「从四表取数」端点运行态全返空），
  裁决结果回写本文件；清理本会话 `tmp_*` 诊断产物。
  - Requirements: 9.1, 9.3
  - Properties: 7

## Notes

### ✅ Wave 1 完成（2026-08-01）+ 真实 DB 实测通过

**产出**
- 共享件 `four_table/report_line_accounts.py` **additive 扩展**：`ReportLineAccountSpec`
  新增可选 `provision_row_code`；`ReportLineAccounts` 新增 `provision_row_code` /
  `provision_formula`。默认 `None` = 引入前逐字等价（D1/K1/K2/F1 零回归，600 测试绿）。
  这是「避免硬编码」的关键 —— 备抵 `1512` 不再是字面量兜底，而是从 `IMP-009` 报表行解析。
- 新建**分类桶单一真源** `four_table/g7_investment_buckets.py`：`G7Bucket` dataclass +
  `G7_INVESTMENT_BUCKETS`（7 桶，每项带 `source_ref` 指向源 xlsx 单元格）+
  `classify_g7_leaf()` + `bucket_defs_payload()`。后端分类器与 prefill 行标签共读它，
  前端经 render 下发的 `bucket_defs` 读，**不抄第二份中文标签**。
- 重写 `_g7_long_term_equity_main.py`：`G7_ACCOUNT_SPEC` + `_load_g7_leaves()`（一次查询）
  + 4 个纯函数 `build_g7_tb_values` / `build_g7_leaf_categories` /
  `build_g7_adjudication_prefill` / `build_g7_source_codes`。
  **删除** `_is_leaf` / `_sum_leaf_by_prefix` / `_G7_CATEGORY_MAP` / `_classify_leaf` /
  `_G7_ACCOUNT_PREFIX` / `_G7_IMPAIRMENT_PREFIX`（死代码直接删）。
  render 的 `account_code` 改为解析结果；新增 `impairment_account_code` /
  `adjudication_prefill` / `bucket_defs` 输出；`sheetName` `审定表G7-1` →
  `长期股权投资审定表G7-1`。
- 测试：新建 `four_table/test_g7_account_scope.py`（29 例）；**重写** 4 个锁旧语义的测试文件
  （`g7/test_g7_tb_values_leaf.py` / `g7_extraction/test_g7_characterization.py` /
  `test_g7_leaf_categories.py` / `test_g7_pbt.py`）—— 它们原来断言的正是要删的硬编码
  （`_G7_ACCOUNT_PREFIX == "1511"`、`_classify_leaf('1511.01') == 'cost'`）。
  **661 passed**（g7 + g7_extraction + four_table + d_cycle_extraction）。

**🔴 实测挖出一个真 bug（已修 + 守卫钉死）**：备抵是**贷方**科目，`credit_amount` 是
**计提（增加）**、`debit_amount` 是转回（减少），与原值侧相反。首版照原值侧口径把
`credit → decrease`，活体 `1512`（期初 2,840,032.97 + 计提 1,950,000.00 = 期末
4,790,032.97）算出 `roll_forward_ok=false`。改为按 `is_provision` 定向后归 true。
守卫 `test_provision_increase_comes_from_credit_side` / `test_gross_increase_comes_from_debit_side`。

**实测结论**（真实 DB 直跑 render 取数路径，三个项目）

| 项目 | 解析 | 叶子 | parent_check | 备抵 | 预填 |
|------|------|------|--------------|------|------|
| `2aa00f57` | `BS-024`+`IMP-009` 均 `report_config`，`provision_exact=True` | 2（`1511.01`/`1512`） | `diff=0.0`（40,459,060.60） | 存 −4,790,032.97 → 输出 **+4,790,032.97** | `subsidiary` + `impairment.total`（增 1,950,000 / roll-forward ✓） |
| `0ec33ac9` | 同上 | 6（子科目全套） | `diff=0.0`（500,000.00） | 0 | `subsidiary` + `associate` + `other`（`.03`+`.04.01`+`.04.02`）；**合营键不出现** |
| `c8621493` | 同上 | 6（金额全空） | `diff=0.0` | 0 | 同上形态，金额全 0 |

- `unmapped` 三个项目均为 `[]` → 名称分类全覆盖；`.04.01 属于其他综合收益` → `oci`，
  `.04.02 不属于其他综合收益` → `other_equity`（否决词生效，这是名称分类最易错的一处）。
- **变动性质不摊入类别**：`other.codes = ['1511.03','1511.04.01','1511.04.02']`，
  `subsidiary.codes = ['1511.01']`，两者无交集。
- ⚠️ 发现 `2aa00f57` 的 `tb_balance` 有多个 dataset 版本，**active dataset** 里只有
  `1511`/`1511.01`/`1512`（无 `1511.03`）。此前用裸 SQL（无 dataset 过滤）看到的
  `1511.01` 期初 53,218,583.61 + `1511.03` −12,759,523.01 属另一版本 —— 测试 fixture
  已注明来源，不当成 active 值。

### ✅ Task 2.5 完成（2026-08-01）—— 科目码单一真源，字面量清零

新建 `composables/g7AccountScope.ts`：`G7_REPORT_ROW_CODE='BS-024'` /
`G7_PROVISION_REPORT_ROW_CODE='IMP-009'` / 两个 `*_FALLBACK_STANDARD` /
`G7_ACCOUNT_NAME`·`G7_PROVISION_ACCOUNT_NAME` /
`g7GrossQueryCodes`·`g7ProvisionQueryCodes`·`g7AccountCode`·`g7ImpairmentAccountCode` /
`isG7GrossCode`·`isG7ProvisionCode`·`g7CodeMatchesPrefix`（**点号 + 横杠双分隔符边界**，
标准码用 `-` 分级、客户原始码用 `.` 分级）/ `g7TrialBalancePrefix()`（按解析结果求最长公共前缀）/
`G7_ADJUSTMENT_ACCOUNT_OPTIONS`。

宿主 `GtG7LongTermEquityMain.vue` 新增 `provide('g7TbSourceCodes', computed(...))`
（读 `project_context.tb_source_codes`，snake_case 优先 + camelCase 回退）。

**清零的散落点（10 个文件）**

| 文件 | 原字面量 | 改为 |
|------|---------|------|
| `GtG7LongTermEquityMain.vue` | `G7_ACCOUNT_CODE`/`G7_IMPAIRMENT_CODE`（`writebackTB` + 事件过滤） | `g7AccountCode(src)` / `isG7GrossCode()` |
| `G7TabAdjudication.vue` | `ACCOUNT_GROSS`/`ACCOUNT_IMPAIRMENT`、`account_prefix:'151'`、`/^1511/`·`/^1512/`、`subjectPrefix`/`subjectCode`/`subjectLabel` | computed + `g7TrialBalancePrefix()` + 谓词 + 模板串 |
| `G7TabDisclosureListed/SOE.vue` | 各自 `ACCOUNT_CODE='1511'` | inject 溯源 → computed |
| `g7AdjustmentModel.ts` | **类型层硬编码** `codePrefix: '1511' \| '1512'`（3 处）+ `startsWith` 无边界 + 重复的 4 条账户清单 | `codePrefix: string` + `tbSource?` + `isG7ProvisionCode()` + `g7CodeMatchesPrefix()` + 复用共享清单 |
| `G7TabAdjustment.vue` | 同款类型联合 + 8 处调用实参 + 重复账户清单 | computed 实参 + 共享清单 |
| `G7VoucherSampleSection.vue` + 4 个调用点 | `accountCode:'1511'` / `account-code="1511"` | `G7_GROSS_FALLBACK_STANDARD` |
| `G7TabImpairmentTest.vue` | 事件载荷 `'1512'` | `G7_PROVISION_FALLBACK_STANDARD` |
| `g7EquityMethodCalcModel.ts` | 建议分录借贷科目码与名称 | 共享常量 |
| `g7InvestmentCostModel.ts` | 分录 `accountCode:'1511'` | 共享常量 |

**有意保留（守卫 allowlist 须写明理由）**：①测试 fixture 里的字面量；
②纯 UI 说明文案（审计目标 / 编制提示 / 勾稽说明里的「TB1511」「1511−1512」等给人看的科目号）。

**⚠️ subsidiary / method 组用常量而非 resolver**：那 4 个文件属**独立底稿**，
其宿主未 provide 四表溯源 → 现用 `G7_GROSS_FALLBACK_STANDARD`（单一真源、零行为变化）。
把溯源 provide 接到 `GtG7LongTermEquitySubsidiary` / `...Method` 宿主是后续任务。

**验证**：`get_diagnostics` 12 文件零诊断；**Vite transform 12 文件全 200**；
vitest `9158 total / 9143 passed / 15 failed / 8 files` —— **G7 相关文件零失败**，
失败全在 H5/H6/L4/N1/F3/F5/H10/H4（未触碰，属既有基线）。

### ✅ Wave 4 完成（2026-08-01）—— 附注模板结构对齐，四作用域全部 `--check` 0 项欠账

**产出四个幂等脚本**（`backend/scripts/fix/`）：

| 脚本 | 作用域 | 变更 |
|------|--------|------|
| `fix_note_g7_long_term_equity_structure.py`（并发会话已完成） | 上市 `五、18` | 主表 5→13 列两级表头、删假行、补 2 段说明 |
| `fix_note_g7_listed_other_entities_structure.py` | 上市 `七、1` | `tables:0→14` / `text_sections:187→20`（剔除示例/【提示】括注） |
| `fix_note_g7_soe_structure.py` | 国企 `八、18` | 分类表补「对子公司投资」行、两张同名`续：`正名、两张段落泄漏名正名、10 表补 columns/guidance |
| `fix_note_g7_soe_scope_change_structure.py` | 国企 `七、*`13节 | 表头首格泄漏名（`序号`/`公司名称`）正名、纠正「出售日」漂移为「处置日」的一处、补 columns/guidance/text_sections |

**关键决策/发现**：
- 上市 `七、1` 「重要联营企业主要财务信息」17 行**不含**「其中：现金和现金等价物」
  （该行只在合营表 R135 出现，18 行），已在脚本与守卫双向锁死（Property 12）。
- 国企 `八、18` R268 字面「对**合营**企业权益投资的账面价值」处于**联营**表内属源模板笔误，
  沿用附注模板已修正口径「对联营企业权益投资的账面价值」，代码注释留证。
- 国企 `七、*` 的「本期出售的子公司出售日的经营成果」表名曾漂移成「**处置**日」，本次纠正。
- 三级表头（`购买日被购买方 > 可辨认净资产公允价值总额 > 金额/确定方法`）按平台惟一落法
  把二级子标题并入叶子列名（`group` 禁 `/`，只支持单级）。
- `grouped_columns` 的 `group` 名不得含 `/`：源模板「持股比例/享有的份额(%)」改用
  「持股比例或享有的份额(%)」等价无斜杠表述（脚本内联注释留证）。

**测试**：新建 `backend/tests/test_note_g7_structure.py`（37 例，三向比对 + Property 12
反向自检 + 反向自检两类"改造前状态必判红"）；`backend/tests/four_table + g7 + g7_extraction`
全量 **313 passed**。回归排查：`git diff` 显示两个 note_template JSON 另有 27/41 个**非 G7**
章节被并发会话同时改动（D2 `八、5` 应收账款等）——已用四脚本各自 `--check` 逐一确认
G7 的四个作用域仍 0 项欠账，未受影响。

**PowerShell 编码踩坑**：`python script.py --check > file.txt` 在 PowerShell 下用
`Select-Object` 会把 UTF-8 输出腌成乱码（终端渲染问题，不影响实际写盘内容）；
`subprocess.run(capture_output=True)` 后手动 `.decode('utf-8', errors='replace')`
才能可靠捕获中文输出（管道 `text=True` 在本机默认 GBK 会直接抛异常）。

### 调查阶段已固化的事实（实施时直接引用，不必重查）

**报表映射**（postgres 只读）
- `BS-024 长期股权投资 = TB('1511','期末余额')`，`listed_standalone` / `listed_consolidated` /
  `soe_standalone` / `soe_consolidated` **四条完全一致**。
- `IMP-009 八、长期股权投资减值准备`：`soe_standalone = TB('1512','期末余额')`；
  `soe_consolidated` 的 `formula` 为 **NULL**；listed 两条**不存在该行**。
- `account_mapping`：9 个项目一律 `1511` / `1511.01` / `1511.02` / `1511.03` / `1511.04` /
  `1511.04.01` / `1511.04.02` → 标准码 `1511`；`1512` → `1512`，全部 `auto_exact`。

**活体科目树与金额**（项目 `2aa00f57 重庆和平药房连锁有限责任公司_2025`）

| 科目 | 名称 | 方向 | 期初 | 借 | 贷 | 期末 |
|------|------|------|------|----|----|------|
| `1511` | 长期股权投资 | debit | 40,459,060.60 | 12,759,523.01 | 12,759,523.01 | 40,459,060.60 |
| `1511.01` | 长期股权投资_对子公司的投资 | debit | 53,218,583.61 | — | 12,759,523.01 | 40,459,060.60 |
| `1511.03` | 长期股权投资_损益调整 | debit | −12,759,523.01 | 12,759,523.01 | — | —（0） |
| `1512` | 长期股权投资减值准备 | credit | −2,840,032.97 | — | 1,950,000.00 | **−4,790,032.97** |

→ 叶子和（`.01` + `.03`）= 40,459,060.60 = 父科目 `1511` 期末/期初 ✓（Property 1 实证）
→ `1512` 负值存储 → 必须 abs 归一（Property 3）

其它候选项目：`c8621493`（24 行 `151%`，金额全空，适合测「无数据」路径）、
`0ec33ac9`（24 行，`1511.01` 期初/期末 500,000.00，含 `.02/.03/.04/.04.01/.04.02` 全套子科目，
适合测名称分类全覆盖）。

**源模板结构**（openpyxl 直读 `backend/wp_templates/G/G7 长期股权投资.xlsx`）
- 22 个 sheet；披露 sheet 名逐字 `附注披露信息（上市公司）`（243 行 × 13 列）与
  `附注披露信息（国企）`（355 行 × 17 列，有效业务列止于 M）。
- 上市主表 `A8:M23`：`A8:A11` 被投资单位 / `B8:B11` 期初余额（账面价值） /
  `C9:C11` 减值准备期初余额 / `D8:K8` 本期增减变动（8 子列 `D9..K9`；
  其中 `F9/F10/F11` = 权益法下·确认的·投资损益 三行拼字，`G9/G10` = 其他综合·收益调整） /
  `L8:L11` 期末余额（账面价值） / `M8:M11` 减值准备期末余额。
  行 `R12 ①合营企业` / `R13 …` / `R15 小  计` / `R16 ②联营企业` / `R17 …` / `R22 小  计` / `R23 合  计`。
- 上市合营 FS `R134:R151` = **18 行**（含 `R135 其中：现金和现金等价物`）；
  上市联营 FS `R171:R187` = **17 行**（**不含**现金行）。现模型两个都用 18 行 → 联营多一行。
- 国企 `R202` 分类表 5 列，行 = 对子公司投资 / 对合营企业投资 / 对联营企业投资 /
  小  计 / 减：长期股权投资减值准备 / 合  计 = **6 行**；
  附注模板 `八、18` table[0] 只有 5 行（**缺「对子公司投资」**）。
- 国企 `R210:R211` 明细表 13 列：被投资单位 / 投资成本 / 期初余额 /
  本期增减变动（8 子列） / 期末余额 / 减值准备期末余额。
- 国企 `R268` 字面为「对**合营**企业权益投资的账面价值」但处于**联营**表内 = 源模板笔误；
  附注模板已修正为「对联营企业…」→ 代码沿用附注模板口径并留证。
- G7-1 审定表源名逐字 `长期股权投资审定表G7-1`（render 现下发 `审定表G7-1`，不一致）；
  三段（一、原值 / 二、减值准备 / 三、净值）× 四块（未审数 / 账项调整 / 重分类调整 / 审定数），
  每块 4 行分类（对子公司 / 对合营 / 对联营 / **第 4 行空白可扩**，
  合并区 `A11:B11`·`A16:B16`·`A21:B21`·`A26:B26` 等），列 = 项目 / 期初数 / 本期增加 / 本期减少 / 期末数 / 索引；
  `R54 试算平衡表数` / `R55 差异数`。

**附注侧现状**
- 上市 `五、18`：`tables=1`、headers **5 列**（源 13 列）、`columns=0`、`guidance=None`、
  1 个 `row_type: header_label` 假行、2 个 `…` 占位行、`text_sections` 仅 2 段裸标题。
- 上市 `七、1 在其他主体中的权益`：`tables=0` / `text_sections=187`（整章零表格）。
  另有章「三、重要会计政策」下的 `三、在子公司中的权益`(6 表)、
  `三、在合营安排或联营企业中的权益`(8 表)、`三、处置子公司`(12 表)、
  `三、非同一控制下企业合并`(4 表) 等 —— 表名全是表头首格泄漏（`项  目` / `子公司名称`），
  `columns` 全 0。**这些属会计政策章，不是 G7 披露落点，本 spec 不动**（留作平台级待办）。
- 国企 `八、18`：`tables=10`，全部 `columns=0` / `guidance=None`；
  table[3] 与 table[5] **都叫 `续：`**（同名 → `sub_table_data` 键冲突丢表）；
  table[8]/[9] 表名是段落文本泄漏；table[9] `rows[0].label` 含 `<br/>`。
- 国企 `七、*`：15 个 level-2 节，表名多为 `序号` / `公司名称` / `项  目`，`columns` 全 0，多数 `rows=0`。
- **G7 完全不在 `note_workpaper_sync_registry.json`**（无 `g7NoteSectionMap.ts`，
  生成器扫不到）→ 附注侧「打开同步底稿」反查不到 G7。

**代码现状**
- 后端 `_g7_long_term_equity_main.py` 357 行：已有叶子聚合 + `tb_source_codes` 雏形，
  但 ①硬编码 `_G7_ACCOUNT_PREFIX='1511'` / `_G7_IMPAIRMENT_PREFIX='1512'`
  ②自造 `_is_leaf`（`other.startswith(code)` 缺点号边界）+ `_sum_leaf_by_prefix`
  （`code.startswith(prefix)` 同样缺边界）③`_G7_CATEGORY_MAP` 硬编码客户子科目码
  ④备抵未 abs ⑤无 `adjudication_prefill`。
- 前端披露侧：国企模型**已是跨章节编排器**（`G7SoeDisclosureSection.noteSectionId` +
  `buildG7SoeSyncPayloads` + `sync-batch-from-workpaper`），设计正确，只缺两级表头与 columns 表态；
  上市模型**把 15 张表全推 `五、18`**（14 张孤儿）。
- `g7DisclosureCrossSheet.ts` 2900+ 行已成熟（G7-1/2/4/5/8/9/10/11/12/14/16/17 全接），
  **唯独没有四表库来源**。
- 两个披露 Tab 的 `scheduleAutoSync` 在 `persist()` 内（非 `syncToDisclosureNotes` 内）
  = **无自调度**，合规。

### 实施注意（平台踩坑，逐条已在 tasks 引用）

- `readFile` 对并发会话在改的文件可能返回陈旧版本 → 判定落盘真相用
  `python -c "open(p,encoding='utf-8').read()"`。
- 新建共享模块前先 grep 消费方；可能已存在的文件用 `str_replace` 而非 `fs_write`。
- 禁用 PowerShell `Set-Content` / `>` 重定向处理 .vue/.md（破坏 UTF-8 + 加 BOM）。
- `buildXColumns` 必须零入参可调（覆盖率 sweep 用空入参调用）。
- `flat` / `group` 必须模板 seed 与同步载荷**两处都加**（H8 只加模板漏了载荷，
  F2 只加载荷漏了模板，双向都踩过）。
- 表名改名走 `rule(aliases=)`，**不能进 `drop_tables`**（drop 在 apply_plan 前执行会连行删掉）。
- 补 `text_sections` 用 `ensure_text_sections`（追加缺段）而非 `run_section(text_sections=...)`（整表替换）。
- 读源码型守卫先 `stripComments()`，并加反向自检防断言空转。
- 改模板 JSON 对既有项目不生效（`guidance` 只经 seed 路径），交付说明须写清。

### 待用户裁决

1. **`G7_FOUR_TABLE_EXTRACTION_ENABLED` 默认 `False`**（Task 7.3）：本环境 opt-in 还是全局翻默认？
   开关关闭时 `tb_leaf_categories` 与「从四表取数」端点运行态全返空，
   即「四表入库后 G7 能刷新取数」这个目标在开关关闭下**不成立**。
2. **上市 `七、1` 重建的深度**（Task 4.2）：该节现状 187 段纯文本零表格，
   完整重建 14 张表工程量约等于一个独立 spec。若希望先保交付，可分两步：
   先建主表所在的 `五、18`（Wave 4.1）+ 国企两章（4.3/4.4），
   上市 `七、1` 单独排期。
3. **章「三、重要会计政策」下重复的在子公司/合营联营权益表**（30 张表，表名全是
   表头首格泄漏、`columns` 全 0）：属 md 重建把「在其他主体中的权益」内容重复落在会计政策章，
   是平台级 data-hygiene 问题，本 spec 不动，是否另立？
