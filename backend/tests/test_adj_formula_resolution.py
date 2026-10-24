"""test_adj_formula_resolution.py — ADJ() 真执行求值端到端守卫.

spec: adj-formula-repair-and-approval-gate-wiring · 阶段 0 任务 0.1 + 0.2

本文件有三组守卫：
1. ADJ() 在底稿预填路径真正求值（0.1）：类型归一 / 符号归一 / 仅已审批 / 无数据返 0
2. 每个注册的取数函数，统一预载层都在真库上取到数据（0.2，原「_FORMULA_RESOLVERS 全成员冒烟」）
3. normalize_adj_type 类型归一专项（1.3）

formula-fetch-followup-defect-closure 6.5 改写：0.1 / 0.2 原以 ``prefill_engine._resolve_adj_formula`` /
``_FORMULA_RESOLVERS`` / ``_resolve_tb_aux`` 为对象，三者自 formula-execution-path-convergence 起已无调用方、
``2638b32fd`` 删除，13 例红。且原用例多为 mock DB（复盘已记：删掉 adj_net 的 type / status 过滤，spy 守卫零打红）。
现改为真 SQLite 落多类分录、经现行入口 ``resolve_extended_formula``（用户公式预览，内部「预载 → L1」，与
``prefill_workpaper_real`` 同一 ADJ 口径）按值断言；0.2 改为「每个注册的取数函数，预载层都有取数分支且真库上取到数据」
—— 原冒烟只防 ImportError，收敛后 LEDGER_DETAIL 预载层根本不取数（恒 0 笔）它也发现不了。

Validates: Requirements 7.1, 7.2, 7.4, 7.5 · Properties P1, P2, P12
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base

_PID = uuid.UUID("aaaaaaaa-0000-4000-8000-000000000001")
_UID = uuid.UUID("aaaaaaaa-0000-4000-8000-000000000002")
_YEAR = 2099


@pytest_asyncio.fixture
async def db() -> AsyncSession:
    """1001 库存现金：已审批 AJE 借 500、RJE 借 300，另有草稿 AJE 900（不计）、已删除 AJE 700（不计）；
    2202 应付账款（贷方类）：已审批 AJE 贷 1000；1122 应收账款：已审批 AJE 借 120 + 贷 20 两行同一分录组。
    另：试算表 1001 审定数 100 / 1602 序时账贷方 / 1121 辅助余额，供「每个取数函数都有数据源」守卫用。"""
    from app.models.audit_platform_models import (
        AccountCategory, Adjustment, AdjustmentEntry, AdjustmentType, TbAuxBalance, TbLedger, TrialBalance,
    )

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        def adj(no, kind, lines, status="approved", deleted=False):
            adj_id, grp = uuid.uuid4(), uuid.uuid4()
            code, name, debit, credit = lines[0]
            s.add(Adjustment(id=adj_id, project_id=_PID, year=_YEAR, company_code="001", adjustment_no=no,
                             adjustment_type=kind, account_code=code, account_name=name,
                             debit_amount=Decimal(debit), credit_amount=Decimal(credit), entry_group_id=grp,
                             review_status=status, origin="manual", is_deleted=deleted, created_by=_UID))
            for i, (code, name, debit, credit) in enumerate(lines, start=1):
                s.add(AdjustmentEntry(id=uuid.uuid4(), adjustment_id=adj_id, entry_group_id=grp, line_no=i,
                                      standard_account_code=code, account_name=name, debit_amount=Decimal(debit),
                                      credit_amount=Decimal(credit), is_deleted=deleted))

        adj("AJE-1001", AdjustmentType.aje, [("1001", "库存现金", "500", "0")])
        adj("RJE-1001", AdjustmentType.rje, [("1001", "库存现金", "300", "0")])
        adj("AJE-1001-DRAFT", AdjustmentType.aje, [("1001", "库存现金", "900", "0")], status="draft")
        adj("AJE-1001-DEL", AdjustmentType.aje, [("1001", "库存现金", "700", "0")], deleted=True)
        adj("AJE-2202", AdjustmentType.aje, [("2202", "应付账款", "0", "1000")])
        adj("AJE-1122", AdjustmentType.aje, [("1122", "应收账款", "120", "0"), ("1122", "应收账款", "0", "20")])
        s.add(TrialBalance(project_id=_PID, year=_YEAR, company_code="001", standard_account_code="1001",
                           account_name="库存现金", account_category=AccountCategory.asset,
                           unadjusted_amount=Decimal("100"), audited_amount=Decimal("100"),
                           aje_adjustment=Decimal("0"), rje_adjustment=Decimal("0"),
                           opening_balance=Decimal("40"), is_deleted=False))
        s.add(TbLedger(project_id=_PID, year=_YEAR, company_code="001", voucher_date=date(_YEAR, 6, 30),
                       voucher_no="记-06-1", account_code="1602", account_name="累计折旧", accounting_period=6,
                       debit_amount=Decimal("0"), credit_amount=Decimal("6000")))
        s.add(TbAuxBalance(project_id=_PID, year=_YEAR, company_code="001", account_code="1121",
                           aux_type="客户", aux_code="C001", aux_name="甲公司",
                           closing_balance=Decimal("300"), opening_balance=Decimal("0")))
        await s.commit()
        yield s
    await engine.dispose()


async def _adj(db: AsyncSession, code: str, kind: str):
    from app.services.prefill_engine import resolve_extended_formula

    return await resolve_extended_formula(db, _PID, _YEAR, "ADJ", f"'{code}','{kind}'")


# ---------------------------------------------------------------------------
# 0.1 — ADJ() 在底稿预填路径真正求值
# ---------------------------------------------------------------------------


class TestAdjFormulaResolution:
    """经 ``resolve_extended_formula``（预载 ``adj_net_batch`` → L1 ``_handle_adj``）在真库分录上按值断言。"""

    def test_adj_models_importable(self):
        """P1：调整分录模型在 audit_platform_models（原 phase10_models 无此定义 ⇒ 每次调用必抛 ImportError）。"""
        from app.models.audit_platform_models import Adjustment, AdjustmentEntry  # noqa: F401

    @pytest.mark.asyncio
    async def test_aje_and_rje_differ_by_type_filter(self, db):
        """P2：同一科目 AJE 与 RJE 各取各的（删掉 adjustment_type 过滤会两者相等 = 800）。"""
        assert await _adj(db, "1001", "aje_net") == Decimal("500")
        assert await _adj(db, "1001", "rje_net") == Decimal("300")

    @pytest.mark.asyncio
    async def test_only_approved_and_not_deleted(self, db):
        """仅已审批：草稿 900、已删除 700 都不计入（口径矩阵第 2 行，ADR-ADJ-003）。"""
        assert await _adj(db, "1001", "aje_net") == Decimal("500")

    @pytest.mark.asyncio
    async def test_credit_account_sign_normalization(self, db):
        """贷方类科目（2202 应付账款）：贷记 1000 ⇒ SUM(借-贷) = -1000，按科目方向取反为 1000。"""
        assert await _adj(db, "2202", "aje_net") == Decimal("1000")

    @pytest.mark.asyncio
    async def test_debit_account_keeps_sign_and_nets_lines(self, db):
        """借方类科目：同一分录组借 120 贷 20 ⇒ 净额 100，不取反（与贷方类互为正 / 反样本，P12）。"""
        assert await _adj(db, "1122", "aje_net") == Decimal("100")

    @pytest.mark.asyncio
    async def test_no_data_returns_zero(self, db):
        """无分录 ⇒ Decimal('0')（合法的 0，不是 None）；与上面有数据的非零结果互为正 / 反样本。"""
        result = await _adj(db, "9999", "aje_net")
        assert result == Decimal("0") and result is not None

    @pytest.mark.asyncio
    async def test_invalid_type_is_not_a_number(self, db):
        """P3：类型写错（「类型」占位）⇒ 取不到（None），不退化为不加类型过滤。"""
        assert await _adj(db, "1001", "类型") is None


# ---------------------------------------------------------------------------
# 0.2 — 每个注册的取数函数，预载层都有取数分支且真库上取到数据
# ---------------------------------------------------------------------------

#: 取数函数 → (样例公式, 预载扫描键, FormulaContext 字段, 样例在本文件真库上的期望值)。
#: 期望值为 None 的：取值 SQL 是 PG 专用写法或依赖附注 / 报表 / 上年数据，真库求值在所列测试里覆盖。
_DATA_FUNCTIONS: dict[str, tuple[str, str, str, Decimal | None]] = {
    "TB": ("TB('1001','期末余额')", "tb_codes", "tb_data", Decimal("100")),
    "SUM_TB": ("SUM_TB('1001~1002','期末余额')", "tb_codes", "tb_data", Decimal("100")),
    "ADJ": ("ADJ('1001','aje_net')", "adj_codes", "adj_data", Decimal("500")),
    "LEDGER": ("LEDGER('1602','credit','6月')", "ledger_specs", "ledger_data", Decimal("6000")),
    "COUNT_LEDGER": ("COUNT_LEDGER('1602','6月')", "ledger_count_specs", "ledger_count_data", Decimal("1")),
    "LEDGER_DETAIL": ("LEDGER_DETAIL('1602','6月','>=5000')", "ledger_detail_specs", "ledger_detail_data",
                      Decimal("1")),
    "TB_AUX": ("TB_AUX('1121','客户','期末余额')", "tb_aux_specs", "tb_aux_data", Decimal("300")),
    "AUX": ("AUX('1121','客户','C001','期末余额')", "aux_specs", "aux_data", None),       # test_aux_formula_*
    "WP": ("WP('D2','明细表D2-2','期末合计')", "wp_refs", "wp_data", None),               # test_prefill_wp_prev_resolution
    "NOTE": ("NOTE('五、1','货币资金','期末余额')", "note_refs", "note_data", None),     # formula_settings/test_note_*
    "PREV": ("PREV('1001','期末余额')", "prev_codes", "prior_tb_data", None),            # test_prefill_wp_prev_resolution
    "ROW": ("ROW('BS-001')", "report_refs", "row_cache", None),                          # 报表行由 row_cache / 已生成报表供数
    "SUM_ROW": ("SUM_ROW('BS-001','BS-002')", "report_refs", "row_cache", None),
    "REPORT": ("REPORT('BS-001','本期')", "report_refs", "row_cache", None),
}
#: 不取数的函数（纯运算 / 占位）
_NON_DATA_FUNCTIONS = frozenset({"ABS", "ROUND", "MAX", "MIN", "IF", "PLACEHOLDER"})


def _builtin_functions() -> set[str]:
    from app.services.formula_engine import _REGISTRY

    return {item["name"] for item in _REGISTRY.list_all() if item.get("category") != "自定义"}


class TestPreloadCoversEveryDataFunction:
    """原「_FORMULA_RESOLVERS 全成员冒烟」：注册表里每个取数函数，预载层都扫得到、取得到。"""

    def test_every_registered_function_is_classified(self):
        """注册表成员现算：新增函数未登记取数口径即红（防「加了函数，预载层没取数，求值恒 0」重演）。"""
        unclassified = sorted(_builtin_functions() - set(_DATA_FUNCTIONS) - _NON_DATA_FUNCTIONS)
        assert not unclassified, f"注册表新增函数未登记取数口径：{unclassified}"
        stale = sorted((set(_DATA_FUNCTIONS) | _NON_DATA_FUNCTIONS) - _builtin_functions())
        assert not stale, f"登记了注册表里已没有的函数：{stale}"

    @pytest.mark.parametrize("name", sorted(_DATA_FUNCTIONS))
    def test_preloader_scans_each_data_function(self, name):
        from app.services.formula_preloader import _scan_refs

        formula, ref_key, _field, _expected = _DATA_FUNCTIONS[name]
        assert _scan_refs([formula])[ref_key], f"{formula} 没被扫进 {ref_key}：预填里该类公式恒取不到"

    @pytest.mark.asyncio
    async def test_preload_fills_context_and_l1_reads_it(self, db):
        """所有样例一次预载（任一取数分支 import / SQL 出错即抛）；能在 SQLite 上取数的逐个按值断言 ——
        LEDGER_DETAIL 原先 ``ledger_detail_data={}`` 写死，这里就是 0 笔而不是 1 笔。"""
        from app.services.formula_engine import execute
        from app.services.formula_preloader import preload

        ctx = await preload(db, _PID, _YEAR, [f for f, *_ in _DATA_FUNCTIONS.values()], row_cache={})
        checked = 0
        for name, (formula, _ref_key, field, expected) in sorted(_DATA_FUNCTIONS.items()):
            if expected is None:
                continue
            assert getattr(ctx, field), f"{name}：预载后 ctx.{field} 为空"
            result = execute(formula, ctx)
            assert result.ok and result.value == expected, f"{name} {formula} → {result.value}（{result.errors}）"
            checked += 1
        assert checked >= 7, "按值断言的取数函数过少，守卫空转"

    @pytest.mark.asyncio
    async def test_mutation_proof_unloaded_source_is_detected(self, db, monkeypatch):
        """P12 双向变异：把 LEDGER_DETAIL 的预载分支换成不取数（原缺陷形态），上一条的判据必须打红。"""
        from app.services import formula_preloader
        from app.services.formula_engine import execute

        async def _no_detail(*_a, **_k):
            return {}

        monkeypatch.setattr(formula_preloader, "_load_ledger_detail", _no_detail)
        formula = _DATA_FUNCTIONS["LEDGER_DETAIL"][0]
        ctx = await formula_preloader.preload(db, _PID, _YEAR, [formula])
        assert not ctx.ledger_detail_data
        assert not execute(formula, ctx).ok, "预载层不取明细时 L1 必须报错（原先给 0 笔）"


# ---------------------------------------------------------------------------
# 1.3 — normalize_adj_type 类型归一专项守卫
# ---------------------------------------------------------------------------


class TestNormalizeAdjType:
    """normalize_adj_type 全覆盖守卫。

    spec: adj-formula-repair-and-approval-gate-wiring · 阶段 1 任务 1.3
    Validates: Requirements 2.1, 2.2, 2.3 · Properties P2, P3

    归一表须容纳：
    - AJE 族：aje_net / AJE / 审计调整 → "aje"
    - RJE 族：rje_net / RJE / 重分类 → "rje"
    不可归一 → raise ValueError，禁退化为不加 adjustment_type 过滤。
    """

    # -- P2: AJE 族全部归一到 "aje" --

    @pytest.mark.parametrize("raw", ["aje_net", "AJE", "审计调整", "aje", "Aje_Net", "AJE_NET"])
    def test_aje_family_normalizes_to_aje(self, raw: str):
        """需求 2.1 + 2.2：AJE 族各种写法（含大小写变体）均归一到 "aje"。"""
        from app.services.adjustment_amount_source import normalize_adj_type

        assert normalize_adj_type(raw) == "aje", (
            f"输入 {raw!r} 应归一为 'aje'"
        )

    # -- P2: RJE 族全部归一到 "rje" --

    @pytest.mark.parametrize("raw", ["rje_net", "RJE", "重分类", "rje", "Rje_Net", "RJE_NET"])
    def test_rje_family_normalizes_to_rje(self, raw: str):
        """需求 2.1 + 2.2：RJE 族各种写法（含大小写变体）均归一到 "rje"。"""
        from app.services.adjustment_amount_source import normalize_adj_type

        assert normalize_adj_type(raw) == "rje", (
            f"输入 {raw!r} 应归一为 'rje'"
        )

    # -- P2: AJE 组与 RJE 组结果必不相等 --

    def test_aje_and_rje_groups_differ(self):
        """P2 双向：AJE 族的归一值与 RJE 族的归一值必不相同。"""
        from app.services.adjustment_amount_source import normalize_adj_type

        aje_results = {normalize_adj_type(r) for r in ["aje_net", "AJE", "审计调整"]}
        rje_results = {normalize_adj_type(r) for r in ["rje_net", "RJE", "重分类"]}

        # 族内应一致
        assert len(aje_results) == 1, f"AJE 族内归一不一致: {aje_results}"
        assert len(rje_results) == 1, f"RJE 族内归一不一致: {rje_results}"

        # 族间应不同
        assert aje_results != rje_results, (
            f"AJE 族 {aje_results} 不应等于 RJE 族 {rje_results}，"
            "否则 SQL 查询无法区分 aje/rje"
        )

    # -- P3: 非法入参 raise ValueError，不静默省略过滤 --

    @pytest.mark.parametrize("bad_input", [
        "类型",          # 占位符（现算 1 处）
        "INVALID",
        "adjustment",
        "audit",
        "net",
        "",              # 空字符串
        "  ",            # 纯空格
        "aje_rje",       # 混合
        "123",
    ])
    def test_invalid_input_raises_value_error(self, bad_input: str):
        """需求 2.3 + P3：不可归一 → raise ValueError，禁退化为不加过滤。"""
        from app.services.adjustment_amount_source import normalize_adj_type

        with pytest.raises(ValueError):
            normalize_adj_type(bad_input)

    # -- P3: 附加边界 --

    def test_none_like_input_raises(self):
        """P3 边界：None 传入不应被静默处理。"""
        from app.services.adjustment_amount_source import normalize_adj_type

        # normalize_adj_type 签名接收 str，传 None 应在 strip() 时或之前失败
        with pytest.raises((ValueError, TypeError, AttributeError)):
            normalize_adj_type(None)  # type: ignore[arg-type]

    # -- P2 + P3: 归一表常量与白名单一致性 --

    def test_valid_literals_whitelist_consistency(self):
        """VALID_ADJ_TYPE_LITERALS 白名单应与归一表 key 集合完全一致。"""
        from app.services.adjustment_amount_source import (
            VALID_ADJ_TYPE_LITERALS,
            _ADJ_TYPE_NORMALIZE,
        )

        expected_keys = frozenset(_ADJ_TYPE_NORMALIZE.keys())
        assert VALID_ADJ_TYPE_LITERALS == expected_keys, (
            f"白名单 {VALID_ADJ_TYPE_LITERALS} != 归一表 keys {expected_keys}"
        )

    # -- P2: 归一结果只能是 "aje" 或 "rje"，无第三种 --

    def test_normalize_output_domain(self):
        """归一函数的值域严格为 {"aje", "rje"}。"""
        from app.services.adjustment_amount_source import (
            _ADJ_TYPE_NORMALIZE,
            normalize_adj_type,
        )

        all_outputs = {normalize_adj_type(k) for k in _ADJ_TYPE_NORMALIZE}
        assert all_outputs == {"aje", "rje"}, (
            f"归一值域应为 {{'aje', 'rje'}}，得到 {all_outputs}"
        )

    # -- P2: 大小写不敏感 --

    def test_case_insensitive(self):
        """归一匹配大小写不敏感。"""
        from app.services.adjustment_amount_source import normalize_adj_type

        assert normalize_adj_type("AJE_NET") == "aje"
        assert normalize_adj_type("Aje_Net") == "aje"
        assert normalize_adj_type("rJe_NeT") == "rje"
        assert normalize_adj_type("RJE") == "rje"

    # -- P2: 前后空格容忍 --

    def test_whitespace_tolerance(self):
        """归一函数应容忍首尾空格。"""
        from app.services.adjustment_amount_source import normalize_adj_type

        assert normalize_adj_type(" aje_net ") == "aje"
        assert normalize_adj_type("\trje_net\n") == "rje"
        assert normalize_adj_type("  AJE  ") == "aje"
