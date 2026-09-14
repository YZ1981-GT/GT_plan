"""N5 所得税费用四表取数守卫（Property 1 / 2 / 3 / 8）。

spec: `.kiro/specs/n345-four-table-extraction-alignment/`

为什么必须有这个文件
--------------------
`_n5_income_tax_expense.py` 曾有两处 `get_active_filter(ctx.project_id)` 单参调用，
而真实签名是 `async def get_active_filter(db, table, project_id, year, *, ...)` →
**调用即 TypeError**，被 `except Exception` 捕获后只留一条 warning，
于是 `trial_balance` 恒全 0、`adjudication_prefill` 恒 `None`。

而既有 `test_n5_integration.py` 的 28 例全绿 —— 因为它们只测导入可用性、
`RENDERER_DISPATCH` 指向、`N5_SHEETS` 完整性、`_parse_num` 单测，
**从不真实调用取数函数**。这类缺陷只有真实签名调用的测试能拦。

因此本文件的核心断言是：**用真实签名 + 真实 await 调用被测函数，并断言返回值非零**。
"""

from __future__ import annotations

import asyncio
import inspect
import re
import types
from unittest.mock import AsyncMock

import pytest

from app.routers.wp_render_strategies import _n5_income_tax_expense as n5


def _run(coro):
    return asyncio.run(coro)


class _Result:
    def __init__(self, rows=(), one=None):
        self._rows = list(rows)
        self._one = one

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._one


def _tb_row(code: str, unadjusted: float, audited: float | None = None):
    """trial_balance 行（平台权威的损益类本期发生额来源）。"""
    return types.SimpleNamespace(
        standard_account_code=code,
        unadjusted_amount=unadjusted,
        audited_amount=audited if audited is not None else unadjusted,
    )


def _bal_row(code: str, debit: float):
    """tb_balance 行（借方发生额兜底来源）。"""
    return types.SimpleNamespace(account_code=code, debit_amount=debit)


def _balance_row(code: str, name: str, debit: float, credit: float):
    return types.SimpleNamespace(
        account_code=code, account_name=name, debit_amount=debit, credit_amount=credit
    )


def _seq_ctx(results: list[_Result]):
    """按调用顺序返回不同结果（`_fetch_period_amount` 先查 trial_balance 再查 tb_balance）。"""
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=list(results))
    return types.SimpleNamespace(db=db, project_id="p1", year=2025, wp_id="w1")


def _ctx(result: _Result | None = None, *, raise_on_execute: bool = False):
    db = AsyncMock()
    if raise_on_execute:
        db.execute = AsyncMock(side_effect=RuntimeError("boom"))
    else:
        db.execute = AsyncMock(return_value=result or _Result())
    return types.SimpleNamespace(db=db, project_id="p1", year=2025, wp_id="w1")


# ─── Property 1: `get_active_filter` 调用签名正确（源码级 + 运行级双拦）──────


def _strip_comments(src: str) -> str:
    """去掉行注释与 docstring。

    🔴 必需：本模块的**修复说明注释里原样引用了错误形态**
    （`get_active_filter(ctx.project_id)`），不剥注释会被数成真实调用 → 守卫恒红。
    同理生产代码里解释「为什么不能这么写」的注释也会误伤。
    """
    # 先去三引号块（docstring）
    src = re.sub(r'"""[\s\S]*?"""', "", src)
    src = re.sub(r"'''[\s\S]*?'''", "", src)
    # 再去行注释（本仓库无 '#' 出现在字符串字面量中的用法）
    return re.sub(r"#[^\n]*", "", src)


def test_strip_comments_self_check():
    """反向自检：证明原始源码确实含被禁字样，且剥注释后消失 —— 否则上面两条恒绿。"""
    raw = inspect.getsource(n5)
    assert "get_active_filter(ctx.project_id)" in raw, (
        "修复说明注释被删了？请保留反例说明，否则本守卫失去校准基准"
    )
    assert "get_active_filter(ctx.project_id)" not in _strip_comments(raw)


def test_no_single_arg_get_active_filter_call():
    """源码级：禁止 `get_active_filter(<单个实参>)` 形态。

    这是 P0 缺陷的**字面形态**，钉死它防回归。
    """
    src = _strip_comments(inspect.getsource(n5))
    # 匹配 get_active_filter( ... ) 中不含逗号的调用（单实参）
    bad = [m.group(0) for m in re.finditer(r"get_active_filter\(\s*[^(),]*\s*\)", src)]
    assert bad == [], f"发现单参 get_active_filter 调用（真实签名需 4 参）：{bad}"


def test_all_get_active_filter_calls_are_awaited():
    """源码级：`get_active_filter` 是 async 函数，未 await 会返回 coroutine 而非谓词。"""
    src = _strip_comments(inspect.getsource(n5))
    for m in re.finditer(r"get_active_filter\(", src):
        pos = m.start()
        line_start = src.rfind("\n", 0, pos) + 1
        line_end = src.find("\n", pos)
        line = src[line_start : line_end if line_end != -1 else len(src)]
        if "import" in line:
            continue
        assert "await" in line, f"未 await 的 get_active_filter 调用：{line.strip()}"


def test_no_manual_project_id_filter():
    """`get_active_filter` 已含 project_id + year + is_deleted 过滤，手写会绕过统一入口。"""
    src = _strip_comments(inspect.getsource(n5))
    assert "project_id == str(" not in src, "不应手写 project_id 过滤（统一入口已含）"


def test_guard_self_check_signature_is_four_args():
    """反向自检：确认 `get_active_filter` 真实签名确实是 4 位参数。"""
    from app.services.dataset_query import get_active_filter

    params = list(inspect.signature(get_active_filter).parameters)
    assert params[:4] == ["db", "table", "project_id", "year"], params
    assert inspect.iscoroutinefunction(get_active_filter)


# ─── Property 2: 真实签名调用下取数返回非零（拦 P0）──────────────────────────


@pytest.fixture(autouse=True)
def _patch_active_filter(monkeypatch):
    """用真实签名（4 参 + await）的替身 —— 若生产代码仍单参调用，这里会 TypeError。"""

    async def _fake(db, table, project_id, year, **kw):  # noqa: ANN001
        return True

    monkeypatch.setattr(n5, "get_active_filter", _fake)


def test_fetch_tb_data_prefers_trial_balance():
    """平台权威口径：`trial_balance` 与报表 `TB('6801','本期发生额')` 同源。"""
    ctx = _seq_ctx([_Result(rows=[_tb_row("6801", 21_151_383.26)])])
    out = _run(n5._fetch_tb_data(ctx))
    assert out["period_amount"] == 21_151_383.26, "P0 回归：取数不应恒为 0"
    assert out["source"] == "trial_balance"
    assert out["direction"] == "debit"


def test_fetch_tb_data_trial_balance_leaf_only():
    """trial_balance 里同时有父级与子科目时只取叶子，防双算。"""
    ctx = _seq_ctx(
        [
            _Result(
                rows=[
                    _tb_row("6801", 21_151_383.26),
                    _tb_row("6801.01", 24_891_157.62),
                    _tb_row("6801.02", -3_739_774.36),
                ]
            )
        ]
    )
    out = _run(n5._fetch_tb_data(ctx))
    assert out["period_amount"] == 21_151_383.26, "叶子之和，不含父级"


def test_fetch_tb_data_falls_back_to_tb_balance_debit():
    """trial_balance 未 recalc → 用 tb_balance 的**借方发生额**兜底。"""
    ctx = _seq_ctx(
        [
            _Result(rows=[]),                                  # trial_balance 空
            _Result(rows=[_bal_row("6801", 11_258_989.55)]),    # tb_balance 科目级
        ]
    )
    out = _run(n5._fetch_tb_data(ctx))
    assert out["period_amount"] == 11_258_989.55
    assert out["source"] == "tb_balance"


def test_fetch_tb_data_tb_balance_leaf_aggregation():
    ctx = _seq_ctx(
        [
            _Result(rows=[]),
            _Result(rows=[_bal_row("6801.01", 24_891_157.62), _bal_row("6801.02", -3_739_774.36)]),
        ]
    )
    out = _run(n5._fetch_tb_data(ctx))
    assert out["period_amount"] == 21_151_383.26, "负数借方保留符号（递延性质为贷）"


def test_fetch_tb_data_honours_resolved_codes():
    ctx = _seq_ctx([_Result(rows=[_tb_row("6801", 10.0)])])
    out = _run(n5._fetch_tb_data(ctx, ["6801", "6802"]))
    assert out["account_codes"] == ["6801", "6802"]


def test_fetch_tb_data_blank_codes_fall_back():
    ctx = _seq_ctx([_Result(rows=[_tb_row("6801", 5.0)])])
    out = _run(n5._fetch_tb_data(ctx, ["", "  "]))
    assert out["account_codes"] == ["6801"]


def test_no_ledger_debit_minus_credit_algorithm():
    """🔴 禁止对损益类 sum `tb_ledger` 的「Σ借 − Σ贷」。

    活体实证（项目 a7fc75e5 / 6801.01）：凭证「计提当期所得税」借 110,445.40，
    凭证「结转损益」贷 110,445.40 → 全年序时账借贷两侧恒相等 → 该差**结构性恒为 0**。
    实测 9 个项目的 6403 / 6801 全部如此。
    """
    src = _strip_comments(inspect.getsource(n5))
    assert "TbLedger.debit_amount" not in src, (
        "不得 sum tb_ledger 借方（含结转损益，借−贷恒为 0）；"
        "损益类本期发生额应取 trial_balance，兜底取 tb_balance.debit_amount"
    )
    assert "debit - credit" not in src.replace(" ", "").replace("debit-credit", "debit - credit")


def test_fetch_tb_data_query_error_fails_open():
    out = _run(n5._fetch_tb_data(_ctx(raise_on_execute=True)))
    assert out["period_amount"] == 0


def test_adjudication_prefill_splits_current_and_deferred():
    """活体叶子 `6801.01 当期所得税费用` / `6801.02 递延所得税费用` 语义清晰。"""
    rows = [
        _balance_row("6801", "所得税费用", 1_000_000.0, 0.0),
        _balance_row("6801.01", "所得税费用_当期所得税费用", 900_000.0, 0.0),
        _balance_row("6801.02", "所得税费用_递延所得税费用", 100_000.0, 0.0),
    ]
    out = _run(n5._build_adjudication_prefill(_ctx(_Result(rows=rows))))
    assert out is not None, "P0 回归：有子科目时预填不应为 None"
    assert out["current"]["periodAmount"] == 900_000.0
    assert out["deferred"]["periodAmount"] == 100_000.0
    assert out["total_period"] == 1_000_000.0


def test_adjudication_prefill_classifies_by_name_when_code_differs():
    """编码非 .02 但名称含「递延」→ 仍归递延（双判据）。"""
    rows = [
        _balance_row("6801.11", "递延所得税费用调整", 50_000.0, 0.0),
        _balance_row("6801.12", "当期税费", 20_000.0, 0.0),
    ]
    out = _run(n5._build_adjudication_prefill(_ctx(_Result(rows=rows))))
    assert out["deferred"]["periodAmount"] == 50_000.0
    assert out["current"]["periodAmount"] == 20_000.0


def test_adjudication_prefill_leaf_only_no_double_count():
    """中间级不得与其叶子同时计入（Property 4）。"""
    rows = [
        _balance_row("6801.01", "当期所得税费用", 900_000.0, 0.0),        # 中间级
        _balance_row("6801.01.01", "当期-境内", 600_000.0, 0.0),          # 叶子
        _balance_row("6801.01.02", "当期-境外", 300_000.0, 0.0),          # 叶子
    ]
    out = _run(n5._build_adjudication_prefill(_ctx(_Result(rows=rows))))
    assert out["current"]["periodAmount"] == 900_000.0, "叶子之和，不含中间级"


def test_adjudication_prefill_parent_only_falls_back_to_current():
    """只有父级 6801（无子科目）→ 总额落「当期」行（保留既有合理回退）。"""
    rows = [_balance_row("6801", "所得税费用", 777_000.0, 0.0)]
    out = _run(n5._build_adjudication_prefill(_ctx(_Result(rows=rows))))
    assert out["current"]["periodAmount"] == 777_000.0
    assert out["deferred"]["periodAmount"] == 0


def test_adjudication_prefill_no_rows_returns_none():
    out = _run(n5._build_adjudication_prefill(_ctx(_Result(rows=[]))))
    assert out is None


def test_adjudication_prefill_query_error_fails_open():
    out = _run(n5._build_adjudication_prefill(_ctx(raise_on_execute=True)))
    assert out is None


def test_prefill_ignores_credit_side_closing_entry():
    """贷方是年末「结转损益」，不参与本期发生额；只取借方（负借方保留符号）。

    活体实证：`6801.01` dr=cr=24,891,157.62 → 若做借−贷则该行为 0，
    而 trial_balance 权威值是 24,891,157.62。
    """
    rows = [_balance_row("6801.01", "当期所得税费用", 24_891_157.62, 24_891_157.62)]
    out = _run(n5._build_adjudication_prefill(_ctx(_Result(rows=rows))))
    assert out["current"]["periodAmount"] == 24_891_157.62


def test_prefill_negative_debit_preserved_for_deferred():
    """`6801.02 递延所得税费用` 活体为负借方 −3,739,774.36（贷方性质），符号须保留。"""
    rows = [
        _balance_row("6801", "所得税费用", 21_151_383.26, 21_151_383.26),
        _balance_row("6801.01", "当期所得税费用", 24_891_157.62, 24_891_157.62),
        _balance_row("6801.02", "递延所得税费用", -3_739_774.36, -3_739_774.36),
    ]
    out = _run(n5._build_adjudication_prefill(_ctx(_Result(rows=rows))))
    assert out["current"]["periodAmount"] == 24_891_157.62
    assert out["deferred"]["periodAmount"] == -3_739_774.36
    # 逐分勾稽：叶子之和 == 父级 == trial_balance 权威值
    assert round(
        out["current"]["periodAmount"] + out["deferred"]["periodAmount"], 2
    ) == 21_151_383.26
    assert out["total_period"] == 21_151_383.26


# ─── Property 3: 映射解析 fail-open ─────────────────────────────────────────


def test_row_code_is_db_verified():
    """DB 实证：`IS-023 减：所得税费用 = TB('6801','本期发生额')`（4 准则一致）。"""
    assert n5._N5_ROW_CODE == "IS-023"


def test_resolve_uses_report_config(monkeypatch):
    monkeypatch.setattr(
        n5, "resolve_report_line_account_codes", AsyncMock(return_value=["6801", "6811"])
    )
    assert _run(n5._resolve_account_codes(_ctx())) == ["6801", "6811"]


def test_resolve_falls_back_on_exception(monkeypatch):
    monkeypatch.setattr(
        n5,
        "resolve_report_line_account_codes",
        AsyncMock(side_effect=RuntimeError("db down")),
    )
    assert _run(n5._resolve_account_codes(_ctx())) == ["6801"]


def test_resolve_falls_back_on_empty(monkeypatch):
    monkeypatch.setattr(
        n5, "resolve_report_line_account_codes", AsyncMock(return_value=["", " "])
    )
    assert _run(n5._resolve_account_codes(_ctx())) == ["6801"]


# ─── Property 8: 损益类恒取发生额 ───────────────────────────────────────────


def test_income_statement_basis_is_period_not_balance():
    """源码不得出现按期末余额取所得税费用的迹象；输出 basis 标注为 period。"""
    src = inspect.getsource(n5)
    assert "closing_balance" not in src, "损益类不应读 closing_balance（应取发生额）"
    assert '"basis": "period"' in src, "tb_source_codes 应标注 period 口径"
