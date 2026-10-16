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
