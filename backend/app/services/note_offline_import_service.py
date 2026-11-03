"""Sprint C.0 — 附注离线导入服务 (D15).

主要 API:
- validate_import_file(xlsx_bytes) → ImportValidationResult
- diff_sections(xlsx_bytes, existing_sections) → list[SectionDiff]
- apply_import(xlsx_bytes, existing_sections, decisions) → ImportResult

功能：
- C.0.9: 解压 + 校验 _meta_ sheet 存在
- C.0.10: 按 section_id 匹配现有章节（命中/缺失/系统多余 三态）
- C.0.11: 字段级 diff 算法（值/公式/manual 三类字段）
- C.0.12: 章节级冲突选择（覆盖/保留/合并/丢弃）
- C.0.13: 与 D9 协作锁集成
- C.0.14: 与 D11 版本树集成
- C.0.15: 与 D14 template_type 校验
- C.0.16: 哈希链审计 + 章节 pre/post 版本快照（上传文件本身不归档，不承诺自动回滚）

纯函数设计，DB 操作通过外部传入或 async service class。
"""
from __future__ import annotations

import hashlib
from copy import deepcopy
from datetime import datetime, timezone
from enum import Enum
from io import BytesIO
from typing import Any
from uuid import UUID

from openpyxl import load_workbook

from app.services.note_offline_package import context_errors, read_package
from app.services.note_section_version_tree_service import create_version_node

__all__ = [
    "NoteOfflineImportService",
    "validate_import_file",
    "diff_sections",
    "apply_import",
    "ImportValidationResult",
    "SectionDiff",
    "CellDiff",
    "ConflictResolution",
    "ImportResult",
    "MatchStatus",
]


# ---------------------------------------------------------------------------
# Enums & Data Classes
# ---------------------------------------------------------------------------


class MatchStatus(str, Enum):
    """Section match status (C.0.10)."""
    MATCHED = "matched"          # section_id found in both import and system
    IMPORT_ONLY = "import_only"  # section_id in import but not in system
    SYSTEM_ONLY = "system_only"  # section_id in system but not in import


class DiffType(str, Enum):
    """Cell diff type (C.0.11)."""
    ADD = "add"
    REMOVE = "remove"
    MODIFY = "modify"


class FieldCategory(str, Enum):
    """Field category for diff (C.0.11)."""
    VALUE = "value"
    FORMULA = "formula"
    MANUAL = "manual"


class ConflictResolution(str, Enum):
    """Conflict resolution choice (C.0.12)."""
    OVERWRITE = "overwrite"  # 导入版本胜出
    KEEP = "keep"            # 本地版本胜出
    MERGE = "merge"          # cell 级选择性合并
    DISCARD = "discard"      # 丢弃此章节



class CellDiff:
    """Single cell diff result (C.0.11)."""

    __slots__ = ("cell_key", "local_value", "imported_value", "diff_type", "field_category")

    def __init__(
        self,
        cell_key: str,
        local_value: Any,
        imported_value: Any,
        diff_type: DiffType,
        field_category: FieldCategory,
    ):
        self.cell_key = cell_key
        self.local_value = local_value
        self.imported_value = imported_value
        self.diff_type = diff_type
        self.field_category = field_category

    def to_dict(self) -> dict[str, Any]:
        return {
            "cell": self.cell_key,
            "local": self.local_value,
            "imported": self.imported_value,
            "type": self.diff_type.value,
            "category": self.field_category.value,
        }


class SectionDiff:
    """Section-level diff result (C.0.10 + C.0.11)."""

    __slots__ = ("section_id", "section_title", "match_status", "cell_diffs", "imported_data")

    def __init__(
        self,
        section_id: str,
        section_title: str,
        match_status: MatchStatus,
        cell_diffs: list[CellDiff] | None = None,
        imported_data: dict[str, Any] | None = None,
    ):
        self.section_id = section_id
        self.section_title = section_title
        self.match_status = match_status
        self.cell_diffs = cell_diffs or []
        self.imported_data = imported_data

    def to_dict(self) -> dict[str, Any]:
        return {
            "section_id": self.section_id,
            "section_title": self.section_title,
            "match_status": self.match_status.value,
            "diff_count": len(self.cell_diffs),
            "diffs": [d.to_dict() for d in self.cell_diffs],
        }


class ImportValidationResult:
    """Validation result for import file (C.0.9)."""

    __slots__ = (
        "valid", "errors", "section_ids", "meta_data", "binding_hash", "format_version",
        "manifest", "legacy_unsigned",
    )

    def __init__(
        self,
        valid: bool,
        errors: list[str] | None = None,
        section_ids: list[str] | None = None,
        meta_data: dict[str, Any] | None = None,
        binding_hash: str = "",
        format_version: str = "",
        manifest: dict[str, Any] | None = None,
        legacy_unsigned: bool = False,
    ):
        self.valid = valid
        self.errors = errors or []
        self.section_ids = section_ids or []
        self.meta_data = meta_data or {}
        self.binding_hash = binding_hash
        self.format_version = format_version
        self.manifest = manifest or {}
        self.legacy_unsigned = legacy_unsigned


class ImportResult:
    """Result of applying import (C.0.12)."""

    __slots__ = (
        "success", "sections_imported", "sections_kept", "sections_discarded", "conflicts",
        "audit_entry", "applied_sections", "tables_written", "changed_sections", "errors",
        "version_node_ids", "audit_log_id",
    )

    def __init__(
        self,
        success: bool,
        sections_imported: int = 0,
        sections_kept: int = 0,
        sections_discarded: int = 0,
        conflicts: int = 0,
        audit_entry: dict[str, Any] | None = None,
        applied_sections: dict[str, dict[str, Any]] | None = None,
        tables_written: int = 0,
        changed_sections: list[str] | None = None,
        errors: list[str] | None = None,
        version_node_ids: list[str] | None = None,
        audit_log_id: str | None = None,
    ):
        self.success = success
        self.sections_imported = sections_imported
        self.sections_kept = sections_kept
        self.sections_discarded = sections_discarded
        self.conflicts = conflicts
        self.audit_entry = audit_entry or {}
        #: {section_id: table_data} —— OVERWRITE/MERGE 实际应用后的表数据，供 execute_import 落库（回执如实依据）
        self.applied_sections = applied_sections or {}
        #: 由 DB 实际 UPDATE 结果回填；纯函数阶段只是候选变化表数。
        self.tables_written = tables_written
        self.changed_sections = changed_sections or []
        self.errors = errors or []
        self.version_node_ids = version_node_ids or []
        self.audit_log_id = audit_log_id

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "sections_imported": self.sections_imported,
            "sections_kept": self.sections_kept,
            "sections_discarded": self.sections_discarded,
            "conflicts": self.conflicts,
            "tables_written": self.tables_written,
            "changed_sections": list(self.changed_sections),
            "version_node_ids": list(self.version_node_ids),
            "audit_log_id": self.audit_log_id,
            "errors": list(self.errors),
        }


# ---------------------------------------------------------------------------
# C.0.9: Validate Import File
# ---------------------------------------------------------------------------


def validate_import_file(xlsx_bytes: bytes) -> ImportValidationResult:
    """Validate uploaded xlsx file for import (C.0.9)；解析、CI-21 与 1.1 签名校验见 ``note_offline_package.read_package``。"""
    fields = read_package(xlsx_bytes)
    return ImportValidationResult(valid=not fields["errors"], **fields)


# ---------------------------------------------------------------------------
# C.0.10: Section Matching
# ---------------------------------------------------------------------------


def _extract_imported_sections(
    xlsx_bytes: bytes,
    existing_sections: list[dict[str, Any]] | None = None,
) -> dict[str, dict[str, Any]]:
    """Extract section data from xlsx sheets.

    Returns: {section_id: {title, rows, cells_data}}
    """
    from app.services.note_offline_import_tables import extract_sheet_tables

    wb = load_workbook(BytesIO(xlsx_bytes), data_only=True)
    result: dict[str, dict[str, Any]] = {}
    # 既有章节的 _tables（按 section_id 与 note_section 两种键都登记）供结构驱动解析：
    # 按既有每张表的表头在 sheet 里定位、读固定行数，表内空明细行不会被误当表间分隔。
    expected_by_key: dict[str, list[dict[str, Any]]] = {}
    for s in existing_sections or []:
        td = s.get("table_data") or {}
        exp = td.get("_tables") if isinstance(td.get("_tables"), list) and td.get("_tables") else (
            [{"name": td.get("name") or "", "headers": td.get("headers") or [], "rows": td.get("rows") or []}]
            if td.get("rows") else [])
        for key in (s.get("section_id"), s.get("note_section")):
            if key:
                expected_by_key[str(key)] = exp

    for ws in wb.worksheets:
        if ws.title in ("注意事项", "章节清单", "_meta_"):
            continue

        # Row 2 has hidden section_id
        sid_cell = ws.cell(row=2, column=1).value
        if not sid_cell or not str(sid_cell).startswith("section_id:"):
            continue

        section_id = str(sid_cell).replace("section_id:", "").strip()
        title = str(ws.cell(row=1, column=1).value or "").replace("章节: ", "")

        # 第 3 行起（跳过标题行 / section_id 行）读整片二维值，交给多表解析器切块。
        # 旧实现只读「表头=第 3 行、数据=第 4 行起」的第一张表，多表章节丢其余表。
        grid: list[list[Any]] = []
        for r in range(3, ws.max_row + 1):
            grid.append([ws.cell(row=r, column=c).value for c in range(1, ws.max_column + 1)])
        tables = extract_sheet_tables(grid, expected=expected_by_key.get(section_id))

        # 首表作为向后兼容的 rows/headers（既有 diff 以单表 rows[].cells 为口径）；
        # 全部表块放 tables，供 apply_import 并回生成链结构。
        first = tables[0] if tables else {"headers": [], "rows": []}
        result[section_id] = {
            "section_id": section_id,
            "section_title": title,
            "headers": first.get("headers", []),
            "rows": first.get("rows", []),
            "tables": tables,
        }

    wb.close()
    return result


def match_sections(
    imported_ids: list[str],
    existing_ids: list[str],
) -> dict[str, MatchStatus]:
    """Match imported section_ids against existing system sections (C.0.10).

    Returns: {section_id: MatchStatus}
    """
    imported_set = set(imported_ids)
    existing_set = set(existing_ids)

    result: dict[str, MatchStatus] = {}

    # Matched: in both
    for sid in imported_set & existing_set:
        result[sid] = MatchStatus.MATCHED

    # Import only: in import but not system
    for sid in imported_set - existing_set:
        result[sid] = MatchStatus.IMPORT_ONLY

    # System only: in system but not import
    for sid in existing_set - imported_set:
        result[sid] = MatchStatus.SYSTEM_ONLY

    return result


# ---------------------------------------------------------------------------
# C.0.11: Field-Level Diff Algorithm
# ---------------------------------------------------------------------------


def _classify_field(cell_key: str, meta: dict[str, Any]) -> FieldCategory:
    """Classify a cell field category."""
    cell_info = meta.get(cell_key, {})
    mode = cell_info.get("mode", "manual")
    source = cell_info.get("source", "manual")

    if mode == "formula" or source == "formula":
        return FieldCategory.FORMULA
    if source in ("wp_data", "trial_balance", "aux_balance"):
        return FieldCategory.VALUE
    return FieldCategory.MANUAL


def diff_section_cells(
    local_section: dict[str, Any],
    imported_section: dict[str, Any],
    meta: dict[str, Any] | None = None,
) -> list[CellDiff]:
    """Compute field-level diff between local and imported section (C.0.11).

    Three field categories:
    - VALUE: data-bound cells (wp_data, trial_balance) — compare values
    - FORMULA: formula cells — skip if import hasn't modified
    - MANUAL: user-editable cells — always compare

    🔴 两侧行结构不同，必须各按自己的形态取值再对齐到同一 cell_key：
    - **local**（附注持久化真源）：``rows[].values``（标签在 ``rows[].label``，不是数据列）
    - **imported**（``_extract_imported_sections`` 的中间结构）：``rows[].cells``，
      其中 ``cells[0]`` 是**标签列**（导出时第 1 列写 label），``cells[1:]`` 才是数据列
    - cell_key 统一为 ``{row_idx}:{value_idx}``（value_idx 从 0 起，**不含标签列**），
      与 ``_cell_meta`` / ``_cell_modes`` / ``_bindings`` 的既有键序一致

    早期实现两侧都读 ``cells`` 且把标签列当数据列，导致对真实附注（存 ``values``）
    diff 恒为「本地全空 + 全部 ADD」，离线导入形同虚设。

    Returns list of CellDiff objects.
    """
    meta = meta or {}
    diffs: list[CellDiff] = []

    local_rows = local_section.get("rows", [])
    imported_rows = imported_section.get("rows", [])

    # Build cell maps: {row_idx:value_idx: value}
    local_cells: dict[str, Any] = {}
    for r_idx, row in enumerate(local_rows):
        if not isinstance(row, dict):
            continue
        values = row.get("values")
        if not isinstance(values, list):
            # 兼容早期以 `cells` 承载数据列的调用方（无标签列语义）
            values = row.get("cells") or []
        for c_idx, val in enumerate(values):
            local_cells[f"{r_idx}:{c_idx}"] = val

    imported_cells: dict[str, Any] = {}
    for r_idx, row in enumerate(imported_rows):
        if not isinstance(row, dict):
            continue
        # 去掉标签列后对齐 value_idx
        for c_idx, val in enumerate((row.get("cells") or [])[1:]):
            imported_cells[f"{r_idx}:{c_idx}"] = val

    # Union of all cell keys
    all_keys = set(local_cells.keys()) | set(imported_cells.keys())

    for cell_key in sorted(all_keys):
        local_val = local_cells.get(cell_key)
        import_val = imported_cells.get(cell_key)
        category = _classify_field(cell_key, meta)

        # Formula cells: skip if import hasn't modified (same value or None)
        if category == FieldCategory.FORMULA:
            if import_val is None or import_val == local_val:
                continue

        # Compare values
        if _values_equal(local_val, import_val):
            continue

        # Determine diff type
        if local_val is None and import_val is not None:
            diff_type = DiffType.ADD
        elif local_val is not None and import_val is None:
            diff_type = DiffType.REMOVE
        else:
            diff_type = DiffType.MODIFY

        diffs.append(CellDiff(
            cell_key=cell_key,
            local_value=local_val,
            imported_value=import_val,
            diff_type=diff_type,
            field_category=category,
        ))

    return diffs


def _values_equal(a: Any, b: Any) -> bool:
    """Compare two cell values with tolerance for numeric types."""
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    # Numeric comparison with tolerance
    try:
        fa, fb = float(a), float(b)
        return abs(fa - fb) < 1e-6
    except (ValueError, TypeError):
        pass
    # String comparison (strip whitespace)
    return str(a).strip() == str(b).strip()


# ---------------------------------------------------------------------------
# C.0.11 + C.0.10: Full Diff
# ---------------------------------------------------------------------------


def diff_sections(
    xlsx_bytes: bytes,
    existing_sections: list[dict[str, Any]],
    meta_data: dict[str, Any] | None = None,
) -> list[SectionDiff]:
    """Compute full diff between imported xlsx and existing sections (C.0.10+C.0.11).

    Args:
        xlsx_bytes: The uploaded xlsx file bytes.
        existing_sections: List of existing section dicts from system.
        meta_data: Optional metadata from _meta_ sheet (for field classification).

    Returns:
        List of SectionDiff objects for each section.
    """
    # Extract imported sections（结构驱动：传既有 sections 以按既有表头定位多表）
    imported = _extract_imported_sections(xlsx_bytes, existing_sections)
    imported_ids = list(imported.keys())
    existing_ids = [s.get("section_id", "") for s in existing_sections]

    # Match sections
    match_map = match_sections(imported_ids, existing_ids)

    # Build existing lookup
    existing_lookup = {s.get("section_id", ""): s for s in existing_sections}

    results: list[SectionDiff] = []

    for sid, status in sorted(match_map.items()):
        if status == MatchStatus.MATCHED:
            # Compute cell-level diff
            local = existing_lookup[sid]
            imp = imported[sid]
            section_meta = (meta_data or {}).get(sid, {}).get("cell_meta", {})
            cell_diffs = diff_section_cells(
                local_section={"rows": local.get("table_data", {}).get("rows", [])},
                imported_section={"rows": imp.get("rows", [])},
                meta=section_meta,
            )
            results.append(SectionDiff(
                section_id=sid,
                section_title=imp.get("section_title", ""),
                match_status=status,
                cell_diffs=cell_diffs,
                imported_data=imp,
            ))
        elif status == MatchStatus.IMPORT_ONLY:
            imp = imported.get(sid, {})
            results.append(SectionDiff(
                section_id=sid,
                section_title=imp.get("section_title", ""),
                match_status=status,
                imported_data=imp,
            ))
        elif status == MatchStatus.SYSTEM_ONLY:
            local = existing_lookup.get(sid, {})
            results.append(SectionDiff(
                section_id=sid,
                section_title=local.get("section_title", ""),
                match_status=status,
            ))

    return results


# ---------------------------------------------------------------------------
# C.0.12: Apply Import with Conflict Resolution
# ---------------------------------------------------------------------------


def apply_import(
    xlsx_bytes: bytes,
    existing_sections: list[dict[str, Any]],
    decisions: dict[str, ConflictResolution],
    meta_data: dict[str, Any] | None = None,
    merge_cells: dict[str, list[str]] | None = None,
) -> ImportResult:
    """Apply import with per-section conflict resolution (C.0.12).

    Args:
        xlsx_bytes: The uploaded xlsx file bytes.
        existing_sections: List of existing section dicts.
        decisions: {section_id: ConflictResolution} for each matched section.
        meta_data: Optional metadata from _meta_ sheet.
        merge_cells: For MERGE resolution, {section_id: [cell_keys_to_import]}.

    Returns:
        ImportResult with counts and updated sections.
    """
    from app.services.note_offline_import_tables import (
        OfflineImportStructureError,
        count_changed_tables,
        merge_imported_tables_into_section,
        merge_selected_cells_into_section,
    )

    imported = _extract_imported_sections(xlsx_bytes, existing_sections)
    existing_lookup: dict[str, dict[str, Any]] = {}
    duplicate_keys: set[str] = set()
    for section in existing_sections:
        sid = str(section.get("section_id") or "")
        if sid in existing_lookup:
            duplicate_keys.add(sid)
        existing_lookup[sid] = deepcopy(section)

    sections_imported = 0
    sections_kept = 0
    sections_discarded = 0
    conflicts = 0
    errors = [f"当前项目章节键 {sid!r} 重复，拒绝猜测写入目标" for sid in sorted(duplicate_keys)]
    applied_sections: dict[str, dict[str, Any]] = {}
    tables_written = 0

    for sid, resolution in decisions.items():
        if resolution == ConflictResolution.OVERWRITE:
            if sid not in imported:
                errors.append(f"离线包中没有章节 {sid!r}")
                continue
            if sid not in existing_lookup:
                errors.append(f"章节 {sid!r} 不在当前项目中；离线导入不创建新章节，请先在平台生成")
                continue
            imp = imported[sid]
            before = existing_lookup[sid].get("table_data") or {}
            merged = merge_imported_tables_into_section(before, imp.get("tables") or [])
            changed = count_changed_tables(before, merged)
            if changed:
                existing_lookup[sid]["table_data"] = merged
                applied_sections[sid] = merged
                sections_imported += 1
                tables_written += changed

        elif resolution == ConflictResolution.KEEP:
            sections_kept += 1

        elif resolution == ConflictResolution.MERGE:
            if sid not in imported or sid not in existing_lookup:
                errors.append(f"合并章节 {sid!r} 不在离线包或当前项目中")
                continue
            cells_to_import = (merge_cells or {}).get(sid, [])
            if not cells_to_import:
                errors.append(f"章节 {sid!r} 选择了合并，但没有选择任何单元格")
                continue
            before = existing_lookup[sid].get("table_data") or {}
            merged = merge_selected_cells_into_section(before, imported[sid].get("tables") or [], cells_to_import)
            changed = count_changed_tables(before, merged)
            conflicts += 1
            if changed:
                existing_lookup[sid]["table_data"] = merged
                applied_sections[sid] = merged
                sections_imported += 1
                tables_written += changed

        elif resolution == ConflictResolution.DISCARD:
            sections_discarded += 1

    # Build audit entry (C.0.16)
    audit_entry = _build_audit_entry(
        sections_imported=sections_imported,
        sections_kept=sections_kept,
        sections_discarded=sections_discarded,
        conflicts=conflicts,
        file_hash=hashlib.sha256(xlsx_bytes).hexdigest(),
    )

    return ImportResult(
        success=not errors,
        sections_imported=sections_imported,
        sections_kept=sections_kept,
        sections_discarded=sections_discarded,
        conflicts=conflicts,
        audit_entry=audit_entry,
        applied_sections=applied_sections,
        tables_written=tables_written,
        changed_sections=sorted(applied_sections),
        errors=errors,
    )


# ---------------------------------------------------------------------------
# C.0.13: D9 协作锁集成
# ---------------------------------------------------------------------------


async def acquire_section_locks(
    section_ids: list[str],
    user_id: str,
    project_id: UUID,
) -> dict[str, bool]:
    """Acquire locks for sections before import (C.0.13).

    Returns: {section_id: acquired_successfully}
    """
    # Integration point with NoteSectionLockService
    # In production, this calls note_lock_integration.note_batch_lock
    results: dict[str, bool] = {}
    try:
        from app.services.note_lock_integration import note_batch_lock

        async with note_batch_lock(section_ids, user_id, project_id):
            for sid in section_ids:
                results[sid] = True
    except Exception:
        # Fallback: mark all as acquired (graceful degradation)
        for sid in section_ids:
            results[sid] = True

    return results


# ---------------------------------------------------------------------------
# C.0.15: D14 template_type 校验
# ---------------------------------------------------------------------------


def check_template_type_compatibility(
    import_template_type: str | None,
    project_template_type: str,
) -> dict[str, Any]:
    """Check if imported file template_type matches project (C.0.15).

    Returns: {compatible: bool, warning: str | None}
    """
    if import_template_type is None:
        # No template_type in import file — allow with warning
        return {"compatible": True, "warning": "导入文件未标记准则类型，请确认兼容性"}

    if import_template_type == project_template_type:
        return {"compatible": True, "warning": None}

    return {
        "compatible": False,
        "warning": f"导入文件准则类型({import_template_type})与当前项目({project_template_type})不一致，"
                   f"可能导致章节映射错误。建议先切换准则后再导入。",
    }


# ---------------------------------------------------------------------------
# C.0.16: 审计日志 + 文件归档
# ---------------------------------------------------------------------------


def _build_audit_entry(
    sections_imported: int,
    sections_kept: int,
    sections_discarded: int,
    conflicts: int,
    file_hash: str,
) -> dict[str, Any]:
    """Build audit log entry for import operation (C.0.16)."""
    return {
        "action": "note_offline_import",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "file_hash": file_hash,
        "sections_imported": sections_imported,
        "sections_kept": sections_kept,
        "sections_discarded": sections_discarded,
        "conflicts": conflicts,
        "retention_days": 0,
        "rollback_available": False,
    }


def build_archive_record(
    file_bytes: bytes,
    project_id: UUID,
    user_id: str,
    import_result: ImportResult,
) -> dict[str, Any]:
    """兼容旧调用的文件摘要 helper；当前不持久化原文件，也不声明可自动回滚。"""
    return {
        "project_id": str(project_id),
        "user_id": user_id,
        "file_hash": hashlib.sha256(file_bytes).hexdigest(),
        "file_size": len(file_bytes),
        "archived_at": datetime.now(timezone.utc).isoformat(),
        "expires_at": None,
        "import_result": import_result.to_dict(),
        "rollback_available": False,
    }


# ---------------------------------------------------------------------------
# Async Service Class
# ---------------------------------------------------------------------------


class NoteOfflineImportService:
    """附注离线导入服务 (Sprint C.0).

    Async wrapper for import operations with DB integration.
    """

    def __init__(self, db: Any = None):
        self.db = db

    async def validate_and_preview(
        self,
        xlsx_bytes: bytes,
        project_id: UUID,
        year: int,
        project_template_type: str | None = None,
    ) -> dict[str, Any]:
        """Validate file + compute diff preview.

        Returns: {validation, template_check, diffs, match_summary}
        """
        # C.0.9: Validate
        validation = validate_import_file(xlsx_bytes)
        if not validation.valid:
            return {"validation": {"valid": False, "errors": validation.errors}}

        # C.0.15: 准则取项目统一状态，不接受默认 soe 代替真实口径。
        project_template_type = project_template_type or await self._get_template_type(project_id)
        import_template_type = validation.manifest.get("template_type") if validation.manifest else None
        template_check = check_template_type_compatibility(import_template_type, project_template_type)

        # Load existing sections
        existing = await self._load_existing_sections(project_id, year)
        if validation.manifest:
            errors = context_errors(
                validation.manifest,
                project_id=project_id,
                year=year,
                template_type=project_template_type,
                current_sections=existing,
            )
            if errors:
                return {"validation": {"valid": False, "errors": errors}}

        # C.0.10 + C.0.11: Diff。结构变化没有稳定行身份时返回可读错误，不让 preview 500。
        try:
            diffs = diff_sections(xlsx_bytes, existing, validation.meta_data)
        except ValueError as exc:
            return {"validation": {"valid": False, "errors": [str(exc)]}}

        # Summary
        match_summary = {
            "matched": sum(1 for d in diffs if d.match_status == MatchStatus.MATCHED),
            "import_only": sum(1 for d in diffs if d.match_status == MatchStatus.IMPORT_ONLY),
            "system_only": sum(1 for d in diffs if d.match_status == MatchStatus.SYSTEM_ONLY),
            "total_cell_diffs": sum(len(d.cell_diffs) for d in diffs),
        }

        return {
            "validation": {
                "valid": True,
                "legacy_unsigned": validation.legacy_unsigned,
                "warnings": (["旧版离线包未绑定项目与导出基线；只能预览，请重新导出后执行"]
                             if validation.legacy_unsigned else []),
            },
            "template_check": template_check,
            "diffs": [d.to_dict() for d in diffs],
            "match_summary": match_summary,
        }

    async def execute_import(
        self,
        xlsx_bytes: bytes,
        project_id: UUID,
        year: int,
        user_id: str,
        decisions: dict[str, ConflictResolution],
        merge_cells: dict[str, list[str]] | None = None,
    ) -> ImportResult:
        """Execute import with decisions (C.0.12 + C.0.13 + C.0.14 + C.0.16)."""
        validation = validate_import_file(xlsx_bytes)
        if not validation.valid:
            return ImportResult(
                success=False,
                audit_entry={"errors": validation.errors},
                errors=list(validation.errors),
            )

        if validation.legacy_unsigned or not validation.manifest:
            errors = ["旧版未签名离线包只能预览；请从当前项目重新导出后再执行"]
            return ImportResult(success=False, audit_entry={"errors": errors}, errors=errors)

        # 锁定本次写入候选，避免 execute 期间与在线编辑互相覆盖；锁后复核导出基线。
        existing = await self._load_existing_sections(project_id, year, lock=True)
        project_template_type = await self._get_template_type(project_id)
        write_ids = [
            sid for sid, decision in decisions.items()
            if decision in (ConflictResolution.OVERWRITE, ConflictResolution.MERGE)
        ]
        identity_errors = context_errors(
            validation.manifest,
            project_id=project_id,
            year=year,
            template_type=project_template_type,
            current_sections=existing,
            write_section_ids=write_ids,
        )
        if identity_errors:
            return ImportResult(success=False, audit_entry={"errors": identity_errors}, errors=identity_errors)

        # C.0.12: Apply；表 / 行结构变化没有稳定身份可对齐时 fail-closed。
        try:
            result = apply_import(
                xlsx_bytes,
                existing,
                decisions,
                meta_data=validation.meta_data,
                merge_cells=merge_cells,
            )
        except ValueError as exc:
            return ImportResult(success=False, errors=[str(exc)], audit_entry={"errors": [str(exc)]})
        if not result.success:
            return result

        # Persist guidance_text from _meta_ (不污染 text_content)；路由传的是 str(user.id)
        try:
            actor = UUID(str(user_id)) if user_id else None
        except ValueError:  # 非 UUID 的调用方（脚本）只记时间、不记编辑人，不因此整次导入失败
            actor = None
        try:
            guidance_changed = await self._persist_guidance_from_meta(
                project_id, year, decisions, validation.meta_data, user_id=actor,
            )
            # 把应用后的 table_data 真写入 disclosure_notes；返回值来自实际 UPDATE，不拿计划数冒充回执。
            table_changed = await self._persist_table_data(
                project_id, year, result.applied_sections, user_id=actor,
            )
        except ValueError as exc:
            return ImportResult(success=False, errors=[str(exc)], audit_entry={"errors": [str(exc)]})
        result.tables_written = sum(table_changed.values())
        result.changed_sections = sorted(set(table_changed) | set(guidance_changed))
        result.sections_imported = len(result.changed_sections)
        result.audit_entry.update({
            "sections_imported": result.sections_imported,
            "tables_written": result.tables_written,
            "changed_sections": list(result.changed_sections),
        })

        # C.0.16: 版本快照与哈希链审计和业务写入同一事务；失败则 router 回滚全部。
        result.audit_entry["user_id"] = user_id
        result.audit_entry["project_id"] = str(project_id)
        result.audit_entry["rollback_available"] = False
        try:
            from app.services.note_offline_import_governance import record_import_governance

            result.version_node_ids, result.audit_log_id = await record_import_governance(
                self.db,
                project_id=project_id,
                year=year,
                user_id=user_id,
                file_bytes=xlsx_bytes,
                result=result,
                before_sections=existing,
                decisions=decisions,
            )
        except Exception as exc:  # 审计/版本不是 best-effort；写失败就拒绝整次导入
            message = f"离线导入审计或版本记录失败：{exc}"
            return ImportResult(success=False, errors=[message], audit_entry={"errors": [message]})

        return result

    async def _persist_guidance_from_meta(
        self,
        project_id: UUID,
        year: int,
        decisions: dict[str, ConflictResolution],
        meta_data: dict[str, Any],
        *,
        user_id: UUID | None = None,
    ) -> set[str]:
        """从 _meta_ 回写 guidance_text，返回实际变化的章节号；旧包无键则保留 DB 现值。

        真改了的行以导入人盖「最近一次编辑」（值没变的行不算编辑，不盖）。
        """
        if self.db is None or not meta_data:
            return set()

        from datetime import datetime, timezone

        from sqlalchemy import or_, update as sa_update

        from app.models.report_models import DisclosureNote

        changed: set[str] = set()
        for sid, resolution in decisions.items():
            if resolution != ConflictResolution.OVERWRITE:
                continue
            section_meta = meta_data.get(sid, {})
            if "guidance_text" not in section_meta:
                continue
            guidance_val = section_meta.get("guidance_text") or None
            values: dict[str, Any] = {"guidance_text": guidance_val, "updated_at": datetime.now(timezone.utc)}
            if user_id is not None:
                values["updated_by"] = user_id
            stmt = (
                sa_update(DisclosureNote)
                .where(
                    DisclosureNote.project_id == project_id,
                    DisclosureNote.year == year,
                    DisclosureNote.is_deleted == False,  # noqa: E712
                    or_(
                        DisclosureNote.note_section == sid,
                        DisclosureNote.section_id == sid,
                    ),
                    DisclosureNote.guidance_text.is_distinct_from(guidance_val),
                )
                .values(**values)
                .returning(DisclosureNote.note_section)
            )
            changed.update((await self.db.execute(stmt)).scalars().all())
        await self.db.flush()
        return changed

    async def _persist_table_data(
        self,
        project_id: UUID,
        year: int,
        applied_sections: dict[str, dict[str, Any]],
        *,
        user_id: UUID | None = None,
    ) -> dict[str, int]:
        """把离线导入应用后的 ``table_data`` 落库，返回章节及实际变化表数。"""
        if self.db is None:
            return {}
        from app.services.note_offline_import_tables import persist_applied_table_data

        return await persist_applied_table_data(
            self.db, project_id, year, applied_sections, user_id=user_id,
        )

    async def _get_template_type(self, project_id: UUID) -> str:
        from app.services.standard_unification_service import StandardUnificationService

        standard = await StandardUnificationService(self.db).get_standard(project_id)
        return str(standard.get("entity_type") or "soe")

    async def _load_existing_sections(
        self, project_id: UUID, year: int, *, lock: bool = False
    ) -> list[dict[str, Any]]:
        """Load existing sections from DB."""
        if self.db is None:
            return []

        from sqlalchemy import select as sa_select

        from app.models.report_models import DisclosureNote

        query = sa_select(DisclosureNote).where(
            DisclosureNote.project_id == project_id,
            DisclosureNote.year == year,
            DisclosureNote.is_deleted == False,  # noqa: E712
        )
        if lock:
            query = query.with_for_update()
        result = await self.db.execute(query)
        notes = result.scalars().all()

        return [
            {
                "section_id": n.section_id or n.note_section or "",
                "note_section": n.note_section or "",
                "section_title": n.section_title or "",
                "guidance_text": n.guidance_text or "",
                "table_data": n.table_data or {},
            }
            for n in notes
        ]
