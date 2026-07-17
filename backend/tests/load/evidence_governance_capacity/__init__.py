"""Evidence Governance Capacity & Chaos tooling (Task 8.2, Wave 7).

Spec: attachment-ocr-ai-evidence-governance-hardening
Requirements: R12 (observability), R15 (performance/capacity/degradation)
Design: §9.1 6000 VU capacity model + SLO table, §9.2 queue backpressure +
        PG/PgBouncer quotas, §10.2 layer 6 "capacity/chaos" (independent tool,
        NOT Playwright, NOT pytest PBT).

This package is the single machine-readable source of truth for the evidence
governance capacity/chaos scenario:

* ``scenario``          — traffic model (70/20/7/3), SLO table, steady/burst
                          phases, chaos fault-injection points, canary/duplicate
                          invariants. Emits ``scenario.json``.
* ``connection_budget`` — PgBouncer transaction-pooling + per-service PG
                          connection budgets and the ``total + ops_reserve <
                          max_connections`` / ``>=20% reserved`` invariant.
* ``chaos``             — storage/OCR/retrieval/AI outage injection points and
                          the fail-closed / no-forbidden-terminal-state
                          degradation assertions.
* ``capacity_report``   — machine-readable capacity report schema + generator +
                          SLO/error-rate/leakage/duplicate threshold assertions.

The actual 6000 VU run requires a dedicated capacity environment; see
``README.md`` for execution. The Locust harness lives in
``locustfile_evidence_capacity.py``.
"""

from __future__ import annotations
