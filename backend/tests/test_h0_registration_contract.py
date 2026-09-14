"""H0 固定资产循环函证 — 注册契约测试 (Task 1.2).

验证：
1. wp_code_overrides.json 含完整 9 条 H0 映射
2. confirmation-alternative-h05 ∈ VALID_COMPONENT_TYPES
3. render_h0_alternative ∈ RENDERER_DISPATCH
4. account_package_registry 含 H0_fixed_asset_confirmation
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.wp_classification_service import VALID_COMPONENT_TYPES

_JSON_PATH = Path(__file__).resolve().parent.parent / "app" / "data" / "wp_code_overrides.json"
_PKG_REGISTRY_PATH = Path(__file__).resolve().parent.parent / "data" / "account_package_registry.json"

H0_WP_CODES = {
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


def _load_overrides() -> dict[str, str]:
    with open(_JSON_PATH, encoding="utf-8") as f:
        return json.load(f)


def _load_packages() -> list[dict]:
    with open(_PKG_REGISTRY_PATH, encoding="utf-8") as f:
        return json.load(f)["packages"]


class TestH0Overrides:
    """9 条 wp_code → componentType 映射。"""

    @pytest.fixture(scope="class")
    def overrides(self) -> dict[str, str]:
        return _load_overrides()

    @pytest.mark.parametrize("wp_code,component_type", list(H0_WP_CODES.items()))
    def test_override_entry(self, overrides, wp_code, component_type):
        assert overrides.get(wp_code) == component_type, f"{wp_code} 应映射为 {component_type}"

    def test_exactly_nine_entries(self, overrides):
        import re

        h0_keys = {k for k in overrides if re.fullmatch(r"H0(A|-[0-9]+)?", k)}
        assert len(h0_keys) == 9


class TestH0ComponentRegistration:
    """confirmation-alternative-h05 注册契约。"""

    def test_h05_in_valid_component_types(self):
        assert "confirmation-alternative-h05" in VALID_COMPONENT_TYPES

    def test_h05_renderer_dispatch_registered(self):
        from app.routers.wp_render_strategies import RENDERER_DISPATCH

        assert "confirmation-alternative-h05" in RENDERER_DISPATCH
        assert callable(RENDERER_DISPATCH["confirmation-alternative-h05"])


class TestH0AccountPackage:
    """account_package_registry 含 H0 包。"""

    def test_h0_fixed_asset_confirmation_exists(self):
        packages = _load_packages()
        h0_pkg = next(
            (p for p in packages if p["account_package_id"] == "H0_fixed_asset_confirmation"),
            None,
        )
        assert h0_pkg is not None, "H0_fixed_asset_confirmation 包应存在"
