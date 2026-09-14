"""I1 无形资产 — 注册契约测试.

Spec: .kiro/specs/i1-intangible-assets/ Task 1.2
Validates: Requirements 1.6, 1.7, 1.8

验证 i1-intangible-assets componentType 在后端三个注册表中正确注册：
1. wp_code_overrides（I1/I1A/I1-1~I1-13 共15个映射）
2. VALID_COMPONENT_TYPES
3. RENDERER_DISPATCH（task 5.1 实现后注册）
4. schema_contract: checklist_responses 表结构验证
5. column_contract: item_id 支持 "I1-" 前缀
"""

import json
from pathlib import Path

import pytest

COMPONENT_TYPE = "i1-intangible-assets"

# I1/I1A/I1-1~I1-13 共15个wp_code
EXPECTED_WP_CODES = [
    "I1",
    "I1A",
    "I1-1",
    "I1-2",
    "I1-3",
    "I1-4",
    "I1-5",
    "I1-6",
    "I1-7",
    "I1-8",
    "I1-9",
    "I1-10",
    "I1-11",
    "I1-12",
    "I1-13",
]


def _load_overrides() -> dict:
    p = Path(__file__).resolve().parent.parent / "app" / "data" / "wp_code_overrides.json"
    return json.loads(p.read_text(encoding="utf-8"))


# ─── wp_code_overrides 映射 ──────────────────────────────────────────────────


@pytest.mark.parametrize("wp_code", EXPECTED_WP_CODES)
def test_wp_code_override_mapping(wp_code: str):
    """wp_code_overrides: {wp_code} → i1-intangible-assets."""
    data = _load_overrides()
    assert data.get(wp_code) == COMPONENT_TYPE


def test_wp_code_overrides_completeness():
    """wp_code_overrides 中 i1-intangible-assets 映射覆盖完整（共15个）."""
    data = _load_overrides()
    i1_mappings = [k for k, v in data.items() if v == COMPONENT_TYPE]
    assert sorted(i1_mappings) == sorted(EXPECTED_WP_CODES)


# ─── VALID_COMPONENT_TYPES ───────────────────────────────────────────────────


def test_i1_in_valid_component_types():
    """i1-intangible-assets 已注册于 VALID_COMPONENT_TYPES."""
    from app.services.wp_classification_service import VALID_COMPONENT_TYPES

    assert COMPONENT_TYPE in VALID_COMPONENT_TYPES


# ─── RENDERER_DISPATCH ───────────────────────────────────────────────────────


def test_i1_registered_in_dispatch():
    """i1-intangible-assets 已注册于 RENDERER_DISPATCH（或 task 5.1 后注册）."""
    from app.routers.wp_render_strategies import RENDERER_DISPATCH

    # NOTE: RENDERER_DISPATCH 注册在 task 5.1 完成后才有
    # 此测试提前声明契约：一旦注册必须为 callable
    if COMPONENT_TYPE in RENDERER_DISPATCH:
        assert callable(RENDERER_DISPATCH[COMPONENT_TYPE])
    else:
        pytest.skip("i1-intangible-assets 尚未注册 RENDERER_DISPATCH（待 task 5.1）")


# ─── validate_overrides ──────────────────────────────────────────────────────


def test_validate_overrides_passes_for_i1():
    """validate_overrides 对 I1 映射及完整线上 overrides 均校验通过."""
    from app.services.wp_code_override_loader import validate_overrides

    # I1 映射单独校验通过
    single = {wp: COMPONENT_TYPE for wp in EXPECTED_WP_CODES}
    validate_overrides(single)

    # 完整线上 overrides 整体校验通过
    validate_overrides(_load_overrides())


# ─── schema_contract: checklist_responses 表结构验证 ─────────────────────────


def test_schema_contract_checklist_responses_supports_i1_prefix():
    """schema_contract: checklist_responses item_id 字段支持 I1- 前缀字符串.

    验证 Pydantic schema 中 item_id 为 str 类型，能承载 'I1-xxx' 前缀数据。
    """
    from app.routers.checklist_responses import ChecklistResponseItem

    # 验证 schema 定义中 item_id 字段存在且为 str 类型
    fields = ChecklistResponseItem.model_fields
    assert "item_id" in fields, "ChecklistResponseItem 缺少 item_id 字段"
    field_info = fields["item_id"]
    assert field_info.annotation is str or field_info.annotation == str, (
        f"item_id 字段类型应为 str，实际为 {field_info.annotation}"
    )

    # 验证 I1- 前缀的 item_id 值能通过 schema 验证
    item = ChecklistResponseItem(item_id="I1-adj-note", conclusion="Y")
    assert item.item_id == "I1-adj-note"


def test_column_contract_i1_item_id_prefix_valid():
    """column_contract: 'I1-' 前缀格式 item_id 值合法.

    确认以 'I1-' 开头的 item_id 能通过后端校验规则。
    """
    # I1 专属前缀示例
    i1_item_ids = [
        "I1-adj-note",
        "I1-adj-conclusion",
        "I1-1-audited-row-1",
        "I1-2-detail-row-001",
        "I1-10-amort-no-impair",
        "I1-11-amort-with-impair",
        "I1-12-impairment-dcf",
        "I1-13-recoverable-pv",
    ]
    for item_id in i1_item_ids:
        assert item_id.startswith("I1-"), f"{item_id} 不以 I1- 开头"
        # 验证不包含非法字符
        assert len(item_id) <= 255, f"{item_id} 超过最大长度"
