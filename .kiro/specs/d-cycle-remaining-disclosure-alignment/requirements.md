# Requirements Document

## Introduction

D 类循环剩余 4 个披露 Tab（D3 预收款项 / D5 应收款项融资 / D6 合同资产 / D7 合同负债）的
披露表结构与附注章节，需按源模板 `backend/wp_templates/D/*.xlsx` 的
「附注披露信息（上市公司）/（国企）」sheet 逐格对齐。D1、D2 已由前序 spec 收口，
本 spec 复用其范式（幂等脚本 + 契约测试 + 两级表头走 `ColumnDef.group` + `flat` 三态表态）。

诊断已完成（`diagnose_disclosure_sheet_vs_template.py` + openpyxl 逐格读源模板），
四个循环**均已接同步链路**（`syncToDisclosureNotes` + `useDisclosureAutoSync`），
问题集中在「模板欠账」与「载荷结构失真」两类：

| 循环 | 章节 | 模板表数 | 源模板小节 | 主要缺陷 |
|------|------|---------|-----------|---------|
| D3 | 五、38 / 八、38 | 3 / 2 | 3 / 2 | `columns=0`、`guidance` 空、无 `flat` 表态 |
| D5 | 五、6 / 八、6 | 4 / 1 | 4 / 1 | 同上 + 上市减值表模板只有 1 列（缺标签列）+ 背书表共前缀「期末」会被推断出凭空父表头 |
| D6 | 五、10 / 八、11 | 9 / 3 | 6 / 3 | 🔴 两级表头全被拍平、上年年末段整体缺失（3 表）、载荷表名与模板不一致（孤儿子表）、模板含 5 张垃圾表名 |
| D7 | 五、39 / 八、39 | 3 / 2 | 3 / 2 | 同 D3 + 国企第 2 表名为占位「合同负债（表2）」 |

## Requirements

### Requirement 1: 模板列元数据与编制提示补齐（四循环共性）

**User Story:** 作为审计助理，我需要附注四个章节的每张表都有列元数据与编制提示，
这样新建项目时 seed 路径就能渲染正确列头，TAB 页签也能看到源模板的口径说明。

#### Acceptance Criteria

1. WHEN 读取 `note_template_listed.json` 五、38 / 五、6 / 五、10 / 五、39 与
   `note_template_soe.json` 八、38 / 八、6 / 八、11 / 八、39 THEN 每张表都有非空 `columns`
2. WHEN 表头为源模板单行表头 THEN 该表 `columns` 中至少一列带 `flat: true`
   （抑制 `_infer_groups_from_headers` 前缀推断）
3. WHEN 表头为源模板两级表头 THEN `columns` 中数据列带 `group`，且 `_column_groups` 非空
4. WHEN 表存在源模板红字提示 / 附注括注 THEN 该表 `guidance` 非空且内容取自源模板
5. WHEN 幂等脚本以 `--check` 运行 THEN exit code 为 0；重复 `--apply` 无新增变更

### Requirement 2: D6 两级表头与上年年末段还原

**User Story:** 作为项目经理，我需要合同资产附注的减值披露包含上年比较期与账面价值列，
这样附注才是可交付的完整披露。

#### Acceptance Criteria

1. WHEN 同步 D6 主表（上市「合同资产」/ 国企「合同资产情况」）THEN 列结构为
   标签列 + 两个分组（上市 `期末余额`/`上年年末余额`、国企 `期末数`/`期初数`），
   每组含 `账面余额`/`减值准备`/`账面价值` 三列，且 `group` 由 `ColumnDef.group` 声明
   （**不得**拍平成「期末账面余额」式组合列名）
2. WHEN 同步上市「（2）合同资产减值准备计提情况」THEN 列结构为源模板 11 列：
   `类别` + `期末余额`{`账面余额`{金额, 比例(%)}, `减值准备`{金额, 预期信用损失率(%)}, `账面价值`}
   + `上年年末余额`{同构}（源 B43:F43 / G43:K43 两级 + B44/D44/F44 三级）
3. WHEN 同步上市「按单项计提减值准备」THEN 期末与上年年末各一张表
   （源 A55-A60 与 A61「续：」A62-A66），后者表名带「（续：上年年末余额）」
4. WHEN 同步上市组合明细 THEN 列结构为 `账龄` + `期末余额`{合同资产, 坏账准备, 预期信用损失率(%)}
   + `上年年末余额`{同构}（源 B69:D69 / E69:G69）
5. WHEN 同步国企「（2）合同资产减值准备」THEN 列结构为
   `项目` + `期初数` + `本期变动金额`{计提, 转回, 转销/核销} + `期末数` + `原因`（源 C19:E19 分组）

### Requirement 3: 载荷表名与模板表名逐字一致

**User Story:** 作为审计助理，我不希望附注里出现空骨架表和重复表。

#### Acceptance Criteria

1. WHEN 构建各循环同步载荷 THEN 每个子表名与对应 `note_template_*.json` 的
   `tables[].name` 逐字一致（含全角/半角与空格）
2. WHEN 模板存在源模板不存在的垃圾表名（D6 上市 `续：` / 空名 / `项  目` /
   `组合计提项目：工程施工` 等示例表）THEN 按源模板重命名或删除，并在脚本中记录
3. WHEN 底稿改版导致旧子表名不再推送 THEN 载荷通过 `_removed_table_keys` 声明，
   避免附注残留孤儿表
4. WHEN 载荷标签列列头 THEN 与该表 `headers[0]` 逐字一致

### Requirement 4: 文本段落与说明域完整性

**User Story:** 作为审计助理，我需要源模板要求的定性披露段落在底稿里有录入位置，
并且能回流到附注正文。

#### Acceptance Criteria

1. WHEN 源模板存在「披露以下信息：」类定性段落（D7 上市 A31-A37 三段、D7 国企 A14-A19、
   D6 两版说明段、D5 上市 A15 说明与终止确认参考披露）THEN 底稿对应 Tab 有文本域
   且带 AI 辅助与复核入口
2. WHEN 文本域键集与 `_note_texts` 条目比对 THEN 无缺无余，且每条带中文 `title`
3. WHEN 模板 `text_sections` 含裸表名段落 THEN 加 `#### ` 前缀
   （后端 `_is_table_title_paragraph` 判定，否则会被当披露正文渲染）

### Requirement 5: 守卫与回归

**User Story:** 作为质量控制复核合伙人，我需要这些结构约束有自动化守卫，防止并发会话回退。

#### Acceptance Criteria

1. WHEN 运行 `python backend/scripts/fix/fix_note_d_cycle_rest_structure.py --check` THEN exit 0
2. WHEN 运行后端结构契约测试 THEN 覆盖四循环 8 个章节的表数 / 列数 / `group` / `flat` /
   `guidance` / 无垃圾表名 / 无 `header_label` 假数据行
3. WHEN 运行前端契约测试 THEN 每循环接入
   `_disclosureSubtableContract.helper.ts` 的 `runDisclosureSubtableContract`
4. WHEN 新增 `build*Columns` THEN 已登记 `disclosureColumnsCoverage.spec.ts` 的 `P1_ROUTE`
5. WHEN CI 运行 THEN 新增 job `note-d-cycle-rest-structure` 执行 `--check` + 契约测试
6. WHEN 改动完成 THEN 前端 D3/D5/D6/D7 相关测试与后端结构测试全绿，
   改动的 `.vue` / `.ts` 经 Vite transform 返回 200

### Requirement 6: 浏览器实测

**User Story:** 作为业务合伙人，我要确认改动在真实项目里跑通，而不只是测试绿。

#### Acceptance Criteria

1. WHEN 在真实项目打开各循环披露 Tab THEN 组件正确挂载（含变体分发），控制台无报错
2. WHEN 录入数据并触发同步 THEN `disclosure_notes.table_data.sub_table_data` 落库表数
   与列元数据（`_sub_table_columns` 的 `group`）与设计一致
3. WHEN 实测完成 THEN 造出的测试数据全部复原

## Glossary

| 术语 | 含义 |
|------|------|
| 披露 Tab | 底稿内「附注披露信息（上市公司）/（国企）」sheet 对应的 Vue 组件 |
| 载荷 | 前端 `buildDXSyncPayload` 产出的 `sync-from-workpaper` 请求体 |
| 两级表头 | 附注表的父子表头，唯一机制 = `ColumnDef.group` → 后端 `_column_groups` |
| `flat` 三态 | `_extract_column_groups` 的语义：`None`=未声明（回退前缀推断）/ `[]`=显式单级 / 非空=显式分组 |
| 孤儿子表 | 载荷表名与模板 `tables[].name` 不一致时产生的、附注里永空或重复的表 |
| seed 路径 | 新建项目 / 重新生成附注时由 `disclosure_engine` 从模板生成 `table_data` 的路径 |
| 幂等脚本 | `backend/scripts/fix/fix_note_*_structure.py`，带 `--dry-run` / `--check` / `--apply` |
