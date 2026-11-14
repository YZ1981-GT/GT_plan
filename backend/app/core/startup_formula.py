"""公式设置相关的启动注册（从 startup_registry 抽出，行数门禁）。

🔴 2026-11-14：startup_registry.py 已 1033 行（whitelist 基线 991，本就超 5%），
本轮为解 formula <-> import-export 双向依赖又加了 16 行。按仓库规矩（超限优先抽伴生
模块、不抬基线）把「公式设置传播 handler + outbox 专用派发器注册」整段搬到这里，
startup_registry 只留一行调用。与既有 ``startup_deferred.py`` 同一模式。
"""
from __future__ import annotations

import logging


def register_formula_settings_startup() -> None:
    """注册公式设置传播 handler，并**断言** outbox 专用派发器已完成注册。

    为什么必须断言：``formula_settings.outbox`` 在模块导入期向通用 outbox 注册自己的
    专用派发器（解 ``formula <-> import-export`` 双向依赖）。而 ``propagation`` 不
    import ``outbox`` —— 只写注册代码而不显式导入它，注册**永不发生**，于是
    FORMULA_CONFIG_CHANGED 的 outbox 行退回事件总线（总线吞异常），
    **行为静默退化且不报错**。这里把静默退化变成启动即失败。
    """
    from app.services.event_bus import event_bus
    from app.services.formula_settings.propagation import register_formula_settings_handlers

    # 导入即注册（formula_settings.outbox_registration 模块底部 _register()）
    import app.services.formula_settings.outbox_registration  # noqa: F401
    # 查 core 里的中立注册表（🔴 不放 import-export 的 outbox service 里：
    # 那会让 core 反向依赖 import-export，见 typed_event_dispatch 文档头）
    from app.core.typed_event_dispatch import registered_typed_event_types

    if "formula_config.changed" not in registered_typed_event_types():
        raise RuntimeError(
            "formula_settings.outbox 未完成专用派发器注册 —— "
            "FORMULA_CONFIG_CHANGED 的 outbox 行会退回事件总线（吞异常）"
        )

    register_formula_settings_handlers(event_bus)
