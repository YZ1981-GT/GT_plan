"""Unit tests for A1-12 checklist DOCX parser (A112ChecklistData format)."""

import os
import tempfile
from pathlib import Path

import pytest

from app.services.a112_checklist_parser import (
    _empty_result,
    _extract_categories,
    _extract_header,
    _extract_signatures,
    format_to_docx,
    parse_a112_checklist,
)

# ─── 实际模板路径 ────────────────────────────────────────────────────────────

_TEMPLATE = Path(__file__).resolve().parent.parent / "wp_templates" / "A" / "A1-12 重大事项决定程序的履行情况核查表1105.docx"


class TestParseA112Checklist:
    """测试 parse_a112_checklist 主函数."""

    def test_parse_real_template(self):
        """解析真实模板，验证输出结构完整性."""
        result = parse_a112_checklist(str(_TEMPLATE))

        # 顶层结构
        assert "header" in result
        assert "categories" in result
        assert "signatures" in result

    def test_exactly_2_categories(self):
        """Property 7a: 恰好 2 个 categories."""
        result = parse_a112_checklist(str(_TEMPLATE))
        assert len(result["categories"]) == 2

    def test_category_1_has_14_items(self):
        """Property 7b: 第一类有 14 项固定条目."""
        result = parse_a112_checklist(str(_TEMPLATE))
        cat1 = result["categories"][0]
        assert len(cat1["items"]) == 14

    def test_category_1_not_allow_custom(self):
        """第一类 allow_custom=False."""
        result = parse_a112_checklist(str(_TEMPLATE))
        assert result["categories"][0]["allow_custom"] is False

    def test_category_2_allow_custom(self):
        """第二类 allow_custom=True."""
        result = parse_a112_checklist(str(_TEMPLATE))
        assert result["categories"][1]["allow_custom"] is True

    def test_unique_item_ids(self):
        """Property 7c: 所有 item ID 唯一."""
        result = parse_a112_checklist(str(_TEMPLATE))
        all_ids = [item["id"] for cat in result["categories"] for item in cat["items"]]
        assert len(all_ids) == len(set(all_ids))

    def test_items_have_nonempty_description(self):
        """Property 7d: 所有 item 有非空 description."""
        result = parse_a112_checklist(str(_TEMPLATE))
        for cat in result["categories"]:
            for item in cat["items"]:
                assert item["description"].strip(), f"{item['id']} has empty description"

    def test_item_structure(self):
        """每个 item 有 id/seq/description/category_tag 字段."""
        result = parse_a112_checklist(str(_TEMPLATE))
        item1 = result["categories"][0]["items"][0]
        assert item1["id"] == "item-1"
        assert item1["seq"] == 1
        assert "首次承接" in item1["description"]
        assert item1["category_tag"] == "A1"

    def test_category_ids(self):
        """category ID 格式正确."""
        result = parse_a112_checklist(str(_TEMPLATE))
        assert result["categories"][0]["id"] == "cat-1"
        assert result["categories"][1]["id"] == "cat-2"

    def test_category_titles(self):
        """category title 包含预期内容."""
        result = parse_a112_checklist(str(_TEMPLATE))
        assert "一、" in result["categories"][0]["title"]
        assert "二、" in result["categories"][1]["title"]
        assert "专业技术委员会" in result["categories"][0]["title"]

    def test_signatures_4_roles(self):
        """签字区提取 4 个标准角色."""
        result = parse_a112_checklist(str(_TEMPLATE))
        assert len(result["signatures"]) == 4
        roles = [s["role"] for s in result["signatures"]]
        assert "项目负责经理" in roles
        assert "项目合伙人" in roles
        assert "质量复核合伙人" in roles
        assert "质量控制复核人" in roles

    def test_signatures_name_date_none(self):
        """模板中签字区 name/date 均为 None."""
        result = parse_a112_checklist(str(_TEMPLATE))
        for sig in result["signatures"]:
            assert sig["name"] is None
            assert sig["date"] is None

    def test_header_template_empty(self):
        """模板中头部字段均为 None（未填写）."""
        result = parse_a112_checklist(str(_TEMPLATE))
        h = result["header"]
        assert h["entity_name"] is None
        assert h["period_end"] is None
        assert h["business_class"] is None
        assert h["is_first_engagement"] is None

    def test_category_tag_extraction(self):
        """从描述中正确提取 category_tag."""
        result = parse_a112_checklist(str(_TEMPLATE))
        items = result["categories"][0]["items"]
        # item-1: (A1) → A1
        assert items[0]["category_tag"] == "A1"
        # item-7: (A7，包括...) → A7
        assert items[6]["category_tag"] == "A7"
        # item-9: 无 tag
        assert items[8]["category_tag"] is None


class TestErrorHandling:
    """测试异常降级."""

    def test_nonexistent_file(self):
        """不存在的文件返回空结构，不崩溃."""
        result = parse_a112_checklist("/nonexistent/path.docx")
        assert result["categories"] == []
        assert len(result["signatures"]) == 4
        assert result["header"]["entity_name"] is None

    def test_none_path_uses_default(self):
        """None 路径使用默认模板."""
        result = parse_a112_checklist(None)
        # 如果默认模板存在，应正常解析
        if _TEMPLATE.exists():
            assert len(result["categories"]) == 2

    def test_empty_result_structure(self):
        """_empty_result 返回完整结构."""
        result = _empty_result()
        assert "header" in result
        assert "categories" in result
        assert "signatures" in result
        assert result["categories"] == []
        assert len(result["signatures"]) == 4


class TestFormatToDocx:
    """测试 format_to_docx round-trip."""

    def test_roundtrip_real_template(self):
        """Property 8: parse → format_to_docx → re-parse 产生等价数据."""
        original = parse_a112_checklist(str(_TEMPLATE))
        buf = format_to_docx(original)

        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as f:
            f.write(buf.read())
            tmp_path = f.name

        try:
            reparsed = parse_a112_checklist(tmp_path)
        finally:
            os.unlink(tmp_path)

        # Same category count
        assert len(reparsed["categories"]) == len(original["categories"])

        # Each category: same title, same items
        for ci, (oc, rc) in enumerate(zip(original["categories"], reparsed["categories"])):
            assert rc["title"] == oc["title"]
            assert len(rc["items"]) == len(oc["items"])
            for ii, (oi, ri) in enumerate(zip(oc["items"], rc["items"])):
                assert ri["description"] == oi["description"]
                assert ri["category_tag"] == oi["category_tag"]

        # Signatures: same roles
        assert len(reparsed["signatures"]) == len(original["signatures"])
        for os_, rs_ in zip(original["signatures"], reparsed["signatures"]):
            assert rs_["role"] == os_["role"]

    def test_format_returns_bytesio(self):
        """format_to_docx 返回 BytesIO 对象."""
        import io

        data = _empty_result()
        data["categories"] = [
            {"id": "cat-1", "title": "一、测试类别", "items": [
                {"id": "item-1", "seq": 1, "description": "测试条目(A1)", "category_tag": "A1"},
            ], "allow_custom": False},
        ]
        buf = format_to_docx(data)
        assert isinstance(buf, io.BytesIO)
        # 验证是有效 DOCX（PK 开头）
        assert buf.read(2) == b"PK"

    def test_roundtrip_with_header_values(self):
        """Round-trip 保留 header 中的 entity_name 和 period_end."""
        data = {
            "header": {
                "entity_name": "测试公司",
                "period_end": "2025年12月31日",
                "business_class": None,
                "is_first_engagement": None,
            },
            "categories": [
                {"id": "cat-1", "title": "一、核查事项", "items": [
                    {"id": "item-1", "seq": 1, "description": "首次承接(A1)", "category_tag": "A1"},
                ], "allow_custom": False},
            ],
            "signatures": [
                {"role": "项目负责经理", "name": None, "date": None},
                {"role": "项目合伙人", "name": None, "date": None},
                {"role": "质量复核合伙人", "name": None, "date": None},
                {"role": "质量控制复核人", "name": None, "date": None},
            ],
        }
        buf = format_to_docx(data)

        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as f:
            f.write(buf.read())
            tmp_path = f.name

        try:
            reparsed = parse_a112_checklist(tmp_path)
        finally:
            os.unlink(tmp_path)

        assert reparsed["header"]["entity_name"] == "测试公司"
        assert reparsed["header"]["period_end"] == "2025年12月31日"

    def test_roundtrip_preserves_category_structure(self):
        """Round-trip 保留 category 结构（title + items + tags）."""
        data = {
            "header": {"entity_name": None, "period_end": None, "business_class": None, "is_first_engagement": None},
            "categories": [
                {"id": "cat-1", "title": "一、第一类事项", "items": [
                    {"id": "item-1", "seq": 1, "description": "条目一(A1)", "category_tag": "A1"},
                    {"id": "item-2", "seq": 2, "description": "条目二无标签", "category_tag": None},
                ], "allow_custom": False},
                {"id": "cat-2", "title": "二、第二类事项", "items": [
                    {"id": "item-3", "seq": 3, "description": "自定义条目(B1)", "category_tag": "B1"},
                ], "allow_custom": True},
            ],
            "signatures": [
                {"role": "项目负责经理", "name": None, "date": None},
                {"role": "项目合伙人", "name": None, "date": None},
                {"role": "质量复核合伙人", "name": None, "date": None},
                {"role": "质量控制复核人", "name": None, "date": None},
            ],
        }
        buf = format_to_docx(data)

        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as f:
            f.write(buf.read())
            tmp_path = f.name

        try:
            reparsed = parse_a112_checklist(tmp_path)
        finally:
            os.unlink(tmp_path)

        assert len(reparsed["categories"]) == 2
        assert reparsed["categories"][0]["title"] == "一、第一类事项"
        assert reparsed["categories"][1]["title"] == "二、第二类事项"
        assert len(reparsed["categories"][0]["items"]) == 2
        assert reparsed["categories"][0]["items"][0]["category_tag"] == "A1"
        assert reparsed["categories"][0]["items"][1]["category_tag"] is None
        assert reparsed["categories"][1]["items"][0]["category_tag"] == "B1"
