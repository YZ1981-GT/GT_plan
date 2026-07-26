"""ConfirmationEvidenceService — 函证台账↔附件证据链编排层

M2（附件链）核心服务：
- link_attachment: 挂附件（发函件直接挂；回函件强校验配对发函件）
- unlink_attachment: 解绑（清 reference/删 link，不物删附件，留痕）
- list_attachments: 列某函证全部附件（含角色/配对/OCR状态）
- list_attachment_counts: 批量单查询免 N+1

服务只 flush 不 commit（router 统一 commit）。
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from decimal import Decimal

from app.models.attachment_models import Attachment
from app.models.confirmation_models import (
    Confirmation,
    ConfirmationAttachmentLink,
    ConfirmationActionLog,
)
from app.services.attachment_service import AttachmentService


# ---------------------------------------------------------------------------
# link_attachment
# ---------------------------------------------------------------------------


async def link_attachment(
    db: AsyncSession,
    *,
    confirmation_id: uuid.UUID,
    attachment_id: uuid.UUID,
    role: str,
    paired_outbound_id: uuid.UUID | None = None,
    actor_user_id: uuid.UUID,
) -> ConfirmationAttachmentLink:
    """挂附件到函证记录。

    - role='outbound': 直接创建 link
    - role='inbound':
      1. 校验该函证至少有一份 outbound 附件，无则拒绝
      2. 仅一份 outbound → 自动配对
      3. 多份 outbound → 要求指定 paired_outbound_id
      4. 验证 paired_outbound_id 指向同函证的 outbound 附件
    """
    if role not in ("outbound", "inbound"):
        raise ValueError(f"附件角色必须是 outbound 或 inbound，收到: {role}")

    # 获取函证记录（需要 project_id 供 action_log）
    confirmation = await db.get(Confirmation, confirmation_id)
    if confirmation is None:
        raise ValueError(f"函证记录不存在: {confirmation_id}")

    final_paired_outbound_id: uuid.UUID | None = None

    if role == "inbound":
        # 查询该函证已有的 outbound 附件
        outbound_q = select(ConfirmationAttachmentLink).where(
            and_(
                ConfirmationAttachmentLink.confirmation_id == confirmation_id,
                ConfirmationAttachmentLink.role == "outbound",
            )
        )
        result = await db.execute(outbound_q)
        outbound_links = result.scalars().all()

        if not outbound_links:
            raise ValueError("无发函件不得单独挂回函件")

        if len(outbound_links) == 1:
            # 单份发函件 → 自动配对
            final_paired_outbound_id = outbound_links[0].attachment_id
        else:
            # 多份发函件 → 必须指定
            if paired_outbound_id is None:
                raise ValueError("有多份发函件时须指定配对发函件")
            # 验证 paired_outbound_id 指向同函证的 outbound 附件
            valid_outbound_att_ids = {link.attachment_id for link in outbound_links}
            if paired_outbound_id not in valid_outbound_att_ids:
                raise ValueError(
                    f"指定的配对发函件 {paired_outbound_id} 不属于该函证的发函件"
                )
            final_paired_outbound_id = paired_outbound_id
    else:
        # outbound: paired_outbound_id 无意义，置 None
        final_paired_outbound_id = None

    # 创建 link 记录
    link = ConfirmationAttachmentLink(
        confirmation_id=confirmation_id,
        attachment_id=attachment_id,
        role=role,
        paired_outbound_attachment_id=final_paired_outbound_id,
        match_status="manual",
        created_by=actor_user_id,
    )
    db.add(link)

    # 写 action_log（留痕）
    log = ConfirmationActionLog(
        confirmation_id=confirmation_id,
        project_id=confirmation.project_id,
        action="attachment_link",
        attachment_id=attachment_id,
        final_value={"role": role, "paired_outbound_attachment_id": str(final_paired_outbound_id) if final_paired_outbound_id else None},
        actor_user_id=actor_user_id,
    )
    db.add(log)

    # 设置 attachment 的 reference（复用现有挂载机制）
    attachment = await db.get(Attachment, attachment_id)
    if attachment is not None:
        attachment.reference_type = "confirmation_list"
        attachment.reference_id = confirmation_id

    await db.flush()
    return link


# ---------------------------------------------------------------------------
# unlink_attachment
# ---------------------------------------------------------------------------


async def unlink_attachment(
    db: AsyncSession,
    *,
    link_id: uuid.UUID,
    actor_user_id: uuid.UUID,
) -> None:
    """解绑附件（清 reference，删 link 行，不物理删附件，留痕）。"""
    link = await db.get(ConfirmationAttachmentLink, link_id)
    if link is None:
        raise ValueError(f"挂载记录不存在: {link_id}")

    # 获取 confirmation 的 project_id
    confirmation = await db.get(Confirmation, link.confirmation_id)
    project_id = confirmation.project_id if confirmation else link.confirmation_id

    # 清 attachment reference
    attachment = await db.get(Attachment, link.attachment_id)
    if attachment is not None:
        attachment.reference_type = None
        attachment.reference_id = None

    # 写 action_log
    log = ConfirmationActionLog(
        confirmation_id=link.confirmation_id,
        project_id=project_id,
        action="attachment_unlink",
        attachment_id=link.attachment_id,
        final_value={"role": link.role, "link_id": str(link_id)},
        actor_user_id=actor_user_id,
    )
    db.add(log)

    # 删 link 记录
    await db.delete(link)
    await db.flush()


# ---------------------------------------------------------------------------
# list_attachments
# ---------------------------------------------------------------------------


async def list_attachments(
    db: AsyncSession,
    confirmation_id: uuid.UUID,
) -> list[dict[str, Any]]:
    """返回该函证的全部附件（含角色/配对/OCR 状态/文件信息）。"""
    q = (
        select(
            ConfirmationAttachmentLink.id.label("link_id"),
            ConfirmationAttachmentLink.role,
            ConfirmationAttachmentLink.paired_outbound_attachment_id,
            ConfirmationAttachmentLink.match_status,
            ConfirmationAttachmentLink.created_at.label("link_created_at"),
            Attachment.id.label("attachment_id"),
            Attachment.file_name,
            Attachment.created_at.label("upload_time"),
            Attachment.ocr_status,
        )
        .join(
            Attachment,
            ConfirmationAttachmentLink.attachment_id == Attachment.id,
        )
        .where(ConfirmationAttachmentLink.confirmation_id == confirmation_id)
        .order_by(ConfirmationAttachmentLink.created_at)
    )
    result = await db.execute(q)
    rows = result.all()

    return [
        {
            "link_id": str(row.link_id),
            "attachment_id": str(row.attachment_id),
            "role": row.role,
            "paired_outbound_attachment_id": str(row.paired_outbound_attachment_id) if row.paired_outbound_attachment_id else None,
            "match_status": row.match_status,
            "file_name": row.file_name,
            "upload_time": row.upload_time.isoformat() if row.upload_time else None,
            "ocr_status": row.ocr_status,
            "link_created_at": row.link_created_at.isoformat() if row.link_created_at else None,
        }
        for row in rows
    ]


# ---------------------------------------------------------------------------
# list_attachment_counts
# ---------------------------------------------------------------------------


async def list_attachment_counts(
    db: AsyncSession,
    confirmation_ids: list[uuid.UUID],
) -> dict[str, dict[str, int]]:
    """批量返回每笔函证的发函件/回函件计数（单次 GROUP BY 查询，免 N+1）。

    返回: {confirmation_id_str: {"outbound": N, "inbound": M}}
    未在结果中出现的 confirmation_id 意味着 0/0。
    """
    if not confirmation_ids:
        return {}

    q = (
        select(
            ConfirmationAttachmentLink.confirmation_id,
            ConfirmationAttachmentLink.role,
            func.count().label("cnt"),
        )
        .where(ConfirmationAttachmentLink.confirmation_id.in_(confirmation_ids))
        .group_by(
            ConfirmationAttachmentLink.confirmation_id,
            ConfirmationAttachmentLink.role,
        )
    )
    result = await db.execute(q)
    rows = result.all()

    counts: dict[str, dict[str, int]] = {}
    for row in rows:
        cid_str = str(row.confirmation_id)
        if cid_str not in counts:
            counts[cid_str] = {"outbound": 0, "inbound": 0}
        if row.role in ("outbound", "inbound"):
            counts[cid_str][row.role] = row.cnt

    return counts


# ---------------------------------------------------------------------------
# extract_and_compare
# ---------------------------------------------------------------------------

# 默认容差：|diff| <= 0.01 元
_DEFAULT_TOLERANCE: Decimal = Decimal("0.01")


async def extract_and_compare(
    db: AsyncSession,
    attachment_id: uuid.UUID,
    *,
    tolerance: Decimal = _DEFAULT_TOLERANCE,
) -> dict[str, Any]:
    """OCR 识别回函件 + 与所属函证 book_amount 比对。

    1. 调 extract_confirmation_reply（算法不改）抽取 reply_amount/reply_date/reply_entity/confidence
    2. 经 confirmation_attachment_link 找所属函证
    3. 比对：
       - diff = book_amount − reply_amount
       - |diff| <= tolerance → matched
       - 否则 → discrepancy
       - 任一缺失 → low_confidence（永不产生虚假"相符"）
    4. 主体名称比对：reply_entity != counterparty → counterparty_mismatch = True
    5. 结果写 attachment.ocr_fields_cache（仅此处，不写 confirmations）
    6. 恒 governed=False / requires_human_confirmation=True

    返回比对结果 dict。
    """
    # ── Step 1: 调用 OCR 抽取（算法不改） ──
    svc = AttachmentService(db)
    ocr_result = await svc.extract_confirmation_reply(attachment_id)

    reply_amount = ocr_result.get("reply_amount")
    reply_date = ocr_result.get("reply_date")
    reply_entity = ocr_result.get("reply_entity")
    confidence = ocr_result.get("confidence", "low")

    # ── Step 2: 查找所属函证（经 confirmation_attachment_link） ──
    link_q = select(ConfirmationAttachmentLink).where(
        ConfirmationAttachmentLink.attachment_id == attachment_id
    )
    link_result = await db.execute(link_q)
    link = link_result.scalar_one_or_none()

    if link is None:
        # 附件未挂载到任何函证 → 无法比对
        comparison = _build_result(
            reply_amount=reply_amount,
            reply_date=reply_date,
            reply_entity=reply_entity,
            confidence=confidence,
            diff=None,
            match_verdict="low_confidence",
            counterparty_mismatch=None,
        )
        await _write_ocr_cache(db, attachment_id, comparison)
        return comparison

    confirmation = await db.get(Confirmation, link.confirmation_id)
    if confirmation is None:
        comparison = _build_result(
            reply_amount=reply_amount,
            reply_date=reply_date,
            reply_entity=reply_entity,
            confidence=confidence,
            diff=None,
            match_verdict="low_confidence",
            counterparty_mismatch=None,
        )
        await _write_ocr_cache(db, attachment_id, comparison)
        return comparison

    book_amount = confirmation.book_amount
    counterparty = confirmation.counterparty

    # ── Step 3: 金额比对 ──
    if book_amount is None or reply_amount is None:
        # 任一缺失 → 永不产生"相符"结论
        diff = None
        match_verdict = "low_confidence"
    else:
        diff = float(Decimal(str(book_amount)) - Decimal(str(reply_amount)))
        if abs(diff) <= float(tolerance):
            match_verdict = "matched"
        else:
            match_verdict = "discrepancy"

    # ── Step 4: 主体名称比对 ──
    if reply_entity is None or counterparty is None:
        counterparty_mismatch = None
    else:
        counterparty_mismatch = reply_entity.strip() != counterparty.strip()

    # ── Step 5: 构建结果 + 写 ocr_fields_cache ──
    comparison = _build_result(
        reply_amount=reply_amount,
        reply_date=reply_date,
        reply_entity=reply_entity,
        confidence=confidence,
        diff=diff,
        match_verdict=match_verdict,
        counterparty_mismatch=counterparty_mismatch,
    )
    await _write_ocr_cache(db, attachment_id, comparison)

    return comparison


def _build_result(
    *,
    reply_amount: float | None,
    reply_date: str | None,
    reply_entity: str | None,
    confidence: str,
    diff: float | None,
    match_verdict: str,
    counterparty_mismatch: bool | None,
) -> dict[str, Any]:
    """构建 OCR 比对结果 dict（governed=False 恒定）。"""
    return {
        "reply_amount": reply_amount,
        "reply_date": reply_date,
        "reply_entity": reply_entity,
        "confidence": confidence,
        "diff": diff,
        "match_verdict": match_verdict,
        "counterparty_mismatch": counterparty_mismatch,
        "governed": False,
        "requires_human_confirmation": True,
    }


async def _write_ocr_cache(
    db: AsyncSession,
    attachment_id: uuid.UUID,
    comparison: dict[str, Any],
) -> None:
    """将比对结果写入 attachment.ocr_fields_cache（不写 confirmations）。"""
    attachment = await db.get(Attachment, attachment_id)
    if attachment is not None:
        attachment.ocr_fields_cache = comparison
        await db.flush()


# ---------------------------------------------------------------------------
# apply_reply（人工确认回填）
# ---------------------------------------------------------------------------

# 合法终态集合（用户确认最终状态须在此集合内）
_VALID_TERMINAL_STATUSES: set[str] = {"matched", "discrepancy"}


# ---------------------------------------------------------------------------
# auto_match — 回函自动匹配发函记录
# ---------------------------------------------------------------------------


async def auto_match(
    db: AsyncSession,
    *,
    project_id: uuid.UUID,
    attachment_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    tolerance: Decimal = _DEFAULT_TOLERANCE,
) -> dict[str, Any]:
    """按 OCR 主体名称 + 金额容差 + 可选函证编号匹配 status∈{sent,returned} 记录。

    结果三态：
    - 唯一命中 → 自动挂载（link_attachment role=inbound + 绑发函件 + match_status=auto）
    - 多义命中 → 返回候选列表，不挂载
    - 无命中 → 创建 pending link（入人工匹配队列）

    匹配依据记入 match_evidence（可解释）。
    只 flush 不 commit。
    """
    # ── Step 1: 读 OCR 结果 ──
    from app.models.attachment_models import Attachment

    attachment = await db.get(Attachment, attachment_id)
    if attachment is None:
        raise ValueError(f"附件不存在: {attachment_id}")

    ocr_cache: dict[str, Any] = attachment.ocr_fields_cache or {}
    reply_entity: str | None = ocr_cache.get("reply_entity")
    reply_amount: float | None = ocr_cache.get("reply_amount")

    # ── Step 2: 查候选函证（project 下 status∈{sent,returned}） ──
    candidates_q = select(Confirmation).where(
        and_(
            Confirmation.project_id == project_id,
            Confirmation.status.in_(["sent", "returned"]),
        )
    )
    result = await db.execute(candidates_q)
    candidates: list[Confirmation] = list(result.scalars().all())

    if not candidates:
        # 无候选 → 入队列
        return _enter_pending_queue(db, attachment_id, actor_user_id, project_id)

    # ── Step 3: 匹配逻辑 ──
    matches: list[tuple[Confirmation, dict[str, Any]]] = []

    for conf in candidates:
        evidence: dict[str, Any] = {
            "counterparty_matched": False,
            "amount_within_tolerance": False,
            "matched_by": None,
            "confidence": "low",
        }

        # 3a: 主体名称匹配（精确 → 模糊/包含）
        counterparty_hit = False
        if reply_entity and conf.counterparty:
            re_clean = reply_entity.strip()
            cp_clean = conf.counterparty.strip()
            if re_clean == cp_clean:
                counterparty_hit = True
                evidence["matched_by"] = "counterparty_exact"
                evidence["confidence"] = "high"
            elif re_clean in cp_clean or cp_clean in re_clean:
                counterparty_hit = True
                evidence["matched_by"] = "counterparty_fuzzy"
                evidence["confidence"] = "medium"

        evidence["counterparty_matched"] = counterparty_hit

        # 3b: 金额容差匹配
        amount_hit = False
        if reply_amount is not None and conf.book_amount is not None:
            diff = abs(Decimal(str(conf.book_amount)) - Decimal(str(reply_amount)))
            if diff <= tolerance:
                amount_hit = True
                evidence["amount_within_tolerance"] = True
                # 如果名称没匹配到，金额匹配可作为依据
                if not counterparty_hit:
                    evidence["matched_by"] = "amount"
                    evidence["confidence"] = "medium"

        # 判定：主体命中 或 金额命中 → 视为候选
        if counterparty_hit or amount_hit:
            matches.append((conf, evidence))

    # ── Step 4: 处理结果 ──
    if len(matches) == 1:
        # 唯一命中 → 自动挂载
        matched_conf, evidence = matches[0]
        return await _auto_link(
            db,
            confirmation=matched_conf,
            attachment_id=attachment_id,
            actor_user_id=actor_user_id,
            match_evidence=evidence,
        )
    elif len(matches) > 1:
        # 多义 → 返回候选列表，不挂载
        return {
            "result": "ambiguous",
            "candidates": [
                {
                    "confirmation_id": str(conf.id),
                    "counterparty": conf.counterparty,
                    "book_amount": float(conf.book_amount) if conf.book_amount else None,
                    "status": conf.status,
                    "match_evidence": ev,
                }
                for conf, ev in matches
            ],
            "attachment_id": str(attachment_id),
        }
    else:
        # 无命中 → 入队列
        return _enter_pending_queue(db, attachment_id, actor_user_id, project_id)


def _enter_pending_queue(
    db: AsyncSession,
    attachment_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    project_id: uuid.UUID,
) -> dict[str, Any]:
    """无命中 → 返回 pending 状态。

    不创建 link 记录（confirmation_id 是 NOT NULL FK，无法存无效值）。
    人工匹配队列通过 list_match_queue 查找"无已挂载 link 的回函件附件"实现。
    附件的 reference_type 设为 confirmation_list 但 reference_id 留空，
    标记该附件属于函证模块但未关联到具体函证。
    """
    return {
        "result": "no_match",
        "match_status": "pending",
        "attachment_id": str(attachment_id),
        "project_id": str(project_id),
    }


async def _auto_link(
    db: AsyncSession,
    *,
    confirmation: Confirmation,
    attachment_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    match_evidence: dict[str, Any],
) -> dict[str, Any]:
    """唯一命中：挂载 + 绑发函件 + 记 match_evidence。"""
    # 查该函证的发函件（绑发函件逻辑复用 link_attachment 的规则）
    outbound_q = select(ConfirmationAttachmentLink).where(
        and_(
            ConfirmationAttachmentLink.confirmation_id == confirmation.id,
            ConfirmationAttachmentLink.role == "outbound",
        )
    )
    result = await db.execute(outbound_q)
    outbound_links = result.scalars().all()

    # 确定 paired_outbound_attachment_id
    paired_outbound_id: uuid.UUID | None = None
    if len(outbound_links) == 1:
        paired_outbound_id = outbound_links[0].attachment_id
    elif len(outbound_links) > 1:
        # 多份发函件 → 自动匹配无法选择，取第一份（或留空由人工补选）
        paired_outbound_id = outbound_links[0].attachment_id

    # 创建 link
    link = ConfirmationAttachmentLink(
        confirmation_id=confirmation.id,
        attachment_id=attachment_id,
        role="inbound",
        paired_outbound_attachment_id=paired_outbound_id,
        match_status="auto",
        match_evidence=match_evidence,
        created_by=actor_user_id,
    )
    db.add(link)

    # 设置 attachment reference
    attachment = await db.get(Attachment, attachment_id)
    if attachment is not None:
        attachment.reference_type = "confirmation_list"
        attachment.reference_id = confirmation.id

    # 写 action_log
    log = ConfirmationActionLog(
        confirmation_id=confirmation.id,
        project_id=confirmation.project_id,
        action="attachment_link",
        attachment_id=attachment_id,
        final_value={
            "role": "inbound",
            "paired_outbound_attachment_id": str(paired_outbound_id) if paired_outbound_id else None,
            "match_status": "auto",
            "match_evidence": match_evidence,
        },
        actor_user_id=actor_user_id,
    )
    db.add(log)

    await db.flush()

    return {
        "result": "unique_match",
        "confirmation_id": str(confirmation.id),
        "counterparty": confirmation.counterparty,
        "book_amount": float(confirmation.book_amount) if confirmation.book_amount else None,
        "match_status": "auto",
        "match_evidence": match_evidence,
        "attachment_id": str(attachment_id),
        "paired_outbound_attachment_id": str(paired_outbound_id) if paired_outbound_id else None,
    }


# ---------------------------------------------------------------------------
# list_match_queue — 列出未匹配回函件（待人工指派）
# ---------------------------------------------------------------------------


async def list_match_queue(
    db: AsyncSession,
    project_id: uuid.UUID,
) -> list[dict[str, Any]]:
    """列出项目下待人工指派的回函件附件。

    包含两类：
    1. 有 link 且 match_status='pending' 的（历史数据兼容）
    2. attachment_type='confirmation' 且 reference_type='confirmation_list'
       但无对应 ConfirmationAttachmentLink 记录的（auto_match 无命中）

    返回 link 记录/附件信息，供人工匹配队列 UI 使用。
    """
    results: list[dict[str, Any]] = []

    # 路径 1: 已有 link 且 match_status='pending'
    pending_q = (
        select(
            ConfirmationAttachmentLink.id.label("link_id"),
            ConfirmationAttachmentLink.attachment_id,
            ConfirmationAttachmentLink.match_status,
            ConfirmationAttachmentLink.match_evidence,
            ConfirmationAttachmentLink.created_at.label("link_created_at"),
            Attachment.file_name,
            Attachment.ocr_status,
            Attachment.ocr_fields_cache,
        )
        .join(
            Attachment,
            ConfirmationAttachmentLink.attachment_id == Attachment.id,
        )
        .join(
            Confirmation,
            ConfirmationAttachmentLink.confirmation_id == Confirmation.id,
        )
        .where(
            and_(
                ConfirmationAttachmentLink.match_status == "pending",
                Confirmation.project_id == project_id,
            )
        )
        .order_by(ConfirmationAttachmentLink.created_at.desc())
    )
    result = await db.execute(pending_q)
    rows = result.all()

    for row in rows:
        results.append({
            "link_id": str(row.link_id),
            "attachment_id": str(row.attachment_id),
            "match_status": row.match_status,
            "match_evidence": row.match_evidence,
            "file_name": row.file_name,
            "ocr_status": row.ocr_status,
            "ocr_fields_cache": row.ocr_fields_cache,
            "link_created_at": row.link_created_at.isoformat() if row.link_created_at else None,
        })

    # 路径 2: confirmation 类型附件在项目内但无 link（auto_match no-hit 不建 link 的情况）
    # 子查询：已有 link 的 attachment_id 集合
    linked_att_ids_sq = (
        select(ConfirmationAttachmentLink.attachment_id)
        .distinct()
        .scalar_subquery()
    )
    # 查项目下函证的 id 集合
    project_conf_ids_sq = (
        select(Confirmation.id)
        .where(Confirmation.project_id == project_id)
        .scalar_subquery()
    )
    unlinked_q = (
        select(
            Attachment.id.label("attachment_id"),
            Attachment.file_name,
            Attachment.ocr_status,
            Attachment.ocr_fields_cache,
            Attachment.created_at.label("upload_time"),
        )
        .where(
            and_(
                Attachment.reference_type == "confirmation_list",
                Attachment.reference_id.in_(project_conf_ids_sq),
                Attachment.id.notin_(linked_att_ids_sq),
            )
        )
        .order_by(Attachment.created_at.desc())
    )
    unlinked_result = await db.execute(unlinked_q)
    unlinked_rows = unlinked_result.all()

    for row in unlinked_rows:
        results.append({
            "link_id": None,
            "attachment_id": str(row.attachment_id),
            "match_status": "pending",
            "match_evidence": None,
            "file_name": row.file_name,
            "ocr_status": row.ocr_status,
            "ocr_fields_cache": row.ocr_fields_cache,
            "link_created_at": row.upload_time.isoformat() if row.upload_time else None,
        })

    return results


# ---------------------------------------------------------------------------
# assign_match — 人工指派队列回函件到某函证
# ---------------------------------------------------------------------------


async def assign_match(
    db: AsyncSession,
    *,
    attachment_id: uuid.UUID,
    confirmation_id: uuid.UUID,
    paired_outbound_id: uuid.UUID | None = None,
    actor_user_id: uuid.UUID,
) -> dict[str, Any]:
    """人工把队列中的回函件指派到指定函证 + 绑发函件。

    如果有既有 pending link → 更新其 confirmation_id/paired/match_status。
    如果无既有 link（auto_match no-hit 不建 link）→ 创建新 link。
    写 action_log（action='match_assign'）。
    只 flush 不 commit。
    """
    # 查找该附件的既有 pending link（可能不存在）
    link_q = select(ConfirmationAttachmentLink).where(
        and_(
            ConfirmationAttachmentLink.attachment_id == attachment_id,
            ConfirmationAttachmentLink.match_status == "pending",
        )
    )
    result = await db.execute(link_q)
    link = result.scalar_one_or_none()

    # 获取函证记录
    confirmation = await db.get(Confirmation, confirmation_id)
    if confirmation is None:
        raise ValueError(f"函证记录不存在: {confirmation_id}")

    # 确定 paired_outbound_attachment_id（复用 link_attachment 逻辑）
    final_paired_outbound_id: uuid.UUID | None = paired_outbound_id
    if final_paired_outbound_id is None:
        # 尝试自动绑定：查该函证的 outbound 附件
        outbound_q = select(ConfirmationAttachmentLink).where(
            and_(
                ConfirmationAttachmentLink.confirmation_id == confirmation_id,
                ConfirmationAttachmentLink.role == "outbound",
            )
        )
        ob_result = await db.execute(outbound_q)
        outbound_links = ob_result.scalars().all()

        if len(outbound_links) == 1:
            final_paired_outbound_id = outbound_links[0].attachment_id
        elif len(outbound_links) > 1:
            raise ValueError("有多份发函件时须指定配对发函件")
        # 0 份发函件时，允许不绑（assign 时可能先挂再补发函件）

    if link is not None:
        # 更新既有 link
        link.confirmation_id = confirmation_id
        link.paired_outbound_attachment_id = final_paired_outbound_id
        link.match_status = "assigned"
    else:
        # 创建新 link（auto_match no-hit 未建 link 的情况）
        link = ConfirmationAttachmentLink(
            confirmation_id=confirmation_id,
            attachment_id=attachment_id,
            role="inbound",
            paired_outbound_attachment_id=final_paired_outbound_id,
            match_status="assigned",
            match_evidence={"reason": "manual_assignment"},
            created_by=actor_user_id,
        )
        db.add(link)

    # 设置 attachment reference
    attachment = await db.get(Attachment, attachment_id)
    if attachment is not None:
        attachment.reference_type = "confirmation_list"
        attachment.reference_id = confirmation_id

    # 写 action_log
    log = ConfirmationActionLog(
        confirmation_id=confirmation_id,
        project_id=confirmation.project_id,
        action="match_assign",
        attachment_id=attachment_id,
        final_value={
            "role": "inbound",
            "paired_outbound_attachment_id": str(final_paired_outbound_id) if final_paired_outbound_id else None,
            "match_status": "assigned",
            "assigned_by": str(actor_user_id),
        },
        actor_user_id=actor_user_id,
    )
    db.add(log)

    await db.flush()

    return {
        "link_id": str(link.id),
        "confirmation_id": str(confirmation_id),
        "attachment_id": str(attachment_id),
        "paired_outbound_attachment_id": str(final_paired_outbound_id) if final_paired_outbound_id else None,
        "match_status": "assigned",
    }


# ---------------------------------------------------------------------------
# apply_reply（人工确认回填）
# ---------------------------------------------------------------------------


async def apply_reply(
    db: AsyncSession,
    *,
    confirmation_id: uuid.UUID,
    attachment_id: uuid.UUID,
    confirmed_amount: float,
    reply_date: str | None,  # ISO date string
    target_status: str,  # 'matched' or 'discrepancy', user decides
    actor_user_id: uuid.UUID,
    tolerance: Decimal = _DEFAULT_TOLERANCE,
) -> dict[str, Any]:
    """人工确认后回填台账。

    1. 加载函证记录（校验存在）
    2. 加载 OCR 原值（从 attachment.ocr_fields_cache，可能为空）
    3. 写 confirmed_amount / reply_date / diff_amount 到函证记录
    4. 置 status = target_status（用户确认值，非系统自动定终态）
    5. 写 confirmation_action_log（action=apply_reply，保留 OCR 原值 + 最终落库值双值留痕）
    6. 发布状态变化事件（复用现有 event_bus 下游刷新链）
    7. 返回结果 dict（含建议状态 + 实际状态 + diff 等）

    只 flush 不 commit（router 统一 commit）。
    """
    # ── Step 1: 加载函证记录 ──
    confirmation = await db.get(Confirmation, confirmation_id)
    if confirmation is None:
        raise ValueError(f"函证记录不存在: {confirmation_id}")

    # ── Step 2: 校验 target_status 合法 ──
    if target_status not in _VALID_TERMINAL_STATUSES:
        raise ValueError(
            f"target_status 必须为 {_VALID_TERMINAL_STATUSES}，收到: {target_status}"
        )

    # ── Step 3: 加载 OCR 原值（从 attachment.ocr_fields_cache） ──
    ocr_original: dict[str, Any] | None = None
    attachment = await db.get(Attachment, attachment_id)
    if attachment is not None and attachment.ocr_fields_cache:
        ocr_original = dict(attachment.ocr_fields_cache)

    # ── Step 4: 计算 diff_amount = book_amount − confirmed_amount ──
    book_amount = confirmation.book_amount
    if book_amount is not None:
        diff_amount = float(Decimal(str(book_amount)) - Decimal(str(confirmed_amount)))
    else:
        diff_amount = None

    # ── Step 5: 建议逻辑（仅建议，最终由入参 target_status 定） ──
    if diff_amount is not None and abs(diff_amount) <= float(tolerance):
        suggested_status = "matched"
    elif diff_amount is not None:
        suggested_status = "discrepancy"
    else:
        # book_amount 缺失，无法判定，建议 discrepancy（保守）
        suggested_status = "discrepancy"

    # ── Step 6: 写入 confirmed_amount / reply_date / diff_amount / status ──
    confirmation.confirmed_amount = confirmed_amount
    confirmation.diff_amount = diff_amount
    if reply_date is not None:
        confirmation.reply_date = reply_date
    confirmation.status = target_status

    # ── Step 7: 构建 final_value（最终落库值） ──
    final_value: dict[str, Any] = {
        "confirmed_amount": confirmed_amount,
        "reply_date": reply_date,
        "diff_amount": diff_amount,
        "status": target_status,
    }

    # ── Step 8: 写 confirmation_action_log（双值留痕） ──
    log = ConfirmationActionLog(
        confirmation_id=confirmation_id,
        project_id=confirmation.project_id,
        action="apply_reply",
        from_status=None,  # apply_reply 不记录状态转换方向
        to_status=target_status,
        ocr_original=ocr_original,
        final_value=final_value,
        attachment_id=attachment_id,
        actor_user_id=actor_user_id,
    )
    db.add(log)

    await db.flush()

    # ── Step 9: 发布状态变化事件（复用现有 event_bus 下游刷新链） ──
    try:
        from app.services.event_bus import event_bus
        from app.models.audit_platform_schemas import EventPayload, EventType

        await event_bus.publish_immediate(EventPayload(
            event_type=EventType.WORKPAPER_SAVED,
            project_id=confirmation.project_id,
            extra={
                "source": "apply_reply",
                "confirmation_id": str(confirmation_id),
                "status": target_status,
                "confirmed_amount": confirmed_amount,
            },
        ))
    except Exception:
        # 事件发布失败不阻断主动作（best-effort）
        pass

    # ── Step 10: 返回结果 ──
    return {
        "confirmation_id": str(confirmation_id),
        "attachment_id": str(attachment_id),
        "confirmed_amount": confirmed_amount,
        "reply_date": reply_date,
        "diff_amount": diff_amount,
        "book_amount": float(book_amount) if book_amount is not None else None,
        "suggested_status": suggested_status,
        "actual_status": target_status,
        "ocr_original": ocr_original,
        "final_value": final_value,
    }
