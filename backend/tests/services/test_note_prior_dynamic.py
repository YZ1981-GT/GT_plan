"""单测 — PRIOR 3-arg 跨年动态匹配（Sprint A.3.2）.

Spec:    .kiro/specs/note-dynamic-tables-and-template-inheritance/ Sprint A.3.2
Design:  D4 公式 DSL — PRIOR('section','label','期末'|'期初')
Reqs:    Sprint A.3 验收 — PRIOR 跨年动态行匹配（与 2-arg 兼容）

覆盖：
- 3-arg PRIOR 命中嵌套 label dict（期末 / 期初）
- 2-arg PRIOR 与 3-arg 共存不互相干扰（同一 section_dict 既有 closing/opening 又有 label dict）
- 缺数据 / 缺 label / 缺 section 全返 None（不抛错）
- _index_prior_dynamic_rows 同 label 多次累加
- _load_cross_table_data 加载上年 dynamic_data 行后 3-arg PRIOR 可命中
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.services.note_formula_generator import (
    _index_prior_dynamic_rows,
    _load_cross_table_data,
    _resolve_single_cross_ref,
)


# ---------------------------------------------------------------------------
# 1. 3-arg PRIOR 直接解析（cross_data 手工构造）
# ---------------------------------------------------------------------------


def _make_cross_with_dynamic():
    return {
        "report": {}, "tb": {}, "notes": {}, "wp": {}, "aging": {},
        "prior": {
            "八、3": {
                # 2-arg 兼容：合计行
                "closing": 1234.56,
                "opening": 1100.00,
                # 3-arg：动态行
                "客户A": {"closing": 100.0, "opening": 80.0},
                "客户B": {"closing": 200.0, "opening": 150.0},
            },
            "应收账款前 5 名": {
                "客户A": {"closing": 100.0, "opening": 80.0},
            },
        },
    }


def test_prior_3arg_dynamic_label_closing():
    cross = _make_cross_with_dynamic()
    val = _resolve_single_cross_ref("PRIOR('八、3','客户A','期末')", cross)
    assert val == 100.0


def test_prior_3arg_dynamic_label_opening():
    cross = _make_cross_with_dynamic()
    val = _resolve_single_cross_ref("PRIOR('八、3','客户B','期初')", cross)
    assert val == 150.0


def test_prior_3arg_unknown_label_returns_none():
    """label 不存在 → None（用于触发 fallback / not_applicable）."""
    cross = _make_cross_with_dynamic()
    val = _resolve_single_cross_ref("PRIOR('八、3','客户Z','期末')", cross)
    assert val is None


def test_prior_3arg_unknown_section_returns_none():
    cross = _make_cross_with_dynamic()
    val = _resolve_single_cross_ref("PRIOR('未知章节','客户A','期末')", cross)
    assert val is None


def test_prior_3arg_unknown_period_returns_none():
    cross = _make_cross_with_dynamic()
    val = _resolve_single_cross_ref("PRIOR('八、3','客户A','xx')", cross)
    assert val is None


def test_prior_3arg_section_title_index():
    """按 section_title 索引也能命中 3-arg."""
    cross = _make_cross_with_dynamic()
    val = _resolve_single_cross_ref(
        "PRIOR('应收账款前 5 名','客户A','期末')", cross
    )
    assert val == 100.0


# ---------------------------------------------------------------------------
# 2. 2-arg / 3-arg 共存兼容
# ---------------------------------------------------------------------------


def test_2arg_still_works_with_3arg_data_present():
    """同 section_dict 既有 closing/opening 又有 label dict → 2-arg 仍取合计."""
    cross = _make_cross_with_dynamic()
    val = _resolve_single_cross_ref("PRIOR('八、3','期末')", cross)
    assert val == 1234.56


def test_2arg_label_named_closing_does_not_corrupt():
    """label 是 'closing' 这种边界场景：3-arg 优先于 2-arg；2-arg 仍走平铺值."""
    cross = {
        "report": {}, "tb": {}, "notes": {}, "wp": {}, "aging": {},
        "prior": {
            "X": {
                "closing": 999.0,  # 2-arg 平铺
                "opening": 888.0,
            },
        },
    }
    # 2-arg：取平铺
    assert _resolve_single_cross_ref("PRIOR('X','期末')", cross) == 999.0


# ---------------------------------------------------------------------------
# 3. _index_prior_dynamic_rows 单测
# ---------------------------------------------------------------------------


def test_index_dynamic_rows_basic():
    """dynamic_data 行 label → values[0]=closing, values[1]=opening."""
    prior: dict = {}
    rows = [
        {"row_type": "dynamic_anchor", "label": "锚点", "values": [None, None]},
        {"row_type": "dynamic_data", "label": "客户A", "values": [100.0, 80.0]},
        {"row_type": "dynamic_data", "label": "客户B", "values": [200.0, 150.0]},
        {"row_type": "dynamic_marker_end", "label": "", "values": [None, None]},
        # 合计行不索引
        {"row_type": "data", "label": "合计", "is_total": True, "values": [300.0, 230.0]},
    ]
    _index_prior_dynamic_rows(prior, keys=["八、3"], rows=rows)
    assert prior["八、3"]["客户A"] == {"closing": 100.0, "opening": 80.0}
    assert prior["八、3"]["客户B"] == {"closing": 200.0, "opening": 150.0}
    assert "合计" not in prior["八、3"]


def test_index_dynamic_rows_same_label_accumulates():
    """同 label 多次出现 → closing/opening 累加."""
    prior: dict = {}
    rows = [
        {"row_type": "dynamic_data", "label": "客户A", "values": [50.0, 30.0]},
        {"row_type": "dynamic_data", "label": "客户A", "values": [70.0, 40.0]},
    ]
    _index_prior_dynamic_rows(prior, keys=["S"], rows=rows)
    assert prior["S"]["客户A"] == {"closing": 120.0, "opening": 70.0}


def test_index_dynamic_rows_handles_none_values():
    prior: dict = {}
    rows = [
        {"row_type": "dynamic_data", "label": "X", "values": [None, 50.0]},
        {"row_type": "dynamic_data", "label": "Y", "values": [10.0, None]},
    ]
    _index_prior_dynamic_rows(prior, keys=["S"], rows=rows)
    assert prior["S"]["X"] == {"closing": 0.0, "opening": 50.0}
    assert prior["S"]["Y"] == {"closing": 10.0, "opening": 0.0}


def test_index_dynamic_rows_skips_empty_label():
    prior: dict = {}
    rows = [
        {"row_type": "dynamic_data", "label": "", "values": [10.0, 5.0]},
        {"row_type": "dynamic_data", "label": "  ", "values": [10.0, 5.0]},
    ]
    _index_prior_dynamic_rows(prior, keys=["S"], rows=rows)
    # section_dict 仍会被创建（占位），但内部无 label 索引
    assert prior == {"S": {}}


def test_index_dynamic_rows_preserves_existing_2arg_data():
    """已有 closing/opening 平铺值不被 dynamic 索引覆盖."""
    prior: dict = {"S": {"closing": 999.0, "opening": 888.0}}
    rows = [{"row_type": "dynamic_data", "label": "客户A", "values": [10.0, 5.0]}]
    _index_prior_dynamic_rows(prior, keys=["S"], rows=rows)
    assert prior["S"]["closing"] == 999.0
    assert prior["S"]["opening"] == 888.0
    assert prior["S"]["客户A"] == {"closing": 10.0, "opening": 5.0}


# ---------------------------------------------------------------------------
# 4. _load_cross_table_data 端到端 — 上年附注 dynamic_data 索引
# ---------------------------------------------------------------------------


def _empty_scalars():
    r = MagicMock()
    r.all = MagicMock(return_value=[])
    s = MagicMock()
    s.all = MagicMock(return_value=[])
    r.scalars = MagicMock(return_value=s)
    return r


def _scalars_with(items: list):
    r = MagicMock()
    s = MagicMock()
    s.all = MagicMock(return_value=items)
    r.scalars = MagicMock(return_value=s)
    r.all = MagicMock(return_value=[])
    return r


def _result_all(rows: list):
    r = MagicMock()
    r.all = MagicMock(return_value=rows)
    s = MagicMock()
    s.all = MagicMock(return_value=[])
    r.scalars = MagicMock(return_value=s)
    return r


@pytest.mark.asyncio
async def test_load_cross_table_data_indexes_dynamic_rows_for_3arg():
    """加载上年附注后 3-arg PRIOR('section','label','期末') 可解析."""
    project_id = uuid4()
    year = 2025

    # 上年（2024）附注：八、3 应收账款前 5 名 含动态行
    prior_note = SimpleNamespace(
        note_section="八、3",
        section_title="应收账款前 5 名",
        table_data={
            "headers": ["客户名称", "期末余额", "期初余额"],
            "rows": [
                {"row_type": "dynamic_anchor", "label": "锚点", "values": [None, None]},
                {"row_type": "dynamic_data", "label": "客户A", "values": [100.0, 80.0]},
                {"row_type": "dynamic_data", "label": "客户B", "values": [200.0, 150.0]},
                {"row_type": "dynamic_marker_end", "label": "", "values": [None, None]},
                {"label": "合计", "is_total": True, "values": [300.0, 230.0]},
            ],
        },
    )

    db = MagicMock()
    db.execute = AsyncMock(side_effect=[
        _empty_scalars(),               # report
        _empty_scalars(),               # tb
        _empty_scalars(),               # wp
        _empty_scalars(),               # notes (当年)
        _scalars_with([prior_note]),    # prior notes (2024)
        _result_all([]),                 # aging ledger
    ])
    db.rollback = AsyncMock()

    cross = await _load_cross_table_data(db, project_id, year)

    # 2-arg 仍可命中（合计行）
    assert _resolve_single_cross_ref("PRIOR('八、3','期末')", cross) == 300.0
    # 3-arg 命中 dynamic 行
    assert _resolve_single_cross_ref("PRIOR('八、3','客户A','期末')", cross) == 100.0
    assert _resolve_single_cross_ref("PRIOR('八、3','客户B','期初')", cross) == 150.0
    # section_title 索引也通
    assert _resolve_single_cross_ref(
        "PRIOR('应收账款前 5 名','客户A','期末')", cross
    ) == 100.0
