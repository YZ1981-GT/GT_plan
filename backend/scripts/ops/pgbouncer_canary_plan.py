"""生成 PgBouncer transaction 模式灰度计划（只计划，不部署）。

用法：
    python backend/scripts/ops/pgbouncer_canary_plan.py --dry-run \
      --pg-max-connections 500 --replicas 4 --pool-size 20 --max-overflow 30

灰度阶段固定为 2% → 25% → 100%。比例是**流量比例**，不是副本比例；
连接预算按目标副本数与池配置逐阶段计算。预算不可行时 dry-run 仍输出完整计划，
但退出码为 2，避免「先切流、后发现 PG 连接不够」。

本工具不调用 Docker/Kubernetes/云平台 API。真实切流必须由部署系统另行执行，
并在每阶段通过 RLS/SET LOCAL、取消、prepared statement 与健康指标门禁后人工/流水线推进。
"""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from typing import Any

from app.core.connection_budget import ConnectionBudget, compute_bouncer_budget

__all__ = ["CANARY_STAGES", "CanaryStage", "build_canary_plan", "main"]

CANARY_STAGES: tuple[int, ...] = (2, 25, 100)


@dataclass(frozen=True)
class CanaryStage:
    traffic_percent: int
    replicas: int
    budget: ConnectionBudget
    required_gates: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["budget"] = asdict(self.budget)
        return data


def build_canary_plan(
    *,
    pg_max_connections: int,
    replicas: int,
    bouncer_instances: int = 1,
    bouncer_max_client_conn: int = 10000,
    bouncer_default_pool_size: int = 50,
    pool_size: int = 50,
    max_overflow: int = 100,
    superuser_reserved: int = 3,
    admin_reserve: int = 8,
    non_pool_connections_per_replica: int = 3,
) -> tuple[CanaryStage, ...]:
    """按目标副本数生成三阶段计划；任何阶段预算不可行仍保留计划但标失败。"""
    budget = compute_bouncer_budget(
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
    gates = (
        "RLS 与 SET LOCAL 隔离通过",
        "prepared statement 缓存关闭（statement_cache_size=0）",
        "取消后 rollback 且连接可复用",
        "pool wait/timeout、event-loop lag、错误率无回退",
        "当前阶段观察窗口完成并保留原始指标",
    )
    return tuple(
        CanaryStage(traffic_percent=traffic, replicas=replicas, budget=budget, required_gates=gates)
        for traffic in CANARY_STAGES
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="生成 PgBouncer transaction 模式 2/25/100 灰度计划")
    parser.add_argument("--pg-max-connections", type=int, required=True)
    parser.add_argument("--replicas", type=int, required=True)
    parser.add_argument("--bouncer-instances", type=int, default=1)
    parser.add_argument("--bouncer-max-client-conn", type=int, default=10000)
    parser.add_argument("--bouncer-default-pool-size", type=int, default=50)
    parser.add_argument("--pool-size", type=int, default=50)
    parser.add_argument("--max-overflow", type=int, default=100)
    parser.add_argument("--superuser-reserved", type=int, default=3)
    parser.add_argument("--admin-reserve", type=int, default=8)
    parser.add_argument("--non-pool-connections-per-replica", type=int, default=3)
    parser.add_argument("--dry-run", action="store_true", help="只输出 JSON 计划；未指定也不会部署")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    # `dry_run` 只是 CLI 控制项，不进入预算函数。
    values = vars(args).copy()
    values.pop("dry_run", None)
    plan = build_canary_plan(**values)
    payload = {
        "mode": "dry-run",
        "stages": [stage.to_dict() for stage in plan],
        "overall_feasible": all(stage.budget.feasible for stage in plan),
        "deployment": "未执行；需部署系统按阶段门禁推进",
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["overall_feasible"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
