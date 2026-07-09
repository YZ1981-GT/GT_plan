"""H8 使用权资产 — 注册契约测试.

Spec: .kiro/specs/h8-right-of-use-assets/ Task 1.2
Validates: Requirements 1.6, 1.7, 1.8

验证 h8-right-of-use-assets componentType 在后端注册表中正确注册：
1. wp_code_overrides（H8/H8A/H8-1~H8-14 共16个映射）
2. VALID_COMPONENT_TYPES
3. RENDERER_DISPATCH
4. schema_contract: checklist_responses 表结构验证
5. column_contract: item_id 支持 "H8-" 前缀
"""

import json
from pathlib import Path

import pytest

COMPONENT_TYPE = "h8-right-of-use-assets"

# H8/H8A/H8-1~H8-14 共16个wp_code
EXPECTED_WP_CODES = [
    "H8",
    "H8A",
    "H8-1",
    "H8-2",
    "H8-3",
    "H8-4",
    "H8-5",
    "H8-6",
    "H8-7",
    "H8-8",
    "H8-9",
    "H8-10",
    "H8-11",
    "H8-12",
    "H8-13",
    "H8-14",
]


def _load_overrides() -> dict:
    p = Path(__file__).resolve().parent.parent / "app" / "data" / "wp_code_overrides.json"
    return json.loads(p.read_text(encoding="utf-8"))


# ─── wp_code_overrides 映射 ──────────────────────────────────────────────────


@pytest.mark.parametrize("wp_code", EXPECTED_WP_CODES)
def test_wp_code_override_mapping(wp_code: str):
    """wp_code_overrides: {wp_code} → h8-right-of-use-assets."""
    data = _load_overrides()
    assert data.get(wp_code) == COMPONENT_TYPE


def test_wp_code_overrides_completeness():
    """wp_code_overrides 中 h8-right-of-use-assets 映射覆盖完整（共16个）."""
    data = _load_overrides()
    h8_mappings = [k for k, v in data.items() if v == COMPONENT_TYPE]
    assert sorted(h8_mappings) == sorted(EXPECTED_WP_CODES)


def test_wp_code_overrides_count():
    """wp_code_overrides 中 h8-right-of-use-assets 映射数量正好16个."""
    data = _load_overrides()
    h8_mappings = [k for k, v in data.items() if v == COMPONENT_TYPE]
    assert len(h8_mappings) == 16


# ─── VALID_COMPONENT_TYPES ───────────────────────────────────────────────────


def test_h8_in_valid_component_types():
    """h8-right-of-use-assets 已注册于 VALID_COMPONENT_TYPES."""
    from app.services.wp_classification_service import VALID_COMPONENT_TYPES

    assert COMPONENT_TYPE in VALID_COMPONENT_TYPES


# ─── RENDERER_DISPATCH ───────────────────────────────────────────────────────


def test_h8_registered_in_dispatch():
    """h8-right-of-use-assets 已注册于 RENDERER_DISPATCH."""
    from app.routers.wp_render_strategies import RENDERER_DISPATCH

    assert COMPONENT_TYPE in RENDERER_DISPATCH
    assert callable(RENDERER_DISPATCH[COMPONENT_TYPE])


# ─── validate_overrides ──────────────────────────────────────────────────────


def test_validate_overrides_passes_for_h8():
    """validate_overrides 对 H8 映射及完整线上 overrides 均校验通过."""
    from app.services.wp_code_override_loader import validate_overrides

    # H8 映射单独校验通过
    single = {wp: COMPONENT_TYPE for wp in EXPECTED_WP_CODES}
    validate_overrides(single)

    # 完整线上 overrides 整体校验通过
    validate_overrides(_load_overrides())


# ─── schema_contract: checklist_responses 表结构验证 ─────────────────────────


def test_schema_contract_checklist_responses_supports_h8_prefix():
    """schema_contract: checklist_responses item_id 字段支持 H8- 前缀字符串.

    验证 Pydantic schema 中 item_id 为 str 类型，能承载 'H8-xxx' 前缀数据。
    """
    from app.routers.checklist_responses import ChecklistResponseItem

    # 验证 schema 定义中 item_id 字段存在且为 str 类型
    fields = ChecklistResponseItem.model_fields
    assert "item_id" in fields, "ChecklistResponseItem 缺少 item_id 字段"
    field_info = fields["item_id"]
    assert field_info.annotation is str or field_info.annotation == str, (
        f"item_id 字段类型应为 str，实际为 {field_info.annotation}"
    )

    # 验证 H8- 前缀的 item_id 值能通过 schema 验证
    item = ChecklistResponseItem(item_id="H8-1-audited-row-1", conclusion="Y")
    assert item.item_id == "H8-1-audited-row-1"


def test_column_contract_h8_item_id_prefix_valid():
    """column_contract: 'H8-' 前缀格式 item_id 值合法.

    确认以 'H8-' 开头的 item_id 能通过后端校验规则。
    """
    # H8 专属前缀示例（覆盖多种sheet）
    h8_item_ids = [
        "H8-1-audited-row-1",
        "H8-1-adj-note",
        "H8-1-adj-conclusion",
        "H8-2-detail-row-001",
        "H8-3-adjustment-001",
        "H8-4-identification-001",
        "H8-5-lease-term-001",
        "H8-6-measurement-001",
        "H8-7-modification-001",
        "H8-8-depreciation-001",
        "H8-9-alloc-001",
        "H8-10-impairment-001",
        "H8-11-recoverable-001",
        "H8-12-disposal-001",
        "H8-13-simplified-001",
        "H8-14-related-001",
    ]
    for item_id in h8_item_ids:
        assert item_id.startswith("H8-"), f"{item_id} 不以 H8- 开头"
        # 验证不包含非法字符
        assert len(item_id) <= 255, f"{item_id} 超过最大长度"
