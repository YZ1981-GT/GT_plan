"""通用序时账条件查询服务 — LedgerSamplingService

被截止测试和未来 voucher-sampling-engine 共享。
内置 get_active_filter 调用，外部调用者无需关心 dataset 可见性。
所有方法设计为静态方法，无状态，便于复用。

核心规范：
- asyncpg 不支持 IN tuple 参数，必须用 = ANY(:list) + list 类型
- service 只 flush 不 commit（调用者控制事务）
- 金额使用 Decimal 精度，序列化为字符串避免浮点损失
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import date
from decimal import Decimal
from typing import Optional
from uuid import UUID, uuid4

import sqlalchemy as sa
from pydantic import BaseModel, Field
from sqlalchemy import Select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_platform_models import TbLedger, WorkpaperExtractionLog
from app.services.dataset_query import get_active_filter
from app.services.sampling_batch_service import SAMPLING_BATCH_STATUSES


def derive_idempotency_key(
    workpaper_id: UUID,
    extraction_type: str,
    fill_mode: str,
    filled_voucher_nos: list[str],
) -> str:
    """派生稳定幂等键：同一底稿+类型+模式+相同凭证集合 → 同一键（重复提交去重）。

    凭证集合排序后参与哈希，保证顺序无关；不同凭证集合 → 不同键（合法新批次）。
    """
    payload = json.dumps(
        {
            "wp": str(workpaper_id),
            "type": extraction_type or "",
            "mode": fill_mode or "",
            "vouchers": sorted(filled_voucher_nos or []),
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()

logger = logging.getLogger(__name__)


def _escape_like_pattern(keyword: str) -> str:
    """转义 LIKE 元字符使关键词按字面量匹配（配合 ilike(..., escape='\\')）。

    顺序固定：先转义反斜杠自身，再转义 % 与 _，避免二次转义。
    """
    return (
        keyword.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    )


def _ledger_row_to_item(row) -> dict:
    """TbLedger ORM 实例 → dict（金额序列化为字符串）。

    execute_with_stats 与 fetch_by_unit_ids 共用，保证样本行结构一致（零回归）。
    """
    return {
        "id": str(row.id),
        "voucher_date": row.voucher_date.isoformat() if row.voucher_date else None,
        "voucher_no": row.voucher_no,
        "account_code": row.account_code,
        "account_name": row.account_name,
        "voucher_type": row.voucher_type,
        "debit_amount": str(row.debit_amount) if row.debit_amount is not None else None,
        "credit_amount": str(row.credit_amount) if row.credit_amount is not None else None,
        "counterpart_account": row.counterpart_account,
        "summary": row.summary,
        "entry_seq": row.entry_seq,
        "accounting_period": row.accounting_period,
        "preparer": row.preparer,
        "company_code": row.company_code,
        "currency_code": row.currency_code,
    }


# ─── Pydantic Models ──────────────────────────────────────────────────────────


class LedgerQueryFilters(BaseModel):
    """通用序时账查询过滤条件（被截止测试和抽凭引擎共享）"""

    date_start: date
    date_end: date
    account_codes: list[str]  # 前缀匹配列表
    amount_threshold: Decimal = Decimal("0")
    # 金额上限：GREATEST(COALESCE(debit,0), COALESCE(credit,0)) <= amount_max（None=不限）
    amount_max: Optional[Decimal] = None
    # 离散会计月份 1-12（空=不按月份过滤）；用于「选 1 月和 12 月」不被扩为 1~12 连续区间
    months: list[int] = Field(default_factory=list)
    direction_filter: str = "all"  # "debit" | "credit" | "all"
    voucher_type_filter: list[str] = Field(default_factory=list)  # 空=不限
    summary_keyword: str = ""
    exclude_voucher_nos: list[str] = Field(default_factory=list)  # 排除的凭证号列表
    # P3 行级排除：排除的分录行 id（ledger id）。ledger_line 单位下按行排除，避免"同一
    # 凭证号跨不同科目"被整张误排（跨科目过度排除）；voucher 单位仍按 voucher_no 排除。
    exclude_unit_ids: list[str] = Field(default_factory=list)


class StatsResult(BaseModel):
    """查询统计摘要"""

    total_count: int
    debit_total: Decimal
    credit_total: Decimal
    # 全量总体代表金额：SUM(GREATEST(|debit|, |credit|))，不受分页/max_total 截断影响。
    # 供抽凭引擎的覆盖率分母与 MUS 抽样间隔使用（避免用截断后的 items 重算导致失真）。
    amount_total: Decimal = Decimal("0")
    by_voucher_type: dict[str, int]
    truncated: bool


class ExtractionLogCreate(BaseModel):
    """提取日志创建模型"""

    project_id: UUID
    workpaper_id: UUID
    user_id: UUID
    extraction_type: str = "cutoff"
    extraction_criteria: dict
    total_matched: int
    filled_count: int
    fill_mode: str  # "append" | "replace" | "merge"
    before_data: Optional[list[dict]] = None
    # ── 批次治理（V123 / Task 7 激活）──
    # idempotency_key: 稳定幂等键（同一回填重复提交去重）；None 则由 record_extraction_log 派生
    idempotency_key: Optional[str] = None
    # batch_id: 本次回填批次标识；None 则自动生成 uuid4
    batch_id: Optional[UUID] = None
    # status: 批次状态（draft/confirmed/filled/undone）；回填落库直接为 filled
    status: str = "filled"


class CutoffExtractRequest(BaseModel):
    """截止测试提取请求"""

    cutoff_date: date
    days_before: int = Field(default=5, ge=0, le=60)
    days_after: int = Field(default=10, ge=0, le=60)
    amount_threshold: Decimal = Decimal("0")
    account_codes: list[str]
    direction_filter: str = "all"
    voucher_type_filter: list[str] = Field(default_factory=list)
    summary_keyword: str = ""
    exclude_extracted: bool = True
    workpaper_id: UUID
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=100)


# ─── Service ──────────────────────────────────────────────────────────────────


class LedgerSamplingService:
    """通用序时账条件查询服务

    被截止测试和未来 voucher-sampling-engine 共享。
    内置 get_active_filter 调用，外部调用者无需关心 dataset 可见性。
    设计为无状态静态方法，便于复用。
    """

    @staticmethod
    async def build_ledger_query(
        db: AsyncSession,
        project_id: UUID,
        year: int,
        filters: LedgerQueryFilters,
    ) -> Select:
        """构建带条件的 SQLAlchemy Select 对象

        内部调用 get_active_filter 确保只查询 active dataset。
        必须包含 project_id + year 安全隔离条件。

        Args:
            db: 数据库会话
            project_id: 项目 ID（安全隔离）
            year: 年度（安全隔离）
            filters: 过滤条件

        Returns:
            SQLAlchemy Select 对象，可继续链式操作或直接执行
        """
        # 基础安全隔离：get_active_filter 内含 project_id + year + dataset 可见性
        active_filter = await get_active_filter(
            db, TbLedger.__table__, project_id, year
        )

        # 起始查询：始终包含安全隔离条件
        stmt = sa.select(TbLedger).where(active_filter)

        # 日期范围条件
        stmt = stmt.where(
            TbLedger.voucher_date >= filters.date_start,
            TbLedger.voucher_date <= filters.date_end,
        )

        # 科目前缀匹配：account_code LIKE ANY('{1122%,6001%}')
        # 使用 OR 构造多个 like 条件（兼容 asyncpg）
        if filters.account_codes:
            prefixes = [f"{code}%" for code in filters.account_codes]
            # 使用 sa.or_ + like 组合替代 LIKE ANY，因为 SQLAlchemy ORM 层
            # 对 any_ 结合 like 的支持因驱动而异；OR 方式最可靠
            prefix_conditions = [
                TbLedger.account_code.like(prefix) for prefix in prefixes
            ]
            stmt = stmt.where(sa.or_(*prefix_conditions))

        # 方向过滤
        if filters.direction_filter == "debit":
            stmt = stmt.where(TbLedger.debit_amount > 0)
        elif filters.direction_filter == "credit":
            stmt = stmt.where(TbLedger.credit_amount > 0)

        # 金额阈值：GREATEST(COALESCE(debit_amount,0), COALESCE(credit_amount,0)) >= threshold
        if filters.amount_threshold > 0:
            stmt = stmt.where(
                sa.func.greatest(
                    sa.func.coalesce(TbLedger.debit_amount, 0),
                    sa.func.coalesce(TbLedger.credit_amount, 0),
                )
                >= filters.amount_threshold
            )

        # 金额上限：GREATEST(COALESCE(debit,0), COALESCE(credit,0)) <= amount_max
        # 与 amount_threshold 口径一致（不取绝对值），此前前端传了但后端从不消费。
        if filters.amount_max is not None and filters.amount_max > 0:
            stmt = stmt.where(
                sa.func.greatest(
                    sa.func.coalesce(TbLedger.debit_amount, 0),
                    sa.func.coalesce(TbLedger.credit_amount, 0),
                )
                <= filters.amount_max
            )

        # 离散会计月份过滤：EXTRACT(MONTH FROM voucher_date) IN (months)
        # 在 date_start/date_end 范围内进一步按离散月份收窄，避免「1 月+12 月」被误扩为 1~12。
        if filters.months:
            valid_months = [m for m in filters.months if 1 <= int(m) <= 12]
            if valid_months:
                stmt = stmt.where(
                    sa.extract("month", TbLedger.voucher_date).in_(valid_months)
                )

        # 摘要关键词模糊匹配：转义 LIKE 元字符（\ % _）使其按字面量匹配，
        # 避免用户搜索含 %/_/\ 的摘要时被当作通配符误匹配/漏匹配。
        if filters.summary_keyword:
            escaped = _escape_like_pattern(filters.summary_keyword)
            stmt = stmt.where(
                TbLedger.summary.ilike(f"%{escaped}%", escape="\\")
            )

        # 凭证类型过滤
        if filters.voucher_type_filter:
            # asyncpg 不支持 IN tuple，使用 = ANY + list
            stmt = stmt.where(
                TbLedger.voucher_type.in_(filters.voucher_type_filter)
            )

        # 排除已提取凭证号：voucher_no NOT IN (...)
        # asyncpg 兼容：使用 .notin_ + list（SQLAlchemy 会转为 != ALL）
        if filters.exclude_voucher_nos:
            stmt = stmt.where(
                TbLedger.voucher_no.notin_(filters.exclude_voucher_nos)
            )

        # P3 行级排除：排除具体分录行 id（ledger_line 单位）。非法 UUID 静默跳过。
        if filters.exclude_unit_ids:
            valid_ids = []
            for raw in filters.exclude_unit_ids:
                try:
                    valid_ids.append(UUID(str(raw)))
                except (ValueError, AttributeError, TypeError):
                    continue
            if valid_ids:
                stmt = stmt.where(TbLedger.id.notin_(valid_ids))

        return stmt

    @staticmethod
    async def execute_with_stats(
        db: AsyncSession,
        query: Select,
        page: int,
        page_size: int,
        max_total: int = 500,
    ) -> tuple[list[dict], StatsResult]:
        """执行查询并返回分页数据+统计摘要

        - 分页返回（默认 page_size=50）
        - 统计：总匹配笔数、借贷合计、按凭证类型分类
        - 超过 max_total 时标记 truncated=true
        - 金额使用 Decimal 精度，序列化为字符串

        Args:
            db: 数据库会话
            query: build_ledger_query 返回的 Select 对象
            page: 页码（1-based）
            page_size: 每页条数
            max_total: 最大返回总数（超过时 truncated=True）

        Returns:
            (items, stats) — items 为 dict 列表（金额序列化为字符串），
            stats 为 StatsResult 统计摘要
        """
        # 构建子查询用于聚合计算
        subq = query.subquery()

        # 1. COUNT(*) 获取总匹配数
        count_stmt = sa.select(sa.func.count()).select_from(subq)
        count_result = await db.execute(count_stmt)
        total_count = count_result.scalar_one()

        # 2. 聚合查询：SUM(debit_amount)、SUM(credit_amount)、
        #    SUM(GREATEST(|debit|, |credit|))（全量总体代表金额，同一次往返算出，
        #    供抽凭覆盖率分母/MUS 间隔使用，不受 max_total 截断影响）
        agg_stmt = sa.select(
            sa.func.coalesce(sa.func.sum(subq.c.debit_amount), 0),
            sa.func.coalesce(sa.func.sum(subq.c.credit_amount), 0),
            sa.func.coalesce(
                sa.func.sum(
                    sa.func.greatest(
                        sa.func.abs(sa.func.coalesce(subq.c.debit_amount, 0)),
                        sa.func.abs(sa.func.coalesce(subq.c.credit_amount, 0)),
                    )
                ),
                0,
            ),
        ).select_from(subq)
        agg_result = await db.execute(agg_stmt)
        agg_row = agg_result.one()
        debit_total = Decimal(str(agg_row[0])) if agg_row[0] is not None else Decimal("0")
        credit_total = Decimal(str(agg_row[1])) if agg_row[1] is not None else Decimal("0")
        amount_total = Decimal(str(agg_row[2])) if agg_row[2] is not None else Decimal("0")

        # 3. GROUP BY voucher_type 统计各类型笔数
        type_stmt = sa.select(
            subq.c.voucher_type,
            sa.func.count(),
        ).select_from(subq).group_by(subq.c.voucher_type)
        type_result = await db.execute(type_stmt)
        by_voucher_type: dict[str, int] = {}
        for row in type_result.all():
            key = row[0] if row[0] is not None else "未分类"
            by_voucher_type[key] = row[1]

        # 4. 判断是否截断
        truncated = total_count > max_total

        # 5. 分页查询获取实际数据行
        # 排序：voucher_date, voucher_no 确保稳定分页
        data_query = query.order_by(
            TbLedger.voucher_date,
            TbLedger.voucher_no,
        )

        if truncated:
            # 超过 max_total 时限制总返回量
            data_query = data_query.limit(max_total)
        else:
            # 正常分页
            offset = (page - 1) * page_size
            data_query = data_query.offset(offset).limit(page_size)

        data_result = await db.execute(data_query)
        rows = data_result.scalars().all()

        # 6. ORM 实例 → dict，Decimal 金额序列化为字符串
        items: list[dict] = [_ledger_row_to_item(row) for row in rows]

        # 7. 构建 StatsResult
        stats = StatsResult(
            total_count=total_count,
            debit_total=debit_total,
            credit_total=credit_total,
            amount_total=amount_total,
            by_voucher_type=by_voucher_type,
            truncated=truncated,
        )

        return items, stats

    @staticmethod
    async def record_extraction_log(
        db: AsyncSession,
        log_data: ExtractionLogCreate,
    ) -> dict:
        """记录提取日志到 workpaper_extraction_log

        Args:
            db: 数据库会话
            log_data: 提取日志创建模型

        Returns:
            dict 含 id 和 created_at
        """
        # ── 批次治理（V123 激活）：状态校验 + 幂等键 + 批次号 ──
        status = log_data.status or "filled"
        if status not in SAMPLING_BATCH_STATUSES:
            raise ValueError(f"非法的抽样批次状态：{status}")

        # 幂等键：优先用调用方传入，否则从 criteria.filled_voucher_nos 稳定派生
        idem_key = log_data.idempotency_key
        if not idem_key:
            filled_nos = []
            crit = log_data.extraction_criteria or {}
            if isinstance(crit, dict):
                fv = crit.get("filled_voucher_nos")
                if isinstance(fv, list):
                    filled_nos = [str(v) for v in fv]
            # 无凭证号可派生时不设幂等键（key 为 NULL，不参与去重，保持向后兼容）
            if filled_nos:
                idem_key = derive_idempotency_key(
                    log_data.workpaper_id,
                    log_data.extraction_type,
                    log_data.fill_mode,
                    filled_nos,
                )

        # 幂等去重：同一底稿+幂等键已有未撤销记录 → 直接返回既有（幂等 no-op，不重复落库）
        if idem_key:
            existing = (
                await db.execute(
                    sa.select(WorkpaperExtractionLog)
                    .where(
                        WorkpaperExtractionLog.workpaper_id == log_data.workpaper_id,
                        WorkpaperExtractionLog.idempotency_key == idem_key,
                        WorkpaperExtractionLog.is_undone == sa.false(),
                    )
                    .limit(1)
                )
            ).scalar_one_or_none()
            if existing is not None:
                return {
                    "id": str(existing.id),
                    "created_at": existing.created_at.isoformat(),
                    "idempotent": True,
                }

        record = WorkpaperExtractionLog(
            project_id=log_data.project_id,
            workpaper_id=log_data.workpaper_id,
            user_id=log_data.user_id,
            extraction_type=log_data.extraction_type,
            extraction_criteria=log_data.extraction_criteria,
            total_matched=log_data.total_matched,
            filled_count=log_data.filled_count,
            fill_mode=log_data.fill_mode,
            before_data=log_data.before_data,
            batch_id=log_data.batch_id or uuid4(),
            idempotency_key=idem_key,
            status=status,
        )
        db.add(record)
        try:
            await db.flush()
        except IntegrityError:
            # 并发竞态：唯一约束命中 → 回滚本次插入，返回既有记录（幂等）
            await db.rollback()
            if idem_key:
                existing = (
                    await db.execute(
                        sa.select(WorkpaperExtractionLog)
                        .where(
                            WorkpaperExtractionLog.workpaper_id == log_data.workpaper_id,
                            WorkpaperExtractionLog.idempotency_key == idem_key,
                            WorkpaperExtractionLog.is_undone == sa.false(),
                        )
                        .limit(1)
                    )
                ).scalar_one_or_none()
                if existing is not None:
                    return {
                        "id": str(existing.id),
                        "created_at": existing.created_at.isoformat(),
                        "idempotent": True,
                    }
            raise
        return {
            "id": str(record.id),
            "created_at": record.created_at.isoformat(),
            "batch_id": str(record.batch_id) if record.batch_id else None,
        }

    @staticmethod
    async def get_extraction_history(
        db: AsyncSession,
        workpaper_id: UUID,
        extraction_type: str | None = None,
    ) -> list[dict]:
        """获取指定底稿的提取历史（按 created_at DESC）

        不返回 before_data（可能很大），仅返回摘要信息。

        Args:
            db: 数据库会话
            workpaper_id: 底稿 ID
            extraction_type: 可选提取类型过滤（如 "cutoff"）；缺省不过滤，向后兼容。
                截止测试历史应传 "cutoff" 以避免混入其它抽样日志。

        Returns:
            按时间倒序的历史记录列表
        """
        conds = [WorkpaperExtractionLog.workpaper_id == workpaper_id]
        if extraction_type:
            conds.append(WorkpaperExtractionLog.extraction_type == extraction_type)
        stmt = (
            sa.select(WorkpaperExtractionLog)
            .where(*conds)
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
            }
            for row in rows
        ]

    @staticmethod
    async def undo_extraction(
        db: AsyncSession,
        log_id: UUID,
        workpaper_id: UUID,
        extraction_type: str | None = None,
    ) -> dict:
        """撤销指定提取记录，返回 before_data

        仅允许撤销最近一次非撤销记录。

        Args:
            db: 数据库会话
            log_id: 要撤销的日志记录 ID
            workpaper_id: 底稿 ID（安全校验）
            extraction_type: 可选提取类型过滤（如 "cutoff"）；缺省不过滤，向后兼容。
                传入时"最近一次"仅在同类型日志范围内判定，避免跨类型误判最新。

        Returns:
            {"success": True, "before_data": [...]}

        Raises:
            ValueError: 记录不存在 / 无权操作 / 非最新记录
        """
        # 1. 加载记录
        stmt = sa.select(WorkpaperExtractionLog).where(
            WorkpaperExtractionLog.id == log_id
        )
        result = await db.execute(stmt)
        record = result.scalar_one_or_none()

        if record is None:
            raise ValueError("提取记录不存在")

        # 2. 安全校验：workpaper_id 归属
        if record.workpaper_id != workpaper_id:
            raise ValueError("无权操作此记录")

        # 3. 验证是最新非撤销记录（可按 extraction_type 限定范围）
        latest_conds = [
            WorkpaperExtractionLog.workpaper_id == workpaper_id,
            WorkpaperExtractionLog.is_undone == False,  # noqa: E712
        ]
        if extraction_type:
            latest_conds.append(
                WorkpaperExtractionLog.extraction_type == extraction_type
            )
        latest_stmt = (
            sa.select(WorkpaperExtractionLog)
            .where(*latest_conds)
            .order_by(WorkpaperExtractionLog.created_at.desc())
            .limit(1)
        )
        latest_result = await db.execute(latest_stmt)
        latest = latest_result.scalar_one_or_none()

        if latest is None or latest.id != log_id:
            raise ValueError("仅可撤销最近一次操作")

        # 4. 标记撤销（status='undone' 使 V123 部分唯一索引强制"同批次至多撤销一次"）
        record.is_undone = True
        record.status = "undone"
        await db.flush()

        # 5. 返回 before_data（None 视为空列表）
        before_data = record.before_data if record.before_data is not None else []
        return {"success": True, "before_data": before_data}

    # ─── 全量抽样框：两阶段"标识抽样 + 按标识取回"（voucher-sampling-hardening Task 2/3）──

    @staticmethod
    async def locate_sampling_units(
        db: AsyncSession,
        query: Select,
        unit: str = "ledger_line",
        max_units: int | None = None,
        min_greatest: Optional[Decimal] = None,
    ) -> list[dict]:
        """阶段 A：全量定位——对满足过滤的**全部**总体返回抽样所需最小投影。

        不受 execute_with_stats 的 max_total（完整行内存）限制：仅取标识 + 代表金额，
        使随机 / 系统 / MUS 抽样可覆盖全总体，高值必选可在全量上识别。

        Args:
            db: 会话
            query: build_ledger_query 返回的 Select（含全部过滤 + 安全隔离）
            unit: 'ledger_line'（分录行，unit_id=ledger id）或 'voucher'（整张凭证，unit_id=voucher_no）
            max_units: 可选硬上限（极端超大总体保护）；命中则截断并标记
            min_greatest: 可选 GREATEST 阈值（P2 性能）——仅用于 specific_item（高值全选，
                确定性、无种子）：在 DB 侧过滤 GREATEST(|debit|,|credit|) >= 阈值，避免把
                低于阈值的行全部物化进内存。等价于 canonical specific_item 在合成总体上的
                过滤（合成金额即 DB abs-greatest），非 specific_item 方法禁止传入。

        Returns:
            list[dict]，每项 {unit_id, voucher_no, voucher_date, greatest_amount}；
            voucher 单位下 greatest_amount 为该凭证内各行 GREATEST(|debit|,|credit|) 之和。
        """
        proj = LedgerSamplingService._build_locate_projection(
            query.subquery(), unit, min_greatest
        )
        if max_units is not None:
            proj = proj.limit(max_units)

        result = await db.execute(proj)
        units: list[dict] = []
        for row in result.all():
            units.append(
                {
                    "unit_id": str(row.unit_id),
                    "voucher_no": row.voucher_no,
                    "voucher_date": (
                        row.voucher_date.isoformat() if row.voucher_date else None
                    ),
                    "greatest_amount": (
                        Decimal(str(row.greatest_amount))
                        if row.greatest_amount is not None
                        else Decimal("0")
                    ),
                }
            )
        return units

    @staticmethod
    def _build_locate_projection(
        subq, unit: str, min_greatest: Optional[Decimal] = None
    ) -> Select:
        """构建阶段 A 最小投影 Select（不执行）——供 locate_sampling_units 与单测复用。

        - ledger_line：select id/voucher_no/voucher_date/greatest_line，按日期+凭证号排序。
        - voucher：group by voucher_no，金额=Σ行 GREATEST，日期=min。
        - min_greatest（P2，仅 specific_item）：ledger_line 用 WHERE、voucher 用 HAVING
          在 DB 侧过滤 GREATEST >= 阈值。
        """
        greatest_line = sa.func.greatest(
            sa.func.abs(sa.func.coalesce(subq.c.debit_amount, 0)),
            sa.func.abs(sa.func.coalesce(subq.c.credit_amount, 0)),
        )
        if unit == "voucher":
            voucher_greatest = sa.func.coalesce(sa.func.sum(greatest_line), 0)
            stmt = (
                sa.select(
                    subq.c.voucher_no.label("unit_id"),
                    subq.c.voucher_no.label("voucher_no"),
                    sa.func.min(subq.c.voucher_date).label("voucher_date"),
                    voucher_greatest.label("greatest_amount"),
                )
                .select_from(subq)
                .group_by(subq.c.voucher_no)
                .order_by(sa.func.min(subq.c.voucher_date), subq.c.voucher_no)
            )
            if min_greatest is not None:
                stmt = stmt.having(voucher_greatest >= min_greatest)
            return stmt
        stmt = (
            sa.select(
                subq.c.id.label("unit_id"),
                subq.c.voucher_no.label("voucher_no"),
                subq.c.voucher_date.label("voucher_date"),
                greatest_line.label("greatest_amount"),
            )
            .select_from(subq)
            .order_by(subq.c.voucher_date, subq.c.voucher_no)
        )
        if min_greatest is not None:
            stmt = stmt.where(greatest_line >= min_greatest)
        return stmt

    @staticmethod
    async def fetch_by_unit_ids(
        db: AsyncSession,
        query: Select,
        unit: str,
        unit_ids: list[str],
    ) -> list[dict]:
        """阶段 B：按阶段 A 命中的抽样单位标识取回完整样本行（与 execute_with_stats item 同结构）。

        - ledger_line：按 TbLedger.id ∈ unit_ids 取回（每单位一行）。
        - voucher：按 TbLedger.voucher_no ∈ unit_ids 在过滤范围内取回该凭证全部分录行。

        保持过滤范围（复用传入 query 的 WHERE），不越过原过滤取数。
        """
        if not unit_ids:
            return []

        subq = query.subquery()
        base = sa.select(TbLedger).select_from(
            TbLedger.__table__.join(
                subq, TbLedger.id == subq.c.id
            )
        )
        # 上述 join 等价于"在过滤结果内"，再按单位键过滤
        if unit == "voucher":
            stmt = base.where(TbLedger.voucher_no.in_(unit_ids)).order_by(
                TbLedger.voucher_date, TbLedger.voucher_no, TbLedger.entry_seq
            )
        else:
            # 分录行：unit_id 是 ledger id（字符串）→ 直接按 id 过滤
            stmt = base.where(
                sa.cast(TbLedger.id, sa.String).in_([str(u) for u in unit_ids])
            ).order_by(TbLedger.voucher_date, TbLedger.voucher_no)

        result = await db.execute(stmt)
        rows = result.scalars().all()
        return [_ledger_row_to_item(row) for row in rows]
