"""合并附注从单体附注拉取数据服务（路径 A）。

数据流：
  企业树数据叶子 → 各子企业 disclosure_notes → 按章节映射 + 行列匹配 → 汇总个别数

与公式引擎（路径 B：consol_note_formula_service）互不干扰。
reaggregate 端点走路径 A，fill-by-formula 端点走路径 B。

spec: consol-note-pull-from-standalone · Task 2 + Task 3
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Sequence
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.consol_note_section_mapping import (
    resolve_standalone_section,
    resolve_standalone_table_name,
)

logger = logging.getLogger(__name__)

# ─── 列名词表（复用 note_writer 同源） ──────────────────────────────────────

_END_SYNONYMS: frozenset[str] = frozenset({
    "期末余额", "期末数", "期末", "期末金额", "期末账面价值", "期末公允价值",
    "期末余额（账面价值）", "期末余额/本期发生额", "期末数/本期发生额",
    "本期发生额", "本期金额", "本期数", "本期", "本年发生额", "本年金额", "本年数", "本年",
})
_PRIOR_SYNONYMS: frozenset[str] = frozenset({
    "期初余额", "期初数", "期初", "期初金额", "期初账面价值", "期初公允价值",
    "期初余额（账面价值）", "年初余额", "年初数", "年初金额",
    "上年年末余额", "上年年末数", "上年年末", "上年年末余额/上期发生额",
    "期初数/上期发生额", "上期发生额", "上期金额", "上期数", "上期",
    "上年发生额", "上年金额", "上年数", "上年",
})

# 业务键 → 列名组
_FIELD_TO_GROUP: dict[str, frozenset[str]] = {
    "end_amount": _END_SYNONYMS,
    "ending": _END_SYNONYMS,
    "end_balance": _END_SYNONYMS,
    "prior_amount": _PRIOR_SYNONYMS,
    "opening": _PRIOR_SYNONYMS,
    "prior_balance": _PRIOR_SYNONYMS,
}

_WS_RE = re.compile(r"[\s\u3000]+")
_BR_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)


def _norm(text: Any) -> str:
    """列名/行名规范化：去 HTML 换行 + 去空白。"""
    return _WS_RE.sub("", _BR_RE.sub("", str(text or "")))


# ─── 数据结构 ────────────────────────────────────────────────────────────────

@dataclass
class CellValue:
    """合并附注一个单元格的汇总值 + 溯源。"""
    row_index: int
    col_index: int
    row_label: str = ""
    col_name: str = ""
    individual: float = 0.0
    consolidated: float = 0.0
    source: str = "standalone_aggregate"
    by_company: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class LeafStatus:
    """单个数据叶子的读取状态。"""
    company_code: str
    company_name: str
    node_key: str
    project_id: str | None
    status: str  # "found" | "missing" | "empty" | "no_project" | "no_mapping"
    rows_read: int = 0
    reason: str = ""


@dataclass
class AggregateResult:
    """单章节汇总结果。"""
    project_id: str
    year: int
    section_id: str
    node_key: str | None
    template_type: str
    cells: list[CellValue] = field(default_factory=list)
    leaf_summary: list[LeafStatus] = field(default_factory=list)
    unmatched_rows: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def cell_count(self) -> int:
        return len([c for c in self.cells if c.individual != 0.0])


# ─── 标准化表读取 ────────────────────────────────────────────────────────────

@dataclass
class StandardizedRow:
    """标准化的附注行：label + 各列名对应的数值。"""
    label: str
    values: dict[str, float | None]  # {规范化列名: 数值}
    is_total: bool = False


@dataclass
class StandardizedTable:
    """标准化的附注表。"""
    rows: list[StandardizedRow]
    col_names: list[str]  # 规范化后的列名列表


def _safe_float(val: Any) -> float | None:
    """安全转 float。"""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        v = float(val)
        return v if v == v else None  # NaN check
    s = str(val).strip().replace(",", "").replace("，", "")
    if not s:
        return None
    try:
        return float(s)
    except (ValueError, TypeError):
        return None


def _match_column(consol_col_norm: str, standalone_headers_norm: list[str]) -> int | None:
    """合并模板列名（规范化后） → 单体附注 headers 列号。

    1. 精确匹配
    2. 同义词组匹配（同属 _END_SYNONYMS 或 _PRIOR_SYNONYMS）
    3. 斜杠路径末段匹配（合并模板 "期末数/账面余额" → 匹配 "账面余额"）
    """
    # 精确匹配
    for i, h in enumerate(standalone_headers_norm):
        if h == consol_col_norm:
            return i
    # 同义词组匹配
    for synonyms in (_END_SYNONYMS, _PRIOR_SYNONYMS):
        if consol_col_norm in synonyms:
            for i, h in enumerate(standalone_headers_norm):
                if h in synonyms:
                    return i
            break
    # 斜杠路径末段匹配：合并模板可能用 "期末数/账面余额" 编码多级表头
    if "/" in consol_col_norm:
        last_part = consol_col_norm.rsplit("/", 1)[-1]
        if last_part:
            for i, h in enumerate(standalone_headers_norm):
                if h == last_part:
                    return i
            # 末段也走同义词
            for synonyms in (_END_SYNONYMS, _PRIOR_SYNONYMS):
                if last_part in synonyms:
                    for i, h in enumerate(standalone_headers_norm):
                        if h in synonyms:
                            return i
                    break
    return None


def _resolve_consol_col_names(
    headers: list[str],
    column_groups: list[dict] | None,
    multi_header: list[list[str]] | None,
) -> list[str]:
    """把合并模板的 headers（可能有空串）解析为每列的语义名称。

    空串列通过 _column_groups 映射到组名，
    或通过 multi_header 最深非空行取名。
    """
    result = list(headers)

    # 用 _column_groups 补空
    if column_groups:
        for g in column_groups:
            group_name = g.get("group", "")
            start = g.get("start", 0)
            span = g.get("span", 1)
            for ci in range(start, min(start + span, len(result))):
                if not _norm(result[ci]):
                    result[ci] = group_name

    # 用 multi_header 最后一行非空值补空
    if multi_header and len(multi_header) >= 2:
        last_row = multi_header[-1]
        for ci in range(len(result)):
            if not _norm(result[ci]) and ci < len(last_row):
                v = str(last_row[ci] or "").strip()
                if v:
                    result[ci] = v

    # 对仍为空的列，用 multi_header 第一行组名 + 第二行子列名拼成路径
    if multi_header and len(multi_header) >= 2:
        row0 = multi_header[0]
        row1 = multi_header[1] if len(multi_header) > 1 else []
        current_group = ""
        for ci in range(len(result)):
            if ci < len(row0) and str(row0[ci] or "").strip():
                current_group = str(row0[ci]).strip()
            if not _norm(result[ci]) and current_group:
                sub = str(row1[ci]).strip() if ci < len(row1) else ""
                result[ci] = f"{current_group}/{sub}" if sub else current_group

    return result


def read_tables_format(
    table_data: dict,
    table_name: str | None,
    consol_headers: list[str],
) -> StandardizedTable | None:
    """从 _tables 格式（F1）读取并标准化。

    _tables 的行结构是 {label, values:[], is_total, row_type}
    values[i] 对应 headers[i+1]（跳过首列标签）
    """
    tables = table_data.get("_tables")
    if not isinstance(tables, list) or not tables:
        return None

    # 按 table_name 匹配目标表
    target = None
    if table_name:
        norm_name = _norm(table_name)
        for tbl in tables:
            if isinstance(tbl, dict) and _norm(tbl.get("name", "")) == norm_name:
                target = tbl
                break
    # 兜底首表
    if target is None:
        target = tables[0] if isinstance(tables[0], dict) else None
    if target is None:
        return None

    headers = target.get("headers", [])
    rows_data = target.get("rows", [])
    if not headers or not rows_data:
        return None

    # 标准化列名（跳过首列标签）
    standalone_norms = [_norm(h) for h in headers[1:]]

    # 建列映射：合并模板列号(1-based) → 单体 values 下标
    consol_norms = [_norm(h) for h in consol_headers]
    col_map: dict[int, int] = {}  # consol_col_index → standalone_values_index
    for ci in range(1, len(consol_norms)):
        idx = _match_column(consol_norms[ci], standalone_norms)
        if idx is not None:
            col_map[ci] = idx

    std_rows = []
    for row in rows_data:
        if isinstance(row, dict):
            label = str(row.get("label", "")).strip()
            values_arr = row.get("values", [])
            is_total = bool(row.get("is_total"))
        elif isinstance(row, (list, tuple)):
            label = str(row[0]).strip() if row else ""
            values_arr = list(row[1:]) if len(row) > 1 else []
            is_total = _norm(label) in ("合计", "小计")
        else:
            continue

        vals: dict[str, float | None] = {}
        for ci, vi in col_map.items():
            v = values_arr[vi] if vi < len(values_arr) else None
            vals[consol_norms[ci]] = _safe_float(v)

        std_rows.append(StandardizedRow(label=label, values=vals, is_total=is_total))

    mapped_cols = [consol_norms[ci] for ci in sorted(col_map)]
    return StandardizedTable(rows=std_rows, col_names=mapped_cols)


def read_sub_table_format(
    table_data: dict,
    table_name: str | None,
    consol_headers: list[str],
) -> StandardizedTable | None:
    """从 sub_table_data 格式（F2/F3）读取并标准化。"""
    sub = table_data.get("sub_table_data")
    if not isinstance(sub, dict) or not sub:
        return None

    # 按 table_name 找子表
    rows_data = None
    if table_name:
        norm_name = _norm(table_name)
        for k, v in sub.items():
            if _norm(k) == norm_name and isinstance(v, list):
                rows_data = v
                break
    # 兜底首个非空子表
    if rows_data is None:
        for v in sub.values():
            if isinstance(v, list) and v:
                rows_data = v
                break
    if not rows_data:
        return None

    consol_norms = [_norm(h) for h in consol_headers]

    # 检查行格式：F2（业务键）还是 F3（values 数组）
    first = rows_data[0] if rows_data else {}
    if not isinstance(first, dict):
        return None

    has_values = isinstance(first.get("values"), list)
    has_biz_keys = any(k in first for k in ("end_amount", "prior_amount", "ending", "opening"))

    if has_biz_keys and not has_values:
        # F2 格式：{label, end_amount, prior_amount, ...}
        return _read_f2(rows_data, consol_norms, consol_headers)
    elif has_values:
        # F3 格式：{label, values:[], ...}
        columns_def = table_data.get("_sub_table_columns", {})
        col_defs = None
        if table_name:
            col_defs = columns_def.get(table_name)
        if not col_defs:
            for v in columns_def.values():
                if isinstance(v, list) and v:
                    col_defs = v
                    break
        return _read_f3(rows_data, consol_norms, consol_headers, col_defs)

    return None


def _read_f2(
    rows_data: list[dict],
    consol_norms: list[str],
    consol_headers: list[str],
) -> StandardizedTable:
    """F2 格式：行有业务键（end_amount/prior_amount/ending/opening 等）。"""
    # 建业务键 → 合并列名的映射
    key_to_col: dict[str, str] = {}
    for ci in range(1, len(consol_norms)):
        col_norm = consol_norms[ci]
        for biz_key, synonyms in _FIELD_TO_GROUP.items():
            if col_norm in synonyms:
                key_to_col[biz_key] = col_norm
                break

    std_rows = []
    for row in rows_data:
        label = str(row.get("label", "")).strip()
        is_total = bool(row.get("is_total"))
        vals: dict[str, float | None] = {}
        for biz_key, col_name in key_to_col.items():
            v = row.get(biz_key)
            vals[col_name] = _safe_float(v)
        std_rows.append(StandardizedRow(label=label, values=vals, is_total=is_total))

    return StandardizedTable(rows=std_rows, col_names=list(set(key_to_col.values())))


def _read_f3(
    rows_data: list[dict],
    consol_norms: list[str],
    consol_headers: list[str],
    col_defs: list[dict] | None,
) -> StandardizedTable:
    """F3 格式：行有 values 数组 + _sub_table_columns 列定义。"""
    # 列定义转规范化名
    if col_defs:
        standalone_norms = [_norm(d.get("label", d.get("key", ""))) for d in col_defs if not d.get("is_label")]
    else:
        standalone_norms = []

    # 列映射
    col_map: dict[int, int] = {}
    for ci in range(1, len(consol_norms)):
        if standalone_norms:
            idx = _match_column(consol_norms[ci], standalone_norms)
            if idx is not None:
                col_map[ci] = idx
        else:
            # 无列定义：按位置
            vi = ci - 1
            col_map[ci] = vi

    std_rows = []
    for row in rows_data:
        label = str(row.get("label", "")).strip()
        is_total = bool(row.get("is_total"))
        values_arr = row.get("values", [])
        vals: dict[str, float | None] = {}
        for ci, vi in col_map.items():
            v = values_arr[vi] if vi < len(values_arr) else None
            vals[consol_norms[ci]] = _safe_float(v)
        std_rows.append(StandardizedRow(label=label, values=vals, is_total=is_total))

    mapped_cols = [consol_norms[ci] for ci in sorted(col_map)]
    return StandardizedTable(rows=std_rows, col_names=mapped_cols)


def read_standalone_note_table(
    table_data: dict | None,
    table_name: str | None,
    consol_headers: list[str],
) -> StandardizedTable | None:
    """从单体附注 table_data 读取一张表的标准化数据。

    读取优先级（与 note_writer.locate_table 一致）：
    1. sub_table_data[table_name] — 有明确业务键
    2. _tables 中按 table_name 匹配的表 — 用 values[] + headers
    3. _tables[0] — 首表兜底
    """
    if not isinstance(table_data, dict) or not table_data:
        return None

    # 优先 sub_table_data
    result = read_sub_table_format(table_data, table_name, consol_headers)
    if result and result.rows:
        return result

    # 降级到 _tables
    result = read_tables_format(table_data, table_name, consol_headers)
    if result and result.rows:
        return result

    return None


# ─── 行匹配（复用 find_row 三级策略） ───────────────────────────────────────


def _find_matching_row(
    std_rows: list[StandardizedRow],
    target_label: str,
) -> int | None:
    """在标准化行中找匹配行：精确 → 去后缀 → 包含匹配（唯一命中）。"""
    want = _norm(target_label)
    if not want:
        return None

    # ① 精确匹配
    for i, row in enumerate(std_rows):
        if not row.is_total and _norm(row.label) == want:
            return i

    # ② 去"小计"后缀
    for suffix in ("小计",):
        if want.endswith(suffix):
            stripped = want[:-len(suffix)]
            if stripped:
                for i, row in enumerate(std_rows):
                    if not row.is_total and _norm(row.label) == stripped:
                        return i

    # ③ 包含匹配（唯一命中）
    candidates = []
    for i, row in enumerate(std_rows):
        if row.is_total:
            continue
        rl = _norm(row.label)
        if not rl:
            continue
        if want in rl or rl in want:
            candidates.append(i)
    if len(candidates) == 1:
        return candidates[0]

    return None


# ─── 汇总核心 ────────────────────────────────────────────────────────────────


async def _batch_load_notes(
    db: AsyncSession,
    project_ids: list[UUID],
    year: int,
    note_section: str,
) -> dict[UUID, dict]:
    """批量加载各子企业的 disclosure_notes（一次查询）。

    返回 {project_id: table_data_dict}
    """
    from app.models.report_models import DisclosureNote

    if not project_ids:
        return {}

    rows = (await db.execute(
        sa.select(DisclosureNote.project_id, DisclosureNote.table_data).where(
            DisclosureNote.project_id.in_(project_ids),
            DisclosureNote.year == year,
            DisclosureNote.note_section == note_section,
            DisclosureNote.is_deleted == sa.false(),
        )
    )).all()

    result: dict[UUID, dict] = {}
    for row in rows:
        td = row.table_data
        if isinstance(td, dict) and td:
            result[row.project_id] = td
    return result


async def aggregate_section(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    consol_section_id: str,
    template_type: str,
    *,
    tree: Any = None,
) -> AggregateResult:
    """从各子企业单体附注拉取并汇总一个章节。

    步骤：
    1. 查章节映射
    2. 构建/遍历企业树数据叶子
    3. 批量加载各叶子的 disclosure_notes
    4. 逐叶子读取 + 行列匹配 + 累加
    5. 返回 AggregateResult
    """
    from app.services.consol_tree_service import build_tree, iter_nodes

    result = AggregateResult(
        project_id=str(project_id),
        year=year,
        section_id=consol_section_id,
        node_key=None,
        template_type=template_type,
    )

    # 1. 查章节映射
    standalone_section = resolve_standalone_section(template_type, consol_section_id)
    if standalone_section is None:
        result.warnings.append(f"章节 {consol_section_id} 无单体附注映射（合并特有章节）")
        return result

    standalone_table_name = resolve_standalone_table_name(template_type, consol_section_id)

    # 2. 构建企业树
    if tree is None:
        tree = await build_tree(db, project_id)
    if tree is None:
        result.warnings.append("企业树构建失败（项目不存在或不是合并项目）")
        return result

    # 3. 收集数据叶子
    data_leaves = [
        node for node in iter_nodes(tree)
        if node.kind == "data" and node.project_id is not None
    ]
    if not data_leaves:
        result.warnings.append("企业树没有数据叶子（子企业为空）")
        return result

    # 4. 加载合并模板结构
    from app.services.consol_note_formula_service import find_table

    consol_table = find_table(template_type, consol_section_id)
    if consol_table is None:
        result.warnings.append(f"合并附注模板中没有 {consol_section_id}")
        return result

    consol_headers = consol_table.get("headers", [])
    consol_rows = consol_table.get("rows", [])
    if not consol_headers or not consol_rows:
        result.warnings.append(f"合并模板 {consol_section_id} 无表头或行")
        return result

    # 4b. 解析多级表头列名（处理空串和斜杠路径）
    resolved_headers = _resolve_consol_col_names(
        consol_headers,
        consol_table.get("_column_groups"),
        consol_table.get("multi_header"),
    )

    # 5. 批量查询所有叶子的单体附注
    leaf_project_ids = [leaf.project_id for leaf in data_leaves]
    notes = await _batch_load_notes(db, leaf_project_ids, year, standalone_section)

    # 6. 初始化单元格
    cells: dict[tuple[int, int], CellValue] = {}

    # 7. 逐叶子处理
    for leaf in data_leaves:
        if leaf.project_id not in notes:
            result.leaf_summary.append(LeafStatus(
                company_code=leaf.company_code,
                company_name=leaf.company_name,
                node_key=leaf.node_key,
                project_id=str(leaf.project_id),
                status="missing",
                reason=f"附注章节 {standalone_section} 未生成",
            ))
            continue

        table_data = notes[leaf.project_id]
        std_table = read_standalone_note_table(table_data, standalone_table_name, resolved_headers)
        if std_table is None:
            result.leaf_summary.append(LeafStatus(
                company_code=leaf.company_code,
                company_name=leaf.company_name,
                node_key=leaf.node_key,
                project_id=str(leaf.project_id),
                status="empty",
                reason="表格数据为空或格式不可读",
            ))
            continue

        rows_read = 0
        for ri, consol_row in enumerate(consol_rows):
            # 取合并模板行标签
            if isinstance(consol_row, (list, tuple)):
                label = str(consol_row[0]).strip() if consol_row else ""
            elif isinstance(consol_row, dict):
                label = str(consol_row.get("label", "")).strip()
            else:
                continue

            if not label:
                continue

            # 在单体标准化表中找匹配行
            src_idx = _find_matching_row(std_table.rows, label)
            if src_idx is None:
                continue

            src_row = std_table.rows[src_idx]
            rows_read += 1

            # 逐列读数值并累加
            for ci in range(1, len(resolved_headers)):
                col_norm = _norm(resolved_headers[ci])
                val = src_row.values.get(col_norm)
                if val is None or val == 0.0:
                    continue

                cell = cells.setdefault((ri, ci), CellValue(
                    row_index=ri,
                    col_index=ci,
                    row_label=label,
                    col_name=resolved_headers[ci] if ci < len(resolved_headers) else "",
                ))
                cell.individual += val
                cell.by_company.append({
                    "company_code": leaf.company_code,
                    "company_name": leaf.company_name,
                    "node_key": leaf.node_key,
                    "value": val,
                })

        result.leaf_summary.append(LeafStatus(
            company_code=leaf.company_code,
            company_name=leaf.company_name,
            node_key=leaf.node_key,
            project_id=str(leaf.project_id),
            status="found",
            rows_read=rows_read,
        ))

    # 8. 记录未匹配的行（合并模板有但所有子企业都没匹配到的行）
    matched_rows = {cell.row_index for cell in cells.values()}
    for ri, consol_row in enumerate(consol_rows):
        if ri in matched_rows:
            continue
        if isinstance(consol_row, (list, tuple)):
            label = str(consol_row[0]).strip() if consol_row else ""
        elif isinstance(consol_row, dict):
            label = str(consol_row.get("label", "")).strip()
        else:
            label = ""
        if label and _norm(label) not in ("合计", "小计"):
            result.unmatched_rows.append({
                "row_index": ri,
                "label": label,
                "reason": "所有子企业的单体附注中均无对应行",
            })

    # 9. 合并数 = 个别数（Phase 1 差额节点不参与）
    for cell in cells.values():
        cell.consolidated = cell.individual

    result.cells = list(cells.values())
    return result


async def reaggregate_from_standalone(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    section_ids: list[str],
    *,
    node_key: str | None = None,
    template_type: str,
    tree: Any = None,
) -> dict:
    """逐章节从单体附注汇总，以 SAVEPOINT 隔离。

    返回与 fill_note_sections 兼容的结构。
    """
    from app.services.consol_note_formula_service import (
        find_table,
        fill_rows,
        MEASURE_CONSOLIDATED,
    )
    from app.services.consol_tree_service import build_tree
    from app.models.consol_note_data_models import ConsolNoteData

    if tree is None:
        tree = await build_tree(db, project_id)

    results: list[dict] = []
    failures: list[dict] = []
    all_leaf_summaries: list[dict] = []

    for section_id in dict.fromkeys(section_ids):
        try:
            async with db.begin_nested():
                agg = await aggregate_section(
                    db, project_id, year, section_id, template_type, tree=tree,
                )

                if not agg.cells:
                    results.append({
                        "section_id": section_id,
                        "status": "skipped",
                        "reason": "; ".join(agg.warnings) or "无数据",
                        "filled": [],
                        "kept_manual": [],
                        "kept_manual_count": 0,
                        "blank": [],
                        "leaf_summary": [ls.__dict__ for ls in agg.leaf_summary],
                    })
                    continue

                # 加载合并模板
                table = find_table(template_type, section_id) or {}
                headers = table.get("headers", [])
                template_rows = table.get("rows", [])

                # 加载已保存数据
                target = (
                    ConsolNoteData.node_key == node_key if node_key
                    else ConsolNoteData.node_key.is_(None)
                )
                record = (await db.execute(
                    sa.select(ConsolNoteData).where(
                        ConsolNoteData.project_id == project_id,
                        ConsolNoteData.year == year,
                        ConsolNoteData.section_id == section_id,
                        target,
                    )
                )).scalar_one_or_none()

                data = dict(record.data or {}) if record and isinstance(record.data, dict) else {}
                saved_headers = data.get("headers") or headers
                saved_rows = data.get("rows") if isinstance(data.get("rows"), list) else template_rows

                # 跳过锁定章节
                if record and getattr(record, "cell_state", "auto") == "locked":
                    results.append({
                        "section_id": section_id,
                        "status": "skipped_locked",
                        "reason": "整节被锁定",
                        "filled": [], "kept_manual": [], "kept_manual_count": 0, "blank": [],
                        "leaf_summary": [ls.__dict__ for ls in agg.leaf_summary],
                    })
                    continue

                # manual_cells 保护
                manual_set: set[tuple[int, int]] = set()
                raw_manual = data.get("manual_cells")
                if isinstance(raw_manual, list):
                    for item in raw_manual:
                        if isinstance(item, dict) and "row" in item and "col" in item:
                            manual_set.add((int(item["row"]), int(item["col"])))
                        elif isinstance(item, (list, tuple)) and len(item) == 2:
                            manual_set.add((int(item[0]), int(item[1])))
                # locked_cells
                if record:
                    for lc in getattr(record, "locked_cells", None) or []:
                        if isinstance(lc, dict) and "row_index" in lc and "col_index" in lc:
                            manual_set.add((int(lc["row_index"]), int(lc["col_index"])))

                # 构造 fill_rows 需要的 cells 输入
                fill_cells = [
                    {
                        "row_index": cell.row_index,
                        "col_index": cell.col_index,
                        MEASURE_CONSOLIDATED: str(cell.consolidated),
                    }
                    for cell in agg.cells
                ]

                new_rows, summary = fill_rows(saved_headers, saved_rows, fill_cells, manual_set, template_rows)
                data.update({"headers": saved_headers, "rows": new_rows})

                data["_aggregate_source"] = "standalone"
                data["_aggregate_at"] = datetime.now(timezone.utc).isoformat()
                data["_aggregate_leaf_count"] = len([ls for ls in agg.leaf_summary if ls.status == "found"])
                data["_aggregate_cell_count"] = agg.cell_count

                now = datetime.now(timezone.utc)
                now = datetime.now(timezone.utc)

                if record is None:
                    record = ConsolNoteData(
                        project_id=project_id, year=year, section_id=section_id,
                        node_key=node_key, data=data, is_stale=False, updated_at=now,
                    )
                    db.add(record)
                else:
                    record.data = data
                    record.is_stale = False
                    record.updated_at = now

                await db.flush()

                results.append({
                    "section_id": section_id,
                    "node_key": node_key,
                    "status": "persisted",
                    "record_id": str(record.id) if record.id else None,
                    **summary,
                    "leaf_summary": [ls.__dict__ for ls in agg.leaf_summary],
                    "unmatched_rows": agg.unmatched_rows,
                    "cell_count": agg.cell_count,
                })

        except Exception as exc:
            failures.append({
                "section_id": section_id,
                "status": "failed",
                "error": str(exc),
            })
            logger.warning(
                "consol_note_aggregator: 章节 %s 汇总失败", section_id, exc_info=True
            )

    # 收集全局叶子汇总
    seen_leaves: set[str] = set()
    for r in results:
        for ls in r.get("leaf_summary", []):
            key = ls.get("node_key", "")
            if key not in seen_leaves:
                seen_leaves.add(key)
                all_leaf_summaries.append(ls)

    return {
        "project_id": str(project_id),
        "year": year,
        "node_key": node_key,
        "legacy_null": node_key is None,
        "template_type": template_type,
        "status": "persisted" if results and not failures else "failed" if failures else "skipped",
        "results": results,
        "failures": failures,
        "sections_processed": len(results) + len(failures),
        "sections_updated": len([r for r in results if r.get("status") == "persisted"]),
        "leaf_summary": all_leaf_summaries,
        "source": "standalone_aggregate",
    }
