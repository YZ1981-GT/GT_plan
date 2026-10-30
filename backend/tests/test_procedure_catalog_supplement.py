"""程序裁剪页补齐程序行与读取标注（spec trim-generation-plan-linkage R5 / R3.4 / R3.7）。

纯函数：按真实目录（gt_template_library.json 331 行 + 映射表 1025 个编码）算补哪些编码、补齐后幂等、
适用性分裂（程序行是 / 不是模板编码两种基准）。
SQLite：初始化建行 + 补齐、已初始化循环只补缺的、不改已有行、只读读取不补、来源与业务分类建议。
"""
from __future__ import annotations

import random
import uuid

import pytest
import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.pool import StaticPool

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

import app.models  # noqa: E402, F401
from app.models.base import Base, ProjectStatus  # noqa: E402
from app.models.core import Project  # noqa: E402
from app.models.procedure_models import ProcedureInstance  # noqa: E402
from app.routers import procedures as procedures_router  # noqa: E402
from app.services import procedure_catalog as cat  # noqa: E402
from app.services import procedure_scope_retention as scope_retention  # noqa: E402
from app.services.procedure_scope_retention import (  # noqa: E402
    SUBSTANTIVE_CYCLES,
    TrimmedScope,
    code_lineage,
    normalize_code,
)
from app.services.procedure_service import ProcedureService  # noqa: E402

CYCLES = "BCDEFGHIJKLMNAS"


def _catalog_rows() -> list[tuple[str, str]]:
    return [(i.get("code"), "execute") for i in cat._library_items()]


# ── 纯函数 ──────────────────────────────────────────────────────────────


def test_real_catalog_supplements_exactly_the_uncovered_and_split_codes():
    rows = _catalog_rows()
    assert len(rows) == 331
    added = {c: [i["wp_code"] for i in cat.supplement_items(rows, cat.cycle_template_items(c))] for c in CYCLES}
    assert {c: len(v) for c, v in added.items() if v} == {"B": 26, "A": 17, "S": 3}
    assert added["B"][:3] == ["B1", "B5", "B60"], "保持模板清单顺序"
    assert {"B5-1", "B5-9-2", "B5附件", "B60A", "B60-3"} <= set(added["B"])
    assert {"A18", "A21", "A27-1"} <= set(added["A"])
    assert {"A1-12", "A1-16"} <= set(added["A"]), "A1 行里只有这两张是上市专用：适用性分裂补成自己的行"
    assert added["S"] == ["S33-REV", "S32", "S35"]
    for cycle in "DEFGHIJKLMN":
        assert added[cycle] == [], f"{cycle}：科目母码（D2 / D4 / E1 / F2）跟随下级程序行，不补"
    # 补齐之后再算一次补 0 个（幂等）
    rows2 = rows + [(code, "execute") for codes in added.values() for code in codes]
    assert all(cat.supplement_items(rows2, cat.cycle_template_items(c)) == [] for c in CYCLES)


def test_existing_rows_and_range_codes_are_never_supplemented():
    items = [{"wp_code": "Z9", "wp_name": "甲"}, {"wp_code": "Z9-1至Z9-3", "wp_name": "区间"}, {"wp_code": "Z8", "wp_name": "乙"}]
    picked = cat.supplement_items([("z8 ", "not_applicable")], items)
    assert [i["wp_code"] for i in picked] == ["Z9"]


def _decisions_before_after(rows, cycle):
    entries = cat.supplement_entries(rows, cat.cycle_template_items(cycle))
    before = TrimmedScope.from_rows(rows)
    after = TrimmedScope.from_rows(list(rows) + [(i["wp_code"], s) for i, s, _ in entries])
    codes = [i["wp_code"] for i in cat.cycle_template_items(cycle)]
    changed = [c for c in codes if before.is_trimmed(c) != after.is_trimmed(c)]
    return entries, before, after, changed


def test_supplement_keeps_every_generation_decision():
    """真实目录、随机状态：补齐前后每个模板编码的生成判定不变（A1 整行裁掉时补的 A1-12 / A1-16 也已裁）。"""
    rng = random.Random(20261028)
    statuses = ("execute", "skip", "not_applicable")
    split_seen = 0
    for _ in range(80):
        rows = [(code, rng.choice(statuses)) for code, _ in _catalog_rows()]
        for cycle in CYCLES:
            entries, before, _, changed = _decisions_before_after(rows, cycle)
            assert changed == [], f"{cycle}：补齐改变了生成判定 {changed}"
            for item, status, reason in entries:
                if before.is_trimmed(item["wp_code"]):
                    split_seen += 1
                    assert status in ("skip", "not_applicable") and reason, item["wp_code"]
    assert split_seen > 0, "随机状态里应出现过「原决定行已裁」的分裂子码（否则本判据没测到）"


def test_split_supplement_reason_falls_back_to_owner_name():
    rows = [(code, "not_applicable" if code == "A1" else "execute") for code, _ in _catalog_rows()]
    got = {i["wp_code"]: (s, r) for i, s, r in cat.supplement_entries(rows, cat.cycle_template_items("A"), {})}
    assert got["A1-12"] == got["A1-16"] == ("not_applicable", "随程序行 A1 一起裁剪")
    assert got["A18"] == ("execute", None), "没有程序行管的编码照旧补「执行」"


def test_catalog_gap_only_reopens_substantive_parent_of_new_child():
    """目录缺了下级编码（项目选用的模板库不全）时补的下级行是「执行」，唯一会变的是跟随它的科目母码：
    从「下级全裁」变为保留（与该下级照常生成一致，也与本规则上线前母码恒保留一致），其他编码不变。"""
    rng = random.Random(7)
    statuses = ("execute", "skip", "not_applicable")
    for _ in range(80):
        rows = [(code, rng.choice(statuses)) for code, _ in _catalog_rows() if rng.random() > 0.15]
        for cycle in CYCLES:
            entries, before, after, changed = _decisions_before_after(rows, cycle)
            added = {normalize_code(i["wp_code"]) for i, s, _ in entries if s == "execute"}
            for code in changed:
                assert code[:1] in SUBSTANTIVE_CYCLES and before.is_trimmed(code) and not after.is_trimmed(code)
                assert after.follows_children(code)
                assert any(code in code_lineage(c)[1:] for c in added), code


def test_split_base_is_owner_itself_or_majority_of_owned(monkeypatch):
    mappings = [
        {"wp_code": "Q1", "cycle": "Q", "wp_name": "母码"},
        {"wp_code": "Q1-1", "cycle": "Q", "wp_name": "甲"},
        {"wp_code": "Q1-2", "cycle": "Q", "wp_name": "乙", "applicable_categories": ["A"]},
        {"wp_code": "Q2-1", "cycle": "Q", "wp_name": "丙", "applicable_categories": ["A"]},
        {"wp_code": "Q2-2", "cycle": "Q", "wp_name": "丁", "applicable_categories": ["A"]},
        {"wp_code": "Q2-3", "cycle": "Q", "wp_name": "戊"},
    ]
    monkeypatch.setattr(cat, "template_mappings", lambda: mappings)
    rows = [("Q1", "execute"), ("Q2-1至Q2-3", "execute")]
    picked = [i["wp_code"] for i in cat.supplement_items(rows, cat.cycle_template_items("Q"))]
    # Q1 行本身是模板编码：以 Q1（三类都适用）为准 ⇒ 只补 Q1-2；区间行不是模板编码：以多数（仅 A 类）为准 ⇒ 补 Q2-3
    assert picked == ["Q1-2", "Q2-3"]


def test_annotate_rows_origin_and_category_hint():
    rows = [
        {"procedure_code": "A17", "wp_code": "A17", "status": "execute", "is_custom": False},
        {"procedure_code": "A17-5", "wp_code": "A17-5", "status": "execute", "is_custom": False},
        {"procedure_code": "A1", "wp_code": "A1", "status": "execute", "is_custom": False},
        {"procedure_code": "A1-12", "wp_code": "A1-12", "status": "execute", "is_custom": False},
        {"procedure_code": "A-C01", "wp_code": "A-C01", "status": "execute", "is_custom": True},
    ]
    catalog = {cat.item_code(i) for i in cat._library_items() if i.get("cycle_prefix") == "A"}
    cat.annotate_rows(rows, "A", catalog_codes=catalog, category="C", defaulted=True)
    by = {r["procedure_code"]: r for r in rows}
    assert [by[c]["origin"] for c in ("A17", "A1", "A1-12", "A-C01")] == ["catalog", "catalog", "supplement", "custom"]
    hint = by["A17"]["category_hint"]
    assert hint and "A17" in hint["codes"] and len(hint["codes"]) == 9, "A17-5 族归 A17-5 行"
    assert hint["reason"] == "按项目业务分类 C 类（项目未填写 A / B / C 业务分类，按 C 类判断），本行 9 个底稿均不适用：仅 A 类适用"
    assert len(by["A17-5"]["category_hint"]["codes"]) == 5
    assert by["A1-12"]["category_hint"]["codes"] == ["A1-12"]
    assert by["A1"]["category_hint"] is None, "A1 行还管着适用的底稿 ⇒ 不建议裁剪"
    assert by["A-C01"]["category_hint"] is None
    cat.annotate_rows(rows, "A", catalog_codes=catalog, category="A", defaulted=False)
    assert all(r["category_hint"] is None for r in rows), "A 类项目全部适用"


# ── SQLite ──────────────────────────────────────────────────────────────


@pytest.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)() as session:
        yield session
    await engine.dispose()


async def _project(db, category: str | None = "C") -> uuid.UUID:
    p = Project(id=uuid.uuid4(), name="【测试】补齐程序行", client_name="【测试】补齐程序行",
                status=ProjectStatus.execution, template_type="soe", report_scope="standalone",
                audit_year=2025, business_category=category)
    db.add(p)
    await db.flush()
    return p.id


async def _rows(db, pid, cycle):
    return (await db.execute(sa.select(ProcedureInstance).where(
        ProcedureInstance.project_id == pid, ProcedureInstance.audit_cycle == cycle,
        ProcedureInstance.is_deleted == sa.false()).order_by(ProcedureInstance.sort_order))).scalars().all()


@pytest.mark.asyncio
async def test_init_builds_catalog_rows_then_supplements(db):
    pid = await _project(db)
    out = await ProcedureService(db).init_from_templates(pid, "B")
    rows = await _rows(db, pid, "B")
    catalog_n = sum(1 for i in cat._library_items() if i.get("cycle_prefix") == "B")
    assert len(rows) == catalog_n + 26 == len(out)
    tail = rows[-26:]
    assert [r.procedure_code for r in tail[:3]] == ["B1", "B5", "B60"]
    assert all(r.status == "execute" and r.wp_code == r.procedure_code and not r.is_custom for r in tail)
    assert tail[0].procedure_name == "风险评估表（适用于承接）"
    assert tail[0].sort_order > rows[catalog_n - 1].sort_order
    assert {r["origin"] for r in out if r["procedure_code"] in {"B1", "B5-1"}} == {"supplement"}
    # 再初始化一次：不重复
    again = await ProcedureService(db).init_from_templates(pid, "B")
    assert len(again) == len(out) and len(await _rows(db, pid, "B")) == len(rows)


@pytest.mark.asyncio
async def test_reinit_of_initialized_cycle_only_adds_missing_and_keeps_existing_rows(db):
    """本功能上线前已初始化的循环（只有目录行）：再初始化只补缺的，已有行的状态 / 理由 / 名称不动。"""
    pid = await _project(db)
    catalog = [i for i in cat._library_items() if i.get("cycle_prefix") == "S"]
    for n, item in enumerate(catalog):
        db.add(ProcedureInstance(project_id=pid, audit_cycle="S", procedure_code=item["code"], procedure_name=item["name"],
                                 status="execute", wp_code=item["code"], sort_order=n * 10))
    db.add(ProcedureInstance(project_id=pid, audit_cycle="S", procedure_code="S32", procedure_name="已有",
                             status="not_applicable", skip_reason="非 IPO", wp_code="S32", sort_order=5))
    await db.flush()
    first = (await _rows(db, pid, "S"))[0]
    first.status, first.skip_reason = "not_applicable", "本期无此事项"
    await db.flush()
    await ProcedureService(db).init_from_templates(pid, "S")
    rows = await _rows(db, pid, "S")
    by = {r.procedure_code: r for r in rows}
    assert (by[first.procedure_code].status, by[first.procedure_code].skip_reason) == ("not_applicable", "本期无此事项")
    assert (by["S32"].status, by["S32"].skip_reason) == ("not_applicable", "非 IPO")
    last = (len(catalog) - 1) * 10
    assert [(r.procedure_code, r.sort_order) for r in rows if r.sort_order > last] == [
        ("S33-REV", last + 10), ("S35", last + 20)], "S32 已有行，不补"
    assert len(rows) == len(catalog) + 3


@pytest.mark.asyncio
async def test_catalog_sql_failure_is_fail_closed_and_writes_no_rows(db, monkeypatch):
    """项目目录查询异常不能伪装成「没选择模板」后回退全局目录并成功写入。"""
    pid = await _project(db)
    original = db.execute

    async def fail_selection(statement, *args, **kwargs):
        if "project_template_selections" in str(statement):
            raise OperationalError("SELECT", {}, RuntimeError("目录库不可用"))
        return await original(statement, *args, **kwargs)

    monkeypatch.setattr(db, "execute", fail_selection)
    with pytest.raises(cat.ProcedureCatalogUnavailable):
        await ProcedureService(db).init_from_templates(pid, "B")
    assert await _rows(db, pid, "B") == [], "目录读取失败后不得留下半套程序行"
    with pytest.raises(cat.ProcedureCatalogUnavailable):
        await cat.catalog_codes_by_cycle(db, pid)


@pytest.mark.asyncio
async def test_init_add_and_delete_custom_take_the_generation_scope_lock(db, monkeypatch):
    pid = await _project(db)
    calls = []

    async def record(_db, project_id):
        calls.append(project_id)

    monkeypatch.setattr(cat, "lock_project_procedure_scope", record)
    monkeypatch.setattr(scope_retention, "lock_project_procedure_scope", record)
    await cat.lock_cycle_init(db, pid, "B")
    created = await ProcedureService(db).add_custom(
        pid, "B", {"procedure_name": "锁测试", "procedure_code": "B-CUSTOM-LOCK"},
    )
    assert await ProcedureService(db).delete_custom(pid, uuid.UUID(created["id"])) is True
    assert calls == [pid, pid, pid]


@pytest.mark.asyncio
async def test_custom_identity_is_canonical_unique_and_soft_delete_has_timestamp(db):
    pid = await _project(db)
    svc = ProcedureService(db)
    created = await svc.add_custom(
        pid, " b ", {"procedure_name": "自定义", "procedure_code": " custom-1 ", "wp_code": " custom-1 "},
    )
    assert (created["audit_cycle"], created["procedure_code"], created["wp_code"]) == ("B", "CUSTOM-1", "CUSTOM-1")
    with pytest.raises(ValueError, match="CUSTOM-1 已存在"):
        await svc.add_custom(pid, "B", {"procedure_name": "重复", "procedure_code": "Custom-1"})
    assert await db.scalar(sa.select(sa.literal(1))) == 1, "唯一冲突只回滚保存点，外层事务仍可用"
    assert await svc.delete_custom(pid, uuid.UUID(created["id"])) is True
    deleted = await db.get(ProcedureInstance, uuid.UUID(created["id"]))
    assert deleted is not None and deleted.is_deleted is True and deleted.deleted_at is not None


@pytest.mark.asyncio
async def test_database_constraints_reject_noncanonical_and_active_duplicate(db):
    pid = await _project(db)
    db.add(ProcedureInstance(
        project_id=pid, audit_cycle="B", procedure_code="B-ONE", procedure_name="一", wp_code="B-ONE",
    ))
    await db.flush()
    with pytest.raises(IntegrityError):
        async with db.begin_nested():
            db.add(ProcedureInstance(
                project_id=pid, audit_cycle="b", procedure_code=" b-two ", procedure_name="非规范", wp_code="b-two",
            ))
            await db.flush()
    with pytest.raises(IntegrityError):
        async with db.begin_nested():
            db.add(ProcedureInstance(
                project_id=pid, audit_cycle="B", procedure_code="B-ONE", procedure_name="重复", wp_code="B-ONE",
            ))
            await db.flush()


@pytest.mark.asyncio
async def test_catalog_unavailable_is_503_at_read_and_init_routes(db, monkeypatch):
    pid = await _project(db)

    async def read_boom(*_args, **_kwargs):
        raise cat.ProcedureCatalogUnavailable("目录不可用")

    monkeypatch.setattr(ProcedureService, "get_procedures", read_boom)
    with pytest.raises(HTTPException) as read_error:
        await procedures_router.get_procedures(pid, "B", db, user=None)
    assert read_error.value.status_code == 503
    assert read_error.value.detail["error"] == cat.PROCEDURE_CATALOG_UNAVAILABLE

    async def init_boom(*_args, **_kwargs):
        raise cat.ProcedureCatalogUnavailable("目录不可用")

    monkeypatch.setattr(ProcedureService, "init_from_templates", init_boom)
    with pytest.raises(HTTPException) as init_error:
        await procedures_router.init_procedures(pid, "B", db, _guard=None)
    assert init_error.value.status_code == 503


@pytest.mark.asyncio
async def test_cross_cycle_standard_code_cannot_be_added_as_custom(db):
    pid = await _project(db)
    with pytest.raises(ValueError, match="标准底稿编码 A18 属于 A 循环"):
        await ProcedureService(db).add_custom(pid, "B", {"procedure_name": "错误归属", "procedure_code": " a18 "})
    assert await _rows(db, pid, "B") == []
    same_cycle = await ProcedureService(db).add_custom(pid, "A", {"procedure_name": "同循环扩展", "procedure_code": "A18"})
    assert same_cycle["procedure_code"] == "A18"


@pytest.mark.asyncio
async def test_reinit_after_owner_trimmed_keeps_split_children_trimmed(db):
    """上线前已把 A1 整行裁掉的项目：再打开裁剪页（委派人走初始化）补的 A1-12 / A1-16 仍已裁、理由沿用。"""
    pid = await _project(db)
    catalog = [i for i in cat._library_items() if i.get("cycle_prefix") == "A"]
    for n, item in enumerate(catalog):
        trimmed = item["code"] == "A1"
        db.add(ProcedureInstance(project_id=pid, audit_cycle="A", procedure_code=item["code"],
                                 procedure_name=item["name"], status="not_applicable" if trimmed else "execute",
                                 skip_reason="非上市公司，本项目不执行" if trimmed else None,
                                 wp_code=item["code"], sort_order=n * 10))
    await db.flush()
    await ProcedureService(db).init_from_templates(pid, "A")
    by = {r.procedure_code: r for r in await _rows(db, pid, "A")}
    for code in ("A1-12", "A1-16"):
        assert (by[code].status, by[code].skip_reason) == ("not_applicable", "非上市公司，本项目不执行"), code
    assert (by["A18"].status, by["A18"].skip_reason) == ("execute", None)
    assert (by["A1"].status, by["A1"].skip_reason) == ("not_applicable", "非上市公司，本项目不执行"), "不改已有行"


@pytest.mark.asyncio
async def test_get_procedures_is_read_only_and_annotates(db):
    pid = await _project(db, category=None)
    db.add_all([
        ProcedureInstance(project_id=pid, audit_cycle="A", procedure_code="A17", procedure_name="A17",
                          status="execute", wp_code="A17", sort_order=0),
        ProcedureInstance(project_id=pid, audit_cycle="A", procedure_code="A1", procedure_name="A1",
                          status="execute", wp_code="A1", sort_order=10),
    ])
    await db.flush()
    rows = await ProcedureService(db).get_procedures(pid, "A")
    assert len(await _rows(db, pid, "A")) == 2, "GET 不补齐"
    by = {r["procedure_code"]: r for r in rows}
    assert by["A17"]["origin"] == "catalog" and "未填写 A / B / C 业务分类" in by["A17"]["category_hint"]["reason"]
    # A1 行此时还管 A1-12 / A1-16（未补齐）⇒ 本行底稿不是全部不适用 ⇒ 没有建议
    assert by["A1"]["category_hint"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize("raw,expected", [
    ("A1", ("A", False)), ("B2", ("B", False)), ("C", ("C", False)), (None, ("C", True)),
])
async def test_project_category_only_accepts_a_b_c(db, raw, expected):
    pid = await _project(db, category=raw)
    assert await cat.project_category(db, pid) == expected


@pytest.mark.parametrize("raw,expected", [
    ("b2", ("B", False)), ("  ", ("C", True)), ("IPO", ("C", True)), ("refinancing", ("C", True)), ("D9", ("C", True)),
])
def test_project_category_legacy_values_resolve_like_before(raw, expected):
    """V219 CHECK 后库里写不进非登记值；迁移前残留值经同一解释（project_classification）仍按 C 类默认。"""
    from app.services.project_classification import resolve

    c = resolve(raw)
    assert (c.category_group, c.defaulted) == expected


@pytest.mark.asyncio
async def test_ensure_supplement_rows_is_idempotent(db):
    pid = await _project(db)
    await ProcedureService(db).init_from_templates(pid, "A")
    assert await cat.ensure_supplement_rows(db, pid, "A") == 0
    codes = [r.procedure_code for r in await _rows(db, pid, "A")]
    assert len(codes) == len(set(codes)), "没有重复的程序行"
    assert {"A1-12", "A1-16", "A18", "A26-4"} <= set(codes)
