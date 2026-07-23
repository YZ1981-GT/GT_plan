"""K1 render: bs_date / adjudication_prefill 契约."""

from __future__ import annotations

from app.routers.wp_render_strategies._k1_other_receivables import (
    _classify_nature,
    _has_persisted_adjudication,
    _row_depth,
)


def test_classify_nature_keywords():
    assert _classify_nature("履约保证金") == "margin"
    assert _classify_nature("房屋押金") == "deposit"
    assert _classify_nature("员工备用金") == "petty"
    assert _classify_nature("关联方往来款") == "intercompany"
    assert _classify_nature("其他应收") == "other-nature"


def test_row_depth():
    assert _row_depth("1221", "1221") == 0
    assert _row_depth("1221.01", "1221") == 1
    assert _row_depth("1221.01.02", "1221") == 2


def test_has_persisted_adjudication_detects_nonzero_unadj():
    assert not _has_persisted_adjudication({})
    assert not _has_persisted_adjudication({"K1-1-receivable-r0-unadj": {"remark": "0"}})
    assert _has_persisted_adjudication({"K1-1-receivable-r0-unadj": {"remark": "100.5"}})
    assert not _has_persisted_adjudication({"K1-1-audit-note": {"remark": "说明"}})
