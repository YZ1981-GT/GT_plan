"""平台容量正式验收合同（E5/E6 单一来源）。

同一份常量同时由 Locust ``StepLoadShape``、runner 判定器、报告和测试读取，避免
「脚本跑 5 分钟、spec 写 30 分钟」「报告写 p99≤1s、overall_pass 却不检查」的漂移。
"""
from __future__ import annotations

# E5：严格阶段；500 VU 不再作为正式阶段。6000 VU 稳态必须 30 分钟。
LOAD_STAGES: tuple[dict[str, int | str], ...] = (
    {"label": "Stage 1", "users": 100, "spawn_rate": 20, "duration": 60},
    {"label": "Stage 2", "users": 1000, "spawn_rate": 100, "duration": 120},
    {"label": "Stage 3", "users": 3000, "spawn_rate": 200, "duration": 180},
    {"label": "Stage 4", "users": 6000, "spawn_rate": 300, "duration": 1800},
)

# E6：核心读性能与错误率。
CORE_READ_P95_MS = 300.0
CORE_READ_P99_MS = 1000.0
CORE_ERROR_RATE_PCT = 0.1
ALL_SCENARIO_ERROR_RATE_PCT = 1.0

# Locust 的稳定 metric name（不能用具体 UUID）。
CORE_READ_ENDPOINTS: tuple[str, ...] = (
    "/api/projects/{pid}/trial-balance",
    "/api/projects/{pid}/working-papers",
    "/api/projects/{pid}/ledger/window/{account_code}",
)

# E6：正式报告必须由外部不变量探针提供这六项，缺项同样 fail-closed。
SAFETY_ZERO_KEYS: tuple[str, ...] = (
    "unauthorized_successes",
    "connection_leaks",
    "connection_timeouts",
    "event_loss",
    "duplicate_side_effects",
    "data_corruption",
)

# 稳态窗口：标称加压结束后再等 5 秒才开始计入，避开派生尾巴；覆盖时长允许 2 秒调度抖动。
STEADY_SETTLE_SECONDS = 5.0
STEADY_COVERAGE_TOLERANCE_SECONDS = 2.0

ESTIMATED_TOTAL_SECONDS = int(sum(
    float(stage["users"]) / float(stage["spawn_rate"]) + float(stage["duration"])
    for stage in LOAD_STAGES
))
