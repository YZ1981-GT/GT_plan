"""需求 1.10：29 条历史 ``wp_formula`` 的真 PG 重放（spec formula-hub-integrity-closure 任务 25）。

🔴 2026-10-29 补齐：本文件原先**不存在** —— 任务 25 的 25-2 段自记「29 行重放留后续任务 26…本段写占位，
不硬写假测试」，任务 26 没有补上，于是需求 1.10 与变异 #10 一起成了假绿（变异 #10 记录就是 **0/35 打红**）。

做法：在回滚事务里把真库软删项目 ``辽宁卫生服务有限公司`` 的 29 条公式及其底稿复制到【测试】项目
（原行只读、一个字节不改），调**生产** ``FormulaRuntimeCoordinator.generate_mutation_plan`` 产计划、
再经生产 workpaper adapter ``apply_many`` 落库，逐行与 `_replay29_gold`（测试内独立实现）比。

断言（需求 1.10 原文逐条）：
- 跨底稿条目 = 金标准值；
- 自引用与 A↔B 环 ``blocked``；
- 字面量条目值 = 字面量且与存值一致（值不变）；
- 错 sheet 目标 ``blocked`` 且该底稿 ``html_data`` 键集合不变；
- 未被成功写入的底稿 ``parsed_data`` 规范化 JSON 的 sha256 前后相等。

另附一条**不属于 29 行**、专为关闭变异 #10 的用例：29 行全部经「批内依赖」或「字面量」求值，
一次也没走到 ``wp_ref_strict.read_wp_ref_strict``，所以必须另造列名两参引用才能让该变异可见。
"""
from __future__ import annotations

import ast
import uuid
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import text

from app.services.formula_runtime.coordinator import FormulaRuntimeCoordinator
from tests.formula_hub import _replay29_gold as gold
from tests.formula_hub._replay29_world import (
    REPLAY_YEAR,
    build_replay_world,
    html_key_sets,
    parsed_digests,
)

pytestmark = pytest.mark.pg_only

#: F2 给出的形态分布（现扫共享库复核一致）：字面量 11 / 自引用 13 / 跨底稿 5
EXPECTED_TOTAL = 29
#: F41：2 条 ``sheet_name='Playwright自定义底稿'`` 与 ``html_data`` 键（wp_code）不符
EXPECTED_SHEET_MISMATCH = 2


def _decimal(value: object) -> Decimal:
    return Decimal(str(value))


async def test_replay_29_rows_against_gold(pg_tx):
    """29 行逐行重放：生产计划的每条结论与值都等于测试内独立算出的金标准。"""
    world = await build_replay_world(pg_tx)
    rows = world.rows
    assert len(rows) == EXPECTED_TOTAL, f"复制到【测试】项目的公式条数应为 {EXPECTED_TOTAL}，实得 {len(rows)}"

    # —— 夹具非空转自证 ——
    mismatched = [r for r in rows if (r.stable_sheet_key or "").strip() not in
                  {k.strip() for k in r.html_keys}]
    assert len(mismatched) == EXPECTED_SHEET_MISMATCH, (
        f"错 sheet 行应为 {EXPECTED_SHEET_MISMATCH} 条，实得 {len(mismatched)}："
        f"{[(r.wp_code, r.stable_sheet_key, r.html_keys) for r in mismatched]}")

    expected, unknown = gold.evaluate(rows)
    assert unknown == [], f"金标准遇到未识别写法（需求 1.10 要求为 0）：{unknown}"

    gold_ok = {fid for fid, o in expected.items() if o.state == "ok"}
    gold_blocked = {fid for fid, o in expected.items() if o.state == "blocked"}
    assert len(gold_ok) + len(gold_blocked) == EXPECTED_TOTAL
    # 金标准本身的形态自证：blocked 必须正好是 13 条（13 自引用，其中 2 条先被目标表校验挡下）
    assert len(gold_blocked) == 13, f"金标准 blocked 应为 13 条，实得 {len(gold_blocked)}"
    assert len(gold_ok) == 16, f"金标准 ok 应为 16 条（11 字面量 + 5 跨底稿），实得 {len(gold_ok)}"

    before_digests = await parsed_digests(pg_tx, [r.wp_id for r in rows])
    before_keys = await html_key_sets(pg_tx, [r.wp_id for r in rows])

    # —— 生产路径：产计划 ——
    coordinator = FormulaRuntimeCoordinator(pg_tx)
    plan = await coordinator.generate_mutation_plan(world.project_id, REPLAY_YEAR, ["workpaper"])

    produced_ok = {str(m.source_formula_id): m for m in plan.mutations if m.source_formula_id}
    diagnostics = (
        f"\n  plan.mutations={len(plan.mutations)}"
        f" scope_failures={len(plan.scope_failures)} issues={len(plan.issues)}"
        f"\n  failures={[(f.get('kind'), str(f.get('detail'))[:120]) for f in plan.scope_failures[:6]]}"
        f"\n  issues={[str(i)[:120] for i in plan.issues[:4]]}"
        f"\n  mutation 样本={[(m.target.addr_id, m.before_value, m.after_value) for m in plan.mutations[:3]]}"
    )
    assert set(produced_ok) == gold_ok, (
        "生产计划产出 mutation 的公式集合与金标准 ok 集合不符：\n"
        f"  只生产有：{sorted(set(produced_ok) - gold_ok)}\n"
        f"  只金标准有：{sorted(gold_ok - set(produced_ok))}" + diagnostics)

    blocked_failures = [f for f in plan.scope_failures if f.get("kind") == "typed_eval_blocked"]
    assert len(blocked_failures) == len(gold_blocked), (
        f"blocked 条数应为 {len(gold_blocked)}，实得 {len(blocked_failures)}："
        f"{[f.get('detail') for f in blocked_failures]}")

    # —— 逐行比值（跨底稿 + 字面量）——
    by_id = {str(r.formula_id): r for r in rows}
    mismatches: list[str] = []
    for fid, mutation in produced_ok.items():
        row, want = by_id[fid], expected[fid]
        got = _decimal(mutation.after_value)
        if got != want.value:
            mismatches.append(f"{row.wp_code}/{row.target_cell} {row.expression!r}："
                              f"生产 {got} ≠ 金标准 {want.value}")
    assert mismatches == [], "逐行值不符：\n  " + "\n  ".join(mismatches)

    # 跨底稿条目确有引用、且不是空转
    cross = [fid for fid in gold_ok if expected[fid].refs]
    assert len(cross) == 5, f"跨底稿条目应为 5 条，实得 {len(cross)}"
    assert all(_decimal(produced_ok[fid].after_value) == expected[fid].value for fid in cross)

    # 字面量条目：值 = 字面量，且与底稿里的存值一致（需求 1.10「值不变」）
    literals = [fid for fid in gold_ok if not expected[fid].refs]
    assert len(literals) == 11, f"字面量条目应为 11 条，实得 {len(literals)}"
    for fid in literals:
        row = by_id[fid]
        stored = gold._stored(row.cells, gold.cell_key(row.target_cell))
        assert stored == expected[fid].value, (
            f"{row.wp_code}/{row.target_cell} 字面量 {row.expression!r} 的金标准 {expected[fid].value}"
            f" 与底稿存值 {stored} 不一致 ⇒「值不变」不成立")
        assert _decimal(produced_ok[fid].before_value) == stored

    # —— blocked 的原因分类：11 条循环引用 + 2 条目标表 ——
    reasons = [str(f.get("detail") or "") for f in blocked_failures]
    cyclic = [r for r in reasons if "循环引用" in r]
    sheet_missing = [r for r in reasons if "工作表" in r]
    assert len(cyclic) == 11, f"「循环引用」应为 11 条，实得 {len(cyclic)}：{reasons}"
    assert len(sheet_missing) == EXPECTED_SHEET_MISMATCH, (
        f"目标工作表类原因应为 {EXPECTED_SHEET_MISMATCH} 条，实得 {len(sheet_missing)}：{reasons}")

    # —— 生产路径：apply ——
    adapter = coordinator.build_adapter_map({"workpaper"}).get("workpaper")
    assert adapter is not None, "拿不到 workpaper adapter，apply 无法按生产路径执行"
    applied = await adapter.apply_many(plan.mutations)
    await pg_tx.flush()
    assert len(applied) == len(plan.mutations), (
        f"apply_many 落库条数 {len(applied)} ≠ 计划条数 {len(plan.mutations)}")

    # —— 错 sheet 的底稿：html_data 键集合不变（不得新建工作表）——
    after_keys = await html_key_sets(pg_tx, [r.wp_id for r in rows])
    for row in mismatched:
        assert after_keys[row.wp_id] == before_keys[row.wp_id], (
            f"{row.wp_code} 的 html_data 键集合被改了："
            f"{before_keys[row.wp_id]} → {after_keys[row.wp_id]}")
    assert after_keys == before_keys, "任何底稿都不应新增 / 删除 html_data 工作表键"

    # —— 未被成功写入的底稿：parsed_data 规范化 sha256 前后相等 ——
    written = {produced_ok[fid] and by_id[fid].wp_id for fid in produced_ok}
    after_digests = await parsed_digests(pg_tx, [r.wp_id for r in rows])
    untouched = [r for r in rows if r.wp_id not in written]
    assert untouched, "没有「未被写入」的底稿 ⇒ 该判据空转"
    drifted = [f"{r.wp_code}" for r in untouched
               if after_digests[r.wp_id] != before_digests[r.wp_id]]
    assert drifted == [], f"未被成功写入的底稿 parsed_data 变了：{drifted}"


async def test_strict_external_read_missing_column_key_is_not_zero(pg_tx):
    """变异 #10 的可见性用例：列名两参引用取不到键时必须 blocked 并给原因，不得代入 0。

    29 行全部经批内依赖或字面量求值，一次也没走到 ``read_wp_ref_strict`` ⇒ 变异 #10
    在 29 行重放里**仍不可见**。这里另造一条 ``WP('<另一底稿>','审定数')``：目标底稿的
    ``parsed_data`` 没有「审定数」顶层键，严格读取必须报 missing，整条公式 blocked。
    """
    world = await build_replay_world(pg_tx)
    donor, host = world.rows[0], world.rows[1]
    assert donor.wp_code != host.wp_code

    # 把宿主那条公式改成列名两参引用（指向另一份底稿、该底稿没有这个列名键）
    await pg_tx.execute(
        text("UPDATE wp_formula SET expression = :expr WHERE id = :fid"),
        {"expr": f"WP('{donor.wp_code}','审定数')", "fid": host.formula_id},
    )
    # 目标表校验要先过，否则会被「目标工作表不存在」挡在严格读取之前
    await pg_tx.execute(
        text("UPDATE wp_formula SET stable_sheet_key = :k WHERE id = :fid"),
        {"k": host.html_keys[0], "fid": host.formula_id},
    )
    await pg_tx.flush()

    donor_pd = (await pg_tx.execute(
        text("SELECT parsed_data FROM working_paper WHERE id = :wid AND is_deleted = false"),
        {"wid": donor.wp_id})).scalar_one()
    assert "审定数" not in (donor_pd or {}), "夹具空转：目标底稿居然有「审定数」键"

    plan = await FormulaRuntimeCoordinator(pg_tx).generate_mutation_plan(
        world.project_id, REPLAY_YEAR, ["workpaper"])

    produced = {str(m.source_formula_id) for m in plan.mutations if m.source_formula_id}
    assert str(host.formula_id) not in produced, (
        "列名两参取不到值却产出了 mutation —— 这正是变异 #10（缺键返回 0）的表现")
    details = [str(f.get("detail") or "") for f in plan.scope_failures]
    assert any("审定数" in d for d in details), (
        f"blocked 原因里应点名取不到的列名「审定数」，实得：{details}")


def test_gold_evaluator_is_independent() -> None:
    """独立性守卫：金标准模块只许 import 标准库，不得碰任何生产模块（ADR-FHIC-24 同纪律）。"""
    path = Path(__file__).with_name("_replay29_gold.py")
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    forbidden = {name for name in imported if name in {"app", "tests"}}
    assert forbidden == set(), f"金标准模块不得 import 生产 / 测试包：{sorted(forbidden)}"
    assert "re" in imported and "decimal" in imported, f"金标准模块的 import 异常：{sorted(imported)}"
