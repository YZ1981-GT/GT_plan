"""底稿渲染 schema 服务 — 配置驱动渲染

从 backend/data/wp_render_schema/{wp_code}.yaml 加载渲染 schema，
支持模板级 fallback（如 B-template.yaml 覆盖所有 B 类底稿）和项目级覆盖合并。

Requirements: 2.2 原则 2（配置驱动）
"""

from __future__ import annotations

import copy
import logging
from pathlib import Path
from uuid import UUID

import yaml

logger = logging.getLogger(__name__)

# schema 文件根目录
_SCHEMA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "wp_render_schema"


class WpRenderSchemaService:
    """底稿渲染 schema 服务 — 配置驱动渲染"""

    def __init__(self) -> None:
        self._cache: dict[str, dict] = {}

    def load_schema(
        self,
        wp_code: str,
        template_version_id: UUID | None = None,
    ) -> dict:
        """Load render schema YAML for a given wp_code.

        查找顺序：
        1. backend/data/wp_render_schema/{wp_code}.yaml（精确匹配）
        2. backend/data/wp_render_schema/{prefix}-template.yaml（前缀 fallback）
           例如 wp_code='B12' → 尝试 'B-template.yaml'

        template_version_id 用于缓存键隔离（未来多版本场景），
        当前版本下同一 wp_code 只加载一次。

        Returns:
            解析后的 YAML dict

        Raises:
            FileNotFoundError: 精确匹配和 fallback 均未找到
        """
        cache_key = self._build_cache_key(wp_code, template_version_id)

        if cache_key in self._cache:
            return self._cache[cache_key]

        schema_path = self._resolve_schema_path(wp_code)
        if schema_path is None:
            raise FileNotFoundError(
                f"Render schema not found for wp_code='{wp_code}'. "
                f"Searched: {_SCHEMA_DIR / f'{wp_code}.yaml'} and "
                f"{_SCHEMA_DIR / f'{self._extract_prefix(wp_code)}-template.yaml'}"
            )

        with open(schema_path, "r", encoding="utf-8") as f:
            schema = yaml.safe_load(f)

        if schema is None:
            schema = {}

        self._cache[cache_key] = schema
        logger.debug("Loaded render schema: %s (from %s)", wp_code, schema_path)
        return schema

    def merge_with_override(
        self,
        schema: dict,
        project_override: dict | None,
    ) -> dict:
        """Merge project-level schema override into base schema.

        project_override 来自 project_workpaper_sheet_override.schema_override JSONB。
        深度合并：override 中的 key 在相同路径下覆盖 base 中的 key。

        Args:
            schema: 基础 schema（从 YAML 加载）
            project_override: 项目级覆盖 dict，可为 None

        Returns:
            合并后的新 dict（不修改原 schema）
        """
        if not project_override:
            return schema

        merged = copy.deepcopy(schema)
        _deep_merge(merged, project_override)
        return merged

    def invalidate_cache(self, wp_code: str | None = None) -> None:
        """清除缓存（用于热更新场景）

        Args:
            wp_code: 指定清除某个 wp_code 的缓存；None 则清除全部
        """
        if wp_code is None:
            self._cache.clear()
            logger.debug("Cleared all render schema cache")
        else:
            keys_to_remove = [k for k in self._cache if k.startswith(f"{wp_code}:")]
            for k in keys_to_remove:
                del self._cache[k]
            logger.debug("Cleared render schema cache for wp_code=%s", wp_code)

    # ─── Private helpers ─────────────────────────────────────────────────

    def _resolve_schema_path(self, wp_code: str) -> Path | None:
        """按优先级查找 schema 文件路径"""
        # 1. 精确匹配
        exact = _SCHEMA_DIR / f"{wp_code}.yaml"
        if exact.is_file():
            return exact

        # 2. 前缀 fallback（如 B-template.yaml）
        prefix = self._extract_prefix(wp_code)
        if prefix:
            fallback = _SCHEMA_DIR / f"{prefix}-template.yaml"
            if fallback.is_file():
                return fallback

        return None

    @staticmethod
    def _extract_prefix(wp_code: str) -> str:
        """提取 wp_code 的字母前缀（如 'D2A' → 'D', 'B12' → 'B'）"""
        prefix = ""
        for ch in wp_code:
            if ch.isalpha():
                prefix += ch
            else:
                break
        return prefix

    @staticmethod
    def _build_cache_key(wp_code: str, template_version_id: UUID | None) -> str:
        """构建缓存键"""
        version_part = str(template_version_id) if template_version_id else "default"
        return f"{wp_code}:{version_part}"


def _deep_merge(base: dict, override: dict) -> None:
    """递归深度合并 override 到 base（原地修改 base）

    规则：
    - override 中的 dict 值递归合并到 base 对应 key
    - override 中的非 dict 值直接覆盖 base 对应 key
    - override 中新增的 key 直接添加到 base
    """
    for key, value in override.items():
        if (
            key in base
            and isinstance(base[key], dict)
            and isinstance(value, dict)
        ):
            _deep_merge(base[key], value)
        else:
            base[key] = copy.deepcopy(value)
