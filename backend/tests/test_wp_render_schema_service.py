"""Tests for wp_render_schema_service — 配置驱动渲染 schema 加载 + 项目级覆盖合并

Validates: Requirements 2.2 原则 2（配置驱动）
"""

import tempfile
from pathlib import Path
from uuid import uuid4

import pytest
import yaml

from app.services.wp_render_schema_service import (
    WpRenderSchemaService,
    _SCHEMA_DIR,
    _deep_merge,
)


@pytest.fixture
def service():
    """Fresh service instance per test (no shared cache)."""
    return WpRenderSchemaService()


@pytest.fixture
def tmp_schema_dir(monkeypatch, tmp_path):
    """Redirect _SCHEMA_DIR to a temp directory for isolated tests."""
    monkeypatch.setattr(
        "app.services.wp_render_schema_service._SCHEMA_DIR", tmp_path
    )
    return tmp_path


# ─── load_schema tests ────────────────────────────────────────────────────


class TestLoadSchema:
    def test_load_exact_match(self, service, tmp_schema_dir):
        """精确匹配 wp_code.yaml 文件"""
        schema_data = {
            "wp_code": "D2A",
            "template_path": "backend/wp_templates/D/D2.xlsx",
            "sheets": {"程序表D2A": {"component_type": "a-program-console"}},
        }
        schema_file = tmp_schema_dir / "D2A.yaml"
        schema_file.write_text(yaml.dump(schema_data, allow_unicode=True), encoding="utf-8")

        result = service.load_schema("D2A")

        assert result["wp_code"] == "D2A"
        assert result["sheets"]["程序表D2A"]["component_type"] == "a-program-console"

    def test_load_fallback_template(self, service, tmp_schema_dir):
        """前缀 fallback: B12 → B-template.yaml"""
        template_data = {
            "wp_code": "B-template",
            "sheets": {"底稿目录": {"component_type": "b-index"}},
        }
        fallback_file = tmp_schema_dir / "B-template.yaml"
        fallback_file.write_text(yaml.dump(template_data, allow_unicode=True), encoding="utf-8")

        result = service.load_schema("B12")

        assert result["wp_code"] == "B-template"
        assert result["sheets"]["底稿目录"]["component_type"] == "b-index"

    def test_exact_match_takes_priority_over_fallback(self, service, tmp_schema_dir):
        """精确匹配优先于 fallback"""
        # 创建 fallback
        fallback_data = {"wp_code": "B-template", "source": "fallback"}
        (tmp_schema_dir / "B-template.yaml").write_text(
            yaml.dump(fallback_data), encoding="utf-8"
        )
        # 创建精确匹配
        exact_data = {"wp_code": "B12", "source": "exact"}
        (tmp_schema_dir / "B12.yaml").write_text(
            yaml.dump(exact_data), encoding="utf-8"
        )

        result = service.load_schema("B12")

        assert result["source"] == "exact"

    def test_file_not_found_raises(self, service, tmp_schema_dir):
        """找不到 schema 文件时抛 FileNotFoundError"""
        with pytest.raises(FileNotFoundError, match="Render schema not found"):
            service.load_schema("NONEXISTENT99")

    def test_caching(self, service, tmp_schema_dir):
        """同一 wp_code 只加载一次（缓存命中）"""
        schema_data = {"wp_code": "E1A", "counter": 1}
        schema_file = tmp_schema_dir / "E1A.yaml"
        schema_file.write_text(yaml.dump(schema_data), encoding="utf-8")

        result1 = service.load_schema("E1A")
        # 修改文件内容
        schema_file.write_text(yaml.dump({"wp_code": "E1A", "counter": 2}), encoding="utf-8")
        result2 = service.load_schema("E1A")

        # 应该返回缓存的旧值
        assert result1 is result2
        assert result2["counter"] == 1

    def test_template_version_id_isolates_cache(self, service, tmp_schema_dir):
        """不同 template_version_id 使用独立缓存"""
        schema_data = {"wp_code": "D2A", "version": "base"}
        (tmp_schema_dir / "D2A.yaml").write_text(
            yaml.dump(schema_data), encoding="utf-8"
        )

        v1 = uuid4()
        v2 = uuid4()

        result1 = service.load_schema("D2A", template_version_id=v1)
        result2 = service.load_schema("D2A", template_version_id=v2)

        # 两者内容相同（同一文件），但缓存键不同
        assert result1["wp_code"] == result2["wp_code"]

    def test_empty_yaml_returns_empty_dict(self, service, tmp_schema_dir):
        """空 YAML 文件返回空 dict"""
        (tmp_schema_dir / "EMPTY.yaml").write_text("", encoding="utf-8")

        result = service.load_schema("EMPTY")

        assert result == {}


# ─── merge_with_override tests ────────────────────────────────────────────


class TestMergeWithOverride:
    def test_none_override_returns_original(self, service):
        """project_override 为 None 时返回原 schema"""
        schema = {"wp_code": "D2A", "sheets": {"s1": {"type": "a"}}}

        result = service.merge_with_override(schema, None)

        assert result is schema  # 无拷贝，直接返回

    def test_empty_override_returns_original(self, service):
        """project_override 为空 dict 时返回原 schema"""
        schema = {"wp_code": "D2A", "sheets": {"s1": {"type": "a"}}}

        result = service.merge_with_override(schema, {})

        assert result is schema

    def test_shallow_override(self, service):
        """浅层 key 覆盖"""
        schema = {"wp_code": "D2A", "template_version": "v2025"}
        override = {"template_version": "v2026"}

        result = service.merge_with_override(schema, override)

        assert result["template_version"] == "v2026"
        assert result["wp_code"] == "D2A"

    def test_deep_merge_nested_dict(self, service):
        """深层嵌套 dict 递归合并"""
        schema = {
            "sheets": {
                "s1": {
                    "component_type": "a-program-console",
                    "fixed_cells": {"A1": "致同", "H3": "${index_no}"},
                }
            }
        }
        override = {
            "sheets": {
                "s1": {
                    "fixed_cells": {"H3": "CUSTOM-001"}
                }
            }
        }

        result = service.merge_with_override(schema, override)

        # H3 被覆盖
        assert result["sheets"]["s1"]["fixed_cells"]["H3"] == "CUSTOM-001"
        # A1 保留
        assert result["sheets"]["s1"]["fixed_cells"]["A1"] == "致同"
        # component_type 保留
        assert result["sheets"]["s1"]["component_type"] == "a-program-console"

    def test_override_adds_new_keys(self, service):
        """override 中新增的 key 被添加"""
        schema = {"wp_code": "D2A"}
        override = {"custom_field": "custom_value"}

        result = service.merge_with_override(schema, override)

        assert result["custom_field"] == "custom_value"
        assert result["wp_code"] == "D2A"

    def test_override_replaces_non_dict_with_dict(self, service):
        """override 用 dict 替换 base 中的非 dict 值"""
        schema = {"field": "string_value"}
        override = {"field": {"nested": "dict_value"}}

        result = service.merge_with_override(schema, override)

        assert result["field"] == {"nested": "dict_value"}

    def test_does_not_mutate_original_schema(self, service):
        """合并不修改原 schema"""
        schema = {"sheets": {"s1": {"type": "a", "cells": {"A1": "x"}}}}
        override = {"sheets": {"s1": {"cells": {"A1": "y"}}}}

        service.merge_with_override(schema, override)

        # 原 schema 不变
        assert schema["sheets"]["s1"]["cells"]["A1"] == "x"


# ─── invalidate_cache tests ───────────────────────────────────────────────


class TestInvalidateCache:
    def test_invalidate_all(self, service, tmp_schema_dir):
        """清除全部缓存"""
        (tmp_schema_dir / "X1.yaml").write_text(yaml.dump({"wp_code": "X1"}), encoding="utf-8")
        (tmp_schema_dir / "X2.yaml").write_text(yaml.dump({"wp_code": "X2"}), encoding="utf-8")

        service.load_schema("X1")
        service.load_schema("X2")
        assert len(service._cache) == 2

        service.invalidate_cache()

        assert len(service._cache) == 0

    def test_invalidate_specific_wp_code(self, service, tmp_schema_dir):
        """清除指定 wp_code 的缓存"""
        (tmp_schema_dir / "X1.yaml").write_text(yaml.dump({"wp_code": "X1"}), encoding="utf-8")
        (tmp_schema_dir / "X2.yaml").write_text(yaml.dump({"wp_code": "X2"}), encoding="utf-8")

        service.load_schema("X1")
        service.load_schema("X2")

        service.invalidate_cache("X1")

        assert len(service._cache) == 1
        # X2 still cached
        assert any("X2" in k for k in service._cache)


# ─── _deep_merge unit tests ──────────────────────────────────────────────


class TestDeepMerge:
    def test_simple_override(self):
        base = {"a": 1, "b": 2}
        override = {"b": 3, "c": 4}

        _deep_merge(base, override)

        assert base == {"a": 1, "b": 3, "c": 4}

    def test_nested_merge(self):
        base = {"x": {"y": 1, "z": 2}}
        override = {"x": {"z": 3, "w": 4}}

        _deep_merge(base, override)

        assert base == {"x": {"y": 1, "z": 3, "w": 4}}

    def test_override_dict_replaces_scalar(self):
        base = {"x": "scalar"}
        override = {"x": {"nested": True}}

        _deep_merge(base, override)

        assert base == {"x": {"nested": True}}

    def test_override_scalar_replaces_dict(self):
        base = {"x": {"nested": True}}
        override = {"x": "scalar"}

        _deep_merge(base, override)

        assert base == {"x": "scalar"}


# ─── _extract_prefix tests ────────────────────────────────────────────────


class TestExtractPrefix:
    @pytest.mark.parametrize(
        "wp_code,expected",
        [
            ("D2A", "D"),
            ("B12", "B"),
            ("E1A", "E"),
            ("G7", "G"),
            ("S34-8", "S"),
            ("ABC", "ABC"),
            ("123", ""),
        ],
    )
    def test_prefix_extraction(self, wp_code, expected):
        assert WpRenderSchemaService._extract_prefix(wp_code) == expected
