# 需求文档：第一阶段MVP底稿 — ONLYOFFICE集成+底稿模板引擎+底稿质量自检

## 简介

本文档定义审计作业平台第一阶段MVP底稿模块的需求。本阶段在Phase 1核心（数据导入+试算表+调整分录）基础上，实现底稿编辑、模板管理和质量自检三大核心能力。涵盖：底稿模板引擎（取数公式DSL解析与执行、区域类型定义、模板版本管理）、ONLYOFFICE集成（WOPI Host实现、自定义取数函数插件、复核批注插件）、底稿索引与生成、底稿质量自检（规则引擎，12项检查规则）。本阶段依赖Phase 0基础设施和Phase 1核心已实现的试算表、调整分录、科目映射等模块。

## 术语表

- **Platform（审计作业平台）**：面向会计师事务所的本地私有化审计全流程作业系统
- **Auditor（审计员）**：执行审计程序、编制底稿的项目组成员
- **Manager（项目经理）**：负责项目管理、复核底稿质量的项目负责人
- **WOPI_Host（WOPI宿主服务）**：实现WOPI协议的FastAPI后端服务，管理ONLYOFFICE与后端的文件交互（文件存取、锁定/解锁、版本管理、权限校验）
- **ONLYOFFICE_Editor（在线编辑器）**：通过iframe嵌入前端的ONLYOFFICE Document Server实例，提供原生.xlsx/.docx编辑能力
- **Template_Engine（底稿模板引擎）**：管理底稿模板文件的生命周期、定义取数公式执行规则、管理模板中的区域标记、在项目创建时从模板生成项目底稿文件的后端服务
- **WP_Template（底稿模板）**：标准的.xlsx/.docx文件，通过命名范围和自定义函数实现结构化管理，存储于`wp_template`表
- **WP_Template_Set（底稿模板集）**：一组底稿模板的集合，按审计类型和适用准则组织，如"标准年审"、"IPO审计"等
- **WP_Index（底稿索引）**：底稿的目录结构，记录底稿编号、名称、所属循环、编制人、复核人、状态，存储于`wp_index`表
- **Working_Paper（底稿）**：项目中的具体底稿文件（.xlsx/.docx），元数据存储于`working_paper`表，文件内容存储在项目目录中
- **WP_Cross_Ref（底稿交叉索引）**：底稿间的引用关系，实现底稿间穿透跳转，存储于`wp_cross_ref`表
- **Formula_Engine（取数公式引擎）**：解析和执行底稿中取数公式（TB/WP/AUX/PREV/SUM_TB）的后端服务，为ONLYOFFICE自定义函数提供数据
- **TB_Function（试算表取数函数）**：`=TB(科目代码, 列名)`，从试算表获取指定科目的指定列数据
- **WP_Function（跨底稿引用函数）**：`=WP(底稿编号, 单元格引用)`，引用其他底稿中指定单元格的值
- **AUX_Function（辅助账取数函数）**：`=AUX(科目代码, 辅助维度, 维度值, 列名)`，从辅助余额表获取数据
- **PREV_Function（上年数据函数）**：`=PREV(公式)`，获取上年同期数据
- **SUM_TB_Function（科目范围汇总函数）**：`=SUM_TB(科目代码范围, 列名)`，汇总指定科目范围的数据
- **QC_Engine（质量自检引擎）**：底稿提交复核前自动执行12项检查规则的规则引擎
- **Named_Range（命名范围）**：Excel命名范围，用于标记底稿中的结论区（WP_CONCLUSION）、取数公式区、人工填写区等区域
- **Prefill（预填充）**：离线下载前后端批量执行取数公式并将结果写入.xlsx单元格的过程
- **Parse_Back（解析回写）**：上传.xlsx后后端解析人工填写区域并将结构化数据回写数据库的过程

## 需求

### 需求 1：底稿模板管理

**用户故事：** 作为项目经理，我希望系统提供底稿模板的上传、版本管理和模板集组织能力，以便事务所的标准底稿模板能在系统中统一管理和分发。

#### 验收标准

1. THE Template_Engine SHALL support uploading .xlsx and .docx template files with the following metadata: template code (e.g. "E1-1"), template name, audit cycle (e.g. "货币资金"), applicable accounting standard, version number (major.minor format), and status (draft/published/deprecated)
2. THE Template_Engine SHALL store template metadata in the `wp_template` table and the template file in the file system at path `templates/{template_code}/{version}/{filename}`
3. WHEN a template with the same template code already exists, THE Template_Engine SHALL increment the version number: major version for structural changes (add/remove rows/columns, modify formulas), minor version for formatting changes (text edits, style adjustments)
4. THE Template_Engine SHALL prevent deletion of template versions that are referenced by any project's working papers
5. THE Template_Engine SHALL parse uploaded .xlsx template files using openpyxl to extract Named Ranges and store them in the `wp_template_meta` table with fields: template_id, range_name, region_type (formula/manual/ai_fill/conclusion/cross_ref), and description
6. THE Template_Engine SHALL support organizing templates into template sets (`wp_template_set` table) with fields: set_name, template_code_list (array), applicable_audit_type, and applicable_standard
7. THE Platform SHALL provide 6 built-in template sets: standard annual audit (标准年审), simplified version (精简版), listed company (上市公司), IPO, SOE notes (国企附注), and listed company notes (上市附注)
8. WHEN Manager creates a new project and selects a template set, THE Template_Engine SHALL copy all template files from the selected set into the project directory at `/{project_id}/{year}/` and create corresponding `wp_index` and `working_paper` records

### 需求 2：取数公式引擎

**用户故事：** 作为审计员，我希望在底稿中使用取数公式（如`=TB("1001","期末余额")`）自动从试算表和其他数据源获取数据，以便底稿中的数据始终与系统数据保持一致。

#### 验收标准

1. THE Formula_Engine SHALL support the following custom functions with their exact syntax:
   - `TB(account_code, column_name)` — fetch from trial balance (columns: 期末余额/未审数/AJE调整/RJE调整/年初余额)
   - `WP(wp_code, cell_ref)` — cross-workpaper reference
   - `AUX(account_code, aux_dimension, dimension_value, column_name)` — fetch from auxiliary balance
   - `PREV(formula)` — fetch prior year data by wrapping any formula
   - `SUM_TB(account_code_range, column_name)` — sum over account code range (e.g. "6001~6099")
2. WHEN the TB function is called with a valid account code and column name, THE Formula_Engine SHALL return the corresponding value from the `trial_balance` table for the current project and year within 1 second
3. WHEN the WP function is called with a valid workpaper code and cell reference, THE Formula_Engine SHALL parse the referenced workpaper file using openpyxl and return the cell value within 1 second
4. WHEN the AUX function is called, THE Formula_Engine SHALL query the `tb_aux_balance` table filtered by account_code, aux_type, and aux_name, and return the specified column value
5. WHEN the PREV function wraps any supported formula, THE Formula_Engine SHALL execute the inner formula against the prior year's data (year - 1) for the same project
6. WHEN the SUM_TB function is called with an account code range (format "start~end"), THE Formula_Engine SHALL sum the specified column values for all accounts whose codes fall within the range (inclusive, string comparison)
7. IF a formula references a non-existent account code or unmapped account, THEN THE Formula_Engine SHALL return an error object with code "FORMULA_ERROR" and a descriptive message (e.g. "科目1001未配置映射")
8. THE Formula_Engine SHALL cache formula results in Redis with key pattern `formula:{project_id}:{year}:{formula_hash}` and TTL of 5 minutes, and invalidate cache entries when underlying data changes (trial balance recalculation, adjustment entry CRUD, data import)
9. THE Formula_Engine SHALL provide a REST API endpoint `POST /api/formula/execute` accepting `{project_id, year, formula_type, params}` and returning `{value, cached, error}`
10. FOR ALL valid formulas, executing the formula twice with unchanged underlying data SHALL return identical results (deterministic execution)

### 需求 3：WOPI Host实现与ONLYOFFICE集成

**用户故事：** 作为审计员，我希望在浏览器中直接编辑底稿（.xlsx/.docx），体验与本地Excel/Word一致，以便零学习成本地在线编制审计底稿。

#### 验收标准

1. THE WOPI_Host SHALL implement the following WOPI protocol endpoints:
   - `GET /wopi/files/{file_id}` — CheckFileInfo (return file metadata: filename, size, owner, permissions, version)
   - `GET /wopi/files/{file_id}/contents` — GetFile (return file binary content)
   - `POST /wopi/files/{file_id}/contents` — PutFile (save file content, update version)
   - `POST /wopi/files/{file_id}` — Lock/Unlock/RefreshLock operations
2. THE WOPI_Host SHALL validate access tokens on every WOPI request by verifying the JWT token contains valid user_id and project_id claims, and the user has appropriate permissions for the requested operation
3. THE WOPI_Host SHALL manage file locking: Lock operation acquires an exclusive lock with a lock_id, Unlock releases it, RefreshLock extends the lock timeout; IF a different user attempts to edit a locked file, THEN THE WOPI_Host SHALL return HTTP 409 Conflict
4. THE WOPI_Host SHALL store working paper files in the project directory at path `{storage_root}/{project_id}/{year}/{wp_code}.xlsx` and track file metadata (file_path, file_version, last_modified) in the `working_paper` table
5. THE Platform SHALL embed ONLYOFFICE Editor in the frontend via iframe, passing the WOPI discovery URL and access token, so that Auditor can edit .xlsx and .docx files directly in the browser
6. THE ONLYOFFICE_Editor SHALL load a working paper file within 3 seconds from the moment Auditor clicks to open it
7. WHEN ONLYOFFICE saves a file via PutFile, THE WOPI_Host SHALL increment the `file_version` in the `working_paper` table and update `updated_at` timestamp
8. WHEN ONLYOFFICE_Editor is unavailable (service down), THE Platform SHALL automatically degrade to offline mode: display a "下载编辑" button instead of the inline editor, allowing Auditor to download the .xlsx file for local editing

### 需求 4：ONLYOFFICE自定义取数函数插件

**用户故事：** 作为审计员，我希望在ONLYOFFICE编辑器中直接输入取数公式（如`=TB("1001","期末余额")`），公式实时调用后端API返回数据，体验与Excel原生函数一致。

#### 验收标准

1. THE Platform SHALL develop an ONLYOFFICE plugin that registers custom functions (TB, WP, AUX, PREV, SUM_TB) via the ONLYOFFICE `AddCustomFunction` API
2. WHEN Auditor types a custom function in a cell (e.g. `=TB("1001","期末余额")`), THE plugin SHALL asynchronously call the Formula_Engine REST API (`POST /api/formula/execute`) and display the returned value in the cell
3. IF the Formula_Engine returns an error, THE plugin SHALL display `#REF!` in the cell and show the error message (e.g. "科目1001未配置映射") as a cell tooltip on hover
4. THE plugin SHALL respond to each formula execution within 1 second end-to-end (from cell input to value display)
5. WHEN underlying data changes (e.g. new adjustment entry created), THE Platform SHALL notify open ONLYOFFICE sessions via the ONLYOFFICE Command Service API to trigger formula recalculation in affected cells, updating only formula cells without overwriting manual input cells

### 需求 5：ONLYOFFICE复核批注插件

**用户故事：** 作为项目经理，我希望在ONLYOFFICE编辑器中直接对底稿添加复核意见，审计员可以逐条回复，以便复核流程在底稿编辑界面内闭环完成。

#### 验收标准

1. THE Platform SHALL develop an ONLYOFFICE sidebar plugin that displays a review comments panel listing all review comments for the current working paper, sorted by creation time
2. WHEN Manager adds a review comment, THE plugin SHALL save it to the `review_records` table with fields: working_paper_id, cell_reference (optional), comment_text, commenter_id, status (open/replied/resolved), and created_at
3. WHEN Auditor replies to a review comment, THE plugin SHALL update the comment status to "replied" and append the reply text with replier_id and replied_at timestamp
4. WHEN Manager marks a comment as "resolved", THE plugin SHALL update the status and record resolved_by and resolved_at
5. THE plugin SHALL display unresolved comments with a coral-orange left border (`#FF5149`) and replied comments with a teal-blue left border (`#0094B3`), following the GT brand visual specification

### 需求 6：底稿索引与底稿生成

**用户故事：** 作为项目经理，我希望系统自动生成项目底稿索引并从模板创建底稿文件，以便项目底稿有清晰的组织结构和编号体系。

#### 验收标准

1. THE Platform SHALL maintain a workpaper index (`wp_index` table) for each project with fields: project_id, wp_code (e.g. "E1-1"), wp_name, audit_cycle, assigned_to (user_id), reviewer (user_id), status (not_started/in_progress/draft_complete/review_passed/archived), and cross_ref_codes (array of referenced workpaper codes)
2. WHEN a project is created with a selected template set, THE Template_Engine SHALL automatically generate `wp_index` records for all templates in the set, with status "not_started" and assigned_to/reviewer as null
3. THE Platform SHALL generate working paper files by copying template files to the project directory and creating `working_paper` records with fields: project_id, wp_index_id, file_path, source_type (template/manual/imported), status (draft/edit_complete/review_level1_passed/review_level2_passed/archived), assigned_to, reviewer, file_version (starting at 1), and last_parsed_at
4. THE Template_Engine SHALL execute prefill on generated working paper files: batch-execute all formula cells using openpyxl, writing computed values into cells while preserving the formula text in cell comments for reference
5. THE Platform SHALL complete prefill for a single working paper within 5 seconds
6. WHEN Auditor uploads a working paper file (.xlsx), THE Platform SHALL parse the file using openpyxl to extract values from manual input regions (identified by Named Ranges), store extracted data in the `working_paper` table's metadata, and update `last_parsed_at` timestamp, completing within 3 seconds
7. THE Platform SHALL maintain cross-reference relationships in the `wp_cross_ref` table with fields: source_wp_id, target_wp_code, cell_reference, and auto-populate these records by scanning WP() function calls in working paper files

### 需求 7：底稿离线编辑支持

**用户故事：** 作为审计员，我希望在客户现场没有网络时能下载底稿用本地Excel编辑，回到事务所后上传回系统，以便离线场景下审计工作不中断。

#### 验收标准

1. WHEN Auditor requests to download a working paper for offline editing, THE Platform SHALL execute prefill (replace formula cells with computed static values) and return the .xlsx file with the current `file_version` recorded
2. WHEN Auditor uploads an edited working paper file, THE Platform SHALL compare the uploaded file's recorded version against the current `file_version` in the database
3. IF the uploaded file version matches the current database version, THEN THE Platform SHALL accept the upload, parse manual input regions, update the file in the project directory, increment `file_version`, and trigger formula re-execution to refresh computed values
4. IF the uploaded file version is older than the current database version (another user has modified the file), THEN THE Platform SHALL detect the conflict and display a cell-level diff showing "本地值" vs "服务器值" for each conflicting cell, allowing Auditor to choose which value to keep for each cell
5. THE Platform SHALL preserve all manual input values during the upload-parse-refresh cycle: values entered by Auditor in manual input regions must not be overwritten by formula re-execution

### 需求 8：底稿质量自检引擎

**用户故事：** 作为审计员，我希望在提交底稿复核前系统自动执行质量检查，以便在复核人审阅之前发现并修正低级问题，提升复核效率。

#### 验收标准

1. THE QC_Engine SHALL execute the following 12 quality check rules when Auditor triggers a pre-review check on a working paper:

   **阻断级（必须通过才能提交复核）：**
   - Rule 1: WHEN the conclusion region (Named Range `WP_CONCLUSION`) is empty or contains only whitespace, THE QC_Engine SHALL report a blocking finding "结论区未填写"
   - Rule 2: WHEN any cell in the AI-fill region (background color `rgba(75,45,119,0.08)` with comment "AI填充") has status "待确认", THE QC_Engine SHALL report a blocking finding "AI填充区存在未确认内容"
   - Rule 3: WHEN any formula cell's current value differs from the Formula_Engine's live computation result by more than 0.01, THE QC_Engine SHALL report a blocking finding "取数公式结果与试算表不一致" with the cell reference, expected value, and actual value

   **警告级（允许提交但标注）：**
   - Rule 4: WHEN any cell in the manual input region (white background, unprotected) is empty, THE QC_Engine SHALL report a warning finding "人工填写区存在空白项" with the cell reference
   - Rule 5: WHEN any subtotal cell's value does not equal the sum of its detail cells (identified by Named Range patterns), THE QC_Engine SHALL report a warning finding "底稿内部合计数不正确"
   - Rule 6: WHEN a WP() cross-reference formula returns a value that differs from the referenced workpaper's current cell value by more than 0.01, THE QC_Engine SHALL report a warning finding "交叉索引引用数据不一致"
   - Rule 7: WHEN the working paper's wp_code does not exist in the `wp_index` table for the current project, THE QC_Engine SHALL report a warning finding "底稿编号未在索引表中登记"
   - Rule 8: WHEN a WP() formula references a wp_code that does not exist in the project's `wp_index`, THE QC_Engine SHALL report a warning finding "交叉索引引用的底稿不存在"
   - Rule 9: WHEN audit procedures linked to this working paper in the audit program are not all marked as "已执行", THE QC_Engine SHALL report a warning finding "关联审计程序未全部执行"
   - Rule 10: WHEN the working paper involves sampling and the `sampling_records` for this workpaper have incomplete fields (missing method, sample_size, result, or conclusion), THE QC_Engine SHALL report a warning finding "抽样记录不完整"
   - Rule 11: WHEN the working paper contains adjustment items (cells marked with adjustment annotations) that have not been recorded as adjustment entries in the `adjustments` table, THE QC_Engine SHALL report a warning finding "需调整事项未录入调整分录"

   **提示级：**
   - Rule 12: WHEN the working paper's preparation date is earlier than the project's field entry date or later than the project's report date, THE QC_Engine SHALL report an info finding "底稿编制日期超出合理范围"

2. THE QC_Engine SHALL return results as a structured list sorted by severity (blocking → warning → info), each finding containing: rule_id, severity, message, cell_reference (if applicable), expected_value (if applicable), and actual_value (if applicable)
3. IF any blocking-level finding exists, THEN THE Platform SHALL prevent the working paper from being submitted for review and display the blocking findings prominently
4. THE Platform SHALL store QC check results in a `wp_qc_results` table with fields: working_paper_id, check_timestamp, findings (jsonb), passed (boolean), checked_by (user_id), so that reviewers can view the QC status at the time of submission

### 需求 9：项目级底稿质量汇总

**用户故事：** 作为项目经理，我希望在项目看板中查看所有底稿的质量自检状态汇总，以便快速了解项目底稿的整体质量状况。

#### 验收标准

1. THE Platform SHALL provide a project-level QC summary API that returns: total_workpapers (total count in wp_index), passed_qc (count with no blocking findings), has_blocking (count with unresolved blocking findings), not_started (count with status "not_started"), and pass_rate calculated as passed_qc / (total_workpapers - not_started) × 100%
2. WHEN Manager views the project dashboard, THE Platform SHALL display the QC summary as a status card showing the five metrics defined above
3. THE Platform SHALL allow Manager to drill down from the QC summary to a list of workpapers filtered by QC status (passed/blocking/warning/not_checked)

### 需求 10：底稿相关数据表Schema定义

**用户故事：** 作为开发者，我希望底稿相关数据表的Schema明确定义，以便通过Alembic迁移脚本创建表结构。

#### 验收标准

1. THE Migration_Framework SHALL create the `wp_template` table with columns: `id` (UUID PK), `template_code` (varchar, not null), `template_name` (varchar, not null), `audit_cycle` (varchar), `applicable_standard` (varchar), `version_major` (integer, default 1), `version_minor` (integer, default 0), `status` (enum: draft/published/deprecated, default draft), `file_path` (varchar, not null), `description` (text), `is_deleted` (boolean, default false), `created_at`, `updated_at`, `created_by` (UUID FK to users); with composite unique index on (template_code, version_major, version_minor)
2. THE Migration_Framework SHALL create the `wp_template_meta` table with columns: `id` (UUID PK), `template_id` (UUID FK to wp_template), `range_name` (varchar, not null), `region_type` (enum: formula/manual/ai_fill/conclusion/cross_ref), `description` (text), `created_at`, `updated_at`; with index on (template_id)
3. THE Migration_Framework SHALL create the `wp_template_set` table with columns: `id` (UUID PK), `set_name` (varchar, not null, unique), `template_codes` (jsonb, array of template codes), `applicable_audit_type` (varchar), `applicable_standard` (varchar), `description` (text), `is_deleted` (boolean, default false), `created_at`, `updated_at`
4. THE Migration_Framework SHALL create the `wp_index` table with columns: `id` (UUID PK), `project_id` (UUID FK to projects), `wp_code` (varchar, not null), `wp_name` (varchar, not null), `audit_cycle` (varchar), `assigned_to` (UUID FK to users, nullable), `reviewer` (UUID FK to users, nullable), `status` (enum: not_started/in_progress/draft_complete/review_passed/archived, default not_started), `cross_ref_codes` (jsonb, array of wp_codes), `is_deleted` (boolean, default false), `created_at`, `updated_at`; with composite unique index on (project_id, wp_code)
5. THE Migration_Framework SHALL create the `working_paper` table with columns: `id` (UUID PK), `project_id` (UUID FK to projects), `wp_index_id` (UUID FK to wp_index), `file_path` (varchar, not null), `source_type` (enum: template/manual/imported), `status` (enum: draft/edit_complete/review_level1_passed/review_level2_passed/archived, default draft), `assigned_to` (UUID FK to users, nullable), `reviewer` (UUID FK to users, nullable), `file_version` (integer, default 1), `last_parsed_at` (timestamp, nullable), `is_deleted` (boolean, default false), `created_at`, `updated_at`, `created_by` (UUID FK to users), `updated_by` (UUID FK to users); with composite unique index on (project_id, wp_index_id)
6. THE Migration_Framework SHALL create the `wp_cross_ref` table with columns: `id` (UUID PK), `project_id` (UUID FK to projects), `source_wp_id` (UUID FK to working_paper), `target_wp_code` (varchar, not null), `cell_reference` (varchar), `created_at`, `updated_at`; with index on (project_id, source_wp_id)
7. THE Migration_Framework SHALL create the `wp_qc_results` table with columns: `id` (UUID PK), `working_paper_id` (UUID FK to working_paper), `check_timestamp` (timestamp, not null), `findings` (jsonb, not null), `passed` (boolean, not null), `blocking_count` (integer, default 0), `warning_count` (integer, default 0), `info_count` (integer, default 0), `checked_by` (UUID FK to users), `created_at`; with index on (working_paper_id)
8. THE Migration_Framework SHALL create the `review_records` table with columns: `id` (UUID PK), `working_paper_id` (UUID FK to working_paper), `cell_reference` (varchar, nullable), `comment_text` (text, not null), `commenter_id` (UUID FK to users), `status` (enum: open/replied/resolved, default open), `reply_text` (text, nullable), `replier_id` (UUID FK to users, nullable), `replied_at` (timestamp, nullable), `resolved_by` (UUID FK to users, nullable), `resolved_at` (timestamp, nullable), `is_deleted` (boolean, default false), `created_at`, `updated_at`; with index on (working_paper_id, status)


### 需求 11：抽样记录管理

**用户故事：** 作为审计员，我希望系统能支持抽样方法配置、样本量自动计算、抽样执行记录和结果推断，以便完整记录审计抽样程序的执行过程并满足质控检查要求。

#### 验收标准

1. THE Platform SHALL provide a sampling configuration interface using the `sampling_config` table with fields: `id` (UUID PK), `project_id` (UUID FK to projects), `config_name` (varchar, not null), `sampling_type` (enum: statistical/non_statistical, not null), `sampling_method` (enum: mus/attribute/random/systematic/stratified, not null), `applicable_scenario` (enum: control_test/substantive_test, not null), `confidence_level` (numeric(5,4), nullable, e.g. 0.95 for 95%), `expected_deviation_rate` (numeric(5,4), nullable, for attribute sampling), `tolerable_deviation_rate` (numeric(5,4), nullable, for attribute sampling), `tolerable_misstatement` (numeric(20,2), nullable, for MUS), `population_amount` (numeric(20,2), nullable, for MUS), `population_count` (integer, nullable, total items in population), `calculated_sample_size` (integer, nullable, auto-calculated), `is_deleted` (boolean, default false), `created_at`, `updated_at`, `created_by` (UUID FK to users); with composite index on (project_id, sampling_method)
2. WHEN Auditor selects a sampling method and fills in the required parameters, THE Platform SHALL automatically calculate the sample size using the following formulas:
   - Attribute sampling: sample_size = (confidence_factor / tolerable_deviation_rate) adjusted for expected_deviation_rate and population_count
   - MUS (Monetary Unit Sampling): sample_size = (population_amount × confidence_factor) / tolerable_misstatement
   - Random/Systematic: sample_size = user-specified or calculated from confidence level and population parameters
3. THE Platform SHALL provide a sampling execution and results interface using the `sampling_records` table with fields: `id` (UUID PK), `project_id` (UUID FK to projects), `working_paper_id` (UUID FK to working_paper, nullable), `sampling_config_id` (UUID FK to sampling_config, nullable), `sampling_purpose` (text, not null, description of what is being tested), `population_description` (text, not null), `population_total_amount` (numeric(20,2), nullable), `population_total_count` (integer, nullable), `sample_size` (integer, not null), `sampling_method_description` (text, description of method used), `deviations_found` (integer, nullable, for control tests), `misstatements_found` (numeric(20,2), nullable, for substantive tests), `projected_misstatement` (numeric(20,2), nullable, extrapolated to population), `upper_misstatement_limit` (numeric(20,2), nullable, for MUS), `conclusion` (text, nullable, auditor's conclusion), `is_deleted` (boolean, default false), `created_at`, `updated_at`, `created_by` (UUID FK to users); with composite index on (project_id, working_paper_id)
4. WHEN Auditor records sampling results for MUS, THE Platform SHALL automatically calculate the projected_misstatement (extrapolation from sample to population) and upper_misstatement_limit using the MUS evaluation formula based on the tainting factors of identified misstatements
5. THE Platform SHALL validate sampling record completeness: before a working paper involving sampling can pass QC check (Rule 10 in Phase 1b QC Engine), the associated sampling_records must have non-empty values for: sampling_purpose, population_description, sample_size, and conclusion
6. THE Platform SHALL link sampling records to working papers via working_paper_id, so that the QC Engine can verify sampling completeness for each working paper that involves sampling procedures

### 需求 12：抽样相关数据表Schema定义

**用户故事：** 作为开发者，我希望抽样相关数据表的Schema明确定义，以便通过Alembic迁移脚本创建表结构。

#### 验收标准

1. THE Migration_Framework SHALL create the `sampling_config` table with columns as defined in Requirement 11.1, with composite index on (project_id, sampling_method)
2. THE Migration_Framework SHALL create the `sampling_records` table with columns as defined in Requirement 11.3, with composite index on (project_id, working_paper_id)
