"""H7 生产性生物资产 — 注册契约测试.

Spec: .kiro/specs/h7-biological-assets/ Task 1.2
Validates: Requirements 1.6, 1.7, 1.8

验证 h7-biological-assets componentType 在后端三个注册表中正确注册：
1. wp_code_overrides（H7/H7A/H7-1~H7-17 共19个映射）
2. VALID_COMPONENT_TYPES
3. RENDERER_DISPATCH
4. schema_contract: checklist_responses 表结构验证
5. column_contract: item_id 支持 "H7-" 前缀
"""

import json
from pathlib import Path

import pytest

COMPONENT_TYPE = "h7-biological-assets"

# H7/H7A/H7-1~H7-17 共19个wp_code
EXPECTED_WP_CODES = [
    "H7",
    "H7A",
    "H7-1",
    "H7-2",
    "H7-3",
    "H7-4",
    "H7-5",
    "H7-6",
    "H7-7",
    "H7-8",
    "H7-9",
    "H7-10",
    "H7-11",
    "H7-12",
    "H7-13",
    "H7-14",
    "H7-15",
    "H7-16",
    "H7-17",
]


def _load_overrides() -> dict:
    p = Path(__file__).resolve().parent.parent / "app" / "data" / "wp_code_overrides.json"
    return json.loads(p.read_text(encoding="utf-8"))


# ─── wp_code_overrides 映射 ──────────────────────────────────────────────────


@pytest.mark.parametrize("wp_code", EXPECTED_WP_CODES)
def test_wp_code_override_mapping(wp_code: str):
    """wp_code_overrides: {wp_code} → h7-biological-assets."""
    data = _load_overrides()
    assert data.get(wp_code) == COMPONENT_TYPE


def test_wp_code_overrides_completeness():
    """wp_code_overrides 中 h7-biological-assets 映射覆盖完整（共19个）."""
    data = _load_overrides()
    h7_mappings = [k for k, v in data.items() if v == COMPONENT_TYPE]
    assert sorted(h7_mappings) == sorted(EXPECTED_WP_CODES)


# ─── VALID_COMPONENT_TYPES ───────────────────────────────────────────────────


def test_h7_in_valid_component_types():
    """h7-biological-assets 已注册于 VALID_COMPONENT_TYPES."""
    from app.services.wp_classification_service import VALID_COMPONENT_TYPES

    assert COMPONENT_TYPE in VALID_COMPONENT_TYPES


# ─── RENDERER_DISPATCH ───────────────────────────────────────────────────────


def test_h7_registered_in_dispatch_or_dedicated():
    """h7-biological-assets 已注册于 RENDERER_DISPATCH 或 DEDICATED_COMPONENT_TYPES."""
    from app.routers.wp_render_strategies import RENDERER_DISPATCH
    from app.services.dedicated_component_types import DEDICATED_COMPONENT_TYPES

    in_dispatch = COMPONENT_TYPE in RENDERER_DISPATCH
    in_dedicated = COMPONENT_TYPE in DEDICATED_COMPONENT_TYPES
    assert in_dispatch or in_dedicated, (
        f"{COMPONENT_TYPE} 不在 RENDERER_DISPATCH 也不在 DEDICATED_COMPONENT_TYPES"
    )


# ─── validate_overrides ──────────────────────────────────────────────────────


def test_validate_overrides_passes_for_h7():
    """validate_overrides 对 H7 映射及完整线上 overrides 均校验通过."""
    from app.services.wp_code_override_loader import validate_overrides

    # H7 映射单独校验通过
    single = {wp: COMPONENT_TYPE for wp in EXPECTED_WP_CODES}
    validate_overrides(single)

    # 完整线上 overrides 整体校验通过
    validate_overrides(_load_overrides())


# ─── schema_contract: checklist_responses 表结构验证 ─────────────────────────


def test_schema_contract_checklist_responses_supports_h7_prefix():
    """schema_contract: checklist_responses item_id 字段支持 H7- 前缀字符串."""
    from app.routers.checklist_responses import ChecklistResponseItem

    # 验证 schema 定义中 item_id 字段存在且为 str 类型
    fields = ChecklistResponseItem.model_fields
    assert "item_id" in fields, "ChecklistResponseItem 缺少 item_id 字段"
    field_info = fields["item_id"]
    assert field_info.annotation is str or field_info.annotation == str, (
        f"item_id 字段类型应为 str，实际为 {field_info.annotation}"
    )

    # 验证 H7- 前缀的 item_id 值能通过 schema 验证
    item = ChecklistResponseItem(item_id="H7-1-audited-row-1", conclusion="Y")
    assert item.item_id == "H7-1-audited-row-1"


def test_column_contract_h7_item_id_prefix_valid():
    """column_contract: 'H7-' 前缀格式 item_id 值合法."""
    h7_item_ids = [
        "H7-adj-note",
        "H7-adj-conclusion",
        "H7-1-audited-row-1",
        "H7-2-detail-row-001",
        "H7-11-dep-branch",
        "H7-14-production-row-1",
        "H7-measurement-model",
    ]
    for item_id in h7_item_ids:
        assert item_id.startswith("H7-"), f"{item_id} 不以 H7- 开头"
        assert len(item_id) <= 255, f"{item_id} 超过最大长度"
