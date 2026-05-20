"""运行时 Label 解析器 — 三层优先级

语义 label → 物理坐标 (row, col)

三层优先级：
1. address_label_overrides.json overrides（用户手动指定）
2. address_label_overrides.json header_rules（用户指定 data_start_row）
3. 启发式全 sheet 扫描（找"数据区域首行"）

缓存：Redis key = resolve:{project_id}:{wp_code}:{sheet_name}:{label}
TTL = 24h，底稿保存时清除该 wp 缓存
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
OVERRIDES_PATH = DATA_DIR / "address_label_overrides.json"

# Cache TTL in seconds (24 hours)
CACHE_TTL = 86400


class LinkageLabelResolver:
    """语义 label → 物理坐标 (row, col) 解析器。

    三层优先级：
    1. overrides（用户手动指定 label→row+col）
    2. header_rules（用户指定 data_start_row/col_header_row）
    3. 启发式全 sheet 扫描（找"数据区域首行"）
    """

    def __init__(self, redis_client: Any | None = None):
        self._redis = redis_client
        self._overrides: list[dict[str, Any]] = []
        self._header_rules: list[dict[str, Any]] = []
        self._load_overrides()

    def _load_overrides(self) -> None:
        """加载 address_label_overrides.json。"""
        if not OVERRIDES_PATH.exists():
            self._overrides = []
            self._header_rules = []
            return

        try:
            data = json.loads(OVERRIDES_PATH.read_text(encoding="utf-8"))
            self._overrides = data.get("overrides", [])
            self._header_rules = data.get("header_rules", [])
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to load address_label_overrides.json: %s", e)
            self._overrides = []
            self._header_rules = []

    async def resolve(
        self,
        project_id: str,
        wp_code: str,
        sheet_name: str,
        label: str,
    ) -> dict[str, Any] | None:
        """解析语义 label 到物理坐标。

        Args:
            project_id: 项目 ID
            wp_code: 底稿编码
            sheet_name: Sheet 名称
            label: 语义标签

        Returns:
            {"row": int, "col": int, "source": "override"|"header_rule"|"heuristic"}
            or None if not resolved
        """
        # Check cache first
        cache_key = f"resolve:{project_id}:{wp_code}:{sheet_name}:{label}"
        cached = await self._get_cache(cache_key)
        if cached is not None:
            return cached

        # Layer 1: User overrides
        result = self._resolve_from_overrides(wp_code, sheet_name, label)
        if result:
            await self._set_cache(cache_key, result)
            return result

        # Layer 2: Header rules
        result = self._resolve_from_header_rules(wp_code, sheet_name, label)
        if result:
            await self._set_cache(cache_key, result)
            return result

        # Layer 3: Heuristic scan (placeholder — requires xlsx access)
        result = self._resolve_heuristic(wp_code, sheet_name, label)
        if result:
            await self._set_cache(cache_key, result)
            return result

        return None

    def _resolve_from_overrides(
        self, wp_code: str, sheet_name: str, label: str
    ) -> dict[str, Any] | None:
        """Layer 1: 从 overrides 精确匹配。"""
        for override in self._overrides:
            if (
                override.get("wp_code") == wp_code
                and override.get("sheet_name") == sheet_name
                and override.get("label") == label
            ):
                return {
                    "row": override.get("row"),
                    "col": override.get("col"),
                    "source": "override",
                }
        return None

    def _resolve_from_header_rules(
        self, wp_code: str, sheet_name: str, label: str
    ) -> dict[str, Any] | None:
        """Layer 2: 从 header_rules 匹配（用户指定 data_start_row）。"""
        for rule in self._header_rules:
            if (
                rule.get("wp_code") == wp_code
                and rule.get("sheet_name") == sheet_name
            ):
                # If the rule specifies column headers, try to match label
                col_headers = rule.get("col_headers", {})
                if label in col_headers:
                    return {
                        "row": rule.get("data_start_row"),
                        "col": col_headers[label],
                        "source": "header_rule",
                    }
                # If the rule specifies row headers, try to match label
                row_headers = rule.get("row_headers", {})
                if label in row_headers:
                    return {
                        "row": row_headers[label],
                        "col": rule.get("data_start_col", 1),
                        "source": "header_rule",
                    }
        return None

    def _resolve_heuristic(
        self, wp_code: str, sheet_name: str, label: str
    ) -> dict[str, Any] | None:
        """Layer 3: 启发式全 sheet 扫描。

        Note: Full implementation requires xlsx file access.
        This is a placeholder that returns None.
        Real implementation would:
        1. Open the xlsx file for wp_code
        2. Find the sheet by sheet_name
        3. Scan for "data area first row" (连续多非空短文本单元格)
        4. Match label against row/col headers
        """
        # Placeholder — full implementation requires openpyxl + file access
        return None

    async def invalidate_cache(self, project_id: str, wp_code: str) -> None:
        """底稿保存时清除该 wp 的所有缓存。"""
        if not self._redis:
            return

        try:
            pattern = f"resolve:{project_id}:{wp_code}:*"
            # Use SCAN to find and delete matching keys
            cursor = 0
            while True:
                cursor, keys = await self._redis.scan(
                    cursor=cursor, match=pattern, count=100
                )
                if keys:
                    await self._redis.delete(*keys)
                if cursor == 0:
                    break
        except Exception as e:
            logger.warning("Failed to invalidate cache for %s:%s: %s", project_id, wp_code, e)

    async def add_override(
        self,
        wp_code: str,
        sheet_name: str,
        label: str,
        row: int,
        col: int,
    ) -> dict[str, Any]:
        """添加用户手动校正。"""
        override = {
            "wp_code": wp_code,
            "sheet_name": sheet_name,
            "label": label,
            "row": row,
            "col": col,
        }

        # Remove existing override for same key
        self._overrides = [
            o for o in self._overrides
            if not (
                o.get("wp_code") == wp_code
                and o.get("sheet_name") == sheet_name
                and o.get("label") == label
            )
        ]
        self._overrides.append(override)
        self._persist_overrides()
        return override

    def delete_override(
        self, wp_code: str, sheet_name: str, label: str
    ) -> bool:
        """删除用户手动校正。"""
        before = len(self._overrides)
        self._overrides = [
            o for o in self._overrides
            if not (
                o.get("wp_code") == wp_code
                and o.get("sheet_name") == sheet_name
                and o.get("label") == label
            )
        ]
        if len(self._overrides) < before:
            self._persist_overrides()
            return True
        return False

    def add_header_rule(
        self,
        wp_code: str,
        sheet_name: str,
        data_start_row: int,
        col_header_row: int | None = None,
        col_headers: dict[str, int] | None = None,
        row_headers: dict[str, int] | None = None,
    ) -> dict[str, Any]:
        """设置表头规则。"""
        rule: dict[str, Any] = {
            "wp_code": wp_code,
            "sheet_name": sheet_name,
            "data_start_row": data_start_row,
        }
        if col_header_row is not None:
            rule["col_header_row"] = col_header_row
        if col_headers:
            rule["col_headers"] = col_headers
        if row_headers:
            rule["row_headers"] = row_headers

        # Remove existing rule for same wp+sheet
        self._header_rules = [
            r for r in self._header_rules
            if not (
                r.get("wp_code") == wp_code
                and r.get("sheet_name") == sheet_name
            )
        ]
        self._header_rules.append(rule)
        self._persist_overrides()
        return rule

    def list_overrides(self) -> list[dict[str, Any]]:
        """列出所有 overrides。"""
        return self._overrides

    def list_header_rules(self) -> list[dict[str, Any]]:
        """列出所有 header_rules。"""
        return self._header_rules

    def _persist_overrides(self) -> None:
        """持久化到 address_label_overrides.json。"""
        data = {
            "overrides": self._overrides,
            "header_rules": self._header_rules,
        }
        try:
            OVERRIDES_PATH.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError as e:
            logger.error("Failed to persist address_label_overrides.json: %s", e)

    # ─── Cache helpers ───────────────────────────────────────────

    async def _get_cache(self, key: str) -> dict[str, Any] | None:
        """从 Redis 读缓存。"""
        if not self._redis:
            return None
        try:
            val = await self._redis.get(key)
            if val:
                return json.loads(val)
        except Exception:
            pass
        return None

    async def _set_cache(self, key: str, value: dict[str, Any]) -> None:
        """写 Redis 缓存。"""
        if not self._redis:
            return
        try:
            await self._redis.set(key, json.dumps(value), ex=CACHE_TTL)
        except Exception:
            pass
