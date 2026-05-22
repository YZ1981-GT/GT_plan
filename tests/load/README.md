# 压力测试（Locust）

## 概述

使用 [Locust](https://locust.io/) 对审计平台后端 API 进行压力测试，验证 6000 并发用户下系统性能是否达标。

## 环境准备

```bash
# 安装 locust（已包含在 backend/requirements.txt）
pip install locust
```

## 运行方式

### Web UI 模式（推荐）

```bash
locust -f tests/load/locustfile.py --host=http://localhost:9980
```

启动后访问 http://localhost:8089 打开 Locust Web UI，设置并发用户数和加压速率。

### 无头模式（CI/自动化）

```bash
locust -f tests/load/locustfile.py --host=http://localhost:9980 --headless -u 100 -r 10 --run-time 60s
```

参数说明：
- `-u 100`：总并发用户数
- `-r 10`：每秒新增用户数（加压速率）
- `--run-time 60s`：运行时长

### 梯度加压 — 自动模式（LoadTestShape）

直接运行即可，`StepLoadShape` 会自动按阶段加压：

```bash
locust -f tests/load/locustfile.py --host=http://localhost:9980 --headless
```

脚本内置 `StepLoadShape` 类自动控制梯度：

| 阶段 | 并发用户 | 加压速率 | 稳定持续时间 | 观察重点 |
|------|---------|---------|-------------|---------|
| 1 | 100 | 20/s | 60s | 基线响应时间 |
| 2 | 500 | 50/s | 120s | 连接池压力 |
| 3 | 1000 | 100/s | 120s | DB 查询瓶颈 |
| 4 | 3000 | 200/s | 180s | 内存/CPU 瓶颈 |
| 5 | 6000 | 300/s | 300s | 目标并发验证 |

如需自定义阶段参数，编辑 `locustfile.py` 中的 `LOAD_STAGES` 常量。

### 梯度加压 — 手动模式

不使用 LoadTestShape，手动指定用户数（适合调试单阶段）：

```bash
locust -f tests/load/locustfile.py --host=http://localhost:9980 --headless -u 500 -r 50 --run-time 120s
```

注意：手动模式下 `StepLoadShape` 会被忽略（Locust 优先使用命令行参数覆盖 shape）。

## 压测场景

| 场景 | 权重 | 说明 | 响应验证 |
|------|------|------|---------|
| 登录 | 1 | POST /api/auth/login | 200 + access_token 存在 |
| 查询试算表 | 3 | GET /api/projects/{pid}/trial-balance | 200 |
| 查询底稿列表 | 2 | GET /api/projects/{pid}/workpapers | 200 |
| 编辑保存底稿 | 1 | GET + PUT /api/projects/{pid}/workpapers/{wid} | GET 200 + PUT 200/204/409 |
| 穿透查询 | 2 | GET /api/projects/{pid}/drilldown?account_code=1001 | 200 |

### 场景 4 详细说明

编辑保存底稿场景模拟真实用户操作流程：
1. **GET** 读取底稿当前数据
2. **PUT** 提交修改后的 JSON payload（含 cells_modified 数组）

PUT 返回 409（版本冲突）视为正常业务场景（乐观锁），不计入错误。

## 达标指标

| 指标 | 目标值 |
|------|--------|
| P95 响应时间 | ≤ 2s |
| P99 响应时间 | ≤ 5s |
| 错误率 | < 0.1% |
| 吞吐量 (RPS) | 根据基线确定 |

## 报告输出

- 基线报告：`tests/load/baseline_report.md`
- 最终报告：`tests/load/final_report.md`

## 注意事项

1. 压测前确保后端服务已启动（端口 9980）
2. 确保数据库中有测试项目数据（PROJECT_ID=1）
3. 压测会产生大量请求，建议在独立环境执行，避免影响开发数据库
4. 如需修改测试项目 ID，编辑 `locustfile.py` 中的 `PROJECT_ID` 变量
