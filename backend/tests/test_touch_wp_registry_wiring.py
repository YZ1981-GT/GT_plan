# Feature: custom-workpaper-formula-binding — touch_wp_registry 接线守护
"""静态检查：写 parsed_data 并 commit 的路由须在 commit 后调用 touch。"""

from __future__ import annotations

import re
from pathlib import Path

ROUTERS = Path(__file__).resolve().parents[1] / "app" / "routers"

# 仅检查「wp.parsed_data =」后存在 commit 的文件
PARSED_ASSIGN = re.compile(r"wp\.parsed_data\s*=")
COMMIT = re.compile(r"await\s+db\.commit\(\)")
TOUCH = re.compile(
    r"touch_after_parsed_data_commit|touch_wp_registry"
)


def test_routers_with_parsed_data_assign_touch_after_commit():
    missing: list[str] = []
    for path in sorted(ROUTERS.glob("*.py")):
        text = path.read_text(encoding="utf-8")
        if not PARSED_ASSIGN.search(text):
            continue
        if not COMMIT.search(text):
            continue
        if not TOUCH.search(text):
            missing.append(path.name)
    assert not missing, (
        "以下路由写 parsed_data 且 commit，但未调用 touch："
        + ", ".join(missing)
    )
