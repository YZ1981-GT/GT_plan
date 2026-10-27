"""已抽凭证登记表（sampled_vouchers）的查询：项目级已抽、跨底稿重复、项目级概览。

spec voucher-identity-writeback-and-audit-phase 任务 5（需求 2.4）：三处原先都按凭证号，同号别日、
同日同号别凭证字的凭证会被当成一张（误排除 / 误报重复）。现按凭证键 (主体, 日期, 凭证字, 号)；
V210 前登记、没有日期的旧行按凭证号兼容，结果里标 ``legacy``。

只统计抽凭引擎登记的行（``batch_id IS NOT NULL``）—— 穿透页手工标记不是「已执行抽凭程序」。
三个函数都 fail-open：查询失败返回空 + WARNING，不阻断抽样（重复抽凭另有独立提示）。
原在 sampling_registry_service，该文件已到行数上限，迁出后那边保留同名导出。
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workpaper_models import SampledVoucher, SamplingRecord
from app.services.voucher_identity import (
    VoucherKey,
    legacy_voucher_nos_condition,
    norm_text,
    voucher_key_sql,
    voucher_keys_in,
)

logger = logging.getLogger(__name__)

_SV = SampledVoucher.__table__


def _engine_rows(project_id: UUID, year: int) -> list[sa.ColumnElement]:
    return [
        _SV.c.project_id == project_id,
        _SV.c.year == year,
        _SV.c.is_deleted == sa.false(),
        _SV.c.batch_id.isnot(None),
    ]


def _row_key(row: Any, year: int) -> VoucherKey | None:
    """登记行 → 凭证键；没有日期的旧行返回 None（只能按凭证号认）。"""
    if row.voucher_date is None:
        return None
    return VoucherKey.of(
        year=year, company_code=row.company_code, voucher_date=row.voucher_date,
        voucher_type=row.voucher_type, voucher_no=row.voucher_no,
    )


async def project_level_extracted_vouchers(
    db: AsyncSession, project_id: UUID, year: int
) -> tuple[list[VoucherKey], list[str]]:
    """项目级已抽凭证（exclude_scope=project 的排除来源）：(凭证键, 旧行凭证号)。

    fail-open 的理由（沿用 R5.5）：本表是投影，权威留痕不依赖它；查询失败降级为「不排除」，
    重复抽凭仍由 cross_workpaper_duplicate_vouchers 独立提示。
    """
    try:
        rows = (
            await db.execute(
                sa.select(_SV.c.company_code, _SV.c.voucher_date, _SV.c.voucher_type, _SV.c.voucher_no)
                .where(*_engine_rows(project_id, year))
                .distinct()
            )
        ).all()
        keys = {k for k in (_row_key(r, year) for r in rows) if k is not None}
        legacy = {norm_text(r.voucher_no) for r in rows if r.voucher_date is None and norm_text(r.voucher_no)}
        return sorted(keys, key=VoucherKey.parts), sorted(legacy)
    except Exception:  # noqa: BLE001 — 排除是增强，失败不得阻断抽样
        logger.warning(
            "项目级已抽凭证查询失败，本次不做跨底稿排除"
            "（重复项仍由 cross_workpaper_duplicate_vouchers 弹窗提示）project=%s year=%s",
            project_id, year, exc_info=True,
        )
        return [], []


async def cross_workpaper_duplicate_vouchers(
    db: AsyncSession,
    *,
    project_id: UUID,
    year: int,
    voucher_keys: list[VoucherKey] | tuple = (),
    exclude_workpaper_id: UUID | None,
) -> list[dict[str, Any]]:
    """本次样本里已被**其它底稿**抽取登记过的凭证（R8.1，供前端弹窗让审计师判断）。

    样本按凭证键比对登记行；没有日期的旧登记行只能按凭证号比对，命中的结果标 ``legacy``
    （可能是同号别日的另一张凭证）。排除当前底稿自身的登记；NULL 底稿的引擎登记保留（仍属
    「别处抽过」）。

    Returns:
        ``[{voucher_key, voucher_no, voucher_date, voucher_type, wp_codes, batch_count, legacy}]``
        按凭证键排序，旧行排在最后。
    """
    keys = sorted(set(voucher_keys), key=VoucherKey.parts)
    if not keys:
        return []
    try:
        from app.models.workpaper_models import WorkingPaper, WpIndex

        conds = _engine_rows(project_id, year)
        conds.append(sa.or_(
            voucher_keys_in(_SV, keys),
            sa.and_(
                _SV.c.voucher_date.is_(None),
                legacy_voucher_nos_condition(_SV.c.voucher_no, (k.voucher_no for k in keys), exclude=False),
            ),
        ))
        if exclude_workpaper_id is not None:
            conds.append(sa.or_(
                SampledVoucher.working_paper_id.is_(None),
                SampledVoucher.working_paper_id != exclude_workpaper_id,
            ))
        stmt = (
            sa.select(_SV.c.company_code, _SV.c.voucher_date, _SV.c.voucher_type, _SV.c.voucher_no,
                      WpIndex.wp_code, _SV.c.batch_id)
            .select_from(SampledVoucher)
            .join(WorkingPaper, WorkingPaper.id == SampledVoucher.working_paper_id, isouter=True)
            .join(WpIndex, WpIndex.id == WorkingPaper.wp_index_id, isouter=True)
            .where(*conds)
        )
        rows = (await db.execute(stmt)).all()
        by_no: dict[str, list[VoucherKey]] = {}
        for k in keys:
            by_no.setdefault(k.voucher_no, []).append(k)
        grouped: dict[tuple, dict[str, Any]] = {}
        for r in rows:
            vk = _row_key(r, year)
            legacy = vk is None
            # 旧行只有号：同号的每张样本凭证都算命中（说不清是哪一张，结果标 legacy）
            targets = by_no.get(norm_text(r.voucher_no), []) if legacy else [vk]
            for target in targets:
                entry = grouped.setdefault((legacy, target), {"wp_codes": set(), "batches": set()})
                if r.wp_code:
                    entry["wp_codes"].add(str(r.wp_code))
                if r.batch_id is not None:
                    entry["batches"].add(str(r.batch_id))
        out = []
        for (legacy, vk), data in sorted(grouped.items(), key=lambda kv: (kv[0][0], kv[0][1].parts())):
            out.append({
                "voucher_key": vk.to_str(),
                "voucher_no": vk.voucher_no,
                "voucher_date": vk.voucher_date,
                "voucher_type": vk.voucher_type,
                "wp_codes": sorted(data["wp_codes"]),
                "batch_count": len(data["batches"]),
                "legacy": legacy,
            })
        return out
    except Exception:  # noqa: BLE001 — 检测是增强，失败不得阻断抽样
        logger.warning(
            "跨底稿重复抽凭检测失败，本次不提示（project=%s year=%s wp=%s）",
            project_id, year, exclude_workpaper_id, exc_info=True,
        )
        return []


async def project_sampling_coverage(db: AsyncSession, project_id: UUID, year: int) -> dict[str, Any]:
    """项目级抽样登记概览（R5.6）。

    - by_workpaper：按底稿汇总批次数 / 样本数
    - duplicated：被 ≥2 个底稿抽取的凭证（按凭证键；旧行按凭证号单独成组，标 legacy）
    """
    by_wp_rows = (
        await db.execute(
            sa.select(
                SamplingRecord.working_paper_id,
                sa.func.count(sa.distinct(SamplingRecord.batch_id)).label("batch_count"),
                sa.func.coalesce(sa.func.sum(SamplingRecord.sample_size), 0).label("sample_count"),
            )
            .where(SamplingRecord.project_id == project_id, SamplingRecord.is_deleted == sa.false())
            .group_by(SamplingRecord.working_paper_id)
        )
    ).all()

    key_cols = voucher_key_sql(_SV)
    wp_count = sa.func.count(sa.distinct(_SV.c.working_paper_id))
    dup_rows = (
        await db.execute(
            sa.select(*key_cols, wp_count.label("wp_count"))
            .where(*_engine_rows(project_id, year))
            .group_by(*key_cols)
            .having(wp_count >= 2)
            .order_by(wp_count.desc())
            .limit(500)
        )
    ).all()

    duplicated = []
    for r in dup_rows:
        company, vdate, vtype, vno, count = r
        vk = None if vdate is None else VoucherKey.of(
            year=year, company_code=company, voucher_date=vdate, voucher_type=vtype, voucher_no=vno,
        )
        duplicated.append({
            "voucher_key": vk.to_str() if vk else None,
            "voucher_no": vno,
            "voucher_date": vdate.isoformat() if vdate else None,
            "voucher_type": vtype if vk else None,
            "workpaper_count": int(count or 0),
            "legacy": vk is None,
        })
    return {
        "by_workpaper": [
            {
                "working_paper_id": str(r.working_paper_id) if r.working_paper_id else None,
                "batch_count": int(r.batch_count or 0),
                "sample_count": int(r.sample_count or 0),
            }
            for r in by_wp_rows
        ],
        "duplicated": duplicated,
    }
