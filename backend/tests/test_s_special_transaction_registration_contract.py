"""S 类交易/专家/检查型底稿（S4/S5/S6/S12/S13/S14 + 检查表型）— 注册契约测试.

Spec: .kiro/specs/s-special-transaction-workpapers/ Task 2.3
Validates: Requirements 1.1, 1.3
Feature: s-special-transaction-workpapers

mirror 自 test_s_estimate_registration_contract.py 模式：
断言 6 个交易型专属 componentType 在 VALID_COMPONENT_TYPES / RENDERER_DISPATCH /
_WHOLE_WP_MULTISHEET_DEDICATED 中完整注册；wp_code_overrides 映射正确（交易型→专属，
检查表型→a-program-console）；子 sheet 编码映射正确；
完整线上 overrides 经 validate_overrides 校验通过。
"""

import json
from pathlib import Path

# ─── 常量定义 ────────────────────────────────────────────────────────────────

S4_COMPONENT_TYPE = "s4-nonmonetary-exchange"
S5_COMPONENT_TYPE = "s5-debt-restructuring"
S6_COMPONENT_TYPE = "s6-fund-occupation"
S12_COMPONENT_TYPE = "s12-cpa-expert"
S13_COMPONENT_TYPE = "s13-mgmt-expert"
S14_COMPONENT_TYPE = "s14-accounting-estimate"

ALL_DEDICATED_TYPES = [
    S4_COMPONENT_TYPE,
    S5_COMPONENT_TYPE,
    S6_COMPONENT_TYPE,
    S12_COMPONENT_TYPE,
    S13_COMPONENT_TYPE,
    S14_COMPONENT_TYPE,
]

# 检查表型底稿 wp_code → a-program-console
CHECKLIST_WP_CODES = ["S1", "S2", "S8", "S9", "S10", "S11", "S16", "S17"]

# 子 sheet 编码映射
SUB_SHEET_MAPPINGS = {
    # S4 子 sheet → s4-nonmonetary-exchange
    "S4-1": S4_COMPONENT_TYPE,
    "S4-2": S4_COMPONENT_TYPE,
    # S5 子 sheet → s5-debt-restructuring
    "S5-1": S5_COMPONENT_TYPE,
    "S5-2": S5_COMPONENT_TYPE,
    # S6 子 sheet → s6-fund-occupation
    "S6-1": S6_COMPONENT_TYPE,
    # S9 子 sheet → a-program-console
    "S9-1": "a-program-console",
    "S9-2": "a-program-console",
    # S10 子 sheet → a-program-console
    "S10-1": "a-program-console",
    "S10-2": "a-program-console",
    # S17 子 sheet → a-program-console
    "S17-1": "a-program-console",
    "S17-2": "a-program-console",
    "S17-3": "a-program-console",
    "S17-11": "a-program-console",
    "S17-21": "a-program-console",
}


def _load_overrides() -> dict:
    p = Path(__file__).resolve().parent.parent / "app" / "data" / "wp_code_overrides.json"
    return json.loads(p.read_text(encoding="utf-8"))


# ─── wp_code_overrides：交易型→专属 componentType ─────────────────────────────


def test_s4_overrides_mapping():
    """S4 在 wp_code_overrides 中映射到 s4-nonmonetary-exchange."""
    data = _load_overrides()
    assert data.get("S4") == S4_COMPONENT_TYPE


def test_s5_overrides_mapping():
    """S5 在 wp_code_overrides 中映射到 s5-debt-restructuring."""
    data = _load_overrides()
    assert data.get("S5") == S5_COMPONENT_TYPE


def test_s6_overrides_mapping():
    """S6 在 wp_code_overrides 中映射到 s6-fund-occupation."""
    data = _load_overrides()
    assert data.get("S6") == S6_COMPONENT_TYPE


def test_s12_overrides_mapping():
    """S12 在 wp_code_overrides 中映射到 s12-cpa-expert."""
    data = _load_overrides()
    assert data.get("S12") == S12_COMPONENT_TYPE


def test_s13_overrides_mapping():
    """S13 在 wp_code_overrides 中映射到 s13-mgmt-expert."""
    data = _load_overrides()
    assert data.get("S13") == S13_COMPONENT_TYPE


def test_s14_overrides_mapping():
    """S14 在 wp_code_overrides 中映射到 s14-accounting-estimate."""
    data = _load_overrides()
    assert data.get("S14") == S14_COMPONENT_TYPE


# ─── wp_code_overrides：检查表型→a-program-console ────────────────────────────


def test_checklist_type_s1_overrides():
    """S1 在 wp_code_overrides 中映射到 a-program-console."""
    data = _load_overrides()
    assert data.get("S1") == "a-program-console"


def test_checklist_type_s2_overrides():
    """S2 在 wp_code_overrides 中映射到 a-program-console."""
    data = _load_overrides()
    assert data.get("S2") == "a-program-console"


def test_checklist_type_s8_overrides():
    """S8 在 wp_code_overrides 中映射到 a-program-console."""
    data = _load_overrides()
    assert data.get("S8") == "a-program-console"


def test_checklist_type_s9_overrides():
    """S9 在 wp_code_overrides 中映射到 a-program-console."""
    data = _load_overrides()
    assert data.get("S9") == "a-program-console"


def test_checklist_type_s10_overrides():
    """S10 在 wp_code_overrides 中映射到 a-program-console."""
    data = _load_overrides()
    assert data.get("S10") == "a-program-console"


def test_checklist_type_s11_overrides():
    """S11 在 wp_code_overrides 中映射到 a-program-console."""
    data = _load_overrides()
    assert data.get("S11") == "a-program-console"


def test_checklist_type_s16_overrides():
    """S16 在 wp_code_overrides 中映射到 a-program-console."""
    data = _load_overrides()
    assert data.get("S16") == "a-program-console"


def test_checklist_type_s17_overrides():
    """S17 在 wp_code_overrides 中映射到 a-program-console."""
    data = _load_overrides()
    assert data.get("S17") == "a-program-console"


# ─── wp_code_overrides：子 sheet 编码映射 ─────────────────────────────────────


def test_sub_sheet_s4_1_mapping():
    """S4-1 在 wp_code_overrides 中映射到 s4-nonmonetary-exchange."""
    data = _load_overrides()
    assert data.get("S4-1") == S4_COMPONENT_TYPE


def test_sub_sheet_s4_2_mapping():
    """S4-2 在 wp_code_overrides 中映射到 s4-nonmonetary-exchange."""
    data = _load_overrides()
    assert data.get("S4-2") == S4_COMPONENT_TYPE


def test_sub_sheet_s5_1_mapping():
    """S5-1 在 wp_code_overrides 中映射到 s5-debt-restructuring."""
    data = _load_overrides()
    assert data.get("S5-1") == S5_COMPONENT_TYPE


def test_sub_sheet_s5_2_mapping():
    """S5-2 在 wp_code_overrides 中映射到 s5-debt-restructuring."""
    data = _load_overrides()
    assert data.get("S5-2") == S5_COMPONENT_TYPE


def test_sub_sheet_s6_1_mapping():
    """S6-1 在 wp_code_overrides 中映射到 s6-fund-occupation."""
    data = _load_overrides()
    assert data.get("S6-1") == S6_COMPONENT_TYPE


def test_sub_sheet_s9_1_mapping():
    """S9-1 在 wp_code_overrides 中映射到 a-program-console."""
    data = _load_overrides()
    assert data.get("S9-1") == "a-program-console"


def test_sub_sheet_s9_2_mapping():
    """S9-2 在 wp_code_overrides 中映射到 a-program-console."""
    data = _load_overrides()
    assert data.get("S9-2") == "a-program-console"


def test_sub_sheet_s10_1_mapping():
    """S10-1 在 wp_code_overrides 中映射到 a-program-console."""
    data = _load_overrides()
    assert data.get("S10-1") == "a-program-console"


def test_sub_sheet_s10_2_mapping():
    """S10-2 在 wp_code_overrides 中映射到 a-program-console."""
    data = _load_overrides()
    assert data.get("S10-2") == "a-program-console"


def test_sub_sheet_s17_1_mapping():
    """S17-1 在 wp_code_overrides 中映射到 a-program-console."""
    data = _load_overrides()
    assert data.get("S17-1") == "a-program-console"


def test_sub_sheet_s17_2_mapping():
    """S17-2 在 wp_code_overrides 中映射到 a-program-console."""
    data = _load_overrides()
    assert data.get("S17-2") == "a-program-console"


def test_sub_sheet_s17_3_mapping():
    """S17-3 在 wp_code_overrides 中映射到 a-program-console."""
    data = _load_overrides()
    assert data.get("S17-3") == "a-program-console"


def test_sub_sheet_s17_11_mapping():
    """S17-11 在 wp_code_overrides 中映射到 a-program-console."""
    data = _load_overrides()
    assert data.get("S17-11") == "a-program-console"


def test_sub_sheet_s17_21_mapping():
    """S17-21 在 wp_code_overrides 中映射到 a-program-console."""
    data = _load_overrides()
    assert data.get("S17-21") == "a-program-console"


# ─── VALID_COMPONENT_TYPES ───────────────────────────────────────────────────


def test_s4_in_valid_component_types():
    """s4-nonmonetary-exchange 已注册于 VALID_COMPONENT_TYPES."""
    from app.services.wp_classification_service import VALID_COMPONENT_TYPES

    assert S4_COMPONENT_TYPE in VALID_COMPONENT_TYPES


def test_s5_in_valid_component_types():
    """s5-debt-restructuring 已注册于 VALID_COMPONENT_TYPES."""
    from app.services.wp_classification_service import VALID_COMPONENT_TYPES

    assert S5_COMPONENT_TYPE in VALID_COMPONENT_TYPES


def test_s6_in_valid_component_types():
    """s6-fund-occupation 已注册于 VALID_COMPONENT_TYPES."""
    from app.services.wp_classification_service import VALID_COMPONENT_TYPES

    assert S6_COMPONENT_TYPE in VALID_COMPONENT_TYPES


def test_s12_in_valid_component_types():
    """s12-cpa-expert 已注册于 VALID_COMPONENT_TYPES."""
    from app.services.wp_classification_service import VALID_COMPONENT_TYPES

    assert S12_COMPONENT_TYPE in VALID_COMPONENT_TYPES


def test_s13_in_valid_component_types():
    """s13-mgmt-expert 已注册于 VALID_COMPONENT_TYPES."""
    from app.services.wp_classification_service import VALID_COMPONENT_TYPES

    assert S13_COMPONENT_TYPE in VALID_COMPONENT_TYPES


def test_s14_in_valid_component_types():
    """s14-accounting-estimate 已注册于 VALID_COMPONENT_TYPES."""
    from app.services.wp_classification_service import VALID_COMPONENT_TYPES

    assert S14_COMPONENT_TYPE in VALID_COMPONENT_TYPES


# ─── RENDERER_DISPATCH ───────────────────────────────────────────────────────


def test_s4_registered_in_dispatch():
    """s4-nonmonetary-exchange 已注册于 RENDERER_DISPATCH."""
    from app.routers.wp_render_strategies import RENDERER_DISPATCH

    assert S4_COMPONENT_TYPE in RENDERER_DISPATCH


def test_s5_registered_in_dispatch():
    """s5-debt-restructuring 已注册于 RENDERER_DISPATCH."""
    from app.routers.wp_render_strategies import RENDERER_DISPATCH

    assert S5_COMPONENT_TYPE in RENDERER_DISPATCH


def test_s6_registered_in_dispatch():
    """s6-fund-occupation 已注册于 RENDERER_DISPATCH."""
    from app.routers.wp_render_strategies import RENDERER_DISPATCH

    assert S6_COMPONENT_TYPE in RENDERER_DISPATCH


def test_s12_registered_in_dispatch():
    """s12-cpa-expert 已注册于 RENDERER_DISPATCH."""
    from app.routers.wp_render_strategies import RENDERER_DISPATCH

    assert S12_COMPONENT_TYPE in RENDERER_DISPATCH


def test_s13_registered_in_dispatch():
    """s13-mgmt-expert 已注册于 RENDERER_DISPATCH."""
    from app.routers.wp_render_strategies import RENDERER_DISPATCH

    assert S13_COMPONENT_TYPE in RENDERER_DISPATCH


def test_s14_registered_in_dispatch():
    """s14-accounting-estimate 已注册于 RENDERER_DISPATCH."""
    from app.routers.wp_render_strategies import RENDERER_DISPATCH

    assert S14_COMPONENT_TYPE in RENDERER_DISPATCH


# ─── _WHOLE_WP_MULTISHEET_DEDICATED ─────────────────────────────────────────


def test_s4_in_whole_wp_multisheet_dedicated():
    """s4-nonmonetary-exchange 已加入 _WHOLE_WP_MULTISHEET_DEDICATED（整册统一路由）."""
    from app.routers.wp_render_config import _WHOLE_WP_MULTISHEET_DEDICATED

    assert S4_COMPONENT_TYPE in _WHOLE_WP_MULTISHEET_DEDICATED


def test_s5_in_whole_wp_multisheet_dedicated():
    """s5-debt-restructuring 已加入 _WHOLE_WP_MULTISHEET_DEDICATED（整册统一路由）."""
    from app.routers.wp_render_config import _WHOLE_WP_MULTISHEET_DEDICATED

    assert S5_COMPONENT_TYPE in _WHOLE_WP_MULTISHEET_DEDICATED


def test_s6_in_whole_wp_multisheet_dedicated():
    """s6-fund-occupation 已加入 _WHOLE_WP_MULTISHEET_DEDICATED（整册统一路由）."""
    from app.routers.wp_render_config import _WHOLE_WP_MULTISHEET_DEDICATED

    assert S6_COMPONENT_TYPE in _WHOLE_WP_MULTISHEET_DEDICATED


def test_s12_in_whole_wp_multisheet_dedicated():
    """s12-cpa-expert 已加入 _WHOLE_WP_MULTISHEET_DEDICATED（整册统一路由）."""
    from app.routers.wp_render_config import _WHOLE_WP_MULTISHEET_DEDICATED

    assert S12_COMPONENT_TYPE in _WHOLE_WP_MULTISHEET_DEDICATED


def test_s13_in_whole_wp_multisheet_dedicated():
    """s13-mgmt-expert 已加入 _WHOLE_WP_MULTISHEET_DEDICATED（整册统一路由）."""
    from app.routers.wp_render_config import _WHOLE_WP_MULTISHEET_DEDICATED

    assert S13_COMPONENT_TYPE in _WHOLE_WP_MULTISHEET_DEDICATED


def test_s14_in_whole_wp_multisheet_dedicated():
    """s14-accounting-estimate 已加入 _WHOLE_WP_MULTISHEET_DEDICATED（整册统一路由）."""
    from app.routers.wp_render_config import _WHOLE_WP_MULTISHEET_DEDICATED

    assert S14_COMPONENT_TYPE in _WHOLE_WP_MULTISHEET_DEDICATED


# ─── validate_overrides ──────────────────────────────────────────────────────


def test_validate_overrides_passes_for_s_special_transaction():
    """validate_overrides 对 S4~S14 + 检查表型映射及完整线上 overrides 均校验通过."""
    from app.services.wp_code_override_loader import validate_overrides

    # 交易型专属映射单独校验通过
    dedicated_overrides = {
        "S4": S4_COMPONENT_TYPE,
        "S5": S5_COMPONENT_TYPE,
        "S6": S6_COMPONENT_TYPE,
        "S12": S12_COMPONENT_TYPE,
        "S13": S13_COMPONENT_TYPE,
        "S14": S14_COMPONENT_TYPE,
    }
    validate_overrides(dedicated_overrides)

    # 检查表型映射单独校验通过
    checklist_overrides = {code: "a-program-console" for code in CHECKLIST_WP_CODES}
    validate_overrides(checklist_overrides)

    # 完整线上 overrides 整体校验通过
    validate_overrides(_load_overrides())
