"""汇总行「是否收到回函」三态（spec attachment-confirmation-evidence-loop 需求 1.6）。

H0 / K0 / L0 的「从 X0-1 带入替代程序」原先只认 ``is_replied is False``：明细面板写的「否」永远带不进来。
"""
from __future__ import annotations

import pytest

from app.services.confirmation_reply_flag import is_unreplied_summary_row, normalize_reply_flag


@pytest.mark.parametrize(("value", "expected"), [
    (True, True), ("是", True), (" 是 ", True), ("Y", True), ("√", True),
    (False, False), ("否", False), ("N", False), ("×", False), ("未回函", False),
    (None, None), ("", None), ("   ", None), ("待定", None),
])
def test_normalize(value, expected):
    assert normalize_reply_flag(value) is expected


@pytest.mark.parametrize(("row", "expected"), [
    ({"is_replied": "否"}, True),
    ({"is_replied": False, "match_status": "不符"}, True),
    ({"match_status": "未回函"}, True),
    ({"is_replied": "否", "match_status": "相符"}, False),  # 消极式未回函视同相符，不带
    ({"is_replied": "是"}, False),
    ({}, False),  # 未填不算未回函（空行不得带进替代程序）
])
def test_unreplied_filter(row, expected):
    assert is_unreplied_summary_row(row) is expected


def test_three_cycles_use_the_shared_filter():
    from pathlib import Path

    root = Path(__file__).resolve().parents[2] / "app" / "routers" / "wp_render_strategies"
    for name in ("_h0_confirmation_import_export.py", "_k0_confirmation_import_export.py", "_l0_confirmation_import_export.py"):
        src = (root / name).read_text(encoding="utf-8")
        assert "is_unreplied_summary_row(r)" in src, name
        assert "is_replied is False" not in src, name
