"""ACNR 侧的底稿单元格取值接线（design §2.4，T12）。

本模块是 ACNR 取值的唯一接线：判身份只经 ``exact_identity``（目录按 ``effective_catalog`` 取，锁定项目用锁定目录，
R2-F7），取值只经共享读取函数 ``wp_cell_reader.resolve_wp_cell``；不读 ``parsed_data``、不调 ``extract_custom_cells``。

- ``sheet_key_for``：目录 sheet 名在父级内唯一指向本 sheet ⇒ 归一后的名称作读取键；被别的 sheet 借用或父级内
  多义 ⇒ blocked ``sheet_name_borrowed``；
- ``bind_wp_code``：项目有 sheet 级底稿（``wp_index.wp_code == sheet_code``，与 ``resolve_instance`` 第 1 步同一查询）
  读它，否则读父底稿——只在「sheet 级底稿不存在」时回落；
- ``read_entry_cell`` / ``read_formula_cell``：见各函数；
- 原因细化（PG）：``missing`` 且原因为没有该表 / 单元格未录入时，按底稿存储形态改为 ``value_in_form_storage``（表单
  录入）或 ``value_in_file``（只有在线编辑文件），每张底稿每个会话查一次（``db.info`` 记忆）。

数据库异常一律上抛，不伪装成 missing。
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import UUID

import sqlalchemy as sa

from app.models.workpaper_models import WpIndex
from app.services.acnr import exact_identity
from app.services.acnr.catalog import get_catalog
from app.services.acnr.reasons import CELL_VALUE_REASONS
from app.services.acnr.project_registry_lock import get_locked_version
from app.services.acnr.metrics import get_acnr_metrics
from app.services.formula_management.stable_key import normalize_sheet_key
from app.services.wp_cell_reader import WpCellRead, resolve_wp_cell

if TYPE_CHECKING:
    from app.services.acnr.catalog import CatalogIndex

__all__ = [
    "SheetKey", "TargetRead", "bind_wp_code", "effective_catalog", "read_entry_cell", "read_formula_cell",
    "sheet_key_for",
]

#: 细化后的两个 missing 原因（design §2.2 表；文案唯一来源 reasons.CELL_VALUE_REASONS）
FORM_STORAGE_REASON = CELL_VALUE_REASONS["value_in_form_storage"]
FILE_ONLY_REASON = CELL_VALUE_REASONS["value_in_file"]
_REFINABLE = frozenset({"sheet_missing", "cell_empty"})
_STORAGE_MEMO_KEY = "acnr_wp_cell_target_storage_kind"
_BIND_MEMO_KEY = "acnr_wp_cell_target_sheet_level"


@dataclass(frozen=True)
class SheetKey:
    """``sheet_key_for`` 的结果：``key`` 与 ``blocked`` 恰有其一。"""

    key: str | None
    blocked: WpCellRead | None = None


@dataclass(frozen=True)
class TargetRead:
    read: WpCellRead
    #: 实际读取的底稿编码（sheet 级或父底稿）；未读取时 None
    bound_wp_code: str | None


async def _locked_version(db, project_id) -> str | None:
    """项目锁定的目录版本，与 ``full_resolve`` 同一锁源：落库的 `projects.acnr_registry_version`。

    两处必须同源 —— 取值接线按一个版本的目录找格子、resolver 按另一个版本判身份，
    就会出现「身份解析得到但取不到值」这类查不出原因的空值（T18）。
    """
    return await get_locked_version(db, project_id)


async def effective_catalog(db, project_id) -> "CatalogIndex":
    """锁定项目 ⇒ 锁定版本的目录快照（缺快照抛 ``VersionNotFoundError``，不回退当前目录）；否则当前目录。"""
    cat = get_catalog()
    if not project_id:
        return cat
    metrics = get_acnr_metrics()
    if db is None:  # T26：与 full_resolve 同口径计 version_lock_unchecked
        metrics.record_version_lock("unchecked")
        return cat
    locked = await _locked_version(db, project_id)
    if not locked:
        return cat
    if locked != cat.registry_version:
        from app.services.acnr.resolver import VersionNotFoundError, load_versioned_catalog

        try:
            cat = load_versioned_catalog(locked)
        except VersionNotFoundError:
            metrics.record_version_lock("snapshot_missing", locked)
            raise
    metrics.record_version_lock("hit", locked)
    return cat


def _blocked(reason: str, code: str, candidates: tuple[str, ...] = ()) -> WpCellRead:
    return WpCellRead("blocked", None, reason, None, None, candidates=candidates, reason_code=code)


def sheet_key_for(entry: dict, *, index: "CatalogIndex") -> SheetKey:
    """目录 sheet 的读取键。

    名称归属按 ``exact_identity.sheet_of(父级, sheet_name)`` 判：命中本 sheet（含名称恰等于本 sheet 编码的情形）
    才用名称；``name_owner`` 不认编码命中，名称等于自身编码的 sheet（如 S17/S17）会被误判为借用，故不用它。
    """
    parent = entry.get("parent_wp_code", "")
    name = entry.get("sheet_name") or ""
    match = exact_identity.sheet_of(parent, name, index=index)
    if match.ok and match.entry is not None and match.entry.get("addr_id") == entry.get("addr_id"):
        return SheetKey(key=normalize_sheet_key(name))
    owner = (match.entry or {}).get("addr_id") if match.ok else None
    detail = f"已被 {owner} 使用" if owner else "在父级内不唯一"
    reason = f"{CELL_VALUE_REASONS['sheet_name_borrowed']}（{entry.get('addr_id')} 的表名「{name}」{detail}）"
    return SheetKey(key=None, blocked=_blocked(reason, "sheet_name_borrowed", tuple(match.candidates)))


async def bind_wp_code(db, project_id, entry: dict) -> str:
    """有 sheet 级底稿读它，否则读父底稿（只在 sheet 级底稿不存在时回落）。"""
    sheet_code = entry.get("sheet_code") or ""
    parent = entry.get("parent_wp_code") or sheet_code
    if not sheet_code or sheet_code == parent:
        return parent
    memo = db.info.setdefault(_BIND_MEMO_KEY, {})
    key = (str(project_id), sheet_code)
    if key not in memo:
        pid = project_id if isinstance(project_id, UUID) else UUID(str(project_id))
        hit = (await db.execute(
            sa.select(WpIndex.id).where(
                WpIndex.project_id == pid, WpIndex.wp_code == sheet_code, WpIndex.is_deleted == sa.false(),
            ).limit(1)
        )).first()
        memo[key] = hit is not None
    return sheet_code if memo[key] else parent


async def _storage_kind(db, wp_id: UUID) -> str | None:
    """PG：表单录入 ⇒ value_in_form_storage；无 html_data 且有文件 ⇒ value_in_file；其余 None。"""
    if db.get_bind().dialect.name != "postgresql":
        return None
    memo = db.info.setdefault(_STORAGE_MEMO_KEY, {})
    if wp_id not in memo:
        row = (await db.execute(sa.text(
            "SELECT EXISTS (SELECT 1 FROM checklist_responses c WHERE c.wp_id = w.id), "
            "(w.parsed_data -> 'html_data') IS NULL, NULLIF(w.file_path, '') IS NOT NULL "
            "FROM working_paper w WHERE w.id = :wp"), {"wp": wp_id})).first()
        kind = None
        if row is not None:
            has_form, no_html, has_file = row
            kind = "value_in_form_storage" if has_form else ("value_in_file" if no_html and has_file else None)
        memo[wp_id] = kind
    return memo[wp_id]


async def _refine(db, read: WpCellRead) -> WpCellRead:
    if read.state != "missing" or read.reason_code not in _REFINABLE or read.wp_id is None:
        return read
    kind = await _storage_kind(db, read.wp_id)
    if kind is None:
        return read
    reason = FORM_STORAGE_REASON if kind == "value_in_form_storage" else FILE_ONLY_REASON
    return dataclasses.replace(read, reason_code=kind, reason=reason)


async def read_entry_cell(db, *, project_id, year, entry: dict, cell: str, index: "CatalogIndex") -> TargetRead:
    """读目录 sheet ``entry`` 的单元格 ``cell``。"""
    key = sheet_key_for(entry, index=index)
    if key.blocked is not None:
        return TargetRead(read=key.blocked, bound_wp_code=None)
    wp_code = await bind_wp_code(db, project_id, entry)
    read = await resolve_wp_cell(db, project_id, year, wp_code, key.key, cell)
    return TargetRead(read=await _refine(db, read), bound_wp_code=wp_code)


async def read_formula_cell(
    db, *, project_id, year, wp_code: str, sheet_text: str, cell: str, index: "CatalogIndex",
) -> TargetRead:
    """按公式写法 ``WP(wp_code, sheet_text, cell)`` 取值。

    目录内命中 ⇒ ``read_entry_cell``；目录无此表 / 父级不在目录 ⇒ 按原文读（自定义底稿等）；
    多义 / 禁止别名 ⇒ 不读，blocked ``sheet_ambiguous`` 带候选。
    """
    match = exact_identity.sheet_of(wp_code, sheet_text, index=index)
    if match.ok and match.entry is not None:
        return await read_entry_cell(db, project_id=project_id, year=year, entry=match.entry, cell=cell, index=index)
    if match.state in ("ambiguous", "alias_forbidden"):
        return TargetRead(read=_blocked(match.reason, "sheet_ambiguous", tuple(match.candidates)), bound_wp_code=None)
    read = await resolve_wp_cell(db, project_id, year, wp_code, normalize_sheet_key(sheet_text), cell)
    return TargetRead(read=await _refine(db, read), bound_wp_code=wp_code)
