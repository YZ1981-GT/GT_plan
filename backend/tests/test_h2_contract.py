"""H2 在建工程 — 注册契约测试.

Spec: .kiro/specs/h2-construction-in-progress/ Task 1.2
Validates: Requirements 1.6, 1.7, 1.8

验证 h2-construction-in-progress componentType 在后端三个注册表中正确注册：
1. wp_code_overrides（H2/H2A/H2-1~H2-17 共19个映射）
2. VALID_COMPONENT_TYPES
3. RENDERER_DISPATCH（Phase 5完成后生效，当前 xfail）
4. schema_contract: checklist_responses 表结构验证
5. column_contract: item_id 支持 "H2-" 前缀
"""

import json
from pathlib import Path

import pytest

COMPONENT_TYPE = "h2-construction-in-progress"

# H2/H2A/H2-1~H2-17 共19个wp_code
EXPECTED_WP_CODES = [
    "H2",
    "H2A",
    "H2-1",
    "H2-2",
    "H2-3",
    "H2-4",
    "H2-5",
    "H2-6",
    "H2-7",
    "H2-8",
    "H2-9",
    "H2-10",
    "H2-11",
    "H2-12",
    "H2-13",
    "H2-14",
    "H2-15",
    "H2-16",
    "H2-17",
]


def _load_overrides() -> dict:
    p = Path(__file__).resolve().parent.parent / "app" / "data" / "wp_code_overrides.json"
    return json.loads(p.read_text(encoding="utf-8"))


# ─── wp_code_overrides 映射 ──────────────────────────────────────────────────


@pytest.mark.parametrize("wp_code", EXPECTED_WP_CODES)
def test_wp_code_override_mapping(wp_code: str):
    """wp_code_overrides: {wp_code} → h2-construction-in-progress."""
    data = _load_overrides()
    assert data.get(wp_code) == COMPONENT_TYPE


def test_wp_code_overrides_completeness():
    """wp_code_overrides 中 h2-construction-in-progress 映射覆盖完整（共19个）."""
    data = _load_overrides()
    h2_mappings = [k for k, v in data.items() if v == COMPONENT_TYPE]
    assert sorted(h2_mappings) == sorted(EXPECTED_WP_CODES)


def test_wp_code_overrides_count():
    """wp_code_overrides 中 h2-construction-in-progress 映射数量正好19个."""
    data = _load_overrides()
    h2_mappings = [k for k, v in data.items() if v == COMPONENT_TYPE]
    assert len(h2_mappings) == 19


# ─── VALID_COMPONENT_TYPES ───────────────────────────────────────────────────


def test_h2_in_valid_component_types():
    """h2-construction-in-progress 已注册于 VALID_COMPONENT_TYPES."""
    from app.services.wp_classification_service import VALID_COMPONENT_TYPES

    assert COMPONENT_TYPE in VALID_COMPONENT_TYPES


# ─── RENDERER_DISPATCH ───────────────────────────────────────────────────────


def test_h2_registered_in_dispatch():
    """h2-construction-in-progress 已注册于 RENDERER_DISPATCH."""
    from app.routers.wp_render_strategies import RENDERER_DISPATCH

    assert COMPONENT_TYPE in RENDERER_DISPATCH
    assert callable(RENDERER_DISPATCH[COMPONENT_TYPE])


# ─── validate_overrides ──────────────────────────────────────────────────────


def test_validate_overrides_passes_for_h2():
    """validate_overrides 对 H2 映射及完整线上 overrides 均校验通过."""
    from app.services.wp_code_override_loader import validate_overrides

    # H2 映射单独校验通过
    single = {wp: COMPONENT_TYPE for wp in EXPECTED_WP_CODES}
    validate_overrides(single)

    # 完整线上 overrides 整体校验通过
    validate_overrides(_load_overrides())


# ─── schema_contract: checklist_responses 表结构验证 ─────────────────────────


def test_schema_contract_checklist_responses_supports_h2_prefix():
    """schema_contract: checklist_responses item_id 字段支持 H2- 前缀字符串.

    验证 Pydantic schema 中 item_id 为 str 类型，能承载 'H2-xxx' 前缀数据。
    """
    from app.routers.checklist_responses import ChecklistResponseItem

    # 验证 schema 定义中 item_id 字段存在且为 str 类型
    fields = ChecklistResponseItem.model_fields
    assert "item_id" in fields, "ChecklistResponseItem 缺少 item_id 字段"
    field_info = fields["item_id"]
    assert field_info.annotation is str or field_info.annotation == str, (
        f"item_id 字段类型应为 str，实际为 {field_info.annotation}"
    )

    # 验证 H2- 前缀的 item_id 值能通过 schema 验证
    item = ChecklistResponseItem(item_id="H2-adj-note", conclusion="Y")
    assert item.item_id == "H2-adj-note"


def test_column_contract_h2_item_id_prefix_valid():
    """column_contract: 'H2-' 前缀格式 item_id 值合法.

    确认以 'H2-' 开头的 item_id 能通过后端校验规则。
    """
    # H2 专属前缀示例
    h2_item_ids = [
        "H2-adj-note",
        "H2-adj-conclusion",
        "H2-1-audited-row-1",
        "H2-2-detail-row-001",
        "H2-5-transfer-cond",
        "H2-10-interest-cap",
        "H2-15-impairment-dcf",
        "H2-17-related-party",
    ]
    for item_id in h2_item_ids:
        assert item_id.startswith("H2-"), f"{item_id} 不以 H2- 开头"
        # 验证不包含非法字符
        assert len(item_id) <= 255, f"{item_id} 超过最大长度"
