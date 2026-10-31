"""合同证据：按合同身份挂原件、跨底稿查询与引用（Spec F FEAT-001 F2/F3）。

合同检查行的原件（合同原件、补充协议等）挂在证据链接上，链接带合同键（``evidence_links.contract_key``，
V232）。同一份合同被多张底稿引用时：

- :func:`contract_evidence_by_keys`：按合同键查本项目各底稿已取得的合同证据，只列当前用户可见的底稿；
- :func:`reuse_contract_evidence`：把另一张可见底稿上同一合同的证据附件引用到本底稿（不复制文件）。

合同键 = ``["合同号", "对方名称"]`` 的 JSON 规范串（空 ⇒ None、格式错 ⇒ 400）。
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

#: 合同键规范串的长度上限
MAX_CONTRACT_KEY_LEN = 600
#: 他稿查询单次最多这么多个合同键
MAX_QUERY_KEYS = 500
#: 带合同键而未指定类型时的证据类型
CONTRACT_EVIDENCE_TYPE = "contract"


def normalize_contract_key(raw: Any) -> str | None:
    """空 ⇒ None；格式错 / 缺合同号 / 过长 ⇒ 400；否则返回 ``["合同号","对方名称"]`` 的规范 JSON。

    接受两种输入：
    - JSON 数组字符串 ``'["HT-001","甲方公司"]'``
    - 直接传合同号字符串 ``'HT-001'``（对方名称为空串）
    """
    text = "" if raw is None else str(raw).strip()
    if not text:
        return None
    if len(text) > MAX_CONTRACT_KEY_LEN:
        raise HTTPException(status_code=400, detail="合同键过长")
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list) and len(parsed) == 2:
            contract_no = str(parsed[0]).strip()
            counterparty = str(parsed[1]).strip()
        else:
            raise ValueError
    except (json.JSONDecodeError, ValueError, TypeError):
        # 回退到纯合同号
        contract_no = text.strip()
        counterparty = ""
    if not contract_no:
        raise HTTPException(status_code=400, detail="合同键缺少合同号")
    return json.dumps([contract_no, counterparty], ensure_ascii=False, separators=(",", ":"))


def contract_key_label(text: str | None) -> str:
    """合同键串 → 「HT-001 / 甲方公司」；解析不了原样返回。"""
    if not text:
        return ""
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list) and len(parsed) == 2:
            no, party = str(parsed[0]).strip(), str(parsed[1]).strip()
            if party:
                return f"{no} / {party}"
            return no
    except (json.JSONDecodeError, ValueError, TypeError):
        pass
    return text


async def _visible_wp_ids(db: AsyncSession, user: Any, wp_ids: set[UUID]) -> set[UUID]:
    """逐张过底稿可见性（与 voucher_evidence 同口径）。"""
    from app.services.wp_visibility.entry_integration import try_gate_wp

    visible: set[UUID] = set()
    for wid in sorted(wp_ids, key=str):
        ctx = await try_gate_wp(
            db, user, entrypoint="attachment.read", action="attach_read", method="GET",
            wp_id=wid, entry_family="attachment",
        )
        if ctx is not None:
            visible.add(wid)
    return visible


def _evidence_rows_stmt(project_id: UUID):
    from app.models.attachment_models import Attachment
    from app.models.workpaper_models import WorkingPaper, WpIndex
    from app.models.wp_optimization_models import EvidenceLink

    return (
        sa.select(
            EvidenceLink.contract_key, EvidenceLink.wp_id, EvidenceLink.evidence_type,
            WpIndex.wp_code, WpIndex.wp_name,
            Attachment.id.label("attachment_id"), Attachment.file_name, Attachment.file_type, Attachment.ocr_status,
        )
        .join(Attachment, Attachment.id == EvidenceLink.attachment_id)
        .join(WorkingPaper, WorkingPaper.id == EvidenceLink.wp_id)
        .outerjoin(WpIndex, WpIndex.id == WorkingPaper.wp_index_id)
        .where(
            EvidenceLink.contract_key.is_not(None),
            WorkingPaper.project_id == project_id,
            WorkingPaper.is_deleted == sa.false(),
            Attachment.project_id == project_id,
            Attachment.is_deleted == sa.false(),
        )
        .order_by(WpIndex.wp_code, EvidenceLink.created_at, EvidenceLink.id)
    )


async def contract_evidence_by_keys(
    db: AsyncSession, user: Any, project_id: UUID, keys: list[str],
) -> dict[str, list[dict]]:
    """合同键 → [{底稿, attachments: [...]}]：本项目各底稿已取得的合同证据，只列当前用户可见的底稿。"""
    if len(keys) > MAX_QUERY_KEYS:
        raise HTTPException(status_code=422, detail={
            "error_code": "TOO_MANY_CONTRACT_KEYS",
            "message": f"一次最多查 {MAX_QUERY_KEYS} 个合同键，本次 {len(keys)} 个",
        })
    wanted: set[str] = set()
    for raw in keys:
        try:
            normalized = normalize_contract_key(raw)
        except HTTPException:
            continue  # 格式错的键丢弃（与 voucher_evidence_by_keys 同口径）
        if normalized is not None:
            wanted.add(normalized)
    if not wanted:
        return {}
    from app.models.wp_optimization_models import EvidenceLink

    rows = (await db.execute(
        _evidence_rows_stmt(project_id).where(EvidenceLink.contract_key.in_(sorted(wanted)))
    )).all()
    visible = await _visible_wp_ids(db, user, {r.wp_id for r in rows})
    out: dict[str, dict[UUID, dict]] = {}
    for r in rows:
        if r.wp_id not in visible:
            continue
        entry = out.setdefault(r.contract_key, {}).setdefault(r.wp_id, {
            "working_paper_id": str(r.wp_id), "wp_code": r.wp_code, "wp_name": r.wp_name, "attachments": [],
        })
        if any(a["id"] == str(r.attachment_id) for a in entry["attachments"]):
            continue
        entry["attachments"].append({
            "id": str(r.attachment_id), "file_name": r.file_name, "file_type": r.file_type,
            "ocr_status": r.ocr_status, "evidence_type": r.evidence_type,
        })
    return {ck: list(by_wp.values()) for ck, by_wp in out.items()}


async def reuse_contract_evidence(
    db: AsyncSession, user: Any, wp: Any, contract_key: str, attachment_id: UUID,
) -> tuple[dict, bool]:
    """把另一张可见底稿上同一合同的证据附件引用到本底稿（合同级链接，只 flush）。返回（链接, 是否已存在）。

    源须是同项目另一张未删除底稿上、合同键相同、附件未删除的链接，且该底稿对当前用户可见；否则 404。
    """
    from app.models.wp_optimization_models import EvidenceLink
    from app.services.wp_evidence_service import WpEvidenceService

    ck = normalize_contract_key(contract_key)
    if ck is None:
        raise HTTPException(status_code=400, detail="缺少合同键")
    sources = (await db.execute(
        _evidence_rows_stmt(wp.project_id).where(
            EvidenceLink.contract_key == ck, EvidenceLink.attachment_id == attachment_id, EvidenceLink.wp_id != wp.id,
        )
    )).all()
    visible = await _visible_wp_ids(db, user, {r.wp_id for r in sources})
    source = next((r for r in sources if r.wp_id in visible), None)
    if source is None:
        raise HTTPException(status_code=404, detail="其他底稿上没有这份合同的这份证据，或你无权查看")
    return await WpEvidenceService(db).create_contract_link(
        wp_id=wp.id, attachment_id=attachment_id, created_by=user.id, contract_key=ck,
        evidence_type=source.evidence_type or CONTRACT_EVIDENCE_TYPE,
    )
