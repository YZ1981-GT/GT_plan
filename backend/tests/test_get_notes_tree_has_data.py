"""get_notes_tree 的 has_data 字段契约测试（spec: disclosure-notes-selective-generation）。

覆盖 Property 6（has_data 值与 note_has_data 一致）、Property 10/12（前缀原样 + 现有字段保持）。
用 mock session 避免真实 DB 依赖。
"""
import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

from app.services.disclosure_engine import DisclosureEngine
from app.services.note_content_utils import note_has_data


def _enum(v):
    return SimpleNamespace(value=v)


def _note(note_section, **kw):
    kw.setdefault("id", uuid4())
    kw.setdefault("section_title", "标题")
    kw.setdefault("account_name", None)
    kw.setdefault("content_type", None)
    kw.setdefault("status", None)
    kw.setdefault("sort_order", 0)
    kw.setdefault("is_empty", False)
    kw.setdefault("text_content", None)
    kw.setdefault("table_data", None)
    return SimpleNamespace(note_section=note_section, **kw)


def _run_tree(notes):
    fake_result = MagicMock()
    fake_result.scalars.return_value.all.return_value = notes

    async def _execute(*_a, **_k):
        return fake_result

    fake_db = SimpleNamespace(execute=_execute)
    eng = DisclosureEngine.__new__(DisclosureEngine)
    eng.db = fake_db
    return asyncio.run(eng.get_notes_tree(uuid4(), 2025))


def test_each_node_has_has_data_field_and_preserves_existing():
    notes = [
        _note("五、1", text_content="有数据", content_type=_enum("workpaper"), status=_enum("draft")),
        _note("五、2", table_data={"rows": [{"values": [0]}]}),  # 无数据
        _note("三、7", is_empty=True, text_content="x"),  # not_applicable → False
        _note("五、3", table_data={"rows": [{"values": [999]}]}),  # 有数据
    ]
    tree = _run_tree(notes)
    assert len(tree) == 4
    for node, src in zip(tree, notes):
        # Property 12：现有字段保持
        assert node["note_section"] == src.note_section
        assert node["section_title"] == src.section_title
        assert "id" in node and "sort_order" in node and "account_name" in node
        assert "content_type" in node and "status" in node
        # Property 6：has_data 与共享 helper 一致
        assert node["has_data"] == note_has_data(src)


def test_has_data_values_match_expectation():
    notes = [
        _note("五、1", text_content="有数据"),
        _note("五、2", table_data={"rows": [{"values": ["-", 0, ""]}]}),
        _note("三、9", is_empty=True, table_data={"rows": [{"values": [100]}]}),
    ]
    tree = _run_tree(notes)
    assert tree[0]["has_data"] is True
    assert tree[1]["has_data"] is False
    assert tree[2]["has_data"] is False  # is_empty 短路


def test_prefixes_passed_through_verbatim():
    # Property 10：前缀（三、/五、）原样返回，不改写
    notes = [_note("三、7"), _note("五、22")]
    tree = _run_tree(notes)
    assert [n["note_section"] for n in tree] == ["三、7", "五、22"]
