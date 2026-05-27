"""单测 — 附注公式 schema 扩展（Sprint 1.5 Task 1.5.4）.

Spec:    .kiro/specs/disclosure-note-full-revamp/ Sprint 1.5 Task 1.5.4
Design:  D4 _formulas 单元格级公式存储 schema 扩展（binding_id + evaluated_at）

覆盖：
- generate_formulas_for_table 给所有 4 类公式 value 写 binding_id=None 占位
- execute_note_formulas 公式实际执行成功时写 ISO 格式 evaluated_at
- 现有 5/6 字段读取不被新字段破坏（下游兼容性）
- _formulas 形态依旧是 dict[str, dict]（key="row:col"），不变成 list

PBT 不在本任务范围 — 1.5.4 是 schema 扩展（不动现有 dict 形态），
单测覆盖 evaluated_at 字段存在 + binding_id 字段存在两个不变量足够。
"""

from __future__ import annotations

import re
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.services.note_formula_generator import (
    execute_note_formulas,
    generate_formulas_for_table,
)


# ===========================================================================
# generate_formulas_for_table — binding_id 占位字段
# ===========================================================================


def test_vertical_sum_formula_has_binding_id_placeholder():
    """check_presets sub_item → vertical_sum 公式 value 含 binding_id=None 占位."""
    template = {
        "headers": ["项目", "期末", "期初"],
        "rows": [
            {"label": "明细1"},
            {"label": "明细2"},
            {"label": "合计", "is_total": True},
        ],
    }
    formulas = generate_formulas_for_table(template, ["sub_item"])
    # 合计行第 0/1 列应有 vertical_sum 公式
    assert "2:0" in formulas
    assert "2:1" in formulas
    for key in ("2:0", "2:1"):
        f = formulas[key]
        assert f["type"] == "vertical_sum"
        # 🆕 binding_id 字段必须存在（即便是 None）
        assert "binding_id" in f, f"{key} missing binding_id placeholder"
        assert f["binding_id"] is None


def test_cross_table_formula_has_binding_id_placeholder():
    """account_codes → cross_table 公式 value 含 binding_id=None 占位."""
    template = {
        "headers": ["项目", "期末", "期初"],
        "rows": [
            {"label": "库存现金", "account_codes": ["1001"]},
        ],
    }
    formulas = generate_formulas_for_table(template, [])
    # 明细行第 0/1 列应有 cross_table 公式
    assert "0:0" in formulas
    f = formulas["0:0"]
    assert f["type"] == "cross_table"
    assert "binding_id" in f
    assert f["binding_id"] is None


def test_horizontal_balance_formula_has_binding_id_placeholder():
    """movement preset → horizontal_balance 公式 value 含 binding_id=None 占位."""
    template = {
        "headers": ["项目", "期初", "增加", "减少", "期末"],
        "rows": [
            {"label": "明细1"},
        ],
    }
    formulas = generate_formulas_for_table(template, ["movement"])
    # 期末列（col 3）应有 horizontal_balance 公式
    assert "0:3" in formulas
    f = formulas["0:3"]
    assert f["type"] == "horizontal_balance"
    assert "binding_id" in f
    assert f["binding_id"] is None


def test_book_value_formula_has_binding_id_placeholder():
    """book_value preset → book_value 公式 value 含 binding_id=None 占位."""
    template = {
        "headers": ["项目", "期末"],
        "rows": [
            {"label": "原值期末"},
            {"label": "累计折旧期末"},
            {"label": "减值准备期末"},
            {"label": "账面价值期末"},
        ],
    }
    formulas = generate_formulas_for_table(template, ["book_value"])
    # 账面价值行（idx=3）第 0 列应有 book_value 公式
    assert "3:0" in formulas
    f = formulas["3:0"]
    assert f["type"] == "book_value"
    assert "binding_id" in f
    assert f["binding_id"] is None


def test_existing_six_fields_preserved():
    """现有 6 字段（type/expression/description/category/source/binding_id）全部存在 — 下游兼容."""
    template = {
        "headers": ["项目", "期末"],
        "rows": [{"label": "明细1", "account_codes": ["1001"]}],
    }
    formulas = generate_formulas_for_table(template, [])
    assert "0:0" in formulas
    f = formulas["0:0"]
    # 5 个原有 + 1 新增（binding_id），共 6 字段
    expected_keys = {"type", "expression", "description", "category", "source", "binding_id"}
    assert expected_keys.issubset(set(f.keys())), f"missing keys: {expected_keys - set(f.keys())}"


def test_formulas_is_dict_not_list():
    """_formulas 仍是 dict[str, dict]（不变成 list）— schema 形态铁律."""
    template = {
        "headers": ["项目", "期末"],
        "rows": [
            {"label": "明细1", "account_codes": ["1001"]},
            {"label": "合计", "is_total": True},
        ],
    }
    formulas = generate_formulas_for_table(template, ["sub_item"])
    assert isinstance(formulas, dict)
    # key 格式 "row:col"
    for key in formulas.keys():
        assert isinstance(key, str)
        assert ":" in key
        parts = key.split(":")
        assert len(parts) == 2
        assert parts[0].isdigit() and parts[1].isdigit()


# ===========================================================================
# execute_note_formulas — evaluated_at 字段
# ===========================================================================

ISO_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(\+\d{2}:\d{2}|Z|[+-]\d{2}:\d{2})?$"
)


def _make_note_with_formulas() -> SimpleNamespace:
    """构造一个含可执行公式的 DisclosureNote mock."""
    return SimpleNamespace(
        project_id=uuid4(),
        year=2025,
        note_section="五、1",
        table_data={
            "headers": ["项目", "期末", "期初"],
            "rows": [
                {"label": "明细1", "values": [10.0, 8.0]},
                {"label": "明细2", "values": [20.0, 15.0]},
                {"label": "合计", "values": [None, None], "is_total": True},
            ],
            "_formulas": {
                "2:0": {
                    "type": "vertical_sum",
                    "expression": "SUM(0:1, 0)",
                    "description": "合计列1",
                    "category": "auto_calc",
                    "source": "check_presets.sub_item",
                    "binding_id": None,
                },
                "2:1": {
                    "type": "vertical_sum",
                    "expression": "SUM(0:1, 1)",
                    "description": "合计列2",
                    "category": "auto_calc",
                    "source": "check_presets.sub_item",
                    "binding_id": None,
                },
            },
            "_check_presets": ["sub_item"],
        },
    )


def _empty_scalars_result() -> MagicMock:
    result = MagicMock()
    result.all = MagicMock(return_value=[])
    scalars = MagicMock()
    scalars.all = MagicMock(return_value=[])
    result.scalars = MagicMock(return_value=scalars)
    return result


def _scalars_with(items: list) -> MagicMock:
    result = MagicMock()
    scalars = MagicMock()
    scalars.all = MagicMock(return_value=items)
    result.scalars = MagicMock(return_value=scalars)
    result.all = MagicMock(return_value=[])
    return result


@pytest.mark.asyncio
async def test_execute_note_formulas_writes_evaluated_at_iso_format():
    """公式执行成功后 _formulas[key] 写入 ISO 格式 evaluated_at."""
    note = _make_note_with_formulas()

    # mock db：第 1 次查询返回 note，后续 _load_cross_table_data 6 次全空
    note_query_result = MagicMock()
    note_query_result.scalar_one_or_none = MagicMock(return_value=note)

    db = MagicMock()
    db.execute = AsyncMock(side_effect=[
        note_query_result,           # load note
        _empty_scalars_result(),     # report
        _empty_scalars_result(),     # tb
        _empty_scalars_result(),     # wp
        _empty_scalars_result(),     # notes (当年)
        _empty_scalars_result(),     # prior notes
        MagicMock(all=lambda: []),    # aging ledger
    ])
    db.flush = AsyncMock()
    db.rollback = AsyncMock()

    with patch("sqlalchemy.orm.attributes.flag_modified", lambda *_a, **_kw: None):
        result = await execute_note_formulas(
            db, note.project_id, note.year, note.note_section,
        )

    # 公式执行成功 → updated > 0
    assert result["updated"] >= 1, f"expected >=1 updated, got {result}"

    # 🆕 每个成功执行的公式都应有 evaluated_at（ISO 格式）
    formulas = note.table_data["_formulas"]
    for key, fdef in formulas.items():
        assert "evaluated_at" in fdef, f"{key} missing evaluated_at"
        ts = fdef["evaluated_at"]
        assert isinstance(ts, str), f"{key} evaluated_at not str: {type(ts)}"
        # ISO 8601 格式校验
        assert ISO_PATTERN.match(ts), f"{key} evaluated_at not ISO: {ts}"
        # 可被 datetime.fromisoformat 解析（双重保险）
        parsed = datetime.fromisoformat(ts)
        assert parsed.tzinfo is not None, f"{key} evaluated_at missing tz info"


@pytest.mark.asyncio
async def test_execute_note_formulas_preserves_binding_id():
    """execute_note_formulas 不破坏既有 binding_id 字段（不论 None 还是已填值）."""
    note = _make_note_with_formulas()
    # 给一个公式预填 binding_id（模拟 _build_with_binding 写入后的形态）
    note.table_data["_formulas"]["2:0"]["binding_id"] = "binding_huobi_total"

    note_query_result = MagicMock()
    note_query_result.scalar_one_or_none = MagicMock(return_value=note)

    db = MagicMock()
    db.execute = AsyncMock(side_effect=[
        note_query_result,
        _empty_scalars_result(),
        _empty_scalars_result(),
        _empty_scalars_result(),
        _empty_scalars_result(),
        _empty_scalars_result(),
        MagicMock(all=lambda: []),
    ])
    db.flush = AsyncMock()
    db.rollback = AsyncMock()

    with patch("sqlalchemy.orm.attributes.flag_modified", lambda *_a, **_kw: None):
        await execute_note_formulas(db, note.project_id, note.year, note.note_section)

    # 已填的 binding_id 必须保留
    assert note.table_data["_formulas"]["2:0"]["binding_id"] == "binding_huobi_total"
    # 未填的（"2:1"）保持 None
    assert note.table_data["_formulas"]["2:1"]["binding_id"] is None


@pytest.mark.asyncio
async def test_execute_note_formulas_does_not_break_existing_5_fields():
    """新增 evaluated_at / binding_id 不破坏现有 5 字段（type/expression/description/category/source）读取."""
    note = _make_note_with_formulas()
    note_query_result = MagicMock()
    note_query_result.scalar_one_or_none = MagicMock(return_value=note)

    db = MagicMock()
    db.execute = AsyncMock(side_effect=[
        note_query_result,
        _empty_scalars_result(),
        _empty_scalars_result(),
        _empty_scalars_result(),
        _empty_scalars_result(),
        _empty_scalars_result(),
        MagicMock(all=lambda: []),
    ])
    db.flush = AsyncMock()
    db.rollback = AsyncMock()

    with patch("sqlalchemy.orm.attributes.flag_modified", lambda *_a, **_kw: None):
        await execute_note_formulas(db, note.project_id, note.year, note.note_section)

    formulas = note.table_data["_formulas"]
    for key, fdef in formulas.items():
        # 现有 5 个字段必须仍然可读
        assert fdef["type"] == "vertical_sum"
        assert fdef["expression"].startswith("SUM(")
        assert fdef["description"] in ("合计列1", "合计列2")
        assert fdef["category"] == "auto_calc"
        assert fdef["source"] == "check_presets.sub_item"
