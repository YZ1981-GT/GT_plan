"""Render-config canonical identity projection (guidance Task 10).

Emits stable sheet_uid / null_reason / template authority input for hosts.
Display names and regex-derived codes are never the sole identity key.
"""

from __future__ import annotations

from typing import Any

from app.services.guidance_gid import StableSheetIdentity, sheet_identity_from_authority
from app.services.guidance_source_refs import TemplateAuthoritySnapshot

__all__ = [
    "project_sheet_uid",
    "annotate_sheet_canonical_identity",
]


def project_sheet_uid(
    *,
    parent_wp_code: str,
    sheet_code: str | None,
    sheet_name: str | None,
    whole_workbook: bool,
    explicit_uid: str | None = None,
    code_reason: str | None = None,
) -> tuple[str | None, str | None]:
    """Return (sheet_uid, null_reason).

    Priority:
      1. explicit sheet_uid carrier
      2. whole_workbook → uid is None with reason whole_workbook
      3. stable sheet_code → deterministic uid:{wp}:{code}
      4. otherwise None + honest null_reason (never invent uid from display name)
    """
    if explicit_uid and str(explicit_uid).strip():
        return str(explicit_uid).strip(), None
    if whole_workbook:
        return None, "whole_workbook"
    if sheet_code and str(sheet_code).strip():
        return f"uid:{parent_wp_code}:{str(sheet_code).strip()}", None
    reason = "sheet_uid_unavailable"
    if code_reason == "no_canonical_code":
        reason = "no_canonical_code"
    elif sheet_name:
        reason = "display_name_not_identity"
    return None, reason


def annotate_sheet_canonical_identity(
    sheet: dict[str, Any],
    *,
    parent_wp_code: str,
    template_lineage_id: str | None = None,
    template_version_id: str | None = None,
    authority_snapshot: TemplateAuthoritySnapshot | None = None,
) -> dict[str, Any]:
    """Augment a render-config sheet dict with G-ID identity fields (in-place)."""
    whole = bool(sheet.get("whole_workbook", False))
    code = sheet.get("sheet_code")
    code = str(code).strip() if code is not None and str(code).strip() else None
    uid, null_reason = project_sheet_uid(
        parent_wp_code=parent_wp_code,
        sheet_code=code,
        sheet_name=sheet.get("sheet_name"),
        whole_workbook=whole,
        explicit_uid=sheet.get("sheet_uid"),
        code_reason=sheet.get("sheet_code_reason"),
    )
    sheet["sheet_uid"] = uid
    sheet["sheet_uid_null_reason"] = null_reason

    identity = sheet_identity_from_authority(
        wp_code=parent_wp_code,
        sheet_uid=uid,
        sheet_code=code,
        snapshot=authority_snapshot,
        null_reason=null_reason,
    )
    if template_lineage_id is not None or template_version_id is not None:
        identity = StableSheetIdentity(
            template_lineage_id=template_lineage_id,
            template_version_id=template_version_id,
            wp_code=parent_wp_code,
            sheet_uid=uid,
            sheet_code=code,
            null_reason=null_reason,
        )
    sheet["stable_identity"] = identity.to_dict()
    return sheet
