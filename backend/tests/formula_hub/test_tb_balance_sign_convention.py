"""试算平衡口径识别测试（需求 16.1，ADR-FHIC-15）。

4 口径夹具（debit_positive / v2_positive × 已结转 / 未结转）
+ 资不抵债 + 医疗器械 / 华氏真 PG 只读。
"""
from __future__ import annotations

from decimal import Decimal

import pytest
import pytest_asyncio

from app.services.consistency_gate._tb_sign import (
    EXPECTED_CATEGORIES,
    BalanceVerdict,
    balance_diff,
)

D = Decimal

# ---------------------------------------------------------------------------
# 纯函数单测：balance_diff
# ---------------------------------------------------------------------------


class TestBalanceDiffPure:
    """4 口径 + 资不抵债 + 口径未知"""

    def test_v2_positive_settled(self):
        """v2 口径、已结转（收入 / 费用 = 0）：asset − liability − equity"""
        sums = {
            "asset": D("1000"), "liability": D("600"), "equity": D("400"),
            "revenue": D("0"), "expense": D("0"),
        }
        v = balance_diff(sums)
        assert v.convention == "v2_positive"
        assert v.diff == D("0")
        assert v.warning == ""

    def test_v2_positive_unsettled(self):
        """v2 口径、未结转（收入/费用非 0）"""
        sums = {
            "asset": D("1500"), "liability": D("600"), "equity": D("400"),
            "revenue": D("800"), "expense": D("300"),
        }
        # diff = 1500 − 600 − 400 − (800 − 300) = 1500 − 600 − 400 − 500 = 0
        v = balance_diff(sums)
        assert v.convention == "v2_positive"
        assert v.diff == D("0")

    def test_debit_positive_settled(self):
        """借正贷负口径、已结转：五类之和"""
        sums = {
            "asset": D("1000"), "liability": D("-600"), "equity": D("-400"),
            "revenue": D("0"), "expense": D("0"),
        }
        v = balance_diff(sums)
        assert v.convention == "debit_positive"
        assert v.diff == D("0")
        assert "借正贷负" in v.warning

    def test_debit_positive_unsettled(self):
        """借正贷负口径、未结转"""
        sums = {
            "asset": D("1500"), "liability": D("-600"), "equity": D("-400"),
            "revenue": D("-800"), "expense": D("300"),
        }
        # diff = 1500 + (-600) + (-400) + (-800) + 300 = 0
        v = balance_diff(sums)
        assert v.convention == "debit_positive"
        assert v.diff == D("0")

    def test_v2_insolvent(self):
        """v2 资不抵债：权益 < 0、负债 > 0 → 仍按 v2"""
        sums = {
            "asset": D("100"), "liability": D("200"), "equity": D("-100"),
            "revenue": D("0"), "expense": D("0"),
        }
        # diff = 100 − 200 − (−100) − 0 = 0
        v = balance_diff(sums)
        assert v.convention == "v2_positive"
        assert v.diff == D("0")

    def test_sign_unknown(self):
        """负债与权益都为 0 → convention=None"""
        sums = {
            "asset": D("100"), "liability": D("0"), "equity": D("0"),
            "revenue": D("0"), "expense": D("0"),
        }
        v = balance_diff(sums)
        assert v.convention is None
        assert "无法识别" in v.warning

    def test_liability_zero_equity_positive(self):
        """负债 = 0、权益 > 0 → v2"""
        sums = {
            "asset": D("500"), "liability": D("0"), "equity": D("500"),
            "revenue": D("0"), "expense": D("0"),
        }
        v = balance_diff(sums)
        assert v.convention == "v2_positive"

    def test_liability_zero_equity_negative(self):
        """负债 = 0、权益 < 0 → 借正贷负"""
        sums = {
            "asset": D("500"), "liability": D("0"), "equity": D("-500"),
            "revenue": D("0"), "expense": D("0"),
        }
        v = balance_diff(sums)
        assert v.convention == "debit_positive"

    def test_nonzero_diff(self):
        """差额非 0"""
        sums = {
            "asset": D("1100"), "liability": D("600"), "equity": D("400"),
            "revenue": D("0"), "expense": D("0"),
        }
        v = balance_diff(sums)
        assert v.convention == "v2_positive"
        assert v.diff == D("100")  # 1100 − 600 − 400 = 100

    def test_missing_category_defaults_zero(self):
        """缺失的类别按 0 处理"""
        sums = {"asset": D("100"), "liability": D("100")}
        v = balance_diff(sums)
        assert v.convention == "v2_positive"
        assert v.diff == D("0")


# ---------------------------------------------------------------------------
# 真 PG 只读（需求 16.1 后半）
# ---------------------------------------------------------------------------

@pytest.mark.pg_only
class TestTbBalanceSignConventionPG:
    """医疗器械 / 华氏真 PG 只读：生产差额 = 独立 SQL 差额"""

    @pytest_asyncio.fixture()
    async def _projects(self, pg_tx):
        """返回有试算表的活项目列表（只读）"""
        from sqlalchemy import text

        sql = text("""
            SELECT DISTINCT p.id, p.name,
                   COALESCE(p.audit_year, EXTRACT(YEAR FROM p.audit_period_end)::int) AS year
            FROM projects p
            JOIN trial_balance tb ON tb.project_id = p.id AND tb.is_deleted = false
            WHERE p.is_deleted = false
              AND COALESCE(p.audit_year, EXTRACT(YEAR FROM p.audit_period_end)::int) IS NOT NULL
        """)
        result = await pg_tx.execute(sql)
        return result.all()

    async def _gold_diff_for(self, pg_tx, project_id, year):
        """独立 SQL 差额计算（不 import 生产代码的叶子函数）"""
        from sqlalchemy import text

        sql = text("""
            SELECT standard_account_code, account_category, audited_amount
            FROM trial_balance
            WHERE project_id = :pid AND year = :yr AND is_deleted = false
        """)
        result = await pg_tx.execute(sql, {"pid": project_id, "yr": year})
        rows = result.all()
        if not rows:
            return None

        by_cat: dict[str, list[tuple[str, Decimal]]] = {}
        for code, cat, amt in rows:
            c = str(cat) if cat else "unknown"
            by_cat.setdefault(c, []).append((
                str(code) if code else "",
                Decimal(str(amt)) if amt is not None else Decimal("0"),
            ))

        def _leaf_codes(codes):
            ordered = sorted(set(codes))
            succs = [*ordered[1:], None]
            return frozenset(
                c for c, n in zip(ordered, succs) if n is None or not n.startswith(c)
            )

        sums = {}
        for cat, items in by_cat.items():
            if cat not in {"asset", "liability", "equity", "revenue", "expense"}:
                continue
            codes = [c for c, _ in items]
            leaves = _leaf_codes(codes)
            sums[cat] = sum(
                (a for c, a in items if c in leaves), Decimal("0")
            )

        return balance_diff(sums)

    @pytest.mark.asyncio
    async def test_active_projects_diff_matches_gold(self, pg_tx, _projects):
        """每个有试算表的活项目：生产差额 = 独立 SQL 差额"""
        from app.services.consistency_gate._gate import ConsistencyGate

        assert len(_projects) > 0, "快照库无有试算表的活项目"
        gate = ConsistencyGate(pg_tx)

        for row in _projects:
            pid, name, year = row[0], row[1], row[2]
            gold = await self._gold_diff_for(pg_tx, pid, year)
            if gold is None:
                continue
            prod = await gate.check_tb_balance(pid, year)

            if gold.convention is None:
                assert prod.status in ("not_executed",), (
                    f"{name}: 口径未知但生产未标 not_executed"
                )
                continue

            assert prod.status in ("passed", "failed"), (
                f"{name}: 生产状态 {prod.status}"
            )
            assert f"差额={gold.diff:,.2f}" in prod.details, (
                f"{name}: 生产差额与金标准不符\n"
                f"  金标准 diff={gold.diff}, convention={gold.convention}\n"
                f"  生产 details={prod.details}"
            )
            assert f"口径={gold.convention}" in prod.details, (
                f"{name}: 口径不符, 金标准={gold.convention}"
            )



# ---------------------------------------------------------------------------
# unknown_category 分支覆盖（非 PG，mock 查询结果）
# ---------------------------------------------------------------------------

class TestUnknownCategoryBranch:
    """tb_balance.unknown_category 分支：数据含未知科目类别时 → not_executed"""

    def test_unknown_category_returns_not_executed(self):
        """account_category 含 EXPECTED_CATEGORIES 之外的值"""
        import asyncio
        from unittest.mock import AsyncMock, MagicMock

        from app.services.consistency_gate._impl import ConsistencyGate
        from app.services.consistency_gate._models import CheckItem

        # 模拟 db.execute 返回含未知类别的行
        mock_result = MagicMock()
        mock_result.all.return_value = [
            ("9999", "alien_type", D("100")),
            ("1001", "asset", D("100")),
        ]
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)
        # begin_nested 上下文管理器
        mock_nested = AsyncMock()
        mock_nested.__aenter__ = AsyncMock(return_value=None)
        mock_nested.__aexit__ = AsyncMock(return_value=False)
        mock_db.begin_nested = MagicMock(return_value=mock_nested)

        gate = ConsistencyGate(mock_db)

        # asyncio.run 每次新建循环：get_event_loop() 与先跑的用例同进程时报「no current event loop」（2026-10-30 复现）
        item = asyncio.run(
            gate.check_tb_balance("00000000-0000-0000-0000-000000000001", 2025)
        )

        assert isinstance(item, CheckItem)
        assert item.status == "not_executed"
        assert item.branch_id == "tb_balance.unknown_category"
        assert "alien_type" in item.reason
