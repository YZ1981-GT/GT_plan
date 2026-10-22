"""合并附注值变化通知服务——值指纹计算、事件处理、stale 汇总。

spec: consol-note-mapping-reuse-and-reference-push Phase 4 Task 11~15

Service 只 flush 不 commit（router 层 commit）。
"""
from __future__ import annotations

import hashlib
import json
import logging
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# 1. 值指纹计算（纯函数）
# ═══════════════════════════════════════════════════════════════════════════════


def _to_decimal_str(value: Any) -> str | None:
    """将值转为固定精度（小数点后 2 位）字符串，非数值返回 None。"""
    if value is None or value == "":
        return None
    try:
        d = Decimal(str(value).replace(",", "").strip())
        return str(d.quantize(Decimal("0.01")))
    except (InvalidOperation, ValueError, TypeError):
        return None


def compute_value_fingerprint(
    rows: list[Any],
    headers: list[Any] | None = None,
) -> str:
    """计算值指纹——只含数值列的 SHA-256。

    排除：第一列（标签列）、row_type、key 等结构信息。
    只取数值列的内容，按固定精度（Decimal 小数点后 2 位）序列化。

    设计约束：
    - 同一数据 → 同一 fingerprint
    - 改金额 → fingerprint 变化
    - 改行名不改金额 → fingerprint 不变
    """
    numeric_values: list[list[str | None]] = []

    for row in rows:
        if isinstance(row, dict):
            # dict 格式：{values: {col_key: value}} 或 {cells: [...]}
            vals = row.get("values") or row.get("cells") or {}
            if isinstance(vals, dict):
                # 按 key 排序确保确定性
                row_nums = [_to_decimal_str(vals[k]) for k in sorted(vals.keys())]
            elif isinstance(vals, (list, tuple)):
                # dict 行的 values 不含行名（附注 _tables / 标准来源行同口径）：全部是数值列
                row_nums = [_to_decimal_str(v) for v in vals]
            else:
                row_nums = []
        elif isinstance(row, (list, tuple)):
            # list 格式：[label, val1, val2, ...]
            row_nums = [_to_decimal_str(v) for v in row[1:]]
        else:
            row_nums = []
        numeric_values.append(row_nums)

    payload = json.dumps(numeric_values, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# ═══════════════════════════════════════════════════════════════════════════════
# 2. NOTE_SECTION_SAVED 事件处理器
# ═══════════════════════════════════════════════════════════════════════════════


async def on_note_section_saved(
    db: AsyncSession,
    *,
    entity_project_id: UUID,
    section_id: str,
    year: int,
    rows: list[Any],
    consol_project_ids: list[UUID] | None = None,
) -> dict[str, Any] | None:
    """NOTE_SECTION_SAVED 事件处理逻辑（由 handler 调用）。

    1. 计算新的 value_fingerprint
    2. 查该子企业是否参与某个合并项目的映射绑定
    3. 如果参与且 fingerprint 变化：
       a. 标合并侧 ConsolNoteData.is_stale = True
       b. 返回事件 payload（由调用方发 CONSOL_NOTE_VALUE_CHANGED）
       c. 降级 value_confirmation.status = 'outdated'

    Returns:
        None = 无需通知（无映射绑定或 fingerprint 未变）
        dict = 事件 payload（调用方负责发布）
    """
    from app.models.consol_note_mapping_models import ConsolNoteMappingBinding
    from app.models.consol_note_mapping_template_models import ConsolNoteValueConfirmation

    new_fingerprint = compute_value_fingerprint(rows)

    # 查映射绑定：该子企业是否作为某个合并项目的数据源（section_id 是合并章节号）
    query = sa.select(ConsolNoteMappingBinding).where(
        ConsolNoteMappingBinding.entity_project_id == entity_project_id,
        ConsolNoteMappingBinding.section_id == section_id,
        ConsolNoteMappingBinding.status.in_(["confirmed", "stale"]),
    )
    if consol_project_ids is not None:
        query = query.where(ConsolNoteMappingBinding.project_id.in_(consol_project_ids))
    bindings = (await db.execute(query)).scalars().all()

    if not bindings:
        return None

    # 检查 fingerprint 是否变化——与 bound_source_hash 比较
    # ⚠ bound_source_hash 是结构指纹（行标签+行类型），不是值指纹。
    # 值指纹没有持久化存储位置（设计裁决：不新增列，用 ConsolNoteData.is_stale 做标记）。
    # 因此值变化检测采用"每次保存都通知"策略，由前端横幅去重（横幅已显示时不重复弹）。

    results: list[dict[str, Any]] = []
    for binding in bindings:
        consol_project_id = binding.project_id

        # 标 ConsolNoteData.is_stale = True
        try:
            from app.models.consol_note_data_models import ConsolNoteData
            note_data = (await db.execute(
                sa.select(ConsolNoteData).where(
                    ConsolNoteData.project_id == consol_project_id,
                    ConsolNoteData.year == year,
                    ConsolNoteData.section_id == section_id,
                )
            )).scalars().all()
            for nd in note_data:
                if not nd.is_stale:
                    nd.is_stale = True
        except Exception:
            logger.warning("标记 ConsolNoteData.is_stale 失败", exc_info=True)

        # 降级 value_confirmation
        try:
            confirmations = (await db.execute(
                sa.select(ConsolNoteValueConfirmation).where(
                    ConsolNoteValueConfirmation.project_id == consol_project_id,
                    ConsolNoteValueConfirmation.section_id == section_id,
                    ConsolNoteValueConfirmation.entity_node_key == binding.entity_node_key,
                    ConsolNoteValueConfirmation.status == "confirmed",
                )
            )).scalars().all()
            for c in confirmations:
                if c.confirmed_value_hash != new_fingerprint:
                    c.status = "outdated"
        except Exception:
            logger.warning("降级 value_confirmation 失败", exc_info=True)

        results.append({
            "consol_project_id": str(consol_project_id),
            "section_id": section_id,
            "entity_node_key": binding.entity_node_key,
            "entity_project_id": str(entity_project_id),
            "new_fingerprint": new_fingerprint,
        })

    if results:
        await db.flush()

    return {
        "affected_projects": results,
        "fingerprint": new_fingerprint,
    } if results else None


# ═══════════════════════════════════════════════════════════════════════════════
# 3. stale 汇总
# ═══════════════════════════════════════════════════════════════════════════════


async def get_stale_summary(
    db: AsyncSession,
    *,
    consol_project_id: UUID,
    section_id: str | None = None,
) -> dict[str, Any]:
    """返回 stale 汇总：{sections: {section_id: [stale 企业列表]}}。"""
    try:
        from app.models.consol_note_data_models import ConsolNoteData
    except ImportError:
        return {"sections": {}, "total_stale": 0}

    q = sa.select(ConsolNoteData).where(
        ConsolNoteData.project_id == consol_project_id,
        ConsolNoteData.is_stale == sa.true(),
    )
    if section_id:
        q = q.where(ConsolNoteData.section_id == section_id)

    stale_records = (await db.execute(q)).scalars().all()

    sections: dict[str, list[dict[str, Any]]] = {}
    for r in stale_records:
        sid = r.section_id
        if sid not in sections:
            sections[sid] = []
        sections[sid].append({
            "node_key": getattr(r, "node_key", None),
            "is_stale": True,
            "updated_at": r.updated_at.isoformat() if r.updated_at else None,
        })

    return {
        "project_id": str(consol_project_id),
        "sections": sections,
        "total_stale": sum(len(v) for v in sections.values()),
    }
