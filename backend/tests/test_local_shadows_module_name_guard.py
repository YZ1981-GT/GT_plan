"""全部 ``app`` 源码：函数里不许「先读模块级名字、后又给同名局部赋值」—— 读的那一行恒抛 UnboundLocalError。

为什么需要（spec excel-style-table-editing 5.4 触类旁通）：Python 里函数体只要给某个名字赋过值（含函数内
``import x as sa`` / 注解赋值 ``sa: dict = ...``），这个名字在**整个函数**里都是局部变量；赋值之前读它不会去拿
模块级的同名对象，而是直接 UnboundLocalError。现场三处，全是「想用模块级的，却在函数后半段又导入 / 赋值了一次」：

- ``routers/reports.py::update_report_cell`` —— 新建行分支写了 ``sa: dict | None = None`` ⇒ 开头 ``sa.select`` 恒抛，
  报表格内编辑（权益表 / 减值表）自 2026-06-12 起每次 500；
- ``services/wp_download_service.py::WpUploadService.upload_file`` —— 云同步分支里 ``import sqlalchemy as sa`` ⇒
  开头 ``sa.select`` 恒抛，底稿离线上传（正式主链路）自 2026-04-18 起每次失败；
- ``api/wopi.py::wopi_put_file`` —— POC 分支里 ``from app.core.config import settings`` ⇒ 写授权被拒那支读
  ``settings`` 恒抛。

``test_function_global_names_ratchet.py`` 管的是「引用了没定义的全局名」（NameError），本守卫管「本地名遮住了模块名」，
两者互补。判据只看行号先后（读出现在函数里第一次赋值之前），不做控制流：赋值在条件分支里、读在分支外照样算。
"""

from __future__ import annotations

import ast
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app"


def _module_names(tree: ast.Module) -> set[str]:
    out: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            out.update((a.asname or a.name).split(".")[0] for a in node.names)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out.add(node.name)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            out.update(t.id for t in targets if isinstance(t, ast.Name))
    return out


_NESTED = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda,
           ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)


def _own_nodes(fn: ast.AST):
    """函数自身作用域里的节点（不进嵌套函数 / 类 / lambda / 推导式：它们有自己的作用域）。"""
    stack = list(ast.iter_child_nodes(fn))
    while stack:
        n = stack.pop()
        yield n
        if not isinstance(n, _NESTED):
            stack.extend(ast.iter_child_nodes(n))


def _violations(src: str, rel: str) -> list[str]:
    tree = ast.parse(src)
    module = _module_names(tree)
    out: list[str] = []
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        a = fn.args
        params = {x.arg for x in a.args + a.kwonlyargs + a.posonlyargs}
        params.update(x.arg for x in (a.vararg, a.kwarg) if x)
        stores: dict[str, int] = {}
        loads: dict[str, int] = {}
        declared: set[str] = set()
        for n in _own_nodes(fn):
            if isinstance(n, (ast.Global, ast.Nonlocal)):
                declared.update(n.names)
            elif isinstance(n, ast.Name):
                book = stores if isinstance(n.ctx, (ast.Store, ast.Del)) else loads
                book[n.id] = min(book.get(n.id, n.lineno), n.lineno)
            elif isinstance(n, (ast.Import, ast.ImportFrom)):
                for alias in n.names:
                    name = (alias.asname or alias.name).split(".")[0]
                    stores[name] = min(stores.get(name, n.lineno), n.lineno)
        for name, first_store in stores.items():
            if name in params or name in declared or name not in module:
                continue
            first_load = loads.get(name)
            if first_load is not None and first_load < first_store:
                out.append(f"{rel}:{first_load} {fn.name}() 先读模块级 {name}，第 {first_store} 行又在函数里赋值 ⇒ UnboundLocalError")
    return out


def _scan() -> tuple[list[str], int]:
    found: list[str] = []
    files = 0
    for p in sorted(APP.rglob("*.py")):
        files += 1
        found.extend(_violations(p.read_text(encoding="utf-8-sig"), p.relative_to(APP.parent).as_posix()))
    return found, files


def test_no_function_reads_module_name_before_shadowing_it() -> None:
    found, files = _scan()
    assert files > 500, f"扫描面异常（只扫到 {files} 个文件）"
    assert not found, (
        "函数里先读模块级名字、后又给同名局部赋值（函数内 import / 赋值让它整函数变成局部变量，先读恒抛 "
        "UnboundLocalError）—— 删掉函数内的重复导入或给局部变量改名：\n  " + "\n  ".join(found)
    )


def test_detector_flags_the_three_real_shapes() -> None:
    """变异：现场三种写法（后面 import as、注解赋值、from-import）都必须报出；读在赋值之后、嵌套函数里的不报。"""
    src = (
        "import sqlalchemy as sa\n"
        "from app.core.config import settings\n"
        "async def upload(db):\n"
        "    r = await db.execute(sa.select(1))\n"
        "    if r:\n"
        "        import sqlalchemy as sa\n"
        "def edit(db):\n"
        "    db.execute(sa.select(2))\n"
        "    sa: dict | None = None\n"
        "def put(x):\n"
        "    if x:\n"
        "        return settings.FLAG\n"
        "    from app.core.config import settings\n"
        "def fine():\n"
        "    import sqlalchemy as sa\n"
        "    return sa.select(3)\n"
        "def nested():\n"
        "    def inner():\n"
        "        sa = 1\n"
        "        return sa\n"
        "    return sa.select(inner())\n"
    )
    found = _violations(src, "probe.py")
    assert [f.split(" ")[1] for f in found] == ["upload()", "edit()", "put()"], found
