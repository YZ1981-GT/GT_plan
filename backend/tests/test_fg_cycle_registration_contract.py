"""F/G 循环组件注册契约测试."""

from __future__ import annotations

import json
from pathlib import Path

from app.services.wp_classification_service import VALID_COMPONENT_TYPES

_JSON_PATH = Path(__file__).resolve().parent.parent / "app" / "data" / "wp_code_overrides.json"

FG_COMPONENTS = {
    "f1-prepayment": "F1",
    "f2-inventory-main": "F2",
    "f2-inventory-valuation-impairment": "F2-38",
    "f3-notes-payable": "F3",
    "f4-accounts-payable": "F4",
    "f5-cost-of-sales": "F5",
    "g1-trading-financial-assets": "G1",
    "g2-interest-receivable": "G2",
    "g3-dividend-receivable": "G3",
    "g4-bond-investment-main": "G4",
    "g4-bond-investment-sppi": "G4-5",
    "g4-bond-investment-ecl": "G4-9",
    "g5-long-term-receivable": "G5",
    "g6-other-bond-investment-main": "G6",
    "g6-other-bond-investment-sppi": "G6-5",
    "g6-other-bond-investment-ecl": "G6-11",
    "g7-long-term-equity-main": "G7",
    "g7-long-term-equity-method": "G7-11",
    "g7-long-term-equity-subsidiary": "G7-8",
    "g8-other-equity-instruments": "G8",
    "g9-other-noncurrent-financial": "G9",
    "g10-trading-financial-liabilities": "G10",
    "g11-investment-income": "G11",
    "g12-net-hedge-gains": "G12",
    "g13-fair-value-changes": "G13",
    "g14-credit-impairment-loss": "G14",
}

RENDER_STRATEGY_REQUIRED = {
    "f1-prepayment",
    "f2-inventory-main",
    "f3-notes-payable",
    "f4-accounts-payable",
    "f5-cost-of-sales",
    "g1-trading-financial-assets",
    "g2-interest-receivable",
    "g3-dividend-receivable",
    "g4-bond-investment-main",
    "g5-long-term-receivable",
    "g6-other-bond-investment-sppi",
    "g8-other-equity-instruments",
    "g9-other-noncurrent-financial",
    "g10-trading-financial-liabilities",
    "g11-investment-income",
    "g12-net-hedge-gains",
    "g13-fair-value-changes",
    "g14-credit-impairment-loss",
}


def _load_overrides() -> dict[str, str]:
    with open(_JSON_PATH, encoding="utf-8") as f:
        return json.load(f)


def test_fg_component_types_in_valid_set():
    for ct in FG_COMPONENTS:
        assert ct in VALID_COMPONENT_TYPES, f"{ct} 未在 VALID_COMPONENT_TYPES 注册"


def test_fg_sample_wp_codes_mapped():
    overrides = _load_overrides()
    for ct, sample_code in FG_COMPONENTS.items():
        assert overrides.get(sample_code) == ct, f"{sample_code} 应映射为 {ct}"


def test_fg_renderer_dispatch_registered():
    from app.routers.wp_render_strategies import RENDERER_DISPATCH

    for ct in RENDER_STRATEGY_REQUIRED:
        assert ct in RENDERER_DISPATCH, f"{ct} 未注册 RENDERER_DISPATCH"
