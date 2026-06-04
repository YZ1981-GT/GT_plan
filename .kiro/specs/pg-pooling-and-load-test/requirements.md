# Requirements: PG 连接池化 + 6000 并发压测（PgBouncer + Locust）

## Introduction

平台目标 6000 并发用户，但当前 asyncpg 直连 PG（默认 `max_connections=100`），高并发下连接耗尽，压测撞 "too many connections" 而非真实业务瓶颈。本 spec 引入 **PgBouncer**（transaction pooling）收敛连接，并编写 **Locust 6000 并发压测脚本** 产出可复现性能基线。PgBouncer 是压测前置，两者一并交付。

## Glossary

- **PgBouncer**: 轻量 PG 连接池中间件，置于后端与 PG 之间
- **transaction pooling**: PgBouncer 池模式，事务结束即归还连接（最高复用率，但有 prepared statement / 会话状态约束）
- **prepared statement 冲突**: asyncpg 默认 server-side prepared statement，在 transaction pooling 连接复用下报 "already exists/does not exist"
- **statement_cache_size=0**: asyncpg 禁用 PS 缓存的参数，根治 PgBouncer 冲突
- **DB_USE_PGBOUNCER**: 环境变量开关，True 走 PgBouncer(6432) / False 直连 PG(5432)
- **阶梯加压**: 100→1000→3000→6000 用户逐级加压，记录各级延迟与错误率
- **性能基线报告**: 压测产出文档，含 p50/p95/p99 / RPS / 错误率 + PgBouncer on/off 对比

## Requirements

### Requirement 1: PgBouncer 部署

**User Story:** As a 运维, I want PgBouncer 作为 PG 连接池, so that 6000 客户端连接收敛到 PG 几十个物理连接，不耗尽 max_connections。

#### Acceptance Criteria
1. THE `docker-compose.yml` SHALL 新增 `audit-pgbouncer` service（transaction pooling，暴露 6432，depends_on audit-postgres）。
2. THE PgBouncer 配置 SHALL 设 `pool_mode=transaction` / `max_client_conn>=10000` / `default_pool_size` 按 PG max_connections 留余量。
3. THE PgBouncer SHALL 正确路由到 `audit_platform` 数据库。

### Requirement 2: 后端连接切换且可回退

**User Story:** As a 后端开发者, I want 用环境变量切换直连/PgBouncer, so that 开发默认直连、压测生产走池化，互不干扰。

#### Acceptance Criteria
1. THE `database.py` SHALL 支持 `DB_USE_PGBOUNCER` 开关：True → 连 6432，False → 直连 5432（默认）。
2. WHEN `DB_USE_PGBOUNCER` 为真, THE 系统 SHALL 设 asyncpg `statement_cache_size=0` 与 SQLAlchemy `prepared_statement_cache_size=0`。
3. WHEN `DB_USE_PGBOUNCER` 为真, THE SQLAlchemy 端 SHALL 用 `poolclass=NullPool`（PgBouncer 已管池，避免双层池争用），不传 pool_size/max_overflow；直连分支保持 QueuePool 不变。
4. WHEN PgBouncer 不可达但开关为真, THE 系统 SHALL 通过 pool_pre_ping 明确报错（不静默挂起）。

### Requirement 3: prepared statement 冲突根治

**User Story:** As a 后端开发者, I want transaction pooling 下不再报 prepared statement 冲突, so that 池化后业务查询稳定。

#### Acceptance Criteria
1. WHEN 经 PgBouncer 连续执行多次相同参数化查询, THE 系统 SHALL NOT 报 "prepared statement already exists/does not exist"。
2. THE 系统 SHALL 有回归测试验证 statement_cache_size=0 路径下参数化查询往返正常。
3. THE 设计 SHALL 确认 LISTEN/NOTIFY 不依赖 PG（走 Redis）；若存在 PG NOTIFY 依赖则单独豁免说明。

### Requirement 4: 6000 并发压测脚本

**User Story:** As a 性能工程师, I want 一个覆盖真实热路径的 Locust 脚本, so that 我能复现 6000 并发并定位瓶颈。

#### Acceptance Criteria
1. THE 系统 SHALL 提供 `backend/tests/load/locustfile_6000.py`，覆盖只读热路径（dashboard / 底稿列表 / TB / 序时账）。
2. THE 压测 SHALL 支持阶梯加压 100→1000→3000→6000，记录各级 p50/p95/p99 / RPS / 错误率。
3. THE 写路径 SHALL 低权重或隔离，避免污染真实数据。
4. THE 系统 SHALL 提供批量测试用户 seed 脚本（`backend/scripts/seed/_seed_load_test_users.py`，`_` 前缀用完即删）。

### Requirement 5: 性能基线报告

**User Story:** As a 项目经理, I want 一份可复现的压测报告, so that 我能判断平台是否达 6000 并发目标及瓶颈所在。

#### Acceptance Criteria
1. THE 系统 SHALL 产出 `backend/tests/load/REPORT_6000.md`，含各阶梯延迟/RPS/错误率 + PgBouncer on/off 对比。
2. THE 报告 SHALL 记录 PG `pg_stat_activity` / PgBouncer `SHOW POOLS` 连接数观测。
3. THE 报告 SHALL 纳入与 memory.md 既有基线（YG2101 128MB/11min 等）的对照。

### Requirement 6: 验证

#### Acceptance Criteria
1. THE 连接正确性测试 SHALL 验证 DB_USE_PGBOUNCER 两条路径 CRUD 往返正常（PgBouncer 路径标 `[ ]*` 外部依赖容器）。
2. THE 压测执行 SHALL 标 `[ ]*`（需起容器 + 真实数据），产出报告作交付物。
