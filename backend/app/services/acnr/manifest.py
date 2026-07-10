"""ACNR manifest — bulk I/E manifest 生成服务层

提供 `list_import_export(db, project_id, cycle?)` 方法，从 catalog 读取
启用 import_export 的 sheet 条目，通过 resolve_instance 解析项目内 wp_id，
返回可直接用于 bulk ZIP 导入导出的 manifest 清单。

核心铁律（R18.6 / R-ROUTE）：
  I/E 路由只认 catalog 的 api_prefix + item_id。
  不从 d*_import_export.py 动态提取，只从 catalog 的 import_export 段读取。

Requirements: 18.6
"""
from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.acnr.catalog import list_sheets
from app.services.acnr.resolver import resolve_instance

logger = logging.getLogger(__name__)


async def list_import_export(
    db: AsyncSession,
    project_id: UUID,
    cycle: str | None = None,
) -> list[dict[str, Any]]:
    """List I/E manifest entries from catalog, resolved with project wp_ids.

    Each entry: {sheet_code, api_prefix, item_id, storage_field, import_order,
                 depends_on_sheets, wp_id, jump_route}

    I/E routes only recognize catalog's api_prefix + item_id (R18.6/R-ROUTE).

    Logic:
      1. Call catalog.list_sheets(cycle=cycle, import_export_only=True) to get
         sheets with I/E enabled.
      2. For each sheet, extract import_export segment (api_prefix, item_id, etc.)
      3. Call resolve_instance(db, project_id, parent_wp_code, sheet_code) to get wp_id.
      4. Return sorted by import_order.

    Args:
        db: Async database session for resolve_instance queries.
        project_id: Project UUID — required for wp_id resolution.
        cycle: Optional cycle filter (e.g. "D"). If None, returns all cycles.

    Returns:
        List of manifest entry dicts sorted by import_order, each containing:
        - sheet_code: Tab encoding (e.g. "D2-2")
        - api_prefix: I/E endpoint prefix (e.g. "d2")
        - item_id: checklist_responses item_id (str or list[str])
        - storage_field: Storage column (e.g. "remark")
        - import_order: Numeric ordering for bulk import sequence
        - depends_on_sheets: List of sheet_codes this sheet depends on
        - wp_id: Resolved WorkingPaper UUID (None if not resolved)
        - jump_route: Resolved jump route (None if wp_id not resolved)
        - parent_wp_code: Parent workpaper code (e.g. "D2")
        - addr_id: Sheet-level addr_id from catalog
    """
    # Step 1: Get sheets with import_export enabled from catalog
    ie_sheets = list_sheets(cycle=cycle, import_export_only=True)

    if not ie_sheets:
        return []

    # Step 2 & 3: Build manifest entries with resolved wp_ids
    manifest_entries: list[dict[str, Any]] = []

    for sheet in ie_sheets:
        ie_segment = sheet.get("import_export", {})
        if not ie_segment or not ie_segment.get("enabled"):
            continue

        parent_wp_code = sheet.get("parent_wp_code", "")
        sheet_code = sheet.get("sheet_code", "")

        # Resolve wp_id via resolve_instance (唯一 wp_id 出口, R13.1)
        wp_id: str | None = None
        jump_route: str | None = None

        try:
            result = await resolve_instance(
                db=db,
                project_id=project_id,
                parent_wp_code=parent_wp_code,
                sheet_code=sheet_code,
            )
            if result.found and result.wp_id:
                wp_id = str(result.wp_id)
                jump_route = result.jump_route
        except Exception as e:
            # resolve_instance failure should not block the entire manifest
            # Log and continue — entry will have wp_id=None
            logger.warning(
                "manifest resolve_instance failed: project=%s sheet=%s error=%s",
                project_id,
                sheet_code,
                e,
            )

        entry: dict[str, Any] = {
            "sheet_code": sheet_code,
            "api_prefix": ie_segment.get("api_prefix", ""),
            "item_id": ie_segment.get("item_id", ""),
            "storage_field": ie_segment.get("storage_field", "remark"),
            "import_order": ie_segment.get("import_order", 999),
            "depends_on_sheets": ie_segment.get("depends_on_sheets", []),
            "wp_id": wp_id,
            "jump_route": jump_route,
            "parent_wp_code": parent_wp_code,
            "addr_id": sheet.get("addr_id", ""),
        }
        manifest_entries.append(entry)

    # Step 4: Sort by import_order
    manifest_entries.sort(key=lambda e: e["import_order"])

    return manifest_entries
