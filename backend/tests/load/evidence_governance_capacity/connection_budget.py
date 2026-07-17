"""PG / PgBouncer connection budget model + invariant (design §9.2).

Requirements: R15 (capacity), R12 (observability of pool wait).

Design §9.2 contract:
  * PgBouncer uses transaction pooling.
  * API metadata pool, long-cursor/archive pool, and worker write pool are
    separated; each service class has a connection budget.
  * ``sum(all service budgets) + ops_reserve < PG max_connections`` and at
    least 20% of ``max_connections`` is reserved for admin/recovery.
  * Worker concurrency is bounded by ``min(PG write budget, external provider
    quota, queue age)`` — no per-VU DB connection.

This module lets the capacity harness assert the deployed budget respects the
invariant BEFORE a run is allowed (a run against an over-budget pool would just
exhaust connections and produce meaningless numbers).

Defaults are grounded in the committed dev/capacity config:
  docker-compose.yml    -> PG ``max_connections=200``
                           PgBouncer POOL_MODE=transaction, DEFAULT_POOL_SIZE=50,
                           RESERVE_POOL_SIZE=10, MAX_CLIENT_CONN=10000
  backend/app/core/config.py -> DB_POOL_SIZE=50, DB_MAX_OVERFLOW=100
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ServicePoolBudget:
    """Connection budget for one service pool class."""

    name: str            # api_metadata | cursor_archive | worker_write
    max_connections: int  # server-side backend connections this pool may hold
    description: str = ""


@dataclass(frozen=True)
class ConnectionBudget:
    """The full PG/PgBouncer budget for the capacity environment."""

    pg_max_connections: int = 200
    pgbouncer_pool_mode: str = "transaction"
    ops_reserve: int = 10  # explicit maintenance/recovery superuser headroom
    min_admin_reserve_pct: float = 20.0
    pools: tuple[ServicePoolBudget, ...] = field(
        default_factory=lambda: (
            ServicePoolBudget("api_metadata", 60, "元数据读/写 API 池（keyset cursor）"),
            ServicePoolBudget("cursor_archive", 40, "长游标/归档只读池"),
            ServicePoolBudget("worker_write", 50, "upload/OCR/AI/stale/archive worker 写池"),
        )
    )

    @property
    def total_service_budget(self) -> int:
        return sum(p.max_connections for p in self.pools)

    @property
    def total_committed(self) -> int:
        return self.total_service_budget + self.ops_reserve

    @property
    def admin_reserve(self) -> int:
        """Connections left free for admin/recovery after service+ops budgets."""
        return self.pg_max_connections - self.total_committed

    @property
    def admin_reserve_pct(self) -> float:
        if self.pg_max_connections <= 0:
            return 0.0
        return 100.0 * self.admin_reserve / self.pg_max_connections


@dataclass(frozen=True)
class BudgetCheck:
    ok: bool
    reasons: tuple[str, ...]
    total_service_budget: int
    total_committed: int
    pg_max_connections: int
    admin_reserve: int
    admin_reserve_pct: float
    pgbouncer_pool_mode: str

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "reasons": list(self.reasons),
            "total_service_budget": self.total_service_budget,
            "total_committed": self.total_committed,
            "pg_max_connections": self.pg_max_connections,
            "admin_reserve": self.admin_reserve,
            "admin_reserve_pct": round(self.admin_reserve_pct, 2),
            "pgbouncer_pool_mode": self.pgbouncer_pool_mode,
        }


def check_budget(budget: ConnectionBudget | None = None) -> BudgetCheck:
    """Assert the §9.2 invariant. Returns a machine-readable check result."""
    b = budget or ConnectionBudget()
    reasons: list[str] = []

    if b.pgbouncer_pool_mode != "transaction":
        reasons.append(
            f"PgBouncer pool mode must be 'transaction', got {b.pgbouncer_pool_mode!r}"
        )

    # total budget + ops reserve must be strictly below max_connections
    if b.total_committed >= b.pg_max_connections:
        reasons.append(
            f"total committed {b.total_committed} (service {b.total_service_budget} + "
            f"ops {b.ops_reserve}) must be < max_connections {b.pg_max_connections}"
        )

    # >= 20% of max_connections reserved for admin/recovery
    if b.admin_reserve_pct < b.min_admin_reserve_pct:
        reasons.append(
            f"admin/recovery reserve {b.admin_reserve_pct:.1f}% < required "
            f"{b.min_admin_reserve_pct:.0f}%"
        )

    for p in b.pools:
        if p.max_connections <= 0:
            reasons.append(f"pool {p.name!r} must have a positive budget")

    return BudgetCheck(
        ok=not reasons,
        reasons=tuple(reasons),
        total_service_budget=b.total_service_budget,
        total_committed=b.total_committed,
        pg_max_connections=b.pg_max_connections,
        admin_reserve=b.admin_reserve,
        admin_reserve_pct=b.admin_reserve_pct,
        pgbouncer_pool_mode=b.pgbouncer_pool_mode,
    )
