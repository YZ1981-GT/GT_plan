"""守卫：用共享引擎 ``app.core.database.engine`` + ``asyncio.run`` 的测试文件必须在用完后 ``engine.dispose()``。

共享引擎的连接池绑在建连时的事件循环上。``asyncio.run`` 退出即关掉该循环，池里的连接没释放的话，同一进程里下一个
``asyncio.run`` 的真库用例从池里拿到旧循环的连接，ping 时报 ``Event loop is closed`` /
``'NoneType' object has no attribute 'send'``——单跑全绿、全量跑才红，红在**下一个**文件上，很容易被误判成业务缺陷。
2026-10-24 全量跑公式推送用例时 K2 canary 即因此红（前一个文件 K1 + D4 canary 没释放），同类 4 个文件一并补上
（spec formula-fetch-followup-defect-closure）。

判定用 AST（注释、文档字符串里写了 ``engine.dispose()`` 不算数）：文件里有 ``from app.core.database import engine``
（含函数体内的延迟导入）且调用了 ``asyncio.run(...)``，就必须有 ``engine.dispose()`` 调用。
"""
from __future__ import annotations

import ast
import warnings
from pathlib import Path

_TESTS = Path(__file__).resolve().parent


def _parse(path: Path) -> ast.AST:
    # utf-8-sig：个别文件带 BOM；别的文件里的无效转义只是 SyntaxWarning，与本判据无关
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", SyntaxWarning)
        return ast.parse(path.read_text(encoding="utf-8-sig"))


def _facts(tree: ast.AST) -> tuple[bool, bool, bool]:
    imports_engine = runs = disposes = False
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "app.core.database":
            imports_engine |= any(alias.name == "engine" and alias.asname is None for alias in node.names)
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            owner = node.func.value
            if isinstance(owner, ast.Name) and owner.id == "asyncio" and node.func.attr == "run":
                runs = True
            elif isinstance(owner, ast.Name) and owner.id == "engine" and node.func.attr == "dispose":
                disposes = True
    return imports_engine, runs, disposes


def _offenders(root: Path) -> list[str]:
    out = []
    for path in sorted(root.rglob("test_*.py")):
        imports_engine, runs, disposes = _facts(_parse(path))
        if imports_engine and runs and not disposes:
            out.append(path.relative_to(root).as_posix())
    return out


def test_shared_engine_is_disposed_after_asyncio_run():
    assert _offenders(_TESTS) == [], "这些测试文件用共享引擎跑 asyncio.run 却没有 engine.dispose()，会让下一个真库用例报 Event loop is closed"


def test_scanner_sees_real_users_and_ignores_comments(tmp_path):
    """判据不空转：真实文件里确有这种用法；漏写 dispose 的样例被抓到；只在注释 / 文档字符串里写 dispose 不算。"""
    real = [p for p in _TESTS.rglob("test_*.py") if _facts(_parse(p))[:2] == (True, True)]
    assert len(real) >= 5, [p.name for p in real]
    (tmp_path / "test_bad.py").write_text(
        '"""这里提到 engine.dispose() 不算。"""\nimport asyncio\n\n\nasync def _s():\n'
        "    from app.core.database import engine  # engine.dispose() 写在注释里也不算\n"
        "    async with engine.connect():\n        pass\n\n\ndef test_x():\n    asyncio.run(_s())\n",
        encoding="utf-8")
    (tmp_path / "test_good.py").write_text(
        "import asyncio\nfrom app.core.database import engine\n\n\nasync def _s():\n"
        "    try:\n        pass\n    finally:\n        await engine.dispose()\n\n\ndef test_x():\n    asyncio.run(_s())\n",
        encoding="utf-8")
    assert _offenders(tmp_path) == ["test_bad.py"]
