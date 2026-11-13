# -*- coding: utf-8 -*-
"""Task 75 守卫的「实现在哪里」解析层（从 `test_task75_published_identity_observer.py` 拆出）。

拆分只为行数门：代码逐行原样搬来，判据仍在测试模块里。这里放的是**判据要用的读法** ——
委托链（多跳 / 错误翻译外壳）、运行时对象回查、AST 片段提取。判据自己在测试模块里。

"""
from __future__ import annotations

import ast
import inspect
import pathlib
from pathlib import Path
from typing import Any

from app.services.workpaper_sync.adapters import registry as RG

#: 生产模块目录 —— 本模块是它的**单一来源**，测试模块从这里 import（禁两份常量各算一次）。
#: `parents[2]` = `backend/`（本文件在 `backend/tests/workpaper_sync/`）。
SVC = pathlib.Path(__file__).resolve().parents[2] / "app" / "services" / "workpaper_sync"
assert SVC.is_dir(), f"生产模块目录解析错了：{SVC}"

# ════════════════════════════════════════════════════════════════════════════
# 🔴 委托链解析（2026-09-27 补）
#
# 背景：本文件的四条 `TestDebtRemovedWithRealImpl` 判据写于「**每个 provider 自己**
# 委托观测器」的 D 循环范式（provider 函数体内直接 `await
# observe_published_frozen_definitions(...)` + 自己做 digest 比对 + 自己 raise）。
#
# H 循环起引入公共骨架 `phase5_h_cycle_common`（HC），provider 侧变成 3 行薄委托：
#
#     async def resolve_published_frozen_definitions(*, session, representation, contract):
#         return await HC.resolve_published_frozen_definitions(
#             IDENTITY, session=session, representation=representation, contract=contract)
#
# 于是四条单层 AST 判据对 **16 个** provider 全部假红（e1 + f2×3 + h×5 + i×6 + j1）——
# 实测那些 provider 一条都没「抄九步」，恰恰是**收敛得更彻底**（一处转发 vs N 处重复）。
#
# 🔴 **修法不是放宽，是跟着委托链走**：识别薄委托后把判据**转移到骨架函数上执行**，
# 骨架那层仍要满足全部四条（真 await 观测器 / 真 digest 比对 / 真 raise / 不返回空）。
# 变异「删掉骨架里的 await 或 digest 比对」SHALL 让 16 个 provider 一起打红。
#
# 🔴 薄委托的定义**收得很紧**（`_is_thin_delegation`）：函数体除 docstring 外
# 必须**只有一条** `return await <骨架>.<同名函数>(...)`。有人想借薄委托外壳偷偷
# 塞逻辑（比如先改 contract 再转发）会因为「不止一条语句」被判为非薄委托，
# 从而按 provider 自身的严格判据核 ⇒ 立刻打红。
# ════════════════════════════════════════════════════════════════════════════

def _is_docstring_stmt(stmt: ast.AST) -> bool:
    return (
        isinstance(stmt, ast.Expr)
        and isinstance(stmt.value, ast.Constant)
        and isinstance(stmt.value.value, str)
    )


#: 不许委托到任意模块：目标必须**现算**满足三条准入（见 `_delegation_admission`）。
#: 原先这里是一张写死的两项白名单（`HC` / `phase5_h_cycle_common`），于是
#: L 循环骨架 `phase5_l_cycle_common`（L1~L8 + N4 共 9 个 provider 走它）一出现就整组假红 ——
#: 正是本文件别处批判的「第二份清单」。改成从 provider 源码的 import 别名表现算。
_DELEGATION_PACKAGE = "app.services.workpaper_sync"
_MAX_DELEGATION_HOPS = 4


def _registered_provider_modules() -> frozenset[str]:
    """已登记的 provider 模块全集（交付台账现算）—— 委托目标不得是其中之一。"""
    return frozenset(str(row["provider_module"]) for row in RG.DELIVERED_PER_ENTRY_CONTRACTS)


def _module_alias_table(path: Path) -> dict[str, str]:
    """源文件里 `from <pkg> import <mod> as <alias>` / `import <pkg>.<mod> as <alias>` 的别名表。"""
    table: dict[str, str] = {}
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                full = f"{node.module}.{alias.name}"
                table[alias.asname or alias.name] = full
        elif isinstance(node, ast.Import):
            for alias in node.names:
                table[alias.asname or alias.name.rsplit(".", 1)[-1]] = alias.name
    return table


def _delegation_admission(target_module: str, name: str) -> Path | None:
    """委托目标准入：同包 + 真的定义同名函数 + **不是**已登记的 provider 模块。

    第三条是关键：委托到别的 entry 的 provider 模块＝复用别人的接线（`TestManifestRegistrar`
    另有一条同义判据），这里一并拒收，于是「借委托外壳蹭别人实现」不可能通过。
    """
    if not target_module.startswith(f"{_DELEGATION_PACKAGE}."):
        return None
    if target_module in _registered_provider_modules():
        return None
    target_path = SVC / f"{target_module.rsplit('.', 1)[-1]}.py"
    if not target_path.is_file():
        return None
    return target_path if _own_node(target_path, name) is not None else None


def _single_stmt(node: ast.AST) -> ast.AST | None:
    """函数/块体里剔掉 docstring 后**恰好一条**语句时返回它，否则 None。"""
    body = [s for s in getattr(node, "body", []) if not _is_docstring_stmt(s)]
    return body[0] if len(body) == 1 else None


def _forwarded_alias(stmt: ast.AST, name: str) -> str | None:
    """`return await <别名>.<name>(...)` 形态里的别名（必须转发到**同名**函数）。"""
    if not isinstance(stmt, ast.Return) or not isinstance(stmt.value, ast.Await):
        return None
    call = stmt.value.value
    if not isinstance(call, ast.Call) or not isinstance(call.func, ast.Attribute):
        return None
    if call.func.attr != name:
        return None
    owner = call.func.value
    return owner.id if isinstance(owner, ast.Name) else None


def _is_thin_delegation(node: ast.AST, name: str, path: Path) -> tuple[str, Path] | None:
    """薄委托判定，返回 `(目标模块, 目标文件)`；两种形态，都**收得很紧**：

    1. 纯转发：函数体除 docstring 外只有一条 `return await <骨架>.<同名函数>(...)`；
    2. 错误翻译转发：函数体除 docstring 外只有**一个 `try`**，`try` 体是形态 1 的那一条，
       每个 `except` 分支体**只有一条 `raise`**（不吞、不兜底 return、无 else/finally）。
       L 循环骨架就是这一形态：把 `HEntrySelectionError` 翻译成 `LEntrySelectionError`。

    任何「借委托外壳塞逻辑」（多语句、改 contract 再转发、handler 里 return 兜底）都不匹配，
    于是按 provider 自身的严格判据核 ⇒ 立刻打红。
    """
    stmt = _single_stmt(node)
    if stmt is None:
        return None
    if isinstance(stmt, ast.Try):
        if stmt.orelse or stmt.finalbody:
            return None
        inner = _single_stmt(stmt)
        if inner is None:
            return None
        for handler in stmt.handlers:
            if len(handler.body) != 1 or not isinstance(handler.body[0], ast.Raise):
                return None
        stmt = inner
    alias = _forwarded_alias(stmt, name)
    if alias is None:
        return None
    target_module = _module_alias_table(path).get(alias)
    if target_module is None:
        return None
    target_path = _delegation_admission(target_module, name)
    return (target_module, target_path) if target_path is not None else None


def _own_node(path: Path, name: str) -> ast.AST | None:
    """顶层同名函数的 AST 节点；没有就返回 None（不抛）。"""
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    return None


def function_node(path: Path, name: str) -> ast.AST:
    """按名字取顶层函数/方法的 AST 节点（**不**用字符窗口截函数体）。"""
    node = _own_node(path, name)
    if node is None:
        raise AssertionError(f"{path.name} 里找不到函数 {name!r} ⇒ 判据无分母")
    return node


def _runtime_impl_node(module_path: str, name: str) -> tuple[ast.AST, Path]:
    """provider 模块里是**转发赋值**（`X = _ns.X` / 工厂闭包）时，按运行期对象定位实现。

    🔴 为什么必须有这一支：D2 / D3 / D5 / D6 / D7 与 M 循环 5 条 provider 的这个函数不是
    `def`，而是 `phase5_entry_orchestration.build_orchestration(...)` 为**本 entry** 造的闭包，
    由 provider 模块转发出来。只看 provider 文件的 AST 会得到「找不到函数」⇒ 11 条 entry 的
    四条判据全部没有分母（本轮实测 56 条失败就是这么来的）。
    用 `inspect` 拿到实现所在文件与首行，再回到**那一层**跑同样严格的四条判据。
    """
    module = __import__(module_path, fromlist=["x"])
    fn = getattr(module, name, None)
    assert fn is not None and callable(fn), f"{module_path} 没有可调用的 {name!r} ⇒ 判据无分母"
    impl_file = inspect.getsourcefile(fn)
    assert impl_file, f"{module_path}.{name} 取不到源文件"
    impl_path = Path(impl_file)
    first_line = fn.__code__.co_firstlineno
    for node in ast.walk(ast.parse(impl_path.read_text(encoding="utf-8"))):
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == name
            and node.lineno <= first_line <= node.end_lineno
        ):
            return node, impl_path
    raise AssertionError(
        f"{module_path}.{name} 的运行期实现在 {impl_path.name}:{first_line}，但该处没有同名函数定义"
    )


def implementing_node(path: Path, name: str, module_path: str | None = None) -> tuple[ast.AST, Path, bool]:
    """返回真正承载实现的 `(函数节点, 所在文件, 是否经委托)`。

    三种形态都走到**承载实现的那一层**再跑判据：provider 自己实现 → 原节点；薄委托（含错误
    翻译、可多跳）→ 骨架里的同名函数；转发赋值 / 工厂闭包 → 运行期对象所在的那个函数。
    """
    node = _own_node(path, name)
    if node is None:
        # provider 文件里没有自有定义 ⇒ 只能按运行期对象定位实现。module_path 缺省由路径推出
        # （provider 一律住在 `app/services/workpaper_sync/` 下），免得调用点漏传就变成假红。
        resolved = module_path or f"{_DELEGATION_PACKAGE}.{path.stem}"
        impl_node, impl_path = _runtime_impl_node(resolved, name)
        return impl_node, impl_path, True
    delegated = False
    current_path = path
    seen = {current_path}
    for _ in range(_MAX_DELEGATION_HOPS):
        hop = _is_thin_delegation(node, name, current_path)
        if hop is None:
            return node, current_path, delegated
        _, target_path = hop
        assert target_path not in seen, f"委托链成环：{target_path.name}"
        seen.add(target_path)
        node, current_path, delegated = function_node(target_path, name), target_path, True
    raise AssertionError(f"{path.name} 的委托链超过 {_MAX_DELEGATION_HOPS} 跳 ⇒ 判据无法定位实现")



def _captured_entry_ids(fn: Any) -> frozenset[str]:
    """可调用对象闭包里捕获到的 entry_id 集合（工厂闭包的「绑了哪条 entry」证据）。

    只读闭包 cell 与 `__globals__['ENTRY_ID']`，不改任何状态；取不到就返回空集合
    （调用方据此判定「不是绑本 entry」⇒ 打红，而不是默默放过）。
    """
    out: set[str] = set()
    closure = getattr(fn, "__closure__", None) or ()
    names = getattr(getattr(fn, "__code__", None), "co_freevars", ()) or ()
    for name, cell in zip(names, closure):
        del name
        try:
            value = cell.cell_contents
        except ValueError:  # pragma: no cover - 未赋值的 cell
            continue
        if isinstance(value, str) and value.startswith(("xlsx/", "docx/")):
            out.add(value)
        entry_id = getattr(value, "entry_id", None)
        if isinstance(entry_id, str):
            out.add(entry_id)
        for attr in ("config", "cfg"):
            nested = getattr(getattr(value, attr, None), "entry_id", None)
            if isinstance(nested, str):
                out.add(nested)
    module_level = getattr(fn, "__globals__", {}).get("ENTRY_ID")
    if isinstance(module_level, str):
        out.add(module_level)
    return frozenset(out)


def _declared_pilot_class(row: Any) -> str:
    """provider 模块自己声明的 pilot_class（台账那一列的唯一真源）。

    优先级与 provider 拼契约载荷时一致：`CONFIG.pilot_class`（逐 entry 配置，M/K 循环用）
    → `PILOT_CLASS` → `PHASE5_WAVE`（循环级 wave 常量）。三个都没有就是缺声明 ⇒ 打红。
    """
    module = __import__(str(row["provider_module"]), fromlist=["x"])
    config = getattr(module, "CONFIG", None)
    value = getattr(config, "pilot_class", None) if config is not None else None
    if isinstance(value, str) and value:
        return value
    for name in ("PILOT_CLASS", "PHASE5_WAVE"):
        value = getattr(module, name, None)
        if isinstance(value, str) and value:
            return value
    raise AssertionError(
        f"{row['provider_module']} 没有声明 pilot_class（CONFIG.pilot_class / PILOT_CLASS / "
        "PHASE5_WAVE 都没有）⇒ 台账那一列没有真源可比"
    )

def imported_module_paths(path: Path) -> set[str]:
    """源文件里**真正 import 的**模块路径（含函数内局部 import）。

    🔴 用 AST 而不是子串：模块 docstring 里写「本模块不 import `adapters.registry`」时，
    子串判据会把那句**说明**当违规 ⇒ 假红（实测踩到）。
    """
    out: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            out.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            out.add(node.module)
            out.update(f"{node.module}.{alias.name}" for alias in node.names)
    return out


def referenced_names(path: Path) -> set[str]:
    """源文件里被**代码**引用到的标识符（`Name` / `Attribute` 末段），不含注释与 docstring。"""
    out: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Name):
            out.add(node.id)
        elif isinstance(node, ast.Attribute):
            out.add(node.attr)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            out.update(alias.asname or alias.name.rsplit(".", 1)[-1] for alias in node.names)
    return out


def _own_code_only_segment(path: Path, function: str) -> str:
    """provider **自有**函数体（剔 docstring）；provider 侧是转发赋值时返回空串。

    「有没有在 pilot 侧抄九步」只对自有函数体成立：转发赋值的 provider 文件里连函数体都没有，
    天然不可能抄 —— 返回空串不是放宽，而是这条判据在该形态下的真实分母（另三条仍在实现层跑）。
    """
    return code_only_segment(path, function) if _own_node(path, function) else ""


def code_only_segment(path: Path, function: str) -> str:
    """函数体源码，**剔掉 docstring**。

    🔴 判「pilot 侧有没有抄 loader 的九步」时必须剔 docstring：本轮的新 docstring 里正当地
    提到了 `ExcelEntryDefinitionLoader.load()`（解释欠账从何而来），带着 docstring 比对会
    把说明文字当违规 ⇒ 假红（实测踩到 4 条）。
    """
    source = path.read_text(encoding="utf-8")
    node = function_node(path, function)
    body = list(getattr(node, "body", []))
    if (
        body
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
        and isinstance(body[0].value.value, str)
    ):
        body = body[1:]
    assert body, f"{path.name}::{function} 剔掉 docstring 后函数体为空 ⇒ 空壳"
    return "\n".join((ast.get_source_segment(source, stmt) or "") for stmt in body)


def except_handler_types(path: Path) -> list[str]:
    """源文件里每个 `except` 子句捕获的类型名（裸 except 记 `<bare>`）。"""
    out: list[str] = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if not isinstance(node, ast.ExceptHandler):
            continue
        if node.type is None:
            out.append("<bare>")
            continue
        targets = node.type.elts if isinstance(node.type, ast.Tuple) else [node.type]
        for target in targets:
            if isinstance(target, ast.Name):
                out.append(target.id)
            elif isinstance(target, ast.Attribute):
                out.append(target.attr)
            else:
                out.append(ast.dump(target))
    return out


def literal_from_source(path: Path, function: str, key: str) -> str:
    """从某函数体里取 `"{key}": "<字面量>"` 的那个字面量（AST，不用正则）。"""
    node = function_node(path, function)
    for inner in ast.walk(node):
        if not isinstance(inner, ast.Dict):
            continue
        for k, v in zip(inner.keys, inner.values):
            if isinstance(k, ast.Constant) and k.value == key and isinstance(v, ast.Constant):
                return str(v.value)
    raise AssertionError(f"{path.name}::{function} 里取不到 {key!r} 的字面量 ⇒ 判据无分母")
