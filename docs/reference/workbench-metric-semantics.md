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


---

## RoleWorkbenchDTO JSON 示例（P0-2.6）

> 以下为 `GET /api/projects/{pid}/role-workbench?role=manager` 返回的标准响应结构。

```json
{
  "role": "manager",
  "project_id": "df5b8403-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "sections": [
    {
      "id": "completion_rate",
      "title": "底稿完成率",
      "items": [
        {
          "id": "cr-1",
          "label": "底稿完成率 75%",
          "priority": "normal",
          "route": "/projects/df5b8403/dashboard#completion",
          "metric": {
            "numerator": 45,
            "denominator": 60,
            "value": 0.75,
            "unit": "percent"
          }
        }
      ]
    },
    {
      "id": "review_aging",
      "title": "复核 Aging",
      "items": [
        {
          "id": "ra-1",
          "label": "复核超期 3 天",
          "priority": "high",
          "route": "/projects/df5b8403/reviews/rv-002",
          "due_date": "2025-12-12",
          "source": "review_conversation_service"
        }
      ]
    },
    {
      "id": "budget_consumption",
      "title": "工时预算消耗率",
      "items": [
        {
          "id": "bc-1",
          "label": "预算数据暂缺",
          "priority": "normal",
          "missing_reason": "budget_hours_field_missing"
        }
      ]
    },
    {
      "id": "personnel_load",
      "title": "人员负荷",
      "items": [
        {
          "id": "pl-1",
          "label": "张三负荷 120%",
          "priority": "high",
          "route": "/projects/df5b8403/workhours#staff-001"
        }
      ]
    },
    {
      "id": "risk_overview",
      "title": "风险总览",
      "items": [
        {
          "id": "ro-1",
          "label": "重大风险 2 项",
          "priority": "high",
          "route": "/projects/df5b8403/risks"
        }
      ]
    }
  ]
}
```

### DTO 字段规范

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `role` | string | ✅ | 当前角色：auditor / manager / qc / partner / eqcr |
| `project_id` | UUID string | ✅ | 项目 ID |
| `sections` | array | ✅ | 角色对应的 section 列表 |
| `sections[].id` | string | ✅ | section 唯一标识 |
| `sections[].title` | string | ✅ | section 展示标题 |
| `sections[].items` | array | ✅ | 该 section 下的具体项目 |
| `items[].id` | string | ✅ | item 唯一标识 |
| `items[].label` | string | ✅ | 展示文案 |
| `items[].priority` | string | ✅ | normal / high / critical |
| `items[].route` | string | ⚠️ | 跳转路径（与 missing_reason 二选一） |
| `items[].missing_reason` | string | ⚠️ | 无法跳转原因（与 route 二选一） |
| `items[].due_date` | string (ISO) | ❌ | 截止日期 |
| `items[].source` | string | ❌ | 数据来源 service |
| `items[].metric` | object | ❌ | 指标数值（仅指标类 section 使用） |

### 核心不变量

1. **每个 item 必须有 `route` 或 `missing_reason`**（二者至少有一）
2. **不同角色返回不同的 section 集合**（角色区块隔离性）
3. **route 以 `/` 开头**（前端相对路径格式）

---

## 数据可用性审计（P0-2.7）

| 指标 | 依赖 DB 字段 | 就绪状态 | 说明 |
|------|-------------|----------|------|
| 底稿完成率 | `wp_index.status` | ✅ 可用 | 字段非空，枚举值已定义 |
| 复核 Aging | `review_issues.created_at`, `review_issues.status` | ✅ 可用 | NOT NULL 列 |
| 工时预算消耗率 | `workhour.approved_hours`, `projects.budget_hours` | ⚠️ **待补** | `budget_hours` 列不存在，P1 migration 补充 |
| 质量分 | `qc_inspections.result` | ⚠️ 需确认 | 字段存在，评分加权规则待定 |
| 签发阻断项 | 多表聚合 | ⚠️ 需 facade | 各子表字段就绪，聚合逻辑 P1 实现 |

**结论**：5 个核心指标中，3 个数据完全就绪，2 个有已知缺口（budget_hours 待 migration、质量分加权规则待 QC 团队确认）。缺口已登记降级策略（返回 null + 前端友好提示）。
