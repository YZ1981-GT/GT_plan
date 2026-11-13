"""合并附注 stale 写入必须经统一状态模块的 AST 守卫。"""
from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1] / "app"
STATE_MODULE = ROOT / "services" / "consol_note_stale_state.py"


def _is_false_constant(node: ast.AST) -> bool:
    return isinstance(node, ast.Constant) and node.value is False


def _contains_model_name(node: ast.AST, model_names: set[str]) -> bool:
    return any(isinstance(item, ast.Name) and item.id in model_names for item in ast.walk(node))


def _offenders(source: str, filename: str = "fixture.py") -> list[str]:
    tree = ast.parse(source, filename=filename)
    model_names = {"ConsolNoteData"}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "app.models.consol_note_data_models":
            for alias in node.names:
                if alias.name == "ConsolNoteData":
                    model_names.add(alias.asname or alias.name)

    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Attribute) and target.attr == "is_stale":
                    found.append(f"{filename}:{node.lineno}: attribute assignment")
        elif isinstance(node, ast.AnnAssign):
            target = node.target
            if isinstance(target, ast.Attribute) and target.attr == "is_stale":
                found.append(f"{filename}:{node.lineno}: annotated assignment")
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute) and node.func.attr == "values" \
                    and _contains_model_name(node.func.value, model_names):
                for keyword in node.keywords:
                    if keyword.arg == "is_stale":
                        found.append(f"{filename}:{node.lineno}: values(is_stale=...)" )
            is_model_ctor = isinstance(node.func, ast.Name) and node.func.id in model_names
            if is_model_ctor:
                stale_kw = next((kw for kw in node.keywords if kw.arg == "is_stale"), None)
                if stale_kw is not None and not _is_false_constant(stale_kw.value):
                    has_reason = any(kw.arg == "stale_reason" for kw in node.keywords)
                    if not has_reason:
                        found.append(f"{filename}:{node.lineno}: dynamic constructor stale state")
    return found


def _production_offenders() -> list[str]:
    offenders: list[str] = []
    for path in ROOT.rglob("*.py"):
        if path == STATE_MODULE or "__pycache__" in path.parts:
            continue
        source = path.read_text(encoding="utf-8")
        if "ConsolNoteData" not in source:
            continue
        offenders.extend(_offenders(source, str(path.relative_to(ROOT))))
    return offenders


def test_production_consol_note_stale_writes_use_single_state_module():
    offenders = _production_offenders()
    assert offenders == [], "发现绕过 consol_note_stale_state 的写入：\n" + "\n".join(offenders)


def test_guard_has_non_empty_scan_surface():
    scanned = [
        path for path in ROOT.rglob("*.py")
        if path != STATE_MODULE and "ConsolNoteData" in path.read_text(encoding="utf-8")
    ]
    assert scanned, "stale 写入守卫扫描分母不能为空"


def test_guard_rejects_attribute_update_values_and_dynamic_constructor_mutations():
    assert _offenders(
        "from app.models.consol_note_data_models import ConsolNoteData\n"
        "import sqlalchemy as sa\n"
        "def f(record):\n"
        "    record.is_stale = True\n"
        "    sa.update(ConsolNoteData).values(is_stale=True)\n"
        "    return ConsolNoteData(is_stale=flag)\n"
    ) == [
        "fixture.py:4: attribute assignment",
        "fixture.py:5: values(is_stale=...)",
        "fixture.py:6: dynamic constructor stale state",
    ]


def test_guard_allows_constant_fresh_constructor_and_read_only_access():
    assert _offenders(
        "from app.models.consol_note_data_models import ConsolNoteData\n"
        "def f(record):\n"
        "    return record.is_stale, ConsolNoteData(is_stale=False)\n"
    ) == []
