# Evidence Governance — 6000 VU 容量与 Chaos 场景工具

Spec: `attachment-ocr-ai-evidence-governance-hardening` · Task 8.2 · _Requirements: R12, R15_
Design 基线: §9.1（6000 VU 容量模型 + SLO 表）、§9.2（队列背压 + PG/PgBouncer 配额）、§10.2（第 6 层 `capacity/chaos` 独立工具）。

> 这是 design §10.2 明确要求的**独立容量/chaos 工具**——不是 Playwright，也不是 pytest PBT。
> Playwright 只证明用户可见边界；PG/约束/并发由 PG integration 与 PBT 证明；6000 VU 由本工具证明。

## 组成

| 文件 | 职责 |
|------|------|
| `scenario.py` | 唯一真源：载荷曲线（30 分钟稳态 + 10 分钟突发）、流量模型（70/20/7/3）、§9.1 SLO 表、全局验收阈值、chaos 故障点、canary 定义。可 `write_scenario_json()` 导出 `scenario.json`。 |
| `connection_budget.py` | PgBouncer transaction pooling + 分池连接预算 + 不变式（`总预算 + 运维保留 < max_connections` 且管理/恢复保留 ≥ 20%）。 |
| `chaos.py` | storage/OCR/retrieval/AI 故障注入点、突发窗口内交错调度、fail-closed / 无禁用终态 / 隔离性的纯断言。 |
| `capacity_report.py` | 机器可读容量报告 schema + 生成器 + SLO/错误率/泄露/重复副作用/背压/预算阈值断言（纯函数）。 |
| `locustfile_evidence_capacity.py` | Locust 压测 harness：编码 70/20/7/3 流量、`StepLoadShape` 曲线、跨项目 canary、自定义计数器；结束时产出报告 JSON。 |
| `run_capacity.py` | 编排入口：`plan`（校验 + 导出场景 + chaos 时间线，随处可跑）/ `run`（预检预算后 headless 跑 locust）。 |

## 验收契约（design §9.1）

- 6000 并发虚拟用户，30 分钟稳态 + 10 分钟突发（突发在稳态之上 +20% 压背压）。
- 流量模型：70% 元数据读 / 20% 写关联 / 7% OCR-AI 入队 / 3% 影响-归档控制。
- 错误率 < 1%，跨项目 canary 泄露 = 0，重复副作用 = 0。
- SLO P95：元数据读 ≤200ms / cursor 列表 ≤300ms / ≤100 节点影响 ≤500ms / 治理写 ≤500ms / staged 入队 ≤300ms / 同步 finalize ≤1s / finalize 外部任务 ≤30s / preflight ≤750ms / stale 入队 ≤200ms / archive 请求 ≤500ms。
- 背压：soft limit → 降速；hard limit → 429；**已持久 job 不丢失**。
- Chaos：storage/OCR/retrieval/AI 故障 → 降级、fail-closed（不产生 confirmed/written_back/archived 终态）、既有业务数据不变、未受影响路径仍在 SLO 内。

## 用法

### 1. 校验场景 + 导出 chaos 时间线（随处可跑，无需容量环境）

```
python -m tests.load.evidence_governance_capacity.run_capacity plan
```

`cwd` = `backend`。输出：`scenario.json`、连接预算检查、机器可读 chaos 切换时间线（`EVIDENCE_CHAOS_*` 环境开关 + 起止偏移）。预算不满足不变式即以非零码退出（阻断跑测）。

### 2. 真实 6000 VU 压测（需专用容量环境）

> ⚠️ 禁止对开发库跑。需独立容量环境 + 大数据 PG + PgBouncer transaction pooling。本仓库不提供伪造的 6000 VU 结果。

先配置环境变量（指向容量环境）：

```
EVID_CAP_USER=<user>
EVID_CAP_PASSWORD=<pwd>
EVID_CAP_PROJECT_ID=<主项目 id>
EVID_CAP_YEAR=2025
EVID_CAP_FOREIGN_PROJECT_ID=<另一项目 id，用于 canary 泄露探针>
EVID_CAP_ATTACHMENT_VERSION_ID=<用于 OCR 入队的版本 id>
EVID_CAP_REPORT_PATH=<报告输出路径>
```

再执行：

```
python -m tests.load.evidence_governance_capacity.run_capacity run --host http://<capacity-host>:9980
```

或直接用 locust：

```
locust -f tests/load/evidence_governance_capacity/locustfile_evidence_capacity.py --host http://<capacity-host>:9980 --headless --autostart
```

`StepLoadShape` 自动按 `scenario.LOAD_PROFILE` 加压：warmup 1k→3k → 稳态 6k（30 min）→ 突发 7.2k（10 min）。结束时 harness 调用 `capacity_report.generate_report` 写出机器可读报告 JSON（含每项 SLO pass/fail、错误率、泄露数、重复副作用、背压 429、chaos 结果、连接预算检查、总 `passed` 判定）。

### 3. Chaos 故障注入调度

`plan` 输出的 `chaos_timeline` 给出每个依赖故障的 `env_key`（如 `EVIDENCE_CHAOS_OCR=timeout`）与相对突发开始的起止偏移。容量环境的 chaos 中间件/feature flag 按该时间线在突发窗口内**交错**开启各依赖故障（不同时），以便归因降级与隔离性。harness 只调度与观测，不改动生产接线。

## 报告消费

报告 JSON 顶层 `passed` 为总判定；`failures` 列出每条违约（SLO 超标、错误率、泄露、重复副作用、丢 job、chaos 未 fail-closed、预算越界）。发布门（Task 11.4）按此 JSON 校验 6000 VU 证据。
