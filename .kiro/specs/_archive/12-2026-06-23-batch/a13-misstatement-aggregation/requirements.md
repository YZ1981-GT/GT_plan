# Requirements Document

## Introduction

A13 错报评价是审计意见形成的核心底稿，当前为 6-tab 套件（GtMisstatementWorkpaper.vue）。A13-1 汇总 tab 目前由 MisstatementSummaryView 手动展示从 `UnadjustedMisstatement` 表聚合的数据，但缺少以下关键能力：

1. A13-2~5 保存后自动触发 A13-1 汇总重算（EventBus 联动）
2. 累计未更正错报与重要性水平（PM/TE/SAT from B15）的实时比较和三色预警
3. 上年结转错报的本年状态追踪（转回/延续/新增）
4. A13-5 沟通 tab 一键生成管理层沟通函草稿
5. 错报条目与源底稿（D~N 循环）的 ref_chip 跳转

本功能将补齐 A13 自动聚合链路，使错报评价从手动汇总升级为事件驱动的实时聚合，直接服务于审计意见形成判断。

## Glossary

- **Aggregation_Resolver**: 新增的 `@auto_resolver("a13_misstatement_summary")` 函数，从 A13-2~5 sheet 数据和 UnadjustedMisstatement 表聚合计算汇总指标
- **Materiality_Indicator**: A13-1 汇总页顶部的三色指示器（绿/黄/红），基于累计未更正错报与 PM 的比值
- **PM**: 整体重要性水平（Overall Materiality），由 B15 底稿确定
- **TE**: 实际执行重要性（Performance Materiality = PM × 75%）
- **SAT**: 明显微小临界值（Clearly Trivial Threshold = PM × 5%），低于此金额不汇总
- **Prior_Year_Status**: 上年结转错报的本年跟踪状态枚举：reversed（已转回）、continuing（延续）、new（本年新增，非结转）
- **Communication_Draft**: A13-5 沟通 tab 自动生成的管理层沟通函草稿文本
- **Source_Ref_Chip**: 错报条目中显示源底稿 wp_code 的可点击标签，通过 cross_wp_references 实现跳转
- **EventPayload**: EventBus 发布事件的标准载体对象，包含 event_type/project_id/year/wp_code 等字段
- **Sheet_Data**: A13-2~5 各 tab 保存在 `parsed_data.html_data[tabId]` 中的 d-form-table 行数据

## Requirements

### Requirement 1: A13-1 汇总自动聚合

**User Story:** As a 审计助理, I want A13-1 汇总在 A13-2~5 任一 tab 保存后自动重算, so that 无需手动填写汇总数据且汇总始终与明细一致。

#### Acceptance Criteria

1. WHEN A13-2 (错报明细) sheet 保存成功, THE Aggregation_Resolver SHALL recalculate the A13-1 summary data within 3 seconds.
2. WHEN A13-3 (合计) sheet 保存成功, THE Aggregation_Resolver SHALL recalculate the A13-1 summary data within 3 seconds.
3. WHEN A13-4 (舞弊) sheet 保存成功, THE Aggregation_Resolver SHALL recalculate the A13-1 summary data within 3 seconds.
4. WHEN A13-5 (沟通) sheet 保存成功, THE Aggregation_Resolver SHALL recalculate the A13-1 summary data within 3 seconds.
5. THE Aggregation_Resolver SHALL compute the following summary fields: total misstatement count, total misstatement amount, count and amount grouped by misstatement_type (factual/judgmental/projected), count of fraud-related misstatements, and net effect on financial statements.
6. THE Aggregation_Resolver SHALL persist the computed summary to `parsed_data.html_data['summary']` of the A13 workpaper.
7. WHEN A13-1 summary tab is opened, THE MisstatementSummaryView SHALL display the latest persisted aggregation result without requiring manual refresh.
8. IF the Aggregation_Resolver encounters an error during recalculation, THEN THE system SHALL log the error and retain the previous summary data unchanged.

### Requirement 2: EventBus 触发重算机制

**User Story:** As a 现场经理, I want A13 各子 tab 保存后通过 EventBus 自动触发汇总联动, so that 跨 tab 数据一致性由系统保证而非依赖人工操作。

#### Acceptance Criteria

1. WHEN the GtMisstatementWorkpaper saves any of A13-2/A13-3/A13-4/A13-5, THE system SHALL publish an EventPayload with event_type=WORKPAPER_SAVED and wp_code containing the sheet identifier.
2. THE system SHALL subscribe an event handler to EventType.WORKPAPER_SAVED that filters for wp_code matching A13-related sheets.
3. WHEN the event handler receives a matching WORKPAPER_SAVED event, THE Aggregation_Resolver SHALL execute asynchronously without blocking the save response.
4. WHEN multiple A13 sub-tabs are saved in rapid succession (within 2 seconds), THE system SHALL debounce recalculation to execute only once after the last save.
5. WHEN the recalculation completes, THE system SHALL broadcast an SSE event to connected clients so that the A13-1 tab auto-refreshes if currently open.
6. THE event handler SHALL pass project_id and year from the EventPayload to the Aggregation_Resolver for scoped computation.

### Requirement 3: 重要性水平比较预警

**User Story:** As a 业务合伙人, I want to see a clear visual indicator comparing cumulative uncorrected misstatements against materiality thresholds, so that I can immediately assess whether the financial statements may be materially misstated.

#### Acceptance Criteria

1. THE Materiality_Indicator SHALL display three states: green (cumulative < SAT), yellow (SAT ≤ cumulative < PM), red (cumulative ≥ PM).
2. WHEN the Aggregation_Resolver completes recalculation, THE Materiality_Indicator SHALL update to reflect the new cumulative amount versus current PM from B15.
3. THE Materiality_Indicator SHALL display the numeric values: cumulative uncorrected amount, PM value, and the ratio (cumulative / PM) as a percentage.
4. WHEN PM has not been determined in B15 (value is null or zero), THE Materiality_Indicator SHALL display a warning state indicating "重要性水平未确定" and link to B15.
5. WHEN cumulative uncorrected misstatements transition from below PM to at-or-above PM, THE system SHALL emit an el-notification warning to the current user.
6. THE Materiality_Indicator SHALL be rendered at the top of the A13-1 summary view as an el-alert component with appropriate type (success/warning/error).
7. WHEN fraud-related misstatements exist (any count > 0 in A13-4), THE Materiality_Indicator SHALL display an additional red badge regardless of amount, per CAS 1141.35.

### Requirement 4: 上年结转错报状态追踪

**User Story:** As a 现场经理, I want to track whether prior year uncorrected misstatements have reversed or continue in the current year, so that I can properly evaluate their cumulative effect per CAS 1251.

#### Acceptance Criteria

1. THE system SHALL assign a Prior_Year_Status to each misstatement record: "new" for current year originations, "continuing" for carried-forward items still uncorrected, and "reversed" for carried-forward items that reversed in current year.
2. WHEN carry_forward executes, THE system SHALL set Prior_Year_Status to "continuing" for all newly created carried-forward records.
3. WHEN a user marks a carried-forward misstatement as "reversed", THE system SHALL update its Prior_Year_Status to "reversed" and exclude it from the cumulative uncorrected total.
4. THE A13-1 summary SHALL separately display: prior year continuing amount, prior year reversed amount, current year new amount, and net cumulative total (continuing + new).
5. THE Aggregation_Resolver SHALL include Prior_Year_Status breakdown in its computed summary output.
6. WHEN PM changes in the current year (B15 update), THE system SHALL re-evaluate all carried-forward misstatements against the new PM threshold.
7. THE A13-2 错报明细 tab SHALL display a visible tag (el-tag) indicating each row's Prior_Year_Status with color coding: blue for "new", orange for "continuing", gray for "reversed".

### Requirement 5: A13-5 沟通函草稿自动生成

**User Story:** As a 现场经理, I want to one-click generate a communication draft listing all uncorrected misstatements for management, so that the communication letter preparation time is reduced and no misstatement is accidentally omitted.

#### Acceptance Criteria

1. WHEN the user clicks "生成沟通函草稿" button in A13-5 tab, THE system SHALL generate a Communication_Draft containing all uncorrected misstatements with status "continuing" or "new".
2. THE Communication_Draft SHALL include for each misstatement: sequence number, description, affected account, amount, misstatement_type classification, and management's stated reason for not correcting.
3. THE Communication_Draft SHALL include a summary section stating: total count of uncorrected misstatements, cumulative amount, comparison to PM, and the auditor's overall evaluation conclusion.
4. THE Communication_Draft SHALL be formatted as structured text that can be copied into A10-1 (治理层沟通函) or exported as a standalone document.
5. IF no uncorrected misstatements exist, THEN THE system SHALL display a message "当前无未更正错报，无需生成沟通函" and disable the generation button.
6. THE Communication_Draft SHALL use the conclusion template from A13 guidance: template A (below PM), B (approaching PM), or C (exceeds PM) based on the current evaluation result.
7. WHEN the Communication_Draft is generated, THE system SHALL persist it to the A13-5 sheet data so it remains available on next open without regeneration.

### Requirement 6: 错报来源 ref_chip 跳转

**User Story:** As a 审计助理, I want each misstatement entry to show a clickable chip linking to its source workpaper, so that I can quickly navigate to the original finding for context.

#### Acceptance Criteria

1. WHEN a misstatement has a non-null source_adjustment_id or a recorded source_wp_code, THE system SHALL display a Source_Ref_Chip showing the source workpaper code (e.g., "D2-1", "F3A", "K1-1").
2. WHEN the user clicks a Source_Ref_Chip, THE system SHALL navigate to the source workpaper using the existing cross_wp_references routing mechanism.
3. THE Source_Ref_Chip SHALL be rendered as an el-tag with type="info" and a link icon, consistent with existing ref_index chip styling in the platform.
4. WHEN a misstatement is created from a rejected AJE (via create_from_rejected_aje), THE system SHALL automatically populate the source_wp_code from the adjustment's originating workpaper.
5. WHEN a misstatement is manually created without source reference, THE Source_Ref_Chip SHALL not be displayed for that row.
6. THE A13-2 错报明细 tab SHALL include a "来源底稿" column displaying the Source_Ref_Chip for each row.
7. THE system SHALL register cross_wp_references entries linking A13 to source workpapers (D~N cycles) to enable bidirectional navigation.
