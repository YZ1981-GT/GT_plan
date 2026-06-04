# Design: PG 连接池化 + 6000 并发压测（PgBouncer + Locust）

## Overview

目标并发 6000 用户，但 asyncpg 直连 PG 时每请求占一个连接，PG 默认 `max_connections=100` 早早耗尽——压测会撞 "too many connections" 而非真实业务瓶颈。本 spec 做两件互为前置的事：
1. **PgBouncer 连接池**（transaction pooling 模式）置于后端与 PG 之间，把 6000 客户端连接收敛到 PG 几十个物理连接。
2. **Locust 压测脚本** 针对真实 PG 数据跑 6000 并发，产出可复现的性能基线报告。

PgBouncer 是压测前置：没有它压测跑不到真实瓶颈。两者一起做。

## 现状勘察

### 当前连接链路
- `backend/app/core/database.py`：SQLAlchemy `create_async_engine` + asyncpg driver；已有 `async_engine = engine` 别名
- 连接参数：待勘察 `pool_size` / `max_overflow` 当前值
- DB：`audit_platform`（Docker `audit-postgres` 5432）

### asyncpg + PgBouncer transaction pooling 的已知坑（design 必须处理）
- **prepared statement 冲突**：asyncpg 默认用 server-side prepared statements + 自动命名缓存；PgBouncer transaction 模式下连接复用会导致 "prepared statement already exists" / "does not exist"。
  - 解法：asyncpg 侧 `statement_cache_size=0` + SQLAlchemy `connect_args={"prepared_statement_cache_size": 0}`（或 `statement_cache_size=0`），并禁用 SQLAlchemy 的 server-side cursor 预编译
- **`SET` 会话级配置**：transaction 模式下 SET 不跨事务保留（memory.md 已记 PG SET 不支持绑定参数，须 set_config）——确认 RLS/search_path 等会话设置不依赖跨事务保留
- **LISTEN/NOTIFY**：transaction 模式不支持；确认代码是否用到（SSE 走 Redis 不走 PG NOTIFY，需勘察确认）

### memory.md 已有性能基线
- "YG2101 128MB/11min / calamine 3.4× 加速"——压测报告应纳入对比

## Architecture

### 部署拓扑

```
6000 客户端
    │
    ▼
后端 (uvicorn/gunicorn 多 worker, 9980)
    │  asyncpg (statement_cache_size=0)
    ▼
PgBouncer (6432, transaction pooling)
    │  收敛到 default_pool_size 个物理连接
    ▼
PostgreSQL (audit-postgres 5432, max_connections 适度上调)
```

### PgBouncer 配置（`docker-compose` 新增 service）

```ini
[databases]
audit_platform = host=audit-postgres port=5432 dbname=audit_platform

[pgbouncer]
pool_mode = transaction
max_client_conn = 10000
default_pool_size = 50          ; 物理连接数（按 PG max_connections 留余量）
reserve_pool_size = 10
server_idle_timeout = 600
; transaction 模式必须：禁用 server-side prepared statement 干扰
ignore_startup_parameters = extra_float_digits
```

`docker-compose.yml` 加 `audit-pgbouncer` service（image `edoburu/pgbouncer` 或 `bitnami/pgbouncer`），depends_on audit-postgres，暴露 6432。

### 后端连接切换（环境变量驱动，可回退）

```python
# database.py
# DB_USE_PGBOUNCER=True → 连 6432 + statement_cache_size=0 + NullPool
# DB_USE_PGBOUNCER=False → 直连 5432（现状，开发默认，QueuePool）
from sqlalchemy.pool import NullPool

if settings.DB_USE_PGBOUNCER:
    # PgBouncer 已在外部管池 → SQLAlchemy 端用 NullPool 避免双层池争用
    engine = create_async_engine(
        pgbouncer_dsn,
        poolclass=NullPool,
        connect_args={
            "statement_cache_size": 0,           # asyncpg 关 PS 缓存（transaction pooling 必须）
            "prepared_statement_cache_size": 0,  # SQLAlchemy 层
        },
        pool_pre_ping=True,
    )
else:
    # 直连：保持现状 QueuePool（pool_size/max_overflow）
    engine = create_async_engine(dsn, pool_size=..., max_overflow=..., pool_pre_ping=True, ...)
```

> ⚠️ **双层池语义（勘察后明确）**：PgBouncer transaction pooling 已在中间层管理物理连接池。若 SQLAlchemy 端再用默认 `QueuePool`（pool_size=20/max_overflow=80），形成两层池叠加——SQLAlchemy 持有的"逻辑连接"映射到 PgBouncer 的"客户端连接"，反而增加复杂度与潜在 idle 占用。**`DB_USE_PGBOUNCER=True` 时 SQLAlchemy 端应改 `poolclass=NullPool`**（每次取连接即向 PgBouncer 新建、用完即还，由 PgBouncer 复用）。直连分支保持 QueuePool 不变。

- 开发环境默认直连（不强制起 PgBouncer）
- 压测/生产环境 `DB_USE_PGBOUNCER=True`

### Locust 压测脚本（`backend/tests/load/`）

memory.md 显示已有 `backend/tests/load/` 目录 + `locust` 依赖。本 spec 扩充：

```python
# backend/tests/load/locustfile_6000.py
class AuditUser(HttpUser):
    wait_time = between(1, 3)
    def on_start(self): self.login()   # admin/admin123 或批量测试用户
    @task(5)  def view_dashboard(self): ...
    @task(3)  def list_workpapers(self): ...
    @task(2)  def query_trial_balance(self): ...
    @task(1)  def read_ledger(self): ...      # 重查询（82384 行序时账）
```

- 覆盖只读热路径（dashboard / 底稿列表 / TB / 序时账）——写路径单独低权重避免污染真实数据
- 阶梯加压：100 → 1000 → 3000 → 6000 用户，记录各阶 p50/p95/p99 延迟 + 错误率 + RPS
- 产出 `backend/tests/load/REPORT_6000.md` 性能基线（含 PgBouncer on/off 对比）

### 压测前置准备
- 测试数据：真实 PG（首汽租车_2025 df5b8403 tb 最全）+ 批量测试用户 seed（`backend/scripts/seed/` 加 `_seed_load_test_users.py`，`_` 前缀=用完即删）
- 监控：压测时观察 PgBouncer `SHOW POOLS` / PG `pg_stat_activity` 连接数

## 配置项

```python
DB_USE_PGBOUNCER: bool = False        # 默认直连，压测/生产开
DB_PGBOUNCER_PORT: int = 6432
DB_POOL_SIZE: int = 20                # SQLAlchemy 应用层池（PgBouncer 后可调小）
DB_MAX_OVERFLOW: int = 10
```

## Error Handling

| 场景 | 处理 |
|------|------|
| prepared statement 冲突 | statement_cache_size=0 根治；测试用例专门验证 |
| PgBouncer 未启动但 DB_USE_PGBOUNCER=True | pool_pre_ping 探测失败 → 启动日志明确报错，不静默 |
| 压测撞 PG max_connections | 调 PgBouncer default_pool_size / PG max_connections，记录调参 |
| LISTEN/NOTIFY 依赖（若存在） | 确认走 Redis；若有 PG NOTIFY 依赖则 session pooling 局部豁免 |

## 测试策略

- **连接正确性单测**：`DB_USE_PGBOUNCER=True` 路径 statement_cache_size=0 生效；CRUD 往返正常（需 PgBouncer 容器，标 `[ ]*` 外部依赖）
- **prepared statement 回归测试**：连续多次相同参数化查询不报 "prepared statement already exists"
- **压测执行**：本身是外部依赖任务（需起容器 + 真实数据），标 `[ ]*`，产出报告作为交付物

## 与现有能力的关系

| 能力 | 复用 | 新增 |
|------|------|------|
| 连接引擎 | `database.py` create_async_engine + async_engine 别名 | DB_USE_PGBOUNCER 分支 |
| 压测 | `backend/tests/load/` + locust 依赖 | locustfile_6000 + 阶梯加压 + 报告 |
| 测试数据 | 真实 PG df5b8403 | 批量测试用户 seed |
| Docker | docker-compose audit-postgres/redis | audit-pgbouncer service |
