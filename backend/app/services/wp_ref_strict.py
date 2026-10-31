"""严格外部取值（ADR-FHIC-06 第 3 点）——typed_eval 专用 WP 引用读取。

数据库异常原样上抛；取不到一律带中文原因，不代 0。
"""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from uuid import UUID

import sqlalchemy as sa

from app.models.workpaper_models import WorkingPaper, WpIndex
from app.services.wp_cell_reader import WpCellRead, _year_gate, resolve_wp_cell

__all__ = ["read_wp_ref_strict", "classify_wp_ref", "WP_COLUMN_KEYS"]

WP_COLUMN_KEYS: dict[str, str] = {
    "审定数": "audited_amount", "未审数": "unadjusted_amount",
    "期初余额": "opening_balance", "期末余额": "audited_amount",
}

_A1_RE = re.compile(r"^[A-Z]{1,3}[0-9]{1,7}$", re.IGNORECASE)
_D23_MARKER = "坏账准备明细表"

WpRefKind = str  # "cell_3"|"cell_2"|"column_2"|"d23_3"|"unknown"


def classify_wp_ref(second: str | None, third: str | None) -> WpRefKind:
    """按 (second, third) 判定 WP 引用写法。"""
    s, t = (second or "").strip(), (third or "").strip()
    if t:
        if _A1_RE.match(t) and _D23_MARKER not in s: return "cell_3"
        if _D23_MARKER in s: return "d23_3"
        return "unknown"
    if _A1_RE.match(s): return "cell_2"
    if s: return "column_2"
    return "unknown"


def _is_dep_edge_kind(kind: WpRefKind) -> bool:
    return kind in ("cell_3", "cell_2")


def _as_uuid(v) -> UUID:
    return v if isinstance(v, UUID) else UUID(str(v))


async def read_wp_ref_strict(db, project_id: UUID, year: int | None,
                             wp_code: str, second: str | None, third: str | None) -> WpCellRead:
    """严格外部取值入口。year=None 跳过闸门（批内已做过一次）。"""
    kind = classify_wp_ref(second, third)
    if kind == "cell_3":
        return await resolve_wp_cell(db, project_id, year, wp_code, second, third)
    if kind == "cell_2":
        return await resolve_wp_cell(db, project_id, year, wp_code, None, second)
    if kind == "column_2":
        return await _read_column(db, _as_uuid(project_id), year, wp_code, second or "")
    if kind == "d23_3":
        return await _read_d23(db, _as_uuid(project_id), year, wp_code, second or "", third)
    return WpCellRead("blocked", None, "引用写法无法识别", None, None)


async def _read_column(db, pid: UUID, year: int | None, wp_code: str, column: str) -> WpCellRead:
    gate = await _year_gate(db, pid, year)
    if gate is not None: return gate
    rows = (await db.execute(
        sa.select(WorkingPaper.id, WorkingPaper.parsed_data)
        .join(WpIndex, WorkingPaper.wp_index_id == WpIndex.id)
        .where(WorkingPaper.project_id == pid, WpIndex.project_id == pid,
               WpIndex.wp_code == wp_code, WorkingPaper.is_deleted == sa.false()).limit(2)
    )).all()
    if not rows:
        return WpCellRead("missing", None, f"项目中没有底稿 {wp_code}", None, None)
    if len(rows) > 1:
        return WpCellRead("blocked", None, "底稿记录有歧义", None, None)
    wp_id, pd = rows[0]
    key = WP_COLUMN_KEYS.get(column, column)
    data = pd if isinstance(pd, dict) else {}
    raw = data.get(key)
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return WpCellRead("missing", None, f"底稿 {wp_code} 无字段「{column}」的值", wp_id, None)
    try:
        val = Decimal(str(raw).strip())
        if not val.is_finite(): raise InvalidOperation
    except (InvalidOperation, ValueError):
        return WpCellRead("blocked", None, f"底稿 {wp_code} 字段「{column}」的值不是数值", wp_id, None)
    return WpCellRead("ok", val, None, wp_id, None)


async def _read_d23(db, pid: UUID, year: int | None, wp_code: str,
                    sheet_name: str, field: str | None) -> WpCellRead:
    gate = await _year_gate(db, pid, year)
    if gate is not None: return gate
    field_str = (field or "").strip()
    if not field_str:
        return WpCellRead("blocked", None, "坏账明细字段为空", None, None)

    from app.models.bad_debt_models import BadDebtDetailRow
    from app.services.bad_debt_nested_table_service import NestedTableService
    from app.services.formula_engine import _D23_FIELD_TO_COLUMN, _normalize_provision_name

    idx_rows = (await db.execute(
        sa.select(BadDebtDetailRow.wp_index_id, WpIndex.wp_code)
        .join(WpIndex, BadDebtDetailRow.wp_index_id == WpIndex.id)
        .where(WpIndex.project_id == pid, WpIndex.wp_code == wp_code).distinct()
    )).all()
    if not idx_rows:
        return WpCellRead("missing", None, f"底稿 {wp_code} 没有坏账准备明细数据", None, None)
    try:
        tree = await NestedTableService(db).get_tree(idx_rows[0][0])
    except Exception:
        return WpCellRead("missing", None, f"底稿 {wp_code} 坏账明细表无法读取", None, None)

    if "." in field_str:
        pk, _, sf = field_str.partition(".")
        col = _D23_FIELD_TO_COLUMN.get(sf.strip())
        if col is None:
            return WpCellRead("blocked", None, f"坏账明细字段无法识别：{sf}", None, None)
        nk = _normalize_provision_name(pk)
        for p in tree.parents:
            lb = _normalize_provision_name(p.provision_method_label)
            rl = _normalize_provision_name(p.row_label)
            if nk and (nk == lb or nk == rl or nk in lb or lb in nk or nk in rl):
                v = getattr(p.amounts, col, None)
                if v is None:
                    return WpCellRead("missing", None, f"坏账明细 {pk} 的 {sf} 为空", None, None)
                return WpCellRead("ok", Decimal(str(v)), None, None, None)
        return WpCellRead("missing", None, f"坏账明细找不到父行 {pk}", None, None)

    col = _D23_FIELD_TO_COLUMN.get(field_str)
    if col is None:
        return WpCellRead("blocked", None, f"坏账明细字段无法识别：{field_str}", None, None)
    v = getattr(tree.summary.amounts, col, None)
    if v is None:
        return WpCellRead("missing", None, f"坏账明细 {field_str} 为空", None, None)
    return WpCellRead("ok", Decimal(str(v)), None, None, None)
