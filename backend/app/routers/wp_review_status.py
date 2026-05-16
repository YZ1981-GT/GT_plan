"""GET /api/projects/{pid}/workpapers/review-status

聚合 cell_annotations WHERE annotation_type='review_mark' 按 wp_id 分组统计，
返回循环级复核进度。

Foundation Sprint 1 Task 1.4
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_db

router = APIRouter(
    prefix="/api/projects/{project_id}/workpapers",
    tags=["workpaper-review-status"],
)


@router.get("/review-status")
async def get_review_status(
    project_id: str,
    cycle: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """返回循环级复核状态统计。

    Response:
    {
      "cycles": [
        {
          "cycle_code": "D",
          "cycle_name": "收入循环",
          "total_workpapers": 8,
          "reviewed_workpapers": 3,
          "workpapers": [
            { "wp_code": "D2", "wp_name": "应收账款", "is_reviewed": true, "review_count": 5 },
            ...
          ]
        }
      ]
    }
    """
    pid = UUID(project_id)

    # 查询所有底稿及其复核标记统计
    # LEFT JOIN cell_annotations 按 annotation_type='review_mark' 聚合
    query = text("""
        SELECT
            wi.wp_code,
            wi.wp_name,
            w.id as wp_id,
            COUNT(ca.id) FILTER (WHERE ca.annotation_type = 'review_mark') as review_count,
            COUNT(ca.id) FILTER (WHERE ca.annotation_type = 'review_mark' AND ca.status = 'reviewed') as reviewed_count
        FROM working_paper w
        JOIN wp_index wi ON w.wp_index_id = wi.id
        LEFT JOIN cell_annotations ca ON ca.object_id = w.id AND ca.annotation_type = 'review_mark'
        WHERE w.project_id = :pid
          AND w.is_deleted = false
        GROUP BY wi.wp_code, wi.wp_name, w.id
        ORDER BY wi.wp_code
    """)

    result = await db.execute(query, {"pid": str(pid)})
    rows = result.all()

    # 按循环分组（wp_code 首字母为循环编码）
    cycles_map: dict[str, dict] = {}
    for row in rows:
        wp_code = row.wp_code or ""
        cycle_code = wp_code[0] if wp_code else "?"

        if cycle and cycle_code.upper() != cycle.upper():
            continue

        if cycle_code not in cycles_map:
            cycles_map[cycle_code] = {
                "cycle_code": cycle_code,
                "cycle_name": _CYCLE_NAMES.get(cycle_code, f"循环 {cycle_code}"),
                "total_workpapers": 0,
                "reviewed_workpapers": 0,
                "workpapers": [],
            }

        is_reviewed = row.reviewed_count > 0
        cycles_map[cycle_code]["total_workpapers"] += 1
        if is_reviewed:
            cycles_map[cycle_code]["reviewed_workpapers"] += 1

        cycles_map[cycle_code]["workpapers"].append({
            "wp_code": wp_code,
            "wp_name": row.wp_name or "",
            "wp_id": str(row.wp_id),
            "is_reviewed": is_reviewed,
            "review_count": row.review_count or 0,
        })

    return {"cycles": list(cycles_map.values())}


# 循环编码 → 中文名称映射
_CYCLE_NAMES = {
    "A": "完成阶段",
    "B": "计划阶段",
    "C": "控制测试",
    "D": "收入循环",
    "E": "货币资金",
    "F": "存货循环",
    "G": "投资循环",
    "H": "固定资产",
    "I": "无形资产",
    "J": "职工薪酬",
    "K": "管理费用",
    "L": "债务循环",
    "M": "权益循环",
    "N": "税金循环",
    "S": "特定项目",
}
