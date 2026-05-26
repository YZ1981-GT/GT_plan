"""底稿溯源服务

按 design §3.9 / §5.1.7 实现：
- trace_upstream: 反向溯源（哪些上游单元格喂入此对象）
- trace_downstream: 正向影响（哪些下游对象被此对象影响）

数据源（best-effort，缺数据时返回空列表）：
1. cross_wp_references.json — 400 条静态规则（底稿 ↔ 底稿）
2. wp_cross_ref — DB 中实例化的项目级跨底稿引用
3. disclosure_notes.last_sync_wp_id — 附注 ← 底稿同步标记
4. report_line_mapping — 报表行 ← 标准科目映射（间接 → 底稿）

Requirements: 3.11.6（报表附注溯源链路）
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_platform_models import ReportLineMapping
from app.models.report_models import DisclosureNote
from app.models.workpaper_models import WorkingPaper, WpCrossRef, WpIndex

logger = logging.getLogger(__name__)

# cross_wp_references.json 路径（与 cross_ref_service 同源）
_CWR_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "cross_wp_references.json"


@dataclass
class TraceItem:
    """单条溯源记录。

    可表示三种语义：
    - 底稿 cell（wp_code + sheet + cell + value）
    - 报表行（target_type='report' + target_identifier=row_code）
    - 附注章节（target_type='disclosure' + target_identifier=section）
    """
    wp_code: str
    sheet: str | None = None
    cell: str | None = None
    value: Any = None
    label: str | None = None
    target_type: str | None = None
    target_identifier: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TraceResult:
    source: str
    identifier: str
    direction: str
    items: list[TraceItem] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "identifier": self.identifier,
            "direction": self.direction,
            "items": [item.to_dict() for item in self.items],
        }


# ─── Static reference loader ────────────────────────────────────────────────


_STATIC_REFS: list[dict] | None = None


def _load_static_references() -> list[dict]:
    """加载 cross_wp_references.json（懒加载 + 模块级缓存）。"""
    global _STATIC_REFS
    if _STATIC_REFS is not None:
        return _STATIC_REFS
    try:
        data = json.loads(_CWR_PATH.read_text(encoding="utf-8"))
        _STATIC_REFS = data.get("references", []) or []
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        logger.warning("Failed to load cross_wp_references.json: %s", exc)
        _STATIC_REFS = []
    return _STATIC_REFS


# ─── Helpers ────────────────────────────────────────────────────────────────


def _parse_workpaper_identifier(identifier: str) -> tuple[str, str | None, str | None]:
    """解析 workpaper identifier。

    支持格式：
    - "D2"                      → ("D2", None, None)
    - "D2:审定表D2-1"           → ("D2", "审定表D2-1", None)
    - "D2:审定表D2-1:K15"       → ("D2", "审定表D2-1", "K15")
    - "D2!审定表D2-1!K15"       → ("D2", "审定表D2-1", "K15")
    """
    cleaned = identifier.strip()
    if not cleaned:
        return ("", None, None)

    # 优先尝试 ':' 分割
    if ":" in cleaned:
        parts = [p.strip() for p in cleaned.split(":") if p.strip()]
        if len(parts) >= 3:
            return (parts[0], parts[1], parts[2])
        if len(parts) == 2:
            return (parts[0], parts[1], None)
        return (parts[0], None, None)

    # 退而求其次 '!' 分割
    if "!" in cleaned:
        parts = [p.strip() for p in cleaned.split("!") if p.strip()]
        if len(parts) >= 3:
            return (parts[0], parts[1], parts[2])
        if len(parts) == 2:
            return (parts[0], parts[1], None)
        return (parts[0], None, None)

    return (cleaned, None, None)


# ─── Upstream tracing ────────────────────────────────────────────────────────


async def trace_upstream(
    db: AsyncSession,
    project_id: UUID,
    source: str,
    identifier: str,
) -> TraceResult:
    """反向溯源：返回喂入指定对象的上游底稿单元格列表。

    source = 'report':
        identifier = row_code（如 'BS-007'）
        → 通过 ReportLineMapping 找到该行对应的标准科目
        → 通过 cross_wp_references / WpIndex 找到喂入这些科目的底稿
    source = 'disclosure':
        identifier = section（如 '五-1-1'）
        → 通过 DisclosureNote.last_sync_wp_id 找到最近同步源
        → 通过 cross_wp_references targets 反查（target=disclosure section 的 source 底稿）
    source = 'workpaper':
        identifier = wp_code 或 wp_code:sheet:cell
        → 通过 cross_wp_references 找到 targets 包含此 cell 的 source 底稿
        → 通过 wp_cross_ref（DB）查找喂入此 wp 的源
    """
    result = TraceResult(source=source, identifier=identifier, direction="upstream")

    if source == "report":
        await _trace_upstream_report(db, project_id, identifier, result)
    elif source == "disclosure":
        await _trace_upstream_disclosure(db, project_id, identifier, result)
    elif source == "workpaper":
        await _trace_upstream_workpaper(db, project_id, identifier, result)

    return result


async def _trace_upstream_report(
    db: AsyncSession,
    project_id: UUID,
    row_code: str,
    result: TraceResult,
) -> None:
    """报表行 → 喂入它的底稿单元格。

    1. 查 ReportLineMapping 找到该行对应的所有 standard_account_code
    2. 这些科目通常喂入 A1 报表 / TB 试算表 → 但底稿层面，
       通过 cross_wp_references 找到 target_wp_code='A1' 的 source 底稿
    3. 简化实现：返回该项目下所有 active wp_index 中 wp_code 以审定数喂报表的（D/E/F/G/H/I/J/K/L/M/N 主底稿）
    """
    # Step 1: 查映射
    stmt = sa.select(ReportLineMapping).where(
        ReportLineMapping.project_id == project_id,
        ReportLineMapping.report_line_code == row_code,
        ReportLineMapping.is_deleted == False,  # noqa: E712
    )
    mapping_rows = (await db.execute(stmt)).scalars().all()

    if not mapping_rows:
        return

    account_codes = {m.standard_account_code for m in mapping_rows}

    # Step 2: 通过 cross_wp_references 找到 target_wp_code in {A1, A1-*} 的 source 底稿
    static_refs = _load_static_references()
    feeding_wps: set[str] = set()
    for ref in static_refs:
        targets = ref.get("targets", []) or []
        for tgt in targets:
            tgt_code = tgt.get("wp_code", "")
            if tgt_code and (tgt_code == "A1" or tgt_code.startswith("A1-")):
                source_wp = ref.get("source_wp")
                if source_wp:
                    feeding_wps.add(source_wp)
                break

    # Step 3: JOIN wp_index 验证项目下确实存在这些底稿
    if feeding_wps:
        wp_stmt = sa.select(WpIndex).where(
            WpIndex.project_id == project_id,
            WpIndex.wp_code.in_(list(feeding_wps)),
            WpIndex.is_deleted == False,  # noqa: E712
        )
        wp_rows = (await db.execute(wp_stmt)).scalars().all()
        for wp in wp_rows:
            result.items.append(
                TraceItem(
                    wp_code=wp.wp_code,
                    label=f"{wp.wp_name}（喂入 {row_code}）",
                )
            )

    # Step 4: 兜底 — 列出与映射科目同 cycle 的主底稿（best-effort）
    if not result.items and mapping_rows:
        # 对于没有静态规则覆盖的科目，列出 ReportLineMapping 信息本身作为提示
        for m in mapping_rows[:10]:  # 最多 10 条避免噪音
            result.items.append(
                TraceItem(
                    wp_code="(mapping)",
                    label=f"标准科目 {m.standard_account_code} ({m.report_line_name})",
                    target_type="report",
                    target_identifier=row_code,
                )
            )


async def _trace_upstream_disclosure(
    db: AsyncSession,
    project_id: UUID,
    section: str,
    result: TraceResult,
) -> None:
    """附注章节 → 喂入它的底稿。

    1. 查 DisclosureNote.last_sync_wp_id（最近一次同步源）
    2. 通过 cross_wp_references 反查 targets 包含 disclosure section 的 source 底稿
    """
    # Step 1: 查 last_sync_wp_id（最近同步源）
    note_stmt = sa.select(DisclosureNote).where(
        DisclosureNote.project_id == project_id,
        DisclosureNote.note_section == section,
        DisclosureNote.is_deleted == False,  # noqa: E712
    )
    notes = (await db.execute(note_stmt)).scalars().all()

    feeding_wp_ids: set[UUID] = set()
    for note in notes:
        if note.last_sync_wp_id:
            feeding_wp_ids.add(note.last_sync_wp_id)

    # 通过 wp_id JOIN wp_index 拿到 wp_code
    if feeding_wp_ids:
        wp_join_stmt = (
            sa.select(WpIndex.wp_code, WpIndex.wp_name, WorkingPaper.id)
            .join(WorkingPaper, WorkingPaper.wp_index_id == WpIndex.id)
            .where(
                WorkingPaper.id.in_(list(feeding_wp_ids)),
                WpIndex.is_deleted == False,  # noqa: E712
                WorkingPaper.is_deleted == False,  # noqa: E712
            )
        )
        rows = (await db.execute(wp_join_stmt)).all()
        for wp_code, wp_name, _wp_id in rows:
            result.items.append(
                TraceItem(
                    wp_code=wp_code,
                    label=f"{wp_name}（最近同步源）",
                )
            )


async def _trace_upstream_workpaper(
    db: AsyncSession,
    project_id: UUID,
    identifier: str,
    result: TraceResult,
) -> None:
    """底稿 cell → 喂入它的上游底稿单元格。

    1. 解析 identifier → (wp_code, sheet, cell)
    2. 通过 cross_wp_references 找到 targets 包含此 (wp_code, sheet, cell) 的 source 底稿
    """
    wp_code, sheet, cell = _parse_workpaper_identifier(identifier)
    if not wp_code:
        return

    static_refs = _load_static_references()
    seen: set[tuple[str, str, str]] = set()

    for ref in static_refs:
        targets = ref.get("targets", []) or []
        for tgt in targets:
            tgt_code = tgt.get("wp_code", "")
            if tgt_code != wp_code:
                continue
            tgt_sheet = tgt.get("sheet", "")
            tgt_cell = tgt.get("cell", "")

            # 如果指定了 sheet/cell，做精确匹配（缺省时按 wp_code 全匹配）
            if sheet and tgt_sheet and tgt_sheet != sheet:
                continue
            if cell and tgt_cell and tgt_cell != cell:
                continue

            source_wp = ref.get("source_wp", "")
            source_sheet = ref.get("source_sheet", "")
            source_cell = ref.get("source_cell", "")
            if not source_wp:
                continue

            key = (source_wp, source_sheet or "", source_cell or "")
            if key in seen:
                continue
            seen.add(key)

            result.items.append(
                TraceItem(
                    wp_code=source_wp,
                    sheet=source_sheet or None,
                    cell=source_cell or None,
                    label=ref.get("description", "") or ref.get("source_cell_label", ""),
                )
            )

    # 同时叠加项目级 wp_cross_ref（DB 中实例化的引用）
    # 找到 target_wp_code=wp_code 的 wp_cross_ref，反查 source_wp_id → wp_code
    db_stmt = (
        sa.select(WpCrossRef, WpIndex.wp_code)
        .join(WorkingPaper, WorkingPaper.id == WpCrossRef.source_wp_id)
        .join(WpIndex, WpIndex.id == WorkingPaper.wp_index_id)
        .where(
            WpCrossRef.project_id == project_id,
            WpCrossRef.target_wp_code == wp_code,
        )
    )
    rows = (await db.execute(db_stmt)).all()
    for cross_ref, src_wp_code in rows:
        key = (src_wp_code, "", cross_ref.cell_reference or "")
        if key in seen:
            continue
        seen.add(key)
        result.items.append(
            TraceItem(
                wp_code=src_wp_code,
                cell=cross_ref.cell_reference,
                label=f"项目级跨底稿引用",
            )
        )


# ─── Downstream tracing ──────────────────────────────────────────────────────


async def trace_downstream(
    db: AsyncSession,
    project_id: UUID,
    source: str,
    identifier: str,
) -> TraceResult:
    """正向影响：返回引用此对象的下游对象列表。

    source = 'report':
        报表本身是最终输出，无下游 → 返回空
    source = 'disclosure':
        附注本身是最终输出，无下游 → 返回空
    source = 'workpaper':
        identifier = wp_code 或 wp_code:sheet:cell
        → 通过 cross_wp_references 找到 source_wp=identifier 的 targets
        → 通过 disclosure_notes.last_sync_wp_id 找到引用此底稿的附注
        → 通过 wp_cross_ref（DB）查找下游引用
    """
    result = TraceResult(source=source, identifier=identifier, direction="downstream")

    if source == "workpaper":
        await _trace_downstream_workpaper(db, project_id, identifier, result)
    # report/disclosure 是下游终点，无需处理

    return result


async def _trace_downstream_workpaper(
    db: AsyncSession,
    project_id: UUID,
    identifier: str,
    result: TraceResult,
) -> None:
    """底稿 cell → 引用它的下游对象。"""
    wp_code, sheet, cell = _parse_workpaper_identifier(identifier)
    if not wp_code:
        return

    static_refs = _load_static_references()
    seen: set[tuple[str, str, str]] = set()

    # Step 1: 通过 cross_wp_references 找到 source_wp=wp_code 的 targets
    for ref in static_refs:
        if ref.get("source_wp") != wp_code:
            continue
        ref_sheet = ref.get("source_sheet", "")
        ref_cell = ref.get("source_cell", "")

        if sheet and ref_sheet and ref_sheet != sheet:
            continue
        if cell and ref_cell and ref_cell != cell:
            continue

        targets = ref.get("targets", []) or []
        for tgt in targets:
            tgt_code = tgt.get("wp_code", "")
            tgt_sheet = tgt.get("sheet", "")
            tgt_cell = tgt.get("cell", "")
            if not tgt_code:
                continue

            key = (tgt_code, tgt_sheet or "", tgt_cell or "")
            if key in seen:
                continue
            seen.add(key)

            # 检查 target 是 report/disclosure/workpaper
            if tgt_code in ("A1",) or tgt_code.startswith("A1-"):
                result.items.append(
                    TraceItem(
                        wp_code=tgt_code,
                        sheet=tgt_sheet or None,
                        cell=tgt_cell or None,
                        label=ref.get("description", ""),
                        target_type="report",
                        target_identifier=tgt_cell,
                    )
                )
            elif tgt_code.startswith("Note") or tgt_code.startswith("附注"):
                result.items.append(
                    TraceItem(
                        wp_code=tgt_code,
                        label=ref.get("description", ""),
                        target_type="disclosure",
                        target_identifier=tgt_sheet or tgt_cell,
                    )
                )
            else:
                result.items.append(
                    TraceItem(
                        wp_code=tgt_code,
                        sheet=tgt_sheet or None,
                        cell=tgt_cell or None,
                        label=ref.get("description", ""),
                    )
                )

    # Step 2: 通过 disclosure_notes.last_sync_wp_id 找引用此底稿的附注
    note_stmt = (
        sa.select(DisclosureNote.note_section, DisclosureNote.section_title)
        .join(WorkingPaper, WorkingPaper.id == DisclosureNote.last_sync_wp_id)
        .join(WpIndex, WpIndex.id == WorkingPaper.wp_index_id)
        .where(
            DisclosureNote.project_id == project_id,
            DisclosureNote.is_deleted == False,  # noqa: E712
            WpIndex.wp_code == wp_code,
            WpIndex.is_deleted == False,  # noqa: E712
        )
    )
    rows = (await db.execute(note_stmt)).all()
    for section, title in rows:
        result.items.append(
            TraceItem(
                wp_code=wp_code,
                target_type="disclosure",
                target_identifier=section,
                label=title or section,
            )
        )

    # Step 3: 通过 wp_cross_ref（DB）查找项目级实例化的下游
    # 查找 source_wp=当前 wp 的 cross_ref → target_wp_code
    db_stmt = (
        sa.select(WpCrossRef.target_wp_code, WpCrossRef.cell_reference)
        .join(WorkingPaper, WorkingPaper.id == WpCrossRef.source_wp_id)
        .join(WpIndex, WpIndex.id == WorkingPaper.wp_index_id)
        .where(
            WpCrossRef.project_id == project_id,
            WpIndex.wp_code == wp_code,
        )
    )
    rows = (await db.execute(db_stmt)).all()
    for target_code, cell_ref in rows:
        key = (target_code, "", cell_ref or "")
        if key in seen:
            continue
        seen.add(key)
        result.items.append(
            TraceItem(
                wp_code=target_code,
                cell=cell_ref,
                label="项目级跨底稿引用",
            )
        )
