"""公式推送附注来源语义回归（residual R6 / ADR-NRG-007）。

JSON ``_source`` 只描述 ``sub_table_data`` 的投影结构；最近一次公式推送动作
由 ORM ``last_sync_source`` 表达。JSON ``_last_sync_*`` 只属于真实底稿披露同步。
"""
from __future__ import annotations

import copy

import pytest
import pytest_asyncio

from app.services.note_sub_table_projector import project_sub_tables
from tests._formula_push_env import base_entries, make_env

_MISSING = object()
_FINGERPRINT = {
    "_last_sync_wp_id": "真实底稿同步",
    "_last_sync_sheet": "E1-披露表",
    "_last_sync_at": "2026-10-29T08:00:00+00:00",
}
_COLUMNS = [
    {"key": "label", "label": "项目", "is_label": True, "flat": True},
    {"key": "end_amount", "label": "期末余额"},
    {"key": "prior_amount", "label": "期初余额"},
]


@pytest_asyncio.fixture
async def env(monkeypatch):
    async with make_env(monkeypatch) as test_env:
        await test_env.seed_entries(base_entries())
        yield test_env


def _legacy_note(source_marker=_MISSING) -> dict:
    table = {
        "name": "货币资金",
        "headers": ["项目", "期末余额", "期初余额"],
        "rows": [
            {"label": "库存现金", "values": [None, None]},
            {"label": "银行存款", "values": [None, None]},
            {"label": "合计", "values": [None, None], "is_total": True},
        ],
    }
    data = {
        "_tables": [copy.deepcopy(table)],
        "name": table["name"],
        "headers": copy.deepcopy(table["headers"]),
        "rows": copy.deepcopy(table["rows"]),
    }
    if source_marker is not _MISSING:
        data["_source"] = source_marker
    return data


def _workpaper_note(source: str) -> dict:
    return {
        "_source": source,
        **_FINGERPRINT,
        "_sub_table_columns": {"货币资金": copy.deepcopy(_COLUMNS)},
        "sub_table_data": {
            "货币资金": [
                {"label": "库存现金", "end_amount": None, "prior_amount": None},
                {"label": "银行存款", "end_amount": None, "prior_amount": None},
                {"label": "合计", "end_amount": None, "prior_amount": None, "is_total": True},
            ],
        },
    }


def _rows_by_label(rows: list[dict]) -> dict[str, dict]:
    return {row["label"]: row for row in rows}


def _assert_formula_push_orm(note, wp_id) -> None:
    assert note.last_sync_source == "formula_push"
    assert note.last_sync_wp_id == wp_id
    assert note.last_sync_at is not None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "source_marker",
    [pytest.param(_MISSING, id="source-missing"), pytest.param(None, id="source-null")],
)
async def test_native_legacy_tables_keep_source_and_do_not_gain_sync_fingerprint(env, source_marker):
    """原生 ``_tables`` 是持久真源，公式推送不得把缺失/null 来源冒充成 workpaper。"""
    await env.add_note("五、1", _legacy_note(source_marker))

    result = await env.push()
    note = await env.note("五、1")
    table_data = note.table_data
    rows = _rows_by_label(table_data["_tables"][0]["rows"])

    assert result.note_sections == ["五、1"]
    assert rows["库存现金"]["values"] == [390, 203]
    assert rows["银行存款"]["values"] == [120, 100]
    assert table_data["rows"] == table_data["_tables"][0]["rows"]
    if source_marker is _MISSING:
        assert "_source" not in table_data
    else:
        assert "_source" in table_data and table_data["_source"] is None
    assert not {"_last_sync_wp_id", "_last_sync_sheet", "_last_sync_at"} & table_data.keys()
    _assert_formula_push_orm(note, env.wp_id)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("source_marker", "expected_source"),
    [
        pytest.param(_MISSING, "workpaper", id="new-structure-source"),
        pytest.param("workpaper_html", "workpaper_html", id="preserve-existing-html-source"),
    ],
)
async def test_new_main_skeleton_sets_only_missing_structure_source_and_is_projectable(
    env, source_marker, expected_source,
):
    """只有本次新建主表骨架才补结构来源；既有 ``workpaper_html`` 不降级。"""
    table_data = {
        "sub_table_data": {"保留的其他表": [{"label": "说明"}]},
        "_sub_table_columns": {"保留的其他表": [{"key": "label", "label": "项目", "is_label": True}]},
    }
    if source_marker is not _MISSING:
        table_data["_source"] = source_marker
    await env.add_note("五、1", table_data)

    result = await env.push()
    note = await env.note("五、1")
    saved = note.table_data

    assert "五、1" in result.note_sections
    assert saved["_source"] == expected_source
    assert "货币资金" in saved["sub_table_data"]
    raw_rows = _rows_by_label(saved["sub_table_data"]["货币资金"])
    assert (raw_rows["库存现金"]["end_amount"], raw_rows["库存现金"]["prior_amount"]) == (390, 203)

    projected = project_sub_tables(saved)
    assert projected is not None
    main = next(table for table in projected if table["name"] == "货币资金")
    projected_cash = _rows_by_label(main["rows"])["库存现金"]
    value_keys = [col["key"] for col in saved["_sub_table_columns"]["货币资金"] if not col.get("is_label")]
    assert projected_cash["values"] == [raw_rows["库存现金"].get(key) for key in value_keys]
    assert not {"_last_sync_wp_id", "_last_sync_sheet", "_last_sync_at"} & saved.keys()
    _assert_formula_push_orm(note, env.wp_id)


@pytest.mark.asyncio
@pytest.mark.parametrize("source", ["workpaper", "workpaper_html"])
async def test_real_workpaper_structure_and_existing_sync_fingerprint_are_preserved(env, source):
    """真实底稿结构来源和既有披露同步指纹保持；最近动作单独记 formula_push。"""
    await env.add_note("五、1", _workpaper_note(source))

    await env.push()
    note = await env.note("五、1")
    saved = note.table_data

    assert saved["_source"] == source
    assert {key: saved[key] for key in _FINGERPRINT} == _FINGERPRINT
    assert {key for key in saved if key.startswith("_last_sync_")} == set(_FINGERPRINT)
    rows = _rows_by_label(saved["sub_table_data"]["货币资金"])
    assert (rows["库存现金"]["end_amount"], rows["库存现金"]["prior_amount"]) == (390, 203)
    projected = project_sub_tables(saved)
    assert projected and any(table["name"] == "货币资金" for table in projected)
    _assert_formula_push_orm(note, env.wp_id)


@pytest.mark.asyncio
async def test_existing_source_less_sub_table_is_not_mistaken_for_new_skeleton(env):
    """已有目标子表只改数值，不因公式动作被当成本次新建的投影骨架。"""
    table_data = _workpaper_note("workpaper")
    table_data.pop("_source")
    for key in _FINGERPRINT:
        table_data.pop(key)
    await env.add_note("五、1", table_data)

    await env.push()
    note = await env.note("五、1")
    saved = note.table_data

    assert "_source" not in saved
    assert not {"_last_sync_wp_id", "_last_sync_sheet", "_last_sync_at"} & saved.keys()
    rows = _rows_by_label(saved["sub_table_data"]["货币资金"])
    assert (rows["库存现金"]["end_amount"], rows["库存现金"]["prior_amount"]) == (390, 203)
    _assert_formula_push_orm(note, env.wp_id)
