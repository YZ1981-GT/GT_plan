"""R5 EQCR 测试套件入口 — 确保所有 EQCR 测试文件可被 collect"""
import importlib
import pytest

EQCR_TEST_MODULES = [
    "tests.test_eqcr_service",
    "tests.test_eqcr_gate_approve",
    "tests.test_eqcr_state_machine_properties",
    "tests.test_eqcr_full_flow",
    "tests.test_eqcr_workbench",
    "tests.test_eqcr_notes",
    "tests.test_eqcr_shadow_compute",
    "tests.test_eqcr_independence_sod",
    "tests.test_eqcr_component_auditor_review",
    "tests.test_eqcr_memo_docx",
    "tests.test_client_lookup",
    "tests.test_eqcr_domain_data",
    "tests.test_eqcr_state_machine_lock",
    "tests.test_eqcr_sod",
]


@pytest.mark.parametrize("module_name", EQCR_TEST_MODULES)
def test_module_importable(module_name: str):
    """验证所有 EQCR 测试模块可正常导入（无 collection error）"""
    importlib.import_module(module_name)
