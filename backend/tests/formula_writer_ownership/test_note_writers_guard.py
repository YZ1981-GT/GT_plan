from __future__ import annotations

import ast
import importlib
from pathlib import Path

from app.services.note_writers import (
    CANONICAL_FIELDS,
    FRONTEND_BUILDER_AUTHORITY,
    NOTE_WRITER_EXCLUSIONS,
    NOTE_WRITER_INDIRECT_FACADES,
    NOTE_WRITER_SCAN_BLIND_SPOTS,
    NOTE_WRITER_SCAN_OUT_OF_SURFACE,
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
    # 「登记了但 AST 已看不见它直接写字段」= 写入已委托给下层（间接门面 / 扫描面外），
    # 必须逐条在可伪证清单里声明；空白名单会让「登记表与事实分离」静默通过。
    stale_registry = sorted(
        registered - observed
        - set(NOTE_WRITER_INDIRECT_FACADES)
        - set(NOTE_WRITER_SCAN_OUT_OF_SURFACE)
        - set(NOTE_WRITER_SCAN_BLIND_SPOTS)
    )
    assert uncovered == [], f"未登记附注写入方：{uncovered}"
    assert stale_registry == [], f"登记入口已不再写附注也未被声明为间接门面：{stale_registry}"


def test_indirect_facades_are_real_and_falsifiable():
    """间接门面清单必须可伪证：登记在册、AST 已看不见它直接写字段、且真的调用了委托目标。"""
    observed = _observed()
    registered = {spec.entrypoint for spec in NOTE_WRITERS}
    problems: list[str] = []
    for facade, delegates_to in NOTE_WRITER_INDIRECT_FACADES.items():
        if facade not in registered:
            problems.append(f"{facade}：不在 NOTE_WRITERS（间接门面必须先是登记写入方）")
        if facade in observed:
            problems.append(f"{facade}：AST 仍看见它直接写 table_data/text_content（不该登记为间接门面）")
        if delegates_to not in registered:
            problems.append(f"{facade}：委托目标 {delegates_to} 不在 NOTE_WRITERS")
        tail = delegates_to.split(":", 1)[1].rsplit(".", 1)[-1]
        module_name, qualname = facade.split(":", 1)
        path = ROOT / "backend" / Path(*module_name.split(".")).with_suffix(".py")
        if tail not in _body_calls(path, qualname):
            problems.append(f"{facade}：函数体没有调用 {tail}，委托声明不成立")
    assert problems == [], "间接门面清单不可伪证：\n" + "\n".join(problems)


def _resolve_target(path: Path, qualname: str) -> ast.AST:
    tree = ast.parse(path.read_text(encoding="utf-8-sig", errors="replace"))
    scope: list[ast.stmt] = tree.body
    node: ast.AST | None = None
    for part in qualname.split("."):
        node = next(
            (n for n in scope
             if isinstance(n, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == part),
            None,
        )
        assert node is not None, f"{path.name}:{qualname} 未找到"
        scope = getattr(node, "body", [])
    return node


def _body_calls(path: Path, qualname: str) -> set[str]:
    """该函数体（含嵌套 def 的调用点）调用到的名字末段。"""
    node = _resolve_target(path, qualname)
    names: set[str] = set()
    for stmt in getattr(node, "body", []):
        for n in ast.walk(stmt):
            if isinstance(n, ast.Call):
                fn = n.func
                if isinstance(fn, ast.Attribute):
                    names.add(fn.attr)
                elif isinstance(fn, ast.Name):
                    names.add(fn.id)
    return names


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
