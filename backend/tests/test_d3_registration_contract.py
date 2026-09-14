"""D3 预收账款 注册契约测试

验证 d3-prepaid-accounts componentType 在三处正确注册：
1. wp_code_overrides.json: D3/D3-1/D3-2 → 'd3-prepaid-accounts', D3-3~D3-7 → 'skip'
2. VALID_COMPONENT_TYPES: 包含 'd3-prepaid-accounts'

**Validates: Requirements 20.5, 20.6, 20.7**
"""

from __future__ import annotations

import json
from pathlib import Path


# ──────────────────────────────────────────────────────────────────────
# 加载配置
# ──────────────────────────────────────────────────────────────────────

_JSON_PATH = Path(__file__).resolve().parent.parent / "app" / "data" / "wp_code_overrides.json"


def _load_overrides() -> dict[str, str]:
    with open(_JSON_PATH, encoding="utf-8") as f:
        return json.load(f)


# ──────────────────────────────────────────────────────────────────────
# wp_code_overrides 契约
# ──────────────────────────────────────────────────────────────────────

# D3/D3-1/D3-2 映射为主组件
D3_MAIN_MAPPINGS: dict[str, str] = {
    "D3": "d3-prepaid-accounts",
    "D3-1": "d3-prepaid-accounts",
    "D3-2": "d3-prepaid-accounts",
}

# D3-3~D3-7 映射为 skip（子sheet在主组件内渲染）
D3_SKIP_MAPPINGS: dict[str, str] = {
    "D3-3": "skip",
    "D3-4": "skip",
    "D3-5": "skip",
    "D3-6": "skip",
    "D3-7": "skip",
}


def test_d3_main_wp_codes_mapped_to_d3_prepaid_accounts():
    """D3/D3-1/D3-2 映射为 'd3-prepaid-accounts'

    Validates: Requirements 20.6
    """
    overrides = _load_overrides()
    for wp_code, expected in D3_MAIN_MAPPINGS.items():
        assert wp_code in overrides, f"{wp_code!r} 不在 wp_code_overrides.json 中"
        assert overrides[wp_code] == expected, (
            f"{wp_code!r}: 期望 {expected!r}, 实际 {overrides[wp_code]!r}"
        )


def test_d3_sub_sheets_mapped_to_skip():
    """D3-3~D3-7 映射为 'skip'（子sheet在主组件Tab内渲染）

    Validates: Requirements 20.6
    """
    overrides = _load_overrides()
    for wp_code, expected in D3_SKIP_MAPPINGS.items():
        assert wp_code in overrides, f"{wp_code!r} 不在 wp_code_overrides.json 中"
        assert overrides[wp_code] == expected, (
            f"{wp_code!r}: 期望 {expected!r}, 实际 {overrides[wp_code]!r}"
        )


# ──────────────────────────────────────────────────────────────────────
# VALID_COMPONENT_TYPES 契约
# ──────────────────────────────────────────────────────────────────────


def test_d3_prepaid_accounts_in_valid_component_types():
    """'d3-prepaid-accounts' 在 VALID_COMPONENT_TYPES 白名单中

    Validates: Requirements 20.7
    """
    from app.services.wp_classification_service import VALID_COMPONENT_TYPES

    assert "d3-prepaid-accounts" in VALID_COMPONENT_TYPES, (
        "'d3-prepaid-accounts' 未在 VALID_COMPONENT_TYPES 中注册，"
        "validate_overrides 启动时将 raise ValueError 阻止 uvicorn 启动"
    )
