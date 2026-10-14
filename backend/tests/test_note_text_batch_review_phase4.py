"""第二轮复盘 Phase 4：章节读取（R-16）、匹配（R-07/R-26）、手工映射（R-08）、子标题并入（R-25）、预览。"""

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
    fold_unmatched_descendants,
    load_target_sections,
    match_sections,
    validate_manual_mappings,
)


def _h(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _src(sid: str, title: str, level: int = 2, html: str | None = None, **meta) -> ParsedSection:
    return ParsedSection(source_id=sid, title=title, level=level, html=html or f"<p>{title}正文</p>", metadata=meta)


def _tgt(code: str, title: str, *, text: str = "", chapter: str | None = None, kind: str = "narrative") -> dict:
    return {
        "id": uuid.uuid4(), "note_section": code, "section_title": title, "text_content": text,
        "content_hash": _h(text), "section_kind": kind, "chapter_title": chapter, "updated_at": None,
        "status": "draft", "is_stale": False,
    }


# ── R-07 / R-26 匹配 ───────────────────────────────────────────────────────


class TestMatchingReview:
    def test_external_unique_title_is_candidate_not_confirmed(self):
        """AC-3.3：标题规范化精确匹配仅作可解释候选。"""
        r = match_sections([_src("s1", "一、公司基本情况")], [_tgt("一、1", "公司基本情况")])[0]
        assert (r.confidence, r.match_kind) == ("candidate", "title_exact")

    def test_duplicate_target_titles_require_manual(self):
        """探针实测：同名「其他」两个目标时首版自动定案到第一个。"""
        targets = [_tgt("四、1", "其他", chapter="重要会计政策"), _tgt("十四、9", "其他", chapter="其他重要事项")]
        r = match_sections([_src("s1", "其他")], targets)[0]
        assert r.confidence == "manual_required" and r.target_note_id is None

    def test_duplicate_titles_disambiguated_by_chapter_path(self):
        targets = [_tgt("四、1", "其他", chapter="重要会计政策"), _tgt("十四、9", "其他", chapter="其他重要事项")]
        sources = [_src("c1", "十四、其他重要事项", level=1), _src("s1", "其他", level=2)]
        by_id = {r.source_id: r for r in match_sections(sources, targets)}
        assert by_id["s1"].target_note_id == targets[1]["id"]
        assert by_id["s1"].confidence == "candidate"

    def test_word_title_alias_matches_system_title(self):
        """R-26：Word「关联方关系及其交易」↔ 系统「关联方及关联交易」。"""
        t = _tgt("十一、1", "关联方及关联交易")
        r = match_sections([_src("s1", "关联方关系及其交易")], [t])[0]
        assert r.target_note_id == t["id"] and r.confidence == "candidate"

    def test_two_sources_claiming_same_target_both_require_manual(self):
        """AC-3.4：冲突时不得自动覆盖（首版先到先得）。"""
        t = _tgt("四、会计期间", "会计期间")
        results = match_sections([_src("s1", "会计期间"), _src("s2", "会计期间")], [t])
        assert [r.confidence for r in results] == ["manual_required", "manual_required"]

    def test_forbidden_pair_never_proposed(self):
        t = _tgt("十二、1", "母公司财务报表主要项目注释")
        r = match_sections([_src("s1", "财务报表主要项目注释")], [t])[0]
        assert r.target_note_id is None

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

    def test_manual_mapping_reserves_target(self):
        """手工占用的目标不再被自动匹配给其他来源。"""
        t = _tgt("四、会计期间", "会计期间")
        results = match_sections([_src("s1", "随便"), _src("s2", "会计期间")], [t], manual_mappings={"s1": t["id"]})
        by_id = {r.source_id: r for r in results}
        assert (by_id["s1"].confidence, by_id["s1"].target_note_id) == ("confirmed", t["id"])
        assert by_id["s2"].target_note_id is None


# ── R-25 未匹配子标题并入上级 ─────────────────────────────────────────────


class TestFoldUnmatchedDescendants:
    def test_unmatched_h3_folds_into_matched_h2(self):
        t = _tgt("三、金融工具", "金融工具")
        sources = [_src("a", "金融工具", 2, "<p>总述</p>"), _src("b", "（1）金融资产分类", 3, "<p>分类正文</p>")]
        folded, matches = fold_unmatched_descendants(sources, match_sections(sources, [t]))
        merged = {s.source_id: s for s in folded}["a"]
        assert merged.html == "<p>总述</p><p><strong>（1）金融资产分类</strong></p><p>分类正文</p>"
        b = {m.source_id: m for m in matches}["b"]
        assert b.match_kind == "folded" and b.target_note_id is None

    def test_no_matched_ancestor_keeps_unmatched(self):
        sources = [_src("a", "无关章", 2), _src("b", "无关子节", 3)]
        folded, matches = fold_unmatched_descendants(sources, match_sections(sources, []))
        assert {m.match_kind for m in matches} == {"unmatched"}
        assert [s.html for s in folded] == [s.html for s in sources]


# ── 预览 ──────────────────────────────────────────────────────────────────


class TestPreviewReview:
    def test_candidate_never_default_selected(self):
        """AC-3.5：一键预填只消费 confirmed；candidate 进入需复核且不默认勾选。"""
        t = _tgt("四、会计期间", "会计期间")
        sources = [_src("s1", "会计期间")]
        item = build_preview(sources, [t], match_sections(sources, [t]))["items"][0]
        assert item["category"] == "review" and item["default_selected"] is False

    def test_empty_source_is_unavailable(self):
        t = _tgt("四、会计期间", "会计期间")
        sources = [_src("s1", "会计期间", html="<p>&nbsp;</p>")]
        item = build_preview(sources, [t], match_sections(sources, [t], manual_mappings={"s1": t["id"]}))["items"][0]
        assert item["category"] == "unavailable" and item["unavailable_reason"] == "来源正文为空"

    def test_replacement_result_is_resanitized_and_append_previewed(self):
        t = _tgt("四、会计期间", "会计期间", text="<p>旧</p>")
        sources = [_src("s1", "会计期间", html="<p>{公司名称}</p>")]
        matches = match_sections(sources, [t], manual_mappings={"s1": t["id"]})
        item = build_preview(sources, [t], matches, target_vars={"company_name": "<b>甲</b>"})["items"][0]
        assert item["proposed_html"] == "<p>&lt;b&gt;甲&lt;/b&gt;</p>"
        assert item["append_html"] == "<p>旧</p><p>&nbsp;</p><p>&lt;b&gt;甲&lt;/b&gt;</p>"
        assert item["append_hash"] == _h(item["append_html"])
        assert item["before_hash"] == _h("<p>旧</p>")

    def test_revoked_replacement_kept_and_digest_changes(self):
        t = _tgt("四、会计期间", "会计期间")
        sources = [_src("s1", "会计期间", html="<p>{公司名称}</p>")]
        matches = match_sections(sources, [t], manual_mappings={"s1": t["id"]})
        first = build_preview(sources, [t], matches, target_vars={"company_name": "甲"})
        rid = first["items"][0]["replacements"][0]["replacement_id"]
        second = build_preview(sources, [t], matches, target_vars={"company_name": "甲"}, revoked_replacement_ids={rid})
        assert second["items"][0]["proposed_html"] == "<p>{公司名称}</p>"
        assert second["preview_digest"] != first["preview_digest"]

    def test_digest_binds_target_state(self):
        sources = [_src("s1", "会计期间")]
        t1 = _tgt("四、会计期间", "会计期间", text="")
        t2 = dict(t1, text_content="<p>他人刚写入</p>", content_hash=_h("<p>他人刚写入</p>"))
        m = match_sections(sources, [t1], manual_mappings={"s1": t1["id"]})
        assert build_preview(sources, [t1], m)["preview_digest"] != build_preview(sources, [t2], m)["preview_digest"]


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
    """Word 模板里「存货」等同时出现在会计政策章与项目注释章；首版两者争抢同一叙述目标 ⇒ 全部冲突。"""

    def _sources(self):
        return [
            _src("c1", "重要会计政策、会计估计", level=1),
            _src("p1", "存货", level=2, html="<p>存货政策</p>"),
            _src("c2", "财务报表主要项目注释", level=1),
            _src("a1", "存货", level=2, html="<p>存货余额表说明</p>"),
        ]

    def test_account_chapter_source_does_not_compete_for_narrative_target(self):
        t = _tgt("四、存货", "存货", chapter="重要会计政策、会计估计")
        by_id = {r.source_id: r for r in match_sections(self._sources(), [t])}
        assert (by_id["p1"].target_note_id, by_id["p1"].confidence) == (t["id"], "candidate")
        assert (by_id["a1"].target_note_id, by_id["a1"].match_kind) == (None, "out_of_scope")

    def test_out_of_scope_sources_excluded_from_preview_and_counted(self):
        t = _tgt("四、存货", "存货", chapter="重要会计政策、会计估计")
        sources = self._sources()
        preview = build_preview(sources, [t], match_sections(sources, [t]))
        assert "a1" not in {i["source_id"] for i in preview["items"]}
        assert preview["summary"]["out_of_scope"] == 2  # c2 章标题本身 + a1
