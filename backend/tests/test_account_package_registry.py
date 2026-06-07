"""科目工作包注册表测试

覆盖：
- Task 1.6: 注册表 schema 和必填字段验证
- Task 1.7: 注册表不得直接引用 generated/*.yaml 作为生产 schema
- Task 1.8: mapping_status=pending_inventory_reconciliation 时不得把 report_row/note_section 当作已确认口径

Requirements: 1.1, 1.5, 5.3
"""

import json
import tempfile
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from backend.app.services.account_package_registry_service import (
    AccountPackageRegistryService,
    REQUIRED_PACKAGE_FIELDS,
    REQUIRED_SHEET_FIELDS,
    RegistryValidationError,
    VALID_MAPPING_STATUSES,
    VALID_SHEET_TYPES,
)


# ─── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def registry_service():
    """使用真实注册表文件的 service 实例"""
    return AccountPackageRegistryService()


@pytest.fixture
def minimal_valid_package():
    """最小有效工作包配置"""
    return {
        "account_package_id": "TEST_pkg",
        "cycle": "D",
        "account_code": "1121",
        "account_name": "测试科目",
        "mapping_status": "pending_inventory_reconciliation",
        "primary_wp_code": "D1",
        "report_row": None,
        "note_section": None,
        "sheets": [
            {"sheet_name": "测试表", "sheet_type": "audit_sheet", "source_wp_code": "D1"}
        ],
    }


def _write_registry(packages, tmp_path):
    """写入临时注册表 JSON"""
    registry = {
        "_description": "test registry",
        "_version": "test",
        "packages": packages,
    }
    path = tmp_path / "registry.json"
    path.write_text(json.dumps(registry, ensure_ascii=False), encoding="utf-8")
    return path


# ─── Task 1.6: Schema 和必填字段 ─────────────────────────────────────────────


class TestRegistrySchemaValidation:
    """**Validates: Requirements 1.1** 注册表 schema 和必填字段"""

    def test_real_registry_loads_successfully(self, registry_service):
        """真实注册表文件可以成功加载"""
        data = registry_service.load()
        assert "packages" in data
        assert len(data["packages"]) > 0

    def test_real_registry_passes_validation(self, registry_service):
        """真实注册表通过完整验证"""
        errors = registry_service.validate()
        assert errors == [], f"Validation errors: {errors}"

    def test_all_packages_have_required_fields(self, registry_service):
        """所有包都包含必填字段"""
        for pkg in registry_service.get_packages():
            for field in REQUIRED_PACKAGE_FIELDS:
                assert field in pkg, (
                    f"Package '{pkg.get('account_package_id')}' "
                    f"missing required field: {field}"
                )

    def test_all_sheets_have_required_fields(self, registry_service):
        """所有 sheet 都包含必填字段"""
        for pkg in registry_service.get_packages():
            for sheet in pkg.get("sheets", []):
                for field in REQUIRED_SHEET_FIELDS:
                    assert field in sheet, (
                        f"Package '{pkg.get('account_package_id')}' "
                        f"sheet '{sheet.get('sheet_name')}' "
                        f"missing required field: {field}"
                    )

    def test_all_sheet_types_are_valid(self, registry_service):
        """所有 sheet_type 都是有效枚举值"""
        for pkg in registry_service.get_packages():
            for sheet in pkg.get("sheets", []):
                assert sheet["sheet_type"] in VALID_SHEET_TYPES, (
                    f"Invalid sheet_type: {sheet['sheet_type']}"
                )

    def test_all_mapping_statuses_are_valid(self, registry_service):
        """所有 mapping_status 都是有效枚举值"""
        for pkg in registry_service.get_packages():
            assert pkg["mapping_status"] in VALID_MAPPING_STATUSES, (
                f"Invalid mapping_status: {pkg['mapping_status']}"
            )

    def test_missing_required_field_fails_validation(self, tmp_path):
        """缺少必填字段时验证失败"""
        incomplete_pkg = {
            "account_package_id": "INCOMPLETE",
            # 缺少 cycle, account_code, account_name 等
            "sheets": [],
        }
        path = _write_registry([incomplete_pkg], tmp_path)
        svc = AccountPackageRegistryService(registry_path=path)
        errors = svc.validate()
        assert len(errors) > 0
        assert any("missing required field" in e for e in errors)

    def test_invalid_sheet_type_fails_validation(self, tmp_path):
        """无效 sheet_type 验证失败"""
        pkg = {
            "account_package_id": "BAD_SHEET_TYPE",
            "cycle": "D",
            "account_code": "1121",
            "account_name": "测试",
            "mapping_status": "pending_inventory_reconciliation",
            "primary_wp_code": "D1",
            "report_row": None,
            "note_section": None,
            "sheets": [
                {"sheet_name": "坏表", "sheet_type": "invalid_type"}
            ],
        }
        path = _write_registry([pkg], tmp_path)
        svc = AccountPackageRegistryService(registry_path=path)
        errors = svc.validate()
        assert any("invalid sheet_type" in e for e in errors)

    def test_validate_strict_raises_on_error(self, tmp_path):
        """validate_strict 在验证失败时抛出异常"""
        pkg = {"account_package_id": "INCOMPLETE", "sheets": []}
        path = _write_registry([pkg], tmp_path)
        svc = AccountPackageRegistryService(registry_path=path)
        with pytest.raises(RegistryValidationError) as exc_info:
            svc.validate_strict()
        assert len(exc_info.value.errors) > 0


# ─── Task 1.7: 不得引用 generated schema ─────────────────────────────────────


class TestNoGeneratedSchemaRefs:
    """**Validates: Requirements 5.3** 注册表不得直接引用 generated/*.yaml 作为生产 schema"""

    def test_real_registry_has_no_generated_refs(self, registry_service):
        """真实注册表无 generated schema 引用"""
        violations = registry_service.check_no_generated_refs()
        assert violations == [], f"Generated refs found: {violations}"

    def test_generated_ref_in_schema_refs_detected(self, tmp_path):
        """schema_refs 中的 generated 引用被检测到"""
        pkg = {
            "account_package_id": "BAD_REF",
            "cycle": "D",
            "account_code": "1121",
            "account_name": "测试",
            "mapping_status": "pending_inventory_reconciliation",
            "primary_wp_code": "D1",
            "report_row": None,
            "note_section": None,
            "schema_refs": ["generated/D1.yaml"],
            "sheets": [
                {"sheet_name": "测试", "sheet_type": "audit_sheet"}
            ],
        }
        path = _write_registry([pkg], tmp_path)
        svc = AccountPackageRegistryService(registry_path=path)
        violations = svc.check_no_generated_refs()
        assert len(violations) == 1
        assert "generated" in violations[0]

    def test_generated_ref_in_sheet_schema_ref_detected(self, tmp_path):
        """sheet 级 schema_ref 中的 generated 引用被检测到"""
        pkg = {
            "account_package_id": "BAD_SHEET_REF",
            "cycle": "D",
            "account_code": "1122",
            "account_name": "测试",
            "mapping_status": "pending_inventory_reconciliation",
            "primary_wp_code": "D2",
            "report_row": None,
            "note_section": None,
            "schema_refs": [],
            "sheets": [
                {
                    "sheet_name": "坏引用",
                    "sheet_type": "analysis",
                    "schema_ref": "generated/D2-6.yaml",
                }
            ],
        }
        path = _write_registry([pkg], tmp_path)
        svc = AccountPackageRegistryService(registry_path=path)
        violations = svc.check_no_generated_refs()
        assert len(violations) == 1
        assert "坏引用" in violations[0]

    def test_production_schema_refs_are_valid_paths(self, registry_service):
        """生产 schema 引用文件确实存在于文件系统"""
        for pkg in registry_service.get_packages():
            for ref in pkg.get("schema_refs", []):
                schema_path = _PRODUCTION_SCHEMA_DIR / ref
                assert schema_path.is_file(), (
                    f"Production schema not found: {schema_path}"
                )

    @given(
        prefix=st.sampled_from(["generated/", "backend/data/wp_render_schema/generated/"]),
        filename=st.from_regex(r"[A-Z][0-9A-Za-z\-]{1,10}\.yaml", fullmatch=True),
    )
    @settings(max_examples=5)
    def test_property_any_generated_path_is_detected(self, prefix, filename):
        """**Validates: Requirements 5.3**
        Property: 任何以 generated/ 开头或包含 /generated/ 的路径都被识别为 generated 引用
        """
        ref = prefix + filename
        assert AccountPackageRegistryService._is_generated_ref(ref)


# ─── Task 1.8: pending 状态下 report_row/note_section 不作为已确认 ───────────


class TestPendingMappingStatus:
    """**Validates: Requirements 1.5**
    mapping_status=pending_inventory_reconciliation 时不得把 report_row/note_section 当作已确认口径
    """

    def test_null_report_row_forces_pending_status(self, registry_service):
        """report_row 为 null 时有效状态强制为 pending"""
        for pkg in registry_service.get_packages():
            if pkg.get("report_row") is None:
                effective = registry_service.get_effective_mapping_status(pkg)
                assert effective == "pending_inventory_reconciliation"

    def test_null_note_section_forces_pending_status(self, registry_service):
        """note_section 为 null 时有效状态强制为 pending"""
        for pkg in registry_service.get_packages():
            if pkg.get("note_section") is None:
                effective = registry_service.get_effective_mapping_status(pkg)
                assert effective == "pending_inventory_reconciliation"

    def test_pending_package_report_row_not_confirmed(self, registry_service):
        """pending 状态下 get_confirmed_report_row 返回 None"""
        for pkg in registry_service.get_packages():
            if registry_service.get_effective_mapping_status(pkg) == "pending_inventory_reconciliation":
                assert registry_service.get_confirmed_report_row(pkg) is None

    def test_pending_package_note_section_not_confirmed(self, registry_service):
        """pending 状态下 get_confirmed_note_section 返回 None"""
        for pkg in registry_service.get_packages():
            if registry_service.get_effective_mapping_status(pkg) == "pending_inventory_reconciliation":
                assert registry_service.get_confirmed_note_section(pkg) is None

    def test_pending_package_is_not_mapping_confirmed(self, registry_service):
        """pending 状态下 is_mapping_confirmed 返回 False"""
        for pkg in registry_service.get_packages():
            if pkg.get("report_row") is None or pkg.get("note_section") is None:
                assert registry_service.is_mapping_confirmed(pkg) is False

    def test_confirmed_package_returns_report_row(self, tmp_path):
        """confirmed 状态下正确返回 report_row"""
        pkg = {
            "account_package_id": "CONFIRMED_PKG",
            "cycle": "D",
            "account_code": "1122",
            "account_name": "已确认科目",
            "mapping_status": "confirmed_production",
            "primary_wp_code": "D2",
            "report_row": "BS-005",
            "note_section": "五、3",
            "sheets": [
                {"sheet_name": "测试", "sheet_type": "audit_sheet"}
            ],
        }
        path = _write_registry([pkg], tmp_path)
        svc = AccountPackageRegistryService(registry_path=path)
        loaded_pkg = svc.get_packages()[0]
        assert svc.get_confirmed_report_row(loaded_pkg) == "BS-005"
        assert svc.get_confirmed_note_section(loaded_pkg) == "五、3"
        assert svc.is_mapping_confirmed(loaded_pkg) is True

    @given(
        report_row=st.one_of(st.none(), st.text(min_size=1, max_size=10)),
        note_section=st.one_of(st.none(), st.text(min_size=1, max_size=10)),
    )
    @settings(max_examples=5)
    def test_property_null_fields_always_force_pending(self, report_row, note_section):
        """**Validates: Requirements 1.5**
        Property: 只要 report_row 或 note_section 任一为 None，
        有效 mapping_status 必然为 pending_inventory_reconciliation，
        不论注册表声明什么状态。
        """
        pkg = {
            "account_package_id": "PROP_TEST",
            "report_row": report_row,
            "note_section": note_section,
            "mapping_status": "confirmed_production",
        }
        svc = AccountPackageRegistryService.__new__(AccountPackageRegistryService)
        effective = svc.get_effective_mapping_status(pkg)

        if report_row is None or note_section is None:
            assert effective == "pending_inventory_reconciliation"
        else:
            # 当两者都非 None 时，使用注册表声明的状态
            assert effective == "confirmed_production"

    @given(
        report_row=st.none(),
        note_section=st.one_of(st.none(), st.text(min_size=1, max_size=10)),
    )
    @settings(max_examples=5)
    def test_property_pending_never_exposes_confirmed_values(self, report_row, note_section):
        """**Validates: Requirements 1.5**
        Property: mapping_status=pending 时，get_confirmed_report_row 和
        get_confirmed_note_section 永远返回 None，
        不管底层值是否非空。
        """
        pkg = {
            "account_package_id": "PROP_TEST_2",
            "report_row": report_row,
            "note_section": note_section,
            "mapping_status": "confirmed_production",
        }
        svc = AccountPackageRegistryService.__new__(AccountPackageRegistryService)
        # report_row=None 强制 pending
        assert svc.get_confirmed_report_row(pkg) is None
        assert svc.is_mapping_confirmed(pkg) is False


# ─── 辅助：引用真实 schema 目录 ──────────────────────────────────────────────

_PRODUCTION_SCHEMA_DIR = (
    Path(__file__).resolve().parent.parent
    / "data"
    / "ledger_adapters"
    / "wp_render_schema"
)
