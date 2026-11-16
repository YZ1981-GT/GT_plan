"""按事件类型分派的**专用派发器注册表**（中立位置，属于 core）。

🔴 2026-11-14 为什么住在 core 而不是 ``import_event_outbox_service``：
注册表原先放在 import-export 域的 outbox service 里，于是 ``core/startup_formula.py``
（启动编排，属 core）为了查「注册是否发生」必须 import 它 ⇒ 出现
``core -> import-export`` 的反向依赖（domain-boundary 的 forbidden_edge）。

事件派发注册表是**跨域中立契约**：import-export 的 outbox 用它派发、formula 用它注册、
core 的启动编排用它自检。三方都要用，放在任一业务域里都必然制造反向依赖 ——
正确位置是 ``app/core``（所有域都可依赖）。

语义（与原先完全一致）：
  * outbox 的 ``_deliver`` 查表：命中 ⇒ 调该域的专用派发器；未命中 ⇒ 事件总线
  * 各域在自己的模块导入期 ``register_typed_deliverer(event_type, fn)``
  * 启动编排用 ``registered_typed_event_types()`` 断言注册确实发生
"""
from __future__ import annotations

from typing import Any

#: event_type 字符串 -> 派发器 ``async (db, item, payload) -> None``
_TYPED_DELIVERERS: dict[str, Any] = {}


def register_typed_deliverer(event_type: str, deliverer: Any) -> None:
    """注册某事件类型的专用派发器（覆盖事件总线默认派发）。

    ``deliverer`` 签名：``async (db, item: ImportEventOutbox, payload: EventPayload) -> None``。
    各业务域在自己的模块导入期调用本函数（见 formula_settings/outbox_registration.py）。
    """
    _TYPED_DELIVERERS[str(event_type)] = deliverer


def get_typed_deliverer(event_type: str) -> Any:
    """查专用派发器；未注册返回 None（调用方退回事件总线）。"""
    return _TYPED_DELIVERERS.get(str(event_type))


def registered_typed_event_types() -> tuple[str, ...]:
    """已注册专用派发器的事件类型（供启动自检 / 守卫断言「注册确实发生」）。"""
    return tuple(sorted(_TYPED_DELIVERERS))
