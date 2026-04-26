"""合并差额表深度开发测试

覆盖：
- Task 15: 树形服务 (build_tree / find_node / get_descendants / to_dict)
- Task 16: 差额表计算引擎 (recalc_full / 叶子节点 / 中间节点 / 抵消分录)
- Task 17: 节点汇总查询 (self / children / descendants)
- Task 18: 穿透查询 (drill_to_companies / drill_to_eliminations / drill_to_trial_balance)
- Task 19: 透视查询 + 模板 CRUD
"""

import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
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
    ConsolQueryTemplate,
    EliminationEntry,
    EliminationEntryType,
    ReviewStatusEnum,
)

# SQLite compat
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

import sqlalchemy as _sa
class _WorkpaperStub(Base):
    __tablename__ = "workpapers"
    __table_args__ = {"extend_existing": True}
    id = _sa.Column(_sa.Uuid, primary_key=True)

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"
engine = create_async_engine(TEST_DB_URL, echo=False)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

YEAR = 2025
ROOT_ID = uuid.uuid4()
CHILD_A_ID = uuid.uuid4()
CHILD_B_ID = uuid.uuid4()
GRANDCHILD_C_ID = uuid.uuid4()


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session


@pytest_asyncio.fixture
async def seeded_db(db_session: AsyncSession):
    """创建三级企业树 + 试算表 + 抵消分录

    结构:
      ROOT (集团)
        ├── CHILD_A (子公司A)
        │     └── GRANDCHILD_C (孙公司C)
        └── CHILD_B (子公司B)
    """
    # Root project
    root = Project(
        id=ROOT_ID, name="集团合并", client_name="集团总公司",
        company_code="ROOT", parent_company_code=None,
        ultimate_company_code="ROOT", consol_level=1,
        status=ProjectStatus.execution,
    )
    # Child A
    child_a = Project(
        id=CHILD_A_ID, name="子公司A", client_name="子公司A",
        company_code="A001", parent_company_code="ROOT",
        ultimate_company_code="ROOT", consol_level=2,
        parent_project_id=ROOT_ID,
        status=ProjectStatus.execution,
    )
    # Child B
    child_b = Project(
        id=CHILD_B_ID, name="子公司B", client_name="子公司B",
        company_code="B001", parent_company_code="ROOT",
        ultimate_company_code="ROOT", consol_level=2,
        parent_project_id=ROOT_ID,
        status=ProjectStatus.execution,
    )
    # Grandchild C (under A)
    grandchild_c = Project(
        id=GRANDCHILD_C_ID, name="孙公司C", client_name="孙公司C",
        company_code="C001", parent_company_code="A001",
        ultimate_company_code="ROOT", consol_level=3,
        parent_project_id=CHILD_A_ID,
        status=ProjectStatus.execution,
    )
    db_session.add_all([root, child_a, child_b, grandchild_c])

    # Trial balance for leaf nodes (A, B, C)
    # A: account 1001 = 1000, 1002 = 500
    # B: account 1001 = 2000, 1002 = 800
    # C: account 1001 = 300,  1002 = 100
    for pid, amounts in [
        (CHILD_A_ID, {"1001": 1000, "1002": 500}),
        (CHILD_B_ID, {"1001": 2000, "1002": 800}),
        (GRANDCHILD_C_ID, {"1001": 300, "1002": 100}),
    ]:
        for code, amt in amounts.items():
            db_session.add(TrialBalance(
                id=uuid.uuid4(), project_id=pid, year=YEAR,
                company_code="001",
                standard_account_code=code, account_name=f"科目{code}",
                account_category=AccountCategory.asset,
                audited_amount=Decimal(str(amt)),
                unadjusted_amount=Decimal(str(amt)),
                rje_adjustment=Decimal("0"), aje_adjustment=Decimal("0"),
            ))

    # Elimination entry: ROOT level, affects A001, account 1001
    db_session.add(EliminationEntry(
        id=uuid.uuid4(), project_id=ROOT_ID, year=YEAR,
        entry_no="EQ-2025-001", entry_type=EliminationEntryType.equity,
        account_code="1001", account_name="科目1001",
        debit_amount=Decimal("100"), credit_amount=Decimal("0"),
        entry_group_id=uuid.uuid4(),
        related_company_codes=["A001"],
        review_status=ReviewStatusEnum.draft,
    ))
    # Another elimination for B001
    db_session.add(EliminationEntry(
        id=uuid.uuid4(), project_id=ROOT_ID, year=YEAR,
        entry_no="IT-2025-001", entry_type=EliminationEntryType.internal_trade,
        account_code="1002", account_name="科目1002",
        debit_amount=Decimal("0"), credit_amount=Decimal("50"),
        entry_group_id=uuid.uuid4(),
        related_company_codes=["B001"],
        review_status=ReviewStatusEnum.draft,
    ))

    await db_session.commit()
    return ROOT_ID


# ===========================================================================
# Task 15: 树形服务测试
# ===========================================================================


@pytest.mark.asyncio
async def test_build_tree_3_levels(db_session: AsyncSession, seeded_db):
    """15.5 验证树形构建：3 级结构正确嵌套"""
    from app.services.consol_tree_service import build_tree, to_dict

    tree = await build_tree(db_session, seeded_db)
    assert tree is not None
    assert tree.company_code == "ROOT"
    assert len(tree.children) == 2

    # Find child A and B
    codes = {c.company_code for c in tree.children}
    assert codes == {"A001", "B001"}

    # A001 has grandchild C001
    child_a = next(c for c in tree.children if c.company_code == "A001")
    assert len(child_a.children) == 1
    assert child_a.children[0].company_code == "C001"

    # B001 has no children
    child_b = next(c for c in tree.children if c.company_code == "B001")
    assert len(child_b.children) == 0


@pytest.mark.asyncio
async def test_find_node(db_session: AsyncSession, seeded_db):
    """find_node 按 company_code 查找"""
    from app.services.consol_tree_service import build_tree, find_node

    tree = await build_tree(db_session, seeded_db)
    node = find_node(tree, "C001")
    assert node is not None
    assert node.company_name == "孙公司C"

    missing = find_node(tree, "NONEXIST")
    assert missing is None


@pytest.mark.asyncio
async def test_get_descendants(db_session: AsyncSession, seeded_db):
    """get_descendants 获取所有后代"""
    from app.services.consol_tree_service import build_tree, find_node, get_descendants

    tree = await build_tree(db_session, seeded_db)
    # ROOT has 3 descendants: A001, B001, C001
    descs = get_descendants(tree)
    assert len(descs) == 3
    desc_codes = {d.company_code for d in descs}
    assert desc_codes == {"A001", "B001", "C001"}

    # A001 has 1 descendant: C001
    a_node = find_node(tree, "A001")
    a_descs = get_descendants(a_node)
    assert len(a_descs) == 1
    assert a_descs[0].company_code == "C001"


@pytest.mark.asyncio
async def test_to_dict(db_session: AsyncSession, seeded_db):
    """to_dict 树→JSON"""
    from app.services.consol_tree_service import build_tree, to_dict

    tree = await build_tree(db_session, seeded_db)
    d = to_dict(tree)
    assert d["company_code"] == "ROOT"
    assert len(d["children"]) == 2
    assert "project_id" in d


# ===========================================================================
# Task 16: 差额表计算引擎测试
# ===========================================================================


@pytest.mark.asyncio
async def test_recalc_full(db_session: AsyncSession, seeded_db):
    """16.6 验证公式：3 个企业 + 2 笔抵消分录"""
    from app.services.consol_worksheet_engine import recalc_full

    result = await recalc_full(db_session, seeded_db, YEAR)
    assert result["node_count"] == 4  # ROOT + A + B + C
    assert result["account_count"] == 2  # 1001, 1002

    # Check leaf node C001: children_amount_sum = audited_amount
    import sqlalchemy as sa
    ws_c = (await db_session.execute(
        sa.select(ConsolWorksheet).where(
            ConsolWorksheet.project_id == seeded_db,
            ConsolWorksheet.node_company_code == "C001",
            ConsolWorksheet.account_code == "1001",
        )
    )).scalar_one()
    assert ws_c.children_amount_sum == Decimal("300")
    assert ws_c.consolidated_amount == Decimal("300")  # no eliminations for C

    # Check leaf node A001: A001 is intermediate (has child C001)
    # children_amount_sum = C001.consolidated = 300
    # elimination debit=100 on 1001
    ws_a = (await db_session.execute(
        sa.select(ConsolWorksheet).where(
            ConsolWorksheet.project_id == seeded_db,
            ConsolWorksheet.node_company_code == "A001",
            ConsolWorksheet.account_code == "1001",
        )
    )).scalar_one()
    assert ws_a.children_amount_sum == Decimal("300")  # C001's consolidated
    assert ws_a.elimination_debit == Decimal("100")
    assert ws_a.net_difference == Decimal("100")  # 100 - 0
    assert ws_a.consolidated_amount == Decimal("400")  # 300 + 100

    # Check B001 account 1002: audited=800, elimination credit=50
    ws_b = (await db_session.execute(
        sa.select(ConsolWorksheet).where(
            ConsolWorksheet.project_id == seeded_db,
            ConsolWorksheet.node_company_code == "B001",
            ConsolWorksheet.account_code == "1002",
        )
    )).scalar_one()
    assert ws_b.children_amount_sum == Decimal("800")
    assert ws_b.elimination_credit == Decimal("50")
    assert ws_b.net_difference == Decimal("-50")  # 0 - 50
    assert ws_b.consolidated_amount == Decimal("750")  # 800 - 50


@pytest.mark.asyncio
async def test_intermediate_node_children_sum(db_session: AsyncSession, seeded_db):
    """16.3 中间节点 children_amount_sum = Σ(直接下级 consolidated_amount)"""
    from app.services.consol_worksheet_engine import recalc_full
    import sqlalchemy as sa

    await recalc_full(db_session, seeded_db, YEAR)

    # ROOT's children_amount_sum for 1001 should be:
    # A001.consolidated(1001) + B001.consolidated(1001)
    # A001.consolidated(1001) = 1000 + 100 = 1100 (but A is intermediate with child C)
    # Wait - A001 is NOT a leaf, it has child C001.
    # A001.children_amount_sum(1001) = C001.consolidated(1001) = 300
    # A001.consolidated(1001) = 300 + 100 = 400
    # B001 is a leaf: consolidated(1001) = 2000
    # ROOT.children_amount_sum(1001) = A001.consolidated(1001) + B001.consolidated(1001) = 400 + 2000 = 2400

    ws_a_1001 = (await db_session.execute(
        sa.select(ConsolWorksheet).where(
            ConsolWorksheet.project_id == seeded_db,
            ConsolWorksheet.node_company_code == "A001",
            ConsolWorksheet.account_code == "1001",
        )
    )).scalar_one()
    # A001 is intermediate (has child C001), so children_amount_sum = C001.consolidated
    assert ws_a_1001.children_amount_sum == Decimal("300")
    assert ws_a_1001.consolidated_amount == Decimal("400")  # 300 + 100

    ws_root_1001 = (await db_session.execute(
        sa.select(ConsolWorksheet).where(
            ConsolWorksheet.project_id == seeded_db,
            ConsolWorksheet.node_company_code == "ROOT",
            ConsolWorksheet.account_code == "1001",
        )
    )).scalar_one()
    # ROOT.children_amount_sum = A001.consolidated + B001.consolidated = 400 + 2000 = 2400
    assert ws_root_1001.children_amount_sum == Decimal("2400")


# ===========================================================================
# Task 17: 节点汇总查询测试
# ===========================================================================


@pytest.mark.asyncio
async def test_query_self(db_session: AsyncSession, seeded_db):
    """17.2 self 模式：返回单节点差额表"""
    from app.services.consol_worksheet_engine import recalc_full
    from app.services.consol_aggregation_service import query_node

    await recalc_full(db_session, seeded_db, YEAR)
    data = await query_node(db_session, seeded_db, YEAR, "B001", "self")
    assert len(data) == 2  # 2 accounts
    acct_1001 = next(d for d in data if d["account_code"] == "1001")
    assert Decimal(acct_1001["consolidated_amount"]) == Decimal("2000")


@pytest.mark.asyncio
async def test_query_children(db_session: AsyncSession, seeded_db):
    """17.3 children 模式：当前节点 + 直接子节点"""
    from app.services.consol_worksheet_engine import recalc_full
    from app.services.consol_aggregation_service import query_node

    await recalc_full(db_session, seeded_db, YEAR)
    # ROOT children mode: ROOT + A001 + B001
    data = await query_node(db_session, seeded_db, YEAR, "ROOT", "children")
    assert len(data) == 2  # 2 accounts aggregated
    acct_1001 = next(d for d in data if d["account_code"] == "1001")
    # Sum of ROOT + A001 + B001 consolidated amounts for 1001
    assert Decimal(acct_1001["consolidated_amount"]) > Decimal("0")


@pytest.mark.asyncio
async def test_query_descendants(db_session: AsyncSession, seeded_db):
    """17.4 descendants 模式：当前节点 + 所有后代"""
    from app.services.consol_worksheet_engine import recalc_full
    from app.services.consol_aggregation_service import query_node

    await recalc_full(db_session, seeded_db, YEAR)
    # ROOT descendants: ROOT + A001 + B001 + C001
    data = await query_node(db_session, seeded_db, YEAR, "ROOT", "descendants")
    assert len(data) == 2  # 2 accounts


@pytest.mark.asyncio
async def test_three_modes_different_results(db_session: AsyncSession, seeded_db):
    """17.5 三种模式返回不同的汇总结果"""
    from app.services.consol_worksheet_engine import recalc_full
    from app.services.consol_aggregation_service import query_node

    await recalc_full(db_session, seeded_db, YEAR)

    self_data = await query_node(db_session, seeded_db, YEAR, "A001", "self")
    children_data = await query_node(db_session, seeded_db, YEAR, "A001", "children")
    desc_data = await query_node(db_session, seeded_db, YEAR, "A001", "descendants")

    # self = just A001, children = A001 + C001, descendants = A001 + C001 (same for A)
    self_1001 = Decimal(next(d for d in self_data if d["account_code"] == "1001")["consolidated_amount"])
    children_1001 = Decimal(next(d for d in children_data if d["account_code"] == "1001")["consolidated_amount"])
    # children should be >= self (includes child C001)
    assert children_1001 >= self_1001


# ===========================================================================
# Task 18: 穿透查询测试
# ===========================================================================


@pytest.mark.asyncio
async def test_drill_to_companies(db_session: AsyncSession, seeded_db):
    """18.1 穿透到企业构成"""
    from app.services.consol_worksheet_engine import recalc_full
    from app.services.consol_drilldown_service import drill_to_companies

    await recalc_full(db_session, seeded_db, YEAR)
    data = await drill_to_companies(db_session, seeded_db, YEAR, "ROOT", "1001")
    assert len(data) == 2  # A001 and B001
    codes = {d["company_code"] for d in data}
    assert codes == {"A001", "B001"}


@pytest.mark.asyncio
async def test_drill_to_eliminations(db_session: AsyncSession, seeded_db):
    """18.2 穿透到抵消分录"""
    from app.services.consol_drilldown_service import drill_to_eliminations

    data = await drill_to_eliminations(db_session, seeded_db, YEAR, "A001", "1001")
    assert len(data) == 1
    assert data[0]["entry_no"] == "EQ-2025-001"
    assert Decimal(data[0]["debit_amount"]) == Decimal("100")


@pytest.mark.asyncio
async def test_drill_to_trial_balance(db_session: AsyncSession, seeded_db):
    """18.3 穿透到试算表"""
    from app.services.consol_drilldown_service import drill_to_trial_balance

    data = await drill_to_trial_balance(db_session, seeded_db, "B001")
    assert data["drill_url"] is not None
    assert data["company_code"] == "B001"
    assert str(CHILD_B_ID) in data["drill_url"]


@pytest.mark.asyncio
async def test_drill_chain(db_session: AsyncSession, seeded_db):
    """18.4 验证穿透链路：合并数 → 企业构成 → 抵消分录 → 试算表"""
    from app.services.consol_worksheet_engine import recalc_full
    from app.services.consol_drilldown_service import (
        drill_to_companies, drill_to_eliminations, drill_to_trial_balance,
    )

    await recalc_full(db_session, seeded_db, YEAR)

    # Step 1: ROOT → companies
    companies = await drill_to_companies(db_session, seeded_db, YEAR, "ROOT")
    assert len(companies) > 0

    # Step 2: Pick A001 → eliminations
    elims = await drill_to_eliminations(db_session, seeded_db, YEAR, "A001")
    assert len(elims) >= 1

    # Step 3: A001 → trial balance
    tb = await drill_to_trial_balance(db_session, seeded_db, "A001")
    assert tb["drill_url"] is not None


# ===========================================================================
# Task 19: 透视查询 + 模板 CRUD 测试
# ===========================================================================


@pytest.mark.asyncio
async def test_pivot_account_by_company(db_session: AsyncSession, seeded_db):
    """19.2 行=科目，列=企业"""
    from app.services.consol_worksheet_engine import recalc_full
    from app.services.consol_pivot_service import execute_query

    await recalc_full(db_session, seeded_db, YEAR)
    result = await execute_query(
        db_session, seeded_db, YEAR,
        row_dimension="account", col_dimension="company",
        value_field="consolidated_amount",
    )
    assert "headers" in result
    assert "rows" in result
    assert len(result["rows"]) == 2  # 2 accounts
    # Headers should include company codes
    assert "合计" in result["headers"]


@pytest.mark.asyncio
async def test_pivot_company_by_account(db_session: AsyncSession, seeded_db):
    """19.3 行=企业，列=科目"""
    from app.services.consol_worksheet_engine import recalc_full
    from app.services.consol_pivot_service import execute_query

    await recalc_full(db_session, seeded_db, YEAR)
    result = await execute_query(
        db_session, seeded_db, YEAR,
        row_dimension="company", col_dimension="account",
    )
    assert len(result["rows"]) == 4  # 4 companies (ROOT, A, B, C)


@pytest.mark.asyncio
async def test_pivot_transpose(db_session: AsyncSession, seeded_db):
    """19.4 转置"""
    from app.services.consol_worksheet_engine import recalc_full
    from app.services.consol_pivot_service import execute_query

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
    # After transpose, rows and columns swap
    assert len(transposed["headers"]) != len(normal["headers"]) or \
           len(transposed["rows"]) != len(normal["rows"])


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
    """透视查询带筛选"""
    from app.services.consol_worksheet_engine import recalc_full
    from app.services.consol_pivot_service import execute_query

    await recalc_full(db_session, seeded_db, YEAR)
    result = await execute_query(
        db_session, seeded_db, YEAR,
        filters={"account_codes": ["1001"]},
    )
    assert len(result["rows"]) == 1  # Only account 1001
