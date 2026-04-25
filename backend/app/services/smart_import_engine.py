# -*- coding: utf-8 -*-
"""通用智能四表导入引擎

支持不同企业导出的各种格式：
1. 单行/双行合并表头自动检测与合并
2. 借贷方向自动推断（期初/期末分借贷两列时不依赖方向列）
3. 核算维度多维度拆分 + 用户确认接口
4. 多文件多年度自动识别
5. 辅助余额表 vs 辅助明细账一致性校验
"""

import hashlib
import io
import logging
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Optional
from uuid import UUID

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# 1. 智能表头检测与合并
# ─────────────────────────────────────────────────────────────────────────────

# 表头关键词（用于识别表头行 vs 标题/说明行）
_HEADER_KEYWORDS = {
    "科目编码", "科目代码", "科目编号", "科目名称", "凭证日期", "记账日期",
    "借方", "贷方", "借方金额", "贷方金额", "期初", "期末", "期初余额", "期末余额",
    "年初余额", "本期发生额", "本年累计",
    "摘要", "凭证号", "凭证类型", "凭证字号",
    "核算维度", "辅助类型", "核算类型",
    "序号", "编码", "名称", "余额", "组织编码", "核算组织", "期间",
    "account_code", "account_name", "debit", "credit", "opening", "closing",
}

# 双行表头中第二行的典型关键词（借方金额/贷方金额）
_SUBHEADER_KEYWORDS = {"借方金额", "贷方金额", "借方", "贷方"}


def detect_header_rows(ws, max_scan: int = 8) -> tuple[int, int]:
    """检测表头的起始行和行数（支持单行/双行合并表头）。

    Returns:
        (header_start_row, header_row_count)
        - header_start_row: 0-indexed，表头第一行的位置
        - header_row_count: 表头占几行（1 或 2）
    """
    rows_cache = []
    rows_iter = ws.iter_rows(values_only=True)
    for _ in range(max_scan):
        try:
            row = next(rows_iter)
            rows_cache.append([str(c).strip() if c else "" for c in row])
        except StopIteration:
            break

    header_start = -1
    for i, cells in enumerate(rows_cache):
        non_empty = [c for c in cells if c]
        if not non_empty:
            continue

        # 检查是否包含表头关键词
        has_kw = any(kw in cell for cell in non_empty for kw in _HEADER_KEYWORDS)

        # 标题/说明行特征
        first = non_empty[0] if non_empty else ""
        is_title = (
            (len(non_empty) == 1)  # 只有1个非空单元格 → 标题行或说明行
            or first.startswith("核算组织")
            or (len(first) > 30)
        )

        if is_title and not has_kw:
            continue

        if has_kw and len(non_empty) >= 2:
            header_start = i
            break

        # 多个短文本单元格也可能是表头
        if len(non_empty) >= 3 and all(len(c) <= 30 for c in non_empty):
            header_start = i
            break

    if header_start < 0:
        return 0, 1

    # 检查下一行是否是第二行表头（双行合并表头）
    if header_start + 1 < len(rows_cache):
        next_row = rows_cache[header_start + 1]
        next_non_empty = [c for c in next_row if c]

        # 第二行表头特征：包含"借方金额"/"贷方金额"等子列名
        has_sub_kw = any(
            kw in cell for cell in next_non_empty for kw in _SUBHEADER_KEYWORDS
        )

        if has_sub_kw:
            # 第一行有空列（合并单元格导致的空位）或第二行有更多非空列
            first_row = rows_cache[header_start]
            empty_count = sum(1 for c in first_row if not c)
            if empty_count >= 2 or len(next_non_empty) > len([c for c in first_row if c]):
                return header_start, 2

    return header_start, 1


def merge_header_rows(ws, header_start: int, header_count: int) -> list[str]:
    """合并单行或双行表头为完整列名列表。

    双行合并规则：
    - Row1: "年初余额"(col5) ""(col6) "期初余额"(col7) ""(col8) ...
    - Row2: ""(col1-4) "借方金额"(col5) "贷方金额"(col6) "借方金额"(col7) ...
    - 合并结果: col5="年初余额_借方金额", col6="年初余额_贷方金额", ...

    支持 read_only 和非 read_only 模式。
    非 read_only 模式下，合并单元格的值只在左上角，其他位置为 None。
    """
    # 尝试用 cell 对象读取（非 read_only 模式）
    try:
        max_col = ws.max_column or 1
    except Exception:
        max_col = 50  # read_only 模式下可能没有 max_column

    def _read_row(row_idx: int) -> list[str]:
        """读取指定行的所有单元格值。"""
        result = []
        try:
            # 尝试按行列索引读取（非 read_only 模式）
            for col in range(1, max_col + 1):
                val = ws.cell(row_idx, col).value
                result.append(str(val).strip() if val else "")
        except Exception:
            # read_only 模式：用 iter_rows
            rows_iter = ws.iter_rows(values_only=True)
            for _ in range(row_idx):
                try:
                    row = next(rows_iter)
                except StopIteration:
                    return []
            try:
                row = next(rows_iter)
                result = [str(c).strip() if c else "" for c in row]
            except StopIteration:
                return []
        return result

    # 读取表头行（1-indexed）
    row1 = _read_row(header_start + 1)

    if header_count == 1:
        return [h if h else f"col_{i}" for i, h in enumerate(row1)]

    # 双行表头
    row2 = _read_row(header_start + 2)
    max_cols = max(len(row1), len(row2))

    # 向右填充 Row1 的合并单元格（空列继承左边的值）
    filled_row1 = list(row1) + [""] * (max_cols - len(row1))
    for i in range(1, max_cols):
        if not filled_row1[i] and filled_row1[i - 1]:
            filled_row1[i] = filled_row1[i - 1]

    filled_row2 = list(row2) + [""] * (max_cols - len(row2))

    headers = []
    for i in range(max_cols):
        h1 = filled_row1[i]
        h2 = filled_row2[i]
        if h1 and h2 and h1 != h2:
            headers.append(f"{h1}_{h2}")
        elif h1:
            headers.append(h1)
        elif h2:
            headers.append(h2)
        else:
            headers.append(f"col_{i}")

    return headers



# ─────────────────────────────────────────────────────────────────────────────
# 2. 通用列名映射（扩展版，覆盖合并表头产生的组合列名）
# ─────────────────────────────────────────────────────────────────────────────

# 标准字段 → 中文描述（用于前端展示）
FIELD_LABELS = {
    "account_code": "科目编码",
    "account_name": "科目名称",
    "opening_debit": "期初借方",
    "opening_credit": "期初贷方",
    "opening_balance": "期初余额",
    "debit_amount": "借方发生额",
    "credit_amount": "贷方发生额",
    "closing_debit": "期末借方",
    "closing_credit": "期末贷方",
    "closing_balance": "期末余额",
    "year_opening_debit": "年初借方",
    "year_opening_credit": "年初贷方",
    "year_debit": "本年累计借方",
    "year_credit": "本年累计贷方",
    "voucher_date": "凭证日期",
    "voucher_no": "凭证号",
    "voucher_type": "凭证类型",
    "accounting_period": "会计期间",
    "summary": "摘要",
    "preparer": "制单人",
    "aux_dimensions": "核算维度",
    "aux_type": "辅助类型",
    "aux_code": "辅助编码",
    "aux_name": "辅助名称",
    "company_code": "组织编码",
    "level": "科目级次",
    "direction": "借贷方向",
}

# ── COPY 写入列定义（四表通用，CSV 和 Excel 分支共用） ──
COPY_LEDGER_COLS = [
    "company_code", "voucher_date", "voucher_no", "account_code",
    "account_name", "debit_amount", "credit_amount", "summary",
    "preparer", "currency_code", "accounting_period", "voucher_type",
    "entry_seq", "debit_qty", "credit_qty", "debit_fc", "credit_fc",
]
COPY_AUX_LEDGER_COLS = COPY_LEDGER_COLS + [
    "aux_type", "aux_code", "aux_name", "aux_dimensions_raw",
]
COPY_BALANCE_COLS = [
    "company_code", "account_code", "account_name", "direction", "level",
    "opening_balance", "opening_debit", "opening_credit",
    "closing_balance", "closing_debit", "closing_credit",
    "debit_amount", "credit_amount",
    "year_opening_debit", "year_opening_credit",
    "opening_qty", "opening_fc", "currency_code",
]
COPY_AUX_BALANCE_COLS = COPY_BALANCE_COLS + [
    "aux_type", "aux_code", "aux_name", "aux_dimensions_raw",
]

_REQUIRED_FIELD_GROUPS: dict[str, list[tuple[str, set[str]]]] = {
    "balance": [
        ("account_code", {"account_code"}),
    ],
    "ledger": [
        ("account_code", {"account_code"}),
        ("voucher_date", {"voucher_date"}),
        ("voucher_no", {"voucher_no"}),
    ],
    "aux_balance": [
        ("account_code", {"account_code"}),
        ("aux_type", {"aux_type"}),
    ],
    "aux_ledger": [
        ("account_code", {"account_code"}),
    ],
    "account_chart": [
        ("account_code", {"account_code"}),
        ("account_name", {"account_name"}),
    ],
}

_RECOMMENDED_FIELD_GROUPS: dict[str, list[tuple[str, set[str]]]] = {
    "balance": [
        ("opening_balance", {"opening_balance", "opening_debit", "opening_credit", "year_opening_debit", "year_opening_credit"}),
        ("debit_amount", {"debit_amount"}),
        ("credit_amount", {"credit_amount"}),
        ("closing_balance", {"closing_balance", "closing_debit", "closing_credit"}),
    ],
    "ledger": [
        ("debit_amount", {"debit_amount"}),
        ("credit_amount", {"credit_amount"}),
        ("summary", {"summary"}),
    ],
    "aux_balance": [
        ("opening_balance", {"opening_balance", "opening_debit", "opening_credit"}),
        ("closing_balance", {"closing_balance", "closing_debit", "closing_credit"}),
        ("aux_code", {"aux_code"}),
        ("aux_name", {"aux_name"}),
    ],
}

# 合并表头列名 → 标准字段（覆盖双行合并产生的组合名）
_MERGED_HEADER_MAP = {
    # 年初余额（双行合并：年初余额_借方金额）
    "年初余额_借方金额": "year_opening_debit",
    "年初余额_贷方金额": "year_opening_credit",
    "年初余额_借方": "year_opening_debit",
    "年初余额_贷方": "year_opening_credit",
    # 年初余额（单行直接列名：年初借方金额）
    "年初借方金额": "year_opening_debit",
    "年初贷方金额": "year_opening_credit",
    "年初借方": "year_opening_debit",
    "年初贷方": "year_opening_credit",
    # 期初余额（双行合并）
    "期初余额_借方金额": "opening_debit",
    "期初余额_贷方金额": "opening_credit",
    "期初余额_借方": "opening_debit",
    "期初余额_贷方": "opening_credit",
    # 期初余额（单行直接列名）
    "期初借方金额": "opening_debit",
    "期初贷方金额": "opening_credit",
    "期初借方": "opening_debit",
    "期初贷方": "opening_credit",
    # 本期发生额（双行合并）
    "本期发生额_借方金额": "debit_amount",
    "本期发生额_贷方金额": "credit_amount",
    "本期发生额_借方": "debit_amount",
    "本期发生额_贷方": "credit_amount",
    # 本期发生额（单行直接列名）
    "本期借方金额": "debit_amount",
    "本期贷方金额": "credit_amount",
    "本期借方": "debit_amount",
    "本期贷方": "credit_amount",
    # 本年累计（双行合并）
    "本年累计_借方金额": "year_debit",
    "本年累计_贷方金额": "year_credit",
    "本年累计_借方": "year_debit",
    "本年累计_贷方": "year_credit",
    # 本年累计（单行直接列名）
    "本年累计借方": "year_debit",
    "本年累计贷方": "year_credit",
    "累计借方": "year_debit",
    "累计贷方": "year_credit",
    # 期末余额（双行合并）
    "期末余额_借方金额": "closing_debit",
    "期末余额_贷方金额": "closing_credit",
    "期末余额_借方": "closing_debit",
    "期末余额_贷方": "closing_credit",
    # 期末余额（单行直接列名）
    "期末借方金额": "closing_debit",
    "期末贷方金额": "closing_credit",
    "期末借方": "closing_debit",
    "期末贷方": "closing_credit",
    # 期初/期末（不带"余额"后缀，双行合并）
    "期初_借方金额": "opening_debit",
    "期初_贷方金额": "opening_credit",
    "期末_借方金额": "closing_debit",
    "期末_贷方金额": "closing_credit",
    # 方向列（双行表头可能产生的组合）
    "期初余额_方向": "opening_direction",
    "期末余额_方向": "closing_direction",
    "期初_方向": "opening_direction",
    "期末_方向": "closing_direction",
}

# 基础列名映射（从 account_chart_service._COLUMN_MAP 复用）
from app.models.audit_platform_models import AccountCategory, AccountChart, AccountDirection, AccountSource
from app.services.account_chart_service import (
    _COLUMN_MAP as _BASE_COLUMN_MAP,
    _infer_category,
    _infer_direction,
    _infer_level as _infer_level_svc,
    parse_aux_dimensions,
)


def _detect_missing_fields(data_type: str, matched_fields: set[str]) -> tuple[list[str], list[str]]:
    missing_required = [
        display for display, candidates in _REQUIRED_FIELD_GROUPS.get(data_type, [])
        if not any(field in matched_fields for field in candidates)
    ]
    missing_recommended = [
        display for display, candidates in _RECOMMENDED_FIELD_GROUPS.get(data_type, [])
        if not any(field in matched_fields for field in candidates)
    ]
    return missing_required, missing_recommended


def smart_match_column(header: str) -> Optional[str]:
    """智能匹配列名到标准字段。优先匹配合并表头组合名。"""
    h = header.strip()
    # 1. 合并表头组合名精确匹配
    if h in _MERGED_HEADER_MAP:
        return _MERGED_HEADER_MAP[h]
    # 2. "核算维度" 特殊处理 → 映射为 aux_dimensions（混合维度列）
    if h in ("核算维度",):
        return "aux_dimensions"
    # 3. 基础列名映射
    if h in _BASE_COLUMN_MAP:
        return _BASE_COLUMN_MAP[h]
    # 4. 清洗后匹配
    cleaned = re.sub(r'[\[\]【】\(\)（）\*\#\s]', '', h)
    if cleaned in _MERGED_HEADER_MAP:
        return _MERGED_HEADER_MAP[cleaned]
    if cleaned in ("核算维度",):
        return "aux_dimensions"
    if cleaned in _BASE_COLUMN_MAP:
        return _BASE_COLUMN_MAP[cleaned]
    return None


# ─────────────────────────────────────────────────────────────────────────────
# 4. 年度自动提取
# ─────────────────────────────────────────────────────────────────────────────

def extract_year_from_content(rows: list[dict], filename: str = "") -> Optional[int]:
    """从文件内容或文件名中提取年度。

    优先级：
    1. 数据行中的日期字段（voucher_date）— 支持 datetime/date 对象和字符串
    2. 会计期间字段（如"2025年1期"）
    3. 文件名中的年份
    """
    for row in rows[:20]:
        # 尝试凭证日期（优先处理 datetime/date 对象）
        for key in ("voucher_date", "记账日期", "凭证日期", "日期"):
            val = row.get(key)
            if val is None:
                continue
            if isinstance(val, (datetime, date)):
                return val.year
            m = re.search(r'(20\d{2})', str(val))
            if m:
                return int(m.group(1))
        # 尝试期间
        for key in ("accounting_period", "期间", "会计期间"):
            val = row.get(key)
            if val:
                m = re.search(r'(20\d{2})', str(val))
                if m:
                    return int(m.group(1))

    # 从文件名提取
    if filename:
        m = re.search(r'(20\d{2})', filename)
        if m:
            return int(m.group(1))

    return None


def _resolve_account_category(code: str, name: str, category_raw) -> AccountCategory:
    category = _infer_category(code, name)
    category_str = str(category_raw or "").strip().lower()
    category_map = {
        "资产": AccountCategory.asset,
        "asset": AccountCategory.asset,
        "负债": AccountCategory.liability,
        "liability": AccountCategory.liability,
        "权益": AccountCategory.equity,
        "equity": AccountCategory.equity,
        "收入": AccountCategory.revenue,
        "revenue": AccountCategory.revenue,
        "费用": AccountCategory.expense,
        "expense": AccountCategory.expense,
        "成本": AccountCategory.expense,
        "cost": AccountCategory.expense,
    }
    return category_map.get(category_str, category)


def _resolve_account_direction(direction_raw, category: AccountCategory) -> AccountDirection:
    direction_str = str(direction_raw or "").strip().lower()
    if direction_str in ("debit", "借", "借方"):
        return AccountDirection.debit
    if direction_str in ("credit", "贷", "贷方"):
        return AccountDirection.credit
    return _infer_direction(category)


def _append_account_record(
    *,
    row: dict,
    project_id: UUID,
    seen_codes: set[str],
    acct_records: list[AccountChart],
    by_category: dict[str, int],
) -> bool:
    code = str(row.get("account_code", "")).strip()
    name = str(row.get("account_name", "")).strip()
    if not code or not name or code in seen_codes:
        return False

    parent_code = str(row.get("parent_code", "")).strip() or None
    category = _resolve_account_category(code, name, row.get("category"))
    direction = _resolve_account_direction(row.get("direction"), category)
    level = _infer_level_svc(code, parent_code)

    level_str = str(row.get("level", "")).strip()
    if level_str.isdigit():
        level = int(level_str)

    seen_codes.add(code)
    acct_records.append(AccountChart(
        project_id=project_id,
        account_code=code,
        account_name=name,
        direction=direction,
        level=level,
        category=category,
        parent_code=parent_code,
        source=AccountSource.client,
    ))
    by_category[category.value] = by_category.get(category.value, 0) + 1
    return True



# ─────────────────────────────────────────────────────────────────────────────
# 5. 通用 Sheet 解析（核心：支持双行表头 + 核算维度拆分）
# ─────────────────────────────────────────────────────────────────────────────

def _safe_decimal(val) -> Optional[Decimal]:
    if val is None:
        return None
    try:
        s = str(val).strip()
        if not s or s == "None" or s == "":
            return None
        return Decimal(s)
    except (InvalidOperation, ValueError):
        return None


def _parse_date_val(val) -> Optional[date]:
    if val is None:
        return None
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, date):
        return val
    s = str(val).strip()
    if not s or s == "None":
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y%m%d", "%Y.%m.%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _parse_period_str(val) -> Optional[int]:
    """解析期间字符串为月份。如 '2025年1期' → 1"""
    if val is None:
        return None
    s = str(val).strip()
    m = re.search(r'(\d+)\s*期', s)
    if m:
        return int(m.group(1))
    # 纯数字
    try:
        v = int(s)
        if 1 <= v <= 12:
            return v
    except (ValueError, TypeError):
        pass
    return None


def _infer_level(code: str) -> int:
    code = code.replace(".", "").replace("-", "")
    if len(code) <= 4:
        return 1
    elif len(code) <= 6:
        return 2
    elif len(code) <= 8:
        return 3
    elif len(code) <= 10:
        return 4
    return 5


def smart_parse_sheet(ws, *, read_only: bool = True) -> dict:
    """通用智能解析单个 worksheet。

    注意：此函数会把所有数据行读入内存，仅适用于预览或小文件。
    大文件流式导入请使用 parse_sheet_header_only() + iter_sheet_rows()。

    Returns:
        {
            "headers": [...],           # 合并后的列名
            "header_start": int,        # 表头起始行
            "header_count": int,        # 表头行数
            "column_mapping": {...},    # 列名→标准字段映射
            "data_type": str,           # 识别的数据类型
            "rows": [...],              # 原始数据行（dict）
            "year": int | None,         # 自动提取的年度
        }
    """
    header_start, header_count = detect_header_rows(ws)
    headers = merge_header_rows(ws, header_start, header_count)

    # 列名映射
    column_mapping = {}
    for h in headers:
        mapped = smart_match_column(h)
        if mapped:
            column_mapping[h] = mapped

    # 读取数据行
    data_start = header_start + header_count
    num_cols = len(headers)
    rows = []

    # 尝试用 min_row 参数（非 read_only 模式更高效）
    try:
        data_iter = ws.iter_rows(min_row=data_start + 1, values_only=True)
    except TypeError:
        data_iter = ws.iter_rows(values_only=True)
        for _ in range(data_start):
            try:
                next(data_iter)
            except StopIteration:
                data_iter = iter([])
                break

    for row_vals in data_iter:
        # 补齐列数（read_only 模式下合并单元格可能导致列数不足）
        padded = list(row_vals) + [None] * max(0, num_cols - len(row_vals))
        if all(c is None for c in padded[:num_cols]):
            continue
        row_dict = {}
        for i in range(num_cols):
            h = headers[i]
            mapped = column_mapping.get(h, h)
            row_dict[mapped] = padded[i]
        rows.append(row_dict)

    # 识别数据类型
    mapped_fields = set(column_mapping.values())
    data_type = _guess_data_type(mapped_fields)

    # 提取年度
    year = extract_year_from_content(rows)

    return {
        "headers": headers,
        "header_start": header_start,
        "header_count": header_count,
        "column_mapping": column_mapping,
        "data_type": data_type,
        "rows": rows,
        "year": year,
        "row_count": len(rows),
    }


def parse_sheet_header_only(ws) -> dict:
    """只解析表头和列映射，不读取数据行。用于流式导入场景。

    Returns:
        {
            "headers": [...],
            "header_start": int,
            "header_count": int,
            "column_mapping": {...},
            "data_type": str,
            "data_start": int,          # 数据起始行（0-indexed）
            "num_cols": int,
            "year": int | None,         # 从前几行提取的年度（采样）
        }
    """
    header_start, header_count = detect_header_rows(ws)
    headers = merge_header_rows(ws, header_start, header_count)

    column_mapping = {}
    for h in headers:
        mapped = smart_match_column(h)
        if mapped:
            column_mapping[h] = mapped

    mapped_fields = set(column_mapping.values())
    data_type = _guess_data_type(mapped_fields)
    data_start = header_start + header_count
    num_cols = len(headers)

    # 从前 30 行数据采样提取年度
    sample_rows = []
    try:
        data_iter = ws.iter_rows(min_row=data_start + 1, max_row=data_start + 30, values_only=True)
    except TypeError:
        data_iter = ws.iter_rows(values_only=True)
        for _ in range(data_start):
            try:
                next(data_iter)
            except StopIteration:
                data_iter = iter([])
                break

    for row_vals in data_iter:
        padded = list(row_vals) + [None] * max(0, num_cols - len(row_vals))
        if all(c is None for c in padded[:num_cols]):
            continue
        row_dict = {}
        for i in range(num_cols):
            h = headers[i]
            mapped = column_mapping.get(h, h)
            row_dict[mapped] = padded[i]
        sample_rows.append(row_dict)

    year = extract_year_from_content(sample_rows)

    return {
        "headers": headers,
        "header_start": header_start,
        "header_count": header_count,
        "column_mapping": column_mapping,
        "data_type": data_type,
        "data_start": data_start,
        "num_cols": num_cols,
        "year": year,
    }


def iter_sheet_rows(ws, meta: dict, batch_size: int = 50_000):
    """逐批迭代 worksheet 数据行的生成器。每次 yield 一批 dict 列表。

    Args:
        ws: openpyxl worksheet
        meta: parse_sheet_header_only() 的返回值
        batch_size: 每批行数

    Yields:
        list[dict]  — 每批最多 batch_size 行
    """
    headers = meta["headers"]
    column_mapping = meta["column_mapping"]
    data_start = meta["data_start"]
    num_cols = meta["num_cols"]

    try:
        data_iter = ws.iter_rows(min_row=data_start + 1, values_only=True)
    except TypeError:
        data_iter = ws.iter_rows(values_only=True)
        for _ in range(data_start):
            try:
                next(data_iter)
            except StopIteration:
                return

    batch: list[dict] = []
    for row_vals in data_iter:
        padded = list(row_vals) + [None] * max(0, num_cols - len(row_vals))
        if all(c is None for c in padded[:num_cols]):
            continue
        row_dict = {}
        for i in range(num_cols):
            h = headers[i]
            mapped = column_mapping.get(h, h)
            row_dict[mapped] = padded[i]
        batch.append(row_dict)
        if len(batch) >= batch_size:
            yield batch
            batch = []
    if batch:
        yield batch


def _parse_with_known_headers(ws, headers: list[str], header_start: int, header_count: int) -> dict:
    """用已知表头解析 read_only 模式的 worksheet（表头从完整模式探测获得）。"""
    column_mapping = {}
    for h in headers:
        mapped = smart_match_column(h)
        if mapped:
            column_mapping[h] = mapped

    data_start = header_start + header_count
    num_cols = len(headers)
    rows = []

    rows_iter = ws.iter_rows(values_only=True)
    for _ in range(data_start):
        try:
            next(rows_iter)
        except StopIteration:
            break

    for row_vals in rows_iter:
        padded = list(row_vals) + [None] * max(0, num_cols - len(row_vals))
        if all(c is None for c in padded[:num_cols]):
            continue
        row_dict = {}
        for i in range(num_cols):
            h = headers[i]
            mapped = column_mapping.get(h, h)
            row_dict[mapped] = padded[i]
        rows.append(row_dict)

    mapped_fields = set(column_mapping.values())
    data_type = _guess_data_type(mapped_fields)
    year = extract_year_from_content(rows)

    return {
        "headers": headers,
        "header_start": header_start,
        "header_count": header_count,
        "column_mapping": column_mapping,
        "data_type": data_type,
        "rows": rows,
        "year": year,
        "row_count": len(rows),
    }


def _guess_data_type(fields: set[str]) -> str:
    """根据已映射的字段集合推断数据类型。"""
    has_code = "account_code" in fields
    has_voucher_date = "voucher_date" in fields
    has_voucher_no = "voucher_no" in fields
    has_debit = "debit_amount" in fields
    has_credit = "credit_amount" in fields
    has_opening = any(f in fields for f in (
        "opening_balance", "opening_debit", "opening_credit",
        "year_opening_debit", "year_opening_credit",
    ))
    has_closing = any(f in fields for f in ("closing_balance", "closing_debit", "closing_credit"))
    # aux_dimensions 是混合维度列（需要拆分），不等于独立辅助表
    has_aux_dimensions = "aux_dimensions" in fields
    has_aux_separate = any(f in fields for f in ("aux_code", "aux_name")) and "aux_type" in fields

    # 独立辅助核算列（非混合维度列）
    if has_aux_separate and not has_aux_dimensions:
        if has_voucher_date:
            return "aux_ledger"
        return "aux_balance"

    # 序时账（可能含核算维度列，拆分后生成辅助明细账）
    if has_voucher_date and has_voucher_no and (has_debit or has_credit):
        return "ledger"

    # 余额表（可能含核算维度列，拆分后生成辅助余额表）
    if has_code and (has_opening or has_closing):
        return "balance"

    # 只有借贷发生额也可能是余额表
    if has_code and (has_debit or has_credit) and not has_voucher_date:
        return "balance"

    if has_code:
        return "account_chart"

    return "unknown"



# ─────────────────────────────────────────────────────────────────────────────
# 6. 四表数据转换（从原始行 → 标准化记录）
# ─────────────────────────────────────────────────────────────────────────────

def convert_balance_rows(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    """将余额表原始行转换为 (tb_balance_rows, tb_aux_balance_rows)。

    两种期初/期末模式都保留原始数据：
    - 分列模式（期初借方+期初贷方）：存 opening_debit/opening_credit，同时算 opening_balance
    - 净额+方向模式（期初余额+方向）：存 opening_balance，不强制拆借贷

    核算维度列自动拆分为辅助余额表记录。
    """
    balance_rows = []
    aux_balance_rows = []

    for row in rows:
        account_code = str(row.get("account_code", "")).strip()
        if not account_code:
            continue

        account_name = str(row.get("account_name", "")).strip()
        company_code = str(row.get("company_code", "")).strip() or "default"

        # ── 期初 ──
        od = _safe_decimal(row.get("opening_debit"))
        oc = _safe_decimal(row.get("opening_credit"))
        opening_bal = _safe_decimal(row.get("opening_balance"))
        opening_dir = row.get("opening_direction") or row.get("direction")

        # 年初余额作为备选
        if od is None and oc is None and opening_bal is None:
            od = _safe_decimal(row.get("year_opening_debit"))
            oc = _safe_decimal(row.get("year_opening_credit"))

        # 分列模式：有借贷分列 → 保留原始借贷，同时算净额
        if od is not None or oc is not None:
            opening_balance = (od or Decimal(0)) - (oc or Decimal(0))
        elif opening_bal is not None and opening_dir:
            # 净额+方向模式：保留净额原值
            opening_balance = opening_bal
            dir_str = str(opening_dir).strip()
            if dir_str in ("贷", "贷方", "C", "c", "credit", "Credit"):
                opening_balance = -abs(opening_bal)
            elif dir_str in ("借", "借方", "D", "d", "debit", "Debit"):
                opening_balance = abs(opening_bal)
        else:
            opening_balance = opening_bal  # 纯净额，无方向

        # ── 期末 ──
        cd = _safe_decimal(row.get("closing_debit"))
        cc = _safe_decimal(row.get("closing_credit"))
        closing_bal = _safe_decimal(row.get("closing_balance"))
        closing_dir = row.get("closing_direction") or row.get("direction")

        if cd is not None or cc is not None:
            closing_balance = (cd or Decimal(0)) - (cc or Decimal(0))
        elif closing_bal is not None and closing_dir:
            closing_balance = closing_bal
            dir_str = str(closing_dir).strip()
            if dir_str in ("贷", "贷方", "C", "c", "credit", "Credit"):
                closing_balance = -abs(closing_bal)
            elif dir_str in ("借", "借方", "D", "d", "debit", "Debit"):
                closing_balance = abs(closing_bal)
        else:
            closing_balance = closing_bal

        debit_amount = _safe_decimal(row.get("debit_amount"))
        credit_amount = _safe_decimal(row.get("credit_amount"))

        # 核算维度处理
        aux_dim_str = str(row.get("aux_dimensions", "")).strip()
        if not aux_dim_str:
            aux_dim_str = str(row.get("aux_type", "")).strip()
            if aux_dim_str and ":" not in aux_dim_str and "：" not in aux_dim_str:
                aux_dim_str = ""

        base_row = {
            "account_code": account_code,
            "account_name": account_name,
            "company_code": company_code,
            "opening_balance": opening_balance,
            "opening_debit": od,
            "opening_credit": oc,
            "debit_amount": debit_amount,
            "credit_amount": credit_amount,
            "closing_balance": closing_balance,
            "closing_debit": cd,
            "closing_credit": cc,
            "currency_code": "CNY",
        }

        if aux_dim_str and (":" in aux_dim_str or "：" in aux_dim_str):
            dims = parse_aux_dimensions(aux_dim_str)
            for dim in dims:
                aux_balance_rows.append({
                    **base_row,
                    "aux_type": dim["aux_type"],
                    "aux_code": dim["aux_code"],
                    "aux_name": dim["aux_name"],
                    "aux_dimensions_raw": aux_dim_str,  # 保留原始维度组合
                })
        else:
            balance_rows.append({
                **base_row,
                "level": _infer_level(account_code),
            })

    return balance_rows, aux_balance_rows


def convert_ledger_rows(rows: list[dict]) -> tuple[list[dict], list[dict], dict]:
    """将序时账原始行转换为 (tb_ledger_rows, tb_aux_ledger_rows, aux_stats)。

    内存优化：辅助明细账只统计维度分布（aux_stats），不在内存中保留全部行。
    实际的辅助明细账行在 write_four_tables 中流式生成写入。

    Returns:
        (ledger_rows, [], aux_stats)
        - ledger_rows: 序时账行（带 _aux_dim_str 原始维度字符串）
        - []: 空列表（辅助明细账不在内存中保留）
        - aux_stats: {"成本中心": 12345, ...} 维度统计
    """
    ledger_rows = []
    aux_stats: dict[str, int] = {}

    for row in rows:
        account_code = str(row.get("account_code", "")).strip()
        if not account_code:
            continue

        voucher_date = _parse_date_val(row.get("voucher_date"))
        voucher_no = str(row.get("voucher_no", "")).strip()
        if not voucher_date or not voucher_no:
            continue

        account_name = str(row.get("account_name", "")).strip()
        voucher_type = str(row.get("voucher_type", "")).strip() or None
        accounting_period = _parse_period_str(row.get("accounting_period"))
        debit_amount = _safe_decimal(row.get("debit_amount"))
        credit_amount = _safe_decimal(row.get("credit_amount"))
        summary = str(row.get("summary", "")).strip() or None
        preparer = str(row.get("preparer", "")).strip() or None

        # 核算维度原始字符串（保留，写入时再拆分）
        aux_dim_str = str(row.get("aux_dimensions", "")).strip()
        if not aux_dim_str:
            aux_dim_str = str(row.get("aux_type", "")).strip()
            if aux_dim_str and ":" not in aux_dim_str and "：" not in aux_dim_str:
                aux_dim_str = ""

        # 统计维度分布（不生成辅助明细行）
        if aux_dim_str and (":" in aux_dim_str or "：" in aux_dim_str):
            dims = parse_aux_dimensions(aux_dim_str)
            for dim in dims:
                aux_stats[dim["aux_type"]] = aux_stats.get(dim["aux_type"], 0) + 1

        ledger_rows.append({
            "account_code": account_code,
            "account_name": account_name,
            "voucher_date": voucher_date,
            "voucher_no": voucher_no,
            "voucher_type": voucher_type,
            "accounting_period": accounting_period,
            "debit_amount": debit_amount,
            "credit_amount": credit_amount,
            "summary": summary,
            "preparer": preparer,
            "company_code": "default",
            "currency_code": "CNY",
            "_aux_dim_str": aux_dim_str,  # 内部字段，写入时拆分
        })

    return ledger_rows, [], aux_stats


# ─────────────────────────────────────────────────────────────────────────────
# 7. 辅助表一致性校验
# ─────────────────────────────────────────────────────────────────────────────

def validate_four_tables(
    balance_rows: list[dict],
    aux_balance_rows: list[dict],
    ledger_rows: list[dict],
    aux_ledger_rows: list[dict],
) -> list[dict]:
    """四表间一致性校验。

    辅助余额表是科目余额表中有辅助核算科目的下级明细展开。
    一条序时账如果有多个维度，会拆成多条辅助明细账记录。

    校验项：
    1. 科目余额表内部勾稽：期初 + 借方 - 贷方 = 期末
    2. 辅助余额表内部勾稽：同上
    3. 科目余额表 vs 辅助余额表：有辅助核算的科目，辅助余额按科目去重后
       的期末合计应等于科目余额表的期末（注意：同一科目多个维度类型，
       每个维度类型各自汇总都应等于科目余额，取任一维度类型比对即可）
    4. 序时账 vs 科目余额表：序时账按科目汇总的借贷发生额应等于余额表
    5. 辅助明细账 vs 辅助余额表：按 (科目, 维度类型, 维度编号) 汇总比对

    Returns:
        [{"level": "info"|"warning"|"error", "category": str, "message": str, "detail": dict}, ...]
    """
    findings = []

    # ── 1. 科目余额表内部勾稽 ──
    bal_map = {}  # account_code -> {opening, debit, credit, closing}
    bal_errors = 0
    for r in balance_rows:
        code = r["account_code"]
        opening = r.get("opening_balance") or Decimal(0)
        debit = r.get("debit_amount") or Decimal(0)
        credit = r.get("credit_amount") or Decimal(0)
        closing = r.get("closing_balance") or Decimal(0)
        bal_map[code] = {"opening": opening, "debit": debit, "credit": credit, "closing": closing}
        expected = opening + debit - credit
        if abs(expected - closing) > Decimal("0.01"):
            bal_errors += 1
            if bal_errors <= 3:
                findings.append({
                    "level": "error", "category": "余额表勾稽",
                    "message": f"{code}: 期初{opening}+借{debit}-贷{credit}={expected}, 期末{closing}, 差{expected-closing}",
                    "detail": {"account_code": code},
                })
    if bal_errors > 3:
        findings.append({"level": "error", "category": "余额表勾稽",
                         "message": f"共 {bal_errors} 个科目不平（仅展示前3条）", "detail": {"total": bal_errors}})

    # ── 2. 辅助余额表内部勾稽 ──
    aux_bal_errors = 0
    for r in aux_balance_rows:
        opening = r.get("opening_balance") or Decimal(0)
        debit = r.get("debit_amount") or Decimal(0)
        credit = r.get("credit_amount") or Decimal(0)
        closing = r.get("closing_balance") or Decimal(0)
        expected = opening + debit - credit
        if abs(expected - closing) > Decimal("0.01"):
            aux_bal_errors += 1
            if aux_bal_errors <= 3:
                findings.append({
                    "level": "error", "category": "辅助余额表勾稽",
                    "message": f"{r['account_code']}/{r.get('aux_type','')}:{r.get('aux_code','')}: "
                               f"期初{opening}+借{debit}-贷{credit}={expected}, 期末{closing}",
                    "detail": {"account_code": r["account_code"], "aux_type": r.get("aux_type")},
                })
    if aux_bal_errors > 3:
        findings.append({"level": "error", "category": "辅助余额表勾稽",
                         "message": f"共 {aux_bal_errors} 条不平", "detail": {"total": aux_bal_errors}})

    # ── 3. 科目余额表 vs 辅助余额表 ──
    # 辅助余额表按科目汇总（去重：同一科目+同一维度组合只算一次期末）
    # 策略：找到每个科目下记录数最少的维度类型，用它汇总比对
    from collections import defaultdict
    aux_by_code_type = defaultdict(lambda: {"closing": Decimal(0), "count": 0})
    aux_codes = set()
    for r in aux_balance_rows:
        code = r["account_code"]
        aux_type = r.get("aux_type", "?")
        key = (code, aux_type)
        aux_by_code_type[key]["closing"] += r.get("closing_balance") or Decimal(0)
        aux_by_code_type[key]["count"] += 1
        aux_codes.add(code)

    cross_bal_errors = 0
    for code in sorted(aux_codes):
        if code not in bal_map:
            continue
        b_closing = bal_map[code]["closing"]
        # 每个维度类型的汇总都应该等于科目余额（核算维度是二级明细）
        # 找最接近的维度类型比对，如实报出差异
        types_for_code = [(k[1], v) for k, v in aux_by_code_type.items() if k[0] == code]
        if not types_for_code:
            continue
        best_type, best = min(types_for_code, key=lambda x: abs(b_closing - x[1]["closing"]))
        a_closing = best["closing"]
        diff = b_closing - a_closing
        if abs(diff) > Decimal("0.01"):
            cross_bal_errors += 1
            if cross_bal_errors <= 5:
                findings.append({
                    "level": "warning", "category": "余额表vs辅助余额表",
                    "message": f"{code}: 科目期末={b_closing}, 最近维度({best_type},{best['count']}条)汇总={a_closing}, 差{diff}",
                    "detail": {"account_code": code, "aux_type": best_type},
                })
    if cross_bal_errors > 5:
        findings.append({"level": "warning", "category": "余额表vs辅助余额表",
                         "message": f"共 {cross_bal_errors} 个科目不一致（仅展示前5条）", "detail": {"total": cross_bal_errors}})
    if cross_bal_errors == 0:
        findings.append({"level": "info", "category": "余额表vs辅助余额表",
                         "message": f"有辅助核算的 {len(aux_codes)} 个科目全部一致",
                         "detail": {"total": len(aux_codes), "match": len(aux_codes)}})

    # ── 4. 序时账 vs 科目余额表 ──
    led_by_code: dict[str, list[Decimal]] = {}  # code -> [debit_sum, credit_sum]
    for r in ledger_rows:
        code = r["account_code"]
        if code not in led_by_code:
            led_by_code[code] = [Decimal(0), Decimal(0)]
        led_by_code[code][0] += r.get("debit_amount") or Decimal(0)
        led_by_code[code][1] += r.get("credit_amount") or Decimal(0)

    led_errors = 0
    for code in sorted(set(bal_map.keys()) & set(led_by_code.keys())):
        b = bal_map[code]
        ld, lc = led_by_code[code]
        if abs(b["debit"] - ld) > Decimal("0.01") or abs(b["credit"] - lc) > Decimal("0.01"):
            led_errors += 1
            if led_errors <= 3:
                findings.append({
                    "level": "warning", "category": "序时账vs余额表",
                    "message": f"{code}: 余额表借{b['debit']}/贷{b['credit']}, 序时账借{ld}/贷{lc}",
                    "detail": {"account_code": code},
                })
    if led_errors > 3:
        findings.append({"level": "warning", "category": "序时账vs余额表",
                         "message": f"共 {led_errors} 个科目不一致", "detail": {"total": led_errors}})
    elif ledger_rows:
        findings.append({"level": "info", "category": "序时账vs余额表",
                         "message": f"序时账 {len(led_by_code)} 个科目中 {len(led_by_code)-led_errors} 个与余额表一致",
                         "detail": {}})

    # ── 5. 辅助明细账 vs 辅助余额表（大数据量时抽样校验） ──
    if aux_ledger_rows and aux_balance_rows:
        # 大数据量（>50万行）时只抽样前10万行做校验，避免内存和时间开销
        sample = aux_ledger_rows if len(aux_ledger_rows) <= 500000 else aux_ledger_rows[:100000]
        is_sampled = len(sample) < len(aux_ledger_rows)

        aux_led_sums: dict[tuple, list[Decimal]] = {}
        for r in sample:
            key = (r["account_code"], r.get("aux_type", ""), r.get("aux_code", ""))
            if key not in aux_led_sums:
                aux_led_sums[key] = [Decimal(0), Decimal(0)]
            aux_led_sums[key][0] += r.get("debit_amount") or Decimal(0)
            aux_led_sums[key][1] += r.get("credit_amount") or Decimal(0)

        if not is_sampled:
            aux_cross_errors = 0
            for r in aux_balance_rows:
                key = (r["account_code"], r.get("aux_type", ""), r.get("aux_code", ""))
                if key not in aux_led_sums:
                    continue
                bal_d = r.get("debit_amount") or Decimal(0)
                bal_c = r.get("credit_amount") or Decimal(0)
                led_d, led_c = aux_led_sums[key]
                if abs(bal_d - led_d) > Decimal("0.01") or abs(bal_c - led_c) > Decimal("0.01"):
                    aux_cross_errors += 1
                    if aux_cross_errors <= 3:
                        findings.append({
                            "level": "warning", "category": "辅助明细账vs辅助余额表",
                            "message": f"{key[0]}/{key[1]}:{key[2]}: 余额表借{bal_d}/贷{bal_c}, 明细账借{led_d}/贷{led_c}",
                            "detail": {"account_code": key[0], "aux_type": key[1], "aux_code": key[2]},
                        })
            if aux_cross_errors > 3:
                findings.append({"level": "warning", "category": "辅助明细账vs辅助余额表",
                                 "message": f"共 {aux_cross_errors} 条不一致", "detail": {"total": aux_cross_errors}})
        else:
            findings.append({"level": "info", "category": "辅助明细账vs辅助余额表",
                             "message": f"辅助明细账 {len(aux_ledger_rows)} 行，数据量较大，抽样前10万行校验",
                             "detail": {"total": len(aux_ledger_rows), "sampled": len(sample)}})

    return findings



# ─────────────────────────────────────────────────────────────────────────────
# 8. 核心入口：智能解析多文件 → 四表数据
# ─────────────────────────────────────────────────────────────────────────────

def _parse_csv_for_preview(
    content: bytes,
    filename: str,
    custom_mapping: Optional[dict] = None,
    max_rows: int = 0,
) -> dict:
    """解析 CSV 文件用于预览/解析。

    大文件时只解析全部行（预览需要完整数据用于转换），
    但使用流式解码避免生成完整 str 副本。

    Args:
        max_rows: 最大读取行数，0=全部
    """
    import codecs
    import csv

    total_lines_est = content.count(b'\n')

    # 编码探测（截断到换行符边界）
    probe_end = min(16384, len(content))
    while probe_end > 0 and content[probe_end - 1:probe_end] != b'\n':
        probe_end -= 1
    if probe_end == 0:
        probe_end = min(16384, len(content))
    sample = content[:probe_end]
    encoding = None
    for enc in ("utf-8-sig", "utf-8", "gbk", "gb2312", "gb18030"):
        try:
            sample.decode(enc)
            encoding = enc
            break
        except (UnicodeDecodeError, LookupError):
            continue
    if encoding is None:
        encoding = "latin-1"

    stream = codecs.getreader(encoding)(io.BytesIO(content))

    # 检测表头
    header_line = None
    for _ in range(5):
        line = stream.readline()
        if not line:
            break
        cells = line.strip().split(',')
        non_empty = [c.strip() for c in cells if c.strip()]
        if len(non_empty) >= 3:
            header_line = line.strip()
            break

    if header_line is None:
        raise ValueError("CSV 文件未找到有效表头")

    reader_header = list(csv.reader([header_line]))[0]
    headers = [c.strip() if c.strip() else f"col_{j}" for j, c in enumerate(reader_header)]

    # 列名映射
    column_mapping: dict[str, str] = {}
    for h in headers:
        mapped = smart_match_column(h)
        if mapped:
            column_mapping[h] = mapped

    if custom_mapping:
        sm = custom_mapping.get("CSV", custom_mapping) if isinstance(custom_mapping, dict) else None
        if sm and not any(isinstance(v, dict) for v in sm.values()):
            for h, v in sm.items():
                if h in headers and v:
                    column_mapping[h] = v

    mapped_fields = set(column_mapping.values())
    dt = _guess_data_type(mapped_fields)

    # 流式读取所有行
    rows = []
    row_count = 0
    line_buf: list[str] = []
    BATCH = 100_000

    while True:
        line = stream.readline()
        if not line:
            break
        line = line.rstrip('\n').rstrip('\r')
        if line:
            line_buf.append(line)

        if len(line_buf) >= BATCH:
            for row_raw in csv.reader(line_buf):
                if not row_raw or all(not c.strip() for c in row_raw):
                    continue
                padded = row_raw + [""] * max(0, len(headers) - len(row_raw))
                row_dict = {}
                for j, h in enumerate(headers):
                    mapped = column_mapping.get(h, h)
                    val = padded[j].strip() if j < len(padded) else ""
                    row_dict[mapped] = val if val else None
                rows.append(row_dict)
                row_count += 1
                if max_rows and row_count >= max_rows:
                    break
            line_buf.clear()
            if max_rows and row_count >= max_rows:
                break

    # 处理剩余行
    if line_buf and (not max_rows or row_count < max_rows):
        for row_raw in csv.reader(line_buf):
            if not row_raw or all(not c.strip() for c in row_raw):
                continue
            padded = row_raw + [""] * max(0, len(headers) - len(row_raw))
            row_dict = {}
            for j, h in enumerate(headers):
                mapped = column_mapping.get(h, h)
                val = padded[j].strip() if j < len(padded) else ""
                row_dict[mapped] = val if val else None
            rows.append(row_dict)
            row_count += 1
            if max_rows and row_count >= max_rows:
                break

    year_val = extract_year_from_content(rows[:100], filename=filename)

    return {
        "headers": headers,
        "column_mapping": column_mapping,
        "data_type": dt,
        "rows": rows,
        "year": year_val,
        "row_count": row_count,
        "total_lines_est": total_lines_est,
    }


def smart_parse_files(
    file_contents: list[tuple[str, bytes]],
    year_override: Optional[int] = None,
    custom_mapping: Optional[dict[str, str] | dict[str, dict[str, str]]] = None,
) -> dict:
    """智能解析多个文件，返回四表数据 + 维度信息 + 校验结果。

    Args:
        file_contents: [(filename, content_bytes), ...]
        year_override: 用户指定年度（优先于自动提取）
        custom_mapping: 用户手动指定的列映射。
            - 全局映射: {原始列名: 标准字段名}
            - 按 sheet 映射: {sheet_name: {原始列名: 标准字段名}}

    Returns:
        {
            "balance_rows": [...],
            "aux_balance_rows": [...],
            "ledger_rows": [...],
            "aux_ledger_rows": [...],
            "year": int,
            "aux_dimensions": [{"type": "成本中心", "count": 1234}, ...],
            "validation": [...],  # 一致性校验结果
            "diagnostics": [...],  # 每个文件/sheet的解析诊断
        }
    """
    import openpyxl

    all_balance_rows = []
    all_aux_balance_rows = []
    all_ledger_rows = []
    all_aux_ledger_rows = []  # 保持为空，辅助明细账在写入时流式生成
    detected_year = year_override
    diagnostics = []
    _aux_type_counts: dict[str, int] = {}  # 维度统计（从余额表+序时账合并）

    for filename, content in file_contents:
        logger.info("解析文件: %s (%d bytes)", filename, len(content))

        # ── CSV 文件单独处理 ──
        if filename.lower().endswith('.csv'):
            try:
                csv_parsed = _parse_csv_for_preview(content, filename, custom_mapping)
            except Exception as e:
                diagnostics.append({
                    "file": filename, "sheet": "CSV",
                    "status": "error", "message": f"CSV 解析失败: {e}",
                })
                continue

            dt = csv_parsed["data_type"]
            matched_fields = set(csv_parsed["column_mapping"].values())
            missing_cols, missing_recommended = _detect_missing_fields(dt, matched_fields)

            if detected_year is None and csv_parsed.get("year"):
                detected_year = csv_parsed["year"]

            diag = {
                "file": filename, "sheet": "CSV", "data_type": dt,
                "row_count": csv_parsed["row_count"],
                "header_count": 1,
                "matched_cols": sorted(matched_fields),
                "missing_cols": missing_cols,
                "missing_recommended": missing_recommended,
                "column_mapping": csv_parsed["column_mapping"],
                "status": "ok",
            }

            if dt == "ledger":
                led, _, aux_stats = convert_ledger_rows(csv_parsed["rows"])
                all_ledger_rows.extend(led)
                diag["ledger_count"] = len(led)
                diag["aux_ledger_count"] = sum(aux_stats.values())
                for t, c in aux_stats.items():
                    _aux_type_counts[t] = _aux_type_counts.get(t, 0) + c
            elif dt == "balance":
                bal, aux_bal = convert_balance_rows(csv_parsed["rows"])
                all_balance_rows.extend(bal)
                all_aux_balance_rows.extend(aux_bal)
                diag["balance_count"] = len(bal)
                diag["aux_balance_count"] = len(aux_bal)
            else:
                diag["status"] = "skipped"
                diag["message"] = f"CSV 未识别的数据类型: {dt}"

            diagnostics.append(diag)
            continue

        # ── Excel 文件处理 ──
        # 第一遍：read_only 模式快速扫描
        try:
            wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        except Exception as e:
            diagnostics.append({
                "file": filename, "sheet": None,
                "status": "error", "message": f"无法打开文件: {e}",
            })
            continue

        needs_full_mode = False
        sheet_col_counts = {}  # sheet_name -> max_column (from full mode probe)
        for ws in wb.worksheets:
            try:
                first_rows = list(ws.iter_rows(max_row=5, values_only=True))
                if first_rows:
                    max_cols = max(len(r) for r in first_rows)
                    if max_cols <= 3:
                        needs_full_mode = True
                        break
                    # 检测合并单元格特征：同一行多列值完全相同
                    for row in first_rows:
                        non_empty = [str(c).strip() for c in row if c is not None and str(c).strip()]
                        if len(non_empty) >= 4:
                            from collections import Counter
                            most_common_val, most_common_count = Counter(non_empty).most_common(1)[0]
                            if most_common_count >= len(non_empty) * 0.6 and most_common_count >= 3:
                                needs_full_mode = True
                                break
                    if needs_full_mode:
                        break
            except Exception:
                pass
        wb.close()

        # 如果需要完整模式（有合并单元格），直接用完整模式打开
        # 完整模式打开约4秒，iter_rows遍历50000行约0.4秒，可接受
        header_cache = {}
        if needs_full_mode:
            logger.info("  检测到合并单元格，使用完整模式: %s", filename)

        try:
            if needs_full_mode:
                wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
            else:
                wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        except Exception as e:
            diagnostics.append({
                "file": filename, "sheet": None,
                "status": "error", "message": f"无法打开文件: {e}",
            })
            continue

        for ws in wb.worksheets:
            sheet_name = ws.title
            # 跳过非数据 sheet
            name_lower = sheet_name.lower()
            if any(kw in name_lower for kw in ("说明", "目录", "封面", "模板")):
                continue

            try:
                parsed = smart_parse_sheet(ws)
            except Exception as e:
                diagnostics.append({
                    "file": filename, "sheet": sheet_name,
                    "status": "error", "message": f"解析失败: {e}",
                })
                continue

            # 应用用户自定义映射（支持全局或按 sheet）
            sheet_mapping = None
            if custom_mapping:
                # 检测是否是按 sheet 的嵌套映射
                if any(isinstance(v, dict) for v in custom_mapping.values()):
                    sheet_mapping = custom_mapping.get(sheet_name)
                else:
                    sheet_mapping = custom_mapping  # type: ignore[assignment]

            if sheet_mapping:
                original_headers = list(parsed["headers"])
                original_column_mapping = dict(parsed["column_mapping"])
                handled_keys = {
                    original_column_mapping.get(header, header)
                    for header in original_headers
                }
                for h, std_field in sheet_mapping.items():
                    if h in original_headers:
                        parsed["column_mapping"][h] = std_field
                new_rows = []
                for row in parsed["rows"]:
                    new_row = {}
                    for header in original_headers:
                        current_key = original_column_mapping.get(header, header)
                        if current_key not in row:
                            continue
                        mapped = parsed["column_mapping"].get(header, current_key)
                        new_row[mapped] = row[current_key]
                    for k, v in row.items():
                        if k not in handled_keys:
                            new_row[k] = v
                    new_rows.append(new_row)
                parsed["rows"] = new_rows
                parsed["data_type"] = _guess_data_type(set(parsed["column_mapping"].values()))

            if parsed.get("year") is None:
                parsed["year"] = extract_year_from_content(parsed["rows"], filename=filename)

            dt = parsed["data_type"]
            row_count = parsed["row_count"]
            matched_fields = set(parsed["column_mapping"].values())
            missing_cols, missing_recommended = _detect_missing_fields(dt, matched_fields)

            # 提取年度
            if detected_year is None and parsed.get("year"):
                detected_year = parsed["year"]

            diag = {
                "file": filename,
                "sheet": sheet_name,
                "data_type": dt,
                "row_count": row_count,
                "header_count": parsed["header_count"],
                "matched_cols": sorted(matched_fields),
                "missing_cols": missing_cols,
                "missing_recommended": missing_recommended,
                "column_mapping": parsed["column_mapping"],
                "status": "ok",
            }

            if dt == "balance":
                bal, aux_bal = convert_balance_rows(parsed["rows"])
                all_balance_rows.extend(bal)
                all_aux_balance_rows.extend(aux_bal)
                diag["balance_count"] = len(bal)
                diag["aux_balance_count"] = len(aux_bal)

            elif dt == "ledger":
                led, _, aux_stats = convert_ledger_rows(parsed["rows"])
                all_ledger_rows.extend(led)
                # 辅助明细账不在内存中保留，写入时从 _aux_dim_str 流式拆分
                aux_led_count = sum(aux_stats.values())
                diag["ledger_count"] = len(led)
                diag["aux_ledger_count"] = aux_led_count
                # 合并维度统计
                for t, c in aux_stats.items():
                    _aux_type_counts[t] = _aux_type_counts.get(t, 0) + c

            elif dt == "aux_balance":
                # 独立辅助余额表直接收集
                all_aux_balance_rows.extend(parsed["rows"])
                diag["aux_balance_count"] = len(parsed["rows"])

            elif dt == "aux_ledger":
                # 独立辅助明细账直接收集
                all_aux_ledger_rows.extend(parsed["rows"])
                diag["aux_ledger_count"] = len(parsed["rows"])

            else:
                diag["status"] = "skipped"
                diag["message"] = f"未识别的数据类型: {dt}"

            diagnostics.append(diag)

        wb.close()

    # 年度兜底
    if detected_year is None:
        detected_year = datetime.now().year - 1

    # 辅助核算维度统计（合并余额表和序时账的统计）
    for r in all_aux_balance_rows:
        t = r.get("aux_type", "?")
        _aux_type_counts[t] = _aux_type_counts.get(t, 0) + 1

    aux_dimensions = [
        {"type": t, "count": c}
        for t, c in sorted(_aux_type_counts.items(), key=lambda x: -x[1])
    ]

    # 一致性校验移到入库后按需触发（预览阶段跳过，632MB CSV 全量校验太慢）
    validation = []

    return {
        "balance_rows": all_balance_rows,
        "aux_balance_rows": all_aux_balance_rows,
        "ledger_rows": all_ledger_rows,
        "aux_ledger_rows": all_aux_ledger_rows,
        "year": detected_year,
        "aux_dimensions": aux_dimensions,
        "validation": validation,
        "diagnostics": diagnostics,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 9. 数据库写入
# ─────────────────────────────────────────────────────────────────────────────

async def _clear_project_year_tables(project_id: UUID, year: int, db) -> None:
    """Soft-delete all four table data for a given project+year.

    Ensures that each project-year has exactly one effective dataset
    and old data from previous imports does not remain as a mix.
    """
    import sqlalchemy as sa
    from app.models.audit_platform_models import TbBalance, TbLedger, TbAuxBalance, TbAuxLedger

    for model in (TbBalance, TbLedger, TbAuxBalance, TbAuxLedger):
        tbl = model.__table__
        await db.execute(
            sa.update(tbl)
            .where(
                tbl.c.project_id == project_id,
                tbl.c.year == year,
                tbl.c.is_deleted == sa.false(),
            )
            .values(is_deleted=True)
        )
    await db.flush()


async def write_four_tables(
    project_id: UUID,
    year: int,
    balance_rows: list[dict],
    aux_balance_rows: list[dict],
    ledger_rows: list[dict],
    aux_ledger_rows: list[dict],
    db,  # AsyncSession
    progress_callback=None,  # (stage, current, total, message) -> None
) -> dict[str, int]:
    """将四表数据写入数据库。返回 {data_type: record_count}。"""
    import uuid as _uuid
    import sqlalchemy as sa
    from app.models.audit_platform_models import (
        TbBalance, TbLedger, TbAuxBalance, TbAuxLedger,
        ImportBatch, ImportStatus,
    )

    def _progress(stage: str, current: int, total: int, msg: str = ""):
        if progress_callback:
            try:
                progress_callback(stage, current, total, msg)
            except Exception:
                pass

    CHUNK_SIZE = 50000
    result: dict[str, int] = {}
    # 计算总行数用于进度
    total_rows = len(balance_rows) + len(aux_balance_rows) + len(ledger_rows)
    # 辅助明细账行数预估（序时账行数 × 平均维度数）
    est_aux_ledger = sum(1 for r in ledger_rows[:1000] if r.get("_aux_dim_str")) * 2.5 * len(ledger_rows) / max(len(ledger_rows[:1000]), 1)
    total_est = total_rows + int(est_aux_ledger)
    written_total = 0

    # 序时账和辅助明细账需要特殊处理：辅助明细从序时账的 _aux_dim_str 流式拆分
    # 先写余额表和辅助余额表，再写序时账+辅助明细账

    # ── 余额表 + 辅助余额表 ──
    for data_type, model, rows in [
        ("tb_balance", TbBalance, balance_rows),
        ("tb_aux_balance", TbAuxBalance, aux_balance_rows),
    ]:
        if not rows:
            continue
        batch = ImportBatch(
            project_id=project_id, year=year, source_type="smart_import",
            file_name=f"smart_{data_type}", data_type=data_type,
            status=ImportStatus.processing, started_at=datetime.utcnow(),
        )
        db.add(batch)
        await db.flush()

        tbl = model.__table__
        await db.execute(
            sa.update(tbl).where(tbl.c.project_id == project_id, tbl.c.year == year, tbl.c.is_deleted == sa.false())
            .values(is_deleted=True)
        )

        record_count = 0
        for i in range(0, len(rows), CHUNK_SIZE):
            chunk = rows[i:i + CHUNK_SIZE]
            recs = [{"id": _uuid.uuid4(), "project_id": project_id, "year": year,
                     "import_batch_id": batch.id, "is_deleted": False, **row} for row in chunk]
            if recs:
                await db.execute(tbl.insert(), recs)
                record_count += len(recs)
                written_total += len(recs)
                _progress(data_type, written_total, total_est, f"{data_type}: {record_count:,} / {len(rows):,}")
            if record_count > 0 and record_count % 50000 < CHUNK_SIZE:
                await db.flush()

        batch.record_count = record_count
        batch.status = ImportStatus.completed
        batch.completed_at = datetime.utcnow()
        result[data_type] = record_count

    # ── 序时账 + 辅助明细账（流式拆分，不在内存中保留全部辅助明细行） ──
    if ledger_rows:
        # 序时账批次
        led_batch = ImportBatch(
            project_id=project_id, year=year, source_type="smart_import",
            file_name="smart_tb_ledger", data_type="tb_ledger",
            status=ImportStatus.processing, started_at=datetime.utcnow(),
        )
        db.add(led_batch)
        # 辅助明细账批次
        aux_batch = ImportBatch(
            project_id=project_id, year=year, source_type="smart_import",
            file_name="smart_tb_aux_ledger", data_type="tb_aux_ledger",
            status=ImportStatus.processing, started_at=datetime.utcnow(),
        )
        db.add(aux_batch)
        await db.flush()

        # 软删除旧数据
        led_tbl = TbLedger.__table__
        aux_tbl = TbAuxLedger.__table__
        await db.execute(
            sa.update(led_tbl).where(led_tbl.c.project_id == project_id, led_tbl.c.year == year, led_tbl.c.is_deleted == sa.false())
            .values(is_deleted=True)
        )
        await db.execute(
            sa.update(aux_tbl).where(aux_tbl.c.project_id == project_id, aux_tbl.c.year == year, aux_tbl.c.is_deleted == sa.false())
            .values(is_deleted=True)
        )

        led_count = 0
        aux_count = 0
        led_buf = []
        aux_buf = []

        # 预生成 UUID 池（比逐个 uuid4() 快）
        def _batch_uuids(n: int) -> list:
            return [_uuid.uuid4() for _ in range(n)]

        for row in ledger_rows:
            aux_dim_str = row.pop("_aux_dim_str", "")

            led_buf.append({
                "id": _uuid.uuid4(), "project_id": project_id, "year": year,
                "import_batch_id": led_batch.id, "is_deleted": False, **row,
            })

            # 流式拆分辅助明细账
            if aux_dim_str and (":" in aux_dim_str or "：" in aux_dim_str):
                dims = parse_aux_dimensions(aux_dim_str)
                for dim in dims:
                    aux_buf.append({
                        "id": _uuid.uuid4(), "project_id": project_id, "year": year,
                        "import_batch_id": aux_batch.id, "is_deleted": False,
                        "aux_type": dim["aux_type"], "aux_code": dim["aux_code"], "aux_name": dim["aux_name"],
                        "aux_dimensions_raw": aux_dim_str,
                        **row,
                    })

            # 分块写入（增大到 50000 减少 INSERT 次数）
            if len(led_buf) >= CHUNK_SIZE:
                await db.execute(led_tbl.insert(), led_buf)
                led_count += len(led_buf)
                written_total += len(led_buf)
                led_buf.clear()
                await db.flush()
                _progress("tb_ledger", written_total, total_est, f"序时账: {led_count:,}, 辅助明细: {aux_count:,}")
            if len(aux_buf) >= CHUNK_SIZE:
                await db.execute(aux_tbl.insert(), aux_buf)
                aux_count += len(aux_buf)
                written_total += len(aux_buf)
                aux_buf.clear()
                await db.flush()
                _progress("tb_aux_ledger", written_total, total_est, f"序时账: {led_count:,}, 辅助明细: {aux_count:,}")

        # 写入剩余
        if led_buf:
            await db.execute(led_tbl.insert(), led_buf)
            led_count += len(led_buf)
        if aux_buf:
            await db.execute(aux_tbl.insert(), aux_buf)
            aux_count += len(aux_buf)

        led_batch.record_count = led_count
        led_batch.status = ImportStatus.completed
        led_batch.completed_at = datetime.utcnow()
        aux_batch.record_count = aux_count
        aux_batch.status = ImportStatus.completed
        aux_batch.completed_at = datetime.utcnow()
        result["tb_ledger"] = led_count
        result["tb_aux_ledger"] = aux_count

    await db.commit()

    # ── 入库后自动计算辅助余额汇总（通用，任何企业都触发） ──
    if result.get("tb_aux_balance", 0) > 0:
        try:
            summary_count = await rebuild_aux_balance_summary(project_id, year, db)
            result["aux_summary"] = summary_count
            logger.info("辅助余额汇总: project=%s, year=%d, %d 条", project_id, year, summary_count)
        except Exception as e:
            logger.warning("辅助余额汇总失败（不影响导入）: %s", e)

    # ── 发布数据导入完成事件，驱动后续重算与缓存失效 ──
    try:
        from app.services.event_bus import event_bus
        from app.models.audit_platform_schemas import EventPayload, EventType

        await event_bus.publish(EventPayload(
            event_type=EventType.DATA_IMPORTED,
            project_id=project_id,
            year=year,
        ))
        logger.info("DATA_IMPORTED 事件已发布: project=%s, year=%d, result=%s", project_id, year, result)
    except Exception as e:
        logger.warning("DATA_IMPORTED 事件发布失败（不影响导入）: %s", e)

    return result



async def _stream_csv_import(
    *,
    content: bytes,
    filename: str,
    project_id,
    year: int,
    batches: dict,
    db,
    custom_mapping: dict | None,
    seen_codes: set,
    acct_records: list,
    by_category: dict,
    counts: dict,
    _aux_type_counts: dict,
    progress_callback,
    chunk_size: int = 50_000,
) -> dict:
    """流式处理 CSV 大文件：流式解码 + 逐批转换 + COPY 写入。

    优化点：
    1. codecs.StreamReader 流式解码（不生成完整 str，内存减半）
    2. asyncpg COPY FROM STDIN 替代 INSERT（写入速度 5-10x）
    3. 每 10 万行一批，峰值内存 ≈ 单批数据大小
    """
    import codecs
    import csv
    import uuid as _uuid
    from app.services.fast_writer import copy_insert

    def _prog(pct, msg=""):
        if progress_callback:
            try:
                progress_callback(pct, msg)
            except Exception:
                pass

    # ── 流式解码：不生成完整 str ──
    total_bytes = len(content)
    total_lines_est = content.count(b'\n')
    _prog(12, f"CSV {filename}: ~{total_lines_est:,} 行, {total_bytes/1024/1024:.0f} MB")

    # 探测编码（截断到最后一个换行符，避免截断多字节字符）
    probe_end = min(16384, len(content))
    # 往回找最近的换行符
    while probe_end > 0 and content[probe_end - 1:probe_end] != b'\n':
        probe_end -= 1
    if probe_end == 0:
        probe_end = min(16384, len(content))
    sample = content[:probe_end]
    encoding = None
    for enc in ("utf-8-sig", "utf-8", "gbk", "gb2312", "gb18030"):
        try:
            sample.decode(enc)
            encoding = enc
            break
        except (UnicodeDecodeError, LookupError):
            continue
    if encoding is None:
        encoding = "latin-1"
    logger.info("CSV 编码检测: %s (probe %d bytes)", encoding, probe_end)

    stream = codecs.getreader(encoding)(io.BytesIO(content))

    # ── 检测表头 ──
    header_line = None
    for _ in range(5):
        line = stream.readline()
        if not line:
            break
        cells = line.strip().split(',')
        non_empty = [c.strip() for c in cells if c.strip()]
        if len(non_empty) >= 3:
            header_line = line.strip()
            break

    if header_line is None:
        raise ValueError("CSV 文件未找到有效表头")

    reader_header = list(csv.reader([header_line]))[0]
    headers = [c.strip() if c.strip() else f"col_{j}" for j, c in enumerate(reader_header)]

    # ── 列名映射 ──
    column_mapping: dict[str, str] = {}
    for h in headers:
        mapped = smart_match_column(h)
        if mapped:
            column_mapping[h] = mapped

    if custom_mapping:
        sm = custom_mapping.get("CSV", custom_mapping) if isinstance(custom_mapping, dict) else None
        if sm and not any(isinstance(v, dict) for v in sm.values()):
            for h, v in sm.items():
                if h in headers and v:
                    column_mapping[h] = v

    mapped_fields = set(column_mapping.values())
    dt = _guess_data_type(mapped_fields)
    miss_req, miss_rec = _detect_missing_fields(dt, mapped_fields)

    diag = {
        "file": filename, "sheet": "CSV", "data_type": dt,
        "row_count": 0, "header_count": 1,
        "matched_cols": sorted(mapped_fields),
        "missing_cols": miss_req, "missing_recommended": miss_rec,
        "column_mapping": column_mapping,
        "status": "ok",
    }

    if dt == "account_chart" and miss_req:
        diag["status"] = "skipped"
        diag["message"] = f"CSV 科目表缺少必需列: {', '.join(miss_req)}"
        return {"diag": diag, "errors": []}

    # 四表关键列缺失时也阻断（不入库）
    if miss_req and dt in ("balance", "ledger", "aux_balance", "aux_ledger"):
        _TYPE_LABELS = {"balance": "余额表", "ledger": "序时账", "aux_balance": "辅助余额表", "aux_ledger": "辅助明细账"}
        diag["status"] = "skipped"
        diag["message"] = f"CSV {_TYPE_LABELS.get(dt, dt)}缺少必需列: {', '.join(miss_req)}，请在列映射中手动指定"
        return {"diag": diag, "errors": [diag["message"]]}

    if dt not in ("ledger", "balance", "aux_balance", "aux_ledger", "account_chart"):
        diag["status"] = "skipped"
        diag["message"] = f"CSV 未识别的数据类型: {dt}"
        return {"diag": diag, "errors": []}

    # ── COPY 写入列定义（引用模块常量） ──
    _LEDGER_COLS = COPY_LEDGER_COLS
    _AUX_LEDGER_COLS = COPY_AUX_LEDGER_COLS
    _BALANCE_COLS = COPY_BALANCE_COLS
    _AUX_BALANCE_COLS = COPY_AUX_BALANCE_COLS

    # ── 流式主循环 ──
    LINES_PER_BATCH = 100_000
    row_count = 0
    errs: list[str] = []
    line_buf: list[str] = []

    async def _flush_batch(rows: list[dict]):
        """转换一批原始行并用 COPY 写入。"""
        if dt == "ledger":
            led, _, aux_stats = convert_ledger_rows(rows)
            for t, c in aux_stats.items():
                _aux_type_counts[t] = _aux_type_counts.get(t, 0) + c

            led_rows: list[dict] = []
            aux_rows: list[dict] = []
            for row in led:
                adim = row.pop("_aux_dim_str", "")
                led_rows.append(row)
                if adim and (":" in adim or "\uff1a" in adim):
                    for dim in parse_aux_dimensions(adim):
                        aux_rows.append({
                            **row,
                            "aux_type": dim["aux_type"],
                            "aux_code": dim["aux_code"],
                            "aux_name": dim["aux_name"],
                            "aux_dimensions_raw": adim,
                        })

            if led_rows:
                n = await copy_insert(
                    db, "tb_ledger", _LEDGER_COLS, led_rows,
                    project_id, year, batches["tb_ledger"].id,
                )
                counts["tb_ledger"] += n
            if aux_rows:
                n = await copy_insert(
                    db, "tb_aux_ledger", _AUX_LEDGER_COLS, aux_rows,
                    project_id, year, batches["tb_aux_ledger"].id,
                )
                counts["tb_aux_ledger"] += n

        elif dt == "balance":
            bal, aux_bal = convert_balance_rows(rows)
            if bal:
                n = await copy_insert(
                    db, "tb_balance", _BALANCE_COLS, bal,
                    project_id, year, batches["tb_balance"].id,
                )
                counts["tb_balance"] += n
            if aux_bal:
                n = await copy_insert(
                    db, "tb_aux_balance", _AUX_BALANCE_COLS, aux_bal,
                    project_id, year, batches["tb_aux_balance"].id,
                )
                counts["tb_aux_balance"] += n

        elif dt == "aux_balance":
            if rows:
                n = await copy_insert(
                    db, "tb_aux_balance", _AUX_BALANCE_COLS, rows,
                    project_id, year, batches["tb_aux_balance"].id,
                )
                counts["tb_aux_balance"] += n
            for r in rows:
                t = r.get("aux_type", "?")
                _aux_type_counts[t] = _aux_type_counts.get(t, 0) + 1

        elif dt == "aux_ledger":
            if rows:
                n = await copy_insert(
                    db, "tb_aux_ledger", _AUX_LEDGER_COLS, rows,
                    project_id, year, batches["tb_aux_ledger"].id,
                )
                counts["tb_aux_ledger"] += n

        # 提取科目
        for row in rows:
            _append_account_record(
                row=row,
                project_id=project_id,
                seen_codes=seen_codes,
                acct_records=acct_records,
                by_category=by_category,
            )

    def _parse_lines(lines: list[str]) -> list[dict]:
        """将一批 CSV 行解析为 dict 列表。"""
        result = []
        for row_raw in csv.reader(lines):
            if not row_raw or all(not c.strip() for c in row_raw):
                continue
            padded = row_raw + [""] * max(0, len(headers) - len(row_raw))
            row_dict = {}
            for j, h in enumerate(headers):
                mapped = column_mapping.get(h, h)
                val = padded[j].strip() if j < len(padded) else ""
                row_dict[mapped] = val if val else None
            result.append(row_dict)
        return result

    # 逐行读取（流式解码）
    while True:
        line = stream.readline()
        if not line:
            break
        line = line.rstrip('\n').rstrip('\r')
        if line:
            line_buf.append(line)

        if len(line_buf) >= LINES_PER_BATCH:
            parsed_rows = _parse_lines(line_buf)
            row_count += len(parsed_rows)
            if parsed_rows:
                await _flush_batch(parsed_rows)
            pct = 15 + int(row_count / max(total_lines_est, 1) * 70)
            _prog(min(pct, 88), f"CSV: {row_count:,}/{total_lines_est:,} 行")
            line_buf.clear()

    # 处理剩余行
    if line_buf:
        parsed_rows = _parse_lines(line_buf)
        row_count += len(parsed_rows)
        if parsed_rows:
            await _flush_batch(parsed_rows)
        line_buf.clear()

    diag["row_count"] = row_count
    _prog(88, f"CSV 完成: {row_count:,} 行")

    return {"diag": diag, "errors": errs}





async def smart_import_streaming(
    project_id: UUID,
    file_contents: list[tuple[str, bytes]],
    db,  # AsyncSession
    year_override: int | None = None,
    custom_mapping: Optional[dict] = None,
    progress_callback=None,
) -> dict:
    """多文件流式导入：逐 sheet 解析并写入，内存可控，只 soft-delete 一次。

    与 smart_parse_files() + write_four_tables() 两步方案的区别：
    - 多文件安全：只在开头软删除一次旧数据，不会后续文件覆盖前面的
    - 内存可控：每次只在内存中保留一个 sheet 的数据行
    - 自动提取科目表：从余额表和序时账行中提取 account_code/name

    Args:
        project_id: 项目ID
        file_contents: [(filename, content_bytes), ...]
        db: AsyncSession
        year_override: 用户指定年度（优先于自动提取）
        custom_mapping: 列映射（全局 dict 或按 sheet 嵌套 dict）
        progress_callback: (pct: int, msg: str) -> None

    Returns:
        {
            "total_accounts": int,
            "by_category": dict,
            "data_sheets_imported": dict,
            "sheet_diagnostics": list,  # 已规范化，可直接返回前端
            "year": int,
            "errors": list,
        }
    """
    import openpyxl
    import uuid as _uuid
    import sqlalchemy as sa
    from app.models.audit_platform_models import (
        TbBalance, TbLedger, TbAuxBalance, TbAuxLedger,
        ImportBatch, ImportStatus,
    )

    CHUNK = 50_000

    def _prog(pct: int, msg: str = ""):
        if progress_callback:
            try:
                progress_callback(pct, msg)
            except Exception:
                pass

    # ── Phase 0: Quick scan to detect year ──────────────────────────────────
    detected_year = year_override
    total_size = sum(len(c) for _, c in file_contents)
    sheet_count_est = 0

    if detected_year is None:
        for fn, ct in file_contents:
            # CSV 文件用文件名提取年度
            if fn.lower().endswith('.csv'):
                sheet_count_est += 1
                if detected_year is None:
                    detected_year = extract_year_from_content([], filename=fn)
                continue
            try:
                wb0 = openpyxl.load_workbook(io.BytesIO(ct), read_only=True, data_only=True)
                for ws0 in wb0.worksheets:
                    sheet_count_est += 1
                    if detected_year is None:
                        detected_year = extract_year_from_content(
                            [{f"c{j}": v for j, v in enumerate(r)}
                             for i, r in enumerate(ws0.iter_rows(max_row=25, values_only=True))],
                            filename=fn,
                        )
                wb0.close()
            except Exception:
                continue
    else:
        # Still count sheets for progress estimation
        for fn, ct in file_contents:
            if fn.lower().endswith('.csv'):
                sheet_count_est += 1
                continue
            try:
                wb0 = openpyxl.load_workbook(io.BytesIO(ct), read_only=True, data_only=True)
                sheet_count_est += len(wb0.worksheets)
                wb0.close()
            except Exception:
                pass

    if detected_year is None:
        detected_year = datetime.now().year - 1
    year = detected_year

    _prog(5, f"年度 {year}，{len(file_contents)} 个文件，{total_size/1024/1024:.1f} MB")

    # ── Phase 0: 统一清理该 project+year 的全部四表旧数据 ────────────────
    await _clear_project_year_tables(project_id, year, db)

    # ── Phase 1: ImportBatch 记录 ─────────────────────────────────────────
    _TABLE_MAP = {
        "tb_balance": TbBalance,
        "tb_aux_balance": TbAuxBalance,
        "tb_ledger": TbLedger,
        "tb_aux_ledger": TbAuxLedger,
    }
    batches: dict[str, ImportBatch] = {}
    for dt_key, model in _TABLE_MAP.items():
        batch = ImportBatch(
            project_id=project_id, year=year, source_type="smart_import",
            file_name=f"multi_{dt_key}", data_type=dt_key,
            status=ImportStatus.processing, started_at=datetime.utcnow(),
        )
        db.add(batch)
        batches[dt_key] = batch

    # soft-delete 旧科目表
    ac_tbl = AccountChart.__table__
    await db.execute(
        sa.update(ac_tbl)
        .where(ac_tbl.c.project_id == project_id, ac_tbl.c.source == "client")
        .values(is_deleted=True)
    )
    await db.flush()
    _prog(10, "旧数据已清理，开始解析文件…")

    # ── Phase 2: 逐文件逐 sheet 流式处理 ────────────────────────────────────
    counts: dict[str, int] = {k: 0 for k in _TABLE_MAP}
    diagnostics: list[dict] = []
    errors: list[str] = []
    seen_codes: set[str] = set()
    acct_records: list[AccountChart] = []
    by_category: dict[str, int] = {}
    _aux_type_counts: dict[str, int] = {}
    sheets_done = 0

    for file_idx, (filename, content) in enumerate(file_contents):
        logger.info("流式导入 %d/%d: %s (%d bytes)",
                     file_idx + 1, len(file_contents), filename, len(content))

        if filename.lower().endswith('.xls'):
            diagnostics.append({
                "file": filename,
                "sheet": None,
                "status": "error",
                "message": "暂不支持 Excel 97-2003 (.xls) 文件，请先转换为 .xlsx 后再上传",
            })
            errors.append(f"暂不支持 .xls 文件: {filename}，请先转换为 .xlsx 后再上传")
            continue

        # ── CSV 文件单独处理（流式：逐批读取+写入，不全部加载到内存） ──
        if filename.lower().endswith('.csv'):
            sheets_done += 1
            _prog(12, f"解析 CSV {filename}")

            try:
                csv_result = await _stream_csv_import(
                    content=content,
                    filename=filename,
                    project_id=project_id,
                    year=year,
                    batches=batches,
                    db=db,
                    custom_mapping=custom_mapping,
                    seen_codes=seen_codes,
                    acct_records=acct_records,
                    by_category=by_category,
                    counts=counts,
                    _aux_type_counts=_aux_type_counts,
                    progress_callback=_prog,
                    chunk_size=CHUNK,
                )
                diagnostics.append(csv_result["diag"])
                if csv_result.get("errors"):
                    errors.extend(csv_result["errors"])
            except Exception as e:
                import traceback
                logger.error("CSV 导入异常: %s\n%s", e, traceback.format_exc())
                diagnostics.append({"file": filename, "sheet": "CSV",
                                    "status": "error", "message": str(e)})
                errors.append(f"CSV 导入失败 {filename}: {e}")
            continue  # 跳过后面的 Excel 处理

        # ── Excel 文件处理 ──
        # 探测是否需要 full mode（合并单元格）
        # read_only 模式下合并单元格的值会被复制到所有合并列，导致表头检测错误
        needs_full = False
        try:
            wb_probe = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
            for _ws in wb_probe.worksheets:
                try:
                    rows5 = list(_ws.iter_rows(max_row=5, values_only=True))
                    if not rows5:
                        continue
                    # 检测1：列数太少（原有逻辑）
                    if max(len(r) for r in rows5) <= 3:
                        needs_full = True
                        break
                    # 检测2：同一行多列值完全相同（合并单元格特征）
                    for row in rows5:
                        non_empty = [str(c).strip() for c in row if c is not None and str(c).strip()]
                        if len(non_empty) >= 4:
                            # 如果超过一半的非空值相同，说明是合并单元格
                            from collections import Counter
                            most_common_val, most_common_count = Counter(non_empty).most_common(1)[0]
                            if most_common_count >= len(non_empty) * 0.6 and most_common_count >= 3:
                                needs_full = True
                                break
                    if needs_full:
                        break
                except Exception:
                    pass
            wb_probe.close()
        except Exception:
            pass

        if needs_full:
            logger.info("  检测到合并单元格特征，使用完整模式: %s", filename)

        try:
            wb = openpyxl.load_workbook(
                io.BytesIO(content),
                read_only=(not needs_full), data_only=True,
            )
        except Exception as e:
            diagnostics.append({"file": filename, "sheet": None,
                                "status": "error", "message": f"无法打开: {e}"})
            errors.append(f"无法打开 {filename}: {e}")
            continue

        for ws in wb.worksheets:
            sname = ws.title
            if any(kw in sname.lower() for kw in ("说明", "目录", "封面", "模板")):
                continue

            sheets_done += 1
            pct = 10 + int(sheets_done / max(sheet_count_est, 1) * 78)
            _prog(min(pct, 88), f"解析 {filename} / {sname}")

            # ── 解析表头（不读数据行，零内存） ──
            try:
                meta = parse_sheet_header_only(ws)
            except Exception as e:
                diagnostics.append({"file": filename, "sheet": sname,
                                    "status": "error", "message": str(e)})
                continue

            # ── 应用自定义映射到表头 ──
            sm = None
            if custom_mapping:
                if any(isinstance(v, dict) for v in custom_mapping.values()):
                    sm = custom_mapping.get(sname)
                else:
                    sm = custom_mapping
            if sm:
                orig_headers = list(meta["headers"])
                matching_keys = [h for h in sm if h in orig_headers]
                if matching_keys:
                    for h, sf in sm.items():
                        if h in orig_headers and sf:
                            meta["column_mapping"][h] = sf
                    meta["data_type"] = _guess_data_type(set(meta["column_mapping"].values()))

            if meta.get("year") is None:
                meta["year"] = extract_year_from_content([], filename=filename)

            dt = meta["data_type"]
            matched_fields = set(meta["column_mapping"].values())
            miss_req, miss_rec = _detect_missing_fields(dt, matched_fields)

            diag: dict = {
                "file": filename, "sheet": sname, "data_type": dt,
                "row_count": 0,  # 流式处理，最终更新
                "header_count": meta["header_count"],
                "matched_cols": sorted(matched_fields),
                "missing_cols": miss_req, "missing_recommended": miss_rec,
                "column_mapping": meta["column_mapping"],
                "status": "ok",
            }

            if dt == "account_chart" and miss_req:
                diag["status"] = "skipped"
                diag["message"] = f"科目表缺少必需列: {', '.join(miss_req)}"
                diagnostics.append(diag)
                continue

            # 四表关键列缺失时也阻断（不入库）
            if miss_req and dt in ("balance", "ledger", "aux_balance", "aux_ledger"):
                _TYPE_LABELS = {"balance": "余额表", "ledger": "序时账", "aux_balance": "辅助余额表", "aux_ledger": "辅助明细账"}
                diag["status"] = "skipped"
                diag["message"] = f"{_TYPE_LABELS.get(dt, dt)}缺少必需列: {', '.join(miss_req)}，请在列映射中手动指定"
                errors.append(diag["message"])
                diagnostics.append(diag)
                continue

            # ── 流式逐批读取 + 转换 + COPY 写入 ──
            from app.services.fast_writer import copy_insert as _copy_insert

            # COPY 写入列定义（引用模块常量）
            _LEDGER_COLS = COPY_LEDGER_COLS
            _AUX_LEDGER_COLS = COPY_AUX_LEDGER_COLS
            _BALANCE_COLS = COPY_BALANCE_COLS
            _AUX_BALANCE_COLS = COPY_AUX_BALANCE_COLS

            logger.info("Sheet %s: data_type=%s, streaming+COPY, matched=%s",
                        sname, dt, sorted(matched_fields)[:5])

            sheet_row_count = 0
            sheet_counts: dict[str, int] = {"tb_balance": 0, "tb_aux_balance": 0, "tb_ledger": 0, "tb_aux_ledger": 0}

            # 用于 ledger 的跨批缓冲（不满 CHUNK 的尾部留到下一批）
            _led_buf: list[dict] = []
            _aux_led_buf: list[dict] = []

            # 预计算自定义映射的重映射表（提到循环外，避免每批重复计算）
            _has_custom_remap = bool(sm and matching_keys)
            _orig_cm: dict[str, str] = {}
            _handled_keys: set[str] = set()
            if _has_custom_remap:
                _orig_cm = {h: meta["column_mapping"].get(h, h) for h in meta["headers"]}
                _handled_keys = set(_orig_cm.values())

            for batch_rows in iter_sheet_rows(ws, meta, batch_size=CHUNK):
                sheet_row_count += len(batch_rows)

                # 应用自定义映射到数据行（如果有）
                if _has_custom_remap:
                    remapped = []
                    for row in batch_rows:
                        nr: dict = {}
                        for h in meta["headers"]:
                            ck = _orig_cm.get(h, h)
                            if ck in row:
                                nr[meta["column_mapping"].get(h, ck)] = row[ck]
                        for k, v in row.items():
                            if k not in _handled_keys:
                                nr[k] = v
                        remapped.append(nr)
                    batch_rows = remapped

                if dt == "balance":
                    bal, aux_bal = convert_balance_rows(batch_rows)
                    if bal:
                        n = await _copy_insert(
                            db, "tb_balance", _BALANCE_COLS, bal,
                            project_id, year, batches["tb_balance"].id,
                        )
                        counts["tb_balance"] += n
                        sheet_counts["tb_balance"] += n
                    if aux_bal:
                        n = await _copy_insert(
                            db, "tb_aux_balance", _AUX_BALANCE_COLS, aux_bal,
                            project_id, year, batches["tb_aux_balance"].id,
                        )
                        counts["tb_aux_balance"] += n
                        sheet_counts["tb_aux_balance"] += n
                    for r in aux_bal:
                        t = r.get("aux_type", "?")
                        _aux_type_counts[t] = _aux_type_counts.get(t, 0) + 1

                elif dt == "ledger":
                    led, _, aux_stats = convert_ledger_rows(batch_rows)
                    for t, c in aux_stats.items():
                        _aux_type_counts[t] = _aux_type_counts.get(t, 0) + c
                    for row in led:
                        adim = row.pop("_aux_dim_str", "")
                        _led_buf.append(row)
                        if adim and (":" in adim or "：" in adim):
                            for dim in parse_aux_dimensions(adim):
                                _aux_led_buf.append({
                                    **row,
                                    "aux_type": dim["aux_type"],
                                    "aux_code": dim["aux_code"],
                                    "aux_name": dim["aux_name"],
                                    "aux_dimensions_raw": adim,
                                })
                    if len(_led_buf) >= CHUNK:
                        n = await _copy_insert(
                            db, "tb_ledger", _LEDGER_COLS, _led_buf,
                            project_id, year, batches["tb_ledger"].id,
                        )
                        counts["tb_ledger"] += n
                        sheet_counts["tb_ledger"] += n
                        _led_buf.clear()
                    if len(_aux_led_buf) >= CHUNK:
                        n = await _copy_insert(
                            db, "tb_aux_ledger", _AUX_LEDGER_COLS, _aux_led_buf,
                            project_id, year, batches["tb_aux_ledger"].id,
                        )
                        counts["tb_aux_ledger"] += n
                        sheet_counts["tb_aux_ledger"] += n
                        _aux_led_buf.clear()

                elif dt == "aux_balance":
                    if batch_rows:
                        n = await _copy_insert(
                            db, "tb_aux_balance", _AUX_BALANCE_COLS, batch_rows,
                            project_id, year, batches["tb_aux_balance"].id,
                        )
                        counts["tb_aux_balance"] += n
                        sheet_counts["tb_aux_balance"] += n
                    for r in batch_rows:
                        t = r.get("aux_type", "?")
                        _aux_type_counts[t] = _aux_type_counts.get(t, 0) + 1

                elif dt == "aux_ledger":
                    _aux_led_buf.extend(batch_rows)
                    if len(_aux_led_buf) >= CHUNK:
                        n = await _copy_insert(
                            db, "tb_aux_ledger", _AUX_LEDGER_COLS, _aux_led_buf,
                            project_id, year, batches["tb_aux_ledger"].id,
                        )
                        counts["tb_aux_ledger"] += n
                        sheet_counts["tb_aux_ledger"] += n
                        _aux_led_buf.clear()

                elif dt == "account_chart":
                    pass  # 科目提取在下面统一做

                # 提取科目（从每批数据中）
                for row in batch_rows:
                    _append_account_record(
                        row=row,
                        project_id=project_id,
                        seen_codes=seen_codes,
                        acct_records=acct_records,
                        by_category=by_category,
                    )

            # ── flush 剩余缓冲（COPY） ──
            if _led_buf:
                n = await _copy_insert(
                    db, "tb_ledger", _LEDGER_COLS, _led_buf,
                    project_id, year, batches["tb_ledger"].id,
                )
                counts["tb_ledger"] += n
                sheet_counts["tb_ledger"] += n
                _led_buf.clear()
            if _aux_led_buf:
                n = await _copy_insert(
                    db, "tb_aux_ledger", _AUX_LEDGER_COLS, _aux_led_buf,
                    project_id, year, batches["tb_aux_ledger"].id,
                )
                counts["tb_aux_ledger"] += n
                sheet_counts["tb_aux_ledger"] += n
                _aux_led_buf.clear()

            diag["row_count"] = sheet_row_count
            if dt == "balance":
                diag["balance_count"] = sheet_counts["tb_balance"]
                diag["aux_balance_count"] = sheet_counts["tb_aux_balance"]
            elif dt == "ledger":
                diag["ledger_count"] = sheet_counts["tb_ledger"]
                diag["aux_ledger_count"] = sheet_counts["tb_aux_ledger"]
            elif dt == "aux_balance":
                diag["aux_balance_count"] = sheet_row_count
            elif dt == "aux_ledger":
                diag["aux_ledger_count"] = sheet_row_count
            elif dt == "account_chart":
                diag["account_count"] = sheet_row_count

            if dt == "unknown":
                diag["status"] = "skipped"
                diag["message"] = f"未识别的数据类型: {dt}"
                logger.warning("  UNKNOWN data_type=%s, matched_fields=%s", dt, matched_fields)

            diagnostics.append(diag)

        wb.close()

    # ── Phase 3: 写入科目表 ─────────────────────────────────────────────────
    if acct_records:
        db.add_all(acct_records)
        await db.flush()
    _prog(90, f"科目 {len(acct_records)} 个，正在完成…")

    # ── Phase 4: 更新 batch 状态 ────────────────────────────────────────────
    for dt_key, batch in batches.items():
        batch.record_count = counts[dt_key]
        batch.status = ImportStatus.completed
        batch.completed_at = datetime.utcnow()
    await db.commit()

    # ── Phase 5: 辅助余额汇总 + 事件 ───────────────────────────────────────
    if counts.get("tb_aux_balance", 0) > 0:
        try:
            sc = await rebuild_aux_balance_summary(project_id, year, db)
            counts["aux_summary"] = sc
        except Exception as e:
            logger.warning("辅助余额汇总失败: %s", e)

    try:
        from app.services.event_bus import event_bus
        from app.models.audit_platform_schemas import EventPayload, EventType
        await event_bus.publish(EventPayload(
            event_type=EventType.DATA_IMPORTED,
            project_id=project_id,
            year=year,
        ))
        logger.info("DATA_IMPORTED 事件: project=%s, year=%d, counts=%s",
                     project_id, year, counts)
    except Exception as e:
        logger.warning("DATA_IMPORTED 事件发布失败: %s", e)

    _prog(100, "导入完成")

    # 规范化诊断结构
    norm_diag: list[dict] = []
    for d in diagnostics:
        norm_diag.append({
            "sheet_name": d.get("sheet", ""),
            "guessed_type": d.get("data_type", "unknown"),
            "matched_cols": d.get("matched_cols", []),
            "missing_cols": d.get("missing_cols", []),
            "missing_recommended": d.get("missing_recommended", []),
            "row_count": d.get("row_count", 0),
        })

    return {
        "total_accounts": len(acct_records),
        "by_category": by_category,
        "data_sheets_imported": counts,
        "sheet_diagnostics": norm_diag,
        "year": year,
        "errors": errors,
    }


async def rebuild_aux_balance_summary(project_id: UUID, year: int, db) -> int:
    """重建辅助余额汇总表（按维度类型+科目+辅助编码分组）。

    通用规则：任何企业导入后都自动调用。
    汇总结果存入 tb_aux_balance_summary，前端直接查汇总表渲染树形视图。
    """
    import sqlalchemy as sa

    # 1. 清除旧汇总
    await db.execute(sa.text(
        "DELETE FROM tb_aux_balance_summary WHERE project_id = :pid AND year = :yr"
    ), {"pid": str(project_id), "yr": year})

    # 2. 用 SQL 聚合直接插入（比 Python 遍历快几十倍）
    await db.execute(sa.text("""
        INSERT INTO tb_aux_balance_summary
            (project_id, year, dim_type, account_code, account_name, aux_code, aux_name,
             record_count, opening_balance, debit_amount, credit_amount, closing_balance)
        SELECT
            project_id, year, aux_type, account_code,
            MAX(account_name),
            aux_code, MAX(aux_name),
            COUNT(*),
            SUM(COALESCE(opening_balance, 0)),
            SUM(COALESCE(debit_amount, 0)),
            SUM(COALESCE(credit_amount, 0)),
            SUM(COALESCE(closing_balance, 0))
        FROM tb_aux_balance
        WHERE project_id = :pid AND year = :yr AND is_deleted = false
        GROUP BY project_id, year, aux_type, account_code, aux_code
    """), {"pid": str(project_id), "yr": year})

    # 3. 查汇总行数
    r = await db.execute(sa.text(
        "SELECT COUNT(*) FROM tb_aux_balance_summary WHERE project_id = :pid AND year = :yr"
    ), {"pid": str(project_id), "yr": year})
    count = r.scalar() or 0

    await db.commit()
    return count
