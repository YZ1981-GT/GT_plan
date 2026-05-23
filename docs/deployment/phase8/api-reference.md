# Phase 8 API 文档

## 概述

Phase 8 新增和优化了多个 API 端点，涵盖数据校验、性能监控、安全增强等功能。

---

## 1. 数据校验 API

### POST /api/projects/{project_id}/data-validation

触发项目数据校验。

**请求参数：**
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| project_id | UUID | 是 | 项目 ID（路径参数） |

**响应示例：**
```json
{
  "findings": [
    {
      "id": "f1",
      "type": "consistency",
      "severity": "high",
      "message": "余额表与辅助表金额不一致",
      "account_code": "1001",
      "details": {}
    }
  ],
  "total": 5,
  "blocking": 1
}
```

### GET /api/projects/{project_id}/data-validation/findings

查询数据校验结果。

**查询参数：**
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| severity | string | 否 | 过滤严重度（high/medium/low） |
| type | string | 否 | 过滤类型（consistency/completeness） |

### POST /api/projects/{project_id}/data-validation/fix

一键修复常见数据问题。

**请求体：**
```json
{
  "finding_ids": ["f1", "f2"]
}
```

### POST /api/projects/{project_id}/data-validation/export

导出数据校验报告。

**请求体：**
```json
{
  "format": "excel"
}
```

---

## 2. 性能监控 API

### GET /api/admin/performance-stats

获取系统性能统计概览。

**响应示例：**
```json
{
  "api_avg_response_ms": 45.2,
  "db_avg_query_ms": 12.8,
  "cache_hit_rate": 0.85,
  "active_connections": 42,
  "uptime_hours": 168.5
}
```

### GET /api/admin/performance-metrics

获取详细性能指标时序数据。

**查询参数：**
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| period | string | 否 | 时间范围（1h/6h/24h/7d），默认 1h |
| metric | string | 否 | 指标类型（api/db/cache） |

### GET /api/admin/slow-queries

获取慢查询列表。

**查询参数：**
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| threshold_ms | int | 否 | 慢查询阈值（默认 1000ms） |
| limit | int | 否 | 返回条数（默认 20） |

---

## 3. 安全监控 API

### GET /api/security/login-attempts

获取登录尝试记录。

**查询参数：**
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| username | string | 否 | 按用户名过滤 |
| status | string | 否 | 状态（failed/success） |

### POST /api/security/lock-account

锁定指定账户。

**请求体：**
```json
{
  "username": "user@example.com",
  "duration_minutes": 30,
  "reason": "多次登录失败"
}
```

### GET /api/security/sessions

获取活跃会话列表。

### GET /api/audit-logs/export

导出审计日志。

**查询参数：**
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| start_date | date | 否 | 开始日期 |
| end_date | date | 否 | 结束日期 |
| format | string | 否 | 导出格式（csv/excel） |

---

## 4. 穿透查询 API（优化）

### GET /api/projects/{project_id}/ledger/penetrate

穿透查询（已优化：移除不必要的 JOIN，支持游标分页）。

**查询参数：**
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| account_code | string | 是 | 科目编码 |
| cursor | string | 否 | 游标（用于分页） |
| limit | int | 否 | 每页条数（默认 100） |

**响应示例：**
```json
{
  "items": [...],
  "next_cursor": "uuid-of-last-item",
  "has_more": true
}
```

---

## 5. 试算表 API（优化）

### GET /api/projects/{project_id}/trial-balance

试算表查询（新增 currency_code 筛选支持）。

**查询参数：**
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| year | int | 是 | 会计年度 |
| currency_code | string | 否 | 货币代码（默认 CNY） |

---

## 变更日志

| 版本 | 日期 | 变更内容 |
|------|------|---------|
| 8.0 | 2025-01 | 新增数据校验/性能监控/安全监控 API |
| 8.0 | 2025-01 | 穿透查询支持游标分页 |
| 8.0 | 2025-01 | 试算表支持 currency_code 筛选 |
