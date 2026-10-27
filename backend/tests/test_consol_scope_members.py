"""合并范围成员以企业树为准（spec consol-autotree-residual-closure R5.1）。

成员 = 合并企业树里的子公司类企业（与合并计算同一棵树）：分公司、母公司本身不算，按最终控制方挂靠的算。
附注正文变量（子公司数 / 清单）与程序表「确定合并范围」原先读合并范围表（真库 0 行）⇒ 恒 0 / 恒「待确定」。

真 SQLite + 真 ORM 行 + 真 service（集团夹具同 ``test_ctree_endpoints``：G 合并 ⊃ 分公司 GB、子公司 A，
另一集团 H；X 没有上级、按控制方挂到 G 下）。
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON  # type: ignore[attr-defined]

from app.models.base import Base, ProjectStatus  # noqa: E402
from app.models.consolidation_models import ConsolScope  # noqa: E402
from app.models.core import Project  # noqa: E402
from app.services import consol_scope_members  # noqa: E402
from app.services.auto_data_resolvers import _REGISTRY  # noqa: E402
from app.services.consol_scope_members import ScopeMember, tree_subsidiaries  # noqa: E402
from app.services.note_text_paragraph_vars import _load_consolidation_vars  # noqa: E402

Y = 2025


@pytest_asyncio.fixture
async def db() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)() as session:
        yield session
    await engine.dispose()


def _p(code, name, scope, *, parent=None, relation=None, ultimate=None, year=Y):
    return Project(
        id=uuid.uuid4(), name=f"{name}_{year}", client_name=name, company_code=code, report_scope=scope,
        audit_year=year, parent_company_code=parent, relation_to_parent=relation,
        ultimate_company_code=ultimate, status=ProjectStatus.execution,
    )


@pytest_asyncio.fixture
async def group(db: AsyncSession) -> dict[str, Project]:
    g = {
        "G": _p("G", "某集团", "consolidated", ultimate="G"),
        "G_s": _p("G", "某集团", "standalone", ultimate="G"),
        "GB": _p("GB", "某集团北京分公司", "standalone", parent="G", relation="branch", ultimate="G"),
        "A": _p("A", "甲公司", "standalone", parent="G", relation="subsidiary", ultimate="G"),
        "X": _p("X", "丙公司", "standalone", ultimate="G"),
        "H": _p("H", "另一集团", "standalone", ultimate="H"),
    }
    db.add_all(g.values())
    await db.flush()
    from app.services.group_links import sync_group_links

    await sync_group_links(db, Y)
    await db.commit()
    return g


def _scope_row(project: Project, code: str, *, ratio: str | None, year: int = Y, included: bool = True) -> ConsolScope:
    return ConsolScope(
        project_id=project.id, year=year, company_code=code, company_name=f"范围表_{code}",
        is_included=included, ownership_ratio=Decimal(ratio) if ratio is not None else None,
    )


async def test_members_are_tree_subsidiaries(db, group) -> None:
    members = await tree_subsidiaries(db, group["G"].id)
    assert sorted(members, key=lambda m: m.company_code) == [ScopeMember("A", "甲公司"), ScopeMember("X", "丙公司")]
    assert len({m.company_code for m in members}) == len(members), "同一企业只列一次"


async def test_mid_level_consolidated_subsidiary_is_listed_once(db) -> None:
    """下级合并的企业在树里有合并户 / 差额户 / 母公司户多个节点（同一企业代码）⇒ 成员、子公司数、取数都只算一次。"""
    rows = [
        _p("G2", "乙集团", "consolidated", ultimate="G2"),
        _p("G2", "乙集团", "standalone", ultimate="G2"),
        _p("S", "乙控股", "consolidated", parent="G2", relation="subsidiary", ultimate="G2"),
        _p("S", "乙控股", "standalone", parent="G2", relation="subsidiary", ultimate="G2"),
        _p("T", "丙公司", "standalone", parent="S", relation="subsidiary", ultimate="G2"),
    ]
    db.add_all(rows)
    await db.flush()
    from app.services.group_links import sync_group_links

    await sync_group_links(db, Y)
    await db.commit()
    root = rows[0].id

    from app.services.consol_tree_service import build_tree, iter_nodes

    nodes_s = [n for n in iter_nodes(await build_tree(db, root)) if n.company_code == "S"]
    assert len(nodes_s) > 1, "前提：下级合并的企业在树里不止一个节点"
    assert await tree_subsidiaries(db, root) == [ScopeMember("S", "乙控股"), ScopeMember("T", "丙公司")]
    assert (await _load_consolidation_vars(db, root, Y))["subsidiary_count"] == 2
    assert await _REGISTRY["consol_scope_status"](db, root, Y) == {"summary": "已纳入2家子公司"}


@pytest.mark.parametrize("key", ["G_s", "A", "H"])
async def test_non_consolidated_project_has_no_members(db, group, key) -> None:
    assert await tree_subsidiaries(db, group[key].id) == []


async def test_unknown_project_has_no_members(db, group) -> None:
    assert await tree_subsidiaries(db, uuid.uuid4()) == []


async def test_note_vars_follow_tree_and_take_ratio_from_scope_attributes(db, group) -> None:
    """子公司数 / 清单按企业树；持股比例取合并范围表同代码、本年度的行（树外企业的行、其他年度的行不用）。"""
    g = group["G"]
    db.add_all([
        _scope_row(g, "A", ratio="60.00"),
        _scope_row(g, "A", ratio="99.00", year=Y - 1),
        _scope_row(g, "Z", ratio="51.00"),  # 不在企业树里 ⇒ 不是成员
    ])
    await db.commit()

    out = await _load_consolidation_vars(db, g.id, Y)
    assert out["subsidiary_count"] == 2 and out["has_consolidation"] is True
    by_code = {s["company_code"]: s for s in out["subsidiaries"]}
    assert set(by_code) == {"A", "X"}
    assert by_code["A"] == {"name": "甲公司", "company_code": "A", "ownership_ratio": 60.0}
    assert by_code["X"]["ownership_ratio"] is None


async def test_note_vars_ignore_scope_table_when_tree_has_no_subsidiary(db, group) -> None:
    """合并范围表有行、企业树没有子公司 ⇒ 0：成员只认企业树（原先这里会把表里的行当成子公司）。"""
    db.add(_scope_row(group["G_s"], "Z", ratio="51.00"))
    await db.commit()
    assert await _load_consolidation_vars(db, group["G_s"].id, Y) == {
        "subsidiary_count": 0, "subsidiaries": [], "has_consolidation": False}


async def test_note_vars_failure_does_not_roll_back_caller(db, group, monkeypatch) -> None:
    """查询在保存点里：失败只返回空，调用方会话里未提交的改动不丢（原先 rollback 整个会话）。"""

    async def _boom(*_args, **_kwargs):
        raise RuntimeError("企业树读取失败")

    monkeypatch.setattr(consol_scope_members, "tree_subsidiaries", _boom)
    pending = _p("P", "未提交项目", "standalone")
    db.add(pending)
    assert await _load_consolidation_vars(db, group["G"].id, Y) == {}
    await db.commit()
    assert (await db.execute(sa.select(Project.id).where(Project.id == pending.id))).scalar_one() == pending.id


async def test_procedure_resolver_counts_tree_subsidiaries(db, group) -> None:
    resolve = _REGISTRY["consol_scope_status"]
    assert await resolve(db, group["G"].id, Y) == {"summary": "已纳入2家子公司"}
    assert await resolve(db, group["G_s"].id, Y) == {"summary": "待确定"}
    db.add(_scope_row(group["G_s"], "Z", ratio=None))
    await db.commit()
    assert await resolve(db, group["G_s"].id, Y) == {"summary": "待确定"}, "合并范围表的行不再算成员"
