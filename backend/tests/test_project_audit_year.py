"""project_audit_year 通用年度解析规则测试。"""

from datetime import date
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.services.project_audit_year import (
    extract_audit_year_from_wizard_state,
    resolve_project_audit_year,
    resolve_project_audit_year_for_request,
    _year_from_name,
)


def _project(**kwargs):
    defaults = dict(
        audit_year=None,
        audit_period_end=None,
        audit_period_start=None,
        wizard_state=None,
        name=None,
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


class TestResolveProjectAuditYear:
    def test_audit_year_column_first(self):
        p = _project(audit_year=2025, audit_period_end=date(2024, 12, 31))
        assert resolve_project_audit_year(p) == 2025

    def test_audit_period_end_when_audit_year_null(self):
        p = _project(audit_year=None, audit_period_end=date(2025, 12, 31))
        assert resolve_project_audit_year(p) == 2025

    def test_audit_period_start_fallback(self):
        p = _project(audit_period_start=date(2024, 1, 1))
        assert resolve_project_audit_year(p) == 2024

    def test_wizard_state_fallback(self):
        p = _project(
            wizard_state={"steps": {"basic_info": {"data": {"audit_year": 2023}}}}
        )
        assert resolve_project_audit_year(p) == 2023

    def test_name_suffix_fallback(self):
        p = _project(name="重药控股安徽有限公司_2025")
        assert resolve_project_audit_year(p) == 2025

    def test_all_empty_returns_none(self):
        assert resolve_project_audit_year(_project()) is None


class TestExtractAuditYearFromWizardState:
    def test_nested_steps_path(self):
        ws = {"steps": {"basic_info": {"data": {"year": 2025}}}}
        assert extract_audit_year_from_wizard_state(ws) == 2025

    def test_flat_basic_info_path(self):
        ws = {"basic_info": {"data": {"audit_year": 2024}}}
        assert extract_audit_year_from_wizard_state(ws) == 2024


class TestYearFromName:
    def test_suffix(self):
        assert _year_from_name("客户公司_2025") == 2025

    def test_no_suffix(self):
        assert _year_from_name("客户公司") is None


class _FakeDb:
    def __init__(self, project):
        self.project = project

    async def get(self, _model, _project_id):
        return self.project


@pytest.mark.asyncio
async def test_resolve_project_audit_year_for_request_prefers_explicit_year():
    project = _project(audit_year=2024)
    db = _FakeDb(project)
    pid = uuid4()

    assert await resolve_project_audit_year_for_request(db, str(pid), 2025) == 2025
    # 缺省年度只从项目上下文取：字符串与 UUID 两种项目 id 写法同口径
    assert await resolve_project_audit_year_for_request(db, str(pid)) == 2024
    assert await resolve_project_audit_year_for_request(db, pid) == 2024


@pytest.mark.asyncio
async def test_resolve_project_audit_year_for_request_returns_none_when_missing():
    assert await resolve_project_audit_year_for_request(_FakeDb(_project()), uuid4()) is None
    assert await resolve_project_audit_year_for_request(_FakeDb(None), uuid4()) is None


@pytest.mark.asyncio
async def test_resolve_project_audit_year_for_request_invalid_project_id_is_missing():
    """项目 id 不是 UUID ⇒ 不可能对应项目，按「年度缺失」返回 None，且不查库。"""

    class _NoQueryDb:
        async def get(self, _model, _project_id):  # pragma: no cover - 被调用即失败
            raise AssertionError("非 UUID 的项目 id 不应查库")

    assert await resolve_project_audit_year_for_request(_NoQueryDb(), "project-id") is None


@pytest.mark.asyncio
async def test_resolve_project_audit_year_for_request_db_error_propagates():
    """查库失败不得伪装成「未设置审计年度」（PG 上事务已中止，吞掉会让调用方继续用坏事务）。"""

    class _BrokenDb:
        async def get(self, _model, _project_id):
            raise RuntimeError("connection lost")

    with pytest.raises(RuntimeError, match="connection lost"):
        await resolve_project_audit_year_for_request(_BrokenDb(), uuid4())
