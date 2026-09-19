"""test_h0_book_amounts.py — H0-1 矩阵账面金额取数守卫.

spec: h0-confirmation-source-fidelity-and-linkage
  Requirements 3.2 / 3.3 / 3.4 / 3.8；Property 8 / Property 9

两条最关键的断言（都带反向自检）：
1. **不得按标准科目码硬查** —— H8 客户实际用 ``1651/1652``、H9 用 ``2651``，
   按标准码硬查这两品种在该项目取空。
2. **不得读 `project_context.tb_amount`** —— 实测 H1~H10 十个 render 策略该字段
   零命中，照抄 F0 口径必得 ``undefined``。
"""
from __future__ import annotations

import inspect
import json
import re
from pathlib import Path

import pytest

from app.services.four_table import h0_book_amounts as mod
from app.services.four_table.h0_book_amounts import (
    H0_CATEGORY_BY_NAME,
    H0_MATRIX_CATEGORY_SPECS,
    H0BookAmountResult,
    resolve_h0_book_amounts,
)
from app.services.four_table import leaf_aggregation as la
from app.services.four_table import semantic_account_resolver as sar

_REPO_ROOT = Path(__file__).resolve().parents[3]
_MODULE_SRC = Path(mod.__file__).read_text(encoding="utf-8")
_RENDER_DIR = _REPO_ROOT / "backend" / "app" / "routers" / "wp_render_strategies"
_WP_SYSTEM_MAP = _REPO_ROOT / "backend" / "data" / "wp_system_map.json"

H_CYCLE_CONFIRM_CATEGORIES = [
    "固定资产", "在建工程", "投资性房地产", "工程物资", "油气资产",
    "固定资产清理", "生产性生物资产", "使用权资产", "租赁负债",
]


def _strip_py_comments_and_docstrings(src: str) -> str:
    """去掉注释与三引号文档串 —— 本模块的注释里**故意**写了标准码作为反例说明，
    不 strip 会把说明文字数成真实查询前缀（守卫自伤）。"""
    src = re.sub(r'"""[\s\S]*?"""', "", src)
    src = re.sub(r"'''[\s\S]*?'''", "", src)
    return "\n".join(line.split("#", 1)[0] for line in src.split("\n"))


# ─── 品种映射齐备性 ──────────────────────────────────────────────────────────


def test_nine_categories_registered():
    assert [c.category for c in H0_MATRIX_CATEGORY_SPECS] == H_CYCLE_CONFIRM_CATEGORIES


def test_categories_match_wp_system_map():
    """品种名逐字取 `wp_system_map.json`，不得自拟简称（Requirement 1.6）."""
    data = json.loads(_WP_SYSTEM_MAP.read_text(encoding="utf-8"))
    cycle = next(c for c in data["business_cycles"] if c.get("name") == "固定资产循环")
    accounts = cycle["accounts"].split("/")
    assert accounts == H_CYCLE_CONFIRM_CATEGORIES + ["资产处置损益"]


@pytest.mark.parametrize("category", H_CYCLE_CONFIRM_CATEGORIES)
def test_slot_keys_exist_in_spec(category: str):
    """声明的 gross_slot / net_of_slots 必须真实存在于该循环的语义规格里.

    写错槽键不会报错，只会静默 `slots.get(...) -> None` 然后跳过扣减 →
    账面金额变成原值（虚增），是典型静默缺陷。
    """
    cat = H0_CATEGORY_BY_NAME[category]
    keys = {s.key for s in cat.spec.slots}
    assert cat.gross_slot in keys, f"{category} gross_slot={cat.gross_slot} 不在 {sorted(keys)}"
    missing = set(cat.net_of_slots) - keys
    assert not missing, f"{category} net_of_slots 缺 {sorted(missing)}"


def test_cross_check_slots_not_summed_into_category():
    """H2 的 `eng_mat` 与 H4 的 `cip` 是跨品种核对槽，不得并入本品种（防双算）."""
    cip = H0_CATEGORY_BY_NAME["在建工程"]
    assert "eng_mat" not in cip.net_of_slots and cip.gross_slot != "eng_mat"
    mat = H0_CATEGORY_BY_NAME["工程物资"]
    assert "cip" not in mat.net_of_slots and mat.gross_slot != "cip"


def test_every_category_has_formula_hint():
    for cat in H0_MATRIX_CATEGORY_SPECS:
        assert cat.formula_hint.strip(), f"{cat.category} 缺口径说明（溯源面板要展示）"


def test_source_wp_codes_are_h_cycles():
    for cat in H0_MATRIX_CATEGORY_SPECS:
        assert re.fullmatch(r"H[1-9]", cat.source_wp_code), cat.source_wp_code


# ─── Property 8: 不按标准科目码硬查 ─────────────────────────────────────────


_H_STANDARD_CODES = [
    "1601", "1602", "1603", "1604", "1605", "1606",
    "1621", "1622", "1631", "1632",
    "1641", "1642", "1643", "2601", "2602",
    "1521", "1525", "1526", "1527",
]


def test_module_has_no_hardcoded_standard_codes():
    """生产代码（去注释后）不得出现 H 类标准科目码字面量.

    标准码只允许出现在各 `h{n}_account_scope.py` 的 `fallback_standard_codes` 与
    注释/docstring 里。本模块只声明「品种 → 槽键」，一个码都不该写。
    """
    code = _strip_py_comments_and_docstrings(_MODULE_SRC)
    hits = [c for c in _H_STANDARD_CODES if c in code]
    assert not hits, f"h0_book_amounts.py 生产代码出现标准科目码字面量: {hits}"


def test_reverse_selfcheck_standard_codes_exist_in_docstring():
    """反向自检：标准码确实出现在本模块的注释/docstring 里（证明上一条不是空转）."""
    assert "1651" in _MODULE_SRC and "2651" in _MODULE_SRC, (
        "本模块 docstring 应记录 H8/H9 非标准码实证；若被删除，"
        "test_module_has_no_hardcoded_standard_codes 会退化为恒真"
    )
    stripped = _strip_py_comments_and_docstrings(_MODULE_SRC)
    assert "1651" not in stripped and "2651" not in stripped


# ─── Property 9: 未照抄 F0 的 tb_amount 口径 ────────────────────────────────


def test_module_does_not_read_project_context_tb_amount():
    code = _strip_py_comments_and_docstrings(_MODULE_SRC)
    assert "tb_amount" not in code, (
        "H 循环 render 策略不下发 project_context.tb_amount（实测 H1~H10 零命中），"
        "读它恒为 undefined —— 不得照抄 F0 的 F0_BOOK_AMOUNT_SOURCES 口径"
    )


def test_reverse_selfcheck_h_render_has_no_tb_amount():
    """反向自检（实证基线）：H1~H10 render 策略主文件里确实没有 `tb_amount`.

    若将来某个 H 循环补了该字段，本断言会红 —— 那时应重新评估是否可以改走
    F0 那种「读相邻循环 tb_amount」的更简路径。
    """
    checked = 0
    for n in range(1, 11):
        for path in _RENDER_DIR.glob(f"_h{n}_*.py"):
            src = path.read_text(encoding="utf-8")
            checked += 1
            assert "tb_amount" not in src, f"{path.name} 出现 tb_amount，需重新评估取数路径"
    assert checked >= 10, f"只扫到 {checked} 个 H render 文件，路径可能不对"


# ─── 共享件调用形态（防 G6 那种「await 同步纯函数」静默失效） ────────────────


def test_shared_helpers_are_sync_and_module_does_not_await_them():
    """`select_leaves`/`to_leaf_rows`/`aggregate_leaves` 是同步纯函数.

    G6 曾写 `await select_leaves(...)` → TypeError 被 except 吞成 warning →
    审定表 TB seed 恒空。
    """
    for fn in (la.select_leaves, la.to_leaf_rows, la.resolve_leaf_totals):
        assert not inspect.iscoroutinefunction(fn), f"{fn.__name__} 变成 async 了，需同步改调用点"
    code = _strip_py_comments_and_docstrings(_MODULE_SRC)
    for name in ("select_leaves", "to_leaf_rows", "resolve_leaf_totals", "aggregate_leaves"):
        assert f"await {name}(" not in code, f"不得 await 同步纯函数 {name}"


def test_resolver_is_async_and_awaited():
    assert inspect.iscoroutinefunction(sar.resolve_semantic_accounts)
    code = _strip_py_comments_and_docstrings(_MODULE_SRC)
    assert "await resolve_semantic_accounts(" in code


def test_uses_convention_aware_aggregation_with_absolute_true():
    """🔴 必须走 `resolve_leaf_totals`（符号约定自校验）而非裸 `aggregate_leaves`.

    2026-08-04 真实库实证：`c8621493` 的 `2651 租赁负债` 家族里
    `2651.01 租赁付款额 98,176.48(credit)` 与 `2651.02 未确认融资费用 3,956.64(debit)`
    方向相反 —— 裸 `aggregate_leaves` 原样求和得 **102,133.12**，而父额是
    **94,219.84**（把借方性质的 contra 子科目加成了正数）。
    `resolve_leaf_totals` 两种约定都算、取与父额勾稽成立的那一种。
    """
    code = _strip_py_comments_and_docstrings(_MODULE_SRC)
    calls = re.findall(r"resolve_leaf_totals\([^)]*\)", code)
    assert calls, "未找到 resolve_leaf_totals 调用"
    for c in calls:
        assert "absolute=True" in c, f"聚合未归一: {c}"
    # 裸 aggregate_leaves 不得复活（它忽略 closing_direction）
    assert "aggregate_leaves(" not in code
    # 🔴 不得先 select_leaves 再传入 —— 父行是符号约定的判定依据
    assert "resolve_leaf_totals(select_leaves(" not in code
    assert "select_leaves(to_leaf_rows(" not in code


# ─── Requirement 3.8: 无科目返 None 不返 0 ──────────────────────────────────


class _FakeSlot:
    def __init__(self, found: bool, codes=(), standard_codes=()):
        self.found = found
        self.codes = list(codes)
        self.standard_codes = list(standard_codes)
        self.resolved_from = "account_chart_client" if found else "none"


class _FakeAccounts:
    def __init__(self, slots: dict):
        self.slots = slots
        self.conflicts: list[str] = []
        self.chart_available = True
        self.row_code = None


@pytest.mark.asyncio
async def test_absent_slot_returns_none_not_zero(monkeypatch):
    """槽 found=False → amounts=None（「本项目无此科目」≠「余额为 0」）."""
    async def fake_resolve(ctx, spec):
        return _FakeAccounts({s.key: _FakeSlot(False) for s in spec.slots})

    monkeypatch.setattr(mod, "resolve_semantic_accounts", fake_resolve)

    amount, source = await mod._resolve_one(
        object(), H0_CATEGORY_BY_NAME["固定资产"], all_rows=[]
    )
    assert amount is None
    assert source["found"] is False
    assert source["absent_reason"]


@pytest.mark.asyncio
async def test_leaves_unavailable_returns_none(monkeypatch):
    """四表不可用（leaves=None）→ None 而不是 0."""
    async def fake_resolve(ctx, spec):
        return _FakeAccounts({s.key: _FakeSlot(True, ["1601"], ["1601"]) for s in spec.slots})

    monkeypatch.setattr(mod, "resolve_semantic_accounts", fake_resolve)
    amount, source = await mod._resolve_one(
        object(), H0_CATEGORY_BY_NAME["固定资产"], all_rows=None
    )
    assert amount is None
    assert source["absent_reason"] == "四表数据不可用"


@pytest.mark.asyncio
async def test_single_category_failure_is_isolated(monkeypatch):
    """单品种解析抛异常不影响其他品种（Error Handling）."""
    calls = {"n": 0}

    async def flaky_resolve(ctx, spec):
        calls["n"] += 1
        if spec.row_code == "BS-027":  # 投资性房地产
            raise RuntimeError("boom")
        return _FakeAccounts({s.key: _FakeSlot(False) for s in spec.slots})

    monkeypatch.setattr(mod, "resolve_semantic_accounts", flaky_resolve)

    async def fake_filter(*a, **k):
        raise RuntimeError("no db")

    monkeypatch.setattr(mod, "get_active_filter", fake_filter)

    res = await resolve_h0_book_amounts(_Ctx())
    assert isinstance(res, H0BookAmountResult)
    # 9 个品种全部有键（异常品种为 None），不因单点失败少键
    assert set(res.amounts) == set(H_CYCLE_CONFIRM_CATEGORIES)
    assert res.amounts["投资性房地产"] is None
    assert res.source_codes["投资性房地产"]["absent_reason"] == "解析失败"


@pytest.mark.asyncio
async def test_unknown_category_produces_no_key(monkeypatch):
    """未登记的品种**不产出键**（调用方渲染「-」），不得凭空返 0."""
    async def fake_resolve(ctx, spec):
        return _FakeAccounts({s.key: _FakeSlot(False) for s in spec.slots})

    monkeypatch.setattr(mod, "resolve_semantic_accounts", fake_resolve)

    async def fake_filter(*a, **k):
        raise RuntimeError("no db")

    monkeypatch.setattr(mod, "get_active_filter", fake_filter)

    res = await resolve_h0_book_amounts(_Ctx(), categories=["自定义品种X", "固定资产"])
    assert "自定义品种X" not in res.amounts
    assert "固定资产" in res.amounts


@pytest.mark.asyncio
async def test_empty_category_list_returns_empty(monkeypatch):
    res = await resolve_h0_book_amounts(_Ctx(), categories=["不存在"])
    assert res.amounts == {} and res.source_codes == {}


class _Ctx:
    db = None
    project_id = "00000000-0000-0000-0000-000000000000"
    year = 2025


# ─── 账面金额口径（原值 − 备抵） ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_book_amount_is_gross_minus_provisions(monkeypatch):
    async def fake_resolve(ctx, spec):
        return _FakeAccounts({
            "gross": _FakeSlot(True, ["1601"], ["1601"]),
            "accum_dep": _FakeSlot(True, ["1602"], ["1602"]),
            "impairment": _FakeSlot(True, ["1603"], ["1603"]),
        })

    monkeypatch.setattr(mod, "resolve_semantic_accounts", fake_resolve)

    agg_map = {("1601",): 1000.0, ("1602",): 300.0, ("1603",): 50.0}

    def fake_sum(all_rows, codes):
        return agg_map[tuple(codes)], {c: 0.0 for c in codes}

    monkeypatch.setattr(mod, "_sum_family", fake_sum)

    amount, source = await mod._resolve_one(object(), H0_CATEGORY_BY_NAME["固定资产"], all_rows=[])
    assert amount == 650.0
    assert source["gross"] == ["1601"]
    assert source["net_of"] == ["1602", "1603"]


@pytest.mark.asyncio
async def test_missing_provision_slot_does_not_break_book_amount(monkeypatch):
    """备抵槽 found=False → 只是不扣减，不让整个品种变 None."""
    async def fake_resolve(ctx, spec):
        return _FakeAccounts({
            "gross": _FakeSlot(True, ["1604"], ["1604"]),
            "impairment": _FakeSlot(False),
            "eng_mat": _FakeSlot(True, ["1605"], ["1605"]),
        })

    monkeypatch.setattr(mod, "resolve_semantic_accounts", fake_resolve)

    def fake_sum(all_rows, codes):
        assert tuple(codes) == ("1604",), f"不该聚合 {codes}（eng_mat 属工程物资品种）"
        return 777.0, {c: 0.0 for c in codes}

    monkeypatch.setattr(mod, "_sum_family", fake_sum)

    amount, source = await mod._resolve_one(object(), H0_CATEGORY_BY_NAME["在建工程"], all_rows=[])
    assert amount == 777.0
    assert source["net_of"] == []


# ─── 符号约定与 contra 子科目（2026-08-04 真实库实证修复） ─────────────────────


def _row(code, name, closing, direction):
    """构造一行 tb_balance 输入（`to_leaf_rows` 的入参形态）."""
    return {
        "account_code": code,
        "account_name": name,
        "opening_balance": 0,
        "closing_balance": closing,
        "debit_amount": 0,
        "credit_amount": 0,
        "closing_direction": direction,
    }


#: `c8621493 / 2025` 的 `2651 租赁负债` 家族实证形态（无符号存储 + 方向列定性质）
LEASE_FAMILY_ROWS = [
    _row("2651", "租赁负债", 94219.84, "credit"),
    _row("2651.01", "租赁负债_租赁付款额", 98176.48, "credit"),
    _row("2651.02", "租赁负债_未确认融资费用", 3956.64, "debit"),
    _row("2651.99", "租赁负债_一年内到期的租赁负债", 0, "credit"),
]


def test_sum_family_picks_convention_that_ties_to_parent():
    """族内叶子方向不一致时，取与父额勾稽成立的约定（94,219.84 而非 102,133.12）."""
    rows = la.to_leaf_rows(LEASE_FAMILY_ROWS)
    total, diffs = mod._sum_family(rows, ["2651"])
    assert round(total, 2) == 94219.84
    assert diffs["2651"] == 0.0, "叶子和与父额勾稽应成立"


def test_reverse_selfcheck_naive_sum_would_be_wrong():
    """反向自检：裸 `aggregate_leaves` 对同一份数据得 102,133.12（≠ 父额）→ 证明修复必要."""
    leaves = la.select_leaves(la.to_leaf_rows(LEASE_FAMILY_ROWS))
    naive = la.aggregate_leaves(leaves, ["2651"], absolute=True)["closing"]
    assert round(naive, 2) == 102133.12
    assert round(naive, 2) != 94219.84


@pytest.mark.asyncio
async def test_contra_subaccount_is_not_subtracted_twice(monkeypatch):
    """备抵槽若是原值科目族的**子科目**，父族聚合已按方向净掉 → 不得再减一次."""
    async def fake_resolve(ctx, spec):
        return _FakeAccounts({
            "gross": _FakeSlot(True, ["2651"], ["2601"]),
            "unearned_finance": _FakeSlot(True, ["2651.02"], ["2602"]),
        })

    monkeypatch.setattr(mod, "resolve_semantic_accounts", fake_resolve)

    rows = la.to_leaf_rows(LEASE_FAMILY_ROWS)
    amount, source = await mod._resolve_one(
        object(), H0_CATEGORY_BY_NAME["租赁负债"], all_rows=rows
    )
    assert amount == 94219.84, "子科目被双减了"
    assert source["net_of"] == []
    assert source["net_of_skipped"] == ["2651.02"]


@pytest.mark.asyncio
async def test_independent_contra_account_is_still_subtracted(monkeypatch):
    """备抵科目是**独立顶层科目**时照常扣减（只跳过族内子科目）."""
    async def fake_resolve(ctx, spec):
        return _FakeAccounts({
            "gross": _FakeSlot(True, ["2601"], ["2601"]),
            "unearned_finance": _FakeSlot(True, ["2602"], ["2602"]),
        })

    monkeypatch.setattr(mod, "resolve_semantic_accounts", fake_resolve)

    rows = la.to_leaf_rows([
        _row("2601", "租赁负债", 1000.0, "credit"),
        _row("2602", "未确认融资费用", 120.0, "debit"),
    ])
    amount, source = await mod._resolve_one(
        object(), H0_CATEGORY_BY_NAME["租赁负债"], all_rows=rows
    )
    assert amount == 880.0
    assert source["net_of"] == ["2602"]
    assert "net_of_skipped" not in source


@pytest.mark.asyncio
async def test_parent_check_diff_is_exposed(monkeypatch):
    """`parent_check` 必须下发（平台铁律：叶子和 == 父额 是审计证据不是调试信息）."""
    async def fake_resolve(ctx, spec):
        return _FakeAccounts({"gross": _FakeSlot(True, ["2651"], ["2601"])})

    monkeypatch.setattr(mod, "resolve_semantic_accounts", fake_resolve)
    rows = la.to_leaf_rows(LEASE_FAMILY_ROWS)
    _, source = await mod._resolve_one(
        object(), H0_CATEGORY_BY_NAME["租赁负债"], all_rows=rows
    )
    assert "parent_check" in source
    assert source["parent_check"]["2651"] == 0.0
