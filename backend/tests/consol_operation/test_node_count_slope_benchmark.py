"""批 8 Task 8.1：10/100/500 节点斜率基准的 pytest 回归守卫。

复用 `backend/scripts/analyze/consol_lifecycle_slope_benchmark.py` 的真实代码路径度量，
断言 R10 性能不变量在节点数 N 从 10 → 100 → 500 时成立：

- 每 target/run 恰一次 build_tree、恰一次 load_calc_basis（R10.1，斜率 0）；
- build_tree / load_calc_basis 的 SQL 语句数对 N 有界（递归 CTE / IN 列表，斜率≈0，无 N² 爆炸）；
- push_targets 的 SQL 恒 1（递归 CTE）；
- 附注 fill_note_sections 的 SQL 对章节数 S 的斜率为每章固定小常数（R10.2 / 批 5.5，
  view_context 一次构建，不含 CalcBasis 级开销）。

该守卫与批 3 的 mock 调用次数守卫（test_consol_basis_reuse_and_push_targets.py /
test_push_calc_basis_reuse.py）互补：那些验证「每 target 一次」的接线，本守卫验证在真实库
上**随规模扩大**的斜率界。标记 perf，可用 `-m "not perf"` 跳过。
"""
from __future__ import annotations

import pytest

import tests.conftest  # noqa: F401 - 注册全模型与 SQLite 方言补丁
from scripts.analyze.consol_lifecycle_slope_benchmark import (
    evaluate_slopes,
    measure_point,
    run_benchmark,
)
from sqlalchemy.ext.asyncio import create_async_engine

from app.models.base import Base
from scripts.analyze.consol_lifecycle_slope_benchmark import _TABLES

pytestmark = pytest.mark.perf

# 守卫用真实 10/100/500；单点度量 <100ms，整测 <1s。
_NODE_TARGETS = (10, 100, 500)


@pytest.mark.asyncio
async def test_node_count_slope_invariants_hold_10_100_500():
    """全链斜率不变量：tree/basis 次数平斜、SQL 对 N 有界、附注对 S 斜率为小常数。"""
    report = await run_benchmark(_NODE_TARGETS)

    # 核心断言：无任何不变量违规（违规列表即回归信号）。
    assert report.ok, "斜率不变量违规：\n" + "\n".join(report.violations)

    # 显式复述关键斜率，保证度量本身被真的计算（避免空 report 伪绿）。
    assert report.tree_build_calls_slope == 0.0
    assert report.basis_load_calls_slope == 0.0
    assert report.tree_sql_slope == 0.0
    assert report.basis_sql_slope == 0.0
    assert 0.0 < report.note_section_sql_slope < 4.5

    # 每个规模点都真的播种并度量到了对应节点数（10→12, 100→102, 500→502：根合并+根差额+母公司）。
    assert [p.node_target for p in report.points] == list(_NODE_TARGETS)
    for p in report.points:
        assert p.actual_node_count >= p.node_target, (
            f"N={p.node_target} 实际节点 {p.actual_node_count} 少于目标，播种未生效"
        )
        assert p.tree_build_calls == 1
        assert p.basis_load_calls == 1
        assert p.push_targets_sql == 1
        # 附注章节真的跑过（S=1→4、S=10→31），不是全章静默失败造出的假 0。
        assert p.note_section_sql_by_s.get(1, 0) >= 2
        assert p.note_section_sql_by_s.get(10, 0) > p.note_section_sql_by_s.get(1, 0)


@pytest.mark.asyncio
async def test_tree_and_basis_sql_do_not_grow_across_scales():
    """build_tree / load_calc_basis 的 SQL 条数在 10/100/500 三档恒定（IN 列表 / 递归 CTE）。"""
    report = await run_benchmark(_NODE_TARGETS)
    tree_sqls = {p.tree_sql for p in report.points}
    basis_sqls = {p.basis_sql for p in report.points}
    # 三档各自只有一个取值 ⇒ 不随 N 变化。
    assert len(tree_sqls) == 1, f"build_tree SQL 随 N 变化：{[(p.node_target, p.tree_sql) for p in report.points]}"
    assert len(basis_sqls) == 1, f"load_calc_basis SQL 随 N 变化：{[(p.node_target, p.basis_sql) for p in report.points]}"


@pytest.mark.asyncio
async def test_note_section_slope_guard_flags_per_section_basis_rebuild():
    """反证：附注斜率守卫会抓住「view_context 退回章节循环内重建」的回归（非伪绿）。

    构造一个 note_section_sql_by_s 表现为「每章多出一整套 CalcBasis 装载」的度量点
    （S=1→14、S=10→59，斜率 5.0），evaluate_slopes 必须将其判为违规。
    """
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all, tables=_TABLES)
        point = await measure_point(engine, 10)
    finally:
        await engine.dispose()

    # 健康基线：真实度量点必须通过。
    healthy = evaluate_slopes([point])
    assert healthy.ok, healthy.violations

    # 注入回归形态：把附注斜率抬到 CalcBasis-per-section 水平（S=1→14, S=10→59 ⇒ 斜率 5.0）。
    import copy

    regressed_point = copy.deepcopy(point)
    regressed_point.note_section_sql_by_s = {1: 14, 10: 59}
    regressed = evaluate_slopes([regressed_point])
    assert not regressed.ok
    assert any("附注章节 SQL 对 S 斜率" in v for v in regressed.violations)
