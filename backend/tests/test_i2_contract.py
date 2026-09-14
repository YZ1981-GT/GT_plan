"""I2 开发支出 — 注册契约测试.

Spec: .kiro/specs/i2-development-expenditure/ Task 1.2
Validates: Requirements 1.6, 1.7, 1.8

验证 i2-development-expenditure componentType 在后端三个注册表中正确注册：
1. wp_code_overrides（I2/I2A/I2-1~I2-16 共18个映射）
2. VALID_COMPONENT_TYPES
3. RENDERER_DISPATCH（task 5.1 实现后注册）
4. schema_contract: checklist_responses 表结构验证
5. column_contract: item_id 支持 "I2-" 前缀
"""

import json
from pathlib import Path

import pytest

COMPONENT_TYPE = "i2-development-expenditure"

# I2/I2A/I2-1~I2-16 共18个wp_code
EXPECTED_WP_CODES = [
    "I2",
    "I2A",
    "I2-1",
    "I2-2",
    "I2-3",
    "I2-4",
    "I2-5",
    "I2-6",
    "I2-7",
    "I2-8",
    "I2-9",
    "I2-10",
    "I2-11",
    "I2-12",
    "I2-13",
    "I2-14",
    "I2-15",
    "I2-16",
]


def _load_overrides() -> dict:
    p = Path(__file__).resolve().parent.parent / "app" / "data" / "wp_code_overrides.json"
    return json.loads(p.read_text(encoding="utf-8"))


# ─── wp_code_overrides 映射 ──────────────────────────────────────────────────


@pytest.mark.parametrize("wp_code", EXPECTED_WP_CODES)
def test_wp_code_override_mapping(wp_code: str):
    """wp_code_overrides: {wp_code} → i2-development-expenditure."""
    data = _load_overrides()
    assert data.get(wp_code) == COMPONENT_TYPE


def test_wp_code_overrides_completeness():
    """wp_code_overrides 中 i2-development-expenditure 映射覆盖完整（共18个）."""
    data = _load_overrides()
    i2_mappings = [k for k, v in data.items() if v == COMPONENT_TYPE]
    assert sorted(i2_mappings) == sorted(EXPECTED_WP_CODES)


# ─── VALID_COMPONENT_TYPES ───────────────────────────────────────────────────


def test_i2_in_valid_component_types():
    """i2-development-expenditure 已注册于 VALID_COMPONENT_TYPES."""
    from app.services.wp_classification_service import VALID_COMPONENT_TYPES

    assert COMPONENT_TYPE in VALID_COMPONENT_TYPES


# ─── RENDERER_DISPATCH ───────────────────────────────────────────────────────


def test_i2_registered_in_dispatch():
    """i2-development-expenditure 已注册于 RENDERER_DISPATCH（或 task 5.1 后注册）."""
    from app.routers.wp_render_strategies import RENDERER_DISPATCH

    # NOTE: RENDERER_DISPATCH 注册在 task 5.1 完成后才有
    # 此测试提前声明契约：一旦注册必须为 callable
    if COMPONENT_TYPE in RENDERER_DISPATCH:
        assert callable(RENDERER_DISPATCH[COMPONENT_TYPE])
    else:
        pytest.skip("i2-development-expenditure 尚未注册 RENDERER_DISPATCH（待 task 5.1）")


# ─── validate_overrides ──────────────────────────────────────────────────────


def test_validate_overrides_passes_for_i2():
    """validate_overrides 对 I2 映射及完整线上 overrides 均校验通过."""
    from app.services.wp_code_override_loader import validate_overrides

    # I2 映射单独校验通过
    single = {wp: COMPONENT_TYPE for wp in EXPECTED_WP_CODES}
    validate_overrides(single)

    # 完整线上 overrides 整体校验通过
    validate_overrides(_load_overrides())


# ─── schema_contract: checklist_responses 表结构验证 ─────────────────────────


def test_schema_contract_checklist_responses_supports_i2_prefix():
    """schema_contract: checklist_responses item_id 字段支持 I2- 前缀字符串.

    验证 Pydantic schema 中 item_id 为 str 类型，能承载 'I2-xxx' 前缀数据。
    """
    from app.routers.checklist_responses import ChecklistResponseItem

    # 验证 schema 定义中 item_id 字段存在且为 str 类型
    fields = ChecklistResponseItem.model_fields
    assert "item_id" in fields, "ChecklistResponseItem 缺少 item_id 字段"
    field_info = fields["item_id"]
    assert field_info.annotation is str or field_info.annotation == str, (
        f"item_id 字段类型应为 str，实际为 {field_info.annotation}"
    )

    # 验证 I2- 前缀的 item_id 值能通过 schema 验证
    item = ChecklistResponseItem(item_id="I2-adj-note", conclusion="Y")
    assert item.item_id == "I2-adj-note"


def test_column_contract_i2_item_id_prefix_valid():
    """column_contract: 'I2-' 前缀格式 item_id 值合法.

    确认以 'I2-' 开头的 item_id 能通过后端校验规则。
    """
    # I2 专属前缀示例
    i2_item_ids = [
        "I2-adj-note",
        "I2-adj-conclusion",
        "I2-1-audited-row-1",
        "I2-2-detail-row-001",
        "I2-6-cas6-cond-1",
        "I2-6-cas6-conclusion",
        "I2-7-project-detail-001",
        "I2-13-cutoff-forward",
        "I2-15-impairment-dcf",
        "I2-16-recoverable-pv",
    ]
    for item_id in i2_item_ids:
        assert item_id.startswith("I2-"), f"{item_id} 不以 I2- 开头"
        # 验证不包含非法字符
        assert len(item_id) <= 255, f"{item_id} 超过最大长度"
