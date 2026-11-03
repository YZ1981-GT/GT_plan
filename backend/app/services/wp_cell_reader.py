"""底稿单元格共享读取函数（formula-hub ADR-FHIC-06 第 1 点 / §8.2 契约；acnr-foundation-defect-closure T11 先落地）。

``resolve_wp_cell(db, project_id, year, wp_code, sheet_key, cell) -> WpCellRead``：按「年度闸门 → 底稿绑定 →
工作表过滤 → 单元格」四步读 ``working_paper.parsed_data``（经 ``extract_custom_cells``），三态：

- ``ok``：``value`` 为 Decimal；
- ``missing``：取不到（年度不符 / 项目中没有底稿 / 没有该工作表的数据 / 单元格未录入），``value`` 为 None；
- ``blocked``：数据本身不可用（项目未设置审计年度 / 底稿记录有歧义 / 工作表名有歧义 / 别名不能用于取值 /
  同一工作表有多份数据 / 单元格内容不是数值），``value`` 为 None。

非 ok 一律带中文原因，不代 0；数据库异常原样上抛，不转 missing。

``_catalog_sheet_keys`` 按 §8.2 首次落地恒为 ``not_found``（空集）：可接受键只有调用方给的 ``sheet_key`` 本身。
ACNR 一侧在 ``services/acnr/wp_cell_target.py`` 用锁定目录（``effective_catalog``）判身份后，把目录 sheet 名
归一后传进来；这里不另读目录——读当前目录会让锁定项目按新目录判名（design §2.4 R2-F7）。
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Literal
from uuid import UUID

import sqlalchemy as sa

from app.models.workpaper_models import WorkingPaper, WpIndex
from app.services.address_registry import extract_custom_cells
from app.services.formula_management.stable_key import normalize_sheet_key
from app.services.project_audit_year import fetch_project_audit_year

__all__ = ["CatalogSheetKeys", "WpCellRead", "resolve_wp_cell"]

ReadState = Literal["ok", "missing", "blocked"]
SheetVerdict = Literal["found", "not_found", "ambiguous", "alias_forbidden"]


@dataclass(frozen=True)
class WpCellRead:
    """一次单元格读取的结果（§8.2「返回」行）。"""

    state: ReadState
    #: 仅 ok 非空
    value: Decimal | None
    #: 非 ok 必有中文原因
    reason: str | None
    wp_id: UUID | None
    #: 命中记录在 ``html_data`` 中的真实表名（不是目录名）
    sheet_key: str | None
    #: 两参（不判表）时 = 含该单元格的表数
    matches: int = 0
    candidates: tuple[str, ...] = ()
    #: J1 补充（ACNR design §2.4 回退流程 B，默认 None 不改三态语义）：与 reason 对应的机器码，ok 为 None
    reason_code: str | None = None
    #: 找到单元格时为原文（文本格据此展示），否则 None
    raw: str | None = None


@dataclass(frozen=True)
class CatalogSheetKeys:
    """目录给出的可接受工作表键（模板名 / sheet_code / 别名）。"""

    keys: frozenset[str]
    verdict: SheetVerdict
    candidates: tuple[str, ...] = ()


def _catalog_sheet_keys(wp_code: str, sheet_key: str) -> CatalogSheetKeys:
    """§8.2：首次落地恒 not_found（空集）；见模块 docstring。"""
    return CatalogSheetKeys(keys=frozenset(), verdict="not_found")


def _as_uuid(value: UUID | str) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


async def _year_gate(db, project_id: UUID, year: int | None) -> WpCellRead | None:
    """``year is None`` 不比对；项目年度未知 ⇒ blocked；不符 ⇒ missing；相符 ⇒ None（继续）。"""
    if year is None:
        return None
    audit_year = await fetch_project_audit_year(db, project_id)
    if audit_year is None:
        return WpCellRead("blocked", None, "项目未设置审计年度", None, None, reason_code="year_unknown")
    if audit_year != year:
        return WpCellRead("missing", None, f"底稿年度与项目年度不符（项目 {audit_year}，请求 {year}）", None, None,
                          reason_code="year_mismatch")
    return None


def _to_decimal(raw: object) -> Decimal | None:
    if isinstance(raw, bool):
        return None
    try:
        value = Decimal(str(raw).strip())
    except (InvalidOperation, ValueError):
        return None
    return value if value.is_finite() else None


def _is_empty(raw: object) -> bool:
    return raw is None or (isinstance(raw, str) and not raw.strip())


async def resolve_wp_cell(db, project_id, year, wp_code, sheet_key, cell) -> WpCellRead:
    """读项目内某底稿某工作表某单元格（契约见 formula-hub design §8.2，本模块 docstring 摘要）。"""
    pid = _as_uuid(project_id)
    gate = await _year_gate(db, pid, year)
    if gate is not None:
        return gate

    rows = (await db.execute(
        sa.select(WorkingPaper.id, WorkingPaper.parsed_data)
        .join(WpIndex, WorkingPaper.wp_index_id == WpIndex.id)
        .where(
            WorkingPaper.project_id == pid,
            WpIndex.project_id == pid,
            WpIndex.wp_code == wp_code,
            WorkingPaper.is_deleted == sa.false(),
        )
        .limit(2)
    )).all()
    if not rows:
        return WpCellRead("missing", None, f"项目中没有底稿 {wp_code}", None, None, reason_code="wp_missing")
    if len(rows) > 1:
        return WpCellRead("blocked", None, "底稿记录有歧义", None, None,
                          candidates=tuple(str(r[0]) for r in rows), reason_code="wp_ambiguous")
    wp_id, parsed_data = rows[0]
    cell_up = str(cell or "").strip().upper()
    records = extract_custom_cells(parsed_data if isinstance(parsed_data, dict) else None)

    if sheet_key is None:
        hits = [r for r in records if r.cell == cell_up]
        if not hits:
            return WpCellRead("missing", None, "单元格未录入", wp_id, None, reason_code="cell_empty")
        return _value_read(hits[0].value, wp_id, hits[0].sheet, matches=len(hits))

    catalog = _catalog_sheet_keys(wp_code, sheet_key)
    if catalog.verdict == "ambiguous":
        return WpCellRead("blocked", None, "工作表名有歧义", wp_id, None, candidates=catalog.candidates,
                          reason_code="sheet_ambiguous")
    if catalog.verdict == "alias_forbidden":
        return WpCellRead("blocked", None, "该别名不能用于取值", wp_id, None, candidates=catalog.candidates,
                          reason_code="sheet_ambiguous")
    accepted = {normalize_sheet_key(k) for k in catalog.keys} | {normalize_sheet_key(sheet_key)}
    in_sheet = [r for r in records if normalize_sheet_key(r.sheet) in accepted]
    if not in_sheet:
        return WpCellRead("missing", None, "没有该工作表的数据", wp_id, None, reason_code="sheet_missing")
    hits = [r for r in in_sheet if r.cell == cell_up]
    if not hits:
        return WpCellRead("missing", None, "单元格未录入", wp_id, None, reason_code="cell_empty")
    if len({str(h.value) for h in hits}) > 1:
        return WpCellRead("blocked", None, "同一工作表有多份数据", wp_id, None,
                          matches=len(hits), candidates=tuple(h.sheet for h in hits), reason_code="sheet_ambiguous")
    return _value_read(hits[0].value, wp_id, hits[0].sheet, matches=len(hits))


def _value_read(raw: object, wp_id: UUID, sheet: str, *, matches: int) -> WpCellRead:
    text = None if raw is None else str(raw)
    if _is_empty(raw):
        return WpCellRead("missing", None, "单元格未录入", wp_id, sheet, matches=matches,
                          reason_code="cell_empty", raw=text)
    value = _to_decimal(raw)
    if value is None:
        return WpCellRead("blocked", None, f"单元格内容不是数值：{text[:50]}", wp_id, sheet, matches=matches,
                          reason_code="non_numeric", raw=text)
    return WpCellRead("ok", value, None, wp_id, sheet, matches=matches, reason_code=None, raw=text)
