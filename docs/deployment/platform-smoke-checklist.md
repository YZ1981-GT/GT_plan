# 平台上线 Smoke Checklist

> 每次部署必须按当前目标环境执行对应检查。三层环境检查逐级递增，不可混用。
>
> 参考：通用发版冒烟见 [`smoke-test-checklist.md`](./smoke-test-checklist.md)

---

## 一、本地开发环境检查

适用场景：开发者本地 `start-dev.bat` 启动后，验证基础服务可用。

### 1.1 后端健康

| # | 检查项 | 命令/URL | 预期结果 | 失败排查 |
|---|--------|----------|----------|----------|
| 1 | Backend 健康端点 | `curl http://localhost:9980/api/health` | 返回 `{"status":"ok"}` HTTP 200 | 检查 uvicorn 是否启动；查看终端错误日志 |
| 2 | Backend 版本端点 | `curl http://localhost:9980/api/version` | 返回版本 JSON | 同上 |

### 1.2 前端健康

| # | 检查项 | 命令/URL | 预期结果 | 失败排查 |
|---|--------|----------|----------|----------|
| 1 | Frontend 可访问 | 浏览器打开 `http://localhost:3030` | 登录页正常渲染 | 检查 vite dev server 是否运行 |
| 2 | 登录链路 | 输入 admin/admin123 | 成功跳转首页 | 检查后端是否启动、CORS 配置 |

### 1.3 OnlyOffice / WOPI

| # | 检查项 | 命令/URL | 预期结果 | 失败排查 |
|---|--------|----------|----------|----------|
| 1 | OnlyOffice 健康（如部署） | `curl http://localhost:8080/healthcheck` | 返回 `true` | 检查 Docker 容器 `onlyoffice` 是否运行 |
| 2 | WOPI 健康端点 | `curl http://localhost:9980/wopi/health` | HTTP 200 | 检查 WOPI 路由注册、OnlyOffice 容器 |

### 1.4 Redis

| # | 检查项 | 命令/URL | 预期结果 | 失败排查 |
|---|--------|----------|----------|----------|
| 1 | Redis PING | `docker exec audit-redis redis-cli PING` | 返回 `PONG` | 检查容器 `audit-redis` 是否运行（端口 6379） |
| 2 | Redis 连接数 | `docker exec audit-redis redis-cli INFO clients` | `connected_clients` ≥ 1 | 检查后端 Redis 配置 |

### 1.5 Postgres

| # | 检查项 | 命令/URL | 预期结果 | 失败排查 |
|---|--------|----------|----------|----------|
| 1 | PG 连接 | `docker exec audit-postgres pg_isready -U postgres` | 返回 accepting connections | 检查容器 `audit-postgres`（端口 5432） |
| 2 | 数据库存在 | `docker exec audit-postgres psql -U postgres -c "\l"` | 列表包含 `audit_platform` | 执行 seed 脚本初始化 |
| 3 | Migration 状态 | 查看启动日志 `MigrationRunner` 输出 | 无 FAILED migration | 检查 `backend/migrations/V*.sql` 语法 |

---

## 二、试点部署环境检查

适用场景：首次部署到试点/Staging 服务器，验证迁移、后台任务、实时通信、降级状态。

> 前置条件：本地环境全部检查项已通过。

### 2.1 数据库迁移

| # | 检查项 | 方法 | 预期结果 | 失败排查 |
|---|--------|------|----------|----------|
| 1 | Migration 全量执行 | 查看应用启动日志 | 所有 V*.sql 按版本号顺序执行成功 | 查看 MigrationRunner 错误；手动执行失败的 SQL |
| 2 | Schema drift 检测 | `python -m pytest backend/tests/test_schema_drift.py` | 0 critical drift | 补齐缺失列（ALTER ADD）或更新 allowlist |
| 3 | 版本号无冲突 | 检查 `backend/migrations/` 目录 | 无重复版本号 | scan_migrations 脚本报错时修复编号 |

### 2.2 Worker 进程

| # | 检查项 | 方法 | 预期结果 | 失败排查 |
|---|--------|------|----------|----------|
| 1 | 异步任务 Worker 存活 | 检查进程列表或 supervisor 状态 | Worker 进程存在且无 crash loop | 查看 Worker 日志、Redis 连接 |
| 2 | 任务队列消费 | `curl http://localhost:9980/api/tasks/stats` | pending 队列无堆积（< 100） | 检查 Worker 是否连接 Redis |
| 3 | 定时任务调度 | 查看 scheduler 日志 | 最近一次定时任务在预期时间执行 | 检查 cron 配置 |

### 2.3 SSE（Server-Sent Events）

| # | 检查项 | 方法 | 预期结果 | 失败排查 |
|---|--------|------|----------|----------|
| 1 | SSE 端点可连接 | `curl -N http://localhost:9980/api/sse/events` | 保持连接，收到心跳 | 检查 SSE 路由注册、Nginx 代理配置 |
| 2 | 多客户端广播 | 两个浏览器标签同时登录 | 一端操作另一端实时收到通知 | 检查 Redis pub/sub 配置 |
| 3 | 断线重连 | 断网后恢复 | 客户端自动重连无数据丢失 | 检查前端 EventSource 重连逻辑 |

### 2.4 Degraded 状态总览

系统在部分组件不可用时应进入 degraded 模式而非完全崩溃。

| # | 组件 | 降级行为 | 检查方法 | 预期 |
|---|------|----------|----------|------|
| 1 | vLLM 不可用 | AI 功能禁用，其余正常 | 停止 vLLM → 访问项目 | 项目可用，AI 按钮灰色/提示 |
| 2 | OnlyOffice 不可用 | 在线编辑禁用，下载编辑可用 | 停止 OnlyOffice 容器 | 底稿下载正常，在线编辑提示不可用 |
| 3 | Redis 不可用 | 缓存穿透到 DB，性能下降但可用 | 停止 Redis 容器 | 页面可加载（慢），无 500 错误 |
| 4 | Embedding 不可用 | 语义搜索降级为 ilike 模糊搜索 | 不启 embedding 实例 | 知识库搜索返回结果（精度降低） |
| 5 | Worker 不可用 | 异步任务排队，同步功能正常 | 停止 Worker 进程 | 导出任务挂起，其余操作正常 |

---

## 三、生产部署环境检查

适用场景：正式上线前/后，验证备份、恢复能力、容量、日志和告警。

> 前置条件：试点环境全部检查项已通过。

### 3.1 备份验证

| # | 检查项 | 方法 | 预期结果 | 失败排查 |
|---|--------|------|----------|----------|
| 1 | PG 全量备份 | `pg_dump -Fc audit_platform > backup.dump` | 文件生成，大小合理 | 检查磁盘空间、PG 连接权限 |
| 2 | Redis RDB 备份 | `redis-cli BGSAVE` + 检查 dump.rdb | `Background saving started` | 检查 Redis 数据目录权限 |
| 3 | 文件存储备份 | 按存储方案执行（本地 rsync / 对象存储 sync） | 备份目录文件数一致 | 检查存储权限和网络 |
| 4 | 备份定时任务 | 检查 crontab / 调度器 | 备份任务按计划执行 | 检查 cron 日志 |

### 3.2 恢复演练

> ⚠️ **恢复演练必须在隔离环境执行，禁止在生产库直接操作。**

| # | 检查项 | 方法 | 预期结果 | 失败排查 |
|---|--------|------|----------|----------|
| 1 | PG 恢复 | `pg_restore -d audit_platform_test backup.dump` | 恢复成功，表数据完整 | 检查目标库是否存在、权限 |
| 2 | 恢复后数据校验 | 对比关键表行数（projects/users/trial_balance） | 行数与备份前一致 | 检查 pg_dump 参数是否含数据 |
| 3 | 恢复后应用启动 | 指向恢复库启动后端 | `/api/health` 返回 ok | 检查连接串、migration 兼容 |
| 4 | RTO 记录 | 记录恢复全流程耗时 | ≤ 目标 RTO（建议 < 30min） | 优化备份粒度或并行恢复 |

### 3.3 容量检查

| # | 检查项 | 方法 | 预期结果 | 失败排查 |
|---|--------|------|----------|----------|
| 1 | 磁盘使用率 | `df -h`（Linux）/ 资源管理器 | 数据盘使用率 < 80% | 清理旧备份/日志；扩容 |
| 2 | PG 数据库大小 | `SELECT pg_database_size('audit_platform')` | 增长趋势可控 | 检查大表、清理历史数据 |
| 3 | Redis 内存 | `redis-cli INFO memory` | `used_memory` < `maxmemory` 80% | 调整 maxmemory 或清理过期 key |
| 4 | 连接池使用 | PgBouncer `SHOW POOLS` | 活跃连接 < 池上限 70% | 扩大连接池或优化长事务 |
| 5 | 文件存储 | 统计上传文件总量 | 增长速率可预测 | 制定归档策略 |

### 3.4 日志检查

| # | 检查项 | 方法 | 预期结果 | 失败排查 |
|---|--------|------|----------|----------|
| 1 | 应用日志可访问 | 查看日志文件或日志收集系统 | 最近日志时间戳 < 5min 前 | 检查日志路径配置、磁盘空间 |
| 2 | 错误日志无异常堆积 | `grep -c ERROR app.log`（近 1h） | ERROR 数 < 阈值（建议 < 50/h） | 定位高频 ERROR 根因 |
| 3 | 慢查询日志 | PG `pg_stat_statements` 或慢查询日志 | 无 > 5s 的常规查询 | 优化 SQL 或加索引 |
| 4 | 日志轮转 | 检查 logrotate 配置 | 日志文件不超过保留天数 | 配置 logrotate |

### 3.5 告警检查

| # | 检查项 | 方法 | 预期结果 | 失败排查 |
|---|--------|------|----------|----------|
| 1 | 健康检查告警 | 模拟后端停机 | 告警通知在 5min 内到达 | 检查监控配置、通知渠道 |
| 2 | 磁盘告警 | 模拟磁盘使用率 > 90% | 收到磁盘告警 | 检查阈值配置 |
| 3 | 错误率告警 | 短时间触发多个 500 | 收到错误率异常通知 | 检查错误率阈值 |
| 4 | 通知渠道验证 | 手动触发测试告警 | 相关人员收到通知 | 检查通知配置（邮件/钉钉/企微） |

---

## 四、恢复演练记录模板

每次恢复演练后填写以下记录，留存备查。

| 字段 | 内容 |
|------|------|
| 演练日期 | |
| 执行人 | |
| 演练环境 | □ 隔离测试环境 □ 灾备环境 |
| 备份时间点 | |
| 备份文件大小 | |
| 恢复开始时间 | |
| 恢复完成时间 | |
| RTO（恢复耗时） | |
| 数据校验结果 | □ 行数一致 □ 关键数据抽检通过 □ 应用启动正常 |
| 发现问题 | |
| 改进措施 | |
| 下次演练计划 | |

---

## 五、签字确认

| 环境 | 检查人 | 日期 | 结果 | 备注 |
|------|--------|------|------|------|
| 本地开发 | | | □ 全部通过 □ 有例外 | |
| 试点部署 | | | □ 全部通过 □ 有例外 | |
| 生产部署 | | | □ 全部通过 □ 有例外 | |

---

## 变更记录

| 日期 | 变更人 | 内容 |
|------|--------|------|
| 2026-06-06 | 初始化 | 新建平台 smoke checklist，覆盖三层环境 |
