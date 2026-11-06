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
# 正式验收请显式指定可归档路径，并保留 locust_*.csv、summary.json 和 Markdown 摘要。
python tests/load/run_final.py --host http://127.0.0.1:9980 --evidence-dir tmp_capacity_evidence/run_20261106
```

报告只有在 100/500/1000/3000/6000 五个阶段均达到至少 90% 目标并发且请求样本大于 0 时，才允许进入性能指标判定。任一阶段缺失或零样本时脚本退出码为 2，不能用 `0ms` 判为 PASS。

> **禁止伪造验收**：本地小并发、mock、空 CSV 或只读 smoke 都不能外推为 6000 VU 通过。正式 E5/E6
> 必须提交同一运行目录下的原始 CSV、`summary.json`、Markdown 报告，以及 PG/Redis/RSS/event-loop
> 观测快照。
