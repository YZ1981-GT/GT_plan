"""E1/E4：连接预算按副本数计算（纯计算，不需要真实 PG）。

spec: `platform-heavy-jobs-and-capacity-closure` E1（连接预算按副本计算）/ E4（容量环境基础）。

## 为什么这些断言值得写

`DB_POOL_SIZE=50` / `DB_MAX_OVERFLOW=100` 的注释写着「6000 并发优化」，但**没有副本维度**。
8 副本 = 8 × 150 = 1200 连接，而 PG 默认 `max_connections=100` ⇒ 一扩容就
`too many clients`，且报错发生在**扩容那一刻**，本地单副本永远测不出来。

本文件用纯计算把「多少副本配多少池」钉死，让配置在提交期就暴露不可行，
而不是等上线扩容时才发现。

## 判据设计要点

- **不可行必须报出「差多少」**，不能把 pool_size 钳到 0 静默通过（静默钳位 = 线上连接不够用时
  表现成随机超时，比启动失败难查得多）。
- **经 PgBouncer 是两层约束**：客户端侧（副本 → bouncer）与服务端侧（bouncer → PG）。
  只检查一层会在另一层打满（见 `compute_bouncer_budget` docstring）。
- **默认配置在合理副本数下必须可行**：如果连 1~4 副本都不可行，说明默认值本身有问题，
  这条断言防止「算法对了但默认配置是错的」。
"""
from __future__ import annotations

import pytest

from app.core.connection_budget import (
    BudgetError,
    compute_bouncer_budget,
    compute_direct_budget,
)


# ---------------------------------------------------------------------------
# 判据 1：默认配置在 1/2/4 副本下可行（8 副本是扩容目标，需按 PG 上限核对）
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("replicas", [1, 2])
def test_default_config_feasible_only_up_to_two_replicas(replicas: int):
    """🔴 **实测结论（2026-11-16）**：默认池配置（50 + 100 = 150/副本）在 PG 500
    连接下**只支持到 2 副本**；3 副本起就不可行。

    这是本 spec 最该暴露的数字：`DB_POOL_SIZE=50` / `DB_MAX_OVERFLOW=100` 的注释
    写着「6000 并发优化」，但当时是**单副本**思维。E2 要扩到 2/4/8 worker，
    默认配置在 4 副本时：
      PG 500 − superuser 3 − admin 8 = 489 总额度
      489 / 4 = 122/副本，扣池外 3 条 = 119 池额度
      需求 150 ⇒ **短 31**，4 × 150 = 600 > 489
    ⇒ 扩到 4 副本**必须**先调池配置（或上 PgBouncer），不是「优化建议」而是**硬阻塞**。
    """
    budget = compute_direct_budget(
        pg_max_connections=500, replicas=replicas,
        pool_size=50, max_overflow=100,
    )
    assert budget.feasible is True, (
        f"{replicas} 副本下默认配置不可行（预期可行）：{budget.reasons}"
    )
    assert budget.per_replica_pool >= 50 + 100


def test_default_config_becomes_infeasible_at_four_replicas():
    """4 副本起默认配置不可行 —— 这是 E2 扩容梯度的第一个硬阻塞点。

    与上一条构成双向对照：不能只断言「1~2 可行」而不钉住「4 不行」，
    否则有人把池配置改大后，这个结论会静默失效。
    """
    budget = compute_direct_budget(
        pg_max_connections=500, replicas=4,
        pool_size=50, max_overflow=100,
    )
    assert budget.feasible is False, (
        f"4 副本 × 150 在 PG 500 下应不可行（489 总额度），却判可行：{budget}"
    )
    joined = " ".join(budget.reasons)
    assert "150" in joined and "119" in joined, (
        f"原因里应写明「需求 150 vs 池额度 119」，实际：{joined}"
    )


def test_default_config_infeasible_at_8_replicas_with_small_pg():
    """8 副本 + PG 200 连接时，默认配置（150/副本）必须报**不可行**。

    这正是「一扩容就 too many clients」的现场：8 × 150 = 1200 > 200 − 保留。
    算法必须在这里拒绝，而不是等到线上。
    """
    budget = compute_direct_budget(
        pg_max_connections=200, replicas=8,
        pool_size=50, max_overflow=100,
    )
    assert budget.feasible is False, "8 副本 × 150 装不进 PG 200 连接，却判可行"
    assert budget.reasons, "不可行时必须写明原因（差多少）"
    # 原因里必须带上实际数字，便于运维一眼算账
    joined = " ".join(budget.reasons)
    assert "1200" in joined or "150" in joined, f"原因里应带实际数字，实际：{joined}"


def test_infeasible_budget_still_reports_numbers_not_zeros():
    """不可行时额度字段必须是**算出来的值**，不能钳到 0（钳位会掩盖「差多少」）。"""
    budget = compute_direct_budget(
        pg_max_connections=200, replicas=8, pool_size=50, max_overflow=100,
    )
    assert budget.per_replica == (200 - 3 - 8) // 8  # 189 // 8 = 23
    assert budget.per_replica == 23, f"单副本额度算错：{budget.per_replica}"
    assert budget.per_replica_pool == 23 - 3, "池额度 = 单副本额度 − 池外连接"


# ---------------------------------------------------------------------------
# 判据 2：参数校验（负数 / 零副本必须拒绝，不能静默当成 0）
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({"pg_max_connections": -1, "replicas": 1}, "非负整数"),
        ({"pg_max_connections": 100, "replicas": 0}, "至少为 1"),
        ({"pg_max_connections": 100, "replicas": 1, "pool_size": -5}, "非负整数"),
    ],
)
def test_direct_budget_rejects_invalid_input(kwargs: dict, message: str):
    with pytest.raises(BudgetError, match=message):
        compute_direct_budget(**kwargs)


def test_budget_error_when_pg_has_no_headroom():
    """PG 保留扣完没有额度时，必须抛错而不是返回可行。"""
    with pytest.raises(BudgetError, match="没有可用额度"):
        compute_direct_budget(
            pg_max_connections=10, replicas=1,
            superuser_reserved=3, admin_reserve=8,
        )


# ---------------------------------------------------------------------------
# 判据 3：PgBouncer 是两层约束（只检查一层会在另一层打满）
# ---------------------------------------------------------------------------


def test_bouncer_client_side_overflow_is_detected():
    """副本 × 池 > bouncer `MAX_CLIENT_CONN` 时必须报不可行（客户端侧）。

    这条对应真实故障：bouncer 报 `no more connections allowed`，
    运维看到的是 bouncer 的错、不是 PG 的，容易误判成「PG 连接池配小了」。
    """
    budget = compute_bouncer_budget(
        pg_max_connections=5000,
        bouncer_instances=1,
        replicas=8,
        bouncer_max_client_conn=1000,   # 8 × 150 = 1200 > 1000
        bouncer_default_pool_size=50,
        pool_size=50, max_overflow=100,
    )
    assert budget.feasible is False
    joined = " ".join(budget.reasons)
    assert "客户端侧超限" in joined, f"应报客户端侧超限，实际：{joined}"
    assert "1200" in joined and "1000" in joined, "原因里必须带实际数字"


def test_bouncer_server_side_overflow_is_detected():
    """bouncer `DEFAULT_POOL_SIZE` × 实例 > PG 额度时必须报不可行（服务端侧）。

    这条对应相反的错误：bouncer 客户端侧配得很大，但它到 PG 的 server 连接
    把 PG 打满 —— 只检查客户端侧会漏掉。
    """
    budget = compute_bouncer_budget(
        pg_max_connections=100,
        bouncer_instances=1,
        replicas=1,
        bouncer_max_client_conn=10000,
        bouncer_default_pool_size=200,  # 200 > (100 - 3 - 8) = 89
        pool_size=50, max_overflow=100,
    )
    assert budget.feasible is False
    joined = " ".join(budget.reasons)
    assert "服务端侧超限" in joined, f"应报服务端侧超限，实际：{joined}"


def test_bouncer_both_layers_ok_identifies_binding_constraint():
    """两层都够时，必须报出**最紧的那一层**（谁的余量最小）。

    运维要靠这个字段决定「先扩 bouncer 还是先扩 PG」。
    """
    budget = compute_bouncer_budget(
        pg_max_connections=500,
        bouncer_instances=2,
        replicas=4,
        bouncer_max_client_conn=1000,   # 容量 2000，需求 600 ⇒ 余 1400
        bouncer_default_pool_size=50,   # 容量 100，PG 额度 489 ⇒ 余 389
        pool_size=50, max_overflow=100,
    )
    assert budget.feasible is True, f"该配置应可行：{budget.reasons}"
    assert budget.binding_constraint == "pg_max_connections", (
        f"PG 侧余量（389）小于 bouncer 客户端侧（1400），瓶颈应是 PG；"
        f"实际报 {budget.binding_constraint}"
    )


def test_bouncer_binding_constraint_flips_when_client_side_tighter():
    """反向对照：客户端侧更紧时必须报 bouncer（证明这个字段不是常量）。"""
    budget = compute_bouncer_budget(
        pg_max_connections=5000,
        bouncer_instances=1,
        replicas=4,
        bouncer_max_client_conn=700,    # 容量 700，需求 600 ⇒ 余 100
        bouncer_default_pool_size=50,   # 容量 50，PG 额度 4989 ⇒ 余 4939
        pool_size=50, max_overflow=100,
    )
    assert budget.feasible is True
    assert budget.binding_constraint == "bouncer_max_client_conn", (
        f"bouncer 侧余量（100）远小于 PG 侧（4939），瓶颈应是 bouncer；"
        f"实际报 {budget.binding_constraint}"
    )


# ---------------------------------------------------------------------------
# 判据 4：与真实平台默认值对齐（防止「算法对了但默认配置错了」）
# ---------------------------------------------------------------------------


def test_platform_default_settings_match_budget_assumptions():
    """`app/core/config.py` 的池默认值必须与预算模块的默认参数一致。

    🔴 这条防的是「两处各写一份默认值」：预算模块按 50/100 算，
    而 `config.py` 哪天改成 200/400，预算就悄悄不再描述实际情况了。
    """
    from app.core.config import settings

    assert settings.DB_POOL_SIZE == 50, (
        f"config.DB_POOL_SIZE={settings.DB_POOL_SIZE}，预算模块按 50 计算，两处必须一致"
    )
    assert settings.DB_MAX_OVERFLOW == 100, (
        f"config.DB_MAX_OVERFLOW={settings.DB_MAX_OVERFLOW}，预算模块按 100 计算"
    )
