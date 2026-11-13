# 合并生命周期 6000 并发容量测试（Task 8.4）

> spec：`consolidation-run-and-workpaper-lifecycle-closure` 批 8 · 任务 8.4（可选 `*`）
> 需求 R10（性能/容量/可观测）、R11.5（6000 并发依赖专用压测环境；代码/脚本/指标/小规模斜率交付，未授权时如实标环境待测）
> 设计 §3 统一运行顺序、§4 API、§6 性能与观测、§7 降级

本套件是**独立容量工具**（不是 Playwright，也不是 pytest PBT），对**合并生命周期热路径**在 6000 VU
下建模，并对结果给出可被 CI 判定的 PASS/FAIL。

## 🔴 6000 VU 实跑状态：代码已改但未实测（需专用环境 + 用户授权）

本任务**只交付脚本/配置/阈值/看板 + 可自验的交付件自测**。真实 6000 VU 压测必须在**专用、可销毁**的压测环境中、
并在**用户显式授权**后才能运行；**不得**对共享开发后端（9980）执行，会干扰并发会话。交付件的正确性由
`test_capacity_tooling.py` 在**不跑 6000 VU** 的前提下验证。

## 文件

| 文件 | 内容 |
|---|---|
| `scenario.py` | 唯一真源：流量模型、SLO 表（p50/p95/p99）、梯度、chaos 注入点、canary/重复幂等不变量。可 `python -m ... scenario` 重写 `scenario.json`。 |
| `connection_budget.py` | PgBouncer 事务池 + 三类服务池（api_read/sse_longpoll/operation_worker）PG 连接预算与不变量。 |
| `chaos.py` | redis/worker/db 故障注入点与 fail-closed（不伪装 succeeded、不降级无版本旧计算）判定。 |
| `capacity_report.py` | 机器可读报告模型 + 生成器 + p50/p95/p99 SLO / 错误率 / 吞吐下限 / 泄露 / 重复阈值判定（纯函数）。 |
| `locustfile_consol_capacity.py` | Locust 压测主体：加权热路径 + StepLoadShape（30 分稳态 + 10 分 burst）+ canary + 停机写报告。 |
| `run_capacity.py` | `plan`（任何环境可跑，校验+写 scenario.json+chaos 时间线）/ `run`（预检预算后 exec locust）。 |
| `pgbouncer.capacity.ini` | 专用压测环境 PgBouncer 事务池配置（与 docker-compose.yml 一致）。 |
| `test_capacity_tooling.py` | 交付件自测（不跑 6000 VU）。 |

## 热路径流量模型（`scenario.TRAFFIC_MODEL`）

对应设计 §3 统一运行顺序 + §4 API：合并场景在规模上以**读**为主（打开工作台 / readiness / 抵销后投影），
小比例触发并轮询持久 operation，极小比例创建手工诊断快照。

| 权重 | 类别 | 端点（真实） |
|---:|---|---|
| 45% | 打开合并工作台 | `GET /api/consolidation/readiness/{pid}/{year}`、`GET /api/consolidation/{pid}/{year}/operations`、`GET /api/consolidation/trial?project_id=&year=` |
| 25% | 角色视图 + 抵销后投影 | `GET /api/consolidation/readiness/{pid}/{year}/role-views`、`GET /api/consolidation/post-elimination/{pid}/{year}` |
| 18% | operation 状态轮询 | `GET /api/consolidation/{pid}/{year}/operations/{id}` |
| 9% | 触发一键刷新 operation | `POST /api/consolidation/{pid}/{year}/operations`（默认关，专用库 + `CONSOL_CAP_ALLOW_TRIGGER=1` 才开） |
| 3% | 手工诊断快照 | `POST /api/consolidation/{pid}/snapshots?year=&reason=manual`（默认关，`CONSOL_CAP_ALLOW_SNAPSHOT=1` 才开） |

canary 用户以本项目身份读**其他项目** readiness，任一非 403/404 即计泄露（必须 0）。

## 阈值（CI 可判定，`capacity_report.generate_report`）

### 逐操作 SLO（p50/p95/p99，`scenario.SLO_TABLE`）

| 操作 | p50 | p95 | p99 | 口径 |
|---|---:|---:|---:|---|
| readiness | 120 | 300 | 1000 | 七域五态；复用证据 readiness，不在请求内重算 |
| role_views | 150 | 400 | 1200 | 角色视图聚合待办 |
| post_elimination | 150 | 400 | 1200 | 四表抵销后 canonical projection；一次预载/递归 CTE |
| trial_read | 120 | 300 | 1000 | 合并试算只读五列；读 `consol_report_values` |
| operation_list | 100 | 250 | 800 | operation 列表（默认 limit<=50） |
| operation_status | 80 | 200 | 500 | 单 operation 状态/步骤/metrics；回执 1 秒内（R10.4） |
| operation_create | 300 | 1000 | 3000 | 创建/合并持久 operation；只持久+入队，返回 operation_id |
| manual_snapshot | 500 | 2000 | 5000 | 手工诊断快照；序列化分片+hash，允许 partial，只 flush 一次 |

> 单位毫秒。设计 §6 明确「具体毫秒 SLO 在 10/100/500 节点基线后确定」——这些预算是任务 8.1 斜率基线后的验收目标，
> 可随真实专用环境基线调整（改 `scenario.SLO_TABLE` 一处，报告/测试/harness 全读它）。

### 全局阈值（`scenario.ACCEPTANCE`）

- 全场景错误率 **< 1%**（HTTP 失败）。
- 稳态吞吐 **≥ 1200 rps**（6000 VU / ~5s 平均循环；低于此即系统基本停摆，哪怕少量完成请求看着快也判失败）。
- 跨项目 canary 泄露 **= 0**。
- 同幂等键重复 operation 副作用 **= 0**（一个幂等键只能产生一个 operation）。
- backpressure 下丢失的已持久 operation **= 0**（R4.3/R4.5：不得永久 running / 伪装成功）。
- chaos（redis/worker/db 故障窗口）下**无**伪 succeeded / 无版本旧计算，且已发布结果不被改写，未受影响路径仍在 SLO 内。
- PG/PgBouncer 连接预算不变量成立（事务池 + `服务预算+ops_reserve < max_connections` + ≥20% 管理/恢复保留 + worker 池不随 VU 增长）。

## 看板 / 指标采集（复用现有可观测层）

本套件**不新建**看板栈，复用平台已有可观测层：

1. **逐操作 SLO 曲线**：Locust `--csv <prefix>` 产出 `*_stats.csv` / `*_stats_history.csv`（逐秒），
   `locustfile_consol_capacity.py` 在停机时把每个 `slo:<op>` 的 p50/p95/p99 写进 `capacity_report_latest.json`
   （判定唯一来源，与 README 阈值逐项对齐）。
2. **服务端资源**：复用 `backend/tests/load/capacity_resource_sampler.py` 每 15 秒采集 `/api/health` 与 `/metrics`
   （`render_platform_metrics` 暴露 DB 连接池 checked-out/overflow、事件循环延迟、平台任务队列），以及 PgBouncer
   `SHOW POOLS` / `SHOW STATS`（`pgbouncer.capacity.ini` 已开 `stats_period=15` + stats 用户），落 `resource_samples.json`。
   读不到记 `error`，不写 0。
3. **Grafana/Metabase（可选）**：平台已挂 Metabase（`audit-metabase:3000`）。专用环境把 `/metrics` 接 Prometheus 后，
   用下述面板规格即可（纯文档规格，不含凭据）：

   ```jsonc
   // Grafana dashboard 规格（panels 对应 /metrics 指标名 + capacity_report 字段）
   {
     "title": "合并生命周期 6000VU 容量",
     "panels": [
       {"title": "逐操作 p95", "targets": ["slo_op_p95_ms{op=~\"readiness|post_elimination|operation_status\"}"], "threshold_from": "scenario.SLO_TABLE"},
       {"title": "全场景错误率", "targets": ["error_rate_pct"], "threshold": 1.0},
       {"title": "吞吐 rps", "targets": ["throughput_rps"], "threshold": 1200},
       {"title": "DB 连接池 checked-out/overflow", "targets": ["db_pool_checked_out", "db_pool_overflow"]},
       {"title": "事件循环延迟", "targets": ["event_loop_lag_seconds"]},
       {"title": "PgBouncer 池等待/客户端连接", "targets": ["pgbouncer_pools_cl_waiting", "pgbouncer_pools_sv_active"]},
       {"title": "backpressure 429 / 泄露 / 重复 operation / 丢失 operation", "targets": ["backpressure_429_count", "cross_project_leakage", "duplicate_operation_effects", "lost_persisted_operations"]}
     ]
   }
   ```

   `summary.json` / `capacity_report_latest.json` 里的字段名与上面 panel target 一一对应，可直接驱动看板或导入 Metabase。

## 执行

### 1) plan（任何环境可跑，交付件自证连贯——不跑 6000 VU）

```powershell
python -m tests.load.consolidation_lifecycle_capacity.run_capacity plan
```

校验 scenario、连接预算不变量，重写 `scenario.json`，打印 chaos 时间线。预算不变量不成立即退出码 1。

### 2) run（🔴 需专用、可销毁的压测环境 + 用户显式授权）

先确认：

- 目标 `--host` 指向**专用容量后端**（独立库 `gt_capacity`，经 `pgbouncer.capacity.ini` 的 6432 前置），
  **不是** 共享 9980、不是 `audit_platform` / `postgres` / `gt_plan` / `metabase`。
- 后端以 `DB_USE_PGBOUNCER=true` 启动（asyncpg NullPool + `statement_cache_size=0`，见 `backend/app/core/database.py`）。
- 账号/项目为容量专用，`CONSOL_CAP_PROJECT_ID` 是名称含「【测试】」的合并集团；`CONSOL_CAP_FOREIGN_PROJECT_ID`
  是另一不属于该账号的合并项目（canary）。
- 写/计算场景默认关闭；只有在可销毁库才设 `CONSOL_CAP_ALLOW_TRIGGER=1` / `CONSOL_CAP_ALLOW_SNAPSHOT=1`。

安装 locust（仅在压测机，**不要**装进跑 pytest 的环境——`import locust` 会 `gevent.monkey.patch_all()` 卡死 pytest，
见 `backend/tests/conftest.py` 顶部说明）：

```powershell
pip install locust
```

授权后实跑命令（cwd = `backend`）：

```powershell
$env:CONSOL_CAP_PROJECT_ID="<【测试】合并集团 project uuid>"
$env:CONSOL_CAP_YEAR="2025"
$env:CONSOL_CAP_FOREIGN_PROJECT_ID="<另一合并项目 uuid（canary）>"
$env:CONSOL_CAP_ENV="capacity"
# 可销毁库才开：
# $env:CONSOL_CAP_ALLOW_TRIGGER="1"
# $env:CONSOL_CAP_ALLOW_SNAPSHOT="1"
python -m tests.load.consolidation_lifecycle_capacity.run_capacity run --host http://<capacity-host>:9980
```

或直接用 locust（带 CSV 曲线归档）：

```powershell
locust -f tests/load/consolidation_lifecycle_capacity/locustfile_consol_capacity.py `
  --host http://<capacity-host>:9980 --headless --autostart `
  --csv tmp_capacity_evidence/consol_run_YYYYMMDD/locust
```

同时在压测机另起资源采样（设计 §6 服务端指标）：

```powershell
python tests/load/capacity_resource_sampler.py --host http://<capacity-host>:9980 `
  --interval 15 --out tmp_capacity_evidence/consol_run_YYYYMMDD/resource_samples.json
```

chaos 窗口按 `plan` 输出的时间线，在目标部署里切 `CONSOL_CHAOS_REDIS` / `CONSOL_CHAOS_WORKER` / `CONSOL_CHAOS_DB`。

### 判定

停机时 harness 写 `capacity_report_latest.json`（或 `CONSOL_CAP_REPORT_PATH`）。`passed=true` 当且仅当上面所有阈值全满足；
`failures[]` 列出每条未达标项。

> **禁止伪造验收**：本地小并发、mock、空 CSV 或只读 smoke 都不能外推为 6000 VU 通过。正式验收须提交同一运行目录下的
> 原始 CSV、`capacity_report_latest.json`、`resource_samples.json` 以及 PG/Redis/事件循环观测快照。

## 自测（交付件验证，不跑 6000 VU）

```powershell
python -m pytest tests/load/consolidation_lifecycle_capacity/test_capacity_tooling.py -p no:playwright
```

验证 scenario 完整性、SLO 的 p50<=p95<=p99、连接预算不变量、报告生成器 PASS/FAIL 逻辑、chaos fail-closed 判定。
不 `import locust`（否则 gevent 猴子补丁会卡死 pytest）。
