"""Chaos fault-injection controller for the capacity scenario (design §9.2).

Requirements: R15.3 (degrade safely), R15.4 (bounded backoff), R12 (observability).

The capacity run injects storage/OCR/retrieval/AI dependency outages during the
burst window and asserts the platform degrades safely:
  * a degraded status is surfaced to the caller;
  * fail-closed — no confirmed / written_back / archived terminal state is
    produced while the dependency is unavailable/timeout/stub/unverifiable;
  * existing business data is preserved unchanged;
  * paths that do not depend on the faulted dependency stay within SLO
    (one outage must not fail the whole run — isolation).

Injection mechanism is intentionally out-of-band and environment-controlled so
the harness never mutates production wiring:
  * ``FaultPlan.to_env()`` produces the ``EVIDENCE_CHAOS_*`` toggles the
    capacity environment reads (a chaos middleware / feature flag in the target
    deployment consumes them). The harness only *schedules* and *observes*.

This module contains no I/O against a live system; it produces the plan and the
pure assertions the report generator consumes.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .scenario import CHAOS_FAULTS, ChaosFault


# Terminal states that MUST NOT be produced while a dependency is faulted.
FORBIDDEN_TERMINAL_STATES: tuple[str, ...] = ("confirmed", "written_back", "archived")


@dataclass(frozen=True)
class FaultWindow:
    """When a fault is active, expressed as offsets from run start (seconds)."""

    fault: ChaosFault
    start_offset_s: int
    duration_s: int

    @property
    def end_offset_s(self) -> int:
        return self.start_offset_s + self.duration_s

    def env_key(self) -> str:
        return f"EVIDENCE_CHAOS_{self.fault.dependency.upper()}"

    def env_value(self) -> str:
        return self.fault.mode


@dataclass(frozen=True)
class FaultPlan:
    """A schedule of dependency outages, staggered across the burst window.

    Faults are staggered (not simultaneous) so each dependency's degradation and
    the isolation of unaffected paths can be attributed unambiguously.
    """

    windows: tuple[FaultWindow, ...]

    def to_env_timeline(self) -> list[dict]:
        """Machine-readable timeline of chaos toggles for the runner/operator."""
        return [
            {
                "dependency": w.fault.dependency,
                "mode": w.fault.mode,
                "env_key": w.env_key(),
                "env_value": w.env_value(),
                "start_offset_s": w.start_offset_s,
                "end_offset_s": w.end_offset_s,
                "expected_behaviour": w.fault.expected_behaviour,
                "unaffected_slo_ops": list(w.fault.unaffected_slo_ops),
            }
            for w in self.windows
        ]


def build_default_fault_plan(
    *,
    burst_start_offset_s: int,
    burst_duration_s: int,
    faults: tuple[ChaosFault, ...] = CHAOS_FAULTS,
) -> FaultPlan:
    """Stagger the four dependency faults evenly across the burst window.

    Each fault gets an equal, non-overlapping slice so degradation and isolation
    are attributable. Slices are sized to fit within the burst window.
    """
    if not faults:
        return FaultPlan(windows=())
    slice_s = max(1, burst_duration_s // len(faults))
    windows: list[FaultWindow] = []
    for i, fault in enumerate(faults):
        start = burst_start_offset_s + i * slice_s
        windows.append(
            FaultWindow(fault=fault, start_offset_s=start, duration_s=slice_s)
        )
    return FaultPlan(windows=tuple(windows))


def is_forbidden_terminal_state(state: str) -> bool:
    """True if ``state`` is a terminal state banned under active chaos."""
    return state in FORBIDDEN_TERMINAL_STATES


def evaluate_degradation(
    *,
    dependency: str,
    degraded_status_surfaced: bool,
    produced_terminal_states: list[str],
    business_data_mutations: int,
    unaffected_ops_within_slo: bool,
) -> tuple[bool, list[str]]:
    """Pure fail-closed evaluation of one dependency-outage window.

    Returns ``(ok, reasons)``. This is the same logic the report generator
    encodes, exposed here so a runner can assert per-window in real time.
    """
    reasons: list[str] = []
    if not degraded_status_surfaced:
        reasons.append(f"{dependency}: degraded status not surfaced to caller")

    forbidden = [s for s in produced_terminal_states if is_forbidden_terminal_state(s)]
    if forbidden:
        reasons.append(
            f"{dependency}: forbidden terminal state(s) produced under outage: {forbidden}"
        )

    if business_data_mutations > 0:
        reasons.append(
            f"{dependency}: {business_data_mutations} business-data mutation(s) under outage"
        )

    if not unaffected_ops_within_slo:
        reasons.append(f"{dependency}: unaffected paths breached SLO (no isolation)")

    return (not reasons, reasons)
