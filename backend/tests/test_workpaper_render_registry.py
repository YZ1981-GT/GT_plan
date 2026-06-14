"""底稿类型注册表 schema 校验测试

验证 workpaper_render_registry.json 结构完整性：
- 顶层字段存在
- 每个 entry 必须有 name/render_type/categories
- render_type 在合法列表内
- upstream/downstream 引用的 wp_code 必须存在于 entries 中
"""

from __future__ import annotations

import pytest

from app.services import workpaper_render_registry_service as registry


VALID_RENDER_TYPES = {
    "html_procedure",
    "html_review",
    "auto_report",
    "univer",
    "word_template",
    "readonly_reference",
    "signing",
}

VALID_CATEGORIES = {"A", "B", "C"}


@pytest.fixture(autouse=True)
def _clear_cache():
    """每个测试前清除缓存确保读最新文件"""
    registry.invalidate_cache()
    yield
    registry.invalidate_cache()


def test_registry_loads_successfully():
    """注册表文件能正常加载"""
    entries = registry.get_all_entries()
    assert len(entries) > 0
    render_types = registry.get_render_types()
    assert set(render_types) == VALID_RENDER_TYPES


def test_all_entries_have_required_fields():
    """每个 entry 必须包含 name/render_type/categories"""
    entries = registry.get_all_entries()
    for code, entry in entries.items():
        assert "name" in entry, f"{code} 缺少 name"
        assert "render_type" in entry, f"{code} 缺少 render_type"
        assert "categories" in entry, f"{code} 缺少 categories"


def test_render_types_are_valid():
    """所有 entry 的 render_type 必须在合法列表内"""
    entries = registry.get_all_entries()
    for code, entry in entries.items():
        assert entry["render_type"] in VALID_RENDER_TYPES, (
            f"{code} render_type={entry['render_type']} 不在合法列表"
        )


def test_categories_are_valid():
    """所有 entry 的 categories 元素必须是 A/B/C"""
    entries = registry.get_all_entries()
    for code, entry in entries.items():
        cats = entry["categories"]
        assert isinstance(cats, list), f"{code} categories 不是列表"
        assert len(cats) > 0, f"{code} categories 为空"
        for c in cats:
            assert c in VALID_CATEGORIES, f"{code} 非法 category: {c}"


def test_upstream_downstream_references_exist():
    """upstream/downstream 引用的 wp_code 必须存在于 entries"""
    entries = registry.get_all_entries()
    all_codes = set(entries.keys())
    for code, entry in entries.items():
        for ref in entry.get("upstream", []):
            assert ref in all_codes, f"{code} upstream 引用不存在的 {ref}"
        for ref in entry.get("downstream", []):
            assert ref in all_codes, f"{code} downstream 引用不存在的 {ref}"


def test_upstream_downstream_bidirectional():
    """如果 A.downstream 含 B，则 B.upstream 应含 A（双向一致）"""
    entries = registry.get_all_entries()
    for code, entry in entries.items():
        for ds in entry.get("downstream", []):
            ds_entry = entries.get(ds)
            if ds_entry:
                assert code in ds_entry.get("upstream", []), (
                    f"{code}.downstream 含 {ds}，但 {ds}.upstream 不含 {code}"
                )


def test_lookup_existing():
    """lookup 已知编码返回条目"""
    entry = registry.lookup("A1")
    assert entry is not None
    assert entry["name"] == "财务报告程序表"


def test_lookup_nonexistent():
    """lookup 不存在编码返回 None"""
    assert registry.lookup("ZZZ-999") is None
