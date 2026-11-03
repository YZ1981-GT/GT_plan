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

__all__ = [
    "OfflineImportProtectedCellError",
    "OfflineImportStructureError",
    "count_changed_tables",
    "extract_sheet_tables",
    "merge_imported_tables_into_section",
    "merge_selected_cells_into_section",
    "persist_applied_table_data",
]


class OfflineImportStructureError(ValueError):
    """离线包改了表 / 行结构，缺少稳定身份时拒绝猜位置写回。"""


class OfflineImportProtectedCellError(ValueError):
    """离线包试图改写由系统取数、公式或锁定状态保护的单元格。"""


def _is_blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _norm_header(v: Any) -> str:
    return str(v).replace("<br/>", "").replace("<br>", "").strip() if v is not None else ""


def _header_matches(
    grid_row: list[Any],
    expected_headers: list[str],
    expected_value_columns: int | None = None,
) -> bool:
    """判断导出表头是否与期望结构相同。

    模板 ``headers`` 有两种合法形态：包含标签列表头，或只含数据列表头。后者在导出时会自动补
    ``项目``；导入必须按导出规则补回再比较，否则任意单表 round-trip 都找不到表头、把值读成空。
    """
    got = [_norm_header(v) for v in grid_row if not _is_blank(v)]
    want = [_norm_header(h) for h in expected_headers if not _is_blank(h)]
    if expected_value_columns is not None and len(want) == expected_value_columns:
        want = ["项目", *want]
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
        exp_rows = exp.get("rows") or []
        exp_nrows = len(exp_rows)
        exp_nvalues = max(
            (len(row.get("values") or []) for row in exp_rows if isinstance(row, dict)),
            default=max(0, len(exp_headers) - 1),
        )
        # 从 pos 起找匹配表头行
        hdr_idx = next(
            (k for k in range(pos, len(grid)) if _header_matches(grid[k], exp_headers, exp_nvalues)),
            None,
        )
        if hdr_idx is None:
            # 每张既有表都必须仍有原表头；否则用户改表头/删表，按位置写会错位。
            raise OfflineImportStructureError(
                f"找不到既有表「{exp.get('name') or ''}」的表头；离线导入只允许改值，"
                "改表头、增删表或重排行请回平台操作"
            )
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
        if read != exp_nrows:
            raise OfflineImportStructureError(
                f"表「{exp.get('name') or ''}」行数从 {exp_nrows} 改成 {read}；离线导入只允许改值，"
                "增删或重排行请回平台操作"
            )
        # 导出器在每张表后留一空行。期望行读完后仍紧跟非空内容，说明用户新增了行；
        # 没有稳定 row id 时继续按位置写会把下一张表或合计行错位覆盖，必须 fail-closed。
        if r < len(grid) and any(not _is_blank(value) for value in grid[r]):
            raise OfflineImportStructureError(
                f"表「{exp.get('name') or ''}」在既有 {exp_nrows} 行后还有数据；"
                "离线导入只允许改值，增删或重排行请回平台操作"
            )
        tables.append({"name": str(exp.get("name") or ""), "headers": headers, "rows": data_rows})
        pos = r  # 下一张表从本表数据之后找
    return tables


def _import_values_for_row(cells: list[Any]) -> list[Any]:
    """导入行 ``cells``（含标签列）→ 数据列 values（去掉 ``cells[0]`` 标签列）。"""
    return list(cells[1:]) if cells else []


def _import_label(cells: list[Any]) -> str:
    """导出器会给动态行标签加 ``★ ``；比较业务行身份时去掉该显示前缀。"""
    value = str(cells[0] if cells else "").strip()
    return value[1:].lstrip() if value.startswith("★") else value


def _validate_row_alignment(existing_rows: list[Any], imported_rows: list[Any], table_name: str) -> None:
    """离线包没有稳定 row id；行数或标签顺序变化时拒绝位置写回。"""
    expected = [str(row.get("label") or "").strip() if isinstance(row, dict) else "" for row in existing_rows]
    actual = [_import_label(row.get("cells") or []) if isinstance(row, dict) else "" for row in imported_rows]
    if expected != actual:
        raise OfflineImportStructureError(
            f"表「{table_name}」行结构已变化：系统={expected!r}，离线包={actual!r}；"
            "离线导入只允许改值，增删或重排行请回平台操作"
        )


def _table_list(table_data: dict[str, Any]) -> list[dict[str, Any]]:
    tables = table_data.get("_tables")
    if isinstance(tables, list) and tables:
        return tables
    return [{"name": table_data.get("name") or "", "headers": table_data.get("headers") or [],
             "rows": table_data.get("rows") or []}]


def count_changed_tables(before: dict[str, Any], after: dict[str, Any]) -> int:
    """按表序统计值 / 结构实际变化的表数；用于回执，不拿计划表数冒充写入数。"""
    old, new = _table_list(before if isinstance(before, dict) else {}), _table_list(after if isinstance(after, dict) else {})
    count = sum(a != b for a, b in zip(old, new, strict=False))
    return count + abs(len(old) - len(new))


async def persist_applied_table_data(
    db: Any,
    project_id: Any,
    year: int,
    applied_sections: dict[str, dict[str, Any]],
    *,
    user_id: Any | None = None,
) -> dict[str, int]:
    """锁定并写回已存在的章节，返回 ``{章节号: 实际变化表数}``。

    IMPORT_ONLY 不在这里偷偷降级成 UPDATE 0 行；找不到或同一键命中多行都 fail-closed。
    """
    if db is None or not applied_sections:
        return {}
    from datetime import datetime, timezone

    from sqlalchemy import and_, or_, select as sa_select, update as sa_update

    from app.models.report_models import DisclosureNote

    changed: dict[str, int] = {}
    for sid, table_data in applied_sections.items():
        if not isinstance(table_data, dict):
            continue
        rows = (await db.execute(
            sa_select(DisclosureNote.id, DisclosureNote.note_section, DisclosureNote.table_data)
            .where(
                DisclosureNote.project_id == project_id,
                DisclosureNote.year == year,
                DisclosureNote.is_deleted == False,  # noqa: E712
                or_(
                    DisclosureNote.section_id == sid,
                    and_(
                        or_(DisclosureNote.section_id.is_(None), DisclosureNote.section_id == ""),
                        DisclosureNote.note_section == sid,
                    ),
                ),
            )
            .with_for_update()
        )).all()
        if len(rows) != 1:
            raise OfflineImportStructureError(
                f"章节 {sid!r} 在当前项目命中 {len(rows)} 行，拒绝猜测写入目标"
            )
        row = rows[0]
        before = row.table_data or {}
        if before == table_data:
            continue
        table_count = count_changed_tables(before, table_data)
        if table_count <= 0:
            raise OfflineImportStructureError(f"章节 {sid!r} 的 table_data 已变化但无法定位变化表")
        values: dict[str, Any] = {
            "table_data": table_data,
            "updated_at": datetime.now(timezone.utc),
        }
        if user_id is not None:
            values["updated_by"] = user_id
        await db.execute(sa_update(DisclosureNote).where(DisclosureNote.id == row.id).values(**values))
        changed[row.note_section or sid] = table_count
    await db.flush()
    return changed


_PROTECTED_MODES = frozenset({"auto", "formula", "locked"})
_AUTO_SOURCES = frozenset({"formula", "wp_data", "trial_balance", "aux_balance", "aux_ledger_aging"})


def _values_equal(left: Any, right: Any) -> bool:
    if left is None or right is None:
        return left is right
    try:
        return abs(float(left) - float(right)) < 1e-6
    except (TypeError, ValueError):
        return str(left).strip() == str(right).strip()


def _coordinate_keys(table_idx: int, row_idx: int, col_idx: int) -> tuple[str, ...]:
    full = f"{table_idx}:{row_idx}:{col_idx}"
    return (full, f"{row_idx}:{col_idx}") if table_idx == 0 else (full,)


def _mapped_value(container: dict[str, Any], field: str, keys: tuple[str, ...]) -> Any:
    mapping = container.get(field)
    if not isinstance(mapping, dict):
        return None
    for key in keys:
        if key in mapping:
            return mapping[key]
    return None


def _protection_reason(
    root: dict[str, Any], table: dict[str, Any], row: dict[str, Any],
    table_idx: int, row_idx: int, col_idx: int,
) -> str | None:
    """以当前数据库元数据判保护；离线包不能解除绑定或锁定。"""
    keys = _coordinate_keys(table_idx, row_idx, col_idx)
    row_meta = row.get("_cell_meta") if isinstance(row.get("_cell_meta"), dict) else {}
    meta = row_meta.get(str(col_idx)) if isinstance(row_meta.get(str(col_idx)), dict) else {}
    if meta.get("binding_id"):
        return "binding"
    mode_map = row.get("_cell_modes") if isinstance(row.get("_cell_modes"), dict) else {}
    mode = str(mode_map.get(str(col_idx)) or meta.get("mode") or "").strip().lower()
    if mode in _PROTECTED_MODES:
        return mode
    if mode and mode not in {"manual", "editable"}:
        return f"unknown_mode:{mode}"
    source = str(meta.get("source") or "").strip().lower()
    if source in _AUTO_SOURCES:
        return "formula" if source == "formula" else "auto_source"
    for holder in (table, root):
        if _mapped_value(holder, "_bindings", keys):
            return "binding"
        if _mapped_value(holder, "_formulas", keys):
            return "formula"
        legacy_meta = _mapped_value(holder, "_cell_meta", keys)
        if isinstance(legacy_meta, dict):
            if legacy_meta.get("binding_id"):
                return "binding"
            legacy_mode = str(legacy_meta.get("mode") or "").strip().lower()
            legacy_source = str(legacy_meta.get("source") or "").strip().lower()
            if legacy_mode in _PROTECTED_MODES:
                return legacy_mode
            if legacy_source in _AUTO_SOURCES:
                return "formula" if legacy_source == "formula" else "auto_source"
        legacy_mode = str(_mapped_value(holder, "_cell_modes", keys) or "").strip().lower()
        if legacy_mode in _PROTECTED_MODES:
            return legacy_mode
    return None


def _assert_protected_changes_allowed(
    existing: dict[str, Any], candidate: dict[str, Any],
    coordinates: list[tuple[int, int, int]] | None = None,
) -> None:
    old_tables, new_tables = _table_list(existing), _table_list(candidate)
    points = coordinates
    if points is None:
        points = []
        for ti, table in enumerate(old_tables):
            for ri, row in enumerate(table.get("rows") or []):
                if isinstance(row, dict):
                    points.extend((ti, ri, ci) for ci in range(len(row.get("values") or [])))
    violations: list[str] = []
    for ti, ri, ci in points:
        try:
            old_table, new_table = old_tables[ti], new_tables[ti]
            old_row, new_row = old_table["rows"][ri], new_table["rows"][ri]
            old_value, new_value = old_row["values"][ci], new_row["values"][ci]
        except (IndexError, KeyError, TypeError):
            continue
        if _values_equal(old_value, new_value):
            continue
        reason = _protection_reason(existing, old_table, old_row, ti, ri, ci)
        if reason:
            label = str(old_row.get("label") or ri)
            violations.append(f"{ti}:{ri}:{ci}（{label}，{reason}）")
    if violations:
        raise OfflineImportProtectedCellError(
            "离线导入不得改写系统取数、公式或锁定单元格：" + "、".join(violations[:10])
        )


def merge_imported_tables_into_section(
    existing_table_data: dict[str, Any],
    imported_tables: list[dict[str, Any]],
    *,
    _check_protected: bool = True,
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
    has_existing_structure = bool(out.get("rows") or out.get("_tables"))
    if single_mode:
        # 把已有顶层单表视作「第 0 张」；真正的空结构用于纯函数建表，不伪造一张空表。
        existing_tables = ([{"name": out.get("name") or "", "headers": out.get("headers") or [],
                             "rows": out.get("rows") or []}] if has_existing_structure else [])

    merged: list[dict[str, Any]] = []
    if has_existing_structure and len(imported_tables) != len(existing_tables):
        raise OfflineImportStructureError(
            f"表数量从 {len(existing_tables)} 改成 {len(imported_tables)}；离线导入只允许改值，增删表请回平台操作"
        )
    for k, imp in enumerate(imported_tables):
        imp_rows = imp.get("rows") or []
        if k < len(existing_tables):
            tbl = deepcopy(existing_tables[k])
            tbl_rows = tbl.get("rows") or []
            if imp_rows:
                _validate_row_alignment(tbl_rows, imp_rows, str(tbl.get("name") or imp.get("name") or k))
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
        if _check_protected:
            _assert_protected_changes_allowed(existing_table_data, out)
        return out
    # 多表：写 _tables + 首表镜像
    out["_tables"] = merged
    out["headers"] = merged[0].get("headers") or [] if merged else []
    out["rows"] = merged[0].get("rows") or [] if merged else []
    if _check_protected:
        _assert_protected_changes_allowed(existing_table_data, out)
    return out


def merge_selected_cells_into_section(
    existing_table_data: dict[str, Any],
    imported_tables: list[dict[str, Any]],
    cell_keys: list[str],
) -> dict[str, Any]:
    """只采纳选中的导入值，保留其余值与全部非值元数据。

    ``row:value_col`` 兼容旧单表协议，等价于 ``0:row:value_col``；多表使用
    ``table:row:value_col``。表 / 行结构先由完整合并路径校验，任何错位都拒绝。
    """
    candidate = merge_imported_tables_into_section(
        existing_table_data, imported_tables, _check_protected=False,
    )
    out = deepcopy(existing_table_data) if isinstance(existing_table_data, dict) else {}
    old_tables = _table_list(out)
    new_tables = _table_list(candidate)

    for key in cell_keys:
        parts = key.split(":")
        try:
            if len(parts) == 2:
                table_idx, row_idx, col_idx = 0, int(parts[0]), int(parts[1])
            elif len(parts) == 3:
                table_idx, row_idx, col_idx = map(int, parts)
            else:
                raise ValueError
        except ValueError as exc:
            raise OfflineImportStructureError(
                f"合并单元格坐标 {key!r} 无效，应为 行:值列 或 表:行:值列"
            ) from exc
        if min(table_idx, row_idx, col_idx) < 0:
            raise OfflineImportStructureError(f"合并单元格坐标 {key!r} 不得为负数")
        try:
            source = new_tables[table_idx]["rows"][row_idx]["values"][col_idx]
            target_row = old_tables[table_idx]["rows"][row_idx]
        except (IndexError, KeyError, TypeError) as exc:
            raise OfflineImportStructureError(f"合并单元格坐标 {key!r} 超出当前附注表范围") from exc
        _assert_protected_changes_allowed(
            existing_table_data, candidate, [(table_idx, row_idx, col_idx)],
        )
        values = target_row.get("values")
        if not isinstance(values, list) or col_idx >= len(values):
            raise OfflineImportStructureError(f"合并单元格坐标 {key!r} 超出当前附注值列范围")
        values[col_idx] = source

    if isinstance(out.get("_tables"), list) and out["_tables"]:
        out["_tables"] = old_tables
        out["headers"] = deepcopy(old_tables[0].get("headers") or [])
        out["rows"] = deepcopy(old_tables[0].get("rows") or [])
    elif old_tables:
        out["headers"] = deepcopy(old_tables[0].get("headers") or [])
        out["rows"] = deepcopy(old_tables[0].get("rows") or [])
    return out
