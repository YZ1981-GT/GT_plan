"""目录只由生成器写出 + use_catalog 不进生产路径（design §5.2 / §5.4，T07）。

AST 判定（不做文本匹配，注释与文档字符串不计）：
1. `backend/app` 与 `backend/scripts`（排除 tests）里，既有字符串常量含 `global_catalog.json`、又调用写文件 API
   （`write_text` / `write_bytes` / `os.replace` / `shutil.copy*` / `json.dump` / 以写模式 `open`）的模块集合，
   必须恰为 `{scripts/acnr/generate_catalog.py}`。
2. `use_catalog` 只供发布门禁与测试：生产代码中调用它的模块恰为 `{app/services/acnr/catalog_release.py}`。
"""
from __future__ import annotations

import ast
from functools import lru_cache
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2]
_GENERATOR = "scripts/acnr/generate_catalog.py"
_LITERAL = "global_catalog.json"


def _is_write_open(call: ast.Call) -> bool:
    if not (isinstance(call.func, ast.Name) and call.func.id == "open"):
        return False
    mode = call.args[1] if len(call.args) >= 2 else next((k.value for k in call.keywords if k.arg == "mode"), None)
    return isinstance(mode, ast.Constant) and isinstance(mode.value, str) and any(c in mode.value for c in "wax+")


def _write_targets(call: ast.Call) -> list[ast.AST]:
    """写文件调用的「写入目标」表达式：X.write_text / X.write_bytes、写模式 open(T)、os.replace / shutil.copy*(…, T)。"""
    f = call.func
    if isinstance(f, ast.Attribute) and f.attr in ("write_text", "write_bytes"):
        return [f.value]
    if _is_write_open(call):
        return call.args[:1]
    if (isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name)
            and (f.value.id, f.attr) in {("os", "replace"), ("os", "rename"), ("shutil", "copy"),
                                         ("shutil", "copyfile"), ("shutil", "copy2"), ("shutil", "move")}):
        return call.args[1:2]
    return []


def _mentions(expr: ast.AST, names: set[str], docs: set[int]) -> bool:
    for n in ast.walk(expr):
        if isinstance(n, ast.Name) and n.id in names:
            return True
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and _LITERAL in n.value and id(n) not in docs:
            return True
    return False


def _assigned(node: ast.AST) -> list[tuple[list[str], ast.AST]]:
    out = []
    for n in ast.walk(node):
        if isinstance(n, ast.Assign):
            out.append(([t.id for t in n.targets if isinstance(t, ast.Name)], n.value))
        elif isinstance(n, ast.AnnAssign) and n.value is not None and isinstance(n.target, ast.Name):
            out.append(([n.target.id], n.value))
    return out


def _propagate(seed: set[str], node: ast.AST, docs: set[int]) -> set[str]:
    """在 node 范围内把「值里提到 seed 名字或目录字面量」的赋值目标并入污点集合（到不动点）。"""
    names = set(seed)
    pairs = _assigned(node)
    while True:
        new = {t for targets, value in pairs if _mentions(value, names, docs) for t in targets} - names
        if not new:
            return names
        names |= new


@lru_cache(maxsize=1)
def _modules() -> tuple[tuple[str, ast.AST], ...]:
    out = []
    for root in (_BACKEND / "app", _BACKEND / "scripts"):
        for p in sorted(root.rglob("*.py")):
            raw = p.read_bytes()
            if b"global_catalog.json" not in raw and b"use_catalog" not in raw:
                continue
            out.append((p.relative_to(_BACKEND).as_posix(), ast.parse(raw.decode("utf-8"))))
    return tuple(out)


def _docstring_ids(tree: ast.AST) -> set[int]:
    ids = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                ids.add(id(first.value))
    return ids


def _callee(call: ast.Call) -> str:
    f = call.func
    return f.id if isinstance(f, ast.Name) else getattr(f, "attr", "")


def _writes_catalog(tree: ast.AST) -> bool:
    """写入目标由目录字面量派生（污点沿赋值传播；写参数的本地辅助函数按调用实参判定）。"""
    docs = _docstring_ids(tree)
    top = ast.Module(body=[s for s in tree.body if isinstance(s, (ast.Assign, ast.AnnAssign))], type_ignores=[])
    module_taint = _propagate(set(), top, docs)
    funcs = [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    helpers: set[str] = set()
    for fn in funcs:
        a = fn.args
        params = {x.arg for x in a.posonlyargs + a.args + a.kwonlyargs}
        local = _propagate(params, fn, set()) - (module_taint - params)
        if any(_mentions(t, local, set()) for c in ast.walk(fn) if isinstance(c, ast.Call) for t in _write_targets(c)):
            helpers.add(fn.name)
    # 模块级作用域只含函数 / 类定义之外的语句：把函数体也并进来会让不同函数里的同名局部变量互相串污点（误报）
    module_scope = ast.Module(body=[s for s in tree.body if not isinstance(
        s, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))], type_ignores=[])
    for scope in [*funcs, module_scope]:
        taint = _propagate(module_taint, scope, docs)
        for c in (n for n in ast.walk(scope) if isinstance(n, ast.Call)):
            if any(_mentions(t, taint, docs) for t in _write_targets(c)):
                return True
            args = list(c.args) + [k.value for k in c.keywords]
            if _callee(c) in helpers and any(_mentions(x, taint, docs) for x in args):
                return True
    return False


def catalog_writers(modules=None) -> set[str]:
    return {rel for rel, tree in (modules if modules is not None else _modules()) if _writes_catalog(tree)}


def use_catalog_callers(modules=None) -> set[str]:
    hits = set()
    for rel, tree in modules if modules is not None else _modules():
        for n in ast.walk(tree):
            if isinstance(n, ast.Call):
                f = n.func
                name = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", None)
                if name == "use_catalog":
                    hits.add(rel)
    return hits


def test_only_generator_writes_catalog():
    writers = catalog_writers()
    assert _GENERATOR in writers, "防空转：生成器本身必须被识别为写出方"
    assert writers == {_GENERATOR}, f"出现生成器以外的目录写入方：{sorted(writers - {_GENERATOR})}"


def test_use_catalog_not_called_in_production():
    assert use_catalog_callers() == {"app/services/acnr/catalog_release.py"}


def test_scanner_self_check_on_synthetic_modules():
    """扫描器自检：写目标由目录字面量派生 → 命中（直接写 / 经写参数的辅助函数 / 局部变量传播）；
    只读、写别的文件、文档字符串里的字面量 → 不命中。"""
    w = ast.parse("P='global_catalog.json'\nopen(P,'w').write('x')\n")
    r = ast.parse("P='global_catalog.json'\nopen(P).read()\n")
    d = ast.parse('"""写 global_catalog.json"""\nimport os\nos.replace("a","b")\n')
    o = ast.parse("P='global_catalog.json'\ndef f():\n    t = open(P).read()\n    open('labels.ts','w').write(t)\n")
    h = ast.parse("P='global_catalog.json'\ndef _w(path, t):\n    tmp = path.with_name('x')\n    open(tmp,'w')\n"
                  "def run(p=None):\n    cat = p or P\n    _w(cat, 'x')\n")
    u = ast.parse("from x import use_catalog\nwith use_catalog(1):\n    pass\n")
    # 同名局部变量不串污点：读目录的函数里叫 doc，写侧车的函数里也叫 doc（只写侧车）→ 不命中；
    # 模块级（if __name__ 块）直接写目录 → 命中
    n = ast.parse("P='global_catalog.json'\nS='side.json'\ndef _w(path, t):\n    open(path,'w')\n"
                  "def read():\n    doc = open(P).read()\n    return doc\n"
                  "def side():\n    doc = {'k': 1}\n    _w(S, doc)\n")
    m = ast.parse("P='global_catalog.json'\nif __name__ == '__main__':\n    open(P, 'w').write('x')\n")
    mods = (("w.py", w), ("r.py", r), ("d.py", d), ("o.py", o), ("h.py", h), ("n.py", n), ("m.py", m))
    assert catalog_writers(mods) == {"w.py", "h.py", "m.py"}
    assert use_catalog_callers((("u.py", u), ("r.py", r))) == {"u.py"}
