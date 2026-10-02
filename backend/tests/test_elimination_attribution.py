"""分录归属与服务修复（spec consol-tree-three-code-autobuild 任务 8 / 需求 6.1~6.6）。

真 SQLite + 真 ORM 行；端点类用例真发请求（ASGITransport），鉴权走真实 ``require_project_access``
（只替换 ``get_current_user`` / ``get_db``，不替换权限判定本身）。

- 8.2 归属校验：合并差额（空）/ 本项目承载的母分差额放行；没有母分差额节点、由其他合并项目承载、
  非合并项目 ⇒ 400 且说明应到哪个合并项目录入；与金额计算同一归属函数（能保存 ⇔ 会计入）；
- 8.3 修改同步明细行与表头代表科目、借贷合计（修改后明细行在重算里生效）；读取单笔排除软删；
  列表按归属节点筛选；
- 8.4 自动生成草稿：交易双方都在同一母公司的分公司闭包内 ⇒ 预填该企业的母分差额，否则留空；
- 孤儿诊断：树结构变化后已审批分录失去归属 ⇒ 重算结果列出，两条路径都不计入（需求 6.4）。
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
import sqlalchemy as sa
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON  # type: ignore[attr-defined]

from app.core.database import get_db  # noqa: E402
from app.deps import get_current_user  # noqa: E402
from app.models.audit_platform_models import AccountCategory, TrialBalance  # noqa: E402
from app.models.base import Base, PermissionLevel, ProjectStatus, UserRole  # noqa: E402
from app.models.consolidation_models import (  # noqa: E402
    EliminationEntry,
    EliminationEntryType,
    InternalArAp,
    ReviewStatusEnum,
)
from app.models.consolidation_schemas import (  # noqa: E402
    EliminationCreate,
    EliminationEntryLine,
    EliminationEntryUpdate,
)
from app.models.core import Project, ProjectUser, User  # noqa: E402
from app.services import elimination_service as svc  # noqa: E402

Y = 2025
D = Decimal
_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)


@pytest_asyncio.fixture
async def db() -> AsyncSession:
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session


def _p(code, name, scope, *, parent=None, relation=None):
    return Project(
        id=uuid.uuid4(), name=f"{name}_{Y}", client_name=name, company_code=code, report_scope=scope,
        audit_year=Y, parent_company_code=parent, relation_to_parent=relation, status=ProjectStatus.execution,
    )


@pytest_asyncio.fixture
async def group(db: AsyncSession) -> dict[str, Project]:
    """G（合并+单户）⊃ 分公司 GB；子公司 A（合并+单户）⊃ 分公司 AB；子公司 S（单户）；另一个单户项目 X。"""
    g = {
        "G": _p("G", "某集团", "consolidated"),
        "G_s": _p("G", "某集团", "standalone"),
        "GB": _p("GB", "某集团北京分公司", "standalone", parent="G", relation="branch"),
        "A": _p("A", "甲公司", "consolidated", parent="G", relation="subsidiary"),
        "A_s": _p("A", "甲公司", "standalone", parent="G", relation="subsidiary"),
        "AB": _p("AB", "甲公司上海分公司", "standalone", parent="A", relation="branch"),
        "S": _p("S", "乙公司", "standalone", parent="G", relation="subsidiary"),
    }
    db.add_all(g.values())
    for key, amount in (("G_s", "1000"), ("GB", "300"), ("S", "500")):
        db.add(TrialBalance(
            id=uuid.uuid4(), project_id=g[key].id, year=Y, company_code="001", standard_account_code="1122",
            account_name="应收账款", account_category=AccountCategory.asset, audited_amount=D(amount),
        ))
    await db.commit()
    return g


def _data(branch=None, lines=None, entry_type=EliminationEntryType.internal_ar_ap):
    lines = lines or [("1122", "应收账款", "100", "0"), ("2202", "应付账款", "0", "100")]
    return EliminationCreate(
        project_id=uuid.uuid4(), year=Y, entry_type=entry_type, description="测试分录",
        branch_entity_code=branch,
        lines=[EliminationEntryLine(account_code=c, account_name=n, debit_amount=D(dr), credit_amount=D(cr))
               for c, n, dr, cr in lines],
    )


# ─────────────────────────────── 8.2 归属校验 ───────────────────────────────


class TestAttributionValidation:
    @pytest.mark.asyncio
    async def test_accepts_consol_elim_and_hosted_branch_elim(self, db, group):
        e1 = await svc.create_entry(db, group["G"].id, _data())
        assert e1.branch_entity_code is None
        e2 = await svc.create_entry(db, group["G"].id, _data(branch=" G "))
        assert e2.branch_entity_code == "G"  # 去空白后保存
        # 下级合并项目录入自己的母分差额（A 的分公司 AB 在 A 的合并项目里承载）
        e3 = await svc.create_entry(db, group["A"].id, _data(branch="A"))
        assert e3.branch_entity_code == "A"

    @pytest.mark.asyncio
    async def test_rejects_with_where_to_enter(self, db, group):
        # A 的母分差额由 A 的合并项目承载：在集团项目录入 ⇒ 说明应到甲公司的合并项目
        with pytest.raises(ValueError, match="甲公司.*应到该合并项目录入"):
            await svc.create_entry(db, group["G"].id, _data(branch="A"))
        # 乙公司没有分公司 ⇒ 没有母分差额节点
        with pytest.raises(ValueError, match="没有母分差额节点"):
            await svc.create_entry(db, group["G"].id, _data(branch="S"))
        # 单户项目不能录合并分录
        with pytest.raises(ValueError, match="只有合并报表项目"):
            await svc.create_entry(db, group["S"].id, _data())
        assert (await db.execute(sa.select(sa.func.count()).select_from(EliminationEntry))).scalar_one() == 0

    @pytest.mark.asyncio
    async def test_rejects_unbalanced_and_missing_account(self, db, group):
        with pytest.raises(ValueError, match="借贷不平衡"):
            await svc.create_entry(db, group["G"].id, _data(lines=[("1122", "应收账款", "100", "0")]))
        with pytest.raises(ValueError, match="没有科目"):
            await svc.create_entry(db, group["G"].id, _data(lines=[("1122", "a", "5", "0"), (" ", "b", "0", "5")]))

    @pytest.mark.asyncio
    async def test_saved_iff_counted(self, db, group):
        """能保存的分录恰是重算会计入的分录（同一归属函数）：保存后审批 ⇒ 重算无孤儿，金额进对应差额节点。"""
        from app.services.consol_worksheet_engine import recalc_full

        e = await svc.create_entry(db, group["G"].id, _data(branch="G"))
        e.review_status = ReviewStatusEnum.approved
        await db.commit()
        result = await recalc_full(db, group["G"].id, Y)
        assert result["orphan_entries"] == []
        from app.models.consolidation_models import ConsolWorksheet

        row = (await db.execute(sa.select(ConsolWorksheet).where(
            ConsolWorksheet.node_company_code == "G:branch_elim", ConsolWorksheet.account_code == "1122",
            ConsolWorksheet.is_deleted == sa.false(),
        ))).scalar_one()
        assert row.consolidated_amount == D(100)


# ─────────────────────────────── 8.3 修改 / 读取 / 列表 ───────────────────────────────


class TestUpdateReadList:
    @pytest.mark.asyncio
    async def test_update_syncs_lines_header_and_totals(self, db, group):
        """修改明细行 ⇒ 明细行、表头代表科目、借贷合计同步（旧版只改合计不改明细行，F10）。"""
        from app.services.consol_trial_service import recalculate_trial

        e = await svc.create_entry(db, group["G"].id, _data())
        updated = await svc.update_entry(db, e.id, group["G"].id, EliminationEntryUpdate(lines=[
            EliminationEntryLine(account_code="1001", account_name="货币资金", debit_amount=D("40")),
            EliminationEntryLine(account_code="1122", account_name="应收账款", credit_amount=D("40")),
        ]))
        assert [ln["account_code"] for ln in updated.lines] == ["1001", "1122"]
        assert (updated.account_code, updated.account_name) == ("1001", "货币资金")
        assert (updated.debit_amount, updated.credit_amount) == (D(40), D(40))

        updated.review_status = ReviewStatusEnum.approved
        await db.commit()
        by_code = {t.standard_account_code: t for t in await recalculate_trial(db, group["G"].id, Y)}
        assert by_code["1122"].consol_elimination == D(-40)  # 新明细行生效，旧的 2202 不再出现
        assert "2202" not in by_code

    @pytest.mark.asyncio
    async def test_update_attribution_validated(self, db, group):
        e = await svc.create_entry(db, group["G"].id, _data())
        with pytest.raises(ValueError, match="没有母分差额节点"):
            await svc.update_entry(db, e.id, group["G"].id, EliminationEntryUpdate(branch_entity_code="S"))
        moved = await svc.update_entry(db, e.id, group["G"].id, EliminationEntryUpdate(branch_entity_code="G"))
        assert moved.branch_entity_code == "G"
        back = await svc.update_entry(db, e.id, group["G"].id, EliminationEntryUpdate(branch_entity_code=None))
        assert back.branch_entity_code is None
        untouched = await svc.update_entry(db, e.id, group["G"].id, EliminationEntryUpdate(description="只改说明"))
        assert untouched.branch_entity_code is None and untouched.description == "只改说明"

    @pytest.mark.asyncio
    async def test_get_entry_excludes_soft_deleted(self, db, group):
        e = await svc.create_entry(db, group["G"].id, _data())
        assert await svc.delete_entry(db, e.id, group["G"].id) is True
        assert await svc.get_entry(db, e.id, group["G"].id) is None
        assert await svc.delete_entry(db, e.id, group["G"].id) is False  # 已删不可再删
        assert await svc.update_entry(db, e.id, group["G"].id, EliminationEntryUpdate(description="x")) is None

    @pytest.mark.asyncio
    async def test_list_filters_by_node(self, db, group):
        a = await svc.create_entry(db, group["G"].id, _data())
        b = await svc.create_entry(db, group["G"].id, _data(branch="G"))
        consol = await svc.get_entries(db, group["G"].id, Y, node_key="G:consol_elim")
        branch = await svc.get_entries(db, group["G"].id, Y, node_key="G:branch_elim")
        assert [e.id for e in consol] == [a.id] and [e.id for e in branch] == [b.id]
        assert len(await svc.get_entries(db, group["G"].id, Y)) == 2
        with pytest.raises(ValueError, match="差额节点"):
            await svc.get_entries(db, group["G"].id, Y, node_key="G:parent")


# ─────────────────────────────── 8.4 自动生成草稿预填归属 ───────────────────────────────


class TestAutoDraftPrefill:
    @pytest.mark.asyncio
    async def test_prefill_branch_when_both_parties_in_branch_closure(self, db, group):
        """母公司本部 ↔ 其分公司的内部往来 ⇒ 预填母公司的母分差额；本部 ↔ 子公司 ⇒ 留空（合并差额）。"""
        from app.services.consol_auto_elimination_service import auto_generate_draft_eliminations

        db.add(InternalArAp(
            id=uuid.uuid4(), project_id=group["G"].id, year=Y, debtor_company_code="G",
            creditor_company_code="GB", debtor_amount=D(80), creditor_amount=D(80),
        ))
        await db.commit()
        [draft] = await auto_generate_draft_eliminations(db, group["G"].id, Y)
        assert draft.review_status == ReviewStatusEnum.draft
        assert draft.branch_entity_code == "G"
        assert draft.related_company_codes == ["G", "GB"]

    @pytest.mark.asyncio
    async def test_prefill_empty_when_parties_span_subsidiary(self, db, group):
        from app.services.consol_auto_elimination_service import auto_generate_draft_eliminations

        db.add(InternalArAp(
            id=uuid.uuid4(), project_id=group["G"].id, year=Y, debtor_company_code="GB",
            creditor_company_code="S", debtor_amount=D(30), creditor_amount=D(30),
        ))
        await db.commit()
        [draft] = await auto_generate_draft_eliminations(db, group["G"].id, Y)
        assert draft.branch_entity_code is None

    def test_suggest_branch_entity_rules(self, group):
        """纯函数：公共祖先向上找「由本项目承载」的母分差额；跨越下级合并项目或有一方不在树中 ⇒ None。"""
        from app.services.consol_calc_basis import suggest_branch_entity
        from app.services.consol_group_tree import derive_group_tree, record_from_project

        recs = [record_from_project(p, Y) for p in group.values()]
        root_g = next(r for r in recs if r.id == group["G"].id)
        root_a = next(r for r in recs if r.id == group["A"].id)
        tree_g = derive_group_tree(recs, root_g, Y).root
        tree_a = derive_group_tree(recs, root_a, Y).root
        gid, aid = group["G"].id, group["A"].id
        assert suggest_branch_entity(tree_g, gid, ["G", "GB"]) == "G"
        assert suggest_branch_entity(tree_g, gid, ["GB"]) == "G"
        assert suggest_branch_entity(tree_g, gid, ["G", "S"]) is None
        # A 与 AB 的母分差额由 A 的合并项目承载：集团项目的草稿不预填
        assert suggest_branch_entity(tree_g, gid, ["A", "AB"]) is None
        assert suggest_branch_entity(tree_a, aid, ["A", "AB"]) == "A"
        assert suggest_branch_entity(tree_g, gid, ["G", "NOPE"]) is None
        assert suggest_branch_entity(tree_g, gid, []) is None


# ─────────────────────────────── 孤儿诊断（需求 6.4） ───────────────────────────────


@pytest.mark.asyncio
async def test_orphan_after_tree_change_listed_and_not_counted(db, group):
    """分公司 GB 删除后 G 不再有分公司 ⇒ 归属 G 母分差额的已审批分录成孤儿：重算列出，两条路径都不计入。"""
    from app.services.consol_trial_service import recalculate_trial
    from app.services.consol_worksheet_engine import recalc_full

    e = await svc.create_entry(db, group["G"].id, _data(branch="G"))
    e.review_status = ReviewStatusEnum.approved
    await db.commit()
    gb = await db.get(Project, group["GB"].id)
    gb.soft_delete()
    await db.commit()

    result = await recalc_full(db, group["G"].id, Y)
    assert [o["entry_no"] for o in result["orphan_entries"]] == [e.entry_no]
    assert "没有母分差额节点" in result["orphan_entries"][0]["reason"]
    by_code = {t.standard_account_code: t for t in await recalculate_trial(db, group["G"].id, Y)}
    assert by_code["1122"].consol_elimination == D(0)
    assert by_code["1122"].consol_amount == by_code["1122"].individual_sum == D(1500)


# ─────────────────────────────── 端点：真发请求 + 真实权限判定 ───────────────────────────────


class _User:
    def __init__(self, role: UserRole, uid: uuid.UUID):
        self.id = uid
        self.username = f"u_{role.value}"
        self.role = role
        self.is_active = True
        self.is_deleted = False


@pytest_asyncio.fixture
async def make_client(db: AsyncSession):
    from app.routers.consolidation import router

    app = FastAPI()
    app.include_router(router)

    async def _db():
        yield db

    def factory(user):
        app.dependency_overrides[get_db] = _db
        app.dependency_overrides[get_current_user] = lambda: user
        return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")

    return factory


def _payload(project_id, branch=None):
    return {
        "project_id": str(project_id), "year": Y, "entry_type": "internal_ar_ap", "description": "端点测试",
        "branch_entity_code": branch,
        "lines": [
            {"account_code": "1122", "account_name": "应收账款", "debit_amount": "60", "credit_amount": "0"},
            {"account_code": "2202", "account_name": "应付账款", "debit_amount": "0", "credit_amount": "60"},
        ],
    }


@pytest.mark.asyncio
async def test_endpoints_attribution_and_filter(db, group, make_client):
    admin = _User(UserRole.admin, uuid.uuid4())
    gid = group["G"].id
    async with make_client(admin) as c:
        ok = await c.post(f"/api/consolidation/eliminations?project_id={gid}", json=_payload(gid, "G"))
        assert ok.status_code == 201, ok.text
        body = ok.json()
        assert body["branch_entity_code"] == "G" and body["related_company_codes"] is None
        bad = await c.post(f"/api/consolidation/eliminations?project_id={gid}", json=_payload(gid, "A"))
        assert bad.status_code == 400 and "应到该合并项目录入" in bad.json()["detail"]

        listed = await c.get(f"/api/consolidation/eliminations?project_id={gid}&year={Y}&node_key=G:branch_elim")
        assert listed.status_code == 200 and [r["id"] for r in listed.json()] == [body["id"]]
        empty = await c.get(f"/api/consolidation/eliminations?project_id={gid}&year={Y}&node_key=G:consol_elim")
        assert empty.json() == []
        wrong = await c.get(f"/api/consolidation/eliminations?project_id={gid}&node_key=G:hq")
        assert wrong.status_code == 400

        put = await c.put(f"/api/consolidation/eliminations/{body['id']}?project_id={gid}",
                          json={"branch_entity_code": "S"})
        assert put.status_code == 400
        gone = await c.delete(f"/api/consolidation/eliminations/{body['id']}?project_id={gid}")
        assert gone.status_code == 204
        read = await c.get(f"/api/consolidation/eliminations/{body['id']}?project_id={gid}")
        assert read.status_code == 404  # 软删后读取不到（需求 6.5）


@pytest.mark.asyncio
async def test_endpoints_require_project_membership(db, group, make_client):
    """非 admin：不是项目成员 ⇒ 403；只读成员可列表不可新增；编辑成员可新增。"""
    gid = group["G"].id
    outsider = _User(UserRole.auditor, uuid.uuid4())
    reader = _User(UserRole.auditor, uuid.uuid4())
    editor = _User(UserRole.auditor, uuid.uuid4())
    for u in (outsider, reader, editor):
        db.add(User(id=u.id, username=u.username + u.id.hex[:6], email=f"{u.id.hex[:8]}@t.local",
                    hashed_password="x", role=u.role))
    db.add(ProjectUser(project_id=gid, user_id=reader.id, role="auditor", permission_level=PermissionLevel.readonly))
    db.add(ProjectUser(project_id=gid, user_id=editor.id, role="auditor", permission_level=PermissionLevel.edit))
    await db.commit()

    async with make_client(outsider) as c:
        assert (await c.get(f"/api/consolidation/eliminations?project_id={gid}")).status_code == 403
    async with make_client(reader) as c:
        assert (await c.get(f"/api/consolidation/eliminations?project_id={gid}")).status_code == 200
        denied = await c.post(f"/api/consolidation/eliminations?project_id={gid}", json=_payload(gid))
        assert denied.status_code == 403
    async with make_client(editor) as c:
        created = await c.post(f"/api/consolidation/eliminations?project_id={gid}", json=_payload(gid))
        assert created.status_code == 201, created.text
