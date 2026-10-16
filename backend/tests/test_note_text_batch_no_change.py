"""批量写入「写入后内容不变」不算一次写入（第 26 组）。

现象（Task 55 真实写入验收登记）：v1 的「八、9」before = after，仍写了应用记录并置 ``is_local_override``。
写入还会把章节状态重置为 draft、发 ``NOTE_SECTION_SAVED`` —— 内容没变，复核状态、底稿推送保护与留痕却都变了。

判据：
- 预览：拟写入内容与现有内容按编辑器口径（``note_text_to_html``）相同 ⇒ unavailable「与现有内容相同，无需写入」，
  不默认勾选。比较在变量替换之后（替换后才是要写入的内容），且按规范化后的 HTML（纯文字存储与同内容 HTML 视为相同）；
- 写入：选了这种章节 ⇒ 422 零写入（正文、状态、本地改写标记、更新时间、应用记录、事件都不动）；
- 追加：来源段落已全部在现有正文中 ⇒ 追加结果与现有内容相同 ⇒ 422 ``SELECTION_NO_CHANGE``；同一章改选「替换」照常写入。
"""
from __future__ import annotations

import pytest

import tests.test_note_text_batch_endpoints as _batch
from app.models.report_models import DisclosureNote, NoteStatus
from tests.test_note_text_batch_endpoints import (
    TPL_HASH, _applications, _apply, _assert_error, _item, _note, _preview, _previewed, _selection,
    _upload_source,
)

env = _batch.env  # fixture 需在本模块命名空间（pytest 按属性名注册）：批量写入端点的 SQLite 环境

#: 上传来源 TREE_DOC「公司基本情况」的拟写入内容（见 test_note_text_batch_endpoints 的写入用例）
UPLOADED = "<p>本公司成立于2001年。</p>"
SAME = "与现有内容相同，无需写入"


async def _set_basic(env: dict, text: str, status: NoteStatus = NoteStatus.confirmed) -> None:
    async with env["factory"]() as db:
        note = await db.get(DisclosureNote, env["ids"]["basic"])
        note.text_content, note.status = text, status
        await db.commit()


def _assert_unavailable_same(preview: dict, item: dict) -> None:
    assert (item["category"], item["unavailable_reason"], item["default_selected"]) == ("unavailable", SAME, False)
    assert item["target_note_section"] == "一、1", "目标仍要显示：用户据此知道是哪一章没必要写"
    assert preview["summary"]["replace"] == 0 and preview["summary"]["unavailable"] >= 1


@pytest.mark.asyncio
async def test_identical_html_is_unavailable_in_preview(env):
    await _set_basic(env, UPLOADED)
    _source, preview, item = await _previewed(env)
    _assert_unavailable_same(preview, item)


@pytest.mark.asyncio
async def test_identical_plain_text_storage_is_unavailable(env):
    """生成链写入的纯文字与来源同内容：编辑器与 Word 都按同一口径显示，写入只会改存储形态。"""
    await _set_basic(env, "本公司成立于2001年。")
    _source, preview, item = await _previewed(env)
    _assert_unavailable_same(preview, item)


@pytest.mark.asyncio
async def test_identical_after_variable_replacement_is_unavailable(env):
    """模板正文「乙公司…」替换后是「甲公司…」：替换后与现有内容相同才算相同（替换前不同）。"""
    await _set_basic(env, "<p>甲公司成立于2001年。</p>")
    source = {"source_kind": "content_template", "template_version_id": str(env["ids"]["ver"]),
              "template_content_hash": TPL_HASH}
    resp = await _preview(env, source)
    assert resp.status_code == 200, resp.text
    preview = resp.json()
    item = next(i for i in preview["items"] if i["target_note_section"] == "一、1")
    assert item["replacements"], "夹具没有触发变量替换，判据空转"
    _assert_unavailable_same(preview, item)


@pytest.mark.asyncio
async def test_different_content_still_needs_review_not_unavailable(env):
    """对照：现有内容不同照常可写（需复核），说明上面的不可用来自「相同」而不是别的条件。"""
    await _set_basic(env, "<p>本公司成立于1999年。</p>")
    _source, _preview_body, item = await _previewed(env)
    assert (item["category"], item["unavailable_reason"]) == ("review", None)


@pytest.mark.asyncio
async def test_apply_identical_selection_is_rejected_with_zero_side_effects(env):
    await _set_basic(env, UPLOADED)
    before = await _note(env, "basic")
    source, preview, item = await _previewed(env)
    resp = await _apply(env, source, preview, [_selection(item)])
    _assert_error(resp, 422, "SELECTION_UNAVAILABLE")
    after = await _note(env, "basic")
    assert (after.text_content, after.status, after.is_local_override, after.updated_at, after.updated_by) == (
        UPLOADED, NoteStatus.confirmed, False, before.updated_at, before.updated_by)
    assert await _applications(env) == [] and env["published"] == []


@pytest.mark.asyncio
async def test_append_adding_nothing_is_rejected_but_replace_writes(env):
    """现有正文已含来源全部段落：追加结果 = 现有内容（零写入 422）；改选替换才是真改动（去掉「前文」）。"""
    existing = "<p>前文</p>" + UPLOADED
    await _set_basic(env, existing)
    source, preview, item = await _previewed(env)
    assert item["category"] == "review"
    assert item["append_html"] == item["before_html"] == existing, "夹具没有构造出「追加不增加内容」"

    resp = await _apply(env, source, preview, [_selection(item, "append")])
    detail = _assert_error(resp, 422, "SELECTION_NO_CHANGE")
    assert "一、1" in detail["message"]
    note = await _note(env, "basic")
    assert (note.text_content, note.status, note.is_local_override) == (existing, NoteStatus.confirmed, False)
    assert await _applications(env) == [] and env["published"] == []

    resp = await _apply(env, source, preview, [_selection(item)], mutation_id="mut-replace-1")
    assert resp.status_code == 200, resp.text
    note = await _note(env, "basic")
    assert (note.text_content, note.status, note.is_local_override) == (UPLOADED, NoteStatus.draft, True)


@pytest.mark.asyncio
async def test_rejected_batch_writes_nothing_for_other_selected_chapters(env):
    """批内一章内容相同 ⇒ 整批零写入（原子，AC-4.3）：同批另一章也不写。"""
    await _set_basic(env, UPLOADED)
    source = await _upload_source(env)
    preview = (await _preview(env, source)).json()
    same, period = _item(preview, "公司基本情况"), _item(preview, "会计期间")
    assert period["category"] != "unavailable", period
    resp = await _apply(env, source, preview, [_selection(same), _selection(period)])
    _assert_error(resp, 422, "SELECTION_UNAVAILABLE")
    assert (await _note(env, "period")).text_content in (None, "")
    assert await _applications(env) == []
