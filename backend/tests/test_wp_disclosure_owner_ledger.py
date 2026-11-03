"""G7 多章节同步的行内 owner 清册与严格事务语义。"""

from __future__ import annotations

import copy
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.report_models import DisclosureNote
from app.routers.wp_disclosure_sync import SyncBatchFromWorkpaperRequest
import app.services.wp_disclosure_owner_ledger as owner_ledger
import app.services.wp_disclosure_sync_service as service


PROJECT_ID = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
WP_ID = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
USER_ID = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
NOW = datetime(2026, 10, 29, 8, 0, tzinfo=timezone.utc)


def _entry(*tables: str, wp_id: uuid.UUID = WP_ID) -> dict:
    return {
        "wp_id": str(wp_id),
        "sheet_name": "附注披露信息（国企）",
        "tables": list(tables),
        "payload_sha256": "old",
        "synced_at": "2026-10-28T00:00:00+00:00",
    }


def _table_data(*, owners: dict | None = None) -> dict:
    data = {
        "sub_table_data": {
            "旧表": [{"label": "旧值"}],
            "共享表": [{"label": "共享值"}],
            "历史未知表": [{"label": "不可猜归属"}],
        },
        "_sub_table_columns": {
            "旧表": [{"key": "label"}],
            "共享表": [{"key": "label"}],
            "历史未知表": [{"key": "label"}],
        },
    }
    if owners is not None:
        data[owner_ledger.TABLE_OWNER_LEDGER_KEY] = {"version": 1, "owners": owners}
    return data


def _apply(data: dict, *, owner: str = "G7:soe", tables: dict | None = None,
           columns: dict | None = None, replace: bool = True, at: datetime = NOW):
    return owner_ledger.apply_table_owner_ledger(
        data,
        owner_key=owner,
        wp_id=WP_ID,
        sheet_name="附注披露信息（国企）",
        pushed_tables=tables or {},
        columns=columns or {},
        note_texts=[],
        removed_text_sections=[],
        row_scopes={},
        replace_owned_tables=replace,
        synced_at=at,
    )


def test_first_owner_registration_never_guesses_or_deletes_legacy_tables():
    data = _table_data()
    dropped = _apply(
        data,
        tables={"新表": [], "空表也是有效表": []},
        columns={"新表": [{"key": "label"}]},
    )

    assert dropped == []
    assert set(data["sub_table_data"]) == {"旧表", "共享表", "历史未知表"}
    owner = data[owner_ledger.TABLE_OWNER_LEDGER_KEY]["owners"]["G7:soe"]
    assert owner["tables"] == ["新表", "空表也是有效表"]
    assert len(owner["payload_sha256"]) == 64


def test_retry_replaces_only_previous_owner_set_and_deletes_data_and_columns():
    data = _table_data(owners={"G7:soe": _entry("旧表", "共享表")})
    dropped = _apply(
        data,
        tables={"共享表": [], "保留空骨架": []},
        columns={"共享表": [{"key": "label"}], "保留空骨架": []},
    )

    assert dropped == ["旧表"]
    assert "旧表" not in data["sub_table_data"]
    assert "旧表" not in data["_sub_table_columns"]
    assert data["sub_table_data"]["共享表"] == [{"label": "共享值"}]
    assert data[owner_ledger.TABLE_OWNER_LEDGER_KEY]["owners"]["G7:soe"]["tables"] == [
        "保留空骨架", "共享表",
    ]


def test_other_owner_protects_shared_table_when_current_owner_relinquishes_it():
    data = _table_data(owners={
        "G7:soe": _entry("旧表", "共享表"),
        "OTHER": _entry("共享表"),
    })
    dropped = _apply(data, tables={})

    assert dropped == ["旧表"]
    assert "共享表" in data["sub_table_data"]
    assert "共享表" in data["_sub_table_columns"]
    assert data[owner_ledger.TABLE_OWNER_LEDGER_KEY]["owners"]["OTHER"]["tables"] == ["共享表"]


def test_non_replacing_narrative_owner_does_not_delete_tables():
    data = _table_data(owners={"G7:soe": _entry("旧表")})
    dropped = _apply(data, tables={}, replace=False)

    assert dropped == []
    assert "旧表" in data["sub_table_data"]
    assert data[owner_ledger.TABLE_OWNER_LEDGER_KEY]["owners"]["G7:soe"]["tables"] == []


def test_payload_hash_is_stable_across_retry_timestamp_but_changes_with_payload():
    first = _table_data()
    second = _table_data()
    _apply(first, tables={"A": [{"v": 1}]}, at=NOW)
    _apply(second, tables={"A": [{"v": 1}]}, at=NOW.replace(hour=9))
    h1 = first[owner_ledger.TABLE_OWNER_LEDGER_KEY]["owners"]["G7:soe"]["payload_sha256"]
    h2 = second[owner_ledger.TABLE_OWNER_LEDGER_KEY]["owners"]["G7:soe"]["payload_sha256"]
    assert h1 == h2

    third = _table_data()
    _apply(third, tables={"A": [{"v": 2}]})
    assert third[owner_ledger.TABLE_OWNER_LEDGER_KEY]["owners"]["G7:soe"]["payload_sha256"] != h1


def _result(**overrides) -> dict:
    result = {
        "success": True,
        "section_id": "八、18",
        "synced_at": NOW.isoformat(),
        "rows_synced": 1,
        "texts_synced": 0,
        "created": False,
        "blocked_by_manual_override": False,
        "row_scope_unresolved": [],
        "row_scope_unresolved_reasons": {},
    }
    result.update(overrides)
    return result


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("semantic", "message"),
    [
        ({"blocked_by_manual_override": True}, "人工覆盖保护"),
        ({"skipped": True, "reason": "section_not_applicable_to_report_scope"}, "未同步"),
        ({"row_scope_unresolved": ["外币货币性项目"],
          "row_scope_unresolved_reasons": {"外币货币性项目": "模板缺段首码"}}, "模板缺段首码"),
    ],
)
async def test_strict_batch_rolls_back_every_semantic_noop(monkeypatch, semantic, message):
    db = MagicMock(spec=AsyncSession)
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    single = AsyncMock(return_value=_result(**semantic))
    monkeypatch.setattr(service, "sync_from_workpaper", single)

    with pytest.raises(ValueError, match=message):
        await service.sync_batch_from_workpaper(
            db,
            PROJECT_ID,
            wp_id=WP_ID,
            current_standard="soe",
            items=[{
                "sheet_name": "附注披露信息（国企）",
                "section_id": "八、18",
                "sub_table_data": {"长期股权投资": []},
                "owner_key": "G7:soe",
                "replace_owned_tables": True,
            }],
            user=MagicMock(id=USER_ID),
            year=2025,
            require_all_applied=True,
        )

    db.commit.assert_not_awaited()
    db.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_strict_batch_passes_owner_contract_and_commits_once(monkeypatch):
    db = MagicMock(spec=AsyncSession)
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    single = AsyncMock(return_value=_result())
    monkeypatch.setattr(service, "sync_from_workpaper", single)
    item = {
        "sheet_name": "附注披露信息（国企）",
        "section_id": "八、18",
        "sub_table_data": {"长期股权投资": []},
        "columns": {"长期股权投资": []},
        "owner_key": "G7:soe",
        "replace_owned_tables": True,
    }

    result = await service.sync_batch_from_workpaper(
        db, PROJECT_ID, wp_id=WP_ID, current_standard="soe", items=[item],
        user=MagicMock(id=USER_ID), year=2025, require_all_applied=True,
    )

    assert result["sections_synced"] == 1
    db.commit.assert_awaited_once()
    db.rollback.assert_not_awaited()
    assert single.await_args.kwargs["owner_key"] == "G7:soe"
    assert single.await_args.kwargs["replace_owned_tables"] is True


def test_batch_request_schema_keeps_owner_and_strict_fields():
    body = SyncBatchFromWorkpaperRequest.model_validate({
        "wp_id": str(WP_ID),
        "current_standard": "soe",
        "require_all_applied": True,
        "items": [{
            "sheet_name": "附注披露信息（国企）",
            "section_id": "八、18",
            "sub_table_data": {},
            "owner_key": "G7:soe",
            "replace_owned_tables": True,
        }],
    })
    dumped = body.model_dump()
    assert dumped["require_all_applied"] is True
    assert dumped["items"][0]["owner_key"] == "G7:soe"
    assert dumped["items"][0]["replace_owned_tables"] is True


def _project_row() -> MagicMock:
    row = MagicMock()
    row.first.return_value = (2025, {"entity_type": "soe", "scope": "standalone"}, None, None)
    return row


def _scalar(value) -> MagicMock:
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


def _no_push_states() -> MagicMock:
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    return result


@pytest.mark.asyncio
async def test_manual_override_does_not_advance_owner_ledger(monkeypatch):
    original = _table_data(owners={"G7:soe": _entry("旧表")})
    original["_manual_override"] = True
    note = DisclosureNote(
        project_id=PROJECT_ID, year=2025, note_section="八、18",
        section_title="长期股权投资", table_data=copy.deepcopy(original), is_deleted=False,
    )
    note.id = uuid.uuid4()
    db = MagicMock(spec=AsyncSession)
    db.execute = AsyncMock(side_effect=[_project_row(), _scalar(note), _no_push_states()])
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    monkeypatch.setattr(service, "_check_manual_override_before_propagate", AsyncMock(return_value="block_enqueued"))

    result = await service.sync_from_workpaper(
        db, PROJECT_ID, wp_id=WP_ID, sheet_name="附注披露信息（国企）",
        section_id="八、18", sub_table_data={"新表": []}, current_standard="soe",
        user=MagicMock(id=USER_ID), owner_key="G7:soe", replace_owned_tables=True,
        commit=False,
    )

    assert result["blocked_by_manual_override"] is True
    assert note.table_data == original
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_sync_from_workpaper_applies_owner_replacement_to_persisted_note():
    original = _table_data(owners={"G7:soe": _entry("旧表", "共享表")})
    note = DisclosureNote(
        project_id=PROJECT_ID, year=2025, note_section="八、18",
        section_title="长期股权投资", table_data=copy.deepcopy(original), is_deleted=False,
    )
    note.id = uuid.uuid4()
    db = MagicMock(spec=AsyncSession)
    db.execute = AsyncMock(side_effect=[_project_row(), _scalar(note), _no_push_states()])
    db.commit = AsyncMock()
    db.rollback = AsyncMock()

    result = await service.sync_from_workpaper(
        db, PROJECT_ID, wp_id=WP_ID, sheet_name="附注披露信息（国企）",
        section_id="八、18", sub_table_data={"共享表": [], "新表": []},
        sub_table_columns={"共享表": [], "新表": []}, current_standard="soe",
        user=MagicMock(id=USER_ID), owner_key="G7:soe", replace_owned_tables=True,
        commit=False,
    )

    assert result["blocked_by_manual_override"] is False
    assert "旧表" not in note.table_data["sub_table_data"]
    assert "旧表" not in note.table_data["_sub_table_columns"]
    assert note.table_data[owner_ledger.TABLE_OWNER_LEDGER_KEY]["owners"]["G7:soe"]["tables"] == [
        "共享表", "新表",
    ]
