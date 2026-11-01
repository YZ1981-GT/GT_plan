"""附注 AI 权威事实包测试。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.services.note_ai_fact_pack import (
    NoteFactPackUnavailable,
    _has_numeric_fact,
    build_note_fact_pack,
)


def _db_with_row(row):
    db = MagicMock()
    result = MagicMock()
    result.first.return_value = row
    db.execute = AsyncMock(return_value=result)
    return db


def _row(*, table_data=None, stale=False):
    return SimpleNamespace(
        id=uuid4(),
        note_section="五、1",
        section_title="货币资金",
        account_name="货币资金",
        table_data=table_data,
        is_stale=stale,
    )


def test_numeric_fact_keeps_real_zero_but_rejects_labels() -> None:
    assert _has_numeric_fact(0)
    assert _has_numeric_fact({"values": ["0.00"]})
    assert not _has_numeric_fact({"year": "2025年", "headers": ["项目", "期末"]})


@pytest.mark.asyncio
async def test_stale_note_fails_before_prior_read() -> None:
    db = _db_with_row(_row(table_data={"values": [[1]]}, stale=True))
    with patch(
        "app.services.note_ai_fact_pack.DisclosureEngine.get_prior_year_data",
        new=AsyncMock(),
    ) as prior:
        with pytest.raises(NoteFactPackUnavailable) as caught:
            await build_note_fact_pack(
                db, project_id=uuid4(), year=2025, note_section="五、1"
            )
    assert caught.value.code == "stale_source"
    prior.assert_not_awaited()


@pytest.mark.asyncio
async def test_missing_current_numeric_data_is_typed_failure() -> None:
    db = _db_with_row(_row(table_data={"headers": ["项目", "期末"]}))
    with pytest.raises(NoteFactPackUnavailable) as caught:
        await build_note_fact_pack(
            db, project_id=uuid4(), year=2025, note_section="五、1"
        )
    assert caught.value.code == "current_data_missing"


@pytest.mark.asyncio
async def test_missing_prior_numeric_data_is_typed_failure() -> None:
    db = _db_with_row(_row(table_data={"values": [[0]]}))
    with patch(
        "app.services.note_ai_fact_pack.DisclosureEngine.get_prior_year_data",
        new=AsyncMock(return_value={"year": 2024, "table_data": None, "amounts": {}}),
    ):
        with pytest.raises(NoteFactPackUnavailable) as caught:
            await build_note_fact_pack(
                db, project_id=uuid4(), year=2025, note_section="五、1"
            )
    assert caught.value.code == "prior_data_missing"


@pytest.mark.asyncio
async def test_zero_amounts_are_preserved_as_authoritative_facts() -> None:
    row = _row(table_data={"values": [[0, "12.50"]]})
    db = _db_with_row(row)
    prior = {"year": 2024, "table_data": {"values": [["0.00"]]}}
    with patch(
        "app.services.note_ai_fact_pack.DisclosureEngine.get_prior_year_data",
        new=AsyncMock(return_value=prior),
    ):
        pack = await build_note_fact_pack(
            db, project_id=uuid4(), year=2025, note_section="五、1"
        )

    assert pack.current_data["values"][0][0] == 0
    assert pack.prior_data == prior
    assert "0.00" in pack.prompt_text()
