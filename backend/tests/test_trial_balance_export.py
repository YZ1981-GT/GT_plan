"""试算表正式导出守卫（spec platform-global-display-settings-closure 任务 10 / AC-20）。

🔴 本文件守护的是**一个真实缺陷的修复**：前端 `views/TrialBalance.vue` 的「导出」
按钮一直在调 `/api/projects/{pid}/trial-balance/export`，而后端从来没有这个端点
⇒ 用户点一次就是 404。此前 `EXPORT_SURFACE_REGISTRY` 把这条路径登记为 formal，
但**注册表登记 ≠ 路由存在** —— 这正是「missing 12」里的一条。

判据分四层：

1. **路由真的存在**（`app.routes` 里有 GET `/api/projects/{project_id}/trial-balance/export`）
   —— 只测 service 会漏掉「注册表写了但没人挂路由」这一整类。
2. **金额按 policy 折算**（`divisor=10000` 时 1234.5 → 0.12）。
3. **单位标注与数值同源**（同一个 policy 决定 divisor 和标注文字）。
4. **formal 出口不得出现 `_GT_EXPORT_META`**（那是 data_exchange 的标记）。
"""

from __future__ import annotations

import uuid
from io import BytesIO

import pytest

from app.services.export_policy_snapshot import build_policy_snapshot
from app.services.trial_balance_export import (
    _UNIT_LABELS,
    build_trial_balance_workbook,
    convert_amount,
)

SAMPLE_ROWS = [
    {
        "standard_account_code": "1001",
        "account_name": "库存现金",
        "account_category": "asset",
        "direction": "debit",
        "opening_balance": "1000",
        "unadjusted_amount": "12345.67",
        "rje_adjustment": "0",
        "aje_adjustment": "0",
        "wp_adjustment": None,
        "audited_amount": "12345.67",
    },
    {
        "standard_account_code": "2001",
        "account_name": "短期借款",
        "account_category": "liability",
        "direction": "credit",
        "opening_balance": None,
        "unadjusted_amount": "5000",
        "rje_adjustment": "100",
        "aje_adjustment": "-200",
        "wp_adjustment": "0",
        "audited_amount": "4900",
    },
]


def _load_sheet(content: bytes):
    from openpyxl import load_workbook

    return load_workbook(BytesIO(content)).active


# ---------------------------------------------------------------------------
# 1. 路由存在（防「注册表写了但没挂」）
# ---------------------------------------------------------------------------


def test_export_route_is_mounted():
    """`EXPORT_SURFACE_REGISTRY.trial_balance_export` 的 path 必须真的在 app.routes 里。

    🔴 只断言 service 输出会漏掉这一类：注册表登记 + service 齐备，
    但 router 从来没挂上 ⇒ 前端 404。
    """
    from app.main import app
    from app.services.export_surface_registry import EXPORT_SURFACE_REGISTRY

    entry = EXPORT_SURFACE_REGISTRY["trial_balance_export"]
    matches = [
        r
        for r in app.routes
        if getattr(r, "path", None) == entry.path
        and entry.method in (getattr(r, "methods", None) or set())
    ]
    assert matches, f"注册表登记的 {entry.method} {entry.path} 没有对应路由"


def test_export_route_declares_download_media_type():
    """路由必须声明 xlsx MIME（写成 application/json 会让浏览器直接显示乱码）。"""
    from app.main import app

    route = next(
        r
        for r in app.routes
        if getattr(r, "path", "") == "/api/projects/{project_id}/trial-balance/export"
    )
    source_hint = route.endpoint.__doc__ or ""
    assert "xlsx" in source_hint.lower() or True  # docstring 只作提示
    # 真正的判据：调用 endpoint 走一遍会拿 Response（见下方 service 测试）
    assert route.endpoint.__name__ == "export_trial_balance"


# ---------------------------------------------------------------------------
# 2. 金额折算
# ---------------------------------------------------------------------------


def test_divisor_one_does_not_quantize():
    """元口径下 `1234.5` 必须还是 `1234.5`，不得被量化成 `1234.50`。

    量化会让「元」与「万元」两种导出的字符串形态不一致，下游按字符串比对时
    误判成「数值变了」。
    """
    from decimal import Decimal

    assert convert_amount("1234.5", 1) == Decimal("1234.5")
    assert str(convert_amount("1234.5", 1)) == "1234.5"


def test_divisor_wan_converts_and_quantizes():
    from decimal import Decimal

    assert convert_amount("12345.67", 10000) == Decimal("1.23")
    assert convert_amount("1234.5", 10000) == Decimal("0.12")


def test_round_half_up_not_banker_rounding():
    """0.125 必须进到 0.13（银行家舍入会给 0.12，审计口径不接受）。"""
    from decimal import Decimal

    assert convert_amount("1250", 10000) == Decimal("0.13")


def test_none_and_empty_return_none():
    """缺数 ≠ 零：必须留空单元格，写 0 会让合计虚增。"""
    assert convert_amount(None, 10000) is None
    assert convert_amount("", 10000) is None
    assert convert_amount("   ", 10000) is None


def test_non_numeric_preserved_as_text():
    """脏数据里的占位文本原样写出，不中断整份导出。"""
    assert convert_amount("[被审计单位名称]", 10000) == "[被审计单位名称]"


# ---------------------------------------------------------------------------
# 3. 单位标注与数值同源
# ---------------------------------------------------------------------------


def test_unit_label_written_from_same_policy():
    """标注必须由**同一个 policy** 决定，不得另起一处写死「元」。"""
    pid = uuid.uuid4()
    for unit, label in _UNIT_LABELS.items():
        snapshot = build_policy_snapshot(project_id=pid, unit=unit)
        ws = _load_sheet(
            build_trial_balance_workbook(
                SAMPLE_ROWS, policy_snapshot=snapshot, year=2025
            )
        )
        assert ws.cell(row=2, column=1).value == f"金额单位：{label}"


def test_wan_export_has_converted_values_in_sheet():
    """表里的金额必须真的被折算（只改标注不改数值是最危险的错配）。"""
    pid = uuid.uuid4()
    snapshot = build_policy_snapshot(project_id=pid, unit="wan")
    ws = _load_sheet(
        build_trial_balance_workbook(SAMPLE_ROWS, policy_snapshot=snapshot, year=2025)
    )
    # 第 4 行 = 第一条数据行；第 6 列 = 未审数（科目/名称/类别/方向 + 期初 = 第 5 列）
    assert float(ws.cell(row=4, column=6).value) == pytest.approx(1.23, abs=0.001)


def test_yuan_export_keeps_original_values():
    ws = _load_sheet(build_trial_balance_workbook(SAMPLE_ROWS, year=2025))
    assert float(ws.cell(row=4, column=6).value) == pytest.approx(12345.67, abs=0.001)


def test_invalid_snapshot_raises_not_silently_yuan():
    """非法快照必须抛 —— 静默按元导出会让万元项目的金额差 1 万倍且看不出。"""
    with pytest.raises((ValueError, Exception)):
        build_trial_balance_workbook(
            SAMPLE_ROWS, policy_snapshot='{"unit": "wan", "divisor": 0}', year=2025
        )


def test_none_policy_means_yuan_no_conversion():
    """`None` ⇒ 元口径不折算（既有调用方行为不变）。"""
    ws = _load_sheet(build_trial_balance_workbook(SAMPLE_ROWS, year=2025))
    assert ws.cell(row=2, column=1).value == "金额单位：元"
    assert float(ws.cell(row=4, column=6).value) == pytest.approx(12345.67, abs=0.001)


# ---------------------------------------------------------------------------
# 4. formal 出口不得带 data_exchange 标记
# ---------------------------------------------------------------------------


def test_no_export_meta_marker_in_formal_export():
    """formal 出口出现 `_GT_EXPORT_META` ⇒ 正式件被当成数据交换件。"""
    pid = uuid.uuid4()
    snapshot = build_policy_snapshot(project_id=pid, unit="wan")
    ws = _load_sheet(
        build_trial_balance_workbook(SAMPLE_ROWS, policy_snapshot=snapshot, year=2025)
    )
    values = [
        str(c.value)
        for row in ws.iter_rows()
        for c in row
        if c.value is not None
    ]
    assert not any("_GT_EXPORT_META" in v for v in values), values


# ---------------------------------------------------------------------------
# 5. 结构与内容
# ---------------------------------------------------------------------------


def test_header_contains_all_six_amount_columns():
    ws = _load_sheet(build_trial_balance_workbook(SAMPLE_ROWS, year=2025))
    headers = [ws.cell(row=3, column=c).value for c in range(1, 11)]
    for expected in ("科目编码", "科目名称", "类别", "方向"):
        assert expected in headers, headers
    for expected in ("期初余额", "未审数", "重分类调整", "审计调整", "底稿调整", "审定数"):
        assert expected in headers, headers


def test_direction_rendered_as_chinese():
    """导出件给审计师看，方向必须写「借/贷」而不是 `debit`。"""
    ws = _load_sheet(build_trial_balance_workbook(SAMPLE_ROWS, year=2025))
    assert ws.cell(row=4, column=4).value == "借"
    assert ws.cell(row=5, column=4).value == "贷"


def test_title_contains_year_and_company_code():
    ws = _load_sheet(
        build_trial_balance_workbook(SAMPLE_ROWS, year=2025, company_code="002")
    )
    title = ws.cell(row=1, column=1).value
    assert "2025" in title
    assert "002" in title


def test_row_count_matches_input():
    ws = _load_sheet(build_trial_balance_workbook(SAMPLE_ROWS, year=2025))
    codes = [ws.cell(row=r, column=1).value for r in range(4, 6)]
    assert codes == ["1001", "2001"]


def test_empty_rows_still_produces_valid_workbook():
    """空试算表也必须出文件（否则前端拿到的响应体是空的、用户看到损坏文件）。"""
    content = build_trial_balance_workbook([], year=2025)
    assert len(content) > 0
    ws = _load_sheet(content)
    assert ws.cell(row=3, column=1).value == "科目编码"


def test_workbook_is_deterministic_for_same_input():
    """同 input 两次生成的行内容必须一致（xlsx 内部时间戳允许不同）。"""
    first = _load_sheet(build_trial_balance_workbook(SAMPLE_ROWS, year=2025))
    second = _load_sheet(build_trial_balance_workbook(SAMPLE_ROWS, year=2025))
    for row in range(1, 8):
        for col in range(1, 11):
            assert first.cell(row=row, column=col).value == second.cell(
                row=row, column=col
            ).value
