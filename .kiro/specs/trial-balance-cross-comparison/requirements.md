# Requirements Document

## Introduction

试算表多项目/多年度对比（Trial Balance Cross Comparison）——合并审计场景同屏对比母子公司同科目金额，或同项目跨年度审定数同比分析。解决"合并审计需逐户核对科目差异"+"续审项目分析年度间异常波动"两大审计痛点。

## Requirements

### Requirement 1: Cross-Year Comparison (Same Project)

When the user selects "跨年度对比" mode for the current project,
the system shall:
- Load prior year(s) trial balance data (audited_amount) alongside current year
- Display comparison columns: 本年审定 / 上年审定 / 变动额 / 变动率
- Highlight rows where |变动率| > 30% (orange) or > 50% (red)
- Support selecting comparison year from available years dropdown

### Requirement 2: Cross-Project Comparison (Group Audit)

When the user selects "跨项目对比" mode (合并审计场景),
the system shall:
- Allow selecting 1-5 subsidiary projects from current group scope
- Load each project's trial balance for the same year
- Display side-by-side columns: 科目 / 母公司审定 / 子公司A审定 / 子公司B审定 / ... / 合计
- Auto-sum subsidiaries into "合计" column for quick reconciliation against consolidated trial balance

### Requirement 3: Variance Analysis

The comparison view shall provide:
- Sortable by variance amount/rate (find largest discrepancies first)
- Filter: only show rows with |variance| > threshold (configurable, default PM)
- Export comparison report as xlsx with conditional formatting (variance>30% highlighted)

### Requirement 4: Data Source

The system shall:
- For cross-year: query `trial_balance` with different `year` parameter for same project
- For cross-project: query `trial_balance` for each selected project_id with same year
- Match rows by `standard_account_code` (consistent after account_mapping normalization)
- Handle missing accounts gracefully: show in "仅本方/仅对方" section

### Requirement 5: UI Layout

The comparison view shall:
- Be accessible from trial balance toolbar as a toggle mode ("📊 对比" button)
- Display in the same page area (replace main table when active, back button to return)
- Support responsive column widths when comparing multiple projects
- Limit to 5 comparison targets to prevent performance degradation

### Requirement 6: Performance

The system shall:
- Load comparison data asynchronously (loading state per comparison target)
- Cache loaded comparison data for the session (avoid re-fetch on toggle)
- Total query time for 5 projects × 200 rows each SHALL < 5 seconds

### Requirement 7: Permissions

The system shall:
- Cross-year: same permission as viewing current trial balance (readonly+)
- Cross-project: require access to each compared project (check per-project permission)
- Projects the user cannot access SHALL NOT appear in the selector

### Requirement 8: Zero Regression

The system shall:
- Not alter the default trial balance view behavior
- Comparison mode is opt-in (toggle button, default off)
- All existing trial balance operations (recalc/save/export/freeze) remain unchanged

## Glossary

- **Cross-Year**: Comparing same project's trial balance across different fiscal years
- **Cross-Project**: Comparing multiple projects' trial balances for the same year (group audit)
- **Variance**: Difference between compared values (amount or percentage)
- **Group Scope**: Set of related projects (parent + subsidiaries) in a consolidated audit engagement
