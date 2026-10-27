"""挂凭（序时账手工挑凭证 → 抽样凭证清单 / 底稿凭证检查）：按凭证键并记审计阶段。

spec voucher-identity-writeback-and-audit-phase 任务 6（需求 2.5）。三个端点原在 ledger_penetration.py，
整体迁到这里（那个文件已到行数上限），URL 不变：

- ``POST   /api/projects/{project_id}/ledger/sample-voucher``
- ``GET    /api/projects/{project_id}/ledger/sampled-vouchers``
- ``DELETE /api/projects/{project_id}/ledger/sampled-vouchers/{sampled_id}``

挂凭的凭证按当前账套定位成一张凭证（凭证键 = 年度 + 主体 + 日期 + 凭证字 + 号）：只给号（或日期 + 号）
却命中多张时 409 VOUCHER_KEY_AMBIGUOUS + 候选，找不到 404。手工侧去重键 = 凭证键 + 目标底稿，与 V210 的
``uq_sampled_voucher_manual_project_year_no`` 同口径（日期 / 主体 / 凭证字按 COALESCE 折叠）；记录保存凭证字、
主体与阶段，回拉按凭证键取分录。
"""

from __future__ import annotations

from datetime import date
from typing import Literal
from uuid import UUID

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import require_project_access
from app.models.audit_platform_models import TbLedger
from app.models.core import User
from app.models.workpaper_models import SampledVoucher
from app.services.dataset_query import get_active_filter
from app.services.voucher_identity import (
    VoucherKey,
    norm_text,
    single_voucher_lines,
    voucher_type_condition,
)

from ._voucher_date import parse_iso_date

router = APIRouter(prefix="/api/projects/{project_id}/ledger", tags=["ledger-penetration"])

#: 项目审计阶段（任务 8 的项目设置）上线前，挂凭缺省记为年审
DEFAULT_PHASE = "final"
_SV = SampledVoucher.__table__
#: 与 V210 手工侧唯一索引里 COALESCE 的哨兵值逐字相同
_NO_DATE = date(1900, 1, 1)
_NO_WP = UUID("00000000-0000-0000-0000-000000000000")


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


async def _resolve_voucher_key(db: AsyncSession, project_id: UUID, body: _SampleVoucherRequest) -> VoucherKey:
    """在当前账套里把要挂的凭证定位成一张：命中多张 409 + 候选（不猜），找不到 404。"""
    tbl = TbLedger.__table__
    conds = [await get_active_filter(db, tbl, project_id, body.year), tbl.c.voucher_no == norm_text(body.voucher_no)]
    vdate = parse_iso_date(body.voucher_date)
    if vdate is not None:
        conds.append(tbl.c.voucher_date == vdate)
    if body.voucher_type is not None:
        conds.append(voucher_type_condition(tbl, body.voucher_type))
    if norm_text(body.company_code):
        conds.append(tbl.c.company_code == norm_text(body.company_code))
    rows = (await db.execute(
        sa.select(tbl.c.id, tbl.c.year, tbl.c.company_code, tbl.c.voucher_date, tbl.c.voucher_type,
                  tbl.c.voucher_no, tbl.c.debit_amount, tbl.c.summary).where(*conds)
    )).mappings().all()
    lines = single_voucher_lines(rows, year=body.year)
    if not lines:
        raise HTTPException(status_code=404, detail={
            "error_code": "VOUCHER_NOT_FOUND",
            "message": "当前账套里没有这张凭证（可能账套已重导，或凭证号、日期、凭证字有误）",
        })
    return VoucherKey.from_row(lines[0], year=body.year)


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
    vk = await _resolve_voucher_key(db, project_id, body)
    phase = body.phase or DEFAULT_PHASE
    row = (await db.execute(
        sa.select(SampledVoucher)
        .where(*_manual_row_conditions(project_id, body.year, vk, body.working_paper_id))
        .order_by(SampledVoucher.is_deleted, SampledVoucher.sampled_at.desc().nullslast(), SampledVoucher.id)
        .limit(1)
    )).scalars().first()
    if row is not None:
        row.is_deleted = False
        row.account_code = body.account_code or row.account_code
        row.sampling_record_id = body.sampling_record_id or row.sampling_record_id
        # 旧行（V210 前）缺的凭证键列按本次定位结果补齐；已记的不改（它们就是去重键）
        row.voucher_date = row.voucher_date or vk.date_value
        row.company_code = row.company_code if row.company_code is not None else vk.company_code
        row.voucher_type = row.voucher_type if row.voucher_type is not None else vk.voucher_type
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
