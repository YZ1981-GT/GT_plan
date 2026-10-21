"""离线导入：每个 sheet 的**多张表**解析 + 并回生成链结构（spec disclosure-note-template-word-realignment Phase 8 Task 9）。

从 ``note_offline_import_service`` 拆出（行数门禁 + 职责内聚）。离线导出 ``note_offline_export_service`` 把一个章节的
``_tables`` 逐张纵向堆在同一 sheet 里（每张 = 可选表名行 + 可选指引行 + 表头行 + 数据行，表间空一行）；旧导入只读
**第一张表**且写回扁平单表，多表章节的其余表与结构全丢。这里按表头行切分出全部表块，并把导入值并回**既有章节的生成链
结构**（``_tables`` + 首表镜像），只改 ``values``，保留 ``row_type`` / ``is_total`` / ``_cell_meta`` / 绑定等非值字段。

表块判据（data_only 读，样式已丢，只能靠内容 + 导出的固定布局）：
- 导出每张表之间**固定空一行**（``note_offline_export_service`` 的 ``cur_row += 1  # 表间空一行``）⇒ **空行是表块分隔符**。
- 一个非空块内：第一行若「第 2 列也非空」就是**表头行**（label 头 + value 列头）；表头之前的「只有第 1 列有值」的行是
  表名 / 跨列指引（取最靠近表头的那个作 ``name``）；表头之后全是数据行。
- 数据行与表头行在 data_only 读下都可能两列非空，**不靠逐行类型区分**，只靠「块内第一行是表头、空行分块」。
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

__all__ = ["extract_sheet_tables", "merge_imported_tables_into_section", "persist_applied_table_data"]


def _is_blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _norm_header(v: Any) -> str:
    return str(v).replace("<br/>", "").replace("<br>", "").strip() if v is not None else ""


def _header_matches(grid_row: list[Any], expected_headers: list[str]) -> bool:
    """grid 行是否是某张期望表的表头行：按**非空单元格文案序列**与期望 headers 相等（去 <br> / 空白）。"""
    got = [_norm_header(v) for v in grid_row if not _is_blank(v)]
    want = [_norm_header(h) for h in expected_headers if not _is_blank(h)]
    return bool(want) and got == want


def extract_sheet_tables(
    grid: list[list[Any]],
    expected: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """从一个 sheet 的二维单元格值（行优先，不含标题/section_id 两行）解析出全部表块。

    Returns: ``[{"name": str, "headers": [...], "rows": [{"cells": [...], "row_idx": int}]}]``，
    其中 ``cells[0]`` 是标签列、``cells[1:]`` 是数据列。``headers`` 第 1 个是标签列表头、其余是数据列表头。

    🔴 **结构驱动优先**（``expected`` = 既有章节的 ``_tables``）：按每张期望表的 **headers 文案**在 grid 里顺序
    定位表头行，再读其后 N 行（N = 该期望表的行数）作数据——**表内空明细行不会被误当表间分隔**（上一版按空行切分
    会把表内空行当分隔，2 表被切成 4 块，已被真实验收抓到）。
    无 ``expected``（IMPORT_ONLY 新建章节，罕见）时退回「空行分块 + 块内首行为表头」的启发式。
    """
    if expected:
        return _extract_by_structure(grid, expected)

    # ── Fallback：无既有结构，按空行分块（IMPORT_ONLY）──
    blocks: list[list[list[Any]]] = []
    cur: list[list[Any]] = []
    for row in grid:
        c1 = row[0] if len(row) > 0 else None
        c2 = row[1] if len(row) > 1 else None
        if _is_blank(c1) and _is_blank(c2):
            if cur:
                blocks.append(cur)
                cur = []
            continue
        cur.append(row)
    if cur:
        blocks.append(cur)
    tables: list[dict[str, Any]] = []
    for block in blocks:
        header_pos = next((k for k, r in enumerate(block) if len(r) > 1 and not _is_blank(r[1])), None)
        if header_pos is None:
            continue
        name = ""
        for r in block[:header_pos]:
            if not _is_blank(r[0] if len(r) > 0 else None):
                name = str(r[0])
        headers = [str(v) for v in block[header_pos] if not _is_blank(v)]
        data_rows = [
            {"cells": [drow[c] if c < len(drow) else None for c in range(len(headers))], "row_idx": idx}
            for idx, drow in enumerate(block[header_pos + 1:])
        ]
        tables.append({"name": name, "headers": headers, "rows": data_rows})
    return tables


def _extract_by_structure(grid: list[list[Any]], expected: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """按既有每张表的 headers 在 grid 里定位表头行、读其后 N 行作数据（N=期望行数）。"""
    tables: list[dict[str, Any]] = []
    pos = 0  # grid 游标，保证表按序定位（同一 headers 多表时不回头）
    for exp in expected:
        exp_headers = exp.get("headers") or []
        exp_nrows = len(exp.get("rows") or [])
        # 从 pos 起找匹配表头行
        hdr_idx = next((k for k in range(pos, len(grid)) if _header_matches(grid[k], exp_headers)), None)
        if hdr_idx is None:
            # sheet 里找不到这张表（被用户删了？）⇒ 该表无导入值，产出空壳（merge 时不改既有）
            tables.append({"name": str(exp.get("name") or ""), "headers": [str(h) for h in exp_headers], "rows": []})
            continue
        headers = [str(v) for v in grid[hdr_idx] if not _is_blank(v)]
        data_rows: list[dict[str, Any]] = []
        # 读期望行数那么多行（期望表每行对应一行；空明细行照样占一行、不跳过）
        r = hdr_idx + 1
        read = 0
        while read < exp_nrows and r < len(grid):
            drow = grid[r]
            cells = [drow[c] if c < len(drow) else None for c in range(len(headers))]
            data_rows.append({"cells": cells, "row_idx": read})
            read += 1
            r += 1
        tables.append({"name": str(exp.get("name") or ""), "headers": headers, "rows": data_rows})
        pos = r  # 下一张表从本表数据之后找
    return tables


def _import_values_for_row(cells: list[Any]) -> list[Any]:
    """导入行 ``cells``（含标签列）→ 数据列 values（去掉 ``cells[0]`` 标签列）。"""
    return list(cells[1:]) if cells else []


async def persist_applied_table_data(
    db: Any,
    project_id: Any,
    year: int,
    applied_sections: dict[str, dict[str, Any]],
    *,
    user_id: Any | None = None,
) -> None:
    """把离线导入应用后的 ``table_data`` 落到 ``disclosure_notes``（OVERWRITE/MERGE 的章节）。

    真改了的章节以导入人盖「最近一次编辑」；值没变（table_data 相等）的不盖、不写。
    键按 note_section 或 section_id 任一匹配（存量行 section_id 可能为空）。
    """
    if db is None or not applied_sections:
        return
    from datetime import datetime, timezone

    from sqlalchemy import or_, update as sa_update

    from app.models.report_models import DisclosureNote

    for sid, table_data in applied_sections.items():
        if not isinstance(table_data, dict):
            continue
        values: dict[str, Any] = {"table_data": table_data, "updated_at": datetime.now(timezone.utc)}
        if user_id is not None:
            values["updated_by"] = user_id
        stmt = (
            sa_update(DisclosureNote)
            .where(
                DisclosureNote.project_id == project_id,
                DisclosureNote.year == year,
                DisclosureNote.is_deleted == False,  # noqa: E712
                or_(DisclosureNote.note_section == sid, DisclosureNote.section_id == sid),
                DisclosureNote.table_data.is_distinct_from(table_data),
            )
            .values(**values)
        )
        await db.execute(stmt)
    await db.flush()


def merge_imported_tables_into_section(
    existing_table_data: dict[str, Any],
    imported_tables: list[dict[str, Any]],
) -> dict[str, Any]:
    """把导入的多张表并回既有章节结构，返回**新的** ``table_data``（深拷贝，不改入参）。

    - 既有章节是多表（``_tables``）：按**表序**对齐，第 k 张导入表的值并进第 k 张既有表的 ``values``，
      只改数据列、保留 label / row_type / is_total / ``_cell_meta`` / ``_cell_modes`` / 绑定等。
    - 既有章节是单表（顶层 ``rows``）：第一张导入表并进顶层。
    - 既有无结构（IMPORT_ONLY 新建）：按导入表直接建结构（``_tables`` + 首表镜像）。
    - 导入表比既有多出的表：追加（结构取导入形态，label=cells[0]、values=cells[1:]）。
    并回后同步**首表镜像**（顶层 ``headers`` / ``rows`` = ``_tables[0]``），与生成链一致。
    """
    out = deepcopy(existing_table_data) if isinstance(existing_table_data, dict) else {}
    existing_tables = out.get("_tables")
    single_mode = not (isinstance(existing_tables, list) and existing_tables)
    if single_mode:
        # 把顶层单表视作「第 0 张」，并回后再决定是否升级为多表
        existing_tables = [{"name": out.get("name") or "", "headers": out.get("headers") or [],
                            "rows": out.get("rows") or []}]

    merged: list[dict[str, Any]] = []
    for k, imp in enumerate(imported_tables):
        imp_rows = imp.get("rows") or []
        if k < len(existing_tables):
            tbl = deepcopy(existing_tables[k])
            tbl_rows = tbl.get("rows") or []
            for r_idx, imp_row in enumerate(imp_rows):
                imp_values = _import_values_for_row(imp_row.get("cells") or [])
                if r_idx < len(tbl_rows) and isinstance(tbl_rows[r_idx], dict):
                    target = tbl_rows[r_idx]
                    vals = target.get("values")
                    if not isinstance(vals, list):
                        vals = []
                    for c_idx, v in enumerate(imp_values):
                        while len(vals) <= c_idx:
                            vals.append(None)
                        vals[c_idx] = v
                    target["values"] = vals
                    target.pop("cells", None)
                else:
                    tbl_rows.append({
                        "label": (imp_row.get("cells") or [None])[0],
                        "values": imp_values,
                    })
            tbl["rows"] = tbl_rows
            if imp.get("headers") and not tbl.get("headers"):
                tbl["headers"] = imp["headers"]
            merged.append(tbl)
        else:
            # 导入多出来的表：按导入形态新建
            merged.append({
                "name": imp.get("name") or "",
                "headers": imp.get("headers") or [],
                "rows": [
                    {"label": (r.get("cells") or [None])[0], "values": _import_values_for_row(r.get("cells") or [])}
                    for r in imp_rows
                ],
            })
    # 既有表比导入多（导入未覆盖的表）：原样保留
    for k in range(len(imported_tables), len(existing_tables)):
        merged.append(deepcopy(existing_tables[k]))

    if single_mode and len(merged) <= 1:
        # 原本单表、导入也只一张 ⇒ 保持单表形态（顶层 rows），不平白升级成 _tables
        first = merged[0] if merged else {"headers": [], "rows": []}
        out["headers"] = first.get("headers") or []
        out["rows"] = first.get("rows") or []
        out.pop("_tables", None)
        return out
    # 多表：写 _tables + 首表镜像
    out["_tables"] = merged
    out["headers"] = merged[0].get("headers") or [] if merged else []
    out["rows"] = merged[0].get("rows") or [] if merged else []
    return out
