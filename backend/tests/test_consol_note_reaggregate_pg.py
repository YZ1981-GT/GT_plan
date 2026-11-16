"""C2/C3：同一套合并附注子树断言在真实 PostgreSQL 上逐值对拍。

执行前必须设置：
- ``DATABASE_URL=postgresql+asyncpg://.../gt_consol_reaggregate``（一次性库）
- ``GT_CONSOL_REAGGREGATE_PG=1``
- ``GT_REQUIRE_PG=1``

fixture 在提交型临时 schema 里运行，结束后 DROP SCHEMA，不写 public。
"""
from __future__ import annotations

import os
from decimal import Decimal

import pytest

from tests.services.test_consol_note_subtree_reaggregate import (
    _SECTION,
    _YEAR,
    _nodes,
    _rec,
    _rows,
    _setup,
    db,
    factory,
    group,
    user,
)
from app.services.consol_note_subtree_reaggregate import reaggregate_subtree

pytestmark = [
    pytest.mark.pg_only,
    pytest.mark.asyncio,
    pytest.mark.skipif(
        os.environ.get("GT_CONSOL_REAGGREGATE_PG", "").strip() not in ("1", "true", "yes"),
        reason="需要 GT_CONSOL_REAGGREGATE_PG=1 显式启用一次性 PG 合并附注对拍",
    ),
]


async def test_pg_full_subtree_reaggregate_matches_sqlite_value_contract(db, user, group):
    """PG 真实写入后，叶子 / 差额 / 中间汇总 / 根汇总逐值等于既有业务契约。"""
    await _setup(db, user, group)
    result = await reaggregate_subtree(
        db, group["G"].id, _YEAR, node_key="G:consol", section_ids=[_SECTION]
    )
    assert result["status"] == "persisted", result["failures"]
    assert result["sections_updated"] == 1

    # 叶子：来源必须来自单体附注，不是试算表
    a1 = await _rec(db, group, "A1:subsidiary")
    assert _rows(a1)["库存现金"] == (Decimal("100.00"), Decimal("50.00"))
    assert _rows(a1)["合计"] == (Decimal("2600.00"), Decimal("1050.00"))

    # 差额：抵销分录 + 公式值，且来源是 formula
    elim = await _rec(db, group, "A:consol_elim")
    assert elim.data["_last_write_source"] == "formula"
    assert _rows(elim)["银行存款"][0] == Decimal("-100")

    # 中间汇总：A 本部 + A1 + A 差额
    middle = _rows(await _rec(db, group, "A:consol"))
    assert middle["库存现金"] == (Decimal("476.73"), Decimal("336.73"))
    assert middle["银行存款"] == (Decimal("1001900.00"), Decimal("801000.00"))
    assert middle["合计"] == (Decimal("1002876.73"), Decimal("801336.73"))

    # 根汇总：A 合并 + B，差额节点不计入子企业计数；公式快照保留试算表口径
    root = await _rec(db, group, "G:consol")
    rows = _rows(root)
    assert rows["库存现金"] == (Decimal("1476.73"), Decimal("1336.73"))
    assert rows["银行存款"] == (Decimal("1001900.00"), Decimal("801000.00"))
    assert rows["合计"] == (Decimal("1003876.73"), Decimal("802336.73"))
    assert root.data["_last_write_source"] == "subtree_aggregate"
    assert root.data["_subtree_child_count"] == 2
    assert root.is_stale is False
    assert root.data["_subtree_provenance"]["children"]


async def test_pg_manual_cells_are_preserved_and_included(db, user, group):
    """PG 逐值对拍：手工格保留，自动合计仍纳入手工值。"""
    from tests.services.test_consol_note_subtree_reaggregate import (
        TestProtectionAndSkips,
    )

    await TestProtectionAndSkips.test_manual_cell_kept_and_counted_in_total(
        object(), db, user, group
    )


async def test_pg_invalid_protection_rolls_back_whole_section(db, user, group):
    """PG 逐值对拍：坏保护元数据触发章节 SAVEPOINT 回滚，不留下前序节点写入。"""
    from tests.services.test_consol_note_subtree_reaggregate import (
        TestProtectionAndSkips,
    )

    await TestProtectionAndSkips.test_invalid_protection_metadata_rolls_back_whole_section(
        object(), db, user, group
    )
