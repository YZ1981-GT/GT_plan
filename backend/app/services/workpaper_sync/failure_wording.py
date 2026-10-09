# -*- coding: utf-8 -*-
"""同步失败码 → 中文说明的**单一解析入口**。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure

═══ 为什么需要它 ═══

2026-09-22 真栈实测：在 OnlyOffice 里往「本月金额」这类 ``amount`` 列填了一段文本，
回写走到 rematerialize 阶段失败，错误码 ``excel_materialize_editable_write_failed``
**只进了后端日志**。前端读 ``GET .../operations/{id}`` 拿到的 ``error_code`` 是 null
（post-durable 失败不写 operation 行，只写 application 事件流），于是界面上只有一句
「同步失败」—— 用户完全看不出「这一列要数字」，无从下手。

═══ 措辞为什么放后端 ═══

各引擎模块本来就各自维护了「码 → 中文」的手写词表（例如
:data:`excel_materialize.FAILURE_KINDS`，它还有「每种 kind 各真触发一次」的可达性守卫）。
前端再抄一份必然与后端漂移，而漂移的表现恰恰是**用户看到一个没人维护的旧措辞**。
因此本模块只做聚合与查表，不新增任何措辞：

* 命中登记 ⇒ 返回那条中文说明；
* 未命中 ⇒ **不编**，返回 ``None``，让调用方原样展示码本身（可诊断 > 看起来完整）。
"""

from __future__ import annotations

from typing import Mapping

__all__ = ["describe_sync_failure_code", "iter_registered_failure_codes"]


def _registries() -> tuple[Mapping[str, str], ...]:
    """按需收集各引擎模块的词表。

    延迟 import：本模块被 router 在请求路径上调用，不该在导入期把整条引擎链拉进来。
    """
    from app.services.workpaper_sync.excel_materialize import FAILURE_KINDS

    return (FAILURE_KINDS,)


def describe_sync_failure_code(code: str) -> str | None:
    """查该失败码的中文说明；未登记返回 ``None``（不编措辞）。"""
    key = str(code or "").strip()
    if not key:
        return None
    for registry in _registries():
        text = registry.get(key)
        if text:
            return str(text)
    return None


def iter_registered_failure_codes() -> tuple[str, ...]:
    """全部已登记的失败码（供守卫核对覆盖面，不让词表悄悄变空）。"""
    codes: list[str] = []
    for registry in _registries():
        codes.extend(str(k) for k in registry)
    return tuple(sorted(set(codes)))
