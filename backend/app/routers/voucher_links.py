"""挂凭（序时账手工挑凭证 → 抽样凭证清单 / 底稿凭证检查）：按凭证键并记审计阶段。

spec voucher-identity-writeback-and-audit-phase 任务 6（需求 2.5）、任务 14（需求 5）。前三个端点原在
ledger_penetration.py，整体迁到这里（那个文件已到行数上限），URL 不变：

- ``POST   /api/projects/{project_id}/ledger/sample-voucher``
- ``GET    /api/projects/{project_id}/ledger/sampled-vouchers``
- ``DELETE /api/projects/{project_id}/ledger/sampled-vouchers/{sampled_id}``
- ``POST   /api/projects/{project_id}/ledger/sample-vouchers/batch``：多张凭证 × 多张底稿一次挂，逐条保存点，
  逐条回 created / existed / failed + 原因（任务 14）
- ``POST   /api/projects/{project_id}/ledger/voucher-links/query``：凭证键 → 已挂 / 已抽于哪些底稿（任务 14；
  键里有主体名称，500 个键放进查询串会超过请求行长度上限，所以用请求体）

挂凭的凭证按当前账套定位成一张凭证（凭证键 = 年度 + 主体 + 日期 + 凭证字 + 号）：只给号（或日期 + 号）
却命中多张时 409 VOUCHER_KEY_AMBIGUOUS + 候选，找不到 404。手工侧去重键 = 凭证键 + 目标底稿，与 V210 的
``uq_sampled_voucher_manual_project_year_no`` 同口径（日期 / 主体 / 凭证字按 COALESCE 折叠）；记录保存凭证字、
主体与阶段，回拉按凭证键取分录。阶段是挂凭发生时的事实：已挂的行再挂不改阶段，软删后复活按一次新的挂凭。
"""

from __future__ import annotations

import logging
from collections import Counter
from datetime import date
from typing import Any, Literal
from uuid import UUID

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import require_project_access
from app.models.audit_platform_models import TbLedger
from app.models.core import User
from app.models.workpaper_models import SampledVoucher, WorkingPaper, WpIndex
from app.services.dataset_query import get_active_filter
from app.services.project_audit_phase import project_phase
from app.services.voucher_identity import (
    VoucherKey,
    company_code_condition,
    norm_text,
    parse_voucher_keys,
    single_voucher_lines,
    voucher_label,
    voucher_type_condition,
)

from ._voucher_date import parse_iso_date

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/projects/{project_id}/ledger", tags=["ledger-penetration"])

_SV = SampledVoucher.__table__
#: 与 V210 手工侧唯一索引里 COALESCE 的哨兵值逐字相同
_NO_DATE = date(1900, 1, 1)
_NO_WP = UUID("00000000-0000-0000-0000-000000000000")
#: 已挂查询单次最多这么多个凭证键（design §5）；批量挂凭单次最多这么多个（凭证 × 底稿）组合
MAX_LINK_KEYS = 500
MAX_BATCH_PAIRS = 500


class _SampleVoucherRequest(BaseModel):
    year: int
    voucher_no: str
    # 凭证号单独不唯一（单号最多对应 83 个日期），同日同号也可能是多张凭证（FY-0003 / ZZ-0003）：
    # 日期、凭证字、主体能给就给；没给的由后端在当前账套里补全，补不全（命中多张）时 409 列候选。
    voucher_date: str | None = None
    voucher_type: str | None = None  # 空串 = 凭证字为空的那张
    company_code: str | None = None
    phase: Literal["preliminary", "final"] | None = None
    account_code: str | None = None
    sampling_record_id: UUID | None = None
    working_paper_id: UUID | None = None
    source: str | None = None  # 来源标识（如 "ledger"），用于追溯
    note: str | None = None


class _BatchVoucher(BaseModel):
    model_config = ConfigDict(extra="forbid")

    voucher_no: str
    voucher_date: str | None = None
    voucher_type: str | None = None  # 空串 = 凭证字为空的那张；None = 不知道（后端补全，命中多张该条失败）
    company_code: str | None = None
    account_code: str | None = None  # 挂凭意图科目（用户所在行的科目），回拉时第 ② 级筛选用


class _BatchAttachRequest(BaseModel):
    """一次挂多张凭证到多张底稿。不收阶段：阶段一律取项目当前阶段（需求 6.2），多余字段 422（字段漂移不静默丢）。"""

    model_config = ConfigDict(extra="forbid")

    year: int
    vouchers: list[_BatchVoucher] = Field(min_length=1)
    working_paper_ids: list[UUID] = Field(min_length=1)
    note: str | None = None
    source: str | None = None


class _LinkQueryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    year: int
    keys: list[str] = Field(default_factory=list)  # VoucherKey.to_str() 串


async def _resolve_voucher_key(db: AsyncSession, project_id: UUID, year: int, v: Any) -> VoucherKey:
    """在当前账套里把要挂的凭证定位成一张：命中多张 409 + 候选（不猜），找不到 404。

    ``v`` 带 voucher_no / voucher_date / voucher_type / company_code（单张与批量两种请求体）。
    """
    tbl = TbLedger.__table__
    conds = [await get_active_filter(db, tbl, project_id, year), tbl.c.voucher_no == norm_text(v.voucher_no)]
    vdate = parse_iso_date(v.voucher_date)
    if vdate is not None:
        conds.append(tbl.c.voucher_date == vdate)
    if v.voucher_type is not None:
        conds.append(voucher_type_condition(tbl, v.voucher_type))
    company_cond = company_code_condition(tbl, v.company_code)
    if company_cond is not None:
        conds.append(company_cond)
    rows = (await db.execute(
        sa.select(tbl.c.id, tbl.c.year, tbl.c.company_code, tbl.c.voucher_date, tbl.c.voucher_type,
                  tbl.c.voucher_no, tbl.c.debit_amount, tbl.c.summary).where(*conds)
    )).mappings().all()
    lines = single_voucher_lines(rows, year=year)
    if not lines:
        raise HTTPException(status_code=404, detail={
            "error_code": "VOUCHER_NOT_FOUND",
            "message": "当前账套里没有这张凭证（可能账套已重导，或凭证号、日期、凭证字有误）",
        })
    return VoucherKey.from_row(lines[0], year=year)


def _manual_row_conditions(project_id: UUID, year: int, vk: VoucherKey, working_paper_id: UUID | None) -> list:
    """手工侧同一「凭证 × 底稿」的条件，表达式与 V210 手工侧唯一索引逐列相同（含软删行，用于复活）。"""
    return [
        _SV.c.project_id == project_id,
        _SV.c.year == year,
        _SV.c.voucher_no == vk.voucher_no,
        sa.func.coalesce(_SV.c.voucher_date, _NO_DATE) == vk.date_value,
        sa.func.coalesce(_SV.c.company_code, sa.literal_column("''")) == vk.company_code,
        sa.func.coalesce(_SV.c.voucher_type, sa.literal_column("''")) == vk.voucher_type,
        sa.func.coalesce(_SV.c.working_paper_id, _NO_WP) == (working_paper_id or _NO_WP),
        _SV.c.batch_id.is_(None),
    ]


async def _manual_row(
    db: AsyncSession, project_id: UUID, year: int, vk: VoucherKey, working_paper_id: UUID | None,
) -> SampledVoucher | None:
    """手工侧同一「凭证 × 底稿」的那一行（只在手工侧查，引擎批次行不复用不改写）：未软删的优先，再按最近登记。"""
    return (await db.execute(
        sa.select(SampledVoucher)
        .where(*_manual_row_conditions(project_id, year, vk, working_paper_id))
        .order_by(SampledVoucher.is_deleted, SampledVoucher.sampled_at.desc().nullslast(), SampledVoucher.id)
        .limit(1)
    )).scalars().first()


def _row_out(r: SampledVoucher, *, status: str | None = None) -> dict:
    vk = None
    if r.voucher_date is not None:
        vk = VoucherKey.of(year=r.year, company_code=r.company_code, voucher_date=r.voucher_date,
                           voucher_type=r.voucher_type, voucher_no=r.voucher_no).to_str()
    out = {
        "id": str(r.id),
        "voucher_no": r.voucher_no,
        # None = 历史行未记日期（回拉时只能按号匹配，可能命中多张，后端回 409）
        "voucher_date": r.voucher_date.isoformat() if r.voucher_date else None,
        # None = V210 前的旧行未记凭证字 / 主体
        "voucher_type": r.voucher_type,
        "company_code": r.company_code,
        "voucher_key": vk,
        "phase": r.phase,
        "account_code": r.account_code,
        "sampling_record_id": str(r.sampling_record_id) if r.sampling_record_id else None,
        "working_paper_id": str(r.working_paper_id) if r.working_paper_id else None,
        "batch_id": str(r.batch_id) if r.batch_id else None,
        "source": "sampling_engine" if r.batch_id else "manual",
        "note": r.note,
        "sampled_at": r.sampled_at.isoformat() if r.sampled_at else None,
    }
    if status:
        out["status"] = status
    return out


@router.post("/sample-voucher")
async def sample_voucher(
    project_id: UUID,
    body: _SampleVoucherRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("edit")),
):
    """抽中本凭证 / 挂凭到底稿：记录到抽样凭证清单（手工侧，batch_id 为空）。

    同一凭证（凭证键）挂同一底稿只有一条（再挂 = 复活 / 更新，幂等）；挂不同底稿各成一行（V166：
    同一张凭证可以既属 D2 应收账款检查、又属 E1 货币资金检查）；同日同号的不同凭证字各是一张凭证。
    只在手工侧查（抽凭引擎批次行不复用不改写），确定性取一行：未软删的优先，再按最近登记。
    """
    vk = await _resolve_voucher_key(db, project_id, body.year, body)
    phase = body.phase or await project_phase(db, project_id)  # 没给阶段按项目当前阶段（需求 6.2）
    row = await _manual_row(db, project_id, body.year, vk, body.working_paper_id)
    if row is not None:
        revived = row.is_deleted
        row.is_deleted = False
        row.account_code = body.account_code or row.account_code
        row.sampling_record_id = body.sampling_record_id or row.sampling_record_id
        # 旧行（V210 前）缺的凭证键列按本次定位结果补齐；已记的不改（它们就是去重键）
        row.voucher_date = row.voucher_date or vk.date_value
        row.company_code = row.company_code if row.company_code is not None else vk.company_code
        row.voucher_type = row.voucher_type if row.voucher_type is not None else vk.voucher_type
        # 阶段是挂凭发生时的事实：已挂的行再挂不改（年审时重挂预审挂过的凭证若改成年审，口径 b 就排除不了它，
        # 需求 6.3 / 7.3）；软删后复活、旧行没标阶段的按本次
        if revived or row.phase is None:
            row.phase = phase
        if body.note:
            row.note = body.note
        row.sampled_by = current_user.id
        await db.commit()
        return _row_out(row, status="updated")

    new_row = SampledVoucher(
        project_id=project_id,
        year=body.year,
        voucher_no=vk.voucher_no,
        voucher_date=vk.date_value,
        company_code=vk.company_code,
        voucher_type=vk.voucher_type,
        phase=phase,
        account_code=body.account_code,
        sampling_record_id=body.sampling_record_id,
        working_paper_id=body.working_paper_id,
        note=body.note or (f"source:{body.source}" if body.source else None),
        sampled_by=current_user.id,
    )
    db.add(new_row)
    await db.commit()
    await db.refresh(new_row)
    return _row_out(new_row, status="created")


@router.get("/sampled-vouchers")
async def list_sampled_vouchers(
    project_id: UUID,
    year: int = Query(...),
    working_paper_id: UUID | None = Query(
        None, description="按目标底稿过滤（底稿凭证检查拉取挂到自己的凭证）"
    ),
    manual_only: bool = Query(
        False,
        description="只取手工挂凭（batch_id IS NULL），排除抽凭引擎批次登记；"
                    "底稿「从序时账挂入导入」应传 true 以免来源标签失真",
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """抽样凭证清单。每行带凭证键各列（日期 / 凭证字 / 主体）与阶段，回拉分录按凭证键定位单张凭证。

    本表同时承载手工挂凭与抽凭引擎批次登记（后者 batch_id 非空）；``source`` = manual / sampling_engine。
    """
    conds = [
        SampledVoucher.project_id == project_id,
        SampledVoucher.year == year,
        SampledVoucher.is_deleted == sa.false(),
    ]
    if working_paper_id is not None:
        conds.append(SampledVoucher.working_paper_id == working_paper_id)
    if manual_only:
        conds.append(SampledVoucher.batch_id.is_(None))
    rows = (await db.execute(
        sa.select(SampledVoucher).where(*conds).order_by(SampledVoucher.sampled_at.desc())
    )).scalars().all()
    return {"items": [_row_out(r) for r in rows], "total": len(rows)}


@router.delete("/sampled-vouchers/{sampled_id}")
async def delete_sampled_voucher(
    project_id: UUID,
    sampled_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("edit")),
):
    """取消抽样（软删）"""
    await db.execute(
        sa.update(SampledVoucher)
        .where(SampledVoucher.id == sampled_id, SampledVoucher.project_id == project_id)
        .values(is_deleted=True)
    )
    await db.commit()
    return {"status": "deleted", "id": str(sampled_id)}


# ── 任务 14：一张凭证挂多张底稿（需求 5.1）────────────────────────────────────────────────────────


def _failure_of(exc: HTTPException) -> dict:
    """定位凭证失败（409 多张 / 404 没有）→ 结果里的失败原因；409 带前 5 张候选，前端照样列出是哪几张。"""
    detail = exc.detail if isinstance(exc.detail, dict) else {"message": str(exc.detail)}
    out = {"error_code": detail.get("error_code") or f"HTTP_{exc.status_code}", "reason": detail.get("message") or "凭证定位失败"}
    if exc.status_code == 409:
        cands = list(detail.get("candidates") or [])
        names = "、".join(voucher_label(VoucherKey.from_str(c["voucher_key"])) for c in cands[:3])
        out["reason"] = f"对应多张凭证（{names}{' 等' if len(cands) > 3 else ''}），请在凭证层选定一张再挂"
        out["candidates"] = cands[:5]
    return out


async def _project_workpapers(db: AsyncSession, project_id: UUID, wp_ids: list[UUID]) -> dict[UUID, tuple[str, str]]:
    """本项目未删除的底稿 → (底稿编码, 名称)；别的项目的、已删的、不存在的都不在结果里。"""
    rows = (await db.execute(
        sa.select(WorkingPaper.id, WpIndex.wp_code, WpIndex.wp_name)
        .join(WpIndex, WpIndex.id == WorkingPaper.wp_index_id)
        .where(WorkingPaper.id.in_(wp_ids), WorkingPaper.project_id == project_id,
               WorkingPaper.is_deleted == sa.false())
    )).all()
    return {r.id: (r.wp_code, r.wp_name) for r in rows}


async def _attach_one(
    db: AsyncSession, *, project_id: UUID, year: int, vk: VoucherKey, wp_id: UUID,
    account_code: str | None, note: str | None, phase: str, user_id: UUID,
) -> tuple[str, SampledVoucher]:
    """挂一个「凭证 × 底稿」：已挂（未软删）→ existed、不改任何列；软删过 → 复活，按本次挂凭；没有 → 新建。"""
    row = await _manual_row(db, project_id, year, vk, wp_id)
    if row is not None and not row.is_deleted:
        return "existed", row
    if row is not None:
        row.is_deleted = False
        row.phase = phase
        row.company_code = row.company_code if row.company_code is not None else vk.company_code
        row.voucher_type = row.voucher_type if row.voucher_type is not None else vk.voucher_type
        row.account_code = account_code or row.account_code
        row.note = note or row.note
        row.sampled_by = user_id
    else:
        row = SampledVoucher(
            project_id=project_id, year=year, voucher_no=vk.voucher_no, voucher_date=vk.date_value,
            company_code=vk.company_code, voucher_type=vk.voucher_type, phase=phase, account_code=account_code,
            working_paper_id=wp_id, note=note, sampled_by=user_id,
        )
        db.add(row)
    await db.flush()  # 在保存点里写库：这一条被数据库拒绝时只回滚这一条
    return "created", row


@router.post("/sample-vouchers/batch")
async def attach_vouchers_batch(
    project_id: UUID,
    body: _BatchAttachRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("edit")),
):
    """多张凭证 × 多张底稿一次挂（需求 5.1）：逐个「凭证 × 底稿」一个保存点，单条失败不影响其余。

    结果逐条：``created``（新挂或软删后复活）/ ``existed``（已挂，原行不动，阶段保持当初挂凭时的）/
    ``failed`` + ``error_code`` + ``reason``（凭证对应多张 / 账套里没有 / 底稿不在本项目 / 数据库拒绝）。
    底稿不在本项目（别的项目的、已删的、不存在的）按条失败，不整单 403：同批其余底稿照挂。
    """
    wp_ids = list(dict.fromkeys(body.working_paper_ids))
    pairs = len(body.vouchers) * len(wp_ids)
    if pairs > MAX_BATCH_PAIRS:
        raise HTTPException(status_code=422, detail={
            "error_code": "ATTACH_BATCH_TOO_LARGE",
            "message": f"一次最多挂 {MAX_BATCH_PAIRS} 个「凭证 × 底稿」组合，本次 {pairs} 个，请分批挂入",
        })
    phase = await project_phase(db, project_id)
    wps = await _project_workpapers(db, project_id, wp_ids)
    note = body.note or (f"source:{body.source}" if body.source else None)
    results: list[dict] = []
    for v in body.vouchers:
        base = {"voucher_no": norm_text(v.voucher_no), "voucher_date": v.voucher_date, "voucher_type": v.voucher_type}
        try:
            async with db.begin_nested():
                vk = await _resolve_voucher_key(db, project_id, body.year, v)
        except HTTPException as exc:
            fail = _failure_of(exc)
            results.extend({**base, "voucher_key": None, "working_paper_id": str(w), "wp_code": wps.get(w, (None,))[0],
                            "status": "failed", **fail} for w in wp_ids)
            continue
        base = {"voucher_no": vk.voucher_no, "voucher_date": vk.voucher_date, "voucher_type": vk.voucher_type,
                "voucher_key": vk.to_str()}
        for wp_id in wp_ids:
            item = {**base, "working_paper_id": str(wp_id), "wp_code": wps.get(wp_id, (None,))[0]}
            if wp_id not in wps:
                results.append({**item, "status": "failed", "error_code": "WP_NOT_IN_PROJECT",
                                "reason": "目标底稿不在本项目（或已删除、未生成）"})
                continue
            try:
                async with db.begin_nested():
                    status, row = await _attach_one(
                        db, project_id=project_id, year=body.year, vk=vk, wp_id=wp_id,
                        account_code=v.account_code, note=note, phase=phase, user_id=current_user.id)
            except SQLAlchemyError:
                logger.warning("批量挂凭单条写入失败（已回滚这一条） project=%s voucher=%s wp=%s",
                               project_id, vk.to_str(), wp_id, exc_info=True)
                results.append({**item, "status": "failed", "error_code": "ATTACH_WRITE_FAILED",
                                "reason": "这一条没写进去（数据库拒绝，例如科目编码超过 50 个字符），其余不受影响"})
                continue
            results.append({**item, "status": status, "id": str(row.id), "phase": row.phase})
    await db.commit()
    counts = Counter(r["status"] for r in results)
    return {"results": results, "created": counts["created"], "existed": counts["existed"],
            "failed": counts["failed"], "phase": phase}


# ── 任务 14：已挂 / 已抽标识（需求 5.2）──────────────────────────────────────────────────────────


@router.post("/voucher-links/query")
async def query_voucher_links(
    project_id: UUID,
    body: _LinkQueryRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """凭证键 → 该凭证已挂 / 已抽于哪些底稿（手工挂凭与抽凭引擎登记合并），单次最多 500 个键。

    每条：底稿 id / 编码 / 名称、来源（manual 挂凭 / sampling_engine 抽凭）、阶段、条数（同一底稿被几个抽凭批次抽到）。
    匹配按凭证键各列；旧登记（V210 前）没记主体或凭证字的那一列不参与比较，标 ``legacy``（同日同号的
    另一张凭证也会显示它）；没记日期的旧登记只有凭证号、说不清是全年哪一张，不显示。
    底稿只认本项目未删除的：别的项目的底稿 id 不透出编码名称，记 ``wp_missing``。
    """
    if len(body.keys) > MAX_LINK_KEYS:
        raise HTTPException(status_code=422, detail={
            "error_code": "TOO_MANY_VOUCHER_KEYS",
            "message": f"一次最多查 {MAX_LINK_KEYS} 个凭证键，本次 {len(body.keys)} 个",
        })
    keys = [k for k in parse_voucher_keys(body.keys) if k.year == str(body.year)]
    by_date_no: dict[tuple[str, str], list[VoucherKey]] = {}
    for k in keys:
        by_date_no.setdefault((k.voucher_date, k.voucher_no), []).append(k)
    if not keys:
        return {"links": {}}
    wp, wi = WorkingPaper.__table__, WpIndex.__table__
    rows = (await db.execute(
        sa.select(_SV.c.voucher_no, _SV.c.voucher_date, _SV.c.company_code, _SV.c.voucher_type, _SV.c.batch_id,
                  _SV.c.phase, _SV.c.working_paper_id, wi.c.wp_code, wi.c.wp_name)
        .select_from(_SV.outerjoin(wp, sa.and_(wp.c.id == _SV.c.working_paper_id, wp.c.project_id == project_id,
                                               wp.c.is_deleted == sa.false()))
                     .outerjoin(wi, wi.c.id == wp.c.wp_index_id))
        # 先按 (日期, 号) 取候选（没记日期的旧登记不取），主体与凭证字在下面逐键比（旧登记没记的那列不比、标 legacy）
        .where(_SV.c.project_id == project_id, _SV.c.year == body.year, _SV.c.is_deleted == sa.false(),
               sa.tuple_(_SV.c.voucher_date, _SV.c.voucher_no).in_(sorted({(k.date_value, k.voucher_no) for k in keys})))
    )).all()
    grouped: dict[str, dict[tuple, dict]] = {}
    for r in rows:
        for k in by_date_no.get((r.voucher_date.isoformat(), r.voucher_no), ()):
            if r.company_code is not None and norm_text(r.company_code) != k.company_code:
                continue
            if r.voucher_type is not None and norm_text(r.voucher_type) != k.voucher_type:
                continue
            legacy = r.company_code is None or r.voucher_type is None
            source = "sampling_engine" if r.batch_id else "manual"
            wp_id = str(r.working_paper_id) if r.working_paper_id else None
            entry = grouped.setdefault(k.to_str(), {}).setdefault((wp_id, source, r.phase, legacy), {
                "working_paper_id": wp_id, "wp_code": r.wp_code, "wp_name": r.wp_name,
                "wp_missing": wp_id is not None and r.wp_code is None,
                "source": source, "phase": r.phase, "count": 0, "legacy": legacy,
            })
            entry["count"] += 1
    links = {
        key: sorted(entries.values(), key=lambda e: (e["wp_code"] is None, e["wp_code"] or "", e["source"],
                                                     e["phase"] or "", e["legacy"]))
        for key, entries in grouped.items()
    }
    return {"links": links}
