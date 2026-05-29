"""Sprint C.0 — 附注离线导出服务 (D15).

主要 API:
- export_sections(project_id, year, section_ids, ...) → (xlsx_bytes, sha256_hash)

功能：
- C.0.1: 按 section_id list 选择章节子集
- C.0.2: xlsx 包结构（注意事项 + 章节清单 + N 章节 + _meta_）
- C.0.3: 4 色语义渲染 + DataValidation 锁定
- C.0.4: 单元格批注（公式说明 + 数据源）
- C.0.5: _meta_ sheet（base64+gzip 压缩 binding/formula/row_meta）
- C.0.6: 注意事项 sheet 模板
- C.0.7: 章节清单 TOC
- C.0.8: 可选 AES 加密 + 文件 hash

纯函数设计，DB 操作通过外部传入数据。
"""
from __future__ import annotations

import base64
import gzip
import hashlib
import json
from copy import deepcopy
from datetime import datetime, timezone
from io import BytesIO
from typing import Any
from uuid import UUID

from openpyxl import Workbook
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Border, Font, PatternFill, Protection, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

__all__ = ["NoteOfflineExportService", "export_sections_to_xlsx"]


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# 4-color semantic fills (C.0.3)
FILL_EDITABLE = PatternFill(start_color="FFFFFF00", end_color="FFFFFF00", fill_type="solid")  # 黄=可填
FILL_FORMULA = PatternFill(start_color="FFD9D9D9", end_color="FFD9D9D9", fill_type="solid")  # 灰=公式
FILL_LOCKED = PatternFill(start_color="FFFF9999", end_color="FFFF9999", fill_type="solid")  # 红=锁定
FILL_REQUIRED = PatternFill(start_color="FF99FF99", end_color="FF99FF99", fill_type="solid")  # 绿=必填


FONT_HEADER = Font(bold=True, size=12)
FONT_TITLE = Font(bold=True, size=14)
FONT_NORMAL = Font(size=10)
ALIGN_CENTER = Alignment(horizontal="center", vertical="center", wrap_text=True)
ALIGN_LEFT = Alignment(horizontal="left", vertical="center", wrap_text=True)
BORDER_THIN = Border(
    left=Side(style="thin"),
    right=Side(style="thin"),
    top=Side(style="thin"),
    bottom=Side(style="thin"),
)

# Max Excel sheet name length
MAX_SHEET_NAME = 31


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _truncate_sheet_name(name: str) -> str:
    """Truncate sheet name to Excel 31-char limit, replace invalid chars."""
    # Replace invalid Excel sheet name characters
    for ch in r"[]:*?/\\":
        name = name.replace(ch, "_")
    if len(name) > MAX_SHEET_NAME:
        name = name[: MAX_SHEET_NAME - 2] + ".."
    return name


def _classify_cell(cell_meta: dict[str, Any]) -> str:
    """Classify cell type for coloring.

    Returns: 'editable' | 'formula' | 'locked' | 'required'
    """
    source = cell_meta.get("source", "manual")
    is_required = cell_meta.get("is_required", False)
    mode = cell_meta.get("mode", "manual")

    if mode == "formula" or source == "formula":
        return "formula"
    if source in ("wp_data", "trial_balance", "aux_balance", "aux_ledger_aging", "consol_aggregation"):
        return "locked"
    if is_required:
        return "required"
    return "editable"


def _get_fill_for_type(cell_type: str) -> PatternFill:
    """Get fill color for cell type."""
    return {
        "editable": FILL_EDITABLE,
        "formula": FILL_FORMULA,
        "locked": FILL_LOCKED,
        "required": FILL_REQUIRED,
    }.get(cell_type, FILL_EDITABLE)


def _compute_sha256(data: bytes) -> str:
    """Compute SHA-256 hex digest."""
    return hashlib.sha256(data).hexdigest()


def _compress_meta(meta_dict: dict[str, Any]) -> str:
    """Compress metadata dict to base64+gzip string (C.0.5)."""
    json_bytes = json.dumps(meta_dict, ensure_ascii=False, default=str).encode("utf-8")
    compressed = gzip.compress(json_bytes)
    return base64.b64encode(compressed).decode("ascii")


def _decompress_meta(encoded: str) -> dict[str, Any]:
    """Decompress base64+gzip string back to dict."""
    compressed = base64.b64decode(encoded.encode("ascii"))
    json_bytes = gzip.decompress(compressed)
    return json.loads(json_bytes.decode("utf-8"))


def _encrypt_bytes(data: bytes, password: str) -> bytes:
    """AES encrypt bytes using Fernet (C.0.8)."""
    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

    # Derive key from password
    salt = b"note_offline_export_salt_v1"  # Fixed salt for deterministic key derivation
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=100_000)
    key = base64.urlsafe_b64encode(kdf.derive(password.encode("utf-8")))
    f = Fernet(key)
    return f.encrypt(data)


def _decrypt_bytes(data: bytes, password: str) -> bytes:
    """AES decrypt bytes using Fernet."""
    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

    salt = b"note_offline_export_salt_v1"
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=100_000)
    key = base64.urlsafe_b64encode(kdf.derive(password.encode("utf-8")))
    f = Fernet(key)
    return f.decrypt(data)


# ---------------------------------------------------------------------------
# C.0.6: 注意事项 Sheet 模板
# ---------------------------------------------------------------------------


def _build_instructions_sheet(ws: Worksheet, context: dict[str, Any]) -> None:
    """Fill the 注意事项 sheet with 7-section usage guide (C.0.6)."""
    project_name = context.get("project_name", "{项目名称}")
    year = context.get("year", "{年度}")
    exporter_name = context.get("exporter_name", "{导出人}")
    export_time = context.get("export_time", _now_str())
    section_count = context.get("section_count", 0)
    partner_name = context.get("partner_name", "{partner_name}")
    partner_email = context.get("partner_email", "{partner_email}")
    partner_phone = context.get("partner_phone", "{partner_phone}")

    ws.column_dimensions["A"].width = 80

    lines = [
        ("═" * 50, FONT_TITLE),
        ("  附注离线编辑包  —  使用说明", FONT_TITLE),
        ("═" * 50, FONT_TITLE),
        ("", None),
        ("【1. 文件用途】", FONT_HEADER),
        (f"  本文件为「{project_name} - {year} 年报附注」离线协作编辑包，", FONT_NORMAL),
        (f"  共 {section_count} 章节，由 {exporter_name} 于 {export_time} 生成。", FONT_NORMAL),
        ("", None),
        ("【2. 单元格颜色含义】", FONT_HEADER),
        ("  ⬛ 黄底 = 您可填写的数据（如金额 / 客户名称 / 描述）", FONT_NORMAL),
        ("  ⬛ 灰底 = 系统自动计算（公式驱动，请勿修改）", FONT_NORMAL),
        ("  ⬛ 红底 = 锁定单元格（如来自试算表 / 底稿，禁止改动）", FONT_NORMAL),
        ("  ⬛ 绿底 = 必填项（导入时若为空将告警）", FONT_NORMAL),
        ("", None),
        ("【3. 动态行操作】", FONT_HEADER),
        ('  在带 ★ 标识的"动态行"区域：', FONT_NORMAL),
        ("    - 复制现有行 → 在两个标记行之间粘贴 → 填写新数据", FONT_NORMAL),
        ("    - 不要在 [DYNAMIC_END:xxx] 标记下方插入数据", FONT_NORMAL),
        ("    - 删除行：选中整行 → 右键删除（不要清空内容留空行）", FONT_NORMAL),
        ("", None),
        ("【4. 公式区域】", FONT_HEADER),
        ("  灰底单元格的公式见单元格批注（鼠标悬停查看）。", FONT_NORMAL),
        ("  如需修改公式逻辑，请在对应黄底原始数据修改后由系统重算。", FONT_NORMAL),
        ("", None),
        ("【5. 文件名 / sheet 名规则】", FONT_HEADER),
        ("  ⚠ 不要重命名文件 / 不要修改 sheet 名（含隐藏的章节 ID 用于回传匹配）", FONT_NORMAL),
        ("  ⚠ 不要删除 _meta_ 隐藏 sheet（删了无法导回）", FONT_NORMAL),
        ("", None),
        ("【6. 完成后回传】", FONT_HEADER),
        (f"  填写完成后，将本文件发回 {partner_email}，", FONT_NORMAL),
        ("  partner 在系统内点「附注 → 一键导入」即可合并您的填报内容。", FONT_NORMAL),
        ("", None),
        ("【7. 注意事项】", FONT_HEADER),
        ("  - 不要修改 sheet 顺序（导入按 section_id 匹配，顺序无关，但避免误删）", FONT_NORMAL),
        ("  - 不要新增 sheet（新 sheet 不会被导入）", FONT_NORMAL),
        ("  - 文字段落（如会计政策）可改但建议保留模板措辞", FONT_NORMAL),
        ("  - 多人协作时合并冲突由 partner 在系统内决策", FONT_NORMAL),
        ("", None),
        ("【联系人】", FONT_HEADER),
        (f"  partner: {partner_name}  邮箱: {partner_email}  电话: {partner_phone}", FONT_NORMAL),
        ("═" * 50, FONT_TITLE),
    ]

    for row_idx, (text, font) in enumerate(lines, start=1):
        cell = ws.cell(row=row_idx, column=1, value=text)
        if font:
            cell.font = font
        cell.alignment = ALIGN_LEFT


# ---------------------------------------------------------------------------
# C.0.7: 章节清单 TOC Sheet
# ---------------------------------------------------------------------------


def _build_toc_sheet(ws: Worksheet, sections: list[dict[str, Any]]) -> None:
    """Build TOC sheet with section list (C.0.7)."""
    headers = ["序号", "章节标题", "完成度(%)", "必填项数", "section_id"]
    col_widths = [8, 40, 12, 12, 30]

    # Header row
    for col_idx, (header, width) in enumerate(zip(headers, col_widths), start=1):
        cell = ws.cell(row=1, column=col_idx, value=header)
        cell.font = FONT_HEADER
        cell.alignment = ALIGN_CENTER
        cell.border = BORDER_THIN
        ws.column_dimensions[get_column_letter(col_idx)].width = width

    # Hide section_id column (column E)
    ws.column_dimensions["E"].hidden = True

    # Data rows
    for row_idx, section in enumerate(sections, start=2):
        section_id = section.get("section_id", "")
        title = section.get("section_title", "")
        completeness = _calc_completeness(section)
        required_count = _count_required_cells(section)

        ws.cell(row=row_idx, column=1, value=row_idx - 1).border = BORDER_THIN
        ws.cell(row=row_idx, column=2, value=title).border = BORDER_THIN
        ws.cell(row=row_idx, column=3, value=completeness).border = BORDER_THIN
        ws.cell(row=row_idx, column=4, value=required_count).border = BORDER_THIN
        ws.cell(row=row_idx, column=5, value=section_id).border = BORDER_THIN


def _calc_completeness(section: dict[str, Any]) -> int:
    """Calculate section completeness percentage."""
    table_data = section.get("table_data", {})
    rows = table_data.get("rows", [])
    if not rows:
        return 0

    total_cells = 0
    filled_cells = 0
    for row in rows:
        cells = row.get("cells", [])
        for cell_val in cells:
            total_cells += 1
            if cell_val is not None and cell_val != "" and cell_val != "-":
                filled_cells += 1

    return int((filled_cells / total_cells * 100) if total_cells > 0 else 0)


def _count_required_cells(section: dict[str, Any]) -> int:
    """Count required cells in section."""
    cell_meta = section.get("_cell_meta", {})
    return sum(1 for m in cell_meta.values() if m.get("is_required", False))


# ---------------------------------------------------------------------------
# C.0.2/C.0.3/C.0.4: Section Sheet Builder
# ---------------------------------------------------------------------------


def _build_section_sheet(
    ws: Worksheet,
    section: dict[str, Any],
    include_formulas: bool = True,
    include_provenance: bool = True,
) -> None:
    """Build a single section sheet with data + 4-color + comments (C.0.2/3/4)."""
    section_id = section.get("section_id", "")
    title = section.get("section_title", "")
    table_data = section.get("table_data", {})
    headers = table_data.get("headers", [])
    rows = table_data.get("rows", [])
    cell_meta = section.get("_cell_meta", {})
    formulas = section.get("_formulas", {})
    provenance = section.get("_cell_provenance", {})

    # Row 1: section title (metadata)
    ws.cell(row=1, column=1, value=f"章节: {title}")
    ws.cell(row=1, column=1).font = FONT_TITLE

    # Row 2: section_id (hidden row for import matching)
    ws.cell(row=2, column=1, value=f"section_id:{section_id}")
    ws.row_dimensions[2].hidden = True

    # Row 3: headers
    for col_idx, header in enumerate(headers, start=1):
        cell = ws.cell(row=3, column=col_idx, value=header)
        cell.font = FONT_HEADER
        cell.alignment = ALIGN_CENTER
        cell.border = BORDER_THIN
        ws.column_dimensions[get_column_letter(col_idx)].width = max(12, len(str(header)) * 2)

    # Data rows (starting row 4)
    for row_idx, row_data in enumerate(rows, start=4):
        row_type = row_data.get("row_type", "data")
        cells = row_data.get("cells", [])
        label = row_data.get("label", "")

        # Dynamic row marker
        is_dynamic = row_type.startswith("dynamic_")

        for col_idx, cell_val in enumerate(cells, start=1):
            cell = ws.cell(row=row_idx, column=col_idx, value=cell_val)
            cell.border = BORDER_THIN

            # Cell key for metadata lookup
            cell_key = f"{row_idx - 4}:{col_idx - 1}"

            # Determine cell type and apply fill (C.0.3)
            meta = cell_meta.get(cell_key, {})
            cell_type = _classify_cell(meta)
            cell.fill = _get_fill_for_type(cell_type)

            # Protection: lock formula/locked cells
            if cell_type in ("formula", "locked"):
                cell.protection = Protection(locked=True)
            else:
                cell.protection = Protection(locked=False)

            # Comments (C.0.4)
            comment_parts = []
            if include_formulas and cell_key in formulas:
                formula_info = formulas[cell_key]
                expr = formula_info.get("expression", "")
                comment_parts.append(f"公式: {expr}")

            if include_provenance and cell_key in provenance:
                prov = provenance[cell_key]
                source = prov.get("source", "")
                if source == "wp_data":
                    wp_code = prov.get("wp_code", "")
                    comment_parts.append(f"数据源: wp_data ({wp_code})")
                elif source == "trial_balance":
                    accounts = prov.get("account_codes", [])
                    comment_parts.append(f"数据源: 试算表 ({', '.join(accounts)})")
                elif source != "manual" and source:
                    comment_parts.append(f"数据源: {source}")

            if comment_parts:
                cell.comment = Comment("\n".join(comment_parts), "系统")

        # Mark dynamic rows with ★ in first cell
        if is_dynamic and cells:
            existing = ws.cell(row=row_idx, column=1).value or ""
            ws.cell(row=row_idx, column=1, value=f"★ {existing}")

    # Enable sheet protection (allow editing unlocked cells)
    ws.protection.sheet = True
    ws.protection.enable()


# ---------------------------------------------------------------------------
# C.0.5: _meta_ Sheet
# ---------------------------------------------------------------------------


def _build_meta_sheet(ws: Worksheet, sections: list[dict[str, Any]]) -> None:
    """Build hidden _meta_ sheet with compressed metadata (C.0.5)."""
    # Collect all metadata
    meta_payload: dict[str, Any] = {}
    for section in sections:
        sid = section.get("section_id", "")
        meta_payload[sid] = {
            "bindings": section.get("_bindings", {}),
            "formulas": section.get("_formulas", {}),
            "row_meta": section.get("_row_meta", []),
            "cell_modes": section.get("_cell_modes", {}),
            "cell_meta": section.get("_cell_meta", {}),
            "dynamic_regions": section.get("_dynamic_regions", []),
        }

    # Compress and store
    compressed = _compress_meta(meta_payload)

    # A1: key label
    ws.cell(row=1, column=1, value="meta_data")
    ws.cell(row=1, column=2, value=compressed)

    # A2: section_id list (for CI-21 validation)
    section_ids = [s.get("section_id", "") for s in sections]
    ws.cell(row=2, column=1, value="section_ids")
    ws.cell(row=2, column=2, value=json.dumps(section_ids, ensure_ascii=False))

    # A3: binding hash (for CI-21 validation)
    binding_hash = _compute_sha256(compressed.encode("utf-8"))
    ws.cell(row=3, column=1, value="binding_hash")
    ws.cell(row=3, column=2, value=binding_hash)

    # A4: export timestamp
    ws.cell(row=4, column=1, value="export_time")
    ws.cell(row=4, column=2, value=_now_str())

    # A5: version
    ws.cell(row=5, column=1, value="format_version")
    ws.cell(row=5, column=2, value="1.0")


# ---------------------------------------------------------------------------
# Core Export Function (C.0.1 + C.0.2 orchestration)
# ---------------------------------------------------------------------------


def export_sections_to_xlsx(
    sections: list[dict[str, Any]],
    *,
    section_ids: list[str] | None = None,
    include_formulas: bool = True,
    include_provenance: bool = True,
    password: str | None = None,
    exporter_name: str = "",
    partner_info: dict[str, str] | None = None,
    project_name: str = "",
    year: int | str = "",
) -> tuple[bytes, str]:
    """Export disclosure note sections to xlsx bytes.

    Args:
        sections: List of section dicts (from DB or service layer).
        section_ids: Optional filter — only export these section_ids.
        include_formulas: Include formula expressions in comments.
        include_provenance: Include data source info in comments.
        password: Optional AES encryption password.
        exporter_name: Name of the person exporting.
        partner_info: Dict with partner_name, partner_email, partner_phone.
        project_name: Project display name.
        year: Fiscal year.

    Returns:
        (xlsx_bytes, sha256_hash) — if password provided, bytes are encrypted.
    """
    # C.0.1: Filter sections by section_id list
    if section_ids is not None:
        id_set = set(section_ids)
        filtered = [s for s in sections if s.get("section_id", "") in id_set]
    else:
        filtered = list(sections)

    if not filtered:
        filtered = []

    # Create workbook
    wb = Workbook()

    # Remove default sheet
    wb.remove(wb.active)

    # C.0.6: 注意事项 sheet (first)
    ws_instructions = wb.create_sheet("注意事项")
    context = {
        "project_name": project_name,
        "year": year,
        "exporter_name": exporter_name,
        "export_time": _now_str(),
        "section_count": len(filtered),
        "partner_name": (partner_info or {}).get("partner_name", ""),
        "partner_email": (partner_info or {}).get("partner_email", ""),
        "partner_phone": (partner_info or {}).get("partner_phone", ""),
    }
    _build_instructions_sheet(ws_instructions, context)

    # C.0.7: 章节清单 sheet (second)
    ws_toc = wb.create_sheet("章节清单")
    _build_toc_sheet(ws_toc, filtered)

    # C.0.2: Section sheets
    for section in filtered:
        section_id = section.get("section_id", "unknown")
        title = section.get("section_title", section_id)
        sheet_name = _truncate_sheet_name(title)

        # Ensure unique sheet name
        existing_names = [ws.title for ws in wb.worksheets]
        if sheet_name in existing_names:
            sheet_name = _truncate_sheet_name(f"{title[:25]}_{section_id[:5]}")

        ws_section = wb.create_sheet(sheet_name)
        _build_section_sheet(ws_section, section, include_formulas, include_provenance)

    # C.0.5: _meta_ sheet (last, hidden)
    ws_meta = wb.create_sheet("_meta_")
    _build_meta_sheet(ws_meta, filtered)
    ws_meta.sheet_state = "hidden"

    # Save to bytes
    buffer = BytesIO()
    wb.save(buffer)
    xlsx_bytes = buffer.getvalue()

    # C.0.8: Compute hash
    file_hash = _compute_sha256(xlsx_bytes)

    # C.0.8: Optional AES encryption
    if password:
        xlsx_bytes = _encrypt_bytes(xlsx_bytes, password)

    return xlsx_bytes, file_hash


# ---------------------------------------------------------------------------
# Async Service Class (wraps pure function with DB access)
# ---------------------------------------------------------------------------


class NoteOfflineExportService:
    """附注离线导出服务 (Sprint C.0).

    Async wrapper that loads sections from DB then delegates to pure export function.
    """

    def __init__(self, db: Any = None):
        """Initialize with optional DB session."""
        self.db = db

    async def export_sections(
        self,
        project_id: UUID,
        year: int,
        section_ids: list[str] | None = None,
        include_formulas: bool = True,
        include_provenance: bool = True,
        password: str | None = None,
        exporter_name: str = "",
        partner_info: dict[str, str] | None = None,
    ) -> tuple[bytes, str]:
        """Export sections from DB to xlsx.

        Returns:
            (xlsx_bytes, sha256_hash)
        """
        # Load sections from DB
        sections = await self._load_sections(project_id, year, section_ids)
        project_name = await self._get_project_name(project_id)

        return export_sections_to_xlsx(
            sections,
            section_ids=section_ids,
            include_formulas=include_formulas,
            include_provenance=include_provenance,
            password=password,
            exporter_name=exporter_name,
            partner_info=partner_info,
            project_name=project_name,
            year=year,
        )

    async def _load_sections(
        self,
        project_id: UUID,
        year: int,
        section_ids: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Load disclosure note sections from DB."""
        if self.db is None:
            return []

        from sqlalchemy import select as sa_select

        from app.models.report_models import DisclosureNote

        query = sa_select(DisclosureNote).where(
            DisclosureNote.project_id == project_id,
            DisclosureNote.year == year,
            DisclosureNote.is_deleted == False,  # noqa: E712
        )
        if section_ids:
            query = query.where(DisclosureNote.section_id.in_(section_ids))

        result = await self.db.execute(query)
        notes = result.scalars().all()

        sections = []
        for note in notes:
            section_dict = {
                "section_id": note.section_id or note.note_section or "",
                "section_title": note.section_title or "",
                "table_data": note.table_data or {},
                "_formulas": (note.table_data or {}).get("_formulas", {}),
                "_cell_provenance": (note.table_data or {}).get("_cell_provenance", {}),
                "_cell_meta": (note.table_data or {}).get("_cell_meta", {}),
                "_cell_modes": (note.table_data or {}).get("_cell_modes", {}),
                "_bindings": (note.table_data or {}).get("_bindings", {}),
                "_row_meta": (note.table_data or {}).get("_row_meta", []),
                "_dynamic_regions": (note.table_data or {}).get("_dynamic_regions", []),
            }
            sections.append(section_dict)

        return sections

    async def _get_project_name(self, project_id: UUID) -> str:
        """Get project display name."""
        if self.db is None:
            return ""
        try:
            from sqlalchemy import select as sa_select

            from app.models.models import Project

            result = await self.db.execute(
                sa_select(Project.name).where(Project.id == project_id)
            )
            row = result.scalar_one_or_none()
            return row or ""
        except Exception:
            return ""
