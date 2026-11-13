"""PG / PgBouncer connection budget model + invariant for the consolidation
lifecycle capacity scenario (design §6 / §7).

Spec: consolidation-run-and-workpaper-lifecycle-closure — Task 8.4
Requirements: R10 (capacity / observability of pool wait), R4 (持久 operation).

Design contract (§7):
  * all new consol routes run on project-level pools;
  * service layer only ``flush``; the operation worker uses short per-stage
    transactions with revision CAS — NO per-VU DB connection for the heavy
    compute path (it runs in the bounded worker pool, not the request);
  * under redis/worker outage a ``queued`` operation can still be created, but
    the request never holds a connection for the heavy compute.

For the capacity environment PG is fronted by PgBouncer in **transaction**
pooling mode. This module lets the harness assert the deployed budget respects
the invariant BEFORE a run is allowed — a run against an over-budget pool just
exhausts connections and produces meaningless numbers.

Invariant (same shape as the platform-wide pg-pooling spec, specialised to the
three consol service classes):
  * PgBouncer pool mode == "transaction";
  * ``sum(service budgets) + ops_reserve < PG max_connections``;
  * at least 20% of ``max_connections`` reserved for admin/recovery;
  * every service pool has a positive budget;
  * the operation worker write pool is bounded (it is NOT allowed to scale with
    virtual users — design §7: no per-VU DB connection).

Defaults are grounded in the committed dev/capacity config:
  docker-compose.yml          -> PG ``max_connections=200``,
                                 PgBouncer POOL_MODE=transaction,
                                 DEFAULT_POOL_SIZE=50, RESERVE_POOL_SIZE=10,
                                 MAX_CLIENT_CONN=10000
  backend/app/core/config.py  -> DB_POOL_SIZE=50, DB_MAX_OVERFLOW=100,
                                 DB_PGBOUNCER_PORT=6432
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ServicePoolBudget:
    """Connection budget for one service pool class."""

    name: str             # api_read | sse_longpoll | operation_worker
    max_connections: int  # server-side backend connections this pool may hold
    description: str = ""
    # Whether this pool's size is allowed to grow with virtual users. The
    # operation worker write pool MUST be bounded (design §7: no per-VU DB conn).
    scales_with_vus: bool = False


@dataclass(frozen=True)
class ConnectionBudget:
    """The full PG/PgBouncer budget for the consol capacity environment."""

    pg_max_connections: int = 200
    pgbouncer_pool_mode: str = "transaction"
    pgbouncer_max_client_conn: int = 10000
    ops_reserve: int = 10  # explicit maintenance/recovery superuser headroom
    min_admin_reserve_pct: float = 20.0
    pools: tuple[ServicePoolBudget, ...] = field(
        default_factory=lambda: (
            ServicePoolBudget(
                "api_read", 90,
                "合并读 API 池：readiness / role-views / post-elimination / trial / operation 状态",
                scales_with_vus=False,
            ),
            ServicePoolBudget(
                "sse_longpoll", 20,
                "operation SSE / 长轮询池（每连接一个 function-scope get_db，避免 idle in transaction）",
                scales_with_vus=False,
            ),
            ServicePoolBudget(
                "operation_worker", 40,
                "operation worker 写池：refresh-all/push/报表/快照 短事务逐阶段提交（非 per-VU）",
                scales_with_vus=False,
            ),
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
    pgbouncer_max_client_conn: int

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
            "pgbouncer_max_client_conn": self.pgbouncer_max_client_conn,
        }


# 6000 VU may each hold at most one front-side PgBouncer client connection
# transiently; transaction pooling multiplexes them onto the small backend
# pools. MAX_CLIENT_CONN must leave headroom above the raw VU count.
TARGET_FRONTSIDE_CLIENTS = 6000


def check_budget(budget: ConnectionBudget | None = None) -> BudgetCheck:
    """Assert the §6/§7 invariant. Returns a machine-readable check result."""
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

    # The operation worker write pool must be bounded (design §7: no per-VU DB conn).
    for p in b.pools:
        if p.name == "operation_worker" and p.scales_with_vus:
            reasons.append(
                "operation_worker pool must NOT scale with virtual users "
                "(design §7: heavy compute runs in a bounded worker pool, no per-VU DB connection)"
            )

    # MAX_CLIENT_CONN must comfortably exceed the 6000 VU front-side demand so
    # PgBouncer does not reject clients before backend pooling even applies.
    if b.pgbouncer_max_client_conn < TARGET_FRONTSIDE_CLIENTS:
        reasons.append(
            f"PgBouncer max_client_conn {b.pgbouncer_max_client_conn} < required "
            f"front-side headroom {TARGET_FRONTSIDE_CLIENTS} for 6000 VU"
        )

    return BudgetCheck(
        ok=not reasons,
        reasons=tuple(reasons),
        total_service_budget=b.total_service_budget,
        total_committed=b.total_committed,
        pg_max_connections=b.pg_max_connections,
        admin_reserve=b.admin_reserve,
        admin_reserve_pct=b.admin_reserve_pct,
        pgbouncer_pool_mode=b.pgbouncer_pool_mode,
        pgbouncer_max_client_conn=b.pgbouncer_max_client_conn,
    )
