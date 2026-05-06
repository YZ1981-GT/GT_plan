"""EQCR 判断域聚合 + 意见 CRUD 服务

从 eqcr_service.py 拆分而来，包含：
- get_materiality / get_estimates / get_related_parties / get_going_concern / get_opinion_type
- create_opinion / update_opinion
- 相关私有辅助方法
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.eqcr_models import EqcrOpinion
from app.models.report_models import AuditReport

from .eqcr_workbench_service import EQCR_CORE_DOMAINS


# 会计估计关键词（用于 WorkingPaper.name/wp_index.wp_name 兜底匹配）
_ESTIMATE_KEYWORDS: tuple[str, ...] = (
    "估计",
    "减值",
    "跌价",
    "折旧",
    "摊销",
)

_ALLOWED_DOMAINS: frozenset[str] = frozenset(
    list(EQCR_CORE_DOMAINS) + ["component_auditor"]
)
_ALLOWED_VERDICTS: frozenset[str] = frozenset(
    ["agree", "disagree", "need_more_evidence"]
)


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------


def _decimal_str(value: Decimal | None) -> str | None:
    """将 Decimal 序列化为字符串（JSON 兼容，保留精度）。"""
    if value is None:
        return None
    return str(value)


def _serialize_opinion(op: "EqcrOpinion") -> dict[str, Any]:
    """把 ``EqcrOpinion`` ORM 对象转换为 JSON 可序列化字典。"""
    return {
        "id": str(op.id),
        "project_id": str(op.project_id),
        "domain": op.domain,
        "verdict": op.verdict,
        "comment": op.comment,
        "extra_payload": op.extra_payload,
        "created_by": str(op.created_by) if op.created_by else None,
        "created_at": op.created_at.isoformat() if op.created_at else None,
        "updated_at": op.updated_at.isoformat() if op.updated_at else None,
    }


def _split_current_history(
    opinions: list["EqcrOpinion"],
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    """按 ``created_at`` 升序，最后一条为 ``current_opinion``，其余为 ``history``。"""
    if not opinions:
        return None, []
    sorted_ops = sorted(opinions, key=lambda o: o.created_at or datetime.min)
    current = _serialize_opinion(sorted_ops[-1])
    history = [_serialize_opinion(o) for o in sorted_ops[:-1]]
    return current, history


async def _load_domain_opinions(
    db: AsyncSession, project_id: uuid.UUID, domain: str
) -> list[EqcrOpinion]:
    """载入某个 domain 下该项目的所有 active opinion，按创建时间升序。"""
    q = (
        select(EqcrOpinion)
        .where(
            EqcrOpinion.project_id == project_id,
            EqcrOpinion.domain == domain,
            EqcrOpinion.is_deleted == False,  # noqa: E712
        )
        .order_by(EqcrOpinion.created_at.asc())
    )
    return list((await db.execute(q)).scalars().all())


# ---------------------------------------------------------------------------
# 主服务
# ---------------------------------------------------------------------------


class EqcrDomainService:
    """EQCR 5 判断域聚合 + 意见 CRUD。"""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ------------------------------------------------------------------
    # 5 判断域聚合方法
    # ------------------------------------------------------------------

    async def get_materiality(self, project_id: uuid.UUID) -> dict[str, Any]:
        """需求 2.2：重要性 Tab 数据 + 本域意见历史。"""
        from app.models.audit_platform_models import Materiality

        q = (
            select(Materiality)
            .where(
                Materiality.project_id == project_id,
                Materiality.is_deleted == False,  # noqa: E712
            )
            .order_by(Materiality.year.desc(), Materiality.created_at.desc())
        )
        rows = list((await self.db.execute(q)).scalars().all())

        current_year: dict[str, Any] | None = None
        history_years: list[dict[str, Any]] = []
        for idx, row in enumerate(rows):
            payload = {
                "year": row.year,
                "benchmark_type": row.benchmark_type,
                "benchmark_amount": _decimal_str(row.benchmark_amount),
                "overall_percentage": _decimal_str(row.overall_percentage),
                "overall_materiality": _decimal_str(row.overall_materiality),
                "performance_ratio": _decimal_str(row.performance_ratio),
                "performance_materiality": _decimal_str(row.performance_materiality),
                "trivial_ratio": _decimal_str(row.trivial_ratio),
                "trivial_threshold": _decimal_str(row.trivial_threshold),
                "is_override": bool(row.is_override),
                "override_reason": row.override_reason,
            }
            if idx == 0:
                current_year = payload
            else:
                history_years.append(payload)

        opinions = await _load_domain_opinions(self.db, project_id, "materiality")
        current_opinion, history_opinions = _split_current_history(opinions)

        return {
            "project_id": str(project_id),
            "domain": "materiality",
            "data": {
                "current": current_year,
                "prior_years": history_years,
            },
            "current_opinion": current_opinion,
            "history_opinions": history_opinions,
        }

    async def get_estimates(self, project_id: uuid.UUID) -> dict[str, Any]:
        """需求 2.3：会计估计 Tab 数据。"""
        from app.models.workpaper_models import WorkingPaper, WpIndex

        name_filter = None
        for kw in _ESTIMATE_KEYWORDS:
            cond = WpIndex.wp_name.like(f"%{kw}%")
            name_filter = cond if name_filter is None else (name_filter | cond)

        has_category = hasattr(WpIndex, "category")
        if has_category:
            category_cond = getattr(WpIndex, "category") == "estimate"
            name_filter = category_cond if name_filter is None else (name_filter | category_cond)

        q = (
            select(WpIndex, WorkingPaper)
            .outerjoin(WorkingPaper, WorkingPaper.wp_index_id == WpIndex.id)
            .where(
                WpIndex.project_id == project_id,
                WpIndex.is_deleted == False,  # noqa: E712
                name_filter,
            )
            .order_by(WpIndex.wp_code.asc())
        )
        rows = (await self.db.execute(q)).all()

        items: list[dict[str, Any]] = []
        seen_wp_index_ids: set[uuid.UUID] = set()
        for idx_row, wp_row in rows:
            if idx_row.id in seen_wp_index_ids:
                continue
            seen_wp_index_ids.add(idx_row.id)
            items.append(
                {
                    "wp_index_id": str(idx_row.id),
                    "wp_code": idx_row.wp_code,
                    "wp_name": idx_row.wp_name,
                    "audit_cycle": idx_row.audit_cycle,
                    "index_status": idx_row.status.value if idx_row.status else None,
                    "file_status": wp_row.status.value if wp_row and wp_row.status else None,
                    "review_status": wp_row.review_status.value
                    if wp_row and wp_row.review_status
                    else None,
                    "working_paper_id": str(wp_row.id) if wp_row else None,
                }
            )

        opinions = await _load_domain_opinions(self.db, project_id, "estimate")
        current_opinion, history_opinions = _split_current_history(opinions)

        return {
            "project_id": str(project_id),
            "domain": "estimate",
            "data": {
                "items": items,
                "match_strategy": "wp_name_keyword",
                "keywords": list(_ESTIMATE_KEYWORDS),
            },
            "current_opinion": current_opinion,
            "history_opinions": history_opinions,
        }

    async def get_related_parties(self, project_id: uuid.UUID) -> dict[str, Any]:
        """需求 2.4：关联方 Tab 数据（注册表 + 交易明细）。"""
        from app.models.related_party_models import (
            RelatedPartyRegistry,
            RelatedPartyTransaction,
        )

        reg_q = (
            select(RelatedPartyRegistry)
            .where(
                RelatedPartyRegistry.project_id == project_id,
                RelatedPartyRegistry.is_deleted == False,  # noqa: E712
            )
            .order_by(RelatedPartyRegistry.created_at.asc())
        )
        registries = list((await self.db.execute(reg_q)).scalars().all())

        txn_q = (
            select(RelatedPartyTransaction)
            .where(
                RelatedPartyTransaction.project_id == project_id,
                RelatedPartyTransaction.is_deleted == False,  # noqa: E712
            )
            .order_by(RelatedPartyTransaction.created_at.asc())
        )
        transactions = list((await self.db.execute(txn_q)).scalars().all())

        registries_payload = [
            {
                "id": str(r.id),
                "name": r.name,
                "relation_type": r.relation_type,
                "is_controlled_by_same_party": bool(r.is_controlled_by_same_party),
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in registries
        ]
        transactions_payload = [
            {
                "id": str(t.id),
                "related_party_id": str(t.related_party_id),
                "amount": _decimal_str(t.amount),
                "transaction_type": t.transaction_type,
                "is_arms_length": t.is_arms_length,
                "evidence_refs": t.evidence_refs,
                "created_at": t.created_at.isoformat() if t.created_at else None,
            }
            for t in transactions
        ]

        opinions = await _load_domain_opinions(self.db, project_id, "related_party")
        current_opinion, history_opinions = _split_current_history(opinions)

        return {
            "project_id": str(project_id),
            "domain": "related_party",
            "data": {
                "registries": registries_payload,
                "transactions": transactions_payload,
                "summary": {
                    "registry_count": len(registries_payload),
                    "transaction_count": len(transactions_payload),
                },
            },
            "current_opinion": current_opinion,
            "history_opinions": history_opinions,
        }

    async def get_going_concern(self, project_id: uuid.UUID) -> dict[str, Any]:
        """需求 2.5：持续经营 Tab 数据（复用 GoingConcernEvaluation）。"""
        from app.models.collaboration_models import (
            GoingConcernEvaluation,
            GoingConcernIndicator,
        )

        eval_q = (
            select(GoingConcernEvaluation)
            .where(
                GoingConcernEvaluation.project_id == project_id,
                GoingConcernEvaluation.is_deleted == False,  # noqa: E712
            )
            .order_by(GoingConcernEvaluation.evaluation_date.desc())
        )
        evaluations = list((await self.db.execute(eval_q)).scalars().all())

        current_eval: dict[str, Any] | None = None
        prior_evals: list[dict[str, Any]] = []
        latest_indicators: list[dict[str, Any]] = []

        for idx, ev in enumerate(evaluations):
            payload = {
                "id": str(ev.id),
                "evaluation_date": ev.evaluation_date.isoformat()
                if ev.evaluation_date
                else None,
                "conclusion": ev.conclusion.value if ev.conclusion else None,
                "key_indicators": ev.key_indicators,
                "management_plan": ev.management_plan,
                "auditor_conclusion": ev.auditor_conclusion,
            }
            if idx == 0:
                current_eval = payload

                ind_q = (
                    select(GoingConcernIndicator)
                    .where(
                        GoingConcernIndicator.evaluation_id == ev.id,
                        GoingConcernIndicator.is_deleted == False,  # noqa: E712
                    )
                    .order_by(GoingConcernIndicator.created_at.asc())
                )
                indicators = list((await self.db.execute(ind_q)).scalars().all())
                latest_indicators = [
                    {
                        "id": str(ind.id),
                        "indicator_type": ind.indicator_type,
                        "indicator_value": ind.indicator_value,
                        "threshold": ind.threshold,
                        "is_triggered": bool(ind.is_triggered),
                        "severity": ind.severity.value if ind.severity else None,
                        "notes": ind.notes,
                    }
                    for ind in indicators
                ]
            else:
                prior_evals.append(payload)

        opinions = await _load_domain_opinions(self.db, project_id, "going_concern")
        current_opinion, history_opinions = _split_current_history(opinions)

        return {
            "project_id": str(project_id),
            "domain": "going_concern",
            "data": {
                "current_evaluation": current_eval,
                "prior_evaluations": prior_evals,
                "indicators": latest_indicators,
            },
            "current_opinion": current_opinion,
            "history_opinions": history_opinions,
        }

    async def get_opinion_type(self, project_id: uuid.UUID) -> dict[str, Any]:
        """需求 2.6：审计意见类型 Tab 数据。"""
        ar_q = (
            select(AuditReport)
            .where(
                AuditReport.project_id == project_id,
                AuditReport.is_deleted == False,  # noqa: E712
            )
            .order_by(AuditReport.year.desc())
        )
        reports = list((await self.db.execute(ar_q)).scalars().all())

        current_report: dict[str, Any] | None = None
        prior_reports: list[dict[str, Any]] = []
        for idx, ar in enumerate(reports):
            payload = {
                "id": str(ar.id),
                "year": ar.year,
                "opinion_type": ar.opinion_type.value if ar.opinion_type else None,
                "company_type": ar.company_type.value if ar.company_type else None,
                "status": ar.status.value if ar.status else None,
                "report_date": ar.report_date.isoformat() if ar.report_date else None,
                "signing_partner": ar.signing_partner,
                "paragraphs": ar.paragraphs,
            }
            if idx == 0:
                current_report = payload
            else:
                prior_reports.append(payload)

        opinions = await _load_domain_opinions(self.db, project_id, "opinion_type")
        current_opinion, history_opinions = _split_current_history(opinions)

        return {
            "project_id": str(project_id),
            "domain": "opinion_type",
            "data": {
                "current_report": current_report,
                "prior_reports": prior_reports,
            },
            "current_opinion": current_opinion,
            "history_opinions": history_opinions,
        }

    # ------------------------------------------------------------------
    # 意见 CRUD（POST / PATCH）
    # ------------------------------------------------------------------

    async def create_opinion(
        self,
        *,
        project_id: uuid.UUID,
        domain: str,
        verdict: str,
        comment: str | None,
        extra_payload: dict | None,
        user_id: uuid.UUID,
    ) -> dict[str, Any]:
        """新建一条 EQCR 意见。调用方负责 ``db.commit()``。"""
        if domain not in _ALLOWED_DOMAINS:
            raise ValueError(f"非法 domain: {domain}；允许值 {sorted(_ALLOWED_DOMAINS)}")
        if verdict not in _ALLOWED_VERDICTS:
            raise ValueError(
                f"非法 verdict: {verdict}；允许值 {sorted(_ALLOWED_VERDICTS)}"
            )

        op = EqcrOpinion(
            project_id=project_id,
            domain=domain,
            verdict=verdict,
            comment=comment,
            extra_payload=extra_payload,
            created_by=user_id,
        )
        self.db.add(op)
        await self.db.flush()
        await self.db.refresh(op)
        return _serialize_opinion(op)

    async def update_opinion(
        self,
        *,
        opinion_id: uuid.UUID,
        user_id: uuid.UUID,
        verdict: str | None = None,
        comment: str | None = None,
        extra_payload: dict | None = None,
    ) -> dict[str, Any] | None:
        """更新一条 EQCR 意见。返回 None 表示不存在。"""
        q = select(EqcrOpinion).where(
            EqcrOpinion.id == opinion_id,
            EqcrOpinion.is_deleted == False,  # noqa: E712
        )
        op = (await self.db.execute(q)).scalar_one_or_none()
        if op is None:
            return None

        if verdict is not None:
            if verdict not in _ALLOWED_VERDICTS:
                raise ValueError(
                    f"非法 verdict: {verdict}；允许值 {sorted(_ALLOWED_VERDICTS)}"
                )
            op.verdict = verdict
        if comment is not None:
            op.comment = comment
        if extra_payload is not None:
            op.extra_payload = extra_payload

        await self.db.flush()
        await self.db.refresh(op)
        return _serialize_opinion(op)
