"""事件处理器 — 核心基础设施

工厂函数和批量注册工具。
"""
from app.services.event_handlers._impl import (
    _make_handler,
    _make_tb_handler,
    subscribe_many,
)

__all__ = ["_make_handler", "_make_tb_handler", "subscribe_many"]
