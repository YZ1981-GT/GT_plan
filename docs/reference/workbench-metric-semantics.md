# 作业台核心指标口径

> MVP-2 产物：冻结 5 个核心指标的口径定义，确保后续开发不产生歧义。

## 指标口径定义

| 指标 | 口径定义 | 分子 | 分母 | 数据来源 | 数据就绪度 |
|------|----------|------|------|----------|-----------|
| 底稿完成率 | 已完成底稿 / 应完成底稿 | wp_index.status IN (reviewed, signed_off) | wp_index 全部（排除 cancelled） | wp_index 表 | ✅ 可用 |
| 复核 Aging | now() - review_issue.created_at | 未关闭 review issues | — | review_issues 表 | ✅ 可用 |
| 工时预算消耗率 | 已审批工时 / 项目预算工时 | SUM(workhour.approved_hours) | project.budget_hours | workhour 表 + projects 表 | ⚠️ budget_hours 字段待补 |
| 质量分 | QC 检查通过率 * 100 | 通过检查数 | 总检查数 | qc_inspections | ⚠️ 需确认评分规则 |
| 签发阻断项 | stale + conflict + 重大复核未关闭 + AI 未确认 + 交付件缺失 | 各条件 count | — | 多表聚合 | ⚠️ 需 facade 聚合 |

## 详细口径说明

### 1. 底稿完成率

```sql
SELECT
  COUNT(*) FILTER (WHERE status IN ('reviewed', 'signed_off')) AS numerator,
  COUNT(*) FILTER (WHERE status != 'cancelled') AS denominator
FROM wp_index
WHERE project_id = :pid
```

- 分子：status 为 reviewed 或 signed_off 的底稿
- 分母：排除 cancelled 后的全部底稿
- 精度：保留 2 位小数百分比

### 2. 复核 Aging

```sql
SELECT
  id,
  EXTRACT(EPOCH FROM (now() - created_at)) / 3600 AS aging_hours
FROM review_issues
WHERE project_id = :pid AND status NOT IN ('closed', 'resolved')
```

- 单位：小时（前端转为"天"展示时 /24）
- 阈值：>72h 标红，>48h 标黄

### 3. 工时预算消耗率

```sql
SELECT
  SUM(approved_hours) AS consumed,
  p.budget_hours AS budget
FROM workhour w
JOIN projects p ON w.project_id = p.id
WHERE w.project_id = :pid
GROUP BY p.budget_hours
```

- **数据缺口**：projects.budget_hours 字段当前不存在，需 migration 补充
- 降级策略：字段缺失时返回 null，前端显示"暂无预算数据"

### 4. 质量分

```sql
SELECT
  COUNT(*) FILTER (WHERE result = 'pass') AS passed,
  COUNT(*) AS total
FROM qc_inspections
WHERE project_id = :pid
```

- 计算：(passed / total) * 100
- **待确认**：是否需要加权（按严重程度加权扣分）

### 5. 签发阻断项

聚合条件（任一存在即为阻断）：

| 阻断类型 | 判定条件 | 来源表 |
|----------|----------|--------|
| stale 数据 | stale_summary.is_stale = true | stale_summary_aggregate |
| conflict | conflict_resolution.status = 'open' | conflict_resolution |
| 重大复核未关闭 | review_issues.severity = 'major' AND status = 'open' | review_issues |
| AI 未确认 | ai_content_log.confirmed = false | ai_content_log |
| 交付件缺失 | deliverable.status = 'missing' | deliverables |

- 返回：阻断项列表（含 type、description、route）
- 前端：红色计数 badge
