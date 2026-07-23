"""通用抽凭引擎 API 路由

- POST /api/projects/{pid}/sampling/voucher-extract  — 执行抽样算法提取凭证
- GET  /api/projects/{pid}/sampling/voucher-history   — 抽凭历史列表
- POST /api/projects/{pid}/sampling/voucher-undo      — 撤销抽凭操作
- POST /api/projects/{pid}/sampling/voucher-compare   — 对比两次抽凭差异

复用 LedgerSamplingService（build_ledger_query / execute_with_stats）。
复用 workpaper_extraction_log 表（extraction_type='voucher_sampling'）。

Validates: Requirements 2.2, 2.3, 2.5, 3.1, 3.2, 3.11, 6.3, 6.4, 8.1, 8.2,
           13.1, 13.2, 13.3, 13.4, 13.5, 14.1, 14.2
"""

from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
import sqlalchemy as sa

from app.deps import authorize_wp_edit
from app.models.audit_platform_models import TrialBalance, WorkpaperExtractionLog
from app.models.core import Project, User as _CoreUser  # noqa: F401 (Project 用于年度校验)
from app.models.core import User
from app.services.ledger_sampling_service import (
    LedgerQueryFilters,
    LedgerSamplingService,
)
from app.services.sampling_methodology import build_methodology_snapshot
from app.services.voucher_sampling_algorithms import (
    SamplingMethod,
    SamplingParams,
    StratumConfig,
    execute_sampling,
)
from app.services.version_trail_service import VersionTrailService

logger = logging.getLogger(__name__)

# 内存样本框上限：总体 ≤ 此值走内存路径（现状，零回归）；> 此值走两阶段全量框。
_SAMPLING_FRAME_LIMIT = 10000
# 全量框阶段 A 最小投影的硬上限（极端超大总体保护）；命中则 frame_capped=True 如实透明。
_SAMPLING_FRAME_MAX_UNITS = 2_000_000

router = APIRouter(
    prefix="/api/projects/{pid}/sampling",
    tags=["sampling"],
)


# ─── Request / Response schemas ──────────────────────────────────────────────


class VoucherExtractRequest(BaseModel):
    """抽凭请求体"""

    sampling_method: SamplingMethod
    sampling_params: dict = Field(default_factory=dict)
    random_seed: Optional[int] = None
    phase: str = "preliminary"  # "preliminary" | "final"
    filters: dict = Field(default_factory=dict)
    workpaper_id: UUID
    year: int


class VoucherCompareRequest(BaseModel):
    """版本对比请求体"""

    log_id_a: UUID
    log_id_b: UUID


# ─── POST /voucher-extract ────────────────────────────────────────────────────


@router.post("/voucher-extract")
async def voucher_extract(
    pid: UUID,
    req: VoucherExtractRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """执行抽凭算法

    从 filters 构建 LedgerQueryFilters，调用 LedgerSamplingService 获取总体，
    再调用 execute_sampling 执行抽样算法，返回结果+统计+种子。
    """
    # ── 服务端授权 + 参数校验（Req8）：置于 try 之外，使 403/404/400 不被 except 吞成 500 ──
    await _authorize_and_validate_extract(
        db, current_user, pid, req.workpaper_id, req.year
    )

    try:
        # ── 版本链：抽凭前自动快照 ──
        await VersionTrailService.create_snapshot_fire_and_forget(
            db=db,
            project_id=pid,
            workpaper_id=req.workpaper_id,
            user_id=current_user.id,
            snapshot_type="auto_sampling",
            description=f"抽凭执行: {req.sampling_method}, phase={req.phase}",
        )

        # 1. 解析过滤条件
        filters = req.filters
        period_range: list[int] = filters.get("period_range", list(range(1, 13)))
        account_codes: list[str] = filters.get("account_codes", [])
        amount_min = filters.get("amount_min")
        amount_max = filters.get("amount_max")
        direction_filter: str = filters.get("direction_filter", "all")
        voucher_type_filter: list[str] = filters.get("voucher_type_filter", [])
        summary_keyword: str = filters.get("summary_keyword", "")
        exclude_extracted: bool = filters.get("exclude_extracted", True)
        # 抽样单位（默认分录行，零回归）；voucher 单位按凭证号聚合（Task 5 前端接入）
        sampling_unit: str = filters.get("sampling_unit", "ledger_line")
        if sampling_unit not in ("ledger_line", "voucher"):
            sampling_unit = "ledger_line"

        # 从 period_range 推导日期范围（year + 月份 → date_start/date_end）
        if period_range:
            min_month = min(period_range)
            max_month = max(period_range)
        else:
            min_month, max_month = 1, 12

        date_start = date(req.year, min_month, 1)
        # date_end 取最大月份的最后一天
        if max_month == 12:
            date_end = date(req.year, 12, 31)
        else:
            # 下个月1日减1天 = 当月最后一天
            date_end = date(req.year, max_month + 1, 1).__class__(
                req.year, max_month + 1, 1
            )
            from datetime import timedelta
            date_end = date(req.year, max_month + 1, 1) - timedelta(days=1)

        # 截止性测试复用：filters 显式日期窗口 date_from/date_to（= 基准日 ∓ 天数）
        # 覆盖由 period_range 推导的日期范围（可选，向后兼容：缺省时沿用月份推导）
        date_from_override = _parse_iso_date(filters.get("date_from"))
        date_to_override = _parse_iso_date(filters.get("date_to"))
        if date_from_override is not None:
            date_start = date_from_override
        if date_to_override is not None:
            date_end = date_to_override

        # 金额阈值：使用 amount_min 作为 threshold（LedgerQueryFilters 设计）
        amount_threshold = Decimal(str(amount_min)) if amount_min else Decimal("0")

        # 金额上限：amount_max（此前前端传入但后端从不消费 → 过滤失效）
        amount_max_val: Optional[Decimal] = None
        if amount_max not in (None, ""):
            try:
                parsed_max = Decimal(str(amount_max))
                if parsed_max > 0:
                    amount_max_val = parsed_max
            except (InvalidOperation, ValueError):
                amount_max_val = None

        # 离散会计月份：仅在未使用显式日期窗口(date_from/date_to)时按 period_range 收窄，
        # 避免「1 月+12 月」被 min~max 推导扩为 1~12 连续区间纳入 2~11 月。
        months_filter: list[int] = []
        if date_from_override is None and date_to_override is None and period_range:
            months_filter = [int(m) for m in period_range if 1 <= int(m) <= 12]

        # 2~3. 排除已提取（unit 感知，P3）：
        #   - ledger_line 单位：新日志按行 id 排除（避免跨科目整张误排），旧日志回退 voucher_no。
        #   - voucher 单位：按 voucher_no 排除（整张凭证已检查，语义正确）。
        exclude_voucher_nos: list[str] = []
        exclude_unit_ids: list[str] = []
        if sampling_unit == "ledger_line":
            if exclude_extracted:
                legacy_nos, unit_ids = await _get_voucher_sampling_exclusions(
                    db, req.workpaper_id
                )
                exclude_voucher_nos = legacy_nos
                exclude_unit_ids = unit_ids
            if req.phase == "final":
                p_nos, p_uids = await _get_voucher_sampling_exclusions(
                    db, req.workpaper_id, preliminary_only=True
                )
                exclude_voucher_nos = list(set(exclude_voucher_nos) | set(p_nos))
                exclude_unit_ids = list(set(exclude_unit_ids) | set(p_uids))
        else:
            if exclude_extracted:
                exclude_voucher_nos = await _get_voucher_sampling_extracted_nos(
                    db, req.workpaper_id
                )
            if req.phase == "final":
                preliminary_nos = await _get_preliminary_voucher_nos(
                    db, req.workpaper_id
                )
                existing_set = set(exclude_voucher_nos)
                for no in preliminary_nos:
                    if no not in existing_set:
                        exclude_voucher_nos.append(no)
                        existing_set.add(no)

        # 4. 构建 LedgerQueryFilters
        ledger_filters = LedgerQueryFilters(
            date_start=date_start,
            date_end=date_end,
            account_codes=account_codes,
            amount_threshold=amount_threshold,
            amount_max=amount_max_val,
            months=months_filter,
            direction_filter=direction_filter,
            voucher_type_filter=voucher_type_filter,
            summary_keyword=summary_keyword,
            exclude_voucher_nos=exclude_voucher_nos,
            exclude_unit_ids=exclude_unit_ids,
        )

        # 5. 构建查询
        query = await LedgerSamplingService.build_ledger_query(
            db, pid, req.year, ledger_filters
        )

        # 6. 全量统计（不受截断影响）+ 内存样本框（≤ 上限）
        items, stats = await LedgerSamplingService.execute_with_stats(
            db, query, page=1, page_size=_SAMPLING_FRAME_LIMIT, max_total=_SAMPLING_FRAME_LIMIT
        )

        # 7. 构建 SamplingParams
        sp = req.sampling_params
        sampling_params = _build_sampling_params(req.sampling_method, sp)

        # 8. 执行抽样算法
        #    - 总体 ≤ 上限：现状内存路径（对全部 items 抽样，逐字节等价，零回归）。
        #    - 总体 > 上限：两阶段全量框——阶段 A 全量最小投影定位抽样单位，用同一
        #      seed 派生序列对全量单位抽样，阶段 B 按命中单位标识取回完整样本行。
        #      这样超过内存上限的单位不再永不可抽（消除随机/分层/系统/MUS 选择偏差）。
        frame_capped = False
        if stats.total_count > _SAMPLING_FRAME_LIMIT:
            # P2 安全快路径：specific_item（高值全选）确定性、无种子 → DB 侧按阈值预过滤，
            # 避免把低于阈值的行全部物化。等价于 canonical 在合成总体上的 _greatest>=阈值
            # 过滤（合成金额即 DB abs-greatest），仅对 specific_item 生效，不影响随机/MUS/
            # 分层/系统的全量框可复现路径。
            locate_min_greatest: Optional[Decimal] = None
            if req.sampling_method == "specific_item":
                locate_min_greatest = getattr(
                    sampling_params, "materiality_threshold", None
                )
            # 两阶段全量框（ledger_line / voucher 均由 locate/fetch 按单位处理）
            units = await LedgerSamplingService.locate_sampling_units(
                db,
                query,
                unit=sampling_unit,
                max_units=_SAMPLING_FRAME_MAX_UNITS,
                min_greatest=locate_min_greatest,
            )
            frame_capped = len(units) >= _SAMPLING_FRAME_MAX_UNITS
            # 合成最小总体（debit_amount=单位代表金额，供 _greatest 权重；保留日期/凭证号
            # 供系统抽样排序），保留 _unit_id 供阶段 B 取回
            synthetic_pop = [
                {
                    "debit_amount": str(u["greatest_amount"]),
                    "credit_amount": None,
                    "voucher_date": u["voucher_date"],
                    "voucher_no": u["voucher_no"],
                    "_unit_id": u["unit_id"],
                }
                for u in units
            ]
            selection = execute_sampling(
                method=req.sampling_method,
                population=synthetic_pop,
                params=sampling_params,
                seed=req.random_seed,
            )
            selected_unit_ids = [
                it["_unit_id"] for it in selection.items if it.get("_unit_id") is not None
            ]
            sample_items = await LedgerSamplingService.fetch_by_unit_ids(
                db, query, sampling_unit, selected_unit_ids
            )
            seed_used_val = selection.seed_used
            result_truncated = selection.truncated
        elif sampling_unit == "voucher":
            # 内存路径 voucher 单位：按凭证号聚合 items（金额=行 GREATEST 之和），对凭证抽样，
            # 抽中一张凭证带出其全部分录行（与两阶段 voucher 单位口径一致）。
            voucher_map: dict[str, dict] = {}
            for it in items:
                vno = it.get("voucher_no") or ""
                entry = voucher_map.setdefault(
                    vno, {"greatest": Decimal("0"), "date": it.get("voucher_date"), "lines": []}
                )
                entry["greatest"] += _greatest_amount(it)
                entry["lines"].append(it)
                d = it.get("voucher_date")
                if d and (entry["date"] is None or d < entry["date"]):
                    entry["date"] = d
            synthetic_pop = [
                {
                    "debit_amount": str(v["greatest"]),
                    "credit_amount": None,
                    "voucher_date": v["date"],
                    "voucher_no": vno,
                    "_vno": vno,
                }
                for vno, v in voucher_map.items()
            ]
            selection = execute_sampling(
                method=req.sampling_method,
                population=synthetic_pop,
                params=sampling_params,
                seed=req.random_seed,
            )
            sample_items = [
                line
                for it in selection.items
                for line in voucher_map.get(it.get("_vno"), {}).get("lines", [])
            ]
            seed_used_val = selection.seed_used
            result_truncated = selection.truncated
        else:
            # 内存路径 ledger_line（现状，逐字节等价，零回归）
            result = execute_sampling(
                method=req.sampling_method,
                population=items,
                params=sampling_params,
                seed=req.random_seed,
            )
            sample_items = result.items
            seed_used_val = result.seed_used
            result_truncated = result.truncated

        # 9. 总体口径以 execute_with_stats 的全量聚合（stats.*）为准（不受截断影响）。
        population_count_full = stats.total_count
        population_amount = stats.amount_total  # 全量总体代表金额

        # 方法学单一真源：优先用 CAS1314 权威口径（置信度/可容忍错报驱动）计算间隔，
        # 缺参时回退 _derive_sampling_interval（总体/mus_sample_size）。前端以此为准。
        methodology = build_methodology_snapshot(
            sampling_method=req.sampling_method,
            population_amount=str(population_amount),
            confidence_level=sp.get("confidence_level"),
            tolerable_misstatement=sp.get("tolerable_misstatement"),
            expected_misstatement=sp.get("expected_misstatement"),
        )
        if methodology.get("sampling_interval") not in (None, "", "0.00"):
            sampling_interval = Decimal(str(methodology["sampling_interval"]))
        else:
            sampling_interval = _derive_sampling_interval(
                req.sampling_method, sp, population_amount
            )

        # 总体完整性核对：独立账面来源（trial_balance，独立于序时账）。取不到 → 未执行核对，
        # 绝不用序时账总体自身作账面（消除自身比对假绿，Req2）。
        independent_book, reconcile_basis = await _resolve_independent_book_amount(
            db, pid, req.year, account_codes
        )
        reconcile_available = independent_book is not None

        # 样本借贷合计 + 代表金额（GREATEST 求和；样本集合小，Python 端计算）
        sample_debit_total = sum(
            (Decimal(str(it["debit_amount"])) for it in sample_items if it.get("debit_amount") is not None),
            Decimal("0"),
        )
        sample_credit_total = sum(
            (Decimal(str(it["credit_amount"])) for it in sample_items if it.get("credit_amount") is not None),
            Decimal("0"),
        )
        sample_amount = sum(
            (_greatest_amount(it) for it in sample_items), Decimal("0")
        )
        sample_count_val = len(sample_items)

        # 覆盖率：分母一律使用全量总体（stats），保证截断时口径诚实（不再虚高）
        count_coverage_rate = _coverage_rate(sample_count_val, population_count_full)
        amount_coverage_rate = _coverage_rate(sample_amount, population_amount)

        # 全量框是否仍受硬上限约束（极端超大总体）：如实透明，不声称覆盖全总体
        truncated = bool(stats.truncated or result_truncated or frame_capped)

        # 10. 高值必选项标识（R17）：单笔金额 ≥ 抽样间隔者标记 high_value
        marked_items: list[dict] = []
        for it in sample_items:
            marked = dict(it)
            if sampling_interval is not None and sampling_interval > 0:
                marked["high_value"] = _greatest_amount(it) >= sampling_interval
            else:
                marked["high_value"] = False
            marked_items.append(marked)

        # 11. 构建返回值（金额序列化为字符串，新增字段均向后兼容）
        return {
            "items": marked_items,
            "stats": {
                "population_count": population_count_full,
                "population_debit_total": str(stats.debit_total),
                "population_credit_total": str(stats.credit_total),
                "population_amount": str(population_amount),
                # 独立账面（trial_balance 审定，独立于序时账）；取不到为 null + 未执行核对
                "book_amount": (
                    str(independent_book) if independent_book is not None else None
                ),
                "reconcile_available": reconcile_available,
                "reconcile_basis": reconcile_basis,
                "sample_count": sample_count_val,
                "sample_debit_total": str(sample_debit_total),
                "sample_credit_total": str(sample_credit_total),
                "sample_amount": str(sample_amount),
                "count_coverage_rate": str(count_coverage_rate),
                "amount_coverage_rate": str(amount_coverage_rate),
                "sampling_interval": (
                    str(sampling_interval) if sampling_interval is not None else None
                ),
                "truncated": truncated,
                # 全量框硬上限命中（极端超大总体仍未覆盖全体）→ 前端如实提示
                "frame_capped": frame_capped,
                "sampling_unit": sampling_unit,
            },
            # 方法学单一真源快照（含 algo_version）——前端以此为准展示/回填留痕
            "methodology": methodology,
            "seed_used": seed_used_val,
            "truncated": truncated,
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("voucher-extract failed: %s", e)
        raise HTTPException(status_code=500, detail="抽凭执行失败")


# ─── GET /voucher-history ─────────────────────────────────────────────────────


@router.get("/voucher-history")
async def voucher_history(
    pid: UUID,
    wp_id: UUID = Query(..., description="底稿ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取指定底稿的抽凭历史列表（按时间倒序）

    仅返回 extraction_type='voucher_sampling' 的记录。
    """
    stmt = (
        select(WorkpaperExtractionLog)
        .where(
            WorkpaperExtractionLog.workpaper_id == wp_id,
            WorkpaperExtractionLog.extraction_type == "voucher_sampling",
        )
        .order_by(WorkpaperExtractionLog.created_at.desc())
    )
    result = await db.execute(stmt)
    rows = result.scalars().all()

    return [
        {
            "id": str(row.id),
            "created_at": row.created_at.isoformat(),
            "user_id": str(row.user_id),
            "extraction_type": row.extraction_type,
            "extraction_criteria": row.extraction_criteria,
            "total_matched": row.total_matched,
            "filled_count": row.filled_count,
            "fill_mode": row.fill_mode,
            "is_undone": row.is_undone,
            # 方法学留痕回显：优先读 extraction_criteria JSON，回退到顶层列，缺省返回 null
            "random_seed": _echo_criteria_field(row, "random_seed"),
            "resample_reason": _echo_criteria_field(row, "resample_reason"),
            "sampling_interval": _echo_criteria_field(row, "sampling_interval"),
            "conclusion": _echo_criteria_field(row, "conclusion"),
        }
        for row in rows
    ]


# ─── POST /voucher-undo ──────────────────────────────────────────────────────


@router.post("/voucher-undo")
async def voucher_undo(
    pid: UUID,
    log_id: UUID = Query(..., description="要撤销的日志记录ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """撤销指定抽凭操作

    仅允许撤销最近一次非撤销记录（extraction_type='voucher_sampling'）。
    标记 is_undone=True 并返回 before_data。
    """
    try:
        # 1. 加载记录
        stmt = select(WorkpaperExtractionLog).where(
            WorkpaperExtractionLog.id == log_id
        )
        result = await db.execute(stmt)
        record = result.scalar_one_or_none()

        if record is None:
            raise ValueError("提取记录不存在")

        # 2. 验证 extraction_type
        if record.extraction_type != "voucher_sampling":
            raise ValueError("该记录不属于抽凭引擎")

        # 3. 验证是最新非撤销记录
        latest_stmt = (
            select(WorkpaperExtractionLog)
            .where(
                WorkpaperExtractionLog.workpaper_id == record.workpaper_id,
                WorkpaperExtractionLog.extraction_type == "voucher_sampling",
                WorkpaperExtractionLog.is_undone == False,  # noqa: E712
            )
            .order_by(WorkpaperExtractionLog.created_at.desc())
            .limit(1)
        )
        latest_result = await db.execute(latest_stmt)
        latest = latest_result.scalar_one_or_none()

        if latest is None or latest.id != log_id:
            raise ValueError("仅可撤销最近一次操作")

        # 4. 标记撤销（status='undone'，配合 V123 部分唯一索引强制撤销唯一）
        record.is_undone = True
        record.status = "undone"
        await db.flush()
        await db.commit()

        # 5. 返回 before_data
        before_data = record.before_data if record.before_data is not None else []
        return {"success": True, "before_data": before_data}

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ─── POST /voucher-compare ───────────────────────────────────────────────────


@router.post("/voucher-compare")
async def voucher_compare(
    pid: UUID,
    req: VoucherCompareRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """对比两次抽凭记录的差异

    从 extraction_criteria 或 before_data 中提取凭证号集合，
    计算 added / removed / retained。
    """
    try:
        # 加载两条记录
        stmt_a = select(WorkpaperExtractionLog).where(
            WorkpaperExtractionLog.id == req.log_id_a
        )
        stmt_b = select(WorkpaperExtractionLog).where(
            WorkpaperExtractionLog.id == req.log_id_b
        )
        result_a = await db.execute(stmt_a)
        result_b = await db.execute(stmt_b)
        record_a = result_a.scalar_one_or_none()
        record_b = result_b.scalar_one_or_none()

        if record_a is None or record_b is None:
            raise ValueError("对比记录不存在")

        # 提取凭证号集合
        set_a = _extract_voucher_nos_from_log(record_a)
        set_b = _extract_voucher_nos_from_log(record_b)

        # 计算差异
        added = sorted(set_b - set_a)
        removed = sorted(set_a - set_b)
        retained = sorted(set_a & set_b)

        return {
            "added": added,
            "removed": removed,
            "retained": retained,
            "added_count": len(added),
            "removed_count": len(removed),
            "retained_count": len(retained),
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ─── Helpers ──────────────────────────────────────────────────────────────────


async def _authorize_and_validate_extract(
    db: AsyncSession,
    current_user: User,
    pid: UUID,
    workpaper_id: UUID,
    year: int,
) -> None:
    """抽凭端点服务端授权 + 参数校验（Req8，先于任何取数/写入）。

    1. 编辑权：复用 authorize_wp_edit（角色 WORKPAPER_WRITE + 项目成员 edit 权），返回底稿所属项目。
    2. 底稿归属：底稿所属项目须 == URL 项目 pid（防跨项目取数）。
    3. 年度合法：year 须属项目审计期（audit_year 精确匹配；缺省时回退审计期起止年份区间；
       两者皆缺则不阻断——无从校验）。

    Raises:
        HTTPException 403（无编辑权 / 跨项目）/ 404（底稿不存在）/ 400（年度非法）。
    """
    wp_project_id = await authorize_wp_edit(db, current_user, workpaper_id)
    if str(wp_project_id) != str(pid):
        raise HTTPException(status_code=403, detail="底稿不属于该项目，禁止跨项目取数")

    proj = (
        await db.execute(
            sa.select(
                Project.audit_year,
                Project.audit_period_start,
                Project.audit_period_end,
            ).where(Project.id == pid)
        )
    ).one_or_none()
    if proj is not None:
        audit_year, period_start, period_end = proj
        if audit_year is not None:
            if int(year) != int(audit_year):
                raise HTTPException(
                    status_code=400,
                    detail=f"年度 {year} 不属于项目审计期（审计年度 {audit_year}）",
                )
        elif period_start is not None and period_end is not None:
            if not (period_start.year <= int(year) <= period_end.year):
                raise HTTPException(
                    status_code=400, detail=f"年度 {year} 不属于项目审计期"
                )


async def _resolve_independent_book_amount(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    account_codes: list[str],
) -> tuple[Optional[Decimal], Optional[str]]:
    """解析**独立于序时账**的账面金额用于总体完整性核对（Req2）。

    从 trial_balance（审定试算表，独立于 tb_ledger 序时账）按科目前缀汇总审定数
    （审定为空回退未审）。取不到返回 (None, None) → 前端显示"未执行核对"，
    绝不以序时账总体自身作为账面（避免自身比对假绿）。

    🔴 口径守卫（P1）：抽凭总体为**本期发生额（movement）**口径。trial_balance 是四列
    结构（无独立本期发生额列），其审定数对**损益/成本类（编码 5/6）= 发生额**，可与凭证
    发生额总体同口径比对；对**资产/负债/权益类（编码 1/2/3/4）= 期末余额**，与发生额总体
    口径不符（余额 vs 发生额是范畴错误）→ 返回 (None, None) 不提供独立核对，避免误导性差异。
    审计师若持有余额型可比总体，可在前端手工录入核对值。

    Returns:
        (book_amount, basis)；basis 标识来源（'trial_balance_audited_occurrence'）。
    """
    if not account_codes:
        return None, None
    # 仅损益/成本类（审定=发生额）与凭证发生额总体同口径；含资产/负债/权益类即口径不符
    if not all(str(code)[:1] in ("5", "6") for code in account_codes):
        return None, None
    prefix_conditions = [
        TrialBalance.standard_account_code.like(f"{code}%") for code in account_codes
    ]
    stmt = sa.select(
        sa.func.coalesce(
            sa.func.sum(
                sa.func.abs(
                    sa.func.coalesce(
                        TrialBalance.audited_amount, TrialBalance.unadjusted_amount, 0
                    )
                )
            ),
            0,
        ),
        sa.func.count(),
    ).where(
        TrialBalance.project_id == project_id,
        TrialBalance.year == year,
        TrialBalance.is_deleted == sa.false(),
        sa.or_(*prefix_conditions),
    )
    try:
        row = (await db.execute(stmt)).one()
        total, cnt = row[0], row[1]
        if not cnt:
            return None, None
        return Decimal(str(total)), "trial_balance_audited_occurrence"
    except Exception:  # noqa: BLE001 — 独立源取数失败不阻断抽样（Req2.5）
        return None, None


def _parse_iso_date(value: Any) -> Optional[date]:
    """将 filters 中的 date_from/date_to 解析为 date（接受 date 或 'YYYY-MM-DD' 字符串）。

    无法解析或为空时返回 None（调用方保留原有日期范围，保证向后兼容）。
    """
    if value is None or value == "":
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except (ValueError, TypeError):
        return None


def _coverage_rate(numerator: Any, denominator: Any) -> Decimal:
    """覆盖率（百分比，保留两位小数）。分母 ≤ 0 时返回 0.00。

    与算法层 _compute_coverage 口径一致（ROUND_HALF_EVEN）。
    """
    try:
        denom = Decimal(str(denominator))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal("0.00")
    if denom <= 0:
        return Decimal("0.00")
    try:
        numer = Decimal(str(numerator))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal("0.00")
    return (numer / denom * 100).quantize(Decimal("0.01"))


def _greatest_amount(item: dict) -> Decimal:
    """GREATEST(|debit_amount|, |credit_amount|) — 单条凭证的代表金额。"""
    debit = item.get("debit_amount")
    credit = item.get("credit_amount")
    try:
        debit_val = abs(Decimal(str(debit))) if debit is not None else Decimal("0")
    except (InvalidOperation, ValueError):
        debit_val = Decimal("0")
    try:
        credit_val = abs(Decimal(str(credit))) if credit is not None else Decimal("0")
    except (InvalidOperation, ValueError):
        credit_val = Decimal("0")
    return max(debit_val, credit_val)


def _derive_sampling_interval(
    method: SamplingMethod, sp: dict, population_amount: Decimal
) -> Optional[Decimal]:
    """推导 MUS 抽样间隔用于高值必选标识（R17）。

    优先使用前端显式传入的 sampling_interval；
    否则在 MUS 方法下按 总体金额 / mus_sample_size 推导；
    其他方法无间隔概念，返回 None（high_value 一律 False）。
    """
    explicit = sp.get("sampling_interval")
    if explicit is not None and explicit != "":
        try:
            val = Decimal(str(explicit))
            if val > 0:
                return val
        except (InvalidOperation, ValueError):
            pass

    if method == "mus":
        try:
            mus_size = int(sp.get("mus_sample_size", 10) or 0)
        except (ValueError, TypeError):
            mus_size = 0
        if mus_size > 0 and population_amount > 0:
            return population_amount / Decimal(mus_size)

    return None


def _echo_criteria_field(record: Any, key: str) -> Any:
    """从抽凭历史记录回显方法学字段。

    优先从 extraction_criteria JSON 读取；回退到记录顶层同名属性；均无则返回 None。
    """
    criteria = getattr(record, "extraction_criteria", None)
    if isinstance(criteria, dict) and key in criteria:
        return criteria.get(key)
    return getattr(record, key, None)


def _build_sampling_params(method: SamplingMethod, sp: dict) -> SamplingParams:
    """从前端传入的 sampling_params JSON 构建 SamplingParams dataclass"""
    params = SamplingParams()

    if method == "random":
        params.sample_size = int(sp.get("sample_size", 30))
    elif method == "stratified":
        raw_strata = sp.get("strata", [])
        strata: list[StratumConfig] = []
        for s in raw_strata:
            strata.append(
                StratumConfig(
                    lower_bound=Decimal(str(s.get("lower_bound", "0"))),
                    upper_bound=Decimal(str(s.get("upper_bound", "0"))),
                    sample_size=int(s.get("sample_size", 5)),
                )
            )
        params.strata = strata
    elif method == "specific_item":
        params.materiality_threshold = Decimal(
            str(sp.get("materiality_threshold", "0"))
        )
    elif method == "systematic":
        params.start_point = int(sp.get("start_point", 1))
        params.interval = int(sp.get("interval", 2))
    elif method == "mus":
        params.mus_sample_size = int(sp.get("mus_sample_size", 10))

    return params


async def _get_voucher_sampling_exclusions(
    db: AsyncSession,
    workpaper_id: UUID,
    preliminary_only: bool = False,
) -> tuple[list[str], list[str]]:
    """P3 行级排除拆分：返回 (legacy_voucher_nos, unit_ids)。

    - unit_ids：新日志 criteria.filled_unit_ids（ledger 行 id）→ 行级排除，避免"同一凭证号
      跨不同科目"被整张误排（跨科目过度排除）。
    - legacy_voucher_nos：仅来自**无 filled_unit_ids** 的旧日志 → 凭证级回退（向后兼容）。
    有 unit_ids 的日志不再贡献其 voucher_no，避免行级与凭证级双重排除。
    preliminary_only=True 时仅统计 phase='preliminary' 的日志。
    """
    stmt = select(WorkpaperExtractionLog.extraction_criteria).where(
        WorkpaperExtractionLog.workpaper_id == workpaper_id,
        WorkpaperExtractionLog.extraction_type == "voucher_sampling",
        WorkpaperExtractionLog.is_undone == False,  # noqa: E712
    )
    result = await db.execute(stmt)
    rows = result.scalars().all()

    legacy_nos: list[str] = []
    unit_ids: list[str] = []
    for criteria in rows:
        if not (criteria and isinstance(criteria, dict)):
            continue
        if preliminary_only and criteria.get("phase") != "preliminary":
            continue
        uids = criteria.get("filled_unit_ids")
        if isinstance(uids, list) and uids:
            unit_ids.extend(str(x) for x in uids)
        else:
            nos = criteria.get("filled_voucher_nos", [])
            if isinstance(nos, list):
                legacy_nos.extend(nos)
    return list(set(legacy_nos)), list(set(unit_ids))


async def _get_voucher_sampling_extracted_nos(
    db: AsyncSession,
    workpaper_id: UUID,
) -> list[str]:
    """从非撤销的 voucher_sampling 日志中收集所有已填充的凭证号

    查询 workpaper_extraction_log 中 extraction_type='voucher_sampling'
    且 is_undone=False 的记录，从 extraction_criteria.filled_voucher_nos 提取。
    """
    stmt = select(
        WorkpaperExtractionLog.extraction_criteria
    ).where(
        WorkpaperExtractionLog.workpaper_id == workpaper_id,
        WorkpaperExtractionLog.extraction_type == "voucher_sampling",
        WorkpaperExtractionLog.is_undone == False,  # noqa: E712
    )
    result = await db.execute(stmt)
    rows = result.scalars().all()

    voucher_nos: list[str] = []
    for criteria in rows:
        if criteria and isinstance(criteria, dict):
            filled = criteria.get("filled_voucher_nos", [])
            if isinstance(filled, list):
                voucher_nos.extend(filled)

    return list(set(voucher_nos))


async def _get_preliminary_voucher_nos(
    db: AsyncSession,
    workpaper_id: UUID,
) -> list[str]:
    """获取预审阶段已抽到的凭证号（用于年审排除）

    查询 extraction_type='voucher_sampling' 且 phase='preliminary' 且未撤销的记录。
    """
    stmt = select(
        WorkpaperExtractionLog.extraction_criteria
    ).where(
        WorkpaperExtractionLog.workpaper_id == workpaper_id,
        WorkpaperExtractionLog.extraction_type == "voucher_sampling",
        WorkpaperExtractionLog.is_undone == False,  # noqa: E712
    )
    result = await db.execute(stmt)
    rows = result.scalars().all()

    voucher_nos: list[str] = []
    for criteria in rows:
        if criteria and isinstance(criteria, dict):
            # 仅取 phase='preliminary' 的记录
            if criteria.get("phase") == "preliminary":
                filled = criteria.get("filled_voucher_nos", [])
                if isinstance(filled, list):
                    voucher_nos.extend(filled)

    return list(set(voucher_nos))


def _extract_voucher_nos_from_log(record: Any) -> set[str]:
    """从提取日志记录中提取凭证号集合

    优先从 extraction_criteria.filled_voucher_nos 获取，
    其次从 before_data 中提取 voucher_no 字段。
    """
    nos: set[str] = set()

    # 从 extraction_criteria 提取
    criteria = record.extraction_criteria
    if criteria and isinstance(criteria, dict):
        filled = criteria.get("filled_voucher_nos", [])
        if isinstance(filled, list):
            nos.update(filled)

    # 如果 extraction_criteria 没有，尝试从 before_data 提取
    if not nos and record.before_data:
        before = record.before_data
        if isinstance(before, list):
            for item in before:
                if isinstance(item, dict) and "voucher_no" in item:
                    nos.add(item["voucher_no"])

    return nos
