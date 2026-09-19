"""核对表 docx 解析器单元测试.

验证 A1-15 和 A1-16 模板解析输出的结构完整性和数量级正确性。
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from app.services.checklist_docx_parser import (
    _CHECKLIST_TEMPLATE_CACHE,
    get_checklist_template,
    get_template_path,
    invalidate_cache,
    parse_checklist_docx,
)

# ─── 路径常量 ─────────────────────────────────────────────────────────────────
_A15_PATH = Path(
    "backend/wp_templates/A/"
    "A1-15 企业会计准则有关财务报表列报及披露核对表20141021.docx"
)
_A16_PATH = Path(
    "backend/wp_templates/A/"
    "A1-16 上市公司财务报表额外披露要求核对表（A股）201503.docx"
)


# ─── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def a15_result():
    """解析 A1-15 的缓存结果."""
    return parse_checklist_docx(_A15_PATH, "A1-15")


@pytest.fixture
def a16_result():
    """解析 A1-16 的缓存结果."""
    return parse_checklist_docx(_A16_PATH, "A1-16")


# ─── A1-15 Tests ──────────────────────────────────────────────────────────────


class TestA15Parsing:
    """A1-15 企业会计准则有关财务报表列报及披露核对表."""

    def test_sections_count(self, a15_result):
        """A1-15 应解析出 35 个章节."""
        assert a15_result["stats"]["total_sections"] == 35

    def test_actionable_count_range(self, a15_result):
        """A1-15 actionable 条目应在 500~600 范围内."""
        count = a15_result["stats"]["total_actionable"]
        assert 500 <= count <= 600, f"Expected 500-600 actionable, got {count}"

    def test_guidance_count_range(self, a15_result):
        """A1-15 guidance 子项应在 100~200 范围内."""
        count = a15_result["stats"]["total_guidance"]
        assert 100 <= count <= 200, f"Expected 100-200 guidance, got {count}"

    def test_toc_not_empty(self, a15_result):
        """A1-15 应有目录数据."""
        assert len(a15_result["toc"]) > 0

    def test_toc_contains_sections(self, a15_result):
        """TOC 应包含带编号的章节."""
        toc = a15_result["toc"]
        # 应至少有 35 个条目（含分类项）
        assert len(toc) >= 35

    def test_output_structure(self, a15_result):
        """输出结构应包含所有必需字段."""
        assert "wp_code" in a15_result
        assert a15_result["wp_code"] == "A1-15"
        assert "title" in a15_result
        assert "sections" in a15_result
        assert "toc" in a15_result
        assert "stats" in a15_result
        assert "parsed_at" in a15_result

    def test_section_structure(self, a15_result):
        """每个 section 应有 id、title、items."""
        for sec in a15_result["sections"]:
            assert "id" in sec
            assert "title" in sec
            assert "items" in sec
            assert sec["id"].startswith("S")

    def test_actionable_item_structure(self, a15_result):
        """actionable 条目应有完整字段."""
        # 找第一个 actionable
        for sec in a15_result["sections"]:
            for item in sec["items"]:
                if item["type"] == "actionable":
                    assert "id" in item
                    assert "type" in item
                    assert item["type"] == "actionable"
                    assert "standard_ref" in item
                    assert "content" in item
                    assert "children" in item
                    assert item["standard_ref"]  # 非空
                    assert item["content"]  # 非空
                    return
        pytest.fail("未找到任何 actionable 条目")

    def test_guidance_children_structure(self, a15_result):
        """guidance 子项应有 id、content."""
        for sec in a15_result["sections"]:
            for item in sec["items"]:
                if item["type"] == "actionable" and item["children"]:
                    child = item["children"][0]
                    assert "id" in child
                    assert "content" in child
                    assert "standard_ref" in child
                    return
        pytest.fail("未找到任何带 children 的 actionable 条目")

    def test_first_section_title(self, a15_result):
        """第一个章节标题应为 '1.1 财务报表的列报'."""
        first = a15_result["sections"][0]
        assert "1.1" in first["title"]
        assert "财务报表" in first["title"]

    def test_standard_ref_format(self, a15_result):
        """准则索引应以 CAS/IG 等开头."""
        cas_found = False
        for sec in a15_result["sections"]:
            for item in sec["items"]:
                if item["type"] == "actionable" and item["standard_ref"].startswith("CAS"):
                    cas_found = True
                    break
            if cas_found:
                break
        assert cas_found, "未找到 CAS 开头的准则索引"


# ─── A1-16 Tests ──────────────────────────────────────────────────────────────


class TestA16Parsing:
    """A1-16 上市公司财务报表额外披露要求核对表（A股）."""

    def test_sections_count(self, a16_result):
        """A1-16 应解析出至少 10 个章节."""
        count = a16_result["stats"]["total_sections"]
        assert count >= 10, f"Expected >= 10 sections, got {count}"

    def test_actionable_count_range(self, a16_result):
        """A1-16 actionable 条目应在 150~300 范围内."""
        count = a16_result["stats"]["total_actionable"]
        assert 150 <= count <= 300, f"Expected 150-300 actionable, got {count}"

    def test_guidance_count_range(self, a16_result):
        """A1-16 guidance 子项应在 200~400 范围内."""
        count = a16_result["stats"]["total_guidance"]
        assert 200 <= count <= 400, f"Expected 200-400 guidance, got {count}"

    def test_output_structure(self, a16_result):
        """输出结构应包含所有必需字段."""
        assert a16_result["wp_code"] == "A1-16"
        assert "title" in a16_result
        assert "sections" in a16_result
        assert "toc" in a16_result
        assert "stats" in a16_result

    def test_toc_matches_sections(self, a16_result):
        """TOC 应与 sections 一一对应."""
        toc_ids = {t["id"] for t in a16_result["toc"]}
        sec_ids = {s["id"] for s in a16_result["sections"]}
        assert toc_ids == sec_ids

    def test_standard_ref_contains_art(self, a16_result):
        """A1-16 准则索引应包含 Art. 格式."""
        art_found = False
        for sec in a16_result["sections"]:
            for item in sec["items"]:
                if item["type"] == "actionable" and "Art" in item.get("standard_ref", ""):
                    art_found = True
                    break
            if art_found:
                break
        assert art_found, "未找到 Art. 格式的准则索引"

    def test_first_section_content(self, a16_result):
        """第一个章节应为 '1 财务报表'."""
        first = a16_result["sections"][0]
        assert "财务报表" in first["title"]


# ─── 缓存测试 ─────────────────────────────────────────────────────────────────


class TestCaching:
    """mtime 缓存机制测试."""

    def setup_method(self):
        """每个测试前清除缓存."""
        invalidate_cache()

    def test_get_template_path_a15(self):
        """get_template_path 能找到 A1-15 模板."""
        path = get_template_path("A1-15")
        assert path is not None
        assert path.exists()
        assert "A1-15" in path.name

    def test_get_template_path_a16(self):
        """get_template_path 能找到 A1-16 模板."""
        path = get_template_path("A1-16")
        assert path is not None
        assert path.exists()
        assert "A1-16" in path.name

    def test_get_template_path_nonexistent(self):
        """不存在的 wp_code 返回 None."""
        path = get_template_path("A99-99")
        assert path is None

    def test_cache_populated_after_get(self):
        """调用 get_checklist_template 后缓存应被填充."""
        result = asyncio.run(get_checklist_template("A1-15"))
        assert "A1-15" in _CHECKLIST_TEMPLATE_CACHE
        assert result["wp_code"] == "A1-15"

    def test_cache_returns_same_object(self):
        """重复调用应返回缓存的同一对象."""
        r1 = asyncio.run(get_checklist_template("A1-15"))
        r2 = asyncio.run(get_checklist_template("A1-15"))
        assert r1 is r2  # 同一引用 → 证明走了缓存

    def test_invalidate_cache_single(self):
        """invalidate_cache(wp_code) 应只清除指定条目."""
        asyncio.run(get_checklist_template("A1-15"))
        assert "A1-15" in _CHECKLIST_TEMPLATE_CACHE
        invalidate_cache("A1-15")
        assert "A1-15" not in _CHECKLIST_TEMPLATE_CACHE

    def test_invalidate_cache_all(self):
        """invalidate_cache() 应清除所有缓存."""
        asyncio.run(get_checklist_template("A1-15"))
        invalidate_cache()
        assert len(_CHECKLIST_TEMPLATE_CACHE) == 0

    def test_get_template_nonexistent_raises(self):
        """不存在的 wp_code 应抛 FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            asyncio.run(get_checklist_template("A99-99"))


# ─── 边界和错误处理 ───────────────────────────────────────────────────────────


class TestEdgeCases:
    """边界情况测试."""

    def test_unsupported_wp_code_raises(self):
        """不支持的 wp_code 应抛 ValueError."""
        with pytest.raises(ValueError, match="不支持"):
            parse_checklist_docx(_A15_PATH, "A99")

    def test_all_items_have_unique_ids(self, a15_result):
        """所有条目 ID 应唯一."""
        all_ids = set()
        for sec in a15_result["sections"]:
            assert sec["id"] not in all_ids
            all_ids.add(sec["id"])
            for item in sec["items"]:
                assert item["id"] not in all_ids, f"Duplicate ID: {item['id']}"
                all_ids.add(item["id"])

    def test_stats_consistent_with_data(self, a15_result):
        """stats 中的数字应与实际 items 一致."""
        actual_actionable = 0
        actual_guidance = 0
        for sec in a15_result["sections"]:
            for item in sec["items"]:
                if item["type"] == "actionable":
                    actual_actionable += 1
                    actual_guidance += len(item.get("children", []))
        assert actual_actionable == a15_result["stats"]["total_actionable"]
        assert actual_guidance == a15_result["stats"]["total_guidance"]
        assert len(a15_result["sections"]) == a15_result["stats"]["total_sections"]
