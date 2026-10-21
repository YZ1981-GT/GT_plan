"""总体完整性核对 — 序时账 vs 科目余额表发生额（SQLite 真 ORM 行）

spec: voucher-sampling-reconcile-balance-source
Task 3

覆盖：
- select_top_level_codes 纯函数（父子层级、单层、叶子无父在范围内）
- resolve_population_reconcile 异步函数
  - 科目前缀匹配（1122 匹配 1122.01；多码）
  - 最高层行选取（父子同时存在时只取父行）
  - 数据集过滤（非 active 行不纳入）
  - 年度窗口（跨年度凭证不纳入 — 序时账侧）
  - 不可用原因三类：无科目 / 余额表无行 / 取数异常
  - 取数异常后外层会话仍可继续用
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.audit_platform_models import TbBalance, TbLedger
from app.services.sampling_population_reconcile import (
    PopulationReconcileFacts,
    resolve_population_reconcile,
    select_top_level_codes,
)

# SQLite 没有 JSONB 类型，用 JSON 替代
SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)

_PID = uuid.uuid4()
_YEAR = 2025
_DATASET = uuid.uuid4()


# ─── Fixtures ─────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def db() -> AsyncSession:
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session


def _bal(code: str, debit=None, credit=None, ds=None) -> TbBalance:
    """构造一行余额表。"""
    return TbBalance(
        project_id=_PID,
        year=_YEAR,
        company_code="001",
        account_code=code,
        account_name=f"科目{code}",
        debit_amount=Decimal(str(debit)) if debit is not None else None,
        credit_amount=Decimal(str(credit)) if credit is not None else None,
        dataset_id=ds or _DATASET,
    )


def _led(code: str, vdate: date, debit=None, credit=None, ds=None) -> TbLedger:
    """构造一行序时账。"""
    return TbLedger(
        project_id=_PID,
        year=_YEAR,
        company_code="001",
        voucher_date=vdate,
        voucher_no=f"记-{vdate.isoformat()}-{code}",
        account_code=code,
        debit_amount=Decimal(str(debit)) if debit is not None else None,
        credit_amount=Decimal(str(credit)) if credit is not None else None,
        dataset_id=ds or _DATASET,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# select_top_level_codes 纯函数
# ═══════════════════════════════════════════════════════════════════════════════


class TestSelectTopLevelCodes:
    def test_empty(self):
        assert select_top_level_codes([]) == []

    def test_single(self):
        assert select_top_level_codes(["1122"]) == ["1122"]

    def test_parent_child(self):
        result = select_top_level_codes(["1122", "1122.01", "1122.02"])
        assert result == ["1122"]

    def test_siblings_no_parent(self):
        """无共同前缀在集合中时，兄弟都是最高层。"""
        result = select_top_level_codes(["1122.01", "1122.02"])
        assert sorted(result) == ["1122.01", "1122.02"]

    def test_multi_tree(self):
        result = select_top_level_codes(["1122", "1122.01", "1221", "1221.01", "1221.02"])
        assert sorted(result) == ["1122", "1221"]

    def test_three_levels(self):
        result = select_top_level_codes(["1012", "1012.02", "1012.02.01"])
        assert result == ["1012"]

    def test_disjoint(self):
        result = select_top_level_codes(["6001", "6401", "6601"])
        assert sorted(result) == ["6001", "6401", "6601"]


# ═══════════════════════════════════════════════════════════════════════════════
# resolve_population_reconcile 异步函数
# ═══════════════════════════════════════════════════════════════════════════════


class TestResolvePopulationReconcile:
    """SQLite 真 ORM 行测试。"""

    @pytest.mark.asyncio
    async def test_no_account_codes(self, db: AsyncSession):
        """无科目 → 不可用 + 原因。"""
        r = await resolve_population_reconcile(db, _PID, _YEAR, [], _DATASET)
        assert r.available is False
        assert "未指定科目" in (r.unavailable_reason or "")

    @pytest.mark.asyncio
    async def test_no_balance_rows(self, db: AsyncSession):
        """余额表无行 → 不可用 + 原因（含映射建议，因为 9999 无映射）。"""
        r = await resolve_population_reconcile(db, _PID, _YEAR, ["9999"], _DATASET)
        assert r.available is False
        assert "科目余额表中无所选科目（9999）的行" in (r.unavailable_reason or "")
        assert "科目映射" in (r.unavailable_reason or "")  # 无映射时追加映射建议

    @pytest.mark.asyncio
    async def test_no_balance_rows_many_codes_summarized(self, db: AsyncSession):
        """超过 5 个科目时只列前 5 个并写明总数。"""
        codes = [f"99{i:02d}" for i in range(7)]
        r = await resolve_population_reconcile(db, _PID, _YEAR, codes, _DATASET)
        assert "9900、9901、9902、9903、9904 等 7 个" in (r.unavailable_reason or "")

    @pytest.mark.asyncio
    async def test_basic_match(self, db: AsyncSession):
        """余额表与序时账一致 → available=True，数值相等。"""
        db.add_all([
            _bal("1122", debit=1000, credit=800),
            _led("1122.01", date(2025, 3, 15), debit=600, credit=None),
            _led("1122.01", date(2025, 6, 20), debit=400, credit=None),
            _led("1122.02", date(2025, 4, 10), debit=None, credit=800),
        ])
        await db.commit()

        r = await resolve_population_reconcile(db, _PID, _YEAR, ["1122"], _DATASET)
        assert r.available is True
        assert r.basis == "tb_balance_movement"
        assert r.ledger_debit == Decimal("1000")
        assert r.ledger_credit == Decimal("800")  # 第三行 1122.02 credit=800 也匹配前缀
        assert r.book_debit == Decimal("1000")
        assert r.book_credit == Decimal("800")

    @pytest.mark.asyncio
    async def test_top_level_selection(self, db: AsyncSession):
        """父子行同时存在时，只取父行（不重复加）。"""
        db.add_all([
            _bal("1122", debit=1000, credit=800),
            _bal("1122.01", debit=600, credit=500),
            _bal("1122.02", debit=400, credit=300),
            _led("1122.01", date(2025, 1, 10), debit=1000, credit=800),
        ])
        await db.commit()

        r = await resolve_population_reconcile(db, _PID, _YEAR, ["1122"], _DATASET)
        assert r.available is True
        # 只取 1122（最高层），不加 1122.01 + 1122.02
        assert r.book_debit == Decimal("1000")
        assert r.book_credit == Decimal("800")

    @pytest.mark.asyncio
    async def test_multi_code(self, db: AsyncSession):
        """多个科目码合计。"""
        db.add_all([
            _bal("1122", debit=1000, credit=800),
            _bal("1221", debit=500, credit=300),
            _led("1122.01", date(2025, 2, 1), debit=1000, credit=None),
            _led("1221.01", date(2025, 3, 1), debit=500, credit=300),
        ])
        await db.commit()

        r = await resolve_population_reconcile(db, _PID, _YEAR, ["1122", "1221"], _DATASET)
        assert r.available is True
        assert r.book_debit == Decimal("1500")
        assert r.book_credit == Decimal("1100")

    @pytest.mark.asyncio
    async def test_dataset_filter(self, db: AsyncSession):
        """非当前数据集的行不纳入。"""
        other_ds = uuid.uuid4()
        db.add_all([
            _bal("1122", debit=1000, credit=800, ds=_DATASET),
            _bal("1122", debit=9999, credit=9999, ds=other_ds),  # 应被排除
            _led("1122.01", date(2025, 1, 1), debit=1000, credit=800, ds=_DATASET),
            _led("1122.01", date(2025, 1, 1), debit=8888, credit=8888, ds=other_ds),  # 应被排除
        ])
        await db.commit()

        r = await resolve_population_reconcile(db, _PID, _YEAR, ["1122"], _DATASET)
        assert r.available is True
        assert r.book_debit == Decimal("1000")
        assert r.ledger_debit == Decimal("1000")

    @pytest.mark.asyncio
    async def test_year_window(self, db: AsyncSession):
        """跨年度的序时账凭证不纳入。"""
        db.add_all([
            _bal("1122", debit=500, credit=300),
            _led("1122.01", date(2025, 6, 15), debit=500, credit=300),
            _led("1122.01", date(2024, 12, 31), debit=999, credit=999),  # 跨年，应排除
        ])
        await db.commit()

        r = await resolve_population_reconcile(db, _PID, _YEAR, ["1122"], _DATASET)
        assert r.available is True
        assert r.ledger_debit == Decimal("500")
        assert r.ledger_credit == Decimal("300")

    @pytest.mark.asyncio
    async def test_negative_amounts(self, db: AsyncSession):
        """红字冲销（负数）在序时账侧正确聚合。"""
        db.add_all([
            _bal("1122", debit=800, credit=900),
            _led("1122.01", date(2025, 1, 5), debit=1000, credit=None),
            _led("1122.01", date(2025, 2, 10), debit=-200, credit=None),  # 红字冲销
            _led("1122.02", date(2025, 3, 15), debit=None, credit=900),
        ])
        await db.commit()

        r = await resolve_population_reconcile(db, _PID, _YEAR, ["1122"], _DATASET)
        assert r.available is True
        assert r.ledger_debit == Decimal("800")  # 1000 + (-200)
        assert r.ledger_credit == Decimal("900")

    @pytest.mark.asyncio
    async def test_no_dataset_fallback(self, db: AsyncSession):
        """dataset_id=None 时降级为 is_deleted=false 过滤（不按数据集）。"""
        db.add_all([
            _bal("1122", debit=100, credit=50),
            _led("1122.01", date(2025, 1, 1), debit=100, credit=50),
        ])
        await db.commit()

        r = await resolve_population_reconcile(db, _PID, _YEAR, ["1122"], None)
        assert r.available is True
        assert r.book_debit == Decimal("100")

    @pytest.mark.asyncio
    async def test_exception_does_not_pollute_session(self, db: AsyncSession):
        """取数异常 → 返回「不可用 + 取数失败」而不是抛出；之后会话仍可查询。

        ⚠️ 本例只证明「异常被吞成不可用」：打桩的 execute 在发 SQL 之前就抛错，SQLite 也没有
        PG「语句失败即整个事务中止」的语义，所以它**证明不了保存点隔离**。保存点隔离由
        ``test_sampling_population_reconcile_pg.py``（真实 PostgreSQL、库里真实报错）守护。
        """
        db.add_all([
            _bal("1122", debit=100, credit=50),
            _led("1122.01", date(2025, 1, 1), debit=100, credit=50),
        ])
        await db.commit()

        # 正常调用
        r1 = await resolve_population_reconcile(db, _PID, _YEAR, ["1122"], _DATASET)
        assert r1.available is True

        # 制造异常（monkeypatch begin_nested 让保存点内抛错）
        import sqlalchemy as sa
        from unittest.mock import patch, AsyncMock

        original_execute = db.execute

        call_count = 0

        async def _boom_execute(stmt, *a, **kw):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:  # 前两次调用（在 begin_nested 内）抛异常
                raise RuntimeError("模拟取数失败")
            return await original_execute(stmt, *a, **kw)

        with patch.object(db, "execute", side_effect=_boom_execute):
            r2 = await resolve_population_reconcile(db, _PID, _YEAR, ["1122"], _DATASET)
        assert r2.available is False
        assert "取数失败" in (r2.unavailable_reason or "")

        # 恢复后会话仍可用
        from app.models.audit_platform_models import TbBalance as _TbB
        result = await db.execute(sa.select(sa.func.count()).select_from(_TbB.__table__))
        count = result.scalar_one()
        assert count >= 1  # 会话未被污染

    @pytest.mark.asyncio
    async def test_to_stats_backward_compatible(self, db: AsyncSession):
        """to_stats() 输出保留 book_amount / reconcile_available / reconcile_basis 向后兼容字段。"""
        db.add_all([
            _bal("6001", debit=500, credit=500),
            _led("6001.01", date(2025, 1, 1), debit=500, credit=500),
        ])
        await db.commit()

        r = await resolve_population_reconcile(db, _PID, _YEAR, ["6001"], _DATASET)
        s = r.to_stats()
        assert "book_amount" in s
        assert "reconcile_available" in s
        assert "reconcile_basis" in s
        assert s["reconcile_available"] is True
        assert s["reconcile_basis"] == "tb_balance_movement"
        # book_amount = |借| + |贷|
        assert Decimal(s["book_amount"]) == Decimal("1000")
        # 新字段也存在
        assert "reconcile_ledger_debit" in s
        assert "reconcile_book_debit" in s
        assert "reconcile_unavailable_reason" in s


class TestToStatsUnavailable:
    def test_unavailable_stats(self):
        r = PopulationReconcileFacts(available=False, unavailable_reason="test reason")
        s = r.to_stats()
        assert s["reconcile_available"] is False
        assert s["book_amount"] is None
        assert s["reconcile_unavailable_reason"] == "test reason"


# ═══════════════════════════════════════════════════════════════════════════════
# resolve_effective_codes 映射反查 + 映射后核对
# ═══════════════════════════════════════════════════════════════════════════════


from app.models.audit_platform_models import AccountMapping
from app.services.sampling_population_reconcile import resolve_effective_codes


def _mapping(standard: str, original: str) -> AccountMapping:
    """构造一行科目映射（标准码 → 企业原始码）。"""
    return AccountMapping(
        project_id=_PID,
        original_account_code=original,
        original_account_name=f"企业科目{original}",
        standard_account_code=standard,
        mapping_type="auto_exact",
    )


class TestResolveEffectiveCodes:
    """映射反查纯函数测试。"""

    @pytest.mark.asyncio
    async def test_no_mapping_fallback(self, db: AsyncSession):
        """无映射记录 → 退回标准编码，mapping_used=False。"""
        codes, used = await resolve_effective_codes(db, _PID, ["1122"])
        assert codes == ["1122"]
        assert used is False

    @pytest.mark.asyncio
    async def test_empty_codes(self, db: AsyncSession):
        """空科目列表 → 原样返回，mapping_used=False。"""
        codes, used = await resolve_effective_codes(db, _PID, [])
        assert codes == []
        assert used is False

    @pytest.mark.asyncio
    async def test_with_mapping(self, db: AsyncSession):
        """有映射 → 返回原始编码，mapping_used=True。"""
        db.add_all([
            _mapping("1122", "SA1122"),
            _mapping("1122", "SA1122.01"),
        ])
        await db.commit()

        codes, used = await resolve_effective_codes(db, _PID, ["1122"])
        assert used is True
        assert sorted(codes) == ["SA1122", "SA1122.01"]

    @pytest.mark.asyncio
    async def test_partial_mapping(self, db: AsyncSession):
        """部分标准科目有映射：映射到的原始码 + 未映射的标准码合并返回。

        传入 ['1122', '1221']，只有 1122 有映射 → 返回 ['SA1122', '1221']，
        mapping_used=True（因为有映射存在）。1221 保留标准编码做前缀匹配，
        避免企业恰好用标准编码体系的科目被丢掉。
        """
        db.add(_mapping("1122", "SA1122"))
        await db.commit()

        codes, used = await resolve_effective_codes(db, _PID, ["1122", "1221"])
        assert used is True
        assert sorted(codes) == ["1221", "SA1122"]  # 映射码 + 未映射标准码

    @pytest.mark.asyncio
    async def test_deleted_mapping_ignored(self, db: AsyncSession):
        """已删除的映射不被反查。"""
        m = _mapping("1122", "SA1122")
        m.is_deleted = True
        db.add(m)
        await db.commit()

        codes, used = await resolve_effective_codes(db, _PID, ["1122"])
        assert codes == ["1122"]  # 退回标准编码
        assert used is False

    @pytest.mark.asyncio
    async def test_prefix_match_in_standard_code(self, db: AsyncSession):
        """标准码做前缀匹配：传入 '1122'，映射表中 standard='1122.01' 也能命中。"""
        db.add(_mapping("1122.01", "QY-AR-SUB01"))
        await db.commit()

        codes, used = await resolve_effective_codes(db, _PID, ["1122"])
        assert used is True
        assert codes == ["QY-AR-SUB01"]

    @pytest.mark.asyncio
    async def test_other_project_ignored(self, db: AsyncSession):
        """其他项目的映射不被反查。"""
        other_pid = uuid.uuid4()
        m = AccountMapping(
            project_id=other_pid,
            original_account_code="SA1122",
            original_account_name="其他项目科目",
            standard_account_code="1122",
            mapping_type="auto_exact",
        )
        db.add(m)
        await db.commit()

        codes, used = await resolve_effective_codes(db, _PID, ["1122"])
        assert codes == ["1122"]  # 退回标准编码
        assert used is False


class TestReconcileWithMapping:
    """映射反查接入核对的集成测试。"""

    @pytest.mark.asyncio
    async def test_mapping_used_in_reconcile(self, db: AsyncSession):
        """有映射时核对用原始编码查余额表和序时账。"""
        # 映射：标准 1122 → 企业 SA1122
        db.add(_mapping("1122", "SA1122"))
        # 余额表和序时账都用企业编码
        db.add_all([
            _bal("SA1122", debit=1000, credit=800),
            _led("SA1122.01", date(2025, 3, 15), debit=600, credit=None),
            _led("SA1122.02", date(2025, 6, 20), debit=400, credit=800),
        ])
        await db.commit()

        # 传入标准编码 1122 → 内部映射反查得到 SA1122 → 匹配到数据
        r = await resolve_population_reconcile(db, _PID, _YEAR, ["1122"], _DATASET)
        assert r.available is True
        assert r.mapping_used is True
        assert r.book_debit == Decimal("1000")
        assert r.book_credit == Decimal("800")
        assert r.ledger_debit == Decimal("1000")  # 600 + 400
        assert r.ledger_credit == Decimal("800")

    @pytest.mark.asyncio
    async def test_no_mapping_standard_code_direct(self, db: AsyncSession):
        """无映射时退回标准编码直接匹配（向后兼容）。"""
        db.add_all([
            _bal("1122", debit=500, credit=300),
            _led("1122.01", date(2025, 1, 10), debit=500, credit=300),
        ])
        await db.commit()

        r = await resolve_population_reconcile(db, _PID, _YEAR, ["1122"], _DATASET)
        assert r.available is True
        assert r.mapping_used is False
        assert r.book_debit == Decimal("500")

    @pytest.mark.asyncio
    async def test_mapping_no_balance_rows_suggests_mapping(self, db: AsyncSession):
        """有映射但余额表无匹配行时，不建议"确认映射"（因为映射已存在）。"""
        db.add(_mapping("1122", "SA1122"))
        # 余额表里没有 SA1122 的行
        await db.commit()

        r = await resolve_population_reconcile(db, _PID, _YEAR, ["1122"], _DATASET)
        assert r.available is False
        assert r.mapping_used is True
        # 有映射时不追加映射建议
        assert "科目映射" not in (r.unavailable_reason or "")

    @pytest.mark.asyncio
    async def test_no_mapping_no_balance_rows_suggests_mapping(self, db: AsyncSession):
        """无映射且余额表无行 → 不可用原因包含映射建议。"""
        r = await resolve_population_reconcile(db, _PID, _YEAR, ["9999"], _DATASET)
        assert r.available is False
        assert r.mapping_used is False
        assert "科目映射" in (r.unavailable_reason or "")

    @pytest.mark.asyncio
    async def test_mapping_used_in_to_stats(self, db: AsyncSession):
        """to_stats() 输出包含 reconcile_mapping_used 字段。"""
        db.add_all([
            _mapping("1122", "SA1122"),
            _bal("SA1122", debit=100, credit=50),
            _led("SA1122", date(2025, 1, 1), debit=100, credit=50),
        ])
        await db.commit()

        r = await resolve_population_reconcile(db, _PID, _YEAR, ["1122"], _DATASET)
        s = r.to_stats()
        assert "reconcile_mapping_used" in s
        assert s["reconcile_mapping_used"] is True

    @pytest.mark.asyncio
    async def test_top_level_after_mapping(self, db: AsyncSession):
        """映射后的原始编码也正确做最高层行选取。"""
        # 映射：1122 → SA1122, 1122 → SA1122.01
        db.add_all([
            _mapping("1122", "SA1122"),
            _mapping("1122", "SA1122.01"),
        ])
        # 余额表有父子两级
        db.add_all([
            _bal("SA1122", debit=1000, credit=800),
            _bal("SA1122.01", debit=600, credit=500),
        ])
        # 序时账
        db.add(_led("SA1122.01", date(2025, 1, 1), debit=1000, credit=800))
        await db.commit()

        r = await resolve_population_reconcile(db, _PID, _YEAR, ["1122"], _DATASET)
        assert r.available is True
        assert r.mapping_used is True
        # 只取最高层 SA1122，不重复加 SA1122.01
        assert r.book_debit == Decimal("1000")
        assert r.book_credit == Decimal("800")
