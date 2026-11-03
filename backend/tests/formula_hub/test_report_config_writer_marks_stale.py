"""定义写入出口同事务标过期（spec formula-hub-integrity-closure 任务 15；需求 5.1 写入部分；ADR-FHIC-04；F49）。

三个出口（报表域）：全局发布 ``publish_global``、项目适配保存 ``save_overrides``、恢复全局 ``restore_global``，在各自事务内
调用 ``report_freshness.mark_changed``：有效定义真正变化的行 ∪ 经 ``ROW`` / ``SUM_ROW`` 直接或间接引用它们的行，在该项目
**全部年度**标过期。生产函数一律不 mock（SQLite 真 ORM，``tests/formula_settings/_env``）；只调服务层、不经路由的 ``_emit``
⇒ 提交后的 ``propagate_report`` 不参与，看到的标记只来自出口本身。

夹具（:func:`_world`）：准则 ``soe_standalone`` 六行（:func:`_definitions`）—— BS-002 是被改的行；合计行 BS-010 =
``SUM_ROW('BS-001','BS-003')``（区间引用 BS-002）；BS-020 = ``ROW('BS-010')+ROW('BS-030')``（间接引用）；BS-001 / BS-003 /
BS-030 不在闭包。六类项目（对 BS-002）：follow 无本项目适配（跟随全局）/ follow_copy 跟随副本（本项目行 = 基线）/
override 本项目覆盖 / pinned 固定在更早的全局 / template 订阅模板（真模板 + 真订阅，模板层优先）/ frozen 已归档。
每个项目两个年度各一套未过期报表行 + 一条已删行。判定（:func:`_check`）：

- 「有效定义变化」= 出口前后 ``load_effective_formulas`` 的 BS-002 公式不同（现读），先断言它等于 F49 / 现读代码的预期，
  再断言变化项目被标的行 = 闭包 × 两个年度，其余项目（都有报表行）一行未标，已删行未标；
- 全局发布：follow / follow_copy 变，override（交确认）/ pinned（暂缓）/ template（跳过）/ frozen 不变；
  项目适配保存：只有保存的项目变（与现行有效定义相同 ⇒ 不变）；
  恢复全局：override / pinned 变，follow（无适配）/ follow_copy（= 全局）/ template（回到模板定义）不变；
- 「BS-002 变化 ⇒ 引用它的合计行同事务标过期」：三个出口各一例，提交前同一会话已看到合计行与间接引用行过期，
  回滚后全部复原（标记只 flush、随出口事务回滚）；
- 真 PG（``pg_only``，快照库 ``pg_tx``，结束回滚）：PG 方言 ``row_code = ANY(:closure)`` 下两个项目侧出口与直接调用同口径。

变异（design §10.4）：#21 标过期改为「该准则全部项目」⇒ 矩阵用例红（override / pinned 等不该标的项目被标）；
#22 ``mark_changed`` 不扩闭包 ⇒ 合计行用例红。
"""
from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql, sqlite

from app.models.base import ProjectStatus, ProjectType
from app.models.core import Project
from app.models.report_models import FinancialReport
from app.services import report_freshness as rf
from app.services.formula_settings import template_service, template_sync
from app.services.formula_settings.project_ops import restore_global, save_overrides
from app.services.formula_settings.publish import publish_global
from app.services.formula_settings.stores import get_store
from app.services.formula_settings.template_access import Viewer
from tests.formula_hub._pg_harness import TEST_PROJECT_PREFIX
from tests.formula_settings._env import BS, STD, add_global_row, add_project, add_project_row, add_user, make_db

SLOT = "balance_sheet:BS-002"
G_PREV = "TB('1002','年初余额')"  # 更早的全局：pinned 项目固定在它
G_OLD = "TB('1002','期末余额')"  # 现行全局
G_NEW = "TB('1002','期末余额')+TB('1012','期末余额')"  # 本次全局发布
MINE = "TB('1002','期末余额')*2"  # 本项目覆盖
TPL = "TB('1002','期末余额')*3"  # 模板定义
LOCAL_NEW = "TB('1002','期末余额')*4"  # 项目适配保存的新公式
YEARS = (2024, 2025)
DELETED_YEAR = 2023
KINDS = ("follow", "follow_copy", "override", "pinned", "template", "frozen")
WRITABLE = KINDS[:-1]  # 已归档项目不能保存 / 恢复（423）
EFFECTIVE = {"follow": G_OLD, "follow_copy": G_OLD, "override": MINE, "pinned": G_PREV, "template": TPL,
             "frozen": G_OLD}
#: 恢复全局后 BS-002 的有效定义是否变化（现读 restore_global：无适配跳过、模板位回到模板定义）
RESTORE_CHANGES = {"follow": False, "follow_copy": False, "override": True, "pinned": True, "template": False}


def _definitions(prefix: str) -> dict[str, str]:
    c = {n: f"{prefix}-{n:03d}" for n in (1, 2, 3, 10, 20, 30)}
    return {c[1]: "TB('1001','期末余额')", c[2]: G_OLD, c[3]: "TB('1003','期末余额')",
            c[10]: f"SUM_ROW('{c[1]}','{c[3]}')", c[20]: f"ROW('{c[10]}')+ROW('{c[30]}')", c[30]: f"ROW('{c[1]}')"}


def _closure_rows(prefix: str) -> set[tuple[int, str]]:
    return {(year, f"{prefix}-{n:03d}") for year in YEARS for n in (2, 10, 20)}


GLOBAL_ROWS = _definitions("BS")
CLOSURE_ROWS = _closure_rows("BS")


def _add_report_rows(db, project_id: uuid.UUID, codes, changed_code: str) -> None:
    db.add_all([FinancialReport(project_id=project_id, year=year, report_type=BS, row_code=code, row_name=code,
                                is_stale=False, calc_version=rf.CALC_VERSION) for year in YEARS for code in codes])
    db.add(FinancialReport(project_id=project_id, year=DELETED_YEAR, report_type=BS, row_code=changed_code,
                           row_name="已删", is_deleted=True))


async def _world(db) -> dict[str, uuid.UUID]:
    for number, (code, formula) in enumerate(GLOBAL_ROWS.items(), 1):
        await add_global_row(db, code, formula, row_number=number)
    p: dict[str, uuid.UUID] = {}
    for kind in KINDS:
        status = ProjectStatus.archived if kind == "frozen" else ProjectStatus.execution
        p[kind] = await add_project(db, f"{TEST_PROJECT_PREFIX}fh15_{kind}", status=status)
    await add_project_row(db, p["follow_copy"], "BS-002", G_OLD, base_formula=G_OLD)
    await add_project_row(db, p["override"], "BS-002", MINE, base_formula=G_OLD)
    await add_project_row(db, p["pinned"], "BS-002", G_PREV, base_formula=G_PREV, pinned=True)
    owner = await add_user(db, "fh15_owner")
    tpl = await template_service.create_template(
        db, viewer=await Viewer.load(db, owner), name="fh15 模板", description=None, share_scope="personal",
        owner_project_id=None, applicable_scope=STD, source="manual", domains=["report"],
        items=[{"domain": "report", "slot_key": SLOT, "definition": {"formula": TPL}}])
    await template_sync.subscribe(db, project_id=p["template"], tpl=tpl, domain="report", decisions=None,
                                  user_id=owner.id)
    for pid in p.values():
        _add_report_rows(db, pid, GLOBAL_ROWS, "BS-002")
    await db.commit()
    counts = dict((await db.execute(sa.select(FinancialReport.project_id, sa.func.count())
                                    .group_by(FinancialReport.project_id))).all())
    assert counts == {pid: len(YEARS) * len(GLOBAL_ROWS) + 1 for pid in p.values()}  # 每类项目都有报表行
    return p


async def _effective(db, projects: dict[str, uuid.UUID]) -> dict[str, str | None]:
    """各项目 BS-002 的现行有效公式（准则行 ⊕ 本项目行，项目真实准则；与 mark_changed 同口径）。"""
    return {kind: (await rf.load_effective_formulas(db, pid)).get(("balance_sheet", "BS-002"))
            for kind, pid in projects.items()}


async def _stale(db, projects: dict[str, uuid.UUID]) -> dict[str, set[tuple[int, str]]]:
    """各项目已标过期的 (年度, 行次)；不过滤已删行（已删行被标也会出现在这里）。"""
    rows = (await db.execute(sa.select(FinancialReport.project_id, FinancialReport.year, FinancialReport.row_code)
                             .where(FinancialReport.project_id.in_(list(projects.values())),
                                    FinancialReport.is_stale == sa.true()))).all()
    kind_of = {pid: kind for kind, pid in projects.items()}
    out: dict[str, set[tuple[int, str]]] = {kind: set() for kind in projects}
    for pid, year, code in rows:
        out[kind_of[pid]].add((year, code))
    return out


def _assert_marked(stale: dict[str, set], changed: set[str], closure_rows: set[tuple[int, str]]) -> None:
    bystanders = {kind: sorted(rows) for kind, rows in stale.items() if kind not in changed and rows}
    assert not bystanders, f"有效定义未变的项目被标过期：{bystanders}"
    wrong = {kind: sorted(stale[kind] ^ closure_rows) for kind in sorted(changed) if stale[kind] != closure_rows}
    assert not wrong, f"有效定义变化的项目标过期的行与闭包 × 全部年度不符（对称差）：{wrong}"


async def _check(db, projects, before, expected_changed: set[str]) -> None:
    after = await _effective(db, projects)
    changed = {kind for kind in projects if after[kind] != before[kind]}
    assert changed == expected_changed, f"有效定义变化的项目 {sorted(changed)} ≠ 预期：{before} → {after}"
    _assert_marked(await _stale(db, projects), changed, CLOSURE_ROWS)


async def _local_version(db, project_id: uuid.UUID, slot: str = SLOT) -> int | None:
    local = (await get_store("report").list_project(db, project_id)).get(slot)
    return local.version if local is not None else None


# ─── 三出口 × 六类项目 ──────────────────────────────────────────────────────────


async def test_publish_global_marks_only_projects_whose_definition_changed():
    async with make_db() as factory, factory() as db:
        p = await _world(db)
        before = await _effective(db, p)
        assert before == EFFECTIVE
        result = await publish_global(db, domain="report", scope=STD, user_id=None, changes=[
            {"slot_key": SLOT, "definition": {"formula": G_NEW}, "expected_version": 1}])
        await _check(db, p, before, {"follow", "follow_copy"})
        # 同一份 changed_slots：提交后的传播事件与同事务标记覆盖同一批项目
        assert {e["project_id"] for e in result["events"]} == {str(p["follow"]), str(p["follow_copy"])}


@pytest.mark.parametrize("same", [False, True], ids=["changed", "same"])
@pytest.mark.parametrize("kind", WRITABLE)
async def test_save_overrides_marks_only_the_saving_project(kind, same):
    async with make_db() as factory, factory() as db:
        p = await _world(db)
        before = await _effective(db, p)
        formula, version = (EFFECTIVE[kind] if same else LOCAL_NEW), await _local_version(db, p[kind])
        await save_overrides(db, domain="report", project_id=p[kind], user_id=None, items=[
            {"slot_key": SLOT, "definition": {"formula": formula}, "expected_version": version}])
        await _check(db, p, before, set() if same else {kind})


@pytest.mark.parametrize("kind", WRITABLE)
async def test_restore_global_marks_only_when_definition_changes(kind):
    async with make_db() as factory, factory() as db:
        p = await _world(db)
        before = await _effective(db, p)
        await restore_global(db, domain="report", project_id=p[kind], slot_keys=[SLOT], user_id=None)
        await _check(db, p, before, {kind} if RESTORE_CHANGES[kind] else set())


# ─── BS-002 变化 ⇒ 引用它的合计行同事务标过期 ─────────────────────────────────────


async def _via_publish(db, p) -> str:
    await publish_global(db, domain="report", scope=STD, user_id=None, changes=[
        {"slot_key": SLOT, "definition": {"formula": G_NEW}, "expected_version": 1}])
    return "follow"


async def _via_save(db, p) -> str:
    await save_overrides(db, domain="report", project_id=p["follow"], user_id=None,
                         items=[{"slot_key": SLOT, "definition": {"formula": LOCAL_NEW}}])
    return "follow"


async def _via_restore(db, p) -> str:
    await restore_global(db, domain="report", project_id=p["override"], slot_keys=[SLOT], user_id=None)
    return "override"


EXITS = {"publish_global": _via_publish, "save_overrides": _via_save, "restore_global": _via_restore}


@pytest.mark.parametrize("exit_name", sorted(EXITS))
async def test_bs002_change_marks_total_rows_in_same_transaction(exit_name):
    async with make_db() as factory, factory() as db:
        p = await _world(db)
        kind = await EXITS[exit_name](db, p)
        stale = (await _stale(db, p))[kind]  # 未提交：同一会话（同一事务）里读
        assert stale == CLOSURE_ROWS, (f"合计行 / 间接引用行未同事务标过期：缺 {sorted(CLOSURE_ROWS - stale)}，"
                                       f"多 {sorted(stale - CLOSURE_ROWS)}")
        await db.rollback()
        assert await _stale(db, p) == {k: set() for k in KINDS}, "标记应随出口事务回滚（只 flush 不 commit）"


def test_slot_row_codes_and_statement_per_dialect():
    assert rf.slot_row_codes(["balance_sheet:BS-002", "income_statement:IS-001", "无冒号", "cash_flow_statement:"]) == {
        "BS-002", "IS-001"}
    pid = uuid.uuid4()
    pg = str(rf.mark_statement("postgresql", pid, {"BS-020", "BS-002"}).compile(dialect=postgresql.dialect()))
    lite = str(rf.mark_statement("sqlite", pid, {"BS-002"}).compile(dialect=sqlite.dialect()))
    assert "financial_report.row_code = ANY (" in pg and " IN (" not in pg, pg
    assert "financial_report.row_code IN (" in lite and "ANY" not in lite, lite
    for sql in (pg, lite):
        assert sql.startswith("UPDATE financial_report SET ") and "is_stale=" in sql, sql
        assert "financial_report.project_id = " in sql and "financial_report.is_deleted = " in sql, sql
        assert "financial_report.year" not in sql, sql  # 不限年度


# ─── 真 PG：row_code = ANY(:closure) ──────────────────────────────────────────────


@pytest.mark.pg_only
async def test_project_exits_mark_closure_on_postgres(pg_tx):
    """快照库外层事务内：甲保存 / 恢复各标一次闭包（全部年度、不碰已删行、不碰乙），直接调用对乙同口径。"""
    rows, closure_rows = _definitions("FHT15"), _closure_rows("FHT15")
    slot, suffix = "balance_sheet:FHT15-002", uuid.uuid4().hex[:8]
    projects = {name: Project(id=uuid.uuid4(), name=f"{TEST_PROJECT_PREFIX}fh15_{name}_{suffix}",
                              client_name=f"{TEST_PROJECT_PREFIX}报表标过期", project_type=ProjectType.annual,
                              status=ProjectStatus.planning, template_type="soe", report_scope="standalone")
                for name in ("a", "b")}
    pg_tx.add_all(projects.values())
    await pg_tx.flush()
    for number, (code, formula) in enumerate(rows.items(), 1):
        await add_global_row(pg_tx, code, formula, row_number=9500 + number)
    for project in projects.values():
        _add_report_rows(pg_tx, project.id, rows, "FHT15-002")
    await pg_tx.commit()  # pg_tx：只释放保存点，夹具留在外层事务里
    ids = {name: project.id for name, project in projects.items()}

    await save_overrides(pg_tx, domain="report", project_id=ids["a"], user_id=None,
                         items=[{"slot_key": slot, "definition": {"formula": LOCAL_NEW}}])
    _assert_marked(await _stale(pg_tx, ids), {"a"}, closure_rows)
    await pg_tx.execute(sa.update(FinancialReport).where(FinancialReport.project_id == ids["a"]).values(is_stale=False))
    await restore_global(pg_tx, domain="report", project_id=ids["a"], slot_keys=[slot], user_id=None)
    _assert_marked(await _stale(pg_tx, ids), {"a"}, closure_rows)
    closures = await rf.mark_changed(pg_tx, {ids["b"]: {"FHT15-002"}})
    assert {code for code in closures[ids["b"]] if code.startswith("FHT15-")} == {c for _, c in closure_rows}
    _assert_marked(await _stale(pg_tx, ids), {"a", "b"}, closure_rows)
