"""底稿准则说明/编制说明服务 — 按 wp_code 加载 guidance JSON

统一为所有需要 guidance 的底稿（A3-8/A4-1/A5-3/A5-4 等）提供
准则引用和编制说明数据，供前端侧栏面板展示。
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)

_GUIDANCE_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "wp_guidance"


@lru_cache(maxsize=32)
def get_wp_guidance(wp_code: str) -> dict | None:
    """按 wp_code 加载准则说明 JSON。

    Returns:
        guidance dict with {wp_code, title, sections: [{title, items}]}
        或 None 如果不存在对应文件
    """
    path = _GUIDANCE_DIR / f"{wp_code}.json"
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning("加载 guidance 失败 wp_code=%s: %s", wp_code, e)
        return None


def list_available_guidance() -> list[str]:
    """列出所有有 guidance 数据的 wp_code。"""
    if not _GUIDANCE_DIR.exists():
        return []
    return [f.stem for f in _GUIDANCE_DIR.glob("*.json")]
