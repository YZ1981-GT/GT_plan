"""合并附注根节点数据到 Word 导出章节的只读适配器。

``ConsolNoteData`` 以“一张表一行”保存，Word 导出器以“一节多表”消费。
本模块只做严格映射和形态转换，不写 ``DisclosureNote`` 镜像，也不修改模板缓存。
"""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass
from typing import Any, Iterable, Sequence
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession


class ConsolNoteExportError(ValueError):
    """合并附注不能形成可信交付件。"""

    def __init__(self, code: str, message: str, *, status: int = 409):
        super().__init__(message)
        self.code = code
        self.status = status


@dataclass(slots=True)
class ConsolExportNote:
    """``NoteWordExporter`` 可消费的最小章节 DTO。"""

    note_section: str
    section_title: str
    table_data: dict[str, Any]
    content_type: str | None = None
    text_content: str | None = None
    source_template: str | None = None
    sort_order: int | None = None
    is_deleted: bool = False
    is_empty: bool = False
    is_stale: bool = False
    status: str | None = None
    guidance_text: str | None = None
    account_name: str | None = None
    id: UUID | None = None
    project_id: UUID | None = None
    year: int | None = None


@dataclass(slots=True)
class RootConsolNoteRecords:
    """已经项目、年度、企业树校验的根节点原始记录。"""

    template_type: str
    node_key: str
    records: list[Any]


_TRAILING_TABLE_NO = re.compile(r"-[0-9]+$")
_KEY_NOISE = re.compile(r"[\s、，,。·：:（）()【】\[\]＿_\-]+")


def _compact(value: Any) -> str:
    """仅用于同一权威索引内的精确归一比较，不做模糊包含匹配。"""
    return _KEY_NOISE.sub("", str(value or "")).casefold()


def _index_maps(
    index_sections: Sequence[dict[str, Any]],
) -> tuple[dict[str, str], dict[str, str], dict[str, set[str]], dict[str, dict[str, Any]]]:
    if not index_sections:
        raise ConsolNoteExportError(
            "CONSOL_NOTE_INDEX_MISSING",
            "合并附注 Word 章节索引为空，已中止导出",
        )

    aliases: dict[str, str] = {}
    compact_codes: dict[str, str] = {}
    titles: dict[str, set[str]] = {}
    entries: dict[str, dict[str, Any]] = {}

    def register(token: str, canonical: str) -> None:
        previous = aliases.get(token)
        if previous is not None and previous != canonical:
            raise ConsolNoteExportError(
                "CONSOL_NOTE_INDEX_AMBIGUOUS",
                f"合并附注章节别名 {token!r} 同时指向 {previous!r} 和 {canonical!r}",
            )
        aliases[token] = canonical
        compact = _compact(token)
        compact_previous = compact_codes.get(compact)
        if compact_previous is not None and compact_previous != canonical:
            raise ConsolNoteExportError(
                "CONSOL_NOTE_INDEX_AMBIGUOUS",
                f"合并附注章节编号 {token!r} 归一化后存在歧义",
            )
        compact_codes[compact] = canonical

    for item in index_sections:
        code = item.get("section_code") if isinstance(item, dict) else None
        if not isinstance(code, str) or not code.strip():
            raise ConsolNoteExportError(
                "CONSOL_NOTE_INDEX_INVALID",
                "合并附注 Word 章节索引含空 section_code",
            )
        code = code.strip()
        if code in entries:
            raise ConsolNoteExportError(
                "CONSOL_NOTE_INDEX_AMBIGUOUS",
                f"合并附注 Word 章节索引重复：{code}",
            )
        entries[code] = item
        register(code, code)
        for alias in item.get("legacy_aliases") or []:
            if isinstance(alias, str) and alias.strip():
                register(alias.strip(), code)
        title = _compact(item.get("section_title"))
        if title:
            titles.setdefault(title, set()).add(code)

    return aliases, compact_codes, titles, entries


def _canonical_for_table(
    template_type: str,
    table: dict[str, Any],
    *,
    aliases: dict[str, str],
    compact_codes: dict[str, str],
    titles: dict[str, set[str]],
) -> str | None:
    from app.services.consol_note_section_mapping import resolve_mapping_entry

    section_id = table.get("section_id")
    if not isinstance(section_id, str) or not section_id:
        raise ConsolNoteExportError(
            "CONSOL_NOTE_TEMPLATE_INVALID",
            "合并附注表模板含空 section_id",
        )

    mapping = resolve_mapping_entry(template_type, section_id) or {}
    base = _TRAILING_TABLE_NO.sub("", section_id)
    structural = base.replace("-", "、", 1)
    code_candidates = [mapping.get("standalone_note_section"), structural]
    matched = {
        aliases.get(candidate.strip()) or compact_codes.get(_compact(candidate))
        for candidate in code_candidates
        if isinstance(candidate, str) and candidate.strip()
    }
    matched.discard(None)
    if len(matched) > 1:
        raise ConsolNoteExportError(
            "CONSOL_NOTE_SECTION_CONFLICT",
            f"合并附注表 {section_id} 的章节映射冲突：{sorted(matched)}",
        )
    if matched:
        return next(iter(matched))

    title_candidates = (
        mapping.get("standalone_section_title"),
        table.get("parent_section"),
    )
    title_matches: set[str] = set()
    for candidate in title_candidates:
        if not isinstance(candidate, str) or not candidate.strip():
            continue
        title_matches.update(titles.get(_compact(candidate), set()))
    if len(title_matches) > 1:
        raise ConsolNoteExportError(
            "CONSOL_NOTE_SECTION_CONFLICT",
            f"合并附注表 {section_id} 的章节标题映射不唯一：{sorted(title_matches)}",
        )
    return next(iter(title_matches)) if title_matches else None


def _resolve_selected_codes(
    selected: Sequence[str] | None,
    *,
    table_targets: dict[str, str | None],
    aliases: dict[str, str],
    compact_codes: dict[str, str],
) -> set[str] | None:
    if selected is None:
        return None
    if not selected:
        raise ConsolNoteExportError(
            "CONSOL_NOTE_SELECTION_EMPTY",
            "合并附注导出章节列表为空，已中止导出",
        )

    resolved: set[str] = set()
    for raw in selected:
        if not isinstance(raw, str) or not raw.strip():
            raise ConsolNoteExportError(
                "CONSOL_NOTE_SELECTION_INVALID",
                "合并附注导出章节编号不能为空",
            )
        token = raw.strip()
        if token in table_targets:
            canonical = table_targets[token]
        else:
            canonical = aliases.get(token) or compact_codes.get(_compact(token))
        if canonical is None:
            raise ConsolNoteExportError(
                "CONSOL_NOTE_SELECTION_INVALID",
                f"所选合并附注章节不存在或未映射到 Word：{token}",
            )
        resolved.add(canonical)
    return resolved


def _export_row(
    row: Any,
    *,
    width: int,
    section_id: str,
    row_index: int,
    row_type: str | None,
) -> dict[str, Any]:
    if isinstance(row, (list, tuple)):
        if len(row) != width:
            raise ConsolNoteExportError(
                "CONSOL_NOTE_ROW_INVALID",
                f"合并附注表 {section_id} 第 {row_index + 1} 行有 {len(row)} 列，模板要求 {width} 列",
            )
        result: dict[str, Any] = {
            "label": copy.deepcopy(row[0]),
            "values": copy.deepcopy(list(row[1:])),
        }
    elif isinstance(row, dict):
        result = copy.deepcopy(row)
        label = result.get("label", result.get("name"))
        values = result.get("values")
        if values is None:
            values = result.get("cells")
        if label is None or not isinstance(values, (list, tuple, dict)):
            raise ConsolNoteExportError(
                "CONSOL_NOTE_ROW_INVALID",
                f"合并附注表 {section_id} 第 {row_index + 1} 行对象缺少 label 与 values/cells",
            )
        if isinstance(values, dict):
            projected = [
                copy.deepcopy(values.get(str(i), values.get(i, "")))
                for i in range(1, width)
            ]
        else:
            projected = copy.deepcopy(list(values))
            if len(projected) != width - 1:
                raise ConsolNoteExportError(
                    "CONSOL_NOTE_ROW_INVALID",
                    f"合并附注表 {section_id} 第 {row_index + 1} 行数据列数与模板不一致",
                )
        result["label"] = copy.deepcopy(label)
        result["values"] = projected
        result.pop("name", None)
        if "cells" in result:
            result["cells"] = copy.deepcopy(projected)
    else:
        raise ConsolNoteExportError(
            "CONSOL_NOTE_ROW_INVALID",
            f"合并附注表 {section_id} 第 {row_index + 1} 行不是数组或对象",
        )

    if row_type and not result.get("row_type"):
        result["row_type"] = row_type
    return result


def _export_table(template: dict[str, Any], record: Any) -> dict[str, Any]:
    section_id = str(template.get("section_id") or "")
    payload = getattr(record, "data", None)
    if not isinstance(payload, dict):
        raise ConsolNoteExportError(
            "CONSOL_NOTE_DATA_INVALID",
            f"合并附注表 {section_id} 的保存数据不是对象",
        )

    headers = template.get("headers")
    stored_headers = payload.get("headers")
    rows = payload.get("rows")
    if not isinstance(headers, list) or not headers:
        raise ConsolNoteExportError(
            "CONSOL_NOTE_TEMPLATE_INVALID",
            f"合并附注表 {section_id} 的模板表头为空",
        )
    if not isinstance(stored_headers, list) or len(stored_headers) != len(headers):
        raise ConsolNoteExportError(
            "CONSOL_NOTE_DATA_INVALID",
            f"合并附注表 {section_id} 的保存表头与当前模板不一致",
        )
    if not isinstance(rows, list):
        raise ConsolNoteExportError(
            "CONSOL_NOTE_DATA_INVALID",
            f"合并附注表 {section_id} 缺少 rows 数组",
        )

    table = copy.deepcopy(template)
    row_types = table.get("_row_types") if isinstance(table.get("_row_types"), list) else []
    table["headers"] = copy.deepcopy(headers)
    table["rows"] = [
        _export_row(
            row,
            width=len(headers),
            section_id=section_id,
            row_index=index,
            row_type=row_types[index] if index < len(row_types) else None,
        )
        for index, row in enumerate(rows)
    ]
    table["name"] = str(template.get("title") or template.get("parent_section") or section_id)
    for key in ("_formulas", "manual_cells", "_cell_modes"):
        if key in payload:
            table[key] = copy.deepcopy(payload[key])
    return table


def adapt_root_consol_records(
    records: Iterable[Any],
    *,
    project_id: UUID,
    year: int,
    template_type: str,
    index_sections: Sequence[dict[str, Any]],
    table_templates: Sequence[dict[str, Any]],
    selected_sections: Sequence[str] | None = None,
) -> list[ConsolExportNote]:
    """把已按根节点作用域读取的表记录严格聚合为 Word 章节。"""
    aliases, compact_codes, titles, index_entries = _index_maps(index_sections)

    table_by_id: dict[str, dict[str, Any]] = {}
    table_targets: dict[str, str | None] = {}
    for table in table_templates:
        section_id = table.get("section_id") if isinstance(table, dict) else None
        if not isinstance(section_id, str) or not section_id:
            raise ConsolNoteExportError(
                "CONSOL_NOTE_TEMPLATE_INVALID",
                "合并附注表模板含空 section_id",
            )
        if section_id in table_by_id:
            raise ConsolNoteExportError(
                "CONSOL_NOTE_TEMPLATE_INVALID",
                f"合并附注表模板重复：{section_id}",
            )
        table_by_id[section_id] = table
        table_targets[section_id] = _canonical_for_table(
            template_type,
            table,
            aliases=aliases,
            compact_codes=compact_codes,
            titles=titles,
        )

    selected_codes = _resolve_selected_codes(
        selected_sections,
        table_targets=table_targets,
        aliases=aliases,
        compact_codes=compact_codes,
    )
    unresolved = [sid for sid, code in table_targets.items() if code is None]
    if selected_codes is None and unresolved:
        sample = "、".join(unresolved[:5])
        raise ConsolNoteExportError(
            "CONSOL_NOTE_TEMPLATE_UNMAPPED",
            f"当前合并附注模板有 {len(unresolved)} 张表未映射到 Word 章节：{sample}",
        )

    expected = [
        table
        for section_id, table in table_by_id.items()
        if table_targets[section_id] is not None
        and (selected_codes is None or table_targets[section_id] in selected_codes)
    ]
    expected_codes = {table_targets[str(table["section_id"])] for table in expected}
    if selected_codes is not None:
        missing_groups = selected_codes - expected_codes
        if missing_groups:
            raise ConsolNoteExportError(
                "CONSOL_NOTE_SECTION_DATA_MISSING",
                f"所选合并附注章节没有表级数据定义：{'、'.join(sorted(missing_groups))}",
            )

    record_by_id: dict[str, Any] = {}
    unknown: list[str] = []
    for record in records:
        section_id = getattr(record, "section_id", None)
        if not isinstance(section_id, str) or not section_id:
            raise ConsolNoteExportError(
                "CONSOL_NOTE_DATA_INVALID",
                "根节点合并附注存在空 section_id 记录",
            )
        if section_id in record_by_id:
            raise ConsolNoteExportError(
                "CONSOL_NOTE_DATA_DUPLICATE",
                f"根节点合并附注章节重复：{section_id}",
            )
        record_by_id[section_id] = record
        if section_id not in table_by_id:
            unknown.append(section_id)
    if unknown and selected_codes is None:
        raise ConsolNoteExportError(
            "CONSOL_NOTE_DATA_UNKNOWN_SECTION",
            f"根节点合并附注含 {len(unknown)} 个当前模板不存在的章节：{'、'.join(unknown[:5])}",
        )

    required_ids = [str(table["section_id"]) for table in expected]
    missing = [section_id for section_id in required_ids if section_id not in record_by_id]
    if missing:
        raise ConsolNoteExportError(
            "CONSOL_NOTE_SECTION_DATA_MISSING",
            f"根节点合并附注缺少 {len(missing)} 张表的数据：{'、'.join(missing[:5])}",
        )
    stale = [section_id for section_id in required_ids if bool(getattr(record_by_id[section_id], "is_stale", False))]
    if stale:
        raise ConsolNoteExportError(
            "CONSOL_NOTE_DATA_STALE",
            f"根节点合并附注有 {len(stale)} 张表待重新汇总：{'、'.join(stale[:5])}",
        )

    grouped: dict[str, list[dict[str, Any]]] = {}
    for table in expected:
        section_id = str(table["section_id"])
        canonical = table_targets[section_id]
        assert canonical is not None
        grouped.setdefault(canonical, []).append(
            _export_table(table, record_by_id[section_id])
        )

    result: list[ConsolExportNote] = []
    for order, item in enumerate(index_sections):
        code = str(item["section_code"]).strip()
        tables = grouped.get(code)
        if not tables:
            continue
        result.append(
            ConsolExportNote(
                note_section=code,
                section_title=str(item.get("section_title") or code),
                content_type=str(item.get("content_type") or "mixed"),
                table_data={"_tables": tables},
                source_template=template_type,
                sort_order=order,
                project_id=project_id,
                year=year,
            )
        )

    if not result:
        raise ConsolNoteExportError(
            "CONSOL_NOTE_SECTION_DATA_MISSING",
            "根节点合并附注没有可导出的章节数据",
        )
    return result


async def load_root_consol_records(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    *,
    template_type: str | None = None,
) -> RootConsolNoteRecords:
    """验证项目、年度与企业树后，只读加载根节点原始记录。"""
    from app.services.consol_group_tree import ROLE_CONSOL
    from app.services.consol_node_scope import (
        NodeScopeError,
        load_scoped_note_records,
        resolve_node_scope,
    )
    from app.services.consol_note_formula_service import (
        NoteFormulaError,
        resolve_note_template_type,
    )
    from app.services.consol_tree_service import build_tree

    try:
        actual_template = await resolve_note_template_type(
            db, project_id, requested=template_type
        )
    except NoteFormulaError as exc:
        raise ConsolNoteExportError(
            "CONSOL_NOTE_TEMPLATE_SCOPE_MISMATCH",
            str(exc),
            status=getattr(exc, "status", 400),
        ) from exc

    tree = await build_tree(db, project_id)
    if tree is None or tree.role != ROLE_CONSOL or not tree.node_key:
        raise ConsolNoteExportError(
            "CONSOL_NOTE_ROOT_MISSING",
            "合并项目无法确定唯一企业树根节点，已中止附注导出",
        )
    try:
        scope = await resolve_node_scope(db, project_id, year, tree.node_key)
    except NodeScopeError as exc:
        raise ConsolNoteExportError(
            "CONSOL_NOTE_ROOT_SCOPE_INVALID",
            str(exc),
            status=getattr(exc, "status", 400),
        ) from exc
    if not scope.is_root_consol or scope.node_key != tree.node_key:
        raise ConsolNoteExportError(
            "CONSOL_NOTE_ROOT_SCOPE_INVALID",
            "合并附注读取范围不是当前企业树根节点，已中止导出",
        )

    records = await load_scoped_note_records(
        db,
        scope,
        allow_root_legacy_fallback=True,
    )
    if not records:
        raise ConsolNoteExportError(
            "CONSOL_NOTE_ROOT_DATA_MISSING",
            "合并项目根节点没有附注数据，请先完成重新汇总",
        )
    return RootConsolNoteRecords(
        template_type=actual_template,
        node_key=tree.node_key,
        records=list(records),
    )


async def load_root_consol_export_notes(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    *,
    template_type: str,
    index_sections: Sequence[dict[str, Any]],
    selected_sections: Sequence[str] | None = None,
) -> list[ConsolExportNote]:
    """加载并严格转换当前合并项目根节点的 Word 导出章节。"""
    from app.services.consol_note_formula_service import consol_note_tables

    root = await load_root_consol_records(
        db,
        project_id,
        year,
        template_type=template_type,
    )
    return adapt_root_consol_records(
        root.records,
        project_id=project_id,
        year=year,
        template_type=root.template_type,
        index_sections=index_sections,
        table_templates=consol_note_tables(root.template_type),
        selected_sections=selected_sections,
    )


__all__ = [
    "ConsolExportNote",
    "ConsolNoteExportError",
    "RootConsolNoteRecords",
    "adapt_root_consol_records",
    "load_root_consol_export_notes",
    "load_root_consol_records",
]
