"""PgBouncer 灰度计划纯函数与 CLI 的守卫。"""
from __future__ import annotations

import json

from scripts.ops import pgbouncer_canary_plan as plan


def test_plan_has_2_25_100_stages_without_deploying():
    stages = plan.build_canary_plan(
        pg_max_connections=500,
        replicas=2,
        pool_size=50,
        max_overflow=100,
    )
    assert [stage.traffic_percent for stage in stages] == [2, 25, 100]
    assert all(stage.budget.feasible for stage in stages)
    assert all("RLS 与 SET LOCAL 隔离通过" in stage.required_gates for stage in stages)


def test_plan_is_infeasible_at_four_replicas_with_default_pool():
    stages = plan.build_canary_plan(
        pg_max_connections=500,
        replicas=4,
        bouncer_max_client_conn=500,
        max_overflow=100,
    )
    assert [stage.traffic_percent for stage in stages] == [2, 25, 100]
    assert all(not stage.budget.feasible for stage in stages)
    assert all(stage.budget.reasons for stage in stages)


def test_plan_uses_bouncer_client_and_server_constraints():
    client_limited = plan.build_canary_plan(
        pg_max_connections=5000,
        replicas=4,
        bouncer_max_client_conn=500,
        bouncer_default_pool_size=50,
        pool_size=50,
        max_overflow=100,
    )
    assert "客户端侧超限" in " ".join(client_limited[0].budget.reasons)

    server_limited = plan.build_canary_plan(
        pg_max_connections=100,
        replicas=1,
        bouncer_max_client_conn=10000,
        bouncer_default_pool_size=200,
        pool_size=10,
        max_overflow=10,
    )
    assert "服务端侧超限" in " ".join(server_limited[0].budget.reasons)


def test_cli_dry_run_outputs_json_and_nonzero_for_infeasible(capsys):
    exit_code = plan.main([
        "--pg-max-connections", "500",
        "--replicas", "4",
        "--bouncer-max-client-conn", "500",
        "--dry-run",
    ])
    assert exit_code == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["mode"] == "dry-run"
    assert payload["overall_feasible"] is False
    assert [item["traffic_percent"] for item in payload["stages"]] == [2, 25, 100]


def test_cli_dry_run_does_not_contain_deployment_action(capsys):
    exit_code = plan.main([
        "--pg-max-connections", "5000",
        "--replicas", "2",
        "--dry-run",
    ])
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["deployment"].startswith("未执行")
