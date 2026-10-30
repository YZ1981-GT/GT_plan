"""provider 的生产函数是不是「本 entry 自己的那一份」：两种合法形态共用一个判据。

① provider 模块自己定义（`__module__` 就是 provider 模块）；
② 工厂 `phase5_entry_orchestration.build_orchestration(cfg)` 为本 entry 造的闭包：`__module__` 是工厂
   模块，判据落到闭包捕获的 `cfg`（entry_id / adapter_id 必须是本 entry 的）。

2026-10-02 起 D3/D5/D6/D7/K/M/pilot_d2_* 改由工厂造，按 `__module__` 判的守卫对它们恒红；那不是
「复用了别人的接线」，是判据没认出工厂形态（spec writeback-followup-issue-closure R12）。
"""
from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

FACTORY_FN = "build_orchestration"
FACTORY_PY = (
    Path(__file__).resolve().parents[2]
    / "app"
    / "services"
    / "workpaper_sync"
    / "phase5_entry_orchestration.py"
)


def is_factory_closure(fn: Any, name: str) -> bool:
    """`fn` 是工厂 `build_orchestration` 里直接定义的嵌套函数 `name`（qualname + 源文件双判）。"""
    code = getattr(fn, "__code__", None)
    return (
        code is not None
        and getattr(fn, "__qualname__", "") == f"{FACTORY_FN}.<locals>.{name}"
        and Path(code.co_filename).resolve() == FACTORY_PY.resolve()
    )


def import_aliases(path: Path) -> dict[str, str]:
    """文件里 `from app.services.workpaper_sync import X as Y` 的 `Y → X`（委托目标按 import 现解析）。"""
    out: dict[str, str] = {}
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom) and node.module == "app.services.workpaper_sync":
            for alias in node.names:
                out[alias.asname or alias.name] = alias.name
    return out


def closure_cell(fn: Any, name: str) -> Any:
    """闭包自由变量 `name` 的当前值（不存在就打红：说明这个闭包根本不引用它）。"""
    cells = dict(zip(fn.__code__.co_freevars, fn.__closure__ or ()))
    assert name in cells, f"{getattr(fn, '__qualname__', fn)} 的闭包不引用 {name}"
    return cells[name].cell_contents


def attach_owner_problem(
    attach: Any, *, provider_module: str, entry_id: str, adapter_id: str
) -> str | None:
    """`attach` 属于本 entry 时返回 None，否则返回原因（供断言消息用）。"""
    if getattr(attach, "__module__", None) == provider_module:
        return None
    if not is_factory_closure(attach, "attach_adapters"):
        return (
            f"attach 来自 {getattr(attach, '__module__', None)}"
            f"（{getattr(attach, '__qualname__', attach)!r}）⇒ 复用了别人的接线"
        )
    cfg = closure_cell(attach, "cfg")
    if (cfg.entry_id, cfg.adapter_id) != (entry_id, adapter_id):
        return f"工厂 attach 捕获的是 {cfg.entry_id} / {cfg.adapter_id} ⇒ 复用了别人的接线"
    return None
