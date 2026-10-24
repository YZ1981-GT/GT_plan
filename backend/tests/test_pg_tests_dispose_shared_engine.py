"""守卫：用共享连接池（``app.core.database`` 的 ``engine`` / ``async_engine`` / ``async_session``）跑 ``asyncio.run`` 的测试
文件，必须在用完后释放连接池（``engine.dispose()``，或 ``asyncio.run(run_and_dispose(...))``，见 ``tests/_pg_shared_engine.py``）。

共享引擎的连接池绑在建连时的事件循环上。``asyncio.run`` 退出即关掉该循环，池里的连接没释放的话，同一进程里下一个
``asyncio.run`` 的真库用例从池里拿到旧循环的连接，ping 时报 ``Event loop is closed`` /
``'NoneType' object has no attribute 'send'``——单跑全绿、全量跑才红，红在**下一个**文件上，很容易被误判成业务缺陷。
2026-10-24 全量跑公式推送用例时 K2 canary 即因此红（前一个文件 K1 + D4 canary 没释放）；同类共 12 个文件一并补上
（spec formula-fetch-followup-defect-closure）。

判定用 AST（注释、文档字符串里写了 ``engine.dispose()`` 不算数）：文件里从 ``app.core.database`` 导入了上述任一对象
（含函数体内的延迟导入、``as`` 别名）且调用了 ``asyncio.run(...)``，就必须有对引擎别名的 ``.dispose()`` 调用或
``run_and_dispose(...)`` 调用。只把 ``get_db`` 当依赖覆盖键用的文件不经连接池，不在此列。
"""
from __future__ import annotations

import ast
import warnings
from pathlib import Path

_TESTS = Path(__file__).resolve().parent
_POOL_OBJECTS = frozenset({"engine", "async_engine", "async_session"})
_ENGINES = frozenset({"engine", "async_engine"})


def _parse(path: Path) -> ast.AST:
    # utf-8-sig：个别文件带 BOM；别的文件里的无效转义只是 SyntaxWarning，与本判据无关
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", SyntaxWarning)
        return ast.parse(path.read_text(encoding="utf-8-sig"))


def _facts(tree: ast.AST) -> tuple[bool, bool, bool]:
    """(导入了共享连接池对象, 调用了 asyncio.run, 释放了连接池)。"""
    pool_aliases: set[str] = set()
    engine_aliases: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "app.core.database":
            for alias in node.names:
                if alias.name in _POOL_OBJECTS:
                    pool_aliases.add(alias.asname or alias.name)
                if alias.name in _ENGINES:
                    engine_aliases.add(alias.asname or alias.name)
    runs = disposes = False
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
            if func.value.id == "asyncio" and func.attr == "run":
                runs = True
            elif func.value.id in engine_aliases and func.attr == "dispose":
                disposes = True
        if (isinstance(func, ast.Name) and func.id == "run_and_dispose") or (
                isinstance(func, ast.Attribute) and func.attr == "run_and_dispose"):
            disposes = True
    return bool(pool_aliases), runs, disposes


def _offenders(root: Path) -> list[str]:
    out = []
    for path in sorted(root.rglob("test_*.py")):
        uses_pool, runs, disposes = _facts(_parse(path))
        if uses_pool and runs and not disposes:
            out.append(path.relative_to(root).as_posix())
    return out


def test_shared_engine_is_disposed_after_asyncio_run():
    assert _offenders(_TESTS) == [], (
        "这些测试文件用共享连接池跑 asyncio.run 却没有释放（engine.dispose() 或 run_and_dispose），"
        "会让下一个真库用例报 Event loop is closed")


def test_scanner_sees_real_users_and_ignores_comments(tmp_path):
    """判据不空转：真实文件里确有这种用法；漏写释放的样例被抓到（含 as 别名、函数体内导入）；
    只在注释 / 文档字符串里写 dispose 不算；两种释放写法都认。"""
    real = [p for p in _TESTS.rglob("test_*.py") if _facts(_parse(p))[:2] == (True, True)]
    assert len(real) >= 12, [p.name for p in real]
    samples = {
        "test_bad_engine.py": (
            '"""这里提到 engine.dispose() 不算。"""\nimport asyncio\n\n\nasync def _s():\n'
            "    from app.core.database import engine  # engine.dispose() 写在注释里也不算\n"
            "    async with engine.connect():\n        pass\n\n\ndef test_x():\n    asyncio.run(_s())\n"),
        "test_bad_session_alias.py": (
            "import asyncio\n\n\ndef test_x():\n    from app.core.database import async_session as Session\n\n"
            "    async def _s():\n        async with Session():\n            pass\n\n    asyncio.run(_s())\n"),
        "test_good_engine.py": (
            "import asyncio\nfrom app.core.database import engine\n\n\nasync def _s():\n"
            "    try:\n        pass\n    finally:\n        await engine.dispose()\n\n\ndef test_x():\n    asyncio.run(_s())\n"),
        "test_good_helper.py": (
            "import asyncio\nfrom app.core.database import async_session\nfrom tests._pg_shared_engine import run_and_dispose\n\n\n"
            "async def _s():\n    async with async_session():\n        pass\n\n\n"
            "def test_x():\n    asyncio.run(run_and_dispose(_s()))\n"),
        "test_get_db_only.py": (
            "import asyncio\nfrom app.core.database import get_db\n\n\ndef test_x():\n"
            "    overrides = {get_db: None}\n    asyncio.run(asyncio.sleep(0))\n"),
    }
    for name, text in samples.items():
        (tmp_path / name).write_text(text, encoding="utf-8")
    assert _offenders(tmp_path) == ["test_bad_engine.py", "test_bad_session_alias.py"]
