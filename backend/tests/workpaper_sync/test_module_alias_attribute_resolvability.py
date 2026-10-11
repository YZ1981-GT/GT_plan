# -*- coding: utf-8 -*-
"""守卫：`workpaper_sync` 包内「模块别名.属性」必须可解析，调用实参必须能绑定到签名。

spec: d2-online-edit-platform-closure · R1.2

═══ 为什么需要它 ═══

2026-10-10 真栈：N1/N2/N3/N5 四个 provider 写的是 `_L.attach_adapters(...)`，而
`phase5_l_cycle_common`（别名 `_L`）里**根本没有**这个名字（真名 `attach_l_entry_adapter`）。
`AttributeError` 不是 `SyncDomainError`，manifest 注册的逐 entry 隔离接不住它 ⇒ **整条注册链
中断**，186 条 entry 的每个 sync 端点 500，D2 用户点「在线编辑」毫无反应。

同轮又抓到同族的第二形态：J2/J3 调 `HC.publish_definitions_for(...)` 漏传必填的
keyword-only 参数 `contract_payload_builder` —— 名字对了，**实参绑不上签名**，同样只在运行时
炸成 `TypeError`。

两类都是「静态可判、运行时才炸」，而既有守卫都看不到：

* `test_lazy_import_resolvability` 管的是 `from app.x import Name` 的 **Name**，不管
  `alias.attr` 的 **attr**；
* 逐 provider 的单测通常 mock 掉 registry，attach 那一行从不真跑。

═══ 判据（纯 AST，不做文本匹配）═══

1. 收集每个文件里**全部**（含函数体内）把一个 `app.*` **模块**绑定到名字的 import：
   `from app.a import mod as X` / `from app.a import mod` / `import app.a.mod as X`；
2. 对 `X.attr` 的每次读取，断言目标模块真有 `attr`（或 `attr` 是可导入的子模块）；
3. 对 `X.attr(...)` 的每次调用，用 `inspect.signature(...).bind(...)` 按**实参个数与关键字名**
   试绑定（含 `*args` / `**kwargs` 展开的调用跳过 —— 静态不可知）。

别名在同一文件里还被赋值 / 当形参（遮蔽）⇒ 该别名整文件跳过，不猜。
"""
from __future__ import annotations

import ast
import importlib
import importlib.util
import inspect
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
if str(_BACKEND) not in sys.path:  # pragma: no cover - import 环境自举
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

SCAN_ROOT = _BACKEND / "app" / "services" / "workpaper_sync"


@dataclass(frozen=True)
class AliasUse:
    file: str
    line: int
    alias: str
    module: str
    attr: str
    call: ast.Call | None


def _is_module(dotted: str) -> bool:
    try:
        return importlib.util.find_spec(dotted) is not None
    except (ImportError, ValueError):
        return False


def _module_aliases(tree: ast.AST) -> tuple[dict[str, str], set[str]]:
    """`别名 → 模块全名`；第二项是**歧义**别名（同名绑到不同模块，或被遮蔽）。"""
    aliases: dict[str, str] = {}
    ambiguous: set[str] = set()

    def bind(name: str, module: str) -> None:
        prior = aliases.get(name)
        if prior is not None and prior != module:
            ambiguous.add(name)
        aliases[name] = module

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            if not node.module.startswith("app."):
                continue
            for item in node.names:
                if item.name == "*":
                    continue
                dotted = f"{node.module}.{item.name}"
                if _is_module(dotted):
                    bind(item.asname or item.name, dotted)
        elif isinstance(node, ast.Import):
            for item in node.names:
                if item.asname and item.name.startswith("app.") and _is_module(item.name):
                    bind(item.asname, item.name)
    # 遮蔽：同名还被赋值 / 当形参 / 当循环变量 ⇒ 不再能断定 `X.attr` 指的是那个模块。
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store) and node.id in aliases:
            ambiguous.add(node.id)
        elif isinstance(node, ast.arg) and node.arg in aliases:
            ambiguous.add(node.arg)
    return aliases, ambiguous


def _alias_uses(path: Path) -> list[AliasUse]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    aliases, ambiguous = _module_aliases(tree)
    if not aliases:
        return []
    calls: dict[int, ast.Call] = {
        id(node.func): node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    rel = path.relative_to(_REPO).as_posix()
    out: list[AliasUse] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.ctx, ast.Load)
            and isinstance(node.value, ast.Name)
            and node.value.id in aliases
            and node.value.id not in ambiguous
        ):
            out.append(
                AliasUse(
                    file=rel,
                    line=node.lineno,
                    alias=node.value.id,
                    module=aliases[node.value.id],
                    attr=node.attr,
                    call=calls.get(id(node)),
                )
            )
    return out


def _all_uses() -> list[AliasUse]:
    uses: list[AliasUse] = []
    for path in sorted(SCAN_ROOT.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        uses.extend(_alias_uses(path))
    return uses


def _resolve(use: AliasUse) -> tuple[bool, Any]:
    module = importlib.import_module(use.module)
    if hasattr(module, use.attr):
        return True, getattr(module, use.attr)
    # 子模块：`pkg.sub` 只在被 import 过之后才是 `pkg` 的属性；可导入即视为可解析。
    return _is_module(f"{use.module}.{use.attr}"), None


def _binding_error(target: Any, call: ast.Call) -> str | None:
    """按实参个数 + 关键字名试绑定；`*args` / `**kwargs` 展开的调用静态不可知 ⇒ 跳过。"""
    if any(isinstance(a, ast.Starred) for a in call.args) or any(
        kw.arg is None for kw in call.keywords
    ):
        return None
    if not callable(target):
        return None
    try:
        signature = inspect.signature(target)
    except (TypeError, ValueError):
        return None
    try:
        signature.bind(
            *[object() for _ in call.args],
            **{kw.arg: object() for kw in call.keywords if kw.arg is not None},
        )
    except TypeError as exc:
        return str(exc)
    return None


def _defects(uses: list[AliasUse]) -> tuple[list[str], list[str]]:
    unresolved: list[str] = []
    unbindable: list[str] = []
    for use in uses:
        ok, target = _resolve(use)
        where = f"{use.file}:{use.line} {use.alias}.{use.attr}（{use.module}）"
        if not ok:
            unresolved.append(where)
            continue
        if use.call is not None and target is not None:
            error = _binding_error(target, use.call)
            if error is not None:
                unbindable.append(f"{where}：{error}")
    return unresolved, unbindable


@pytest.fixture(scope="module")
def uses() -> list[AliasUse]:
    return _all_uses()


def test_the_scanner_sees_the_known_alias_families(uses: list[AliasUse]) -> None:
    """扫描面自检：两族真实别名（`_L` / `HC`）都在，且调用点数远非空集（防空集假绿）。"""
    seen = {(u.alias, u.module) for u in uses}
    assert ("_L", "app.services.workpaper_sync.phase5_l_cycle_common") in seen
    assert ("HC", "app.services.workpaper_sync.phase5_h_cycle_common") in seen
    assert len(uses) > 200, f"只扫到 {len(uses)} 处别名访问 —— 扫描面被掏空"
    assert sum(1 for u in uses if u.call is not None) > 100


def test_every_module_alias_attribute_resolves(uses: list[AliasUse]) -> None:
    unresolved, _ = _defects(uses)
    assert not unresolved, (
        "以下「模块别名.属性」在目标模块上不存在 —— 运行时 AttributeError，"
        "且不在注册隔离的捕获范围内：\n  " + "\n  ".join(unresolved)
    )


def test_every_module_alias_call_binds_to_its_signature(uses: list[AliasUse]) -> None:
    _, unbindable = _defects(uses)
    assert not unbindable, (
        "以下调用的实参绑不上目标签名 —— 运行时 TypeError：\n  " + "\n  ".join(unbindable)
    )


def _mutated(source: str, old: str, new: str) -> list[AliasUse]:
    assert source.count(old) >= 1, f"变异锚点不存在：{old!r}"
    tree_src = source.replace(old, new, 1)
    tmp = SCAN_ROOT / "_alias_guard_mutation_probe.py"
    tmp.write_text(tree_src, encoding="utf-8")
    try:
        return _alias_uses(tmp)
    finally:
        tmp.unlink(missing_ok=True)


def test_mutation_unknown_attribute_is_caught() -> None:
    """变异：把 N1 改回事故形态 `_L.attach_adapters(...)` ⇒ 必须判「不可解析」。"""
    src = (SCAN_ROOT / "phase5_n1_deferred_tax_assets.py").read_text(encoding="utf-8")
    uses = _mutated(src, "_L.attach_l_entry_adapter(", "_L.attach_adapters(")
    unresolved, _ = _defects(uses)
    assert any("_L.attach_adapters" in item for item in unresolved), unresolved


def test_mutation_missing_required_keyword_is_caught() -> None:
    """变异：J2 的 `HC.publish_definitions_for` 漏传 `contract_payload_builder` ⇒ 必须判「绑不上」。"""
    src = (SCAN_ROOT / "phase5_j2_defined_benefit.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    call = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "publish_definitions_for"
    )
    keyword = next(kw for kw in call.keywords if kw.arg == "contract_payload_builder")
    call_text = ast.get_source_segment(src, call)
    keyword_text = ast.get_source_segment(src, keyword)
    assert call_text and keyword_text, "J2 的 publish_definitions_for 调用取不到源码段"
    # 🔴 只在**这一个调用**的源码段内删实参：整文件首次出现的同名实参在 attach 调用里，
    #    删错位置时守卫照样红，但红在别处 ⇒ 证明不了「漏传必填关键字」这一形态被抓到。
    assert src.count(call_text) == 1, "publish_definitions_for 调用源码段不唯一"
    mutated_call = call_text.replace(keyword_text + ",", "", 1)
    assert mutated_call != call_text, "调用段内找不到 `contract_payload_builder=…,`"
    uses = _mutated(src, call_text, mutated_call)
    _, unbindable = _defects(uses)
    hits = [item for item in unbindable if "publish_definitions_for" in item]
    assert hits and "contract_payload_builder" in hits[0], unbindable
