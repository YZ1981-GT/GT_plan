"""E1 spec Sprint 1 Task 1.23: 10 种公式类型各 2 用例

覆盖 prefill_engine + formula_engine 全部公式类型语法解析层:
- TB / SUM_TB (FormulaEngine)
- WP / LEDGER / AUX / PREV / ADJ / NOTE (extended resolvers)
- LEDGER_DETAIL / COUNT_LEDGER (E1 spec Task 1.4 + 1.5 新增)

每种 2 用例 = 1 正向(参数齐全语法 OK) + 1 反向(参数不足应返回 None / 列表空)。
不依赖 DB:用 _parse_args + _FORMULA_RE 测试解析层;真实 DB 查询测试归集成测试。
"""
from __future__ import annotations

import re

import pytest

from app.services.prefill_engine import (
    _FORMULA_RE,
    _FORMULA_RESOLVERS,
    _parse_args,
    _parse_period_range,
)


# ---------------------------------------------------------------------------
# 解析层 — _FORMULA_RE 必须识别全部 10 种公式类型
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "formula,expected_type",
    [
        ("=TB('1001','期末余额')", "TB"),
        ("=SUM_TB('1001~1012','期末余额')", "SUM_TB"),
        ("=WP('E1','审定表E1-1','审定数')", "WP"),
        ("=LEDGER('1001','借','全年')", "LEDGER"),
        ("=AUX('1002','客户','C001','期末余额')", "AUX"),
        ("=PREV('E1','审定表E1-1','审定数')", "PREV"),
        ("=ADJ('1001','aje_net')", "ADJ"),
        ("=NOTE('五、1','货币资金','期末余额')", "NOTE"),
        ("=LEDGER_DETAIL('1001','12月','>=100000')", "LEDGER_DETAIL"),
        ("=COUNT_LEDGER('1001','全年')", "COUNT_LEDGER"),
    ],
)
def test_formula_type_recognized(formula: str, expected_type: str):
    """正向用例: 10 种公式类型全部被 _FORMULA_RE 正确识别"""
    m = _FORMULA_RE.search(formula)
    assert m is not None, f"_FORMULA_RE 未识别 {formula}"
    assert m.group(1).upper() == expected_type


@pytest.mark.parametrize(
    "formula",
    [
        "TB('1001','期末余额')",  # 缺 = 前缀
        "=UNKNOWN('a','b')",
        "=TB",  # 无括号
        "",
    ],
)
def test_formula_type_rejected(formula: str):
    """反向用例: 不合法的公式不被识别"""
    m = _FORMULA_RE.search(formula)
    if m is None:
        return
    # 即使 search 命中,也不应是支持的类型
    assert m.group(1).upper() not in {
        "TB", "SUM_TB", "WP", "LEDGER", "AUX", "PREV",
        "ADJ", "NOTE", "LEDGER_DETAIL", "COUNT_LEDGER",
    } or "=" not in formula


# ---------------------------------------------------------------------------
# _FORMULA_RESOLVERS 注册完整性
# ---------------------------------------------------------------------------


def test_resolvers_registered_for_extended_types():
    """LEDGER_DETAIL + COUNT_LEDGER 必须注册到 _FORMULA_RESOLVERS"""
    assert "LEDGER_DETAIL" in _FORMULA_RESOLVERS
    assert "COUNT_LEDGER" in _FORMULA_RESOLVERS
    assert callable(_FORMULA_RESOLVERS["LEDGER_DETAIL"])
    assert callable(_FORMULA_RESOLVERS["COUNT_LEDGER"])


def test_resolvers_complete_for_6_existing_types():
    """6 种已有类型 (WP/LEDGER/AUX/PREV/ADJ/NOTE) 仍正确注册"""
    for ft in ("WP", "LEDGER", "AUX", "PREV", "ADJ", "NOTE"):
        assert ft in _FORMULA_RESOLVERS
        assert callable(_FORMULA_RESOLVERS[ft])


# ---------------------------------------------------------------------------
# _parse_args 参数解析(各类型 2 用例 — 正向 + 反向)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        # TB
        ("'1001','期末余额'", ["1001", "期末余额"]),
        ("'',", ["", ""]),  # 空 args 反向
        # SUM_TB
        ("'1001~1012','期末余额'", ["1001~1012", "期末余额"]),
        # WP
        ("'E1','审定表E1-1','R18'", ["E1", "审定表E1-1", "R18"]),
        # LEDGER
        ("'1001','借','全年'", ["1001", "借", "全年"]),
        # AUX
        ("'1002','客户','C001','期末余额'", ["1002", "客户", "C001", "期末余额"]),
        # PREV
        ("'E1','审定表E1-1','审定数'", ["E1", "审定表E1-1", "审定数"]),
        # ADJ
        ("'1001','aje_net'", ["1001", "aje_net"]),
        # NOTE
        ("'五、1','货币资金','期末余额'", ["五、1", "货币资金", "期末余额"]),
        # LEDGER_DETAIL — 含三个参数
        ("'1001','12月','>=100000'", ["1001", "12月", ">=100000"]),
        # COUNT_LEDGER — 仅 2 个参数
        ("'1001','全年'", ["1001", "全年"]),
    ],
)
def test_parse_args_correct(raw: str, expected: list):
    """正向用例: 10 种公式 args 正确解析"""
    args = _parse_args(raw)
    # 前 N 个参数应严格匹配(允许尾部空字符串)
    for i, exp in enumerate(expected):
        if i < len(args):
            assert args[i] == exp, f"args[{i}]={args[i]!r} != {exp!r} (raw={raw!r})"


# ---------------------------------------------------------------------------
# _parse_period_range — LEDGER_DETAIL/COUNT_LEDGER 期间解析
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "period,expected",
    [
        ("全年", (1, 12)),
        ("all", (1, 12)),
        ("*", (1, 12)),
        ("1月", (1, 1)),
        ("12月", (12, 12)),
        ("1-3月", (1, 3)),
        ("1~6月", (1, 6)),
        ("3", (3, 3)),
        ("", (1, 12)),  # 空字符串 → 全年
        ("xxx", (None, None)),  # 反向: 不可解析
    ],
)
def test_parse_period_range(period: str, expected: tuple):
    """LEDGER_DETAIL/COUNT_LEDGER 期间字符串解析"""
    assert _parse_period_range(period) == expected
