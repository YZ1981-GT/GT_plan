# 6000 并发容量测试

该套件只允许使用 seed 回执中的真实 UUID 和专用账号池。默认只读，不得指向共享生产或开发库执行写场景。

## 配置

账号与场景可直接传 JSON，也可传 UTF-8 JSON 文件，两种方式只能选一种：

```powershell
$env:GT_LOAD_ACCOUNTS_FILE="C:/capacity/accounts.json"
$env:GT_LOAD_SCENARIOS_FILE="C:/capacity/scenarios.json"
```

`accounts.json`：

```json
[{"username":"load-001","password":"从密钥管理器注入"}]
```

`scenarios.json`：

```json
[{"project_id":"00000000-0000-0000-0000-000000000001","workpaper_id":"00000000-0000-0000-0000-000000000002","year":2025,"account_code":"1001"}]
```

写场景默认关闭。只在可销毁数据库中同时设置：

```powershell
$env:GT_LOAD_ALLOW_WRITES="1"
$env:GT_LOAD_DISPOSABLE_ENV="YES"
# 必填：被压后端实际连接的专用库，且不得等于 DATABASE_URL / audit_platform / postgres / gt_plan / metabase
$env:GT_LOAD_DISPOSABLE_DB_URL="postgresql+asyncpg://capacity:***@capacity-db:5432/gt_capacity_202611"
```

`run_final.py` / `run_baseline.py` 和 `locustfile.py` 都会在**发出任何请求前**校验这三项；
任一缺失、指向共享/默认库、或与运行库同名即退出码 2。只读压测不需要这三项。

`pytest -m perf` 中含 `pg_only` 的性能用例也会写大规模测试数据。它们只能在专用库运行：

```powershell
$env:GT_PERF_DISPOSABLE_DB="YES"
python -m pytest -m perf
```

若只想跑不连数据库的性能用例，使用 `python -m pytest -m "perf and not pg_only"`。

## 执行与判定

```powershell
# evidence-dir 必须是本次运行独有目录；默认写入仓库根 tmp_capacity_evidence/（已 gitignore）。
# 正式验收请显式指定可归档路径，整个目录原样归档。
python tests/load/run_final.py --host http://127.0.0.1:9980 `
  --evidence-dir tmp_capacity_evidence/run_20261106 `
  --safety-evidence C:/capacity/safety_20261106.json `
  --baseline tmp_capacity_evidence/run_20261101/summary.json
```

正式梯度、阈值和安全键只有一份来源：`load_contract.py`（Locust 形状、判定器、报告和测试都读它）。

- **梯度（E5）**：100 → 1000 → 3000 → 6000 VU，各阶段稳态 60 / 120 / 180 / **1800** 秒；
  加上按 spawn rate 计的加压时间，总时长约 37 分钟。500 VU 不再是正式阶段。
- **稳态窗口**：每阶段从标称加压结束后 5 秒开始计入，到该阶段结束为止。`locustfile.py` 在
  `events.request` 上把窗口内的每个请求记进直方图，结束时写 `stage_stats.json`（原始桶计数，
  可复算分位）。`locust_stats_history.csv` 只作曲线归档、**不参与判定**：开了
  `--csv-full-history` 后它的分位列是最近约 10 秒的滚动值、计数列却是全程累计，任何一行都代表不了
  某个阶段的 30 分钟稳态分布。
- **样本完整**：四个阶段都要有请求样本；窗口内观测到的最低并发 ≥ 目标的 90%；稳态覆盖时长按合同
  现算（不读证据文件自报），允许 2 秒调度抖动。`stage_stats.json` 缺失或被改（桶计数与请求数不符）
  一律判失败。
- **核心读 SLO（E6）**：6000 VU 稳态窗口内，`trial-balance`、`working-papers`、
  `ledger/window/{account_code}` 三个端点逐个满足 p95 ≤ 300ms、p99 ≤ 1s、错误率 < 0.1%；
  任一端点没有样本即失败，缺分位按无穷大处理。
- **全场景错误率**：全程聚合与 6000 稳态窗口取较差值，必须 < 1%。
- **安全与完整性**：`--safety-evidence` 必须提供下面六个键且全为 0；不提供、缺键、多出未知键、
  负数或非数字都判失败：

```json
{"safety": {"unauthorized_successes": 0, "connection_leaks": 0, "connection_timeouts": 0,
            "event_loss": 0, "duplicate_side_effects": 0, "data_corruption": 0}}
```

  这些计数来自压测之外的不变量探针（越权回放、连接池指标、事件序号对账、幂等键重复、业务恒等式），
  runner 只校验与判定，不代为生成。
- **A/B（0.1）**：`--baseline` 指向上一轮 `run_final.py` 的 `summary.json`；路径不存在或不是该格式时
  runner 在发压前退出。对比按聚合、同名端点、同并发阶段逐项给出差值，只写进报告和 summary，
  不参与 PASS。`business_hashes` 目前没有生产者，相等性显示为 `None`。
- **退出码**：PASS 为 0；任何一项失败、闸门拒绝或外部证据无效为 2。

运行目录里的文件：

| 文件 | 内容 |
|---|---|
| `locust_stats.csv` / `locust_failures.csv` / `locust_exceptions.csv` | Locust 全程聚合、失败与异常 |
| `locust_stats_history.csv` | 逐秒曲线（只归档，不判定） |
| `stage_stats.json` | 稳态窗口直方图，判定的唯一阶段来源 |
| `resource_samples.json` | 每 15 秒一份 `/api/health`、`/metrics`（连接池 / 事件循环 / 平台任务等前缀）与负载机 CPU / 内存；读不到记 `error`，不写 0 |
| `summary.json` | 统计、判定、A/B 对比与上述文件清单；严格 JSON（无穷大写成 `null`），可直接作下一轮 `--baseline` |

Markdown 报告写到 `--output`（默认 `tests/load/final_report.md`）。

当前仍是**单个 Locust 进程**：6000 VU 在一台负载机上可能先打满负载机 CPU。分布式负载机（E4）需要把
各 worker 的 `stage_stats.json` 同阶段同端点同桶计数相加后再判定，这一步尚未实现。PG / Redis / WAL /
RSS 等服务端指标只有在容量环境把它们接进 `/metrics` 或单独采集后才有，`resource_samples.json` 不代替它们。

`run_baseline.py` 是早期的 100 用户 / 60 秒冒烟脚本（跑完删 CSV、阈值仍是旧口径），不能作为 A/B 基线；
基线一律用 `run_final.py` 产出的 `summary.json`。

> **禁止伪造验收**：本地小并发、mock、空 CSV 或只读 smoke 都不能外推为 6000 VU 通过。正式 E5/E6
> 必须提交同一运行目录下的原始 CSV、`summary.json`、Markdown 报告，以及 PG/Redis/RSS/event-loop
> 观测快照。
