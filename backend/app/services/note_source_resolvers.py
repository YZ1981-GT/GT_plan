"""7 种 source 数据源解析器（Sprint 1 Task 1.4）.

Spec:   .kiro/specs/disclosure-note-full-revamp/ Sprint 1 Task 1.4
Design: D2 binding schema 中 ``source`` 字段的 7 种取值
Reqs:   R1.2 七种数据源支持

API
---
每个 resolver 都是 ``async def resolve_xxx(binding, ctx) -> Any``：

- ``binding: dict``  单元格级 binding（含 source / field / account_codes /
  agg / period_filter / aux_type / bucket / manual_value 等可选字段）
- ``ctx: dict``      上下文：
    - ``project_id: UUID``
    - ``year: int``
    - ``db: AsyncSession``       仅 ledger_sum / aux_balance / aux_ledger_aging 用
    - ``_tb_cache: dict``        预加载试算表（trial_balance）
    - ``_wp_cache: dict``        预加载底稿（暂未使用）
    - ``_prior_notes_cache: dict``  上年附注

返回值：
- 数值（float）/ None（缺数据 / 客户未提供辅助序时账等场景）/ 字符串
  （manual / prior_year_note 文本场景）
- **永不抛异常 — 缺数据返 None，调用方降级到 manual placeholder**

7 种 source ↔ resolver 映射
---------------------------
- ``trial_balance``     → ``resolve_trial_balance``  （走 ctx["_tb_cache"]）
- ``ledger_sum``        → ``resolve_ledger_sum``     （实时查 TbLedger）
- ``aux_balance``       → ``resolve_aux_balance``    （实时查 TbAuxBalance）
- ``aux_ledger_aging``  → ``resolve_aux_ledger_aging``（实时查 TbAuxLedger 反推账龄）
- ``formula``           → ``resolve_formula``        （Sprint 1.5 实现，1.4 stub）
- ``prior_year_note``   → ``resolve_prior_year_note``（走 ctx["_prior_notes_cache"]）
- ``manual``            → ``resolve_manual``         （直接读 binding.manual_value）

Validates: Requirements R1.2 验收 6/7/8/9
"""

from __future__ import annotations

import logging
import re
import warnings
from datetime import date
from decimal import Decimal
from typing import Any

import sqlalchemy as sa

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# VALID_SOURCES — 与 generate_note_template_bindings.py 同步
# ---------------------------------------------------------------------------

VALID_SOURCES: tuple[str, ...] = (
    "trial_balance",
    "ledger_sum",
    "aux_balance",
    "aux_ledger_aging",
    "wp_data",
    "formula",
    "prior_year_note",
    "manual",
    "consol_aggregation",
)


# ---------------------------------------------------------------------------
# 内部小工具
# ---------------------------------------------------------------------------


def _to_float(x: Any) -> float | None:
    """安全转 float（支持 Decimal / int / str / float / None）."""
    if x is None:
        return None
    if isinstance(x, bool):
        return None
    if isinstance(x, int | float):
        return float(x)
    if isinstance(x, Decimal):
        return float(x)
    if isinstance(x, str):
        s = x.strip()
        if not s:
            return None
        try:
            return float(s)
        except ValueError:
            return None
    return None


def _safe_account_codes(binding: dict[str, Any]) -> list[str]:
    """提取 account_codes 列表（剔除 None / 非 str / 空串）."""
    codes = binding.get("account_codes")
    if not isinstance(codes, list):
        return []
    return [c for c in codes if isinstance(c, str) and c]


def _aggregate(values: list[float], agg: str) -> float | None:
    """按 agg 聚合 — 缺值已在 caller 过滤；空 list 返 None."""
    if not values:
        return None
    agg = agg or "sum"
    if agg == "sum":
        return sum(values)
    if agg == "sum_minus":
        return -sum(values)
    if agg == "first":
        return values[0]
    if agg == "max":
        return max(values)
    if agg == "min":
        return min(values)
    if agg == "avg":
        return sum(values) / len(values)
    # 未识别 agg → sum 兜底
    return sum(values)


def _interp_var(s: str, ctx: dict[str, Any]) -> str:
    """简单变量插值 ``${current_year}`` → ctx['year']."""
    year = ctx.get("year")
    if year is None:
        return s
    return s.replace("${current_year}", str(year))


def _parse_date(s: Any) -> date | None:
    """解析 ISO 日期字符串（YYYY-MM-DD）；失败返 None."""
    if isinstance(s, date):
        return s
    if not isinstance(s, str):
        return None
    s = s.strip()
    if not s:
        return None
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# 1) trial_balance
# ---------------------------------------------------------------------------


async def resolve_trial_balance(
    binding: dict[str, Any],
    ctx: dict[str, Any],
) -> float | None:
    """从 ctx["_tb_cache"] 取 trial_balance 数值.

    binding 字段：
      - account_codes: list[str]      账户代码
      - field:         str             "audited" / "audited_amount" /
                                       "opening" / "opening_balance" /
                                       "unadjusted" / "unadjusted_amount"
      - agg:           str             "sum" / "sum_minus" / "first" / ...
      - abs_for:       list[str]       (本轮暂不使用 — manager + 1.5)

    缓存结构：
      ctx["_tb_cache"][code_or_name] = {
          "audited": float, "unadjusted": float, "opening": float
      }

    无任一命中或缓存未预热 → None.
    """
    tb_cache = ctx.get("_tb_cache") or {}
    if not tb_cache:
        return None

    codes = _safe_account_codes(binding)
    if not codes:
        return None

    field = binding.get("field") or "audited_amount"
    # 统一字段名（json 中可能写 audited_amount / opening_balance）
    if field in ("audited_amount", "audited"):
        cache_key = "audited"
    elif field in ("opening_balance", "opening"):
        cache_key = "opening"
    elif field in ("unadjusted_amount", "unadjusted"):
        cache_key = "unadjusted"
    else:
        cache_key = field  # 兜底

    values: list[float] = []
    for code in codes:
        entry = tb_cache.get(code)
        if not isinstance(entry, dict):
            continue
        v = _to_float(entry.get(cache_key))
        if v is not None:
            values.append(v)

    if not values:
        return None

    return _aggregate(values, binding.get("agg") or "sum")


# ---------------------------------------------------------------------------
# 2) ledger_sum  — 实时查 TbLedger，按 period_filter 过滤
# ---------------------------------------------------------------------------


def _build_period_where_clause(
    binding: dict[str, Any],
    model: Any,
    ctx: dict[str, Any],
) -> Any:
    """根据 binding.period_filter 构造 WHERE 子句（or None 表示无 period 限制）.

    支持三种模式（R1.2 验收 8）：
      a) year_range: {start, end}        日期 — voucher_date 区间
      b) month_range: {start, end}       会计月 — accounting_period IN [start, end]
      c) date_range: {start, end}        日期含变量 ${current_year}

    无 period_filter / mode 不识别 → 不过滤（caller 仅 by year + project_id）.
    """
    pf = binding.get("period_filter")
    if not isinstance(pf, dict):
        return None
    mode = pf.get("mode") or "year_range"

    if mode == "month_range":
        start = pf.get("start")
        end = pf.get("end")
        if not isinstance(start, int) or not isinstance(end, int):
            return None
        return model.accounting_period.between(start, end)

    if mode in ("year_range", "date_range"):
        raw_start = pf.get("start")
        raw_end = pf.get("end")
        if isinstance(raw_start, str):
            raw_start = _interp_var(raw_start, ctx)
        if isinstance(raw_end, str):
            raw_end = _interp_var(raw_end, ctx)
        d_start = _parse_date(raw_start)
        d_end = _parse_date(raw_end)
        if not d_start or not d_end:
            return None
        return model.voucher_date.between(d_start, d_end)

    return None


async def resolve_ledger_sum(
    binding: dict[str, Any],
    ctx: dict[str, Any],
) -> float | None:
    """实时查 TbLedger，按 account_codes + period_filter 求 debit / credit sum.

    binding 字段：
      - account_codes: list[str]       必填
      - field:         str             "debit_amount" / "credit_amount"
      - period_filter: dict            可选（见 _build_period_where_clause）
      - agg:           str             "sum" / "sum_minus"（默认 sum）

    缺 db / 缺 account_codes / 查询异常 → None.
    """
    db = ctx.get("db")
    if db is None:
        return None
    project_id = ctx.get("project_id")
    year = ctx.get("year")
    if project_id is None or year is None:
        return None

    codes = _safe_account_codes(binding)
    if not codes:
        return None

    field = binding.get("field") or "debit_amount"

    try:
        from app.models.audit_platform_models import TbLedger
    except Exception as err:  # pragma: no cover — 环境问题
        logger.warning("ledger_sum: import TbLedger failed: %s", err)
        return None

    column = getattr(TbLedger, field, None)
    if column is None:
        # 字段名不识别 — 兜底用 debit_amount
        column = TbLedger.debit_amount

    where = [
        TbLedger.project_id == project_id,
        TbLedger.year == year,
        TbLedger.is_deleted == sa.false(),
        TbLedger.account_code.in_(codes),
    ]
    period_where = _build_period_where_clause(binding, TbLedger, ctx)
    if period_where is not None:
        where.append(period_where)

    try:
        result = await db.execute(
            sa.select(sa.func.coalesce(sa.func.sum(column), 0)).where(*where)
        )
        total = result.scalar()
    except Exception as err:
        logger.warning("ledger_sum query failed: %s", err)
        return None

    val = _to_float(total)
    if val is None:
        return None
    if (binding.get("agg") or "sum") == "sum_minus":
        return -val
    return val


# ---------------------------------------------------------------------------
# 3) aux_balance — 实时查 TbAuxBalance
# ---------------------------------------------------------------------------


async def resolve_aux_balance(
    binding: dict[str, Any],
    ctx: dict[str, Any],
) -> float | None:
    """实时查 TbAuxBalance，按 account_codes + 可选 aux_type 过滤求和.

    binding 字段：
      - account_codes: list[str]       必填
      - field:         str             "closing_balance" / "opening_balance"
                                       / "debit_amount" / "credit_amount"
      - aux_type:      str             可选过滤
      - agg:           str             默认 sum；sum_minus 翻号

    缺 db / 缺 account_codes / 查询异常 → None.
    """
    db = ctx.get("db")
    if db is None:
        return None
    project_id = ctx.get("project_id")
    year = ctx.get("year")
    if project_id is None or year is None:
        return None

    codes = _safe_account_codes(binding)
    if not codes:
        return None

    field = binding.get("field") or "closing_balance"

    try:
        from app.models.audit_platform_models import TbAuxBalance
    except Exception as err:  # pragma: no cover
        logger.warning("aux_balance: import TbAuxBalance failed: %s", err)
        return None

    column = getattr(TbAuxBalance, field, None)
    if column is None:
        column = TbAuxBalance.closing_balance

    where = [
        TbAuxBalance.project_id == project_id,
        TbAuxBalance.year == year,
        TbAuxBalance.is_deleted == sa.false(),
        TbAuxBalance.account_code.in_(codes),
    ]
    aux_type = binding.get("aux_type")
    if isinstance(aux_type, str) and aux_type:
        where.append(TbAuxBalance.aux_type == aux_type)

    try:
        result = await db.execute(
            sa.select(sa.func.coalesce(sa.func.sum(column), 0)).where(*where)
        )
        total = result.scalar()
    except Exception as err:
        logger.warning("aux_balance query failed: %s", err)
        return None

    val = _to_float(total)
    if val is None:
        return None
    if (binding.get("agg") or "sum") == "sum_minus":
        return -val
    return val


# ---------------------------------------------------------------------------
# 4) aux_ledger_aging — 从 TbAuxLedger 反推账龄分桶（D4 新建）
# ---------------------------------------------------------------------------


# 5 桶：上闭下开（日期差天数 ≥ low 且 < high；最后一桶含 ∞）
_AGING_BUCKETS: dict[str, tuple[int, int]] = {
    "1年以内": (0, 366),
    "1-2年": (366, 731),
    "2-3年": (731, 1096),
    "3-5年": (1096, 1826),
    "5年以上": (1826, 10**9),
}


async def resolve_aux_ledger_aging(
    binding: dict[str, Any],
    ctx: dict[str, Any],
) -> float | None:
    """从 TbAuxLedger 反推账龄分桶（按 voucher_date 至年末算天数）.

    binding 字段：
      - account_codes: list[str]       必填
      - bucket:        str             "1年以内"/"1-2年"/"2-3年"/"3-5年"/"5年以上"
      - field:         str             默认 "bucket_amount" — 桶内 (debit-credit) 余额

    R1.2 验收 7：客户未提供辅助序时账时章节标 not_applicable —
                 实现：查询若 0 行 → 返 None（caller 据此判定 not_applicable）.

    缺 db / 缺 account_codes / 缺 bucket → None.
    """
    db = ctx.get("db")
    if db is None:
        return None
    project_id = ctx.get("project_id")
    year = ctx.get("year")
    if project_id is None or year is None:
        return None

    codes = _safe_account_codes(binding)
    if not codes:
        return None

    bucket = binding.get("bucket")
    if bucket not in _AGING_BUCKETS:
        return None
    low, high = _AGING_BUCKETS[bucket]

    try:
        from app.models.audit_platform_models import TbAuxLedger
    except Exception as err:  # pragma: no cover
        logger.warning("aux_ledger_aging: import TbAuxLedger failed: %s", err)
        return None

    where = [
        TbAuxLedger.project_id == project_id,
        TbAuxLedger.year == year,
        TbAuxLedger.is_deleted == sa.false(),
        TbAuxLedger.account_code.in_(codes),
        TbAuxLedger.voucher_date.isnot(None),
    ]

    try:
        result = await db.execute(
            sa.select(
                TbAuxLedger.voucher_date,
                TbAuxLedger.debit_amount,
                TbAuxLedger.credit_amount,
            ).where(*where)
        )
        rows = result.all()
    except Exception as err:
        logger.warning("aux_ledger_aging query failed: %s", err)
        return None

    if not rows:
        # 客户未提供辅助序时账 — caller 据此判定 not_applicable
        return None

    # 以年末为基准日（YYYY-12-31）算账龄天数
    base_date = date(int(year), 12, 31)
    total: float = 0.0
    for vdate, deb, cre in rows:
        if not isinstance(vdate, date):
            continue
        days = (base_date - vdate).days
        if days < 0:
            continue
        if days < low or days >= high:
            continue
        d = _to_float(deb) or 0.0
        c = _to_float(cre) or 0.0
        total += d - c

    return total


# ---------------------------------------------------------------------------
# 5) wp_data — 从 WorkingPaper.parsed_data 提数（Sprint A.2.4）
# ---------------------------------------------------------------------------


async def resolve_wp_data(
    binding: dict[str, Any],
    ctx: dict[str, Any],
) -> Any:
    """从底稿 ``parsed_data`` 取值（cell / table / column_sum 三种模式）.

    binding 字段：
      - source:    "wp_data"
      - wp_code:   str             底稿编号（必填，如 "h08"）
      - sheet:     str             sheet 名（必填）
      - extract:   str             "cell" | "table" | "column_sum"
      - cell_ref:  str             extract=cell 用（如 "F5"）
      - row_filter:dict            extract=table 用
      - label_col: str             extract=table 用（默认 "A"）
      - value_cols:dict            extract=table 用 ``{col_id: col_letter}``
      - col_letter:str             extract=column_sum 用
      - row_range: [int, int]      extract=column_sum 用

    ctx 用 ``_wp_cache`` 缓存已加载的 WorkingPaper：
      ctx["_wp_cache"] = {wp_code: WorkingPaper}

    流程：
    1. ``_wp_cache`` 命中 → 直接调 ``extract_wp_*``
    2. 未命中且 ``ctx["db"]`` 存在 → 从 DB 加载 → 缓存 → extract
    3. wp 不存在 / parsed_data 为空 → None

    缺数据返 None — 永不抛异常.
    """
    if not isinstance(binding, dict):
        return None

    wp_code = binding.get("wp_code")
    sheet = binding.get("sheet")
    if not isinstance(wp_code, str) or not wp_code:
        return None
    if not isinstance(sheet, str) or not sheet:
        return None

    parsed_data = await _get_wp_parsed_data(wp_code, ctx)
    if not isinstance(parsed_data, dict) or not parsed_data:
        return None

    extract = binding.get("extract") or "cell"

    try:
        from app.services.note_wp_data_resolver import (
            extract_wp_cell,
            extract_wp_column_sum,
            extract_wp_table,
        )
    except Exception as err:  # pragma: no cover
        logger.warning("wp_data: import note_wp_data_resolver failed: %s", err)
        return None

    if extract == "cell":
        cell_ref = binding.get("cell_ref")
        if not isinstance(cell_ref, str) or not cell_ref:
            return None
        return extract_wp_cell(parsed_data, sheet, cell_ref)

    if extract == "table":
        row_filter = binding.get("row_filter")
        label_col = binding.get("label_col") or "A"
        value_cols = binding.get("value_cols")
        return extract_wp_table(
            parsed_data,
            sheet,
            row_filter=row_filter if isinstance(row_filter, dict) else None,
            label_col=label_col if isinstance(label_col, str) else "A",
            value_cols=value_cols if isinstance(value_cols, dict) else None,
        )

    if extract == "column_sum":
        col_letter = binding.get("col_letter")
        if not isinstance(col_letter, str) or not col_letter:
            return None
        rng = binding.get("row_range")
        row_range: tuple[int, int] | None = None
        if isinstance(rng, list | tuple) and len(rng) == 2:
            try:
                row_range = (int(rng[0]), int(rng[1]))
            except (TypeError, ValueError):
                row_range = None
        return extract_wp_column_sum(parsed_data, sheet, col_letter, row_range)

    return None


async def _get_wp_parsed_data(
    wp_code: str,
    ctx: dict[str, Any],
) -> dict | None:
    """从 ``ctx["_wp_cache"]`` 取（命中）或从 DB 加载（未命中）.

    缓存的 value 既可以是 ``WorkingPaper`` ORM 对象，也可以是直接的
    ``parsed_data`` dict（测试场景常用）— 一次兼容两形态。

    DB 加载使用 ``project_id``（必填），匹配 ``parsed_data.wp_code == wp_code``
    的非删除底稿；找不到则返回 None。
    """
    cache = ctx.get("_wp_cache")
    if isinstance(cache, dict) and wp_code in cache:
        cached = cache[wp_code]
        if isinstance(cached, dict):
            # 直接缓存了 parsed_data（测试场景）
            return cached
        # ORM-like 对象：取 .parsed_data
        pd = getattr(cached, "parsed_data", None)
        return pd if isinstance(pd, dict) else None

    db = ctx.get("db")
    if db is None:
        return None
    project_id = ctx.get("project_id")
    if project_id is None:
        return None

    try:
        from app.models.workpaper_models import WorkingPaper
    except Exception as err:  # pragma: no cover
        logger.warning("wp_data: import WorkingPaper failed: %s", err)
        return None

    try:
        result = await db.execute(
            sa.select(WorkingPaper).where(
                WorkingPaper.project_id == project_id,
                WorkingPaper.is_deleted == sa.false(),
            )
        )
        wps = result.scalars().all()
    except Exception as err:
        logger.warning("wp_data: db query failed: %s", err)
        return None

    matched = None
    for wp in wps:
        pd = getattr(wp, "parsed_data", None)
        if isinstance(pd, dict) and pd.get("wp_code") == wp_code:
            matched = wp
            break

    if matched is None:
        return None

    # 写回 cache 供后续 cell 复用
    if not isinstance(cache, dict):
        cache = {}
        ctx["_wp_cache"] = cache
    cache[wp_code] = matched

    pd = getattr(matched, "parsed_data", None)
    return pd if isinstance(pd, dict) else None


# ---------------------------------------------------------------------------
# 6) formula — 表内单元格引用（sum / report / aging / prior_year_note）
#    Spec: disclosure-note-formula-and-report-sync Wave1 (2.1)
#    Reqs: 1.1 / 1.2 / 1.3 / 1.4 / 8.3 / 8.4
# ---------------------------------------------------------------------------


def _formula_enabled() -> bool:
    """灰度开关（默认 False = 保持 stub 行为，逐字节零回归）."""
    try:
        from app.core.config import settings

        return bool(getattr(settings, "DISCLOSURE_NOTE_FORMULA_ENABLED", False))
    except Exception:  # pragma: no cover — 配置不可用时安全降级为关闭
        return False


def _resolve_row_col(binding: dict[str, Any]) -> tuple[int, int] | None:
    """从 binding 解析单元格 (row_idx, col_idx)（0-based）.

    支持两种写法：
      - ``cell``: "R2C2"（1-based Excel 风格，转 0-based）
      - ``row`` + ``col``: 整数（0-based，直接用）
    非法 / 缺失 → None。
    """
    cell = binding.get("cell")
    if isinstance(cell, str):
        m = re.fullmatch(r"\s*[Rr](\d+)[Cc](\d+)\s*", cell)
        if m:
            return (int(m.group(1)) - 1, int(m.group(2)) - 1)
    row = binding.get("row")
    col = binding.get("col")
    if isinstance(row, int) and isinstance(col, int) and row >= 0 and col >= 0:
        return (row, col)
    return None


def _select_table(table_data: Any, table_index: int) -> dict[str, Any] | None:
    """按 table_index 选表：多表取 ``_tables[i]``，单表取自身."""
    if not isinstance(table_data, dict):
        return None
    tables = table_data.get("_tables")
    if isinstance(tables, list) and tables:
        if 0 <= table_index < len(tables) and isinstance(tables[table_index], dict):
            return tables[table_index]
        return None
    return table_data


def _cell_value_from_table(table_data: Any, binding: dict[str, Any]) -> float | None:
    """从 table_data 按 (table_index + cell 坐标) 反查单元格数值.

    table_data 结构：``{rows: [{values: [...]}, ...]}`` 或 ``{_tables: [...]}``。
    坐标越界 / 表越界 / 非数值 → None。
    """
    table_index = binding.get("table_index")
    if not isinstance(table_index, int) or table_index < 0:
        table_index = 0
    tbl = _select_table(table_data, table_index)
    if not isinstance(tbl, dict):
        return None
    coord = _resolve_row_col(binding)
    if coord is None:
        return None
    r, c = coord
    rows = tbl.get("rows")
    if not isinstance(rows, list) or not (0 <= r < len(rows)):
        return None
    row = rows[r]
    if not isinstance(row, dict):
        return None
    vals = row.get("values")
    if not isinstance(vals, list) or not (0 <= c < len(vals)):
        return None
    return _to_float(vals[c])


def _current_cell_value(ctx: dict[str, Any], coord: str) -> float | None:
    """取当前表某坐标数值.

    优先 ``ctx["cell_values"]``（{coord: value}，由 NoteFormulaEvaluator 预填）；
    回退从 ``ctx["table_data"]`` 按坐标反查。
    """
    cv = ctx.get("cell_values")
    if isinstance(cv, dict) and coord in cv:
        return _to_float(cv.get(coord))
    td = ctx.get("table_data")
    if isinstance(td, dict):
        return _cell_value_from_table(
            td, {"cell": coord, "table_index": ctx.get("table_index", 0)}
        )
    return None


async def _resolve_formula_sum(
    binding: dict[str, Any],
    ctx: dict[str, Any],
) -> float | None:
    """SUM：对 binding.cells 指定的同表坐标求和 — 复用既有 evaluate_formula 内核.

    构造 ``ROW('c1') + ROW('c2') + ...`` 交由 ``formula_parse_utils.evaluate_formula``
    求值（不新造求值器，满足 Req1.2 / Property4）。缺任一坐标值 → 跳过该项；
    全部缺失 → None。
    """
    cells = binding.get("cells")
    if not isinstance(cells, list) or not cells:
        return None

    row_values: dict[str, Decimal] = {}
    terms: list[str] = []
    for c in cells:
        if not isinstance(c, str) or not c:
            continue
        v = _current_cell_value(ctx, c)
        if v is None:
            continue
        row_values[c] = Decimal(str(v))
        terms.append(f"ROW('{c}')")
    if not terms:
        return None

    formula = " + ".join(terms)
    from app.services.formula_parse_utils import evaluate_formula

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        result = await evaluate_formula(
            formula,
            ctx.get("db"),
            ctx.get("project_id"),
            ctx.get("year"),
            row_values=row_values,
        )
    if not isinstance(result, dict):
        return None
    return _to_float(result.get("value"))


def _resolve_formula_report(
    binding: dict[str, Any],
    ctx: dict[str, Any],
) -> float | None:
    """REPORT：按 row_code 取 ``ctx.report_data[row_code]``（current_period_amount）.

    row_code 不存在 / report_data 缺失 → None（Req1.3 / Property3）。
    """
    row_code = binding.get("row_code")
    if not isinstance(row_code, str) or not row_code:
        return None
    report_data = ctx.get("report_data")
    if not isinstance(report_data, dict):
        return None
    if row_code not in report_data:
        return None
    return _to_float(report_data.get(row_code))


def _resolve_formula_aging(
    binding: dict[str, Any],
    ctx: dict[str, Any],
) -> float | None:
    """AGING：按账龄段取 ``ctx.aging_data[band]``（复用既有账龄配置聚合结果）.

    ctx 无账龄数据 / 段缺失 → None（不新造账龄引擎）。
    """
    aging_data = ctx.get("aging_data")
    if not isinstance(aging_data, dict) or not aging_data:
        return None
    band = binding.get("band") or binding.get("bucket")
    if not isinstance(band, str) or not band:
        return None
    if band not in aging_data:
        return None
    return _to_float(aging_data.get(band))


async def resolve_formula(
    binding: dict[str, Any],
    ctx: dict[str, Any],
) -> Any:
    """表内公式引用求值（sum / report / aging / prior_year_note）.

    按 ``binding.source`` 装配数据后委托既有公式内核
    （``formula_parse_utils.evaluate_formula``）—— 不新造求值器（Design 决策1）。

    - ``source=='sum'``：对 binding.cells 同表坐标求和（走 evaluate_formula）
    - ``source=='report'``：按 row_code 取 ctx.report_data[row_code]
    - ``source=='aging'``：按账龄段取 ctx.aging_data[band]
    - ``source=='prior_year_note'``：委托 resolve_prior_year_note

    灰度：``DISCLOSURE_NOTE_FORMULA_ENABLED`` 默认 False 时保持 stub 行为返 None
    （零回归，Req8.3/8.4）。任一异常 / 缺数据 → None（fail-open，Req1.4，不抛到调用方）。
    """
    if not isinstance(binding, dict):
        return None
    if not _formula_enabled():
        return None

    source = binding.get("source")
    try:
        if source == "sum":
            return await _resolve_formula_sum(binding, ctx)
        if source == "report":
            return _resolve_formula_report(binding, ctx)
        if source == "aging":
            return _resolve_formula_aging(binding, ctx)
        if source == "prior_year_note":
            return await resolve_prior_year_note(binding, ctx)
    except Exception as err:
        logger.warning(
            "resolve_formula source=%s raised %s; returning None (fail-open)",
            source,
            err,
        )
        return None
    return None


# ---------------------------------------------------------------------------
# 6) prior_year_note — 走 ctx["_prior_notes_cache"]
# ---------------------------------------------------------------------------


async def resolve_prior_year_note(
    binding: dict[str, Any],
    ctx: dict[str, Any],
) -> Any:
    """从 ctx["_prior_notes_cache"] 取上年附注 — 不重复 SQL.

    binding 字段：
      - section / note_section: str    指定章节号（缺则回退 ctx["section_number"]）
      - field:         str             "value" / "text" — 取单元格数值 vs 取文本
      - cell / row+col: 坐标（value 模式用）
      - table_index:   int             多表定位（value 模式，默认 0）

    缓存结构（disclosure_engine._preload_data_for_notes 写入）现为：
      ctx["_prior_notes_cache"][note_section] = {"text": str|None, "table": dict|None}
    **向后兼容旧扁平字符串缓存** ``{note_section: text_content (str)}``。

    - field=='text'（历史行为，不受开关约束、不回归）：返回上年文本；
      dict 缓存取 .text、旧扁平缓存直接返回字符串。
    - field=='value'：按 section + 坐标(+table_index) 从上年 table 反查单元格金额；
      仅新 dict 缓存 + 开关开启时生效；无表 / 坐标不存在 / 旧扁平缓存 → None。

    上年无数据一律静默返回 None — 不阻塞（Req2.2）。
    """
    cache = ctx.get("_prior_notes_cache") or {}
    if not cache:
        return None

    section = binding.get("section") or binding.get("note_section")
    if not isinstance(section, str) or not section:
        # 没指定章节 — 调用方应该传 section_number 进 ctx
        section = ctx.get("section_number")
        if not isinstance(section, str) or not section:
            return None

    raw = cache.get(section)
    if raw is None:
        return None

    field = binding.get("field") or "value"

    if field == "text":
        # 兼容旧扁平字符串缓存 + 新 dict 缓存（text 模式不回归、不受开关约束）
        if isinstance(raw, str):
            return raw
        if isinstance(raw, dict):
            t = raw.get("text")
            return t if isinstance(t, str) else None
        return None

    # value 模式：单元格级反查（新行为，受开关控制 = 关闭时零回归 Req8.3/8.4）
    if not _formula_enabled():
        return None
    if not isinstance(raw, dict):
        # 旧扁平字符串缓存无单元格数据
        return None
    return _cell_value_from_table(raw.get("table"), binding)


# ---------------------------------------------------------------------------
# 7) manual — 直接读 binding.manual_value
# ---------------------------------------------------------------------------


async def resolve_manual(
    binding: dict[str, Any],
    ctx: dict[str, Any],  # noqa: ARG001 — 接口对齐
) -> Any:
    """读 binding.manual_value；缺则 None.

    类型透传（数值 / 字符串 / None） — 不强制转换.
    """
    if not isinstance(binding, dict):
        return None
    return binding.get("manual_value")


# ---------------------------------------------------------------------------
# 8) consol_aggregation — 合并附注从子公司单体附注汇总（D12）
# ---------------------------------------------------------------------------


async def resolve_consol_aggregation(
    binding: dict[str, Any],
    ctx: dict[str, Any],
) -> Any:
    """从子公司单体附注汇总数据到合并附注.

    binding 字段：
      - child_section_id: str          子公司单体附注对应章节 ID（CI-15 必有）
      - aggregation_method: str        聚合方式
      - aggregation_config: dict       聚合配置（top_n / threshold 等）
      - elimination_rules: list[dict]  抵销规则列表
      - child_filter: dict             子公司筛选

    ctx 字段：
      - project_id: UUID               合并项目 ID
      - year: int
      - db: AsyncSession

    返回 dict（聚合结果）或 None.
    """
    if not isinstance(binding, dict):
        return None

    child_section_id = binding.get("child_section_id")
    if not child_section_id:
        logger.warning("consol_aggregation binding missing child_section_id")
        return None

    project_id = ctx.get("project_id")
    year = ctx.get("year")
    db = ctx.get("db")
    if not project_id or not year:
        return None

    try:
        from app.services.consol_note_aggregation_service import aggregate_section

        method = binding.get("aggregation_method", "simple_sum")
        config = binding.get("aggregation_config") or {}
        elimination_rules = binding.get("elimination_rules") or []
        child_filter = binding.get("child_filter") or {}

        result = await aggregate_section(
            consol_project_id=project_id,
            section_id=child_section_id,
            year=year,
            method=method,
            config=config,
            elimination_rules=elimination_rules,
            child_filter=child_filter,
            db=db,
        )
        return result
    except Exception as err:
        logger.warning(
            "resolve_consol_aggregation failed: %s; returning None", err,
        )
        return None


# ---------------------------------------------------------------------------
# Dispatcher — source 字符串到 resolver 的映射
# ---------------------------------------------------------------------------


SOURCE_RESOLVERS: dict[str, Any] = {
    "trial_balance": resolve_trial_balance,
    "ledger_sum": resolve_ledger_sum,
    "aux_balance": resolve_aux_balance,
    "aux_ledger_aging": resolve_aux_ledger_aging,
    "wp_data": resolve_wp_data,
    "formula": resolve_formula,
    "prior_year_note": resolve_prior_year_note,
    "manual": resolve_manual,
    "consol_aggregation": resolve_consol_aggregation,
}

# 资源完整性 — 与 VALID_SOURCES 对齐（CI 单测断言）
assert set(SOURCE_RESOLVERS.keys()) == set(VALID_SOURCES), (
    "SOURCE_RESOLVERS keys must match VALID_SOURCES"
)


async def dispatch_resolver(
    binding: dict[str, Any],
    ctx: dict[str, Any],
) -> Any:
    """根据 binding.source 调用对应 resolver；未识别 source → None.

    缺 binding / 非 dict / 缺 source → None.
    """
    if not isinstance(binding, dict):
        return None
    source = binding.get("source")
    if not isinstance(source, str):
        return None
    fn = SOURCE_RESOLVERS.get(source)
    if fn is None:
        return None
    try:
        return await fn(binding, ctx)
    except Exception as err:
        logger.warning(
            "resolver %s raised %s; returning None for safety",
            source, err,
        )
        return None


__all__ = [
    "SOURCE_RESOLVERS",
    "VALID_SOURCES",
    "dispatch_resolver",
    "resolve_aux_balance",
    "resolve_aux_ledger_aging",
    "resolve_consol_aggregation",
    "resolve_formula",
    "resolve_ledger_sum",
    "resolve_manual",
    "resolve_prior_year_note",
    "resolve_trial_balance",
    "resolve_wp_data",
]
