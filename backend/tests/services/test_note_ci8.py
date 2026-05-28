"""单测 — CI-8：auto_trim_v2 三级互斥（Sprint A.3.4 验收）.

Spec:    .kiro/specs/note-dynamic-tables-and-template-inheritance/ Sprint A.3.4
Design:  D5 三级 trim — CI-8: 同一章节最多触发一个级别
Reqs:    CI-8 = section > paragraph > table 优先级铁律

CI-8 互斥契约（铁律）：
- 章节级 ``status='not_applicable'`` 触发后，DisclosureNote 不应被 ``is_deleted``
  或 ``_render_as`` 标记
- 段落级 ``is_deleted=true`` 触发后，``table_data._render_as`` 不应被标
- 表格级 ``_render_as='no_business_paragraph'`` 仅在前两级未触发时设置
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.services import note_template_bindings_loader as loader
from app.services.note_trim_service import NoteTrimService


def _binding_for(account_codes: list[str]) -> dict[str, Any]:
    return {
        "tables": [{
            "table_index": 0,
            "rows": {
                "data_row": {
                    "row_type": "data",
                    "binding": {
                        "closing_balance": {
                            "source": "trial_balance",
                            "field": "audited_amount",
                            "account_codes": list(account_codes),
                            "mode": "auto",
                        },
                    },
                },
            },
        }],
    }


def _make_note(*, snum: str, text: str = "", table: dict | None = None):
    return SimpleNamespace(
        id=uuid4(),
        note_section=snum,
        section_title=snum,
        text_content=text,
        table_data=table if table is not None else {"rows": []},
        is_deleted=False,
        template_lineage=None,
    )


def _empty_table() -> dict:
    return {"headers": ["项目", "期末"], "rows": [
        {"row_type": "data", "label": "x", "values": [None, 0]},
        {"row_type": "data", "label": "y", "values": [None, None]},
    ]}


def _nonempty_table() -> dict:
    return {"headers": ["项目", "期末"], "rows": [
        {"row_type": "data", "label": "x", "values": [None, 100.0]},
    ]}


def _make_service(
    *,
    sections: list[dict],
    notes: list,
    tb_zero: set[str] | None = None,
):
    db = MagicMock()
    db.flush = AsyncMock()
    db.rollback = AsyncMock()

    async def _exec(query):
        res = MagicMock()
        sc = MagicMock()
        sc.all = MagicMock(return_value=notes)
        res.scalars = MagicMock(return_value=sc)
        res.all = MagicMock(return_value=[])
        return res
    db.execute = AsyncMock(side_effect=_exec)

    svc = NoteTrimService(db)

    async def _resolve(_p, _t):
        return "soe"
    svc.resolve_template_type = _resolve  # type: ignore[assignment]

    async def _get_sections(_p, _t):
        return sections
    svc.get_sections = _get_sections  # type: ignore[assignment]

    async def _save_trim(_p, _t, _items):
        return len(_items)
    svc.save_trim = _save_trim  # type: ignore[assignment]

    tb_zero = tb_zero or set()

    async def _is_all_zero(_p, _y, codes):
        return all(c in tb_zero for c in codes)
    svc._is_all_zero_for_codes = _is_all_zero  # type: ignore[assignment]

    return svc


@pytest.fixture(autouse=True)
def _reset_loader():
    loader.reload()
    yield
    loader.reload()


def _patch_loader(monkeypatch, mapping):
    def _fake(snum):
        return mapping.get(snum)
    monkeypatch.setattr(
        "app.services.note_trim_service.get_binding_for_section",
        _fake,
        raising=False,
    )


# ===========================================================================
# CI-8 边界场景：每个 note 同时触发三级条件，但只有最高优先级生效
# ===========================================================================


@pytest.mark.asyncio
async def test_ci8_section_wins_when_all_three_apply(monkeypatch):
    """边界：section 级触发时，note.is_deleted / _render_as 都不应被标."""
    sections = [{
        "id": str(uuid4()), "section_number": "S1", "section_title": "X",
        "status": "retain", "skip_reason": None, "sort_order": 0,
    }]
    _patch_loader(monkeypatch, {"S1": _binding_for(["1604"])})  # 全 0
    note = _make_note(snum="S1", text="", table=_empty_table())  # 三级条件都触发
    svc = _make_service(sections=sections, notes=[note], tb_zero={"1604"})

    result = await svc.auto_trim_v2(uuid4(), 2025)

    # 只章节级触发
    assert result["section_skipped"] == 1
    assert result["section_deleted"] == 0
    assert result["table_replaced"] == 0
    # CI-8：note 没被段落级删
    assert note.is_deleted is False
    assert note.template_lineage is None
    # CI-8：table_data 没被表格级标
    assert "_render_as" not in note.table_data


@pytest.mark.asyncio
async def test_ci8_paragraph_wins_over_table(monkeypatch):
    """边界：无 binding（绕过 section 级），段落 + 表都空 → 仅段落级."""
    sections = [{
        "id": str(uuid4()), "section_number": "S1", "section_title": "X",
        "status": "retain", "skip_reason": None, "sort_order": 0,
    }]
    _patch_loader(monkeypatch, {})  # 无 binding
    note = _make_note(snum="S1", text="", table=_empty_table())
    svc = _make_service(sections=sections, notes=[note])

    result = await svc.auto_trim_v2(uuid4(), 2025)

    assert result["section_skipped"] == 0
    assert result["section_deleted"] == 1
    assert result["table_replaced"] == 0  # CI-8：段落已标，表格不再标
    assert note.is_deleted is True
    assert "_render_as" not in note.table_data  # 关键：CI-8 互斥


@pytest.mark.asyncio
async def test_ci8_table_only_when_text_nonempty(monkeypatch):
    """边界：text 非空 → 段落级跳过 → 表格级独立触发."""
    sections = [{
        "id": str(uuid4()), "section_number": "S1", "section_title": "X",
        "status": "retain", "skip_reason": None, "sort_order": 0,
    }]
    _patch_loader(monkeypatch, {})
    note = _make_note(snum="S1", text="本年无相关业务", table=_empty_table())
    svc = _make_service(sections=sections, notes=[note])

    result = await svc.auto_trim_v2(uuid4(), 2025)

    assert result["section_skipped"] == 0
    assert result["section_deleted"] == 0
    assert result["table_replaced"] == 1
    assert note.is_deleted is False
    assert note.table_data["_render_as"] == "no_business_paragraph"


@pytest.mark.asyncio
async def test_ci8_three_sections_one_per_level(monkeypatch):
    """完整 CI-8 验收：3 章节一一映射 3 级，断言每级正好命中 1."""
    s1 = str(uuid4())
    s2 = str(uuid4())
    s3 = str(uuid4())
    sections = [
        {"id": s1, "section_number": "L1", "section_title": "X1",
         "status": "retain", "skip_reason": None, "sort_order": 0},
        {"id": s2, "section_number": "L2", "section_title": "X2",
         "status": "retain", "skip_reason": None, "sort_order": 1},
        {"id": s3, "section_number": "L3", "section_title": "X3",
         "status": "retain", "skip_reason": None, "sort_order": 2},
    ]
    _patch_loader(monkeypatch, {
        "L1": _binding_for(["1604"]),  # 走 section 级
        # L2 / L3 无 binding
    })
    n1 = _make_note(snum="L1", text="x", table=_nonempty_table())  # 不应被段落/表格触
    n2 = _make_note(snum="L2", text="", table=_empty_table())  # 段落级
    n3 = _make_note(snum="L3", text="本年说明", table=_empty_table())  # 表格级

    svc = _make_service(sections=sections, notes=[n1, n2, n3], tb_zero={"1604"})

    result = await svc.auto_trim_v2(uuid4(), 2025)

    assert result["section_skipped"] == 1
    assert result["section_deleted"] == 1
    assert result["table_replaced"] == 1
    assert result["retained"] == 1  # 3 - 1 - 1 = 1（L3 章节保留即便表标了）

    # CI-8 严格断言：每个 note 最多被一级触
    assert n1.is_deleted is False and "_render_as" not in n1.table_data
    assert n2.is_deleted is True and "_render_as" not in n2.table_data
    assert n3.is_deleted is False and n3.table_data["_render_as"] == "no_business_paragraph"


@pytest.mark.asyncio
async def test_ci8_partial_empty_section_not_deleted(monkeypatch):
    """章节内多 note，部分空 → 不走段落级删除（保护人工编辑）."""
    sections = [{
        "id": str(uuid4()), "section_number": "S1", "section_title": "X",
        "status": "retain", "skip_reason": None, "sort_order": 0,
    }]
    _patch_loader(monkeypatch, {})
    n_empty = _make_note(snum="S1", text="", table=_empty_table())
    n_nonempty = _make_note(snum="S1", text="说明", table=_nonempty_table())
    svc = _make_service(sections=sections, notes=[n_empty, n_nonempty])

    result = await svc.auto_trim_v2(uuid4(), 2025)

    # 段落级要求 all empty 才触发 → 不触
    assert result["section_deleted"] == 0
    assert n_empty.is_deleted is False
    assert n_nonempty.is_deleted is False
    # 表格级独立判定每个 note → 空 table 标，非空不标
    assert result["table_replaced"] == 1
    assert n_empty.table_data["_render_as"] == "no_business_paragraph"
    assert "_render_as" not in n_nonempty.table_data
