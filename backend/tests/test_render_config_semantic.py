"""render-config 语义契约扩展测试。

覆盖 Task 2.1 / 2.2 / 4.5 / 4.6:
- sheet_type 从 schema 显式值提取
- sheet_type 从启发式推断
- sheet_type 两者皆无时返回 None
- field_sources 从 schema 提取
- field_sources 无配置时返回空 dict
- Task 4.5: schema 显式值优先于 registry 和启发式
- Task 4.6: registry schema_ref 不引用 generated/*.yaml
"""

import json
from pathlib import Path

import pytest

from backend.app.routers.wp_render_config import (
    _infer_sheet_type_from_schema,
    _infer_sheet_type_by_heuristic,
    _infer_sheet_type_from_registry,
    _load_semantic_registry,
    _resolve_sheet_type,
    _extract_field_sources,
)
import backend.app.routers.wp_render_config as _render_config_module


@pytest.fixture(autouse=True)
def _reset_registry_cache():
    """Reset the semantic registry cache between tests for clean state."""
    _render_config_module._SEMANTIC_REGISTRY_CACHE = None
    yield
    _render_config_module._SEMANTIC_REGISTRY_CACHE = None


# ---------------------------------------------------------------------------
# Task 2.1: sheet_type 推断
# ---------------------------------------------------------------------------


class TestInferSheetTypeFromSchema:
    """从 schema YAML 提取显式 sheet_type。"""

    def test_per_sheet_schema_has_sheet_type(self):
        sheet_schema = {"sheet_type": "audit_sheet", "sub_tables": []}
        assert _infer_sheet_type_from_schema(sheet_schema, None) == "audit_sheet"

    def test_full_schema_has_sheet_type(self):
        full_schema = {"sheet_type": "control_panel", "sheets": {}}
        assert _infer_sheet_type_from_schema(None, full_schema) == "control_panel"

    def test_per_sheet_overrides_full(self):
        sheet_schema = {"sheet_type": "detail_table"}
        full_schema = {"sheet_type": "audit_sheet"}
        assert _infer_sheet_type_from_schema(sheet_schema, full_schema) == "detail_table"

    def test_no_sheet_type_returns_none(self):
        assert _infer_sheet_type_from_schema(None, None) is None
        assert _infer_sheet_type_from_schema({}, {}) is None
        assert _infer_sheet_type_from_schema({"sub_tables": []}, {"wp_code": "D1"}) is None

    def test_empty_string_not_treated_as_valid(self):
        assert _infer_sheet_type_from_schema({"sheet_type": ""}, None) is None


class TestInferSheetTypeByHeuristic:
    """中文关键词启发式推断 sheet_type。"""

    @pytest.mark.parametrize("name,expected", [
        ("应收账款审定表D1-1", "audit_sheet"),
        ("D1-2 应收账款明细表", "detail_table"),
        ("账龄分析表", "analysis"),
        ("应收账款实质性程序表D2A", "procedure"),
        ("审计调整分录", "adjustment"),
        ("附注披露信息（上市公司）", "disclosure"),
        ("内控了解", "control_understanding"),
        ("控制测试", "control_test"),
        ("函证汇总", "confirmation_summary"),
        ("科目结论", "conclusion"),
        ("底稿目录", "control_panel"),
        ("科目驾驶舱", "control_panel"),
        ("随便一个英文sheet", None),
        ("Sheet1", None),
    ])
    def test_heuristic_patterns(self, name: str, expected: str | None):
        assert _infer_sheet_type_by_heuristic(name) == expected


class TestResolveSheetType:
    """完整优先级：schema > 启发式 > None。"""

    def test_schema_explicit_wins(self):
        """Property 2: schema 显式 sheet_type 存在时，启发式不覆盖。"""
        sheet_schema = {"sheet_type": "disclosure"}
        # sheet_name 含「审定」会被启发式推断为 audit_sheet，但 schema 优先
        result = _resolve_sheet_type(sheet_schema, None, "应收账款审定表D1-1")
        assert result == "disclosure"

    def test_heuristic_fallback(self):
        result = _resolve_sheet_type(None, None, "应收账款审定表D1-1")
        assert result == "audit_sheet"

    def test_returns_none_when_unknown(self):
        result = _resolve_sheet_type(None, None, "Sheet1")
        assert result is None


# ---------------------------------------------------------------------------
# Task 2.2: field_sources 提取
# ---------------------------------------------------------------------------


class TestExtractFieldSources:
    """从 schema 提取 field_sources 配置。"""

    def test_per_sheet_field_sources(self):
        field_sources = {
            "d1.audit_sheet.current_unadjusted": {
                "field_id": "d1.audit_sheet.current_unadjusted",
                "source_type": "trial_balance",
            }
        }
        sheet_schema = {"field_sources": field_sources}
        assert _extract_field_sources(sheet_schema, None) == field_sources

    def test_full_schema_field_sources(self):
        field_sources = {"some_field": {"source_type": "manual"}}
        full_schema = {"field_sources": field_sources}
        assert _extract_field_sources(None, full_schema) == field_sources

    def test_per_sheet_overrides_full(self):
        sheet_fs = {"a": {"type": "trial_balance"}}
        full_fs = {"b": {"type": "formula"}}
        assert _extract_field_sources({"field_sources": sheet_fs}, {"field_sources": full_fs}) == sheet_fs

    def test_no_field_sources_returns_empty(self):
        assert _extract_field_sources(None, None) == {}
        assert _extract_field_sources({}, {}) == {}
        assert _extract_field_sources({"sub_tables": []}, {"wp_code": "D1"}) == {}

    def test_non_dict_field_sources_ignored(self):
        """field_sources 必须是 dict，非 dict 值忽略。"""
        assert _extract_field_sources({"field_sources": "invalid"}, None) == {}
        assert _extract_field_sources({"field_sources": []}, None) == {}


# ---------------------------------------------------------------------------
# Task 4.3: 函证识别为 confirmation_summary 外部卡片
# ---------------------------------------------------------------------------


class TestConfirmationSummaryIdentification:
    """D2 函证应被识别为 confirmation_summary，不得误标为普通 D2-5 sheet。"""

    def test_registry_identifies_confirmation_summary(self):
        """函证汇总D2-5 在 registry 中标注为 confirmation_summary。"""
        result = _infer_sheet_type_from_registry("函证汇总D2-5")
        assert result == "confirmation_summary"

    def test_heuristic_also_catches_confirmation(self):
        """启发式也能识别函证关键词。"""
        result = _infer_sheet_type_by_heuristic("函证汇总D2-5")
        assert result == "confirmation_summary"

    def test_registry_marks_external_card(self):
        """Registry 标注 is_external_card=true。"""
        registry = _load_semantic_registry()
        entry = registry.get("函证汇总D2-5")
        assert entry is not None
        assert entry.get("is_external_card") is True


# ---------------------------------------------------------------------------
# Task 4.4: 审定表关键金额 field_sources 从 registry 读取
# ---------------------------------------------------------------------------


class TestRegistryFieldSources:
    """registry 中审定表应配置 field_sources。"""

    def test_d1_audit_sheet_has_field_sources(self):
        """D1 审定表在 registry 中配置了 field_sources。"""
        registry = _load_semantic_registry()
        entry = registry.get("审定表D1-1")
        assert entry is not None
        fs = entry.get("field_sources")
        assert isinstance(fs, dict)
        assert "d1.audit_sheet.current_unadjusted" in fs
        assert fs["d1.audit_sheet.current_unadjusted"]["source_type"] == "trial_balance"

    def test_d2_audit_sheet_has_field_sources(self):
        """D2 审定表在 registry 中配置了 field_sources。"""
        registry = _load_semantic_registry()
        entry = registry.get("审定表D2-1")
        assert entry is not None
        fs = entry.get("field_sources")
        assert isinstance(fs, dict)
        assert "d2.audit_sheet.current_unadjusted" in fs
        assert fs["d2.audit_sheet.current_unadjusted"]["source_type"] == "trial_balance"

    def test_extract_field_sources_falls_back_to_registry(self):
        """schema 无 field_sources 时从 registry 回退取出。"""
        result = _extract_field_sources(None, None, "审定表D1-1")
        assert "d1.audit_sheet.current_unadjusted" in result


# ---------------------------------------------------------------------------
# Task 4.5: schema 显式值优先于启发式和 registry
# ---------------------------------------------------------------------------


class TestSchemaExplicitOverridesAll:
    """Property 2: schema 显式 sheet_type 优先于 registry 和启发式。

    Validates: Requirements 1.2
    """

    def test_schema_overrides_registry_value(self):
        """Schema 显式 sheet_type 优先于 registry 中相同 sheet 的标注。"""
        # "审定表D1-1" 在 registry 中是 audit_sheet
        # 但若 schema 显式指定为 detail_table，应以 schema 为准
        sheet_schema = {"sheet_type": "detail_table"}
        result = _resolve_sheet_type(sheet_schema, None, "审定表D1-1")
        assert result == "detail_table"

    def test_schema_overrides_heuristic(self):
        """Schema 显式 sheet_type 优先于启发式推断。"""
        # "账龄分析表" 启发式会推断为 analysis
        # 但 schema 显式指定 procedure 应胜出
        sheet_schema = {"sheet_type": "procedure"}
        result = _resolve_sheet_type(sheet_schema, None, "账龄分析表")
        assert result == "procedure"

    def test_registry_overrides_heuristic(self):
        """Registry 标注优先于启发式（但低于 schema）。"""
        # "应收账款检查D2-13" 在 registry 中标注 procedure
        # 启发式可能因"分析"关键词推出别的，但 registry 优先
        result = _resolve_sheet_type(None, None, "应收账款检查D2-13")
        assert result == "procedure"

    def test_full_schema_sheet_type_overrides_registry(self):
        """顶层 full_schema 的 sheet_type 也优先于 registry。"""
        full_schema = {"sheet_type": "conclusion"}
        result = _resolve_sheet_type(None, full_schema, "审定表D1-1")
        assert result == "conclusion"


# ---------------------------------------------------------------------------
# Task 4.6: generated/*.yaml 不得出现在 production registry 的 schema_ref
# ---------------------------------------------------------------------------


class TestNoGeneratedInProductionRegistry:
    """generated/*.yaml 只能出现在 inventory/report，不得出现在 production registry 的 schema_ref。

    Validates: Requirements 4.6
    """

    def test_no_schema_ref_points_to_generated(self):
        """Registry 中所有 schema_ref 不得指向 generated/ 路径。"""
        registry = _load_semantic_registry()
        for sheet_name, entry in registry.items():
            if not isinstance(entry, dict):
                continue
            schema_ref = entry.get("schema_ref", "")
            assert not schema_ref.startswith("generated/"), (
                f"sheet '{sheet_name}' 的 schema_ref='{schema_ref}' "
                f"指向 generated/ 目录，违反 production registry 规则"
            )

    def test_registry_schema_refs_are_production_files(self):
        """Registry 中有 schema_ref 的条目，引用的文件必须在生产目录中存在。"""
        registry = _load_semantic_registry()
        schema_dir = Path(__file__).parent.parent / "data" / "ledger_adapters" / "wp_render_schema"
        for sheet_name, entry in registry.items():
            if not isinstance(entry, dict):
                continue
            schema_ref = entry.get("schema_ref")
            if schema_ref:
                target_path = schema_dir / schema_ref
                assert target_path.exists(), (
                    f"sheet '{sheet_name}' 的 schema_ref='{schema_ref}' "
                    f"引用的文件不存在: {target_path}"
                )

    def test_registry_has_valid_sheet_types(self):
        """Registry 中所有 sheet_type 值必须在 SheetContentType 枚举内。"""
        from backend.app.schemas.workpaper_semantic_contract import SheetContentType

        valid_values = {m.value for m in SheetContentType}
        registry = _load_semantic_registry()
        for sheet_name, entry in registry.items():
            if not isinstance(entry, dict):
                continue
            st = entry.get("sheet_type")
            if st:
                assert st in valid_values, (
                    f"sheet '{sheet_name}' 的 sheet_type='{st}' "
                    f"不在 SheetContentType 枚举中"
                )
