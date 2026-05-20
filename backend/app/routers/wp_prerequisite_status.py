"""GET /api/projects/{pid}/workpapers/prerequisite-status

E1 Sprint 2 Task 2.16: 查询 B/C 类前置底稿状态，驱动 E1 编辑器前置横幅
（F5.6 + F5.3 共 5 个前置底稿）。

锚定 requirements:
- F5.3 B/C 类前置底稿联动（5 个: B23-2 / B23-2-2 / B51-3 / C3 / C3-2）
- F5.6 前置状态横幅（3 状态: ready/partial/blocked）

实现：按 wp_code 查 working_paper.status + parsed_data.conclusion，
按规则映射为 PrerequisiteState（completed/in_progress/pending）。
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_db

router = APIRouter(
    prefix="/api/projects/{project_id}/workpapers",
    tags=["workpaper-prerequisite-status"],
)


# E1 的前置底稿清单（按 requirements F5.3）
_E1_PREREQUISITES = [
    {"wp_code": "B23-2", "wp_name": "货币资金控制了解"},
    {"wp_code": "C3", "wp_name": "货币资金控制测试结论"},
    {"wp_code": "B51-3", "wp_name": "舞弊风险评估"},
]

# D 循环前置底稿清单（按 D-sales-cycle spec F8 requirements）
# B23-1 了解内部控制 / C2 控制测试结论 / B51-5 舞弊风险评估
D_CYCLE_PREREQUISITES = [
    {"wp_code": "B23-1", "label": "了解内部控制", "required": True},
    {"wp_code": "C2", "label": "控制测试结论", "required": True},
    {"wp_code": "B51-5", "label": "舞弊风险评估", "required": False},  # 非必须但影响 IPO 触发
]

# F 循环前置底稿清单（按 workpaper-f-purchase-inventory spec F-F9 requirements）
# B23-3 采购存货循环业务层面控制 / C4 采购存货循环控制测试 / B51-4 存货舞弊风险评估
F_CYCLE_PREREQUISITES = [
    {"wp_code": "B23-3", "label": "采购存货循环业务层面控制", "required": True},
    {"wp_code": "C4", "label": "采购存货循环控制测试结论", "required": True},
    {"wp_code": "B51-4", "label": "存货舞弊风险评估", "required": False},  # 非必须但影响 IPO 触发
]


def _wp_status_to_state(status: str | None, conclusion: str | None) -> str:
    """working_paper.status + parsed_data.conclusion → PrerequisiteState

    映射规则：
    - status='completed'/'reviewed'/'approved' 且 conclusion 非空 → completed
    - status='in_progress'/'draft' 或 conclusion 部分填 → in_progress
    - status='not_started' 或没有底稿记录 → pending
    """
    if not status:
        return "pending"
    s = (status or "").lower()
    if s in ("completed", "reviewed", "approved", "archived"):
        return "completed"
    if s in ("draft", "in_progress", "pending_review"):
        return "in_progress" if conclusion else "in_progress"
    if s in ("not_started", "queued"):
        return "pending"
    return "in_progress"


@router.get("/prerequisite-status")
async def get_prerequisite_status(
    project_id: str,
    wp_code: str = Query("E1", description="目标底稿 wp_code，决定查哪些前置"),
    db: AsyncSession = Depends(get_db),
):
    """返回前置底稿状态聚合。

    Response:
    {
      "items": [
        { "wp_code": "B23-2", "wp_name": "...", "state": "completed", "conclusion": "..." },
        ...
      ],
      "overall": "ready" | "partial" | "blocked",
      "message": "..."
    }
    """
    pid = UUID(project_id)

    # 按 wp_code 路由到对应前置清单
    if wp_code == "E1":
        prereq_list = _E1_PREREQUISITES
    elif wp_code.upper().startswith("D") and wp_code[1:2].isdigit():
        # D 循环（D0~D7 及子表 D2-1, D4-22A 等）
        prereq_list = [
            {"wp_code": p["wp_code"], "wp_name": p["label"]}
            for p in D_CYCLE_PREREQUISITES
        ]
    elif wp_code.upper().startswith("F") and wp_code[1:2].isdigit():
        # F 循环（F0~F5 及子表 F2-1, F2-21 等）
        prereq_list = [
            {"wp_code": p["wp_code"], "wp_name": p["label"]}
            for p in F_CYCLE_PREREQUISITES
        ]
    elif wp_code.upper().startswith("M") and wp_code[1:2].isdigit():
        # M 权益循环（M1~M10 及子表 M2-2, M6-2 等）
        # M 循环无独立 C 类前置底稿（由 A 类总体审计策略覆盖），直接返回 ready
        prereq_list = []
    else:
        prereq_list = []

    items: list[dict] = []
    if prereq_list:
        codes = [p["wp_code"] for p in prereq_list]
        try:
            query = text("""
                SELECT wi.wp_code, wi.wp_name, w.status, w.parsed_data
                FROM wp_index wi
                LEFT JOIN working_paper w
                  ON w.wp_index_id = wi.id AND w.is_deleted = false
                WHERE wi.project_id = :pid
                  AND wi.wp_code = ANY(:codes)
            """)
            result = await db.execute(query, {"pid": str(pid), "codes": codes})
            rows = result.mappings().all()
            row_map = {r["wp_code"]: r for r in rows}
        except Exception:
            try:
                await db.rollback()
            except Exception:
                pass
            row_map = {}

        for p in prereq_list:
            row = row_map.get(p["wp_code"])
            conclusion = None
            risk_level = None
            status_val = None
            if row is not None:
                status_val = row.get("status")
                pd = row.get("parsed_data") or {}
                conclusion = pd.get("conclusion") if isinstance(pd, dict) else None
                # B51-3 / B51-4 / B51-5 舞弊风险等级
                if p["wp_code"] in ("B51-3", "B51-4", "B51-5") and isinstance(pd, dict):
                    risk_level = pd.get("risk_level") or pd.get("fraud_risk_level")

            state = _wp_status_to_state(status_val, conclusion)
            items.append({
                "wp_code": p["wp_code"],
                "wp_name": p["wp_name"],
                "state": state,
                "conclusion": conclusion,
                "risk_level": risk_level,
            })

    # 聚合 overall
    states = {it["state"] for it in items}
    if not items or "pending" in states:
        overall = "blocked" if "pending" in states else "ready"
    elif "in_progress" in states:
        overall = "partial"
    else:
        overall = "ready"

    msg = {
        "ready": "前置底稿已就绪",
        "partial": "前置底稿部分完成",
        "blocked": "前置底稿未完成",
    }.get(overall, "")

    return {
        "items": items,
        "overall": overall,
        "message": msg,
    }
