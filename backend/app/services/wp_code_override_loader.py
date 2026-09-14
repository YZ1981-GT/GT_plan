"""_WP_CODE_OVERRIDE JSON 外置加载器

启动时读取 + 验证；运行时基于 mtime 热重载。
文件损坏时保留旧缓存 + WARNING 日志。

Requirements: 6.2, 6.3, 6.4
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

_JSON_PATH: Path = Path(__file__).resolve().parent.parent / "data" / "wp_code_overrides.json"

# Module-level cache state
_cache: dict[str, str] | None = None
_mtime: float = 0.0


def load_wp_code_overrides() -> dict[str, str]:
    """加载并验证 override 映射。mtime 变化时自动重载。

    启动时首次调用：读取 JSON + validate，非法值直接 raise ValueError 阻止启动。
    运行时后续调用：检测 mtime，变化则热重载；解析失败保留旧缓存 + WARNING。

    Returns:
        扁平 {wp_code: componentType} 字典
    """
    global _cache, _mtime

    # 首次加载（启动时）
    if _cache is None:
        data = _read_json()
        validate_overrides(data)
        _mtime = os.path.getmtime(_JSON_PATH)
        _cache = data
        return _cache

    # 运行时：检查 mtime 是否变化
    try:
        current_mtime = os.path.getmtime(_JSON_PATH)
    except OSError:
        # 文件不可访问，保留旧缓存
        logger.warning("无法获取 %s 的 mtime，保留旧缓存", _JSON_PATH)
        return _cache

    if current_mtime == _mtime:
        return _cache

    # mtime 变化 → 尝试热重载（原地更新，保持外部持有的 dict 引用有效）
    try:
        data = _read_json()
        validate_overrides(data)
        _cache.clear()
        _cache.update(data)
        _mtime = current_mtime
        logger.info("已热重载 wp_code_overrides.json（%d 条）", len(_cache))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning(
            "热重载 %s 失败（%s），保留旧缓存",
            _JSON_PATH,
            exc,
        )
    except ValueError as exc:
        logger.warning(
            "热重载 %s 验证失败（%s），保留旧缓存",
            _JSON_PATH,
            exc,
        )

    return _cache


def validate_overrides(overrides: dict[str, str]) -> None:
    """验证所有 value ∈ VALID_COMPONENT_TYPES，否则 raise ValueError。

    Args:
        overrides: {wp_code: componentType} 映射字典

    Raises:
        ValueError: 存在非法 componentType 值时
    """
    from app.services.wp_classification_service import VALID_COMPONENT_TYPES

    invalid = {k: v for k, v in overrides.items() if v not in VALID_COMPONENT_TYPES}
    if invalid:
        raise ValueError(f"非法 componentType 映射: {invalid}")


def _read_json() -> dict[str, str]:
    """读取 JSON 文件并返回解析后的字典。

    Raises:
        FileNotFoundError: 文件不存在
        json.JSONDecodeError: JSON 格式错误
    """
    with open(_JSON_PATH, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"wp_code_overrides.json 根元素必须是 object，实际为 {type(data).__name__}")
    return data
