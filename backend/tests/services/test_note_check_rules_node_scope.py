"""合并附注勾稽校验按节点读取已保存数据（spec consol-note-header-library-and-node-reaggregate R7.5）。

旧实现先按单体附注章节号查 ``disclosure_notes``（合并章节号「五-5-1」永不命中），再查
``ConsolNoteData.is_deleted``（列不存在 ⇒ 异常被吞），且不分节点 ⇒ 每条规则恒「无附注数据」跳过。
本文件用真实 ORM 表（SQLite）钉住：本表与对照表都读所选节点的已保存数据、根节点兼容旧行、
子节点不串读根 / 旧行、省略节点只读旧行；端点带 ``node_key`` 且按项目实际口径取模板。
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import tests.conftest  # noqa: F401  注册全部模型与 SQLite 方言补丁
from app.core.database import get_db
from app.deps import get_current_user
from app.models.base import Base, UserRole
from app.models.consol_note_data_models import ConsolNoteData
from app.models.core import Project
from app.services import note_check_rules as ncr
from app.services.consol_node_scope import NodeScopeError
from app.services.note_table_header_library import RollForward

YEAR = 2025
ROOT_KEY = "G:consol"
CHILD_KEY = "A:subsidiary"
SELF = "五-1-2"
PEER = "五-1-1"

# 合成规则：跨表（本表合计 col1 = 对照表合计 col1）+ 列平衡（期初 + 增加 − 减少 = 期末）
_CROSS = ncr.CheckRule(
    check_id="T-X", peer_section_id=PEER, peer_row_label="合计", peer_col_index=1,
    self_row_label="合  计", self_col_index=1, relation="equal", tolerance=0.01,
    description="本表合计 = 对照表合计",
)
_BALANCE = ncr.CheckRule(
    check_id="T-B", peer_section_id="", peer_row_label="", peer_col_index=0,
    self_row_label="合  计", self_col_index=0, relation="column_balance", tolerance=0.01,
    description="期初 + 增加 − 减少 = 期末", mode="column_balance",
)
#: 合成表的变动表列（列平衡的列由标题行库按模板表头认，这里替换模板来源）
_FLOW = RollForward(opening=1, closing=4, increase=(2,), decrease=(3,), unknown=())


@pytest_asyncio.fixture
async def factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False, poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    try:
        yield async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    finally:
        await engine.dispose()


@pytest.fixture
def synthetic_rules(monkeypatch):
    """只替换模板来源（规则与表头 → 变动表列、模板列数），读取 / 作用域 / 校验全走生产代码。"""
    monkeypatch.setattr(ncr, "_load_check_rules", lambda tt, sid: [_CROSS, _BALANCE] if sid == SELF else [])
    monkeypatch.setattr(ncr, "rollforward_for", lambda tt, sid: _FLOW if sid == SELF else None)
    monkeypatch.setattr(ncr, "find_table", lambda tt, sid: {"headers": ["项目", "期初", "增加", "减少", "期末"]})


async def _seed_group(factory, *, template_type: str | None = None) -> Project:
    root = Project(
        id=uuid.uuid4(), name="勾稽集团_2025", client_name="勾稽集团",
        company_code="G", ultimate_company_code="G", report_scope="consolidated",
        audit_year=YEAR, audit_period_end=date(YEAR, 12, 31), template_type=template_type,
    )
    child = Project(
        id=uuid.uuid4(), name="勾稽子公司_2025", client_name="勾稽子公司",
        company_code="A", parent_company_code="G", ultimate_company_code="G",
        relation_to_parent="subsidiary", report_scope="standalone",
        audit_year=YEAR, audit_period_end=date(YEAR, 12, 31),
    )
    async with factory() as db:
        db.add_all([root, child])
        await db.commit()
    return root


async def _put(factory, project: Project, section_id: str, node_key: str | None, rows: list[list[str]]):
    async with factory() as db:
        db.add(ConsolNoteData(
            project_id=project.id, year=YEAR, section_id=section_id, node_key=node_key,
            data={"headers": ["项目", "期初", "增加", "减少", "期末"], "rows": rows},
            updated_at=datetime.now(timezone.utc),
        ))
        await db.commit()


def _table(total_opening: str, inc: str = "0", dec: str = "0", closing: str | None = None) -> list[list[str]]:
    closing = total_opening if closing is None else closing
    return [["甲", total_opening, inc, dec, closing], ["合  计", total_opening, inc, dec, closing]]


async def _run(factory, project: Project, node_key: str | None):
    async with factory() as db:
        results = await ncr.check_note_cross_rules(db, project.id, YEAR, SELF, "soe", node_key=node_key)
    return {r.check_id: r for r in results}


# ─── 服务层 ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_child_node_reads_its_own_saved_rows(factory, synthetic_rules):
    project = await _seed_group(factory)
    # 旧行与根节点：两侧一致；子节点：本表 150 ≠ 对照表 100，且本表 100+80−30 ≠ 160
    await _put(factory, project, SELF, None, _table("100"))
    await _put(factory, project, PEER, None, _table("100"))
    await _put(factory, project, SELF, CHILD_KEY, [["合  计", "100", "80", "30", "160"]])
    await _put(factory, project, PEER, CHILD_KEY, [["合计", "150", "", "", ""]])

    out = await _run(factory, project, CHILD_KEY)
    assert out["T-X"].status == "fail"
    assert (out["T-X"].actual, out["T-X"].expected) == ("100", "150")
    assert out["T-B"].status == "fail" and out["T-B"].expected == "150" and out["T-B"].actual == "160"


@pytest.mark.asyncio
async def test_root_node_falls_back_to_legacy_rows(factory, synthetic_rules):
    project = await _seed_group(factory)
    await _put(factory, project, SELF, None, _table("1,234.56", "10", "4", "1,240.56"))
    await _put(factory, project, PEER, None, [["合计", "1234.56", "", "", ""]])

    out = await _run(factory, project, ROOT_KEY)
    # 千分位与合计重算同一口径（consol_note_table_totals.to_decimal）
    assert out["T-X"].status == "pass" and out["T-X"].actual == "1234.56"
    assert out["T-B"].status == "pass" and out["T-B"].actual == "1240.56"


@pytest.mark.asyncio
async def test_root_node_prefers_its_own_row_over_legacy(factory, synthetic_rules):
    project = await _seed_group(factory)
    await _put(factory, project, SELF, None, _table("100"))
    await _put(factory, project, PEER, None, [["合计", "100", "", "", ""]])
    await _put(factory, project, SELF, ROOT_KEY, _table("300"))

    out = await _run(factory, project, ROOT_KEY)
    assert out["T-X"].status == "fail" and (out["T-X"].actual, out["T-X"].expected) == ("300", "100")


@pytest.mark.asyncio
async def test_child_without_rows_does_not_read_root_or_legacy(factory, synthetic_rules):
    project = await _seed_group(factory)
    await _put(factory, project, SELF, None, _table("100"))
    await _put(factory, project, PEER, None, _table("100"))
    await _put(factory, project, SELF, ROOT_KEY, _table("100"))

    out = await _run(factory, project, CHILD_KEY)
    assert {r.status for r in out.values()} == {"skipped"}
    assert f"本章节 {SELF} 无附注数据" in out["T-X"].reason


@pytest.mark.asyncio
async def test_peer_table_is_read_in_the_same_node(factory, synthetic_rules):
    project = await _seed_group(factory)
    await _put(factory, project, SELF, CHILD_KEY, _table("100", "10", "10"))
    await _put(factory, project, PEER, None, [["合计", "100", "", "", ""]])  # 只有旧行有对照表

    out = await _run(factory, project, CHILD_KEY)
    assert out["T-X"].status == "skipped" and f"对照章节 {PEER} 无附注数据" in out["T-X"].reason
    assert out["T-B"].status == "pass"


@pytest.mark.asyncio
async def test_omitted_node_reads_legacy_rows_only(factory, synthetic_rules):
    project = await _seed_group(factory)
    await _put(factory, project, SELF, CHILD_KEY, _table("999"))
    await _put(factory, project, PEER, CHILD_KEY, [["合计", "999", "", "", ""]])

    out = await _run(factory, project, None)
    assert {r.status for r in out.values()} == {"skipped"}

    await _put(factory, project, SELF, None, _table("5"))
    await _put(factory, project, PEER, None, [["合计", "5", "", "", ""]])
    out = await _run(factory, project, None)
    assert out["T-X"].status == "pass" and out["T-X"].actual == "5"


@pytest.mark.asyncio
async def test_saved_rows_with_other_width_are_not_checked(factory, synthetic_rules):
    """旧数据列数与模板不同：列号对不上，跳过并写明（不拿错列比出假的不一致）。"""
    project = await _seed_group(factory)
    async with factory() as db:
        db.add(ConsolNoteData(project_id=project.id, year=YEAR, section_id=SELF, node_key=CHILD_KEY,
                              data={"headers": ["项目", "期初", "期末"], "rows": [["合  计", "1", "2"]]},
                              updated_at=datetime.now(timezone.utc)))
        await db.commit()
    out = await _run(factory, project, CHILD_KEY)
    assert {r.status for r in out.values()} == {"skipped"}
    assert out["T-B"].reason == f"本章节 {SELF} 已保存数据 3 列，与模板 5 列不符"


@pytest.mark.asyncio
async def test_invalid_node_or_year_raises_scope_error(factory, synthetic_rules):
    project = await _seed_group(factory)
    async with factory() as db:
        with pytest.raises(NodeScopeError) as exc:
            await ncr.check_note_cross_rules(db, project.id, YEAR, SELF, "soe", node_key="Z:unknown")
        assert exc.value.status == 404
        with pytest.raises(NodeScopeError) as exc:
            await ncr.check_note_cross_rules(db, project.id, YEAR - 1, SELF, "soe", node_key=ROOT_KEY)
        assert exc.value.status == 400


# ─── 端点 ───────────────────────────────────────────────────────────────


def _app(factory) -> FastAPI:
    from app.routers.consol_note_sections import router

    app = FastAPI()
    app.include_router(router)
    actor = type("Actor", (), {
        "id": uuid.uuid4(), "username": "check_rules_admin",
        "role": UserRole.admin, "is_active": True, "is_deleted": False,
    })()

    async def override_db():
        async with factory() as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: actor
    return app


async def _get(factory, project: Project, section_id: str, **params):
    async with AsyncClient(transport=ASGITransport(app=_app(factory)), base_url="http://test") as client:
        return await client.get(
            f"/api/consol-note-sections/check-rules/{project.id}/{YEAR}/{section_id}", params=params,
        )


# 真模板规则：应付职工薪酬变动表（两版都在 五-40-1，规则编号不同）
_REAL_SECTION = "五-40-1"


@pytest.mark.asyncio
async def test_endpoint_reads_selected_node_with_project_template(factory):
    listed_ids = [r.check_id for r in ncr._load_check_rules("listed", _REAL_SECTION)]
    soe_ids = [r.check_id for r in ncr._load_check_rules("soe", _REAL_SECTION)]
    assert listed_ids and soe_ids and listed_ids != soe_ids  # 前提：两版规则可区分

    project = await _seed_group(factory, template_type="listed")
    await _put(factory, project, _REAL_SECTION, CHILD_KEY, [
        ["短期薪酬", "100", "50", "30", "120"],
        ["合计", "100", "50", "30", "999"],
    ])

    resp = await _get(factory, project, _REAL_SECTION, node_key=CHILD_KEY)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["template_type"] == "listed" and body["node_key"] == CHILD_KEY
    assert [r["check_id"] for r in body["rules"]] == listed_ids
    statuses = {r["description"]: r["status"] for r in body["results"]}
    assert any(k.endswith("（短期薪酬）") and v == "pass" for k, v in statuses.items())
    assert any(k.endswith("（合计）") and v == "fail" for k, v in statuses.items())

    # 根节点没有数据（也没有旧行）⇒ 全部跳过，不串读子节点
    resp = await _get(factory, project, _REAL_SECTION, node_key=ROOT_KEY)
    assert resp.status_code == 200, resp.text
    assert {r["status"] for r in resp.json()["results"]} == {"skipped"}


@pytest.mark.asyncio
async def test_endpoint_rejects_template_mismatch_and_bad_node(factory):
    project = await _seed_group(factory, template_type="listed")

    resp = await _get(factory, project, _REAL_SECTION, template_type="soe")
    assert resp.status_code == 400, resp.text
    assert "上市版" in resp.text

    resp = await _get(factory, project, _REAL_SECTION, node_key="Z:unknown")
    assert resp.status_code == 404, resp.text

    resp = await _get(factory, project, _REAL_SECTION, node_key=ROOT_KEY, template_type="listed_consolidated")
    assert resp.status_code == 200, resp.text


@pytest.mark.asyncio
async def test_endpoint_section_without_rules_returns_empty(factory):
    project = await _seed_group(factory)
    resp = await _get(factory, project, "五-1-1", node_key=ROOT_KEY)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["rules"] == [] and body["results"] == [] and body["template_type"] == "soe"
