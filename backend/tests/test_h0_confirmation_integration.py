"""H0 固定资产循环函证 — 集成测试（后端视角）.

覆盖：
1. wp_code_overrides 映射正确性（9 条 H0 → 对应 componentType）
2. confirmation-alternative-h05 注册契约（VALID_COMPONENT_TYPES + RENDERER_DISPATCH + 初始格式）
3. H0-5 导入导出三端点 + 四区块列定义完整性
4. account_package_registry H0 包 sheets 顺序
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.wp_classification_service import _WP_CODE_OVERRIDE, VALID_COMPONENT_TYPES

_DATA_DIR = Path(__file__).resolve().parent.parent / "app" / "data"
_BACKEND_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
_OVERRIDES_PATH = _DATA_DIR / "wp_code_overrides.json"
_PKG_REGISTRY_PATH = _BACKEND_DATA_DIR / "account_package_registry.json"

_H0_EXPECTED_MAP = {
    "H0": "confirmation-hub",
    "H0A": "a-program-console",
    "H0-1": "confirmation-summary",
    "H0-2": "confirmation-entity-verify",
    "H0-3": "confirmation-followup",
    "H0-4": "confirmation-diff-reconcile",
    "H0-5": "confirmation-alternative-h05",
    "H0-6": "confirmation-reliability",
    "H0-7": "confirmation-fraud-risk",
}


class TestH0OverridesMapping:
    @pytest.fixture(scope="class")
    def overrides(self) -> dict:
        return json.loads(_OVERRIDES_PATH.read_text(encoding="utf-8"))

    @pytest.mark.parametrize("wp_code,component_type", list(_H0_EXPECTED_MAP.items()))
    def test_override_entry(self, overrides, wp_code, component_type):
        assert overrides.get(wp_code) == component_type

    def test_runtime_override_consistent_with_file(self):
        for wp_code, component_type in _H0_EXPECTED_MAP.items():
            assert _WP_CODE_OVERRIDE.get(wp_code) == component_type

    def test_exactly_nine_h0_entries(self, overrides):
        import re

        h0_keys = {k for k in overrides if re.fullmatch(r"H0(A|-[0-9]+)?", k)}
        assert h0_keys == set(_H0_EXPECTED_MAP)


class TestH0RegistrationContract:
    def test_valid_component_types(self):
        assert "confirmation-alternative-h05" in VALID_COMPONENT_TYPES

    def test_renderer_dispatch_registered(self):
        from app.routers.wp_render_strategies import RENDERER_DISPATCH

        assert "confirmation-alternative-h05" in RENDERER_DISPATCH
        assert callable(RENDERER_DISPATCH["confirmation-alternative-h05"])

    def test_render_config_format_map(self):
        from app.routers.wp_render_config import _CONFIRMATION_FORMAT_MAP

        assert _CONFIRMATION_FORMAT_MAP.get("confirmation-alternative-h05") == "alternative-h05-v1"


class TestH0ImportExport:
    @pytest.fixture(scope="class")
    def ie_module(self):
        from app.routers.wp_render_strategies import _h0_confirmation_import_export as mod

        return mod

    def test_sheet_name_map(self, ie_module):
        assert ie_module._SHEET_NAME_MAP["H0-5"] == "替代程序H0-5"

    def test_four_blocks_defined(self, ie_module):
        assert set(ie_module._H05_BLOCKS) == {"block1", "block2", "block3", "block4"}

    def test_block1_has_entity_column(self, ie_module):
        cols = ie_module._H05_BLOCKS["block1"]["columns"]
        assert cols[0] == ("被函证单位", "_entity", False)

    def test_voucher_columns_in_each_block(self, ie_module):
        voucher_labels = {"日期", "凭证编号", "业务内容", "对方科目", "金额"}
        for cfg in ie_module._H05_BLOCKS.values():
            labels = {c[0] for c in cfg["columns"]}
            assert voucher_labels.issubset(labels)

    def test_block_sheet_titles_unique(self, ie_module):
        titles = [cfg["sheet_title"] for cfg in ie_module._H05_BLOCKS.values()]
        assert len(titles) == len(set(titles))


class TestH0AccountPackage:
    @pytest.fixture(scope="class")
    def h0_pkg(self) -> dict:
        data = json.loads(_PKG_REGISTRY_PATH.read_text(encoding="utf-8"))
        pkg = next(p for p in data["packages"] if p["account_package_id"] == "H0_fixed_asset_confirmation")
        return pkg

    def test_primary_wp_code(self, h0_pkg):
        assert h0_pkg["primary_wp_code"] == "H0"

    def test_eight_sheets(self, h0_pkg):
        assert len(h0_pkg["sheets"]) == 8

    def test_h05_sheet_present(self, h0_pkg):
        names = [s["sheet_name"] for s in h0_pkg["sheets"]]
        assert "替代程序H0-5" in names


class TestH0YamlSchema:
    def test_h05_component_type_in_yaml(self):
        yaml_path = _BACKEND_DATA_DIR / "ledger_adapters" / "wp_render_schema" / "generated" / "H0.yaml"
        content = yaml_path.read_text(encoding="utf-8")
        assert "confirmation-alternative-h05" in content
