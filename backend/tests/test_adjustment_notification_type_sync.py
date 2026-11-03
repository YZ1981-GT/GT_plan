"""调整分录大厅通知类型前后端同步契约（spec adjustment-hall-entry-review-closure 需求 4.5）。

新增类型必须同时：登记进后端 ALL_NOTIFICATION_TYPES；在前端 notificationTypes.ts 以字面量出现
（标签与跳转规则据此生效，缺了点通知不会跳转）。
"""
from __future__ import annotations

import re
from pathlib import Path

from app.services.notification_types import ADJ_HALL_NOTIFICATION_TYPES, ALL_NOTIFICATION_TYPES

_FRONTEND = (Path(__file__).resolve().parents[2] / "audit-platform" / "frontend" / "src" / "services"
             / "notificationTypes.ts")


def test_types_registered_in_backend_all_list():
    assert ADJ_HALL_NOTIFICATION_TYPES, "集合不应为空（防扫描空转）"
    for t in ADJ_HALL_NOTIFICATION_TYPES:
        assert t in ALL_NOTIFICATION_TYPES, f"{t} 未登记到 ALL_NOTIFICATION_TYPES"
        assert len(t) <= 50, f"{t} 超过 notifications.message_type 的 50 字长度"


def test_types_have_frontend_label_and_jump_route():
    text = _FRONTEND.read_text(encoding="utf-8")
    consts = dict(re.findall(r"^\s+(ADJ_[A-Z_]+): '([^']+)',", text, flags=re.M))
    for t in ADJ_HALL_NOTIFICATION_TYPES:
        assert f"'{t}'" in text, f"前端 notificationTypes.ts 缺少类型 {t}（前后端未同步）"
        name = next((k for k, v in consts.items() if v == t), None)
        assert name, f"前端没有 {t} 的常量"
        assert f"[NOTIFICATION_TYPES.{name}]: '" in text, f"{name} 缺中文标签"
        assert re.search(rf"\[NOTIFICATION_TYPES\.{name}\]: \(m\) =>", text), f"{name} 缺跳转规则"
