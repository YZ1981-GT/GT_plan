"""附注叙述段 `_note_texts` **按 section 浅合并**守卫。

原实现是「整列表替换 + 没推就置 `None`」→ 多循环共用同一附注章节时
（实证 G2/G3/K1 共用 `五、8`/`八、9`，三方都开了自动同步），
**K1 录的 10 段说明会被 G2 的一段整体覆盖**；附注模块 AI 填充的正文同样会被清掉。

**Validates: Requirements 5.1~5.5, 6.2 / Properties 11, 12**

清空仍然可达，但必须**显式**：推 `_note_texts: []`（或全空文本）或
`_removed_text_sections: [...]`。"「没推」与「推了空」是两回事」是本 spec 的核心区分。

反向自检两条：
1. 若合并退化为整替换 → Property 11「未推送 section 保留」必红
2. 无键段（`[{text}]`，F4 范式）若按「保留 + 追加」处理 → 反复同步必膨胀
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.report_models import DisclosureNote
from app.services.wp_disclosure_sync_service import (
    REMOVED_TEXT_SECTIONS_KEY,
    _extract_removed_text_sections,
    _format_note_texts,
    _merge_note_texts,
    sync_from_workpaper,
)

PROJECT_ID = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
WP_ID = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
USER_ID = uuid.UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")

#: 真实多 owner 场景：G2/G3/K1 共用 soe `八、9`（新准则应收利息/应收股利并入其他应收款）
K1_TEXTS = [
    {"section": "k1-aging", "title": "账龄分析说明", "text": "1 年以内占比 92%。"},
    {"section": "k1-top5", "title": "前五名说明", "text": "前五名合计 6,800 万元。"},
]
G2_TEXTS = [{"section": "g2-audit-note", "title": "应收利息说明", "text": "本期无应收利息。"}]


def _keys(items: list[dict]) -> list[str]:
    return [str(i.get("section") or i.get("title") or "") for i in items]


# ─────────────────────────────────────────────────────────────────────────────
# `_extract_removed_text_sections`
# ─────────────────────────────────────────────────────────────────────────────


class TestExtractRemovedTextSections:
    def test_extracts_and_dedups(self):
        data, keys = _extract_removed_text_sections(
            {"表": [], REMOVED_TEXT_SECTIONS_KEY: ["a", "a", " b ", "", None]}
        )
        assert keys == ["a", "b"]
        assert REMOVED_TEXT_SECTIONS_KEY not in data
        assert set(data) == {"表"}

    @pytest.mark.parametrize("raw", ["a", 1, {"a": 1}, None])
    def test_illegal_forms_yield_empty(self, raw):
        _data, keys = _extract_removed_text_sections({REMOVED_TEXT_SECTIONS_KEY: raw})
        assert keys == []


# ─────────────────────────────────────────────────────────────────────────────
# Property 11 / 12：纯函数语义
# ─────────────────────────────────────────────────────────────────────────────


class TestMergeNoteTexts:
    def test_property11_keyset_union_minus_removed(self):
        merged = _merge_note_texts(K1_TEXTS, G2_TEXTS)
        assert _keys(merged) == ["k1-aging", "k1-top5", "g2-audit-note"], (
            "既有顺序在前、新 section 追加在后（text_content 重排不跳动）"
        )

    def test_property11_same_section_overridden_in_place(self):
        incoming = [{"section": "k1-top5", "title": "前五名说明", "text": "改口径后 7,100 万元。"}]
        merged = _merge_note_texts(K1_TEXTS, incoming)
        assert _keys(merged) == ["k1-aging", "k1-top5"], "原位替换，不挪到末尾"
        assert merged[1]["text"] == "改口径后 7,100 万元。"
        assert merged[0] == K1_TEXTS[0], "未推送的段逐字段不变"

    def test_property11_removed_sections_dropped(self):
        merged = _merge_note_texts(
            K1_TEXTS + G2_TEXTS, G2_TEXTS, removed_sections=["k1-aging"]
        )
        assert _keys(merged) == ["k1-top5", "g2-audit-note"]

    def test_property11_push_beats_removal(self):
        """推送优先：本次推了就不删（同 `_drop_removed_tables` 既有语义）。"""
        merged = _merge_note_texts(
            K1_TEXTS, [{"section": "k1-aging", "text": "新说明"}], removed_sections=["k1-aging"]
        )
        assert _keys(merged) == ["k1-aging", "k1-top5"]
        assert merged[0]["text"] == "新说明"

    def test_property12_single_owner_merge_equals_replace(self):
        """🔴 零回归论证：既有键集 ⊆ 推送键集 → 合并结果 ≡ 整替换。"""
        updated = [{**t, "text": t["text"] + "（更新）"} for t in K1_TEXTS]
        assert _merge_note_texts(K1_TEXTS, updated) == updated

    def test_property12_no_incoming_keeps_existing(self):
        assert _merge_note_texts(K1_TEXTS, []) == K1_TEXTS
        assert _merge_note_texts(K1_TEXTS, None) == K1_TEXTS

    def test_no_existing_returns_incoming(self):
        assert _merge_note_texts(None, G2_TEXTS) == G2_TEXTS
        assert _merge_note_texts([], []) == []

    def test_title_fallback_key(self):
        """无 `section` 时用 `title` 作合并键（存量有这种形态）。"""
        exist = [{"title": "补充披露", "text": "旧"}]
        merged = _merge_note_texts(exist, [{"title": "补充披露", "text": "新"}])
        assert merged == [{"title": "补充披露", "text": "新"}]

    def test_keyless_sections_do_not_accumulate(self):
        """🔴 无键段（`[{text}]`，F4 范式）反复同步不得膨胀。

        若按「无键段一律保留 + 追加」实现，同步 N 次就有 N 条 → 附注正文无限膨胀。
        位置化占位键让第 n 条无键段被第 n 条无键推送替换。
        """
        state = [{"text": "第 1 版"}]
        for i in range(2, 6):
            state = _merge_note_texts(state, [{"text": f"第 {i} 版"}])
            assert len(state) == 1, f"第 {i} 轮膨胀到 {len(state)} 条"
        assert state == [{"text": "第 5 版"}]

    def test_non_mapping_items_ignored(self):
        merged = _merge_note_texts(["x", None, {"section": "a", "text": "1"}], [42])
        assert merged == [{"section": "a", "text": "1"}]

    def test_returns_copies_not_aliases(self):
        merged = _merge_note_texts(K1_TEXTS, G2_TEXTS)
        merged[0]["text"] = "改了"
        assert K1_TEXTS[0]["text"] == "1 年以内占比 92%。", "不得原地改调用方数据"

    def test_reverse_check_replace_would_lose_unpushed(self):
        """🔴 反向自检：整替换（旧实现）确实会丢掉未推送的 section。"""
        replaced = list(G2_TEXTS)  # 旧实现：note_texts = incoming
        assert _keys(replaced) == ["g2-audit-note"]
        assert "k1-aging" not in _keys(replaced)
        # 合并实现必须保住它
        assert "k1-aging" in _keys(_merge_note_texts(K1_TEXTS, G2_TEXTS))


class TestMergeNoteTextsPBT:
    """PBT：键集恒等式 + 未推送段不变。"""

    _SECTIONS = st.sampled_from(["a", "b", "c", "d"])

    @settings(max_examples=40, deadline=None)
    @given(
        exist_keys=st.lists(_SECTIONS, max_size=4, unique=True),
        inc_keys=st.lists(_SECTIONS, max_size=4, unique=True),
        removed=st.lists(_SECTIONS, max_size=2, unique=True),
    )
    def test_keyset_identity(self, exist_keys, inc_keys, removed):
        exist = [{"section": k, "text": f"old-{k}"} for k in exist_keys]
        inc = [{"section": k, "text": f"new-{k}"} for k in inc_keys]
        merged = _merge_note_texts(exist, inc, removed)
        expected = (set(exist_keys) | set(inc_keys)) - (set(removed) - set(inc_keys))
        assert set(_keys(merged)) == expected
        assert len(merged) == len(expected), "无重复段"
        by_key = {m["section"]: m for m in merged}
        for k in expected:
            want = f"new-{k}" if k in inc_keys else f"old-{k}"
            assert by_key[k]["text"] == want


# ─────────────────────────────────────────────────────────────────────────────
# 服务层（多 owner 真实场景）
# ─────────────────────────────────────────────────────────────────────────────


def _user() -> MagicMock:
    u = MagicMock()
    u.id = USER_ID
    return u


def _scalar_result(value):
    res = MagicMock()
    res.scalar_one_or_none = MagicMock(return_value=value)
    return res


def _project_row() -> MagicMock:
    row = MagicMock()
    row.first = MagicMock(
        return_value=(2025, {"entity_type": "soe", "scope": "standalone"}, None, None)
    )
    return row


def _make_db(note: DisclosureNote) -> MagicMock:
    db = MagicMock(spec=AsyncSession)
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    db.execute = AsyncMock(side_effect=[_project_row(), _scalar_result(note)])
    return db


async def _sync(note: DisclosureNote, payload: dict) -> DisclosureNote:
    await sync_from_workpaper(
        _make_db(note),
        PROJECT_ID,
        wp_id=WP_ID,
        sheet_name="附注披露信息(国企)",
        section_id="八、9",
        sub_table_data=payload,
        current_standard="soe_standalone",
        user=_user(),
        commit=False,
    )
    return note


@pytest.mark.asyncio
class TestServiceMultiOwnerTexts:
    async def test_k1_then_g2_both_survive(self):
        """K1 先推 2 段、G2 再推 1 段 → 三段**都在** `text_content` 里。"""
        note = DisclosureNote(
            project_id=PROJECT_ID, year=2025, note_section="八、9",
            section_title="其他应收款", table_data={}, is_deleted=False,
        )
        note.id = uuid.uuid4()
        await _sync(note, {"其他应收款账龄": [{"label": "1年以内"}], "_note_texts": K1_TEXTS})
        assert len(note.table_data["_note_texts"]) == 2
        await _sync(note, {"应收利息": [{"label": "定期存款利息"}], "_note_texts": G2_TEXTS})

        texts = note.table_data["_note_texts"]
        assert _keys(texts) == ["k1-aging", "k1-top5", "g2-audit-note"]
        assert note.text_content == _format_note_texts(texts)
        for marker in ("【账龄分析说明】", "【前五名说明】", "【应收利息说明】"):
            assert marker in note.text_content
        # 表级浅合并照旧：两方的表都在
        assert set(note.table_data["sub_table_data"]) == {"其他应收款账龄", "应收利息"}

    async def test_third_owner_table_only_push_keeps_texts(self):
        """只推表格不推叙述的 owner（K1 的某些 Tab）不得清掉他人说明。"""
        note = DisclosureNote(
            project_id=PROJECT_ID, year=2025, note_section="八、9",
            section_title="其他应收款",
            table_data={"_note_texts": list(K1_TEXTS)},
            text_content=_format_note_texts(K1_TEXTS),
            is_deleted=False,
        )
        note.id = uuid.uuid4()
        await _sync(note, {"应收股利": [{"label": "子公司分红"}]})
        assert _keys(note.table_data["_note_texts"]) == ["k1-aging", "k1-top5"]
        assert "【账龄分析说明】" in (note.text_content or "")

    async def test_removed_text_sections_deletes_own_segment(self):
        """底稿删掉自己的说明段 → 走显式 `_removed_text_sections`。"""
        note = DisclosureNote(
            project_id=PROJECT_ID, year=2025, note_section="八、9",
            section_title="其他应收款",
            table_data={"_note_texts": K1_TEXTS + G2_TEXTS},
            is_deleted=False,
        )
        note.id = uuid.uuid4()
        await _sync(
            note,
            {
                "其他应收款账龄": [{"label": "1年以内"}],
                "_note_texts": [K1_TEXTS[0]],
                REMOVED_TEXT_SECTIONS_KEY: ["k1-top5"],
            },
        )
        assert _keys(note.table_data["_note_texts"]) == ["k1-aging", "g2-audit-note"], (
            "自己的段被删、他人的段保留"
        )
        assert REMOVED_TEXT_SECTIONS_KEY not in note.table_data["sub_table_data"]

    async def test_removed_all_texts_clears_text_content(self):
        note = DisclosureNote(
            project_id=PROJECT_ID, year=2025, note_section="八、9",
            section_title="其他应收款",
            table_data={"_note_texts": list(K1_TEXTS)},
            text_content=_format_note_texts(K1_TEXTS),
            is_deleted=False,
        )
        note.id = uuid.uuid4()
        await _sync(
            note,
            {"表": [{"label": "x"}], REMOVED_TEXT_SECTIONS_KEY: ["k1-aging", "k1-top5"]},
        )
        assert "_note_texts" not in note.table_data
        assert note.text_content is None
