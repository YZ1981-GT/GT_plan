# Requirements Document

## Introduction

将现有科目级审计复核提示词（69个 .md 文件，存储在 `backend/data/tsj_review_prompts/`）拆分为底稿级（sheet-level）提示词，使得每个科目的每张底稿（审定表/明细表/坏账准备/分析表/凭证检查/政策检查/附注等）都有专属的复核提示词。试点范围为 D2 应收账款（约8张底稿），试点通过后推广到全科目。

现有 `review_workpaper_with_prompt` 方法在 `workpaper_fill_service.py` 已实现但未接 HTTP router（孤儿能力），本需求将其激活并升级为按 wp_code + sheet_name 精确匹配加载底稿级提示词，同时新增批量复核端点和前端复核结果展示面板。

## Glossary

- **Sheet_Level_Prompt**: 底稿级复核提示词，针对特定底稿类型（如审定表/明细表/坏账准备等）的专属审计复核指引 Markdown 文件
- **Review_Prompt_Service**: 底稿级提示词加载服务，负责按 wp_code + sheet_suffix 匹配加载对应提示词文件
- **Batch_Review_Service**: 批量复核服务，对一个科目的所有底稿逐份调用 LLM 复核并汇总结果
- **Review_Finding**: 单条复核发现，包含问题描述、风险等级、是否通过、涉及底稿定位
- **Review_Result**: 单张底稿的复核结果，包含多条 Review_Finding 及通过/未通过总体结论
- **Batch_Review_Report**: 科目级批量复核报告，包含该科目下所有底稿的 Review_Result 集合
- **Review_Panel**: 前端复核结果展示面板组件，展示每张底稿的复核发现清单、风险等级、是否通过、未处理项数
- **Sheet_Suffix**: 底稿编号后缀（如 D2-1/D2-2/D2-3 等），用于匹配提示词文件
- **LLM_Service**: 大语言模型服务（vLLM Qwen3.5-27B），通过 chat_completion 接口调用

## Requirements

### Requirement 1: 底稿级提示词文件拆分与存储

**User Story:** As a 现场经理, I want 应收账款审计复核提示词按底稿拆分为独立文件, so that 每张底稿的复核聚焦于该底稿特有的审计要点而非整个科目。

#### Acceptance Criteria

1. WHEN the Review_Prompt_Service initializes, THE Review_Prompt_Service SHALL load sheet-level prompt files from the directory `backend/data/tsj_review_prompts/D/` with naming pattern `{wp_code}-{sheet_suffix}.md`
2. THE Review_Prompt_Service SHALL provide D2 pilot prompts for at least 8 sheets: D2-1(审定表), D2-2(明细表), D2-3(坏账准备), D2-5(分析表), D2-7(凭证检查), D2-8(政策检查), D2-note-listed(附注上市), D2-note-soe(附注国企)
3. WHEN a sheet-level prompt file is loaded, THE Review_Prompt_Service SHALL parse it into structured sections: tips, checklist, and risk_areas using the existing TsjPromptService parsing logic
4. IF a sheet-level prompt file does not exist for a requested wp_code + sheet_suffix combination, THEN THE Review_Prompt_Service SHALL fall back to the existing subject-level prompt file (e.g., `应收账款审计复核提示词.md`)

### Requirement 2: 提示词匹配加载机制

**User Story:** As a 业务合伙人, I want the system to automatically match the correct review prompt based on workpaper code and sheet name, so that each review focuses on the specific audit procedures relevant to that sheet.

#### Acceptance Criteria

1. WHEN a review request is received with wp_code and sheet_name parameters, THE Review_Prompt_Service SHALL resolve the sheet_suffix from the sheet_name using pattern matching (e.g., "审定表D2-1" → "D2-1", "明细表D2-2" → "D2-2")
2. WHEN the sheet_suffix is resolved, THE Review_Prompt_Service SHALL look up the file at path `backend/data/tsj_review_prompts/{cycle_letter}/{wp_code}-{sheet_suffix}.md` where cycle_letter is derived from the wp_code first character
3. THE Review_Prompt_Service SHALL support the existing `_audit_cycle_aliases` keyword matching as a secondary resolution strategy when wp_code-based lookup fails
4. WHEN multiple prompt files could match a single sheet, THE Review_Prompt_Service SHALL select the most specific match (sheet-level over subject-level)

### Requirement 3: 单底稿复核 HTTP 端点接线

**User Story:** As a 现场经理, I want to trigger AI review for a single workpaper sheet through an HTTP API, so that I can review individual sheets on demand from the workbench.

#### Acceptance Criteria

1. WHEN a POST request is sent to `/api/workpapers/{wp_id}/review` with optional body `{sheet_name: string}`, THE HTTP_Router SHALL invoke review_workpaper_with_prompt with the matched sheet-level prompt
2. WHEN the sheet_name parameter is provided, THE HTTP_Router SHALL pass it to the Review_Prompt_Service for sheet-level prompt matching
3. IF the sheet_name parameter is omitted, THEN THE HTTP_Router SHALL use the subject-level prompt as before (backward compatible)
4. THE HTTP_Router SHALL return a structured response containing: findings (list of Review_Finding), overall_pass (boolean), risk_summary (count by level), and sheet_info (wp_code, sheet_name)

### Requirement 4: 批量复核端点

**User Story:** As a 业务合伙人, I want to trigger batch review for all sheets in a subject (e.g., D2 应收账款) with a single API call, so that I can get a comprehensive review report for the entire account cycle.

#### Acceptance Criteria

1. WHEN a POST request is sent to `/api/projects/{project_id}/batch-review` with body `{wp_code_prefix: "D2", year: number}`, THE Batch_Review_Service SHALL identify all sheet-level workpapers under that prefix for the specified project
2. THE Batch_Review_Service SHALL sequentially invoke LLM review for each identified sheet, using the matched sheet-level prompt for each
3. WHEN all sheet reviews complete, THE Batch_Review_Service SHALL return a Batch_Review_Report containing: per-sheet results (list of Review_Result), overall statistics (total sheets, passed count, failed count, total findings by risk level), and execution metadata (start_time, end_time, model_used)
4. IF a single sheet review fails (LLM timeout or error), THEN THE Batch_Review_Service SHALL mark that sheet as "review_error" and continue processing remaining sheets without aborting the batch

### Requirement 5: 复核结果数据持久化

**User Story:** As a QC合伙人, I want review results to be persisted so that I can access them later without re-running the review.

#### Acceptance Criteria

1. WHEN a review (single or batch) completes successfully, THE Review_Prompt_Service SHALL persist each Review_Finding to the `ai_content` table with content_type="review_finding" and structured data_sources containing sheet_name, risk_level, pass_status, and finding_category
2. THE Review_Prompt_Service SHALL store the batch review summary in a new `review_batch_results` item within checklist_responses (item_id pattern: `{wp_code}-batch-review-{timestamp}`)
3. WHEN a subsequent review is triggered for the same sheet, THE Review_Prompt_Service SHALL create a new version of findings (append-only, never overwrite previous results)
4. THE Review_Prompt_Service SHALL associate each finding with the project_id, workpaper_id, and a review_session_id for traceability

### Requirement 6: 前端复核结果展示面板

**User Story:** As a 现场经理, I want a visual panel showing review results for each sheet in a subject, so that I can quickly identify which sheets have issues and what those issues are.

#### Acceptance Criteria

1. WHEN the Review_Panel component is rendered with a wp_code_prefix, THE Review_Panel SHALL display a card for each sheet showing: sheet name, pass/fail badge, finding count, risk level distribution (high/medium/low counts), and unresolved item count
2. WHEN a user clicks on a sheet card, THE Review_Panel SHALL expand to show the full list of Review_Finding items with: description, risk level tag (color-coded: red=high, orange=medium, gray=low), category, and referenced workpaper location
3. WHILE a batch review is in progress, THE Review_Panel SHALL show a progress indicator with the current sheet being reviewed and completion percentage
4. THE Review_Panel SHALL provide a "开始批量复核" button (visible to 现场经理/业务合伙人/QC合伙人 roles) that triggers the batch review API

### Requirement 7: 复核结果导出为 Excel

**User Story:** As a 业务合伙人, I want to export the batch review results as an Excel file, so that I can share them with team members and include them in the audit file.

#### Acceptance Criteria

1. WHEN a user clicks the export button on the Review_Panel, THE Export_Service SHALL generate an Excel workbook with one worksheet per reviewed sheet
2. THE Export_Service SHALL format each worksheet with columns: 序号, 检查项, 风险等级, 是否通过, 问题描述, 涉及底稿定位, 整改建议, 负责人, 状态
3. THE Export_Service SHALL include a summary worksheet as the first sheet containing: 科目名称, 复核日期, 复核人, 各底稿通过/未通过统计, 风险分布汇总
4. THE Export_Service SHALL use RFC5987 encoding for the Chinese filename in the Content-Disposition header (e.g., `D2应收账款复核报告_2026-07-20.xlsx`)

### Requirement 8: LLM 复核结果结构化解析

**User Story:** As a 现场经理, I want LLM review output to be parsed into structured findings, so that the system can compute pass/fail status and risk statistics automatically.

#### Acceptance Criteria

1. WHEN the LLM returns a review response, THE Review_Prompt_Service SHALL parse the raw text into individual Review_Finding objects by identifying checklist items marked as problematic (not `[ ] 已确认合规`)
2. THE Review_Prompt_Service SHALL extract risk_level from finding context: items under "高风险" sections map to "high", "中风险" to "medium", "低风险" to "low"
3. THE Review_Prompt_Service SHALL determine overall pass_status for a sheet: "pass" if zero high-risk findings and fewer than 3 medium-risk findings, otherwise "fail"
4. IF the LLM output cannot be parsed into structured findings (malformed response), THEN THE Review_Prompt_Service SHALL store the raw text as a single finding with risk_level="unknown" and pass_status="manual_review_required"

### Requirement 9: 提示词拆分内容质量要求

**User Story:** As a QC合伙人, I want each sheet-level prompt to be focused and actionable for that specific sheet type, so that LLM reviews produce relevant and precise findings.

#### Acceptance Criteria

1. THE D2-1(审定表) sheet-level prompt SHALL focus on: 期初期末勾稽、试算平衡表核对、审计调整完整性、分类列报准确性
2. THE D2-2(明细表) sheet-level prompt SHALL focus on: 客户信息完整性、余额准确性、账龄分析正确性、前五大客户集中度分析
3. THE D2-3(坏账准备) sheet-level prompt SHALL focus on: ECL模型参数合理性、迁徙率计算准确性、单项减值判断充分性、计提比例与政策一致性
4. THE D2-7(凭证检查) sheet-level prompt SHALL focus on: 样本选取方法合理性、凭证核对完整性、检查比例达标性、异常交易标注充分性
5. THE D2-5(分析表) sheet-level prompt SHALL focus on: 变动分析合理性、周转率计算准确性、异常波动解释充分性、前后期对比逻辑性

### Requirement 10: 试点推广机制

**User Story:** As a 业务合伙人, I want a clear mechanism to extend sheet-level prompts from D2 pilot to all 69 subjects, so that the system can progressively cover all audit cycles.

#### Acceptance Criteria

1. THE Review_Prompt_Service SHALL support a directory structure `backend/data/tsj_review_prompts/{cycle_letter}/` where cycle_letter is D, E, F, G, H, I, J, K, L, M, N, S for organizing sheet-level prompts by cycle
2. WHEN a new subject's sheet-level prompts are added to the directory, THE Review_Prompt_Service SHALL automatically discover and load them without code changes (file-system driven)
3. THE Review_Prompt_Service SHALL provide a `GET /api/review-prompts/coverage` endpoint returning: total subjects (69), subjects with sheet-level prompts, sheets per subject breakdown, and missing prompt gaps
4. IF a cycle directory does not exist or is empty for a requested subject, THEN THE Review_Prompt_Service SHALL seamlessly fall back to the subject-level prompt file in the root `tsj_review_prompts/` directory

