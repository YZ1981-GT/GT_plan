"""合并 readiness 七域五态 + 角色视图（批 5 / ADR-CRW-005 R7、批 6.4 / ADR-CRW-006 R8）。

状态 = ready / not_ready / unknown / not_applicable / warning，事实与阻断策略分离。
七域 = tree / worksheet / elimination / calc / report / note / lifecycle。

批 6.4 在装载层接入两处既有真源（不重建）：
- 证据充分性：合并薄底稿壳 ``A3-CONSOL`` 的 ``working_paper_id`` 经
  :class:`app.services.evidence_readiness.EvidenceReadinessService` 评估，四态
  （ready / not_ready / not_declared / unknown）直接折进 ``worksheet`` 域事实，
  与附件 owner / QC / 签发 / 归档共用同一事实来源。
- 复核状态：壳的 ``review_status / status / assigned_to / reviewer``（批 6.2 状态机）折进
  ``lifecycle`` 域事实。

角色视图（``build_role_views``）是纯函数：把七域 readiness + 证据 + 复核事实投影成四个审计角色
待办桶——编制（preparer，edit 级）、审批（approval，edit 级）、重大判断（significant judgment，
edit 级）、质控（qc，review 级）。角色→级别经 :data:`app.services.assignment_service.ROLE_MAP`
（partner/manager/auditor/assistant = edit，qc/eqcr = review），不另写级别字面量副本。
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
    # 证据充分性来自壳底稿的统一四态（evidence_readiness），只映射不重算（ADR-CRW-006 R8.3）。
    ev_status = facts.get("evidence_status")
    if ev_status == "not_ready":
        missing = facts.get("evidence_missing_types") or []
        detail = ("：缺 " + "、".join(str(m) for m in missing)) if missing else ""
        blockers.append(f"合并底稿证据不充分{detail}")
    elif ev_status == "unknown":
        blockers.append("合并底稿证据状态暂时无法判断")
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
    # 复核状态来自壳状态机（批 6.2）：退回修改是阻断，待复核是 warning，复核通过前不算就绪。
    review_status = facts.get("review_status")
    if review_status == "level1_rejected":
        blockers.append("合并底稿复核被退回，需修改后重新提交")
    if not facts.get("has_snapshot"):
        blockers.append("未创建签字快照")
    status = _status(blockers)
    if not blockers and review_status in ("not_submitted", "pending_level1", "level1_in_progress"):
        status = "warning"
        label = {
            "not_submitted": "合并底稿尚未提交复核",
            "pending_level1": "合并底稿待复核",
            "level1_in_progress": "合并底稿复核中",
        }[review_status]
        blockers.append(label)
    return DomainReadiness("lifecycle", status, "生命周期", dict(facts), blockers)


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


# ─────────────────────────────── 角色视图（纯函数） ───────────────────────────

# 四个审计角色待办桶。``level`` = 该桶的项目权限级别，经 ROLE_MAP 推导（不写字面量副本）：
#   编制 / 审批 / 重大判断 = edit（partner/manager/auditor/assistant）
#   质控                   = review（qc/eqcr）
# ``roles`` 是能处理该桶待办的委派角色别名（用于前端按当前用户角色高亮“我的待办”）。
RoleKey = Literal["preparer", "approval", "significant_judgment", "qc"]

_ROLE_VIEW_SPEC: dict[RoleKey, dict[str, Any]] = {
    "preparer": {"label": "编制", "level": "edit"},
    "approval": {"label": "审批", "level": "edit"},
    "significant_judgment": {"label": "重大判断", "level": "edit"},
    "qc": {"label": "质控", "level": "review"},
}


def _role_level(role_key: RoleKey) -> str:
    """该角色桶对应的项目权限级别，从 ROLE_MAP 现算，不写死 'edit'/'review' 副本。"""
    from app.services.assignment_service import ROLE_MAP

    # 代表角色：编制/审批/重大判断取编制类（auditor=edit），质控取 qc（review）。
    representative = "qc" if role_key == "qc" else "auditor"
    _project_role, level = ROLE_MAP[representative]
    return str(getattr(level, "value", level))


def _role_aliases(level: str) -> list[str]:
    """该级别下的委派角色别名集合（ROLE_MAP 反查；英文别名，按字典序稳定）。"""
    from app.services.assignment_service import ROLE_MAP

    out = sorted(
        {
            alias
            for alias, (_r, lv) in ROLE_MAP.items()
            if str(getattr(lv, "value", lv)) == level and alias.isascii()
        }
    )
    return out


def _todo(code: str, message: str, domain: str, severity: str) -> dict[str, Any]:
    return {"code": code, "message": message, "domain": domain, "severity": severity}


def build_role_views(
    domains: list[DomainReadiness], *, evidence: dict[str, Any], review: dict[str, Any],
) -> dict[str, Any]:
    """把七域 readiness + 证据 + 复核事实投影成四个角色待办桶（纯函数）。

    - 编制：企业树 / 工作底稿 / 抵销草稿 / 计算 / 证据 的 not_ready|warning 事实。
    - 审批：待审批抵销分录、未发布正式报表运行。
    - 重大判断：附注来源混合 / 未确认映射、抵销草稿（需人工判断是否成立）。
    - 质控：复核状态（未提交 / 待复核 / 退回）、证据不充分、整体阻断项汇总。

    事实全部取自服务端 readiness，不在前端拼装（R7.1 / R8）。
    """
    by_domain = {d.domain: d for d in domains}

    def dom(name: str) -> DomainReadiness:
        return by_domain.get(name) or DomainReadiness(name, "unknown", name, {}, [])

    tree, worksheet, elim = dom("tree"), dom("worksheet"), dom("elimination")
    calc, report, note = dom("calc"), dom("report"), dom("note")

    preparer: list[dict[str, Any]] = []
    approval: list[dict[str, Any]] = []
    significant: list[dict[str, Any]] = []
    qc: list[dict[str, Any]] = []

    # ── 编制待办 ──
    if tree.status == "not_ready":
        preparer.append(_todo("tree_not_ready", tree.blockers[0] if tree.blockers else "企业树未就绪", "tree", "blocker"))
    if worksheet.status in ("not_ready", "warning"):
        for b in worksheet.blockers:
            preparer.append(_todo("worksheet_todo", b, "worksheet", "blocker" if worksheet.status == "not_ready" else "warning"))
    if calc.status == "not_ready":
        for b in calc.blockers:
            preparer.append(_todo("calc_not_ready", b, "calc", "blocker"))
    draft_count = int(elim.facts.get("draft_count", 0))
    if draft_count:
        preparer.append(_todo("elimination_draft", f"{draft_count} 笔抵销草稿未提交", "elimination", "warning"))

    # ── 审批待办 ──
    pending_count = int(elim.facts.get("pending_count", 0))
    if pending_count:
        approval.append(_todo("elimination_pending", f"{pending_count} 笔抵销分录待审批", "elimination", "blocker"))
    if report.status == "not_ready":
        for b in report.blockers:
            approval.append(_todo("report_not_published", b, "report", "blocker"))

    # ── 重大判断待办 ──
    if draft_count:
        significant.append(_todo("judgment_draft_entries", f"{draft_count} 笔抵销草稿需判断是否成立", "elimination", "warning"))
    pending_mappings = int(note.facts.get("pending_mappings", 0))
    if pending_mappings:
        significant.append(_todo("note_pending_mappings", f"{pending_mappings} 个附注映射未确认或已过期", "note", "warning"))
    source_dist = note.facts.get("source_mode_distribution") or {}
    mixed = int(source_dist.get("mixed", 0))
    if mixed:
        significant.append(_todo("note_mixed_source", f"{mixed} 个附注章节来源混合，需逐格确认", "note", "warning"))

    # ── 质控待办 ──
    review_status = str(review.get("review_status") or "")
    if review_status == "level1_rejected":
        qc.append(_todo("review_rejected", "合并底稿复核被退回，待编制人修改", "lifecycle", "blocker"))
    elif review_status in ("pending_level1", "level1_in_progress"):
        qc.append(_todo("review_pending", "合并底稿待复核处理", "lifecycle", "action"))
    elif review_status in ("", "not_submitted"):
        qc.append(_todo("review_not_submitted", "合并底稿尚未提交复核", "lifecycle", "warning"))
    ev_status = str(evidence.get("status") or "")
    if ev_status == "not_ready":
        qc.append(_todo("evidence_insufficient", "合并底稿证据不充分", "worksheet", "blocker"))
    elif ev_status == "unknown":
        qc.append(_todo("evidence_unknown", "合并底稿证据状态暂时无法判断", "worksheet", "warning"))

    buckets = {
        "preparer": preparer,
        "approval": approval,
        "significant_judgment": significant,
        "qc": qc,
    }

    views = []
    for role_key in ("preparer", "approval", "significant_judgment", "qc"):
        spec = _ROLE_VIEW_SPEC[role_key]  # type: ignore[index]
        level = _role_level(role_key)  # type: ignore[arg-type]
        todos = buckets[role_key]
        has_blocker = any(t["severity"] == "blocker" for t in todos)
        views.append(
            {
                "role": role_key,
                "label": spec["label"],
                "level": level,
                "role_aliases": _role_aliases(level),
                "status": "not_ready" if has_blocker else ("warning" if todos else "ready"),
                "todo_count": len(todos),
                "todos": todos,
            }
        )
    return {"views": views}


# ─────────────────────────────── 装载层（连库） ───────────────────────────────


async def load_readiness_facts(
    db: AsyncSession, project_id: UUID, year: int,
) -> dict[str, dict[str, Any]]:
    """批量读取七域事实；不执行重算，只读当前库状态。"""
    from app.models.consol_note_data_models import ConsolNoteData
    from app.models.consol_worksheet_data_models import ConsolWorksheetData
    from app.models.consolidation_models import ConsolTrial, EliminationEntry
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

    # 证据充分性 + 复核状态：读合并薄底稿壳（A3-CONSOL），复用统一证据四态真源，不重算、不重建。
    evidence_facts, review_facts = await _load_shell_evidence_and_review(db, project_id)
    # 证据折进 worksheet 域事实（映射四态，不改 evidence_readiness 判定口径）
    ws_facts["evidence_status"] = evidence_facts.get("status")
    ws_facts["evidence_sufficient"] = evidence_facts.get("sufficient")
    ws_facts["evidence_missing_types"] = evidence_facts.get("missing_types", [])

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
    from app.models.phase10_models import ConsolSnapshot

    project = await db.get(Project, project_id)
    # 批 7 已实现 v2 manifest 快照：has_snapshot 改为真实存在性查询（不再恒 False），
    # 使签字创建后 lifecycle 域不再永远报「未创建签字快照」；签字门内的鸡生蛋豁免仍生效。
    has_snapshot = (await db.execute(
        sa.select(sa.func.count()).select_from(ConsolSnapshot).where(
            ConsolSnapshot.project_id == project_id,
            ConsolSnapshot.year == year,
        )
    )).scalar_one() > 0
    lifecycle_facts: dict[str, Any] = {
        "is_locked": bool(getattr(project, "consol_lock", False)) if project else False,
        "is_archived": (getattr(project, "status", None) == ProjectStatus.archived) if project else False,
        "has_snapshot": has_snapshot,
        # 复核状态折进 lifecycle 域事实（壳状态机，批 6.2）
        "review_status": review_facts.get("review_status"),
        "paper_status": review_facts.get("paper_status"),
        "has_shell": review_facts.get("has_shell", False),
    }

    return {
        "tree": tree_facts,
        "worksheet": ws_facts,
        "elimination": elim_facts,
        "calc": calc_facts,
        "report": report_facts,
        "note": note_facts,
        "lifecycle": lifecycle_facts,
        # 显式的证据 / 复核事实桶（角色视图直接消费，不再从 domain facts 里反推）
        "evidence": evidence_facts,
        "review": review_facts,
    }


async def _load_shell_evidence_and_review(
    db: AsyncSession, project_id: UUID,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """读合并薄底稿壳的证据充分性（统一四态）与复核状态。壳不存在时返回 unknown/无壳事实。

    证据：壳的 ``working_paper_id`` 经 :class:`EvidenceReadinessService` 评估 —— 与附件 owner、
    QC-17、签发门、归档共用同一事实来源（不以“附件数 > 0”近似，不重建充分性判定）。
    复核：壳的 ``review_status / status / assigned_to / reviewer``（批 6.2 状态机）。
    """
    from uuid import UUID as _UUID

    from app.services.consol_workpaper_shell import get_consol_workpaper_shell

    shell = await get_consol_workpaper_shell(db, project_id)
    if shell is None:
        # 无壳：证据状态未知（尚未建壳，也就无从挂证据）；复核无壳。
        return (
            {
                "status": "unknown",
                "sufficient": False,
                "missing_types": [],
                "has_shell": False,
                "wp_id": None,
            },
            {
                "review_status": None,
                "paper_status": None,
                "assigned_to": None,
                "reviewer": None,
                "rejection_reason": None,
                "has_shell": False,
            },
        )

    wp_id = _UUID(str(shell["working_paper_id"]))
    from app.services.evidence_readiness import EvidenceReadinessService

    readiness = await EvidenceReadinessService(db).evaluate_workpaper(wp_id)
    evidence_facts = {
        "status": readiness.status,
        # 与 wp_evidence_service.check_sufficiency 同口径：ready / not_declared 视为充分。
        "sufficient": readiness.status in {"ready", "not_declared"},
        "missing_types": list(readiness.missing_types),
        "has_shell": True,
        "wp_id": str(wp_id),
    }
    review_facts = {
        "review_status": shell.get("review_status"),
        "paper_status": shell.get("status"),
        "assigned_to": shell.get("assigned_to"),
        "reviewer": shell.get("reviewer"),
        "rejection_reason": shell.get("rejection_reason"),
        "has_shell": True,
    }
    return evidence_facts, review_facts


async def load_consol_readiness(
    db: AsyncSession, project_id: UUID, year: int,
) -> dict[str, Any]:
    facts = await load_readiness_facts(db, project_id, year)
    domains = build_readiness(facts)
    payload = readiness_payload(domains)
    # 证据 / 复核摘要随 readiness 一并暴露（R8.3），不改既有 domains 契约。
    payload["evidence"] = facts.get("evidence", {})
    payload["review"] = facts.get("review", {})
    return payload


async def load_consol_role_views(
    db: AsyncSession, project_id: UUID, year: int,
) -> dict[str, Any]:
    """角色视图：编制 / 审批 / 重大判断 / 质控四桶待办（服务端事实，不前端拼装）。

    附带 readiness 的 domains / 整体 blockers 摘要，便于前端一次取数、同页展示。
    """
    facts = await load_readiness_facts(db, project_id, year)
    domains = build_readiness(facts)
    role_payload = build_role_views(
        domains, evidence=facts.get("evidence", {}), review=facts.get("review", {}),
    )
    readiness = readiness_payload(domains)
    role_payload["readiness_status"] = readiness["status"]
    role_payload["domains"] = readiness["domains"]
    role_payload["evidence"] = facts.get("evidence", {})
    role_payload["review"] = facts.get("review", {})
    return role_payload


__all__ = [
    "DomainReadiness",
    "RoleKey",
    "Status",
    "build_readiness",
    "build_role_views",
    "load_consol_readiness",
    "load_consol_role_views",
    "load_readiness_facts",
    "readiness_payload",
]
