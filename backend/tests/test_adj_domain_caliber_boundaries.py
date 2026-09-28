"""ADJ 的域边界与口径边界守卫（Phase 1 复盘补漏）。

spec: tb-adjustment-column-formula-closure Phase 1（需求 2.3 / Task 1.9 收尾 / Task 1.12）

## 为什么补这个文件

Phase 1 首轮交付后复盘，发现 4 处欠账：

1. 🔴 **需求 2.3 从未被验证** —— 判据是「底稿域既有 `=ADJ('1521','aje_net')`
   行为零变化（prefill_engine 路径不动）」。我改了 `formula_engine` 却没测过
   prefill 路径，而两者**同名不同口径**（prefill 不排除 origin / L2 排除 workpaper）。
2. 🔴 **`PRELOADED_COLUMN_KEYS` 是死常量** —— 只在 `__all__` 与 docstring 里出现，
   实现另手写一份 9 键字面量，两份清单无一致性检查；且原注释声称
   「守卫据此断言」而那个守卫**不存在**（假声明）。
3. 🔴 **`adj_map` 参数无生产调用方** —— Task 1.9 给 `from_simple_map` 加了参数，
   但唯一生产调用方 `execute_formula` 没传 ⇒ `FormulaEngine.execute`
   （底稿用户自定义公式，`wp_user_formulas` 端点）路径上 `ADJ()` 仍恒 0。
4. 🔴 **合并域静默 0 无说明** —— `consol_report_service` 不传 `adj_data` 是对的
   （合并调整是 `consol_adjustment`，不是单体 `adjustments`），但代码里没写明，
   读者会当成漏传。

## 口径矩阵的两条相关行（差异是刻意的）

| 行 | 用途 | review_status | origin |
|----|------|---------------|--------|
| 2 | `ADJ()` 底稿呈现 | 仅 approved | **不排除** |
| 4 | 试算平衡表调整列 | 仅 approved | **排除 workpaper** |

底稿域（prefill 预设 + 用户自定义公式）走第 2 行；
试算平衡表/报表/审定表回写走第 4 行。
"""
from __future__ import annotations

import inspect
import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base

_PID = uuid.UUID("bbbb3333-0000-4000-8000-000000000411")
_UID = uuid.UUID("bbbb4444-0000-4000-8000-000000000412")
_YEAR = 2096
_CO = "001"
_CODE = "1521"  # 需求 2.3 判据里点名的科目
_NAME = "投资性房地产"

_MANUAL = Decimal("10000")   # origin=manual，两种口径都计入
_WORKPAPER = Decimal("3000")  # origin=workpaper，只有底稿口径计入


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        await _seed(s)
        yield s
    await engine.dispose()


async def _seed(db: AsyncSession) -> None:
    """一行 trial_balance + 两笔 approved AJE（manual 10000 / workpaper 3000）。

    两笔金额不同是刻意的：口径差异 = 3000，可直接从数值判出走的是哪一行口径。
    """
    from app.models.audit_platform_models import (
        AccountCategory,
        Adjustment,
        AdjustmentEntry,
        AdjustmentType,
        TrialBalance,
    )

    db.add(TrialBalance(
        project_id=_PID, year=_YEAR, company_code=_CO,
        standard_account_code=_CODE, account_name=_NAME,
        account_category=AccountCategory.asset,
        unadjusted_amount=Decimal("500000"), audited_amount=Decimal("500000"),
        aje_adjustment=Decimal("0"), rje_adjustment=Decimal("0"),
        opening_balance=Decimal("0"), is_deleted=False,
    ))

    for no, amt, origin in (
        ("AJE-CB-MANUAL", _MANUAL, "manual"),
        ("AJE-CB-WP", _WORKPAPER, "workpaper"),
    ):
        adj_id, grp = uuid.uuid4(), uuid.uuid4()
        db.add(Adjustment(
            id=adj_id, project_id=_PID, year=_YEAR, company_code=_CO,
            adjustment_no=no, adjustment_type=AdjustmentType.aje,
            account_code=_CODE, account_name=_NAME,
            debit_amount=amt, credit_amount=Decimal("0"),
            entry_group_id=grp, review_status="approved", origin=origin,
            is_deleted=False, created_by=_UID,
        ))
        db.add(AdjustmentEntry(
            id=uuid.uuid4(), adjustment_id=adj_id, entry_group_id=grp, line_no=1,
            standard_account_code=_CODE, account_name=_NAME,
            debit_amount=amt, credit_amount=Decimal("0"), is_deleted=False,
        ))
    await db.flush()


# ─── 欠账 1：需求 2.3 底稿域 prefill 路径 ───────────────────────────────────


@pytest.mark.asyncio
async def test_req23_prefill_adj_uses_workpaper_inclusive_caliber(db_session):
    """🔴 需求 2.3：底稿 prefill 的 `ADJ()` 口径 = 矩阵第 2 行（**不排除** origin）。

    值必须是 manual + workpaper = 13000。若得 10000 说明它被改成了
    第 4 行口径 —— 那违反「底稿域行为零变化」。
    """
    from app.services.prefill_engine import _resolve_adj_formula

    v = await _resolve_adj_formula(db_session, _PID, _YEAR, [_CODE, "aje_net"])
    assert v == _MANUAL + _WORKPAPER, (
        f"prefill 的 ADJ 得 {v}，期望 {_MANUAL + _WORKPAPER}（含 workpaper 来源）"
        f" —— 若为 {_MANUAL} 则口径被改成了排除 workpaper，违反需求 2.3"
    )


@pytest.mark.asyncio
async def test_l2_adj_uses_workpaper_exclusive_caliber(db_session):
    """对照：三个 L2 域的 `ADJ()` 口径 = 矩阵第 4 行（**排除** workpaper）。

    值必须是 10000（只算 manual）。与上一条合起来证明两套口径**都正确地不同**。
    """
    from app.services.formula_engine import execute
    from app.services.formula_management.adjudication_writeback import (
        AdjudicationWritebackService,
    )

    ctx = await AdjudicationWritebackService(db_session).build_context(_PID, _YEAR)
    r = execute(f"ADJ('{_CODE}','aje_net')", ctx)
    assert r.errors == [], r.errors
    assert r.value == _MANUAL, (
        f"L2 域的 ADJ 得 {r.value}，期望 {_MANUAL}（排除 workpaper）"
        f" —— 若为 {_MANUAL + _WORKPAPER} 则 V124 双计缺陷复活"
    )


@pytest.mark.asyncio
async def test_two_calibers_differ_by_exactly_the_workpaper_entry(db_session):
    """两套口径的差额必须**恰好**是那笔 workpaper 分录（证明差异有且只有一处）。"""
    from app.services.formula_engine import execute
    from app.services.formula_management.adjudication_writeback import (
        AdjudicationWritebackService,
    )
    from app.services.prefill_engine import _resolve_adj_formula

    wp_inclusive = await _resolve_adj_formula(db_session, _PID, _YEAR, [_CODE, "aje_net"])
    ctx = await AdjudicationWritebackService(db_session).build_context(_PID, _YEAR)
    wp_exclusive = execute(f"ADJ('{_CODE}','aje_net')", ctx).value

    assert wp_inclusive - wp_exclusive == _WORKPAPER, (
        f"两口径差额 {wp_inclusive - wp_exclusive} ≠ workpaper 分录额 {_WORKPAPER}"
    )


def test_prefill_adj_resolver_is_still_registered():
    """prefill 的 ADJ 解析器必须仍在注册表里（需求 2.3「路径不动」）。"""
    from app.services.prefill_engine import (
        _FORMULA_RESOLVERS,
        _resolve_adj_formula,
    )

    assert _FORMULA_RESOLVERS.get("ADJ") is _resolve_adj_formula, (
        "prefill 的 ADJ 解析器被替换/摘除 —— 违反需求 2.3"
    )


def test_prefill_adj_documents_the_dual_implementation():
    """两套实现的存在必须写在 prefill 侧（否则读者只看到一半）。"""
    from app.services.prefill_engine import _resolve_adj_formula

    doc = _resolve_adj_formula.__doc__ or ""
    assert "两套实现" in doc, "prefill 的 ADJ 未说明存在第二套实现"
    assert "_handle_adj" in doc, "未指向 formula_engine 侧的实现"
    assert "需求 2.3" in doc, "未说明为何本函数不得改口径"


# ─── 欠账 2：PRELOADED_COLUMN_KEYS 不再是死常量 ─────────────────────────────


def test_preloaded_keys_constant_is_actually_enforced():
    """🔴 常量必须被实现**运行时**校验，不只是文档。

    首版它只出现在 `__all__` 与 docstring 里，实现另手写一份 9 键字面量 ——
    两份清单无一致性检查，改一处不改另一处不会被发现。
    """
    from app.services.tb_formula_context import build_tb_formula_data

    src = inspect.getsource(build_tb_formula_data)
    assert "PRELOADED_COLUMN_KEYS" in src, (
        "build_tb_formula_data 未引用 PRELOADED_COLUMN_KEYS ⇒ 常量是死的，"
        "实现与它可以任意漂移"
    )
    assert "assert" in src or "raise" in src, (
        "引用了常量但没做断言 ⇒ 仍然测不出漂移"
    )


@pytest.mark.asyncio
async def test_preloaded_keys_match_actual_output(db_session):
    """实际输出的键集 == 常量声明（端到端，不看源码看结果）。"""
    from app.models.audit_platform_models import TrialBalance
    from app.services.tb_formula_context import (
        PRELOADED_COLUMN_KEYS,
        build_tb_formula_data,
    )

    tb_data = await build_tb_formula_data(
        db_session,
        tb=TrialBalance.__table__,
        project_id=_PID, year=_YEAR, company_code=_CO,
        adj_lookup=lambda c, k: Decimal("0"),
    )
    assert tb_data, "分母为空 ⇒ 本测试空转"
    for code, cols in tb_data.items():
        assert set(cols) >= set(PRELOADED_COLUMN_KEYS), (
            f"{code} 实际键集缺 {set(PRELOADED_COLUMN_KEYS) - set(cols)}"
        )


@pytest.mark.asyncio
async def test_preloaded_keys_assertion_catches_missing_key(db_session):
    """🔴 变异证明：往常量里加一个实现不产的键，必须打红。

    直接 monkeypatch 常量（比改实现更干净），验证那条 assert 真的在跑。
    """
    from app.models.audit_platform_models import TrialBalance
    from app.services import tb_formula_context as mod

    original = mod.PRELOADED_COLUMN_KEYS
    mod.PRELOADED_COLUMN_KEYS = original + ("不存在的列名",)
    try:
        with pytest.raises(AssertionError, match="缺预载键"):
            await mod.build_tb_formula_data(
                db_session,
                tb=TrialBalance.__table__,
                project_id=_PID, year=_YEAR, company_code=_CO,
                adj_lookup=lambda c, k: Decimal("0"),
            )
    finally:
        mod.PRELOADED_COLUMN_KEYS = original


# ─── 欠账 3：adj_map 参数有真实生产调用方 ──────────────────────────────────


def test_execute_formula_accepts_and_forwards_adj_map():
    """`execute_formula` 必须接受并转发 `adj_map`（否则 Task 1.9 的参数是死的）。"""
    from app.services.formula_engine import execute_formula

    sig = inspect.signature(execute_formula)
    assert "adj_map" in sig.parameters
    assert sig.parameters["adj_map"].default is None, "默认 None 保既有调用方零回归"

    src = inspect.getsource(execute_formula)
    assert "adj_map=adj_map" in src, "未把 adj_map 转发给 from_simple_map"


def test_formula_engine_execute_loads_adj_data():
    """🔴 `FormulaEngine.execute`（底稿用户自定义公式）必须取调整额。

    这是 `from_simple_map(adj_map=...)` 的**唯一生产调用链**。不取的话
    底稿里写 `ADJ()` 或 `TB(...,'AJE调整')` 恒 0 且无提示。

    🔴 判据按**调用链**而非「源码含 adj_net_batch」——取数逻辑已抽到伴生模块
    `tb_formula_context.load_adj_map_if_needed`（`formula_engine` 是 L1 内核，
    不该内联 L2 取数）。首版按源码字面判，抽取后立刻误判成"未取数"。
    """
    from app.services.formula_engine import FormulaEngine

    src = inspect.getsource(FormulaEngine.execute)
    assert "load_adj_map_if_needed" in src, "未调 L2 取数口 ⇒ 该路径 ADJ() 恒 0"
    assert "adj_map=adj_map" in src, "取了但没传给 execute_formula"
    # 口径必须是第 2 行（底稿呈现：不排除 origin）
    assert "exclude_origins=frozenset()" in src, (
        "底稿用户自定义公式应用矩阵第 2 行口径（不排除 origin），"
        "与 prefill_engine 对齐；用第 4 行会让同一底稿两种 ADJ 得不同的数"
    )
    # 且那个取数口真的走 adj_net_batch（一路查到底，不止看直接调用）
    from app.services.tb_formula_context import load_adj_map_if_needed

    loader_src = inspect.getsource(load_adj_map_if_needed)
    assert "adj_net_batch" in loader_src, "取数口未走 adj_net_batch 单一真源"


def test_formula_engine_execute_only_loads_when_needed():
    """公式不含调整额 token 时不该触发取数（预判在取数口内）。"""
    from app.services.tb_formula_context import (
        _ADJ_TOKENS,
        load_adj_map_if_needed,
    )

    assert set(_ADJ_TOKENS) == {"ADJ(", "AJE调整", "RJE调整"}, (
        f"token 预判清单变了：{_ADJ_TOKENS} —— 漏一个写法即该写法恒 0"
    )
    src = inspect.getsource(load_adj_map_if_needed)
    assert "_ADJ_TOKENS" in src, "取数口未做 token 预判 ⇒ 每条公式都触发取数"


@pytest.mark.asyncio
async def test_adj_loader_returns_none_without_adj_token(db_session):
    """行为级：公式不含调整额 token → 返 None（不发查询）。"""
    from app.services.tb_formula_context import load_adj_map_if_needed

    r = await load_adj_map_if_needed(
        db_session, project_id=_PID, year=_YEAR,
        formula="TB('1521','期末余额')",
        account_codes={_CODE}, exclude_origins=frozenset(),
    )
    assert r is None, "不含 ADJ token 却触发了取数"


@pytest.mark.asyncio
async def test_adj_loader_honours_caliber_parameter(db_session):
    """🔴 取数口的 `exclude_origins` 必须真的生效（两种口径给两个值）。

    该参数**无默认值**是刻意的：给默认值会让下一个调用方在不知道有两种口径的
    情况下静默继承一个。
    """
    from app.services.tb_formula_context import load_adj_map_if_needed

    kw = dict(
        project_id=_PID, year=_YEAR,
        formula=f"ADJ('{_CODE}','aje_net')", account_codes={_CODE},
    )
    inclusive = await load_adj_map_if_needed(
        db_session, exclude_origins=frozenset(), **kw
    )
    exclusive = await load_adj_map_if_needed(
        db_session, exclude_origins=frozenset({"workpaper"}), **kw
    )
    assert inclusive[_CODE]["aje_net"] == _MANUAL + _WORKPAPER
    assert exclusive[_CODE]["aje_net"] == _MANUAL


# ─── 欠账 4：合并域不传 adj_data 有显式说明 ────────────────────────────────


def test_consol_documents_why_adj_data_is_omitted():
    """🔴 合并域刻意不传 `adj_data` 必须写明理由，否则会被当成漏传"修好"。

    合并调整是 `consol_trial.consol_adjustment` / `consol_elimination`，
    与单体 `adjustments` 是不同会计概念（合并数 = 个别数汇总 + 差额表）。
    喂单体调整额进去会把同一笔调整计两次。
    """
    from app.services.consol_report_service import ConsolReportService

    src = inspect.getsource(ConsolReportService)
    assert "adj_data" in src, "合并域未提及 adj_data（读者无法判断是刻意还是漏传）"
    assert "consol_adjustment" in src or "consol_elimination" in src, (
        "未说明合并域的调整数据在哪"
    )
    # 且确实没传
    assert "adj_data=" not in src, "合并域传了 adj_data ⇒ 单体调整额会被计两次"
