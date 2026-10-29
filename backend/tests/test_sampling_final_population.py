"""年审抽样口径的纯函数部分（spec voucher-identity-writeback-and-audit-phase 任务 15，需求 7.1~7.4）。

数据库路径（缺口径 422、口径 a 窗口、口径 b 扣除、重导后仍扣除）在 test_sampling_phase_pg.py。
"""

from __future__ import annotations

import uuid
from datetime import date
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.services.sampling_final_population import (
    FinalPopulation,
    InterimWork,
    PhaseContext,
    _attach_matches,
    _remaining_window,
    batch_period_end,
    resolve_final_population,
)
from app.services.sampling_registry_service import build_population_description


def _ctx(*, phase="final", cutoff=None, end=date(2025, 12, 31), batches=0, attaches=0, batch_end=None, last=None):
    return PhaseContext(phase, cutoff, end, InterimWork(batches, batches, batches, attaches, batch_end), last)


class TestBatchPeriodEnd:
    def test_explicit_date_to_wins(self):
        assert batch_period_end({"filters": {"date_to": "2025-09-15", "period_range": [1, 2]}}, 2025) == date(2025, 9, 15)

    def test_last_selected_month_end(self):
        assert batch_period_end({"filters": {"period_range": [3, 1, 6]}}, 2025) == date(2025, 6, 30)
        assert batch_period_end({"filters": {"period_range": [2]}}, 2024) == date(2024, 2, 29)

    @pytest.mark.parametrize("criteria,year", [
        ({}, 2025), ({"filters": {"period_range": []}}, 2025), ({"filters": {"period_range": [13, "x"]}}, 2025),
        ({"filters": {"period_range": [6]}}, None), ({"filters": "bad"}, 2025),
    ])
    def test_unknown_period(self, criteria, year):
        assert batch_period_end(criteria, year) is None


class TestPhaseContext:
    def test_requires_mode_only_in_final_with_interim_work(self):
        assert _ctx(batches=1).requires_mode and _ctx(attaches=1).requires_mode
        assert not _ctx(phase="preliminary", batches=1).requires_mode and not _ctx().requires_mode

    def test_effective_cutoff_prefers_project_then_batches(self):
        assert _ctx(cutoff=date(2025, 6, 30), batch_end=date(2025, 9, 30)).effective_cutoff() == (date(2025, 6, 30), "project")
        assert _ctx(batch_end=date(2025, 9, 30)).effective_cutoff() == (date(2025, 9, 30), "interim_batches")
        assert _ctx().effective_cutoff() == (None, None)

    def test_to_dict_default_mode_is_last_choice_else_b(self):
        d = _ctx(batches=2, attaches=1, cutoff=date(2025, 6, 30)).to_dict()
        assert d["default_final_population_mode"] == "full_minus_interim" and d["last_final_population_mode"] is None
        assert (d["interim_batch_count"], d["interim_attach_count"], d["requires_final_population_mode"]) == (2, 1, True)
        assert _ctx(batches=1, last="remaining").to_dict()["default_final_population_mode"] == "remaining"


class TestRemainingWindow:
    def test_intersects_user_period_with_cutoff_to_period_end(self):
        ctx = _ctx(cutoff=date(2025, 6, 30), batches=1)
        assert _remaining_window(ctx, 2025, date(2025, 1, 1), date(2025, 12, 31))[:2] == (date(2025, 7, 1), date(2025, 12, 31))
        assert _remaining_window(ctx, 2025, date(2025, 8, 1), date(2025, 10, 31))[:2] == (date(2025, 8, 1), date(2025, 10, 31))

    def test_period_end_defaults_to_year_end(self):
        ctx = _ctx(cutoff=date(2025, 9, 30), end=None, batches=1)
        assert _remaining_window(ctx, 2025, date(2025, 1, 1), date(2026, 3, 31))[:2] == (date(2025, 10, 1), date(2025, 12, 31))

    def test_empty_intersection_400(self):
        with pytest.raises(HTTPException) as exc:
            _remaining_window(_ctx(cutoff=date(2025, 6, 30), batches=1), 2025, date(2025, 1, 1), date(2025, 3, 31))
        assert exc.value.status_code == 400 and exc.value.detail["error_code"] == "REMAINING_PERIOD_EMPTY"

    def test_no_cutoff_400(self):
        with pytest.raises(HTTPException) as exc:
            _remaining_window(_ctx(batches=1), 2025, date(2025, 1, 1), date(2025, 12, 31))
        assert exc.value.status_code == 400 and exc.value.detail["error_code"] == "INTERIM_CUTOFF_REQUIRED"


class TestAttachMatches:
    LINE = SimpleNamespace(voucher_date=date(2025, 1, 3), voucher_no="0004", voucher_type="ZZ", company_code="C1")

    def _att(self, **kw):
        base = dict(voucher_date=date(2025, 1, 3), voucher_no="0004", voucher_type="ZZ", company_code="C1")
        return SimpleNamespace(**{**base, **kw})

    def test_whole_key(self):
        assert _attach_matches(self._att(), self.LINE)
        assert not _attach_matches(self._att(voucher_type="ZJGJ"), self.LINE)
        assert not _attach_matches(self._att(company_code="C2"), self.LINE)
        assert not _attach_matches(self._att(voucher_date=date(2025, 1, 4)), self.LINE)

    def test_old_registrations_without_type_or_company_match_any(self):
        assert _attach_matches(self._att(voucher_type=None, company_code=None), self.LINE)

    def test_blank_type_matches_only_blank(self):
        assert not _attach_matches(self._att(voucher_type=""), self.LINE)
        assert _attach_matches(self._att(voucher_type=""), SimpleNamespace(**{**vars(self.LINE), "voucher_type": None}))


async def test_mode_not_applicable_outside_final_phase():
    # 预审：不查库、不要求口径（db=None 一旦被用到就会报错）
    assert await resolve_final_population(
        None, project_id=None, workpaper_id=None, year=2025, phase="preliminary", mode=None,
        date_start=date(2025, 1, 1), date_end=date(2025, 12, 31), account_codes=[]) is None


def test_trace_fields():
    fp = FinalPopulation("full_minus_interim", date(2025, 6, 30), "project", date(2025, 1, 1), date(2025, 12, 31),
                         InterimWork(2, 30, 28, 3, date(2025, 6, 30)), ("a", "b"), 1)
    assert fp.to_trace() == {
        "mode": "full_minus_interim", "interim_cutoff_date": "2025-06-30", "interim_cutoff_source": "project",
        "date_start": "2025-01-01", "date_end": "2025-12-31", "interim_batch_count": 2, "interim_sample_count": 30,
        "interim_batch_line_fps": 28, "interim_attach_count": 3, "excluded_attach_lines": 2, "unresolved_attach_count": 1,
    }


class TestPopulationDescription:
    BASE = {"filters": {"account_codes": ["2241"], "period_range": list(range(1, 13))}}

    def test_old_records_unchanged(self):
        assert build_population_description(self.BASE) == "序时账；科目 2241；全年度"

    def test_mode_a(self):
        crit = {**self.BASE, "final_population_mode": "remaining", "final_population": {
            "mode": "remaining", "interim_cutoff_date": "2025-06-30", "interim_cutoff_source": "interim_batches",
            "date_start": "2025-07-01", "date_end": "2025-12-31"}}
        assert build_population_description(crit) == (
            "序时账；科目 2241；全年度；年审口径 a：只抽预审截止日 2025-06-30 次日至期末（实际 2025-07-01 至 2025-12-31）"
            "；项目未设预审截止日，取预审批次期间上限")

    def test_mode_b(self):
        crit = {**self.BASE, "final_population_mode": "full_minus_interim", "final_population": {
            "mode": "full_minus_interim", "interim_batch_line_fps": 12, "excluded_attach_lines": 3}}
        assert build_population_description(crit).endswith("年审口径 b：全年扣除本底稿预审已检样本（预审批次分录 12 条、预审挂凭分录 3 条）")


class TestVoucherExtractWiring:
    """抽凭路由把口径接进抽样框：a 收窄日期窗口，b 把挂凭分录并进行级排除，口径的 422 原样返回。"""

    async def _post(self, final_population, *, mode="full_minus_interim", raises=None):
        from unittest.mock import AsyncMock, MagicMock, patch

        from httpx import ASGITransport, AsyncClient

        from app.services.sampling_population_reconcile import PopulationReconcileFacts
        from app.services.voucher_sampling_exclusion import SamplingExclusions
        from tests.test_voucher_sampling_integration import (
            _make_app, _make_extract_request, _make_ledger_rows, _make_stats,
        )

        app, _ = _make_app()
        population = _make_ledger_rows(5)
        resolver = AsyncMock(return_value=final_population, side_effect=raises)
        body = {**_make_extract_request(phase="final"), "final_population_mode": mode}
        with patch("app.routers.voucher_sampling._authorize_and_validate_extract", new=AsyncMock(return_value=None)), \
                patch("app.routers.voucher_sampling.resolve_population_reconcile",
                      new=AsyncMock(return_value=PopulationReconcileFacts(available=False))), \
                patch("app.routers.voucher_sampling.resolve_final_population", new=resolver), \
                patch("app.routers.voucher_sampling.collect_exclusions",
                      new=AsyncMock(return_value=SamplingExclusions(line_ids=["batch-line"]))), \
                patch("app.routers.voucher_sampling.LedgerSamplingService") as svc:
            svc.build_ledger_query = AsyncMock(return_value=MagicMock())
            svc.execute_with_stats = AsyncMock(return_value=(population, _make_stats(population)))
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.post(f"/api/projects/{uuid.uuid4()}/sampling/voucher-extract", json=body)
        filters = svc.build_ledger_query.call_args[0][3] if svc.build_ledger_query.call_args else None
        return resp, resolver, filters

    async def test_mode_b_merges_attach_lines_into_line_exclusions(self):
        fp = FinalPopulation("full_minus_interim", date(2025, 6, 30), "project", date(2025, 1, 1), date(2025, 12, 31),
                             InterimWork(1, 1, 1, 2, None), ("attach-1", "attach-2"), 0)
        resp, resolver, filters = await self._post(fp)
        assert resp.status_code == 200, resp.text
        assert resolver.await_args.kwargs["phase"] == "final" and resolver.await_args.kwargs["mode"] == "full_minus_interim"
        assert sorted(filters.exclude_line_ids) == ["attach-1", "attach-2", "batch-line"]
        assert resp.json()["stats"]["final_population"]["excluded_attach_lines"] == 2

    async def test_mode_a_narrows_date_window(self):
        fp = FinalPopulation("remaining", date(2025, 6, 30), "project", date(2025, 7, 1), date(2025, 12, 31),
                             InterimWork(1, 1, 1, 0, None))
        resp, _, filters = await self._post(fp, mode="remaining")
        assert resp.status_code == 200, resp.text
        assert (filters.date_start, filters.date_end) == (date(2025, 7, 1), date(2025, 12, 31))
        assert filters.exclude_line_ids == ["batch-line"]

    async def test_not_applicable_leaves_stats_unchanged(self):
        resp, _, filters = await self._post(None)
        assert resp.status_code == 200 and "final_population" not in resp.json()["stats"]

    async def test_mode_required_422_is_not_swallowed(self):
        err = HTTPException(status_code=422, detail={"error_code": "FINAL_POPULATION_MODE_REQUIRED", "message": "x"})
        resp, _, filters = await self._post(None, raises=err)
        assert resp.status_code == 422 and resp.json()["detail"]["error_code"] == "FINAL_POPULATION_MODE_REQUIRED"
        assert filters is None
