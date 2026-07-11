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
from app.models.audit_platform_models import WorkpaperExtractionLog
from app.models.core import User
from app.services.ledger_sampling_service import (
    LedgerQueryFilters,
    LedgerSamplingService,
)
from app.services.voucher_sampling_algorithms import (
    SamplingMethod,
    SamplingParams,
    StratumConfig,
    execute_sampling,
)
from app.services.version_trail_service import VersionTrailService

logger = logging.getLogger(__name__)

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

        # 2. 排除已提取凭证号
        exclude_voucher_nos: list[str] = []
        if exclude_extracted:
            exclude_voucher_nos = await _get_voucher_sampling_extracted_nos(
                db, req.workpaper_id
            )

        # 3. phase='final' 时自动追加预审已抽凭证号到排除列表
        if req.phase == "final":
            preliminary_nos = await _get_preliminary_voucher_nos(
                db, req.workpaper_id
            )
            # 合并去重
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
            direction_filter=direction_filter,
            voucher_type_filter=voucher_type_filter,
            summary_keyword=summary_keyword,
            exclude_voucher_nos=exclude_voucher_nos,
        )

        # 5. 构建查询
        query = await LedgerSamplingService.build_ledger_query(
            db, pid, req.year, ledger_filters
        )

        # 6. 获取全量 population（不分页，max_total=10000 足够覆盖）
        items, stats = await LedgerSamplingService.execute_with_stats(
            db, query, page=1, page_size=10000, max_total=10000
        )

        # 7. 构建 SamplingParams
        sp = req.sampling_params
        sampling_params = _build_sampling_params(req.sampling_method, sp)

        # 8. 执行抽样算法
        result = execute_sampling(
            method=req.sampling_method,
            population=items,
            params=sampling_params,
            seed=req.random_seed,
        )

        # 9. 总体金额（账面来源=序时账总体，按 GREATEST 汇总）与 MUS 抽样间隔推导
        #    population_amount / book_amount 用于总体完整性校验（R19）
        population_amount = sum(
            (_greatest_amount(it) for it in items), Decimal("0")
        )
        sampling_interval = _derive_sampling_interval(
            req.sampling_method, sp, population_amount
        )

        # 10. 高值必选项标识（R17）：单笔金额 ≥ 抽样间隔者标记 high_value
        #     无可推导间隔时 high_value 一律 False（向后兼容默认值）
        marked_items: list[dict] = []
        for it in result.items:
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
                "population_count": result.population_count,
                "population_debit_total": str(result.population_debit_total),
                "population_credit_total": str(result.population_credit_total),
                "population_amount": str(population_amount),
                # 账面来源合计（序时账总体 GREATEST 汇总）；无法获取时降级为 null
                "book_amount": str(population_amount) if items else None,
                "sample_count": result.sample_count,
                "sample_debit_total": str(result.sample_debit_total),
                "sample_credit_total": str(result.sample_credit_total),
                "count_coverage_rate": str(result.count_coverage_rate),
                "amount_coverage_rate": str(result.amount_coverage_rate),
                "sampling_interval": (
                    str(sampling_interval) if sampling_interval is not None else None
                ),
            },
            "seed_used": result.seed_used,
            "truncated": result.truncated,
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

        # 4. 标记撤销
        record.is_undone = True
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
