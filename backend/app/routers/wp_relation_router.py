"""底稿关系/索引 API 路由（从 working_paper.py 拆出，零行为变更）

关系域端点（与 working_paper 主 router 共用 `/api/projects/{project_id}` 前缀）：
- GET    /wp-index                               — 底稿索引列表
- GET    /wp-cross-refs                          — 交叉索引关系
- GET    /working-papers/{wp_id}/cross-links      — 底稿间穿透链接
- GET    /working-papers/{wp_id}/relation-graph    — 底稿关系图数据
- POST   /working-papers/{wp_id}/sync-procedure    — 底稿状态与审计程序联动
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
import sqlalchemy as sa

from app.core.database import get_db
from app.deps import require_project_access, check_consol_lock
from app.models.core import User
from app.models.workpaper_models import WpIndex, WpCrossRef, WorkingPaper

router = APIRouter(
    prefix="/api/projects/{project_id}",
    tags=["working-papers"],
)


# ---------------------------------------------------------------------------
# WP Index & Cross-ref endpoints
# ---------------------------------------------------------------------------

@router.get("/wp-index")
async def list_wp_index(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """底稿索引列表（需项目成员权限）"""
    result = await db.execute(
        sa.select(WpIndex)
        .where(WpIndex.project_id == project_id, WpIndex.is_deleted == sa.false())
        .order_by(WpIndex.wp_code)
    )
    items = result.scalars().all()
    return [
        {
            "id": str(i.id),
            "wp_code": i.wp_code,
            "wp_name": i.wp_name,
            "audit_cycle": i.audit_cycle,
            "status": i.status.value if i.status else None,
            "assigned_to": str(i.assigned_to) if i.assigned_to else None,
            "reviewer": str(i.reviewer) if i.reviewer else None,
        }
        for i in items
    ]


@router.get("/wp-cross-refs")
async def list_wp_cross_refs(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """交叉索引关系（需项目成员权限）"""
    result = await db.execute(
        sa.select(WpCrossRef)
        .where(WpCrossRef.project_id == project_id)
        .order_by(WpCrossRef.created_at)
    )
    items = result.scalars().all()
    return [
        {
            "id": str(i.id),
            "source_wp_id": str(i.source_wp_id),
            "target_wp_code": i.target_wp_code,
            "cell_reference": i.cell_reference,
        }
        for i in items
    ]


@router.get("/working-papers/{wp_id}/cross-links")
async def get_cross_links(
    project_id: UUID,
    wp_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """获取底稿间可点击的穿透链接

    返回当前底稿引用的其他底稿列表（含跳转URL）。
    基于 wp_account_mapping.json 的同循环关联 + 交叉索引。
    """
    from app.services.wp_data_rules import get_mapping_for_wp, _load_mapping

    # 获取当前底稿信息
    result = await db.execute(
        sa.select(WpIndex).where(WpIndex.id == (
            sa.select(WorkingPaper.wp_index_id).where(WorkingPaper.id == wp_id).scalar_subquery()
        ))
    )
    idx = result.scalar_one_or_none()
    if not idx:
        return {"links": []}

    wp_code = idx.wp_code
    cycle = idx.audit_cycle

    # 同循环的其他底稿
    mappings = _load_mapping()
    same_cycle = [m for m in mappings if m.get("cycle") == cycle and m.get("wp_code") != wp_code]

    links = []
    for m in same_cycle:
        # 查找该底稿是否存在
        target_result = await db.execute(
            sa.select(WpIndex.id, WorkingPaper.id).outerjoin(
                WorkingPaper, WorkingPaper.wp_index_id == WpIndex.id
            ).where(
                WpIndex.project_id == project_id,
                WpIndex.wp_code == m["wp_code"],
                WpIndex.is_deleted == sa.false(),
            ).limit(1)
        )
        target = target_result.first()
        links.append({
            "wp_code": m["wp_code"],
            "wp_name": m.get("wp_name", ""),
            "exists": target is not None,
            "wp_id": str(target[1]) if target and target[1] else None,
            "jump_url": f"/projects/{project_id}/workpapers?code={m['wp_code']}",
            "relation": "同循环关联",
        })

    # 审定表 ↔ 附注链接
    mapping = get_mapping_for_wp(wp_code)
    if mapping and mapping.get("note_section"):
        links.append({
            "wp_code": f"附注{mapping['note_section']}",
            "wp_name": f"附注 {mapping['note_section']} {mapping.get('account_name', '')}",
            "exists": True,
            "jump_url": f"/projects/{project_id}/disclosure-notes?section={mapping['note_section']}",
            "relation": "对应附注",
        })

    # 审定表 ↔ 报表行次链接
    if mapping and mapping.get("report_row"):
        links.append({
            "wp_code": mapping["report_row"],
            "wp_name": f"报表行次 {mapping['report_row']}",
            "exists": True,
            "jump_url": f"/projects/{project_id}/reports?row={mapping['report_row']}",
            "relation": "对应报表",
        })

    return {"wp_code": wp_code, "links": links, "count": len(links)}


@router.get("/working-papers/{wp_id}/relation-graph")
async def get_wp_relation_graph(
    project_id: UUID,
    wp_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """获取底稿关系图数据（基于 cross_wp_references.json）

    返回当前底稿的上游（被引用）和下游（引用其他）关系，
    用于 WorkpaperAuditNav 的关系图 SVG 渲染。
    """
    import json
    from pathlib import Path

    # 1. 获取当前底稿编号
    result = await db.execute(
        sa.select(WpIndex)
        .join(WorkingPaper, WorkingPaper.wp_index_id == WpIndex.id)
        .where(WorkingPaper.id == wp_id, WorkingPaper.is_deleted == sa.false())
    )
    idx = result.scalar_one_or_none()
    if not idx:
        return {"wp_code": "", "current": None, "upstream": [], "downstream": []}

    wp_code = idx.wp_code
    # 当前底稿 cycle 前缀（如 D2 → D, E1A → E, H1-13 → H）
    cycle_prefix = wp_code[0] if wp_code else ""

    # 2. 加载 cross_wp_references.json
    cwr_path = Path(__file__).resolve().parents[2] / "data" / "cross_wp_references.json"
    if not cwr_path.exists():
        return {"wp_code": wp_code, "current": {"code": wp_code, "name": idx.wp_name}, "upstream": [], "downstream": []}

    try:
        cwr_data = json.loads(cwr_path.read_text(encoding="utf-8"))
        all_refs = cwr_data.get("references", [])
    except Exception:
        return {"wp_code": wp_code, "current": {"code": wp_code, "name": idx.wp_name}, "upstream": [], "downstream": []}

    # 3. 找上游（其他底稿是 source，本底稿是 target）
    # 4. 找下游（本底稿是 source，其他底稿是 target）
    # 匹配规则：wp_code 完全匹配，或 wp_code 是子表（如 D2 匹配 D2-1, D2-12）
    def _matches(ref_code: str, my_code: str) -> bool:
        if not ref_code or not my_code:
            return False
        return ref_code == my_code or ref_code.startswith(my_code + "-") or my_code.startswith(ref_code + "-")

    upstream: dict[str, dict] = {}  # wp_code → {code, description}
    downstream: dict[str, dict] = {}

    for ref in all_refs:
        src = ref.get("source_wp", "")
        targets = ref.get("targets", [])
        target_codes = [t.get("wp_code", "") for t in targets if t.get("wp_code")]
        desc = ref.get("description", "")
        severity = ref.get("severity", "info")

        # 本底稿出现在 targets 中 → src 是上游
        if any(_matches(tc, wp_code) for tc in target_codes) and src and src != wp_code:
            if src not in upstream:
                upstream[src] = {"code": src, "description": desc, "severity": severity}

        # 本底稿是 source → targets 是下游
        if _matches(src, wp_code):
            for tc in target_codes:
                if tc and tc != wp_code and tc not in downstream:
                    downstream[tc] = {"code": tc, "description": desc, "severity": severity}

    # 5. 查询数据库获取这些 wp_code 是否在项目中存在 + 取名称
    all_codes = list(set(list(upstream.keys()) + list(downstream.keys())))
    if all_codes:
        idx_result = await db.execute(
            sa.select(WpIndex.wp_code, WpIndex.wp_name).where(
                WpIndex.project_id == project_id,
                WpIndex.wp_code.in_(all_codes),
                WpIndex.is_deleted == sa.false(),
            )
        )
        existing = {row[0]: row[1] for row in idx_result.all()}
        for code, info in upstream.items():
            info["name"] = existing.get(code, "")
            info["exists"] = code in existing
        for code, info in downstream.items():
            info["name"] = existing.get(code, "")
            info["exists"] = code in existing

    return {
        "wp_code": wp_code,
        "current": {"code": wp_code, "name": idx.wp_name, "cycle": cycle_prefix},
        "upstream": sorted(upstream.values(), key=lambda x: x["code"]),
        "downstream": sorted(downstream.values(), key=lambda x: x["code"]),
    }


@router.post("/working-papers/{wp_id}/sync-procedure")
async def sync_procedure_status(
    project_id: UUID,
    wp_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("edit")),
    _lock_check=Depends(check_consol_lock),
):
    """底稿状态与审计程序联动

    底稿提交复核时 → 对应程序实例标记为 completed
    底稿退回时 → 对应程序实例标记为 in_progress
    """
    from app.models.procedure_models import ProcedureInstance

    # 获取底稿编号
    result = await db.execute(
        sa.select(WorkingPaper, WpIndex)
        .join(WpIndex, WorkingPaper.wp_index_id == WpIndex.id)
        .where(WorkingPaper.id == wp_id, WorkingPaper.is_deleted == sa.false())
    )
    row = result.first()
    if not row:
        raise HTTPException(status_code=404, detail="底稿不存在")

    wp, idx = row
    wp_code = idx.wp_code
    wp_status = wp.status.value if wp.status else "draft"

    # 映射底稿状态到程序执行状态
    if wp_status in ("under_review", "review_passed", "archived"):
        exec_status = "completed"
    elif wp_status in ("revision_required",):
        exec_status = "in_progress"
    elif wp_status in ("draft", "edit_complete"):
        exec_status = "in_progress"
    else:
        exec_status = "not_started"

    # 更新对应的程序实例
    updated = await db.execute(
        sa.update(ProcedureInstance).where(
            ProcedureInstance.project_id == project_id,
            ProcedureInstance.wp_code == wp_code,
            ProcedureInstance.is_deleted == sa.false(),
        ).values(execution_status=exec_status)
    )

    await db.flush()
    await db.commit()
    return {
        "wp_code": wp_code,
        "wp_status": wp_status,
        "procedure_status": exec_status,
        "updated": updated.rowcount,
    }
