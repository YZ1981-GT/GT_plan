"""Consolidation lifecycle Capacity & Chaos tooling (Task 8.4).

Spec: consolidation-run-and-workpaper-lifecycle-closure
Requirements: R10 (performance/capacity/observability), R11 (验收;
              6000 并发依赖专用压测环境，未授权时如实标环境待测)
Design: §3 统一运行顺序, §4 API, §6 性能与观测, §7 降级.

This package is the single machine-readable source of truth for the
consolidation lifecycle 6000 VU capacity/chaos scenario. It is an INDEPENDENT
tool (NOT Playwright, NOT pytest PBT):

* ``scenario``          — traffic model (open workbench / role-views +
                          post-elimination / operation poll / operation trigger /
                          manual snapshot), SLO table (p50/p95/p99), steady/burst
                          phases, chaos fault-injection points, canary/duplicate
                          invariants. Emits ``scenario.json``.
* ``connection_budget`` — PgBouncer transaction-pooling + per-service PG
                          connection budgets (api_read / sse_longpoll /
                          operation_worker) and the ``total + ops_reserve <
                          max_connections`` / ``>=20% reserved`` / bounded worker
                          invariant.
* ``chaos``             — redis/worker/db outage injection points and the
                          fail-closed / no-fake-succeeded / no-version-less-
                          recompute degradation assertions.
* ``capacity_report``   — machine-readable capacity report schema + generator +
                          p50/p95/p99 SLO / error-rate / throughput-floor /
                          leakage / duplicate threshold assertions.

The actual 6000 VU run requires a dedicated capacity environment AND explicit
authorization; see ``README.md`` for execution and the authorized-run checklist.
The Locust harness lives in ``locustfile_consol_capacity.py``. The tooling
itself is verified by ``test_capacity_tooling.py`` WITHOUT running 6000 VU.
"""

from __future__ import annotations
