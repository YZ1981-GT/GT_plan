"""合并附注下推 → 预览 exact_id → ⚡ 自动映射 → apply 全链路（spec note-pull-header-formula-closure R6.2 / R6.3）。

真企业树（三码推导，夹具同 ``test_consol_note_pull_e2e``）+ SQLite 真 ORM + 生产函数逐级调用，不手造来源行：
①下推后的单体行经读取层 → 预览为 exact_id 且可自动确认 ②可自动确认集合 = 下推行 / 精确 / 别名 / 通用别名 / 历史，
模糊不算 ③自动映射：未绑定章节建模板 + 绑定，整组可自动确认才确认，否则回报企业与行名；重跑不重复确认；
用户排除的企业保持排除；同一操作人第二个合并项目追加版本（模板唯一键）④自动映射后 apply 写出与人工确认相同的合并数。
"""
from __future__ import annotations

import copy
from decimal import Decimal
from uuid import uuid4

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import Base
from app.models.consol_note_mapping_models import (
    ConsolNoteDetailTemplate,
    ConsolNoteDetailTemplateVersion,
    ConsolNoteMappingBinding,
    ConsolNoteMappingRule,
    ConsolNoteTemplateBinding,
)
from app.models.consolidation_models import ConsolNoteTemplatePushLog
from app.models.report_models import DisclosureNote
from app.services.consol_note_auto_mapping import auto_map_sections
from app.services.consol_note_detail_apply_service import apply_detail_refresh
from app.services.consol_note_detail_source_service import preview_detail_refresh
from app.services.consol_note_detail_suggest import AUTO_CONFIRM_MATCH_TYPES, is_auto_confirmable
from app.services.consol_note_template_push_service import push_template_to_subsidiaries
from tests.services import test_consol_note_pull_e2e as base
from tests.services.test_consol_note_pull_e2e import (  # noqa: F401  夹具（db 在本文件覆盖）
    A_ROWS, _ENGINE, _SESSION, _SECTION, _YEAR, _amounts, _note_record, _seed_cash_note, _seed_workpaper_cash_note,
    _tables_row, group, user,
)

_TABLES = base._TABLES + [ConsolNoteTemplatePushLog.__table__]


@pytest_asyncio.fixture
async def db() -> AsyncSession:
    async with _ENGINE.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.drop_all(c, tables=_TABLES))
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=_TABLES))
    async with _SESSION() as session:
        yield session
        await session.rollback()


@pytest.fixture(autouse=True)
def _gate_allows(monkeypatch):
    """附注编辑门禁放行（成员表不在本夹具里；门禁拒绝的行为见 test_consol_note_template_push_db）。"""
    async def allow(_db, user, _pid, *, consol_lock):
        assert consol_lock is True
        return user
    monkeypatch.setattr("app.services.note_edit_gate.assert_note_edit_access", allow)


async def _bindings(db, consol) -> dict[str, ConsolNoteMappingBinding]:
    rows = (await db.execute(sa.select(ConsolNoteMappingBinding).where(
        ConsolNoteMappingBinding.project_id == consol.id))).scalars().all()
    return {b.entity_node_key: b for b in rows}


async def _auto_map(db, consol, user):
    return await auto_map_sections(db, project_id=consol.id, year=_YEAR, section_ids=[_SECTION], user_id=user.id)


async def _apply(db, consol, preview):
    return await apply_detail_refresh(db, project_id=consol.id, section_id=_SECTION, year=_YEAR, node_key="G:consol",
                                      preview_entity_hashes=preview["_token_data"]["entity_hashes"])


async def _count(db, model) -> int:
    return (await db.execute(sa.select(sa.func.count()).select_from(model))).scalar_one()


async def _seed_listed_portfolio_note(db, project, amounts: dict[str, float]) -> DisclosureNote:
    """上市单体真模板「组合计提项目：应收中央企业客户」（底稿 D2 表头「期末余额/应收账款」）：只留 ``amounts`` 里的行
    （按模板行序），期末应收账款列填数。"""
    import json

    from app.services.note_section_catalog import section_applies_to_scope, template_json_path

    seed = json.loads(template_json_path("listed").read_text(encoding="utf-8"))
    sec = next(s for s in seed["sections"] if s["section_number"] == "五、5" and section_applies_to_scope(s, "standalone"))
    table = copy.deepcopy(next(t for t in sec["tables"] if t.get("name") == "组合计提项目：应收中央企业客户"))
    table["rows"] = [{**r, "values": [amounts[r["label"]], None, None, None, None, None]}
                     for r in table["rows"] if r["label"] in amounts]
    note = DisclosureNote(project_id=project.id, year=_YEAR, note_section="五、5", section_title="应收账款",
                          table_data={"_tables": [table]}, status="draft")
    db.add(note)
    await db.flush()
    return note


class TestAutoMap:

    @pytest.mark.asyncio
    async def test_creates_template_binds_and_confirms_groups_then_apply_matches_manual(self, db, user, group):
        G = group["G"]
        await _seed_cash_note(db, group["A"], A_ROWS)
        await _seed_workpaper_cash_note(db, group["A1"])  # 行名「现金」：全局别名库认得 = 库存现金

        result = await _auto_map(db, G, user)
        (sec,) = result["sections"]
        assert (sec["status"], sec["template_action"], sec["pending"]) == ("mapped", "created", [])
        assert sorted(e["node_key"] for e in sec["confirmed"]) == ["A1:subsidiary", "A:parent"]
        assert result["summary"]["confirmed_entities"] == 2 and result["summary"]["templates_created"] == 1
        assert await _count(db, ConsolNoteTemplateBinding) == 1 and await _count(db, ConsolNoteMappingRule) == 2
        version = (await db.execute(sa.select(ConsolNoteDetailTemplateVersion))).scalar_one()
        names = [r["canonical_name"] for r in version.rows]
        assert "现金" not in names, "「现金」并进「库存现金」别名，不单列（否则合并附注两行各算一半）"

        preview = await preview_detail_refresh(db, project_id=G.id, section_id=_SECTION, year=_YEAR)
        assert preview["needs_review_count"] == 0 and all(s["auto_confirmable"] for s in preview["suggestions"])
        assert (await _apply(db, G, preview))["status"] == "applied"
        rows = {r[0]: r for r in (await _note_record(db, G, "G:consol")).data["rows"]}
        # 与人工确认（test_consol_note_pull_e2e）同一结果
        assert _amounts(rows["库存现金"]) == (Decimal("476.73"), Decimal("336.73"))
        assert _amounts(rows["合计"]) == (Decimal("1002976.73"), Decimal("801336.73"))

    @pytest.mark.asyncio
    async def test_rerun_does_not_reconfirm_and_keeps_exclusions(self, db, user, group):
        G = group["G"]
        await _seed_cash_note(db, group["A"], A_ROWS)
        await _seed_workpaper_cash_note(db, group["A1"])
        await _auto_map(db, G, user)
        rules_before = await _count(db, ConsolNoteMappingRule)
        (await _bindings(db, G))["A1:subsidiary"].status = "excluded"
        await db.flush()

        again = (await _auto_map(db, G, user))["sections"][0]
        assert (again["status"], again["template_action"], again["confirmed"]) == ("mapped", "existing", [])
        assert sorted(e["node_key"] for e in again["already"]) == ["A:parent"]
        assert await _count(db, ConsolNoteMappingRule) == rules_before, "没有变化不重复确认"
        assert await _count(db, ConsolNoteDetailTemplateVersion) == 1
        assert (await _bindings(db, G))["A1:subsidiary"].status == "excluded", "用户排除的企业保持排除"

    @pytest.mark.asyncio
    async def test_group_with_a_fuzzy_label_stays_pending_with_company_and_label(self, db, user, group):
        G = group["G"]
        note = await _seed_cash_note(db, group["A"], A_ROWS)
        await _seed_workpaper_cash_note(db, group["A1"])
        await _auto_map(db, G, user)
        td = copy.deepcopy(note.table_data)
        td["_tables"][0]["rows"].insert(2, _tables_row("银行存款户", 5.0, None))  # 与「银行存款」相似度 0.89：模糊
        note.table_data = td
        await db.flush()

        preview = await preview_detail_refresh(db, project_id=G.id, section_id=_SECTION, year=_YEAR)
        fuzzy = next(s for s in preview["suggestions"] if s["source_label"] == "银行存款户")
        assert fuzzy["match_type"] == "fuzzy" and fuzzy["auto_confirmable"] is False
        assert preview["needs_review_count"] == 1

        sec = (await _auto_map(db, G, user))["sections"][0]
        assert sec["status"] == "partial" and sec["confirmed"] == []
        assert [(p["node_key"], p["labels"]) for p in sec["pending"]] == [("A:parent", ["银行存款户"])]
        assert [e["node_key"] for e in sec["already"]] == ["A1:subsidiary"]
        assert (await _bindings(db, G))["A:parent"].bound_source_hash != next(
            g["hash"] for g in preview["groups"] if any(e["node_key"] == "A:parent" for e in g["entities"])), \
            "待确认的组没有被确认"


    @pytest.mark.asyncio
    async def test_push_does_not_invalidate_confirmed_mapping(self, db, user, group):
        """⚡ 自动映射 → 📤 下推 → 直接写入：下推只打行身份，已确认的企业不变成「结构已变化」，不用再确认一遍
        （2026-10-26 浏览器实测：指纹含行身份时下推后甲被标 stale、重新汇总跳过它）。"""
        G = group["G"]
        await _seed_cash_note(db, group["A"], A_ROWS)
        await _auto_map(db, G, user)
        bound = (await db.execute(sa.select(ConsolNoteTemplateBinding.template_version_id))).scalar_one()
        pushed = await push_template_to_subsidiaries(db, consol_project_id=G.id, section_id=_SECTION, year=_YEAR,
                                                     template_version_id=bound, actor=user)
        assert {e.node_key: e.status for e in pushed.entities}["A:parent"] == "success"
        note = (await db.execute(sa.select(DisclosureNote).where(
            DisclosureNote.project_id == group["A"].id).execution_options(populate_existing=True))).scalar_one()
        assert all(r.get("_pushed_row_id") for r in note.table_data["_tables"][0]["rows"]), "前提：行身份已写入"

        preview = await preview_detail_refresh(db, project_id=G.id, section_id=_SECTION, year=_YEAR)
        assert preview["stale_entities"] == [] and preview["stale_count"] == 0
        assert {s["match_type"] for s in preview["suggestions"]} == {"exact_id"}
        result = await _apply(db, G, preview)
        assert result["status"] == "applied" and not result.get("unbound_entities")
        rows = {r[0]: r for r in (await _note_record(db, G, "G:consol")).data["rows"]}
        assert _amounts(rows["库存现金"])[0] is not None

    @pytest.mark.asyncio
    async def test_pushed_rows_preview_as_exact_id_even_after_subsidiary_renames(self, db, user, group):
        G = group["G"]
        await _seed_cash_note(db, group["A"], A_ROWS)
        await _seed_workpaper_cash_note(db, group["A1"])
        await _auto_map(db, G, user)
        bound = (await db.execute(sa.select(ConsolNoteTemplateBinding.template_version_id))).scalar_one()

        pushed = await push_template_to_subsidiaries(db, consol_project_id=G.id, section_id=_SECTION, year=_YEAR,
                                                     template_version_id=bound, actor=user)
        status = {e.node_key: e.status for e in pushed.entities}
        assert status["A:parent"] == "success" and status["A1:subsidiary"] == "skipped", "底稿同步的章节不写"
        note = (await db.execute(sa.select(DisclosureNote).where(
            DisclosureNote.project_id == group["A"].id).execution_options(populate_existing=True))).scalar_one()
        td = copy.deepcopy(note.table_data)
        td["_tables"][0]["rows"][0]["label"] = "现金及现金等价物"  # 子企业改了行名
        note.table_data = td
        await db.flush()

        preview = await preview_detail_refresh(db, project_id=G.id, section_id=_SECTION, year=_YEAR)
        renamed = next(s for s in preview["suggestions"] if s["source_label"] == "现金及现金等价物")
        assert (renamed["match_type"], renamed["auto_confirmable"]) == ("exact_id", True)
        assert renamed["suggested_target"]["canonical_name"] == "库存现金"
        sec = (await _auto_map(db, G, user))["sections"][0]
        assert sec["status"] == "mapped" and [e["node_key"] for e in sec["confirmed"]] == ["A:parent"]
        preview = await preview_detail_refresh(db, project_id=G.id, section_id=_SECTION, year=_YEAR)
        assert (await _apply(db, G, preview))["status"] == "applied"
        rows = {r[0]: r for r in (await _note_record(db, G, "G:consol")).data["rows"]}
        assert _amounts(rows["库存现金"]) == (Decimal("476.73"), Decimal("336.73")), "改名后的行仍按行身份汇进库存现金"

    @pytest.mark.asyncio
    async def test_existing_template_of_the_same_user_gets_a_new_version(self, db, user, group):
        """模板唯一键是 口径 + 章节 + 创建人：同一操作人已有该章节模板（如另一个合并项目建的）⇒ 追加版本、不新建。"""
        G = group["G"]
        await _seed_cash_note(db, group["A"], A_ROWS)
        db.add(ConsolNoteDetailTemplate(id=(tid := uuid4()), template_type="soe", section_id=_SECTION, name="旧",
                                        created_by=user.id))
        await db.flush()
        db.add(ConsolNoteDetailTemplateVersion(template_id=tid, version_number=1, rows=[
            {"target_row_id": "old", "canonical_name": "库存现金", "aliases": [], "row_type": "data"}]))
        await db.flush()

        sec = (await _auto_map(db, G, user))["sections"][0]
        assert (sec["status"], sec["template_action"]) == ("mapped", "versioned")
        versions = (await db.execute(sa.select(ConsolNoteDetailTemplateVersion.version_number).where(
            ConsolNoteDetailTemplateVersion.template_id == tid))).scalars().all()
        assert sorted(versions) == [1, 2] and await _count(db, ConsolNoteDetailTemplate) == 1

    @pytest.mark.asyncio
    async def test_section_without_any_source_is_skipped_without_creating_a_template(self, db, user, group):
        result = await _auto_map(db, group["G"], user)
        (sec,) = result["sections"]
        assert sec["status"] == "skipped" and "没有读到任何子企业的单体附注" in sec["reason"]
        assert await _count(db, ConsolNoteDetailTemplate) == 0 and await _count(db, ConsolNoteTemplateBinding) == 0


class TestTemplateSuggestionShape:

    @pytest.mark.asyncio
    async def test_source_rows_replace_the_placeholder_in_source_order(self, db, user, group):
        """上市 五-5-6 合并模板「1年以内 / 1至2年 / 2至3年 / …… / 合计」+ 单体「1-2年 … 5年以上」（【测试】集团实测）：
        区间写法并成同一行，来源独有的行按来源顺序替换「……」占位行，不留空占位。"""
        from app.services.consol_note_detail_source_service import suggest_template_for_section

        group["G"].template_type = "listed"
        # 来源独有的三行金额不单调（20 / 5 / 30）：按金额升序、降序都会换序，只有按来源顺序才是「3-4年 / 4-5年 / 5年以上」
        await _seed_listed_portfolio_note(db, group["A"], {"1年以内": 60.0, "1-2年": 50.0, "2-3年": 40.0, "3-4年": 20.0,
                                                           "4-5年": 5.0, "5年以上": 30.0, "合  计": 205.0})

        suggestion = await suggest_template_for_section(db, project_id=group["G"].id, section_id="五-5-6", year=_YEAR)
        got = [(r["canonical_name"], r["origin"]) for r in suggestion["suggested_rows"]]
        assert got == [("1年以内", "template"), ("1至2年", "template"), ("2至3年", "template"), ("3-4年", "source"),
                       ("4-5年", "source"), ("5年以上", "source"), ("合计", "template")]
        by_name = {r["canonical_name"]: r for r in suggestion["suggested_rows"]}
        assert by_name["1至2年"]["aliases"] == ["1-2年"]
        # 金额确实读到了（否则按金额排序与按来源顺序分不出来）
        assert [by_name[n]["total_amount"] for n in ("3-4年", "4-5年", "5年以上")] == [20.0, 5.0, 30.0]

    @pytest.mark.asyncio
    async def test_placeholder_kept_as_dynamic_zone_and_never_pushed(self, db, user, group):
        """来源行都在模板里（没有来源独有的行）：「……」留在建议里、标成动态行区；自动映射建的模板照此存，
        下推不把它写进子企业附注（2026-10-26 浏览器实测：修复前推进【测试】甲 五、5 一行删不掉的「……」）。"""
        from app.services.consol_note_detail_source_service import suggest_template_for_section

        G = group["G"]
        G.template_type = "listed"
        note = await _seed_listed_portfolio_note(db, group["A"], {"1年以内": 60.0, "1-2年": 50.0, "2-3年": 40.0,
                                                                  "合  计": 150.0})
        suggestion = await suggest_template_for_section(db, project_id=G.id, section_id="五-5-6", year=_YEAR)
        assert [(r["canonical_name"], r.get("category")) for r in suggestion["suggested_rows"]] == [
            ("1年以内", None), ("1至2年", None), ("2至3年", None), ("……", "dynamic_zone"), ("合计", None)]

        await auto_map_sections(db, project_id=G.id, year=_YEAR, section_ids=["五-5-6"], user_id=user.id)
        bound = (await db.execute(sa.select(ConsolNoteTemplateBinding.template_version_id))).scalar_one()
        version = await db.get(ConsolNoteDetailTemplateVersion, bound)
        assert [(r["canonical_name"], r["category"]) for r in version.rows][3] == ("……", "dynamic_zone")

        pushed = await push_template_to_subsidiaries(db, consol_project_id=G.id, section_id="五-5-6", year=_YEAR,
                                                     template_version_id=bound, actor=user)
        assert {e.node_key: e.status for e in pushed.entities}["A:parent"] == "success"
        await db.refresh(note)
        rows = note.table_data["_tables"][0]["rows"]
        assert [r["label"] for r in rows] == ["1年以内", "1-2年", "2-3年", "合  计"]
        assert all(r.get("_pushed_row_id") for r in rows)


class TestAutoMapIsolation:

    @pytest.mark.asyncio
    async def test_excluded_entity_in_a_reconfirmed_group_stays_excluded(self, db, user, group):
        G = group["G"]
        notes = [await _seed_cash_note(db, group[k], A_ROWS) for k in ("A", "B")]  # 同结构 ⇒ 同一组
        await _auto_map(db, G, user)
        (await _bindings(db, G))["B:subsidiary"].status = "excluded"
        for note in notes:  # 两家都加一行别名认得的行 ⇒ 结构变了，整组要重新确认
            td = copy.deepcopy(note.table_data)
            td["_tables"][0]["rows"].insert(1, _tables_row("其它货币资金", 1.0, None))
            note.table_data = td
        await db.flush()

        sec = (await _auto_map(db, G, user))["sections"][0]
        assert [e["node_key"] for e in sec["confirmed"]] == ["A:parent"]
        bindings = await _bindings(db, G)
        assert bindings["B:subsidiary"].status == "excluded" and bindings["A:parent"].status == "confirmed"

    @pytest.mark.asyncio
    async def test_a_failing_section_rolls_back_alone(self, db, user, group, monkeypatch):
        from app.services import consol_note_mapping_rule_service as rules

        G = group["G"]
        await _seed_cash_note(db, group["A"], A_ROWS)
        real = rules.confirm_mapping

        async def flaky(db_, **kw):
            if kw["section_id"] == _SECTION:
                raise rules.MappingRuleError(409, "X", "来源结构已变化，请重新预览")
            return await real(db_, **kw)

        monkeypatch.setattr(rules, "confirm_mapping", flaky)
        result = await auto_map_sections(db, project_id=G.id, year=_YEAR, section_ids=[_SECTION, "五-1-2"],
                                         user_id=user.id)
        status = {s["section_id"]: (s["status"], s["reason"]) for s in result["sections"]}
        assert status[_SECTION] == ("failed", "自动映射失败：来源结构已变化，请重新预览")
        assert status["五-1-2"][0] == "mapped"
        bound = (await db.execute(sa.select(ConsolNoteTemplateBinding.section_id))).scalars().all()
        assert bound == ["五-1-2"], "失败章节建的模板绑定随保存点回滚"


    @pytest.mark.asyncio
    async def test_enterprise_tree_is_built_once_for_all_sections(self, db, user, group, monkeypatch):
        from app.services import consol_tree_service

        await _seed_cash_note(db, group["A"], A_ROWS)
        real, calls = consol_tree_service.build_tree, []

        async def counted(db_, pid):
            calls.append(pid)
            return await real(db_, pid)

        monkeypatch.setattr(consol_tree_service, "build_tree", counted)
        result = await auto_map_sections(db, project_id=group["G"].id, year=_YEAR, section_ids=[_SECTION, "五-1-2"],
                                         user_id=user.id)
        assert [s["status"] for s in result["sections"]] == ["mapped", "mapped"]
        assert len(calls) == 1, "企业树只建一次（逐章节扫描 / 预览 / 建议都用传入的树）"


class TestAutoConfirmRule:

    def test_auto_confirm_set_is_pinned(self):
        assert AUTO_CONFIRM_MATCH_TYPES == {"exact_id", "exact", "alias", "global_alias", "history"}

    @pytest.mark.parametrize("match_type", sorted(AUTO_CONFIRM_MATCH_TYPES))
    def test_auto_types_with_target(self, match_type):
        assert is_auto_confirmable({"match_type": match_type, "suggested_target": {"target_row_id": "t"}})
        assert not is_auto_confirmable({"match_type": match_type, "suggested_target": None})

    @pytest.mark.parametrize("match_type", ["fuzzy", "rule_template", "previous_year", "manual", None])
    def test_review_types(self, match_type):
        assert not is_auto_confirmable({"match_type": match_type, "suggested_target": {"target_row_id": "t"}})

    def test_aging_range_spellings_are_the_same_row(self):
        """合并模板「1至2年」与单体组合计提表「1-2年」（【测试】甲 五、5 实测）是同一行：精确匹配、建模板不补重名行、下推认领。"""
        from app.services.consol_note_detail_suggest import _label_key, suggest_template_rows
        from app.services.consol_note_template_push_service import plan_merge

        assert {_label_key(x) for x in ("1-2年", "1至2年", "1～2年", " 1 - 2 年", "1－2年")} == {"1至2年"}
        assert _label_key("0-6个月") == "0至6个月" and _label_key("2025-12-31") == "2025-12-31"
        assert _label_key("其中：0-X个月") == "其中：0-X个月"
        template = [{"target_row_id": "t12", "canonical_name": "1至2年", "aliases": [], "row_type": "data"}]
        groups = [{"hash": "h", "entities": [], "source_rows": [{"label": "1-2年"}]}]
        (s,) = suggest_template_rows(groups, existing_template_rows=template)
        assert (s["match_type"], s["suggested_target"]["target_row_id"]) == ("exact", "t12")
        plan = plan_merge(template, [{"label": "1-2年", "values": [5.0]}], width=1)
        assert [(r["label"], r.get("_pushed_row_id")) for r in plan.rows] == [("1-2年", "t12")]

    def test_confirmed_history_beats_fuzzy_similarity(self):
        from app.services.consol_note_detail_suggest import suggest_template_rows

        template = [{"target_row_id": "t-bank", "canonical_name": "银行存款", "aliases": []},
                    {"target_row_id": "t-other", "canonical_name": "其他货币资金", "aliases": []}]
        # 两个行名与「银行存款」的相似度都过模糊线（0.8 / 0.89 ≥ 0.75）
        groups = [{"hash": "h", "entities": [], "source_rows": [{"label": "银行存款利息"}, {"label": "银行存款户"}]}]
        history = [{"source_label": "银行存款利息", "target_row_id": "t-other"},
                   {"source_label": "银行存款户", "target_row_id": "gone"}]
        got = {s["source_label"]: s for s in suggest_template_rows(groups, existing_template_rows=template,
                                                                   history_mappings=history)}
        assert (got["银行存款利息"]["match_type"], got["银行存款利息"]["suggested_target"]["target_row_id"]) == (
            "history", "t-other"), "用户确认过的对应先于字面相似度"
        assert (got["银行存款户"]["match_type"], got["银行存款户"]["suggested_target"]["target_row_id"]) == (
            "fuzzy", "t-bank"), "历史目标已不在模板里 ⇒ 继续往下匹配，不直接判手动"


class TestAutoMapEndpoint:
    """真实 require_project_access("edit") + check_consol_lock；只替换取库与当前用户。"""

    @pytest_asyncio.fixture
    async def client(self, db, user):
        from types import SimpleNamespace

        from fastapi import FastAPI, HTTPException
        from httpx import ASGITransport, AsyncClient

        from app.core.database import get_db
        from app.deps import get_current_user
        from app.middleware.error_handler import http_exception_handler
        from app.models.base import UserRole
        from app.routers import consol_note_detail_templates

        app = FastAPI()
        app.include_router(consol_note_detail_templates.router)
        app.add_exception_handler(HTTPException, http_exception_handler)

        async def same_session():
            yield db

        app.dependency_overrides[get_db] = same_session
        app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=user.id, role=UserRole.admin)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            yield c

    @pytest.mark.asyncio
    async def test_maps_and_commits(self, db, group, client):
        await _seed_cash_note(db, group["A"], A_ROWS)
        resp = await client.post(f"/api/projects/{group['G'].id}/consol-note-detail-refresh/auto-map",
                                 json={"year": _YEAR, "section_ids": [_SECTION]})
        assert resp.status_code == 200, resp.text
        assert not db.in_transaction(), "端点提交了事务"
        assert resp.json()["summary"]["confirmed_entities"] == 1
        assert await _count(db, ConsolNoteMappingBinding) == 1

    @pytest.mark.asyncio
    async def test_consol_locked_project_is_rejected(self, db, group, client):
        await _seed_cash_note(db, group["A"], A_ROWS)
        group["G"].consol_lock = True
        await db.flush()
        resp = await client.post(f"/api/projects/{group['G'].id}/consol-note-detail-refresh/auto-map",
                                 json={"year": _YEAR, "section_ids": [_SECTION]})
        assert resp.status_code == 423 and "合并锁定" in resp.json()["message"]
        assert await _count(db, ConsolNoteDetailTemplate) == 0
