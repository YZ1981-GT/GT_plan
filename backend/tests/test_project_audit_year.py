"""project_audit_year 通用年度解析规则测试。"""

from datetime import date
from types import SimpleNamespace

import pytest

from app.services.project_audit_year import (
    extract_audit_year_from_wizard_state,
    resolve_project_audit_year,
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
