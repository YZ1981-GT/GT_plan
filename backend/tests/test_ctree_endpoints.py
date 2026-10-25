"""接口（spec consol-tree-three-code-autobuild 任务 9.3）：真 SQLite + 真 ORM 行 + 真发请求（ASGITransport）。

鉴权走真实实现：只替换 ``get_current_user`` / ``get_db``，``require_project_access`` 与森林可见性判定本身不替换。

- ``GET /api/consolidation/worksheet/tree``：``{tree, mode, mode_label, diagnostics, year}``；节点带 node_key 等新字段；
  诊断含未归属的已审批分录（重算没计入的同一批）与未审批分录；非成员 403；项目不存在给说明；
- ``GET /api/consolidation/worksheet/accounts``：试算表科目 ∪ 分录明细行科目，名称/方向与计算口径同源；只读成员可读；
- ``GET /api/projects/tree``：P14（非 admin/partner 只见参与的项目、上级不可见不标脱挂）；admin/partner 全部可见；
  企业实体合并两口径；只填审计年度的项目按年度能查到；
- 分录审批流：提交审批 → 审批；审批前重新校验归属（树变化后不能审批找不到归属的分录）；
- 合并范围校对取合并企业树的子公司类企业（分公司、母公司不算合并范围成员，需求 11.3）。
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON  # type: ignore[attr-defined]

from app.core.database import get_db  # noqa: E402
from app.deps import get_current_user  # noqa: E402
from app.models.audit_platform_models import AccountCategory, TrialBalance  # noqa: E402
from app.models.base import Base, PermissionLevel, ProjectStatus, UserRole  # noqa: E402
from app.models.consolidation_models import EliminationEntry, EliminationEntryType, ReviewStatusEnum  # noqa: E402
from app.models.core import Project, ProjectUser, User  # noqa: E402

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


def _p(code, name, scope, *, parent=None, relation=None, ultimate=None, year=Y, **kw):
    return Project(
        id=uuid.uuid4(), name=f"{name}_{year}", client_name=name, company_code=code, report_scope=scope,
        audit_year=year, parent_company_code=parent, relation_to_parent=relation,
        ultimate_company_code=ultimate, status=ProjectStatus.execution, **kw,
    )


def _tb(project, code, name, category, amount):
    return TrialBalance(
        id=uuid.uuid4(), project_id=project.id, year=Y, company_code="001", standard_account_code=code,
        account_name=name, account_category=category, audited_amount=D(amount),
    )


@pytest_asyncio.fixture
async def group(db: AsyncSession) -> dict[str, Project]:
    """G（合并+单户）⊃ 分公司 GB、子公司 A（单户）；另一集团 H 的单户项目；上一年度 G 的合并项目。"""
    g = {
        "G": _p("G", "某集团", "consolidated", ultimate="G"),
        "G_s": _p("G", "某集团", "standalone", ultimate="G"),
        "GB": _p("GB", "某集团北京分公司", "standalone", parent="G", relation="branch", ultimate="G"),
        "A": _p("A", "甲公司", "standalone", parent="G", relation="subsidiary", ultimate="G"),
        "H": _p("H", "另一集团", "standalone", ultimate="H"),
        "G24": _p("G", "某集团", "consolidated", ultimate="G", year=2024),
    }
    db.add_all(g.values())
    db.add_all([
        _tb(g["G_s"], "1122", "应收账款", AccountCategory.asset, "1000"),
        _tb(g["A"], "2202", "应付账款", AccountCategory.liability, "400"),
        _tb(g["GB"], "1122", "应收账款", AccountCategory.asset, "300"),
    ])
    await db.flush()
    from app.services.group_links import sync_group_links

    for year in (2024, Y):  # 与建项写路径一致：派生链接已按三码重算（否则树诊断会报链接不一致）
        await sync_group_links(db, year)
    await db.commit()
    return g


class _User:
    def __init__(self, role: UserRole):
        self.id = uuid.uuid4()
        self.username = f"u_{role.value}_{self.id.hex[:6]}"
        self.role = role
        self.is_active = True
        self.is_deleted = False


async def _persist(db, user: _User, memberships=()):
    db.add(User(id=user.id, username=user.username, email=f"{user.id.hex[:8]}@t.local",
                hashed_password="x", role=user.role))
    for project, level in memberships:
        db.add(ProjectUser(project_id=project.id, user_id=user.id, role="auditor", permission_level=level))
    await db.commit()
    return user


@pytest_asyncio.fixture
async def client_for(db: AsyncSession):
    from app.routers.batch_project import router as batch_router
    from app.routers.consol_worksheet import router as worksheet_router
    from app.routers.consolidation import router as elim_router
    from app.routers.project_wizard import router as wizard_router

    app = FastAPI()
    for r in (batch_router, wizard_router, worksheet_router, elim_router):
        app.include_router(r)

    async def _db():
        yield db

    def factory(user):
        app.dependency_overrides[get_db] = _db
        app.dependency_overrides[get_current_user] = lambda: user
        return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")

    return factory


def _walk(node):
    yield node
    for c in node.get("children") or []:
        yield from _walk(c)


def _forest_nodes(forest):
    for t in forest["trees"]:
        for c in t["children"]:
            yield from _walk(c)
    for n in forest["independents"]:
        yield from _walk(n)


def _entry(project, no, lines, *, branch=None, status=ReviewStatusEnum.approved):
    return EliminationEntry(
        id=uuid.uuid4(), project_id=project.id, year=Y, entry_no=no, entry_type=EliminationEntryType.internal_ar_ap,
        account_code=lines[0][0], account_name=lines[0][1], entry_group_id=uuid.uuid4(),
        lines=[{"account_code": c, "account_name": n, "debit_amount": dr, "credit_amount": cr}
               for c, n, dr, cr in lines],
        debit_amount=D(lines[0][2]), credit_amount=D(lines[0][2]),
        branch_entity_code=branch, review_status=status,
    )


# ─────────────────────────────── worksheet/tree ───────────────────────────────


class TestWorksheetTree:
    @pytest.mark.asyncio
    async def test_payload_mode_year_and_node_fields(self, db, group, client_for):
        admin = _User(UserRole.admin)
        async with client_for(admin) as c:
            resp = await c.get("/api/consolidation/worksheet/tree", params={"project_id": str(group["G"].id)})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert (body["mode"], body["mode_label"], body["year"]) == ("mixed", "母子合并＋总分汇总", Y)
        tree = body["tree"]
        assert (tree["node_key"], tree["role"], tree["kind"], tree["display_name"]) == (
            "G:consol", "consol", "aggregate", "某集团（合并）",
        )
        assert tree["project_id"] == str(group["G"].id) and tree["company_code"] == "G"  # 旧字段保留
        keys = [n["node_key"] for n in _walk(tree)]
        assert keys == ["G:consol", "G:consol_elim", "G:parent", "G:branch_elim", "G:hq", "GB:branch", "A:subsidiary"]
        elim = next(n for n in _walk(tree) if n["node_key"] == "G:consol_elim")
        assert elim["project_id"] is None and elim["host_project_id"] == str(group["G"].id)
        assert next(n for n in _walk(tree) if n["node_key"] == "A:subsidiary")["relation"] == "subsidiary"
        assert body["diagnostics"] == []
        assert str(group["G24"].id) not in {n["project_id"] for n in _walk(tree)}, "上一年度项目不进本树"

    @pytest.mark.asyncio
    async def test_orphan_diagnostics_match_recalc(self, db, group, client_for):
        """树变化后失去归属的分录 ⇒ 诊断列出；已审批的与重算结果的孤儿清单是同一批；草稿也提示。"""
        from app.services.consol_worksheet_engine import recalc_full

        approved = _entry(group["G"], "E-A", [("1122", "应收账款", "50", "0"), ("2202", "应付账款", "0", "50")],
                          branch="G")
        draft = _entry(group["G"], "E-D", [("1122", "应收账款", "5", "0"), ("2202", "应付账款", "0", "5")],
                       branch="G", status=ReviewStatusEnum.draft)
        fine = _entry(group["G"], "E-OK", [("1122", "应收账款", "7", "0"), ("2202", "应付账款", "0", "7")])
        db.add_all([approved, draft, fine])
        gb = await db.get(Project, group["GB"].id)
        gb.soft_delete()  # G 不再有分公司 ⇒ 母分差额节点消失
        await db.commit()

        admin = _User(UserRole.admin)
        async with client_for(admin) as c:
            body = (await c.get("/api/consolidation/worksheet/tree",
                                params={"project_id": str(group["G"].id)})).json()
        orphan_msgs = [d["message"] for d in body["diagnostics"] if d["code"] == "orphan_entries"]
        assert len(orphan_msgs) == 2
        assert any(m.startswith("分录 E-A 未计入合并") for m in orphan_msgs)
        assert any(m.startswith("分录 E-D（草稿）找不到归属节点") and "提交审批" in m for m in orphan_msgs)
        assert body["mode"] == "subsidiary"

        recalc = await recalc_full(db, group["G"].id, Y)
        assert [o["entry_no"] for o in recalc["orphan_entries"]] == ["E-A"]

    @pytest.mark.asyncio
    async def test_auth_and_missing_project(self, db, group, client_for):
        outsider = await _persist(db, _User(UserRole.auditor))
        reader = await _persist(db, _User(UserRole.auditor), [(group["G"], PermissionLevel.readonly)])
        pid = str(group["G"].id)
        async with client_for(outsider) as c:
            assert (await c.get("/api/consolidation/worksheet/tree", params={"project_id": pid})).status_code == 403
        async with client_for(reader) as c:
            assert (await c.get("/api/consolidation/worksheet/tree", params={"project_id": pid})).status_code == 200
        admin = _User(UserRole.admin)
        async with client_for(admin) as c:
            gone = await c.get("/api/consolidation/worksheet/tree", params={"project_id": str(uuid.uuid4())})
        assert gone.status_code == 200
        assert gone.json()["tree"] is None and gone.json()["message"] == "项目不存在或已删除"

    @pytest.mark.asyncio
    async def test_standalone_root_reports_not_consolidated(self, db, group, client_for):
        admin = _User(UserRole.admin)
        async with client_for(admin) as c:
            body = (await c.get("/api/consolidation/worksheet/tree",
                                params={"project_id": str(group["A"].id)})).json()
        assert body["tree"]["node_key"] == "A:parent" and body["mode"] == "none"
        assert [d["code"] for d in body["diagnostics"]] == ["root_not_consolidated"]


# ─────────────────────────────── worksheet/accounts ───────────────────────────────


class TestWorksheetAccounts:
    @pytest.mark.asyncio
    async def test_accounts_union_with_direction(self, db, group, client_for):
        """试算表科目 ∪ 分录明细行科目（含草稿）；方向与计算口径同一判定；其他树的科目不出现。"""
        db.add(_TB_OTHER := _tb(group["H"], "1001", "货币资金", AccountCategory.asset, "9"))
        db.add(_entry(group["G"], "E-1", [("6001", "营业收入", "20", "0"), ("6401", "营业成本", "0", "20")],
                      status=ReviewStatusEnum.draft))
        await db.commit()
        reader = await _persist(db, _User(UserRole.auditor), [(group["G"], PermissionLevel.readonly)])
        async with client_for(reader) as c:
            resp = await c.get("/api/consolidation/worksheet/accounts", params={"project_id": str(group["G"].id)})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["year"] == Y
        rows = {a["account_code"]: a for a in body["accounts"]}
        assert list(rows) == ["1122", "2202", "6001", "6401"], "1001 属于别的集团，不出现"
        assert rows["1122"] == {
            "account_code": "1122", "account_name": "应收账款", "account_category": "asset",
            "direction": "debit", "in_trial_balance": True, "in_entries": False,
        }
        assert (rows["2202"]["direction"], rows["2202"]["account_category"]) == ("credit", "liability")
        assert (rows["6001"]["in_trial_balance"], rows["6001"]["in_entries"]) == (False, True)
        assert rows["6001"]["direction"] == "credit" and rows["6401"]["direction"] == "debit"
        assert _TB_OTHER.standard_account_code not in rows

    @pytest.mark.asyncio
    async def test_accounts_auth_and_404(self, db, group, client_for):
        outsider = await _persist(db, _User(UserRole.auditor))
        async with client_for(outsider) as c:
            denied = await c.get("/api/consolidation/worksheet/accounts", params={"project_id": str(group["G"].id)})
        assert denied.status_code == 403
        admin = _User(UserRole.admin)
        async with client_for(admin) as c:
            missing = await c.get("/api/consolidation/worksheet/accounts", params={"project_id": str(uuid.uuid4())})
            other_year = await c.get("/api/consolidation/worksheet/accounts",
                                     params={"project_id": str(group["G"].id), "year": 2024})
        assert missing.status_code == 404
        assert other_year.json() == {"year": 2024, "accounts": []}


# ─────────────────────────────── worksheet/node-amounts ───────────────────────────────


class TestNodeAmounts:
    @pytest.mark.asyncio
    async def test_live_amounts_equal_recalculated_worksheet(self, db, group, client_for):
        """面板节点金额 = 计算口径实时求值 = 重算写入差额表的数（逐列相等）；草稿不计入。"""
        from app.models.consolidation_models import ConsolWorksheet
        from app.services.consol_worksheet_engine import recalc_full

        db.add_all([
            _entry(group["G"], "E-1", [("1122", "应收账款", "7", "0"), ("2202", "应付账款", "0", "7")]),
            _entry(group["G"], "E-D", [("1122", "应收账款", "9", "0"), ("2202", "应付账款", "0", "9")],
                   status=ReviewStatusEnum.draft),
        ])
        await db.commit()
        reader = await _persist(db, _User(UserRole.auditor), [(group["G"], PermissionLevel.readonly)])
        async with client_for(reader) as c:
            resp = await c.get("/api/consolidation/worksheet/node-amounts",
                               params={"project_id": str(group["G"].id), "node_key": "G:consol_elim"})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert (body["year"], body["node_key"], body["kind"], body["display_name"]) == (
            Y, "G:consol_elim", "elim", "某集团（合并差额）",
        )
        rows = {r["account_code"]: r for r in body["rows"]}
        assert list(rows) == ["1122", "2202"]
        assert (rows["1122"]["elimination_debit"], rows["1122"]["net_difference"]) == ("7.00", "7.00")
        assert (rows["2202"]["elimination_credit"], rows["2202"]["net_difference"]) == ("7.00", "7.00")
        assert rows["2202"]["direction"] == "credit"

        await recalc_full(db, group["G"].id, Y)
        stored = {
            r.account_code: r for r in (await db.execute(
                ConsolWorksheet.__table__.select().where(
                    ConsolWorksheet.node_company_code == "G:consol_elim",
                    ConsolWorksheet.is_deleted.is_(False),
                )
            )).all()
        }
        for code, row in rows.items():
            for col in ("elimination_debit", "elimination_credit", "net_difference", "consolidated_amount"):
                assert D(row[col]) == getattr(stored[code], col), (code, col)

    @pytest.mark.asyncio
    async def test_data_node_and_errors(self, db, group, client_for):
        admin = _User(UserRole.admin)
        async with client_for(admin) as c:
            hq = await c.get("/api/consolidation/worksheet/node-amounts",
                             params={"project_id": str(group["G"].id), "node_key": "G:hq"})
            unknown = await c.get("/api/consolidation/worksheet/node-amounts",
                                  params={"project_id": str(group["G"].id), "node_key": "NOPE:consol_elim"})
            missing = await c.get("/api/consolidation/worksheet/node-amounts",
                                  params={"project_id": str(uuid.uuid4()), "node_key": "G:consol"})
        assert [(r["account_code"], r["consolidated_amount"]) for r in hq.json()["rows"]] == [("1122", "1000.00")]
        assert unknown.status_code == 404 and "NOPE:consol_elim" in unknown.json()["detail"]
        assert missing.status_code == 404
        outsider = await _persist(db, _User(UserRole.auditor))
        async with client_for(outsider) as c:
            denied = await c.get("/api/consolidation/worksheet/node-amounts",
                                 params={"project_id": str(group["G"].id), "node_key": "G:consol"})
        assert denied.status_code == 403


# ─────────────────────────────── /api/projects/tree（P14） ───────────────────────────────


class TestProjectsTree:
    @pytest.mark.asyncio
    async def test_p14_auditor_sees_only_member_projects(self, db, group, client_for):
        """P14：非 admin/partner 只见参与的项目；上级不可见 ⇒ 标「上级不可见」而不是脱挂。"""
        auditor = await _persist(db, _User(UserRole.auditor), [
            (group["A"], PermissionLevel.readonly), (group["H"], PermissionLevel.edit),
        ])
        async with client_for(auditor) as c:
            resp = await c.get("/api/projects/tree")
        assert resp.status_code == 200, resp.text
        forest = resp.json()
        ids = sorted(p["id"] for n in _forest_nodes(forest) for p in n["projects"])
        assert ids == sorted([str(group["A"].id), str(group["H"].id)])
        a = next(n for n in _forest_nodes(forest) if n["companyCode"] == "A")
        assert "parent_hidden" in a["flags"] and not a["isDetached"]
        assert "某集团" not in str(forest), "不可见项目的名称不出现在响应里"

    @pytest.mark.asyncio
    async def test_hidden_legacy_parent_resolved_by_name_suffix(self, db, group, client_for):
        """不可见上级是只能靠项目名后缀解析年度的旧项目 ⇒ 仍判「上级不可见」，不误标脱挂。"""
        legacy = Project(
            id=uuid.uuid4(), name=f"某控股_{Y}", client_name="某控股", company_code="P", report_scope="standalone",
            audit_year=None, status=ProjectStatus.execution,
        )
        child = _p("C", "丁公司", "standalone", parent="P", relation="subsidiary")
        db.add_all([legacy, child])
        await db.commit()
        auditor = await _persist(db, _User(UserRole.auditor), [(child, PermissionLevel.readonly)])
        async with client_for(auditor) as c:
            forest = (await c.get("/api/projects/tree")).json()
        [n] = list(_forest_nodes(forest))
        assert n["companyCode"] == "C" and "parent_hidden" in n["flags"] and not n["isDetached"]

    @pytest.mark.asyncio
    async def test_p14_manager_without_membership_sees_nothing(self, db, group, client_for):
        manager = await _persist(db, _User(UserRole.manager))
        async with client_for(manager) as c:
            forest = (await c.get("/api/projects/tree")).json()
        assert forest == {"trees": [], "independents": []}

    @pytest.mark.asyncio
    @pytest.mark.parametrize("role", [UserRole.admin, UserRole.partner])
    async def test_p14_admin_and_partner_see_all(self, db, group, client_for, role):
        user = await _persist(db, _User(role))
        async with client_for(user) as c:
            forest = (await c.get("/api/projects/tree")).json()
        ids = sorted(p["id"] for n in _forest_nodes(forest) for p in n["projects"])
        assert ids == sorted(str(p.id) for p in group.values())

    @pytest.mark.asyncio
    async def test_entity_merge_year_and_grouping(self, db, group, client_for):
        """企业实体合并两口径；只填审计年度的项目按年度能查到（F11）；未传年度按（控制方, 年度）分树。"""
        admin = _User(UserRole.admin)
        async with client_for(admin) as c:
            by_year = (await c.get("/api/projects/tree", params={"year": Y})).json()
            all_years = (await c.get("/api/projects/tree")).json()
            consol_only = (await c.get("/api/projects/tree", params={"year": Y, "scope": "consolidated"})).json()
        g_tree = next(t for t in by_year["trees"] if t["ultimateCode"] == "G")
        root = g_tree["children"][0]
        assert root["companyCode"] == "G" and g_tree["rootProjectId"] == str(group["G"].id)
        assert {p["id"] for p in root["projects"]} == {str(group["G"].id), str(group["G_s"].id)}
        assert [c["companyCode"] for c in root["children"]] == ["GB", "A"]
        assert next(c for c in root["children"] if c["companyCode"] == "GB")["relation"] == "branch"
        assert sorted((t["ultimateCode"], t["year"]) for t in all_years["trees"]) == [
            ("G", 2024), ("G", 2025), ("H", 2025),
        ], "控制方是自己的单户企业自成一棵树（与旧实现一致）"
        assert all_years["independents"] == []
        [only] = consol_only["trees"]
        assert [n["companyCode"] for n in _walk(only["children"][0])] == ["G"]


# ─────────────────────────────── 分录审批流 ───────────────────────────────


def _payload(project, branch=None):
    return {
        "project_id": str(project.id), "year": Y, "entry_type": "internal_ar_ap", "description": "审批流测试",
        "branch_entity_code": branch,
        "lines": [
            {"account_code": "1122", "account_name": "应收账款", "debit_amount": "30", "credit_amount": "0"},
            {"account_code": "2202", "account_name": "应付账款", "debit_amount": "0", "credit_amount": "30"},
        ],
    }


class TestReviewFlow:
    @pytest.mark.asyncio
    async def test_submit_then_approve(self, db, group, client_for):
        admin = _User(UserRole.admin)
        gid = str(group["G"].id)
        async with client_for(admin) as c:
            created = (await c.post(f"/api/consolidation/eliminations?project_id={gid}", json=_payload(group["G"]))).json()
            eid = created["id"]
            submitted = await c.post(f"/api/consolidation/eliminations/{eid}/review?project_id={gid}",
                                     json={"action": "submit"})
            assert submitted.status_code == 200, submitted.text
            assert submitted.json()["review_status"] == "pending_review"
            again = await c.post(f"/api/consolidation/eliminations/{eid}/review?project_id={gid}",
                                 json={"action": "submit"})
            assert again.status_code == 400 and "待审批" in again.json()["detail"]
            approved = await c.post(f"/api/consolidation/eliminations/{eid}/review?project_id={gid}",
                                    json={"action": "approve"})
            assert approved.status_code == 200 and approved.json()["review_status"] == "approved"

    @pytest.mark.asyncio
    async def test_rejected_can_be_resubmitted(self, db, group, client_for):
        admin = _User(UserRole.admin)
        gid = str(group["G"].id)
        async with client_for(admin) as c:
            eid = (await c.post(f"/api/consolidation/eliminations?project_id={gid}", json=_payload(group["G"]))).json()["id"]
            rejected = await c.post(f"/api/consolidation/eliminations/{eid}/review?project_id={gid}",
                                    json={"action": "reject", "rejection_reason": "金额需核对"})
            assert rejected.json()["review_status"] == "rejected"
            resubmitted = await c.post(f"/api/consolidation/eliminations/{eid}/review?project_id={gid}",
                                       json={"action": "submit"})
            assert resubmitted.status_code == 200 and resubmitted.json()["review_status"] == "pending_review"

    @pytest.mark.asyncio
    async def test_approve_revalidates_attribution(self, db, group, client_for):
        """录入时归属合法、之后分公司删除 ⇒ 母分差额节点消失 ⇒ 提交与审批都被拦（能审批 ⇔ 会被计入）。"""
        admin = _User(UserRole.admin)
        gid = str(group["G"].id)
        async with client_for(admin) as c:
            eid = (await c.post(f"/api/consolidation/eliminations?project_id={gid}",
                                json=_payload(group["G"], branch="G"))).json()["id"]
            gb = await db.get(Project, group["GB"].id)
            gb.soft_delete()
            await db.commit()
            for action in ("submit", "approve"):
                resp = await c.post(f"/api/consolidation/eliminations/{eid}/review?project_id={gid}",
                                    json={"action": action})
                assert resp.status_code == 400 and "没有母分差额节点" in resp.json()["detail"], action
        entry = await db.get(EliminationEntry, uuid.UUID(eid))
        await db.refresh(entry)
        assert entry.review_status == ReviewStatusEnum.draft


# ─────────────────────────────── 合并范围校对（需求 11.3） ───────────────────────────────


@pytest.mark.asyncio
async def test_scope_diff_uses_consolidation_tree_members(db, group):
    """T = 合并企业树中的子公司类企业：分公司 GB 与母公司 G 不是合并范围成员；按控制方挂靠的也算。"""
    from app.services.scope_diff_service import compute_scope_diff

    db.add(_p("X", "丙公司", "standalone", ultimate="G"))  # 没有上级 ⇒ 按控制方挂到 G（合并）下
    await db.commit()
    diff = await compute_scope_diff(db, group["G"].id)
    assert [d["company_code"] for d in diff["in_tree_not_scope"]] == ["A", "X"]
    assert diff["in_scope_not_tree"] == []
