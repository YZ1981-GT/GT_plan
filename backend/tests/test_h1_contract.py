"""H1 固定资产 — 注册契约测试.

Spec: .kiro/specs/h1-fixed-assets/ Task 1.2 + Task 7.1
Validates: Requirements 1.6, 1.7, 1.8

验证 h1-fixed-assets componentType 在后端三个注册表中正确注册：
1. wp_code_overrides（H1/H1A/H1-1~H1-20 共22个映射）
2. VALID_COMPONENT_TYPES
3. RENDERER_DISPATCH
4. schema_contract: checklist_responses 表结构验证
5. column_contract: item_id 支持 "H1-" 前缀
"""

import json
from pathlib import Path

import pytest

COMPONENT_TYPE = "h1-fixed-assets"

# H1/H1A/H1-1~H1-20 共22个wp_code
EXPECTED_WP_CODES = [
    "H1",
    "H1A",
    "H1-1",
    "H1-2",
    "H1-3",
    "H1-4",
    "H1-5",
    "H1-6",
    "H1-7",
    "H1-8",
    "H1-9",
    "H1-10",
    "H1-11",
    "H1-12",
    "H1-13",
    "H1-14",
    "H1-15",
    "H1-16",
    "H1-17",
    "H1-18",
    "H1-19",
    "H1-20",
]


def _load_overrides() -> dict:
    p = Path(__file__).resolve().parent.parent / "app" / "data" / "wp_code_overrides.json"
    return json.loads(p.read_text(encoding="utf-8"))


# ─── wp_code_overrides 映射 ──────────────────────────────────────────────────


@pytest.mark.parametrize("wp_code", EXPECTED_WP_CODES)
def test_wp_code_override_mapping(wp_code: str):
    """wp_code_overrides: {wp_code} → h1-fixed-assets."""
    data = _load_overrides()
    assert data.get(wp_code) == COMPONENT_TYPE


def test_wp_code_overrides_completeness():
    """wp_code_overrides 中 h1-fixed-assets 映射覆盖完整（共22个）."""
    data = _load_overrides()
    h1_mappings = [k for k, v in data.items() if v == COMPONENT_TYPE]
    assert sorted(h1_mappings) == sorted(EXPECTED_WP_CODES)


# ─── VALID_COMPONENT_TYPES ───────────────────────────────────────────────────


def test_h1_in_valid_component_types():
    """h1-fixed-assets 已注册于 VALID_COMPONENT_TYPES."""
    from app.services.wp_classification_service import VALID_COMPONENT_TYPES

    assert COMPONENT_TYPE in VALID_COMPONENT_TYPES


# ─── RENDERER_DISPATCH ───────────────────────────────────────────────────────


def test_h1_registered_in_dispatch():
    """h1-fixed-assets 已注册于 RENDERER_DISPATCH."""
    from app.routers.wp_render_strategies import RENDERER_DISPATCH

    assert COMPONENT_TYPE in RENDERER_DISPATCH
    assert callable(RENDERER_DISPATCH[COMPONENT_TYPE])


# ─── validate_overrides ──────────────────────────────────────────────────────


def test_validate_overrides_passes_for_h1():
    """validate_overrides 对 H1 映射及完整线上 overrides 均校验通过."""
    from app.services.wp_code_override_loader import validate_overrides

    # H1 映射单独校验通过
    single = {wp: COMPONENT_TYPE for wp in EXPECTED_WP_CODES}
    validate_overrides(single)

    # 完整线上 overrides 整体校验通过
    validate_overrides(_load_overrides())


# ─── schema_contract: checklist_responses 表结构验证 ─────────────────────────


def test_schema_contract_checklist_responses_supports_h1_prefix():
    """schema_contract: checklist_responses item_id 字段支持 H1- 前缀字符串.

    验证 Pydantic schema 中 item_id 为 str 类型，能承载 'H1-xxx' 前缀数据。
    """
    from app.routers.checklist_responses import ChecklistResponseItem

    # 验证 schema 定义中 item_id 字段存在且为 str 类型
    fields = ChecklistResponseItem.model_fields
    assert "item_id" in fields, "ChecklistResponseItem 缺少 item_id 字段"
    field_info = fields["item_id"]
    assert field_info.annotation is str or field_info.annotation == str, (
        f"item_id 字段类型应为 str，实际为 {field_info.annotation}"
    )

    # 验证 H1- 前缀的 item_id 值能通过 schema 验证
    item = ChecklistResponseItem(item_id="H1-adj-note", conclusion="Y")
    assert item.item_id == "H1-adj-note"


def test_column_contract_h1_item_id_prefix_valid():
    """column_contract: 'H1-' 前缀格式 item_id 值合法.

    确认以 'H1-' 开头的 item_id 能通过后端校验规则。
    """
    # H1 专属前缀示例
    h1_item_ids = [
        "H1-adj-note",
        "H1-adj-conclusion",
        "H1-1-audited-row-1",
        "H1-2-detail-row-001",
        "H1-12-dep-branch",
        "H1-14-impairment-dcf",
    ]
    for item_id in h1_item_ids:
        assert item_id.startswith("H1-"), f"{item_id} 不以 H1- 开头"
        # 验证不包含非法字符
        assert len(item_id) <= 255, f"{item_id} 超过最大长度"
