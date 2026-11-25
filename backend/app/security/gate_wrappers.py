"""经注入对象到达统一 wp 门的 router 包装函数登记（coverage_guard 的伴生模块）。

某些 router 的每个 handler 第一句都是本模块内的包装函数，经注入对象（而非模块级函数）到达
平台门，coverage_guard 的「1 层间接解析」跟不过去。这里登记 ``包装函数名 → (模块, verifier)``，
只有同时满足下面两条才算接门（可伪证、不可凭注释）：

* handler 定义在登记的模块里（别的模块里同名函数不算）；
* verifier 的源码（AST）里真的调用了门函数。

2026-11-25：统一同步端点（wp_sync_router）每个 handler 第一句是 ``_guard(...)`` →
``SyncEndpointGuard.enforce`` → ``WpGateVisibilityProbe.observe`` → ``enforce_wp_gate``
（entrypoint ``workpaper.dedicated_subroute``）。只读用户的写 action 由 guard 阶段 ⑤ 按探针回报的
readonly 拒绝（403，``SyncReadonlyAccessError``）。
"""
from __future__ import annotations

import importlib
from typing import Any, Callable

VERIFIED_GATE_WRAPPERS: dict[str, tuple[str, str]] = {
    "_guard": ("app.routers.wp_sync_router", "WpGateVisibilityProbe.observe"),
}


def verified_wrapper_gate(
    module_name: str,
    qualname: str,
    *,
    source_of: Callable[[Any], str | None],
    calls_gate: Callable[[str], bool],
) -> bool:
    """True iff ``module_name.qualname`` exists and its source calls a gate (AST)."""
    try:
        obj: Any = importlib.import_module(module_name)
        for part in qualname.split("."):
            obj = getattr(obj, part)
    except Exception:  # noqa: BLE001
        return False
    src = source_of(obj)
    return src is not None and calls_gate(src)
