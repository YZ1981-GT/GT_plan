"""E1 spec Sprint 1 Task 1.23: 10 种公式类型各 2 用例（解析层，不依赖 DB）。

formula-fetch-followup-defect-closure 6.5 改写：原文件从 ``prefill_engine`` 导入 ``_FORMULA_RE`` / ``_FORMULA_RESOLVERS``，
二者已随 ``2638b32fd`` 删除 / 改为延迟构建（预填改走「统一预载层 ``formula_preloader`` + L1 ``formula_engine``」），
整文件收集即错。现按现行口径：公式识别 = ``_get_formula_re()``（由 ``_REGISTRY`` 派生），类型注册 = ``_REGISTRY``
有 handler 且预载层能扫出它的数据源引用；``_parse_args`` / ``_parse_period_range`` 用例原样保留。
取数口径（真库数据求值）见 ``test_h_ledger_formula`` / ``test_k_prefill_ledger_detail`` / ``test_adj_formula_resolution``。
"""
from __future__ import annotations

import pytest

from app.services.formula_engine import _REGISTRY
from app.services.formula_preloader import _scan_refs
from app.services.prefill_engine import _get_formula_re, _parse_args, _parse_period_range

#: 10 种底稿取数公式（TB / SUM_TB 由 L1 直接取试算表，其余 8 种由预载层取数）
_TEN_TYPES = ("TB", "SUM_TB", "WP", "LEDGER", "AUX", "PREV", "ADJ", "NOTE", "LEDGER_DETAIL", "COUNT_LEDGER")


# ---------------------------------------------------------------------------
# 解析层 — 公式正则必须识别全部 10 种公式类型
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
    """正向用例: 10 种公式类型全部被识别，且长名优先（LEDGER_DETAIL 不被截成 LEDGER）。"""
    m = _get_formula_re().search(formula)
    assert m is not None, f"公式正则未识别 {formula}"
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
    """反向用例: 不合法的公式不被识别。"""
    assert _get_formula_re().search(formula) is None, f"不合法写法被识别成公式：{formula!r}"


# ---------------------------------------------------------------------------
# 类型注册：L1 有 handler，预载层能扫出数据源引用
# ---------------------------------------------------------------------------


def test_ten_types_registered_in_l1():
    """10 种类型都在 L1 注册表里且有可调用 handler（原 ``_FORMULA_RESOLVERS`` 的职责）。"""
    missing = [t for t in _TEN_TYPES if not callable(_REGISTRY.get(t))]
    assert not missing, f"L1 注册表缺 handler：{missing}"


@pytest.mark.parametrize(
    "formula,ref_key,expected",
    [
        ("WP('E1','审定表E1-1','审定数')", "wp_refs", ("E1", "审定表E1-1", "审定数")),
        ("LEDGER('1001','借','全年')", "ledger_specs", ("1001", "借", "全年")),
        ("AUX('1002','客户','C001','期末余额')", "aux_specs", None),
        ("PREV('E1','审定表E1-1','审定数')", "prev_wp_refs", ("E1", "审定表E1-1", "审定数")),
        ("ADJ('1001','aje_net')", "adj_codes", "1001"),
        ("NOTE('五、1','货币资金','期末余额')", "note_refs", ("五、1", "货币资金", "期末余额")),
        ("LEDGER_DETAIL('1001','12月','>=100000')", "ledger_detail_specs", ("1001", "12月", ">=100000")),
        ("COUNT_LEDGER('1001','全年')", "ledger_count_specs", ("1001", "全年")),
    ],
)
def test_preloader_scans_data_source_of_each_type(formula: str, ref_key: str, expected):
    """预载层扫出每种取数函数的数据源引用（扫不出 = 该类公式在预填里恒取不到）。"""
    refs = _scan_refs([formula])
    assert refs[ref_key], f"{formula} 没被扫进 {ref_key}"
    if expected is not None:
        assert expected in refs[ref_key], f"{formula} 扫出 {refs[ref_key]}"


# ---------------------------------------------------------------------------
# _parse_args 参数解析(各类型 2 用例 — 正向 + 反向)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        # TB
        ("'1001','期末余额'", ["1001", "期末余额"]),
        ("'',", [""]),  # 空 args 反向：末尾逗号后没有内容，不产生第二个参数（原用例只比前 N 个，写成两个空串也绿）
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
    """正向用例: 10 种公式 args 正确解析。"""
    assert _parse_args(raw) == expected, f"raw={raw!r}"


# ---------------------------------------------------------------------------
# _parse_period_range — LEDGER / LEDGER_DETAIL / COUNT_LEDGER 期间解析
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
        ("xxx", (None, None)),  # 反向: 不可解析（预载层据此不取数，见 formula_preloader._period_clause）
    ],
)
def test_parse_period_range(period: str, expected: tuple):
    assert _parse_period_range(period) == expected
