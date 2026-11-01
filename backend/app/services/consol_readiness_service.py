"""合并 readiness 七域五态（批 5 / ADR-CRW-005 R7）。

状态 = ready / not_ready / unknown / not_applicable / warning，事实与阻断策略分离。
七域 = tree / worksheet / elimination / calc / report / note / lifecycle。

纯函数 ``build_readiness`` 由装载层给事实 dict，不连库；路由层只做项目/年度边界。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

Status = Literal["ready", "not_ready", "unknown", "not_applicable", "warning"]

_ALL_DOMAINS = ("tree", "worksheet", "elimination", "calc", "report", "note", "lifecycle")


@dataclass(frozen=True)
class DomainReadiness:
    domain: str
    status: Status
    label: str
    facts: dict[str, Any] = field(default_factory=dict)
    blockers: list[str] = field(default_factory=list)


def _status(blockers: list[str]) -> Status:
    return "not_ready" if blockers else "ready"


def _tree(facts: dict[str, Any]) -> DomainReadiness:
    blockers: list[str] = []
    if not facts.get("has_tree"):
        blockers.append("未构建企业树")
    elif facts.get("node_count", 0) < 2:
        blockers.append("企业树少于 2 个节点（至少需要一个子公司）")
    return DomainReadiness("tree", _status(blockers), "企业树", dict(facts), blockers)


def _worksheet(facts: dict[str, Any]) -> DomainReadiness:
    blockers: list[str] = []
    if not facts.get("has_worksheet_data"):
        blockers.append("未保存任何合并工作底稿数据")
    return DomainReadiness("worksheet", _status(blockers), "工作底稿", dict(facts), blockers)


def _elimination(facts: dict[str, Any]) -> DomainReadiness:
    blockers: list[str] = []
    approved = int(facts.get("approved_count", 0))
    draft = int(facts.get("draft_count", 0))
    pending = int(facts.get("pending_count", 0))
    if approved == 0 and draft == 0 and pending == 0:
        blockers.append("没有任何抵销分录")
    elif pending > 0:
        blockers.append(f"{pending} 笔分录待审批")
    status = _status(blockers)
    if not blockers and draft > 0:
        status = "warning"
        blockers.append(f"{draft} 笔草稿分录未提交")
    return DomainReadiness("elimination", status, "抵销分录", dict(facts), blockers)


def _calc(facts: dict[str, Any]) -> DomainReadiness:
    blockers: list[str] = []
    if not facts.get("has_trial"):
        blockers.append("未生成合并试算")
    stale = int(facts.get("stale_trial_count", 0))
    if stale:
        blockers.append(f"合并试算有 {stale} 行标记过期")
    return DomainReadiness("calc", _status(blockers), "计算", dict(facts), blockers)


def _report(facts: dict[str, Any]) -> DomainReadiness:
    blockers: list[str] = []
    if not facts.get("has_published_run"):
        blockers.append("没有已发布的正式报表运行")
    elif facts.get("report_run_stale"):
        blockers.append("正式报表运行的输入已过期")
    return DomainReadiness("report", _status(blockers), "报表", dict(facts), blockers)


def _note(facts: dict[str, Any]) -> DomainReadiness:
    blockers: list[str] = []
    total = int(facts.get("total_sections", 0))
    stale = int(facts.get("stale_count", 0))
    pending_mappings = int(facts.get("pending_mappings", 0))
    if total == 0:
        return DomainReadiness("note", "not_applicable", "附注", dict(facts), ["没有合并附注数据"])
    if stale:
        blockers.append(f"{stale} 个章节×节点标记过期")
    if pending_mappings:
        blockers.append(f"{pending_mappings} 个映射未确认或已过期")
    status = _status(blockers)
    source_dist = facts.get("source_mode_distribution") or {}
    if not blockers and source_dist.get("mixed", 0) > 0:
        status = "warning"
        blockers.append(f"{source_dist['mixed']} 个章节来源混合，建议逐格确认")
    return DomainReadiness("note", status, "附注", dict(facts), blockers)


def _lifecycle(facts: dict[str, Any]) -> DomainReadiness:
    blockers: list[str] = []
    if facts.get("is_locked"):
        return DomainReadiness("lifecycle", "ready", "签字锁定", dict(facts), [])
    if facts.get("is_archived"):
        return DomainReadiness("lifecycle", "ready", "已归档", dict(facts), [])
    if not facts.get("has_snapshot"):
        blockers.append("未创建签字快照")
    return DomainReadiness("lifecycle", _status(blockers), "生命周期", dict(facts), blockers)


_BUILDERS = {
    "tree": _tree,
    "worksheet": _worksheet,
    "elimination": _elimination,
    "calc": _calc,
    "report": _report,
    "note": _note,
    "lifecycle": _lifecycle,
}


def build_readiness(facts: dict[str, dict[str, Any]]) -> list[DomainReadiness]:
    """纯函数：七域五态 readiness，从事实 dict 推导。"""
    return [_BUILDERS[domain](facts.get(domain, {})) for domain in _ALL_DOMAINS]


def readiness_payload(domains: list[DomainReadiness]) -> dict[str, Any]:
    blockers = [b for d in domains for b in d.blockers if d.status == "not_ready"]
    overall = "ready" if not blockers else "not_ready"
    return {
        "status": overall,
        "domains": [
            {
                "domain": d.domain,
                "label": d.label,
                "status": d.status,
                "facts": d.facts,
                "blockers": d.blockers,
            }
            for d in domains
        ],
        "blockers": blockers,
    }


# ─────────────────────────────── 装载层（连库） ───────────────────────────────


async def load_readiness_facts(
    db: AsyncSession, project_id: UUID, year: int,
) -> dict[str, dict[str, Any]]:
    """批量读取七域事实；不执行重算，只读当前库状态。"""
    from app.models.consol_note_data_models import ConsolNoteData
    from app.models.consol_worksheet_data_models import ConsolWorksheetData
    from app.models.consolidation_models import ConsolTrial, EliminationEntry, ReviewStatusEnum
    from app.models.report_generation_models import ReportGenerationRun
    from app.services.consol_report_run_service import resolve_published_run
    from app.services.consol_tree_service import build_tree, iter_nodes

    # tree
    tree = await build_tree(db, project_id)
    tree_facts: dict[str, Any] = {"has_tree": tree is not None}
    if tree is not None:
        tree_facts["node_count"] = sum(1 for _ in iter_nodes(tree))
        tree_facts["root_node_key"] = tree.node_key

    # worksheet
    ws_count = (await db.execute(
        sa.select(sa.func.count()).select_from(ConsolWorksheetData).where(
            ConsolWorksheetData.project_id == project_id,
            ConsolWorksheetData.year == year,
        )
    )).scalar_one()
    ws_facts: dict[str, Any] = {"has_worksheet_data": ws_count > 0, "sheet_count": ws_count}

    # elimination
    elim_status_counts: dict[str, int] = {}
    for row in (await db.execute(
        sa.select(EliminationEntry.review_status, sa.func.count()).where(
            EliminationEntry.project_id == project_id,
            EliminationEntry.year == year,
            EliminationEntry.is_deleted == sa.false(),
        ).group_by(EliminationEntry.review_status)
    )).all():
        status_val = str(getattr(row[0], "value", row[0]) or "")
        elim_status_counts[status_val] = int(row[1])
    elim_facts: dict[str, Any] = {
        "approved_count": elim_status_counts.get("approved", 0),
        "draft_count": elim_status_counts.get("draft", 0),
        "pending_count": elim_status_counts.get("pending_review", 0),
        "total_count": sum(elim_status_counts.values()),
    }

    # calc (trial)
    trial_count = (await db.execute(
        sa.select(sa.func.count()).select_from(ConsolTrial).where(
            ConsolTrial.project_id == project_id,
            ConsolTrial.year == year,
            ConsolTrial.is_deleted == sa.false(),
        )
    )).scalar_one()
    stale_trial = (await db.execute(
        sa.select(sa.func.count()).select_from(ConsolTrial).where(
            ConsolTrial.project_id == project_id,
            ConsolTrial.year == year,
            ConsolTrial.is_deleted == sa.false(),
            ConsolTrial.is_stale == sa.true(),
        )
    )).scalar_one()
    calc_facts: dict[str, Any] = {
        "has_trial": trial_count > 0,
        "trial_count": trial_count,
        "stale_trial_count": stale_trial,
    }

    # report
    published_run = await resolve_published_run(db, project_id, year)
    report_facts: dict[str, Any] = {
        "has_published_run": published_run is not None,
    }
    if published_run is not None:
        report_facts["report_run_id"] = str(published_run.id)
        report_facts["report_row_count"] = published_run.row_count
        report_facts["report_run_stale"] = False  # 真正的 stale 判定需要 version vector 重算，这里只读现有 status

    # note
    note_rows = (await db.execute(
        sa.select(
            sa.func.count(),
            sa.func.sum(sa.case((ConsolNoteData.is_stale == sa.true(), 1), else_=0)),
        ).where(
            ConsolNoteData.project_id == project_id,
            ConsolNoteData.year == year,
        )
    )).one()
    source_mode_rows = (await db.execute(
        sa.select(ConsolNoteData.source_mode, sa.func.count()).where(
            ConsolNoteData.project_id == project_id,
            ConsolNoteData.year == year,
            ConsolNoteData.source_mode.is_not(None),
        ).group_by(ConsolNoteData.source_mode)
    )).all()
    source_dist = {str(row[0]): int(row[1]) for row in source_mode_rows}

    # pending mappings：未确认或 stale 的绑定
    try:
        from app.models.consol_note_mapping_models import ConsolNoteMappingBinding

        pending_mappings = (await db.execute(
            sa.select(sa.func.count()).select_from(ConsolNoteMappingBinding).where(
                ConsolNoteMappingBinding.project_id == project_id,
                ConsolNoteMappingBinding.section_id.is_not(None),
                ConsolNoteMappingBinding.status.in_(("pending", "stale")),
            )
        )).scalar_one()
    except Exception:
        pending_mappings = 0

    note_facts: dict[str, Any] = {
        "total_sections": int(note_rows[0] or 0),
        "stale_count": int(note_rows[1] or 0),
        "source_mode_distribution": source_dist,
        "pending_mappings": pending_mappings,
    }

    # lifecycle
    from app.models.core import Project
    from app.models.base import ProjectStatus

    project = await db.get(Project, project_id)
    lifecycle_facts: dict[str, Any] = {
        "is_locked": bool(getattr(project, "consol_lock", False)) if project else False,
        "is_archived": (getattr(project, "status", None) == ProjectStatus.archived) if project else False,
        "has_snapshot": False,  # snapshot v2 尚未实现，先报 False
    }

    return {
        "tree": tree_facts,
        "worksheet": ws_facts,
        "elimination": elim_facts,
        "calc": calc_facts,
        "report": report_facts,
        "note": note_facts,
        "lifecycle": lifecycle_facts,
    }


async def load_consol_readiness(
    db: AsyncSession, project_id: UUID, year: int,
) -> dict[str, Any]:
    facts = await load_readiness_facts(db, project_id, year)
    domains = build_readiness(facts)
    return readiness_payload(domains)


__all__ = [
    "DomainReadiness",
    "Status",
    "build_readiness",
    "load_consol_readiness",
    "load_readiness_facts",
    "readiness_payload",
]
