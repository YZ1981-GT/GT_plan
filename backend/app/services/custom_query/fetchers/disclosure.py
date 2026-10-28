"""附注取数器（advanced-query-linkage-closure 任务 19，ADR-AQL-16，design §3.2 / §3.8；R5.4、R10.4 后端）。

**存在理由（AQ-10）**：改造前指标树附注叶子按合并附注模板种子编号（「五-1-1」）生成，单体项目的附注编号是「八、1」，
两者交集为 0 ⇒ 点任何附注叶子都是 0 行；「附注（全部）」把全部章节的全部表摊平成一张表，只取第一张表的表头，
其余表的列错位（华氏 1,810 行）。现在：

- 单体项目附注树按本项目本年度实际章节生成（章节集合与顺序 = 附注编辑器同一函数 ``DisclosureEngine.get_notes_tree``，
  含口径过滤），再叠加本人循环范围（R3.8）：:func:`project_note_tree`；
- ``disclosure``（附注目录）= 每「章节 × 表」一行（章节号、标题、表名、行数、需更新）：:func:`_query_disclosure_catalog`；
- ``disclosure_note:{章节}`` 按 ``filters.table_index``（默认 0）返回**一张表**，列 = 三列 + 该表表头，行序 = ``table_data``
  原序，``meta.tables`` 列出全部表供切换：:func:`_query_disclosure_section`；
- 合并项目（``report_scope = consolidated``）沿用种子树与 ``consol_note_data`` 旧取数（:func:`_query_disclosure`）。

``_query_disclosure`` 由 router 再导出（``test_note_table_payload_readers_pg.py`` 从 router 导入它），行为不变。
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException
from sqlalchemy import false, func, select, text

from app.services.custom_query.fetchers import effective_fetch_limit as _effective_limit

logger = logging.getLogger(__name__)


def _flatten_disclosure_note_rows(
    note_section: str,
    section_title: str,
    source_template: str | None,
    table_data: Any,
    *,
    max_rows_per_section: int = 100,
) -> tuple[list[dict], list[str]]:
    """把 ``disclosure_notes.table_data`` 展平为查询行（多表走 ``_tables``）。

    表头缺失（legacy ``headers=[]``）时经 ``note_header_projector`` 读时派生
    （模板优先 → 语义兜底），与附注模块/Word 导出同口径。
    行支持两种形态：``{label, values:[...]}``（当前）与 ``[...]``（旧扁平）。
    """
    from app.services.note_header_projector import derive_headers_for_legacy_table

    if not isinstance(table_data, dict):
        return [], []

    tables = table_data.get("_tables")
    if isinstance(tables, list) and tables:
        pairs = [(i, t) for i, t in enumerate(tables) if isinstance(t, dict)]
    else:
        pairs = [(0, table_data)]

    out: list[dict] = []
    columns: list[str] = []
    for t_idx, tbl in pairs:
        rows = tbl.get("rows")
        if not isinstance(rows, list) or not rows:
            continue
        headers = tbl.get("headers")
        if not (isinstance(headers, list) and headers):
            headers = derive_headers_for_legacy_table(
                tbl,
                section_number=note_section,
                source_template=source_template,
                table_index=t_idx,
            ) or []
        headers = [str(h or "") for h in headers]
        if not columns and headers:
            columns = ["note_section", "section_title", "table_name"] + headers
        table_name = str(tbl.get("name") or "")
        for row in rows[:max_rows_per_section]:
            if isinstance(row, dict):
                cells = [row.get("label", "")] + list(row.get("values") or [])
            elif isinstance(row, list):
                cells = list(row)
            else:
                continue
            obj: dict = {
                "note_section": note_section,
                "section_title": section_title,
                "table_name": table_name,
            }
            for hi, h in enumerate(headers):
                if h:
                    obj[h] = cells[hi] if hi < len(cells) else ""
            out.append(obj)
    return out, columns


async def _query_disclosure(db, pid, year, filters, limit):
    """附注数据查询。

    无 node_key 的兼容查询优先读取单体 ``disclosure_notes``，再读取合并附注 legacy NULL 行。
    节点查询不消费缺少节点身份的单体/legacy 数据，只返回精确 node_key 的合并附注行。
    """
    section_id = str(filters.get("section_id", "") or "").strip()
    node_key = filters.get("node_key")

    # ── 第 1 真源：单体附注 disclosure_notes ─────────────────────────────
    # disclosure_notes 没有 node_key 列。节点级查询不得将项目级单体附注误当成合并节点数据。
    if node_key is None:
        try:
            if section_id:
                note_res = await db.execute(
                    text(
                        "SELECT note_section, section_title, source_template::text, table_data "
                        "FROM disclosure_notes WHERE project_id = :pid AND year = :y "
                        "AND is_deleted = false AND note_section = :sid"
                    ),
                    {"pid": pid, "y": year, "sid": section_id},
                )
            else:
                # 「有表」= 非空 JSON 对象（与附注章节读取 / Word 导出同口径）：生成链把 None 存成 JSON null，
                # IS NOT NULL 对它恒真 ⇒ 纯文字章节占 LIMIT 名额却展平不出任何行（第 26 组）
                note_res = await db.execute(
                    text(
                        "SELECT note_section, section_title, source_template::text, table_data "
                        "FROM disclosure_notes WHERE project_id = :pid AND year = :y "
                        "AND is_deleted = false AND jsonb_typeof(table_data) = 'object' "
                        "AND table_data::text <> '{}' "
                        "ORDER BY sort_order NULLS LAST, note_section LIMIT :lim"
                    ),
                    {"pid": pid, "y": year, "lim": _effective_limit(limit)},
                )
            note_flat: list[dict] = []
            note_cols: list[str] = []
            for r in note_res.fetchall():
                rows_part, cols_part = _flatten_disclosure_note_rows(
                    r[0] or "", r[1] or "", r[2], r[3],
                )
                if cols_part and not note_cols:
                    note_cols = cols_part
                note_flat.extend(rows_part)
            if note_flat:
                return {
                    "rows": note_flat[:limit],
                    "columns": note_cols or ["note_section", "section_title", "table_name"],
                    "total": len(note_flat),
                }
        except Exception as err:  # noqa: BLE001 - 缺表/无数据时继续合并附注兼容读取
            logger.warning("query disclosure_notes failed, fallback to consol: %s", err)

    # ── 第 2 真源（回退）：合并附注 consol_note_data ─────────────────────
    # 使用 ORM UUID 类型匹配，避免 SQLite/PG UUID 参数格式差异；稳定按主键排序。
    from app.models.consol_note_data_models import ConsolNoteData

    try:
        from uuid import UUID
        project_uuid = pid if isinstance(pid, UUID) else UUID(str(pid))
    except (ValueError, TypeError, AttributeError):
        return {"rows": [], "columns": ["section_id"], "total": 0}

    stmt = select(ConsolNoteData.section_id, ConsolNoteData.data).where(
        ConsolNoteData.project_id == project_uuid,
        ConsolNoteData.year == year,
    )
    if section_id:
        stmt = stmt.where(ConsolNoteData.section_id == section_id)
    # 节点请求精确匹配；旧请求只读 legacy NULL，绝不混入其它节点行。
    if node_key is None:
        stmt = stmt.where(ConsolNoteData.node_key.is_(None))
    else:
        stmt = stmt.where(ConsolNoteData.node_key == node_key)
    stmt = stmt.order_by(ConsolNoteData.id).limit(_effective_limit(limit))
    result = await db.execute(stmt)

    # 将附注数据展平为表格行（每个章节的每行数据变成一条记录）
    flat_rows = []
    all_headers: list[str] = []
    for r in result.fetchall():
        data = r[1] if isinstance(r[1], dict) else {}
        headers = data.get("headers", [])
        rows = data.get("rows", [])
        if headers and not all_headers:
            all_headers = ["section_id"] + headers
        for row_data in rows[:100]:  # 每章节最多100行
            obj: dict = {"section_id": r[0]}
            for hi, h in enumerate(headers):
                obj[h] = row_data[hi] if hi < len(row_data) else ''
            flat_rows.append(obj)
    columns = all_headers if all_headers else ["section_id"]
    return {"rows": flat_rows[:limit], "columns": columns, "total": len(flat_rows)}


# ─── 单体项目：按项目章节树、逐表返回（任务 19）────────────────────────────────

#: 章节表结果的固定前三列（之后是该表表头）
NOTE_BASE_COLUMNS: tuple[str, ...] = ("note_section", "section_title", "table_name")
#: 附注目录的列
CATALOG_COLUMNS: tuple[str, ...] = ("note_section", "section_title", "table_name", "row_count", "is_stale")
CATALOG_LEAF_LABEL = "附注目录"


def _uuid(value: Any) -> uuid.UUID | None:
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError, AttributeError):
        return None


async def _report_scope(db, pid) -> str:
    from app.models.core import Project

    puid = _uuid(pid)
    project = await db.get(Project, puid) if puid is not None else None
    return "consolidated" if project is not None and project.report_scope == "consolidated" else "standalone"


def _template_text(value: Any) -> str | None:
    if value is None:
        return None
    return str(getattr(value, "value", value))


def note_tables(note_section: str, source_template: str | None, table_data: Any) -> list[tuple[str, list[str], list]]:
    """``table_data`` → ``[(表名, 表头, 行)]``，顺序即原表顺序（多表走 ``_tables``）。

    表头缺失（legacy ``headers=[]``）时经 ``note_header_projector`` 读时派生，与附注模块 / Word 导出同口径；
    没有名称、表头与行的空对象不算一张表。
    """
    from app.services.note_header_projector import derive_headers_for_legacy_table

    if not isinstance(table_data, dict):
        return []
    tables = table_data.get("_tables")
    if isinstance(tables, list) and tables:
        pairs = [(i, t) for i, t in enumerate(tables) if isinstance(t, dict)]
    else:
        pairs = [(0, table_data)]
    out: list[tuple[str, list[str], list]] = []
    for t_idx, tbl in pairs:
        rows = tbl.get("rows") if isinstance(tbl.get("rows"), list) else []
        headers = tbl.get("headers")
        if not (isinstance(headers, list) and headers):
            headers = derive_headers_for_legacy_table(
                tbl, section_number=note_section, source_template=source_template, table_index=t_idx,
            ) or []
        name = str(tbl.get("name") or "")
        if not (rows or headers or name):
            continue
        out.append((name, [str(h or "") for h in headers], rows))
    return out


def _column_keys(headers: list[str]) -> list[str]:
    """表头 → 列键：空表头记「列 n」，重名的后者加「（2）」…，不让同名列互相覆盖。"""
    keys: list[str] = []
    seen: dict[str, int] = {}
    for i, header in enumerate(headers):
        base = header.strip() or f"列{i + 1}"
        seen[base] = seen.get(base, 0) + 1
        keys.append(base if seen[base] == 1 else f"{base}（{seen[base]}）")
    return keys


def _table_rows(section: str, title: str, table_name: str, keys: list[str], rows: list) -> list[dict]:
    out: list[dict] = []
    for row in rows:
        if isinstance(row, dict):
            cells = [row.get("label", "")] + list(row.get("values") or [])
        elif isinstance(row, list):
            cells = list(row)
        else:
            continue
        obj: dict = {"note_section": section, "section_title": title, "table_name": table_name}
        for i, key in enumerate(keys):
            obj[key] = cells[i] if i < len(cells) else ""
        out.append(obj)
    return out


def _invalid_table_index(value: Any, message: str) -> HTTPException:
    return HTTPException(status_code=400, detail={
        "error_code": "INVALID_FILTER_VALUE", "message": message, "filter_key": "table_index", "value": str(value),
    })


def _table_index(raw: Any) -> int:
    if raw is None or raw == "":
        return 0
    if isinstance(raw, bool):
        raise _invalid_table_index(raw, f"表序号「{raw}」不是整数")
    try:
        return int(str(raw).strip())
    except ValueError:
        raise _invalid_table_index(raw, f"表序号「{raw}」不是整数") from None


async def _query_disclosure_section(db, pid, year, filters, limit, *, sections: frozenset[str] | None = None):
    """``disclosure_note:{章节}``：一张表（``filters.table_index``，默认 0），列随该表表头、行序同原表，``meta.tables`` 列全部表。

    ``sections``：本人循环范围内的章节（None = 不限）；章节不在其中 ⇒ 403 ``SECTION_OUT_OF_SCOPE``（R3.8）。
    合并项目、节点级请求沿用 :func:`_query_disclosure`。
    """
    from app.models.report_models import DisclosureNote
    from app.services.custom_query.cycle_scope import section_out_of_scope

    section = str(filters.get("section_id", "") or "").strip()
    if sections is not None and section not in sections:
        raise section_out_of_scope(section)
    if not section or filters.get("node_key") is not None or await _report_scope(db, pid) == "consolidated":
        return await _query_disclosure(db, pid, year, filters, limit)
    index = _table_index(filters.get("table_index"))
    note = (await db.execute(
        select(DisclosureNote.section_title, DisclosureNote.source_template, DisclosureNote.table_data).where(
            DisclosureNote.project_id == _uuid(pid), DisclosureNote.year == int(year),
            DisclosureNote.note_section == section, DisclosureNote.is_deleted == false(),
        )
    )).first()
    empty = {"rows": [], "columns": list(NOTE_BASE_COLUMNS), "total": 0, "meta": {"tables": [], "table_index": 0}}
    if note is None:
        return empty
    # 按位置取列（Row 与测试替身的元组都能用，与 _query_disclosure 同写法）
    title = str(note[0] or "")
    tables = note_tables(section, _template_text(note[1]), note[2])
    if not tables:
        return empty
    if not 0 <= index < len(tables):
        raise _invalid_table_index(index, f"附注「{section}」只有 {len(tables)} 张表（表序号 0~{len(tables) - 1}）")
    name, headers, rows = tables[index]
    keys = _column_keys(headers)
    data = _table_rows(section, title, name, keys, rows)
    meta = {"tables": [{"index": i, "name": n, "row_count": len(r)} for i, (n, _h, r) in enumerate(tables)],
            "table_index": index}
    return {"rows": data, "columns": [*NOTE_BASE_COLUMNS, *keys], "total": len(data), "meta": meta}


async def _query_disclosure_catalog(db, pid, year, filters, limit, *, sections: frozenset[str] | None = None):
    """``disclosure``（附注目录）：章节 × 表一行，章节顺序 = 附注编辑器目录（``get_notes_tree``），再按循环范围严格过滤。

    合并项目沿用 :func:`_query_disclosure`（合并附注 ``consol_note_data``），同样按循环章节过滤。
    """
    from app.models.report_models import DisclosureNote
    from app.services.disclosure_engine import DisclosureEngine

    if await _report_scope(db, pid) == "consolidated":
        result = await _query_disclosure(db, pid, year, filters, limit)
        if sections is not None:
            rows = [r for r in result.get("rows") or [] if str(r.get("section_id") or r.get("note_section")) in sections]
            result = {**result, "rows": rows, "total": len(rows)}
        return result
    puid = _uuid(pid)
    tree = await DisclosureEngine(db).get_notes_tree(puid, int(year))
    order = [n["note_section"] for n in tree if sections is None or n["note_section"] in sections]
    # 按位置取列（Row 与测试替身的元组都能用）：章节号、标题、来源模板、表数据、需更新
    notes = {r[0]: r for r in (await db.execute(
        select(DisclosureNote.note_section, DisclosureNote.section_title, DisclosureNote.source_template,
               DisclosureNote.table_data, DisclosureNote.is_stale).where(
            DisclosureNote.project_id == puid, DisclosureNote.year == int(year), DisclosureNote.is_deleted == false(),
        )
    )).all() if r}
    rows: list[dict] = []
    for section in order:
        note = notes.get(section)
        if note is None or len(note) < 5:
            continue
        for name, _headers, table_rows in note_tables(section, _template_text(note[2]), note[3]):
            rows.append({"note_section": section, "section_title": str(note[1] or ""), "table_name": name,
                         "row_count": len(table_rows), "is_stale": bool(note[4])})
    return {"rows": rows, "columns": list(CATALOG_COLUMNS), "total": len(rows)}


# ─── 指标树附注分支（router ``_build_disclosure_tree`` 的项目分支）──────────────


@dataclass(frozen=True)
class NotesContext:
    """一次指标树请求的附注上下文：年度（None = 取不到）、报表范围、本人循环章节（None = 不限）、版本摘要。"""

    year: int | None
    report_scope: str
    sections: frozenset[str] | None
    version: str


async def resolve_notes_context(db, project_id: Any, year: int | None, user: Any) -> NotesContext:
    """``X-Notes-Version`` = ``sha1(行数|max(updated_at)|循环章节集合或 *)[:12]``；无项目 ``none``、取不到年度 ``no-year``。

    年度缺省经平台入口 ``resolve_project_audit_year_for_request`` 取项目审计年度（不用日历年）。
    """
    from app.models.report_models import DisclosureNote
    from app.services.custom_query.cycle_scope import CycleScopeCache, sections_label
    from app.services.project_audit_year import resolve_project_audit_year_for_request

    puid = _uuid(project_id) if project_id else None
    if puid is None:
        return NotesContext(None, "standalone", None, "none")
    report_scope = await _report_scope(db, puid)
    resolved = await resolve_project_audit_year_for_request(db, puid, year)
    if resolved is None:
        return NotesContext(None, report_scope, None, "no-year")
    scope = await CycleScopeCache(user, db).scope(puid)
    table = DisclosureNote.__table__
    count, latest = (await db.execute(
        select(func.count(), func.max(table.c.updated_at)).where(
            table.c.project_id == puid, table.c.year == resolved, table.c.is_deleted == false(),
        )
    )).one()
    digest = hashlib.sha1(f"{count}|{latest}|{sections_label(scope)}".encode("utf-8")).hexdigest()[:12]
    return NotesContext(resolved, report_scope, scope.sections, digest)


async def project_note_tree(db, project_id: Any, year: int, *, sections: frozenset[str] | None = None) -> list[dict]:
    """单体项目附注分支：「附注目录」叶子 + 按章节号首个「、」之前分组的章节叶子（组名取同号章节的标题，没有则用章节号）。

    章节集合与顺序 = ``DisclosureEngine.get_notes_tree``（附注编辑器目录同一函数），再按本人循环章节严格过滤（空集即空）。
    """
    from app.services.disclosure_engine import DisclosureEngine

    tree = await DisclosureEngine(db).get_notes_tree(_uuid(project_id), int(year))
    nodes = [n for n in tree if sections is None or n["note_section"] in sections]
    titles = {n["note_section"]: (n.get("section_title") or "") for n in nodes}
    groups: dict[str, dict] = {}
    for node in nodes:
        section = node["note_section"]
        head = section.split("、", 1)[0]
        group = groups.get(head)
        if group is None:
            group = groups[head] = {"key": f"note_group_{head}", "label": titles.get(head) or head, "children": []}
        group["children"].append({
            "key": f"disclosure_note:{section}", "label": f"{section} {titles[section]}".strip(),
            "section_id": section, "columns": [], "supports_conditions": False,
        })
    catalog = {"key": "disclosure", "label": CATALOG_LEAF_LABEL, "columns": [], "supports_conditions": False}
    return [catalog, *groups.values()]
