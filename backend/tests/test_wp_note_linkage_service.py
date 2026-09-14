"""WpNoteLinkageService 真实实现契约测试（P1 落地，替换原桩）。

原桩：check_consistency 恒 consistent=True、one_click_fetch 恒 0。本测试锁定：
- _extract_note_current_total 正确从各种 table_data 形态取"本期/期末"合计。
- check_consistency 能真实发现差异（不再恒 True），无可比数据时如实 skip。
- one_click_fetch 返回真实可带入节数（不再恒 0）。

不依赖真实 DB：patch 两个 DB 加载器（_load_tb_audited_by_name / _load_notes）。
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.services.wp_note_linkage_service import (
    WpNoteLinkageService,
    _extract_note_current_total,
    _to_decimal,
)


# ─── 纯函数：合计提取 ─────────────────────────────────────────────────────────


def test_extract_total_prefers_is_total_row():
    td = {
        "headers": ["项目", "期末余额", "期初余额"],
        "rows": [
            {"label": "其他应付款", "values": [100, 90], "is_total": False},
            {"label": "合计", "values": [100, 90], "is_total": True},
        ],
    }
    assert _extract_note_current_total(td) == Decimal("100")


def test_extract_total_single_data_row_fallback():
    td = {"rows": [{"label": "研发费用", "values": [150000, 0], "is_total": False}]}
    assert _extract_note_current_total(td) == Decimal("150000")


def test_extract_total_none_when_no_numeric():
    assert _extract_note_current_total(None) is None
    assert _extract_note_current_total({"rows": []}) is None
    assert _extract_note_current_total(
        {"rows": [{"label": "x", "values": [None, None], "is_total": True}]}
    ) is None


def test_to_decimal_robust():
    assert _to_decimal("12.5") == Decimal("12.5")
    assert _to_decimal(None) is None
    assert _to_decimal("abc") is None


# ─── check_consistency / one_click_fetch：真实比较逻辑 ────────────────────────


def _note(section: str, title: str, account_name: str, total_current):
    td = None
    if total_current is not None:
        td = {
            "headers": ["项目", "期末余额", "期初余额"],
            "rows": [{"label": "合计", "values": [total_current, 0], "is_total": True}],
        }
    return SimpleNamespace(
        note_section=section,
        section_title=title,
        account_name=account_name,
        table_data=td,
    )


class _Svc(WpNoteLinkageService):
    """注入内存版加载器，绕过 DB。"""

    def __init__(self, tb_by_name, notes):
        self._tb = tb_by_name
        self._notes = notes

    async def _load_tb_audited_by_name(self, project_id, year):  # type: ignore[override]
        return {k: Decimal(str(v)) for k, v in self._tb.items()}

    async def _load_notes(self, project_id, year):  # type: ignore[override]
        return self._notes


@pytest.mark.asyncio
async def test_check_consistency_detects_real_difference():
    pid, yr = uuid.uuid4(), 2025
    svc = _Svc(
        tb_by_name={"其他应付款": 100, "研发费用": 150000},
        notes=[
            _note("五、21", "其他应付款", "其他应付款", 100),       # 一致
            _note("五、34", "研发费用", "研发费用", 149000),        # 差 1000 → 不一致
            _note("一", "公司基本情况", "公司基本情况", None),      # 无合计 → skip
            _note("五、99", "无对应科目", "查无此名", 500),          # TB 无匹配 → skip
        ],
    )
    res = await svc.check_consistency(project_id=pid, year=yr)
    assert res["consistent"] is False
    assert res["checked_sections"] == 2
    assert res["skipped_sections"] == 2
    assert len(res["inconsistencies"]) == 1
    inc = res["inconsistencies"][0]
    assert inc["account_name"] == "研发费用"
    assert inc["note_amount"] == 149000.0
    assert inc["tb_audited_amount"] == 150000.0
    assert inc["difference"] == -1000.0


@pytest.mark.asyncio
async def test_check_consistency_all_match_is_consistent():
    pid, yr = uuid.uuid4(), 2025
    svc = _Svc(
        tb_by_name={"其他应付款": 100},
        notes=[_note("五、21", "其他应付款", "其他应付款", 100.004)],  # 差 < 容差
    )
    res = await svc.check_consistency(project_id=pid, year=yr)
    assert res["consistent"] is True
    assert res["checked_sections"] == 1
    assert res["inconsistencies"] == []


@pytest.mark.asyncio
async def test_one_click_fetch_reports_available_sections():
    pid, yr = uuid.uuid4(), 2025
    svc = _Svc(
        tb_by_name={"其他应付款": 100, "研发费用": 150000},
        notes=[
            _note("五、21", "其他应付款", "其他应付款", 100),
            _note("五、34", "研发费用", "研发费用", None),
            _note("五、99", "无对应科目", "查无此名", 500),  # 无 TB 匹配 → 不计
        ],
    )
    res = await svc.one_click_fetch(project_id=pid, year=yr)
    assert res["available_sections"] == 2
    names = {s["account_name"] for s in res["sections"]}
    assert names == {"其他应付款", "研发费用"}
