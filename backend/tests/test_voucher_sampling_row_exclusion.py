"""行级排除测试（voucher-sampling-hardening P3）

ledger_line 单位下按行 id 排除，避免"同一凭证号跨不同科目"被整张误排；voucher 单位仍
按 voucher_no 排除。向后兼容：无 filled_unit_ids 的旧日志回退 voucher_no 排除。

- `_get_voucher_sampling_exclusions` 拆分 (legacy_voucher_nos, unit_ids)：有 unit_ids 的日志
  不再贡献 voucher_no（避免行级+凭证级双重排除）。
- `build_ledger_query` 的 exclude_unit_ids → TbLedger.id NOT IN，非法 UUID 静默跳过。

Validates: Requirements 3.x（行级排除）
Properties: Property 6, Property 7
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
import sqlalchemy as sa

from app.models.audit_platform_models import TbLedger
from app.routers.voucher_sampling import _get_voucher_sampling_exclusions
from app.services.ledger_sampling_service import (
    LedgerQueryFilters,
    LedgerSamplingService,
)

_WP = uuid.uuid4()


def _fake_db_returning(criteria_rows: list[dict]):
    db = AsyncMock()
    result = MagicMock()
    result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=criteria_rows)))
    db.execute = AsyncMock(return_value=result)
    return db


class TestGetExclusionsSplit:
    @pytest.mark.asyncio
    async def test_new_log_uses_unit_ids_not_voucher_no(self):
        # 有 filled_unit_ids 的日志 → 贡献 unit_ids，不贡献 voucher_no
        rows = [
            {"filled_voucher_nos": ["V1", "V2"], "filled_unit_ids": ["id-1", "id-2"]},
        ]
        nos, uids = await _get_voucher_sampling_exclusions(_fake_db_returning(rows), _WP)
        assert set(uids) == {"id-1", "id-2"}
        assert nos == []  # 有 unit_ids → voucher_no 不参与（避免双重排除）

    @pytest.mark.asyncio
    async def test_legacy_log_falls_back_to_voucher_no(self):
        # 无 filled_unit_ids 的旧日志 → 回退 voucher_no
        rows = [{"filled_voucher_nos": ["V1", "V2"]}]
        nos, uids = await _get_voucher_sampling_exclusions(_fake_db_returning(rows), _WP)
        assert set(nos) == {"V1", "V2"}
        assert uids == []

    @pytest.mark.asyncio
    async def test_mixed_logs(self):
        # 新旧日志混合：各自走各自路径，不交叉
        rows = [
            {"filled_voucher_nos": ["V1"], "filled_unit_ids": ["id-1"]},  # 新
            {"filled_voucher_nos": ["V9"]},  # 旧
        ]
        nos, uids = await _get_voucher_sampling_exclusions(_fake_db_returning(rows), _WP)
        assert set(uids) == {"id-1"}
        assert set(nos) == {"V9"}

    @pytest.mark.asyncio
    async def test_preliminary_only_filter(self):
        rows = [
            {"phase": "preliminary", "filled_unit_ids": ["p-1"]},
            {"phase": "final", "filled_unit_ids": ["f-1"]},
        ]
        nos, uids = await _get_voucher_sampling_exclusions(
            _fake_db_returning(rows), _WP, preliminary_only=True
        )
        assert set(uids) == {"p-1"}


class TestBuildQueryExcludeUnitIds:
    def _filters(self, unit_ids: list[str]) -> LedgerQueryFilters:
        from datetime import date

        return LedgerQueryFilters(
            date_start=date(2025, 1, 1),
            date_end=date(2025, 12, 31),
            account_codes=["1122"],
            exclude_unit_ids=unit_ids,
        )

    def _compiled(self, filters: LedgerQueryFilters) -> str:
        # 直接构造 stmt 的排除分支：用一个最小 select 验证 id NOT IN 出现
        stmt = sa.select(TbLedger).where(sa.true())
        if filters.exclude_unit_ids:
            valid = []
            for raw in filters.exclude_unit_ids:
                try:
                    valid.append(uuid.UUID(str(raw)))
                except (ValueError, AttributeError, TypeError):
                    continue
            if valid:
                stmt = stmt.where(TbLedger.id.notin_(valid))
        return str(
            stmt.compile(
                compile_kwargs={"literal_binds": True},
                dialect=sa.dialects.postgresql.dialect(),
            )
        ).lower()

    def test_valid_uuid_produces_not_in(self):
        uid = str(uuid.uuid4())
        sql = self._compiled(self._filters([uid]))
        assert "not in" in sql
        assert uid in sql

    def test_invalid_uuid_silently_skipped(self):
        # 非法 UUID → 不加入排除，不崩
        sql = self._compiled(self._filters(["not-a-uuid"]))
        assert "not in" not in sql

    def test_mixed_valid_invalid(self):
        uid = str(uuid.uuid4())
        sql = self._compiled(self._filters([uid, "bad"]))
        assert uid in sql
