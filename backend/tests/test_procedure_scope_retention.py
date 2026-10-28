"""生成底稿保留范围判定（spec procedure-trim-generation-delegation-chain 需求 2 / 任务 5）。

纯函数：区间展开、母码链、最近一级程序行决定、同级冲突执行优先、区间编码本身。
SQLite：读取（COALESCE / 软删 / 跨项目隔离）、读取失败 fail-closed 且不污染外层事务、生成分流。
"""
from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

import app.models  # noqa: E402, F401
from app.models.base import Base, ProjectStatus  # noqa: E402
from app.models.core import Project  # noqa: E402
from app.models.procedure_models import ProcedureInstance  # noqa: E402
from app.models.workpaper_models import WpIndex, WpStatus  # noqa: E402
from app.services.procedure_scope_retention import (  # noqa: E402
    TrimmedScope,
    TrimScopeUnavailable,
    code_lineage,
    describe_skips,
    expand_range_code,
    load_trimmed_scope,
    plan_generation,
    recycled_codes,
    wp_index_states,
)
from app.services.procedure_service import ProcedureService  # noqa: E402


# ── 纯函数 ──────────────────────────────────────────────────────────────


def test_expand_range_code_forms():
    assert expand_range_code("D2-1至D2-4") == ["D2-1", "D2-2", "D2-3", "D2-4"]
    assert expand_range_code(" E1-14 至 E1-15 ") == ["E1-14", "E1-15"]
    assert expand_range_code("D2-6至13") == [f"D2-{n}" for n in range(6, 14)], "右侧可省略前缀"
    assert expand_range_code("D2-1至D3-4") == [], "两侧前缀不一致不展开"
    assert expand_range_code("D2-4至D2-1") == []
    assert expand_range_code("D2") == []
    assert expand_range_code("D2-1至D2-999") == [], "跨度超上限不展开（防御异常数据）"
    # 程序表 wp_id 回填与生成判定同一实现
    assert ProcedureService._expand_range_wp_code("F2-1至F2-14") == expand_range_code("F2-1至F2-14")


def test_code_lineage_boundaries():
    assert code_lineage("B22A-4-1") == ["B22A-4-1", "B22A-4", "B22A", "B22"]
    assert code_lineage("M4A") == ["M4A", "M4"], "程序表跟随科目"
    assert code_lineage("G10-1") == ["G10-1", "G10"]
    assert code_lineage("G10") == ["G10"], "G10 不是 G1 的子表"
    assert code_lineage("A1-11") == ["A1-11", "A1"], "A1-11 不是 A1-1 的子表"
    assert code_lineage("D2-1A") == ["D2-1A", "D2-1", "D2"]
    assert code_lineage("B5附件") == ["B5附件", "B5"]
    assert code_lineage(" h3-2 ") == ["H3-2", "H3"]
    assert code_lineage("") == [] and code_lineage(None) == []


def _scope(*rows: tuple[str, str]) -> TrimmedScope:
    return TrimmedScope.from_rows(rows)


def test_subject_trim_covers_children_and_program_table():
    scope = _scope(("H3", "not_applicable"), ("G1", "execute"), ("G10", "not_applicable"), ("G11", "execute"))
    for code in ("H3", "H3-1", "H3-6", "H3A", "H3-2-1"):
        assert scope.is_trimmed(code), code
    assert scope.trim_owner("H3-2") == "H3" and scope.trim_owner("H3A") == "H3"
    assert scope.is_trimmed("G10-3") and not scope.is_trimmed("G1") and not scope.is_trimmed("G1-1")
    assert not scope.is_trimmed("G11-2") and not scope.is_trimmed("ZZ9"), "没有程序行覆盖 ⇒ 保留"
    assert scope.trim_owner("G1-1") is None


def test_nearest_row_decides():
    """母码被裁、子码自己有「执行」行 ⇒ 子码保留（页面上该行显示执行）；没有自己行的兄弟跟随母码。"""
    scope = _scope(("A1", "not_applicable"), ("A1-11", "execute"))
    assert scope.is_trimmed("A1") and scope.is_trimmed("A1-1")
    assert not scope.is_trimmed("A1-11") and not scope.is_trimmed("A1-11-2")


def test_range_rows():
    scope = _scope(("F2", "not_applicable"), ("F2-1至F2-14", "execute"),
                   ("D2", "execute"), ("D2-6至D2-13", "skip"), ("D2-8", "execute"))
    assert scope.is_trimmed("F2") and scope.is_trimmed("F2-15") and scope.is_trimmed("F2A")
    assert not scope.is_trimmed("F2-3"), "区间行「执行」比母码更近"
    assert scope.is_trimmed("D2-7") and scope.is_trimmed("D2-13-1")
    assert scope.trim_owner("D2-7") == "D2-6至D2-13", "区间成员的决定者回报区间程序行本身"
    assert not scope.is_trimmed("D2-8"), "同级普通行优先于区间行"
    assert scope.decided_by("D2-8") == ("D2-8", False)
    assert not scope.is_trimmed("D2-5") and not scope.is_trimmed("D2")
    # 区间编码本身（模板集里有这种底稿）
    assert scope.is_trimmed("D2-6至D2-13") and not scope.is_trimmed("F2-1至F2-14")
    partial = _scope(("D4-1", "skip"), ("D4-2", "skip"), ("D4-3", "execute"))
    assert not partial.is_trimmed("D4-1至D4-3"), "成员未全裁 ⇒ 保留"
    assert partial.is_trimmed("D4-1至D4-2")
    assert not partial.is_trimmed("D9-1至D9-2"), "成员全无程序行 ⇒ 保留"
    assert scope.trimmed_codes == frozenset({"F2", "D2-6至D2-13"})


def test_duplicate_rows_execute_wins_and_normalization():
    scope = _scope(("K7", "skip"), ("K7", "execute"), (" n3 ", " NOT_APPLICABLE "), ("", "skip"), (None, "skip"))
    assert not scope.is_trimmed("K7")
    assert scope.is_trimmed("N3-1") and scope.is_trimmed("n3a")
    assert not _scope().is_trimmed("H3")


def test_split_keeps_order():
    scope = _scope(("H3", "not_applicable"))
    assert scope.split(["E1", "H3-1", "D2", "H3"]) == (["E1", "D2"], ["H3-1", "H3"])


def test_describe_skips():
    assert describe_skips({"skipped_trimmed_codes": [], "in_recycle_codes": []}) == ""
    text = describe_skips({"skipped_trimmed_codes": ["H3", "M4A"], "in_recycle_codes": ["E2"]})
    assert "2 个编码已在程序裁剪中标为不执行，未生成：H3、M4A" in text
    assert "1 个编码的底稿在回收站中，请从回收站恢复：E2" in text
    many = describe_skips({"skipped_trimmed_codes": [f"C{i}" for i in range(12)]})
    assert many.endswith(" 等")


# ── SQLite ──────────────────────────────────────────────────────────────

_TABLES = [Project.__table__, ProcedureInstance.__table__, WpIndex.__table__]


@pytest.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=_TABLES))
    async with async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)() as session:
        yield session
    await engine.dispose()


def _project(name: str) -> Project:
    return Project(id=uuid.uuid4(), name=name, client_name=name, status=ProjectStatus.execution,
                   template_type="soe", report_scope="standalone", audit_year=2025)


def _proc(pid, code, status, *, wp_code="same", deleted=False) -> ProcedureInstance:
    return ProcedureInstance(project_id=pid, audit_cycle=code[0], procedure_code=code, procedure_name=code,
                             status=status, wp_code=code if wp_code == "same" else wp_code, is_deleted=deleted)


def _index(pid, code, *, deleted=False) -> WpIndex:
    return WpIndex(project_id=pid, wp_code=code, wp_name=code, audit_cycle=code[0],
                   status=WpStatus.not_started, is_deleted=deleted)


@pytest.mark.asyncio
async def test_load_scope_reads_project_rows_only(db):
    mine, other = _project("【测试】保留范围"), _project("【测试】其他项目")
    db.add_all([mine, other])
    await db.flush()
    db.add_all([
        _proc(mine.id, "H3", "not_applicable"),
        _proc(mine.id, "M4", "skip", wp_code=None),          # wp_code 缺省用 procedure_code
        _proc(mine.id, "D5", "not_applicable", deleted=True),  # 软删的程序行不算
        _proc(other.id, "E1", "not_applicable"),             # 别的项目的裁剪不影响本项目
    ])
    await db.flush()
    scope = await load_trimmed_scope(db, mine.id)
    assert scope.is_trimmed("H3-1") and scope.is_trimmed("M4A")
    assert not scope.is_trimmed("D5") and not scope.is_trimmed("E1")


@pytest.mark.asyncio
async def test_load_scope_failure_is_closed_and_keeps_outer_transaction(db):
    pid = uuid.uuid4()
    await db.execute(sa.text("DROP TABLE procedure_instances"))
    with pytest.raises(TrimScopeUnavailable) as err:
        await load_trimmed_scope(db, pid)
    assert err.value.http_detail()["error"] == "trim_scope_unavailable"
    # 外层事务仍可用（读取在保存点里，失败只回滚保存点）
    assert (await db.execute(sa.select(sa.func.count()).select_from(WpIndex))).scalar_one() == 0


@pytest.mark.asyncio
async def test_plan_generation_routes_codes(db):
    mine, other = _project("【测试】生成分流"), _project("【测试】别的项目")
    db.add_all([mine, other])
    await db.flush()
    db.add_all([
        _proc(mine.id, "H3", "not_applicable"),
        _index(mine.id, "E1"),
        _index(mine.id, "E2", deleted=True),
        _index(mine.id, "H3-1", deleted=True),  # 已裁又在回收站：只报「已裁」
        _index(other.id, "ZZ1"),                # 别的项目已有同码不影响
    ])
    await db.flush()
    plan = await plan_generation(db, mine.id, ["H3", "E1", "E2", "H3-1", "ZZ1", "H3A"])
    assert plan.to_create == ["ZZ1"]
    assert plan.skipped_trimmed_codes == ["H3", "H3-1", "H3A"]
    assert plan.in_recycle_codes == ["E2"]
    assert plan.existing_codes == ["E1"]
    assert plan.receipt() == {"skipped_trimmed_codes": ["H3", "H3-1", "H3A"], "in_recycle_codes": ["E2"]}
    assert await recycled_codes(db, mine.id, ["E1", "E2", "H3-1"]) == {"E2", "H3-1"}

    assert await wp_index_states(db, mine.id, ["E1", "E2", "E9"]) == {"E1": False, "E2": True}
