from __future__ import annotations

import ast
import re
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

ROOT = Path(__file__).resolve().parents[3]
APP = ROOT / "backend" / "app"


class FakeDb:
    def __init__(self, rowcount: int = 2) -> None:
        self.rowcount = rowcount
        self.statements = []
        self.flush_count = 0

    async def execute(self, statement):
        self.statements.append(statement)
        return SimpleNamespace(rowcount=self.rowcount)

    async def flush(self):
        self.flush_count += 1


@pytest.mark.asyncio
async def test_mark_note_stale_writes_source_and_flushes_without_commit():
    from app.services.stale_state import StaleSource, mark_note_stale

    db = FakeDb(rowcount=3)
    count = await mark_note_stale(
        db,
        uuid4(),
        source=StaleSource.ADJUSTMENT,
        sections=["八、1", "八、1"],
        year=2025,
    )

    assert count == 3
    assert db.flush_count == 1
    assert len(db.statements) == 1
    compiled = str(db.statements[0])
    assert "stale_source" in compiled
    assert "is_stale" in compiled


@pytest.mark.asyncio
async def test_clear_note_stale_only_targets_currently_stale_rows():
    from app.services.stale_state import clear_note_stale

    db = FakeDb(rowcount=1)
    count = await clear_note_stale(
        db,
        uuid4(),
        sections=["八、1"],
        year=2025,
    )

    assert count == 1
    assert db.flush_count == 1
    compiled = str(db.statements[0])
    assert "stale_source" in compiled
    assert "is_stale" in compiled


@pytest.mark.asyncio
async def test_unknown_source_is_rejected_before_database_write():
    from app.services.stale_state import mark_note_stale

    db = FakeDb()
    with pytest.raises(ValueError, match="不支持的附注 stale 来源"):
        await mark_note_stale(db, uuid4(), source="invented_source", sections=["八、1"])
    assert db.statements == []
    assert db.flush_count == 0


def test_stale_source_label_has_history_and_unknown_fallback():
    from app.services.stale_state import stale_source_label

    assert stale_source_label("adjustment") == "调整分录已变化"
    assert stale_source_label(None) == "来源未记录"
    assert stale_source_label("legacy_source") == "其他数据变化"


def _is_disclosure_write_call(node: ast.Call) -> bool:
    if not isinstance(node.func, ast.Attribute) or node.func.attr != "values":
        return False
    if not any(keyword.arg in {"is_stale", "stale_source"} for keyword in node.keywords):
        return False
    return "DisclosureNote" in ast.unparse(node)


def test_disclosure_note_stale_writes_are_centralized():
    violations: list[str] = []
    for path in sorted(APP.rglob("*.py")):
        if path.name == "stale_state.py" or "__pycache__" in path.parts:
            continue
        text = path.read_text(encoding="utf-8-sig", errors="replace")
        try:
            tree = ast.parse(text, filename=str(path))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                if any(
                    isinstance(target, ast.Attribute)
                    and isinstance(target.value, ast.Name)
                    and target.value.id == "note"
                    and target.attr in {"is_stale", "stale_source"}
                    for target in targets
                ) and "DisclosureNote" in text:
                    violations.append(f"{path.relative_to(ROOT)}:{node.lineno}")
            elif isinstance(node, ast.Call) and _is_disclosure_write_call(node):
                violations.append(f"{path.relative_to(ROOT)}:{node.lineno}")
        if re.search(r"(?is)UPDATE\s+disclosure_notes.{0,300}(?:is_stale|stale_source)", text):
            violations.append(f"{path.relative_to(ROOT)}:raw_sql")

    assert violations == []
