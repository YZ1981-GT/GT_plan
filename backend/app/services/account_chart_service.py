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
) -> AccountImportResult:
    """Import client account chart from Excel/CSV file.

    Parses account_code, account_name, direction, parent_code.
    Validates required columns (account_code + account_name).
    Writes to account_chart with source=client.

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

    # Validate required columns
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

    # Normalize column names
    normalized_rows = _normalize_columns(rows)

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

# Column name mapping: Chinese → English
_COLUMN_MAP = {
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
}


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


def _parse_csv(content: bytes) -> list[dict]:
    """Parse CSV file content into list of dicts."""
    # Try utf-8-sig first, then gbk
    for encoding in ("utf-8-sig", "gbk", "utf-8"):
        try:
            text = content.decode(encoding)
            break
        except (UnicodeDecodeError, ValueError):
            continue
    else:
        raise HTTPException(status_code=400, detail="无法识别文件编码，请使用 UTF-8 或 GBK 编码")

    reader = csv.DictReader(io.StringIO(text))
    return list(reader)


def _parse_excel(content: bytes) -> list[dict]:
    """Parse Excel file content into list of dicts."""
    try:
        import openpyxl
    except ImportError:
        raise HTTPException(
            status_code=500,
            detail="服务器未安装 openpyxl 库，无法解析 Excel 文件",
        )

    wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    ws = wb.active
    if ws is None:
        raise HTTPException(status_code=400, detail="Excel 文件中没有工作表")

    rows_iter = ws.iter_rows(values_only=True)
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

    wb.close()
    return result
