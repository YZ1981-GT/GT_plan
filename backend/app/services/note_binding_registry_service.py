"""附注取数绑定注册表服务

提供 binding registry 的加载、解析、查找和校验能力：
- resolve_binding: 根据 binding_id 获取完整配置
- validate_binding: 校验 binding 字段合法性
- find_bindings_by_section: 按 section_id 查找
- find_bindings_by_source: 按来源类型查找
- impact_by_source: 当某个来源变更时，哪些单元格受影响

Validates: Requirements 5.1, 5.2, 5.3, 5.4, 5.5
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# 默认 registry 路径
_DEFAULT_REGISTRY_PATH = (
    Path(__file__).resolve().parents[2] / "data" / "note_binding_registry.json"
)

# 必需字段
_REQUIRED_FIELDS = frozenset(
    ["binding_id", "section_id", "table_id", "row_id", "col_id", "source"]
)

# 合法来源枚举
VALID_SOURCES = frozenset(
    [
        "trial_balance",
        "ledger",
        "workpaper",
        "report",
        "prior_note",
        "manual",
        "formula",
        "ai_draft",
    ]
)


class NoteBindingRegistryService:
    """附注取数绑定注册表服务。

    初始化时加载 JSON 配置文件，提供运行时查询和校验方法。
    """

    def __init__(self, registry_path: str | None = None) -> None:
        """加载绑定注册表。

        Args:
            registry_path: JSON 文件路径。为 None 时使用默认路径。
        """
        path = Path(registry_path) if registry_path else _DEFAULT_REGISTRY_PATH
        self._bindings: list[dict[str, Any]] = []
        self._index_by_id: dict[str, dict[str, Any]] = {}
        self._valid_sources: set[str] = set(VALID_SOURCES)

        if path.exists():
            try:
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
                self._bindings = data.get("bindings", [])
                # 若 JSON 中声明了 valid_sources，以其为准
                declared_sources = data.get("valid_sources")
                if isinstance(declared_sources, list) and declared_sources:
                    self._valid_sources = set(declared_sources)
            except (json.JSONDecodeError, OSError) as e:
                logger.error("加载 binding registry 失败: %s", e)
                self._bindings = []

        # 构建 ID 索引
        for binding in self._bindings:
            bid = binding.get("binding_id", "")
            if bid:
                self._index_by_id[bid] = binding

    # ------------------------------------------------------------------
    # 公开方法
    # ------------------------------------------------------------------

    def resolve_binding(self, binding_id: str) -> dict[str, Any] | None:
        """根据 binding_id 获取完整绑定配置。

        Args:
            binding_id: 绑定 ID

        Returns:
            绑定字典，未找到返回 None
        """
        return self._index_by_id.get(binding_id)

    def validate_binding(self, binding_id: str) -> list[str]:
        """校验指定 binding 的合法性。

        返回错误列表，空列表表示合法。

        校验项：
        1. binding_id 必须存在于 registry
        2. 必需字段不为空
        3. source 枚举合法
        4. workpaper source 必须有 wp_code
        """
        errors: list[str] = []
        binding = self._index_by_id.get(binding_id)
        if binding is None:
            errors.append(f"binding_id '{binding_id}' 不存在于 registry")
            return errors

        # 必需字段校验
        for field in _REQUIRED_FIELDS:
            val = binding.get(field)
            if not val or (isinstance(val, str) and not val.strip()):
                errors.append(f"字段 '{field}' 为空或缺失")

        # source 枚举校验
        source = binding.get("source", "")
        if source and source not in self._valid_sources:
            errors.append(
                f"source '{source}' 不在合法枚举中: {sorted(self._valid_sources)}"
            )

        # workpaper 来源需要 wp_code
        if source == "workpaper" and not binding.get("wp_code"):
            errors.append("source='workpaper' 但 wp_code 为空")

        return errors

    def find_bindings_by_section(self, section_id: str) -> list[dict[str, Any]]:
        """查找指定 section 的所有绑定。

        Args:
            section_id: 章节 ID

        Returns:
            匹配的绑定列表
        """
        return [
            b for b in self._bindings if b.get("section_id") == section_id
        ]

    def find_bindings_by_source(
        self, source_type: str, source_id: str = ""
    ) -> list[dict[str, Any]]:
        """查找指定来源类型的所有绑定。

        Args:
            source_type: 来源类型（如 workpaper, trial_balance）
            source_id: 可选来源标识（如 wp_code='E4-1'）

        Returns:
            匹配的绑定列表
        """
        results: list[dict[str, Any]] = []
        for b in self._bindings:
            if b.get("source") != source_type:
                continue
            if source_id:
                # 匹配 wp_code 或 field
                if b.get("wp_code") == source_id or b.get("field") == source_id:
                    results.append(b)
            else:
                results.append(b)
        return results

    def impact_by_source(
        self, source_type: str, source_id: str
    ) -> list[dict[str, Any]]:
        """当某个来源变更时，定位受影响的单元格。

        返回受影响绑定列表，每条包含 section_id/table_id/row_id/col_id。

        Args:
            source_type: 来源类型
            source_id: 来源标识（wp_code 或 field）

        Returns:
            受影响绑定列表（仅 active 的）
        """
        impacted: list[dict[str, Any]] = []
        for b in self._bindings:
            if not b.get("active", True):
                continue
            if b.get("source") != source_type:
                continue
            # 匹配 wp_code 或 field
            if b.get("wp_code") == source_id or b.get("field") == source_id:
                impacted.append(
                    {
                        "binding_id": b.get("binding_id"),
                        "section_id": b.get("section_id"),
                        "table_id": b.get("table_id"),
                        "row_id": b.get("row_id"),
                        "col_id": b.get("col_id"),
                    }
                )
        return impacted

    @property
    def all_bindings(self) -> list[dict[str, Any]]:
        """返回所有绑定条目的只读副本。"""
        return list(self._bindings)

    @property
    def valid_sources(self) -> set[str]:
        """返回合法来源枚举集合。"""
        return set(self._valid_sources)
