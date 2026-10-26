"""GET /api/projects/{pid}/workpapers/prerequisite-status

E1 Sprint 2 Task 2.16: 查询 B/C 类前置底稿状态，驱动编辑器前置横幅（F5.6 + F5.3）。

spec procedure-chain-hardening-and-java-contracts R9 收口：
- 各循环的前置清单集中在 ``prerequisites_for``（与前端 ``usePrerequisiteStatus`` 的回退清单同口径，
  ``tests/test_prerequisite_status_routing.py`` 逐项对拍）。原先只认 E1 / D / F / M，其余循环回空清单
  ⇒ 横幅显示「所有前置底稿已完成」；编辑器又恒按 E1 请求 ⇒ 每张底稿看到的都是货币资金的前置。
- 状态按底稿编制生命周期（``WpFileStatus``）逐值映射：原先只认 completed / reviewed / approved，
  复核通过（review_passed）也算「进行中」⇒ 前置永远完成不了。
- 粗裁为不适用 / 跳过的前置底稿记 ``not_applicable``、不阻断（实质性方案不做控制测试时 C 类底稿被裁掉）。
"""

from __future__ import annotations

import logging
import re
from uuid import UUID

import sqlalchemy as sa
from fastapi import APIRouter, Depends, Query
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_db, require_project_access

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/projects/{project_id}/workpapers",
    tags=["workpaper-prerequisite-status"],
    dependencies=[Depends(require_project_access("readonly"))],  # 项目级读鉴权（Phase 8 Task 8 补）
)


def _p(code: str, name: str) -> dict:
    return {"wp_code": code, "wp_name": name}


# E1 货币资金（requirements F5.3）
_E1_PREREQUISITES = [_p("B23-2", "货币资金控制了解"), _p("C3", "货币资金控制测试结论"), _p("B51-3", "舞弊风险评估")]
# 按循环字母的固定清单（D：D-sales-cycle F8；F：F-F9；G/J/K/L/N：各循环 F5/F9 task；M 无独立前置）
_CYCLE_PREREQUISITES: dict[str, list[dict]] = {
    "D": [_p("B23-1", "了解内部控制"), _p("C2", "控制测试结论"), _p("B51-5", "舞弊风险评估")],
    "F": [_p("B23-3", "采购存货循环业务层面控制"), _p("C4", "采购存货循环控制测试结论"), _p("B51-4", "存货舞弊风险评估")],
    "G": [_p("C5", "投资循环控制测试")],
    "J": [_p("C10", "薪酬循环控制测试")],
    "K": [_p("C11", "管理循环控制测试")],
    "L": [_p("C13", "债务循环业务层面控制测试")],
    "M": [],
    "N": [_p("C12", "税金循环控制测试")],
}
_CODE_RE = re.compile(r"^([A-Z])(\d+)")


def prerequisites_for(wp_code: str | None) -> list[dict]:
    """目标底稿的前置底稿清单（没有前置的循环 / 认不出的编码 ⇒ 空）。"""
    code = (wp_code or "").strip().upper()
    if re.match(r"^E1(?!\d)", code):
        return list(_E1_PREREQUISITES)
    m = _CODE_RE.match(code)
    if not m:
        return []
    cycle, num = m.group(1), int(m.group(2))
    if cycle == "H":  # C6 全部 H 底稿共用；C7 仅在建工程 H2；C14 仅使用权资产 / 租赁负债 H8 / H9
        out = [_p("C6", "固定资产循环控制测试")]
        if num == 2:
            out.append(_p("C7", "在建工程循环控制测试"))
        if num in (8, 9):
            out.append(_p("C14", "租赁循环控制测试"))
        return out
    if cycle == "I":  # C8 全部 I 底稿共用；C9 仅开发支出 I2 / 研发费用 I6
        out = [_p("C8", "无形资产及其他长期资产循环控制测试")]
        if num in (2, 6):
            out.append(_p("C9", "研发循环控制测试"))
        return out
    return list(_CYCLE_PREREQUISITES.get(cycle, []))


#: 编制生命周期 → 前置状态（WpFileStatus 逐值登记，新增枚举值须在此归类；见 test_prerequisite_status_routing）
_FILE_STATUS_STATE = {
    "draft": "in_progress",
    "edit_complete": "in_progress",
    "under_review": "in_progress",
    "revision_required": "in_progress",
    "review_passed": "completed",
    "review_level1_passed": "completed",
    "review_level2_passed": "completed",
    "archived": "completed",
}


def _wp_status_to_state(status) -> str:
    """working_paper.status → 前置状态；没有底稿 ⇒ pending，认不出的值按进行中（不当成已完成）。"""
    if status is None:
        return "pending"
    value = getattr(status, "value", status)
    return _FILE_STATUS_STATE.get(str(value).lower(), "in_progress")


def overall_of(states: list[str]) -> str:
    """有未开始 ⇒ blocked，有进行中 ⇒ partial，其余 ready（全部完成 / 不适用 / 没有前置）。"""
    if "pending" in states:
        return "blocked"
    if "in_progress" in states:
        return "partial"
    return "ready"


async def _load_rows(db: AsyncSession, pid: UUID, codes: list[str]) -> tuple[dict, set[str]]:
    from app.models.procedure_models import ProcedureInstance
    from app.models.workpaper_models import WorkingPaper, WpIndex

    rows = (await db.execute(
        sa.select(WpIndex.wp_code, WorkingPaper.status, WorkingPaper.parsed_data)
        .outerjoin(WorkingPaper, sa.and_(WorkingPaper.wp_index_id == WpIndex.id, WorkingPaper.is_deleted == sa.false()))
        .where(WpIndex.project_id == pid, WpIndex.wp_code.in_(codes), WpIndex.is_deleted == sa.false())
    )).all()
    by_code: dict[str, tuple] = {}
    for code, status, parsed in rows:  # 同编码多行：有底稿的优先
        if code not in by_code or (by_code[code][0] is None and status is not None):
            by_code[code] = (status, parsed)
    trimmed = set((await db.execute(
        sa.select(ProcedureInstance.wp_code).where(
            ProcedureInstance.project_id == pid,
            ProcedureInstance.wp_code.in_(codes),
            ProcedureInstance.is_deleted == sa.false(),
            ProcedureInstance.status.in_(["skip", "not_applicable"]),
        )
    )).scalars().all())
    return by_code, trimmed


@router.get("/prerequisite-status")
async def get_prerequisite_status(
    project_id: str,
    wp_code: str = Query("E1", description="目标底稿 wp_code，决定查哪些前置"),
    db: AsyncSession = Depends(get_db),
):
    """返回前置底稿状态聚合：``{items: [{wp_code, wp_name, state, conclusion, risk_level}], overall, message}``。"""
    pid = UUID(project_id)
    prereq_list = prerequisites_for(wp_code)
    items: list[dict] = []
    if prereq_list:
        codes = [p["wp_code"] for p in prereq_list]
        try:
            by_code, trimmed = await _load_rows(db, pid, codes)
        except SQLAlchemyError as exc:  # 只读聚合：查不到按未开始显示，不让横幅把编辑器拖垮
            logger.warning("查询前置底稿状态失败 pid=%s: %s", pid, exc)
            await db.rollback()
            by_code, trimmed = {}, set()
        for p in prereq_list:
            status, parsed = by_code.get(p["wp_code"], (None, None))
            pd = parsed if isinstance(parsed, dict) else {}
            risk_level = None
            if p["wp_code"] in ("B51-3", "B51-4", "B51-5"):  # 舞弊风险等级
                risk_level = pd.get("risk_level") or pd.get("fraud_risk_level")
            state = "not_applicable" if p["wp_code"] in trimmed else _wp_status_to_state(status)
            items.append({**p, "state": state, "conclusion": pd.get("conclusion"), "risk_level": risk_level})

    overall = overall_of([it["state"] for it in items])
    msg = {"ready": "前置底稿已就绪", "partial": "前置底稿部分完成", "blocked": "前置底稿未完成"}[overall]
    return {"items": items, "overall": overall, "message": msg}
