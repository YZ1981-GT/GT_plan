# 公式推送附注跳过减少（formula-push-note-skip-reduction）

## 背景

公式推送引擎"刷新全部公式"（`POST /api/projects/{project_id}/formula-push/run`）在真实项目（重药控股安徽_2025）上运行，**148 项中 109 项（73%）因设计缺陷被跳过**，四表有数据却无法推到对应附注。

经真库排查，跳过分 9 类，其中 4 类属于代码层面可修复的问题：

| 缺陷 | 影响项数 | 严重度 |
|---|---|---|
| B. 旧格式附注 `_source=NULL` 被一刀切拦住 | 38 | P0 |
| A. 附注子表行匹配：binding 产出科目总名，子表只有明细行 | 58 | P0 |
| D. `section_by_template` 硬编码章节号，不同项目排序不同 | 11 | P1 |
| F. `has_obscured_data` 把 `values=[None,None]` 误判为有数据 | 2 | P2 |

其余 39 项属于合理跳过（E1 银行明细未取数 29 / 项目无此科目 6 / 模板缺定义 2 / 章节未生成 1 / 模板无章节 1）。

## 需求

### 1. 旧格式附注可被推送（修复 B 类 38 项）

- **1.1** `locate_table` 不再仅凭 `_source not in WORKPAPER_SOURCES` 就判"模板取数维护"。当 `_source` 为 NULL 且 `sub_table_data` 存在且含目标子表时，正常定位子表。
- **1.2** 当 `_source` 为 NULL 且附注只有旧格式 `{rows, headers}`（无 `sub_table_data`）时，尝试在顶层 `rows` 中按 label 匹配目标行。
- **1.3** 仅当 `_source` 明确为非 workpaper 值（如 `"template"`、`"import"`）时才报"模板取数维护"跳过。
- **1.4** 修复后，`_source=NULL` 的章节首次被推送时，自动将 `_source` 设为 `"workpaper"`（标记已被底稿同步）。

### 2. 附注子表行匹配改进（修复 A 类 58 项）

- **2.1** `note_direct` 族 binding 的 `note_rows` 对单科目底稿（`len(account_prefixes)==1`），`note_label` 改为从附注模板种子中读取实际行标签，而非使用科目总名（`_account_name`）。
- **2.2** `find_row` 增加模糊匹配：当精确匹配失败时，按"标签包含科目名"或"科目名包含标签"做二次匹配。
- **2.3** 对于附注表本身就只有明细行（如"应交税费"表只有增值税/消费税等）、没有与科目总名同名行的场景：推送引擎将值写入合计行（`is_total=True` 或 `row_type="total"`），因为试算表审定数本身就是该科目的汇总数。
- **2.4** 多科目底稿（`len(account_prefixes)>1`）的行为不变：按 `{account_name}_{code}` 匹配明细行 + 合计行。

### 3. 章节号动态定位（修复 D 类 11 项）

- **3.1** `_push_note` 不再直接用 `rule.target.sections.get(template_type)` 取硬编码章节号作为**唯一**定位依据。当硬编码章节号的 `section_title` 与预期不匹配时，**按 `section_title` 反查** `disclosure_notes` 表找到正确的 `note_section`。
- **3.2** 反查逻辑：在同项目同年度的未删除附注中，找 `section_title == table_name`（精确匹配）的唯一章节。找到 0 条或多条时回退到硬编码章节号的原有逻辑。
- **3.3** 反查命中时记录日志 `formula_push: 章节号动态定位 {table_name} → {found_section}（规则声明 {rule_section}）`，便于后续维护。
- **3.4** `section_by_template` 仍保留在规则 JSON 中作为首选/兜底，不删除。

### 4. `has_obscured_data` 误报修复（修复 F 类 2 项）

- **4.1** 遍历行的键值时，跳过 `values` 键（它是列表不是标量）。对 `values` 列表递归检查内部元素是否全为 `None`/`0`/`""`/`"0"`。
- **4.2** 同时跳过以 `_` 开头的内部元数据键（`_cell_meta`、`_cell_modes`、`_legacy_row` 等）。

### 5. 非功能需求

- **5.1** 所有改动必须有对应的单元测试（含真库级别的回归守卫）。
- **5.2** 修复后在真实项目上重跑推送，skipped_count 从 148 降到 ≤45（允许合理跳过的 39 项 + 少量边际情况）。
- **5.3** 不破坏已有的 280+ formula_push 测试。
- **5.4** 改动不影响已正常推送的 223 项 unchanged + 2 项 kept 的行为（幂等不变量）。

## 真库实证基线

> 项目：重药控股安徽有限公司_2025（`0ec33ac9-3de5-4e65-b3bf-f9dccd7b2a49`）
> 运行记录：`8935e359-ffae-4a9a-8b7b-7c17238703f2`（2026-10-10 03:11:03 UTC）

- 四表数据：tb 196 行 / balance 2,436 行 / ledger 702,013 行
- 底稿覆盖：81 个 wp_code 全部参与推送
- 跳过分布：A=58 / B=38 / C=29 / D=11 / I=6 / F=2 / H=2 / G=1 / E=1
- 附注总量：334 条活跃附注，232 条有 table_data
- 旧格式章节（`_source=NULL` + 无 `sub_table_data`）：38 个"五、"章节，含 350 行数据
- 章节号不匹配跨项目验证：重庆和平药房 五、22="长期借款"≠"固定资产"
