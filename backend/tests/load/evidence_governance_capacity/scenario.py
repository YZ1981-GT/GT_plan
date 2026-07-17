"""Evidence Governance capacity/chaos scenario definition (machine-readable).

Spec: attachment-ocr-ai-evidence-governance-hardening — Task 8.2
Requirements: R12, R15
Design: §9.1 (6000 VU model + SLO table), §9.2 (queues/quotas), §10.2 (layer 6).

This module is the single source of truth. It defines:

* the 6000 VU load profile — 30 min steady state + 10 min burst;
* the traffic model — 70% metadata read / 20% write-associate /
  7% OCR-AI enqueue / 3% impact-archive control;
* the SLO table from design §9.1 (P95 targets, keyed by logical operation);
* the global acceptance thresholds (error rate < 1%, cross-project canary
  leakage == 0, duplicate side-effects == 0);
* the chaos fault-injection points (storage/OCR/retrieval/AI).

Everything is expressed with plain dataclasses so it can be serialised to JSON
(``scenario.json``) and consumed by the Locust harness, the report generator and
the threshold assertions. Nothing here performs I/O or fakes a run.
"""

from __future__ import annotations

import dataclasses
import json
from dataclasses import dataclass, field
from pathlib import Path


# ---------------------------------------------------------------------------
# Load profile — design §9.1: 6000 VU, 30 min steady + 10 min burst
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class LoadPhase:
    """One phase of the ramped load profile."""

    name: str
    users: int
    spawn_rate: int  # users/second
    duration_s: int  # steady duration held at ``users`` after ramp
    kind: str  # "warmup" | "steady" | "burst"


# Steady state runs at the 6000 VU design target for 30 minutes, then a 10 minute
# burst pushes 20% above target to prove backpressure (soft->slow, hard->429)
# without losing persisted jobs. Warmup phases exist only to reach the target;
# their SLO measurements are excluded from the pass/fail window.
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
# Traffic model — design §9.1: 70 / 20 / 7 / 3
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TrafficClass:
    """A weighted class of user behaviour mapped to concrete endpoints."""

    name: str
    weight_pct: int
    description: str
    # Logical SLO operation keys (see SLO_TABLE) exercised by this class.
    slo_ops: tuple[str, ...]


TRAFFIC_MODEL: tuple[TrafficClass, ...] = (
    TrafficClass(
        name="metadata_read",
        weight_pct=70,
        description="附件/版本/引用元数据读 + cursor 列表 + OCR job 状态（不读文件字节）",
        slo_ops=("metadata_read", "cursor_list"),
    ),
    TrafficClass(
        name="write_associate",
        weight_pct=20,
        description="创建 EvidenceRef / 跨模块关联（含 audit+outbox，不含外部 I/O）",
        slo_ops=("governance_write",),
    ),
    TrafficClass(
        name="ocr_ai_enqueue",
        weight_pct=7,
        description="OCR/AI enqueue（staged 持久+入队，返回 202）",
        slo_ops=("staged_enqueue",),
    ),
    TrafficClass(
        name="impact_archive_control",
        weight_pct=3,
        description="影响范围查询 + 归档请求（异步构建）",
        slo_ops=("impact_le_100_nodes", "archive_request"),
    ),
)


# ---------------------------------------------------------------------------
# SLO table — verbatim from design §9.1
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SloTarget:
    """A P95 latency budget for one logical operation."""

    op: str
    p95_ms: int
    basis: str  # 口径


SLO_TABLE: tuple[SloTarget, ...] = (
    SloTarget("metadata_read", 200, "单附件/版本/引用元数据读；不读文件字节"),
    SloTarget("cursor_list", 300, "cursor 列表；默认 limit<=100"),
    SloTarget("impact_le_100_nodes", 500, "<=100 节点直接影响；超阈值异步"),
    SloTarget("governance_write", 500, "引用/治理元数据写；含 audit+outbox，不含外部 I/O"),
    SloTarget("staged_enqueue", 300, "staged 持久+enqueue；接收完成后计时，返回 202"),
    SloTarget("sync_finalize_create", 1000, "同步 finalize 创建；只有预算内完成才 201"),
    SloTarget("finalize_external_task", 30000, "finalize 外部任务；与 enqueue SLO 分开统计"),
    SloTarget("formal_preflight_le_500_deps", 750, "FormalOutput preflight <=500 依赖；读 materialized summary/watermark"),
    SloTarget("stale_enqueue", 200, "stale 入队；闭包 95%<=5s，超大图<=60s"),
    SloTarget("archive_request", 500, "archive request；构建异步"),
)

SLO_BY_OP: dict[str, SloTarget] = {t.op: t for t in SLO_TABLE}


# ---------------------------------------------------------------------------
# Global acceptance thresholds — design §9.1 / R15.1
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class AcceptanceThresholds:
    max_error_rate_pct: float = 1.0          # 错误率 < 1%
    max_cross_project_leakage: int = 0       # 跨项目 canary 泄露 = 0
    max_duplicate_side_effects: int = 0      # 重复副作用 = 0
    max_forbidden_terminal_states: int = 0   # chaos 下无 confirmed/written_back/archived 降级终态
    # A dropped (unwritten) persisted job under backpressure violates
    # "已持久 job 不丢失" (design §9.2).
    max_lost_persisted_jobs: int = 0


ACCEPTANCE = AcceptanceThresholds()


# ---------------------------------------------------------------------------
# Chaos fault-injection points — design §9.2 / R15.3, R15.4
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ChaosFault:
    """A dependency outage the scenario can inject during the burst window."""

    dependency: str        # storage | ocr | retrieval | ai
    mode: str              # unavailable | timeout | stub | unverifiable
    # Expected safe behaviour when this fault is active (R15.3):
    #  - degraded status surfaced
    #  - fail-closed: no confirmed/written_back/archived terminal state
    #  - existing business data unchanged
    expected_behaviour: str
    # SLO ops that must still stay within budget for *unaffected* paths while
    # this fault is active (isolation — one outage must not fail the whole run).
    unaffected_slo_ops: tuple[str, ...]


CHAOS_FAULTS: tuple[ChaosFault, ...] = (
    ChaosFault(
        dependency="storage",
        mode="unavailable",
        expected_behaviour="读取先鉴权后拒绝；不产生可用 Attachment/Version；脱敏审计；元数据读路径不受影响",
        unaffected_slo_ops=("metadata_read", "cursor_list"),
    ),
    ChaosFault(
        dependency="ocr",
        mode="timeout",
        expected_behaviour="OCR job 安全失败/有界退避；保留已有结果；不进入 confirmed/written_back",
        unaffected_slo_ops=("metadata_read", "cursor_list", "governance_write"),
    ),
    ChaosFault(
        dependency="retrieval",
        mode="unverifiable",
        expected_behaviour="引用标记不可验证；禁止进入 confirmed AI 内容或 Formal_Output",
        unaffected_slo_ops=("metadata_read", "cursor_list"),
    ),
    ChaosFault(
        dependency="ai",
        mode="stub",
        expected_behaviour="显示降级状态；禁止自动确认或正式写回；保留原始业务数据不变",
        unaffected_slo_ops=("metadata_read", "cursor_list", "governance_write"),
    ),
)


# ---------------------------------------------------------------------------
# Canary — a dedicated cross-project probe user proves P1 isolation under load.
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CanaryProbe:
    """Cross-project leakage probe: attempt access to a foreign project's
    evidence and assert every attempt is denied (leakage == 0)."""

    name: str = "cross_project_canary"
    description: str = (
        "以项目 A 身份尝试读取/关联项目 B 的 evidence ref、OCR job、impact；"
        "任一非 4xx-denied 响应或响应泄露目标元数据即计为泄露"
    )
    # Any of these HTTP statuses count as a correct denial.
    denied_statuses: tuple[int, ...] = (403, 404)


CANARY = CanaryProbe()


# ---------------------------------------------------------------------------
# Full scenario container + serialisation
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CapacityScenario:
    spec: str = "attachment-ocr-ai-evidence-governance-hardening"
    task: str = "8.2"
    requirements: tuple[str, ...] = ("R12", "R15")
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

        # Steady + burst durations must match the design contract.
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
            if f.dependency not in ("storage", "ocr", "retrieval", "ai"):
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
