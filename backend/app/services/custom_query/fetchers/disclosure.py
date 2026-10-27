"""附注取数器（从 ``routers/custom_query`` 原样迁入；按项目章节树逐表返回在任务 19 改造）。

``_query_disclosure`` 由 router 再导出（``test_note_table_payload_readers_pg.py`` 从 router 导入它）。
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select, text

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
