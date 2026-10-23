"""pytest 导入路径隔离守卫（spec formula-fetch-and-wp-generation-defect-closure R8）。

`backend/pytest.ini` 曾写 `pythonpath = tests`，把 tests/ 放到导入路径首位：tests/playwright 包遮蔽真实 playwright，
pytest-playwright 插件加载即 `ModuleNotFoundError: playwright.sync_api`，不带 `-p no:playwright` 连 pytest 都起不来；
tests/scripts 同样遮蔽 backend/scripts（靠插入顺序侥幸可用）。改为测试根目录的辅助模块一律 `from tests.xxx import`。
"""
from __future__ import annotations

import ast
import configparser
import fnmatch
import importlib.machinery
import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
TESTS = BACKEND / "tests"
# 导入即改写整个进程的包：locust 导入时 gevent.monkey.patch_all()，pytest 进程的 threading / socket / time 被换掉，
# 此后 TestClient 与 asyncio 用例静默卡死（全量 `pytest tests` 曾零输出挂起 30 分钟）。
_PROCESS_PATCHING_ROOTS = {"locust", "gevent"}


def _ini_pythonpath() -> list[Path]:
    cp = configparser.ConfigParser()
    cp.read(BACKEND / "pytest.ini", encoding="utf-8")
    raw = cp.get("pytest", "pythonpath", fallback="")
    return [(BACKEND / p).resolve() for p in raw.split() if p.strip()]


def _children(directory: Path) -> set[str]:
    out = set()
    for child in directory.iterdir():
        if child.name == "__pycache__" or child.name.startswith("."):
            continue
        if child.is_dir():
            out.add(child.name)
        elif child.suffix == ".py" and child.name not in ("__init__.py", "conftest.py"):
            out.add(child.stem)
    return out


def _resolvable_elsewhere(name: str, excluded: Path) -> bool:
    """不经 ``excluded`` 目录能否导入到同名模块（已安装包 / 标准库 / backend 下的同名包）。"""
    if name in sys.stdlib_module_names:
        return True
    search = [p for p in sys.path if p and Path(p).resolve() != excluded] + [str(BACKEND)]
    return importlib.machinery.PathFinder.find_spec(name, search) is not None


def _shadowing(directory: Path) -> list[str]:
    return sorted(n for n in _children(directory) if _resolvable_elsewhere(n, directory.resolve()))


def test_pythonpath_entries_do_not_shadow_installed_packages():
    entries = _ini_pythonpath()
    assert TESTS.resolve() not in entries, "pytest.ini 不得把 tests/ 放进 pythonpath（会遮蔽 playwright / scripts）"
    for entry in entries:
        assert not _shadowing(entry), f"pythonpath 条目 {entry} 下的这些名字遮蔽了真实包：{_shadowing(entry)}"


def test_shadow_detector_flags_tests_dir():
    """判据自检：tests/ 本身确实含会遮蔽真实包的名字（playwright）—— 若它又被放进 pythonpath，上一条必红。"""
    assert "playwright" in _shadowing(TESTS)


def _bare_root_imports() -> list[str]:
    root_only = {n for n in _children(TESTS) if not _resolvable_elsewhere(n, TESTS.resolve())}
    hits: list[str] = []
    for f in sorted(TESTS.rglob("*.py")):
        if "__pycache__" in f.parts:
            continue
        try:
            tree = ast.parse(f.read_text(encoding="utf-8-sig"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names = [node.module]
            elif isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            else:
                continue
            for name in names:
                if name.split(".")[0] in root_only:
                    hits.append(f"{f.relative_to(BACKEND).as_posix()}:{node.lineno} {name}")
    return hits


def test_tests_root_modules_are_imported_package_qualified():
    hits = _bare_root_imports()
    assert not hits, "测试根目录的模块要写 `from tests.<模块> import …`（裸导入依赖 tests/ 在导入路径上）：\n" + "\n".join(hits)


def test_bare_import_detector_sees_root_helper_modules():
    """判据自检：authz_world 只存在于 tests/ 根目录 —— 裸导入它会被上一条抓到。"""
    root_only = {n for n in _children(TESTS) if not _resolvable_elsewhere(n, TESTS.resolve())}
    assert {"authz_world", "note_edit_gate_recipes"} <= root_only


def _subprocess_env() -> dict[str, str]:
    """子进程环境 = pytest 启动时的环境（不带之后被别的 conftest / 用例改过的变量）。"""
    from tests.conftest import ENVIRON_AT_START

    return dict(ENVIRON_AT_START, PYTHONIOENCODING="utf-8")


def test_subprocess_env_ignores_variables_changed_during_the_run(monkeypatch):
    """同一进程里先收集过 tests/e2e（其 conftest 设 sqlite DATABASE_URL）时，子进程不能继承它。"""
    from tests.conftest import ENVIRON_AT_START

    polluted = "sqlite+aiosqlite:///__set_during_run__"
    monkeypatch.setenv("DATABASE_URL", polluted)
    got = _subprocess_env().get("DATABASE_URL")
    assert got != polluted and got == ENVIRON_AT_START.get("DATABASE_URL")


def test_pytest_starts_without_disabling_playwright_plugin():
    """不带 `-p no:playwright` 能完成收集（插件已安装时这正是原先崩溃的位置）。"""
    env = _subprocess_env()
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "--co", "-q", "-p", "no:cacheprovider", "tests/test_pytest_import_isolation.py"],
        cwd=BACKEND, env=env, capture_output=True, timeout=300,
    )
    out = (proc.stdout + proc.stderr).decode("utf-8", "replace")
    assert proc.returncode == 0, out[-3000:]
    assert "test_pytest_starts_without_disabling_playwright_plugin" in out, out[-3000:]


# ── 收集期进程级副作用：被收集的模块不得导入 locust / gevent ─────────────────────────────


def _python_files_patterns() -> list[str]:
    cp = configparser.ConfigParser()
    cp.read(BACKEND / "pytest.ini", encoding="utf-8")
    return cp.get("pytest", "python_files", fallback="test_*.py *_test.py").split()


def _collect_ignored(conftest: Path) -> set[Path]:
    """读 conftest 的 ``collect_ignore`` 字面量（AST，不导入）。"""
    tree = ast.parse(conftest.read_text(encoding="utf-8-sig"))
    out: set[Path] = set()
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "collect_ignore" for t in node.targets):
            for elt in getattr(node.value, "elts", []):
                if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                    out.add((conftest.parent / elt.value).resolve())
    return out


def _module_level_imports(tree: ast.Module) -> Iterator[tuple[int, str]]:
    """模块导入时就会执行的 import（含 try / if / with 块，不含函数与类体）。"""
    stack: list[ast.stmt] = list(tree.body)
    while stack:
        node = stack.pop()
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield node.lineno, alias.name
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            yield node.lineno, node.module
        elif isinstance(node, (ast.Try, ast.If, ast.With)):
            for field in ("body", "orelse", "finalbody"):
                stack.extend(getattr(node, field, []) or [])
            for handler in getattr(node, "handlers", []) or []:
                stack.extend(handler.body)


def _collected_process_patching_imports() -> list[str]:
    patterns = _python_files_patterns()
    ignored: set[Path] = set()
    for conftest in TESTS.rglob("conftest.py"):
        ignored |= _collect_ignored(conftest)
    hits: list[str] = []
    for f in sorted(TESTS.rglob("*.py")):
        if "__pycache__" in f.parts or not any(fnmatch.fnmatch(f.name, p) for p in patterns):
            continue
        resolved = f.resolve()
        if resolved in ignored or any(parent in ignored for parent in resolved.parents):
            continue
        try:
            tree = ast.parse(f.read_text(encoding="utf-8-sig"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        for lineno, name in _module_level_imports(tree):
            if name.split(".")[0] in _PROCESS_PATCHING_ROOTS:
                hits.append(f"{f.relative_to(BACKEND).as_posix()}:{lineno} {name}")
    return hits


def test_collected_modules_do_not_import_process_patching_packages():
    hits = _collected_process_patching_imports()
    assert not hits, (
        "这些文件会被 pytest 收集，导入时就给整个进程打 gevent 补丁（之后的用例卡死）；"
        "压测脚本加进 tests/conftest.py 的 collect_ignore：\n" + "\n".join(hits)
    )


def test_process_patching_detector_sees_load_test_script():
    """判据自检：load_test.py 命中默认 python_files 且顶层导入 locust —— 把它移出 collect_ignore，上一条必红。"""
    script = TESTS / "load_test.py"
    assert any(fnmatch.fnmatch(script.name, p) for p in _python_files_patterns())
    names = [n for _, n in _module_level_imports(ast.parse(script.read_text(encoding="utf-8")))]
    assert "locust" in names
    assert script.resolve() in _collect_ignored(TESTS / "conftest.py")


class _FakeMonkey:
    def __init__(self, patched: bool):
        self._patched = patched

    def is_module_patched(self, name: str) -> bool:
        return self._patched and name == "threading"


def test_collection_finish_hook_rejects_gevent_patched_process(monkeypatch):
    """经辅助模块间接导入 locust 时静态判据看不到 —— 收集结束钩子在跑任何用例前报错，而不是让进程卡死。"""
    from tests import conftest as root_conftest

    monkeypatch.setitem(sys.modules, "gevent.monkey", _FakeMonkey(patched=True))
    with pytest.raises(pytest.UsageError, match=r"gevent\.monkey\.patch_all"):
        root_conftest.pytest_collection_finish(None)


def test_collection_finish_hook_allows_unpatched_process(monkeypatch):
    from tests import conftest as root_conftest

    monkeypatch.setitem(sys.modules, "gevent.monkey", _FakeMonkey(patched=False))
    root_conftest.pytest_collection_finish(None)
    monkeypatch.delitem(sys.modules, "gevent.monkey")
    root_conftest.pytest_collection_finish(None)
