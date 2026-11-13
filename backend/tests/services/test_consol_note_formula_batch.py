"""合并附注多章节公式预取测试。"""
from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from app.services.consol_note_formula_service import section_formulas_many
from app.services.formula_settings.consol_note_settings import _overlay_formulas


def _formula(section: str, row: int, value: str):
    return SimpleNamespace(
        section_id=section,
        row_index=row,
        col_index=1,
        formula=value,
        source="seed",
    )


def test_overlay_formulas_preserves_override_and_disable_semantics():
    globals_by_section = {
        "S1": [_formula("S1", 0, "GLOBAL-1")],
        "S2": [_formula("S2", 0, "GLOBAL-2")],
    }
    project_rows = [
        SimpleNamespace(
            slot_key="S1|0|1",
            definition={"formula": "PROJECT-1"},
        ),
        SimpleNamespace(
            slot_key="S2|0|1",
            definition={"disabled": True},
        ),
    ]

    result = _overlay_formulas(
        ["S1", "S2"],
        globals_by_section,
        project_rows,
    )

    assert [(item.formula, item.source) for item in result["S1"]] == [
        ("PROJECT-1", "project")
    ]
    assert result["S2"] == []


@pytest.mark.asyncio
async def test_section_formulas_many_uses_two_queries_for_many_sections():
    global_rows = [_formula("S1", 0, "G1"), _formula("S2", 1, "G2")]
    project_rows = [
        SimpleNamespace(
            slot_key="S2|1|1",
            definition={"formula": "P2"},
        )
    ]

    class Scalars:
        def __init__(self, rows):
            self.rows = rows

        def all(self):
            return self.rows

    class Result:
        def __init__(self, rows):
            self.rows = rows

        def scalars(self):
            return Scalars(self.rows)

    class Savepoint:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

    class Db:
        def __init__(self):
            self.calls = 0

        async def execute(self, _statement):
            self.calls += 1
            return Result(global_rows if self.calls == 1 else project_rows)

        def begin_nested(self):
            return Savepoint()

    db = Db()
    result = await section_formulas_many(
        db,
        uuid.uuid4(),
        "soe",
        ["S1", "S2"],
    )

    assert db.calls == 2
    assert result["S1"][0].formula == "G1"
    assert result["S2"][0].formula == "P2"
