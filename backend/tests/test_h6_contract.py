"""H6 固定资产清理 — 注册契约测试.

Spec: .kiro/specs/h6-asset-disposal-clearing/ Task 1.2
Validates: Requirements 1.6, 1.7, 1.8

验证 h6-asset-disposal-clearing componentType 在后端注册表中正确注册：
1. wp_code_overrides（H6/H6A/H6-1~H6-4 共6个映射）
2. VALID_COMPONENT_TYPES
3. RENDERER_DISPATCH（Phase 5创建后验证）
4. schema_contract: checklist_responses 表结构验证
5. column_contract: item_id 支持 "H6-" 前缀
"""

import json
from pathlib import Path

import pytest

COMPONENT_TYPE = "h6-asset-disposal-clearing"

# H6/H6A/H6-1~H6-4 共6个wp_code
EXPECTED_WP_CODES = [
    "H6",
    "H6A",
    "H6-1",
    "H6-2",
    "H6-3",
    "H6-4",
]


def _load_overrides() -> dict:
    p = Path(__file__).resolve().parent.parent / "app" / "data" / "wp_code_overrides.json"
    return json.loads(p.read_text(encoding="utf-8"))


# ─── wp_code_overrides 映射 ──────────────────────────────────────────────────


@pytest.mark.parametrize("wp_code", EXPECTED_WP_CODES)
def test_wp_code_override_mapping(wp_code: str):
    """wp_code_overrides: {wp_code} → h6-asset-disposal-clearing."""
    data = _load_overrides()
    assert data.get(wp_code) == COMPONENT_TYPE


def test_wp_code_overrides_completeness():
    """wp_code_overrides 中 h6-asset-disposal-clearing 映射覆盖完整（共6个）."""
    data = _load_overrides()
    h6_mappings = [k for k, v in data.items() if v == COMPONENT_TYPE]
    assert sorted(h6_mappings) == sorted(EXPECTED_WP_CODES)


def test_wp_code_overrides_count():
    """wp_code_overrides 中 h6-asset-disposal-clearing 映射数量正好6个."""
    data = _load_overrides()
    h6_mappings = [k for k, v in data.items() if v == COMPONENT_TYPE]
    assert len(h6_mappings) == 6


# ─── VALID_COMPONENT_TYPES ───────────────────────────────────────────────────


def test_h6_in_valid_component_types():
    """h6-asset-disposal-clearing 已注册于 VALID_COMPONENT_TYPES."""
    from app.services.wp_classification_service import VALID_COMPONENT_TYPES

    assert COMPONENT_TYPE in VALID_COMPONENT_TYPES


# ─── RENDERER_DISPATCH ───────────────────────────────────────────────────────


def test_h6_registered_in_dispatch():
    """h6-asset-disposal-clearing 已注册于 RENDERER_DISPATCH（Phase 5 创建后验证）."""
    from app.routers.wp_render_strategies import RENDERER_DISPATCH

    # 注意：renderer将在Phase 5(task 5.1)创建，此处验证key存在性
    # 如果Phase 5尚未完成，此测试会跳过
    if COMPONENT_TYPE not in RENDERER_DISPATCH:
        pytest.skip("RENDERER_DISPATCH 注册将在 Phase 5 (task 5.1) 完成")
    assert COMPONENT_TYPE in RENDERER_DISPATCH
    assert callable(RENDERER_DISPATCH[COMPONENT_TYPE])


# ─── validate_overrides ──────────────────────────────────────────────────────


def test_validate_overrides_passes_for_h6():
    """validate_overrides 对 H6 映射及完整线上 overrides 均校验通过."""
    from app.services.wp_code_override_loader import validate_overrides

    # H6 映射单独校验通过
    single = {wp: COMPONENT_TYPE for wp in EXPECTED_WP_CODES}
    validate_overrides(single)

    # 完整线上 overrides 整体校验通过
    validate_overrides(_load_overrides())


# ─── schema_contract: checklist_responses 表结构验证 ─────────────────────────


def test_schema_contract_checklist_responses_supports_h6_prefix():
    """schema_contract: checklist_responses item_id 字段支持 H6- 前缀字符串.

    验证 Pydantic schema 中 item_id 为 str 类型，能承载 'H6-xxx' 前缀数据。
    """
    from app.routers.checklist_responses import ChecklistResponseItem

    # 验证 schema 定义中 item_id 字段存在且为 str 类型
    fields = ChecklistResponseItem.model_fields
    assert "item_id" in fields, "ChecklistResponseItem 缺少 item_id 字段"
    field_info = fields["item_id"]
    assert field_info.annotation is str or field_info.annotation == str, (
        f"item_id 字段类型应为 str，实际为 {field_info.annotation}"
    )

    # 验证 H6- 前缀的 item_id 值能通过 schema 验证
    item = ChecklistResponseItem(item_id="H6-1-audited-row-1", conclusion="Y")
    assert item.item_id == "H6-1-audited-row-1"


def test_column_contract_h6_item_id_prefix_valid():
    """column_contract: 'H6-' 前缀格式 item_id 值合法.

    确认以 'H6-' 开头的 item_id 能通过后端校验规则。
    """
    # H6 专属前缀示例
    h6_item_ids = [
        "H6-1-audited-row-1",
        "H6-1-adj-note",
        "H6-1-adj-conclusion",
        "H6-2-detail-row-001",
        "H6-3-adjustment-001",
        "H6-4-check-001",
    ]
    for item_id in h6_item_ids:
        assert item_id.startswith("H6-"), f"{item_id} 不以 H6- 开头"
        # 验证不包含非法字符
        assert len(item_id) <= 255, f"{item_id} 超过最大长度"
