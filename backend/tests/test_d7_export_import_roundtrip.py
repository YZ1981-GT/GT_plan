"""D7 合同负债 — 导入导出动态账龄 属性测试 (P8-P10) + 往返回归

Feature: d7-contract-liabilities-enhancement

本文件覆盖后端 `_d7_import_export.py` 的动态账龄导入导出链路（复用
`_cycle_import_export_common` 的 build_aging_headers / aging_export_values /
match_import_aging / subject_aging_periods 与 resolve_segments）：

- Property 8：动态列头 2N 含全段 label + 导出取值顺序与列头一致。
- Property 9：导入按 label 匹配写段、缺列置零、未匹配报 warning。
- Property 10：D7-2 导入导出账龄往返一致。

回归：`test_d7_export_import_roundtrip` 仿 D3 往返回归，覆盖 THREE_YEAR/FIVE_YEAR
段的 D7-2 动态账龄往返 + D7-3 性质/账龄字段往返。

所有 hypothesis 属性测试显式 `@settings(max_examples=100)`（仓库 conftest fast
profile 默认 5，故必须显式覆盖）。

**Validates: Requirements 6.1, 6.3, 6.4, 6.5, 6.6, 6.7, 12.2, 12.3**
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

# Ensure the backend app is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.routers.wp_render_strategies._cycle_import_export_common import (
    aging_export_values,
    build_aging_headers,
    match_import_aging,
    safe_float,
    subject_aging_periods,
)
from app.routers.wp_render_strategies._d7_import_export import (
    _D7_2_BASE_HEADERS,
    _SHEET_HEADERS,
    _d7_2_dynamic_headers,
    _export_d7_2_row_dynamic,
    _export_row,
    _parse_row,
)
from app.services.aging_config_service import (
    AgingPreset,
    AgingSegment,
    PRESET_SEGMENTS,
)

# ═══════════════════════════════════════════════════════════════════════════════
# 常量 / 辅助
# ═══════════════════════════════════════════════════════════════════════════════

# D7 = 2-period subject → 账龄期间 [prior, audited]
_D7_PERIODS = subject_aging_periods("D7")
# 期间 key → nested 字段名（与 _cycle_import_export_common._AGING_PERIOD_FIELD 一致）
_PERIOD_FIELD = {"prior": "agingPrior", "audited": "agingAudited"}
# 期间 key → 列头后缀标签（与 AGING_PERIOD_LABELS 一致）
_PERIOD_LABEL = {"prior": "期初", "audited": "期末审定"}

_THREE_YEAR = list(PRESET_SEGMENTS[AgingPreset.THREE_YEAR])
_FIVE_YEAR = list(PRESET_SEGMENTS[AgingPreset.FIVE_YEAR])


def _custom_segments(n: int) -> list[AgingSegment]:
    """生成 n 段唯一 key/label 的自定义账龄段（label 不与预设或告警字面量冲突）。"""
    segs: list[AgingSegment] = []
    for i in range(n):
        segs.append(
            AgingSegment(
                key=f"custseg{i}",
                label=f"自定义账龄第{i}段",
                dayFrom=i * 366,
                dayTo=None if i == n - 1 else i * 366 + 365,
            )
        )
    return segs


# ═══════════════════════════════════════════════════════════════════════════════
# Strategies
# ═══════════════════════════════════════════════════════════════════════════════

_amount_st = st.floats(min_value=0, max_value=1e9, allow_nan=False, allow_infinity=False)


@st.composite
def _segments_st(draw: st.DrawFn) -> list[AgingSegment]:
    """段列表生成器：THREE_YEAR / FIVE_YEAR / CUSTOM(2-6段)。"""
    choice = draw(st.integers(min_value=0, max_value=2))
    if choice == 0:
        return list(_THREE_YEAR)
    if choice == 1:
        return list(_FIVE_YEAR)
    return _custom_segments(draw(st.integers(min_value=2, max_value=6)))


@st.composite
def _config_and_row_st(draw: st.DrawFn) -> tuple[list[AgingSegment], dict]:
    """生成 (segments, nested row)；每段值可能缺失（测试缺列/缺 key → 0）。"""
    segments = draw(_segments_st())

    def _bucket() -> dict[str, float]:
        b: dict[str, float] = {}
        for seg in segments:
            if draw(st.booleans()):
                b[seg.key] = draw(_amount_st)
        return b

    row = {"agingPrior": _bucket(), "agingAudited": _bucket()}
    return segments, row


# ═══════════════════════════════════════════════════════════════════════════════
# Property 8: 动态列头 2N 含全段 label + 导出取值顺序一致
# ═══════════════════════════════════════════════════════════════════════════════


@settings(max_examples=100)
@given(data=_config_and_row_st())
def test_p8_dynamic_headers_and_export_values(data: tuple[list[AgingSegment], dict]) -> None:
    """Feature: d7-contract-liabilities-enhancement, Property 8: 动态列头 2N 含全段 label，
    aging_export_values 取值顺序与列头一一对应，值等于 row[period][segKey]（缺失取 0）。

    **Validates: Requirements 6.1, 6.3, 6.4**
    """
    segments, row = data
    headers = build_aging_headers(segments, _D7_PERIODS)

    # 2N 列头
    assert len(headers) == 2 * len(segments)
    # 含全部段 label
    for seg in segments:
        assert sum(1 for h in headers if seg.label in h) == 2  # 期初 + 期末审定 各一

    # 导出取值顺序与列头一致
    values = aging_export_values(row, segments, _D7_PERIODS)
    assert len(values) == len(headers)

    expected: list[float] = []
    for period in _D7_PERIODS:
        bucket = row.get(_PERIOD_FIELD[period]) or {}
        for seg in segments:
            expected.append(safe_float(bucket.get(seg.key)))
    assert values == pytest.approx(expected, abs=1e-6)


# ═══════════════════════════════════════════════════════════════════════════════
# Property 9: 导入按 label 匹配写段 + 缺列置零 + 未匹配报 warning
# ═══════════════════════════════════════════════════════════════════════════════


@settings(max_examples=100)
@given(
    data=_config_and_row_st(),
    subset_frac=st.integers(min_value=0, max_value=100),
)
def test_p9_import_label_match_missing_zero_unmatched_warning(
    data: tuple[list[AgingSegment], dict], subset_frac: int
) -> None:
    """Feature: d7-contract-liabilities-enhancement, Property 9: 导入按列头 label 匹配写
    nested 段；当前配置缺失的段列头初始化为 0；表头中"看起来像账龄"但不属当前段的列进入 unmatched。

    **Validates: Requirements 6.5, 6.6**
    """
    segments, row = data
    full_headers = build_aging_headers(segments, _D7_PERIODS)

    # 构造 value_map：仅包含子集列头（其余列头缺失 → get_value 返回 None → 0）
    keep_count = (len(full_headers) * subset_frac) // 100
    kept_headers = full_headers[:keep_count]
    value_map: dict[str, float] = {}
    for period in _D7_PERIODS:
        bucket = row.get(_PERIOD_FIELD[period]) or {}
        for seg in segments:
            header = f"{seg.label}({_PERIOD_LABEL[period]})"
            if header in kept_headers:
                value_map[header] = safe_float(bucket.get(seg.key))

    # 注入一个"看起来像账龄"但不属当前段的 alien 列头
    alien = "陈年未知账龄段ZZZ(期初)"
    actual_headers = list(kept_headers) + [alien]

    aging_nested, unmatched = match_import_aging(
        lambda h: value_map.get(h),
        actual_headers,
        segments,
        _D7_PERIODS,
    )

    # nested 结构含两期全段
    assert set(aging_nested.keys()) == {"agingPrior", "agingAudited"}
    for period in _D7_PERIODS:
        bucket_out = aging_nested[_PERIOD_FIELD[period]]
        assert set(bucket_out.keys()) == {seg.key for seg in segments}
        for seg in segments:
            header = f"{seg.label}({_PERIOD_LABEL[period]})"
            # 命中列头 → 对应值；缺列 → 0
            assert bucket_out[seg.key] == pytest.approx(value_map.get(header, 0.0), abs=1e-6)

    # alien 账龄列进入 unmatched
    assert alien in unmatched


# ═══════════════════════════════════════════════════════════════════════════════
# Property 10: D7-2 导入导出账龄往返一致
# ═══════════════════════════════════════════════════════════════════════════════


@settings(max_examples=100)
@given(data=_config_and_row_st())
def test_p10_aging_export_import_round_trip(data: tuple[list[AgingSegment], dict]) -> None:
    """Feature: d7-contract-liabilities-enhancement, Property 10: 先 aging_export_values
    导出、再经 match_import_aging 导入，nested agingPrior/agingAudited 各段值与导出前一致。

    **Validates: Requirements 6.7, 12.2**
    """
    segments, row = data
    headers = build_aging_headers(segments, _D7_PERIODS)
    values = aging_export_values(row, segments, _D7_PERIODS)
    value_map = dict(zip(headers, values))

    aging_nested, unmatched = match_import_aging(
        lambda h: value_map.get(h),
        headers,
        segments,
        _D7_PERIODS,
    )

    # 同配置往返无未匹配列
    assert unmatched == []
    for period in _D7_PERIODS:
        bucket_in = row.get(_PERIOD_FIELD[period]) or {}
        bucket_out = aging_nested[_PERIOD_FIELD[period]]
        for seg in segments:
            assert bucket_out[seg.key] == pytest.approx(safe_float(bucket_in.get(seg.key)), abs=1e-6)


# ═══════════════════════════════════════════════════════════════════════════════
# 回归：D7-2 动态账龄往返（THREE_YEAR / FIVE_YEAR）经真实 _export/_parse 链路
# ═══════════════════════════════════════════════════════════════════════════════


def _make_d7_2_row(segments: list[AgingSegment]) -> dict:
    """构造一条 D7-2 明细行（nested keyed 账龄按 segments key 赋值）。"""
    prior = {seg.key: float((i + 1) * 100) for i, seg in enumerate(segments)}
    audited = {seg.key: float((i + 1) * 250) for i, seg in enumerate(segments)}
    return {
        "rowId": "r1",
        "seqNo": 1,
        "contractName": "销售合同A",
        "companyName": "甲公司",
        "companyCode": "C001",
        "relatedPartyType": "非关联方",
        "natureType": "预收货款",
        "priorUnadjusted": 1000.0,
        "priorAje": 50.0,
        "priorRje": 25.0,
        "priorAudited": 1075.0,
        "agingPrior": prior,
        "debitAmount": 200.0,
        "creditAmount": 500.0,
        "endBalance": 1375.0,
        "entityReclass": 10.0,
        "endUnadjusted": 1385.0,
        "endAje": 5.0,
        "endRje": 3.0,
        "endAudited": 1393.0,
        "agingAudited": audited,
        "isConfirmed": "是",
        "postTransfer": 60.0,
    }


@pytest.mark.parametrize(
    "segments",
    [_THREE_YEAR, _FIVE_YEAR],
    ids=["THREE_YEAR", "FIVE_YEAR"],
)
def test_d7_export_import_roundtrip(segments: list[AgingSegment]) -> None:
    """D7-2 动态账龄 export → import 往返一致（含 THREE_YEAR / FIVE_YEAR 段）。

    经真实后端函数：_d7_2_dynamic_headers / _export_d7_2_row_dynamic / _parse_row(segments)。

    **Validates: Requirements 6.1, 6.3, 6.4, 6.5, 6.6, 6.7, 12.2**
    """
    headers = _d7_2_dynamic_headers(segments)
    # 列头 = 基础列 + 2N 账龄列
    assert headers[: len(_D7_2_BASE_HEADERS)] == _D7_2_BASE_HEADERS
    assert len(headers) == len(_D7_2_BASE_HEADERS) + 2 * len(segments)

    original = _make_d7_2_row(segments)
    exported = _export_d7_2_row_dynamic(original, segments)
    assert len(exported) == len(headers)

    imported = _parse_row("D7-2", tuple(exported), headers, segments)

    # 基础字段往返（可编辑输入列）
    assert imported["contractName"] == original["contractName"]
    assert imported["companyName"] == original["companyName"]
    assert imported["companyCode"] == original["companyCode"]
    assert imported["relatedPartyType"] == original["relatedPartyType"]
    assert imported["natureType"] == original["natureType"]
    assert imported["isConfirmed"] == original["isConfirmed"]
    assert imported["priorUnadjusted"] == pytest.approx(original["priorUnadjusted"], abs=1e-6)
    assert imported["priorAje"] == pytest.approx(original["priorAje"], abs=1e-6)
    assert imported["priorRje"] == pytest.approx(original["priorRje"], abs=1e-6)
    assert imported["debitAmount"] == pytest.approx(original["debitAmount"], abs=1e-6)
    assert imported["creditAmount"] == pytest.approx(original["creditAmount"], abs=1e-6)
    assert imported["postTransfer"] == pytest.approx(original["postTransfer"], abs=1e-6)

    # 账龄 nested 往返（按段一致）
    assert set(imported["agingPrior"].keys()) == {seg.key for seg in segments}
    assert set(imported["agingAudited"].keys()) == {seg.key for seg in segments}
    for seg in segments:
        assert imported["agingPrior"][seg.key] == pytest.approx(original["agingPrior"][seg.key], abs=1e-6)
        assert imported["agingAudited"][seg.key] == pytest.approx(original["agingAudited"][seg.key], abs=1e-6)

    # 迁移后不再输出旧扁平账龄 key
    for legacy_key in ("priorAging1", "priorAging2", "endAging1", "endAging4"):
        assert legacy_key not in imported


# ═══════════════════════════════════════════════════════════════════════════════
# 回归：D7-3 调整分录 性质/账龄字段往返
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    ("nature_type", "aging_band"),
    [
        ("预收货款", "within1"),
        ("开发项目预收款", "y1to2"),
        ("预收工程款", "over3"),
        ("其他", ""),
    ],
)
def test_d7_3_nature_aging_roundtrip(nature_type: str, aging_band: str) -> None:
    """D7-3 调整分录 export → import 保留 natureType / agingBand 字段。

    **Validates: Requirements 12.3**
    """
    headers = _SHEET_HEADERS["D7-3"]
    assert "款项性质" in headers
    assert "账龄段" in headers

    original = {
        "rowId": "adj1",
        "description": "重分类一年内到期合同负债",
        "category": "重分类调整",
        "reportItem": "合同负债",
        "accountName": "2205",
        "noteItem": "合同负债附注",
        "placeholder": "",
        "debitAmount": 12345.67,
        "creditAmount": 0.0,
        "indexRef": "D7-1",
        "remark": "测试备注",
        "natureType": nature_type,
        "agingBand": aging_band,
    }

    exported = _export_row("D7-3", original, headers)
    assert len(exported) == len(headers)

    imported = _parse_row("D7-3", tuple(exported), headers)

    assert imported["description"] == original["description"]
    assert imported["category"] == original["category"]
    assert imported["reportItem"] == original["reportItem"]
    assert imported["accountName"] == original["accountName"]
    assert imported["debitAmount"] == pytest.approx(original["debitAmount"], abs=1e-6)
    assert imported["creditAmount"] == pytest.approx(original["creditAmount"], abs=1e-6)
    # 性质/账龄字段保留
    assert imported["natureType"] == (nature_type or "其他")
    assert imported["agingBand"] == aging_band


def test_d7_3_import_defaults_nature_and_aging() -> None:
    """D7-3 导入缺 natureType → 默认"其他"、缺 agingBand → 默认空段。

    **Validates: Requirements 12.4**
    """
    headers = _SHEET_HEADERS["D7-3"]
    # 构造一行：款项性质/账龄段两列留空
    nature_idx = headers.index("款项性质")
    aging_idx = headers.index("账龄段")
    row_vals: list = [""] * len(headers)
    row_vals[headers.index("调整事项说明")] = "缺省测试"
    row_vals[headers.index("类别")] = "账项调整"
    row_vals[headers.index("借方调整金额")] = 100.0
    row_vals[nature_idx] = ""
    row_vals[aging_idx] = ""

    imported = _parse_row("D7-3", tuple(row_vals), headers)
    assert imported["natureType"] == "其他"
    assert imported["agingBand"] == ""
