"""利润表归属行 8 行的真库状态守卫（spec formula-hub-integrity-closure 任务 19；需求 6.6；ADR-FHIC-23；决策项 X2）。

判据：国企两套 IS-074 / IS-075、上市两套 IS-051 / IS-052 每行要么已是目标定义（需求 6.1；按行名解析，与升级工具同一份
``resolve_targets``），要么逐字等于对应的已知坏式（升级工具 ``KNOWN_BAD``，待升级）；出现第三种定义（含缺行）即红。
待升级清单写进 junit property ``pending_upgrade``（X2 执行前应为 8 行、执行后 0 行）。行与行名用本文件自己的 SQL 读，
归类判定在本文件另写，不调用工具的 ``classify``（工具的旧值比对被改坏时本守卫不跟着变）。

自检 :func:`test_injected_third_definition_is_caught`：回滚事务内把国企合并 IS-075 改成第三种定义 ⇒ 问题清单恰好多这一条。
"""
from __future__ import annotations

import json

import pytest
from sqlalchemy import text

from scripts.fix.republish_report_seed_rows import KNOWN_BAD, STANDARDS, Target, resolve_targets
from tests.formula_hub._report_definition_rows import require_snapshot

pytestmark = pytest.mark.pg_only

_ROWS_SQL = text(
    "SELECT applicable_standard, row_code, row_name, formula FROM report_config WHERE is_deleted = false "
    "AND report_type = 'income_statement' AND applicable_standard = ANY(:stds)")


async def _state(db) -> tuple[dict[tuple[str, str], Target], dict[tuple[str, str], str | None]]:
    rows = (await db.execute(_ROWS_SQL, {"stds": list(STANDARDS)})).all()
    targets = resolve_targets((r[0], r[1], r[2] or "") for r in rows)
    return targets, {(r[0], r[1]): r[3] for r in rows if (r[0], r[1]) in KNOWN_BAD}


def verdicts(targets: dict[tuple[str, str], Target],
             current: dict[tuple[str, str], str | None]) -> tuple[list[str], list[dict]]:
    """（问题清单, 待升级清单）。已是目标 = 去首尾空白后等于目标（目标无公式时，无公式或空白都算）。"""
    problems: list[str] = []
    pending: list[dict] = []
    for key in sorted(KNOWN_BAD):
        target = targets[key]
        if key not in current:
            problems.append(f"{key[0]} {key[1]}「{target.row_name}」缺行（未删的准则行里没有）")
            continue
        formula = current[key]
        if formula == KNOWN_BAD[key]:
            pending.append({"standard": key[0], "row_code": key[1], "row_name": target.row_name, "old": formula,
                            "target": target.formula})
        elif (formula or "").strip() != (target.formula or ""):
            problems.append(f"{key[0]} {key[1]}「{target.row_name}」第三种定义 {formula!r}：既不是目标 "
                            f"{target.formula!r}，也不是已知坏式 {KNOWN_BAD[key]!r}")
    return problems, pending


async def test_attribution_rows_are_target_or_known_bad(pg_tx, request):
    targets, current = await _state(pg_tx)
    problems, pending = verdicts(targets, current)
    request.node.user_properties.extend([("pending_count", str(len(pending))),
                                         ("pending_upgrade", json.dumps(pending, ensure_ascii=False))])
    assert len(targets) == 8 and problems == [], problems


async def test_injected_third_definition_is_caught(pg_tx):
    await require_snapshot(pg_tx, "归属行状态守卫的自检（回滚事务内改写一行）")
    targets, current = await _state(pg_tx)
    before, _ = verdicts(targets, current)
    key, third = ("soe_consolidated", "IS-075"), "ROW('IS-049')"
    changed = await pg_tx.execute(text(
        "UPDATE report_config SET formula = :f WHERE is_deleted = false AND report_type = 'income_statement' "
        "AND applicable_standard = :s AND row_code = :c"), {"f": third, "s": key[0], "c": key[1]})
    assert changed.rowcount == 1
    after, _ = verdicts(*await _state(pg_tx))
    expected = (f"soe_consolidated IS-075「*归属于少数股东的综合收益总额」第三种定义 {third!r}：既不是目标 "
                f"\"ROW('IS-049')+ROW('IS-072')\"，也不是已知坏式 \"SUM_ROW('IS-001','IS-074')\"")
    assert ([p for p in after if p not in before], len(after)) == ([expected], len(before) + 1), after
