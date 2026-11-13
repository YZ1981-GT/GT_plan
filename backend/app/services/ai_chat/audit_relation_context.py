"""项目内审计关系上下文。

只从已授权宿主所属项目读取权威数据。底稿关联项再逐份经过统一可见性门；所有
查询都带 project_id/year，不接受客户端传入的项目断言。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_platform_models import Adjustment, ReviewStatus, TrialBalance
from app.models.core import Project
from app.models.evidence_governance_models import EvidenceRef
from app.models.knowledge_models import KnowledgeDocument, KnowledgeFolder
from app.models.report_models import DisclosureNote, FinancialReport
from app.models.workpaper_models import WorkingPaper, WpIndex
from app.services.ai_chat.contracts import HostType
from app.services.ai_chat.host_context import AuthorizedHostContext
from app.services.knowledge_access_policy import KnowledgeAccessPolicy, KnowledgeResource


@dataclass(frozen=True)
class AuditRelationItem:
    source_type: str
    source_id: str
    label: str
    content: str
    version: str = ""
    jump_route: str = ""


@lru_cache(maxsize=1)
def _mappings() -> tuple[dict[str, Any], ...]:
    path = Path(__file__).resolve().parents[3] / "data" / "wp_account_mapping.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    return tuple(payload.get("mappings") or ())


def _mapping_for_wp(wp_code: str) -> dict[str, Any] | None:
    return next((row for row in _mappings() if row.get("wp_code") == wp_code), None)


def _mapping_for_note(section: str) -> dict[str, Any] | None:
    return next((
        row for row in _mappings()
        if section in {
            row.get("note_section"), row.get("note_section_soe"),
            row.get("note_section_listed"),
        }
    ), None)


async def _visible_related_workpapers(
    db: AsyncSession,
    *,
    project_id: UUID,
    user: Any,
    account_codes: set[str],
    current_id: UUID | None,
) -> list[AuditRelationItem]:
    related_codes = sorted({
        str(row.get("wp_code"))
        for row in _mappings()
        if account_codes & set(row.get("account_codes") or []) and row.get("wp_code")
    })[:30]
    if not related_codes:
        return []
    rows = (await db.execute(sa.select(
        WorkingPaper.id, WorkingPaper.content_revision, WpIndex.wp_code, WpIndex.wp_name,
    ).join(WpIndex, WorkingPaper.wp_index_id == WpIndex.id).where(
        WorkingPaper.project_id == project_id,
        WorkingPaper.is_deleted == sa.false(),
        WpIndex.wp_code.in_(related_codes),
    ).order_by(WpIndex.wp_code))).all()
    from app.services.wp_visibility.entry_integration import try_gate_wp

    result: list[AuditRelationItem] = []
    for wp_id, revision, code, name in rows:
        if current_id is not None and wp_id == current_id:
            continue
        visible = await try_gate_wp(
            db,
            user,
            entrypoint="workpaper.ai_context",
            action="ai_read",
            method="GET",
            wp_id=wp_id,
            entry_family="ai_chat",
        )
        if visible is None:
            continue
        result.append(AuditRelationItem(
            "workpaper", str(wp_id), f"关联底稿 {code} {name or ''}".strip(),
            f"{code} {name or ''}（内容版本 {int(revision or 0)}）",
            version=str(int(revision or 0)), jump_route=f"/workpapers/{wp_id}",
        ))
    return result[:12]


async def build_audit_relation_context(
    db: AsyncSession,
    *,
    host: AuthorizedHostContext,
    user: Any,
) -> list[AuditRelationItem]:
    """返回同项目关系项；无项目/非底稿附注宿主时为空。"""
    if host.project_id is None or host.year is None:
        return []
    mapping: dict[str, Any] | None = None
    current_wp_id: UUID | None = None
    if host.resource_type is HostType.workpaper:
        current_wp_id = UUID(host.resource_id)
        code = (await db.execute(sa.select(WpIndex.wp_code).join(
            WorkingPaper, WorkingPaper.wp_index_id == WpIndex.id
        ).where(
            WorkingPaper.id == current_wp_id,
            WorkingPaper.project_id == host.project_id,
            WorkingPaper.is_deleted == sa.false(),
        ))).scalar_one_or_none()
        mapping = _mapping_for_wp(str(code or ""))
    elif host.resource_type is HostType.note:
        section = (await db.execute(sa.select(DisclosureNote.note_section).where(
            DisclosureNote.id == UUID(host.resource_id),
            DisclosureNote.project_id == host.project_id,
            DisclosureNote.year == host.year,
            DisclosureNote.is_deleted == sa.false(),
        ))).scalar_one_or_none()
        mapping = _mapping_for_note(str(section or ""))
    else:
        return []
    if not mapping:
        return []

    account_codes = {str(value) for value in mapping.get("account_codes") or [] if value}
    result = await _visible_related_workpapers(
        db, project_id=host.project_id, user=user,
        account_codes=account_codes, current_id=current_wp_id,
    )
    if account_codes:
        conditions = [TrialBalance.standard_account_code.like(f"{code}%") for code in account_codes]
        tb_rows = (await db.execute(sa.select(
            TrialBalance.id, TrialBalance.standard_account_code,
            TrialBalance.account_name, TrialBalance.unadjusted_amount,
            TrialBalance.audited_amount, TrialBalance.created_at,
        ).where(
            TrialBalance.project_id == host.project_id,
            TrialBalance.year == host.year,
            TrialBalance.is_deleted == sa.false(),
            sa.or_(*conditions),
        ).order_by(TrialBalance.standard_account_code).limit(20))).all()
        for row in tb_rows:
            result.append(AuditRelationItem(
                "trial_balance", str(row.id),
                f"试算表 {row.standard_account_code} {row.account_name or ''}".strip(),
                f"未审数 {row.unadjusted_amount or 0}；审定数 {row.audited_amount or 0}",
                version=str(row.created_at or ""),
                jump_route=f"/trial-balance?year={host.year}&account={row.standard_account_code}",
            ))
        adjustment_rows = (await db.execute(sa.select(
            Adjustment.id, Adjustment.adjustment_no, Adjustment.account_code,
            Adjustment.description, Adjustment.debit_amount, Adjustment.credit_amount,
            Adjustment.updated_at,
        ).where(
            Adjustment.project_id == host.project_id,
            Adjustment.year == host.year,
            Adjustment.is_deleted == sa.false(),
            Adjustment.review_status == ReviewStatus.approved,
            sa.or_(*[Adjustment.account_code.like(f"{code}%") for code in account_codes]),
        ).order_by(Adjustment.adjustment_no).limit(12))).all()
        for row in adjustment_rows:
            result.append(AuditRelationItem(
                "adjustment", str(row.id), f"已批准调整 {row.adjustment_no}",
                f"科目 {row.account_code}；借方 {row.debit_amount or 0}；贷方 {row.credit_amount or 0}；摘要 {row.description or ''}",
                version=str(row.updated_at or ""), jump_route=f"/adjustments?highlight={row.id}",
            ))

    report_row = mapping.get("report_row")
    if report_row:
        rows = (await db.execute(sa.select(
            FinancialReport.id, FinancialReport.row_code, FinancialReport.row_name,
            FinancialReport.current_period_amount, FinancialReport.prior_period_amount,
            FinancialReport.updated_at,
        ).where(
            FinancialReport.project_id == host.project_id,
            FinancialReport.year == host.year,
            FinancialReport.row_code == report_row,
            FinancialReport.is_deleted == sa.false(),
        ).limit(4))).all()
        for row in rows:
            result.append(AuditRelationItem(
                "report", str(row.id), f"报表 {row.row_code} {row.row_name or ''}".strip(),
                f"本期 {row.current_period_amount or 0}；上期 {row.prior_period_amount or 0}",
                version=str(row.updated_at or ""), jump_route=f"/reports/{row.id}",
            ))

    note_sections = {
        str(value) for value in (
            mapping.get("note_section"), mapping.get("note_section_soe"),
            mapping.get("note_section_listed"),
        ) if value
    }
    if note_sections:
        notes = (await db.execute(sa.select(
            DisclosureNote.id, DisclosureNote.note_section, DisclosureNote.section_title,
            DisclosureNote.text_content, DisclosureNote.updated_at, DisclosureNote.is_stale,
        ).where(
            DisclosureNote.project_id == host.project_id,
            DisclosureNote.year == host.year,
            DisclosureNote.note_section.in_(note_sections),
            DisclosureNote.is_deleted == sa.false(),
        ).order_by(DisclosureNote.note_section))).all()
        for row in notes:
            result.append(AuditRelationItem(
                "note", str(row.id), f"附注 {row.note_section} {row.section_title or ''}".strip(),
                ("[过期] " if row.is_stale else "") + (row.text_content or "[暂无正文]"),
                version=str(row.updated_at or ""), jump_route=f"/disclosure-notes/{row.id}",
            ))

    # ── 上年关系：按 client_name + year-1 找上年同项目，注入上年底稿/附注 ─────────────
    prior_year = host.year - 1
    prior_project_row = (await db.execute(
        sa.select(Project.id).where(
            Project.client_name == sa.select(Project.client_name).where(
                Project.id == host.project_id
            ).scalar_subquery(),
            Project.audit_year == prior_year,
            Project.is_deleted == sa.false(),
        ).limit(1)
    )).scalar_one_or_none()
    if prior_project_row is not None:
        prior_project_id = prior_project_row
        # 上年同底稿
        if current_wp_id is not None and mapping:
            prior_wp_rows = (await db.execute(sa.select(
                WorkingPaper.id, WpIndex.wp_code, WpIndex.wp_name,
            ).join(WpIndex, WorkingPaper.wp_index_id == WpIndex.id).where(
                WorkingPaper.project_id == prior_project_id,
                WorkingPaper.is_deleted == sa.false(),
                WpIndex.wp_code == str(mapping.get("wp_code") or ""),
            ).limit(3))).all()
            for row in prior_wp_rows:
                result.append(AuditRelationItem(
                    "prior_workpaper", str(row.id),
                    f"上年底稿 {row.wp_code} {row.wp_name or ''}".strip(),
                    f"上年（{prior_year}）{row.wp_code} {row.wp_name or ''}",
                    jump_route=f"/workpapers/{row.id}",
                ))
        # 上年同附注
        if note_sections:
            prior_notes = (await db.execute(sa.select(
                DisclosureNote.id, DisclosureNote.note_section, DisclosureNote.section_title,
            ).where(
                DisclosureNote.project_id == prior_project_id,
                DisclosureNote.year == prior_year,
                DisclosureNote.note_section.in_(note_sections),
                DisclosureNote.is_deleted == sa.false(),
            ).order_by(DisclosureNote.note_section).limit(4))).all()
            for row in prior_notes:
                result.append(AuditRelationItem(
                    "prior_note", str(row.id),
                    f"上年附注 {row.note_section} {row.section_title or ''}".strip(),
                    f"上年（{prior_year}）{row.note_section}",
                    jump_route=f"/disclosure-notes/{row.id}",
                ))

    # ── 证据关系：EvidenceRef 关联的证据文件 ────────────────────────────────────────
    resource_id_str = host.resource_id
    evidence_rows = (await db.execute(sa.select(
        EvidenceRef.id, EvidenceRef.label, EvidenceRef.evidence_type,
        EvidenceRef.evidence_id, EvidenceRef.created_at,
    ).where(
        EvidenceRef.project_id == host.project_id,
        EvidenceRef.source_id == resource_id_str,
        EvidenceRef.status == "active",
    ).order_by(EvidenceRef.created_at.desc()).limit(8))).all()
    for row in evidence_rows:
        result.append(AuditRelationItem(
            "evidence", str(row.id),
            f"关联证据 {row.label or row.evidence_type or ''}".strip(),
            f"证据类型：{row.evidence_type or '通用'}；ID：{row.evidence_id or ''}",
            version=str(row.created_at or ""),
        ))

    # ── 知识标签关系：按 template_file / 科目码找关联知识库文档 ─────────────────────
    if mapping:
        relation_tags: set[str] = set()
        template_file = mapping.get("template_file")
        template_type = mapping.get("template_type")
        if template_file:
            relation_tags.add(str(template_file))
        if template_type:
            relation_tags.add(str(template_type))
        for code in list(account_codes)[:3]:
            relation_tags.add(code)
        if relation_tags:
            tag_conditions = [
                KnowledgeDocument.tags.contains([tag]) for tag in sorted(relation_tags)
            ]
            knowledge_rows = (await db.execute(sa.select(
                KnowledgeDocument.id, KnowledgeDocument.name,
                KnowledgeDocument.tags, KnowledgeDocument.access_level,
                KnowledgeDocument.project_ids, KnowledgeDocument.created_by,
                KnowledgeFolder.access_level, KnowledgeFolder.project_ids,
                KnowledgeFolder.created_by,
            ).join(
                KnowledgeFolder, KnowledgeDocument.folder_id == KnowledgeFolder.id,
            ).where(
                KnowledgeDocument.is_deleted == sa.false(),
                KnowledgeFolder.is_deleted == sa.false(),
                sa.or_(*tag_conditions),
            ).limit(8))).all()
            subject = await KnowledgeAccessPolicy.resolve_subject(db, user)
            for row in knowledge_rows:
                doc_resource = KnowledgeResource.of_row(
                    row.access_level, row.project_ids, row.created_by
                )
                folder_resource = KnowledgeResource.of_row(
                    row[6], row[7], row[8]
                )
                if not KnowledgeAccessPolicy.can_read_document(
                    subject, doc_resource, folder_resource
                ):
                    continue
                tags = row.tags if isinstance(row.tags, list) else []
                result.append(AuditRelationItem(
                    "knowledge_relation", str(row.id),
                    f"关联知识 {row.name or '未命名文档'}",
                    "标签关系：" + "、".join(str(tag) for tag in tags[:12]),
                ))

    return result
