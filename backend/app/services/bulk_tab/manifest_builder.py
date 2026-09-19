"""ManifestBuilder — 唯一读 ACNR 生成 Bulk manifest。

从 wp_bulk_tab_export.list_export_sheets (逐 cycle) 汇总 entries,
生成 §8.6.6 字段的 BulkManifest 结构。路由元数据只来自 ACNR，不手写清单。

核心铁律：
  - manifest 字段只来自 acnr/manifest.list_import_export
  - 排序只用 wp_bulk_tab_export._topological_sort
  - ACNR catalog 不可用时抛明确异常，绝不静默退回分散 JSON（Req 7.4）
  - skip_reason/wp_id=None 条目写入 skipped[], 不产 xlsx

Requirements: 1.4, 1.5, 1.6, 1.8, 7.1, 7.2, 7.3, 7.4
"""
from __future__ import annotations

import re
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.acnr.catalog import CatalogLoadError
from app.services.bulk_tab.exceptions import AcnrCatalogUnavailableError

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class ManifestFileEntry:
    """manifest.json 中 files[] 的一条记录。"""

    addr_id: str
    wp_code: str
    parent_wp_code: str
    sheet_code: str
    sheet_name: str
    origin: str  # standard | custom
    api_prefix: str
    item_id: str | list[str]
    storage_field: str
    wp_id: str | None
    import_order: int
    depends_on_sheets: list[str]
    zip_path: str
    sha256: str  # 导出时填入, build 阶段为空占位


@dataclass
class ManifestSkippedEntry:
    """manifest.json 中 skipped[] 的一条记录。"""

    addr_id: str
    sheet_code: str
    sheet_name: str
    parent_wp_code: str
    skip_reason: str


@dataclass
class BulkManifest:
    """Bulk ZIP manifest.json 完整结构。"""

    schema_version: str = "1.0"
    project_id: str = ""
    audit_year: int = 0
    exported_at: str = ""
    exported_by: str = ""
    platform_version: str = ""
    mode: str = ""  # template | data
    cycles: list[str] = field(default_factory=list)
    files: list[ManifestFileEntry] = field(default_factory=list)
    skipped: list[ManifestSkippedEntry] = field(default_factory=list)

    def exportable(self) -> list[ManifestFileEntry]:
        """返回可导出的 file entries（wp_id 非空）。"""
        return [f for f in self.files if f.wp_id is not None]

    def to_dict(self) -> dict[str, Any]:
        """序列化为 dict（供 JSON dump）。"""
        return {
            "schema_version": self.schema_version,
            "project_id": self.project_id,
            "audit_year": self.audit_year,
            "exported_at": self.exported_at,
            "exported_by": self.exported_by,
            "platform_version": self.platform_version,
            "mode": self.mode,
            "cycles": self.cycles,
            "files": [
                {
                    "addr_id": f.addr_id,
                    "wp_code": f.wp_code,
                    "parent_wp_code": f.parent_wp_code,
                    "sheet_code": f.sheet_code,
                    "sheet_name": f.sheet_name,
                    "origin": f.origin,
                    "api_prefix": f.api_prefix,
                    "item_id": f.item_id,
                    "storage_field": f.storage_field,
                    "wp_id": f.wp_id,
                    "import_order": f.import_order,
                    "depends_on_sheets": f.depends_on_sheets,
                    "zip_path": f.zip_path,
                    "sha256": f.sha256,
                }
                for f in self.files
            ],
            "skipped": [
                {
                    "addr_id": s.addr_id,
                    "sheet_code": s.sheet_code,
                    "sheet_name": s.sheet_name,
                    "parent_wp_code": s.parent_wp_code,
                    "skip_reason": s.skip_reason,
                }
                for s in self.skipped
            ],
        }


# ---------------------------------------------------------------------------
# Slug 化 helper
# ---------------------------------------------------------------------------

# 去掉 sheet_code 后缀用的模式: sheet_name 末尾可能带 sheet_code
_SHEET_CODE_SUFFIX_RE = re.compile(r"[A-Za-z]\d+(?:-\d+)?[A-Za-z]?\s*$")
# 替换非法文件名字符（保留中文、字母、数字、连字符）
_ILLEGAL_PATH_CHARS_RE = re.compile(r"[^\w\u4e00-\u9fff\-]", re.UNICODE)


def _make_short_label(sheet_name: str, sheet_code: str) -> str:
    """生成 short_label: sheet_name 去 sheet_code 后缀并 slug 化。

    例: "明细表D2-2" → "明细表", "应收账款实质性程序表D2A" → "应收账款实质性程序表"
    中文安全，保留中文字符。
    """
    label = sheet_name
    # 尝试去除末尾 sheet_code 精确匹配
    if label.endswith(sheet_code):
        label = label[: -len(sheet_code)]
    else:
        # fallback: 去除末尾类似编码的后缀
        label = _SHEET_CODE_SUFFIX_RE.sub("", label)

    label = label.strip()

    # 如果去除后为空，回退到原名
    if not label:
        label = sheet_name

    # slug 化: 替换非法文件名字符为下划线, 合并连续下划线
    label = _ILLEGAL_PATH_CHARS_RE.sub("_", label)
    label = re.sub(r"_+", "_", label).strip("_")

    # 截断到 40 字符避免路径过长
    if len(label) > 40:
        label = label[:40].rstrip("_")

    return label or sheet_code


def _build_zip_path(
    cycle: str,
    parent_wp_code: str,
    sheet_code: str,
    sheet_name: str,
    mode: Literal["template", "data"],
) -> str:
    """构建 zip_path: {cycle}/{parent_wp_code}/{sheet_code}_{short_label}_{模板|数据}.xlsx"""
    short_label = _make_short_label(sheet_name, sheet_code)
    mode_label = "模板" if mode == "template" else "数据"
    return f"{cycle}/{parent_wp_code}/{sheet_code}_{short_label}_{mode_label}.xlsx"


# ---------------------------------------------------------------------------
# build_manifest 主函数
# ---------------------------------------------------------------------------


async def build_manifest(
    db: AsyncSession,
    project_id: UUID,
    cycles: list[str] | None,
    mode: Literal["template", "data"],
    *,
    exported_by: str = "",
    platform_version: str = "",
    audit_year: int = 0,
) -> BulkManifest:
    """从 wp_bulk_tab_export.list_export_sheets 汇总 entries，生成 BulkManifest。

    逐 cycle 调 list_export_sheets 获取已拓扑排序 + 已过滤 wp_id=None 的有效条目，
    同时从 ACNR manifest.list_import_export 获取全量条目（含 wp_id=None），
    差集写入 skipped[]。

    ACNR catalog 不可用时抛 AcnrCatalogUnavailableError（Req 7.4），
    绝不静默退回分散 JSON。

    路由元数据只来自 ACNR (Req 7.1)，不手写 sheet 清单。

    Args:
        db: Async database session.
        project_id: 项目 UUID.
        cycles: 循环列表（如 ["D"]）。None 表示导出全部已启用循环。
        mode: "template" 或 "data".
        exported_by: 导出人用户名.
        platform_version: 平台版本号.
        audit_year: 审计年度.

    Returns:
        BulkManifest 实例，files[] 为可导出条目（已拓扑排序），
        skipped[] 为 wp_id=None 的条目。

    Raises:
        AcnrCatalogUnavailableError: ACNR catalog 加载失败时抛出。
    """
    from app.services.wp_bulk_tab_export import list_export_sheets
    from app.services.acnr.manifest import list_import_export
    from app.services.acnr.catalog import list_sheets

    # 确定要处理的循环列表
    effective_cycles = cycles if cycles else _get_all_cycles()

    manifest = BulkManifest(
        schema_version="1.0",
        project_id=str(project_id),
        audit_year=audit_year,
        exported_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        exported_by=exported_by,
        platform_version=platform_version,
        mode=mode,
        cycles=effective_cycles,
    )

    for cycle_code in effective_cycles:
        # ─── 获取可导出条目（已拓扑排序, wp_id 非空） ───────────────
        try:
            export_entries = await list_export_sheets(
                db=db,
                project_id=str(project_id),
                cycle=cycle_code,
            )
        except CatalogLoadError as e:
            # Req 7.4: ACNR catalog 不可用 → 抛明确异常，不静默降级
            logger.error(
                "ACNR catalog 不可用: project=%s cycle=%s error=%s",
                project_id,
                cycle_code,
                e,
            )
            raise AcnrCatalogUnavailableError(
                f"ACNR catalog 不可用，无法生成 bulk manifest（cycle={cycle_code}）",
                cause=e,
            ) from e

        export_addr_ids = {e.get("addr_id", "") for e in export_entries}

        # ─── 获取全量条目（含 wp_id=None, 用于确定 skipped） ────────
        try:
            all_entries = await list_import_export(
                db=db,
                project_id=project_id,
                cycle=cycle_code,
            )
        except CatalogLoadError as e:
            logger.error(
                "ACNR catalog 不可用(全量): project=%s cycle=%s error=%s",
                project_id,
                cycle_code,
                e,
            )
            raise AcnrCatalogUnavailableError(
                f"ACNR catalog 不可用，无法生成 bulk manifest（cycle={cycle_code}）",
                cause=e,
            ) from e

        # 构建 catalog 元数据映射 (取 sheet_name/origin)
        catalog_by_addr_id: dict[str, dict[str, Any]] = {}
        try:
            for sheet in list_sheets(cycle=cycle_code, import_export_only=True):
                aid = sheet.get("addr_id", "")
                if aid:
                    catalog_by_addr_id[aid] = sheet
        except CatalogLoadError as e:
            logger.error(
                "ACNR catalog 不可用(catalog): cycle=%s error=%s",
                cycle_code,
                e,
            )
            raise AcnrCatalogUnavailableError(
                f"ACNR catalog 不可用，无法生成 bulk manifest（cycle={cycle_code}）",
                cause=e,
            ) from e

        # ─── 可导出条目 → files[] ─────────────────────────────────
        for entry in export_entries:
            addr_id = entry.get("addr_id", "")
            cat_entry = catalog_by_addr_id.get(addr_id, {})

            sheet_name = cat_entry.get("sheet_name", entry.get("sheet_code", ""))
            origin = cat_entry.get("origin", "standard")
            parent_wp_code = entry.get("parent_wp_code", "")

            zip_path = _build_zip_path(
                cycle=cycle_code,
                parent_wp_code=parent_wp_code,
                sheet_code=entry.get("sheet_code", ""),
                sheet_name=sheet_name,
                mode=mode,
            )

            file_entry = ManifestFileEntry(
                addr_id=addr_id,
                wp_code=parent_wp_code,
                parent_wp_code=parent_wp_code,
                sheet_code=entry.get("sheet_code", ""),
                sheet_name=sheet_name,
                origin=origin,
                api_prefix=entry.get("api_prefix", ""),
                item_id=entry.get("item_id", ""),
                storage_field=entry.get("storage_field", "remark"),
                wp_id=entry.get("wp_id"),
                import_order=entry.get("import_order", 999),
                depends_on_sheets=entry.get("depends_on_sheets", []),
                zip_path=zip_path,
                sha256="",  # 导出时由 ZipAssembler 填入
            )
            manifest.files.append(file_entry)

        # ─── 差集 → skipped[] ─────────────────────────────────────
        for entry in all_entries:
            addr_id = entry.get("addr_id", "")
            if addr_id in export_addr_ids:
                continue  # 已在 files[] 中

            cat_entry = catalog_by_addr_id.get(addr_id, {})
            sheet_name = cat_entry.get("sheet_name", entry.get("sheet_code", ""))
            parent_wp_code = entry.get("parent_wp_code", "")

            # 确定 skip_reason
            skip_reason = "resolve_instance_miss"
            if entry.get("wp_id") is not None:
                skip_reason = "unknown"

            skipped_entry = ManifestSkippedEntry(
                addr_id=addr_id,
                sheet_code=entry.get("sheet_code", ""),
                sheet_name=sheet_name,
                parent_wp_code=parent_wp_code,
                skip_reason=skip_reason,
            )
            manifest.skipped.append(skipped_entry)

    return manifest


# ---------------------------------------------------------------------------
# Helper: 获取所有可用循环
# ---------------------------------------------------------------------------


def _get_all_cycles() -> list[str]:
    """从 ACNR catalog 获取所有含 I/E 的循环列表。"""
    from app.services.acnr.catalog import list_sheets

    all_ie_sheets = list_sheets(import_export_only=True)
    cycles_seen: set[str] = set()
    for s in all_ie_sheets:
        c = s.get("cycle", "")
        if c:
            cycles_seen.add(c.upper())

    return sorted(cycles_seen)
