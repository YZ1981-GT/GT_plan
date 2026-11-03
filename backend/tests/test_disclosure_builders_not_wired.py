"""后端披露表 builder 已删除，不得复活（静态守卫）。

``disclosure_builders`` 与前端披露 Tab 不是同一口径（D2 账龄期末恒 0、坏账准备恒 0、标准 builder 只产出一张两行表），
``build_and_sync`` 写进附注的是错数。2026-10-26 从 ``WORKPAPER_SAVED`` 与 ``refresh-from-disclosure`` 摘除
（spec note-pull-header-formula-closure R1），2026-10-27 连模块一起删除（spec note-pull-followup-closure R17）：
披露表口径只有前端一份（ADR-DPA-001），不打开底稿取数走附注页离屏同步（``noteHeadlessDisclosure.ts``）。

判据：①模块与包不存在 ②``backend`` 下（app / scripts / tests）没有任何代码 import 它们或调用 ``build_and_sync``
（AST：注释 / docstring 不算引用，铁律 ㉖）③附注刷新服务的底稿保存 handler 不再订阅。
"""
from __future__ import annotations

import ast
import inspect
import textwrap
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
APP = BACKEND / "app"
_SERVICE = "app.services.disclosure_payload_builder_service"
_PACKAGE = "app.services.disclosure_builders"
_FORBIDDEN_NAMES = frozenset({"build_and_sync", "build_for_wp_code"})


def _offences(source: str) -> list[str]:
    tree = ast.parse(source)
    out: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            if node.module == _SERVICE or node.module == _PACKAGE or node.module.startswith(_PACKAGE + "."):
                out.append(f"from {node.module} import …")
            elif node.module == "app.services" and any(
                    a.name in ("disclosure_builders", "disclosure_payload_builder_service") for a in node.names):
                out.append(f"from app.services import {', '.join(a.name for a in node.names)}")
        elif isinstance(node, ast.Import):
            out += [f"import {a.name}" for a in node.names
                    if a.name in (_SERVICE, _PACKAGE) or a.name.startswith(_PACKAGE + ".")]
        elif isinstance(node, ast.Attribute) and node.attr in _FORBIDDEN_NAMES:
            out.append(f".{node.attr}")
        elif isinstance(node, ast.Name) and node.id in _FORBIDDEN_NAMES:
            out.append(node.id)
    return out


def _backend_files() -> list[Path]:
    me = Path(__file__).resolve()
    return [p for p in BACKEND.rglob("*.py")
            if p.resolve() != me and "__pycache__" not in p.parts and ".venv" not in p.parts]


def test_builder_modules_are_gone() -> None:
    assert not (APP / "services" / "disclosure_payload_builder_service.py").exists()
    assert not any((APP / "services" / "disclosure_builders").glob("*.py")), "disclosure_builders 包又出现了"


def test_nothing_imports_or_calls_the_builders() -> None:
    hits = {}
    for path in _backend_files():
        try:
            found = _offences(path.read_text(encoding="utf-8-sig"))  # 个别文件带 BOM
        except SyntaxError:
            continue
        if found:
            hits[str(path.relative_to(BACKEND))] = found
    assert not hits, f"已删除的后端披露表 builder 又被引用：{hits}"


def test_scan_covers_app_scripts_and_tests() -> None:
    """扫描范围不空转：生产代码、脚本、测试三处都在扫描集合里。"""
    rel = {p.relative_to(BACKEND).parts[0] for p in _backend_files()}
    assert {"app", "scripts", "tests"} <= rel
    names = {p.name for p in _backend_files()}
    assert {"event_handlers_cycle_linkage.py", "disclosure_notes.py", "note_disclosure_refresh_service.py"} <= names


def test_detector_flags_the_removed_wiring() -> None:
    """变异：把 2026-10-26 前的接法写回去，判据必须点名（不空转）。"""
    lazy = textwrap.dedent('''
        async def handler(db):
            from app.services.disclosure_payload_builder_service import build_and_sync, get_builder
            if get_builder("D2") is not None:
                await build_and_sync(db, 1, 2025, "D2")
    ''')
    assert _offences(lazy) == [f"from {_SERVICE} import …", "build_and_sync"]
    assert _offences("import app.services.disclosure_builders\n") == ["import app.services.disclosure_builders"]
    assert _offences("import x\nx.build_for_wp_code(1)\n") == [".build_for_wp_code"]
    # 注释 / 字符串里提到不算引用
    assert _offences("# build_and_sync 已删除\nDOC = 'build_and_sync'\n") == []


def test_workpaper_saved_no_longer_refreshes_notes_from_backend_builders() -> None:
    """底稿保存不再订阅附注刷新 handler（AST：注册函数里没有 import 它）。"""
    from app.services import event_handlers_cycle_linkage as linkage

    tree = ast.parse(textwrap.dedent(inspect.getsource(linkage.register_cycle_linkage_handlers)))
    imported = {
        (node.module, alias.name)
        for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
        for alias in node.names
    }
    assert ("app.services.note_disclosure_refresh_service", "handle_workpaper_saved") not in imported
