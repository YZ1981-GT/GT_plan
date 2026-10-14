"""第二轮复盘 Phase 5：原子 apply 复核（R-09）、lineage 落库（R-06）、逐章事件（R-12）。

真 SQLite + 真 ORM：apply 前按服务端状态重算 preview，写入值只取服务端预览结果。
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import tests.conftest  # noqa: F401  注册全部模型 + SQLite JSONB 兼容
from app.models.base import Base
from app.models.core import Project, User
from app.models.note_content_template_models import (
    NoteContentTemplate,
    NoteContentTemplateVersion,
    NoteTextBatchApplication,
)
from app.models.report_models import DisclosureNote
from app.services.note_document_parser import ParsedSection
from app.services.note_text_batch_apply import (
    ApplyError,
    append_content_template_lineage,
    apply_batch,
    build_note_saved_events,
    lock_target_notes,
)
from app.services.note_text_batch_service import build_preview, load_target_sections, match_sections

YEAR = 2025
_TABLES = [User.__table__, Project.__table__, DisclosureNote.__table__, NoteContentTemplate.__table__,
           NoteContentTemplateVersion.__table__, NoteTextBatchApplication.__table__]


@pytest_asyncio.fixture
async def factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=_TABLES))
    yield async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    await engine.dispose()


async def _seed(factory, *, lineage=None) -> dict:
    pid, other = uuid.uuid4(), uuid.uuid4()
    ids = {"basic": uuid.uuid4(), "period": uuid.uuid4(), "foreign": uuid.uuid4()}
    async with factory() as s:
        s.add_all([Project(id=pid, name="甲_2025", client_name="甲公司", template_type="soe", report_scope="standalone"),
                   Project(id=other, name="乙_2025", client_name="乙公司", template_type="soe", report_scope="standalone")])
        await s.flush()
        s.add_all([
            DisclosureNote(id=ids["basic"], project_id=pid, year=YEAR, note_section="一、1", section_title="公司基本情况",
                           text_content="<p>旧基本情况</p>", template_lineage=lineage, sort_index=1),
            DisclosureNote(id=ids["period"], project_id=pid, year=YEAR, note_section="四、会计期间",
                           section_title="会计期间", sort_index=2),
            DisclosureNote(id=ids["foreign"], project_id=other, year=YEAR, note_section="四、会计期间",
                           section_title="会计期间", sort_index=2),
        ])
        await s.commit()
    return {"pid": pid, **ids}


def _sources(basic_html: str = "<p>新基本情况</p>") -> list[ParsedSection]:
    return [ParsedSection(source_id="s1", title="公司基本情况", html=basic_html),
            ParsedSection(source_id="s2", title="会计期间", html="<p>会计期间正文</p>"),
            ParsedSection(source_id="s3", title="空章", html="<p>&nbsp;</p>")]


async def _preview(db: AsyncSession, seed: dict, sources: list[ParsedSection], manual: dict | None = None) -> dict:
    targets = await load_target_sections(db, seed["pid"], YEAR, scope="narrative", include_content=True)
    mapping = manual or {"s1": seed["basic"], "s2": seed["period"], "s3": seed["period"]}
    mapping = {k: v for k, v in mapping.items() if k in {s.source_id for s in sources}}
    if "s3" in mapping and "s2" in mapping and mapping["s3"] == mapping["s2"]:
        mapping.pop("s3")
    return build_preview(sources, targets, match_sections(sources, targets, manual_mappings=mapping),
                         source_identity={"kind": "upload"})


def _sel(item: dict, mode: str = "replace", **over) -> dict:
    sel = {"source_id": item["source_id"], "target_note_id": uuid.UUID(item["target_note_id"]), "mode": mode,
           "before_hash": item["before_hash"],
           "proposed_hash": item["append_hash"] if mode == "append" else item["proposed_hash"],
           "proposed_html": "<p>浏览器提交的正文一律忽略</p>", "expected_updated_at": None,
           "revoked_replacement_ids": []}
    sel.update(over)
    return sel


async def _apply(factory, seed: dict, preview: dict, selections: list[dict], *, sources=None,
                 template_version_id=None, manual=None) -> dict:
    """模拟 apply 端点：锁目标 → 服务端重算 preview → apply_batch → commit。"""
    async with factory() as db:
        locked = await lock_target_notes(db, seed["pid"], YEAR, [s["target_note_id"] for s in selections])
        recomputed = await _preview(db, seed, sources or _sources(), manual)
        result = await apply_batch(
            db, project_id=seed["pid"], year=YEAR, locked_notes=locked, preview=recomputed,
            request_digest=preview["preview_digest"], selections=selections,
            source_kind="content_template" if template_version_id else "upload",
            template_version_id=template_version_id, template_content_hash="c" * 64 if template_version_id else None,
            source_metadata={"file_hash": "f" * 64}, mutation_id="m-1", request_fingerprint="a" * 64,
            user_id=uuid.uuid4(),
        )
        await db.commit()
        return result


async def _note(factory, note_id) -> DisclosureNote:
    async with factory() as db:
        return await db.get(DisclosureNote, note_id)


def _item(preview: dict, source_id: str) -> dict:
    return next(i for i in preview["items"] if i["source_id"] == source_id)


class TestApplyWritesServerPreview:
    @pytest.mark.asyncio
    async def test_replace_writes_server_preview_not_client_html(self, factory):
        seed = await _seed(factory)
        async with factory() as db:
            preview = await _preview(db, seed, _sources())
        item = _item(preview, "s1")
        result = await _apply(factory, seed, preview, [_sel(item)])
        note = await _note(factory, seed["basic"])
        assert note.text_content == item["proposed_html"] == "<p>新基本情况</p>"
        assert (note.status.value, note.is_local_override) == ("draft", True)
        assert result["applied_count"] == 1
        assert result["changed_notes"] == [{"id": str(seed["basic"]), "note_section": "一、1"}]
        async with factory() as db:
            app_row = (await db.execute(NoteTextBatchApplication.__table__.select())).one()
        assert app_row.applied_count == 1 and app_row.detail[0]["after_hash"] == item["proposed_hash"]

    @pytest.mark.asyncio
    async def test_append_writes_previewed_append_html(self, factory):
        seed = await _seed(factory)
        async with factory() as db:
            preview = await _preview(db, seed, _sources())
        item = _item(preview, "s1")
        await _apply(factory, seed, preview, [_sel(item, "append")])
        note = await _note(factory, seed["basic"])
        assert note.text_content == item["append_html"] == "<p>旧基本情况</p><p>&nbsp;</p><p>新基本情况</p>"

    @pytest.mark.asyncio
    async def test_append_on_empty_target_rejected(self, factory):
        seed = await _seed(factory)
        async with factory() as db:
            preview = await _preview(db, seed, _sources())
        item = _item(preview, "s2")
        with pytest.raises(ApplyError) as err:
            await _apply(factory, seed, preview, [_sel(item, "append", proposed_hash=item["proposed_hash"])])
        assert err.value.code == "APPEND_NOT_APPLICABLE"


class TestApplyRejects:
    @pytest.mark.asyncio
    async def test_tampered_proposed_hash(self, factory):
        seed = await _seed(factory)
        async with factory() as db:
            preview = await _preview(db, seed, _sources())
        with pytest.raises(ApplyError) as err:
            await _apply(factory, seed, preview, [_sel(_item(preview, "s1"), proposed_hash="0" * 64)])
        assert err.value.code == "PROPOSED_HASH_MISMATCH"
        assert (await _note(factory, seed["basic"])).text_content == "<p>旧基本情况</p>"

    @pytest.mark.asyncio
    async def test_stale_target_lists_sections_and_writes_nothing(self, factory):
        seed = await _seed(factory)
        async with factory() as db:
            preview = await _preview(db, seed, _sources())
        async with factory() as db:  # 预览后他人修改了「会计期间」
            (await db.get(DisclosureNote, seed["period"])).text_content = "<p>他人刚写入</p>"
            await db.commit()
        with pytest.raises(ApplyError) as err:
            await _apply(factory, seed, preview, [_sel(_item(preview, "s1")), _sel(_item(preview, "s2"))])
        assert (err.value.code, err.value.stale_notes) == ("NOTE_BATCH_STALE_PREVIEW", ["四、会计期间"])
        assert (await _note(factory, seed["basic"])).text_content == "<p>旧基本情况</p>"

    @pytest.mark.asyncio
    async def test_unselected_target_edit_does_not_block_batch(self, factory):
        """设计 §7.3 只对**所选**目标做冲突：首版 digest 绑定全部目标 before_hash，
        他人改了未勾选章节也会整批报「预览摘要不一致」，且不指出冲突章节。"""
        seed = await _seed(factory)
        async with factory() as db:
            preview = await _preview(db, seed, _sources())
        async with factory() as db:
            (await db.get(DisclosureNote, seed["period"])).text_content = "<p>他人刚写入</p>"
            await db.commit()
        await _apply(factory, seed, preview, [_sel(_item(preview, "s1"))])
        assert (await _note(factory, seed["basic"])).text_content == "<p>新基本情况</p>"
        assert (await _note(factory, seed["period"])).text_content == "<p>他人刚写入</p>"

    @pytest.mark.asyncio
    async def test_digest_mismatch_when_source_changed(self, factory):
        seed = await _seed(factory)
        async with factory() as db:
            preview = await _preview(db, seed, _sources())
        with pytest.raises(ApplyError) as err:
            await _apply(factory, seed, preview, [_sel(_item(preview, "s1"))], sources=_sources("<p>改过</p>"))
        assert err.value.code == "PREVIEW_DIGEST_MISMATCH"

    @pytest.mark.asyncio
    async def test_selection_target_must_match_preview_mapping(self, factory):
        seed = await _seed(factory)
        async with factory() as db:
            preview = await _preview(db, seed, _sources())
        with pytest.raises(ApplyError) as err:
            await _apply(factory, seed, preview, [_sel(_item(preview, "s1"), target_note_id=seed["period"],
                                                        before_hash=_item(preview, "s2")["before_hash"])])
        assert err.value.code == "SELECTION_MAPPING_MISMATCH"

    @pytest.mark.asyncio
    async def test_unavailable_item_rejected(self, factory):
        seed = await _seed(factory)
        manual = {"s1": seed["basic"], "s3": seed["period"]}
        async with factory() as db:
            preview = await _preview(db, seed, _sources(), manual)
        item = _item(preview, "s3")
        assert item["category"] == "unavailable"
        with pytest.raises(ApplyError) as err:
            await _apply(factory, seed, preview, [_sel(item)], manual=manual)
        assert err.value.code == "SELECTION_UNAVAILABLE"

    @pytest.mark.asyncio
    async def test_foreign_project_note_rejected(self, factory):
        seed = await _seed(factory)
        async with factory() as db:
            preview = await _preview(db, seed, _sources())
        with pytest.raises(ApplyError) as err:
            await _apply(factory, seed, preview, [_sel(_item(preview, "s2"), target_note_id=seed["foreign"])])
        assert err.value.code == "NOTE_NOT_FOUND"


class TestLineagePersists:
    """R-06：首轮原地改写 dict 不落库；遇集团基线写的 list 形态直接 TypeError。"""

    @pytest.mark.parametrize("existing,check", [
        ({"group_baseline": 1}, lambda v: v["group_baseline"] == 1 and len(v["content_templates"]) == 1),
        # 历史集团基线 list 形态 ⇒ 升级为 dict，基线条目原样进 group_baselines
        ([{"baseline_id": "b-1", "version": "1.0"}],
         lambda v: v["group_baselines"] == [{"baseline_id": "b-1", "version": "1.0"}] and len(v["content_templates"]) == 1),
        # NULL ⇒ dict 形态：裁剪服务 dict(lineage)、转换服务 deepcopy(dict) 都能继续保留本条目
        (None, lambda v: isinstance(v, dict) and len(v["content_templates"]) == 1),
    ])
    @pytest.mark.asyncio
    async def test_content_template_lineage_coexists_and_persists(self, factory, existing, check):
        seed = await _seed(factory, lineage=existing)
        async with factory() as db:
            preview = await _preview(db, seed, _sources())
        version_id = uuid.uuid4()
        await _apply(factory, seed, preview, [_sel(_item(preview, "s1"))], template_version_id=version_id)
        lineage = (await _note(factory, seed["basic"])).template_lineage  # 新会话重读 = 真落库
        assert check(lineage), lineage
        entry = lineage["content_templates"][-1]
        assert (entry["template_version_id"], entry["content_hash"]) == (str(version_id), "c" * 64)

    def test_lineage_helper_never_mutates_input(self):
        existing = {"conversions": [{"direction": "soe->listed"}]}
        snapshot = {"conversions": [{"direction": "soe->listed"}]}
        result = append_content_template_lineage(existing, {"kind": "content_template", "application_id": "a"})
        assert existing == snapshot and result is not existing
        assert result["conversions"] == snapshot["conversions"]


class TestLineageReverseOrderCoexists:
    """AC-11.2 反向：集团基线曾写 list，而其余写入方（内容模板 / 程序裁剪 / 国企↔上市转换）
    全按 dict 读写、非 dict 一律当空 ⇒ 任一方后写都会静默抹掉另一方。"""

    @staticmethod
    def _baseline():
        from types import SimpleNamespace

        return SimpleNamespace(id=uuid.uuid4(), version="v1.0")

    def test_group_baseline_after_content_template_keeps_both(self):
        from app.services.group_note_baseline_service import _build_lineage_entry, _lineage_contains_baseline

        baseline = self._baseline()
        after_ct = append_content_template_lineage(None, {"kind": "content_template", "application_id": "a"})
        after_gb = _build_lineage_entry(after_ct, baseline)
        assert after_gb["content_templates"] == after_ct["content_templates"]
        assert _lineage_contains_baseline(after_gb, baseline.id)

    def test_group_baseline_survives_other_dict_writers(self):
        from app.services.group_note_baseline_service import _build_lineage_entry, _lineage_contains_baseline
        from app.services.note_conversion_service import snapshot_note_state
        from app.services.procedure_trim_note_linkage import _lineage_without_mark

        baseline = self._baseline()
        lineage = _build_lineage_entry(None, baseline)
        note = DisclosureNote(id=uuid.uuid4(), note_section="八、1", template_lineage=lineage, is_deleted=False)
        assert _lineage_contains_baseline(snapshot_note_state(note)["template_lineage"], baseline.id)
        assert _lineage_contains_baseline(_lineage_without_mark(lineage), baseline.id)
        assert _lineage_contains_baseline(append_content_template_lineage(lineage, {"kind": "content_template"}),
                                          baseline.id)

    def test_legacy_list_lineage_still_readable(self):
        from app.services.group_note_baseline_service import _build_lineage_entry, _lineage_contains_baseline

        bid = uuid.uuid4()
        legacy = [{"baseline_id": str(bid), "version": "v0.9"}]
        upgraded = _build_lineage_entry(legacy, self._baseline())
        assert upgraded["group_baselines"][0]["baseline_id"] == str(bid)
        assert _lineage_contains_baseline(legacy, bid) and _lineage_contains_baseline(upgraded, bid)

    @pytest.mark.asyncio
    async def test_affected_children_not_hidden_by_other_lineage_notes(self, factory):
        """首版只抽项目内任一条 lineage 非空的章节判断 ⇒ 抽到内容模板章节就把子企业漏掉。"""
        from app.services.group_note_baseline_service import GroupNoteBaselineService, _build_lineage_entry

        baseline = self._baseline()
        seed = await _seed(factory, lineage=append_content_template_lineage(None, {"kind": "content_template"}))
        async with factory() as db:
            db.add(DisclosureNote(project_id=seed["pid"], year=YEAR, note_section="八、1", section_title="货币资金",
                                  template_lineage=_build_lineage_entry(None, baseline), sort_index=9))
            await db.commit()
        async with factory() as db:
            assert await GroupNoteBaselineService(db)._find_affected_children(baseline.id) == [str(seed["pid"])]


class TestEventsPerChangedSection:
    def test_one_note_saved_event_per_changed_section(self):
        from app.models.audit_platform_schemas import EventType

        pid = uuid.uuid4()
        response = {"application_id": "app-1", "source_kind": "upload",
                    "changed_notes": [{"id": "n1", "note_section": "一、1"}, {"id": "n2", "note_section": "四、会计期间"}]}
        events = build_note_saved_events(pid, YEAR, response)
        assert [e.event_type for e in events] == [EventType.NOTE_SECTION_SAVED] * 2
        assert [e.extra["section_code"] for e in events] == ["一、1", "四、会计期间"]
        assert {e.extra["action"] for e in events} == {"batch_text_apply"}
        assert all(e.project_id == pid and e.year == YEAR for e in events)


class TestCoordinatorPublishesEachEvent:
    """R-12：首轮只做了源码文本匹配，这里真跑 coordinator.execute。"""

    def _coordinator(self, monkeypatch, published: list, fail_on: str | None = None):
        from unittest.mock import AsyncMock

        from app.services import disclosure_mutation_coordinator as mod
        from app.services.event_bus import event_bus

        async def _no_redis(self):
            return None

        async def _publish(payload):
            if payload.extra.get("section_code") == fail_on:
                raise RuntimeError("bus down")
            published.append(payload.extra["section_code"])

        monkeypatch.setattr(mod.DisclosureMutationCoordinator, "_redis", _no_redis)
        monkeypatch.setattr(event_bus, "publish", _publish)
        db = AsyncMock()
        coordinator = mod.DisclosureMutationCoordinator(
            db, project_id=uuid.uuid4(), mutation_id=f"m-{uuid.uuid4()}", fingerprint="f" * 64)
        return coordinator, db

    async def _run(self, coordinator, pid):
        response = {"application_id": "a", "source_kind": "upload", "warnings": [],
                    "changed_notes": [{"id": "1", "note_section": "一、1"}, {"id": "2", "note_section": "二、1"},
                                      {"id": "3", "note_section": "四、会计期间"}]}

        async def _mutate():
            return response

        return await coordinator.execute(_mutate, lambda r: build_note_saved_events(pid, YEAR, r))

    @pytest.mark.asyncio
    async def test_all_events_published_after_single_commit(self, monkeypatch):
        published: list[str] = []
        coordinator, db = self._coordinator(monkeypatch, published)
        result = await self._run(coordinator, uuid.uuid4())
        assert published == ["一、1", "二、1", "四、会计期间"]
        assert db.commit.await_count == 1 and db.rollback.await_count == 0
        assert result["event_delivery"] == "published"

    @pytest.mark.asyncio
    async def test_one_failed_event_does_not_block_others(self, monkeypatch):
        published: list[str] = []
        coordinator, db = self._coordinator(monkeypatch, published, fail_on="二、1")
        result = await self._run(coordinator, uuid.uuid4())
        assert published == ["一、1", "四、会计期间"]
        assert result["event_delivery"] == "partial" and db.rollback.await_count == 0
        assert any("二、1" in str(w) for w in result["warnings"])


class TestServiceOnlyFlushes:
    @pytest.mark.asyncio
    async def test_caller_rollback_discards_every_write(self, factory):
        """Task 28：service 只 flush —— 调用方（coordinator）回滚后两章正文与审计记录全部不落库。"""
        seed = await _seed(factory)
        async with factory() as db:
            preview = await _preview(db, seed, _sources())
        selections = [_sel(_item(preview, "s1")), _sel(_item(preview, "s2"))]
        async with factory() as db:
            locked = await lock_target_notes(db, seed["pid"], YEAR, [s["target_note_id"] for s in selections])
            result = await apply_batch(
                db, project_id=seed["pid"], year=YEAR, locked_notes=locked, preview=await _preview(db, seed, _sources()),
                request_digest=preview["preview_digest"], selections=selections, source_kind="upload",
                template_version_id=None, template_content_hash=None, source_metadata={}, mutation_id="m-rb",
                request_fingerprint="b" * 64, user_id=uuid.uuid4(),
            )
            assert result["applied_count"] == 2
            await db.rollback()
        assert (await _note(factory, seed["basic"])).text_content == "<p>旧基本情况</p>"
        assert (await _note(factory, seed["period"])).text_content is None
        async with factory() as db:
            assert (await db.execute(NoteTextBatchApplication.__table__.select())).all() == []


class TestBatchAiFillSkipsBatchWritten:
    @pytest.mark.asyncio
    async def test_batch_written_draft_section_not_offered(self, factory, monkeypatch):
        """Task 30 验收：批量写入后章节是 draft，AI 批填按「空或 draft」取数 ⇒ 只靠 is_local_override 排除。"""
        from types import SimpleNamespace

        from app.routers.disclosure_notes import batch_ai_fill_notes
        from app.services.note_knowledge_enricher import NoteKnowledgeEnricher

        seed = await _seed(factory)
        async with factory() as db:
            preview = await _preview(db, seed, _sources())
        await _apply(factory, seed, preview, [_sel(_item(preview, "s1"))])
        offered: list[str] = []

        async def _capture(self, project_id, year, sections, **_kw):
            offered.extend(s["note_section"] for s in sections)
            return []

        monkeypatch.setattr(NoteKnowledgeEnricher, "batch_prefill", _capture)
        async with factory() as db:
            await batch_ai_fill_notes(seed["pid"], YEAR, None, db, SimpleNamespace(id=uuid.uuid4()))
        assert offered == ["四、会计期间"]


class TestGenerateRespectsLocalOverride:
    """Task 30 验收：批量写入（is_local_override=True）后，重新生成附注不得覆盖正文。"""

    @pytest.mark.asyncio
    async def test_generate_notes_keeps_batch_written_text(self):
        from unittest.mock import AsyncMock, MagicMock

        from tests.test_disclosure_note_rag_characterization import (
            _make_engine,
            _minimal_template,
            _stub_generate_notes_io,
        )

        eng = _make_engine()
        eng._load_templates = AsyncMock(return_value=[_minimal_template(["模板默认文字：本公司存货按成本计量。"])])

        async def _no_prior(_pid, _yr):
            eng._prior_notes_cache = {}

        eng._preload_data_for_notes = _no_prior
        _stub_generate_notes_io(eng)
        eng._generate_text_with_llm = AsyncMock(return_value=None)
        existing = DisclosureNote(project_id=uuid.uuid4(), year=YEAR, note_section="五、1 存货", section_title="存货",
                                  text_content="<p>批量写入的正文</p>", is_local_override=True)
        res = MagicMock()
        res.scalar_one_or_none = MagicMock(return_value=existing)
        res.scalar = MagicMock(return_value=None)
        eng.db.execute = AsyncMock(return_value=res)

        await eng.generate_notes(uuid.uuid4(), YEAR, "soe")
        assert existing.text_content == "<p>批量写入的正文</p>"
