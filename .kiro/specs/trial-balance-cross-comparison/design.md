# Design Document

## Architecture

纯前端对比视图 + 后端已有 `GET /trial-balance?year=` 复用（零新后端端点）。

### Cross-Year 数据流

```
用户选"跨年度对比" → 选对比年度(2024)
→ GET /api/projects/{pid}/trial-balance?year=2024 (复用已有端点)
→ 前端按 standard_account_code join 当前年行
→ 渲染对比表
```

### Cross-Project 数据流

```
用户选"跨项目对比" → 选子公司项目(最多5)
→ 并发 GET /api/projects/{子pid}/trial-balance?year={year} (每个项目独立请求)
→ 前端按 standard_account_code union-join 全部行
→ 渲染对比表(母+子+合计)
```

### 无新后端端点

已有 `getTrialBalance(pid, year)` 完整返回该项目该年度的所有行。对比纯前端 join。权限由各端点现有项目级鉴权保证（无权访问的项目 403 → 前端提示"无权限"不显示该列）。

## Components and Interfaces

### TbComparisonView.vue (新建)

```typescript
interface Props {
  projectId: string
  year: number
  currentRows: TrialBalanceRow[]  // 当前年度/项目的行
}

// 内部状态
mode: 'cross_year' | 'cross_project'
comparisonYear: number | null           // 跨年度对比目标年度
comparisonProjects: { id: string; name: string }[]  // 跨项目目标
comparedData: Map<string, TrialBalanceRow[]>  // key=pid or year → rows
```

Emits: `close` (返回正常视图)

### useTbComparison composable (新建)

```typescript
export function useTbComparison(projectId, year, currentRows) {
  // loadComparisonYear(targetYear) → GET trial-balance → cache
  // loadComparisonProject(targetPid) → GET trial-balance → cache  
  // joinedRows: computed → 按 standard_account_code outer-join
  // varianceStats: computed → changed/added/removed counts
  // sortByVariance(field, direction)
  // filterByThreshold(minAbsVariance)
}
```

### 集成到 TrialBalance.vue

- 工具栏加「📊 对比」下拉按钮(跨年度/跨项目两选项)
- `v-if="comparisonActive"` 渲染 `TbComparisonView` 替代主表
- 返回按钮 → `comparisonActive = false`

## Correctness Properties

### Property 1: Join by Account Code
Rows SHALL be matched by `standard_account_code` (exact). Accounts present in one side but not the other SHALL appear in "仅本方/仅对方" section. Validates: Requirement 4.

### Property 2: Variance Calculation
`variance_amount = target_audited - current_audited`. `variance_rate = variance_amount / abs(current_audited)` (current=0 → rate=null, display "∞" or "新增"). Validates: Requirement 3.

### Property 3: Permission Isolation
Cross-project comparison SHALL only show data from projects the user has at least readonly access to. 403 response for a target project SHALL result in that column showing "无权限" placeholder, not blocking the entire comparison. Validates: Requirement 7.

### Property 4: Cache Consistency
Cached comparison data SHALL be invalidated when the user triggers recalc on the current project (current rows changed → variance recalculated). Validates: Requirement 6.

### Property 5: Column Limit
Cross-project SHALL enforce max 5 targets. UI SHALL disable "添加" after 5. Validates: Requirement 5.

### Property 6: Export Correctness
Exported xlsx SHALL contain all comparison columns + variance columns + conditional formatting matching UI colors. Validates: Requirement 3.

### Property 7: Zero Regression
Default view (no comparison active) SHALL render identically to before. All existing toolbar actions SHALL remain functional. Validates: Requirement 8.

## Error Handling

- Target year has no trial_balance data: show "该年度无数据" placeholder column
- Target project 403: show "无权限访问该项目" placeholder column, do not remove from comparison
- Target project trial_balance empty: show "该项目无试算表数据"
- Network timeout (>10s): abort that target, show retry button on that column header
- standard_account_code collision (same code different name): use current project's name, tooltip shows other project's name

## Testing Strategy

- Vitest: useTbComparison join logic (same accounts / disjoint accounts / partial overlap) + variance calc + cache invalidation
- Integration: TbComparisonView mount with mock data → column rendering + filter + sort
- Playwright*: toggle comparison → select year → variance column renders → export downloads
