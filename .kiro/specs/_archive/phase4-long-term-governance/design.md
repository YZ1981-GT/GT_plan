# Design Document — Phase 4 长期治理

## 变更记录

| 版本 | 日期 | 变更内容 |
|------|------|----------|
| v1.0 | 2026-05-21 | 初始设计 |

---

## Overview

Phase 4 包含五项长期治理功能：PG RLS 行级安全、多年度对比分析、EQCR 快照机制、数据库迁移回滚、Redis 高可用。这些功能涉及基础设施层变更，风险较高，需要充分测试和灰度发布。

---

## F1 PG RLS 行级安全

### ADR-F1: RLS 实施策略

**决策**：使用 PG session 变量 + RLS POLICY，应用层在每次请求开始时 SET LOCAL。

**理由**：
1. SET LOCAL 仅在当前事务内有效，事务结束自动清除（安全）
2. 不需要修改现有查询（RLS 透明过滤）
3. admin bypass 通过 SECURITY DEFINER 函数实现（不需要 BYPASSRLS 角色）

### 实施方案

```sql
-- V006__enable_rls.sql

-- 1. 启用 RLS
ALTER TABLE working_paper ENABLE ROW LEVEL SECURITY;
ALTER TABLE adjustments ENABLE ROW LEVEL SECURITY;
ALTER TABLE tb_balance ENABLE ROW LEVEL SECURITY;
ALTER TABLE reports ENABLE ROW LEVEL SECURITY;
ALTER TABLE review_records ENABLE ROW LEVEL SECURITY;

-- 2. 创建策略
CREATE POLICY project_isolation ON working_paper
  USING (project_id::text = current_setting('app.current_project_id', true));

CREATE POLICY project_isolation ON adjustments
  USING (project_id::text = current_setting('app.current_project_id', true));

-- ... 其他表类似

-- 3. 应用角色不是表 owner，需要 FORCE
ALTER TABLE working_paper FORCE ROW LEVEL SECURITY;
-- ...

-- 4. bypass 函数（admin 跨项目查询用）
CREATE OR REPLACE FUNCTION admin_query_all_projects()
RETURNS SETOF working_papers
LANGUAGE sql SECURITY DEFINER
AS $$ SELECT * FROM working_papers; $$;
```

### 应用层改造

```python
# backend/app/core/database.py — 新增 middleware
@asynccontextmanager
async def scoped_session(project_id: str | None):
    """在事务开始时设置 RLS session 变量"""
    async with async_session() as session:
        if project_id:
            await session.execute(text(f"SET LOCAL app.current_project_id = '{project_id}'"))
        yield session
```

### 回滚脚本

```sql
-- R006__disable_rls.sql
DROP POLICY IF EXISTS project_isolation ON working_papers;
ALTER TABLE working_papers DISABLE ROW LEVEL SECURITY;
-- ... 其他表
```

---

## F2 多年度对比分析

### 后端 API

```python
# GET /api/projects/{pid}/reports/multi-year?years=2023,2024,2025&report_type=BS
# Response:
{
  "years": [2023, 2024, 2025],
  "report_type": "BS",
  "rows": [
    {
      "line_code": "BS-001",
      "item_name": "货币资金",
      "values": {
        "2023": 3000000,
        "2024": 4500000,
        "2025": 5000000
      },
      "yoy_changes": {
        "2024": 50.0,   # (4500000-3000000)/3000000 * 100
        "2025": 11.1    # (5000000-4500000)/4500000 * 100
      }
    },
    ...
  ]
}
```

### 前端组件

```
┌─────────────────────────────────────────────────────────────┐
│ MultiYearCompare.vue                                         │
│   ├─ 年度选择器（el-date-picker type="years" multiple）      │
│   ├─ 报表类型切换（BS/IS/CFS）                              │
│   └─ el-table                                                │
│       ├─ 项目名称列 (fixed)                                  │
│       ├─ 2023 金额列                                         │
│       ├─ 2024 金额列 + YoY 变动                             │
│       ├─ 2025 金额列 + YoY 变动                             │
│       └─ 趋势列（迷你折线图 sparkline）                      │
└─────────────────────────────────────────────────────────────┘
```

---

## F3 EQCR 快照机制

### 数据模型

```sql
-- V007__eqcr_snapshots.sql
CREATE TABLE eqcr_snapshots (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id UUID NOT NULL REFERENCES projects(id),
  year INTEGER NOT NULL,
  created_by UUID NOT NULL REFERENCES users(id),
  created_at TIMESTAMP NOT NULL DEFAULT NOW(),
  snapshot_data JSONB NOT NULL,  -- 全量快照数据
  is_current BOOLEAN NOT NULL DEFAULT TRUE,
  UNIQUE(project_id, year, is_current) WHERE is_current = TRUE
);
```

### 快照数据结构

```json
{
  "workpapers": [
    {"wp_id": "...", "wp_code": "D2-1", "status": "signed", "version": 5}
  ],
  "reports": {
    "BS": [{"line_code": "BS-001", "amount": 5000000}],
    "IS": [...]
  },
  "adjustments": [
    {"id": "...", "type": "AJE", "status": "approved", "amount": 100000}
  ],
  "vr_results": [
    {"rule_id": "VR-D4-01", "passed": true, "severity": "blocking"}
  ],
  "metadata": {
    "snapshot_version": 1,
    "total_workpapers": 45,
    "signed_workpapers": 42
  }
}
```

### EQCR 工作台改造

EqcrProjectView.vue 改为从 `eqcr_snapshots` 读取数据（而非实时查询 working_papers 等表）。

---

## F4 数据库迁移回滚

### migration_runner.py 改造

```python
# 新增 --rollback 参数
def rollback_to(target_version: str):
    """回滚到指定版本（逆序执行 R*.sql）"""
    current = get_current_version()  # 从 schema_version 表读取
    versions_to_rollback = get_versions_between(target_version, current)  # 逆序

    # 1. 自动备份
    backup_file = f"backup_{current}_{datetime.now().isoformat()}.sql"
    subprocess.run(["pg_dump", "-f", backup_file, DB_URL])

    # 2. 逆序执行回滚脚本
    for version in reversed(versions_to_rollback):
        rollback_script = f"R{version[1:]}"  # V004 → R004
        execute_sql_file(rollback_script)

    # 3. 更新 schema_version
    update_schema_version(target_version, rollback=True, operator=os.getenv("USER"))
```

### 文件命名规范

```
backend/migrations/
├── V001__init.sql
├── R001__rollback_init.sql
├── V002__add_schema_version.sql
├── R002__rollback_schema_version.sql
├── V003__example_add_comment.sql
├── R003__rollback_example_add_comment.sql
├── V004__add_workpaper_version.sql      (Phase 1)
├── R004__rollback_workpaper_version.sql
├── V005__add_review_priority.sql        (Phase 2)
├── R005__rollback_review_priority.sql
├── V006__enable_rls.sql                 (Phase 4)
├── R006__disable_rls.sql
└── V007__eqcr_snapshots.sql             (Phase 4)
    R007__rollback_eqcr_snapshots.sql
```

---

## F5 Redis 高可用

### 部署架构

```
┌─────────────────────────────────────────────────┐
│ Redis Sentinel Cluster                           │
│                                                  │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐        │
│  │Sentinel1│  │Sentinel2│  │Sentinel3│        │
│  └────┬────┘  └────┬────┘  └────┬────┘        │
│       │             │             │              │
│  ┌────▼────┐  ┌────▼────┐  ┌────▼────┐        │
│  │ Master  │──│Replica 1│──│Replica 2│        │
│  │ :6379   │  │ :6380   │  │ :6381   │        │
│  └─────────┘  └─────────┘  └─────────┘        │
└─────────────────────────────────────────────────┘
```

### 应用层改造

```python
# backend/app/core/redis.py
from redis.asyncio.sentinel import Sentinel

sentinel = Sentinel(
    [(settings.REDIS_SENTINEL_HOST_1, 26379),
     (settings.REDIS_SENTINEL_HOST_2, 26379),
     (settings.REDIS_SENTINEL_HOST_3, 26379)],
    socket_timeout=0.5,
)

async def get_redis():
    """获取 Redis master 连接（自动故障转移）"""
    try:
        master = sentinel.master_for(settings.REDIS_SENTINEL_SERVICE, decode_responses=True)
        return master
    except Exception:
        logger.warning("Redis Sentinel unavailable, degrading")
        return None  # 降级：返回 None，调用方检查后走 DB fallback
```

### 降级策略

| 功能 | Redis 可用 | Redis 不可用（降级） |
|------|-----------|-------------------|
| JWT 黑名单 | Redis SET/GET | 跳过检查（接受短暂风险） |
| 权限缓存 | Redis 5min TTL | 直接查 DB |
| 编辑锁 | Redis SETNX | 跳过锁（接受并发风险，版本锁兜底） |
| SSE 状态 | Redis PubSub | 降级为轮询 |

---

## 测试策略

| 功能 | 测试方式 |
|------|---------|
| F1 RLS | 渗透测试（模拟跨项目访问）+ 现有测试全量回归 |
| F2 多年度 | 后端 API 单测 + 前端 vitest |
| F3 EQCR 快照 | 快照创建/读取/刷新 + 数据完整性校验 |
| F4 迁移回滚 | 模拟回滚 V003→V002 + 数据完整性 |
| F5 Redis HA | 模拟 master 宕机 + 故障转移 + 降级验证 |
