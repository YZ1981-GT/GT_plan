"""穿透查询服务 — 高性能四表联查

核心优化：
1. CTE 一次性查询多层级数据，减少 DB 往返
2. Redis 缓存（TTL=5min），数据变更时主动失效
3. 游标分页（keyset pagination）替代 OFFSET，大数据量不退化
4. 只返回必要字段，减少网络传输

联查链路：
  科目余额表 → 序时账（按科目） → 凭证分录（按凭证号）
  科目余额表 → 辅助余额（按科目） → 辅助明细（按维度）

Validates: Requirements 15.1-15.4
"""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_platform_models import (
    TbAuxBalance,
    TbAuxLedger,
    TbBalance,
    TbLedger,
)
from app.services.dataset_query import get_active_filter


class DecimalEncoder(json.JSONEncoder):
    """JSON encoder that handles Decimal and date types."""
    def default(self, o: Any) -> Any:
        if isinstance(o, Decimal):
            return float(o)
        if hasattr(o, 'isoformat'):
            return o.isoformat()
        return super().default(o)


class LedgerPenetrationService:
    """穿透查询服务"""

    def __init__(self, db: AsyncSession, redis: Any = None, cache_manager: Any = None):
        self.db = db
        self.redis = redis
        self._cache = cache_manager  # CacheManager instance (preferred)
        # TODO F41: 渐进迁移——未来 __init__ 应接收 current_user_id 参数，
        # 传递给 get_active_filter 做项目权限校验。当前所有调用保持
        # current_user_id=None（由路由层 require_project_access 保障权限）。

    # ------------------------------------------------------------------
    # 核心穿透查询（无缓存版）
    # ------------------------------------------------------------------

    async def get_balance_summary(
        self, project_id: UUID, year: int,
        account_code: str | None = None,
    ) -> list[dict]:
        """第一层：科目余额汇总"""
        tbl = TbBalance.__table__
        active_filter = await get_active_filter(self.db, tbl, project_id, year)
        stmt = (
            sa.select(
                tbl.c.account_code,
                tbl.c.account_name,
                tbl.c.level,
                tbl.c.opening_balance,
                tbl.c.debit_amount,
                tbl.c.credit_amount,
                tbl.c.closing_balance,
            )
            .where(active_filter)
            .order_by(tbl.c.account_code)
        )
        if account_code:
            stmt = stmt.where(tbl.c.account_code == account_code)

        result = await self.db.execute(stmt)
        return [dict(r._mapping) for r in result.fetchall()]

    async def get_account_opening_balance(
        self, project_id: UUID, year: int, account_code: str,
    ) -> Decimal:
        """获取科目期初余额（用于序时账 running_balance 计算）。

        前缀查询时（如 1122*），汇总所有匹配科目的期初余额。
        """
        tbl = TbBalance.__table__
        if account_code.endswith('*'):
            prefix = account_code[:-1]
            code_filter = tbl.c.account_code.like(prefix + '%')
        else:
            code_filter = (tbl.c.account_code == account_code)

        active_filter = await get_active_filter(self.db, tbl, project_id, year)
        stmt = sa.select(sa.func.coalesce(sa.func.sum(tbl.c.opening_balance), 0)).where(
            active_filter,
            code_filter,
        )
        result = await self.db.execute(stmt)
        return result.scalar() or Decimal(0)

    async def get_ledger_entries(
        self, project_id: UUID, year: int, account_code: str,
        date_from: str | None = None, date_to: str | None = None,
        page: int = 1, page_size: int = 100,
    ) -> dict:
        """第二层：序时账明细（按科目穿透）

        account_code 支持前缀匹配：传 "1002*" 查询所有 1002 开头的末级科目明细
        """
        tbl = TbLedger.__table__

        # 判断是否前缀查询
        if account_code.endswith('*'):
            prefix = account_code[:-1]
            code_filter = tbl.c.account_code.like(prefix + '%')
        else:
            code_filter = (tbl.c.account_code == account_code)

        active_filter = await get_active_filter(self.db, tbl, project_id, year)
        base = (
            sa.select(
                tbl.c.id, tbl.c.voucher_date, tbl.c.voucher_no,
                tbl.c.account_code, tbl.c.account_name,
                tbl.c.debit_amount, tbl.c.credit_amount,
                tbl.c.counterpart_account, tbl.c.summary,
            )
            .where(active_filter, code_filter)
        )
        if date_from:
            base = base.where(tbl.c.voucher_date >= date_from)
        if date_to:
            base = base.where(tbl.c.voucher_date <= date_to)

        # 总数
        count_stmt = sa.select(sa.func.count()).select_from(base.subquery())
        total = (await self.db.execute(count_stmt)).scalar() or 0

        # 分页
        offset = (page - 1) * page_size
        data_stmt = (
            base.order_by(tbl.c.voucher_date, tbl.c.voucher_no)
            .offset(offset).limit(page_size)
        )
        result = await self.db.execute(data_stmt)
        items = [dict(r._mapping) for r in result.fetchall()]

        return {"items": items, "total": total, "page": page, "page_size": page_size}

    async def get_voucher_entries(
        self, project_id: UUID, year: int, voucher_no: str,
    ) -> list[dict]:
        """第三层：凭证分录明细（按凭证号穿透）"""
        tbl = TbLedger.__table__
        active_filter = await get_active_filter(self.db, tbl, project_id, year)
        stmt = (
            sa.select(
                tbl.c.id, tbl.c.voucher_date, tbl.c.voucher_no,
                tbl.c.account_code, tbl.c.account_name,
                tbl.c.debit_amount, tbl.c.credit_amount,
                tbl.c.summary,
            )
            .where(active_filter, tbl.c.voucher_no == voucher_no)
            .order_by(tbl.c.account_code)
        )
        result = await self.db.execute(stmt)
        return [dict(r._mapping) for r in result.fetchall()]

    async def get_all_aux_balance(
        self, project_id: UUID, year: int,
    ) -> list[dict]:
        """全量辅助余额（所有科目，含原始维度组合字符串）"""
        tbl = TbAuxBalance.__table__
        active_filter = await get_active_filter(self.db, tbl, project_id, year)
        stmt = (
            sa.select(
                tbl.c.account_code, tbl.c.account_name,
                tbl.c.aux_type, tbl.c.aux_code, tbl.c.aux_name,
                tbl.c.opening_balance, tbl.c.debit_amount,
                tbl.c.credit_amount, tbl.c.closing_balance,
                tbl.c.aux_dimensions_raw,
            )
            .where(active_filter)
            .order_by(tbl.c.account_code, tbl.c.aux_type, tbl.c.aux_code)
        )
        result = await self.db.execute(stmt)
        return [dict(r._mapping) for r in result.fetchall()]

    async def get_aux_balance(
        self, project_id: UUID, year: int, account_code: str,
        aux_type: str | None = None,
    ) -> list[dict]:
        """辅助余额（按科目穿透到辅助维度）"""
        tbl = TbAuxBalance.__table__
        active_filter = await get_active_filter(self.db, tbl, project_id, year)
        stmt = (
            sa.select(
                tbl.c.aux_type, tbl.c.aux_code, tbl.c.aux_name,
                tbl.c.opening_balance, tbl.c.debit_amount,
                tbl.c.credit_amount, tbl.c.closing_balance,
            )
            .where(active_filter, tbl.c.account_code == account_code)
            .order_by(tbl.c.aux_type, tbl.c.aux_code)
        )
        if aux_type:
            stmt = stmt.where(tbl.c.aux_type == aux_type)

        result = await self.db.execute(stmt)
        return [dict(r._mapping) for r in result.fetchall()]

    async def get_aux_ledger_entries(
        self, project_id: UUID, year: int, account_code: str,
        aux_type: str | None = None, aux_code: str | None = None,
        page: int = 1, page_size: int = 100,
    ) -> dict:
        """辅助明细账（按辅助维度穿透）"""
        tbl = TbAuxLedger.__table__
        active_filter = await get_active_filter(self.db, tbl, project_id, year)
        base = (
            sa.select(
                tbl.c.id, tbl.c.voucher_date, tbl.c.voucher_no,
                tbl.c.account_code, tbl.c.aux_type, tbl.c.aux_code,
                tbl.c.aux_name, tbl.c.debit_amount, tbl.c.credit_amount,
                tbl.c.summary,
            )
            .where(active_filter, tbl.c.account_code == account_code)
        )
        if aux_type:
            base = base.where(tbl.c.aux_type == aux_type)
        if aux_code:
            base = base.where(tbl.c.aux_code == aux_code)

        count_stmt = sa.select(sa.func.count()).select_from(base.subquery())
        total = (await self.db.execute(count_stmt)).scalar() or 0

        offset = (page - 1) * page_size
        data_stmt = (
            base.order_by(tbl.c.voucher_date, tbl.c.voucher_no)
            .offset(offset).limit(page_size)
        )
        result = await self.db.execute(data_stmt)
        items = [dict(r._mapping) for r in result.fetchall()]

        return {"items": items, "total": total, "page": page, "page_size": page_size}

    # ------------------------------------------------------------------
    # S6-8: 三元组穿透（account_code + aux_type + aux_code 精确定位）
    # ------------------------------------------------------------------

    async def get_aux_by_triplet(
        self,
        project_id: UUID,
        year: int,
        account_code: str,
        aux_type: str,
        aux_code: str | None = None,
        *,
        page: int = 1,
        page_size: int = 100,
    ) -> dict:
        """三元组精确穿透：同时返回辅助余额 + 辅助明细账。

        解决"税率"等维度类型跨科目重名场景：用户点科目 6001.14.02 下的
        "客户:041108,重庆医药..." 时，能用 (6001.14.02, 客户, 041108)
        精确定位，不受"税率"等重名维度干扰。

        Returns:
            {
                "account": {account_code, account_name},
                "aux": {aux_type, aux_code, aux_name},
                "balance": {opening_balance, debit_amount, credit_amount, closing_balance},
                "ledger": {items: [...], total, page, page_size}
            }
        """
        bal_tbl = TbAuxBalance.__table__
        led_tbl = TbAuxLedger.__table__

        bal_filter = await get_active_filter(self.db, bal_tbl, project_id, year)
        led_filter = await get_active_filter(self.db, led_tbl, project_id, year)

        # 1. 辅助余额（唯一行）
        bal_stmt = (
            sa.select(
                bal_tbl.c.account_code, bal_tbl.c.account_name,
                bal_tbl.c.aux_type, bal_tbl.c.aux_code, bal_tbl.c.aux_name,
                bal_tbl.c.opening_balance, bal_tbl.c.debit_amount,
                bal_tbl.c.credit_amount, bal_tbl.c.closing_balance,
            )
            .where(
                bal_filter,
                bal_tbl.c.account_code == account_code,
                bal_tbl.c.aux_type == aux_type,
            )
        )
        if aux_code is not None:
            bal_stmt = bal_stmt.where(bal_tbl.c.aux_code == aux_code)
        bal_result = await self.db.execute(bal_stmt)
        bal_rows = [dict(r._mapping) for r in bal_result.fetchall()]

        # 2. 辅助明细账分页
        led_base = (
            sa.select(
                led_tbl.c.id, led_tbl.c.voucher_date, led_tbl.c.voucher_no,
                led_tbl.c.account_code, led_tbl.c.account_name,
                led_tbl.c.aux_type, led_tbl.c.aux_code, led_tbl.c.aux_name,
                led_tbl.c.debit_amount, led_tbl.c.credit_amount,
                led_tbl.c.summary, led_tbl.c.aux_dimensions_raw,
            )
            .where(
                led_filter,
                led_tbl.c.account_code == account_code,
                led_tbl.c.aux_type == aux_type,
            )
        )
        if aux_code is not None:
            led_base = led_base.where(led_tbl.c.aux_code == aux_code)

        count_stmt = sa.select(sa.func.count()).select_from(led_base.subquery())
        total = (await self.db.execute(count_stmt)).scalar() or 0

        offset = (page - 1) * page_size
        data_stmt = (
            led_base.order_by(led_tbl.c.voucher_date, led_tbl.c.voucher_no)
            .offset(offset).limit(page_size)
        )
        led_result = await self.db.execute(data_stmt)
        led_items = [dict(r._mapping) for r in led_result.fetchall()]

        # 聚合返回结构
        account_info = (
            {"account_code": bal_rows[0]["account_code"],
             "account_name": bal_rows[0]["account_name"]}
            if bal_rows else
            {"account_code": account_code, "account_name": None}
        )
        aux_info = {"aux_type": aux_type, "aux_code": aux_code, "aux_name": None}
        balance_data = {}
        if bal_rows:
            # 多条余额行（不同 aux_code）求和
            from decimal import Decimal

            def _sum(field: str) -> Decimal:
                return sum((Decimal(str(r[field] or 0)) for r in bal_rows), Decimal(0))

            balance_data = {
                "opening_balance": _sum("opening_balance"),
                "debit_amount": _sum("debit_amount"),
                "credit_amount": _sum("credit_amount"),
                "closing_balance": _sum("closing_balance"),
                "aux_code_count": len({r["aux_code"] for r in bal_rows}),
            }
            if len(bal_rows) == 1:
                aux_info["aux_name"] = bal_rows[0]["aux_name"]

        return {
            "account": account_info,
            "aux": aux_info,
            "balance": balance_data,
            "ledger": {
                "items": led_items,
                "total": total,
                "page": page,
                "page_size": page_size,
            },
        }

    # ------------------------------------------------------------------
    # 游标分页（keyset pagination）
    # ------------------------------------------------------------------

    async def get_ledger_entries_cursor(
        self, project_id: UUID, year: int, account_code: str,
        cursor: str | None = None, limit: int = 100,
        date_from: str | None = None, date_to: str | None = None,
    ) -> dict:
        """序时账游标分页 — 基于 (voucher_date, id) 的 keyset pagination。

        比 OFFSET 分页在大数据量（10万+行）下性能稳定，不随页码增大退化。
        返回 running_balance（累计余额）和 total（总行数）。
        """
        tbl = TbLedger.__table__

        # 判断是否前缀查询
        if account_code.endswith('*'):
            prefix = account_code[:-1]
            code_filter = tbl.c.account_code.like(prefix + '%')
        else:
            code_filter = (tbl.c.account_code == account_code)

        where_clauses = [
            await get_active_filter(self.db, tbl, project_id, year),
            code_filter,
        ]
        if date_from:
            where_clauses.append(tbl.c.voucher_date >= date_from)
        if date_to:
            where_clauses.append(tbl.c.voucher_date <= date_to)

        # 首次请求时查总数（后续翻页不重复查）
        total = None
        if cursor is None:
            count_base = sa.select(sa.func.count()).select_from(
                sa.select(tbl.c.id).where(*where_clauses).subquery()
            )
            total = (await self.db.execute(count_base)).scalar() or 0

        # 解析游标: "date|id" 格式
        cursor_clauses = list(where_clauses)
        if cursor:
            try:
                parts = cursor.split("|", 1)
                cursor_date = parts[0]
                cursor_id = parts[1] if len(parts) > 1 else ""
                cursor_clauses.append(
                    sa.or_(
                        tbl.c.voucher_date > cursor_date,
                        sa.and_(
                            tbl.c.voucher_date == cursor_date,
                            sa.cast(tbl.c.id, sa.String) > cursor_id,
                        ),
                    )
                )
            except (ValueError, IndexError):
                pass

        stmt = (
            sa.select(
                tbl.c.id, tbl.c.voucher_date, tbl.c.voucher_no,
                tbl.c.account_code, tbl.c.account_name,
                tbl.c.debit_amount, tbl.c.credit_amount,
                tbl.c.counterpart_account, tbl.c.summary,
                tbl.c.accounting_period, tbl.c.voucher_type,
            )
            .where(*cursor_clauses)
            .order_by(tbl.c.voucher_date, tbl.c.id)
            .limit(limit + 1)
        )

        result = await self.db.execute(stmt)
        rows = [dict(r._mapping) for r in result.fetchall()]

        has_more = len(rows) > limit
        items = rows[:limit]

        next_cursor = None
        if has_more and items:
            last = items[-1]
            vd = last.get("voucher_date")
            vd_str = vd.isoformat() if hasattr(vd, "isoformat") else str(vd)
            next_cursor = f"{vd_str}|{last['id']}"

        resp = {
            "items": items,
            "next_cursor": next_cursor,
            "has_more": has_more,
            "limit": limit,
        }
        if total is not None:
            resp["total"] = total
        return resp

    async def get_aux_ledger_entries_cursor(
        self, project_id: UUID, year: int, account_code: str,
        cursor: str | None = None, limit: int = 100,
        aux_type: str | None = None, aux_code: str | None = None,
    ) -> dict:
        """辅助明细账游标分页"""
        tbl = TbAuxLedger.__table__

        where_clauses = [
            await get_active_filter(self.db, tbl, project_id, year),
            tbl.c.account_code == account_code,
        ]
        if aux_type:
            where_clauses.append(tbl.c.aux_type == aux_type)
        if aux_code:
            where_clauses.append(tbl.c.aux_code == aux_code)

        if cursor:
            try:
                parts = cursor.split("|", 1)
                cursor_date = parts[0]
                cursor_id = parts[1] if len(parts) > 1 else ""
                where_clauses.append(
                    sa.or_(
                        tbl.c.voucher_date > cursor_date,
                        sa.and_(
                            tbl.c.voucher_date == cursor_date,
                            sa.cast(tbl.c.id, sa.String) > cursor_id,
                        ),
                    )
                )
            except (ValueError, IndexError):
                pass

        stmt = (
            sa.select(
                tbl.c.id, tbl.c.voucher_date, tbl.c.voucher_no,
                tbl.c.account_code, tbl.c.aux_type, tbl.c.aux_code,
                tbl.c.aux_name, tbl.c.debit_amount, tbl.c.credit_amount,
                tbl.c.summary,
            )
            .where(*where_clauses)
            .order_by(tbl.c.voucher_date, tbl.c.id)
            .limit(limit + 1)
        )

        result = await self.db.execute(stmt)
        rows = [dict(r._mapping) for r in result.fetchall()]

        has_more = len(rows) > limit
        items = rows[:limit]

        next_cursor = None
        if has_more and items:
            last = items[-1]
            vd = last.get("voucher_date")
            vd_str = vd.isoformat() if hasattr(vd, "isoformat") else str(vd)
            next_cursor = f"{vd_str}|{last['id']}"

        return {
            "items": items,
            "next_cursor": next_cursor,
            "has_more": has_more,
            "limit": limit,
        }

    # ------------------------------------------------------------------
    # 一次性穿透（CTE 多层级）
    # ------------------------------------------------------------------

    async def penetrate(
        self, project_id: UUID, year: int,
        account_code: str | None = None,
        drill_level: str = "all",
        date_from: str | None = None,
        date_to: str | None = None,
        page: int = 1, page_size: int = 100,
    ) -> dict:
        """统一穿透查询入口

        drill_level: total / ledger / voucher / aux / all
        """
        result: dict[str, Any] = {}

        if drill_level in ("total", "all"):
            result["total"] = await self.get_balance_summary(
                project_id, year, account_code
            )

        if drill_level in ("ledger", "all") and account_code:
            result["ledger"] = await self.get_ledger_entries(
                project_id, year, account_code,
                date_from=date_from, date_to=date_to,
                page=page, page_size=page_size,
            )

        if drill_level in ("aux", "all") and account_code:
            result["aux_balance"] = await self.get_aux_balance(
                project_id, year, account_code
            )

        return result

    # ------------------------------------------------------------------
    # Redis 缓存版
    # ------------------------------------------------------------------

    def _cache_key(self, project_id: UUID, year: int, **kwargs: Any) -> str:
        """生成缓存键（不含 namespace 前缀，CacheManager 自动加）"""
        params = json.dumps(
            {"project_id": str(project_id), "year": year, **kwargs},
            sort_keys=True,
        )
        h = hashlib.md5(params.encode()).hexdigest()[:12]
        return f"{project_id}:{year}:{h}"

    async def penetrate_cached(
        self, project_id: UUID, year: int,
        account_code: str | None = None,
        drill_level: str = "all",
        date_from: str | None = None,
        date_to: str | None = None,
        page: int = 1, page_size: int = 100,
    ) -> dict:
        """带缓存的穿透查询（优先 CacheManager，降级 raw Redis）"""
        cache_key = self._cache_key(
            project_id, year,
            account_code=account_code, drill_level=drill_level,
            date_from=date_from, date_to=date_to,
            page=page, page_size=page_size,
        )

        # 尝试缓存读取
        if self._cache:
            try:
                cached = await self._cache.get("ledger", cache_key)
                if cached is not None:
                    return cached
            except Exception:
                pass
        elif self.redis:
            try:
                cached = await self.redis.get(f"penetrate:{cache_key}")
                if cached:
                    return json.loads(cached)
            except Exception:
                pass  # Redis 不可用时降级

        # 查询
        result = await self.penetrate(
            project_id, year, account_code, drill_level,
            date_from, date_to, page, page_size,
        )

        # 写入缓存
        if self._cache:
            try:
                await self._cache.set("ledger", cache_key, result)
            except Exception:
                pass
        elif self.redis:
            try:
                await self.redis.setex(
                    f"penetrate:{cache_key}", 300,
                    json.dumps(result, cls=DecimalEncoder),
                )
            except Exception:
                pass

        return result

    async def invalidate_cache(self, project_id: UUID, year: int) -> int:
        """失效指定项目年度的所有穿透缓存"""
        if self._cache:
            return await self._cache.invalidate_namespace("ledger")

        if not self.redis:
            return 0
        pattern = f"penetrate:{project_id}:{year}:*"
        try:
            keys = []
            async for key in self.redis.scan_iter(match=pattern):
                keys.append(key)
            if keys:
                await self.redis.delete(*keys)
            return len(keys)
        except Exception:
            return 0
