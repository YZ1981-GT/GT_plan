"""底稿关联附件的统一视图（spec attachment-evidence-intake 需求 4.1、4.5，ADR-AEI-07）。

来源：整稿关联（associated）∪ ``reference`` 指向本底稿（referenced）∪ 本底稿函证挂载（confirmation）∪ 本底稿证据链接
（evidence_link，行级 / 单元格级）。按附件去重，多来源合并进 ``sources``；主来源优先级
associated > referenced > confirmation > evidence_link。每项另带 ``evidence_positions``（本底稿的行级位置）与
``linked_wp_count``（整稿关联的底稿数）。

组装逻辑原在 ``AttachmentService.get_wp_attachments``（spec attachment-workpaper-linkage-convergence Task 2.2 / 3.1），
挪到这里后服务层方法只做委托：``attachment_service.py`` 已超行数门，新来源不再往里加。
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING, Any
from uuid import UUID

import sqlalchemy as sa

from app.models.attachment_models import Attachment, AttachmentWorkingPaper

if TYPE_CHECKING:
    from app.services.attachment_service import AttachmentService


def _fail_open(event: str, **fields: Any) -> None:
    from app.services.attachment_wp_fail_open import log_awp_fail_open

    log_awp_fail_open(event, **fields)


def _add_source(by_id: dict[str, dict], svc: "AttachmentService", att: Attachment, source: str) -> dict:
    aid = str(att.id)
    row = by_id.get(aid)
    if row is None:
        row = svc._to_dict(att)
        row["source"] = source
        row["sources"] = [source]
        row["association_type"] = None
        by_id[aid] = row
    elif source not in row["sources"]:
        row["sources"].append(source)
    return row


async def linked_wp_id_sets(db, attachment_ids: Iterable[str | UUID]) -> dict[str, set[UUID]]:
    """每个附件出现在哪些底稿：整稿关联 ∪ 行级证据链接 ∪ ``reference`` 指向的底稿（去重）。

    函证挂载由函证模块管理（统一视图里单独标「函证回函」），不计入。行级上传只写证据链接（ADR-AEI-02），
    只数整稿关联会把它们算成「未关联底稿」。
    """
    from app.models.wp_optimization_models import EvidenceLink

    ids = [UUID(str(aid)) for aid in attachment_ids]
    out: dict[str, set[UUID]] = {str(aid): set() for aid in ids}
    if not ids:
        return out
    for model in (AttachmentWorkingPaper, EvidenceLink):
        rows = (await db.execute(
            sa.select(model.attachment_id, model.wp_id).where(model.attachment_id.in_(ids))
        )).all()
        for aid, wid in rows:
            if wid is not None:
                out.setdefault(str(aid), set()).add(wid)
    ref_rows = (await db.execute(
        sa.select(Attachment.id, Attachment.reference_id).where(
            Attachment.id.in_(ids),
            Attachment.reference_type == "working_paper",
            Attachment.reference_id.is_not(None),
        )
    )).all()
    for aid, wid in ref_rows:
        out.setdefault(str(aid), set()).add(wid)
    return out


async def linked_wp_counts(db, attachment_ids: Iterable[str | UUID]) -> dict[str, int]:
    """每个附件出现在几张底稿（口径见 :func:`linked_wp_id_sets`）。"""
    return {aid: len(wps) for aid, wps in (await linked_wp_id_sets(db, attachment_ids)).items()}


async def linked_workpapers(db, attachment_id: UUID) -> list[dict]:
    """附件出现的底稿清单（编码 / 名称），只取与附件同项目、未删除的底稿，按编码排序。"""
    from app.models.workpaper_models import WorkingPaper, WpIndex

    project_id = (await db.execute(
        sa.select(Attachment.project_id).where(Attachment.id == attachment_id)
    )).scalar_one_or_none()
    wp_ids = (await linked_wp_id_sets(db, [attachment_id])).get(str(attachment_id)) or set()
    if project_id is None or not wp_ids:
        return []
    rows = (await db.execute(
        sa.select(WorkingPaper.id, WpIndex.wp_code, WpIndex.wp_name)
        .join(WpIndex, WpIndex.id == WorkingPaper.wp_index_id)
        .where(
            WorkingPaper.id.in_(list(wp_ids)),
            WorkingPaper.project_id == project_id,
            WorkingPaper.is_deleted == sa.false(),
        )
        .order_by(WpIndex.wp_code, WorkingPaper.id)
    )).all()
    return [{"wp_id": str(wid), "wp_code": code, "wp_name": name} for wid, code, name in rows]


async def annotate_linked_wp_count(db, items: list[dict]) -> list[dict]:
    counts = await linked_wp_counts(db, [item["id"] for item in items if item.get("id")])
    for item in items:
        item["linked_wp_count"] = counts.get(str(item.get("id")), 0)
    return items


async def build_wp_attachment_view(svc: "AttachmentService", wp_id: UUID) -> dict:
    """返回 ``{"items": [...], "evidence_requirements"?: [...], "stale_info"?: {...}}``。"""
    db = svc.db
    by_id: dict[str, dict] = {}

    # 1) 整稿关联（权威链表）
    link_rows = (await db.execute(
        sa.select(Attachment, AttachmentWorkingPaper.association_type)
        .join(AttachmentWorkingPaper, AttachmentWorkingPaper.attachment_id == Attachment.id)
        .where(AttachmentWorkingPaper.wp_id == wp_id, Attachment.is_deleted == sa.false())
    )).all()
    for att, assoc_type in link_rows:
        _add_source(by_id, svc, att, "associated")["association_type"] = assoc_type

    # 2) reference 关联（兼容路径）
    ref_atts = (await db.execute(
        sa.select(Attachment).where(
            Attachment.reference_type == "working_paper",
            Attachment.reference_id == wp_id,
            Attachment.is_deleted == sa.false(),
        )
    )).scalars().all()
    for att in ref_atts:
        _add_source(by_id, svc, att, "referenced")

    # 3) 函证只读纳入（wp → confirmations → confirmation_attachment_link）；异常跳过
    try:
        from app.models.confirmation_models import Confirmation, ConfirmationAttachmentLink

        conf_atts = (await db.execute(
            sa.select(Attachment)
            .join(ConfirmationAttachmentLink, ConfirmationAttachmentLink.attachment_id == Attachment.id)
            .join(Confirmation, Confirmation.id == ConfirmationAttachmentLink.confirmation_id)
            .where(Confirmation.wp_id == wp_id, Attachment.is_deleted == sa.false())
        )).scalars().unique().all()
        for att in conf_atts:
            _add_source(by_id, svc, att, "confirmation")
    except Exception:
        _fail_open("awp_confirmation_lookup_fail_open", wp_id=wp_id)

    # 4) 本底稿证据链接（行级 / 单元格级）
    from app.models.wp_optimization_models import EvidenceLink

    ev_rows = (await db.execute(
        sa.select(EvidenceLink, Attachment)
        .join(Attachment, Attachment.id == EvidenceLink.attachment_id)
        .where(EvidenceLink.wp_id == wp_id, Attachment.is_deleted == sa.false())
        .order_by(EvidenceLink.created_at, EvidenceLink.id)
    )).all()
    for link, att in ev_rows:
        row = _add_source(by_id, svc, att, "evidence_link")
        row.setdefault("evidence_positions", []).append({
            "link_id": str(link.id),
            "sheet_name": link.sheet_name,
            "cell_ref": link.cell_ref,
            "page_ref": link.page_ref,
            "evidence_type": link.evidence_type,
        })

    items = list(by_id.values())
    for item in items:
        item.setdefault("evidence_positions", [])
    await annotate_linked_wp_count(db, items)
    result: dict = {"items": items}

    # 一次取 wp 元数据，供证据声明 + stale 共用
    wp_meta = await svc._resolve_wp_meta(wp_id)

    # 证据类型声明（无声明不附加键；失败 fail-open）
    try:
        from app.services.workpaper_evidence_requirements import build_evidence_requirements

        ev_req = build_evidence_requirements(wp_meta.get("wp_code") if wp_meta else None, items)
        if ev_req is not None:
            result["evidence_requirements"] = ev_req
    except Exception:
        _fail_open("awp_evidence_requirements_fail_open", wp_id=wp_id)

    # stale 失效前置（失败 omit；无失效也返回 has_stale=false 供前端门控）
    try:
        from app.services.workpaper_attachment_stale import build_stale_info

        stale = await build_stale_info(
            db, wp_id=wp_id, attachment_ids=[str(it.get("id")) for it in items if it.get("id")], wp_meta=wp_meta,
        )
        if stale is not None:
            result["stale_info"] = stale
    except Exception:
        _fail_open("awp_stale_fail_open", wp_id=wp_id)

    return result
