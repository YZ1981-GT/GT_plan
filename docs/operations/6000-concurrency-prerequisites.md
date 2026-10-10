# 6000 并发前置条件清单

**创建日期：** 2026-10-10
**目标：** 从当前 ~200 并发支撑能力提升到 6000 并发用户

## 1. 当前基线

| 指标 | 当前值 | 来源 |
|------|--------|------|
| PG max_connections | 200 | pg_settings |
| PG shared_buffers | 4 GB | pg_settings（524288 × 8kB） |
| PG work_mem | 4 MB | pg_settings |
| PG effective_cache_size | 128 MB | pg_settings（16384 × 8kB） |
| PG max_worker_processes | 8 | pg_settings |
| 数据库大小 | 28 GB | pg_database_size |
| 最大表行数 | checklist_responses 1,034,719 行 | COUNT |
| API 单请求延迟 | health 0.15s / TB 0.15s / 报表 0.16s | 和平药房 5 次均值 |
| 后端进程 | 单进程 uvicorn（dev 模式） | start-dev.bat |
| Redis | 单实例 6379 | docker audit-redis |

## 2. 瓶颈分析

### 2.1 数据库连接池（最严格瓶颈）
- 当前 max_connections=200，单进程 uvicorn async 约用 10-20 连接
- 6000 并发 × 每请求 ~0.15s DB 占用 ≈ 需 ~900 个并发连接
- **缺 PgBouncer**：应用直连 PG，连接不可复用跨请求

### 2.2 应用层
- 单进程 uvicorn 无法利用多核
- 无 gunicorn/uvicorn workers 配置
- 事件处理（EventBus）是进程内异步，无跨进程队列

### 2.3 Redis
- 单实例无 Sentinel/Cluster
- 会话 token 和 RLS context 都走 Redis
- 6000 并发下 Redis 单线程可能成瓶颈

### 2.4 前端/反向代理
- 无 Nginx 限流/负载均衡
- Vite dev server 不适合生产

## 3. 前置条件清单

### 3.1 必须项（阻塞 6000 并发）

| # | 改动 | 预计工作量 | 说明 |
|---|------|-----------|------|
| 1 | **PgBouncer 连接池** | 1 天 | `docker-compose.yml` 加 PgBouncer 容器，transaction 模式，pool_size=100，max_client_conn=6000 |
| 2 | **多 worker 进程** | 0.5 天 | `gunicorn -w 4 -k uvicorn.workers.UvicornWorker`（4 核机器 4 worker，每 worker 25 连接 = 100 总连接） |
| 3 | **PG max_connections 提升** | 0.5 天 | 200 → 500（配合 PgBouncer 后实际只需 120 给应用 + 余量给管理/迁移） |
| 4 | **PG shared_buffers 调优** | 0.5 天 | 4GB → 8GB（服务器 RAM 的 25%），effective_cache_size → 24GB |
| 5 | **Nginx 反向代理** | 0.5 天 | 限流 + WebSocket 代理（SSE）+ 静态文件缓存 + gzip |
| 6 | **前端生产构建** | 0.5 天 | `npm run build` + Nginx 托管 dist/（替代 Vite dev server） |

### 3.2 建议项（提升稳定性）

| # | 改动 | 预计工作量 | 说明 |
|---|------|-----------|------|
| 7 | Redis Sentinel | 1 天 | 主从 + 自动故障转移，避免 Redis 单点 |
| 8 | EventBus 改 Celery/SAQ | 2-3 天 | 跨进程任务队列，公式推送/合并推送不再依赖进程内 asyncio.Task |
| 9 | API 响应缓存 | 1 天 | 报表/附注只读端点 Redis 缓存 + stale 失效 |
| 10 | 慢查询优化 | 1-2 天 | checklist_responses（100 万行）的 JOIN 加索引 |

### 3.3 验收项

| # | 验收内容 | 工具 |
|---|---------|------|
| 11 | Locust 压测脚本 | `backend/tests/load_test.py`（已存在，需调整 user 数） |
| 12 | 6000 虚拟用户 × 60s | Locust `--users 6000 --spawn-rate 100` |
| 13 | P95 响应时间 < 2s | Locust 报告 |
| 14 | 错误率 < 1% | Locust 报告 |
| 15 | PG 连接不超限 | `SELECT count(*) FROM pg_stat_activity` |
| 16 | Redis 无 OOM | `redis-cli info memory` |
| 17 | 无数据损坏 | 压测后 TB 恒等式全通过 |

## 4. 推荐实施顺序

```
阶段 1（基础设施，3 天）：
  PgBouncer → 多 worker → Nginx → 前端构建

阶段 2（调优，2 天）：
  PG 参数调优 → Redis Sentinel → 慢查询优化

阶段 3（验收，1 天）：
  Locust 1000 并发 → 3000 并发 → 6000 并发 逐步提升
```

## 5. docker-compose 示例片段

```yaml
services:
  pgbouncer:
    image: edoburu/pgbouncer:latest
    environment:
      DATABASE_URL: postgresql://postgres:postgres@audit-postgres:5432/audit_platform
      POOL_MODE: transaction
      DEFAULT_POOL_SIZE: 100
      MAX_CLIENT_CONN: 6000
    ports:
      - "6432:6432"
    depends_on:
      - audit-postgres

  backend:
    command: >
      gunicorn app.main:app
      -w 4
      -k uvicorn.workers.UvicornWorker
      --bind 0.0.0.0:9980
      --timeout 120
    environment:
      DATABASE_URL: postgresql://postgres:postgres@pgbouncer:6432/audit_platform
```
