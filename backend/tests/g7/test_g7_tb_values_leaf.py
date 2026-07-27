"""G7 长期股权投资 TB 取数：叶子汇总（防父子双算）+ 1512 减值准备补齐.

覆盖 `_g7_long_term_equity_main` 的三个单元：
    1. `_is_leaf`      —— 纯函数叶子判定（口径与 F1/H2/H4/D-cycle prefill 一致）
    2. `_sum_leaf_by_prefix` —— 纯同步汇总（父子共存时只算叶子）
    3. `_fetch_tb_values`    —— 薄封装（假 db + monkeypatch get_active_filter）

真实数据背景（postgres 实证）：tb_balance 里 1511 同时存在父级 `1511` 与子级
`1511.01/1511.02/1511.03/1511.04` 及三级 `1511.04.01/1511.04.02`，前缀累加会把
父子同时计入 → opening/closing 虚增 2~3 倍。
"""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.routers.wp_render_strategies import _g7_long_term_equity_main as g7
from app.routers.wp_render_strategies._g7_long_term_equity_main import (
    _fetch_tb_values,
    _is_leaf,
    _sum_leaf_by_prefix,
)


# ---------------------------------------------------------------------------
# 1) _is_leaf 纯函数
# ---------------------------------------------------------------------------


def test_is_leaf_three_level_only_deepest_is_leaf():
    """`{'1511','1511.01','1511.01.01'}` 中只有 `1511.01.01` 是叶子。"""
    codes = {"1511", "1511.01", "1511.01.01"}
    assert _is_leaf("1511.01.01", codes) is True
    assert _is_leaf("1511.01", codes) is False
    assert _is_leaf("1511", codes) is False


def test_is_leaf_empty_and_single_boundary():
    """空集合 / 单元素边界：自身不算自身的前缀 → 是叶子。"""
    assert _is_leaf("1511", set()) is True
    assert _is_leaf("1511", {"1511"}) is True


def test_is_leaf_siblings_are_all_leaves():
    """兄弟科目互不为前缀 → 各自都是叶子（父级不是）。"""
    codes = {"1511", "1511.01", "1511.02"}
    assert _is_leaf("1511.01", codes) is True
    assert _is_leaf("1511.02", codes) is True
    assert _is_leaf("1511", codes) is False


# ---------------------------------------------------------------------------
# 2) _sum_leaf_by_prefix 纯同步汇总
# ---------------------------------------------------------------------------


def test_sum_leaf_parent_child_only_leaves_counted():
    """父 1511=100、子 1511.01=60 / 1511.02=40 → closing=100 而不是 200。"""
    rows = [
        ("1511", 10.0, 100.0),
        ("1511.01", 6.0, 60.0),
        ("1511.02", 4.0, 40.0),
    ]
    opening, closing, leaf_codes = _sum_leaf_by_prefix(rows, "1511")
    assert closing == pytest.approx(100.0)
    assert opening == pytest.approx(10.0)
    assert leaf_codes == ["1511.01", "1511.02"]


def test_sum_leaf_three_level_nested():
    """三级嵌套：只算最深层（1511.04.01 + 1511.04.02），中间级 1511.04 与父级都不计。"""
    rows = [
        ("1511", 0.0, 500.0),
        ("1511.04", 0.0, 300.0),
        ("1511.04.01", 0.0, 200.0),
        ("1511.04.02", 0.0, 100.0),
    ]
    _opening, closing, leaf_codes = _sum_leaf_by_prefix(rows, "1511")
    assert closing == pytest.approx(300.0)
    assert leaf_codes == ["1511.04.01", "1511.04.02"]


def test_sum_leaf_parent_only_is_itself_leaf():
    """只有父级一行（无子科目）→ 父级即叶子，正常计入。"""
    rows = [("1511", 8.0, 88.0)]
    opening, closing, leaf_codes = _sum_leaf_by_prefix(rows, "1511")
    assert (opening, closing) == (pytest.approx(8.0), pytest.approx(88.0))
    assert leaf_codes == ["1511"]


def test_sum_leaf_prefix_groups_do_not_cross_contaminate():
    """1511 组与 1512 组互不污染。"""
    rows = [
        ("1511", 0.0, 100.0),
        ("1511.01", 0.0, 100.0),
        ("1512", 0.0, 30.0),
    ]
    _o1, c1, codes1 = _sum_leaf_by_prefix(rows, "1511")
    _o2, c2, codes2 = _sum_leaf_by_prefix(rows, "1512")
    assert (c1, codes1) == (pytest.approx(100.0), ["1511.01"])
    assert (c2, codes2) == (pytest.approx(30.0), ["1512"])


def test_sum_leaf_no_candidate_returns_zero():
    """无匹配前缀 → (0,0,[])。"""
    assert _sum_leaf_by_prefix([("1601", 1.0, 2.0)], "1511") == (0.0, 0.0, [])
    assert _sum_leaf_by_prefix([], "1511") == (0.0, 0.0, [])


def test_sum_leaf_none_amounts_treated_as_zero():
    """金额为 None 视为 0，不抛异常。"""
    rows = [("1511.01", None, None), ("1511.02", None, 5.0)]
    opening, closing, leaf_codes = _sum_leaf_by_prefix(rows, "1511")  # type: ignore[arg-type]
    assert opening == pytest.approx(0.0)
    assert closing == pytest.approx(5.0)
    assert leaf_codes == ["1511.01", "1511.02"]


# ---------------------------------------------------------------------------
# 3) _fetch_tb_values 薄封装（假 db + monkeypatch get_active_filter）
# ---------------------------------------------------------------------------


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


class _FakeDb:
    """最小 async db：execute 返回可 fetchall() 的行对象列表。"""

    def __init__(self, rows, raise_exc: Exception | None = None):
        self._rows = rows
        self._raise = raise_exc
        self.calls = 0

    async def execute(self, *_args, **_kwargs):
        self.calls += 1
        if self._raise is not None:
            raise self._raise
        return _FakeResult(self._rows)


def _row(code, opening, closing):
    return SimpleNamespace(
        account_code=code, opening_balance=opening, closing_balance=closing
    )


def _ctx(db):
    return SimpleNamespace(db=db, project_id=uuid4(), year=2025)


@pytest.fixture(autouse=True)
def _stub_active_filter(monkeypatch):
    """get_active_filter 是 async 且要求真实 dataset，测试里替换为恒真条件。"""

    async def _fake_filter(_db, _table, _project_id, _year):
        import sqlalchemy as sa

        return sa.true()

    monkeypatch.setattr(g7, "get_active_filter", _fake_filter)


@pytest.mark.asyncio
async def test_fetch_tb_values_only_sums_leaves():
    """父子共存时只算叶子：父 1511=100 / 子 60+40 → closing=100（非 200）。"""
    db = _FakeDb(
        [
            _row("1511", 10.0, 100.0),
            _row("1511.01", 6.0, 60.0),
            _row("1511.02", 4.0, 40.0),
        ]
    )
    tb = await _fetch_tb_values(_ctx(db))
    assert tb["closing"] == pytest.approx(100.0)
    assert tb["opening"] == pytest.approx(10.0)
    assert tb["source_codes"]["gross"] == ["1511.01", "1511.02"]
    assert db.calls == 1  # 一次查询取回两组


@pytest.mark.asyncio
async def test_fetch_tb_values_impairment_grouped_separately():
    """1512 减值准备独立汇总进 impairment / impairment_opening。"""
    db = _FakeDb(
        [
            _row("1511.01", 6.0, 60.0),
            _row("1512", 0.0, 0.0),
            _row("1512.01", 1.0, 12.0),
            _row("1512.02", 2.0, 8.0),
        ]
    )
    tb = await _fetch_tb_values(_ctx(db))
    assert tb["closing"] == pytest.approx(60.0)
    assert tb["impairment"] == pytest.approx(20.0)
    assert tb["impairment_opening"] == pytest.approx(3.0)
    assert tb["source_codes"] == {
        "gross": ["1511.01"],
        "impairment": ["1512.01", "1512.02"],
    }


@pytest.mark.asyncio
async def test_fetch_tb_values_keeps_legacy_keys():
    """向后兼容：原有 opening/closing 键名与含义不变。"""
    db = _FakeDb([_row("1511", 7.0, 77.0)])
    tb = await _fetch_tb_values(_ctx(db))
    assert set(tb) == {
        "opening",
        "closing",
        "impairment",
        "impairment_opening",
        "source_codes",
    }
    assert (tb["opening"], tb["closing"]) == (pytest.approx(7.0), pytest.approx(77.0))
    assert tb["impairment"] == pytest.approx(0.0)


@pytest.mark.asyncio
async def test_fetch_tb_values_no_match_returns_empty_dict():
    """无匹配科目 → 保持降级语义返回 {}（前端允许手填）。"""
    db = _FakeDb([_row("1601", 1.0, 2.0)])
    assert await _fetch_tb_values(_ctx(db)) == {}
    assert await _fetch_tb_values(_ctx(_FakeDb([]))) == {}


@pytest.mark.asyncio
async def test_fetch_tb_values_fail_open_on_exception():
    """异常 fail-open：返回 {} 不抛出（不阻断 render）。"""
    db = _FakeDb([], raise_exc=RuntimeError("db down"))
    assert await _fetch_tb_values(_ctx(db)) == {}
