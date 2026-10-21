"""统一预载层：批量扫描公式文本 → 一次性查 DB → 构建 FormulaContext。

spec: formula-execution-path-convergence Phase 1 · Task 2~6

取代 ``prefill_engine`` 的逐格查 DB 模式：扫描全部公式文本提取数据源引用，
按类型去重后批量查一次 DB，构建 ``FormulaContext`` 喂给 L1 内核 ``execute()``。

调用方传入的参数决定口径差异：
- ``adj_exclude_origins=frozenset()``   → 底稿路径（不排 origin）
- ``adj_exclude_origins=frozenset({"workpaper"})`` → 报表路径（排 workpaper）
"""
from __future__ import annotations

import logging
import re
import uuid
from decimal import Decimal, InvalidOperation
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.formula_engine import FormulaContext

logger = logging.getLogger(__name__)

# ── 公式文本扫描正则 ──────────────────────────────────────────────────────────

_TB_RE = re.compile(r"(?:SUM_)?TB\(\s*'([^']+)'")
_ADJ_RE = re.compile(r"ADJ\(\s*'([^']+)'")
_AUX_RE = re.compile(r"AUX\(\s*'([^']+)'\s*,\s*'([^']+)'\s*,\s*'([^']+)'\s*(?:,\s*'([^']+)')?\s*\)")
_WP_RE = re.compile(r"WP\(\s*'([^']+)'\s*,\s*'([^']+)'(?:\s*,\s*'([^']+)')?\s*\)")
_NOTE_RE = re.compile(r"NOTE\(\s*'([^']+)'\s*,\s*'([^']+)'(?:\s*,\s*'([^']+)')?\s*\)")
_PREV_RE = re.compile(r"PREV\(\s*'([^']+)'")
_LEDGER_RE = re.compile(r"(?:COUNT_)?LEDGER\(\s*'([^']+)'\s*,\s*'([^']+)'\s*(?:,\s*'([^']+)')?\s*\)")
_LEDGER_DETAIL_RE = re.compile(r"LEDGER_DETAIL\(\s*'([^']+)'\s*,\s*'([^']+)'\s*(?:,\s*'([^']+)')?\s*\)")
_TB_AUX_RE = re.compile(r"TB_AUX\(\s*'([^']+)'\s*,\s*'([^']+)'\s*,\s*'([^']+)'\s*\)")


def _scan_refs(formulas: list[str]) -> dict[str, set]:
    """扫描全部公式文本，提取各数据源引用（去重）。"""
    refs: dict[str, set] = {
        "tb_codes": set(),
        "adj_codes": set(),
        "aux_specs": set(),  # (account, aux_type, aux_code, column)
        "wp_refs": set(),    # (wp_code, column) or (wp_code, sheet, cell)
        "note_refs": set(),  # (section, field) or (section, field, row_label)
        "prev_codes": set(),
        "ledger_specs": set(),       # (account, direction, period)
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
        for m in _AUX_RE.finditer(t):
            refs["aux_specs"].add((m.group(1), m.group(2), m.group(3), m.group(4) or "期末余额"))
        for m in _WP_RE.finditer(t):
            refs["wp_refs"].add(tuple(g for g in m.groups() if g))
        for m in _NOTE_RE.finditer(t):
            refs["note_refs"].add(tuple(g for g in m.groups() if g))
        for m in _PREV_RE.finditer(t):
            refs["prev_codes"].add(m.group(1))
        for m in _LEDGER_RE.finditer(t):
            refs["ledger_specs"].add((m.group(1), m.group(2), m.group(3) or "全年"))
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
                   codes: set[str]) -> dict[str, dict[str, Decimal]]:
    """从 trial_balance 批量取科目数据（前缀聚合口径）。"""
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

    # 按前缀聚合（与 ReportFormulaParser._get_tb_rows_prefix 同口径）
    out: dict[str, dict[str, Decimal]] = {}
    for row in rows:
        code = row.standard_account_code
        if not code:
            continue
        for target_code in codes:
            if code.startswith(target_code) or code == target_code:
                entry = out.setdefault(target_code, {})
                for alias, standard in COLUMN_ALIASES.items():
                    if alias == standard:  # 只累加标准名一次
                        val = Decimal("0")
                        if standard == "期末余额":
                            val = _safe_decimal(row.audited_amount)
                        elif standard == "年初余额":
                            val = _safe_decimal(row.opening_balance)
                        elif standard == "本期发生额":
                            val = _safe_decimal(row.audited_amount) - _safe_decimal(row.opening_balance)
                        elif standard == "AJE调整":
                            val = _safe_decimal(row.aje_adjustment)
                        elif standard == "RJE调整":
                            val = _safe_decimal(row.rje_adjustment)
                        elif standard == "本期借方":
                            val = _safe_decimal(getattr(row, "debit_amount", None))
                        elif standard == "本期贷方":
                            val = _safe_decimal(getattr(row, "credit_amount", None))
                        entry[standard] = entry.get(standard, Decimal("0")) + val
    # 别名映射
    for code_data in out.values():
        for alias, standard in COLUMN_ALIASES.items():
            if alias != standard and standard in code_data:
                code_data[alias] = code_data[standard]
    return out


async def _load_adj(db: AsyncSession, project_id: uuid.UUID, year: int,
                    codes: set[str], exclude_origins: frozenset[str]) -> dict[str, dict[str, Decimal]]:
    """从 adjustment_amount_source 批量取调整额。"""
    if not codes:
        return {}
    try:
        from app.services.adjustment_amount_source import adj_net_batch
        return await adj_net_batch(db, project_id=project_id, year=year,
                                   account_codes=codes, exclude_origins=exclude_origins)
    except Exception as exc:
        logger.warning("preloader: adj_net_batch failed: %s", exc)
        return {}


async def _load_ledger(db: AsyncSession, project_id: uuid.UUID, year: int,
                       specs: set[tuple]) -> dict[str, Decimal]:
    """从 tb_ledger 批量取发生额。key = "{code}:{direction}:{period}"。"""
    if not specs:
        return {}
    from app.models.audit_platform_models import TbLedger
    from app.services.dataset_query import get_active_filter
    from app.services.prefill_engine import _parse_period_range

    active_filter = await get_active_filter(db, TbLedger.__table__, project_id, year)
    out: dict[str, Decimal] = {}
    for code, direction, period in specs:
        col = TbLedger.debit_amount if direction.lower() in ("debit", "借") else TbLedger.credit_amount
        q = sa.select(sa.func.coalesce(sa.func.sum(col), 0)).where(
            active_filter, TbLedger.account_code == code)
        start_p, end_p = _parse_period_range(period)
        if start_p is not None and end_p is not None and (start_p, end_p) != (1, 12):
            q = q.where(TbLedger.accounting_period.between(start_p, end_p))
        val = (await db.execute(q)).scalar()
        out[f"{code}:{direction}:{period}"] = _safe_decimal(val)
    return out


async def _load_ledger_count(db: AsyncSession, project_id: uuid.UUID, year: int,
                             specs: set[tuple]) -> dict[str, int]:
    """从 tb_ledger 取笔数。key = "{code}:{period}"。"""
    if not specs:
        return {}
    from app.models.audit_platform_models import TbLedger
    from app.services.dataset_query import get_active_filter
    from app.services.prefill_engine import _parse_period_range

    active_filter = await get_active_filter(db, TbLedger.__table__, project_id, year)
    out: dict[str, int] = {}
    # Deduplicate: ledger_specs has (code, direction, period), extract (code, period)
    code_periods = {(code, period) for code, _d, period in specs}
    for code, period in code_periods:
        q = sa.select(sa.func.count()).select_from(TbLedger).where(
            active_filter, TbLedger.account_code == code)
        start_p, end_p = _parse_period_range(period)
        if start_p is not None and end_p is not None and (start_p, end_p) != (1, 12):
            q = q.where(TbLedger.accounting_period.between(start_p, end_p))
        val = (await db.execute(q)).scalar()
        out[f"{code}:{period}"] = int(val or 0)
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
    try:
        from app.services.prefill_anchor_map import read_anchor_value, resolve_anchor
        for ref_tuple in refs:
            wp_code = ref_tuple[0]
            sheet = ref_tuple[1] if len(ref_tuple) > 1 else ""
            cell = ref_tuple[2] if len(ref_tuple) > 2 else sheet  # 2 参形式
            spec = resolve_anchor(wp_code, sheet, cell)
            if spec is None:
                continue
            try:
                res = await read_anchor_value(db, project_id, wp_code, spec)
                if res.value is not None:
                    out.setdefault(wp_code, {})[cell or sheet] = _safe_decimal(res.value)
            except Exception:
                pass
    except ImportError:
        logger.warning("preloader: prefill_anchor_map not available")
    return out


async def _load_note(db: AsyncSession, project_id: uuid.UUID, year: int,
                     refs: set[tuple], template_type: str) -> dict[str, dict[str, Decimal]]:
    """从披露表 sub_table_data 取附注值（复用 disclosure_source，与 note-data-from-disclosure-table 对齐）。

    spec: formula-execution-path-convergence 复盘修复 P0-2
    """
    if not refs:
        return {}
    out: dict[str, dict[str, Decimal]] = {}

    # 按 section 分组需要的 field
    section_fields: dict[str, set[str]] = {}
    for ref_tuple in refs:
        section = ref_tuple[0]
        field = ref_tuple[1] if len(ref_tuple) > 1 else ""
        section_fields.setdefault(section, set()).add(field)

    # 复用 disclosure_source 的 wp_code → section 映射查询 sub_table_data
    try:
        from app.services.formula_push.bindings.disclosure_source import (
            _load_section_map,
            load_disclosure_sub_table_data,
            note_rows_from_disclosure,
        )
    except ImportError:
        logger.warning("preloader._load_note: disclosure_source not available, falling back to direct query")
        return await _load_note_fallback(db, project_id, year, refs)

    # 反查 section → wp_code（section_map 是 wp_code → {listed/soe: section}）
    section_map = _load_section_map()
    section_to_wp: dict[str, str] = {}
    for wp_code, entry in section_map.items():
        for variant_key in ("listed", "soe"):
            sec = entry.get(variant_key, "")
            if sec:
                section_to_wp.setdefault(sec, wp_code)

    for section, fields in section_fields.items():
        wp_code = section_to_wp.get(section)
        if not wp_code:
            continue
        sub = await load_disclosure_sub_table_data(db, project_id, year, wp_code, template_type)
        if sub is None:
            continue
        entry = out.setdefault(section, {})
        for table_name, rows_list in sub.items():
            if not isinstance(rows_list, list):
                continue
            for row in rows_list:
                if not isinstance(row, dict):
                    continue
                label = str(row.get("label") or "").strip()
                for field in fields:
                    if not field:
                        continue
                    # 复用 disclosure_source._read_row_value 的多键名兼容
                    from app.services.formula_push.bindings.disclosure_source import _read_row_value
                    from app.services.formula_push.note_writer import NOTE_FIELDS
                    value_key = NOTE_FIELDS.get(field, (field, "end"))[0]
                    raw = _read_row_value(row, value_key, field)
                    if raw is not None:
                        entry[field] = _safe_decimal(raw)
                        if label:
                            entry[f"{label}:{field}"] = _safe_decimal(raw)
    return out


async def _load_note_fallback(db: AsyncSession, project_id: uuid.UUID, year: int,
                              refs: set[tuple]) -> dict[str, dict[str, Decimal]]:
    """降级：直接查 disclosure_notes（disclosure_source 不可用时）。"""
    out: dict[str, dict[str, Decimal]] = {}
    sections = {r[0] for r in refs}
    from app.models.report_models import DisclosureNote

    for section in sections:
        note = (await db.execute(
            sa.select(DisclosureNote).where(
                DisclosureNote.project_id == project_id,
                DisclosureNote.year == year,
                DisclosureNote.note_section == section,
                DisclosureNote.is_deleted == sa.false(),
            )
        )).scalar_one_or_none()
        if note is None or not isinstance(note.table_data, dict):
            continue
        td_rows = note.table_data.get("rows", [])
        for r in td_rows:
            if not isinstance(r, dict):
                continue
            for field_ref in refs:
                if field_ref[0] != section:
                    continue
                field = field_ref[1] if len(field_ref) > 1 else ""
                val = r.get("values", {}).get(field)
                if val is not None:
                    out.setdefault(section, {})[field] = _safe_decimal(val)
    return out


# ── 主入口 ────────────────────────────────────────────────────────────────────


async def preload(
    db: AsyncSession,
    project_id: uuid.UUID,
    year: int,
    formulas: list[str],
    *,
    adj_exclude_origins: frozenset[str] = frozenset(),
    template_type: str = "soe",
    row_cache: dict[str, Decimal] | None = None,
) -> FormulaContext:
    """批量扫描公式文本 → 一次性查 DB → 构建 FormulaContext。

    Args:
        formulas: 公式文本列表（可含 ``=`` 前缀）
        adj_exclude_origins: ADJ 取数排除的 origin 集合（底稿传空集、报表传 {"workpaper"}）
        template_type: 项目模板类型（"soe"/"listed"），影响附注取数的章节映射
        row_cache: 已计算的行次缓存（供 ROW/SUM_ROW/REPORT 引用）
    """
    refs = _scan_refs(formulas)

    # 批量查 DB（各数据源独立，失败不互相拖累）
    tb_data = await _load_tb(db, project_id, year, refs["tb_codes"])
    adj_data = await _load_adj(db, project_id, year, refs["adj_codes"], adj_exclude_origins)
    wp_data = await _load_wp(db, project_id, year, refs["wp_refs"])
    note_data = await _load_note(db, project_id, year, refs["note_refs"], template_type)
    ledger_data = await _load_ledger(db, project_id, year, refs["ledger_specs"])
    ledger_count = await _load_ledger_count(db, project_id, year, refs["ledger_specs"])
    tb_aux_data = await _load_tb_aux(db, project_id, year, refs["tb_aux_specs"])

    # PREV: 取上年 TB 数据
    prior_tb_data: dict[str, dict[str, Decimal]] = {}
    if refs["prev_codes"]:
        prior_tb_data = await _load_tb(db, project_id, year - 1, refs["prev_codes"])

    return FormulaContext(
        tb_data=tb_data,
        row_cache={k: Decimal(str(v)) for k, v in (row_cache or {}).items()},
        prior_tb_data=prior_tb_data,
        note_data=note_data,
        wp_data=wp_data,
        aux_data={},  # AUX 数据走 ctx.aux_data（已有字段，格式与 _load_aux 不同）
        adj_data=adj_data,
        ledger_data=ledger_data,
        ledger_detail_data={},  # Phase 2 实装 LEDGER_DETAIL 明细查询
        ledger_count_data=ledger_count,
        tb_aux_data=tb_aux_data,
    )
