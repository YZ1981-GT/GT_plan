"""连接预算计算：按副本数算「本系统最多能开多少连接」。

spec: `platform-heavy-jobs-and-capacity-closure` E1/E4。

## 为什么需要它

`DB_POOL_SIZE=50` / `DB_MAX_OVERFLOW=100` 是**单副本**的默认值，注释写着「6000 并发优化」。
但这两个数字没有副本维度：8 个副本时总连接 = 8 × 150 = **1200**，而 PG 默认
`max_connections` 只有 100，Docker 里的 PG16 常配 200~500 ⇒ 一扩容就 `too many clients`。
E1 要求「连接预算按副本数计算」，E4 要求「构建容量环境」，这条就是那个计算的单一来源。

## 预算模型（三层，逐层收窄）

```
PG max_connections
  − superuser_reserved_connections（PG 保留给超级用户，不可挪用）
  − 管理/运维连接预算（备份、迁移、监控、pg_dump）
  = 应用可用总额度
      ↓ 按副本数均分
    单副本额度
      ↓ 扣掉本副本非池连接（直连工具、迁移、健康检查）
    单副本池额度  = pool_size + max_overflow（必须 ≤ 单副本额度）
```

## 有 PgBouncer 时是两层不是一层

直连 PG 时：每个副本的池连接**直接**占 PG 连接。
经 PgBouncer（transaction 模式）时：副本连的是 bouncer 的 **client** 连接，
bouncer 到 PG 的是 **server** 连接（`DEFAULT_POOL_SIZE`）。所以：

- 副本 × `(pool_size + max_overflow)` ≤ **bouncer** `MAX_CLIENT_CONN`
- `DEFAULT_POOL_SIZE` × bouncer 实例数 ≤ **PG** 应用可用额度

这两条约束**同时**成立才行 —— 只算一层的配置在扩容时必炸其中一边。

## 本模块只做纯计算，不连库

不读实际 `max_connections`、不探 bouncer 配置：那需要真实环境，而算错预算的代价是
扩容时线上 `too many clients`。所以把**算法**单独成模块、用单测把它钉死，
部署时把实际值当参数传入即可。
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "ConnectionBudget",
    "BudgetError",
    "compute_direct_budget",
    "compute_bouncer_budget",
]


class BudgetError(ValueError):
    """配置不可能成立（算出来是负数 / 超限），必须拒绝而不是钳到 0。"""


@dataclass(frozen=True)
class ConnectionBudget:
    """一次预算计算的结论（纯数据，可 JSON 化、可断言逐值）。

    ``feasible`` 为 False 时其余「额度」字段仍有值 —— 它们是**算出来的**，不是猜的，
    保留下来才能回答「差多少」。
    """

    #: 应用可用的 PG 连接总额度（扣掉保留与管理后）
    pg_app_total: int
    #: 单副本可用额度
    per_replica: int
    #: 单副本池额度（pool_size + max_overflow 的上限）
    per_replica_pool: int
    #: 是否可行
    feasible: bool
    #: 不可行/需注意的原因（可行时为空）
    reasons: tuple[str, ...]
    #: 该模式下最紧的那一条约束（便于运维一眼看到瓶颈在哪层）
    binding_constraint: str


def _validate_positive(**values: int) -> None:
    for name, value in values.items():
        if not isinstance(value, int) or value < 0:
            raise BudgetError(f"{name} 必须是非负整数，实际 {value!r}")


def compute_direct_budget(
    *,
    pg_max_connections: int,
    replicas: int,
    superuser_reserved: int = 3,
    admin_reserve: int = 8,
    non_pool_connections_per_replica: int = 3,
    pool_size: int = 50,
    max_overflow: int = 100,
) -> ConnectionBudget:
    """直连 PG 的预算：``replicas × (pool_size + max_overflow)`` 必须装进总额度。

    Args:
        pg_max_connections: PG 的 ``max_connections``（现查 `SHOW max_connections`）。
        replicas: 要扩容到的副本数（1 / 2 / 4 / 8 是 E2 的验收梯度）。
        superuser_reserved: PG 的 ``superuser_reserved_connections``（默认 3）。
        admin_reserve: 留给备份/迁移/监控的连接数（经验值，可按运维实际调）。
        non_pool_connections_per_replica: 每个副本池外还要占的连接（migration runner /
            健康检查 / 直连工具）。
        pool_size / max_overflow: 单副本池配置（现默认 50 / 100）。
    """
    _validate_positive(
        pg_max_connections=pg_max_connections,
        replicas=replicas,
        superuser_reserved=superuser_reserved,
        admin_reserve=admin_reserve,
        non_pool_connections_per_replica=non_pool_connections_per_replica,
        pool_size=pool_size,
        max_overflow=max_overflow,
    )
    if replicas < 1:
        raise BudgetError(f"replicas 至少为 1，实际 {replicas}")

    pg_app_total = pg_max_connections - superuser_reserved - admin_reserve
    reasons: list[str] = []
    if pg_app_total <= 0:
        raise BudgetError(
            f"PG max_connections={pg_max_connections} 扣掉保留（{superuser_reserved}）与"
            f"管理（{admin_reserve}）后没有可用额度（={pg_app_total}）"
        )

    per_replica = pg_app_total // replicas
    per_replica_pool = per_replica - non_pool_connections_per_replica
    requested = pool_size + max_overflow
    feasible = True

    if per_replica_pool <= 0:
        feasible = False
        reasons.append(
            f"{replicas} 个副本时单副本只分到 {per_replica} 条，扣掉池外 "
            f"{non_pool_connections_per_replica} 条后池额度为 {per_replica_pool}（≤0）"
        )
    elif requested > per_replica_pool:
        feasible = False
        reasons.append(
            f"单副本池配置 pool_size({pool_size}) + max_overflow({max_overflow}) = "
            f"{requested} 超过单副本池额度 {per_replica_pool}"
            f"（{replicas} 副本 × {requested} = {replicas * requested}，"
            f"而 PG 应用可用总额度只有 {pg_app_total}）"
        )

    return ConnectionBudget(
        pg_app_total=pg_app_total,
        per_replica=per_replica,
        per_replica_pool=per_replica_pool,
        feasible=feasible,
        reasons=tuple(reasons),
        binding_constraint="pg_max_connections",
    )


def compute_bouncer_budget(
    *,
    pg_max_connections: int,
    bouncer_instances: int,
    replicas: int,
    superuser_reserved: int = 3,
    admin_reserve: int = 8,
    bouncer_max_client_conn: int = 10000,
    bouncer_default_pool_size: int = 50,
    non_pool_connections_per_replica: int = 3,
    pool_size: int = 50,
    max_overflow: int = 100,
) -> ConnectionBudget:
    """经 PgBouncer（transaction 模式）的预算：**两层约束同时**检查。

    第一层（客户端侧）：``replicas × (pool_size + max_overflow)`` ≤
    ``bouncer_instances × bouncer_max_client_conn``。
    第二层（服务端侧）：``bouncer_instances × bouncer_default_pool_size`` ≤
    ``pg_app_total``（bouncer 到 PG 的 server 连接才真正占 PG）。

    🔴 只检查第二层是常见错误：bouncer 的 `DEFAULT_POOL_SIZE` 配得很小，
    就以为「PG 连接够用」，结果副本一扩容先把 bouncer 的 `MAX_CLIENT_CONN` 打满，
    报的是 bouncer 的 `no more connections allowed`，而不是 PG 的。
    反之只检查第一层，则 bouncer 会把 PG 打满。⇒ 两层都要过。
    """
    _validate_positive(
        pg_max_connections=pg_max_connections,
        bouncer_instances=bouncer_instances,
        replicas=replicas,
        superuser_reserved=superuser_reserved,
        admin_reserve=admin_reserve,
        bouncer_max_client_conn=bouncer_max_client_conn,
        bouncer_default_pool_size=bouncer_default_pool_size,
        non_pool_connections_per_replica=non_pool_connections_per_replica,
        pool_size=pool_size,
        max_overflow=max_overflow,
    )
    if replicas < 1:
        raise BudgetError(f"replicas 至少为 1，实际 {replicas}")
    if bouncer_instances < 1:
        raise BudgetError(f"bouncer_instances 至少为 1，实际 {bouncer_instances}")

    pg_app_total = pg_max_connections - superuser_reserved - admin_reserve
    if pg_app_total <= 0:
        raise BudgetError(
            f"PG max_connections={pg_max_connections} 扣掉保留后没有可用额度（={pg_app_total}）"
        )

    # 第一层：客户端 → bouncer
    client_capacity = bouncer_instances * bouncer_max_client_conn
    requested_pool = pool_size + max_overflow
    per_replica = pg_app_total // replicas
    per_replica_pool = per_replica - non_pool_connections_per_replica
    reasons: list[str] = []
    feasible = True

    if replicas * requested_pool > client_capacity:
        feasible = False
        reasons.append(
            f"客户端侧超限：{replicas} 副本 × {requested_pool} = "
            f"{replicas * requested_pool} > bouncer 容量 "
            f"{bouncer_instances} × {bouncer_max_client_conn} = {client_capacity}"
        )

    # 第二层：bouncer → PG
    server_capacity = bouncer_instances * bouncer_default_pool_size
    if server_capacity > pg_app_total:
        feasible = False
        reasons.append(
            f"服务端侧超限：bouncer {bouncer_instances} 实例 × "
            f"DEFAULT_POOL_SIZE {bouncer_default_pool_size} = {server_capacity} "
            f"> PG 应用可用总额度 {pg_app_total}"
        )

    # 单副本自身也可能分不到（与直连同一条约束，只是额度按 PG 算）
    if per_replica_pool <= 0:
        feasible = False
        reasons.append(
            f"{replicas} 个副本时单副本只分到 {per_replica} 条，扣掉池外后为 {per_replica_pool}"
        )

    # 最紧的那一层：谁的余量最小
    binding = "bouncer_max_client_conn"
    if feasible:
        client_headroom = client_capacity - replicas * requested_pool
        server_headroom = pg_app_total - server_capacity
        binding = (
            "bouncer_max_client_conn" if client_headroom <= server_headroom
            else "pg_max_connections"
        )

    return ConnectionBudget(
        pg_app_total=pg_app_total,
        per_replica=per_replica,
        per_replica_pool=per_replica_pool,
        feasible=feasible,
        reasons=tuple(reasons),
        binding_constraint=binding,
    )
