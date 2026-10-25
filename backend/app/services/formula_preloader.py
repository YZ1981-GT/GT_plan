"""统一预载层：批量扫描公式文本 → 一次性查 DB → 构建 FormulaContext。

spec: formula-execution-path-convergence Phase 1 · Task 2~6

取代 ``prefill_engine`` 的逐格查 DB 模式：扫描全部公式文本提取数据源引用，
按类型去重后批量查一次 DB，构建 ``FormulaContext`` 喂给 L1 内核 ``execute()``。

调用方传入的参数决定口径差异：
- ``adj_exclude_origins=frozenset()``   → 底稿路径（不排 origin）
- ``adj_exclude_origins=frozenset({"workpaper"})`` → 报表路径（排 workpaper）

AUX 与报表行（spec formula-governance-coverage-closure R6.5）：AUX 按引用写法逐个取数（与表间审核严格代入
同一口径），存 ``aux_data[科目][aux_ref_key(参数)]``；调用方没给 ``row_cache`` 且公式引用了 ROW / SUM_ROW /
REPORT 时读本年度报表本期金额。``gaps`` 收集取数缺口，供严格调用方报错。

PREV（spec formula-fetch-and-wp-generation-defect-closure R2）：两参 / ``PREV(TB(…))`` 读上年试算表，三参（上年同底稿）
逐个预先求值进 ``prev_wp_data``、缺数原因进 ``prev_wp_missing``（L1 据此报错、不按 0）；两者的上年来源都是
``prior_year_context``（同项目上年 → 上年项目）。

三参 WP 与序时账（spec formula-fetch-followup-defect-closure 6.5）：三参 ``WP('底稿','表','锚点')`` 按「表!锚点」存值
（原先只按锚点存、L1 按第二参「表」取 ⇒ 已对齐的锚点也恒为 0）；LEDGER / COUNT_LEDGER / LEDGER_DETAIL 的方向、期间、
金额条件无法识别时不取数（原先按贷方 / 全年 / 不过滤取，给的是错数），L1 对没取的键报错。
"""
from __future__ import annotations

import logging
import re
import uuid
from decimal import Decimal, InvalidOperation
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.formula_engine import FormulaContext, aux_ref_key
from app.services.formula_ref_preload import (
    PREV3_RE,
    PREV_RE,
    PREV_TB_RE,
    AuxRef,
    load_report_rows,
    note_refs_in,
    parse_aux_refs,
    resolve_aux_refs,
)

logger = logging.getLogger(__name__)


def _gap(gaps: list[str] | None, reason: str) -> None:
    """记一条取数缺口（调用方传了 ``gaps`` 才记；不传 = 沿用非严格的置 0 行为）。"""
    if gaps is not None and reason not in gaps:
        gaps.append(reason)


# ── 公式文本扫描正则 ──────────────────────────────────────────────────────────

_TB_RE = re.compile(r"(?:SUM_)?TB\(\s*'([^']+)'")
_ADJ_RE = re.compile(r"ADJ\(\s*'([^']+)'")
#: 报表行引用（ROW / SUM_ROW / REPORT）：调用方没给 row_cache 时据此决定是否读本年度报表
_REPORT_REF_RE = re.compile(r"(?<![A-Za-z0-9_])(?:ROW|SUM_ROW|REPORT)\s*\(")
_WP_RE = re.compile(r"WP\(\s*'([^']+)'\s*,\s*'([^']+)'(?:\s*,\s*'([^']+)')?\s*\)")
#: LEDGER('科目','方向'[,'范围'])；前面紧挨字母 / 下划线的（COUNT_LEDGER）不算
_LEDGER_RE = re.compile(r"(?<![A-Za-z0-9_])LEDGER\(\s*'([^']+)'\s*,\s*'([^']+)'\s*(?:,\s*'([^']+)')?\s*\)")
#: COUNT_LEDGER('科目'[,'范围'])：原先混在 LEDGER 里扫，第二参被当成方向、期间恒按全年 ⇒ 非全年的笔数恒取不到
_COUNT_LEDGER_RE = re.compile(r"COUNT_LEDGER\(\s*'([^']+)'\s*(?:,\s*'([^']+)'\s*)?\)")
_LEDGER_DETAIL_RE = re.compile(r"LEDGER_DETAIL\(\s*'([^']+)'\s*(?:,\s*'([^']+)'\s*)?(?:,\s*'([^']+)'\s*)?\)")
_TB_AUX_RE = re.compile(r"TB_AUX\(\s*'([^']+)'\s*,\s*'([^']+)'\s*,\s*'([^']+)'\s*\)")


def _scan_refs(formulas: list[str]) -> dict[str, set]:
    """扫描全部公式文本，提取各数据源引用（去重）。"""
    refs: dict[str, set] = {
        "tb_codes": set(),
        "adj_codes": set(),
        "aux_specs": set(),  # formula_ref_preload.AuxRef（四参 / 三参 / 两参，按写法原样）
        "report_refs": set(),  # 出现过的 ROW / SUM_ROW / REPORT 调用（只用于判断要不要读报表）
        "wp_refs": set(),    # (wp_code, column) or (wp_code, sheet, cell)
        "note_refs": set(),  # (章节, 行, 列)；两参写法列为空串
        "prev_codes": set(),        # PREV 两参 / PREV(TB(…)) 的科目（上年试算表）
        "prev_wp_refs": set(),      # PREV 三参 (底稿, 表, 字段)（上年同底稿取数）
        "ledger_specs": set(),       # (account, direction, period)
        "ledger_count_specs": set(),   # (account, period)
        "ledger_detail_specs": set(),  # (account, period, amount_filter)
        "tb_aux_specs": set(),       # (account, aux_type, column)
    }
    for text in formulas:
        if not text:
            continue
        t = text.lstrip("=").strip()
        for m in _TB_RE.finditer(t):
            refs["tb_codes"].add(m.group(1))
        for m in _ADJ_RE.finditer(t):
            refs["adj_codes"].add(m.group(1))
        refs["aux_specs"].update(parse_aux_refs(t))
        refs["report_refs"].update(m.group(0) for m in _REPORT_REF_RE.finditer(t))
        for m in _WP_RE.finditer(t):
            refs["wp_refs"].add(tuple(g for g in m.groups() if g))
        # NOTE 与严格代入同一个识别正则（允许空参：预设公式写 NOTE('五、1','','') = 合计行第一列）
        refs["note_refs"].update(note_refs_in(t))
        for m in (*PREV_RE.finditer(t), *PREV_TB_RE.finditer(t)):
            refs["prev_codes"].add(m.group(1))
        for m in PREV3_RE.finditer(t):
            refs["prev_wp_refs"].add((m.group(1).strip(), m.group(2).strip(), m.group(3).strip()))
        for m in _LEDGER_RE.finditer(t):
            refs["ledger_specs"].add((m.group(1), m.group(2), m.group(3) or "全年"))
        for m in _COUNT_LEDGER_RE.finditer(t):
            refs["ledger_count_specs"].add((m.group(1), m.group(2) or "全年"))
        for m in _LEDGER_DETAIL_RE.finditer(t):
            refs["ledger_detail_specs"].add((m.group(1), m.group(2) or "全年", m.group(3) or "*"))
        for m in _TB_AUX_RE.finditer(t):
            refs["tb_aux_specs"].add((m.group(1), m.group(2), m.group(3)))
    return refs


# ── 各数据源批量查 DB ─────────────────────────────────────────────────────────

def _safe_decimal(val: Any) -> Decimal:
    if val is None:
        return Decimal("0")
    try:
        return Decimal(str(val))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


async def _load_tb(db: AsyncSession, project_id: uuid.UUID, year: int,
                   codes: set[str], *, with_occurrence: bool = False) -> dict[str, dict[str, Decimal]]:
    """从 trial_balance 批量取科目数据（前缀聚合口径）。

    ``'起~止'`` 形态（SUM_TB 的区间）按区间聚合，存在区间本身这个键下（L1 ``_sum_tb_value`` 优先用它）；原先当科目前缀，
    一条也匹配不到 ⇒ 区间求和恒 0。发生额（本期借方 / 本期贷方）``trial_balance`` 没有这两列，原先 ``getattr`` 恒取到 0；
    ``with_occurrence`` 时改取 ``tb_balance`` 叶子归集（与底稿求值器、初次预填同一共享件）。
    spec formula-fetch-followup-defect-closure R7。
    """
    if not codes:
        return {}
    from app.models.audit_platform_models import TrialBalance
    from app.services.formula_engine import COLUMN_ALIASES

    rows = (await db.execute(
        sa.select(TrialBalance).where(
            TrialBalance.project_id == project_id,
            TrialBalance.year == year,
            TrialBalance.is_deleted == sa.false(),
        )
    )).scalars().all()

    ranges = {c: tuple(p.strip() for p in c.split("~", 1)) for c in codes if c.count("~") == 1}
    plain = [c for c in codes if c not in ranges]

    def _targets(code: str) -> list[str]:
        hits = [t for t in plain if code.startswith(t)]
        return hits + [r for r, (start, end) in ranges.items() if start and start <= code[:len(start)] <= end]

    # 按前缀聚合（与 ReportFormulaParser._get_tb_rows_prefix 同口径）
    out: dict[str, dict[str, Decimal]] = {}
    for row in rows:
        code = row.standard_account_code
        if not code:
            continue
        columns = {
            "期末余额": _safe_decimal(row.audited_amount),
            "年初余额": _safe_decimal(row.opening_balance),
            "本期发生额": _safe_decimal(row.audited_amount) - _safe_decimal(row.opening_balance),
            "AJE调整": _safe_decimal(row.aje_adjustment),
            "RJE调整": _safe_decimal(row.rje_adjustment),
        }
        for target_code in _targets(code):
            entry = out.setdefault(target_code, {})
            for standard, val in columns.items():
                entry[standard] = entry.get(standard, Decimal("0")) + val
    if with_occurrence:
        from app.services.four_table.occurrence_by_standard_code import (
            CREDIT_KEY,
            DEBIT_KEY,
            fetch_occurrence_by_standard_code,
        )

        occurrence = await fetch_occurrence_by_standard_code(db, project_id, year)
        for target_code in codes:
            if target_code in ranges:
                start, end = ranges[target_code]
                picked = [v for c, v in occurrence.items() if start and start <= c[:len(start)] <= end]
            else:  # 单科目与底稿求值器同口径：按标准码取归集结果
                picked = [occurrence[target_code]] if target_code in occurrence else []
            if picked:
                entry = out.setdefault(target_code, {})
                entry["本期借方"] = sum((_safe_decimal(v.get(DEBIT_KEY)) for v in picked), Decimal("0"))
                entry["本期贷方"] = sum((_safe_decimal(v.get(CREDIT_KEY)) for v in picked), Decimal("0"))
    # 别名映射
    for code_data in out.values():
        for alias, standard in COLUMN_ALIASES.items():
            if alias != standard and standard in code_data:
                code_data[alias] = code_data[standard]
    return out


async def _load_adj(db: AsyncSession, project_id: uuid.UUID, year: int,
                    codes: set[str], exclude_origins: frozenset[str],
                    gaps: list[str] | None = None) -> dict[str, dict[str, Decimal]]:
    """从 adjustment_amount_source 批量取调整额（只含已审批分录；某科目没有分录 = 合法的 0）。"""
    if not codes:
        return {}
    try:
        from app.services.adjustment_amount_source import adj_net_batch
        async with db.begin_nested():
            return await adj_net_batch(db, project_id=project_id, year=year,
                                       account_codes=codes, exclude_origins=exclude_origins)
    except Exception as exc:
        logger.warning("preloader: adj_net_batch failed: %s", exc)
        _gap(gaps, f"调整分录取数失败：{exc}")
        return {}


async def _load_aux(db: AsyncSession, project_id: uuid.UUID, year: int,
                    refs: set[AuxRef], gaps: list[str] | None = None) -> dict[str, dict[str, Decimal]]:
    """按 AUX 引用写法逐个取数（与表间审核严格代入同一口径，``formula_ref_preload.resolve_aux_refs``）。

    结果存 ``aux_data[科目][aux_ref_key(参数)]``，L1 ``_handle_aux`` 用同一键取值；取不到的引用不存值并记缺口。
    """
    if not refs:
        return {}
    ordered = sorted(refs, key=lambda ref: ref.token)
    try:
        async with db.begin_nested():
            resolved = await resolve_aux_refs(db, project_id, year, ordered)
    except Exception as exc:
        logger.warning("preloader: aux 取数失败: %s", exc)
        _gap(gaps, f"辅助核算余额取数失败：{exc}")
        return {}
    out: dict[str, dict[str, Decimal]] = {}
    for ref in ordered:
        value, reason = resolved[ref.token]
        if value is None:
            _gap(gaps, f"{ref.token}：{reason}")
            continue
        out.setdefault(ref.account, {})[aux_ref_key((ref.account, *ref.args))] = value
    return out


async def _load_report_rows(db: AsyncSession, project_id: uuid.UUID, year: int,
                            gaps: list[str] | None = None) -> dict[str, Decimal]:
    """本年度报表本期金额 → row_cache（供 ROW / SUM_ROW / REPORT）；报表未生成记缺口。"""
    try:
        async with db.begin_nested():
            rows = await load_report_rows(db, project_id, year)
    except Exception as exc:
        logger.warning("preloader: 报表行取数失败: %s", exc)
        _gap(gaps, f"报表行取数失败：{exc}")
        return {}
    if not rows:
        _gap(gaps, f"本年度（{year}）报表未生成")
    return {code: Decimal(str(current)) for code, (current, _prior) in rows.items() if current is not None}


#: 序时账方向：只认这两组写法（原先其余一律按贷方取，`LEDGER('1403','期末数量')` 得到的是贷方发生额）
_DEBIT_WORDS = frozenset({"debit", "借"})
_CREDIT_WORDS = frozenset({"credit", "贷"})
#: LEDGER_DETAIL 明细行上限：超过就不取（L1 按行数给值，截断后的行数是错数）
LEDGER_DETAIL_LIMIT = 200
_AMOUNT_FILTER_RE = re.compile(r"^(>=|<=|>|<|==|=)\s*(-?\d+(?:\.\d+)?)$")


def _period_clause(column: Any, period: str) -> tuple[bool, Any]:
    """期间 →（能识别, 条件）：全年无条件；「3月」「1-6月」「7~12月」「3」；无法识别 / 月份越界 ⇒ (False, None)。

    原先无法识别的期间不加条件、按全年取（错数）。"""
    from app.services.prefill_engine import _parse_period_range

    start, end = _parse_period_range(period)
    if start is None or end is None or not 1 <= start <= end <= 12:
        return False, None
    return True, (None if (start, end) == (1, 12) else column.between(start, end))


def _amount_clause(table: Any, amount_filter: str) -> Any:
    """金额条件 → 条件（借方或贷方任一侧成立即命中，与原 prefill 实现同口径）；``*`` / 空 ⇒ None；无法识别 ⇒ False。"""
    text = (amount_filter or "").strip()
    if text in ("", "*"):
        return None
    m = _AMOUNT_FILTER_RE.match(text)
    if m is None:
        return False
    op, threshold = ("==" if m.group(1) == "=" else m.group(1)), Decimal(m.group(2))
    compare = {">=": lambda c: c >= threshold, "<=": lambda c: c <= threshold, ">": lambda c: c > threshold,
               "<": lambda c: c < threshold, "==": lambda c: c == threshold}[op]
    return sa.or_(compare(table.debit_amount), compare(table.credit_amount))


def _account_clause(column: Any, code: str) -> Any:
    """科目：含 ``%`` 按 LIKE（与原 COUNT_LEDGER / LEDGER_DETAIL 实现同口径），否则精确匹配。"""
    return column.like(code) if "%" in code else column == code


async def _load_ledger(db: AsyncSession, project_id: uuid.UUID, year: int,
                       specs: set[tuple]) -> dict[str, Decimal]:
    """从 tb_ledger 批量取发生额。key = "{code}:{direction}:{period}"；方向 / 期间无法识别的不取（L1 报错）。"""
    if not specs:
        return {}
    from app.models.audit_platform_models import TbLedger
    from app.services.dataset_query import get_active_filter

    active_filter = await get_active_filter(db, TbLedger.__table__, project_id, year)
    out: dict[str, Decimal] = {}
    for code, direction, period in sorted(specs):
        word = direction.strip().lower()
        col = TbLedger.debit_amount if word in _DEBIT_WORDS else TbLedger.credit_amount if word in _CREDIT_WORDS else None
        ok, clause = _period_clause(TbLedger.accounting_period, period)
        if col is None or not ok:
            logger.warning("preloader: LEDGER('%s','%s','%s') 方向或期间无法识别，不取数", code, direction, period)
            continue
        q = sa.select(sa.func.coalesce(sa.func.sum(col), 0)).where(active_filter, TbLedger.account_code == code)
        if clause is not None:
            q = q.where(clause)
        val = (await db.execute(q)).scalar()
        out[f"{code}:{direction}:{period}"] = _safe_decimal(val)
    return out


async def _load_ledger_count(db: AsyncSession, project_id: uuid.UUID, year: int,
                             specs: set[tuple]) -> dict[str, int]:
    """从 tb_ledger 取笔数。key = "{code}:{period}"（``COUNT_LEDGER('科目','范围')``）；期间无法识别的不取。"""
    if not specs:
        return {}
    from app.models.audit_platform_models import TbLedger
    from app.services.dataset_query import get_active_filter

    active_filter = await get_active_filter(db, TbLedger.__table__, project_id, year)
    out: dict[str, int] = {}
    for code, period in sorted(specs):
        ok, clause = _period_clause(TbLedger.accounting_period, period)
        if not ok:
            logger.warning("preloader: COUNT_LEDGER('%s','%s') 期间无法识别，不取数", code, period)
            continue
        q = sa.select(sa.func.count()).select_from(TbLedger).where(
            active_filter, _account_clause(TbLedger.account_code, code))
        if clause is not None:
            q = q.where(clause)
        val = (await db.execute(q)).scalar()
        out[f"{code}:{period}"] = int(val or 0)
    return out


async def _load_ledger_detail(db: AsyncSession, project_id: uuid.UUID, year: int,
                              specs: set[tuple]) -> dict[str, list[dict[str, Any]]]:
    """LEDGER_DETAIL 明细行。key = "{code}:{period}:{amount_filter}" → 按凭证日期 / 凭证号排序的明细。

    L1 按行数给值（spec formula-execution-path-convergence R2.2）；原先预载层从不取这份数据 ⇒ 恒为 0 笔。
    期间 / 金额条件无法识别、符合条件超过 :data:`LEDGER_DETAIL_LIMIT` 行 ⇒ 不存这个键（L1 报错，不给截断后的行数）。
    """
    if not specs:
        return {}
    from app.models.audit_platform_models import TbLedger
    from app.services.dataset_query import get_active_filter

    active_filter = await get_active_filter(db, TbLedger.__table__, project_id, year)
    out: dict[str, list[dict[str, Any]]] = {}
    for code, period, amount_filter in sorted(specs):
        ok, period_cond = _period_clause(TbLedger.accounting_period, period)
        amount_cond = _amount_clause(TbLedger, amount_filter)
        if not ok or amount_cond is False:
            logger.warning("preloader: LEDGER_DETAIL('%s','%s','%s') 期间或金额条件无法识别，不取数",
                           code, period, amount_filter)
            continue
        q = sa.select(TbLedger.voucher_date, TbLedger.voucher_no, TbLedger.summary, TbLedger.debit_amount,
                      TbLedger.credit_amount, TbLedger.counterpart_account, TbLedger.account_code,
                      TbLedger.account_name).where(active_filter, _account_clause(TbLedger.account_code, code))
        for cond in (period_cond, amount_cond):
            if cond is not None:
                q = q.where(cond)
        q = q.order_by(TbLedger.voucher_date.asc(), TbLedger.voucher_no.asc()).limit(LEDGER_DETAIL_LIMIT + 1)
        rows = (await db.execute(q)).all()
        if len(rows) > LEDGER_DETAIL_LIMIT:
            logger.warning("preloader: LEDGER_DETAIL('%s','%s','%s') 符合条件超过 %d 行，不取数",
                           code, period, amount_filter, LEDGER_DETAIL_LIMIT)
            continue
        out[f"{code}:{period}:{amount_filter}"] = [{
            "voucher_date": r.voucher_date.isoformat() if r.voucher_date else None,
            "voucher_no": r.voucher_no, "summary": r.summary or "",
            "debit_amount": str(_safe_decimal(r.debit_amount)), "credit_amount": str(_safe_decimal(r.credit_amount)),
            "counterpart_account": r.counterpart_account or "", "account_code": r.account_code,
            "account_name": r.account_name or "",
        } for r in rows]
    return out


async def _load_tb_aux(db: AsyncSession, project_id: uuid.UUID, year: int,
                       specs: set[tuple]) -> dict[str, Decimal]:
    """从 tb_aux_balance 取汇总值。key = "{code}:{aux_type}:{column}"。"""
    if not specs:
        return {}
    from app.models.audit_platform_models import TbAuxBalance
    from app.services.dataset_query import get_active_filter

    active_filter = await get_active_filter(db, TbAuxBalance.__table__, project_id, year)
    col_map = {
        "期末余额": TbAuxBalance.closing_balance,
        "期初余额": TbAuxBalance.opening_balance,
        "借方发生额": TbAuxBalance.debit_amount,
        "贷方发生额": TbAuxBalance.credit_amount,
    }
    out: dict[str, Decimal] = {}
    for code, aux_type, column in specs:
        col_attr = col_map.get(column, TbAuxBalance.closing_balance)
        q = sa.select(sa.func.coalesce(sa.func.sum(col_attr), 0)).where(
            active_filter, TbAuxBalance.account_code == code,
            TbAuxBalance.aux_type == aux_type)
        val = (await db.execute(q)).scalar()
        out[f"{code}:{aux_type}:{column}"] = _safe_decimal(val)
    return out


async def _load_wp(db: AsyncSession, project_id: uuid.UUID, year: int,
                   refs: set[tuple]) -> dict[str, dict[str, Decimal]]:
    """从 checklist_responses + prefill_anchor_map 取底稿值。"""
    if not refs:
        return {}
    out: dict[str, dict[str, Decimal]] = {}
    from app.services.prefill_anchor_map import read_anchor_value, resolve_anchor

    for ref_tuple in sorted(refs):
        wp_code = ref_tuple[0]
        sheet = ref_tuple[1] if len(ref_tuple) > 1 else ""
        cell = ref_tuple[2] if len(ref_tuple) > 2 else sheet  # 2 参形式
        spec = resolve_anchor(wp_code, sheet, cell)
        if spec is None:
            # 未对齐的锚点留日志：静默跳过会让「接线没生效」伪装成「本项目无此数据」
            logger.warning("preloader: WP 锚点未对齐，不取值 WP('%s','%s','%s')", wp_code, sheet, cell)
            continue
        try:
            async with db.begin_nested():  # 取值 SQL 出错只回滚自己，不让后续预载停在中止的事务里
                res = await read_anchor_value(db, project_id, wp_code, spec)
        except Exception:  # noqa: BLE001 —— fail-soft，但不得静默
            logger.warning("preloader: WP 取值失败 WP('%s','%s','%s')", wp_code, sheet, cell, exc_info=True)
            continue
        if res.value is not None:  # 三参按「表!锚点」存（L1 _handle_wp 同一写法取）；两参按列名
            key = f"{sheet.strip()}!{cell.strip()}" if len(ref_tuple) > 2 else (cell or sheet)
            out.setdefault(wp_code, {})[key] = _safe_decimal(res.value)
    return out


async def _load_note(db: AsyncSession, project_id: uuid.UUID, year: int,
                     refs: set[tuple], gaps: list[str] | None = None) -> dict[str, dict[str, Decimal]]:
    """附注取数：按章节 / 行 / 列取本年度附注单元格，取不到的写进 ``gaps``（L1 ``_handle_note`` 仍按 0 求值）。

    委托 NOTE 取数的唯一实现 ``formula_ref_preload.load_note_values``（按行标签 + 表头列名定位，与引用校验、
    严格代入、报表求值同一套匹配；值按 ``note_value_key(行, 列)`` 存）。

    原实现只读披露表同步数据 ``sub_table_data``、按第二参当字段键（``end_amount`` 等）取最后一行的值 ⇒
    ``NOTE('五、1','合计','期末余额')`` 这种标准写法恒取不到、静默为 0，公式调试也不提示；它的降级分支
    ``_load_note_fallback`` 把 ``values``（列表）当字典取 ⇒ 恒抛错（spec formula-fetch-followup-defect-closure 7.2）。
    """
    if not refs:
        return {}
    from app.services.formula_ref_preload import load_note_values, note_token

    wanted = [(str(r[0]).strip(), r[1] if len(r) > 1 else "", r[2] if len(r) > 2 else "") for r in refs]
    values, missing = await load_note_values(db, project_id, year, sorted(set(wanted)))
    for ref, why in missing.items():
        _gap(gaps, f"{note_token(ref)}：{why}")
    return values


def _mentions_occurrence(formulas: list[str]) -> bool:
    """公式里用了发生额列（本期借方 / 本期贷方及其别名）⇒ 预载要取 ``tb_balance`` 归集。"""
    from app.services.formula_engine import COLUMN_ALIASES

    aliases = [a for a, s in COLUMN_ALIASES.items() if s in ("本期借方", "本期贷方")]
    return any(a in (text or "") for text in formulas for a in aliases)


async def _load_prev(db: AsyncSession, project_id: uuid.UUID, year: int, refs: dict[str, set],
                     gaps: list[str] | None, *, with_occurrence: bool = False,
                     ) -> tuple[dict[str, dict[str, Decimal]], dict, dict]:
    """PREV 两参 → 上年试算表（前缀聚合）；三参 → 逐个上年同底稿取数。上年来源同一（``prior_year_context``）。"""
    prior_tb: dict[str, dict[str, Decimal]] = {}
    values: dict[tuple[str, str, str], Decimal] = {}
    missing: dict[tuple[str, str, str], str] = {}
    if not refs["prev_codes"] and not refs["prev_wp_refs"]:
        return prior_tb, values, missing
    from app.services.prev_wp_field import PriorWpFieldResolver

    resolver = PriorWpFieldResolver(db, project_id, year)
    if refs["prev_codes"]:
        source = await resolver.source()
        if source.project_id is None:
            _gap(gaps, f"PREV 上年试算表：{source.reason}")
        else:
            prior_tb = await _load_tb(db, source.project_id, source.year, refs["prev_codes"],
                                      with_occurrence=with_occurrence)
    for key in sorted(refs["prev_wp_refs"]):
        hit = await resolver.resolve(*key)
        if hit.value is None:
            missing[key] = hit.reason
            _gap(gaps, f"PREV('{key[0]}','{key[1]}','{key[2]}')：{hit.reason}")
        else:
            values[key] = hit.value
    return prior_tb, values, missing


# ── 主入口 ────────────────────────────────────────────────────────────────────


async def preload(
    db: AsyncSession,
    project_id: uuid.UUID,
    year: int,
    formulas: list[str],
    *,
    adj_exclude_origins: frozenset[str] = frozenset(),
    row_cache: dict[str, Decimal] | None = None,
    gaps: list[str] | None = None,
) -> FormulaContext:
    """批量扫描公式文本 → 一次性查 DB → 构建 FormulaContext。

    Args:
        formulas: 公式文本列表（可含 ``=`` 前缀）
        adj_exclude_origins: ADJ 取数排除的 origin 集合（底稿传空集、报表传 {"workpaper"}）
        row_cache: 已计算的行次缓存（供 ROW/SUM_ROW/REPORT 引用）；不传且公式引用了报表行 ⇒ 读本年度报表本期金额
        gaps: 传入列表时记取数缺口（报表未生成、辅助核算取不到、调整分录取数失败、附注单元格取不到），供严格调用方报错；
            不传 = 非严格（缺数按 0，L1 内核行为）

    原有 ``template_type`` 参数已删：只用于附注旧取法的「底稿 → 附注章节」映射；NOTE 第一参就是本项目附注的
    章节编号，按编号直接取，不需要口径（spec formula-fetch-followup-defect-closure 7.2）。
    """
    refs = _scan_refs(formulas)

    # 批量查 DB（各数据源独立，失败不互相拖累）
    with_occurrence = _mentions_occurrence(formulas)
    tb_data = await _load_tb(db, project_id, year, refs["tb_codes"], with_occurrence=with_occurrence)
    adj_data = await _load_adj(db, project_id, year, refs["adj_codes"], adj_exclude_origins, gaps)
    aux_data = await _load_aux(db, project_id, year, refs["aux_specs"], gaps)
    if row_cache is None and refs["report_refs"]:
        row_cache = await _load_report_rows(db, project_id, year, gaps)
    wp_data = await _load_wp(db, project_id, year, refs["wp_refs"])
    note_data = await _load_note(db, project_id, year, refs["note_refs"], gaps)
    ledger_data = await _load_ledger(db, project_id, year, refs["ledger_specs"])
    ledger_count = await _load_ledger_count(db, project_id, year, refs["ledger_count_specs"])
    ledger_detail = await _load_ledger_detail(db, project_id, year, refs["ledger_detail_specs"])
    tb_aux_data = await _load_tb_aux(db, project_id, year, refs["tb_aux_specs"])

    prior_tb_data, prev_wp_data, prev_wp_missing = await _load_prev(db, project_id, year, refs, gaps,
                                                                    with_occurrence=with_occurrence)

    return FormulaContext(
        tb_data=tb_data,
        row_cache={k: Decimal(str(v)) for k, v in (row_cache or {}).items()},
        prior_tb_data=prior_tb_data,
        prev_wp_data=prev_wp_data,
        prev_wp_missing=prev_wp_missing,
        note_data=note_data,
        wp_data=wp_data,
        aux_data=aux_data,
        adj_data=adj_data,
        ledger_data=ledger_data,
        ledger_detail_data=ledger_detail,
        ledger_count_data=ledger_count,
        tb_aux_data=tb_aux_data,
    )
