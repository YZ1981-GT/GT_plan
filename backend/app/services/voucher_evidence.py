"""凭证证据：按凭证身份挂原件、跨底稿查询与引用、抽凭样本逐笔统计（spec attachment-voucher-evidence-binding）。

凭证检查行的原件（记账凭证、发票、回单等）挂在证据链接上，链接带凭证键（``evidence_links.voucher_key``，
ADR-AVE-01）。同一张凭证被多张底稿抽到时：

- :func:`voucher_evidence_by_keys`：按凭证键查本项目各底稿已取得的凭证证据，只列当前用户可见的底稿（ADR-AVE-07）；
- :func:`reuse_voucher_evidence`：把另一张可见底稿上同一凭证的证据附件引用到本底稿（不复制文件，ADR-AVE-02）；
- :func:`voucher_sample_breakdown`：本底稿登记的抽凭样本（抽凭批次 + 挂凭）里取得了凭证证据的笔数与缺证据清单
  （「凭证」类声明的逐笔统计，只展示、不改声明口径，ADR-AVE-06）。

旧登记（V210 前）没记主体或凭证字的那一列按通配比，与 ``voucher-links/query`` 同口径；没记日期的说不清是哪一张，
计为缺证据并注明。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.voucher_identity import VoucherKey, norm_text, voucher_label

#: 凭证键规范串的长度上限（年度 + 主体名称 + 日期 + 凭证字 + 号的 JSON；超过即视为异常输入）
MAX_VOUCHER_KEY_LEN = 600
#: 他稿查询单次最多这么多个凭证键（与 voucher-links/query 同上限）
MAX_QUERY_KEYS = 500
#: 带凭证键而未指定类型时的证据类型（ADR-AVE-05）
VOUCHER_EVIDENCE_TYPE = "voucher"
#: 逐笔统计里缺证据清单最多列这么多笔
MISSING_ITEMS_LIMIT = 50
REASON_NO_DATE = "旧登记缺凭证日期，无法对应到凭证"


def normalize_voucher_key(raw: Any) -> str | None:
    """空 ⇒ None；格式错 / 日期不可解析 / 凭证号为空 / 过长 ⇒ 400；否则返回规范串。"""
    text = "" if raw is None else str(raw).strip()
    if not text:
        return None
    if len(text) > MAX_VOUCHER_KEY_LEN:
        raise HTTPException(status_code=400, detail="凭证键过长")
    try:
        vk = VoucherKey.from_str(text)
        vk.date_value  # noqa: B018 — 校验日期可解析
    except ValueError:
        raise HTTPException(status_code=400, detail="凭证键格式错误")
    if not vk.voucher_no:
        raise HTTPException(status_code=400, detail="凭证键缺少凭证号")
    return vk.to_str()


def voucher_key_label(text: str | None) -> str:
    """凭证键串 → 「2025-01-07 FY-0003」；解析不了原样返回。"""
    try:
        return voucher_label(VoucherKey.from_str(text or ""))
    except ValueError:
        return text or ""


async def _visible_wp_ids(db: AsyncSession, user: Any, wp_ids: set[UUID]) -> set[UUID]:
    """逐张过底稿可见性（附件读口径，与附件关联底稿清单同一判定）；拒绝的不报错、只是不列。"""
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


# ─── 跨底稿查询与引用 ─────────────────────────────────────────────────────────


def _evidence_rows_stmt(project_id: UUID):
    from app.models.attachment_models import Attachment
    from app.models.workpaper_models import WorkingPaper, WpIndex
    from app.models.wp_optimization_models import EvidenceLink

    return (
        sa.select(
            EvidenceLink.voucher_key, EvidenceLink.wp_id, EvidenceLink.evidence_type,
            WpIndex.wp_code, WpIndex.wp_name,
            Attachment.id.label("attachment_id"), Attachment.file_name, Attachment.file_type, Attachment.ocr_status,
        )
        .join(Attachment, Attachment.id == EvidenceLink.attachment_id)
        .join(WorkingPaper, WorkingPaper.id == EvidenceLink.wp_id)
        .outerjoin(WpIndex, WpIndex.id == WorkingPaper.wp_index_id)
        .where(
            EvidenceLink.voucher_key.is_not(None),
            WorkingPaper.project_id == project_id,
            WorkingPaper.is_deleted == sa.false(),
            Attachment.project_id == project_id,
            Attachment.is_deleted == sa.false(),
        )
        .order_by(WpIndex.wp_code, EvidenceLink.created_at, EvidenceLink.id)
    )


async def voucher_evidence_by_keys(
    db: AsyncSession, user: Any, project_id: UUID, year: int, keys: list[str],
) -> dict[str, list[dict]]:
    """凭证键 → [{底稿, attachments: [...]}]：本项目各底稿已取得的凭证证据，只列当前用户可见的底稿。

    年度与 ``year`` 不符、格式错的键丢弃（不报错，与 voucher-links/query 同口径）；附件已删除、底稿已删除的不列。
    """
    if len(keys) > MAX_QUERY_KEYS:
        raise HTTPException(status_code=422, detail={
            "error_code": "TOO_MANY_VOUCHER_KEYS",
            "message": f"一次最多查 {MAX_QUERY_KEYS} 个凭证键，本次 {len(keys)} 个",
        })
    wanted: set[str] = set()
    for raw in keys:
        try:
            vk = VoucherKey.from_str(str(raw))
        except ValueError:
            continue
        if vk.year == str(year) and vk.voucher_no:
            wanted.add(vk.to_str())
    if not wanted:
        return {}
    from app.models.wp_optimization_models import EvidenceLink

    rows = (await db.execute(
        _evidence_rows_stmt(project_id).where(EvidenceLink.voucher_key.in_(sorted(wanted)))
    )).all()
    visible = await _visible_wp_ids(db, user, {r.wp_id for r in rows})
    out: dict[str, dict[UUID, dict]] = {}
    for r in rows:
        if r.wp_id not in visible:
            continue
        entry = out.setdefault(r.voucher_key, {}).setdefault(r.wp_id, {
            "working_paper_id": str(r.wp_id), "wp_code": r.wp_code, "wp_name": r.wp_name, "attachments": [],
        })
        if any(a["id"] == str(r.attachment_id) for a in entry["attachments"]):
            continue  # 同一附件在同一底稿有多个位置（本行 + 同凭证另一行）只列一次
        entry["attachments"].append({
            "id": str(r.attachment_id), "file_name": r.file_name, "file_type": r.file_type,
            "ocr_status": r.ocr_status, "evidence_type": r.evidence_type,
        })
    return {vk: list(by_wp.values()) for vk, by_wp in out.items()}


async def reuse_voucher_evidence(
    db: AsyncSession, user: Any, wp: Any, voucher_key: str, attachment_id: UUID,
) -> tuple[dict, bool]:
    """把另一张可见底稿上同一凭证的证据附件引用到本底稿（凭证级链接，只 flush）。返回（链接, 是否已存在）。

    源须是同项目另一张未删除底稿上、凭证键相同、附件未删除的链接，且该底稿对当前用户可见；否则 404（不区分
    不存在与看不到）。本底稿的可写与归档由调用方先判。
    """
    from app.models.wp_optimization_models import EvidenceLink
    from app.services.wp_evidence_service import WpEvidenceService

    vk = normalize_voucher_key(voucher_key)
    if vk is None:
        raise HTTPException(status_code=400, detail="缺少凭证键")
    sources = (await db.execute(
        _evidence_rows_stmt(wp.project_id).where(
            EvidenceLink.voucher_key == vk, EvidenceLink.attachment_id == attachment_id, EvidenceLink.wp_id != wp.id,
        )
    )).all()
    visible = await _visible_wp_ids(db, user, {r.wp_id for r in sources})
    source = next((r for r in sources if r.wp_id in visible), None)
    if source is None:
        raise HTTPException(status_code=404, detail="其他底稿上没有这张凭证的这份证据，或你无权查看")
    return await WpEvidenceService(db).create_voucher_link(
        wp_id=wp.id, attachment_id=attachment_id, created_by=user.id, voucher_key=vk,
        evidence_type=source.evidence_type or VOUCHER_EVIDENCE_TYPE,
    )


# ─── 抽凭样本逐笔统计 ─────────────────────────────────────────────────────────


@dataclass
class _Sample:
    """一笔登记样本（同一凭证被几个批次 / 挂凭登记只算一笔）。``company`` / ``vtype`` 为 None = 旧登记没记、按通配比。"""

    year: str
    company: str | None
    vdate: str | None
    vtype: str | None
    no: str
    phase: str | None = None
    sources: set[str] = field(default_factory=set)

    @property
    def key(self) -> VoucherKey:
        return VoucherKey.of(year=self.year, company_code=self.company, voucher_date=self.vdate,
                             voucher_type=self.vtype, voucher_no=self.no)

    def matches(self, vk: VoucherKey) -> bool:
        return (
            self.vdate is not None and vk.year == self.year and vk.voucher_date == self.vdate
            and vk.voucher_no == self.no
            and (self.company is None or vk.company_code == self.company)
            and (self.vtype is None or vk.voucher_type == self.vtype)
        )


def _source_label(sources: set[str]) -> str:
    return "both" if len(sources) > 1 else next(iter(sources), "engine")


async def _registered_samples(db: AsyncSession, project_id: UUID, wp_ids: list[UUID]) -> dict[UUID, list[_Sample]]:
    from app.models.workpaper_models import SampledVoucher

    if not wp_ids:
        return {}
    rows = (await db.execute(
        sa.select(SampledVoucher).where(
            SampledVoucher.project_id == project_id,
            SampledVoucher.working_paper_id.in_(wp_ids),
            SampledVoucher.is_deleted == sa.false(),
        ).order_by(SampledVoucher.voucher_date, SampledVoucher.voucher_no, SampledVoucher.sampled_at)
    )).scalars().all()
    out: dict[UUID, dict[tuple, _Sample]] = {}
    for r in rows:
        company = None if r.company_code is None else norm_text(r.company_code)
        vtype = None if r.voucher_type is None else norm_text(r.voucher_type)
        vdate = r.voucher_date.isoformat() if r.voucher_date else None
        ident = (str(r.year), company, vdate, vtype, norm_text(r.voucher_no))
        sample = out.setdefault(r.working_paper_id, {}).setdefault(ident, _Sample(*ident, phase=r.phase))
        sample.sources.add("engine" if r.batch_id else "attach")
        sample.phase = sample.phase or r.phase
    # 有日期的按日期、号排在前，旧登记缺日期的排最后（与库的 NULL 排序无关）
    return {wid: sorted(by_id.values(), key=lambda s: (s.vdate is None, s.vdate or "", s.no))
            for wid, by_id in out.items()}


async def _wp_voucher_evidence(db: AsyncSession, wp_ids: list[UUID]) -> dict[UUID, list[tuple[VoucherKey, dict]]]:
    from app.models.attachment_models import Attachment
    from app.models.wp_optimization_models import EvidenceLink

    if not wp_ids:
        return {}
    rows = (await db.execute(
        sa.select(EvidenceLink.wp_id, EvidenceLink.voucher_key, Attachment.id, Attachment.file_name)
        .join(Attachment, Attachment.id == EvidenceLink.attachment_id)
        .where(EvidenceLink.wp_id.in_(wp_ids), EvidenceLink.voucher_key.is_not(None), Attachment.is_deleted == sa.false())
        .order_by(EvidenceLink.created_at, EvidenceLink.id)
    )).all()
    out: dict[UUID, list[tuple[VoucherKey, dict]]] = {}
    for wid, raw, att_id, file_name in rows:
        try:
            vk = VoucherKey.from_str(raw)
        except ValueError:
            continue
        out.setdefault(wid, []).append((vk, {"id": str(att_id), "file_name": file_name}))
    return out


def _pair(samples: list[_Sample], evidence: list[tuple[VoucherKey, dict]]) -> list[tuple[_Sample, list[dict]]]:
    paired: list[tuple[_Sample, list[dict]]] = []
    for s in samples:
        files: dict[str, dict] = {}
        for vk, att in evidence:
            if s.matches(vk):
                files.setdefault(att["id"], att)
        paired.append((s, list(files.values())))
    return paired


def _missing_item(s: _Sample) -> dict:
    item = {"voucher_key": s.key.to_str(), "label": voucher_label(s.key), "phase": s.phase,
            "source": _source_label(s.sources)}
    if s.vdate is None:
        item["reason"] = REASON_NO_DATE
    return item


async def voucher_sample_breakdown(db: AsyncSession, project_id: UUID, wp_id: UUID) -> dict | None:
    """本底稿登记样本的凭证证据逐笔统计；没有登记样本 ⇒ None（调用方不附加）。只读。"""
    samples = (await _registered_samples(db, project_id, [wp_id])).get(wp_id) or []
    if not samples:
        return None
    paired = _pair(samples, (await _wp_voucher_evidence(db, [wp_id])).get(wp_id) or [])
    missing = [s for s, files in paired if not files]
    return {
        "total": len(paired), "with_evidence": len(paired) - len(missing), "missing": len(missing),
        "missing_items": [_missing_item(s) for s in missing[:MISSING_ITEMS_LIMIT]],
        "truncated": len(missing) > MISSING_ITEMS_LIMIT,
    }


async def project_sample_evidence(db: AsyncSession, project_id: UUID) -> list[dict]:
    """归档章节用：每张有登记样本的底稿 → 逐笔样本与证据文件（按底稿编码排序）。"""
    from app.models.workpaper_models import SampledVoucher, WorkingPaper, WpIndex

    wps = (await db.execute(
        sa.select(WorkingPaper.id, WpIndex.wp_code, WpIndex.wp_name)
        .join(WpIndex, WpIndex.id == WorkingPaper.wp_index_id)
        .where(
            WorkingPaper.project_id == project_id, WorkingPaper.is_deleted == sa.false(),
            WorkingPaper.id.in_(sa.select(SampledVoucher.working_paper_id).where(
                SampledVoucher.project_id == project_id, SampledVoucher.is_deleted == sa.false(),
            )),
        )
        .order_by(WpIndex.wp_code, WorkingPaper.id)
    )).all()
    ids = [w.id for w in wps]
    samples = await _registered_samples(db, project_id, ids)
    evidence = await _wp_voucher_evidence(db, ids)
    out = []
    for w in wps:
        paired = _pair(samples.get(w.id) or [], evidence.get(w.id) or [])
        out.append({
            "wp_code": w.wp_code, "wp_name": (w.wp_name or "").strip(),
            "samples": [{**_missing_item(s), "files": files} for s, files in paired],
        })
    return out
