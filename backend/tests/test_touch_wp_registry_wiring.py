# Feature: ACNR — touch_wp_registry 已由 ACNR events.on_workpaper_saved 统一处理
"""
历史遗留静态检查（R23.2 收口后简化）：
确认各 router 不再自行调用 touch_wp_registry（统一由 EventBus handler 驱动）。
"""

from __future__ import annotations

import re
from pathlib import Path

ROUTERS = Path(__file__).resolve().parents[1] / "app" / "routers"

# touch_wp_registry 直接调用（非注释）
TOUCH_CALL = re.compile(r"^\s*(?:await\s+)?touch_wp_registry\(")


def test_no_router_directly_calls_touch_wp_registry():
    """R23.2: 各 router 不应直接调用 touch_wp_registry（已统一由 ACNR EventBus handler 处理）。"""
    violators: list[str] = []
    for path in sorted(ROUTERS.glob("*.py")):
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if TOUCH_CALL.search(line):
                violators.append(f"{path.name}:{i}")
    assert not violators, (
        "以下路由仍直接调用 touch_wp_registry（应由 ACNR 统一失效）："
        + ", ".join(violators)
    )
