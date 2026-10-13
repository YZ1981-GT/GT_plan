"""合并附注明细刷新 apply service（Phase 4 Task 22~27）。

spec: consol-note-detail-template-and-mapping

按已确认的映射规则，将下属企业来源行转换后写入 consol_note_data.data.rows。
Service 只 flush 不 commit。
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.consol_note_data_models import ConsolNoteData
from app.models.consol_note_mapping_models import (
    ConsolNoteDetailTemplateVersion,
    ConsolNoteMappingBinding,
    ConsolNoteMappingRule,
    ConsolNoteTemplateBinding,
)

logger = logging.getLogger(__name__)

# 与 consol_note_formula_service 同口径的 manual_cells 解析
CONSOL_NOTE_CELL_STATES_LOCKED = ("locked",)


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
) -> dict[str, Any]:
    """按已确认映射规则，将来源行转换后写入 consol_note_data。

    流程：
    1. 加载模板绑定 → 模板行
    2. 加载所有已确认绑定 → 规则 → 来源行
    3. 校验 preview_entity_hashes（409 防护）
    4. 检查阻断条件（未映射行 / 未确认绑定）
    5. 按规则转换来源行 → 按目标行汇总金额
    6. 读取 consol_note_data → 手工保护 / locked 跳过
    7. 写入新行 + 穿透 provenance
    8. 清 is_stale
    """
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

    # ── 2. 加载确认绑定 + 规则 + 来源行 ──
    entity_bindings = (await db.execute(
        sa.select(ConsolNoteMappingBinding).where(
            ConsolNoteMappingBinding.project_id == project_id,
            ConsolNoteMappingBinding.section_id == section_id,
        )
    )).scalars().all()

    confirmed = [b for b in entity_bindings if b.status == "confirmed"]
    stale = [b for b in entity_bindings if b.status == "stale"]

    if not confirmed and not stale:
        raise ApplyError(400, "NO_BINDINGS", "该章节没有已确认的企业绑定，请先预览并确认映射")

    # ── 3. 校验 preview_entity_hashes（409 防护） ──
    if preview_entity_hashes:
        from app.services.consol_note_detail_source_service import (
            compute_source_structure_hash,
            load_entity_source_rows,
        )
        for b in confirmed:
            expected = preview_entity_hashes.get(b.entity_node_key)
            if expected is None:
                continue
            current_rows = await load_entity_source_rows(db, b.entity_project_id, section_id, year)
            current_hash = compute_source_structure_hash(section_id, current_rows)
            if current_hash != expected:
                raise ApplyError(
                    409, "SOURCE_CHANGED",
                    f"企业 {b.entity_node_key} 的来源数据已变化，请重新预览",
                )

    # ── 4. 加载规则并检查阻断 ──
    rule_cache: dict[UUID, ConsolNoteMappingRule] = {}
    unmapped_labels: list[str] = []

    for b in confirmed:
        if b.rule_id not in rule_cache:
            rule = (await db.execute(
                sa.select(ConsolNoteMappingRule).where(ConsolNoteMappingRule.id == b.rule_id)
            )).scalar_one_or_none()
            if rule is not None:
                rule_cache[b.rule_id] = rule

        rule = rule_cache.get(b.rule_id)
        if rule is None:
            unmapped_labels.append(f"企业 {b.entity_node_key} 的规则已删除")
            continue
        for m in (rule.mappings if isinstance(rule.mappings, list) else []):
            action = m.get("mapping_action", "")
            if action in ("map", "map_merge"):
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

    # stale 企业不参与但不阻断（R4.3.2）
    stale_node_keys = {b.entity_node_key for b in stale}

    # ── 5. 按规则转换 + 金额汇总 ──
    from app.services.consol_note_detail_source_service import load_entity_source_rows

    # 初始化目标行金额：{target_row_idx: {col_key: Decimal}}
    # 模板 headers 从现有数据或模板取
    width = max(3, len(template_rows[0].get("aliases", [])) + 3) if template_rows else 3

    # 目标金额汇总
    target_amounts: dict[int, dict[int, Decimal]] = {}
    # 穿透 provenance
    provenance: list[dict[str, Any]] = []
    applied_entities: list[str] = []
    skipped_stale: list[str] = list(stale_node_keys)

    for b in confirmed:
        rule = rule_cache.get(b.rule_id)
        if rule is None:
            continue

        source_rows = await load_entity_source_rows(db, b.entity_project_id, section_id, year)
        # 建立来源标签→行的索引
        source_by_label: dict[str, list[dict[str, Any]]] = {}
        for sr in source_rows:
            label = _first_cell(sr).strip()
            source_by_label.setdefault(label, []).append(sr)

        entity_contrib: list[dict[str, Any]] = []

        for m in (rule.mappings if isinstance(rule.mappings, list) else []):
            action = m.get("mapping_action", "")
            source_label = str(m.get("source_label", "")).strip()

            if action == "ignore":
                continue

            target_row_id = str(m.get("target_row_id", ""))
            target_idx = target_row_index.get(target_row_id)
            if target_idx is None:
                continue

            source_hits = source_by_label.get(source_label, [])
            for sr in source_hits:
                amounts = _extract_amounts(sr, width)
                if target_idx not in target_amounts:
                    target_amounts[target_idx] = {}
                for col, val in amounts.items():
                    target_amounts[target_idx][col] = target_amounts[target_idx].get(col, Decimal("0")) + val

                entity_contrib.append({
                    "source_label": source_label,
                    "target_row_id": target_row_id,
                    "target_name": template_rows[target_idx]["canonical_name"] if target_idx < len(template_rows) else "",
                    "amounts": {str(k): str(v) for k, v in amounts.items()},
                })

        applied_entities.append(b.entity_node_key)
        provenance.append({
            "entity_node_key": b.entity_node_key,
            "entity_project_id": str(b.entity_project_id),
            "contributions": entity_contrib,
        })

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
    manual_set = _parse_manual_cells(data)
    locked_set = _parse_locked_cells(note_record)

    protected = manual_set | locked_set

    # ── 7. 构建新行 ──
    # 以模板行为骨架
    existing_rows = data.get("rows", [])
    # 取当前列数
    if existing_rows and isinstance(existing_rows[0], (list, tuple)):
        width = max(width, len(existing_rows[0]))
    elif existing_rows and isinstance(existing_rows[0], dict):
        width = max(width, len(existing_rows[0].get("values", {})) + 1)

    new_rows: list[list[str]] = []
    filled: list[dict[str, Any]] = []
    kept_manual: list[dict[str, Any]] = []

    for i, tr in enumerate(template_rows):
        row = [""] * width
        row[0] = tr.get("canonical_name", "")

        if i in target_amounts:
            for col, val in target_amounts[i].items():
                if col < 1 or col >= width:
                    continue
                if (i, col) in protected:
                    # 保留手工值
                    old_val = _get_existing_cell(existing_rows, i, col)
                    row[col] = old_val
                    kept_manual.append({"row": i, "col": col, "kept_value": old_val})
                else:
                    formatted = str(val.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
                    row[col] = formatted
                    filled.append({"row": i, "col": col, "value": formatted, "target_name": tr.get("canonical_name", "")})

        # 合计行自动求和
        if tr.get("row_type") == "total":
            for col in range(1, width):
                if (i, col) in protected:
                    old_val = _get_existing_cell(existing_rows, i, col)
                    row[col] = old_val
                    continue
                total = Decimal("0")
                for j in range(len(new_rows)):
                    if j < len(template_rows) and template_rows[j].get("row_type") in ("total", "subtotal"):
                        continue
                    try:
                        total += Decimal(str(new_rows[j][col]).replace(",", "")) if new_rows[j][col] else Decimal("0")
                    except Exception:
                        pass
                row[col] = str(total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

        new_rows.append(row)

    # 写入
    headers = data.get("headers", [])
    if not headers and template_rows:
        headers = ["项目"] + [f"列{c}" for c in range(1, width)]

    data["rows"] = new_rows
    data["headers"] = headers
    data["_detail_provenance"] = provenance

    note_record.data = data
    note_record.is_stale = False
    note_record.updated_at = datetime.now(timezone.utc)
    await db.flush()

    return {
        "status": "applied",
        "section_id": section_id,
        "node_key": node_key,
        "applied_entity_count": len(applied_entities),
        "skipped_stale": skipped_stale,
        "filled_count": len(filled),
        "kept_manual_count": len(kept_manual),
        "filled": filled[:50],
        "kept_manual": kept_manual[:50],
        "template_row_count": len(template_rows),
        "output_row_count": len(new_rows),
    }


# ─── 内部辅助 ────────────────────────────────────────────────────────────────


def _first_cell(row: Any) -> str:
    if isinstance(row, dict):
        return str(row.get("label") or row.get("name") or "")
    if isinstance(row, (list, tuple)) and row:
        return str(row[0] or "")
    return ""


def _extract_amounts(row: Any, width: int) -> dict[int, Decimal]:
    """从来源行提取数值列金额。返回 {col_index: Decimal}。"""
    amounts: dict[int, Decimal] = {}
    if isinstance(row, dict):
        vals = row.get("values") or row.get("cells") or {}
        if isinstance(vals, dict):
            for k, v in vals.items():
                try:
                    col = int(k) if str(k).isdigit() else None
                    if col is not None and col >= 1:
                        amounts[col] = Decimal(str(v))
                except (TypeError, ValueError):
                    pass
        elif isinstance(vals, (list, tuple)):
            for j, v in enumerate(vals):
                if j >= 1:
                    try:
                        amounts[j] = Decimal(str(v))
                    except (TypeError, ValueError):
                        pass
    elif isinstance(row, (list, tuple)):
        for j, v in enumerate(row):
            if j >= 1:
                s = str(v or "").strip().replace(",", "").replace("，", "")
                if s:
                    try:
                        amounts[j] = Decimal(s)
                    except Exception:
                        pass
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


def _get_existing_cell(rows: list, row_idx: int, col_idx: int) -> str:
    """从现有行中安全取值。"""
    if row_idx >= len(rows):
        return ""
    row = rows[row_idx]
    if isinstance(row, (list, tuple)):
        return str(row[col_idx]) if col_idx < len(row) else ""
    if isinstance(row, dict):
        vals = row.get("values") or row.get("cells") or {}
        if isinstance(vals, dict):
            return str(vals.get(str(col_idx), vals.get(col_idx, "")))
    return ""


async def _load_or_create_note_data(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    section_id: str,
    node_key: str | None,
) -> ConsolNoteData:
    """加载或创建 consol_note_data 行。"""
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
