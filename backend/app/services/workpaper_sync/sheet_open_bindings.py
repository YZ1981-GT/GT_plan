"""Sheet 级 OnlyOffice 入口到真实 sync entry 的显式解析。

spec: `onlyoffice-sheet-open-via-published-artifact` Phase 1 / umbrella 2.8

本模块只读生成物 `workpaper_sync_sheet_open_bindings.json`。它不读取模板目录，
不按 sheet 名猜父级，不构造 `xlsx-sheet/*` 虚假 entry。
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from app.services.workpaper_sync.entry_profile import manifest_entries_by_id

BACKEND_ROOT = Path(__file__).resolve().parents[3]
BINDINGS_PATH = BACKEND_ROOT / "data" / "workpaper_sync_sheet_open_bindings.json"


@dataclass(frozen=True)
class SheetOpenBindingResolution:
    """一个 sheet 请求的显式映射结果。"""

    status: str
    reason: str | None
    binding: Mapping[str, Any] | None = None

    @property
    def is_migrated(self) -> bool:
        return self.status == "migrated" and self.binding is not None

    def as_dict(self) -> dict[str, Any]:
        row = dict(self.binding or {})
        return {
            "status": self.status,
            "reason": self.reason,
            "binding_id": row.get("binding_id"),
            "entry_id": row.get("entry_id"),
            "effective_entry_id": row.get("effective_entry_id"),
            "source_wp_code": row.get("source_wp_code"),
            "document_scope": row.get("document_scope"),
            "target_sheet": row.get("target_sheet"),
            "mapping_kind": row.get("mapping_kind"),
            "manifest_entry_digest": row.get("manifest_entry_digest"),
            "input_digest": row.get("input_digest"),
        }


class SheetOpenBindingResolver:
    """从生成物解析 sheet → manifest entry，不做请求期猜测。"""

    def __init__(self, bindings_path: Path = BINDINGS_PATH) -> None:
        self.bindings_path = bindings_path

    def _load(self) -> list[dict[str, Any]]:
        if not self.bindings_path.is_file():
            raise FileNotFoundError(f"sheet binding 生成物缺失: {self.bindings_path}")
        payload = json.loads(self.bindings_path.read_text(encoding="utf-8"))
        if payload.get("schema_version") != "sheet-open-binding:v1":
            raise ValueError("sheet binding schema_version 不受支持")
        rows = payload.get("bindings")
        if not isinstance(rows, list) or not rows:
            raise ValueError("sheet binding bindings 必须是非空数组")
        return [dict(row) for row in rows]

    def resolve(
        self,
        *,
        source_wp_code: str,
        sheet_name: str,
        whole_workbook: bool,
        manifest: Mapping[str, Any],
    ) -> SheetOpenBindingResolution:
        code = str(source_wp_code or "").strip()
        sheet = str(sheet_name or "").strip()
        rows = [
            row for row in self._load()
            if row.get("source_wp_code") == code
            and row.get("document_type") == "xlsx"
            and row.get("status") != "out_of_scope"
        ]
        if not rows:
            return SheetOpenBindingResolution("pending", "sheet_binding_not_found")

        manifest_ids = set(manifest_entries_by_id(manifest))
        if whole_workbook:
            candidates = [row for row in rows if row.get("document_scope") == "whole_workbook"]
        else:
            candidates = [
                row for row in rows
                if row.get("document_scope") == "single_sheet"
                and row.get("mapping_kind") == "exact"
                and row.get("target_sheet") == sheet
            ]

        if len(candidates) > 1:
            return SheetOpenBindingResolution("pending", "sheet_binding_ambiguous")
        if not candidates:
            if any(row.get("mapping_kind") == "provider" for row in rows):
                return SheetOpenBindingResolution("pending", "sheet_binding_provider_review_required")
            return SheetOpenBindingResolution("pending", "sheet_target_not_declared")

        binding = candidates[0]
        entry_id = str(binding.get("entry_id") or "")
        effective_id = str(binding.get("effective_entry_id") or entry_id)
        if entry_id not in manifest_ids or effective_id not in manifest_ids:
            return SheetOpenBindingResolution("pending", "sheet_binding_entry_not_in_manifest", binding)
        if binding.get("status") not in {
            "pending", "ready", "migrated", "draining", "retired"
        }:
            return SheetOpenBindingResolution("pending", "sheet_binding_status_invalid", binding)
        return SheetOpenBindingResolution(str(binding["status"]), binding.get("reason"), binding)


__all__ = ["BINDINGS_PATH", "SheetOpenBindingResolution", "SheetOpenBindingResolver"]
