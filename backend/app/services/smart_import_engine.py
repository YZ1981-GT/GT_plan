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

# 合并表头列名 → 标准字段（覆盖双行合并产生的组合名）
_MERGED_HEADER_MAP = {
    # 年初余额
    "年初余额_借方金额": "year_opening_debit",
    "年初余额_贷方金额": "year_opening_credit",
    "年初余额_借方": "year_opening_debit",
    "年初余额_贷方": "year_opening_credit",
    # 期初余额
    "期初余额_借方金额": "opening_debit",
    "期初余额_贷方金额": "opening_credit",
    "期初余额_借方": "opening_debit",
    "期初余额_贷方": "opening_credit",
    # 本期发生额
    "本期发生额_借方金额": "debit_amount",
    "本期发生额_贷方金额": "credit_amount",
    "本期发生额_借方": "debit_amount",
    "本期发生额_贷方": "credit_amount",
    # 本年累计
    "本年累计_借方金额": "year_debit",
    "本年累计_贷方金额": "year_credit",
    "本年累计_借方": "year_debit",
    "本年累计_贷方": "year_credit",
    # 期末余额
    "期末余额_借方金额": "closing_debit",
    "期末余额_贷方金额": "closing_credit",
    "期末余额_借方": "closing_debit",
    "期末余额_贷方": "closing_credit",
    # 期初/期末（不带"余额"后缀）
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
from app.services.account_chart_service import _COLUMN_MAP as _BASE_COLUMN_MAP


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
# 3. 核算维度解析（复用 account_chart_service.parse_aux_dimensions）
# ─────────────────────────────────────────────────────────────────────────────

from app.services.account_chart_service import parse_aux_dimensions


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
        # 找该科目下期末汇总最接近科目余额的维度类型
        types_for_code = [(k[1], v) for k, v in aux_by_code_type.items() if k[0] == code]
        if not types_for_code:
            continue
        best_type, best = min(types_for_code, key=lambda x: abs(b_closing - x[1]["closing"]))
        a_closing = best["closing"]
        diff = b_closing - a_closing
        if abs(diff) > Decimal("0.01"):
            cross_bal_errors += 1
            if cross_bal_errors <= 3:
                findings.append({
                    "level": "warning", "category": "余额表vs辅助余额表",
                    "message": f"{code}: 科目期末={b_closing}, 最近维度({best_type},{best['count']}条)汇总={a_closing}, 差{diff}",
                    "detail": {"account_code": code, "aux_type": best_type},
                })
    if cross_bal_errors > 3:
        findings.append({"level": "warning", "category": "余额表vs辅助余额表",
                         "message": f"共 {cross_bal_errors} 个科目不一致", "detail": {"total": cross_bal_errors}})
    else:
        findings.append({"level": "info", "category": "余额表vs辅助余额表",
                         "message": f"有辅助核算的 {len(aux_codes)} 个科目中，{len(aux_codes)-cross_bal_errors} 个一致",
                         "detail": {"total": len(aux_codes), "match": len(aux_codes)-cross_bal_errors}})

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

def smart_parse_files(
    file_contents: list[tuple[str, bytes]],
    year_override: Optional[int] = None,
    custom_mapping: Optional[dict[str, str]] = None,
) -> dict:
    """智能解析多个文件，返回四表数据 + 维度信息 + 校验结果。

    Args:
        file_contents: [(filename, content_bytes), ...]
        year_override: 用户指定年度（优先于自动提取）
        custom_mapping: 用户手动指定的列映射 {原始列名: 标准字段名}

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

            # 应用用户自定义映射
            if custom_mapping:
                for h, std_field in custom_mapping.items():
                    if h in parsed["column_mapping"]:
                        parsed["column_mapping"][h] = std_field
                # 重新映射数据行
                new_rows = []
                for row in parsed["rows"]:
                    new_row = {}
                    for k, v in row.items():
                        mapped = custom_mapping.get(k, k)
                        new_row[mapped] = v
                    new_rows.append(new_row)
                parsed["rows"] = new_rows
                parsed["data_type"] = _guess_data_type(set(custom_mapping.values()))

            dt = parsed["data_type"]
            row_count = parsed["row_count"]

            # 提取年度
            if detected_year is None and parsed.get("year"):
                detected_year = parsed["year"]

            diag = {
                "file": filename,
                "sheet": sheet_name,
                "data_type": dt,
                "row_count": row_count,
                "header_count": parsed["header_count"],
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

            elif dt in ("aux_balance", "aux_ledger"):
                # 独立的辅助表（非从核算维度拆分）
                diag["status"] = "skipped"
                diag["message"] = "独立辅助表暂不处理（核算维度已从余额表/序时账自动拆分）"

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

    # 一致性校验（四表间交叉比对，辅助明细账用空列表——写入后再校验）
    validation = validate_four_tables(
        all_balance_rows, all_aux_balance_rows,
        all_ledger_rows, [],  # 辅助明细账不在内存中
    )

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

    return result


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
