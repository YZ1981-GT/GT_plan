"""Consolidation lifecycle capacity scenario definition (machine-readable).

Spec: consolidation-run-and-workpaper-lifecycle-closure — Task 8.4
Requirements: R10 (performance/observability/capacity), R11.5 (6000 VU 依赖专用
环境；代码/脚本/指标/小规模斜率交付，未授权时如实标环境待测).
Design: §6 (性能与观测), §3 (统一运行顺序), §4 (API 与兼容).

This module is the single source of truth for the 6000 VU consolidation
lifecycle capacity scenario. It defines:

* the 6000 VU load profile — 30 min steady state + 10 min burst;
* the traffic model weighted on the consolidation lifecycle hot paths
  (open workbench read / operation trigger+poll / readiness+role-views /
  post-elimination read / manual snapshot);
* the SLO table (p50/p95/p99 latency budgets) keyed by logical operation;
* the global acceptance thresholds (error rate, throughput floor,
  cross-project leakage == 0, duplicate operation side-effects == 0,
  no lost persisted operation under backpressure);
* chaos fault-injection points (redis/worker/db) and the fail-closed
  degradation contract for a persistent ``consol_operation``.

Everything is plain dataclasses so it serialises to JSON (``scenario.json``)
and is consumed by the Locust harness, the report generator and the threshold
assertions. Nothing here performs I/O or fakes a run.

The actual 6000 VU run requires a dedicated capacity environment and explicit
authorization; see README.md. This file is a *deliverable* — it is verified by
``test_capacity_tooling.py`` WITHOUT running 6000 VU.
"""

from __future__ import annotations

import dataclasses
import json
from dataclasses import dataclass
from pathlib import Path


# ---------------------------------------------------------------------------
# Load profile — design §6 capacity target: 6000 VU, 30 min steady + 10 min burst
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class LoadPhase:
    """One phase of the ramped load profile."""

    name: str
    users: int
    spawn_rate: int  # users/second
    duration_s: int  # steady duration held at ``users`` after ramp
    kind: str  # "warmup" | "steady" | "burst"


# Steady state runs at the 6000 VU target for 30 minutes, then a 10 minute burst
# pushes 20% above target to prove operation backpressure (queued persists,
# hard overload -> 429) without losing a persisted ``consol_operation``
# (design R4.3/R4.5: "进程重启后不得永久 running"; "下游失败不得伪装整体成功").
# Warmup phases only exist to reach the target; their SLO samples are excluded
# from the pass/fail window.
LOAD_PROFILE: tuple[LoadPhase, ...] = (
    LoadPhase(name="warmup-1k", users=1000, spawn_rate=100, duration_s=120, kind="warmup"),
    LoadPhase(name="warmup-3k", users=3000, spawn_rate=200, duration_s=120, kind="warmup"),
    LoadPhase(name="steady-6k", users=6000, spawn_rate=300, duration_s=1800, kind="steady"),
    LoadPhase(name="burst-7.2k", users=7200, spawn_rate=400, duration_s=600, kind="burst"),
)

STEADY_STATE_SECONDS = 30 * 60
BURST_SECONDS = 10 * 60
TARGET_VIRTUAL_USERS = 6000


# ---------------------------------------------------------------------------
# Traffic model — consolidation lifecycle hot paths
# ---------------------------------------------------------------------------
# Modeled on the §3 unified run order and §4 API surface. At scale the dominant
# traffic is *reads* of an existing published consolidation (workbench open,
# readiness, post-elimination projection), with a smaller share triggering and
# polling a persistent operation, and an even smaller share creating a manual
# diagnostic snapshot. Weights are tuned so the heavy write/compute path
# (refresh-all operation) is exercised at realistic ratio without turning the
# run into a pure write storm (which a real 6000-user interactive population
# never is).

@dataclass(frozen=True)
class TrafficClass:
    """A weighted class of user behaviour mapped to logical SLO ops."""

    name: str
    weight_pct: int
    description: str
    slo_ops: tuple[str, ...]


TRAFFIC_MODEL: tuple[TrafficClass, ...] = (
    TrafficClass(
        name="open_workbench",
        weight_pct=45,
        description="打开集团合并工作台：readiness 七域 + 节点金额/试算只读 + 操作列表",
        slo_ops=("readiness", "operation_list", "trial_read"),
    ),
    TrafficClass(
        name="role_views_and_post_elim",
        weight_pct=25,
        description="角色视图（编制/审批/质控待办）+ 四表抵销后 canonical projection 只读",
        slo_ops=("role_views", "post_elimination"),
    ),
    TrafficClass(
        name="operation_poll",
        weight_pct=18,
        description="轮询持久 operation 状态/步骤/metrics（回执 1 秒内，R10.4）",
        slo_ops=("operation_status",),
    ),
    TrafficClass(
        name="operation_trigger",
        weight_pct=9,
        description="触发一键刷新 refresh-all（创建/合并持久 operation，返回 operation_id）",
        slo_ops=("operation_create",),
    ),
    TrafficClass(
        name="manual_snapshot",
        weight_pct=3,
        description="创建手工诊断快照（manual，允许 partial；非 sign/lock）",
        slo_ops=("manual_snapshot",),
    ),
)


# ---------------------------------------------------------------------------
# SLO table — p50/p95/p99 latency budgets per logical op
# ---------------------------------------------------------------------------
# Design §6 fixes the shape (tree build ≤1, basis load ≤1, SQL slope 0 over D/S)
# and defers "具体毫秒 SLO 在 10/100/500 节点基线后确定". Task 8.1 delivered the
# 10/100/500 node slope benchmark; these budgets encode the resulting
# acceptance targets for the capacity run. They are intentionally conservative
# read budgets (the workbench must feel instant under load) with a wider budget
# for the operation *create* call, which only enqueues a persistent operation
# (the heavy compute runs in the worker, not in the request — design §7).

@dataclass(frozen=True)
class SloTarget:
    """A latency budget for one logical operation (p50/p95/p99 in ms)."""

    op: str
    p50_ms: int
    p95_ms: int
    p99_ms: int
    basis: str  # 口径


SLO_TABLE: tuple[SloTarget, ...] = (
    SloTarget("readiness", 120, 300, 1000, "七域五态 readiness；复用证据 readiness，不在请求内重算"),
    SloTarget("role_views", 150, 400, 1200, "角色视图聚合待办；读 readiness + 复核/映射计数"),
    SloTarget("post_elimination", 150, 400, 1200, "四表抵销后 canonical projection 只读；一次预载/递归 CTE"),
    SloTarget("trial_read", 120, 300, 1000, "合并试算只读五列；读 consol_report_values，不重算"),
    SloTarget("operation_list", 100, 250, 800, "operation 列表（默认 limit<=50）"),
    SloTarget("operation_status", 80, 200, 500, "单 operation 状态/步骤/metrics；回执 1 秒内（R10.4）"),
    SloTarget("operation_create", 300, 1000, 3000, "创建/合并持久 operation；只持久+入队返回 operation_id，重任务在 worker"),
    SloTarget("manual_snapshot", 500, 2000, 5000, "手工诊断快照 create；序列化分片+hash，允许 partial，只 flush 一次"),
)

SLO_BY_OP: dict[str, SloTarget] = {t.op: t for t in SLO_TABLE}


# ---------------------------------------------------------------------------
# Global acceptance thresholds — design R10 / R4 / R11
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class AcceptanceThresholds:
    max_error_rate_pct: float = 1.0            # 全场景错误率 < 1%
    # Throughput floor: at 6000 VU with a ~1-3s think time and a mostly-read
    # mix, the steady window must sustain a minimum aggregate request rate, or
    # the system is effectively stalled even if latency looks fine on the few
    # requests that completed. 6000 VU / ~5s mean cycle ≈ 1200 rps floor.
    min_throughput_rps: float = 1200.0
    max_cross_project_leakage: int = 0         # 跨项目 canary 泄露 = 0
    max_duplicate_operation_effects: int = 0   # 同幂等键重复 operation 副作用 = 0
    max_forbidden_terminal_states: int = 0     # chaos 下无伪 succeeded 终态
    # A dropped (unwritten) persisted operation under backpressure violates
    # R4.3/R4.5 ("进程重启后不得永久 running"；"下游失败不得伪装整体成功").
    max_lost_persisted_operations: int = 0


ACCEPTANCE = AcceptanceThresholds()


# ---------------------------------------------------------------------------
# Chaos fault-injection points — design §7 (降级) / R4.3, R4.5
# ---------------------------------------------------------------------------
# For the consolidation lifecycle the dependencies that can fail are: redis
# (operation queue / SSE fanout), the operation worker pool, and PG. The
# contract (design §7) is: "Redis/worker 不可用时可以同步创建 queued operation，
# 但不在请求内执行重任务；前端显示'等待工作进程'，不得降级为无版本旧计算."

@dataclass(frozen=True)
class ChaosFault:
    """A dependency outage the scenario can inject during the burst window."""

    dependency: str        # redis | worker | db
    mode: str              # unavailable | timeout | slow
    # Expected safe behaviour when this fault is active (R4.3/R4.5 + §7):
    #  - a queued operation can still be created (persisted), but
    #  - no fake "succeeded" terminal state is produced,
    #  - no degrade to version-less legacy recompute,
    #  - existing published results are unchanged.
    expected_behaviour: str
    # SLO ops that must still stay within budget for *unaffected* paths while
    # this fault is active (isolation — one outage must not fail the whole run).
    unaffected_slo_ops: tuple[str, ...]


CHAOS_FAULTS: tuple[ChaosFault, ...] = (
    ChaosFault(
        dependency="redis",
        mode="unavailable",
        expected_behaviour="同步创建 queued operation 并持久；前端显示'等待工作进程'；不在请求内跑重任务；已发布结果只读不变",
        unaffected_slo_ops=("readiness", "post_elimination", "trial_read"),
    ),
    ChaosFault(
        dependency="worker",
        mode="unavailable",
        expected_behaviour="operation 停在 queued/running 并可被重启恢复；不伪装 succeeded；不降级为无版本旧计算",
        unaffected_slo_ops=("readiness", "role_views", "operation_list", "operation_status"),
    ),
    ChaosFault(
        dependency="db",
        mode="slow",
        expected_behaviour="读路径按 pool/queue 退避并保持 SLO 隔离；写阶段用 revision CAS，旧输入不晚写覆盖新输入",
        unaffected_slo_ops=("operation_status",),
    ),
)


# ---------------------------------------------------------------------------
# Canary — a dedicated cross-project probe proves project isolation under load.
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CanaryProbe:
    """Cross-project leakage probe: attempt to read a FOREIGN consolidation
    project's readiness/post-elimination and assert every attempt is denied
    (leakage == 0). Design R11.1: all endpoints keep project-level authz."""

    name: str = "cross_project_canary"
    description: str = (
        "以项目 A 身份尝试读取项目 B 的 readiness / post-elimination；"
        "任一非 denied(403/404) 响应或泄露目标元数据即计为泄露"
    )
    denied_statuses: tuple[int, ...] = (403, 404)


CANARY = CanaryProbe()


# ---------------------------------------------------------------------------
# Full scenario container + serialisation
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CapacityScenario:
    spec: str = "consolidation-run-and-workpaper-lifecycle-closure"
    task: str = "8.4"
    requirements: tuple[str, ...] = ("R10", "R11")
    target_virtual_users: int = TARGET_VIRTUAL_USERS
    steady_state_seconds: int = STEADY_STATE_SECONDS
    burst_seconds: int = BURST_SECONDS
    load_profile: tuple[LoadPhase, ...] = LOAD_PROFILE
    traffic_model: tuple[TrafficClass, ...] = TRAFFIC_MODEL
    slo_table: tuple[SloTarget, ...] = SLO_TABLE
    acceptance: AcceptanceThresholds = ACCEPTANCE
    chaos_faults: tuple[ChaosFault, ...] = CHAOS_FAULTS
    canary: CanaryProbe = CANARY

    def validate(self) -> None:
        """Fail-fast integrity checks so the tooling cannot silently drift."""
        weights = sum(c.weight_pct for c in self.traffic_model)
        if weights != 100:
            raise ValueError(f"traffic model weights must sum to 100, got {weights}")

        # Every traffic-class SLO op must exist in the SLO table.
        for c in self.traffic_model:
            for op in c.slo_ops:
                if op not in SLO_BY_OP:
                    raise ValueError(f"traffic class {c.name!r} references unknown SLO op {op!r}")

        # p50 <= p95 <= p99 for every SLO target.
        for t in self.slo_table:
            if not (t.p50_ms <= t.p95_ms <= t.p99_ms):
                raise ValueError(
                    f"SLO op {t.op!r} must satisfy p50<=p95<=p99, got "
                    f"{t.p50_ms}/{t.p95_ms}/{t.p99_ms}"
                )

        # Steady + burst durations must match the capacity contract.
        steady = sum(p.duration_s for p in self.load_profile if p.kind == "steady")
        burst = sum(p.duration_s for p in self.load_profile if p.kind == "burst")
        if steady != self.steady_state_seconds:
            raise ValueError(f"steady duration {steady}s != contract {self.steady_state_seconds}s")
        if burst != self.burst_seconds:
            raise ValueError(f"burst duration {burst}s != contract {self.burst_seconds}s")

        # The steady phase must reach the 6000 VU target.
        steady_peak = max((p.users for p in self.load_profile if p.kind == "steady"), default=0)
        if steady_peak != self.target_virtual_users:
            raise ValueError(
                f"steady peak {steady_peak} VU != target {self.target_virtual_users} VU"
            )

        # Chaos faults must reference known dependencies + valid SLO ops.
        for f in self.chaos_faults:
            if f.dependency not in ("redis", "worker", "db"):
                raise ValueError(f"unknown chaos dependency {f.dependency!r}")
            for op in f.unaffected_slo_ops:
                if op not in SLO_BY_OP:
                    raise ValueError(f"chaos fault {f.dependency!r} references unknown SLO op {op!r}")

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)


SCENARIO = CapacityScenario()

SCENARIO_JSON_PATH = Path(__file__).with_name("scenario.json")


def write_scenario_json(path: Path | None = None) -> Path:
    """Emit the machine-readable scenario definition to ``scenario.json``."""
    SCENARIO.validate()
    target = path or SCENARIO_JSON_PATH
    target.write_text(SCENARIO.to_json() + "\n", encoding="utf-8")
    return target


if __name__ == "__main__":  # pragma: no cover - manual regeneration entrypoint
    out = write_scenario_json()
    print(f"[OK] wrote scenario definition -> {out}")
