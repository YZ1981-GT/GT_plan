"""Property 10（V2 落库激活穿透）— disclosure-note-linkage-completion Task 4.3.

验证：``_persist_consol_sections_v2`` 落库 provenance 后，``note_consol_drilldown_service``
对该章节返回 ``has_breakdown=true`` 且 ``by_company`` 非空；breakdown 缺失/空时
``has_breakdown=false``。

契约核心（round-trip / Task 4.0 裁决 C = provenance-only）：
    ``_persist_consol_sections_v2`` 写 ``disclosure_notes.consolidation_breakdown`` 列
    （= ``section["consolidation_breakdown"]`` = ``{by_company:[...], computed_at}``），
    ``note_consol_drilldown_service.get_note_consol_breakdown`` 读**同一列** → ``by_company``。
    二者字段/形态一致。

本测试用 **capture-then-serve round-trip**（真实 PG fixture 在本仓库 conftest 下会挂起）：
    1. ``_persist`` 的所有查询返 None（走新建分支），捕获它构造的真实 ``DisclosureNote``；
    2. 把**同一个 note 对象**喂给穿透服务的 mock db。
    若 persist 写到与穿透读取不同名的属性，捕获的 note 就不会携带 ``consolidation_breakdown``
    → 穿透返回 ``has_breakdown=False`` → 测试失败（即真正捕获字段/形态漂移）。

Validates: Requirements 3.1, 3.2, 7.3; Property 10.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.services.consol_disclosure_service import _persist_consol_sections_v2
from app.services.note_consol_drilldown_service import (
    EMPTY_BREAKDOWN_MESSAGE,
    get_note_consol_breakdown,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run(coro):
    """在独立事件循环中跑协程（hypothesis @given 需同步函数体）."""
    return asyncio.run(coro)


class _CaptureSession:
    """persist 用的 fake AsyncSession：

    - ``execute(...)`` 恒返 ``scalar_one_or_none()==None`` → 强制走"新建"分支；
    - ``add(note)`` 捕获 persist 构造的真实 ``DisclosureNote`` 对象；
    - ``commit`` / ``rollback`` no-op。
    """

    def __init__(self) -> None:
        self.added: list = []

    async def execute(self, _stmt):
        result = MagicMock()
        result.scalar_one_or_none = MagicMock(return_value=None)
        return result

    def add(self, obj) -> None:
        self.added.append(obj)

    async def commit(self) -> None:
        return None

    async def rollback(self) -> None:
        return None


def _drill_db_returning(note):
    """穿透服务用的 mock db：``execute(...).scalar_one_or_none()`` 返回 note."""
    result = MagicMock()
    result.scalar_one_or_none = MagicMock(return_value=note)
    db = AsyncMock()
    db.execute = AsyncMock(return_value=result)
    return db


async def _persist_one(section_id: str, breakdown, *, pid=None, year: int = 2025):
    """跑 _persist 落一个章节，返回 (捕获的 note, persist 汇总)."""
    pid = pid or uuid4()
    cap = _CaptureSession()
    summary = await _persist_consol_sections_v2(
        cap,
        pid,
        year,
        [{"section_id": section_id, "consolidation_breakdown": breakdown}],
        "soe",
    )
    return pid, cap, summary


async def _persist_then_drill(section_id: str, breakdown, *, pid=None, year: int = 2025):
    """完整 round-trip：persist → 捕获 note → 喂穿透服务，返回 (note, 穿透结果)."""
    pid, cap, summary = await _persist_one(section_id, breakdown, pid=pid, year=year)
    assert len(cap.added) == 1, f"期望落库 1 章节, 实际 added={len(cap.added)} summary={summary}"
    note = cap.added[0]
    drill_db = _drill_db_returning(note)
    out = await get_note_consol_breakdown(drill_db, pid, year, section_id)
    return note, out


def _breakdown(by_company):
    return {"by_company": by_company, "computed_at": "2026-07-26T00:00:00+00:00"}


def _sample_company(code="SUB001", amount="1234.56"):
    return {
        "company_code": code,
        "company_name": f"子公司{code}",
        "section_title": "货币资金",
        "amount": amount,
    }


# ---------------------------------------------------------------------------
# 正向：落库非空 breakdown → has_breakdown=True 且 by_company 非空
# ---------------------------------------------------------------------------


class TestPersistActivatesDrilldown:
    """Property 10 正向：落库 provenance 激活穿透."""

    @pytest.mark.asyncio
    async def test_persisted_section_activates_drilldown(self):
        """落库非空 by_company → 穿透返回 has_breakdown=True + by_company 非空."""
        breakdown = _breakdown([_sample_company("SUB001", "1000.50"),
                                _sample_company("SUB002", "234.06")])
        note, out = await _persist_then_drill("consol_section_cash", breakdown)

        # 穿透激活
        assert out["has_breakdown"] is True
        assert out["message"] is None
        assert out["by_company"] == breakdown["by_company"]
        assert len(out["by_company"]) == 2
        assert out["computed_at"] == "2026-07-26T00:00:00+00:00"

    @pytest.mark.asyncio
    async def test_persist_writes_exact_field_drilldown_reads(self):
        """契约锁定：persist 写的属性 == 穿透读的属性（provenance-only）.

        若 persist 改写到别的属性名，捕获的 note 就不带 consolidation_breakdown，
        round-trip 会退化为 has_breakdown=False（漂移即被捕获）。
        """
        breakdown = _breakdown([_sample_company()])
        pid, cap, _ = await _persist_one("consol_section_ar", breakdown)
        note = cap.added[0]

        # persist 写入的 provenance 三字段（Req3.2 / 裁决 C）
        assert note.consolidation_breakdown == breakdown
        assert note.source_project_id == pid
        assert note.last_sync_source == "consolidation"
        # 键：persist 以 note_section=section_id 落库；穿透 _load_note 回退按 note_section 命中
        assert note.note_section == "consol_section_ar"

        # 穿透读同一 note → 命中同一 consolidation_breakdown
        drill_db = _drill_db_returning(note)
        out = await get_note_consol_breakdown(drill_db, pid, 2025, "consol_section_ar")
        assert out["has_breakdown"] is True
        assert out["by_company"] == breakdown["by_company"]


# ---------------------------------------------------------------------------
# 负向：breakdown None / 空 by_company / 落库前 → has_breakdown=False
# ---------------------------------------------------------------------------


class TestNoBreakdownNoActivation:
    """Property 10 负向：breakdown 缺失/空 → 穿透 has_breakdown=False."""

    @pytest.mark.asyncio
    async def test_breakdown_none_no_activation(self):
        """落库 consolidation_breakdown=None → 穿透 has_breakdown=False."""
        note, out = await _persist_then_drill("consol_section_none", None)

        assert note.consolidation_breakdown is None
        assert out["has_breakdown"] is False
        assert out["by_company"] == []
        assert out["message"] == EMPTY_BREAKDOWN_MESSAGE

    @pytest.mark.asyncio
    async def test_breakdown_empty_by_company_no_activation(self):
        """落库 by_company 为空列表 → 穿透 has_breakdown=False."""
        note, out = await _persist_then_drill("consol_section_empty", _breakdown([]))

        assert out["has_breakdown"] is False
        assert out["by_company"] == []
        assert out["message"] == EMPTY_BREAKDOWN_MESSAGE

    @pytest.mark.asyncio
    async def test_before_persist_no_activation(self):
        """落库前（章节不存在）→ 穿透 has_breakdown=False."""
        drill_db = _drill_db_returning(None)
        out = await get_note_consol_breakdown(drill_db, uuid4(), 2025, "consol_section_x")

        assert out["has_breakdown"] is False
        assert out["by_company"] == []
        assert out["message"] == EMPTY_BREAKDOWN_MESSAGE


# ---------------------------------------------------------------------------
# 属性化（hypothesis）：任意非空 by_company 落库后必激活穿透
# ---------------------------------------------------------------------------


_SAFE_ID = st.text(
    alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd"), whitelist_characters="_-"),
    min_size=1,
    max_size=24,
).filter(lambda s: s.strip())

_COMPANY = st.fixed_dictionaries({
    "company_code": st.text(min_size=1, max_size=8).filter(lambda s: s.strip()),
    "company_name": st.text(min_size=1, max_size=12),
    "section_title": st.text(min_size=1, max_size=12),
    "amount": st.decimals(min_value=0, max_value=10**9, places=2).map(str),
})


class TestPersistActivatesDrilldownProperty:
    """Property 10 属性化：任意非空 by_company round-trip 后 has_breakdown=True."""

    @settings(max_examples=25, deadline=None)
    @given(section_id=_SAFE_ID, companies=st.lists(_COMPANY, min_size=1, max_size=6))
    def test_any_nonempty_breakdown_activates(self, section_id, companies):
        breakdown = _breakdown(companies)
        note, out = _run(_persist_then_drill(section_id, breakdown))

        assert note.consolidation_breakdown == breakdown
        assert note.note_section == section_id.strip()
        assert out["has_breakdown"] is True
        assert len(out["by_company"]) == len(companies)
        assert out["message"] is None

    @settings(max_examples=15, deadline=None)
    @given(section_id=_SAFE_ID)
    def test_empty_breakdown_never_activates(self, section_id):
        _note, out = _run(_persist_then_drill(section_id, _breakdown([])))
        assert out["has_breakdown"] is False
        assert out["by_company"] == []
