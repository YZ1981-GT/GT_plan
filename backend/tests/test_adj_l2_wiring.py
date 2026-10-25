"""三个 L2 编排层填充 `FormulaContext.adj_data` 的接线守卫。

spec: tb-adjustment-column-formula-closure Phase 1 Task 1.8

三处 L2：
1. `trial_balance_service.get_summary_with_adjustments`（试算平衡表）
2. `report_engine.ReportFormulaParser.execute` → `evaluate_formula`（报表）
3. `formula_management.adjudication_writeback.build_context`（审定表回写）

判据设计要点：
- **按真实取数链路判**，不只判"参数传没传"。`adj_net_batch` 对空集合
  **直接返回 `{}` 不发查询**，所以"传了 account_codes=None"与"没传"效果相同 ——
  我第一版 report_engine 就写成 `account_codes=None`，参数在、语义错、ADJ 恒 0。
  故本文件对 report_engine 断言它**真的查了科目码**。
- **口径与试算平衡表一致**：三处都必须 `include_statuses={approved}` +
  `exclude_origins={workpaper}`（口径矩阵第 4 行），否则同一 `ADJ()` 公式在
  三个域给出不同的数 —— 那正是本 spec 要消除的形态。
"""
from __future__ import annotations

import ast
import inspect
import re

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    """本地 in-memory SQLite 会话（与 `test_tb_summary_adj_caliber` 同款）。

    本文件的端到端测试自建数据，故不复用那边的 `_seed_base`。
    """
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s
    await engine.dispose()


# ─── 公共：源码级口径断言 ───────────────────────────────────────────────────


def _assert_caliber(src: str, where: str) -> None:
    """断言某段源码里的 `adj_net_batch` 调用带全套过滤（口径矩阵第 4 行）。"""
    assert "adj_net_batch" in src, f"{where} 未调用 adj_net_batch"
    assert "DEFAULT_INCLUDE_STATUSES" in src or "approved" in src, (
        f"{where} 的 adj_net_batch 调用缺 include_statuses ⇒ draft 会进调整额"
    )
    assert "workpaper" in src, (
        f"{where} 的 adj_net_batch 调用缺 exclude_origins={{workpaper}} ⇒ 与审定表 "
        f"writeback 双计"
    )


# ─── L2 #1：trial_balance_service ───────────────────────────────────────────


def test_tb_service_passes_adj_data_to_context():
    """试算平衡表的 `FormulaContext` 必须收到 `adj_data`。"""
    from app.services.trial_balance_service import TrialBalanceService

    src = inspect.getsource(TrialBalanceService.get_summary_with_adjustments)
    assert "adj_data=adj_data" in src, (
        "get_summary_with_adjustments 构造 FormulaContext 时未传 adj_data ⇒ "
        "该域的 ADJ() 恒 0"
    )
    _assert_caliber(src, "trial_balance_service")


def test_tb_service_does_not_rename_adj_keys():
    """`adj_data` 必须是 `adj_net_batch` 的原样返回值，禁做键名转换。

    转换点就是漂移点：L1 的 `_handle_adj` 按 `f"{norm_type}_net"` 取键，
    L2 若改键名则两侧各自演化。
    """
    import textwrap

    from app.services.trial_balance_service import TrialBalanceService

    src = textwrap.dedent(
        inspect.getsource(TrialBalanceService.get_summary_with_adjustments)
    )
    # 🔴 必须按 AST 定位 `FormulaContext(...)` 的 adj_data **实参**。
    # 首版用正则 `adj_data\s*=\s*(...)` 匹配到了赋值语句
    # `adj_data = await adj_net_batch(...)`，把取数调用误判成"键名转换"。
    tree = ast.parse(src)
    args: list[ast.expr] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "FormulaContext"
        ):
            for kw in node.keywords:
                if kw.arg == "adj_data":
                    args.append(kw.value)
    assert args, "FormulaContext 调用里没有 adj_data 实参"
    for value in args:
        assert isinstance(value, ast.Name), (
            f"adj_data 实参是 {type(value).__name__} 而非裸变量 —— "
            f"疑似在 L2 做了键名转换（转换点就是漂移点）"
        )


# ─── L2 #2：report_engine ───────────────────────────────────────────────────


def test_evaluate_formula_accepts_adj_data():
    """`evaluate_formula` signature 含可选 `adj_data`，缺省为 None（既有调用方零回归）。"""
    from app.services.report_engine import evaluate_formula

    sig = inspect.signature(evaluate_formula)
    assert "adj_data" in sig.parameters, "evaluate_formula 缺 adj_data 参数"
    p = sig.parameters["adj_data"]
    assert p.default is None, f"adj_data 默认值应为 None，实为 {p.default!r}"
    assert p.kind == inspect.Parameter.KEYWORD_ONLY, "adj_data 应为关键字参数"


def test_evaluate_formula_forwards_adj_data_to_context():
    from app.services.report_engine import evaluate_formula

    src = inspect.getsource(evaluate_formula)
    assert "adj_data=adj_data or {}" in src, (
        "evaluate_formula 未把 adj_data 传给 FormulaContext"
    )


def test_report_parser_caches_adj_data():
    """🔴 `_get_adj_data` 必须按实例缓存 —— `execute` 是逐行调用的。

    不缓存会让 `adj_net_batch` 按报表行数重复执行，而它存在的理由正是避免 N+1。
    """
    from app.services.report_engine import ReportFormulaParser

    src = inspect.getsource(ReportFormulaParser._get_adj_data)
    assert "self._adj_data is not None" in src, (
        "_get_adj_data 缺缓存短路 ⇒ 逐行重复查询（N+1）"
    )
    init_src = inspect.getsource(ReportFormulaParser.__init__)
    assert "_adj_data" in init_src, "__init__ 未初始化 _adj_data 缓存位"


def test_report_parser_queries_real_account_codes():
    """🔴 `_get_adj_data` 必须真的查科目码，不得传 None/空集。

    `adj_net_batch` 对空集合**直接返回 {} 不发查询**（其 docstring 明载），
    所以 `account_codes=None` 会让 ADJ 静默恒 0 —— 参数在、语义错。
    我第一版就是这么写的，故此判据按「查询语句存在」而非「参数存在」判。
    """
    from app.services.report_engine import ReportFormulaParser

    src = inspect.getsource(ReportFormulaParser._get_adj_data)
    assert "standard_account_code" in src, (
        "_get_adj_data 未查 standard_account_code ⇒ account_codes 可能是空集，"
        "adj_net_batch 会直接返回 {} 而 ADJ() 恒 0"
    )
    assert "account_codes=None" not in src, (
        "account_codes=None ⇒ adj_net_batch 走 `(account_codes or [])` 得空集，"
        "直接返回 {} 不发查询"
    )
    _assert_caliber(src, "report_engine._get_adj_data")


def test_report_parser_only_loads_adj_when_formula_uses_it():
    """公式不含 ADJ 时不应触发调整额取数（绝大多数报表公式不用）。"""
    from app.services.report_engine import ReportFormulaParser

    src = inspect.getsource(ReportFormulaParser.execute)
    assert '"ADJ(" in formula' in src, (
        "execute 未做 ADJ 存在性预判 ⇒ 每条公式都会触发一次调整额取数"
    )


# ─── L2 #3：adjudication_writeback ──────────────────────────────────────────


def test_adjudication_build_context_passes_adj_data():
    from app.services.formula_management.adjudication_writeback import (
        AdjudicationWritebackService,
    )

    src = inspect.getsource(AdjudicationWritebackService.build_context)
    assert "adj_data=adj_data" in src, (
        "build_context 构造 FormulaContext 时未传 adj_data ⇒ 审定表域 ADJ() 恒 0"
    )
    _assert_caliber(src, "adjudication_writeback.build_context")


def test_adjudication_keeps_persisted_and_realtime_separate():
    """🔴 持久化快照与实时汇总必须并存，禁"对齐"。

    `tb_data["AJE调整"]` ← `trial_balance.aje_adjustment`（快照）
    `adj_data["aje_net"]` ← `adj_net_batch`（实时）

    两者不等即快照过期（需求 3.3 的信号）。若有人把 `tb_data["AJE调整"]` 改成
    从 `adj_data` 取，差异就永远观测不到了。
    """
    from app.services.formula_management.adjudication_writeback import (
        AdjudicationWritebackService,
    )

    src = inspect.getsource(AdjudicationWritebackService.build_context)
    assert "row.aje_adjustment" in src, (
        "tb_data 的 AJE调整 不再取自 trial_balance.aje_adjustment ⇒ "
        "快照与实时的差异无法观测"
    )
    # tb_data 的 AJE调整 不得引用 adj_data
    tb_block = src.split("adj_data")[0]
    assert '"AJE调整": aje' in tb_block, "AJE调整 的赋值形态变了，需复核本守卫"


# ─── 三域口径一致性（汇总判据）────────────────────────────────────────────


def test_all_three_l2_use_same_caliber():
    """三处 L2 的 `adj_net_batch` 调用参数必须逐一相同。

    口径不同会让同一条 `ADJ('6001','aje_net')` 在试算平衡表、报表、审定表
    给出三个数 —— 那正是 Phase 0 要消除的「三套口径各自注释声称同口径而实际三样」。
    """
    from app.services.formula_management.adjudication_writeback import (
        AdjudicationWritebackService,
    )
    from app.services.report_engine import ReportFormulaParser
    from app.services.trial_balance_service import TrialBalanceService

    sources = {
        "trial_balance": inspect.getsource(
            TrialBalanceService.get_summary_with_adjustments
        ),
        "report_engine": inspect.getsource(ReportFormulaParser._get_adj_data),
        "adjudication": inspect.getsource(
            AdjudicationWritebackService.build_context
        ),
    }

    calibers: dict[str, tuple[str, ...]] = {}
    for name, src in sources.items():
        # 提取 adj_net_batch(...) 调用的实参名集合（按 AST，避免正则跨行问题）
        tree = ast.parse(inspect.cleandoc(src)) if src.startswith("async def") else None
        if tree is None:
            # 缩进源码：先 dedent
            import textwrap

            tree = ast.parse(textwrap.dedent(src))
        found: tuple[str, ...] | None = None
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "adj_net_batch"
            ):
                found = tuple(sorted(kw.arg or "" for kw in node.keywords))
        assert found is not None, f"{name} 未找到 adj_net_batch 调用"
        calibers[name] = found

    distinct = set(calibers.values())
    assert len(distinct) == 1, (
        f"三处 L2 的 adj_net_batch 实参集不一致：{calibers}"
    )
    # 且必须包含全套过滤
    keys = next(iter(distinct))
    for required in ("project_id", "year", "account_codes", "include_statuses",
                     "exclude_origins"):
        assert required in keys, f"adj_net_batch 调用缺 {required}：{keys}"


@pytest.mark.parametrize(
    "module_path,symbol",
    [
        ("app.services.trial_balance_service", "TrialBalanceService"),
        ("app.services.report_engine", "ReportFormulaParser"),
        (
            "app.services.formula_management.adjudication_writeback",
            "AdjudicationWritebackService",
        ),
    ],
)
def test_l2_modules_import_cleanly(module_path, symbol):
    """三个 L2 模块可正常 import（防我加的 lazy import 写错名字）。

    memory 记录过同源事故：`adj-formula-repair` spec 修了 11 处 lazy import
    引用不存在名字的缺陷（AST 过 ≠ 运行期名字可解析）。
    """
    import importlib

    mod = importlib.import_module(module_path)
    assert hasattr(mod, symbol), f"{module_path} 缺 {symbol}"


# ─── 端到端行为：真 DB 落库 → ADJ() 取到实时值 ──────────────────────────────
#
# 🔴 上面全是源码级判据（防接线退化），但源码对 ≠ 链路通。
# memory 记录的教训：「mock/spy 只验接线不验语义」「『修好 import』≠『跑通』」。
# 本节用真 ORM 落库、跑真实 `build_context`，断言 ADJ() 取到非零实时值。

_E2E_CODE = "6001"
_E2E_NAME = "主营业务收入"


async def _seed(db, *, pid, year, review_status, snapshot_aje="0"):
    """落库 TrialBalance + Adjustment 主表 + AdjustmentEntry 明细行。

    字段清单照 `test_trial_balance._add_adj`（Phase 0 已实证）：
    主表 `account_code`/`debit_amount`/`credit_amount` 是 **NOT NULL 的遗留冗余列**，
    必须填但 `adj_net_batch` 不读它们（ADR-ADJ-001 读明细表）。
    `entry_group_id` 与 `line_no` 也是必填。

    `snapshot_aje` 是 `trial_balance.aje_adjustment`（持久化快照），
    刻意与实时汇总不同，用于验证两口径可区分。
    """
    import uuid
    from decimal import Decimal

    from app.models.audit_platform_models import (
        AccountCategory,
        Adjustment,
        AdjustmentEntry,
        AdjustmentType,
        TrialBalance,
    )

    db.add(
        TrialBalance(
            project_id=pid,
            year=year,
            company_code="001",
            standard_account_code=_E2E_CODE,
            account_name=_E2E_NAME,
            # 6001 主营业务收入 = 收入类（贷方正常）。
            # 这不只是填 NOT NULL：`adj_net_batch` 的符号归一按科目方向取反，
            # 收入类的贷方分录归一后为正 —— 类别填错会让期望值算错。
            account_category=AccountCategory.revenue,
            unadjusted_amount=Decimal("1000"),
            audited_amount=Decimal("1000"),
            aje_adjustment=Decimal(snapshot_aje),
            rje_adjustment=Decimal("0"),
            opening_balance=Decimal("0"),
            is_deleted=False,
        )
    )

    adj_id = uuid.uuid4()
    grp = uuid.uuid4()
    db.add(
        Adjustment(
            id=adj_id,
            project_id=pid,
            year=year,
            company_code="001",
            adjustment_no=f"AJE-E2E-{review_status.value}",
            # 🔴 枚举成员是**小写** `aje`/`rje`（实证 `[m.name for m in AdjustmentType]`）。
            # 我按命名习惯写 `AdjustmentType.AJE` 抛 AttributeError —— 铁律：
            # 引用枚举成员前先 getattr 实证，不信大小写直觉。
            adjustment_type=AdjustmentType.aje,
            # 主表遗留冗余列（NOT NULL 必填，但取数不读）
            account_code=_E2E_CODE,
            account_name=_E2E_NAME,
            debit_amount=Decimal("300"),
            credit_amount=Decimal("0"),
            entry_group_id=grp,
            review_status=review_status,
            origin="manual",  # 非 workpaper（口径矩阵第 4 行排除 workpaper）
            is_deleted=False,
            created_by=uuid.uuid4(),  # NOT NULL
        )
    )
    db.add(
        AdjustmentEntry(
            id=uuid.uuid4(),
            adjustment_id=adj_id,
            entry_group_id=grp,
            line_no=1,
            standard_account_code=_E2E_CODE,  # 🔴 权威科目列在明细表
            account_name=_E2E_NAME,
            debit_amount=Decimal("300"),
            credit_amount=Decimal("0"),
            is_deleted=False,
        )
    )
    await db.flush()


@pytest.mark.asyncio
async def test_adjudication_context_resolves_adj_end_to_end(db_session):
    """真落库 → `build_context` → `ADJ()` 取到实时调整额（非 0）。

    三个必要条件（Phase 0 fixture 教训，缺一即调整额恒 0）：
    ① 建 `AdjustmentEntry` 明细行（ADR-ADJ-001 科目列在明细表）
    ② 显式 `review_status=approved`（server_default 是 `draft`）
    ③ `origin` 非 workpaper（口径矩阵第 4 行）

    并断言实时值 ≠ 持久化快照（快照刻意留 0）—— 需求 3.3 的可观测基础。
    """
    import uuid
    from decimal import Decimal

    from app.models.audit_platform_models import ReviewStatus
    from app.services.formula_engine import execute
    from app.services.formula_management.adjudication_writeback import (
        AdjudicationWritebackService,
    )

    pid, year = uuid.uuid4(), 2025
    await _seed(db_session, pid=pid, year=year,
                review_status=ReviewStatus.approved, snapshot_aje="0")

    ctx = await AdjudicationWritebackService(db_session).build_context(pid, year)

    assert _E2E_CODE in ctx.adj_data, f"adj_data 未含 {_E2E_CODE}：{ctx.adj_data}"

    r_adj = execute(f"ADJ('{_E2E_CODE}','aje_net')", ctx)
    assert r_adj.errors == [], r_adj.errors
    assert r_adj.value != Decimal("0"), (
        "ADJ() 取到 0 —— 实时汇总链路未通（源码判据全绿也可能是这种情况）"
    )

    r_tb = execute(f"TB('{_E2E_CODE}','AJE调整')", ctx)
    assert r_tb.value == Decimal("0"), "持久化快照应仍为 0（fixture 刻意如此）"
    assert r_adj.value != r_tb.value, (
        "实时值与快照相等 ⇒ 两者被「对齐」了，需求 3.3 的信号将永远观测不到"
    )


@pytest.mark.asyncio
async def test_adjudication_context_excludes_draft_end_to_end(db_session):
    """🔴 变异方向：draft 分录**不得**进 ADJ()（口径矩阵第 4 行）。

    与上一条同样的数据，只把 `review_status` 改成 draft ⇒ ADJ() 必须得 0。
    这是双向变异的另一半：上一条证明「有数据能取到」，本条证明「过滤真的生效」。
    """
    import uuid
    from decimal import Decimal

    from app.models.audit_platform_models import ReviewStatus
    from app.services.formula_engine import execute
    from app.services.formula_management.adjudication_writeback import (
        AdjudicationWritebackService,
    )

    pid, year = uuid.uuid4(), 2025
    await _seed(db_session, pid=pid, year=year, review_status=ReviewStatus.draft)

    ctx = await AdjudicationWritebackService(db_session).build_context(pid, year)
    r = execute(f"ADJ('{_E2E_CODE}','aje_net')", ctx)
    assert r.value == Decimal("0"), (
        f"draft 分录被计入 ADJ() ⇒ review_status 过滤未生效，实得 {r.value}"
    )
