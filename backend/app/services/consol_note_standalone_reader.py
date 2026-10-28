"""单体附注表格读取层 —— 合并附注明细映射（V186 链路）唯一的来源读取。

合并附注的个别数从各子企业的单体附注拉取（不从试算表取数）。读的必须是单体附注页面 /
Word 导出实际显示的那张表：

1. ``effective_table_data``：workpaper 来源先把 ``sub_table_data`` 投影成 ``_tables``
   （与编辑器、Word 导出、就绪判定同一口径），其余来源直接读 ``_tables``；
2. 选表与认列全部交给标题行库（``note_table_header_library`` / ``note_table_header_match``）：
   名字（映射子表名、合并表标题）缩小候选，多张候选按列语义键重合度定；续表只认标记，列续表
   （补期间 / 补列）按行名对行，行续表（补行）追加在主表后；比例列不加总、说明类列不取数；
   对不上的列不填，列名回报给用户。

产出 V186 标准来源行 ``{label, row_type, values, _occurrence}``：``values[k]`` 对应合并模板第 ``k+1``
列（第 0 列是行名）；``_occurrence`` 是同名行的出现序号（从 0 起，映射可按（行名, 序号）取行）；集团下推的行另带
``_pushed_row_id``（明细映射按它精确对应，``exact_id``）。合计 / 小计行由 apply 按本表数据重算，不信任来源合计。

spec: consol-note-pull-from-standalone → consol-note-header-library-and-node-reaggregate（读取层收口）
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.services.note_table_header_library import (
    ColumnKey,
    column_keys,
    continuation_links,
    load_vocabulary,
    norm,
    table_identity,
)
from app.services.note_table_header_match import (
    choose_unit,
    match_columns,
    row_values,
    to_number,
    unit_member_keys,
)

__all__ = ["SourceTable", "pick_standalone_table", "read_source_table"]


@dataclass
class SourceTable:
    """一家企业一个合并章节的来源读取结果。"""

    rows: list[dict[str, Any]] = field(default_factory=list)
    table_name: str | None = None
    matched_columns: list[int] = field(default_factory=list)
    unmatched_columns: list[str] = field(default_factory=list)
    ratio_columns: list[str] = field(default_factory=list)
    reason: str | None = None  # 没读到来源行时的中文原因
    # missing（未生成）/ not_applicable（本期无此情形）/ no_source（合并特有章节）/
    # unreadable（有附注但读不出表）；空 = 按 rows 推断
    status: str = ""
    # 怎么认到的这张表：name 按表名 / structure 按表头结构 / single_table 章节只有一张表
    table_choice: str = ""

    def to_status(self) -> dict[str, Any]:
        return {
            "status": self.status or ("found" if self.rows else "unreadable"),
            "reason": self.reason,
            "table_name": self.table_name,
            "table_choice": self.table_choice or None,
            "row_count": len(self.rows),
            "unmatched_columns": self.unmatched_columns,
            "ratio_columns": self.ratio_columns,
        }


_SKIP_ROW_TYPES = frozenset({"expandable", "dynamic_anchor", "dynamic_marker_end"})


def _row_label(row: Any) -> str:
    if isinstance(row, dict):
        return str(row.get("label") or "").strip()
    if isinstance(row, (list, tuple)) and row:
        return str(row[0] or "").strip()
    return ""


def _source_row_type(row: Any, label: str) -> str | None:
    """合计 / 小计 / 数据；可扩位等占位行返回 None（不进来源行）。"""
    if isinstance(row, dict):
        rt = str(row.get("row_type") or "").strip()
        if rt in _SKIP_ROW_TYPES:
            return None
        if rt in ("total", "subtotal"):
            return rt
        if row.get("is_total") is True:
            return "total"
    key = norm(label).rstrip(":")
    if key in ("合计", "总计"):
        return "total"
    if key.endswith("小计"):
        return "subtotal"
    return "data"


def _tables_of(
    table_data: Any, *, section_number: str | None = None, source_template: str | None = None,
) -> list[Any]:
    """用户在单体附注里看到的表格（workpaper 来源先投影 sub_table_data）。

    无 ``_tables`` 的旧单表格式表头为空时，与附注编辑器读时同一补齐口径
    （``note_header_projector``：模板表头列数对得上就用模板，否则按行 ``_cell_meta`` 语义）。
    """
    from app.services.note_content_utils import effective_table_data

    etd = effective_table_data(table_data) if isinstance(table_data, dict) else None
    if not isinstance(etd, dict) or not etd:
        return []
    tables = etd.get("_tables")
    if isinstance(tables, list) and tables:
        return tables
    if isinstance(etd.get("rows"), list) and etd["rows"]:  # 无 _tables 的旧单表格式
        headers = etd.get("headers") or []
        if not headers:
            from app.services.note_header_projector import derive_headers_for_legacy_table

            headers = derive_headers_for_legacy_table(
                etd, section_number=section_number, source_template=source_template,
            ) or []
        return [{
            "name": etd.get("name"),
            "headers": headers,
            "rows": etd["rows"],
            "_column_groups": etd.get("_column_groups"),
        }]
    return []


def pick_standalone_table(
    tables: list[Any],
    *,
    table_name: str | None = None,
    title: str | None = None,
    section_title: str | None = None,
) -> tuple[int | None, str | None]:
    """只按名字在单体章节的表格里找合并章节对应的那一张。返回 (序号, None) 或 (None, 中文原因)。

    带合并表头的选表（名字 + 列语义键）用 ``read_source_table``；本函数给只有名字的调用方。
    """
    choice = choose_unit(tables, table_name=table_name, title=title, section_title=section_title)
    return choice.primary, choice.reason


def _occurrence_index(rows: list[Any]) -> dict[tuple[str, int], Any]:
    """按「行名 + 同名序号」索引（列续表与主表对行，不按位置）。"""
    index: dict[tuple[str, int], Any] = {}
    seen: dict[str, int] = {}
    for r in rows:
        key = norm(_row_label(r))
        if not key:
            continue
        index[(key, seen.get(key, 0))] = r
        seen[key] = seen.get(key, 0) + 1
    return index


def _cell(row: Any, col: int) -> float | int | None:
    vals = row_values(row)
    return to_number(vals[col - 1]) if 0 <= col - 1 < len(vals) else None


def _rows_from(
    primary: dict, joined: list[dict[tuple[str, int], Any]], col_map: dict[int, tuple[int, int]], width: int,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: dict[str, int] = {}
    for r in primary.get("rows") or []:
        label = _row_label(r)
        key = norm(label)
        if not key:
            continue
        rt = _source_row_type(r, label)
        if rt is None:
            continue
        occurrence = (key, seen.get(key, 0))
        seen[key] = occurrence[1] + 1
        values: list[float | int | None] = [None] * width
        for c, (pos, s) in col_map.items():
            src = r if pos == 0 else joined[pos - 1].get(occurrence)
            if src is not None and 1 <= c <= width:
                values[c - 1] = _cell(src, s)
        item: dict[str, Any] = {"label": label, "row_type": rt, "values": values}
        pushed = r.get("_pushed_row_id") if isinstance(r, dict) else None
        if pushed:  # 集团下推的行（consol_note_template_push_service）：按行身份对应合并模板行
            item["_pushed_row_id"] = str(pushed)
            # 下推类别与可选行开关一起带出：子企业把可选行标成「本企业不适用」（False）⇒ 拉数不取这一行的数
            # （spec note-pull-followup-closure R12；结构指纹不含这两个键，见 extract_source_rows）
            if r.get("_pushed_category"):
                item["_pushed_category"] = str(r["_pushed_category"])
            if "_pushed_optional_active" in r:
                item["_pushed_optional_active"] = r["_pushed_optional_active"] is not False
        out.append(item)
    return out


def read_source_table(
    table_data: Any,
    *,
    consol_table: dict | None,
    table_name: str | None = None,
    title: str | None = None,
    section_title: str | None = None,
    std: str | None = None,
    consol_section_id: str | None = None,
    standalone_section: str | None = None,
) -> SourceTable:
    """读一家企业单体附注章节里与合并章节对应的表，按合并模板列对齐成标准来源行。

    ``consol_table`` 为合并附注模板表（``find_table``）；缺失时按单体表自身列输出。
    ``section_title`` 为单体章节标题（旧单表格式的表没有名字时用来确认是主表）。
    ``std`` / ``consol_section_id`` / ``standalone_section`` 用于套标题行库词表里的逐表覆盖。
    """
    tables = _tables_of(table_data, section_number=standalone_section, source_template=std)
    if not tables:
        return SourceTable(reason="单体附注该章节没有表格数据")
    vocab = load_vocabulary()
    has_target = isinstance(consol_table, dict) and bool(consol_table.get("headers"))
    target_keys: list[ColumnKey] | None = column_keys(
        consol_table,
        identity=table_identity(f"{std}_consolidated" if std else None, consol_section_id),
        vocab=vocab,
    ) if has_target else None
    variant = f"{std}_standalone" if std else None
    identities = [
        table_identity(variant, f"{standalone_section}#{t.get('name') or ''}" if standalone_section else None)
        if isinstance(t, dict) else None
        for t in tables
    ]
    links = continuation_links(tables, variant=variant, section=standalone_section, vocab=vocab)
    choice = choose_unit(
        tables, target_keys=target_keys, table_name=table_name, title=title, section_title=section_title,
        links=links, identities=identities, vocab=vocab,
    )
    if choice.primary is None:
        return SourceTable(reason=choice.reason)
    primary = tables[choice.primary]
    if target_keys is None:  # 没有合并模板表：按单体主表自身列输出
        target_keys = column_keys(primary, identity=identities[choice.primary], vocab=vocab)
    member_keys = choice.member_keys or unit_member_keys(
        tables, choice.members, target_keys=target_keys, identities=identities, vocab=vocab,
    )
    match = choice.match or match_columns(target_keys, member_keys, vocab)
    width = max(len(target_keys) - 1, 0)
    joined = [_occurrence_index(tables[i].get("rows") or []) for i in choice.members[1:]]
    rows = _rows_from(primary, joined, match.col_map, width)
    for extra in choice.row_members:  # 行续表：同样的列补行，按它自己的列对应追加
        extra_keys = unit_member_keys(tables, [extra], target_keys=target_keys, identities=identities, vocab=vocab)
        extra_match = match_columns(target_keys, extra_keys, vocab)
        if extra_match.col_map:
            rows += _rows_from(tables[extra], [], extra_match.col_map, width)
    # 同名行的出现序号（主表 + 行续表连起来数）：映射可按（行名, 序号）取行（spec note-pull-followup-closure R11）
    # 按去首尾空白的行名数（与映射的 source_label、建议的来源行同一个键）
    seen: dict[str, int] = {}
    for item in rows:
        item["_occurrence"] = seen.get(item["label"], 0)
        seen[item["label"]] = item["_occurrence"] + 1

    return SourceTable(
        rows=rows,
        table_name=str(primary.get("name") or "") or None,
        matched_columns=sorted(match.col_map),
        unmatched_columns=[target_keys[c].label for c in match.unmatched],
        ratio_columns=[target_keys[c].label for c in match.ratio],
        reason=None if rows else "单体附注对应表格没有行",
        table_choice=choice.method,
    )
