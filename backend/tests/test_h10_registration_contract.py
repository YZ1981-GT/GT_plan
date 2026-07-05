"""H10 资产处置损益 — 注册契约测试."""

from __future__ import annotations

import json
from pathlib import Path

from app.services.wp_classification_service import VALID_COMPONENT_TYPES

_COMPONENT = "h10-asset-disposal-income"
_OVERRIDES_PATH = Path(__file__).resolve().parent.parent / "app" / "data" / "wp_code_overrides.json"

_H10_WP_CODES = ("H10", "H10A", "H10-1", "H10-2", "H10-3", "H10-4")


def _load_overrides() -> dict[str, str]:
    with open(_OVERRIDES_PATH, encoding="utf-8") as f:
        return json.load(f)


def test_h10_in_valid_component_types():
    assert _COMPONENT in VALID_COMPONENT_TYPES


def test_h10_wp_code_overrides():
    overrides = _load_overrides()
    for code in _H10_WP_CODES:
        assert overrides.get(code) == _COMPONENT, f"{code} 应映射为 {_COMPONENT}"


def test_h10_account_package_registry():
    import json
    from pathlib import Path

    registry_path = Path(__file__).resolve().parent.parent / "data" / "account_package_registry.json"
    packages = json.loads(registry_path.read_text(encoding="utf-8"))["packages"]
    pkg = next((p for p in packages if p.get("primary_wp_code") == "H10"), None)
    assert pkg is not None, "H10 应注册 account_package"
    assert pkg["account_code"] == "6115"
    sheet_names = [s["sheet_name"] for s in pkg["sheets"]]
    assert "审定表H10-1" in sheet_names
    assert "附注披露信息（上市公司）" in sheet_names


def test_h10_renderer_dispatch():
    from app.routers.wp_render_strategies import RENDERER_DISPATCH

    assert _COMPONENT in RENDERER_DISPATCH
    assert callable(RENDERER_DISPATCH[_COMPONENT])
