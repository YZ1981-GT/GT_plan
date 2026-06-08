"""占位符注册表 — canonical {{key}} ↔ legacy {key} 双向映射."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.report_placeholder_service import ReportPlaceholderService

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
DEFAULT_REGISTRY_PATH = DATA_DIR / "audit_report_templates" / "placeholder_registry.json"


class PlaceholderRegistry:
    """加载 ``placeholder_registry.json`` 并构建 TemplateFill 用占位符映射."""

    def __init__(self, registry_path: Path | None = None):
        self._path = (registry_path or DEFAULT_REGISTRY_PATH).resolve()
        self._data: dict[str, Any] = {}
        self.reload()

    def reload(self) -> None:
        if not self._path.is_file():
            self._data = {}
            return
        self._data = json.loads(self._path.read_text(encoding="utf-8"))

    @property
    def version(self) -> str:
        return str(self._data.get("version", ""))

    def canonical_to_legacy(self) -> dict[str, str]:
        return dict(self._data.get("canonical_to_legacy", {}))

    def legacy_to_canonical(self) -> dict[str, str]:
        return {v: k for k, v in self.canonical_to_legacy().items()}

    def get_opt_defaults(self, company_subtype: str | None) -> dict[str, bool]:
        """按企业子类型返回 OPT 默认勾选（type_a / type_b / …）."""
        defaults = self._data.get("opt_defaults", {})
        key = (company_subtype or "type_d").strip().lower()
        block = defaults.get(key) or defaults.get("type_d") or {}
        return {str(k): bool(v) for k, v in block.items()}

    def get_section_group_map(self) -> dict[str, str]:
        return dict(self._data.get("section_group_map", {}))

    async def build_placeholder_map(
        self,
        project_id: UUID,
        db: AsyncSession,
    ) -> dict[str, str]:
        """封装 ``ReportPlaceholderService`` + registry 映射为 canonical ``{{key}}`` 值."""
        legacy_svc = ReportPlaceholderService(db)
        legacy_map = await legacy_svc.get_placeholders(project_id)
        c2l = self.canonical_to_legacy()
        l2c = self.legacy_to_canonical()

        canonical: dict[str, str] = {}
        # legacy 键直通（兼容旧模板 {entity_name}）
        for leg_key, value in legacy_map.items():
            can_key = l2c.get(leg_key, leg_key)
            canonical[can_key] = value or ""

        # 确保 registry 中全部 canonical 键存在（缺失留空串供 missing_fields 检测）
        for can_key, leg_key in c2l.items():
            if can_key not in canonical:
                canonical[can_key] = legacy_map.get(leg_key, "")

        return canonical

    def detect_missing_fields(self, mapping: dict[str, str]) -> list[str]:
        """检测仍为占位/空值的关键字段."""
        missing: list[str] = []
        for key, value in mapping.items():
            v = (value or "").strip()
            if not v or v.startswith("[") and v.endswith("]"):
                missing.append(key)
        return missing


@lru_cache(maxsize=1)
def get_placeholder_registry() -> PlaceholderRegistry:
    return PlaceholderRegistry()
