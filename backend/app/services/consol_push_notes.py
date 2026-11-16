"""合并推送 · 附注步骤（spec ``consol-status-semantics-closure`` 任务 1 从 ``consol_push_service`` 迁出）。

本模块承接推送四步里第④步「标记合并附注待更新 + 刷新附注公式」：

- ``_mark_notes_stale``：推送开始时批量置全部行待更新；
- ``_refresh_notes``：标记 stale → 按节点逐章节 ``fill_note_sections`` 刷新 → 返回分口径统计。

迁出原因：``consol_push_service.py`` 895 行已超行数门（800），且后续任务（skip_reason、
待更新原因）都落在本步骤上。原文件保留同名导入（``from app.services.consol_push_notes
import _mark_notes_stale, _refresh_notes``），既有测试按 ``consol_push_service._refresh_notes``
打补丁的写法照常生效（``_push_one`` / ``refresh_notes_exclusive`` 经原模块全局名调用）。

本任务为纯迁移：函数体与 HEAD 逐字节一致，不改行为。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    from app.schemas.consol_context import ConsolContext
    from app.services.consol_calc_basis import CalcBasis
    from app.services.consol_tree_service import TreeNode

logger = logging.getLogger(__name__)


async def _mark_notes_stale(db: AsyncSession, project_id: UUID, year: int) -> int:
    from app.models.consol_note_data_models import ConsolNoteData
    from app.services.consol_note_stale_state import ConsolNoteStaleSource, stale_values

    result = await db.execute(
        sa.update(ConsolNoteData)
        .where(ConsolNoteData.project_id == project_id, ConsolNoteData.year == year)
        .values(**stale_values(ConsolNoteStaleSource.CONSOL_PUSH))
    )
    return int(result.rowcount or 0)


async def _refresh_notes(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    *,
    context: "ConsolContext | None" = None,
    tree: "TreeNode | None" = None,
    basis: "CalcBasis | None" = None,
) -> dict:
    """标记 stale → 真正刷新附注 → 返回分口径统计。

    先标记所有 ``consol_note_data`` 行 stale，再按节点逐章节调用
    ``fill_note_sections`` 执行公式刷新并清除 ``is_stale``。
    返回值区分 section / node_instance / refreshed / failed / skipped 五种计数。
    """
    from app.models.consol_note_data_models import ConsolNoteData
    from app.services.consol_note_formula_service import (
        consol_note_tables,
        fill_note_sections,
        resolve_note_template_type,
    )
    from app.services.consol_tree_service import build_tree, iter_nodes
    from app.services.consol_calc_basis import validate_calc_basis

    resolved_tree = tree if tree is not None else (basis.tree if basis is not None else None)
    if basis is not None:
        # 注入口径的身份错误必须在写 stale 标记前失败，不能先污染目标项目。
        validate_calc_basis(basis, project_id, year, tree=resolved_tree)

    # ── 1. 标记 stale ──
    stale_count = await _mark_notes_stale(db, project_id, year)
    await db.commit()

    stats: dict = {
        "stale_marked": stale_count,
        "distinct_section_count": 0,
        "node_count": 0,
        "refreshed_count": 0,
        "failed_count": 0,
        "skipped_count": 0,
        "skip_reason": None,
        "note_status": "skipped",  # 附注子状态：persisted / partial / failed / skipped
    }

    # ── 2. 解析模板与章节 ──
    try:
        template_type = await resolve_note_template_type(db, project_id)
    except Exception:
        # 无法解析模板（项目无 consolidation_type 等）⇒ 只标 stale 不刷新
        stats["skip_reason"] = "no_template_type"
        logger.warning("合并推送附注刷新跳过：无法解析项目模板类型，project=%s", project_id)
        return stats

    tables = [t for t in consol_note_tables(template_type) if t.get("enabled", True) is not False]
    section_ids = list(dict.fromkeys(
        str(t.get("section_id")) for t in tables if t.get("section_id")
    ))
    stats["distinct_section_count"] = len(section_ids)
    if not section_ids:
        stats["skip_reason"] = "no_sections"
        return stats

    # ── 3. 构建企业树 ──
    if resolved_tree is None:
        resolved_tree = await build_tree(db, project_id)
    if resolved_tree is None:
        stats["skip_reason"] = "no_tree"
        logger.info("合并推送附注刷新跳过：无企业树，project=%s", project_id)
        return stats

    # ── 4. 构建合并计算上下文 ──
    view_ctx = None
    resolved_context = context
    try:
        if resolved_context is None:
            from app.services.consol_context_service import build_consol_context
            resolved_context = await build_consol_context(db, project_id, year, tree=resolved_tree)
        from app.services.consol_report_view_service import load_view_context
        view_ctx = await load_view_context(
            db,
            project_id,
            year,
            context=resolved_context,
            tree=resolved_tree,
            basis=basis,
        )
    except Exception as exc:
        stats["skip_reason"] = "context_failed"
        logger.warning("合并推送附注刷新上下文构建失败（降级只标 stale）：%s", exc)
        return stats

    # ── 5. 遍历节点逐章刷新 ──
    seen: set[str] = set()
    nodes = []
    for node in iter_nodes(resolved_tree):
        nk = str(getattr(node, "node_key", "") or "").strip()
        if nk and nk not in seen:
            seen.add(nk)
            nodes.append(node)
    stats["node_count"] = len(nodes)

    total_persisted = 0
    total_kept = 0
    total_failed = 0
    total_skipped = 0

    for node in nodes:
        node_key = str(node.node_key)
        try:
            # 从单体附注拉来的节点数据（明细映射 / 子树汇总）不按公式覆盖，只在公式值变化时标待更新
            result = await fill_note_sections(
                db, project_id, year, section_ids,
                node_key=node_key,
                template_type=template_type,
                context=resolved_context,
                tree=resolved_tree,
                view_context=view_ctx,
                preserve_pulled=True,
            )
            if result.get("results"):
                await db.commit()
            result_rows = result.get("results") or []
            persisted = sum(1 for item in result_rows if item.get("status") == "persisted")
            kept = sum(1 for item in result_rows if item.get("status") == "kept_pulled")
            skipped = sum(1 for item in result_rows if item.get("status") not in {"persisted", "kept_pulled"})
            failed = len(result.get("failures") or [])
            total_persisted += persisted
            total_kept += kept
            total_failed += failed
            total_skipped += skipped
        except Exception as exc:
            await db.rollback()
            logger.warning("合并推送附注刷新节点 %s 失败：%s", node_key, exc)
            total_failed += len(section_ids)

    stats["refreshed_count"] = total_persisted
    stats["kept_pulled_count"] = total_kept
    stats["failed_count"] = total_failed
    stats["skipped_count"] = total_skipped

    if total_failed and (total_persisted or total_kept):
        stats["note_status"] = "partial"
    elif total_failed:
        stats["note_status"] = "failed"
    elif total_persisted or total_kept:
        stats["note_status"] = "persisted"
    else:
        stats["note_status"] = "skipped"

    return stats


_SKIP_REASON_LABELS = {
    "no_template_type": "无法确定附注模板类型",
    "no_sections": "模板没有启用的章节",
    "no_tree": "没有可用的企业树",
    "context_failed": "合并计算上下文构建失败",
}


def _note_stats_detail(stats: dict) -> str:
    """把附注步骤统计格式化为推送与级联刷新共用的中文回执。"""
    parts: list[str] = []
    stale = int(stats.get("stale_marked") or 0)
    sections = int(stats.get("distinct_section_count") or 0)
    nodes = int(stats.get("node_count") or 0)
    refreshed = int(stats.get("refreshed_count") or 0)
    kept = int(stats.get("kept_pulled_count") or 0)
    failed = int(stats.get("failed_count") or 0)
    if stale:
        parts.append(f"标记 {stale} 行待更新")
    parts.append(f"{sections} 个章节 × {nodes} 个节点")
    parts.append(f"刷新 {refreshed}")
    if kept:
        parts.append(f"保留单体附注拉数 {kept}（待重新汇总）")
    if failed:
        parts.append(f"失败 {failed}")
    reason = stats.get("skip_reason")
    if reason:
        parts.append(f"附注刷新原因：{_SKIP_REASON_LABELS.get(str(reason), '未知原因')}")
    parts.append(f"附注状态={stats.get('note_status', 'skipped')}")
    return "，".join(parts)


def note_step_verdict(stats: dict) -> tuple[str, str]:
    """把附注统计映射成推送/级联刷新步骤状态与回执。

    ``context_failed`` 是真实失败；模板、章节、企业树缺失属于明确跳过。
    只有 ``persisted`` 映射为成功，避免把步骤内部的 ``skipped`` 再伪装成成功。
    """
    note_status = str(stats.get("note_status") or "skipped")
    detail = _note_stats_detail(stats)
    if note_status == "persisted":
        return "succeeded", detail
    if note_status in {"partial", "failed"}:
        return note_status, detail
    if note_status == "skipped":
        reason = str(stats.get("skip_reason") or "")
        if reason == "context_failed":
            return "failed", detail
        return "skipped", detail
    return "failed", f"{detail}，附注状态未知，已按失败处理"


__all__ = ["_mark_notes_stale", "_refresh_notes", "note_step_verdict"]
