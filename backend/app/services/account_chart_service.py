"""科目表管理服务 — 标准科目加载 + 客户科目导入

Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.5
"""

import csv
import io
import json
from pathlib import Path
from uuid import UUID

from fastapi import HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_platform_models import (
    AccountCategory,
    AccountChart,
    AccountDirection,
    AccountSource,
)
from app.models.audit_platform_schemas import (
    AccountChartResponse,
    AccountImportResult,
    AccountTreeNode,
)

# Seed data directory
_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"

# Accounting standard → JSON file mapping
_STANDARD_FILES = {
    "enterprise": "standard_account_chart.json",
}

# Account code prefix → category mapping
_CODE_CATEGORY_MAP: dict[str, AccountCategory] = {
    "1": AccountCategory.asset,
    "2": AccountCategory.liability,
    "3": AccountCategory.equity,
    "4": AccountCategory.expense,   # cost accounts
    "5": AccountCategory.revenue,   # revenue + expense (5001-5111=revenue, 5401+=expense)
}

# More precise: 5001-5399 = revenue, 5400+ = expense
_EXPENSE_CODES_START = "54"


def _infer_category(code: str) -> AccountCategory:
    """Infer account category from code prefix."""
    if not code:
        return AccountCategory.asset
    first = code[0]
    if first == "5":
        # 5001-5311 = revenue, 5401+ = expense
        if code[:2] >= _EXPENSE_CODES_START:
            return AccountCategory.expense
        return AccountCategory.revenue
    return _CODE_CATEGORY_MAP.get(first, AccountCategory.asset)


def _infer_direction(category: AccountCategory) -> AccountDirection:
    """Infer default direction from category."""
    if category in (AccountDirection.credit,):
        return AccountDirection.credit
    if category in (AccountCategory.liability, AccountCategory.equity, AccountCategory.revenue):
        return AccountDirection.credit
    return AccountDirection.debit


def _infer_level(code: str, parent_code: str | None) -> int:
    """Infer account level from code length or parent."""
    if parent_code:
        return 2
    if len(code) <= 4:
        return 1
    return 2


# ---------------------------------------------------------------------------
# load_standard_template
# ---------------------------------------------------------------------------


async def load_standard_template(
    project_id: UUID,
    accounting_standard: str,
    db: AsyncSession,
) -> list[AccountChartResponse]:
    """Load standard account chart template into account_chart table.

    Reads the JSON seed data file and bulk inserts into account_chart
    with source=standard.

    Validates: Requirements 2.1, 2.2
    """
    file_name = _STANDARD_FILES.get(accounting_standard)
    if not file_name:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的会计准则: {accounting_standard}，当前仅支持: {', '.join(_STANDARD_FILES.keys())}",
        )

    json_path = _DATA_DIR / file_name
    if not json_path.exists():
        raise HTTPException(
            status_code=500,
            detail=f"标准科目表数据文件不存在: {file_name}",
        )

    with open(json_path, encoding="utf-8-sig") as f:
        data = json.load(f)

    accounts_data = data.get("accounts", [])
    if not accounts_data:
        raise HTTPException(status_code=500, detail="标准科目表数据为空")

    # Check if standard accounts already loaded for this project
    existing = await db.execute(
        select(AccountChart).where(
            AccountChart.project_id == project_id,
            AccountChart.source == AccountSource.standard,
            AccountChart.is_deleted == False,  # noqa: E712
        ).limit(1)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=400,
            detail="该项目已加载标准科目表，请勿重复加载",
        )

    # Bulk insert
    records: list[AccountChart] = []
    for item in accounts_data:
        record = AccountChart(
            project_id=project_id,
            account_code=item["code"],
            account_name=item["name"],
            direction=AccountDirection(item["direction"]),
            level=item["level"],
            category=AccountCategory(item["category"]),
            parent_code=item.get("parent_code"),
            source=AccountSource.standard,
        )
        records.append(record)

    db.add_all(records)
    await db.flush()

    # Return response models
    result = []
    for r in records:
        result.append(AccountChartResponse(
            id=r.id,
            project_id=r.project_id,
            account_code=r.account_code,
            account_name=r.account_name,
            direction=r.direction,
            level=r.level,
            category=r.category,
            parent_code=r.parent_code,
            source=r.source,
            created_at=r.created_at,
        ))

    await db.commit()
    return result


# ---------------------------------------------------------------------------
# import_client_chart
# ---------------------------------------------------------------------------


async def import_client_chart(
    project_id: UUID,
    file: UploadFile,
    db: AsyncSession,
    column_mapping: dict[str, str | None] | None = None,
) -> AccountImportResult:
    """Import client account chart from Excel/CSV file.

    Parses account_code, account_name, direction, parent_code.
    Validates required columns (account_code + account_name).
    Writes to account_chart with source=client.

    Args:
        column_mapping: Optional user-confirmed mapping {original_header: standard_field}.
                        If provided, overrides the default _COLUMN_MAP normalization.

    Validates: Requirements 2.3, 2.4, 2.5
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="未提供文件")

    filename_lower = file.filename.lower()
    content = await file.read()

    rows: list[dict] = []

    if filename_lower.endswith(".csv"):
        rows = _parse_csv(content)
    elif filename_lower.endswith((".xlsx", ".xls")):
        rows = _parse_excel(content)
    else:
        raise HTTPException(
            status_code=400,
            detail="不支持的文件格式，请上传 Excel (.xlsx/.xls) 或 CSV (.csv) 文件",
        )

    if not rows:
        raise HTTPException(status_code=400, detail="文件中未解析到有效数据")

    # Apply user-provided column mapping or default normalization
    if column_mapping:
        normalized_rows = _apply_custom_mapping(rows, column_mapping)
    else:
        # Validate required columns (legacy path)
        first_row = rows[0]
        missing_cols = []
        if "account_code" not in first_row and "科目编码" not in first_row:
            missing_cols.append("account_code/科目编码")
        if "account_name" not in first_row and "科目名称" not in first_row:
            missing_cols.append("account_name/科目名称")

        if missing_cols:
            raise HTTPException(
                status_code=400,
                detail=f"缺少必填列: {', '.join(missing_cols)}",
            )
        normalized_rows = _normalize_columns(rows)

    # Validate required fields after normalization
    if normalized_rows:
        sample = normalized_rows[0]
        missing = []
        if "account_code" not in sample:
            missing.append("account_code/科目编码")
        if "account_name" not in sample:
            missing.append("account_name/科目名称")
        if missing and column_mapping:
            raise HTTPException(
                status_code=400,
                detail=f"列映射中缺少必填字段: {', '.join(missing)}",
            )

    # Build records
    records: list[AccountChart] = []
    errors: list[str] = []
    by_category: dict[str, int] = {}

    for i, row in enumerate(normalized_rows, start=2):  # row 2+ (header is row 1)
        code = str(row.get("account_code", "")).strip()
        name = str(row.get("account_name", "")).strip()

        if not code or not name:
            errors.append(f"第{i}行: 科目编码或名称为空，已跳过")
            continue

        parent_code = str(row.get("parent_code", "")).strip() or None
        direction_str = str(row.get("direction", "")).strip().lower()

        # Parse direction
        if direction_str in ("debit", "借", "借方"):
            direction = AccountDirection.debit
        elif direction_str in ("credit", "贷", "贷方"):
            direction = AccountDirection.credit
        else:
            # Infer from code
            category = _infer_category(code)
            direction = _infer_direction(category)

        category = _infer_category(code)
        level = _infer_level(code, parent_code)

        record = AccountChart(
            project_id=project_id,
            account_code=code,
            account_name=name,
            direction=direction,
            level=level,
            category=category,
            parent_code=parent_code,
            source=AccountSource.client,
        )
        records.append(record)

        cat_name = category.value
        by_category[cat_name] = by_category.get(cat_name, 0) + 1

    if not records:
        raise HTTPException(status_code=400, detail="未解析到有效科目数据")

    db.add_all(records)
    await db.commit()

    return AccountImportResult(
        total_imported=len(records),
        by_category=by_category,
        errors=errors,
    )


# ---------------------------------------------------------------------------
# get_standard_chart / get_client_chart
# ---------------------------------------------------------------------------


async def get_standard_chart(
    project_id: UUID,
    db: AsyncSession,
) -> list[AccountChartResponse]:
    """Get standard account chart for a project."""
    result = await db.execute(
        select(AccountChart).where(
            AccountChart.project_id == project_id,
            AccountChart.source == AccountSource.standard,
            AccountChart.is_deleted == False,  # noqa: E712
        ).order_by(AccountChart.account_code)
    )
    accounts = result.scalars().all()
    return [
        AccountChartResponse.model_validate(a)
        for a in accounts
    ]


async def get_client_chart_tree(
    project_id: UUID,
    db: AsyncSession,
) -> dict[str, list[AccountTreeNode]]:
    """Get client account chart as tree structure grouped by category.

    Validates: Requirements 2.6
    """
    result = await db.execute(
        select(AccountChart).where(
            AccountChart.project_id == project_id,
            AccountChart.source == AccountSource.client,
            AccountChart.is_deleted == False,  # noqa: E712
        ).order_by(AccountChart.account_code)
    )
    accounts = result.scalars().all()

    # Group by category
    by_category: dict[str, list[AccountChart]] = {}
    for a in accounts:
        cat = a.category.value
        by_category.setdefault(cat, []).append(a)

    # Build tree per category
    tree: dict[str, list[AccountTreeNode]] = {}
    for cat, accts in by_category.items():
        tree[cat] = _build_tree(accts)

    return tree


def _build_tree(accounts: list[AccountChart]) -> list[AccountTreeNode]:
    """Build tree from flat account list using parent_code."""
    nodes: dict[str, AccountTreeNode] = {}
    roots: list[AccountTreeNode] = []

    # Create all nodes
    for a in accounts:
        node = AccountTreeNode(
            account_code=a.account_code,
            account_name=a.account_name,
            direction=a.direction,
            level=a.level,
            category=a.category,
            parent_code=a.parent_code,
            children=[],
        )
        nodes[a.account_code] = node

    # Link children to parents
    for a in accounts:
        node = nodes[a.account_code]
        if a.parent_code and a.parent_code in nodes:
            nodes[a.parent_code].children.append(node)
        else:
            roots.append(node)

    return roots


# ---------------------------------------------------------------------------
# File parsing helpers
# ---------------------------------------------------------------------------

# Column name mapping: Chinese → English (extended for all file types)
_COLUMN_MAP = {
    # 科目信息
    "科目编码": "account_code",
    "科目代码": "account_code",
    "编码": "account_code",
    "科目名称": "account_name",
    "名称": "account_name",
    "借贷方向": "direction",
    "方向": "direction",
    "余额方向": "direction",
    "父科目编码": "parent_code",
    "上级科目编码": "parent_code",
    "上级编码": "parent_code",
    "parent_code": "parent_code",
    "account_code": "account_code",
    "account_name": "account_name",
    "direction": "direction",
    # 凭证信息
    "凭证日期": "voucher_date",
    "日期": "voucher_date",
    "voucher_date": "voucher_date",
    "凭证号": "voucher_no",
    "凭证编号": "voucher_no",
    "voucher_no": "voucher_no",
    "摘要": "summary",
    "summary": "summary",
    "对方科目": "counterpart_account",
    "counterpart_account": "counterpart_account",
    "制单人": "preparer",
    "preparer": "preparer",
    # 金额信息
    "借方金额": "debit_amount",
    "借方": "debit_amount",
    "debit": "debit_amount",
    "debit_amount": "debit_amount",
    "贷方金额": "credit_amount",
    "贷方": "credit_amount",
    "credit": "credit_amount",
    "credit_amount": "credit_amount",
    "期初余额": "opening_balance",
    "年初余额": "opening_balance",
    "opening": "opening_balance",
    "opening_balance": "opening_balance",
    "期末余额": "closing_balance",
    "closing": "closing_balance",
    "closing_balance": "closing_balance",
    # 辅助核算
    "辅助类型": "aux_type",
    "aux_type": "aux_type",
    "辅助编码": "aux_code",
    "aux_code": "aux_code",
    "辅助名称": "aux_name",
    "aux_name": "aux_name",
}


# ---------------------------------------------------------------------------
# preview_file — file preview + auto column mapping
# ---------------------------------------------------------------------------


def _guess_file_type(mapped_cols: set[str]) -> str:
    """Guess file type based on which standard columns are present."""
    has_account_code = "account_code" in mapped_cols
    has_account_name = "account_name" in mapped_cols
    has_voucher_date = "voucher_date" in mapped_cols
    has_voucher_no = "voucher_no" in mapped_cols
    has_debit = "debit_amount" in mapped_cols
    has_credit = "credit_amount" in mapped_cols
    has_opening = "opening_balance" in mapped_cols
    has_closing = "closing_balance" in mapped_cols
    has_aux_type = "aux_type" in mapped_cols
    has_aux_code = "aux_code" in mapped_cols

    if has_aux_type and has_aux_code:
        return "aux_balance"
    if has_voucher_date and has_voucher_no and (has_debit or has_credit):
        return "ledger"
    if has_account_code and (has_opening or has_closing):
        return "balance"
    if has_account_code and has_account_name and not has_debit and not has_credit:
        return "account_chart"
    return "unknown"


async def preview_file(file: UploadFile, skip_rows: int = 2) -> dict:
    """Parse file, return first 20 rows per sheet + auto-matched column mapping.

    Args:
        skip_rows: 跳过前N行（默认2行，第3行作为表头）

    Returns:
        {
            "sheets": [
                {
                    "sheet_name": "Sheet1",
                    "headers": ["col1", "col2", ...],
                    "rows": [...],  # first 20 rows (after skipping)
                    "total_rows": 150,
                    "column_mapping": {"col1": "account_code", ...},
                    "file_type_guess": "ledger"
                },
                ...
            ],
            "active_sheet": 0
        }
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="未提供文件")

    filename_lower = file.filename.lower()
    content = await file.read()

    if filename_lower.endswith(".csv"):
        rows = _parse_csv(content, skip_rows=skip_rows)
        if not rows:
            raise HTTPException(status_code=400, detail="文件中未解析到有效数据")
        headers = list(rows[0].keys())
        column_mapping = {h: _COLUMN_MAP.get(str(h).strip()) for h in headers}
        mapped_cols = {v for v in column_mapping.values() if v}
        return {
            "sheets": [{
                "sheet_name": "CSV",
                "headers": headers,
                "rows": rows[:20],
                "total_rows": len(rows),
                "column_mapping": column_mapping,
                "file_type_guess": _guess_file_type(mapped_cols),
            }],
            "active_sheet": 0,
        }
    elif filename_lower.endswith((".xlsx", ".xls")):
        sheets_data = _parse_excel_multi_sheet(content, skip_rows=skip_rows)
        if not sheets_data:
            raise HTTPException(status_code=400, detail="文件中未解析到有效数据")
        sheets = []
        for sheet_name, rows in sheets_data.items():
            if not rows:
                continue
            headers = list(rows[0].keys())
            column_mapping = {h: _COLUMN_MAP.get(str(h).strip()) for h in headers}
            mapped_cols = {v for v in column_mapping.values() if v}
            sheets.append({
                "sheet_name": sheet_name,
                "headers": headers,
                "rows": rows[:20],
                "total_rows": len(rows),
                "column_mapping": column_mapping,
                "file_type_guess": _guess_file_type(mapped_cols),
            })
        if not sheets:
            raise HTTPException(status_code=400, detail="所有工作表均无有效数据")
        return {"sheets": sheets, "active_sheet": 0}
    else:
        raise HTTPException(status_code=400, detail="不支持的文件格式")


def _normalize_columns(rows: list[dict]) -> list[dict]:
    """Normalize column names from Chinese to English."""
    normalized = []
    for row in rows:
        new_row = {}
        for key, value in row.items():
            if key is None:
                continue
            key_str = str(key).strip()
            mapped = _COLUMN_MAP.get(key_str, key_str)
            new_row[mapped] = value
        normalized.append(new_row)
    return normalized


def _apply_custom_mapping(rows: list[dict], mapping: dict[str, str | None]) -> list[dict]:
    """Apply user-confirmed column mapping to rows."""
    normalized = []
    for row in rows:
        new_row = {}
        for key, value in row.items():
            if key is None:
                continue
            key_str = str(key).strip()
            target = mapping.get(key_str)
            if target:  # skip None / "(忽略)"
                new_row[target] = value
        normalized.append(new_row)
    return normalized


def _parse_csv(content: bytes, skip_rows: int = 0) -> list[dict]:
    """Parse CSV file content into list of dicts."""
    for encoding in ("utf-8-sig", "gbk", "utf-8"):
        try:
            text = content.decode(encoding)
            break
        except (UnicodeDecodeError, ValueError):
            continue
    else:
        raise HTTPException(status_code=400, detail="无法识别文件编码，请使用 UTF-8 或 GBK 编码")

    lines = text.strip().splitlines()
    if skip_rows > 0 and len(lines) > skip_rows:
        lines = lines[skip_rows:]
    reader = csv.DictReader(io.StringIO("\n".join(lines)))
    return list(reader)


def _parse_excel(content: bytes, skip_rows: int = 0) -> list[dict]:
    """Parse Excel active sheet into list of dicts (backward compatible)."""
    try:
        import openpyxl
    except ImportError:
        raise HTTPException(status_code=500, detail="服务器未安装 openpyxl 库")

    wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    ws = wb.active
    if ws is None:
        raise HTTPException(status_code=400, detail="Excel 文件中没有工作表")

    result = _parse_sheet(ws, skip_rows=skip_rows)
    wb.close()
    return result


def _parse_excel_multi_sheet(content: bytes, skip_rows: int = 0) -> dict[str, list[dict]]:
    """Parse ALL sheets in an Excel file, each returning list of dicts."""
    try:
        import openpyxl
    except ImportError:
        raise HTTPException(status_code=500, detail="服务器未安装 openpyxl 库")

    wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    sheets: dict[str, list[dict]] = {}
    for ws_name in wb.sheetnames:
        ws = wb[ws_name]
        rows = _parse_sheet(ws, skip_rows=skip_rows)
        sheets[ws_name] = rows
    wb.close()
    return sheets


def _parse_sheet(ws, skip_rows: int = 0) -> list[dict]:
    """Parse a single worksheet into list of dicts, skipping first N rows."""
    rows_iter = ws.iter_rows(values_only=True)

    # Skip rows
    for _ in range(skip_rows):
        try:
            next(rows_iter)
        except StopIteration:
            return []

    # Header row (the row after skipped rows)
    try:
        header = next(rows_iter)
    except StopIteration:
        return []

    headers = [str(h).strip() if h else f"col_{i}" for i, h in enumerate(header)]

    result = []
    for row in rows_iter:
        if all(cell is None for cell in row):
            continue
        row_dict = {}
        for i, cell in enumerate(row):
            if i < len(headers):
                row_dict[headers[i]] = str(cell) if cell is not None else ""
        result.append(row_dict)
    return result
