"""已抽排除的收集口径与查询条件（spec voucher-identity-writeback-and-audit-phase 任务 5，需求 2.4 / 2.6）

原 voucher-sampling-hardening P3 行级排除测试改写：``collect_exclusions`` 取代路由里的
``_get_voucher_sampling_exclusions``（按凭证号 / 行 id）。

- 新格式日志（filled_line_fps / filled_voucher_keys）：分录行单位按指纹解析到当前账套的行 id，
  整张凭证单位按凭证键；新格式日志不再贡献凭证号，也不贡献旧行 id。
- 旧格式日志（只有 filled_voucher_nos / filled_unit_ids）：按旧口径兼容并标 legacy。
- 年审（phase=final）关掉 exclude_extracted 也排除预审回填；项目级叠加登记表。
- ``build_ledger_query``（编译真实查询，不再在测试里抄一份排除逻辑）：行 id → id NOT IN（非法 UUID
  静默跳过）；凭证键 → 行值 NOT IN；旧凭证号 → voucher_no NOT IN。

Properties: Property 6, Property 7
"""

from __future__ import annotations

import uuid
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import sqlalchemy as sa

from app.models.audit_platform_models import TbLedger
from app.services.ledger_sampling_service import LedgerQueryFilters, LedgerSamplingService
from app.services.voucher_identity import MAX_KEYS_PER_STATEMENT, VoucherKey, line_fingerprint
from app.services.voucher_sampling_exclusion import SamplingExclusions, collect_exclusions

_PID = uuid.uuid4()
_WP = uuid.uuid4()
_VK_FY = VoucherKey.of(year=2025, company_code="001", voucher_date="2025-01-07", voucher_type="FY", voucher_no="0003")
_VK_ZZ = VoucherKey.of(year=2025, company_code="001", voucher_date="2025-01-07", voucher_type="ZZ", voucher_no="0003")
_FP_1 = line_fingerprint(_VK_FY, "1002", "C", "1680.00", 1)
_FP_2 = line_fingerprint(_VK_FY, "2211", "D", "1680.00", 1)
_FP_ZZ = line_fingerprint(_VK_ZZ, "1002", "D", "88.00", 1)


def _fake_db_returning(criteria_rows: list) -> AsyncMock:
    db = AsyncMock()
    result = MagicMock()
    result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=criteria_rows)))
    db.execute = AsyncMock(return_value=result)
    return db


async def _collect(
    rows: list,
    *,
    unit: str = "ledger_line",
    exclude_extracted: bool = True,
    phase: str | None = None,
    scope: str = "workpaper",
    resolved: dict | None = None,
    registry: tuple = ((), ()),
):
    resolver = AsyncMock(return_value=resolved or {})
    reg = AsyncMock(return_value=(list(registry[0]), list(registry[1])))
    db = _fake_db_returning(rows)
    with patch("app.services.voucher_sampling_exclusion.resolve_line_fps", resolver), patch(
        "app.services.sampled_voucher_queries.project_level_extracted_vouchers", reg
    ):
        out = await collect_exclusions(
            db, project_id=_PID, year=2025, workpaper_id=_WP, extraction_type="voucher_sampling",
            sampling_unit=unit, exclude_extracted=exclude_extracted, phase=phase, exclude_scope=scope,
        )
    return out, resolver, reg, db


class TestCollectExclusionsNewFormat:
    @pytest.mark.asyncio
    async def test_line_unit_resolves_fps_to_current_rows(self):
        id1, id2 = uuid.uuid4(), uuid.uuid4()
        rows = [{
            "filled_line_fps": [_FP_1, _FP_2], "filled_voucher_keys": [_VK_FY.to_str()],
            "filled_voucher_nos": ["0003"], "filled_unit_ids": [str(uuid.uuid4())],
        }]
        out, resolver, _, _ = await _collect(rows, resolved={_FP_1: id1, _FP_2: id2})
        assert out.line_ids == sorted([str(id1), str(id2)])
        # 新格式日志：不按凭证键整张排除，也不贡献凭证号 / 旧行 id（避免连带同号别日凭证）
        assert out.voucher_keys == [] and out.voucher_nos == [] and out.legacy_line_ids == []
        assert out.legacy is False and out.unresolved_line_fps == 0
        kwargs = resolver.await_args.kwargs
        assert kwargs["fps"] == [_FP_1, _FP_2] and kwargs["project_id"] == _PID and kwargs["year"] == 2025

    @pytest.mark.asyncio
    async def test_voucher_unit_uses_voucher_keys(self):
        rows = [{"filled_line_fps": [_FP_1], "filled_voucher_keys": [_VK_FY.to_str()], "filled_voucher_nos": ["0003"]}]
        out, resolver, _, _ = await _collect(rows, unit="voucher")
        assert out.voucher_keys == [_VK_FY.to_str()]
        assert out.line_ids == [] and out.voucher_nos == []
        resolver.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_fps_only_log_derives_voucher_keys(self):
        out, _, _, _ = await _collect([{"filled_line_fps": [_FP_1, _FP_2, _FP_ZZ]}], unit="voucher")
        assert out.voucher_keys == [_VK_FY.to_str(), _VK_ZZ.to_str()]

    @pytest.mark.asyncio
    async def test_unresolved_fps_are_counted(self):
        out, _, _, _ = await _collect([{"filled_line_fps": [_FP_1, _FP_2]}], resolved={_FP_1: uuid.uuid4()})
        assert len(out.line_ids) == 1 and out.unresolved_line_fps == 1
        assert out.to_stats()["unresolved_excluded_lines"] == 1


class TestCollectExclusionsLegacy:
    @pytest.mark.asyncio
    async def test_line_unit_uses_old_line_ids(self):
        out, resolver, _, _ = await _collect([{"filled_voucher_nos": ["V1"], "filled_unit_ids": ["id-1", "id-2"]}])
        assert out.legacy_line_ids == ["id-1", "id-2"]
        assert out.voucher_nos == []  # 有行 id → 凭证号不参与（避免行级 + 凭证级双重排除）
        assert out.legacy is True
        resolver.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_without_unit_ids_falls_back_to_voucher_no(self):
        out, _, _, _ = await _collect([{"filled_voucher_nos": ["V1", "V2"]}])
        assert set(out.voucher_nos) == {"V1", "V2"} and out.legacy_line_ids == [] and out.legacy is True

    @pytest.mark.asyncio
    async def test_voucher_unit_uses_voucher_no(self):
        out, _, _, _ = await _collect([{"filled_voucher_nos": ["V1"], "filled_unit_ids": ["id-1"]}], unit="voucher")
        assert out.voucher_nos == ["V1"] and out.legacy_line_ids == [] and out.legacy is True

    @pytest.mark.asyncio
    async def test_mixed_logs_each_take_their_own_path(self):
        lid = uuid.uuid4()
        rows = [{"filled_line_fps": [_FP_1], "filled_voucher_nos": ["0003"]}, {"filled_voucher_nos": ["V9"]}]
        out, _, _, _ = await _collect(rows, resolved={_FP_1: lid})
        assert out.line_ids == [str(lid)] and out.voucher_nos == ["V9"] and out.legacy is True

    @pytest.mark.asyncio
    async def test_non_dict_and_empty_criteria_skipped(self):
        out, _, _, _ = await _collect([None, "x", {"filled_voucher_nos": []}])
        assert out == SamplingExclusions()


class TestCollectExclusionsPhaseAndScope:
    @pytest.mark.asyncio
    async def test_final_excludes_preliminary_even_when_exclude_extracted_off(self):
        rows = [
            {"phase": "preliminary", "filled_line_fps": [_FP_1]},
            {"phase": "final", "filled_line_fps": [_FP_2]},
        ]
        _, resolver, _, _ = await _collect(rows, exclude_extracted=False, phase="final")
        assert resolver.await_args.kwargs["fps"] == [_FP_1]

    @pytest.mark.asyncio
    async def test_exclude_extracted_takes_every_phase(self):
        rows = [
            {"phase": "preliminary", "filled_line_fps": [_FP_1]},
            {"phase": "final", "filled_line_fps": [_FP_2]},
        ]
        _, resolver, _, _ = await _collect(rows, phase="final")
        assert resolver.await_args.kwargs["fps"] == [_FP_1, _FP_2]

    @pytest.mark.asyncio
    async def test_nothing_to_exclude_skips_db(self):
        out, _, reg, db = await _collect([{"filled_line_fps": [_FP_1]}], exclude_extracted=False, phase="preliminary")
        assert out == SamplingExclusions()
        db.execute.assert_not_awaited()
        reg.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_project_scope_merges_registry(self):
        out, _, reg, _ = await _collect(
            [{"filled_voucher_keys": [_VK_FY.to_str()]}], unit="voucher", scope="project",
            registry=([_VK_FY, _VK_ZZ], ["0099"]),
        )
        assert out.voucher_keys == [_VK_FY.to_str(), _VK_ZZ.to_str()]
        assert out.voucher_nos == ["0099"] and out.legacy is True  # 登记表旧行只有凭证号
        assert reg.await_args.args[1:] == (_PID, 2025)

    @pytest.mark.asyncio
    async def test_project_scope_needs_exclude_extracted(self):
        _, _, reg, _ = await _collect([], exclude_extracted=False, phase="final", scope="project")
        reg.assert_not_awaited()

    def test_to_stats_shape(self):
        ex = SamplingExclusions(voucher_keys=["a"], line_ids=["b", "c"], voucher_nos=["d"], legacy=True)
        assert ex.to_stats() == {
            "excluded_voucher_count": 1,
            "excluded_line_count": 2,
            "legacy_exclusion": True,
            "legacy_excluded_voucher_nos": 1,
            "unresolved_excluded_lines": 0,
        }


async def _compiled_sql(**exclude) -> str:
    filters = LedgerQueryFilters(
        date_start=date(2025, 1, 1), date_end=date(2025, 12, 31), account_codes=["1122"], **exclude
    )
    active = sa.and_(TbLedger.project_id == _PID, TbLedger.year == 2025, TbLedger.is_deleted == sa.false())
    with patch("app.services.ledger_sampling_service.get_active_filter", new=AsyncMock(return_value=active)):
        query = await LedgerSamplingService.build_ledger_query(AsyncMock(), _PID, 2025, filters)
    return str(query.compile(compile_kwargs={"literal_binds": True}, dialect=sa.dialects.postgresql.dialect())).lower()


class TestBuildQueryExclusions:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("field", ["exclude_line_ids", "exclude_unit_ids"])
    async def test_valid_line_id_produces_not_in(self, field):
        uid = str(uuid.uuid4())
        sql = await _compiled_sql(**{field: [uid, "not-a-uuid"]})
        assert "tb_ledger.id not in" in sql and uid in sql and "not-a-uuid" not in sql

    @pytest.mark.asyncio
    async def test_invalid_line_ids_only_add_nothing(self):
        assert " not in " not in await _compiled_sql(exclude_line_ids=["bad"], exclude_unit_ids=["worse"])

    @pytest.mark.asyncio
    async def test_voucher_keys_exclude_by_row_value(self):
        sql = await _compiled_sql(exclude_voucher_keys=[_VK_FY.to_str(), "garbage"])
        assert "(tb_ledger.company_code, tb_ledger.voucher_date, coalesce(tb_ledger.voucher_type, ''), tb_ledger.voucher_no) not in" in sql
        assert "'2025-01-07'" in sql and "'fy'" in sql and "'0003'" in sql
        assert "tb_ledger.voucher_no not in" not in sql  # 不退回按凭证号

    @pytest.mark.asyncio
    async def test_legacy_voucher_nos_exclude_by_number(self):
        sql = await _compiled_sql(exclude_voucher_nos=["V1", " V1 ", ""])
        assert "tb_ledger.voucher_no not in ('v1')" in sql

    def test_too_many_keys_is_a_clear_error(self):
        keys = [
            VoucherKey.of(year=2025, company_code="001", voucher_date="2025-03-01", voucher_type="", voucher_no=str(i))
            for i in range(MAX_KEYS_PER_STATEMENT + 1)
        ]
        from app.services.voucher_identity import voucher_keys_not_in

        voucher_keys_not_in(TbLedger.__table__, keys[:-1])  # 恰好上限：照常
        with pytest.raises(ValueError, match="超过单条查询上限"):
            voucher_keys_not_in(TbLedger.__table__, keys)
