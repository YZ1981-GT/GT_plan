# Feature: procedure-delegation-notification — Task 11 通知类型前后端同步
"""程序行任务通知类型前后端同步契约（Req 10.8 / 5.6 / 8.7）。

跨轮约束：新增通知类型必须同步 backend notification_types.py + 前端 notificationTypes.ts。
本契约校验 PROCEDURE_TASK_NOTIFICATION_TYPES 全部：
  1) 已登记进 backend ALL_NOTIFICATION_TYPES；
  2) 在前端 notificationTypes.ts 出现（字面量字符串），保证 metadata 驱动跳转前后端一致。
"""
from __future__ import annotations

from pathlib import Path

from app.services.notification_types import (
    ALL_NOTIFICATION_TYPES,
    PROCEDURE_TASK_NOTIFICATION_TYPES,
)

_FRONTEND_TYPES = (
    Path(__file__).resolve().parents[3]
    / "audit-platform"
    / "frontend"
    / "src"
    / "services"
    / "notificationTypes.ts"
)


def test_procedure_types_registered_in_backend_all_list():
    for t in PROCEDURE_TASK_NOTIFICATION_TYPES:
        assert t in ALL_NOTIFICATION_TYPES, f"{t} 未登记到 ALL_NOTIFICATION_TYPES"


def test_procedure_types_present_in_frontend_dictionary():
    assert _FRONTEND_TYPES.exists(), f"前端类型字典缺失: {_FRONTEND_TYPES}"
    text = _FRONTEND_TYPES.read_text(encoding="utf-8")
    for t in PROCEDURE_TASK_NOTIFICATION_TYPES:
        assert f"'{t}'" in text, f"前端 notificationTypes.ts 缺少类型 {t}（前后端未同步）"
