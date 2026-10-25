"""合并差额表深度开发测试（spec consol-tree-three-code-autobuild 任务 7.6 按三码三节点模型改写）

覆盖：
- Task 15: 树形服务 (build_tree / find_node / get_descendants / to_dict)
- Task 16: 差额表计算引擎 (recalc_full / 数据节点 / 汇总节点 / 差额节点)
- Task 17: 节点汇总查询 (self / children / descendants)
- Task 18: 穿透查询 (drill_to_companies / drill_to_eliminations / drill_to_trial_balance)
- Task 19: 透视查询 + 模板 CRUD

有意的口径变更（旧断言不作为正确性依据，design §十二）：
- 树按三码推导（不再读 parent_project_id）：有合并项目的企业一次生成「合并 / 合并差额 / 母公司」三节点，
  差额表键是 node_key（``{企业代码}:{角色}``），不再是纯企业代码；
- 汇总节点 = Σ 直接子节点，母公司本体经「母公司」数据节点计入（旧版中间节点不含本体，F5）；
- 分录金额只计入归属的差额节点（合并项目的「合并差额」），不再按 related_company_codes 分摊到
  每个相关企业（F6 双计）；金额取明细行并按科目方向归一（F7）；「其他调整」进调整列。

集团（审计年度 2025）：
  ROOT 集团总公司（合并 + 单户）
    ├── A001 子公司A（合并 + 单户）
    │     └── C001 孙公司C（单户）
    └── B001 子公司B（单户）
"""

import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base

# Import all models so metadata is populated
import app.models.core  # noqa: F401
import app.models.audit_platform_models  # noqa: F401
import app.models.report_models  # noqa: F401
import app.models.workpaper_models  # noqa: F401
import app.models.consolidation_models  # noqa: F401
import app.models.staff_models  # noqa: F401
import app.models.collaboration_models  # noqa: F401
import app.models.ai_models  # noqa: F401
import app.models.extension_models  # noqa: F401
import app.models.gt_coding_models  # noqa: F401
import app.models.t_account_models  # noqa: F401
import app.models.attachment_models  # noqa: F401

from app.models.core import Project
from app.models.base import ProjectStatus
from app.models.audit_platform_models import TrialBalance, AccountCategory
from app.models.consolidation_models import (
    ConsolWorksheet,
    EliminationEntry,
    EliminationEntryType,
    ReviewStatusEnum,
)

# SQLite compat
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON


class _WorkpaperStub(Base):
    __tablename__ = "workpapers"
    __table_args__ = {"extend_existing": True}
    id = sa.Column(sa.Uuid, primary_key=True)


TEST_DB_URL = "sqlite+aiosqlite:///:memory:"
engine = create_async_engine(TEST_DB_URL, echo=False)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

YEAR = 2025
ROOT_C = uuid.uuid4()   # 集团合并项目
ROOT_S = uuid.uuid4()   # 集团单户项目（母公司本体数据）
A_C = uuid.uuid4()      # 子公司A 合并项目
A_S = uuid.uuid4()      # 子公司A 单户项目
B_S = uuid.uuid4()      # 子公司B 单户项目
C_S = uuid.uuid4()      # 孙公司C 单户项目

NAMES = {"1001": "货币资金", "1122": "应收账款", "2202": "应付账款", "6001": "营业收入", "6401": "营业成本"}
CATEGORY = {"1001": AccountCategory.asset, "1122": AccountCategory.asset, "2202": AccountCategory.liability}


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session


def _project(pid, code, name, scope, parent=None):
    return Project(
        id=pid, name=f"{name}_{YEAR}", client_name=name, company_code=code,
        parent_company_code=parent, ultimate_company_code="ROOT",
        relation_to_parent="subsidiary" if parent else None,
        report_scope=scope, audit_year=YEAR, status=ProjectStatus.execution,
    )


def _entry(pid, no, entry_type, lines, *, status=ReviewStatusEnum.approved, related=None, branch=None):
    debit = sum((Decimal(str(ln[1])) for ln in lines), Decimal("0"))
    credit = sum((Decimal(str(ln[2])) for ln in lines), Decimal("0"))
    return EliminationEntry(
        id=uuid.uuid4(), project_id=pid, year=YEAR, entry_no=no, entry_type=entry_type,
        account_code=lines[0][0], account_name=NAMES[lines[0][0]],
        debit_amount=debit, credit_amount=credit,
        lines=[
            {"account_code": code, "account_name": NAMES[code], "debit_amount": str(dr), "credit_amount": str(cr)}
            for code, dr, cr in lines
        ],
        entry_group_id=uuid.uuid4(), related_company_codes=related or [],
        branch_entity_code=branch, review_status=status,
    )


@pytest_asyncio.fixture
async def seeded_db(db_session: AsyncSession):
    """三级集团 + 各单户试算表 + 分录（见模块 docstring）。

    分录：
    - IA-2025-001（集团合并项目，内部往来，已审批）：借 应付账款 200 / 贷 应收账款 200
    - OT-2025-001（集团合并项目，其他调整，已审批）：借 货币资金 10 / 贷 应付账款 10 ⇒ 调整列
    - IT-2025-001（子公司A 合并项目，内部交易，已审批）：借 营业收入 50 / 贷 营业成本 50（科目只在分录里出现）
    - IA-2025-002（集团合并项目，草稿）：不计入
    - IA-2025-003（集团合并项目，已审批，归属 B001 的母分差额 —— B001 没有分公司）：孤儿，不计入
    """
    db_session.add_all([
        _project(ROOT_C, "ROOT", "集团总公司", "consolidated"),
        _project(ROOT_S, "ROOT", "集团总公司", "standalone"),
        _project(A_C, "A001", "子公司A", "consolidated", parent="ROOT"),
        _project(A_S, "A001", "子公司A", "standalone", parent="ROOT"),
        _project(B_S, "B001", "子公司B", "standalone", parent="ROOT"),
        _project(C_S, "C001", "孙公司C", "standalone", parent="A001"),
    ])
    for pid, amounts in [
        (ROOT_S, {"1001": 5000, "1122": 400, "2202": 900}),
        (A_S, {"1001": 1000, "1122": 500}),
        (B_S, {"1001": 2000, "2202": 300}),
        (C_S, {"1001": 300, "1122": 100}),
    ]:
        for code, amt in amounts.items():
            db_session.add(TrialBalance(
                id=uuid.uuid4(), project_id=pid, year=YEAR, company_code="001",
                standard_account_code=code, account_name=NAMES[code], account_category=CATEGORY[code],
                audited_amount=Decimal(str(amt)), unadjusted_amount=Decimal(str(amt)),
                rje_adjustment=Decimal("0"), aje_adjustment=Decimal("0"),
            ))
    ia = EliminationEntryType.internal_ar_ap
    db_session.add_all([
        _entry(ROOT_C, "IA-2025-001", ia, [("2202", 200, 0), ("1122", 0, 200)], related=["A001", "B001"]),
        _entry(ROOT_C, "OT-2025-001", EliminationEntryType.other, [("1001", 10, 0), ("2202", 0, 10)]),
        _entry(A_C, "IT-2025-001", EliminationEntryType.internal_trade, [("6001", 50, 0), ("6401", 0, 50)],
               related=["A001", "C001"]),
        _entry(ROOT_C, "IA-2025-002", ia, [("1001", 999, 0), ("1122", 0, 999)], status=ReviewStatusEnum.draft),
        _entry(ROOT_C, "IA-2025-003", ia, [("1001", 7, 0), ("1122", 0, 7)], related=["B001"], branch="B001"),
    ])
    await db_session.commit()
    return ROOT_C


async def _ws(db: AsyncSession, node_key: str, account: str) -> ConsolWorksheet:
    return (await db.execute(
        sa.select(ConsolWorksheet).where(
            ConsolWorksheet.project_id == ROOT_C,
            ConsolWorksheet.node_company_code == node_key,
            ConsolWorksheet.account_code == account,
            ConsolWorksheet.is_deleted == sa.false(),
        )
    )).scalar_one()


def D(value) -> Decimal:
    return Decimal(str(value))


# ===========================================================================
# Task 15: 树形服务测试
# ===========================================================================


@pytest.mark.asyncio
async def test_build_tree_three_nodes(db_session: AsyncSession, seeded_db):
    """15.5 树按三码推导：有合并项目的企业生成「合并 / 合并差额 / 母公司」三节点，嵌套正确。

    口径变更：旧版根的直接子节点是 A001、B001 两家企业；三码树里根的直接子节点是
    合并差额、母公司数据与两家子公司（A001 有合并项目 ⇒ 递归生成三节点）。
    """
    from app.services.consol_tree_service import build_tree

    tree = await build_tree(db_session, seeded_db)
    assert tree is not None
    assert tree.node_key == "ROOT:consol" and tree.company_code == "ROOT"
    assert tree.mode == "subsidiary"
    assert [c.node_key for c in tree.children] == [
        "ROOT:consol_elim", "ROOT:parent", "A001:consol", "B001:subsidiary",
    ]
    a = tree.children[2]
    assert [c.node_key for c in a.children] == ["A001:consol_elim", "A001:parent", "C001:subsidiary"]
    assert a.children[1].project_id == A_S and a.children[2].project_id == C_S
    assert tree.children[0].host_project_id == ROOT_C and tree.children[0].project_id is None
    assert a.children[0].host_project_id == A_C
    assert tree.children[3].children == []


@pytest.mark.asyncio
async def test_find_node(db_session: AsyncSession, seeded_db):
    """find_node：node_key 精确定位；纯企业代码取该代码首个节点（兼容旧调用方）。"""
    from app.services.consol_tree_service import build_tree, find_node

    tree = await build_tree(db_session, seeded_db)
    node = find_node(tree, "C001")
    assert node is not None and node.company_name == "孙公司C" and node.node_key == "C001:subsidiary"
    # A001 先序首个节点是它的合并节点
    assert find_node(tree, "A001").node_key == "A001:consol"
    assert find_node(tree, "A001:parent").project_id == A_S
    assert find_node(tree, "NONEXIST") is None
    assert find_node(tree, "A001:hq") is None


@pytest.mark.asyncio
async def test_get_descendants(db_session: AsyncSession, seeded_db):
    """get_descendants：根的后代 = 7 个节点（旧版 3 个企业）。"""
    from app.services.consol_tree_service import build_tree, find_node, get_descendants

    tree = await build_tree(db_session, seeded_db)
    descs = get_descendants(tree)
    assert [d.node_key for d in descs] == [
        "ROOT:consol_elim", "ROOT:parent", "A001:consol", "A001:consol_elim", "A001:parent",
        "C001:subsidiary", "B001:subsidiary",
    ]
    a_descs = get_descendants(find_node(tree, "A001:consol"))
    assert {d.node_key for d in a_descs} == {"A001:consol_elim", "A001:parent", "C001:subsidiary"}


@pytest.mark.asyncio
async def test_to_dict(db_session: AsyncSession, seeded_db):
    """to_dict：保留旧字段并追加 node_key/role/kind/display_name/host_project_id。"""
    from app.services.consol_tree_service import build_tree, to_dict

    d = to_dict(await build_tree(db_session, seeded_db))
    assert d["company_code"] == "ROOT" and d["project_id"] == str(ROOT_C)
    assert d["node_key"] == "ROOT:consol" and d["kind"] == "aggregate"
    assert d["display_name"] == "集团总公司（合并）"
    assert len(d["children"]) == 4
    elim = d["children"][0]
    assert elim["project_id"] is None and elim["host_project_id"] == str(ROOT_C)
    assert elim["display_name"] == "集团总公司（合并差额）"


# ===========================================================================
# Task 16: 差额表计算引擎测试
# ===========================================================================


@pytest.mark.asyncio
async def test_recalc_full(db_session: AsyncSession, seeded_db):
    """16.6 三类节点公式 + 分录归属 + 科目方向归一（design §5.1~§5.3）。

    口径变更：旧版把 related_company_codes 里每家企业都记一次抵销（F6 双计）、金额取表头、
    借减贷直接相加（F7）；现只计入归属的差额节点、取明细行、按科目方向归一。
    """
    from app.services.consol_worksheet_engine import recalc_full

    result = await recalc_full(db_session, seeded_db, YEAR)
    assert result["node_count"] == 8
    # 科目 = 试算表 1001/1122/2202 ∪ 已归属分录明细行 6001/6401（只在分录里出现也要建行）
    assert result["account_count"] == 5
    assert result["rows_written"] == 40 and result["rows_removed"] == 0
    assert [o["entry_no"] for o in result["orphan_entries"]] == ["IA-2025-003"]
    assert "B001" in result["orphan_entries"][0]["reason"]

    # 数据节点：children_amount_sum = 单户审定数，差额 0
    c = await _ws(db_session, "C001:subsidiary", "1001")
    assert (c.children_amount_sum, c.net_difference, c.consolidated_amount) == (D(300), D(0), D(300))

    # 合并差额：借贷列按录入方向；净额按科目方向归一（应付账款贷方性质：借 200 ⇒ −200，其他调整贷 10 ⇒ +10）
    e = await _ws(db_session, "ROOT:consol_elim", "2202")
    assert (e.elimination_debit, e.elimination_credit) == (D(200), D(0))
    assert (e.adjustment_debit, e.adjustment_credit) == (D(0), D(10))
    assert (e.children_amount_sum, e.net_difference, e.consolidated_amount) == (D(0), D(-190), D(-190))
    e_cash = await _ws(db_session, "ROOT:consol_elim", "1001")
    assert (e_cash.adjustment_debit, e_cash.net_difference) == (D(10), D(10))

    # 下级合并项目的分录归属它自己的合并差额（多级合并纳入下级抵销，需求 6.3）
    it = await _ws(db_session, "A001:consol_elim", "6001")
    assert (it.elimination_debit, it.consolidated_amount) == (D(50), D(-50))

    # 汇总节点 = Σ 直接子节点（含本企业「母公司」数据节点，旧版中间节点不含本体）
    a = await _ws(db_session, "A001:consol", "1001")
    assert (a.children_amount_sum, a.consolidated_amount) == (D(1300), D(1300))
    assert (a.adjustment_debit, a.elimination_debit, a.net_difference) == (D(0), D(0), D(0))

    root = {acct: (await _ws(db_session, "ROOT:consol", acct)).consolidated_amount
            for acct in ("1001", "1122", "2202", "6001", "6401")}
    assert root == {"1001": D(8310), "1122": D(800), "2202": D(1010), "6001": D(-50), "6401": D(-50)}


@pytest.mark.asyncio
async def test_intermediate_node_children_sum(db_session: AsyncSession, seeded_db):
    """16.3 / P7：每个汇总节点逐科目 children_amount_sum = consolidated_amount = Σ 直接子节点合并数。"""
    from app.services.consol_tree_service import build_tree, iter_nodes
    from app.services.consol_worksheet_engine import recalc_full

    await recalc_full(db_session, seeded_db, YEAR)
    rows = (await db_session.execute(
        sa.select(ConsolWorksheet).where(ConsolWorksheet.project_id == ROOT_C, ConsolWorksheet.is_deleted == sa.false())
    )).scalars().all()
    value = {(r.node_company_code, r.account_code): r for r in rows}
    tree = await build_tree(db_session, seeded_db)
    checked = 0
    for node in iter_nodes(tree):
        if node.kind != "aggregate":
            continue
        for acct in ("1001", "1122", "2202", "6001", "6401"):
            row = value[(node.node_key, acct)]
            kids = sum((value[(c.node_key, acct)].consolidated_amount for c in node.children), D(0))
            assert row.children_amount_sum == kids == row.consolidated_amount
            assert row.net_difference == D(0)
            checked += 1
    assert checked == 10  # 两个汇总节点 × 5 科目


@pytest.mark.asyncio
async def test_recalc_cleans_stale_rows_and_revives(db_session: AsyncSession, seeded_db):
    """需求 5.8：全量重算软删旧行（旧的纯企业代码键、已消失节点）；同键软删行复活而不新插；重跑幂等。"""
    from app.services.consol_worksheet_engine import recalc_full

    def row(key, acct, deleted=False):
        return ConsolWorksheet(
            id=uuid.uuid4(), project_id=ROOT_C, node_company_code=key, account_code=acct, year=YEAR,
            consolidated_amount=D(1), is_deleted=deleted,
        )

    db_session.add_all([row("ROOT", "1001"), row("GONE:consol", "1001"), row("ROOT:consol", "1001", deleted=True)])
    await db_session.commit()

    first = await recalc_full(db_session, seeded_db, YEAR)
    assert first["rows_removed"] == 2
    live = (await db_session.execute(
        sa.select(ConsolWorksheet.node_company_code).where(
            ConsolWorksheet.project_id == ROOT_C, ConsolWorksheet.is_deleted == sa.false())
    )).scalars().all()
    assert "ROOT" not in live and "GONE:consol" not in live
    same_key = (await db_session.execute(
        sa.select(ConsolWorksheet).where(
            ConsolWorksheet.node_company_code == "ROOT:consol", ConsolWorksheet.account_code == "1001")
    )).scalars().all()
    assert len(same_key) == 1 and same_key[0].is_deleted is False  # 复活，不是新插
    assert same_key[0].consolidated_amount == D(8310)

    second = await recalc_full(db_session, seeded_db, YEAR)
    assert (second["rows_written"], second["rows_removed"]) == (0, 0)


@pytest.mark.asyncio
async def test_recalc_after_tree_change_drops_vanished_node(db_session: AsyncSession, seeded_db):
    """需求 5.8：树结构变化（子公司B 单户项目删除）后重算，B 节点的旧行被清除，根合并数随之变化。"""
    from app.services.consol_worksheet_engine import recalc_full

    await recalc_full(db_session, seeded_db, YEAR)
    b = await db_session.get(Project, B_S)
    b.soft_delete()
    await db_session.commit()

    result = await recalc_full(db_session, seeded_db, YEAR)
    assert result["node_count"] == 7 and result["rows_removed"] == 5
    left = (await db_session.execute(
        sa.select(sa.func.count()).select_from(ConsolWorksheet).where(
            ConsolWorksheet.node_company_code == "B001:subsidiary", ConsolWorksheet.is_deleted == sa.false())
    )).scalar_one()
    assert left == 0
    assert (await _ws(db_session, "ROOT:consol", "1001")).consolidated_amount == D(6310)


@pytest.mark.asyncio
async def test_draft_and_orphan_entries_not_counted(db_session: AsyncSession, seeded_db):
    """P9：草稿分录与孤儿分录都不计入（IA-2025-002 草稿借 1001 999、IA-2025-003 孤儿借 1001 7）。"""
    from app.services.consol_worksheet_engine import recalc_full

    await recalc_full(db_session, seeded_db, YEAR)
    for key in ("ROOT:consol_elim", "A001:consol_elim"):
        row = await _ws(db_session, key, "1001")
        assert row.elimination_debit == D(0)
    assert (await _ws(db_session, "ROOT:consol", "1001")).consolidated_amount == D(8310)


# ===========================================================================
# Task 17: 节点汇总查询测试
# ===========================================================================


async def _self_amount(db, key: str, acct: str) -> Decimal:
    from app.services.consol_aggregation_service import query_node

    rows = await query_node(db, ROOT_C, YEAR, key, "self")
    return D(next(r for r in rows if r["account_code"] == acct)["consolidated_amount"])


@pytest.mark.asyncio
async def test_query_self(db_session: AsyncSession, seeded_db):
    """17.2 self：单节点差额表；纯企业代码与 node_key 都能定位（口径变更：行按 node_key 取）。"""
    from app.services.consol_aggregation_service import query_node
    from app.services.consol_worksheet_engine import recalc_full

    await recalc_full(db_session, seeded_db, YEAR)
    data = await query_node(db_session, seeded_db, YEAR, "B001", "self")
    assert len(data) == 5  # 本树 5 个科目，每节点每科目一行
    assert D(next(d for d in data if d["account_code"] == "1001")["consolidated_amount"]) == D(2000)
    assert data[0]["node_key"] == "B001:subsidiary" and data[0]["display_name"] == "子公司B"
    assert await _self_amount(db_session, "ROOT:consol_elim", "2202") == D(-190)


@pytest.mark.asyncio
async def test_query_children(db_session: AsyncSession, seeded_db):
    """17.3 children：当前节点 + 直接子节点各行按科目相加（汇总的是这几个节点，不是另算合并数）。"""
    from app.services.consol_aggregation_service import query_node
    from app.services.consol_worksheet_engine import recalc_full

    await recalc_full(db_session, seeded_db, YEAR)
    data = await query_node(db_session, seeded_db, YEAR, "ROOT", "children")
    assert len(data) == 5
    got = D(next(d for d in data if d["account_code"] == "1001")["consolidated_amount"])
    keys = ["ROOT:consol", "ROOT:consol_elim", "ROOT:parent", "A001:consol", "B001:subsidiary"]
    expected = sum([await _self_amount(db_session, k, "1001") for k in keys], D(0))
    assert got == expected == D(16620)


@pytest.mark.asyncio
async def test_query_descendants(db_session: AsyncSession, seeded_db):
    """17.4 descendants：当前节点 + 全部后代。"""
    from app.services.consol_aggregation_service import query_node
    from app.services.consol_worksheet_engine import recalc_full

    await recalc_full(db_session, seeded_db, YEAR)
    data = await query_node(db_session, seeded_db, YEAR, "A001:consol", "descendants")
    got = D(next(d for d in data if d["account_code"] == "1001")["consolidated_amount"])
    keys = ["A001:consol", "A001:consol_elim", "A001:parent", "C001:subsidiary"]
    assert got == sum([await _self_amount(db_session, k, "1001") for k in keys], D(0)) == D(2600)


@pytest.mark.asyncio
async def test_three_modes_different_results(db_session: AsyncSession, seeded_db):
    """17.5 三种模式结果不同：self 只取本节点，children/descendants 叠加子节点。"""
    from app.services.consol_aggregation_service import query_node
    from app.services.consol_worksheet_engine import recalc_full

    await recalc_full(db_session, seeded_db, YEAR)

    def pick(rows):
        return D(next(d for d in rows if d["account_code"] == "1001")["consolidated_amount"])

    self_1001 = pick(await query_node(db_session, seeded_db, YEAR, "A001", "self"))
    children_1001 = pick(await query_node(db_session, seeded_db, YEAR, "A001", "children"))
    root_children = pick(await query_node(db_session, seeded_db, YEAR, "ROOT", "children"))
    root_desc = pick(await query_node(db_session, seeded_db, YEAR, "ROOT", "descendants"))
    assert self_1001 == D(1300) and children_1001 == D(2600)
    assert root_children != root_desc  # 根有孙节点，两种模式范围不同


# ===========================================================================
# Task 18: 穿透查询测试
# ===========================================================================


@pytest.mark.asyncio
async def test_drill_to_companies(db_session: AsyncSession, seeded_db):
    """18.1 穿透到直接子节点构成：按树序列出，合计 = 本节点合并数（口径变更：子节点含差额与母公司节点）。"""
    from app.services.consol_drilldown_service import drill_to_companies
    from app.services.consol_worksheet_engine import recalc_full

    await recalc_full(db_session, seeded_db, YEAR)
    data = await drill_to_companies(db_session, seeded_db, YEAR, "ROOT", "1001")
    assert [d["node_key"] for d in data] == ["ROOT:consol_elim", "ROOT:parent", "A001:consol", "B001:subsidiary"]
    assert data[0]["display_name"] == "集团总公司（合并差额）" and data[0]["kind"] == "elim"
    assert sum((D(d["consolidated_amount"]) for d in data), D(0)) == D(8310)
    assert await drill_to_companies(db_session, seeded_db, YEAR, "B001:subsidiary") == []  # 数据节点没有子节点


@pytest.mark.asyncio
async def test_drill_to_eliminations(db_session: AsyncSession, seeded_db):
    """18.2 穿透到分录：差额节点取归属分录（与金额同一归属函数），汇总节点取子树全部差额节点，
    数据节点按 related_company_codes 留痕筛选；带计入标记与孤儿原因。

    口径变更：旧版一律按 related_company_codes 过滤，且只看本合并项目的分录。
    """
    from app.services.consol_drilldown_service import drill_to_eliminations

    elim = await drill_to_eliminations(db_session, seeded_db, YEAR, "ROOT:consol_elim")
    assert [e["entry_no"] for e in elim] == ["IA-2025-001", "IA-2025-002", "OT-2025-001"]
    assert [e["counted"] for e in elim] == [True, False, True]  # 草稿不计入
    assert elim[0]["lines"][0]["account_code"] == "2202"

    subtree = await drill_to_eliminations(db_session, seeded_db, YEAR, "ROOT")
    assert [e["entry_no"] for e in subtree] == ["IA-2025-001", "IA-2025-002", "IT-2025-001", "OT-2025-001"]
    assert next(e for e in subtree if e["entry_no"] == "IT-2025-001")["node_key"] == "A001:consol_elim"

    cash = await drill_to_eliminations(db_session, seeded_db, YEAR, "ROOT:consol_elim", "1001")
    assert [e["entry_no"] for e in cash] == ["IA-2025-002", "OT-2025-001"]  # 按明细行科目筛选

    related = await drill_to_eliminations(db_session, seeded_db, YEAR, "B001")
    assert [e["entry_no"] for e in related] == ["IA-2025-001", "IA-2025-003"]
    orphan = related[1]
    assert orphan["counted"] is False and orphan["node_key"] is None and "B001" in orphan["orphan_reason"]


@pytest.mark.asyncio
async def test_drill_to_trial_balance(db_session: AsyncSession, seeded_db):
    """18.3 穿透到试算表：只有数据节点有试算表；纯企业代码取该企业的数据节点（母公司取单户项目）。"""
    from app.services.consol_drilldown_service import drill_to_trial_balance

    b = await drill_to_trial_balance(db_session, seeded_db, "B001")
    assert b["drill_url"] == f"/projects/{B_S}/trial-balance" and b["company_code"] == "B001"

    root = await drill_to_trial_balance(db_session, seeded_db, "ROOT")
    assert root["node_key"] == "ROOT:parent" and str(ROOT_S) in root["drill_url"]

    elim = await drill_to_trial_balance(db_session, seeded_db, "ROOT:consol_elim")
    assert elim["drill_url"] is None and "差额节点" in elim["message"]

    agg = await drill_to_trial_balance(db_session, seeded_db, "A001:consol")
    assert agg["drill_url"] is None and "汇总节点" in agg["message"] and "孙公司C" in agg["message"]

    missing = await drill_to_trial_balance(db_session, seeded_db, "NONEXIST")
    assert missing["drill_url"] is None


@pytest.mark.asyncio
async def test_drill_chain(db_session: AsyncSession, seeded_db):
    """18.4 穿透链路：合并数 → 子节点构成 → 下级合并的分录 → 下级企业试算表。"""
    from app.services.consol_drilldown_service import (
        drill_to_companies, drill_to_eliminations, drill_to_trial_balance,
    )
    from app.services.consol_worksheet_engine import recalc_full

    await recalc_full(db_session, seeded_db, YEAR)
    companies = await drill_to_companies(db_session, seeded_db, YEAR, "ROOT")
    sub = next(c for c in companies if c["node_key"] == "A001:consol")
    elims = await drill_to_eliminations(db_session, seeded_db, YEAR, sub["node_key"])
    assert [e["entry_no"] for e in elims] == ["IT-2025-001"]
    tb = await drill_to_trial_balance(db_session, seeded_db, sub["company_code"])
    assert tb["drill_url"] == f"/projects/{A_S}/trial-balance"


# ===========================================================================
# Task 19: 透视查询 + 模板 CRUD 测试
# ===========================================================================

TREE_ORDER_LABELS = [
    "集团总公司（合并）", "集团总公司（合并差额）", "集团总公司（母公司）", "子公司A（合并）",
    "子公司A（合并差额）", "子公司A（母公司）", "孙公司C", "子公司B",
]


@pytest.mark.asyncio
async def test_pivot_account_by_company(db_session: AsyncSession, seeded_db):
    """19.2 行=科目，列=节点：表头用节点展示名、按树序（口径变更：旧表头是原始企业代码且按字母序）。"""
    from app.services.consol_pivot_service import execute_query
    from app.services.consol_worksheet_engine import recalc_full

    await recalc_full(db_session, seeded_db, YEAR)
    result = await execute_query(
        db_session, seeded_db, YEAR,
        row_dimension="account", col_dimension="company",
        value_field="consolidated_amount",
    )
    assert len(result["rows"]) == 5
    assert result["headers"] == ["科目编码", *TREE_ORDER_LABELS, "合计"]
    assert result["node_keys"][0] == "ROOT:consol" and len(result["node_keys"]) == 8
    row_1001 = next(r for r in result["rows"] if r[0] == "1001")
    assert D(row_1001[1]) == D(8310)


@pytest.mark.asyncio
async def test_pivot_company_by_account(db_session: AsyncSession, seeded_db):
    """19.3 行=节点，列=科目：8 个节点各一行，首列为展示名。"""
    from app.services.consol_pivot_service import execute_query
    from app.services.consol_worksheet_engine import recalc_full

    await recalc_full(db_session, seeded_db, YEAR)
    result = await execute_query(
        db_session, seeded_db, YEAR,
        row_dimension="company", col_dimension="account",
    )
    assert [r[0] for r in result["rows"]] == TREE_ORDER_LABELS


@pytest.mark.asyncio
async def test_pivot_transpose(db_session: AsyncSession, seeded_db):
    """19.4 转置"""
    from app.services.consol_pivot_service import execute_query
    from app.services.consol_worksheet_engine import recalc_full

    await recalc_full(db_session, seeded_db, YEAR)
    normal = await execute_query(
        db_session, seeded_db, YEAR,
        row_dimension="account", col_dimension="company",
        transpose=False,
    )
    transposed = await execute_query(
        db_session, seeded_db, YEAR,
        row_dimension="account", col_dimension="company",
        transpose=True,
    )
    assert len(transposed["headers"]) == len(normal["rows"]) + 2  # 首列 + 各科目 + 合计行
    assert [r[0] for r in transposed["rows"]] == normal["headers"][1:]


@pytest.mark.asyncio
async def test_save_and_list_templates(db_session: AsyncSession, seeded_db):
    """19.6 模板 CRUD"""
    from app.services.consol_pivot_service import save_template, list_templates

    tpl = await save_template(
        db_session, seeded_db, "测试模板",
        row_dimension="account", col_dimension="company",
        value_field="consolidated_amount",
        filters={"account_codes": ["1001"]},
        transpose=False, aggregation_mode="self",
    )
    assert tpl["name"] == "测试模板"
    assert tpl["id"] is not None

    templates = await list_templates(db_session, seeded_db)
    assert len(templates) == 1
    assert templates[0]["name"] == "测试模板"


@pytest.mark.asyncio
async def test_pivot_with_filters(db_session: AsyncSession, seeded_db):
    """透视筛选：科目筛选；企业筛选传纯代码 = 该企业全部节点；按节点 + 汇总模式取范围。"""
    from app.services.consol_pivot_service import execute_query
    from app.services.consol_worksheet_engine import recalc_full

    await recalc_full(db_session, seeded_db, YEAR)
    by_account = await execute_query(db_session, seeded_db, YEAR, filters={"account_codes": ["1001"]})
    assert len(by_account["rows"]) == 1

    by_company = await execute_query(db_session, seeded_db, YEAR, filters={"company_codes": ["A001"]})
    assert by_company["node_keys"] == ["A001:consol", "A001:consol_elim", "A001:parent"]

    children = await execute_query(
        db_session, seeded_db, YEAR, node_company_code="A001:consol", aggregation_mode="children",
    )
    assert children["node_keys"] == ["A001:consol", "A001:consol_elim", "A001:parent", "C001:subsidiary"]
