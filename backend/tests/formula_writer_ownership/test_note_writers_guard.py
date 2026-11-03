from __future__ import annotations

import ast
import importlib
from pathlib import Path

from app.services.note_writers import (
    CANONICAL_FIELDS,
    FRONTEND_BUILDER_AUTHORITY,
    NOTE_WRITER_EXCLUSIONS,
    NOTE_WRITER_SCAN_BLIND_SPOTS,
    NOTE_WRITERS,
)

ROOT = Path(__file__).resolve().parents[3]
APP = ROOT / "backend" / "app"
FIELDS = {"table_data", "text_content"}


def _module(path: Path) -> str:
    return ".".join(path.relative_to(ROOT / "backend").with_suffix("").parts)


class _WriterScan(ast.NodeVisitor):
    def __init__(self, module: str) -> None:
        self.module = module
        self.stack: list[str] = []
        self.found: set[str] = set()

    def _entry(self) -> str:
        return f"{self.module}:{'.'.join(self.stack) if self.stack else '<module>'}"

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()

    def visit_Assign(self, node: ast.Assign) -> None:
        if any(isinstance(t, ast.Attribute) and t.attr in FIELDS for t in node.targets):
            self.found.add(self._entry())
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if isinstance(node.target, ast.Attribute) and node.target.attr in FIELDS:
            self.found.add(self._entry())
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Name) and node.func.id == "DisclosureNote":
            self.found.add(self._entry())
        if isinstance(node.func, ast.Name) and node.func.id == "flag_modified" and len(node.args) >= 2:
            if isinstance(node.args[1], ast.Constant) and node.args[1].value == "table_data":
                self.found.add(self._entry())
        if isinstance(node.func, ast.Attribute) and node.func.attr == "values":
            if any(kw.arg in FIELDS for kw in node.keywords):
                self.found.add(self._entry())
        if isinstance(node.func, ast.Attribute) and node.func.attr in {"update_note", "update_note_from_structure"}:
            self.found.add(self._entry())
        self.generic_visit(node)

    def visit_Constant(self, node: ast.Constant) -> None:
        if isinstance(node.value, str):
            upper = node.value.upper()
            if "UPDATE DISCLOSURE_NOTES" in upper and (
                "TABLE_DATA" in upper or "TEXT_CONTENT" in upper
            ):
                self.found.add(self._entry())


def _observed() -> set[str]:
    found: set[str] = set()
    for path in sorted(APP.rglob("*.py")):
        text = path.read_text(encoding="utf-8-sig", errors="replace")
        try:
            tree = ast.parse(text, filename=str(path))
        except SyntaxError:
            continue
        scan = _WriterScan(_module(path))
        scan.visit(tree)
        found.update(scan.found)
    return found


def _defined_qualnames(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8-sig", errors="replace"))
    stack: list[str] = []
    names: set[str] = set()

    class Visitor(ast.NodeVisitor):
        def _visit(self, node):
            stack.append(node.name)
            names.add(".".join(stack))
            self.generic_visit(node)
            stack.pop()

        visit_ClassDef = _visit
        visit_FunctionDef = _visit
        visit_AsyncFunctionDef = _visit

    Visitor().visit(tree)
    return names


def test_registry_ids_fields_and_entrypoints_are_valid():
    ids = [spec.writer_id for spec in NOTE_WRITERS]
    assert len(ids) == len(set(ids)), "writer_id 必须唯一"
    assert all(spec.fields for spec in NOTE_WRITERS)
    assert all(set(spec.fields) <= CANONICAL_FIELDS for spec in NOTE_WRITERS)

    missing = []
    for spec in NOTE_WRITERS:
        module_name, qualname = spec.entrypoint.split(":", 1)
        path = ROOT / "backend" / Path(*module_name.split(".")).with_suffix(".py")
        if not path.exists() or qualname not in _defined_qualnames(path):
            missing.append(spec.entrypoint)
    assert missing == []


def test_all_observed_note_content_writers_are_registered_or_verified_excluded():
    observed = _observed()
    registered = {spec.entrypoint for spec in NOTE_WRITERS}
    uncovered = sorted(observed - registered - set(NOTE_WRITER_EXCLUSIONS))
    stale_registry = sorted(registered - observed - {
        # stale 状态走 SQLAlchemy update，但字段不属于 table_data/text_content 扫描面。
        "app.services.stale_state:mark_note_stale",
        "app.services.stale_state:clear_note_stale",
        # 间接门面本身不直接改字段，由下层已登记 writer 持久化。
        "app.routers.ai_content:_writeback_note",
        "app.routers.disclosure_notes:update_note._mutate",
        "app.routers.excel_html:save_edits",
        *NOTE_WRITER_SCAN_BLIND_SPOTS,
    })
    assert uncovered == [], f"未登记附注写入方：{uncovered}"
    assert stale_registry == [], f"登记入口已不再写附注：{stale_registry}"


def test_exclusions_are_real_and_still_non_persistent():
    observed = _observed()
    assert set(NOTE_WRITER_EXCLUSIONS) <= observed
    for entrypoint, reason in NOTE_WRITER_EXCLUSIONS.items():
        assert len(reason) >= 12
        module_name, qualname = entrypoint.split(":", 1)
        path = ROOT / "backend" / Path(*module_name.split(".")).with_suffix(".py")
        source = path.read_text(encoding="utf-8-sig", errors="replace")
        tree = ast.parse(source)
        target = next(
            node for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == qualname.rsplit(".", 1)[-1]
        )
        calls = {
            node.func.attr
            for node in ast.walk(target)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        }
        assert "commit" not in calls and "flush" not in calls, entrypoint


def test_frontend_builder_authority_guard_exists():
    path = ROOT / FRONTEND_BUILDER_AUTHORITY
    assert path.exists()
    source = path.read_text(encoding="utf-8")
    assert "NOT_YET_HEADLESS" in source
    assert "expect(registry.size).toBe(78)" in source
    assert "expect(Object.keys(NOT_YET_HEADLESS)).toEqual([])" in source


def test_dynamic_offline_import_writer_blind_spot_is_still_real():
    entry = "app.services.note_offline_import_tables:persist_applied_table_data"
    assert entry in NOTE_WRITER_SCAN_BLIND_SPOTS
    path = ROOT / "backend/app/services/note_offline_import_tables.py"
    source = path.read_text(encoding="utf-8-sig", errors="replace")
    tree = ast.parse(source)
    fn = next(
        node for node in ast.walk(tree)
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "persist_applied_table_data"
    )
    calls = [ast.unparse(node) for node in ast.walk(fn) if isinstance(node, ast.Call)]
    assert any("values(**values)" in call for call in calls)
    assert any(
        isinstance(node, ast.Dict)
        and any(isinstance(key, ast.Constant) and key.value == "table_data" for key in node.keys)
        for node in ast.walk(fn)
    )
