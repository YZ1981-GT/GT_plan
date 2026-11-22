"""Sheet 级 OnlyOffice 入口到真实 sync entry 的显式解析。

spec: `onlyoffice-sheet-open-via-published-artifact` Phase 1 / umbrella 2.8

本模块只读生成物 `workpaper_sync_sheet_open_bindings.json`。它不读取模板目录，
不按 sheet 名猜父级，不构造 `xlsx-sheet/*` 虚假 entry。
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from collections.abc import Iterable
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

    @property
    def allows_room_readiness(self) -> bool:
        """该 binding 状态是否允许去跑 room readiness。

        `pending` 必须为 False，两条理由都是实测出来的：

        ① **未审核不得判成 room 可用** —— 那等于绕过审核直接开门（Requirement 3）；
        ② readiness 的失败会被端点 `except Exception` 兜底压成不透明的技术异常名
           （实测 `该底稿尚未接入统一在线编辑（AttributeError）`），把 binding 自己
           给出的**封闭原因码**（如 `runtime_sheet_name_requires_provider_binding`）
           盖掉 —— 用户与前端从此看不到「为什么没迁」。

        `ready` / `migrated` / `draining` 仍走 readiness（room 是它们的正路）；
        `retired` 与 `out_of_scope` 也不走（前者已下线、后者本就不适用本迁移）。
        未知状态一律 False（fail-closed，不猜）。
        """
        return self.status in {"ready", "migrated", "draining"}

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
        source_wp_codes: Iterable[str] | None = None,
        project_id: str | None = None,
    ) -> SheetOpenBindingResolution:
        """按 `(wp_code, sheet_name)` 在生成物里找 binding。

        🔴 `source_wp_codes` 是**候选集合**，不是第二套判定：
        调用方先用 `resolve_sheet_wp_code`（`_wp_sheet_code_resolution.py`，单一实现）
        算出实际使用的码，再把它与底稿原码**一起**传进来。生成器写的是 manifest 的
        `wp_code_patterns[0]`（如 `B60-1`），运行时算出的可能是父码（如 `B60`，当
        父码有自己的模板时）—— 两者都要能命中，否则「迁移了却打不开」。

        实测反例（未加候选集之前）：真实库 B60 的 binding 已是 `migrated`，而
        `GET /sync/entry-identity?sheet_name=B60` 恒返回 `sheet_binding_not_found`。
        """
        declared = {str(c or "").strip() for c in (source_wp_codes or ()) if str(c or "").strip()}
        code = str(source_wp_code or "").strip()
        if code:
            declared.add(code)
        sheet = str(sheet_name or "").strip()
        rows = [
            row for row in self._load()
            if row.get("source_wp_code") in declared
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
            # ── provider 型：target sheet 由**运行时请求名**决定，不猜也不回退父级 ──
            #
            # manifest 的 `sheet_expressions` 形如 `:sheet-name="ooSheetName"`（前端把
            # `dualMode.resolveOoSheetName()` / `props.sheetName` 传给 `<GtOnlyOfficeSheet>`）。
            # 也就是说：**请求里的 `sheet_name` 就是 artifact 内的 target sheet 名**，
            # 后端不需要（也不允许）按模板目录去推断。
            #
            # 三条硬约束（任一不满足仍返回 pending，不伪造 entry）：
            #   ① 该 entry 必须只有一条 provider binding —— 多条说明码族内有歧义；
            #   ② 必须带 `resolver_identity` —— 没有稳定身份就无法审核；
            #   ③ `sheet_name` 必须非空 —— 空名会落到 artifact 默认 sheet 上（等于静默回退）。
            provider_rows = [row for row in rows if row.get("mapping_kind") == "provider"]
            if provider_rows:
                if len(provider_rows) > 1:
                    return SheetOpenBindingResolution("pending", "sheet_binding_ambiguous")
                if not sheet:
                    return SheetOpenBindingResolution(
                        "pending", "sheet_binding_provider_sheet_name_missing"
                    )
                if not provider_rows[0].get("resolver_identity"):
                    return SheetOpenBindingResolution(
                        "pending", "sheet_binding_provider_identity_missing"
                    )
                candidates = [provider_rows[0]]
            else:
                return SheetOpenBindingResolution("pending", "sheet_target_not_declared")

        if len(candidates) > 1:
            return SheetOpenBindingResolution("pending", "sheet_binding_ambiguous")

        binding = dict(candidates[0])
        reviewed = binding.get("reviewed") or {}
        scoped_projects = reviewed.get("project_ids")
        if scoped_projects is not None and str(project_id or "") not in {str(x) for x in scoped_projects}:
            binding["status"] = "pending"
            binding["reason"] = "reviewed_binding_project_not_in_scope"
            binding["reviewed"] = None
            return SheetOpenBindingResolution("pending", binding["reason"], binding)
        entry_id = str(binding.get("entry_id") or "")
        effective_id = str(binding.get("effective_entry_id") or entry_id)
        if entry_id not in manifest_ids or effective_id not in manifest_ids:
            return SheetOpenBindingResolution("pending", "sheet_binding_entry_not_in_manifest", binding)
        if binding.get("status") not in {
            "pending", "ready", "migrated", "draining", "retired"
        }:
            return SheetOpenBindingResolution("pending", "sheet_binding_status_invalid", binding)

        # provider 型的 target sheet 取本次请求名（生成物里那个值恒为 None，因为
        # 表达式形态没法在生成期定型）。`_load()` 每次从磁盘重读并 `dict(row)` 复制，
        # 所以这里直接赋值不会写脏生成物 —— 该保证由 `_load` 承担，不在这里重复拷贝。
        if binding.get("mapping_kind") == "provider" and not binding.get("target_sheet"):
            binding["target_sheet"] = sheet
        return SheetOpenBindingResolution(str(binding["status"]), binding.get("reason"), binding)


__all__ = ["BINDINGS_PATH", "SheetOpenBindingResolution", "SheetOpenBindingResolver"]
