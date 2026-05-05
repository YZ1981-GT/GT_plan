# Background Workers

本目录下的每个模块导出 `async def run(stop_event: asyncio.Event)`，由
`app/main.py` lifespan 的 `_start_workers` 统一编排启动。

## 模块清单

| Worker | 职责 | 多副本安全 |
| --- | --- | --- |
| `sla_worker` | 扫描 SLA 超时告警 | ✅（幂等查询）|
| `import_recover_worker` | 导入任务恢复（进程崩溃重启后续跑） | ✅（行级锁/状态 CAS）|
| `import_worker` | 账套导入执行器 | ✅（状态 CAS）|
| `outbox_replay_worker` | ImportEventOutbox 事件重试发布 | ✅（幂等）|
| `audit_log_writer_worker` | 审计日志批量落库 + 哈希链 | ⚠️ 见下方约束 |

## 审计日志 Writer 单副本约束（R1 硬约束）

`audit_log_writer_worker._write_batch` 按 `project_id` 分组计算哈希链，每组内
顺序依赖 `prev_hash` → `entry_hash`。当多个 worker 副本并发写同一 `project_id`
时，会出现以下 race：

1. Worker A 读到 prev_hash = H0
2. Worker B 同时读到 prev_hash = H0
3. A 计算 entry_hash = HA 写入 → 当前链尾 = HA
4. B 计算 entry_hash = HB（也基于 H0）写入 → 链断：HB.prev_hash = H0 ≠ HA

### 解决方案（双保险）

**方案 1：PG advisory transaction lock（代码层，已实现）**

`_write_batch` 内按 project_id 分组循环前调用
`SELECT pg_advisory_xact_lock(hash(project_id) & 0x7FFFFFFFFFFFFFFF)`，事务
提交/回滚时自动释放。这会将同一 project_id 的并发写入强制串行化。

- ✅ 有效范围：同一 PostgreSQL 实例下的多 worker 副本
- ❌ 无效范围：跨 PG 实例（如读写分离）、SQLite 测试环境
- ⚠️ 代价：高并发场景下 TPS 退化到串行（~10 tps/project）

**方案 2：运维约束（部署层，必须配合）**

生产环境 `audit_log_writer_worker` **必须且只能部署单副本**。具体做法：

- Docker Compose：`deploy.replicas: 1`（且不要 swarm 模式下横向扩容）
- Kubernetes：`Deployment.replicas: 1` + `strategy.type: Recreate`（避免滚动升级期间双实例）
- 进程管理器：systemd 单 unit、supervisord 单 program

### SQLite 测试环境

SQLite 不支持 `pg_advisory_xact_lock`，`_write_batch` 会感知 `DATABASE_URL`
前缀并跳过 advisory lock；测试套件单进程运行，不需要跨 worker 串行。
