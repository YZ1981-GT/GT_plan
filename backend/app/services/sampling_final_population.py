"""年审抽样口径（spec voucher-identity-writeback-and-audit-phase 任务 15，需求 7.1~7.4，ADR-VK-10）。

年审阶段在某底稿抽凭时，若该底稿有未撤销的预审批次或预审手工挂凭，必须选口径：

- ``remaining``（口径 a）：只抽预审截止日次日至审计期末，与用户所选期间求交；
- ``full_minus_interim``（口径 b，缺省）：全年分录扣除本底稿预审已检分录 —— 预审批次回填的分录指纹
  （``collect_exclusions`` 在年审一律排除，两种口径都排除）∪ 预审手工挂凭在本次抽样科目范围内的分录。

项目没设预审截止日时，口径 a 用预审批次期间的上限，留痕注明来源（需求 7.2）；两者都没有则 400。
手工挂凭只登记了凭证键、没有分录指纹：按凭证键在当前账套里取它落在本次科目范围内的分录。凭证键是值、
不是行 id，账套重导后照样定位；凭证字 / 主体为空的旧登记按通配匹配；没有日期的旧登记定位不了，
计入 ``unresolved_attach_count`` 如实回报（不按凭证号整张排除：那会连带全年同号的别的凭证）。
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_platform_models import TbLedger, WorkpaperExtractionLog
from app.models.workpaper_models import SampledVoucher
from app.services.dataset_query import get_active_filter
from app.services.project_audit_phase import load_project_audit_phase
from app.services.voucher_identity import norm_text
from app.services.voucher_sampling_exclusion import log_identity

FINAL_POPULATION_MODES: tuple[str, ...] = ("remaining", "full_minus_interim")
DEFAULT_FINAL_POPULATION_MODE = "full_minus_interim"
MODE_LABELS = {"remaining": "口径 a 只抽剩余期间", "full_minus_interim": "口径 b 全年扣除预审已检样本"}
EXTRACTION_TYPE = "voucher_sampling"
#: 一条语句最多带这么多张挂凭的定位条件（每张 4 个绑定参数）
_ATTACH_CHUNK = 200


@dataclass(frozen=True)
class InterimWork:
    """本底稿的预审工作：未撤销的预审抽凭批次与预审手工挂凭。"""

    batch_count: int = 0
    sample_count: int = 0
    line_count: int = 0
    attach_count: int = 0
    batch_period_end: date | None = None

    @property
    def exists(self) -> bool:
        return bool(self.batch_count or self.attach_count)


@dataclass(frozen=True)
class PhaseContext:
    phase: str
    interim_cutoff_date: date | None
    audit_period_end: date | None
    interim: InterimWork
    last_mode: str | None

    @property
    def requires_mode(self) -> bool:
        return self.phase == "final" and self.interim.exists

    def effective_cutoff(self) -> tuple[date | None, str | None]:
        """口径 a 用的截止日与来源：项目设置优先，没设时取预审批次期间上限（需求 7.2）。"""
        if self.interim_cutoff_date is not None:
            return self.interim_cutoff_date, "project"
        if self.interim.batch_period_end is not None:
            return self.interim.batch_period_end, "interim_batches"
        return None, None

    def to_dict(self) -> dict[str, Any]:
        cutoff, source = self.effective_cutoff()
        return {
            "current_audit_phase": self.phase,
            "interim_cutoff_date": _iso(self.interim_cutoff_date),
            "effective_cutoff_date": _iso(cutoff),
            "cutoff_source": source,
            "audit_period_end": _iso(self.audit_period_end),
            "interim_batch_count": self.interim.batch_count,
            "interim_sample_count": self.interim.sample_count,
            "interim_line_count": self.interim.line_count,
            "interim_attach_count": self.interim.attach_count,
            "last_final_population_mode": self.last_mode,
            "requires_final_population_mode": self.requires_mode,
            "default_final_population_mode": self.last_mode or DEFAULT_FINAL_POPULATION_MODE,
        }


@dataclass(frozen=True)
class FinalPopulation:
    """一次年审抽凭实际采用的口径（写进回填留痕 ``extraction_criteria.final_population``）。"""

    mode: str
    cutoff: date | None
    cutoff_source: str | None
    date_start: date
    date_end: date
    interim: InterimWork
    attach_line_ids: tuple[str, ...] = ()
    unresolved_attach_count: int = 0

    def to_trace(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "interim_cutoff_date": _iso(self.cutoff),
            "interim_cutoff_source": self.cutoff_source,
            "date_start": _iso(self.date_start),
            "date_end": _iso(self.date_end),
            "interim_batch_count": self.interim.batch_count,
            "interim_sample_count": self.interim.sample_count,
            "interim_batch_line_fps": self.interim.line_count,
            "interim_attach_count": self.interim.attach_count,
            "excluded_attach_lines": len(self.attach_line_ids),
            "unresolved_attach_count": self.unresolved_attach_count,
        }


def _iso(value: date | None) -> str | None:
    return value.isoformat() if value is not None else None


def _parse_date(value: Any) -> date | None:
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10]) if value else None
    except ValueError:
        return None


def batch_period_end(criteria: dict, year: int | None) -> date | None:
    """预审批次的期间上限：显式 ``filters.date_to``，否则所选会计月份最大那个月的月末。"""
    filters = criteria.get("filters") if isinstance(criteria.get("filters"), dict) else {}
    explicit = _parse_date(filters.get("date_to"))
    if explicit is not None:
        return explicit
    months = []
    for m in filters.get("period_range") or []:
        try:
            if 1 <= int(m) <= 12:
                months.append(int(m))
        except (TypeError, ValueError):
            continue
    if not months or not year:
        return None
    last = max(months)
    return date(int(year), last, calendar.monthrange(int(year), last)[1])


def _interim_attach_rows(project_id: UUID, workpaper_id: UUID) -> list[sa.ColumnElement]:
    sv = SampledVoucher.__table__.c
    return [
        sv.project_id == project_id,
        sv.working_paper_id == workpaper_id,
        sv.batch_id.is_(None),
        sv.phase == "preliminary",
        sv.is_deleted == sa.false(),
    ]


async def load_phase_context(
    db: AsyncSession, *, project_id: UUID, workpaper_id: UUID, year: int | None
) -> PhaseContext:
    """当前阶段、预审截止日与本底稿的预审工作；上次年审口径取最近一次未撤销的年审批次。"""
    state = await load_project_audit_phase(db, project_id)
    log = WorkpaperExtractionLog
    rows = (await db.execute(
        sa.select(log.extraction_criteria, log.filled_count)
        .where(log.workpaper_id == workpaper_id, log.extraction_type == EXTRACTION_TYPE, log.is_undone == sa.false())
        .order_by(log.created_at.desc())
    )).all()
    batch_count = sample_count = 0
    fps: set[str] = set()
    period_end: date | None = None
    last_mode: str | None = None
    for criteria, filled in rows:
        if not isinstance(criteria, dict):
            continue
        if criteria.get("phase") == "final":
            if last_mode is None and criteria.get("final_population_mode") in FINAL_POPULATION_MODES:
                last_mode = criteria["final_population_mode"]
            continue
        if criteria.get("phase") != "preliminary":
            continue
        batch_count += 1
        sample_count += int(filled or 0)
        fps.update(log_identity(criteria).line_fps)
        end = batch_period_end(criteria, year)
        if end is not None and (period_end is None or end > period_end):
            period_end = end
    attach_count = (await db.execute(
        sa.select(sa.func.count()).select_from(SampledVoucher.__table__)
        .where(*_interim_attach_rows(project_id, workpaper_id))
    )).scalar_one()
    interim = InterimWork(batch_count, sample_count, len(fps), int(attach_count or 0), period_end)
    return PhaseContext(state.phase, state.interim_cutoff_date, state.audit_period_end, interim, last_mode)


def _attach_matches(attach: Any, line: Any) -> bool:
    """这条分录属不属于这张挂凭（判定只在这里）：日期 + 号必比；凭证字、主体登记了才比 ——
    V210 前的旧登记缺这两列（NULL = 不知道，通配）；凭证字空串 = 凭证字为空的那张。"""
    if line.voucher_date != attach.voucher_date or norm_text(line.voucher_no) != norm_text(attach.voucher_no):
        return False
    if attach.voucher_type is not None and norm_text(line.voucher_type) != norm_text(attach.voucher_type):
        return False
    return not norm_text(attach.company_code) or norm_text(line.company_code) == norm_text(attach.company_code)


async def interim_attach_line_ids(
    db: AsyncSession, *, project_id: UUID, workpaper_id: UUID, year: int, account_codes: list[str]
) -> tuple[list[str], int]:
    """预审手工挂凭在当前账套、本次科目范围（前缀匹配，与抽样总体同口径）内的分录行 id；以及定位不到的挂凭张数。

    「定位不到」= 没有日期的旧登记，或当前账套里已没有这张凭证；凭证在、只是分录不在本次科目范围内的不算。
    """
    sv = SampledVoucher.__table__.c
    attaches = (await db.execute(
        sa.select(sv.voucher_date, sv.voucher_type, sv.voucher_no, sv.company_code)
        .where(*_interim_attach_rows(project_id, workpaper_id))
        .distinct()
    )).all()
    locatable = [r for r in attaches if r.voucher_date is not None and norm_text(r.voucher_no)]
    unresolved = len(attaches) - len(locatable)
    if not locatable:
        return [], unresolved
    tbl = TbLedger.__table__
    active = await get_active_filter(db, tbl, project_id, year)
    ids: dict[str, None] = {}
    for start in range(0, len(locatable), _ATTACH_CHUNK):
        chunk = locatable[start : start + _ATTACH_CHUNK]
        # 按 (日期, 号) 粗取同日同号的全部分录（凭证键的超集），归属由 _attach_matches 判
        probe = {(r.voucher_date, norm_text(r.voucher_no)) for r in chunk}
        lines = (await db.execute(
            sa.select(tbl.c.id, tbl.c.voucher_date, tbl.c.voucher_type, tbl.c.voucher_no,
                      tbl.c.company_code, tbl.c.account_code)
            .where(active, sa.or_(*[sa.and_(tbl.c.voucher_date == d, tbl.c.voucher_no == n) for d, n in sorted(probe)]))
        )).all()
        for attach in chunk:
            mine = [ln for ln in lines if _attach_matches(attach, ln)]
            if not mine:
                unresolved += 1
            for ln in mine:
                code = norm_text(ln.account_code)
                if not account_codes or any(code.startswith(norm_text(c)) for c in account_codes):
                    ids[str(ln.id)] = None
    return list(ids), unresolved


def _remaining_window(ctx: PhaseContext, year: int, date_start: date, date_end: date) -> tuple[date, date, date, str]:
    cutoff, source = ctx.effective_cutoff()
    if cutoff is None:
        raise HTTPException(status_code=400, detail={
            "error_code": "INTERIM_CUTOFF_REQUIRED",
            "message": "项目没有设置预审截止日，预审批次也没有期间信息，无法确定剩余期间；"
                       "请先在项目设置「审计阶段」里填写预审截止日，或改选口径 b",
        })
    period_end = ctx.audit_period_end or date(int(year), 12, 31)
    start, end = max(date_start, cutoff + timedelta(days=1)), min(date_end, period_end)
    if start > end:
        raise HTTPException(status_code=400, detail={
            "error_code": "REMAINING_PERIOD_EMPTY",
            "message": f"口径 a 只抽预审截止日 {cutoff.isoformat()} 次日至审计期末 {period_end.isoformat()}；"
                       f"所选期间 {date_start.isoformat()} 至 {date_end.isoformat()} 与之没有交集，请调整抽样期间或改选口径 b",
        })
    return start, end, cutoff, source or ""


async def resolve_final_population(
    db: AsyncSession,
    *,
    project_id: UUID,
    workpaper_id: UUID,
    year: int,
    phase: str,
    mode: str | None,
    date_start: date,
    date_end: date,
    account_codes: list[str],
) -> FinalPopulation | None:
    """年审且本底稿有预审工作时确定口径；否则返回 None（口径不适用，请求带了也不记）。

    缺口径 422 ``FINAL_POPULATION_MODE_REQUIRED``；口径 a 的窗口为空或无截止日 400（见 ``_remaining_window``）。
    """
    if phase != "final":
        return None
    ctx = await load_phase_context(db, project_id=project_id, workpaper_id=workpaper_id, year=year)
    if not ctx.requires_mode:
        return None
    if mode not in FINAL_POPULATION_MODES:
        raise HTTPException(status_code=422, detail={
            "error_code": "FINAL_POPULATION_MODE_REQUIRED",
            "message": f"本底稿有预审抽凭 {ctx.interim.batch_count} 批、预审挂凭 {ctx.interim.attach_count} 张，"
                       "年审抽凭须选择口径：a 只抽剩余期间，或 b 全年扣除预审已检样本",
        })
    if mode == "remaining":
        start, end, cutoff, source = _remaining_window(ctx, year, date_start, date_end)
        return FinalPopulation(mode, cutoff, source, start, end, ctx.interim)
    cutoff, source = ctx.effective_cutoff()
    ids, unresolved = await interim_attach_line_ids(
        db, project_id=project_id, workpaper_id=workpaper_id, year=year, account_codes=account_codes,
    )
    return FinalPopulation(mode, cutoff, source, date_start, date_end, ctx.interim, tuple(ids), unresolved)
