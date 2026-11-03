"""存量项目附注对齐（spec disclosure-note-template-word-realignment Phase 3 Task 10/13，design §4.1）。

计划部分是纯函数：合成模板 + 行快照逐条钉规则（改编号 / 冲突 / 树字段 / section_id 对齐 / 子节点跟随 / 补章 /
脱树改挂 / 关联表）。执行部分见本文件后半：真 SQLite + 真 ORM + 真生成链（只替换取数与构表），断言执行后重算
计划为空、已有行正文表格与编辑人不变。备份 / 恢复只支持 PostgreSQL，见 ``test_note_project_realign_backup_pg.py``。
"""
from __future__ import annotations

from app.services.note_project_realign import NoteRow, RelatedRow, plan_realignment

DIT_OLD, DIT = "六、递延所得税资产及递延所得税负债", "四、递延所得税资产及递延所得税负债"  # 真实种子别名


def _t(code: str, title: str, sid: str, parent: str | None, level: int, sort_order: int, sort_index: int = 0) -> dict:
    return {"note_section": code, "section_title": title, "section_id": sid, "parent_section_id": parent,
            "level": level, "sort_order": sort_order, "sort_index": sort_index}


TEMPLATES = [
    _t("四", "重要会计政策和会计估计", "c4", None, 1, 400),
    _t(DIT, "递延所得税资产及递延所得税负债", "c4-dit", "c4", 2, 431, 31),
    _t("八", "财务报表主要项目注释", "c8", None, 1, 800),
    _t("八、5", "应收账款", "c8-5", "c8", 2, 805, 5),
    _t("八、16", "其他债权投资", "c8-16", "c8", 2, 816, 16),
    _t("十四", "财务报表之批准", "c14", None, 1, 1399),
]
SEEDS = {"十四": {"section_title": "财务报表之批准", "legacy_titles": ["其他重要事项"]},
         "十三": {"section_title": "按照有关财务会计制度应披露的其他内容", "scope": "consolidated_only"}}


def _row(rid: str, code: str, title: str, **kw) -> NoteRow:
    t = next((x for x in TEMPLATES if x["note_section"] == code), None)
    base = {"section_id": t["section_id"], "parent_section_id": t["parent_section_id"], "level": t["level"],
            "sort_order": t["sort_order"], "sort_index": t["sort_index"]} if t else {}
    return NoteRow(id=rid, note_section=code, section_title=title, **{**base, **kw})


def _plan(rows: list[NoteRow], related: list[RelatedRow] | None = None):
    return plan_realignment(rows, TEMPLATES, template_type="soe", report_scope="standalone", seeds=SEEDS,
                            related=related)


def _aligned() -> list[NoteRow]:
    """与模板完全一致的一套行（每个用例在此基础上改）。"""
    return [_row(f"r-{t['note_section']}", t["note_section"], t["section_title"]) for t in TEMPLATES]


def test_aligned_rows_plan_nothing() -> None:
    plan = _plan(_aligned())
    assert plan.action_count() == 0 and plan.counts() == {k: 0 for k in plan.counts()}


def test_rename_by_alias_and_conflicts_with_active_or_soft_deleted_holder() -> None:
    rows = [r for r in _aligned() if r.note_section != DIT]
    rows.append(_row("old-dit", DIT_OLD, "递延所得税资产及递延所得税负债", section_id="c4-dit",
                     parent_section_id="c6", level=2, sort_order=600, sort_index=0))
    rows.append(_row("dup-5", "五、5", "应收账款"))  # 国企旧位置编号 → 八、5，已有活动行
    rows = [r for r in rows if r.note_section != "八、16"]
    rows.append(_row("gone-16", "八、16", "其他债权投资", is_deleted=True))
    rows.append(_row("dup-16", "五、16", "其他债权投资"))  # → 八、16，被软删行占着（唯一索引含软删）
    plan = _plan(rows)
    assert plan.renames == [{"note_id": "old-dit", "old": DIT_OLD, "new": DIT, "title": "递延所得税资产及递延所得税负债"}]
    assert {(c["note_id"], c["holder_id"], c["holder_deleted"]) for c in plan.rename_conflicts} == {
        ("dup-5", "r-八、5", False), ("dup-16", "gone-16", True)}
    moved = next(u for u in plan.tree_updates if u["note_id"] == "old-dit")
    assert moved["note_section"] == DIT
    assert moved["changes"] == {"parent_section_id": ["c6", "c4"], "sort_index": [0, 31], "sort_order": [600, 431]}
    assert plan.insert_blocked == [{"note_section": "八、16", "holder_id": "gone-16"}]


def test_title_rewritten_only_when_it_is_a_known_old_title() -> None:
    rows = [r for r in _aligned() if r.note_section not in ("十四", "八、5")]
    rows += [_row("c14", "十四", "其他重要事项"), _row("ar", "八、5", "应收账款（含应收票据）")]
    plan = _plan(rows)
    assert [(u["note_id"], u["changes"]) for u in plan.tree_updates] == [
        ("c14", {"section_title": ["其他重要事项", "财务报表之批准"]})]
    assert plan.titles_kept == [{"note_id": "ar", "note_section": "八、5", "title": "应收账款（含应收票据）",
                                 "template_title": "应收账款"}]


def test_title_hint_moves_into_guidance_when_old_title_is_cleaned() -> None:
    """种子把标题尾部编制提示拆进 title_hint：存量行标题按 legacy_titles 清理时，提示并入编制指引（与生成链同口径）。"""
    old = "投资收益【下表中不适用的项目，删除】"
    templates = [_t("八", "财务报表主要项目注释", "c8", None, 1, 800),
                 {**_t("八、70", "投资收益", "c8-70", "c8", 2, 870, 70), "title_hint": "下表中不适用的项目，删除"}]
    seeds = {"八、70": {"section_title": "投资收益", "legacy_titles": [old]}}

    def plan_for(**kw):
        rows = [_row("c8", "八", "财务报表主要项目注释", section_id="c8", parent_section_id=None, level=1,
                     sort_order=800, sort_index=0),
                NoteRow(id="ii", note_section="八、70", section_title=kw.pop("title", old), section_id="c8-70",
                        parent_section_id="c8", level=2, sort_order=870, sort_index=70, **kw)]
        return plan_realignment(rows, templates, template_type="soe", report_scope="standalone", seeds=seeds)

    plan = plan_for(account_name=old)
    assert plan.tree_updates == [{"note_id": "ii", "note_section": "八、70", "changes": {
        "section_title": [old, "投资收益"], "guidance_text": [None, "标题提示：下表中不适用的项目，删除"],
        "account_name": [old, "投资收益"]}}]
    kept_guidance = plan_for(guidance_text="请核对本期金额").tree_updates[0]["changes"]["guidance_text"]
    assert kept_guidance == ["请核对本期金额", "标题提示：下表中不适用的项目，删除\n\n请核对本期金额"]
    assert "guidance_text" not in plan_for(guidance_text="提示：下表中不适用的项目，删除").tree_updates[0]["changes"]
    assert plan_for(title="投资收益（审计师改）").tree_updates == []  # 人工标题不动，提示也不搬


def test_section_ids_swapped_both_fixed_and_custom_child_follows() -> None:
    rows = [r for r in _aligned() if r.note_section not in ("八、5", "八、16")]
    rows += [_row("ar", "八、5", "应收账款", section_id="c8-16"), _row("odi", "八、16", "其他债权投资", section_id=None),
             NoteRow(id="custom", note_section="八、5补充", section_title="应收账款补充说明", section_id="x-1",
                     parent_section_id="c8-16", level=3, sort_order=806)]
    plan = _plan(rows)
    assert plan.sid_conflicts == []
    sids = {u["note_id"]: u["changes"]["section_id"] for u in plan.tree_updates}
    assert sids == {"ar": ["c8-16", "c8-5"], "odi": [None, "c8-16"]}
    assert plan.child_reparents == [{"note_id": "custom", "note_section": "八、5补充", "old": "c8-16", "new": "c8-5"}]
    assert plan.orphan_unmatched == []  # 自建节挂在树上：不是脱树行


def test_section_id_held_by_custom_row_is_not_stolen() -> None:
    rows = [r for r in _aligned() if r.note_section != "八、5"]
    rows += [_row("ar", "八、5", "应收账款", section_id=None),
             NoteRow(id="custom", note_section="八、自定义", section_title="自定义", section_id="c8-5",
                     parent_section_id="c8", level=2, sort_order=890)]
    plan = _plan(rows)
    assert plan.sid_conflicts == [{"note_id": "ar", "note_section": "八、5", "section_id": "c8-5",
                                   "holders": ["custom"]}]
    assert all("section_id" not in u["changes"] for u in plan.tree_updates)


def test_missing_sections_inserted_in_template_order() -> None:
    rows = [r for r in _aligned() if r.note_section not in ("八", "八、16")]
    assert _plan(rows).inserts == ["八", "八、16"]


def test_truncated_orphan_rehanged_by_title_when_target_is_free() -> None:
    rows = [r for r in _aligned() if r.note_section != "八、16"]
    rows.append(NoteRow(id="trunc", note_section="八、其他债权", section_title="其他债权投资"))
    plan = _plan(rows)
    assert plan.rehangs == [{"note_id": "trunc", "old": "八、其他债权", "new": "八、16", "title": "其他债权投资"}]
    assert plan.inserts == []  # 改挂后该编号已有行
    upd = next(u for u in plan.tree_updates if u["note_id"] == "trunc")
    assert upd["note_section"] == "八、16" and upd["changes"]["section_id"] == [None, "c8-16"]


def test_orphan_conflict_reports_content_difference_and_unmatched_reports_other_scope() -> None:
    rows = _aligned() + [
        NoteRow(id="trunc", note_section="八、其他债权", section_title="其他债权投资", text_hash="a", table_hash="t"),
        NoteRow(id="c13", note_section="十三", section_title="承诺事项", section_id="s13"),
        NoteRow(id="c13-1", note_section="十三、1", section_title="按照有关财务会计制度应披露的其他内容",
                section_id="s13-1", parent_section_id="s13"),
    ]
    plan = _plan(rows)
    assert plan.rehangs == []
    assert plan.orphan_conflicts == [{"note_id": "trunc", "note_section": "八、其他债权", "title": "其他债权投资",
                                      "matched": "八、16", "holder_id": "r-八、16", "holder_deleted": False,
                                      "same_text": False, "same_table": False}]
    unmatched = {u["note_id"]: (u["candidates"], u["other_scope"]) for u in plan.orphan_unmatched}
    # 十三、1 的上级（十三）自己也脱树 ⇒ 一并报告，不当成「挂在树上的自建节」
    assert unmatched == {"c13": ([], True), "c13-1": ([], False)}


def test_related_rows_follow_code_changes_and_addr_collision_is_reported() -> None:
    rows = [r for r in _aligned() if r.note_section != DIT]
    rows.append(_row("old-dit", DIT_OLD, "递延所得税资产及递延所得税负债", section_id="c4-dit"))
    related = [
        RelatedRow("formula_push_state", "f1", DIT_OLD, f"note://{DIT_OLD}/递延所得税资产/合计.end"),
        RelatedRow("formula_push_state", "f2", DIT_OLD, f"note://{DIT_OLD}/递延所得税负债/合计.end"),
        RelatedRow("formula_push_state", "f3", DIT, f"note://{DIT}/递延所得税负债/合计.end"),  # 新地址已存在
        RelatedRow("note_section_instances", "i1", DIT_OLD),
        RelatedRow("note_section_locks", "l1", DIT_OLD),
    ]
    plan = _plan(rows, related)
    assert [(u["table"], u["id"], u["new"], u["new_addr_id"]) for u in plan.related_updates] == [
        ("formula_push_state", "f1", DIT, f"note://{DIT}/递延所得税资产/合计.end"),
        ("note_section_instances", "i1", DIT, None), ("note_section_locks", "l1", DIT, None)]
    assert plan.related_conflicts == [{"table": "formula_push_state", "id": "f2",
                                       "addr_id": f"note://{DIT_OLD}/递延所得税负债/合计.end",
                                       "new_addr_id": f"note://{DIT}/递延所得税负债/合计.end"}]


def test_plan_on_planned_result_is_empty() -> None:
    """幂等的纯函数版：把计划套到行快照上再算一次，动作必须为 0（执行版见 SQLite 用例）。"""
    rows = [r for r in _aligned() if r.note_section not in (DIT, "八、16", "十四")]
    rows += [_row("old-dit", DIT_OLD, "递延所得税资产及递延所得税负债", section_id=None, parent_section_id=None),
             NoteRow(id="trunc", note_section="八、其他债权", section_title="其他债权投资"),
             _row("c14", "十四", "其他重要事项")]
    plan = _plan(rows)
    assert plan.action_count() > 0
    by_id = {r.id: r for r in rows}
    for c in (*plan.renames, *plan.rehangs):
        by_id[c["note_id"]] = NoteRow(**{**by_id[c["note_id"]].__dict__, "note_section": c["new"]})
    for u in plan.tree_updates:
        by_id[u["note_id"]] = NoteRow(**{**by_id[u["note_id"]].__dict__,
                                         **{f: new for f, (_o, new) in u["changes"].items()}})
    after = list(by_id.values()) + [_row(f"new-{c}", c, next(t["section_title"] for t in TEMPLATES
                                                               if t["note_section"] == c)) for c in plan.inserts]
    assert _plan(after).action_count() == 0


# ── 执行：真 SQLite + 真 ORM + 真生成链（只替换取数与构表）────────────────────

import copy  # noqa: E402
import json  # noqa: E402
import uuid  # noqa: E402
from datetime import datetime, timezone  # noqa: E402

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
import sqlalchemy as sa  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402

from app.models.base import Base, UserRole  # noqa: E402
from app.models.core import Project, User  # noqa: E402
from app.models.dataset_models import LedgerDataset  # noqa: E402
from app.models.formula_push_models import FormulaPushState  # noqa: E402
from app.models.note_trim_models import NoteSectionInstance  # noqa: E402
from app.models.phase16_models import VersionLineStamp  # noqa: E402
from app.models.report_models import DisclosureNote  # noqa: E402
from app.services.disclosure_engine import DisclosureEngine  # noqa: E402
from app.services.note_project_realign_apply import LOCKS, RealignSkipped, build_plan, realign_project  # noqa: E402

YEAR = 2025
STAMP = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
WIZARD = {"steps": {"basic_info": {"data": {"template_type": "soe", "report_scope": "standalone"}}}}


@pytest_asyncio.fixture
async def db(monkeypatch):
    async def _no_preload(self, _pid, _yr):
        self._prior_notes_cache = {}

    async def _no_table(self, *_a, **_k):
        return None

    monkeypatch.setattr(DisclosureEngine, "_preload_data_for_notes", _no_preload)
    monkeypatch.setattr(DisclosureEngine, "_build_section_table_data", _no_table)
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    tables = [User.__table__, Project.__table__, DisclosureNote.__table__, FormulaPushState.__table__,
              NoteSectionInstance.__table__, LedgerDataset.__table__, VersionLineStamp.__table__]
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
        await conn.run_sync(LOCKS.create)
    async with async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)() as session:
        yield session
    await engine.dispose()


async def _seed(db: AsyncSession) -> dict:
    user = User(id=uuid.uuid4(), username="editor", email="editor@example.com", hashed_password="x",
                role=UserRole.auditor)
    pid = uuid.uuid4()
    db.add_all([user, Project(id=pid, name="对齐甲_2025", client_name="对齐甲", template_type="soe",
                              report_scope="standalone", wizard_state=WIZARD)])
    await db.flush()
    templates = await DisclosureEngine(db)._load_templates(pid, "soe")
    by = {t["note_section"]: t for t in templates}
    skip = {DIT, "四、记账基础和计价原则", "八、90", "十、销售退回"}
    ids: dict[str, uuid.UUID] = {}

    def add(key: str, code: str, title: str, **kw) -> None:
        ids[key] = uuid.uuid4()
        db.add(DisclosureNote(id=ids[key], project_id=pid, year=YEAR, note_section=code, section_title=title,
                              updated_by=user.id, updated_at=STAMP, **kw))

    for t in templates:
        if t["note_section"] in skip:
            continue
        add(t["note_section"], t["note_section"], "其他重要事项" if t["note_section"] == "十四" else t["section_title"],
            section_id=t["section_id"], parent_section_id=t["parent_section_id"], level=t["level"],
            sort_index=t["sort_index"] or 0, sort_order=t["sort_order"])
    add("dit", DIT_OLD, "递延所得税资产及递延所得税负债", section_id=by[DIT]["section_id"],
        parent_section_id="chapter-06-shui-xiang", level=2, sort_index=0, sort_order=600,
        text_content="<p>递延正文</p>", table_data={"rows": [{"label": "递延所得税资产", "values": [12.5]}]})
    add("trunc", "四、记账基础和计价原", "记账基础和计价原则", text_content="<p>权责发生制</p>")
    add("gone", "十、销售退回", "销售退回", is_deleted=True)
    add("custom", "八、自定义说明", "自定义说明", section_id="u-1", parent_section_id=by["八"]["section_id"],
        level=2, sort_order=899)
    db.add(FormulaPushState(project_id=pid, year=YEAR, addr_id=f"note://{DIT_OLD}/递延所得税资产/合计.end",
                            rule_id="r1", domain="note", note_section=DIT_OLD, state="auto"))
    await db.commit()
    return {"pid": pid, "user": user.id, "ids": ids, "templates": by}


@pytest.mark.asyncio
async def test_apply_realigns_inserts_and_is_idempotent(db: AsyncSession) -> None:
    s = await _seed(db)
    pid, ids, by = s["pid"], s["ids"], s["templates"]
    report = await realign_project(db, pid, YEAR, apply=True)
    await db.commit()
    assert report["after"]["inserts"] == 0 and report["plan"]["counts"]["inserts"] == 1  # 八、90（销售退回被软删行占着）

    plan, rows, _meta = await build_plan(db, pid, YEAR)
    assert plan.action_count() == 0, plan.counts()
    notes = {n.id: n for n in (await db.execute(sa.select(DisclosureNote).where(
        DisclosureNote.project_id == pid))).scalars()}
    dit, trunc, c14 = notes[ids["dit"]], notes[ids["trunc"]], notes[ids["十四"]]
    assert (dit.note_section, dit.parent_section_id, dit.sort_order) == (
        DIT, by[DIT]["parent_section_id"], by[DIT]["sort_order"])
    assert dit.text_content == "<p>递延正文</p>" and dit.table_data == {"rows": [{"label": "递延所得税资产",
                                                                                  "values": [12.5]}]}
    assert (trunc.note_section, trunc.section_id) == ("四、记账基础和计价原则", by["四、记账基础和计价原则"]["section_id"])
    assert c14.section_title == "财务报表之批准"
    # 系统修复不算用户编辑：编辑人与更新时间原样
    assert {(n.updated_by, n.updated_at.replace(tzinfo=timezone.utc)) for i, n in notes.items()
            if i in ids.values()} == {(s["user"], STAMP)}
    new = [n for n in notes.values() if n.id not in ids.values()]
    assert [(n.note_section, n.section_id, n.is_deleted) for n in new] == [("八、90", by["八、90"]["section_id"], False)]
    assert [n.is_deleted for n in notes.values() if n.note_section == "十、销售退回"] == [True]
    assert notes[ids["custom"]].parent_section_id == by["八"]["section_id"]
    fps = (await db.execute(sa.select(FormulaPushState))).scalar_one()
    assert (fps.note_section, fps.addr_id) == (DIT, f"note://{DIT}/递延所得税资产/合计.end")
    assert sum(not r.is_deleted for r in rows) == len(by) - 1 + 1  # 模板 - 软删占位 + 自建


@pytest.mark.asyncio
async def test_dry_run_writes_nothing(db: AsyncSession) -> None:
    s = await _seed(db)
    before = (await db.execute(sa.select(DisclosureNote.id, DisclosureNote.note_section, DisclosureNote.section_title,
                                         DisclosureNote.sort_order))).all()
    report = await realign_project(db, s["pid"], YEAR, apply=False)
    await db.rollback()
    assert report["plan"]["counts"]["renames"] == 1 and "after" not in report
    after = (await db.execute(sa.select(DisclosureNote.id, DisclosureNote.note_section, DisclosureNote.section_title,
                                        DisclosureNote.sort_order))).all()
    assert sorted(after) == sorted(before)


@pytest.mark.asyncio
async def test_deleted_project_is_skipped(db: AsyncSession) -> None:
    s = await _seed(db)
    (await db.get(Project, s["pid"])).is_deleted = True
    await db.commit()
    with pytest.raises(RealignSkipped, match="已删除"):
        await realign_project(db, s["pid"], YEAR, apply=True)


# ── 生成链补章入口：only_sections / strict / 软删编号不新建 ──────────────────


@pytest.mark.asyncio
async def test_generate_only_sections_touches_nothing_else(db: AsyncSession) -> None:
    s = await _seed(db)
    pid, ids = s["pid"], s["ids"]
    other = await db.get(DisclosureNote, ids["八、1"])
    other.text_content = "<p>用户写的货币资金正文</p>"
    await db.commit()
    created = await DisclosureEngine(db).generate_notes(pid, YEAR, "soe", only_sections={"八、90"}, strict=True)
    await db.commit()
    assert [c["note_section"] for c in created] == ["八、90"]
    await db.refresh(other)
    assert other.text_content == "<p>用户写的货币资金正文</p>" and other.updated_by == s["user"]


@pytest.mark.asyncio
async def test_generate_does_not_recreate_soft_deleted_code(db: AsyncSession) -> None:
    """唯一索引含软删行：旧实现查不到活动行就 INSERT ⇒ 撞键整次生成失败（删章 / 裁剪后再点「生成附注」必 500）。"""
    s = await _seed(db)
    created = await DisclosureEngine(db).generate_notes(s["pid"], YEAR, "soe", only_sections={"十、销售退回"})
    await db.commit()
    assert created == []
    rows = (await db.execute(sa.select(DisclosureNote.is_deleted).where(
        DisclosureNote.project_id == s["pid"], DisclosureNote.note_section == "十、销售退回"))).scalars().all()
    assert rows == [True]


@pytest.mark.asyncio
async def test_generate_strict_raises_instead_of_degrading(db: AsyncSession, monkeypatch) -> None:
    s = await _seed(db)

    async def _boom(self, *_a, **_k):
        raise RuntimeError("构表失败")

    monkeypatch.setattr(DisclosureEngine, "_build_section_table_data", _boom)
    with pytest.raises(RuntimeError, match="构表失败"):
        await DisclosureEngine(db).generate_notes(s["pid"], YEAR, "soe", only_sections={"八、90"}, strict=True)
    await db.rollback()
    created = await DisclosureEngine(db).generate_notes(s["pid"], YEAR, "soe", only_sections={"八、90"})
    assert [c["note_section"] for c in created] == ["八、90"]  # 非 strict：照旧降级为无表


@pytest.mark.asyncio
async def test_apply_refuses_when_content_of_existing_rows_changes(db: AsyncSession, monkeypatch) -> None:
    """执行后已有行正文 / 表格哈希必须逐行不变：执行层若顺手改了内容（这里注入一处）⇒ 抛错，调用方回滚。"""
    import app.services.note_project_realign_apply as mod
    from app.services.note_project_realign_apply import RealignError

    s = await _seed(db)
    real_apply = mod.apply_plan

    async def _apply_and_touch(db_, project_id, year, plan, template_type):
        await real_apply(db_, project_id, year, plan, template_type)
        await db_.execute(sa.update(DisclosureNote.__table__).where(
            DisclosureNote.__table__.c.id == s["ids"]["trunc"]).values(text_content="<p>被改了</p>"))

    monkeypatch.setattr(mod, "apply_plan", _apply_and_touch)
    with pytest.raises(RealignError, match="正文或表格被改动"):
        await realign_project(db, s["pid"], YEAR, apply=True)


@pytest.mark.asyncio
async def test_apply_refuses_when_plan_is_not_fully_applied(db: AsyncSession, monkeypatch) -> None:
    """执行后必须重算计划且为空：执行层漏做（这里注入「什么都不做」）⇒ 抛「不幂等」，不能静默提交半套结果。"""
    import app.services.note_project_realign_apply as mod
    from app.services.note_project_realign_apply import RealignError

    s = await _seed(db)

    async def _noop(*_a, **_k):
        return None

    monkeypatch.setattr(mod, "apply_plan", _noop)
    with pytest.raises(RealignError, match="不幂等"):
        await realign_project(db, s["pid"], YEAR, apply=True)


@pytest.mark.asyncio
async def test_apply_aborts_when_inserted_section_cannot_be_built(db: AsyncSession, monkeypatch) -> None:
    """补章走 strict：构表失败 ⇒ 整个项目回滚，而不是补出一张没有表格的空章还报成功。"""
    s = await _seed(db)

    async def _boom(self, *_a, **_k):
        raise RuntimeError("构表失败")

    monkeypatch.setattr(DisclosureEngine, "_build_section_table_data", _boom)
    with pytest.raises(RuntimeError, match="构表失败"):
        await realign_project(db, s["pid"], YEAR, apply=True)


# ── 表格结构搬值（Task 12，design §4.2）：真 SQLite + 真 ORM ──────────────────

#: 控制用的现行种子表：节 八、1 一张货币资金表（结构 = 期末 / 期初，无 values）
_SEED_TABLES = {
    "八、1": [{"name": "货币资金", "headers": ["项目", "期末余额", "期初余额"],
              "columns": [{"key": "label", "is_label": True}, {"key": "end"}, {"key": "begin"}],
              "rows": [{"label": "库存现金"}, {"label": "银行存款"}, {"label": "合计", "is_total": True}]}],
}


async def _seed_tables_for_realign(db: AsyncSession, project_id: uuid.UUID):
    return _SEED_TABLES


@pytest_asyncio.fixture
async def table_project(db: AsyncSession, monkeypatch):
    """一个最小项目：八、1 库内表列顺序颠倒 + 多一列孤儿值；返回 pid / note_id / 搬前 table_data。"""
    import app.services.note_project_realign_apply as mod

    monkeypatch.setattr(mod, "_seed_tables_by_code", _seed_tables_for_realign)
    user = User(id=uuid.uuid4(), username="e2", email="e2@example.com", hashed_password="x", role=UserRole.auditor)
    pid = uuid.uuid4()
    db.add_all([user, Project(id=pid, name="搬值甲_2025", client_name="搬值甲", template_type="soe",
                              report_scope="standalone")])
    # 库内：列顺序 = 期初、期末、本年增减（种子只有期末 / 期初）；银行存款行有一个孤儿列值 50
    td = {"_tables": [{"name": "货币资金", "headers": ["项目", "期初余额", "期末余额", "本年增减"],
                       "rows": [{"label": "库存现金", "values": [200, 100, 5], "_cell_modes": {"1": "manual"}},
                                {"label": "银行存款", "values": [400, 300, 50]},
                                {"label": "合计", "values": [600, 400, 55], "is_total": True}]}]}
    nid = uuid.uuid4()
    db.add(DisclosureNote(id=nid, project_id=pid, year=YEAR, note_section="八、1", section_title="货币资金",
                          text_content="<p>货币资金正文</p>", table_data=td, updated_by=user.id, updated_at=STAMP))
    await db.commit()
    return {"pid": pid, "nid": nid, "user": user.id, "td": td}


@pytest.mark.asyncio
async def test_table_dry_run_reports_orphans_and_safety(table_project, db: AsyncSession) -> None:
    from app.services.note_project_realign_apply import plan_table_realignment

    report = await plan_table_realignment(db, table_project["pid"], YEAR)
    await db.rollback()
    assert report["compared_sections"] == 1 and report["unsafe_sections"] == 0
    assert report["changed_sections"] == 1  # 列顺序变了
    # 本年增减列 3 个非空值成孤儿
    assert report["orphan_values"] == 3
    assert report["orphans"][0]["note_section"] == "八、1"


@pytest.mark.asyncio
async def test_table_apply_carries_values_keeps_text_and_stamp(table_project, db: AsyncSession) -> None:
    from app.services.note_project_realign_apply import apply_table_realignment

    report = await apply_table_realignment(db, table_project["pid"], YEAR)
    await db.commit()
    assert report["written_sections"] == 1 and report["orphan_values"] == 3
    note = await db.get(DisclosureNote, table_project["nid"])
    tbl = note.table_data["_tables"][0]
    # 新结构 headers = 期末、期初 ⇒ 值按表头搬正
    assert tbl["headers"] == ["项目", "期末余额", "期初余额"]
    assert [r["values"] for r in tbl["rows"]] == [[100, 200], [300, 400], [400, 600]]
    # 边车随值搬（库内「期末」是列索引 1 → 新结构列索引 0）
    assert tbl["rows"][0]["_cell_modes"] == {"0": "manual"}
    orphans = note.table_data["_realign_orphans"]
    assert sorted(v for o in orphans for v in o["values"]) == [5, 50, 55]
    # 正文与编辑人原样（搬值不算用户编辑、不碰正文）
    assert note.text_content == "<p>货币资金正文</p>"
    assert note.updated_by == table_project["user"]


@pytest.mark.asyncio
async def test_table_apply_idempotent(table_project, db: AsyncSession) -> None:
    from app.services.note_project_realign_apply import apply_table_realignment, plan_table_realignment

    await apply_table_realignment(db, table_project["pid"], YEAR)
    await db.commit()
    # 再搬一次：结构已对齐、值在正确落点、孤儿区已固化 ⇒ 预演 0 节、写入 0 节
    plan = await plan_table_realignment(db, table_project["pid"], YEAR)
    await db.rollback()
    assert plan["changed_sections"] == 0 and plan["orphan_values"] == 3
    report = await apply_table_realignment(db, table_project["pid"], YEAR)
    await db.commit()
    assert report["written_sections"] == 0


@pytest_asyncio.fixture
async def two_section_project(db: AsyncSession, monkeypatch):
    """八、1 列序颠倒（要写）+ 八、2 只差种子元数据（不该写）；顶层都带首表镜像（生成链形态）。"""
    import app.services.note_project_realign_apply as mod

    seed_other = {"name": "其他流动资产", "headers": ["项目", "期末余额", "期初余额"],
                  "columns": [{"key": "label", "is_label": True}, {"key": "end"}, {"key": "begin"}],
                  "text_after_table": "注：……",
                  "rows": [{"label": "待抵扣进项税额", "account_codes": ["2221"]}, {"label": "合计", "is_total": True}]}

    async def _seeds(_db, _pid):
        return {**_SEED_TABLES, "八、2": [seed_other]}

    monkeypatch.setattr(mod, "_seed_tables_by_code", _seeds)
    pid = uuid.uuid4()
    db.add(Project(id=pid, name="搬值乙_2025", client_name="搬值乙", template_type="soe", report_scope="standalone"))

    def _with_mirror(tbl: dict) -> dict:
        return {"name": tbl["name"], "headers": tbl["headers"], "rows": copy.deepcopy(tbl["rows"]),
                "_tables": [tbl], "_source": "workpaper"}

    money = {"name": "货币资金", "headers": ["项目", "期初余额", "期末余额"],
             "rows": [{"label": "库存现金", "values": [200, 100]}, {"label": "银行存款", "values": [400, 300]},
                      {"label": "合计", "values": [600, 400], "is_total": True}]}
    other = {"name": "其他流动资产", "headers": ["项目", "期末余额", "期初余额"],
             "rows": [{"label": "待抵扣进项税额", "values": [5, None], "is_total": False, "_cell_modes": {}},
                      {"label": "合计", "values": [5, 0], "is_total": True, "_cell_meta": {}}]}
    ids = {"八、1": uuid.uuid4(), "八、2": uuid.uuid4()}
    tds = {"八、1": _with_mirror(money), "八、2": _with_mirror(other)}
    for code, nid in ids.items():
        db.add(DisclosureNote(id=nid, project_id=pid, year=YEAR, note_section=code, section_title=code,
                              text_content=f"<p>{code}</p>", table_data=tds[code]))
    await db.commit()
    return {"pid": pid, "ids": ids, "tds": copy.deepcopy(tds)}


@pytest.mark.asyncio
async def test_table_apply_writes_only_visible_changes_and_keeps_mirror(two_section_project, db: AsyncSession) -> None:
    """回归（2026-10-31 真库）：预演报 5 节，写入却按整节哈希写了 104 节（只差种子元数据也重写）。"""
    from app.services.note_project_realign_apply import apply_table_realignment, plan_table_realignment

    p = two_section_project
    plan = await plan_table_realignment(db, p["pid"], YEAR)
    await db.rollback()
    assert plan["compared_sections"] == 2 and plan["changed_sections"] == 1
    report = await apply_table_realignment(db, p["pid"], YEAR)
    await db.commit()
    assert report["written_sections"] == plan["changed_sections"] == 1
    untouched = await db.get(DisclosureNote, p["ids"]["八、2"], populate_existing=True)
    assert json.dumps(untouched.table_data, sort_keys=True) == json.dumps(p["tds"]["八、2"], sort_keys=True)
    moved = (await db.get(DisclosureNote, p["ids"]["八、1"], populate_existing=True)).table_data
    assert [r["values"] for r in moved["_tables"][0]["rows"]] == [[100, 200], [300, 400], [400, 600]]
    # 首表镜像随新首表重建，其他顶层键保留
    assert moved["rows"] == moved["_tables"][0]["rows"] and moved["headers"] == ["项目", "期末余额", "期初余额"]
    assert moved["_source"] == "workpaper"
    again = await plan_table_realignment(db, p["pid"], YEAR)
    await db.rollback()
    assert again["changed_sections"] == 0


@pytest.mark.asyncio
async def test_table_apply_refuses_when_text_changes(table_project, db: AsyncSession, monkeypatch) -> None:
    """正文哈希逐行不变断言：搬值过程中若正文被动过 ⇒ 抛错回滚。

    注入 ``_active_sections`` 的「after」读（无锁那次）返回被改过的正文，证明正文守卫会打红。
    """
    import app.services.note_project_realign_apply as mod
    from app.services.note_project_realign_apply import RealignError, apply_table_realignment

    real_active = mod._active_sections

    async def _active_with_text_drift(db_, pid, yr, *, lock=False):
        rows = await real_active(db_, pid, yr, lock=lock)
        if not lock:  # 第二次读（after）：伪造正文漂移
            return [(i, c, td, (text or "") + "X") for i, c, td, text in rows]
        return rows

    monkeypatch.setattr(mod, "_active_sections", _active_with_text_drift)
    with pytest.raises(RealignError, match="正文被改动"):
        await apply_table_realignment(db, table_project["pid"], YEAR)


@pytest.mark.asyncio
async def test_table_apply_refuses_when_result_is_not_a_fixed_point(table_project, db: AsyncSession,
                                                                     monkeypatch) -> None:
    """写完按同一判据重算必须 0 节：注入「写进去的结果再搬还会变」（多一行占位空行）⇒ 不幂等，整体回滚。"""
    import app.services.note_project_table_realign as kernel
    from app.services.note_project_realign_apply import RealignError, apply_table_realignment

    real = kernel.realign_section_tables
    calls = {"n": 0}

    def _unstable(td, seed):
        out = real(td, seed)
        calls["n"] += 1
        if calls["n"] == 1:  # 写入那次多塞一行空占位行（值全空，multiset 不变）
            out["_tables"][0]["rows"].append({"label": "", "values": [None, None]})
        return out

    monkeypatch.setattr(kernel, "realign_section_tables", _unstable)
    with pytest.raises(RealignError, match="不幂等"):
        await apply_table_realignment(db, table_project["pid"], YEAR)
    await db.rollback()
    note = await db.get(DisclosureNote, table_project["nid"], populate_existing=True)
    assert note.table_data == table_project["td"]


@pytest.mark.asyncio
async def test_table_apply_refuses_orphans_when_disallowed(table_project, db: AsyncSession) -> None:
    from app.services.note_project_realign_apply import RealignError, apply_table_realignment

    with pytest.raises(RealignError, match="孤儿"):
        await apply_table_realignment(db, table_project["pid"], YEAR, allow_orphans=False)


def test_account_name_follows_known_system_title_but_manual_name_is_preserved() -> None:
    rows = [r for r in _aligned() if r.note_section != "十四"]
    rows.append(_row("system", "十四", "其他重要事项", account_name="其他重要事项"))
    plan = _plan(rows)
    update = next(item for item in plan.tree_updates if item["note_id"] == "system")
    assert update["changes"] == {
        "section_title": ["其他重要事项", "财务报表之批准"],
        "account_name": ["其他重要事项", "财务报表之批准"],
    }

    rows[-1] = _row("manual", "十四", "其他重要事项", account_name="审计师自定义名称")
    plan = _plan(rows)
    update = next(item for item in plan.tree_updates if item["note_id"] == "manual")
    assert update["changes"] == {"section_title": ["其他重要事项", "财务报表之批准"]}
    assert plan.account_names_kept == [{
        "note_id": "manual", "note_section": "十四", "account_name": "审计师自定义名称",
        "template_account_name": "财务报表之批准",
    }]
