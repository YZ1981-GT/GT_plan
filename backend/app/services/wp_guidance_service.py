"""
底稿编制说明（guidance）加载服务。

从 backend/data/wp_guidance/ 目录加载底稿对应的编制说明 JSON。
guidance 数据是静态的（随模板版本更新），用 LRU 缓存 + mtime 热重载。
"""
from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)

_GUIDANCE_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "wp_guidance"

# wp_code → guidance JSON 文件路径 + mtime（用于热重载检测）
_guidance_cache: dict[str, tuple[float, dict]] = {}


def _scan_guidance_files() -> dict[str, Path]:
    """扫描 wp_guidance 目录，建立 wp_code → 文件路径映射。"""
    mapping: dict[str, Path] = {}
    if not _GUIDANCE_DIR.exists():
        return mapping
    for f in _GUIDANCE_DIR.glob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            for code in data.get("wp_codes", []):
                mapping[code] = f
        except Exception as e:
            logger.warning("解析 guidance 文件失败 %s: %s", f.name, e)
    return mapping


@lru_cache(maxsize=1)
def _get_wp_code_to_file_map() -> dict[str, Path]:
    """缓存 wp_code → 文件路径映射（进程级，重启刷新）。"""
    return _scan_guidance_files()


def get_guidance_for_wp(wp_code: str) -> dict | None:
    """获取指定 wp_code 的 guidance 数据。支持 mtime 热重载。

    Returns:
        guidance JSON dict，无对应数据返回 None。
    """
    file_map = _get_wp_code_to_file_map()
    file_path = file_map.get(wp_code)
    if not file_path or not file_path.exists():
        return None

    current_mtime = file_path.stat().st_mtime
    cached = _guidance_cache.get(wp_code)
    if cached and cached[0] == current_mtime:
        return cached[1]

    # 重新加载
    try:
        data = json.loads(file_path.read_text(encoding="utf-8"))
        _guidance_cache[wp_code] = (current_mtime, data)
        return data
    except Exception as e:
        logger.error("加载 guidance 文件失败 %s: %s", file_path.name, e, exc_info=True)
        return None


def invalidate_guidance_cache() -> None:
    """清除缓存（测试用）。"""
    _guidance_cache.clear()
    _get_wp_code_to_file_map.cache_clear()
