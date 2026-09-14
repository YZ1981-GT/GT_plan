"""单测 — refill_sections 对多表附注（`_tables`）逐表刷新.

背景（真实缺陷）：生成时顶层 ``rows`` 只是 ``_tables[0].rows`` 的**镜像副本**，
而前端 ``currentNoteTables`` 与 Word 导出都**优先渲染 `_tables`**。旧实现只刷
顶层 rows：
  - 多表附注（DB 实测 265 条）刷新结果用户看不到（"点刷新没反应"）
  - ``_tables[1..N]`` 从不刷新
  - 只有 ``_tables`` 没有顶层 rows 的附注（19 条）被整章跳过
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.models.report_models import ContentType, DisclosureNote
from app.services.disclosure_engine import DisclosureEngine

PROJECT_ID = uuid4()
YEAR = 2025
SECTION = "五、M1"


def _make_engine() -> DisclosureEngine:
    db = MagicMock()
    db.execute = AsyncMock()
    db.flush = AsyncMock()
    db.rollback = AsyncMock()
    db.commit = AsyncMock()
    eng = DisclosureEngine(db)
    eng._wp_cache = {}
    eng._tb_cache = {}
    eng._wp_account_cache = {}
    eng._wp_fine_cache = {}
    eng._prior_notes_cache = {}
    return eng


def _note(table_data: dict) -> MagicMock:
    note = MagicMock(spec=DisclosureNote)
    note.note_section = SECTION
    note.content_type = ContentType.table
    note.table_data = table_data
    note.is_stale = True
    return note


def _table(label: str, value):
    return {
        "headers": ["项目", "期末余额"],
        "rows": [
            {
                "label": label,
                "values": [value],
                "_cell_modes": {"0": "auto"},
                "_cell_meta": {"0": {"semantic": "closing_balance"}},
            }
        ],
    }


def _binding_for(labels: list[str]) -> dict:
    """每个表一份 binding（rows 按各表的行标签）。"""
    tables = []
    for lbl in labels:
        tables.append(
            {
                "header_normalize": [
                    {"semantic": "row_label"},
                    {"semantic": "closing_balance"},
                ],
                "rows": {
                    lbl: {
                        "binding": {
                            "closing_balance": {
                                "source": "trial_balance",
                                "account_codes": ["1001"],
                                "field": "audited",
                            }
                        }
                    }
                },
            }
        )
    return {"tables": tables}


@pytest.fixture(autouse=True)
def _patch_flag_modified():
    with patch("sqlalchemy.orm.attributes.flag_modified"):
        yield


async def _run(eng: DisclosureEngine, note, binding, resolver):
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [note]
    eng.db.execute = AsyncMock(return_value=mock_result)
    with (
        patch.object(eng, "_preload_data_for_notes", new_callable=AsyncMock),
        patch(
            "app.services.note_template_bindings_loader.get_binding_for_section",
            return_value=binding,
        ),
        patch(
            "app.services.note_source_resolvers.dispatch_resolver",
            side_effect=resolver,
        ),
    ):
        return await eng.refill_sections(PROJECT_ID, YEAR, [SECTION])


@pytest.mark.asyncio
async def test_all_nested_tables_are_refreshed():
    """`_tables` 的每张表都被刷新（旧实现只刷 table0 的顶层镜像）。"""
    t0 = _table("银行存款", 100.0)
    t1 = _table("其他货币资金", 200.0)
    td = {
        "headers": t0["headers"],
        "rows": t0["rows"],  # 生成时的镜像
        "_tables": [t0, t1],
    }
    note = _note(td)

    async def resolver(cell_binding, ctx):
        return 777.0

    report = await _run(eng := _make_engine(), note, _binding_for(["银行存款", "其他货币资金"]), resolver)
    assert eng is not None

    assert t0["rows"][0]["values"][0] == 777.0
    assert t1["rows"][0]["values"][0] == 777.0, "table1 也必须被刷新"
    assert report.cells_updated == 2
    assert report.sections_recomputed == [SECTION]


@pytest.mark.asyncio
async def test_top_level_mirror_synced_after_refresh():
    """刷新后顶层 rows/headers 与 `_tables[0]` 保持一致（避免两份不一致）。"""
    t0 = _table("银行存款", 100.0)
    td = {
        "headers": list(t0["headers"]),
        "rows": [dict(r) for r in t0["rows"]],  # 顶层是**独立副本**（模拟 JSONB 往返）
        "_tables": [t0],
    }
    note = _note(td)

    async def resolver(cell_binding, ctx):
        return 555.0

    await _run(_make_engine(), note, _binding_for(["银行存款"]), resolver)

    assert t0["rows"][0]["values"][0] == 555.0
    assert td["rows"][0]["values"][0] == 555.0, "顶层镜像应同步（否则前端/导出看不到刷新结果）"
    assert td["headers"] == t0["headers"]


@pytest.mark.asyncio
async def test_tables_only_note_not_skipped():
    """只有 `_tables` 没有顶层 rows 的附注不再被当纯文本跳过。"""
    t0 = _table("银行存款", None)
    td = {"_tables": [t0]}
    note = _note(td)

    async def resolver(cell_binding, ctx):
        return 42.0

    report = await _run(_make_engine(), note, _binding_for(["银行存款"]), resolver)

    assert SECTION not in report.text_only_sections
    assert report.cells_updated == 1
    assert t0["rows"][0]["values"][0] == 42.0


@pytest.mark.asyncio
async def test_single_table_legacy_path_unchanged():
    """无 `_tables` 的 legacy 单表附注行为不变（零回归）。"""
    td = _table("银行存款", 100.0)
    note = _note(td)

    async def resolver(cell_binding, ctx):
        return 300.0

    report = await _run(_make_engine(), note, _binding_for(["银行存款"]), resolver)

    assert report.cells_updated == 1
    assert td["rows"][0]["values"][0] == 300.0
    assert "_tables" not in td


@pytest.mark.asyncio
async def test_one_table_error_does_not_lose_other_tables_report():
    """某表取数抛错 → 记 errors 且该章节不写回（保守），不崩溃。"""
    t0 = _table("银行存款", 100.0)
    t1 = _table("其他货币资金", 200.0)
    td = {"rows": t0["rows"], "headers": t0["headers"], "_tables": [t0, t1]}
    note = _note(td)

    async def resolver(cell_binding, ctx):
        if ctx.get("table_index") == 1:
            raise RuntimeError("boom")
        return 888.0

    report = await _run(_make_engine(), note, _binding_for(["银行存款", "其他货币资金"]), resolver)

    assert report.errors and SECTION in report.errors[0]
    assert report.sections_recomputed == []
