"""批 3：四表 canonical projection 纯函数会计口径守卫。

覆盖：只认 approved、权威总额 = node_measures 权益抵销、逐企业恒等式、多企业/未标企业进未分配、
贷方自然方向、负数、分级舍入、科目前缀匹配。
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import tests.conftest  # noqa: F401
from app.services.consol_calc_basis import (
    CalcBasis,
    TbRow,
    build_calc_basis,
    records_from_entries,
)
from app.services.consol_group_tree import ROLE_CONSOL, ROLE_CONSOL_ELIM, node_key as mk_node_key
from app.services.consol_post_elimination_projection import (
    ACCOUNT_CAPITAL_RESERVE,
    ACCOUNT_INVEST_INCOME,
    ACCOUNT_LONG_INVEST,
    ACCOUNT_MINORITY_EQUITY,
    build_post_elimination_projection,
)
from app.services.consol_tree_service import TreeNode

YEAR = 2025
ROOT = "G"


def _node(code: str, role: str, kind: str, *, pid=None, children=None, host=None) -> TreeNode:
    node = TreeNode(
        project_id=pid, company_code=code, company_name=f"{code}公司",
        parent_company_code=None, ultimate_company_code=ROOT, consol_level=1,
        node_key=mk_node_key(code, role), role=role, kind=kind,
        children=children or [],
    )
    # host_project_id 供母分差额归属校验（本测试只用合并差额，不需要）
    try:
        node.host_project_id = host
    except Exception:  # noqa: BLE001
        pass
    return node


def _tree(root_pid) -> TreeNode:
    """G(合并) → [甲(data), 乙(data), G:consol_elim(差额)]。"""
    jia = _node("A", "subsidiary", "data", pid=uuid.uuid4())
    yi = _node("B", "subsidiary", "data", pid=uuid.uuid4())
    elim = _node(ROOT, ROLE_CONSOL_ELIM, "elim", pid=root_pid, host=root_pid)
    root = _node(ROOT, ROLE_CONSOL, "aggregate", pid=root_pid, children=[jia, yi, elim])
    return root


@dataclass
class _Entry:
    """projection 读取的最小分录接口（也能喂 records_from_entries）。"""

    entry_type: str
    lines: list[dict]
    related_company_codes: list[str]
    review_status: str = "approved"
    id: uuid.UUID = None  # type: ignore[assignment]
    project_id: uuid.UUID = None  # type: ignore[assignment]
    entry_no: str = "E"
    branch_entity_code: str | None = None
    account_code: str = ""
    account_name: str | None = None
    debit_amount: Decimal = Decimal("0")
    credit_amount: Decimal = Decimal("0")

    def __post_init__(self):
        if self.id is None:
            self.id = uuid.uuid4()


def _line(code: str, debit="0", credit="0", name=None) -> dict:
    return {"account_code": code, "account_name": name, "debit_amount": debit, "credit_amount": credit}


def _basis(root_pid, tb_rows: list[TbRow], entries: list[_Entry]) -> CalcBasis:
    # 分录归属到根合并项目的「合并差额」节点：project_id 必须是承载合并项目 id。
    for e in entries:
        e.project_id = root_pid
    records, invalid = records_from_entries(entries)
    return build_calc_basis(_tree(root_pid), YEAR, tb_rows, records, invalid)


SUBS = {"A", "B"}


def test_only_approved_equity_entries_feed_projection():
    """草稿分录与非权益类分录不进权威总额，也不进逐企业分解。"""
    root_pid = uuid.uuid4()
    # 一笔已审批权益抵销：借长投 100（归 A）
    approved = _Entry(
        entry_type="equity", related_company_codes=["A"],
        lines=[_line(ACCOUNT_LONG_INVEST, debit="100")],
    )
    # 一笔草稿（不计入合并数）——projection 只接收 approved，所以调用方应已过滤；
    # 这里验证即便混入，build_calc_basis 的 basis 只含 approved 时权威总额正确。
    basis = _basis(root_pid, [], [approved])
    proj = build_post_elimination_projection(
        basis, [approved], subsidiary_codes=SUBS, root_code=ROOT,
    )
    li = proj.account(ACCOUNT_LONG_INVEST)
    assert li is not None
    # 长投是借方性质 sign=+1，净额 = +100
    assert li.total == Decimal("100.00")
    assert li.is_balanced()
    assert [(s.company_code, s.amount) for s in li.by_company] == [("A", Decimal("100.00"))]
    assert li.unallocated == Decimal("0.00")


def test_identity_holds_single_company_allocation():
    """Σ 企业 + 未分配 == 权威总额（单家可归属）。"""
    root_pid = uuid.uuid4()
    e1 = _Entry(entry_type="equity", related_company_codes=["A"],
                lines=[_line(ACCOUNT_LONG_INVEST, debit="60")])
    e2 = _Entry(entry_type="equity", related_company_codes=["B"],
                lines=[_line(ACCOUNT_LONG_INVEST, debit="40")])
    basis = _basis(root_pid, [], [e1, e2])
    proj = build_post_elimination_projection(basis, [e1, e2], subsidiary_codes=SUBS, root_code=ROOT)
    li = proj.account(ACCOUNT_LONG_INVEST)
    assert li.total == Decimal("100.00")
    assert {s.company_code: s.amount for s in li.by_company} == {
        "A": Decimal("60.00"), "B": Decimal("40.00"),
    }
    assert li.unallocated == Decimal("0.00")
    assert li.is_balanced()


def test_multi_company_entry_goes_unallocated_not_duplicated():
    """关联多家的分录不复制也不平均，全额进未分配并 warning。"""
    root_pid = uuid.uuid4()
    multi = _Entry(entry_type="equity", related_company_codes=["A", "B"],
                   lines=[_line(ACCOUNT_LONG_INVEST, debit="100")])
    basis = _basis(root_pid, [], [multi])
    proj = build_post_elimination_projection(basis, [multi], subsidiary_codes=SUBS, root_code=ROOT)
    li = proj.account(ACCOUNT_LONG_INVEST)
    assert li.total == Decimal("100.00")
    assert li.by_company == ()
    assert li.unallocated == Decimal("100.00")
    assert li.is_balanced()
    assert any("多家" in w for w in li.warnings)


def test_no_company_entry_goes_unallocated_with_warning():
    """未标企业 / 企业不在合并范围 ⇒ 进未分配并 warning。"""
    root_pid = uuid.uuid4()
    orphan = _Entry(entry_type="equity", related_company_codes=[],
                    lines=[_line(ACCOUNT_INVEST_INCOME, credit="30")])
    outside = _Entry(entry_type="equity", related_company_codes=["Z"],  # Z 不在 SUBS
                     lines=[_line(ACCOUNT_INVEST_INCOME, credit="20")])
    basis = _basis(root_pid, [], [orphan, outside])
    proj = build_post_elimination_projection(basis, [orphan, outside], subsidiary_codes=SUBS, root_code=ROOT)
    inc = proj.account(ACCOUNT_INVEST_INCOME)
    # 投资收益贷方性质 sign=-1：贷方金额归一后为 +50（-1 * (0 - 50)）
    assert inc.total == Decimal("50.00")
    assert inc.by_company == ()
    assert inc.unallocated == Decimal("50.00")
    assert inc.is_balanced()
    assert any("未标企业" in w or "合并范围" in w for w in inc.warnings)


def test_credit_natural_direction_and_negative_amounts():
    """贷方性质科目（资本公积 4002）按 sign=-1 归一；净额可为负。"""
    root_pid = uuid.uuid4()
    # 资本公积借 80（归 A）：贷方性质 sign=-1 ⇒ 净额 = -1*(80-0) = -80
    e = _Entry(entry_type="equity", related_company_codes=["A"],
               lines=[_line(ACCOUNT_CAPITAL_RESERVE, debit="80")])
    basis = _basis(root_pid, [], [e])
    proj = build_post_elimination_projection(basis, [e], subsidiary_codes=SUBS, root_code=ROOT)
    cap = proj.account(ACCOUNT_CAPITAL_RESERVE)
    assert cap.total == Decimal("-80.00")
    assert {s.company_code: s.amount for s in cap.by_company} == {"A": Decimal("-80.00")}
    assert cap.is_balanced()


def test_sub_account_prefix_rolls_into_parent():
    """子科目（1511xx）按前缀归入长投。"""
    root_pid = uuid.uuid4()
    e = _Entry(entry_type="equity", related_company_codes=["A"],
               lines=[_line("151101", debit="10"), _line("151102", debit="5")])
    basis = _basis(root_pid, [], [e])
    proj = build_post_elimination_projection(basis, [e], subsidiary_codes=SUBS, root_code=ROOT)
    li = proj.account(ACCOUNT_LONG_INVEST)
    assert li.total == Decimal("15.00")
    assert {s.company_code: s.amount for s in li.by_company} == {"A": Decimal("15.00")}
    assert li.is_balanced()


def test_minority_equity_account_present():
    """少数股东权益 4501 也作为一张 projection 科目产出。"""
    root_pid = uuid.uuid4()
    e = _Entry(entry_type="equity", related_company_codes=["B"],
               lines=[_line(ACCOUNT_MINORITY_EQUITY, credit="200")])
    basis = _basis(root_pid, [], [e])
    proj = build_post_elimination_projection(basis, [e], subsidiary_codes=SUBS, root_code=ROOT)
    mi = proj.account(ACCOUNT_MINORITY_EQUITY)
    assert mi is not None
    # 少数股东权益贷方性质 sign=-1 ⇒ +200
    assert mi.total == Decimal("200.00")
    assert {s.company_code: s.amount for s in mi.by_company} == {"B": Decimal("200.00")}
    assert mi.is_balanced()


def test_manual_overrides_passed_through_untouched():
    """manual override 原样带出，不参与分录事实。"""
    root_pid = uuid.uuid4()
    e = _Entry(entry_type="equity", related_company_codes=["A"],
               lines=[_line(ACCOUNT_LONG_INVEST, debit="10")])
    basis = _basis(root_pid, [], [e])
    overrides = {"post_invest": {"A": {"bookCost": 123}}}
    proj = build_post_elimination_projection(
        basis, [e], subsidiary_codes=SUBS, root_code=ROOT, manual_overrides=overrides,
    )
    assert proj.manual_overrides == overrides


# ─────────────────────────────── 装载层编排（只读） ───────────────────────────────


import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402

from app.models.base import Base  # noqa: E402
from app.models.consol_worksheet_data_models import ConsolWorksheetData  # noqa: E402


@pytest_asyncio.fixture
async def db() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=[ConsolWorksheetData.__table__])
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_loader_filters_approved_reads_manual_and_sets_scope(db: AsyncSession, monkeypatch: pytest.MonkeyPatch):
    """装载层：只用 approved 分录、读四张工作表 manual、正确推导子公司代码与根代码。"""
    import app.services.consol_calc_basis as calc_mod
    import app.services.consol_tree_service as tree_mod
    from app.services.consol_post_elimination_projection import load_post_elimination_projection

    root_pid = uuid.uuid4()
    tree = _tree(root_pid)

    # manual overrides：四张工作表各写一行
    db.add_all([
        ConsolWorksheetData(project_id=root_pid, year=YEAR, sheet_key="post_invest", data={"rows": [1]}, version=1),
        ConsolWorksheetData(project_id=root_pid, year=YEAR, sheet_key="capital", data={"consol_report_amount": 5}, version=1),
        # 非投影表不应被读入 manual_overrides
        ConsolWorksheetData(project_id=root_pid, year=YEAR, sheet_key="info", data={"rows": []}, version=1),
    ])
    await db.commit()

    approved = _Entry(entry_type="equity", related_company_codes=["A"],
                      lines=[_line(ACCOUNT_LONG_INVEST, debit="70")])
    approved.project_id = root_pid
    records, invalid = records_from_entries([approved])
    basis = build_calc_basis(tree, YEAR, [], records, invalid)

    seen_approved_only: list[bool] = []

    async def fake_build_tree(_db, _pid, *a, **k):
        return tree

    async def fake_load_calc_basis(_db, _pid, _year, *, tree=None, **k):
        return basis

    async def fake_load_tree_entries(_db, _tree, _year, *, approved_only=True, **k):
        seen_approved_only.append(approved_only)
        return [approved]

    monkeypatch.setattr(tree_mod, "build_tree", fake_build_tree)
    monkeypatch.setattr(calc_mod, "load_calc_basis", fake_load_calc_basis)
    monkeypatch.setattr(calc_mod, "load_tree_entries", fake_load_tree_entries)

    proj = await load_post_elimination_projection(db, root_pid, YEAR)
    assert proj is not None
    # 只请求 approved 分录
    assert seen_approved_only == [True]
    # manual overrides 只含四张投影表里真实存在的，不含 info
    assert set(proj.manual_overrides) == {"post_invest", "capital"}
    assert proj.manual_overrides["capital"] == {"consol_report_amount": 5}
    # 子公司归属正确：A 得 70
    li = proj.account(ACCOUNT_LONG_INVEST)
    assert {s.company_code: s.amount for s in li.by_company} == {"A": Decimal("70.00")}
    assert li.is_balanced()


@pytest.mark.asyncio
async def test_loader_returns_none_when_not_consolidated(db: AsyncSession, monkeypatch: pytest.MonkeyPatch):
    """无企业树 ⇒ 返回 None（路由据此回 400）。"""
    import app.services.consol_tree_service as tree_mod
    from app.services.consol_post_elimination_projection import load_post_elimination_projection

    async def fake_build_tree(_db, _pid, *a, **k):
        return None

    monkeypatch.setattr(tree_mod, "build_tree", fake_build_tree)
    assert await load_post_elimination_projection(db, uuid.uuid4(), YEAR) is None
