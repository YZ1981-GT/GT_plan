# Requirements Document

## 变更记录

| 版本 | 日期 | 摘要 | 触发原因 |
|------|------|------|----------|
| v1.0 | 2026-05-17 | 初始版本 | 底稿模板内容预设基础设施立项 |

## 依赖矩阵

| 上游 Spec | 关键产出 | Fallback 策略 |
|-----------|----------|---------------|
| workpaper-deep-optimization | prefill_formula_mapping.json / wp_template_metadata / WorkpaperEditor 三级降级 | 本 spec 消费已就绪产出，无需等待 |
| template-library-coordination | 模板库管理页面 / JSON 只读源 ADR | 本 spec 独立于管理页面，仅消费 seed 数据 |
| audit-chain-generation | chain_orchestrator / init_workpaper_from_template | 底稿生成链路已完成，本 spec 在其基础上增强 |

## Introduction

本 spec 为"底稿模板内容预设"工程的基础设施层。当前底稿模板虽已能在 Univer 编辑器中加载并显示 Excel 原始内容（通过 GET /xlsx-to-json 端点），但审计师打开底稿后缺乏以下关键体验：

1. **无法区分"系统预填"与"手动输入"**——所有单元格看起来一样，审计师不知道哪些数据来自 TB/AJE/上年
2. **一键填充仅在 WorkpaperWorkbench 可用**——进入 WorkpaperEditor 后无法触发单底稿预填充
3. **跨模块关联不可见**——底稿中的数据流向附注/报表的关系无法直观感知
4. **复核标记缺失**——无法在单元格级别标记"已复核"/"待确认"
5. **循环级进度不可见**——底稿树中看不到每个循环的复核完成度
6. **E2E 测试缺失**——无自动化回归保障
7. **刷新取数可能覆盖手动编辑**——用户手动修改的单元格被"刷新取数"覆盖

本 spec 聚焦上述 7 个基础设施能力，为后续各循环（D/E/F/G...）的具体内容预设提供通用机制。

## Glossary

- **Prefill_Engine**: 后端预填充引擎，读取 prefill_formula_mapping.json 执行 TB/ADJ/PREV/WP 取数并写入 xlsx 单元格
- **WorkpaperEditor**: 前端 Univer 底稿编辑器组件（views/WorkpaperEditor.vue）
- **WorkpaperWorkbench**: 底稿工作台组件（views/WorkpaperWorkbench.vue），展示 TB 数据卡片和底稿列表
- **Cell_Annotation**: 单元格级批注/标记，存储在 cell_annotations 表
- **Prefill_Source**: 预填充数据来源类型（TB/AJE/RJE/PREV/WP/MANUAL）
- **User_Override**: 用户手动编辑覆盖预填充值的标记，防止刷新取数覆盖
- **Cross_Module_Reference**: 跨模块引用标签，标识单元格数据流向附注/报表的关系
- **Review_Mark**: 复核标记，审计师/复核人在单元格级别标注"已复核"状态
- **Cycle_Node**: 底稿树中的循环节点（如 D 收入循环 / E 货币资金循环）

## Requirements

### Requirement 0: 底稿模板完整加载保障

**User Story:** As a 审计师, I want 打开任何底稿时 Univer 编辑器完整显示模板的全部内容（所有 sheet / 表头 / 固定文字 / 合并单元格 / 边框 / 底色 / 冻结窗格）, so that 我看到的是致同标准模板的完整结构而非空白电子表格。

#### Acceptance Criteria

1. WHEN the user opens a workpaper in WorkpaperEditor, THE Univer editor SHALL display ALL sheets from the template xlsx file (e.g. D2 has 20 sheets, all 20 must appear as tabs)
2. WHEN the template xlsx contains merged cells, THE Univer editor SHALL render them as merged (not split into individual cells)
3. WHEN the template xlsx contains frozen panes, THE Univer editor SHALL apply the same freeze position
4. WHEN the template xlsx contains cell formatting (bold/italic/font-size/background-color/borders/number-format), THE Univer editor SHALL preserve and render all formatting
5. WHEN the template xlsx contains fixed text content (e.g. "审计程序：1. 获取明细表..."), THE Univer editor SHALL display that text exactly as in the original template
6. THE GET /xlsx-to-json endpoint SHALL return a complete IWorkbookData JSON containing all sheets, all cellData (values + styles + formulas), mergeData, columnData, rowData, and freeze settings
7. THE WorkpaperEditor frontend SHALL successfully call GET /xlsx-to-json and pass the returned JSON to `univerAPI.createWorkbook()` without falling through to the empty workbook fallback
8. WHEN the xlsx-to-json conversion encounters an error, THE WorkpaperEditor SHALL display an error message (not silently show empty workbook)

### Requirement 1: 预填充视觉指示器

**User Story:** As a 审计师, I want 打开底稿时能一眼区分"系统自动填充的数据"和"空白待填写的单元格", so that 我知道哪些数据已由系统从 TB/AJE/上年取数完成，无需重复手工录入。

#### Acceptance Criteria

1. WHEN a cell's value originates from Prefill_Engine, THE WorkpaperEditor SHALL display a light-blue background color using CSS token `--gt-marker-prefill-bg` on that cell
2. WHEN the user hovers over a prefilled cell, THE WorkpaperEditor SHALL show a tooltip containing the source type (TB/AJE/PREV/WP) and the formula expression (e.g. "=TB('1122','期末余额')")
3. THE WorkpaperEditor SHALL distinguish at least 4 source types visually: TB (蓝), AJE (绿), PREV (紫), WP (青)
4. WHEN a prefilled cell is selected, THE WorkpaperEditor SHALL display the source formula in the formula bar area
5. WHEN the workpaper is opened for the first time after prefill, THE WorkpaperEditor SHALL render all prefilled cells with visual markers within 500ms of sheet load completion
6. IF the Prefill_Engine returns an error for a specific cell, THEN THE WorkpaperEditor SHALL display a red border on that cell with tooltip "取数失败: {error_message}"

### Requirement 2: 一键填充按钮（编辑器内）

**User Story:** As a 审计师, I want 在底稿编辑器内点击"一键填充"按钮触发当前底稿的预填充, so that 我不需要退回工作台就能刷新取数。

#### Acceptance Criteria

1. THE WorkpaperEditor SHALL display a "📊 一键填充" button in the toolbar area
2. WHEN the user clicks "📊 一键填充", THE WorkpaperEditor SHALL call the prefill API for the current wp_code only
3. WHEN prefill is in progress, THE WorkpaperEditor SHALL show a loading state on the button and disable repeated clicks
4. WHEN prefill completes successfully, THE WorkpaperEditor SHALL reload the workbook data and apply visual markers to all newly filled cells
5. WHEN prefill completes, THE WorkpaperEditor SHALL display a toast summary showing "已填充 N 个单元格（TB: X, AJE: Y, PREV: Z）"
6. IF the current workpaper has no prefill mapping configured, THEN THE WorkpaperEditor SHALL show a disabled button with tooltip "当前底稿无预设公式配置"

### Requirement 3: 跨模块跳转标签

**User Story:** As a 审计师, I want 在底稿单元格上看到"→ 附注 5.7"或"→ 报表 BS-005"标签, so that 我能快速了解该数据流向哪些下游模块，并一键跳转查看。

#### Acceptance Criteria

1. WHEN a cell has cross-module references defined in cross_wp_references.json, THE WorkpaperEditor SHALL display a small tag (e.g. "→ 附注 5.7") adjacent to the cell
2. WHEN the user clicks a cross-module tag, THE WorkpaperEditor SHALL navigate to the target module view (附注编辑器 / 报表视图) with the relevant section highlighted
3. THE WorkpaperEditor SHALL support at least 3 reference target types: 附注章节 (note_section), 报表行次 (report_row), 其他底稿 (workpaper)
4. WHEN a cell has multiple cross-module references, THE WorkpaperEditor SHALL display them as a stacked badge with count, expandable on click
5. THE Cross_Module_Reference tags SHALL use distinct colors per target type: 附注=紫色, 报表=蓝色, 底稿=青色
6. WHEN the target module does not exist or is inaccessible, THE WorkpaperEditor SHALL show the tag in grey with tooltip "目标不可用"

### Requirement 4: 单元格级复核标记

**User Story:** As a 复核人, I want 右键点击单元格选择"标记复核"添加复核批注, so that 我能逐单元格记录复核意见，编制人能看到哪些单元格需要关注。

#### Acceptance Criteria

1. WHEN the user right-clicks a cell, THE WorkpaperEditor SHALL show a context menu item "✓ 标记复核"
2. WHEN "标记复核" is selected, THE WorkpaperEditor SHALL prompt for an optional comment and save a Review_Mark to the backend
3. WHEN a cell has a Review_Mark, THE WorkpaperEditor SHALL display a small green checkmark indicator on the cell corner
4. WHEN the user hovers over a reviewed cell indicator, THE WorkpaperEditor SHALL show the reviewer name, timestamp, and comment in a popover
5. THE WorkpaperEditor side panel SHALL include a "复核标记" tab listing all marked cells with their status (已复核/待确认/有疑问)
6. WHEN a reviewer marks a cell as "有疑问", THE WorkpaperEditor SHALL display an orange indicator instead of green, and the comment SHALL be visible to the preparer
7. THE Cell_Annotation backend SHALL store review marks with fields: wp_id, sheet_name, cell_ref, reviewer_id, status, comment, created_at

### Requirement 5: 循环级复核状态徽章

**User Story:** As a 项目经理, I want 在底稿树的每个循环节点上看到复核完成度徽章 (如 "3/8 已复核"), so that 我能快速掌握各循环的复核进度。

#### Acceptance Criteria

1. THE WorkpaperWorkbench tree SHALL display a completion badge on each Cycle_Node showing "{reviewed_count}/{total_count} 已复核"
2. WHEN all workpapers in a cycle are reviewed, THE Cycle_Node badge SHALL turn green with "✓ 全部完成"
3. WHEN no workpapers in a cycle are reviewed, THE Cycle_Node badge SHALL display in grey "0/{total} 待复核"
4. WHEN the review status of any workpaper changes, THE WorkpaperWorkbench tree SHALL update the badge within 3 seconds (via eventBus subscription)
5. THE review status of a workpaper SHALL be determined by: all required cells have Review_Mark with status "已复核"
6. THE Cycle_Node badge SHALL be clickable, expanding to show per-workpaper review status list

### Requirement 6: Playwright E2E 测试框架

**User Story:** As a 开发者, I want 建立 Playwright E2E 测试框架并编写 4 个基线测试用例, so that 底稿预填充功能有自动化回归保障。

#### Acceptance Criteria

1. THE project SHALL have a playwright.config.ts configured for the audit-platform frontend with baseURL pointing to localhost:3030
2. THE E2E test suite SHALL include a test verifying: login → navigate to workpaper → verify prefilled cells have visual markers
3. THE E2E test suite SHALL include a test verifying: click "一键填充" → verify cell values update → verify toast summary appears
4. THE E2E test suite SHALL include a test verifying: right-click cell → "标记复核" → verify green indicator appears
5. THE E2E test suite SHALL include a test verifying: navigate to WorkpaperWorkbench → verify cycle badge shows correct count
6. THE E2E tests SHALL use real project data (陕西华氏 project, wp_code D2) seeded in the test database
7. THE E2E tests SHALL be runnable via `npx playwright test` and complete within 60 seconds total

### Requirement 7: 预填充覆盖保护

**User Story:** As a 审计师, I want 手动编辑过的单元格在"刷新取数"时不被覆盖, so that 我的手工调整不会因为系统刷新而丢失。

#### Acceptance Criteria

1. WHEN the user manually edits a prefilled cell, THE WorkpaperEditor SHALL mark that cell as User_Override
2. WHEN "刷新取数" is triggered, THE Prefill_Engine SHALL skip all cells marked as User_Override
3. WHEN a User_Override cell exists, THE WorkpaperEditor SHALL display a small pencil icon (✏️) on the cell corner indicating manual override
4. WHEN the user hovers over a User_Override indicator, THE WorkpaperEditor SHALL show tooltip "已手动修改，刷新取数时将跳过此单元格"
5. THE WorkpaperEditor SHALL provide a right-click menu option "恢复预填充" to remove the User_Override mark and re-fetch the original prefill value
6. WHEN "刷新取数" completes, THE WorkpaperEditor SHALL display a summary: "已刷新 N 个单元格，跳过 M 个手动修改的单元格"
7. THE User_Override marks SHALL be persisted in the workpaper's parsed_data JSONB field (key: "user_overrides") so they survive save/reload cycles
