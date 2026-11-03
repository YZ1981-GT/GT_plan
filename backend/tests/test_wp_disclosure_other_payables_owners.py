"""五、42 / 八、42 三 owner 同步顺序与共享主表派生。"""
from __future__ import annotations

import itertools
import json
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.report_models import DisclosureNote
from app.services.wp_disclosure_derived_tables import rebuild_other_payables_summary
from app.services.wp_disclosure_owner_ledger import TABLE_OWNER_LEDGER_KEY
from app.services.wp_disclosure_sync_service import sync_from_workpaper

PROJECT_ID = UUID("00000000-0000-0000-0000-000000004242")
USER_ID = UUID("00000000-0000-0000-0000-000000004243")


def _user() -> MagicMock:
    user = MagicMock()
    user.id = USER_ID
    return user


def _scalar(value):
    result = MagicMock()
    result.scalar_one_or_none = MagicMock(return_value=value)
    return result


def _project_row(variant: str) -> MagicMock:
    row = MagicMock()
    row.first = MagicMock(return_value=(
        2025,
        {"entity_type": variant, "scope": "standalone"},
        None,
        None,
    ))
    return row


def _no_push_states() -> MagicMock:
    result = MagicMock()
    result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
    return result


def _db(note: DisclosureNote, variant: str) -> MagicMock:
    db = MagicMock(spec=AsyncSession)
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    db.execute = AsyncMock(side_effect=[
        _project_row(variant),
        _scalar(note),
        _no_push_states(),
    ])
    return db


def _note(section: str) -> DisclosureNote:
    note = DisclosureNote(
        project_id=PROJECT_ID,
        year=2025,
        note_section=section,
        section_title="其他应付款",
        table_data={
            "sub_table_data": {"第四方保留表": [{"label": "sentinel", "end_amount": 9}]},
            "_sub_table_columns": {"第四方保留表": [{"key": "label", "is_label": True}]},
        },
        is_deleted=False,
    )
    note.id = uuid4()
    return note


def _columns(prior_label: str) -> list[dict]:
    return [
        {"key": "label", "label": "项目", "is_label": True, "flat": True},
        {"key": "end_amount", "label": "期末余额", "format": "amount"},
        {"key": "prior_amount", "label": prior_label, "format": "amount"},
    ]


def _payloads(variant: str) -> tuple[dict[str, tuple[str, list[dict]]], str]:
    if variant == "listed":
        names = ("应付利息", "应付股利", "其他应付款（按款项性质列示）")
        prior_label = "上年年末余额"
    else:
        names = ("应付利息", "应付股利", "按款项性质列示")
        prior_label = "期初余额"
    values = ((11, 1), (22, 2), (33, 3))
    payloads = {
        owner: (name, [
            {"label": owner, "end_amount": end, "prior_amount": prior},
            {"label": "合计", "end_amount": end, "prior_amount": prior, "is_total": True},
        ])
        for owner, name, (end, prior) in zip(("L2", "M1", "K3"), names, values)
    }
    return payloads, prior_label


async def _run_order(variant: str, order: tuple[str, ...]) -> dict:
    section = "五、42" if variant == "listed" else "八、42"
    standard = f"{variant}_standalone"
    note = _note(section)
    payloads, prior_label = _payloads(variant)
    for owner in order:
        table_name, rows = payloads[owner]
        await sync_from_workpaper(
            _db(note, variant),
            PROJECT_ID,
            wp_id=uuid4(),
            sheet_name=f"{owner}-附注披露",
            section_id=section,
            sub_table_data={table_name: rows},
            current_standard=standard,
            user=_user(),
            sub_table_columns={table_name: _columns(prior_label)},
            commit=False,
        )
    return {
        "sub_table_data": note.table_data["sub_table_data"],
        "columns": note.table_data["_sub_table_columns"],
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("variant", "third_label"),
    [("listed", "其他应付款"), ("soe", "其他应付款项")],
)
async def test_all_six_owner_orders_converge(variant: str, third_label: str):
    outputs = [
        await _run_order(variant, order)
        for order in itertools.permutations(("L2", "M1", "K3"))
    ]
    canonical = {json.dumps(item, ensure_ascii=False, sort_keys=True) for item in outputs}
    assert len(canonical) == 1
    result = outputs[0]
    rows = result["sub_table_data"]["其他应付款"]
    assert [row["label"] for row in rows] == ["应付利息", "应付股利", third_label, "合计"]
    assert [(row["end_amount"], row["prior_amount"]) for row in rows] == [
        (11, 1), (22, 2), (33, 3), (66, 6),

    ]
    assert result["sub_table_data"]["第四方保留表"][0]["end_amount"] == 9
    assert "第四方保留表" in result["columns"]


def test_decimal_totals_and_unrelated_section_noop():
    data = {
        "sub_table_data": {
            "应付利息": [{"label": "合计", "end_amount": 0.1, "prior_amount": 0.01, "is_total": True}],
            "应付股利": [{"label": "合计", "end_amount": 0.2, "prior_amount": 0.02, "is_total": True}],
            "其他应付款（按款项性质列示）": [
                {"label": "押金", "end_amount": 0.3, "prior_amount": 0.03},
            ],
        }
    }
    touched = rebuild_other_payables_summary(
        data,
        current_standard="listed_standalone",
        section_id="五、42",
    )
    assert touched == {"其他应付款"}
    total = data["sub_table_data"]["其他应付款"][-1]
    assert total == {"label": "合计", "end_amount": 0.6, "prior_amount": 0.06, "is_total": True}

    unrelated = {"sub_table_data": {"原表": [{"label": "x"}]}}
    before = json.dumps(unrelated, ensure_ascii=False, sort_keys=True)
    assert rebuild_other_payables_summary(
        unrelated,
        current_standard="listed_standalone",
        section_id="五、41",
    ) == set()
    assert json.dumps(unrelated, ensure_ascii=False, sort_keys=True) == before


@pytest.mark.asyncio
async def test_derived_summary_is_in_formula_push_touched(monkeypatch):
    from app.services import note_push_ownership

    captured: set[str] = set()

    async def fake_reapply(*_args, **kwargs):
        captured.update(kwargs["touched"])
        return []

    monkeypatch.setattr(note_push_ownership, "reapply_pushed_cells", fake_reapply)
    note = _note("五、42")
    await sync_from_workpaper(
        _db(note, "listed"),
        PROJECT_ID,
        wp_id=uuid4(),
        sheet_name="L2-附注披露",
        section_id="五、42",
        sub_table_data={"应付利息": [
            {"label": "合计", "end_amount": 11, "prior_amount": 1, "is_total": True},
        ]},
        current_standard="listed_standalone",
        user=_user(),
        sub_table_columns={"应付利息": _columns("上年年末余额")},
        commit=False,
    )
    assert captured == {"应付利息", "其他应付款"}


@pytest.mark.asyncio
async def test_empty_owner_replacement_reapplies_formula_cells_for_derived_summary(monkeypatch):
    """owner 放弃旧来源表时，即使输入为空，重建主表也必须进入公式格保护。"""
    from app.services import note_push_ownership

    captured: set[str] = set()

    async def fake_reapply(*_args, **kwargs):
        captured.update(kwargs["touched"])
        return []

    monkeypatch.setattr(note_push_ownership, "reapply_pushed_cells", fake_reapply)
    note = _note("五、42")
    note.table_data["sub_table_data"].update({
        "应付利息": [{"label": "合计", "end_amount": 11, "prior_amount": 1, "is_total": True}],
        "应付股利": [{"label": "合计", "end_amount": 22, "prior_amount": 2, "is_total": True}],
    })
    note.table_data["_sub_table_columns"].update({
        "应付利息": _columns("上年年末余额"),
        "应付股利": _columns("上年年末余额"),
    })
    note.table_data[TABLE_OWNER_LEDGER_KEY] = {
        "version": 1,
        "owners": {"L2": {"tables": ["应付利息"]}},
    }

    await sync_from_workpaper(
        _db(note, "listed"),
        PROJECT_ID,
        wp_id=uuid4(),
        sheet_name="L2-附注披露",
        section_id="五、42",
        sub_table_data={},
        current_standard="listed_standalone",
        user=_user(),
        sub_table_columns={},
        owner_key="L2",
        replace_owned_tables=True,
        commit=False,
    )

    assert "应付利息" not in note.table_data["sub_table_data"]
    assert captured == {"其他应付款"}
    rows = note.table_data["sub_table_data"]["其他应付款"]
    assert rows[1] == {"label": "应付股利", "end_amount": 22, "prior_amount": 2}
    assert rows[-1] == {"label": "合计", "end_amount": 22, "prior_amount": 2, "is_total": True}
