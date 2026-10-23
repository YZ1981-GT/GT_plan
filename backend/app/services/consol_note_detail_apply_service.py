"""合并附注明细刷新 apply service（Phase 4 Task 22~27）。

spec: consol-note-detail-template-and-mapping（consol-note-pull-from-standalone 收口）

按已确认的映射规则，把各子企业单体附注的来源行（``consol_note_detail_source_service.
load_source_tables``，已按合并模板列对齐）汇总后写入 ``consol_note_data.data.rows``。
合计 / 小计行按本表数据重算。Service 只 flush 不 commit。
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.consol_note_data_models import ConsolNoteData
from app.services.consol_note_table_totals import to_decimal as _to_decimal
from app.models.consol_note_mapping_models import (
    ConsolNoteDetailTemplateVersion,
    ConsolNoteMappingBinding,
    ConsolNoteMappingRule,
    ConsolNoteTemplateBinding,
)

logger = logging.getLogger(__name__)

# 与 consol_note_formula_service 同口径的 manual_cells 解析
CONSOL_NOTE_CELL_STATES_LOCKED = ("locked",)

#: 写入来源标记（ConsolNoteTab 据此显示「📋 明细映射」）
WRITE_SOURCE = "detail_mapping"


class ApplyError(Exception):
    def __init__(self, status: int, code: str, message: str, detail: Any = None):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.detail = detail


# ═══════════════════════════════════════════════════════════════════════════════
# apply（R4.1.3 / R4.3 / R4.4 / R5.4 / D§四）
# ═══════════════════════════════════════════════════════════════════════════════


async def apply_detail_refresh(
    db: AsyncSession,
    *,
    project_id: UUID,
    section_id: str,
    year: int,
    node_key: str | None = None,
    preview_entity_hashes: dict[str, str] | None = None,
    scope_leaves: list[Any] | None = None,
    template_type: str | None = None,
) -> dict[str, Any]:
    """按已确认映射规则，将来源行转换后写入 consol_note_data。

    ``scope_leaves`` / ``template_type``：节点子树重新汇总逐节点调用时传入（已建好的树里该节点的数据叶子、
    已解析的附注模板），免得每个章节每个节点重建一次企业树、重查一次模板口径。

    流程：
    1. 加载模板绑定 → 模板行
    2. 加载已确认绑定；``node_key`` 给定时只取该节点子树内的企业
    3. 一次读取全部来源（单体附注，按合并模板列对齐）；校验 preview 指纹（409 防护）
    4. 检查阻断条件（映射目标行不在模板中）
    5. 按规则把来源行汇总到目标行
    6. 读取 consol_note_data → 手工保护 / locked 跳过
    7. 写入新行（合计 / 小计按本表数据重算）+ 穿透 provenance
    8. 清 is_stale
    """
    from app.services.consol_note_detail_source_service import (
        compute_source_structure_hash,
        load_source_tables,
        resolve_section_template_type,
    )
    from app.services.consol_note_formula_service import find_table

    # ── 1. 模板绑定 ──
    binding = (await db.execute(
        sa.select(ConsolNoteTemplateBinding).where(
            ConsolNoteTemplateBinding.project_id == project_id,
            ConsolNoteTemplateBinding.section_id == section_id,
        )
    )).scalar_one_or_none()
    if binding is None:
        raise ApplyError(400, "NO_TEMPLATE_BINDING", "该章节未绑定明细模板，请先绑定")

    version = (await db.execute(
        sa.select(ConsolNoteDetailTemplateVersion).where(
            ConsolNoteDetailTemplateVersion.id == binding.template_version_id,
        )
    )).scalar_one_or_none()
    if version is None:
        raise ApplyError(400, "VERSION_MISSING", "绑定的模板版本不存在")

    template_rows: list[dict[str, Any]] = version.rows if isinstance(version.rows, list) else []
    target_row_index = {str(tr["target_row_id"]): i for i, tr in enumerate(template_rows)}
    if template_type is None:
        template_type = await resolve_section_template_type(db, project_id)

    # ── 2. 加载确认绑定（按节点子树限定） ──
    entity_bindings = list((await db.execute(
        sa.select(ConsolNoteMappingBinding).where(
            ConsolNoteMappingBinding.project_id == project_id,
            ConsolNoteMappingBinding.section_id == section_id,
        )
    )).scalars().all())

    if scope_leaves is None:
        scope_leaves = await _scope_data_leaves(db, project_id, node_key)
    out_of_scope: list[str] = []
    if scope_leaves is not None:
        scope_keys = {leaf.node_key for leaf in scope_leaves}
        out_of_scope = [
            b.entity_node_key for b in entity_bindings
            if b.entity_node_key not in scope_keys and b.status in ("confirmed", "stale")
        ]
        entity_bindings = [b for b in entity_bindings if b.entity_node_key in scope_keys]

    confirmed = [b for b in entity_bindings if b.status == "confirmed"]
    stale = [b for b in entity_bindings if b.status == "stale"]

    if not confirmed and not stale:
        raise ApplyError(400, "NO_BINDINGS", "该章节没有已确认的企业绑定，请先预览并确认映射")

    # ── 3. 一次读取全部来源（已确认企业 + 本节点范围内全部数据叶子） ──
    source_pids = [b.entity_project_id for b in confirmed]
    source_pids += [leaf.project_id for leaf in (scope_leaves or []) if leaf.project_id is not None]
    sources = await load_source_tables(
        db, source_pids, section_id, year, template_type=template_type,
    )

    def _rows_of(pid: UUID) -> list[Any]:
        src = sources.get(pid)
        return src.rows if src is not None else []

    if preview_entity_hashes:
        for b in confirmed:
            expected = preview_entity_hashes.get(b.entity_node_key)
            if expected is None:
                continue
            if compute_source_structure_hash(section_id, _rows_of(b.entity_project_id)) != expected:
                raise ApplyError(
                    409, "SOURCE_CHANGED",
                    f"企业 {b.entity_node_key} 的来源数据已变化，请重新预览",
                )

    # ── 4. 加载规则并检查阻断 ──
    rule_ids = list({b.rule_id for b in confirmed if b.rule_id is not None})
    rule_cache: dict[UUID, ConsolNoteMappingRule] = {}
    if rule_ids:
        for rule in (await db.execute(
            sa.select(ConsolNoteMappingRule).where(ConsolNoteMappingRule.id.in_(rule_ids))
        )).scalars().all():
            rule_cache[rule.id] = rule

    unmapped_labels: list[str] = []
    for b in confirmed:
        rule = rule_cache.get(b.rule_id)
        if rule is None:
            unmapped_labels.append(f"企业 {b.entity_node_key} 的规则已删除")
            continue
        for m in (rule.mappings if isinstance(rule.mappings, list) else []):
            if m.get("mapping_action", "") in ("map", "map_merge"):
                trid = str(m.get("target_row_id", ""))
                if trid not in target_row_index:
                    unmapped_labels.append(f"映射目标行 {trid} 不在当前模板中")

    # R4.3.1：存在未处理行时阻断
    if unmapped_labels:
        raise ApplyError(
            400, "UNMAPPED_ROWS",
            f"存在 {len(unmapped_labels)} 条未处理映射，请先完善规则",
            {"unmapped": unmapped_labels[:20]},
        )

    # ── 5. 按规则汇总 ──
    consol_table = find_table(template_type, section_id) or {}
    template_headers = list(consol_table.get("headers") or [])
    width = max(len(template_headers), 3)  # 最少 3 列（项目名 + 本期 + 上期）
    for b in confirmed:
        for sr in _rows_of(b.entity_project_id):
            width = max(width, _row_width(sr))

    target_amounts: dict[int, dict[int, Decimal]] = {}
    provenance: list[dict[str, Any]] = []
    applied_entities: list[str] = []
    skipped_entities: list[dict[str, Any]] = [
        {"node_key": b.entity_node_key, "reason": "来源结构已变化，需重新确认映射"} for b in stale
    ]

    for b in confirmed:
        rule = rule_cache.get(b.rule_id)
        if rule is None:
            continue
        source_rows = _rows_of(b.entity_project_id)
        if not source_rows:
            src = sources.get(b.entity_project_id)
            skipped_entities.append({
                "node_key": b.entity_node_key,
                "reason": (src.reason if src is not None else None) or "未读到来源",
            })
            continue
        source_by_label: dict[str, list[Any]] = {}
        # V204: 同时按 _pushed_row_id 索引（集团下推行即使改了名也能找到）
        source_by_rid: dict[str, list[Any]] = {}
        for sr in source_rows:
            source_by_label.setdefault(_first_cell(sr).strip(), []).append(sr)
            rid = sr.get("_pushed_row_id") or (sr if isinstance(sr, dict) else {}).get("_pushed_row_id", "")
            if rid:
                source_by_rid.setdefault(rid, []).append(sr)

        entity_contrib: list[dict[str, Any]] = []
        for m in (rule.mappings if isinstance(rule.mappings, list) else []):
            if m.get("mapping_action", "") == "ignore":
                continue
            target_row_id = str(m.get("target_row_id", ""))
            target_idx = target_row_index.get(target_row_id)
            if target_idx is None:
                continue
            source_label = str(m.get("source_label", "")).strip()
            # 按 label 找来源行；找不到时 fallback 按 _pushed_row_id（V204）
            matched_rows = source_by_label.get(source_label, [])
            if not matched_rows:
                matched_rows = source_by_rid.get(target_row_id, [])
            for sr in matched_rows:
                amounts = _extract_amounts(sr, width)
                bucket = target_amounts.setdefault(target_idx, {})
                for col, val in amounts.items():
                    bucket[col] = bucket.get(col, Decimal("0")) + val
                entity_contrib.append({
                    "source_label": source_label,
                    "target_row_id": target_row_id,
                    "target_name": template_rows[target_idx].get("canonical_name", ""),
                    "amounts": {str(k): str(v) for k, v in amounts.items()},
                })

        applied_entities.append(b.entity_node_key)
        provenance.append({
            "entity_node_key": b.entity_node_key,
            "entity_project_id": str(b.entity_project_id),
            "contributions": entity_contrib,
        })

    # 本节点范围内读到了来源、却还没确认映射的企业（合并数会缺它们）
    bound_keys = {b.entity_node_key for b in entity_bindings if b.status in ("confirmed", "stale", "excluded")}
    unbound_entities = [
        {"node_key": leaf.node_key, "company_name": getattr(leaf, "company_name", "") or ""}
        for leaf in (scope_leaves or [])
        if leaf.node_key not in bound_keys and leaf.project_id is not None and _rows_of(leaf.project_id)
    ]

    # ── 6. 读取 consol_note_data ──
    note_record = await _load_or_create_note_data(
        db, project_id, year, section_id, node_key,
    )

    # 手工保护 + locked 检查
    if getattr(note_record, "cell_state", "auto") in CONSOL_NOTE_CELL_STATES_LOCKED:
        return {
            "status": "skipped_locked",
            "reason": "整节被锁定（cell_state=locked），不覆盖",
            "section_id": section_id,
        }

    data = dict(note_record.data) if isinstance(note_record.data, dict) else {}
    protected = _parse_manual_cells(data) | _parse_locked_cells(note_record)
    existing_rows = data.get("rows", [])
    if existing_rows and isinstance(existing_rows[0], (list, tuple)):
        width = max(width, len(existing_rows[0]))

    # ── 7. 构建新行（以模板行为骨架；合计 / 小计按本表数据重算，与节点子树汇总共用） ──
    from app.services.consol_note_table_totals import build_table_rows

    new_rows, filled, kept_manual = build_table_rows(
        [(tr.get("canonical_name", ""), tr.get("row_type")) for tr in template_rows],
        target_amounts,
        width=width,
        protected=protected,
        existing_rows=existing_rows,
    )

    headers = data.get("headers") or template_headers or ["项目"] + [f"列{c}" for c in range(1, width)]

    data["rows"] = new_rows
    data["headers"] = headers
    data["_detail_provenance"] = provenance
    data["_last_write_source"] = WRITE_SOURCE
    data["_detail_entity_count"] = len(applied_entities)
    data["_detail_applied_at"] = datetime.now(timezone.utc).isoformat()

    note_record.data = data
    note_record.is_stale = False
    note_record.updated_at = datetime.now(timezone.utc)
    await db.flush()

    return {
        "status": "applied",
        "section_id": section_id,
        "node_key": node_key,
        "applied_entity_count": len(applied_entities),
        "skipped_stale": [b.entity_node_key for b in stale],
        "skipped_entities": skipped_entities,
        "unbound_entities": unbound_entities,
        "out_of_scope_count": len(out_of_scope),
        "filled_count": len(filled),
        "kept_manual_count": len(kept_manual),
        "filled": filled[:50],
        "kept_manual": kept_manual[:50],
        "template_row_count": len(template_rows),
        "output_row_count": len(new_rows),
    }


# ─── 内部辅助 ────────────────────────────────────────────────────────────────


async def _scope_data_leaves(db: AsyncSession, project_id: UUID, node_key: str | None) -> list[Any] | None:
    """``node_key`` 子树内的数据叶子；``node_key`` 为空（项目级兼容行）时返回 None = 不限定。

    中间合并节点只汇总自己子树里的企业，不能把整棵树的企业都加进来。
    """
    if not node_key:
        return None
    from app.services.consol_calc_basis import data_leaves
    from app.services.consol_tree_service import build_tree, find_node_by_key

    tree = await build_tree(db, project_id)
    if tree is None:
        raise ApplyError(400, "NO_TREE", "无法构建企业树，不能按节点写入")
    node = find_node_by_key(tree, node_key)
    if node is None:
        raise ApplyError(404, "NODE_NOT_FOUND", f"节点 {node_key} 不在当前企业树中")
    return data_leaves(node)


def _first_cell(row: Any) -> str:
    """提取行标签——与 source service 同口径。"""
    from app.services.consol_note_detail_source_service import _first_cell as _fc
    return _fc(row)


def _row_width(row: Any) -> int:
    """来源行覆盖到的列数（含第 0 列行名）。"""
    if isinstance(row, dict):
        vals = row.get("values")
        return len(vals) + 1 if isinstance(vals, (list, tuple)) else 0
    if isinstance(row, (list, tuple)):
        return len(row)
    return 0


def _extract_amounts(row: Any, width: int) -> dict[int, Decimal]:
    """来源行 → ``{合并模板列号: 金额}``。

    - 标准来源行 ``{label, values:[...]}``：``values[k]`` 是第 ``k+1`` 列（行名不在 values 里）
    - ``{label, values:{"1": v, ...}}``：键即列号
    - ``[label, v1, v2, ...]``：第 ``j`` 项是第 ``j`` 列
    """
    pairs: list[tuple[int, Any]] = []
    if isinstance(row, dict):
        vals = row.get("values")
        if isinstance(vals, dict):
            pairs = [(int(k), v) for k, v in vals.items() if str(k).isdigit()]
        elif isinstance(vals, (list, tuple)):
            pairs = [(k + 1, v) for k, v in enumerate(vals)]
    elif isinstance(row, (list, tuple)):
        pairs = [(j, v) for j, v in enumerate(row) if j >= 1]

    amounts: dict[int, Decimal] = {}
    for col, raw in pairs:
        if not 1 <= col < width:
            continue
        value = _to_decimal(raw)
        if value is not None:
            amounts[col] = value
    return amounts


def _parse_manual_cells(data: dict) -> set[tuple[int, int]]:
    """解析 manual_cells 坐标集合。"""
    raw = data.get("manual_cells")
    if not isinstance(raw, list):
        return set()
    out: set[tuple[int, int]] = set()
    for item in raw:
        try:
            if isinstance(item, dict):
                out.add((int(item["row"]), int(item["col"])))
            elif isinstance(item, (list, tuple)) and len(item) == 2:
                out.add((int(item[0]), int(item[1])))
            elif isinstance(item, str) and ":" in item:
                r, c = item.split(":", 1)
                out.add((int(r), int(c)))
        except (KeyError, TypeError, ValueError):
            pass
    return out


def _parse_locked_cells(record: Any) -> set[tuple[int, int]]:
    """解析 locked_cells 坐标集合。"""
    raw = getattr(record, "locked_cells", None)
    if not isinstance(raw, list):
        return set()
    out: set[tuple[int, int]] = set()
    for item in raw:
        if isinstance(item, dict) and "row_index" in item and "col_index" in item:
            try:
                out.add((int(item["row_index"]), int(item["col_index"])))
            except (TypeError, ValueError):
                pass
    return out


async def _load_or_create_note_data(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    section_id: str,
    node_key: str | None,
) -> ConsolNoteData:
    """加载或创建 consol_note_data 行。

    node_key=None 时操作项目级兼容行（与 consol_note_formula_service.fill_by_formula 同口径）。
    """
    q = sa.select(ConsolNoteData).where(
        ConsolNoteData.project_id == project_id,
        ConsolNoteData.year == year,
        ConsolNoteData.section_id == section_id,
    )
    if node_key is not None:
        q = q.where(ConsolNoteData.node_key == node_key)
    else:
        q = q.where(ConsolNoteData.node_key.is_(None))

    record = (await db.execute(q)).scalar_one_or_none()
    if record is not None:
        return record

    record = ConsolNoteData(
        project_id=project_id,
        year=year,
        section_id=section_id,
        node_key=node_key,
        data={},
        is_stale=False,
    )
    db.add(record)
    await db.flush()
    return record
