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

import logging
from datetime import date
from decimal import Decimal
from typing import Optional
from uuid import UUID

import sqlalchemy as sa
from pydantic import BaseModel, Field
from sqlalchemy import Select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_platform_models import TbLedger, WorkpaperExtractionLog
from app.services.dataset_query import get_active_filter

logger = logging.getLogger(__name__)


# ─── Pydantic Models ──────────────────────────────────────────────────────────


class LedgerQueryFilters(BaseModel):
    """通用序时账查询过滤条件（被截止测试和抽凭引擎共享）"""

    date_start: date
    date_end: date
    account_codes: list[str]  # 前缀匹配列表
    amount_threshold: Decimal = Decimal("0")
    direction_filter: str = "all"  # "debit" | "credit" | "all"
    voucher_type_filter: list[str] = Field(default_factory=list)  # 空=不限
    summary_keyword: str = ""
    exclude_voucher_nos: list[str] = Field(default_factory=list)  # 排除的凭证号列表


class StatsResult(BaseModel):
    """查询统计摘要"""

    total_count: int
    debit_total: Decimal
    credit_total: Decimal
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

        # 摘要关键词模糊匹配
        if filters.summary_keyword:
            stmt = stmt.where(
                TbLedger.summary.ilike(f"%{filters.summary_keyword}%")
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

        # 2. 聚合查询：SUM(debit_amount)、SUM(credit_amount)
        agg_stmt = sa.select(
            sa.func.coalesce(sa.func.sum(subq.c.debit_amount), 0),
            sa.func.coalesce(sa.func.sum(subq.c.credit_amount), 0),
        ).select_from(subq)
        agg_result = await db.execute(agg_stmt)
        agg_row = agg_result.one()
        debit_total = Decimal(str(agg_row[0])) if agg_row[0] is not None else Decimal("0")
        credit_total = Decimal(str(agg_row[1])) if agg_row[1] is not None else Decimal("0")

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
        items: list[dict] = []
        for row in rows:
            item = {
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
            items.append(item)

        # 7. 构建 StatsResult
        stats = StatsResult(
            total_count=total_count,
            debit_total=debit_total,
            credit_total=credit_total,
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
        )
        db.add(record)
        await db.flush()
        return {
            "id": str(record.id),
            "created_at": record.created_at.isoformat(),
        }

    @staticmethod
    async def get_extraction_history(
        db: AsyncSession,
        workpaper_id: UUID,
    ) -> list[dict]:
        """获取指定底稿的提取历史（按 created_at DESC）

        不返回 before_data（可能很大），仅返回摘要信息。

        Args:
            db: 数据库会话
            workpaper_id: 底稿 ID

        Returns:
            按时间倒序的历史记录列表
        """
        stmt = (
            sa.select(WorkpaperExtractionLog)
            .where(WorkpaperExtractionLog.workpaper_id == workpaper_id)
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
    ) -> dict:
        """撤销指定提取记录，返回 before_data

        仅允许撤销最近一次非撤销记录。

        Args:
            db: 数据库会话
            log_id: 要撤销的日志记录 ID
            workpaper_id: 底稿 ID（安全校验）

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

        # 3. 验证是最新非撤销记录
        latest_stmt = (
            sa.select(WorkpaperExtractionLog)
            .where(
                WorkpaperExtractionLog.workpaper_id == workpaper_id,
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

        # 5. 返回 before_data（None 视为空列表）
        before_data = record.before_data if record.before_data is not None else []
        return {"success": True, "before_data": before_data}
