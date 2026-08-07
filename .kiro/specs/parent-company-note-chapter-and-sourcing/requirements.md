# Requirements Document

## Introduction

修复「母公司财务报表主要项目附注」章节的结构错误与取数缺失，并顺带修正报表侧同源的母公司口径缺陷。

**背景与判据真源**（2026-08-05 实证）：

附注模板的源头是两份 docx，此前被误认为不存在，实际位于 `docs/模版/`：

| 变体 | 源 docx | 母公司章 |
|---|---|---|
| listed | `docs/模版/1.上市公司年审报表及附注-2026.01/1.上市公司年审报表及附注-2026.01/3.2025年度上市公司财务报表附注模板-2026.01.15.docx` | 第 16 章「公司财务报表主要项目注释」（Heading 1，章号是 Word 自动编号） |
| soe | `docs/模版/1、2025年度财务决算审计报告-2026.01.06/1、2025年度财务决算审计报告-国企/1.1-2025国企财务报表附注20260119.docx` | 第 12 章「母公司财务报表的主要项目附注」（Heading 1） |

**源模板对母公司章的明文口径**（soe docx 章首说明原文）：

> 「母公司报表主要项目包括应收账款、其他应收款、长期股权投资、营业收入和营业成本、投资收益、现金流量表补充资料等项目，**应参照上述相应项目的要求加以注释**」

listed docx 更直接，4 个子节标题里就写着「披露格式参考附注五、X」。因此母公司章分两类子节：

- **同构子节**（源 docx 无自有表，明文参照合并章）：listed = 应收票据（参考五、4）/ 应收账款（参考五、5）/ 其他应收款（参考五、8）/ 营业收入和营业成本（参考五、62）；soe = 应收账款 / 其他应收款 / 营业收入与营业成本
- **自有表子节**（源 docx 有独立表，与合并章不同构）：listed = 长期股权投资（3 表）/ 投资收益（1 表）；soe = 长期股权投资（3 表）/ 投资收益（1 表）/ 现金流量表补充资料（1 表）

两版子节集合**不对称且不得强行对齐**：listed 有「应收票据」而 soe 无；soe 有「现金流量表补充资料」而 listed 无。

**当前实测缺陷**（`note_template_*.json` 与生产代码）：

1. soe 第十二章 `section_title` 写成「股份支付」、`section_id` 为 `chapter-12-gu-fen-zhi-fu`，而国企源 docx 14 个章里**根本没有股份支付章**（该章名是从 listed 模板串入）；6 个母公司子节的 `section_id` 亦带该错误 slug 前缀。
2. 母公司章全部表 `columns=0`、无 `guidance`、`report_row_code=None`、`_aligned_by=None`（listed 57 表 / soe 36 表）。
3. 长期股权投资的两级表头被压扁（2026-08-05 逐表实测，**注意不是三张全压**）：

   | 变体 | 表 | 源 docx 列数 | JSON 实测列数 | 是否压扁 |
   |---|---|---|---|---|
   | listed | 表 1 | 7 | **3** | 压扁 |
   | listed | 表 2 | 9 | **6** | 压扁 |
   | listed | 表 3 | 13 | **5** | 压扁 |
   | soe | 表 1 | 5 | **5** | **未压扁，与源一致** |
   | soe | 表 2 | 7 | **7** | **未压扁，与源一致** |
   | soe | 表 3 | 12 | **5** | 压扁 |

   ⇒ 实际需要重建的只有 listed 3 张 + soe 表 3 共 4 张；soe 表 1/表 2 已正确，**不得当作压扁去"修复"**（会把正确结构改坏）。

4. 表名为表头首格泄漏、**重名**与**空名**并存（2026-08-05 逐子节实测，规模远超此前描述）：

   | 变体 | 子节 | 表数 | 空名表 | 重名组（名×次数） |
   |---|---|---|---|---|
   | listed | 应收票据 | 14 | 1 | `种  类`×3、`类 别`×2、`承兑人名称`×3、`名  称`×2 |
   | listed | 应收账款 | 15 | **6** | `类  别`×2、`名  称`×2、`（空名）`×6、`单位名称`×3 |
   | listed | 其他应收款 | 18 | 0 | `项  目`×4、`项  目（或被投资单位）`×2、`类  别`×6、`单位名称`×3 |
   | listed | 长期股权投资 | 3 | 0 | `被投资单位`×2 |
   | listed | 营业收入与营业成本 | 6 | 0 | `项  目`×3 |
   | soe | 其他应收款 | 15 | 0 | `其他应收款（续）债务人名称`×4 |

   表名是 `sub_table_data` 的键 ⇒ listed 应收账款 15 张表中 6 张空名会塌成 1 张、`类  别`×6 塌成 1 张；listed 5 个子节 + soe 1 个子节均受影响（listed 投资收益 1 表、soe 其余 5 子节无重名/空名）。
5. 母公司章 100% 无数据来源：`note_template_variant_matrix.json` 102 科目 × 4 变体中指向十六/十二章的条目为 **0**（且 `soe_standalone ≡ soe_consolidated`、`listed_standalone ≡ listed_consolidated`，单体/合并不区分）；全前端 40+ 个 `*NoteSectionMap.ts` 无一指向母公司章。
6. 母公司数据的正确来源是**同企业代码的兄弟项目**：`projects` 表唯一索引 `uq_project_company_year_scope (company_code, audit_year, report_scope)` 保证同代码同年度只能靠 `report_scope` 区分，故「合并 + 母公司单体」是唯一可能的同代码对。`project_display.get_project_display_name(project, all_projects)`（**函数名逐字为此，不是 `build_project_display_name`**）已正确实现该判定（consolidated → 名称加「（合并）」；standalone 且存在同代码同年度 consolidated 兄弟 → 加「（母公司）」），但它只吃 dict 列表、**没有任何 DB 层 helper 供取数复用**。
7. 报表侧 `report_excel_exporter._load_parent_row_index()` 用错口径：按 `Project.company_code == project.parent_company_code`（**上级公司**，不同代码）定位，而非同代码 standalone；且查询只过滤 `company_code` + `is_deleted`，**缺 `report_scope` 与 `audit_year`** —— docstring 明写「匹配的 standalone 项目」但代码无该条件，若同代码同时存在合并与单体两条项目，`.first()` 可能把**合并数**当母公司个别数填入导出报表。
8. `note_section_catalog.normalize_report_scope()` 只认 `standalone`/`consolidated`，其余静默回退 `standalone`；`parent_only` 全后端仅 1 处（`wp_render_config` 底稿层 redirect），附注层无法表达母公司口径。

**真实库现状**：8 个项目全部 `report_scope='standalone'`、无一 `consolidated`；`consol_scope`/`consol_trial`/`companies` 三表 0 行；`parent_project_id` 0 条使用。⇒ 缺陷 5~8 目前为潜伏态，建第一个合并项目时会同时暴露，其中缺陷 7 属「会把错数字写入导出交付件」一类。

**范围外**：合并附注 V2（`CONSOL_NOTES_V2_ENABLED`）、跨模板翻译、国企↔上市转换（`execute_conversion` 三步空操作）另立 spec；本 spec 不改合并章节任何结构。

## Requirements

### 需求 1：判据真源锁定与事实基线

**User Story:** 作为维护者，我需要母公司章的结构判据可机器复核，避免后续会话再次按「常识」改动或误判为重复章。

#### Acceptance Criteria

1.1. WHEN 运行结构守卫 THEN 系统 SHALL 以 `docs/模版/` 下两份源 docx 为唯一裁决者，通过 python-docx 直读 Heading 1 定位母公司章（listed「公司财务报表主要项目注释」/ soe「母公司财务报表的主要项目附注」），不得以 `note_template_*.json` 自证。

1.2. WHEN 源 docx 缺失 THEN 守卫 SHALL 明确失败并提示路径，不得静默跳过（防判据失效变成空转）。

1.3. THE 系统 SHALL 登记两版母公司章子节集合的不对称事实：listed 独有「应收票据」、soe 独有「现金流量表补充资料」，并加反向断言禁止两版被强行对齐。

1.4. THE 系统 SHALL 登记「同构子节」与「自有表子节」两类清单，每条附源 docx 依据（listed 为标题内「披露格式参考附注五、X」字样；soe 为章首说明「应参照上述相应项目的要求加以注释」）。

1.5. WHEN 母公司章被判定为「孤儿重复章」并试图删除 THEN 守卫 SHALL 打红，断言该章及其子节必须存在。

### 需求 2：soe 第十二章标题与标识修正

**User Story:** 作为审计师，我打开国企项目的附注目录时，母公司项目应显示在「母公司财务报表的主要项目附注」章下，而不是「股份支付」下。

#### Acceptance Criteria

2.1. THE `note_template_soe.json` 第十二章 `section_title` SHALL 为「母公司财务报表的主要项目附注」（逐字取自源 docx Heading 1）。

2.2. THE 第十二章 `section_id` SHALL 由 `chapter-12-gu-fen-zhi-fu` 改为反映母公司语义的 slug，且 6 个子节的 `section_id` 前缀 SHALL 同步改写。

2.3. WHEN 改写 `section_id` THEN 系统 SHALL 提供旧 → 新 slug 的迁移映射，并把旧 slug 登记进 `legacy_aliases`，使既有 `disclosure_notes` 行仍可解析（不丢数据）。

2.4. THE 守卫 SHALL 断言国企源 docx 的 14 个 Heading 1 中不含「股份支付」，以证明该章名属串入错误。

2.5. THE 系统 SHALL 保持第十二章的 `sort_index` 与在 14 章中的位置不变（位于「关联方关系及其交易」之后、「按照有关财务会计制度应披露的其他内容」之前）。

### 需求 3：listed 第十六章标题偏差处置

**User Story:** 作为维护者，我需要 listed 侧标题与源 docx 的偏差被显式登记并有明确处置，而不是留着让人猜。

#### Acceptance Criteria

3.1. THE 系统 SHALL 登记实测偏差：源 docx 为「公司财务报表主要项目注释」，`note_template_listed.json` 为「母公司财务报表主要项目注释」（多一个「母」字）。

3.2. THE 系统 SHALL 保留 JSON 现值「母公司财务报表主要项目注释」，理由 SHALL 在登记项中写明：该表述业务上更准确（与第五章「合并财务报表项目注释」构成合并/母公司对照），且改标题会波及 `section_id` slug 与既有 `disclosure_notes` 数据。

3.3. THE 守卫 SHALL 双向锁死该偏差：既断言 JSON 现值不变，也断言源 docx 原值不变（源模板哪天改了就打红，提醒重新裁决）。

### 需求 4：母公司章表结构对齐

**User Story:** 作为审计师，母公司章各子节的表结构必须与源模板一致，同构子节参照合并章、自有表子节按母公司章自己的表，不能混。

#### Acceptance Criteria

4.1. WHEN 子节属「同构子节」THEN 其表集合与列结构 SHALL 与本变体合并章对应科目一致（listed 应收票据→五、4 / 应收账款→五、5 / 其他应收款→五、8 / 营业收入和营业成本→五、62；soe 对应科目同理）。

4.2. WHEN 子节属「自有表子节」THEN 其表集合与列结构 SHALL 严格按母公司章源 docx，**不得**复制合并章结构。

4.3. THE listed 长期股权投资 SHALL 为 3 张表，列数分别为 7 / 9 / 13，且均为两级表头（表 1 = 项目 × {期末余额, 上年年末余额} × {账面余额, 减值准备, 账面价值}；表 2 = 被投资单位/期初余额（账面价值）/减值准备期初余额/本期增减变动{追加投资, 减少投资, 计提减值准备, 其他}/期末余额（账面价值）/减值准备期末余额；表 3 = 表 2 的本期增减变动扩展为 8 子列）。该三张表当前 JSON 实测为 3 / 6 / 5 列，**三张均需重建**。

4.4. THE soe 长期股权投资 SHALL 为 3 张表，列数分别为 5 / 7 / 12（表 1 = 项目/期初余额/本期增加/本期减少/期末余额；表 2 = 被投资单位/期初余额/本期增加/本期减少/期末余额/本期计提减值准备/减值准备期末余额；表 3 = 被投资单位/期初余额/本期增减变动{8 子列}/期末余额/减值准备期末余额）。当前 JSON 实测为 5 / 7 / 5 列 —— **表 1 与表 2 已与源一致，只有表 3 需重建**；守卫 SHALL 对表 1/表 2 加「结构已正确、不得改动」的反向断言，防止按「三张全压扁」的错误前提改坏正确结构。

4.5. THE 两级表头 SHALL 走既有唯一机制 `ColumnDef.group`，单级表 SHALL 显式标 `flat`；**禁止**新建表头机制。

4.6. WHEN 源 docx 某表首列样本含 `…` 或 `一、合营企业`/`二、联营企业` 分组行 THEN 系统 SHALL 保留为可扩行/结构行，不得作为占位删除。

4.7. THE 投资收益表 SHALL 按各自源 docx 行集（listed 16 行 / soe 21 行含表头），**不得**套用合并章的投资收益表（listed 合并侧为 2 张表 15+11 行，与母公司侧 1 张表不同构）。

4.8. THE 系统 SHALL 不增删母公司章的子节数量（listed 6 个 / soe 6 个）。

### 需求 5：列元数据与编制指引补齐

**User Story:** 作为审计师，母公司章的表在附注编辑器里要能正常显示列头与编制提示，而不是只显示行名。

#### Acceptance Criteria

5.1. THE 母公司章全部表 SHALL 具备非空 `columns`，且每张表 SHALL 显式表态 `group` 或 `flat`（三态语义：`None`=未声明会触发前缀推断，必须避免）。

5.2. THE 母公司章全部表 SHALL 具备 `guidance`，内容 SHALL 仅取自源 docx 红字/括注/章首说明，或以「勾稽：」前缀标注的工具提示；**禁止**自造披露要求。

5.3. THE `guidance` SHALL 为纯文本，不含 markdown 粗体标记（与平台级 `fix_note_bold_markers.py` 不打架）。

5.4. THE 修订 SHALL 由幂等脚本执行，支持 `--dry-run` / `--check`，`--check` 在无欠账时 exit 0。

5.5. WHEN 幂等脚本重复执行 THEN 结果 SHALL 逐字节一致。

### 需求 6：表名唯一化

**User Story:** 作为审计师，母公司章的每张表都要有稳定唯一的名字，否则同步时会互相覆盖丢表。

#### Acceptance Criteria

6.1. THE 母公司章内每个子节的表名 SHALL 唯一（同子节内不得重名），且 SHALL 非空。

6.2. WHEN 表名为表头首格泄漏或空名 THEN 系统 SHALL 按 soe 侧已有的自动编号范式正名（主表 = 科目名，其余 = `{科目名}（表N）`），**不得**臆造业务表名。

6.3. THE 正名 SHALL 提供旧名 → 新名映射并登记进 `legacy_aliases` 或 `_removed_table_keys` 语义，使既有已同步数据不成孤儿。

6.4. THE 守卫 SHALL 断言母公司章不存在重名表与空名表。

6.5. THE 正名 SHALL 覆盖实测的全部 6 个受影响子节（listed 应收票据/应收账款/其他应收款/长期股权投资/营业收入与营业成本 + soe 其他应收款），**不得**只处理其中一个；listed 应收账款的 6 张空名表 SHALL 逐张获得稳定唯一名（现状 6 张塌成 1 键）。

6.6. THE 守卫 SHALL 按「同子节内表名集合大小 == 表数量」断言唯一性（而非仅检查是否存在空串），并对每个子节输出实际表数与去重后键数以便定位塌键规模。

### 需求 7：母公司口径项目定位（共享 helper）

**User Story:** 作为开发者，我需要一个单一真源的 helper 来定位「母公司单体项目」，让附注与报表共用同一口径，避免两个交付件的母公司数打架。

#### Acceptance Criteria

7.1. THE 系统 SHALL 提供 `resolve_parent_standalone_project(db, consol_project)`，按 `(company_code, audit_year, report_scope='standalone')` 定位同代码兄弟项目。

7.2. THE helper SHALL 依赖唯一索引 `uq_project_company_year_scope` 保证结果唯一，并断言查询三个条件齐备（缺 `report_scope` 或 `audit_year` 即为缺陷）。

7.3. WHEN 入参项目本身不是 `consolidated` THEN helper SHALL 返回 None（母公司口径只在合并项目下成立）。

7.4. WHEN 找不到兄弟项目 THEN helper SHALL 返回 None 并记 INFO 级日志，调用方 SHALL 留空而非报错（合并项目尚未建母公司单体是合法状态）。

7.5. THE helper SHALL 提供反向 `resolve_consolidated_sibling(db, standalone_project)`，用于判定某 standalone 项目是否为母公司（与 `project_display` 的判定口径一致）。

7.6. THE 守卫 SHALL 交叉锁死 helper 与 `project_display.get_project_display_name(project, all_projects)` 的判定口径：对同一组项目输入，「被判为母公司」（即显示名以「（母公司）」结尾）的集合必须与 helper 判定结果相等。守卫 SHALL 先断言该函数名存在于 `app.services.project_display`（防按错名写守卫导致 0 命中空转）。

### 需求 8：母公司章取数接线

**User Story:** 作为审计师，母公司章的表应能从母公司单体项目自动取数，而不是纯手工填。

#### Acceptance Criteria

8.1. THE `note_template_variant_matrix.json` SHALL 增加母公司口径维度，使母公司章的科目能被解析到（现状 `standalone` 与 `consolidated` 取值完全相同，母公司章零条目）。

8.2. WHEN 附注章节属母公司章 THEN 取数 SHALL 指向 `resolve_parent_standalone_project()` 返回项目的 `trial_balance` / 底稿数据，而非合并数。

8.3. THE 母公司章的表 SHALL 具备 `report_row_code`（现状全为 None），取值 SHALL 按 `report_config` 实证对账，不得按名称推断。

8.4. WHEN 母公司单体项目不存在 THEN 母公司章 SHALL 显示「本项目未建母公司单体」提示并留空，不得显示 0（区分「无数据」与「余额为 0」）。

8.5. THE 母公司章的取数 SHALL 具备溯源展示（来源项目名 + 企业代码 + 口径），复用既有溯源面板范式。

8.6. THE 附注层 SHALL 能表达母公司口径：`normalize_report_scope` 的取值域处置 SHALL 显式登记（扩展取值 或 说明为何 `consolidated_only` + 跨项目取数已足够），不得留 `parent_only` 被静默回退的歧义。

### 需求 9：报表侧母公司列口径修正

**User Story:** 作为审计师，合并报表里的「母公司个别数」列必须是编制合并报表那家公司自己的单体数，且不能混入合并数或跨年数。

#### Acceptance Criteria

9.1. THE `report_excel_exporter._load_parent_row_index()` SHALL 改用 `resolve_parent_standalone_project()`，不再按 `parent_company_code` 定位上级公司。

9.2. THE 查询 SHALL 同时过滤 `report_scope='standalone'` 与 `audit_year`，消除「可能取到合并项目」与「跨年度串数」两个缺口。

9.3. WHEN 定位不到母公司单体项目 THEN 该列 SHALL 留空并记 INFO 日志（保持既有 fail-open 行为，不崩）。

9.4. THE 守卫 SHALL 用反向自检复现旧行为必打红：构造「同代码同时存在 consolidated 与 standalone 两条项目」的场景，断言旧实现会取到合并项目、新实现取到单体项目。

9.5. THE 修正 SHALL 不改变 `:parent` 占位符与 `current_parent` 坐标的语义与填充位置。

### 需求 10：守卫与零回归

**User Story:** 作为维护者，我需要这批修正被守卫钉死，且不影响合并章节与其余 100 个科目的既有行为。

#### Acceptance Criteria

10.1. THE 后端守卫 SHALL 直读源 docx 与 `note_template_*.json` 做三向比对（源 docx ↔ 模板 JSON ↔ 同步列定义），并含反向自检（把结构改错必打红）。

10.2. THE 每个新增守卫 SHALL 实际执行变异检验：改一处必变红，且变异后必须还原。

10.3. THE 合并章节（listed 五、soe 八）的结构 SHALL 逐字节不变，由 characterization 测试钉死。

10.4. THE 其余 100 个非母公司科目的 `variant_matrix` 取值 SHALL 不变。

10.5. THE 修正 SHALL 挂 CI job，并在 `--check` 无欠账时 exit 0。

10.6. THE 真实库验收 SHALL 覆盖「合并项目 + 母公司单体项目」这一对的端到端取数；若真实库无合并项目（当前实测 8 个项目全 standalone），SHALL 明确报告「无法验收」而非用 fixture 冒充通过。

## Glossary

| 术语 | 定义 | 判据/真源 |
|---|---|---|
| **母公司章** | 合并报表附注中单列母公司（本公司）个别报表主要项目的章节 | listed = 源 docx 第 16 章「公司财务报表主要项目注释」；soe = 源 docx 第 12 章「母公司财务报表的主要项目附注」 |
| **合并章** | 合并报表项目注释章 | listed = 第 5 章「合并财务报表项目附注」；soe = 第 8 章「财务报表主要项目注释」 |
| **同构子节** | 母公司章中源 docx **无自有表**、明文要求参照合并章的子节 | listed 标题内「披露格式参考附注五、X」字样；soe 章首说明「应参照上述相应项目的要求加以注释」。listed = 应收票据/应收账款/其他应收款/营业收入和营业成本；soe = 应收账款/其他应收款/营业收入与营业成本 |
| **自有表子节** | 母公司章中源 docx **有独立表**、与合并章不同构的子节 | listed = 长期股权投资(3 表 7/9/13 列)、投资收益(1 表 16 行)；soe = 长期股权投资(3 表 5/7/12 列)、投资收益(1 表 21 行)、现金流量表补充资料(1 表 31 行) |
| **母公司单体项目** | 与合并项目**同企业代码、同年度**但口径为单体的那条 `projects` 记录 | `(company_code, audit_year, report_scope='standalone')`；唯一索引 `uq_project_company_year_scope` 保证同代码同年度只能靠 `report_scope` 区分，故「合并 + 母公司单体」是唯一可能的同代码对 |
| **同代码兄弟** | 上述这一对项目的互称 | `project_display.get_project_display_name(project, all_projects)` 已实现判定：consolidated → 名称加「（合并）」；standalone 且存在同代码同年度 consolidated 兄弟 → 加「（母公司）」。**函数名逐字为此**，写守卫前先断言其存在 |
| **上级公司** | 由 `parent_company_code` 指向的**另一家**公司（代码不同） | **不是**母公司单体。区分这两者是本 spec 需求 9 的核心 —— 报表侧原实现把两者混为一谈 |
| **三个企业代码** | 构建合并树的字段 | `projects.company_code`（本企业）/ `parent_company_code`（上级）/ `ultimate_company_code`（最终），配 `parent_project_id` + `consol_level` |

### 已裁决事项（后续会话不得推翻，除非源模板变更）

1. **母公司章不是「孤儿重复章」，禁删**。此前曾被误判为 md 重建重复落章并建议 `--apply` 删除；实证为母公司章正当子节（判断已于 2026-08-05 撤回）。
2. **表结构不与合并章完全同构**：仅「同构子节」参照合并章，「自有表子节」严格按母公司章源 docx（用户 2026-08-05 明确裁决）。
3. **两版子节集合不对称且不对齐**：listed 独有「应收票据」、soe 独有「现金流量表补充资料」。
4. **listed 标题保留 JSON 现值**「母公司财务报表主要项目注释」（源 docx 为「公司财务报表主要项目注释」），理由见需求 3.2。
5. **表名正名不臆造业务名**，沿用 soe 侧已有的 `{科目名}（表N）` 自动编号范式。

6. **soe 长期股权投资表 1（5 列）与表 2（7 列）结构已正确**（与源 docx 一致），只有表 3 被压扁（5 vs 源 12）。listed 三张才是全压扁（3/6/5 vs 源 7/9/13）。此结论于 2026-08-05 逐表实测得出，**不得按「两版三张表全压扁」的错误前提动 soe 表 1/表 2**。
