"""测试：附注取数绑定注册表服务

Validates: Requirements 5.1, 5.2, 5.3, 5.4, 5.5
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from backend.app.services.note_binding_registry_service import (
    VALID_SOURCES,
    NoteBindingRegistryService,
    _REQUIRED_FIELDS,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_REGISTRY = {
    "version": "1.0.0",
    "valid_sources": list(VALID_SOURCES),
    "bindings": [
        {
            "binding_id": "ar_aging_within_1y_closing",
            "section_id": "accounts_receivable",
            "table_id": "账_龄",
            "row_id": "1年以内_含1年",
            "col_id": "期末数",
            "source": "workpaper",
            "wp_code": "E4-1",
            "sheet": "附注披露表",
            "field": "within_1_year_closing",
            "aggregation": "sum",
            "active": True,
        },
        {
            "binding_id": "ar_aging_within_1y_opening",
            "section_id": "accounts_receivable",
            "table_id": "账_龄",
            "row_id": "1年以内_含1年",
            "col_id": "期初数",
            "source": "prior_note",
            "wp_code": None,
            "sheet": None,
            "field": "within_1_year_opening",
            "aggregation": "direct",
            "active": True,
        },
        {
            "binding_id": "fa_original_value_closing",
            "section_id": "fixed_assets",
            "table_id": "固定资产原值",
            "row_id": "房屋及建筑物",
            "col_id": "期末数",
            "source": "workpaper",
            "wp_code": "E9-1",
            "sheet": "附注披露表",
            "field": "buildings_original_closing",
            "aggregation": "sum",
            "active": True,
        },
        {
            "binding_id": "cash_bank_closing",
            "section_id": "cash_and_bank",
            "table_id": "货币资金明细",
            "row_id": "银行存款",
            "col_id": "期末数",
            "source": "trial_balance",
            "wp_code": None,
            "sheet": None,
            "field": "account_1002_closing",
            "aggregation": "sum",
            "active": True,
        },
        {
            "binding_id": "inactive_binding",
            "section_id": "accounts_receivable",
            "table_id": "账_龄",
            "row_id": "test_row",
            "col_id": "期末数",
            "source": "manual",
            "wp_code": None,
            "sheet": None,
            "field": None,
            "aggregation": None,
            "active": False,
        },
    ],
}


@pytest.fixture
def registry_path(tmp_path: Path) -> str:
    """Create a temp registry JSON for testing."""
    path = tmp_path / "test_registry.json"
    path.write_text(json.dumps(SAMPLE_REGISTRY, ensure_ascii=False), encoding="utf-8")
    return str(path)


@pytest.fixture
def service(registry_path: str) -> NoteBindingRegistryService:
    """Create service instance with test data."""
    return NoteBindingRegistryService(registry_path=registry_path)


# ---------------------------------------------------------------------------
# Unit Tests: resolve_binding
# ---------------------------------------------------------------------------


class TestResolveBinding:
    """测试 resolve_binding 方法。"""

    def test_resolve_existing_binding(self, service: NoteBindingRegistryService) -> None:
        result = service.resolve_binding("ar_aging_within_1y_closing")
        assert result is not None
        assert result["section_id"] == "accounts_receivable"
        assert result["table_id"] == "账_龄"
        assert result["source"] == "workpaper"
        assert result["wp_code"] == "E4-1"

    def test_resolve_nonexistent_binding(self, service: NoteBindingRegistryService) -> None:
        result = service.resolve_binding("nonexistent_id")
        assert result is None

    def test_resolve_empty_string(self, service: NoteBindingRegistryService) -> None:
        result = service.resolve_binding("")
        assert result is None


# ---------------------------------------------------------------------------
# Unit Tests: validate_binding
# ---------------------------------------------------------------------------


class TestValidateBinding:
    """测试 validate_binding 方法。"""

    def test_valid_binding(self, service: NoteBindingRegistryService) -> None:
        errors = service.validate_binding("ar_aging_within_1y_closing")
        assert errors == []

    def test_nonexistent_binding(self, service: NoteBindingRegistryService) -> None:
        errors = service.validate_binding("no_such_id")
        assert len(errors) == 1
        assert "不存在" in errors[0]

    def test_invalid_source(self, tmp_path: Path) -> None:
        """binding 的 source 不在合法枚举中应报错。"""
        bad_registry = {
            "valid_sources": list(VALID_SOURCES),
            "bindings": [
                {
                    "binding_id": "bad_source",
                    "section_id": "test",
                    "table_id": "t1",
                    "row_id": "r1",
                    "col_id": "c1",
                    "source": "invalid_source_type",
                    "wp_code": None,
                    "active": True,
                }
            ],
        }
        path = tmp_path / "bad.json"
        path.write_text(json.dumps(bad_registry), encoding="utf-8")
        svc = NoteBindingRegistryService(registry_path=str(path))
        errors = svc.validate_binding("bad_source")
        assert any("不在合法枚举中" in e for e in errors)

    def test_workpaper_without_wp_code(self, tmp_path: Path) -> None:
        """source=workpaper 但 wp_code 为空应报错。"""
        bad_registry = {
            "valid_sources": list(VALID_SOURCES),
            "bindings": [
                {
                    "binding_id": "no_wp_code",
                    "section_id": "test",
                    "table_id": "t1",
                    "row_id": "r1",
                    "col_id": "c1",
                    "source": "workpaper",
                    "wp_code": None,
                    "active": True,
                }
            ],
        }
        path = tmp_path / "bad2.json"
        path.write_text(json.dumps(bad_registry), encoding="utf-8")
        svc = NoteBindingRegistryService(registry_path=str(path))
        errors = svc.validate_binding("no_wp_code")
        assert any("wp_code" in e for e in errors)


# ---------------------------------------------------------------------------
# Unit Tests: find_bindings_by_section
# ---------------------------------------------------------------------------


class TestFindBindingsBySection:
    """测试 find_bindings_by_section 方法。"""

    def test_find_accounts_receivable(self, service: NoteBindingRegistryService) -> None:
        results = service.find_bindings_by_section("accounts_receivable")
        assert len(results) == 3  # 2 active + 1 inactive
        assert all(r["section_id"] == "accounts_receivable" for r in results)

    def test_find_fixed_assets(self, service: NoteBindingRegistryService) -> None:
        results = service.find_bindings_by_section("fixed_assets")
        assert len(results) == 1
        assert results[0]["binding_id"] == "fa_original_value_closing"

    def test_find_nonexistent_section(self, service: NoteBindingRegistryService) -> None:
        results = service.find_bindings_by_section("nonexistent_section")
        assert results == []


# ---------------------------------------------------------------------------
# Unit Tests: find_bindings_by_source
# ---------------------------------------------------------------------------


class TestFindBindingsBySource:
    """测试 find_bindings_by_source 方法。"""

    def test_find_all_workpaper_bindings(self, service: NoteBindingRegistryService) -> None:
        results = service.find_bindings_by_source("workpaper")
        assert len(results) == 2  # ar + fa
        assert all(r["source"] == "workpaper" for r in results)

    def test_find_workpaper_by_wp_code(self, service: NoteBindingRegistryService) -> None:
        results = service.find_bindings_by_source("workpaper", "E4-1")
        assert len(results) == 1
        assert results[0]["binding_id"] == "ar_aging_within_1y_closing"

    def test_find_trial_balance(self, service: NoteBindingRegistryService) -> None:
        results = service.find_bindings_by_source("trial_balance")
        assert len(results) == 1
        assert results[0]["binding_id"] == "cash_bank_closing"

    def test_find_nonexistent_source(self, service: NoteBindingRegistryService) -> None:
        results = service.find_bindings_by_source("ledger")
        assert results == []


# ---------------------------------------------------------------------------
# Unit Tests: impact_by_source
# ---------------------------------------------------------------------------


class TestImpactBySource:
    """测试 impact_by_source 方法。"""

    def test_impact_workpaper_e4(self, service: NoteBindingRegistryService) -> None:
        results = service.impact_by_source("workpaper", "E4-1")
        assert len(results) == 1
        assert results[0]["section_id"] == "accounts_receivable"
        assert results[0]["table_id"] == "账_龄"

    def test_impact_excludes_inactive(self, service: NoteBindingRegistryService) -> None:
        """inactive binding 不出现在 impact 结果中。"""
        results = service.impact_by_source("manual", "")
        # inactive_binding source=manual 但 active=False，不应被返回
        assert all(r.get("binding_id") != "inactive_binding" for r in results)

    def test_impact_by_field(self, service: NoteBindingRegistryService) -> None:
        results = service.impact_by_source("trial_balance", "account_1002_closing")
        assert len(results) == 1
        assert results[0]["binding_id"] == "cash_bank_closing"

    def test_impact_no_match(self, service: NoteBindingRegistryService) -> None:
        results = service.impact_by_source("workpaper", "Z99-1")
        assert results == []


# ---------------------------------------------------------------------------
# Unit Tests: edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """测试边缘情况。"""

    def test_missing_file(self, tmp_path: Path) -> None:
        """文件不存在时服务正常初始化，bindings 为空。"""
        svc = NoteBindingRegistryService(
            registry_path=str(tmp_path / "does_not_exist.json")
        )
        assert svc.all_bindings == []
        assert svc.resolve_binding("any") is None

    def test_invalid_json(self, tmp_path: Path) -> None:
        """JSON 格式错误时服务正常初始化，bindings 为空。"""
        bad_path = tmp_path / "bad.json"
        bad_path.write_text("not valid json {{{", encoding="utf-8")
        svc = NoteBindingRegistryService(registry_path=str(bad_path))
        assert svc.all_bindings == []

    def test_valid_sources_property(self, service: NoteBindingRegistryService) -> None:
        """valid_sources 属性返回正确的集合。"""
        sources = service.valid_sources
        assert "workpaper" in sources
        assert "trial_balance" in sources
        assert "invalid" not in sources

    def test_default_registry_loads(self) -> None:
        """使用默认路径加载（实际 registry 文件存在）。"""
        svc = NoteBindingRegistryService()
        # 默认 registry 应该有绑定条目
        assert len(svc.all_bindings) > 0


# ---------------------------------------------------------------------------
# Property-Based Test: 所有 binding 必须有必需字段
# ---------------------------------------------------------------------------


class TestBindingRegistryPBT:
    """**Validates: Requirements 5.1**

    PBT: 所有绑定条目必须包含 required fields。
    """

    @settings(max_examples=5)
    @given(
        binding_id=st.text(
            alphabet=st.characters(whitelist_categories=("L", "N", "P")),
            min_size=3,
            max_size=50,
        ),
        section_id=st.sampled_from(["accounts_receivable", "fixed_assets", "cash_and_bank"]),
        source=st.sampled_from(sorted(VALID_SOURCES)),
    )
    def test_constructed_binding_validates(
        self,
        binding_id: str,
        section_id: str,
        source: str,
    ) -> None:
        """任意构造的 binding（含全部必需字段）validate 返回空错误列表。

        **Validates: Requirements 5.1**
        """
        import tempfile

        wp_code = "E4-1" if source == "workpaper" else None
        registry = {
            "valid_sources": list(VALID_SOURCES),
            "bindings": [
                {
                    "binding_id": binding_id,
                    "section_id": section_id,
                    "table_id": "test_table",
                    "row_id": "test_row",
                    "col_id": "test_col",
                    "source": source,
                    "wp_code": wp_code,
                    "active": True,
                }
            ],
        }
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            json.dump(registry, f, ensure_ascii=False)
            tmp_file = f.name

        try:
            svc = NoteBindingRegistryService(registry_path=tmp_file)
            errors = svc.validate_binding(binding_id)
            assert errors == [], f"Expected no errors for valid binding, got: {errors}"
        finally:
            Path(tmp_file).unlink(missing_ok=True)
