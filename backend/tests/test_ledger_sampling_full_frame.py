"""全量抽样框脚手架单测（voucher-sampling-hardening Task 2.1）

无 DB：编译 `_build_locate_projection` 的 SQL 断言结构（阶段 A 最小投影 / voucher 聚合）。
执行期正确性由 Task 3 接线后的 PBT（P1/P2）覆盖。

Validates: Requirements 1.1, 1.2
"""

from __future__ import annotations

import sqlalchemy as sa

from app.models.audit_platform_models import TbLedger
from app.services.ledger_sampling_service import LedgerSamplingService


def _compiled(unit: str, min_greatest=None) -> str:
    base = sa.select(TbLedger).where(sa.true())
    proj = LedgerSamplingService._build_locate_projection(
        base.subquery(), unit, min_greatest
    )
    return str(
        proj.compile(
            compile_kwargs={"literal_binds": True},
            dialect=sa.dialects.postgresql.dialect(),
        )
    ).lower()


class TestBuildLocateProjection:
    def test_ledger_line_projection_minimal_columns(self):
        sql = _compiled("ledger_line")
        # 最小投影：id/voucher_no/voucher_date + greatest 代表金额
        assert "unit_id" in sql
        assert "greatest_amount" in sql
        assert "greatest" in sql
        # 分录行不 group by
        assert "group by" not in sql

    def test_voucher_projection_group_by_voucher_no(self):
        sql = _compiled("voucher")
        assert "group by" in sql
        assert "voucher_no" in sql
        # voucher 单位金额为行 GREATEST 之和
        assert "sum" in sql
        assert "greatest_amount" in sql

    def test_greatest_uses_abs_coalesce(self):
        sql = _compiled("ledger_line")
        assert "abs" in sql
        assert "coalesce" in sql


class TestSpecificItemThresholdFastPath:
    """P2 安全快路径：specific_item 的 min_greatest 在 DB 侧过滤（ledger WHERE / voucher HAVING）。"""

    def test_no_threshold_no_filter(self):
        # 默认不传阈值 → 不加过滤（其它方法全量框行为不变）
        sql = _compiled("ledger_line")
        assert "where" not in sql.split("from")[1] if "from" in sql else True
        # voucher 无 having
        assert "having" not in _compiled("voucher")

    def test_ledger_line_threshold_adds_where(self):
        from decimal import Decimal

        sql = _compiled("ledger_line", Decimal("4000"))
        assert "where" in sql
        assert "4000" in sql
        assert "greatest" in sql

    def test_voucher_threshold_adds_having(self):
        from decimal import Decimal

        sql = _compiled("voucher", Decimal("4000"))
        assert "having" in sql
        assert "4000" in sql
        # HAVING 作用于行 GREATEST 之和（sum）
        assert "sum" in sql
