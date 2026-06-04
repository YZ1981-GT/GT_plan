# Tasks: PG 连接池化 + 6000 并发压测（PgBouncer + Locust）

## Overview

按 design 分 4 组：① 现状勘察 + 配置 → ② PgBouncer 部署 + 后端切换 → ③ prepared statement 根治 + 回归测试 → ④ Locust 压测脚本 + 报告。组③前为代码可在开发环境验证；组④含外部依赖标 `[ ]*`。

**勘察结论（实施前必读）**：
- `database.py` 用**模块级顶层** `engine = create_async_engine(settings.DATABASE_URL, ...)` 构造（非工厂函数），按 `_is_postgres = DATABASE_URL.startswith("postgresql")` 分支；PG 分支已设 `pool_size=max(DB_POOL_SIZE,20)` / `max_overflow=max(DB_MAX_OVERFLOW,80)` / `pool_pre_ping=True` / `pool_recycle=1800`。DB_USE_PGBOUNCER 分支要插在此顶层块。
- `async_engine = engine` 别名已存在（dataset_purge/recycle_bin/ledger_import_health 用）；同步引擎 `_sync_engine = engine.sync_engine` 也派生自此。改 DSN 时三者自动跟随。
- **RLS 已用 `set_config('app.current_project_id', :pid, true)`（is_local=true，事务内）**——这是 transaction pooling **兼容**的（事务结束自动清，不依赖跨事务保留）。SET LOCAL 勘察项实际已有答案：✅ 兼容，无阻塞。
- config 现状：`DATABASE_URL` 完整 DSN（`postgresql+asyncpg://...`）+ `DB_POOL_SIZE=50` + `DB_MAX_OVERFLOW=100` 已存在——**不重复加这两项**，只加 PgBouncer 专属配置。
- 已有 `backend/tests/load/` 目录 + `locust` 依赖 + `backend/scripts/seed/` 目录。

## Tasks

### 组 ① 现状勘察 + 配置项

- [x] 1. 补充勘察（确认无阻塞项，写入核查记录）
  - grep 全仓 `LISTEN` / `NOTIFY` / `pg_notify` → 确认 SSE 走 Redis 不依赖 PG NOTIFY（transaction pooling 不支持 LISTEN/NOTIFY）
  - grep `SET ` 裸语句（非 set_config）→ 确认无依赖跨事务保留的会话级 SET（RLS 已用 set_config is_local=true 兼容，已确认）
  - grep `.execute(text("SET` 排查遗漏点
  - 输出结论：阻塞项清单（预期为空）
  - _Requirements: 3.3_

- [x] 2. 配置项（仅加 PgBouncer 专属，不重复 DB_POOL_SIZE/DB_MAX_OVERFLOW）
  - `backend/app/core/config.py` 的 `Settings` 加：`DB_USE_PGBOUNCER: bool = False` / `DB_PGBOUNCER_HOST: str = "localhost"` / `DB_PGBOUNCER_PORT: int = 6432`
  - `.env.example` 同步 + 注释（开发默认 False 直连，压测/生产 True）
  - _Requirements: 2.1_

- [x] 3. 检查点 — 勘察结论确认无 PG NOTIFY/裸 SET 阻塞项；配置项 getDiagnostics 干净

### 组 ② PgBouncer 部署 + 后端连接切换

- [x] 4. `docker-compose.yml` 加 `audit-pgbouncer` service
  - image `edoburu/pgbouncer`（或 `bitnami/pgbouncer`）
  - 环境/配置：`POOL_MODE=transaction` / `MAX_CLIENT_CONN=10000` / `DEFAULT_POOL_SIZE=50`（< PG max_connections 留余量）/ `RESERVE_POOL_SIZE=10` / `IGNORE_STARTUP_PARAMETERS=extra_float_digits`
  - 上游指 `audit-postgres:5432` dbname=`audit_platform`；depends_on audit-postgres；暴露 6432
  - 与现有 audit-postgres/audit-redis 同 network
  - _Requirements: 1.1, 1.2, 1.3_

- [x] 5. `database.py` 加 DB_USE_PGBOUNCER 分支
  - 在 `_is_postgres` 为真的 PG 分支内：`if settings.DB_USE_PGBOUNCER:` → 用 `sqlalchemy.engine.make_url(settings.DATABASE_URL).set(host=DB_PGBOUNCER_HOST, port=DB_PGBOUNCER_PORT)` 改写 DSN（**用 make_url 而非手写字符串替换**，正确处理 `postgresql+asyncpg://` 方言前缀 + 凭据 + dbname；参照 migration_runner 的 urlparse 先例但 make_url 更安全）
  - PgBouncer 分支：`poolclass=NullPool`（`from sqlalchemy.pool import NullPool`，避免与 PgBouncer 双层池争用）+ `connect_args={"statement_cache_size": 0, "prepared_statement_cache_size": 0}` + `pool_pre_ping=True`
  - 直连分支（False）保持现状完全不变（QueuePool + pool_size/max_overflow）
  - 注意：NullPool 下不传 pool_size/max_overflow（NullPool 不接受这些参数，传了会报错）
  - 注意：`async_engine` 别名 + `_sync_engine` 派生自 engine，无需额外改
  - _Requirements: 2.1, 2.2, 2.3, 2.4_

- [x] 6. 检查点 — 开发环境直连路径不回归（`DB_USE_PGBOUNCER=False` getDiagnostics + 现有 DB 相关测试通过，如 test_health/test_trial_balance 等）

### 组 ③ prepared statement 冲突根治 + 回归测试

- [x] 7. 回归测试 `backend/tests/test_pgbouncer_connection.py`
  - **测试环境约束（勘察）**：conftest 默认 `sqlite+aiosqlite:///:memory:`；`statement_cache_size`/`prepared_statement_cache_size` 是 **asyncpg 专属参数，SQLite 无此概念**。故拆两类：
    - **SQLite 可跑（纯单元，验证构造逻辑）**：mock/直接调用 engine 构造函数，断言 `DB_USE_PGBOUNCER=True` 时 connect_args 含 `statement_cache_size=0` + poolclass 是 NullPool + DSN host:port 经 make_url 正确替换；直连分支仍 QueuePool。这类**不真正连库**，纯断言构造参数，SQLite 环境可跑
    - **`@pytest.mark.pg_only`（需真 PG）**：连续多次相同参数化查询不报 PS 冲突——非 PG 环境自动 skip（conftest 的 pytest_collection_modifyitems 机制）
  - 真 PgBouncer 容器往返：标 `[ ]*`（见 task 8）
  - _Requirements: 3.1, 3.2_

- [ ]* 8. PgBouncer 容器端到端连接验证（外部依赖）
  - `docker compose up audit-pgbouncer` + 后端 `DB_USE_PGBOUNCER=True`
  - 跑核心只读端点（/api/health + 1-2 个 GET）确认无 PS 冲突
  - PgBouncer `SHOW POOLS` 确认连接收敛（cl_active < sv_active）
  - _Requirements: 1.3, 2.2, 3.1_

- [x] 9. 检查点 — PS 根治回归测试（单元部分）通过

### 组 ④ Locust 压测脚本 + 性能基线报告

- [x] 10. 批量测试用户 seed `backend/scripts/seed/_seed_load_test_users.py`
  - 批量建 N 个测试用户（如 6000，密码统一，role=auditor）+ 关联到测试项目（df5b8403 首汽租车_2025）
  - `_` 前缀=用完即删；提供 `--count` 参数 + 清理函数
  - 复用现有 user/staff 创建逻辑（参照 staff import 或 seed 脚本）
  - _Requirements: 4.4_

- [x] 11. `backend/tests/load/locustfile_6000.py`
  - `class AuditUser(HttpUser)`：`wait_time = between(1, 3)` + `on_start` 登录拿 token（POST /api/auth/login，复用 seed 用户）
  - `@task(5) view_dashboard` / `@task(3) list_workpapers` / `@task(2) query_trial_balance` / `@task(1) read_ledger`（序时账重查询）—— 全只读热路径，带 Authorization header
  - 写路径：不含或单独 `@task(0)` 隔离（避免污染 df5b8403 真实数据）
  - 注释阶梯加压用法：`locust -f locustfile_6000.py --users 6000 --spawn-rate 100`（或 `--step-load` 100→1000→3000→6000）
  - _Requirements: 4.1, 4.2, 4.3_

- [ ]* 12. 执行压测 + 产出报告（外部依赖：容器 + 真实数据 + seed 用户）
  - 真实 PG（df5b8403）+ seed 用户；阶梯加压 100→1000→3000→6000 各记录 p50/p95/p99/RPS/错误率
  - PgBouncer on/off 两轮对比；每轮观测 `pg_stat_activity` 连接数 + `SHOW POOLS`
  - 产出 `backend/tests/load/REPORT_6000.md`，含两轮对比表 + 与 memory.md 既有基线（YG2101 128MB/11min）对照 + 瓶颈定位结论
  - _Requirements: 5.1, 5.2, 5.3, 6.2_

- [x] 13. 最终检查点
  - 代码部分：database.py DB_USE_PGBOUNCER 分支 + `test_pgbouncer_connection.py` 单元部分全绿 + `locust -f backend/tests/load/locustfile_6000.py --help` 无加载错误（语法/import 正确）
  - 外部依赖部分（容器压测+报告）如实标 `[ ]*` 状态
  - _Requirements: 6.1, 6.2_
