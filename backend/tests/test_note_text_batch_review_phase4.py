"""第二轮复盘 Phase 4：章节读取（R-16）、匹配（R-07/R-26）、手工映射（R-08）、子标题并入（R-25）、预览。

第 23 组（2026-10-15 用户拍板）起上传 / 知识库按章节树逐级定位：本文件的上传类用例改用带
``section_id / parent_section_id`` 的目标树，原意保留（候选不自动定案 / 别名 / 冲突 / 禁止对 / 并入 / 章类型）。
"""

from __future__ import annotations

import hashlib
import uuid

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import tests.conftest  # noqa: F401  注册全部模型 + SQLite JSONB 兼容
from app.models.base import Base
from app.models.core import Project, User
from app.models.report_models import DisclosureNote
from app.services.note_document_parser import ParsedSection
from app.services.note_text_batch_service import (
    ManualMappingError,
    SourceContext,
    build_preview,
    load_target_sections,
    locate_sources,
    match_sections,
    validate_manual_mappings,
    validate_mappings,
)

UPLOAD = SourceContext(kind="upload")


def _h(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _src(sid: str, title: str, level: int = 2, html: str | None = None, **meta) -> ParsedSection:
    return ParsedSection(source_id=sid, title=title, level=level,
                         html=f"<p>{title}正文</p>" if html is None else html, metadata=meta)


def _tgt(code: str, title: str, *, text: str = "", chapter: str | None = None, kind: str = "narrative",
         parent: dict | None = None) -> dict:
    return {
        "id": uuid.uuid4(), "note_section": code, "section_title": title, "text_content": text,
        "content_hash": _h(text), "section_kind": kind, "updated_at": None, "status": "draft", "is_stale": False,
        "section_id": f"sec-{code}", "parent_section_id": parent["section_id"] if parent else None,
        "chapter_title": chapter if chapter is not None else (parent or {}).get("section_title"),
    }


def _ch(code: str, title: str) -> dict:
    return _tgt(code, title, kind="container")


def _locate(sources, targets, **kw):
    return locate_sources(sources, targets, source_context=kw.pop("ctx", UPLOAD), **kw)


def _matches(sources, targets, **kw):
    return {m.source_id: m for m in _locate(sources, targets, **kw)[1]}


def _preview(sources, targets, *, manual=None, **kw):
    srcs, matches, structural = _locate(sources, targets, manual_mappings=manual)
    return build_preview(srcs, targets, matches, structural_ids=structural, **kw)


# ── R-07 / R-26 匹配（上传：按章节树）────────────────────────────────────────


class TestMatchingReview:
    def test_external_unique_title_is_candidate_not_confirmed(self):
        """AC-3.3：标题定位仅作可解释候选（章正文落同名正文节）。"""
        ch = _ch("一", "公司基本情况")
        leaf = _tgt("一、1", "公司基本情况", parent=ch)
        r = _matches([_src("s1", "一、公司基本情况", 1)], [ch, leaf])["s1"]
        assert (r.target_note_id, r.confidence, r.match_kind) == (leaf["id"], "candidate", "chapter_body")

    def test_leaf_title_at_top_level_is_not_searched_across_chapters(self):
        """首版：来源「其他」在全部目标里按标题找。按树：顶层标题只在一级章里找，不跨章找同名节。"""
        c4, c14 = _ch("四", "重要会计政策"), _ch("十四", "其他重要事项")
        targets = [c4, _tgt("四、1", "其他", parent=c4), c14, _tgt("十四、9", "其他", parent=c14)]
        r = _matches([_src("s1", "其他")], targets)["s1"]
        assert (r.target_note_id, r.match_kind, r.confidence) == (None, "tree_unmatched", "manual_required")

    def test_same_title_twice_in_one_chapter_requires_manual(self):
        c14 = _ch("十四", "其他重要事项")
        targets = [c14, _tgt("十四、8", "其他", parent=c14), _tgt("十四、9", "其他", parent=c14)]
        r = _matches([_src("c", "十四、其他重要事项", 1, ""), _src("s1", "其他")], targets)["s1"]
        assert (r.target_note_id, r.match_kind) == (None, "tree_ambiguous")

    def test_chapter_then_sub_title_locates_the_right_one(self):
        c4, c14 = _ch("四", "重要会计政策"), _ch("十四", "其他重要事项")
        other14 = _tgt("十四、9", "其他", parent=c14)
        targets = [c4, _tgt("四、1", "其他", parent=c4), c14, other14]
        r = _matches([_src("c1", "十四、其他重要事项", level=1, html=""), _src("s1", "其他", level=2)], targets)["s1"]
        assert (r.target_note_id, r.confidence, r.match_kind) == (other14["id"], "candidate", "tree_path")

    def test_word_title_alias_locates_system_chapter(self):
        """R-26：Word「关联方关系及其交易」↔ 系统「关联方及关联交易」（章级别名）。"""
        ch = _ch("十一", "关联方及关联交易")
        leaf = _tgt("十一、1", "关联方及关联交易", parent=ch)
        r = _matches([_src("s1", "关联方关系及其交易", 1)], [ch, leaf])["s1"]
        assert r.target_note_id == leaf["id"] and r.confidence == "candidate"

    def test_two_sources_claiming_same_target_both_require_manual(self):
        """AC-3.4：冲突时不得自动覆盖（首版先到先得）。"""
        ch = _ch("四", "重要会计政策、会计估计")
        t = _tgt("四、会计期间", "会计期间", parent=ch)
        by = _matches([_src("c", "重要会计政策、会计估计", 1, ""), _src("s1", "会计期间"), _src("s2", "会计期间")], [ch, t])
        assert [by["s1"].confidence, by["s2"].confidence] == ["manual_required", "manual_required"]
        assert by["s1"].match_kind == by["s2"].match_kind == "conflict"

    def test_forbidden_pair_never_proposed(self):
        ch = _ch("十二", "母公司财务报表主要项目注释")
        r = _matches([_src("s1", "财务报表主要项目注释", 1)], [ch])["s1"]
        assert r.target_note_id is None

    def test_policy_section_missing_in_chapter_is_not_matched_to_other_chapter(self):
        """国企 Word 实测：「重要会计政策 / 递延所得税资产及递延所得税负债」在系统树挂在「六、税项」下；
        首版跨章配到六的同名节。按树：四下找不到 ⇒ 交给用户，不到别的章找。"""
        c4, c6 = _ch("四", "重要会计政策、会计估计"), _ch("六", "税项")
        dt6 = _tgt("四、递延所得税资产及递延所得税负债", "递延所得税资产及递延所得税负债", parent=c6)
        targets = [c4, _tgt("四、1", "会计期间", parent=c4), c6, dt6]
        sources = [_src("c", "重要会计政策、会计估计", 1, ""), _src("s1", "递延所得税资产及递延所得税负债", 3)]
        r = _matches(sources, targets)["s1"]
        assert (r.target_note_id, r.match_kind) == (None, "tree_unmatched")
        assert "四 重要会计政策、会计估计" in r.evidence

    def test_children_of_unlocated_chapter_are_not_searched_elsewhere(self):
        c4 = _ch("四", "重要会计政策、会计估计")
        targets = [c4, _tgt("四、1", "会计期间", parent=c4)]
        by = _matches([_src("c", "自定义的章", 1, ""), _src("s1", "会计期间", 3)], targets)
        assert (by["c"].match_kind, by["s1"].match_kind, by["s1"].target_note_id) == (
            "tree_unmatched", "parent_unmatched", None)

    def test_manual_anchor_relocates_children_inside_that_chapter(self):
        """用户先把上级标题对应到目标章（锚点），其下小标题随即在该章内定位（AC-3.7）。"""
        c4 = _ch("四", "重要会计政策、会计估计")
        leaf = _tgt("四、1", "会计期间", parent=c4)
        sources = [_src("c", "自定义的章", 1, ""), _src("s1", "会计期间", 3)]
        validate_mappings(sources, [c4, leaf], {"c": c4["id"]}, source_context=UPLOAD)
        by = _matches(sources, [c4, leaf], manual_mappings={"c": c4["id"]})
        assert by["c"].match_kind == "anchor"
        assert (by["s1"].target_note_id, by["s1"].match_kind) == (leaf["id"], "tree_path")

    def test_same_template_code_and_title_is_confirmed(self):
        ctx = SourceContext(kind="content_template", template_type="soe", report_scope="standalone")
        t = _tgt("四、会计期间", "会计期间")
        r = match_sections([_src("s1", "会计期间", note_section="四、会计期间")], [t],
                           source_context=ctx, target_template_type="soe")[0]
        assert (r.confidence, r.match_kind) == ("confirmed", "same_template_code")

    def test_same_code_renamed_title_is_candidate(self):
        ctx = SourceContext(kind="content_template", template_type="soe", report_scope="standalone")
        t = _tgt("四、会计期间", "会计期间及营业周期")  # 同编号、用户改了标题
        r = match_sections([_src("s1", "会计期间", note_section="四、会计期间")], [t],
                           source_context=ctx, target_template_type="soe")[0]
        assert r.confidence == "candidate"

    def test_template_title_fallback_stays_in_same_chapter(self):
        """模板来源编号对不上时只在来源编号所属章内按标题找（AC-3.9，第 23 组）。"""
        ctx = SourceContext(kind="content_template", template_type="soe", report_scope="standalone")
        other = _tgt("六、9", "其他", chapter="税项")
        same = _tgt("四、99", "其他", chapter="重要会计政策、会计估计")
        src = [_src("s1", "其他", note_section="四、98")]
        assert match_sections(src, [other], source_context=ctx, target_template_type="soe")[0].target_note_id is None
        r = match_sections(src, [other, same], source_context=ctx, target_template_type="soe")[0]
        assert (r.target_note_id, r.match_kind) == (same["id"], "title_exact")

    def test_cross_template_account_maps_via_matrix(self):
        """国企 八、1 货币资金 → 上市 五、1（variant matrix 显式映射）。"""
        ctx = SourceContext(kind="content_template", template_type="soe", report_scope="standalone")
        t = _tgt("五、1", "货币资金", kind="account_explanation")
        r = match_sections([_src("s1", "货币资金", note_section="八、1")], [t],
                           source_context=ctx, target_template_type="listed")[0]
        assert (r.target_note_id, r.confidence, r.match_kind) == (t["id"], "confirmed", "variant_matrix")


# ── R-08 手工映射校验 ──────────────────────────────────────────────────────


class TestManualMappingValidation:
    def test_foreign_target_rejected(self):
        with pytest.raises(ManualMappingError, match="不在可写范围"):
            validate_manual_mappings([_src("s1", "x")], [_tgt("一、1", "公司基本情况")], {"s1": uuid.uuid4()})

    def test_unknown_source_rejected(self):
        t = _tgt("一、1", "公司基本情况")
        with pytest.raises(ManualMappingError, match="来源章节不存在"):
            validate_manual_mappings([_src("s1", "x")], [t], {"s9": t["id"]})

    def test_duplicate_target_rejected(self):
        t = _tgt("一、1", "公司基本情况")
        with pytest.raises(ManualMappingError, match="同一目标"):
            validate_manual_mappings([_src("s1", "a"), _src("s2", "b")], [t], {"s1": t["id"], "s2": t["id"]})

    def test_forbidden_pair_forced_rejected(self):
        t = _tgt("十二、1", "母公司财务报表主要项目注释")
        with pytest.raises(ManualMappingError, match="禁止"):
            validate_manual_mappings([_src("s1", "财务报表主要项目注释")], [t], {"s1": t["id"]})

    def test_upload_write_target_must_be_narrative_but_anchor_may_be_any_chapter(self):
        c8 = _ch("八", "财务报表主要项目注释")
        cash = _tgt("八、1", "货币资金", parent=c8, kind="account_explanation")
        sources = [_src("c", "项目注释", 1, ""), _src("s1", "货币资金", 3)]
        validate_mappings(sources, [c8, cash], {"c": c8["id"]}, source_context=UPLOAD)  # 锚点：任意有子节点的行
        with pytest.raises(ManualMappingError, match="不在本次可填范围"):
            validate_mappings(sources, [c8, cash], {"s1": cash["id"]}, source_context=UPLOAD)

    def test_chapter_body_item_cannot_point_at_anchor_and_must_exist(self):
        c9 = _ch("九", "或有事项")
        leaf = _tgt("九、1", "或有负债", parent=c9)
        sources = [_src("c", "或有事项", 1, "<p>本公司无需披露的或有事项。</p>"), _src("s1", "或有负债", 3)]
        validate_mappings(sources, [c9, leaf], {"c#body": leaf["id"]}, source_context=UPLOAD)
        with pytest.raises(ManualMappingError, match="章首正文"):
            validate_mappings(sources, [c9, leaf], {"c#body": c9["id"]}, source_context=UPLOAD)
        with pytest.raises(ManualMappingError, match="来源章节不存在"):
            validate_mappings(sources, [c9, leaf], {"s1#body": leaf["id"]}, source_context=UPLOAD)

    def test_manual_mapping_reserves_target(self):
        """手工占用的目标不再被自动定位给其他来源（另一来源转人工确认，不悄悄配别处）。"""
        ch = _ch("四", "重要会计政策、会计估计")
        t = _tgt("四、会计期间", "会计期间", parent=ch)
        sources = [_src("c", "重要会计政策、会计估计", 1, ""), _src("s1", "随便"), _src("s2", "会计期间")]
        by = _matches(sources, [ch, t], manual_mappings={"s1": t["id"]})
        assert (by["s1"].confidence, by["s1"].target_note_id) == ("confirmed", t["id"])
        assert by["s2"].target_note_id is None


# ── R-25 → 第 23 组：目标是叶子时后代并入 ─────────────────────────────────────


class TestFoldIntoLeaf:
    def test_sub_headings_fold_into_located_leaf(self):
        ch = _ch("四", "重要会计政策、会计估计")
        t = _tgt("四、金融工具", "金融工具", parent=ch)
        sources = [_src("c", "重要会计政策、会计估计", 1, ""), _src("a", "金融工具", 3, "<p>总述</p>"),
                   _src("b", "（1）金融资产分类", 4, "<p>分类正文</p>")]
        folded, matches, _s = _locate(sources, [ch, t])
        merged = {s.source_id: s for s in folded}["a"]
        assert merged.html == "<p>总述</p><p><strong>（1）金融资产分类</strong></p><p>分类正文</p>"
        b = {m.source_id: m for m in matches}["b"]
        assert b.match_kind == "folded" and b.target_note_id is None

    def test_sub_heading_folds_even_if_same_title_exists_elsewhere(self):
        """首版只并「未匹配」的后代：下级标题若在别的章有同名节就被抢走。按树：叶子以下一律并入。"""
        c4, c8 = _ch("四", "重要会计政策、会计估计"), _ch("八", "财务报表主要项目注释")
        inv = _tgt("四、存货", "存货", parent=c4)
        targets = [c4, inv, c8, _tgt("八、9", "存货跌价准备", parent=c8)]
        sources = [_src("c", "重要会计政策、会计估计", 1, ""), _src("a", "存货", 3), _src("b", "存货跌价准备", 4)]
        by = _matches(sources, targets)
        assert (by["a"].target_note_id, by["b"].match_kind) == (inv["id"], "folded")

    def test_manual_mapping_of_a_descendant_is_honoured(self):
        ch = _ch("四", "重要会计政策、会计估计")
        inv, other = _tgt("四、存货", "存货", parent=ch), _tgt("四、10", "投资性房地产", parent=ch)
        sources = [_src("c", "重要会计政策、会计估计", 1, ""), _src("a", "存货", 3), _src("b", "存货的分类", 4)]
        by = _matches(sources, [ch, inv, other], manual_mappings={"b": other["id"]})
        assert (by["a"].target_note_id, by["b"].target_note_id, by["b"].match_kind) == (inv["id"], other["id"], "manual")

    def test_no_located_ancestor_keeps_everything_for_the_user(self):
        sources = [_src("a", "无关章", 2), _src("b", "无关子节", 3)]
        folded, matches, _s = _locate(sources, [])
        assert [m.match_kind for m in matches] == ["tree_unmatched", "parent_unmatched"]
        assert [s.html for s in folded] == [s.html for s in sources]


# ── 预览 ──────────────────────────────────────────────────────────────────


def _period_tree(text: str = ""):
    ch = _ch("四", "重要会计政策、会计估计")
    return ch, _tgt("四、会计期间", "会计期间", parent=ch, text=text)


class TestPreviewReview:
    def test_candidate_never_default_selected(self):
        """AC-3.5：一键预填只消费 confirmed；candidate 进入需复核且不默认勾选。"""
        ch, t = _period_tree()
        item = _preview([_src("c", "重要会计政策、会计估计", 1, ""), _src("s1", "会计期间")], [ch, t])["items"][0]
        assert item["category"] == "review" and item["default_selected"] is False

    def test_empty_source_is_unavailable(self):
        ch, t = _period_tree()
        item = _preview([_src("s1", "会计期间", html="<p>&nbsp;</p>")], [ch, t], manual={"s1": t["id"]})["items"][0]
        assert item["category"] == "unavailable" and item["unavailable_reason"] == "来源正文为空"

    def test_replacement_result_is_resanitized_and_append_previewed(self):
        ch, t = _period_tree("<p>旧</p>")
        item = _preview([_src("s1", "会计期间", html="<p>{公司名称}</p>")], [ch, t], manual={"s1": t["id"]},
                        target_vars={"company_name": "<b>甲</b>"})["items"][0]
        assert item["proposed_html"] == "<p>&lt;b&gt;甲&lt;/b&gt;</p>"
        assert item["append_html"] == "<p>旧</p><p>&nbsp;</p><p>&lt;b&gt;甲&lt;/b&gt;</p>"
        assert item["append_hash"] == _h(item["append_html"])
        assert item["before_hash"] == _h("<p>旧</p>")

    def test_revoked_replacement_kept_and_digest_changes(self):
        ch, t = _period_tree()
        sources = [_src("s1", "会计期间", html="<p>{公司名称}</p>")]
        first = _preview(sources, [ch, t], manual={"s1": t["id"]}, target_vars={"company_name": "甲"})
        rid = first["items"][0]["replacements"][0]["replacement_id"]
        second = _preview(sources, [ch, t], manual={"s1": t["id"]}, target_vars={"company_name": "甲"},
                          revoked_replacement_ids={rid})
        assert second["items"][0]["proposed_html"] == "<p>{公司名称}</p>"
        assert second["preview_digest"] != first["preview_digest"]

    def test_digest_binds_inputs_not_target_state(self):
        """digest 绑来源/映射/拟写入内容；目标现状由 apply 逐章 before_hash 复核（phase5
        ``test_stale_target_lists_sections_and_writes_nothing`` / ``…unselected_target…``）。"""
        sources = [_src("s1", "会计期间")]
        ch, t1 = _period_tree()
        t2 = dict(t1, text_content="<p>他人刚写入</p>", content_hash=_h("<p>他人刚写入</p>"))
        p1 = _preview(sources, [ch, t1], manual={"s1": t1["id"]})
        p2 = _preview(sources, [ch, t2], manual={"s1": t1["id"]})
        assert p1["preview_digest"] == p2["preview_digest"]
        assert p1["items"][0]["before_hash"] != p2["items"][0]["before_hash"]
        changed = [_src("s1", "会计期间", html="<p>改过的来源</p>")]
        assert _preview(changed, [ch, t1], manual={"s1": t1["id"]})["preview_digest"] != p1["preview_digest"]

    def test_chapter_body_without_same_named_leaf_is_listed_for_the_user(self):
        """Word「或有事项」章首有正文、系统章下没有同名正文节 ⇒ 章首正文单列为待人工对应项，不丢、不乱放。"""
        c9 = _ch("九", "或有事项")
        neg = _tgt("九、1", "或有负债", parent=c9)
        sources = [_src("c", "或有事项", 1, "<p>本公司无需披露的或有事项。</p>"), _src("s1", "或有负债", 3)]
        preview = _preview(sources, [c9, neg])
        items = {i["source_id"]: i for i in preview["items"]}
        assert items["c#body"]["category"] == "unavailable" and "没有与之同名的正文节" in items["c#body"]["unavailable_reason"]
        assert items["s1"]["target_note_id"] == str(neg["id"])
        assert {(s["source_id"], s["match_kind"]) for s in preview["skipped_sources"]} == {("c", "anchor")}
        mapped = _preview(sources, [c9, neg], manual={"c#body": neg["id"]})
        by = {i["source_id"]: i for i in mapped["items"]}
        assert by["c#body"]["target_note_id"] == str(neg["id"]) and by["s1"]["target_note_id"] is None  # 抢同一目标

    def test_unlocated_structural_source_is_flagged_for_chapter_picker(self):
        c4, t = _period_tree()
        items = {i["source_id"]: i for i in _preview([_src("c", "自定义的章", 1, ""), _src("s1", "会计期间", 3)],
                                                       [c4, t])["items"]}
        assert items["c"]["structural"] is True and items["s1"]["structural"] is False
        assert "上级「自定义的章」未定位" in items["s1"]["unavailable_reason"]


# ── R-16 章节读取（真 SQLite + 真 ORM）──────────────────────────────────────


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(
            c, tables=[User.__table__, Project.__table__, DisclosureNote.__table__]))
    async with async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)() as session:
        yield session
    await engine.dispose()


async def _seed(db: AsyncSession) -> uuid.UUID:
    pid = uuid.uuid4()
    db.add(Project(id=pid, name="甲_2025", client_name="甲公司", template_type="soe", report_scope="standalone"))
    await db.flush()
    for i, (code, title, text) in enumerate([
        ("一、1", "公司基本情况", "<p>基本情况正文</p>"),
        ("四、会计期间", "会计期间", ""),
        ("八、1", "货币资金", "<p>货币资金说明</p>"),
    ]):
        db.add(DisclosureNote(project_id=pid, year=2025, note_section=code, section_title=title,
                              account_name=title, text_content=text or None, sort_index=i))
    await db.flush()
    return pid


class TestLoadTargetSections:
    @pytest.mark.asyncio
    async def test_targets_follow_document_order_not_sibling_index(self, db):
        """sort_index 是 V019 的「同层级内序号」（真库 6 个项目里 4 个全为 0），不是全文顺序；生成链、导出都按 sort_order。
        首版按 sort_index + 编号字符串排序 ⇒ 汉字码位序「一、三、二」，手工映射下拉与模板章节顺序全乱。"""
        pid = uuid.uuid4()
        db.add(Project(id=pid, name="乙_2025", client_name="乙公司", template_type="soe", report_scope="standalone"))
        await db.flush()
        for code, title, order in (("三、1", "遵循企业会计准则的声明", 300), ("一、1", "公司基本情况", 100),
                                   ("二、1", "财务报表编制基础", 200)):
            db.add(DisclosureNote(project_id=pid, year=2025, note_section=code, section_title=title,
                                  text_content="<p>正文</p>", sort_order=order, sort_index=0))
        await db.flush()
        rows = await load_target_sections(db, pid, 2025, scope="all")
        assert [r["note_section"] for r in rows] == ["一、1", "二、1", "三、1"]

    @pytest.mark.asyncio
    async def test_narrative_scope_excludes_account_even_if_account_name_set(self, db):
        pid = await _seed(db)
        rows = await load_target_sections(db, pid, 2025, scope="narrative")
        assert [r["note_section"] for r in rows] == ["一、1", "四、会计期间"]

    @pytest.mark.asyncio
    async def test_all_scope_classifies_by_word_authority(self, db):
        pid = await _seed(db)
        kinds = {r["note_section"]: r["section_kind"] for r in await load_target_sections(db, pid, 2025, scope="all")}
        assert kinds == {"一、1": "narrative", "四、会计期间": "narrative", "八、1": "account_explanation"}

    @pytest.mark.asyncio
    async def test_content_hash_is_real_even_without_content(self, db):
        pid = await _seed(db)
        rows = {r["note_section"]: r for r in await load_target_sections(db, pid, 2025, scope="narrative")}
        assert rows["一、1"]["content_hash"] == _h("<p>基本情况正文</p>")
        assert "text_content" not in rows["一、1"] and rows["一、1"]["has_content"] is True
        assert rows["四、会计期间"]["has_content"] is False


# ── Word 端到端发现：来源所在章类型须与目标类型一致 ─────────────────────────


class TestChapterKindGating:
    """Word 模板里「存货」等同时出现在会计政策章与项目注释章；首版两者争抢同一叙述目标 ⇒ 全部冲突。
    按树：各自只在本章内定位，项目注释章的「存货」定位到科目注释节 ⇒ 上传不在可填范围。"""

    def _tree(self):
        c4, c8 = _ch("四", "重要会计政策、会计估计"), _ch("八", "财务报表主要项目注释")
        policy = _tgt("四、存货", "存货", parent=c4)
        return [c4, policy, c8, _tgt("八、9", "存货", parent=c8, kind="account_explanation")], policy

    def _sources(self):
        return [
            _src("c1", "重要会计政策、会计估计", level=1, html=""),
            _src("p1", "存货", level=2, html="<p>存货政策</p>"),
            _src("c2", "财务报表主要项目注释", level=1, html=""),
            _src("a1", "存货", level=2, html="<p>存货余额表说明</p>"),
        ]

    def test_account_chapter_source_does_not_compete_for_narrative_target(self):
        targets, policy = self._tree()
        by_id = _matches(self._sources(), targets)
        assert (by_id["p1"].target_note_id, by_id["p1"].confidence) == (policy["id"], "candidate")
        assert (by_id["a1"].target_note_id, by_id["a1"].match_kind) == (None, "out_of_scope")

    def test_out_of_scope_sources_excluded_from_preview_and_counted(self):
        targets, _policy = self._tree()
        preview = _preview(self._sources(), targets)
        assert "a1" not in {i["source_id"] for i in preview["items"]}
        assert (preview["summary"]["out_of_scope"], preview["summary"]["anchor"]) == (1, 2)  # a1；两个章标题


# ── 2026-10-16 种子按四版 Word 对齐后的端到端发现（spec disclosure-note-template-word-realignment）──────


class TestChapterIsBody:
    """上市「十 公允价值」：种子章下只有同名正文节「十、1 公允价值」，Word 章内是正文 +「（1）以公允价值计量的项目和金额」
    …「（5）…」小标题与表格。按锚点处理时章首正文落到「十、1」，五个小标题在章内找不到 ⇒ 全部「需人工对应」。"""

    def test_sub_headings_fold_into_the_sole_body_leaf(self):
        ch = _ch("十", "公允价值")
        leaf = _tgt("十、1", "公允价值", parent=ch)
        sources = [_src("c", "十、公允价值", 1, "<p>层次说明</p>"),
                   _src("a", "（1）以公允价值计量的项目和金额", 3, "<p>表一</p>"),
                   _src("b", "（2）第二层次公允价值计量的相关信息", 3, "<p>表二</p>")]
        folded, matches, _s = _locate(sources, [ch, leaf])
        by = {m.source_id: m for m in matches}
        assert (by["c"].target_note_id, by["c"].match_kind, by["c"].confidence) == (leaf["id"], "chapter_body", "candidate")
        assert [by["a"].match_kind, by["b"].match_kind] == ["folded", "folded"]
        assert {s.source_id: s for s in folded}["c"].html == (
            "<p>层次说明</p><p><strong>（1）以公允价值计量的项目和金额</strong></p><p>表一</p>"
            "<p><strong>（2）第二层次公允价值计量的相关信息</strong></p><p>表二</p>")

    def test_chapter_with_other_sections_keeps_anchor_rule(self):
        """章下除同名正文节外还有别的节 ⇒ 仍是锚点：小标题在章内定位，章首正文单列落到同名正文节。"""
        ch = _ch("七", "在其他主体中的权益")
        body, sub = _tgt("七、1", "在其他主体中的权益", parent=ch), _tgt("七、2", "在子公司中的权益", parent=ch)
        by = _matches([_src("c", "七、在其他主体中的权益", 1, "<p>章首</p>"), _src("s1", "在子公司中的权益", 2)],
                      [ch, body, sub])
        assert by["c"].match_kind == "anchor"
        assert (by["c#body"].target_note_id, by["s1"].target_note_id) == (body["id"], sub["id"])

    def test_word_placeholder_enum_is_not_part_of_title(self):
        """国企 Word「X、数据资源」：X 是模板占位序号（真实附注里换成数字），与 ``note_word_tree`` 同口径不算标题。"""
        ch = _ch("八", "财务报表主要项目注释")
        data = _tgt("八、88", "数据资源", parent=ch, kind="account_explanation")
        by = _matches([_src("c", "财务报表主要项目注释", 1, ""), _src("s1", "X、数据资源", 3)], [ch, data])
        assert (by["s1"].target_note_id, by["s1"].match_kind) == (None, "out_of_scope")  # 定位到了，科目注释不归上传填


# ── 第 7 组整体复盘：variant matrix 别名索引不得因同变体多个旧码而丢码 ─────────────
def test_matrix_index_keeps_every_legacy_alias_code() -> None:
    """首版用 ``{variant: code for variant, codes in ... for code in codes}`` 建池：同一变体有多个旧码时
    字典键被覆盖，只剩最后一个，前面的旧码静默失配（现数据 0 处多码，属潜伏缺陷）。"""
    from app.services.note_text_batch_service import _index_variant_matrix

    by_code, codes = _index_variant_matrix({"accounts": [{
        "account_key": "cash",
        "variants": {"soe_standalone": "五、1", "listed_standalone": "七、1"},
        "legacy_aliases": {"soe_standalone": ["五、01", "五（1）"]},
    }]})
    assert by_code[("soe", "五、01")] == "cash"
    assert by_code[("soe", "五（1）")] == "cash"
    assert codes[("cash", "soe")] == frozenset({"五、1", "五、01", "五（1）"})
    assert codes[("cash", "listed")] == frozenset({"七、1"})


def test_preview_replacements_describe_only_written_content() -> None:
    """替换清单必须基于消毒后的正文生成：只出现在会被丢弃内容里的企业名，不得生成「幻影」替换项。"""
    ch, t = _period_tree()
    sources = [_src("s1", "会计期间", html="<p>正文</p><script>甲公司</script>")]
    item = _preview(sources, [ch, t], manual={"s1": t["id"]}, target_vars={"company_name": "乙公司"},
                    source_entity_name="甲公司")["items"][0]
    assert "甲公司" not in item["proposed_html"] and "script" not in item["proposed_html"]
    assert item["replacements"] == []


def test_preview_item_carries_target_chapter_for_grouping() -> None:
    """AC-2.3：右栏按目标父章分组 ⇒ 预览项带目标所属一级章标题；未匹配项为 None。"""
    ch, t = _period_tree()
    sources = [_src("c", "重要会计政策、会计估计", 1, ""), _src("s1", "会计期间"), _src("s2", "完全无关的标题")]
    items = {i["source_id"]: i for i in _preview(sources, [ch, t])["items"]}
    assert items["s1"]["target_chapter_title"] == "重要会计政策、会计估计"
    assert items["s2"]["target_note_id"] is None and items["s2"]["target_chapter_title"] is None


def test_preview_lists_skipped_sources_with_reason_for_left_pane_status() -> None:
    """AC-2.2：左栏要逐个显示来源的匹配状态。不进预览的来源（并入上级 / 不在可填范围 / 已定位到章）逐个带原因返回，
    且与 summary 计数同口径。"""
    targets, _policy = TestChapterKindGating()._tree()
    preview = _preview(TestChapterKindGating()._sources(), targets)
    assert {(s["source_id"], s["match_kind"]) for s in preview["skipped_sources"]} == {
        ("c1", "anchor"), ("c2", "anchor"), ("a1", "out_of_scope")}
    assert not {s["source_id"] for s in preview["skipped_sources"]} & {i["source_id"] for i in preview["items"]}

    ch = _ch("四", "重要会计政策、会计估计")
    t2 = _tgt("四、金融工具", "金融工具", parent=ch)
    src2 = [_src("c", "重要会计政策、会计估计", 1, ""), _src("a", "金融工具", 2, "<p>总述</p>"),
            _src("b", "（1）金融资产分类", 3, "<p>分类正文</p>")]
    p2 = _preview(src2, [ch, t2])
    assert [s for s in p2["skipped_sources"] if s["source_id"] == "b"] == [
        {"source_id": "b", "match_kind": "folded", "evidence": "已并入「金融工具」"}]
    assert len(p2["skipped_sources"]) == p2["summary"]["folded"] + p2["summary"]["out_of_scope"] + p2["summary"]["anchor"]


def test_matrix_index_rejects_duplicate_code_owner() -> None:
    """同一准则 / 章节号被两个 account 认领时 fail-closed，不能用 setdefault 静默挑第一个。"""
    from app.services.note_text_batch_service import _index_variant_matrix

    with pytest.raises(ValueError, match="同时属于"):
        _index_variant_matrix({"accounts": [
            {"account_key": "one", "variants": {"soe_standalone": "八、70"}},
            {"account_key": "two", "variants": {"soe_standalone": "八、70"}},
        ]})
