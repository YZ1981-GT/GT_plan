"""附注正文批量写入：目标章节类型按真库形态判定（AC-2.3「纯父节点 = container」）。

第 17 组真实写入验收（测试项目甲）：新生成附注的章行「一 公司基本情况」「二 财务报表编制基础」是空正文纯父节点，
却进了上传可填范围 ⇒ 与同名子节「一、1」「二、1」成了两个目标，预览报「存在 2 个同名目标章节，需人工选择」。两处根因：

1. ``table_data`` 是未设 ``none_as_null`` 的 JSONB，生成链写 ``None`` 存成 JSON ``null``；章节读取用 ``IS NOT NULL``
   判「有表」⇒ 恒真、container 永不成立。既有夹具从不写该列（SQL NULL）⇒ 假绿；
2. 分类器先按 Word 标题返回 narrative，叙述章标题的纯父节点（「二 财务报表编制基础」）走不到容器判定。

本文件夹具按真库形态**显式**写 ``table_data=None``，并先断言存储形态确实是 JSON null（对照不成立则后续断言空转）。
从 ``test_note_text_batch_endpoints.py`` 拆出（该文件近行数门禁 800），复用同一套端点夹具与请求 helper。
"""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa

from app.models.report_models import DisclosureNote
from tests import test_note_text_batch_endpoints as _endpoints
from tests.test_note_text_batch_endpoints import YEAR, _docx, _item, _parse, _preview, _url

#: 复用端点测试的夹具（pytest 按名注入）
env = _endpoints.env


async def _add_generated_chapter_rows(env: dict) -> dict[str, uuid.UUID]:
    """按真库生成形态补章行：章行空正文、``table_data`` 显式 None（JSON null）；夹具里的「一、1」挂到章行下。"""
    ids = {key: uuid.uuid4() for key in ("ch1", "ch2", "basis", "table_parent", "table_child", "empty_obj",
                                          "empty_obj_child")}
    pid = env["ids"]["p"]

    def note(key: str, code: str, title: str, **kw) -> DisclosureNote:
        kw.setdefault("table_data", None)  # 显式赋 None ⇒ 存 JSON null（与生成链一致）
        return DisclosureNote(id=ids[key], project_id=pid, year=YEAR, note_section=code, section_title=title, **kw)

    async with env["factory"]() as db:
        db.add_all([
            note("ch1", "一", "公司基本情况", section_id="ch-01", level=1, text_content="", sort_order=1),
            note("ch2", "二", "财务报表编制基础", section_id="ch-02", level=1, text_content="", sort_order=3),
            note("basis", "二、1", "财务报表编制基础", section_id="ch-02-1", parent_section_id="ch-02", level=2,
                 text_content="<p>以持续经营为基础</p>", sort_order=4),
            # 正文只有表格的父节点：表格就是正文载荷，不是容器
            note("table_parent", "四、表格父节", "表格父节", section_id="tp", level=2, text_content="",
                 table_data={"rows": [{"label": "合计", "values": [1]}]}, sort_order=5),
            note("table_child", "四、表格父节、1", "表格子节", parent_section_id="tp", level=3,
                 text_content="<p>子节</p>", sort_order=6),
            # 空对象不出表（与 Word 导出同口径）：仍是容器
            note("empty_obj", "四、空表父节", "空表父节", section_id="eo", level=2, text_content="",
                 table_data={}, sort_order=7),
            note("empty_obj_child", "四、空表父节、1", "空表子节", parent_section_id="eo", level=3,
                 text_content="<p>子节</p>", sort_order=8),
        ])
        basic = await db.get(DisclosureNote, env["ids"]["basic"])
        basic.section_id, basic.parent_section_id, basic.sort_order = "ch-01-1", "ch-01", 2
        await db.commit()
    return ids


async def _kinds(env: dict, scope: str) -> dict[str, str]:
    resp = await env["client"].get(_url(env, "/disclosure-note-text-sections"), params={"year": YEAR, "scope": scope})
    assert resp.status_code == 200, resp.text
    return {i["note_section"]: i["section_kind"] for i in resp.json()["items"]}


class TestGeneratedChapterRows:
    @pytest.mark.asyncio
    async def test_fixture_stores_json_null_like_real_db(self, env):
        """对照：夹具确实复现真库形态（JSON null 而非 SQL NULL），否则下面的断言测不到 ``IS NOT NULL`` 缺陷。"""
        ids = await _add_generated_chapter_rows(env)
        async with env["factory"]() as db:
            is_sql_null, as_text = (await db.execute(
                sa.select(DisclosureNote.table_data.is_(None), sa.cast(DisclosureNote.table_data, sa.Text))
                .where(DisclosureNote.id == ids["ch1"]))).one()
        assert (bool(is_sql_null), as_text) == (False, "null")

    @pytest.mark.asyncio
    async def test_empty_chapter_rows_are_containers(self, env):
        await _add_generated_chapter_rows(env)
        narrative, every = await _kinds(env, "narrative"), await _kinds(env, "all")
        assert {"一", "二"}.isdisjoint(narrative), "空正文章行进了叙述可填范围"
        assert {"一、1", "二、1"} <= set(narrative)
        assert every["一"] == every["二"] == "container"
        assert every["四、空表父节"] == "container", "空对象 table_data 被当成表格正文"
        assert every["四、表格父节"] == "narrative", "只有表格的父节点被误判为容器"

    @pytest.mark.asyncio
    async def test_template_snapshot_labels_containers_like_target_reading(self, env):
        """同一章节在内容模板快照里与目标侧章节读取类型一致（模板快照 scope=all，design §4.1）。"""
        from app.services.note_content_template_snapshot import generate_snapshot

        await _add_generated_chapter_rows(env)
        async with env["factory"]() as db:
            snapshot = await generate_snapshot(db, env["ids"]["p"], YEAR)
        in_template = {s["note_section"]: s["section_kind"] for s in snapshot["sections_data"]}
        assert in_template == await _kinds(env, "all")
        assert in_template["一"] == in_template["二"] == "container"

    @pytest.mark.asyncio
    async def test_upload_preview_targets_the_child_uniquely(self, env):
        """用户可见症状：上传「公司基本情况」「财务报表编制基础」不再因章行同名而只能人工选。"""
        ids = await _add_generated_chapter_rows(env)
        parsed = await _parse(env, _docx(("公司基本情况", "本公司成立于2001年。"), ("财务报表编制基础", "以持续经营为基础编制。")))
        assert parsed.status_code == 200, parsed.text
        preview = await _preview(env, {"source_kind": "upload", "parsed_source": parsed.json()})
        assert preview.status_code == 200, preview.text
        for title, key in (("公司基本情况", None), ("财务报表编制基础", "basis")):
            item = _item(preview.json(), title)
            expected = str(env["ids"]["basic"] if key is None else ids[key])
            assert item["target_note_id"] == expected, (item["match_kind"], item["evidence"])
            assert item["category"] != "unavailable", item
