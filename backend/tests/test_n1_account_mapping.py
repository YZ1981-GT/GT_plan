"""N1 科目映射与叶子聚合守卫（spec n1-four-table-extraction-and-disclosure-alignment）。

正确性属性（design.md §Correctness Properties）：
- Property 1  `_resolve_account_codes` 恒返回非空科目集（fail-open）
- Property 2  叶子聚合不双算（科目级优先 → 无则叶子）
- Property 3  负债槽分类全覆盖且互斥（「投资性房地产」优先于泛化「公允价值」）

🔴 报表行编码 `BS-036` / `BS-067` 来自 `report_config` DB 只读实证（四套准则一致），
不是从 seed JSON 抄的 —— seed 里 `BS-049` 实为应交税费、`BS-018` 实为流动资产合计/存货。
"""

from __future__ import annotations

import asyncio
import types
from unittest.mock import AsyncMock

import pytest

from app.routers.wp_render_strategies import _n1_deferred_tax_assets as n1


def _run(coro):
    return asyncio.run(coro)


def _row(code: str, name: str = "", opening: float = 0.0, closing: float = 0.0):
    return types.SimpleNamespace(
        account_code=code,
        account_name=name,
        opening_balance=opening,
        closing_balance=closing,
        begin_balance=opening,
        end_balance=closing,
        debit_amount=0.0,
        credit_amount=0.0,
    )


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


def _ctx(rows=(), *, raise_on_execute: bool = False):
    db = AsyncMock()
    if raise_on_execute:
        db.execute = AsyncMock(side_effect=RuntimeError("boom"))
    else:
        db.execute = AsyncMock(return_value=_Result(list(rows)))
    return types.SimpleNamespace(db=db, project_id="p1", year=2025)


@pytest.fixture(autouse=True)
def _patch_active_filter(monkeypatch):
    monkeypatch.setattr(n1, "get_active_filter", AsyncMock(return_value=True))


# ─── 报表行编码常量（防再次退回错编码）─────────────────────────────────────────


def test_report_row_codes_are_db_verified_values():
    """DB 实证值：BS-036 递延所得税资产 / BS-067 递延所得税负债。"""
    assert n1._ASSET_ROW_CODE == "BS-036"
    assert n1._LIABILITY_ROW_CODE == "BS-067"
    # 反向断言：曾经用错的两个编码不得出现在本模块
    import inspect

    src = inspect.getsource(n1)
    for bad in ("BS-049", "BS-018"):
        # 只允许出现在解释性注释里，不得作为常量赋值
        assert f'= "{bad}"' not in src, f"{bad} 不得作为取数报表行编码"


# ─── Property 1: 映射解析 fail-open ──────────────────────────────────────────


def test_resolve_uses_report_config_result(monkeypatch):
    monkeypatch.setattr(
        n1, "resolve_report_line_account_codes", AsyncMock(return_value=["1811", "1812"])
    )
    out = _run(n1._resolve_account_codes(_ctx(), "BS-036", ["1811"]))
    assert out == ["1811", "1812"]


def test_resolve_falls_back_on_exception(monkeypatch):
    monkeypatch.setattr(
        n1,
        "resolve_report_line_account_codes",
        AsyncMock(side_effect=RuntimeError("db down")),
    )
    out = _run(n1._resolve_account_codes(_ctx(), "BS-036", ["1811"]))
    assert out == ["1811"]


def test_resolve_falls_back_on_empty_or_blank(monkeypatch):
    for ret in ([], ["", "  "], None):
        monkeypatch.setattr(
            n1, "resolve_report_line_account_codes", AsyncMock(return_value=ret or [])
        )
        out = _run(n1._resolve_account_codes(_ctx(), "BS-067", ["2901"]))
        assert out == ["2901"], f"入参 {ret!r} 应回退 fallback"


# ─── Property 2: 叶子聚合不双算 ──────────────────────────────────────────────


def test_leaf_rows_excludes_parent_dotted():
    rows = [_row("1811"), _row("1811.01"), _row("1811.02")]
    kept = {r.account_code for r in n1._leaf_rows(rows)}
    assert kept == {"1811.01", "1811.02"}


def test_leaf_rows_excludes_parent_flat():
    """平铺层级（无点）同样要正确判定 —— 这是不带点 startswith 的存在理由。"""
    rows = [_row("2901"), _row("290101"), _row("290102")]
    kept = {r.account_code for r in n1._leaf_rows(rows)}
    assert kept == {"290101", "290102"}


def test_leaf_rows_excludes_intermediate_level():
    rows = [_row("1811.02"), _row("1811.02.01"), _row("1811.02.02")]
    kept = {r.account_code for r in n1._leaf_rows(rows)}
    assert kept == {"1811.02.01", "1811.02.02"}


def test_fetch_tb_prefers_exact_account_row():
    """科目级精确行存在时只用它，不与子科目双算。"""
    rows = [
        _row("1811", opening=100.0, closing=200.0),
        _row("1811.01", opening=60.0, closing=120.0),
        _row("1811.02", opening=40.0, closing=80.0),
    ]
    out = _run(
        n1._fetch_tb_for_codes(
            _ctx(rows), ["1811"], account_name="递延所得税资产", direction="debit"
        )
    )
    assert out["begin_balance"] == 100.0
    assert out["end_balance"] == 200.0


def test_fetch_tb_falls_back_to_leaf_aggregation():
    rows = [
        _row("1811.01", opening=60.0, closing=120.0),
        _row("1811.02", opening=40.0, closing=80.0),
    ]
    out = _run(
        n1._fetch_tb_for_codes(
            _ctx(rows), ["1811"], account_name="递延所得税资产", direction="debit"
        )
    )
    assert out["begin_balance"] == 100.0
    assert out["end_balance"] == 200.0


def test_fetch_tb_absolute_normalizes_credit_sign():
    """负债类两种符号约定并存（活体实测）→ absolute=True 统一归正。"""
    rows = [_row("2901", opening=-528013.88, closing=-233512.19)]
    out = _run(
        n1._fetch_tb_for_codes(
            _ctx(rows),
            ["2901"],
            account_name="递延所得税负债",
            direction="credit",
            absolute=True,
        )
    )
    assert out["begin_balance"] == 528013.88
    assert out["end_balance"] == 233512.19


def test_fetch_tb_empty_codes_returns_zero_shape():
    out = _run(
        n1._fetch_tb_for_codes(_ctx(), [], account_name="x", direction="debit")
    )
    assert out["end_balance"] == 0
    assert out["account_codes"] == []


def test_fetch_tb_query_error_fails_open():
    out = _run(
        n1._fetch_tb_for_codes(
            _ctx(raise_on_execute=True),
            ["1811"],
            account_name="递延所得税资产",
            direction="debit",
        )
    )
    assert out["end_balance"] == 0


# ─── Property 3: 负债槽分类 ──────────────────────────────────────────────────


def test_liability_classify_all_slots():
    c = n1._classify_n1_liability_subaccount
    assert c("递延所得税负债_固定资产加速折旧") == "depreciation"
    assert c("购入摊销年限大于税法规定的资产") == "depreciation"
    assert c("递延所得税负债_公允价值变动") == "afs_fv"
    assert c("可供出售金融资产公允价值变动") == "afs_fv"
    assert c("投资性房地产公允价值变动") == "investment_property_fv"
    assert c("递延所得税负债_经营租赁相关") == "lease"
    assert c("使用权资产") == "lease"
    assert c("租赁形成") == "lease"
    assert c("其他说不清的") == "other"
    assert c("") == "other"
    assert c(None) == "other"


def test_liability_classify_investment_property_wins_over_fv():
    """「投资性房地产公允价值变动」含「公允价值」，但必须归投资性房地产槽。"""
    assert n1._classify_n1_liability_subaccount("投资性房地产公允价值变动") != "afs_fv"


def test_liability_classify_is_total_function():
    """全覆盖：任意输入恒落在已声明槽集内。"""
    samples = [
        "", None, "x", "公允价值", "投资性房地产", "租赁", "加速折旧",
        "使用权资产减值", "折旧年限差异", "递延所得税负债", "！@#￥",
    ]
    for s in samples:
        assert n1._classify_n1_liability_subaccount(s) in n1._N1_LIABILITY_SLOTS


def test_liability_slots_order_matches_source_template():
    """槽顺序 = 源模板 R23:R27 行序（前端按此顺序渲染负债段）。"""
    assert n1._N1_LIABILITY_SLOTS == [
        "depreciation",
        "afs_fv",
        "investment_property_fv",
        "lease",
        "other",
    ]


# ─── 负债段预填 ──────────────────────────────────────────────────────────────


def test_liability_prefill_aggregates_by_slot():
    rows = [
        _row("2901.01", "递延所得税负债_公允价值变动", -1000.0, -1200.0),
        _row("2901.02", "递延所得税负债_固定资产加速折旧", -2000.0, -2500.0),
        _row("2901.03", "递延所得税负债_经营租赁相关", -528013.88, -233512.19),
    ]
    out = _run(n1._build_liability_prefill(_ctx(rows)))
    assert out["afs_fv"] == {"opening": 1000.0, "closing": 1200.0}
    assert out["depreciation"] == {"opening": 2000.0, "closing": 2500.0}
    assert out["lease"] == {"opening": 528013.88, "closing": 233512.19}


def test_liability_prefill_skips_all_zero_slot():
    rows = [
        _row("2901.01", "公允价值变动", 0.0, 0.0),
        _row("2901.02", "固定资产加速折旧", 0.0, 500.0),
    ]
    out = _run(n1._build_liability_prefill(_ctx(rows)))
    assert "afs_fv" not in out
    assert out["depreciation"] == {"opening": 0.0, "closing": 500.0}


def test_liability_prefill_parent_only_returns_empty():
    """只有父级 2901（无子科目）→ 无法按槽拆分，返回 {} 而非虚构分类。"""
    rows = [_row("2901", "递延所得税负债", -100.0, -200.0)]
    out = _run(n1._build_liability_prefill(_ctx(rows)))
    assert out == {}


def test_liability_prefill_query_error_fails_open():
    out = _run(n1._build_liability_prefill(_ctx(raise_on_execute=True)))
    assert out == {}


def test_liability_prefill_leaf_only():
    rows = [
        _row("2901.03", "经营租赁相关", -1000.0, -1000.0),        # 中间级
        _row("2901.03.01", "经营租赁-房屋", -600.0, -600.0),      # 叶子
        _row("2901.03.02", "经营租赁-设备", -400.0, -400.0),      # 叶子
    ]
    out = _run(n1._build_liability_prefill(_ctx(rows)))
    assert out["lease"] == {"opening": 1000.0, "closing": 1000.0}


# ─── 资产段预填：父级排除（本次泛化后的新行为）───────────────────────────────


def test_asset_prefill_excludes_root_account_row():
    """科目级父行是总额，不参与分类拆分（否则与子科目双算）。"""
    rows = [
        _row("1811", "递延所得税资产", 8048699.80, 8048699.80),
        _row("1811.02", "递延所得税资产_资产减值准备", 3983376.55, 3983376.55),
        _row("1811.04", "递延所得税资产_可抵扣亏损", 1172298.25, 1172298.25),
    ]
    out = _run(n1._build_adjudication_prefill(_ctx(rows)))
    total = sum(v["closing"] for v in out.values())
    assert total == pytest.approx(3983376.55 + 1172298.25)


def test_asset_prefill_supports_flat_chart_of_accounts():
    """平铺层级（181102）也要能归类 —— 原实现只 like '1811.%' 时静默返回 {}。"""
    rows = [
        _row("1811", "递延所得税资产", 100.0, 100.0),
        _row("181102", "递延所得税资产_资产减值准备", 60.0, 70.0),
        _row("181104", "递延所得税资产_可抵扣亏损", 40.0, 30.0),
    ]
    out = _run(n1._build_adjudication_prefill(_ctx(rows)))
    assert out["资产减值准备"] == {"opening": 60.0, "closing": 70.0}
    assert out["可抵扣亏损"] == {"opening": 40.0, "closing": 30.0}


# ─── 反向自检：断言比对逻辑本身非空转 ────────────────────────────────────────


def test_guard_self_check_slot_sets_differ_between_asset_and_liability():
    """资产 7 类与负债 5 槽必须是两套键（若被合并成一套，本守卫立即失效）。"""
    assert set(n1._N1_ADJUDICATION_CATEGORIES) & set(n1._N1_LIABILITY_SLOTS) == set()
    assert len(n1._N1_ADJUDICATION_CATEGORIES) == 7
    assert len(n1._N1_LIABILITY_SLOTS) == 5


# ─── render 输出契约（新增键 + 既有键零回归）──────────────────────────────────


def _render_ctx():
    """render 内部用裸 SQL 读 checklist_responses / projects，其余走已 patch 的辅助函数。"""

    class _Row:
        item_id = "N1-1-total-audited"
        conclusion = None
        remark = "123.45"

    class _Proj:
        client_name = "测试公司"
        audit_year = 2025
        business_category = "manufacturing"

    class _Res:
        def __init__(self, mode):
            self._mode = mode

        def fetchall(self):
            return [_Row()] if self._mode == "resp" else []

        def fetchone(self):
            return _Proj() if self._mode == "proj" else None

    async def _execute(stmt, params=None):
        text = str(stmt)
        if "checklist_responses" in text:
            return _Res("resp")
        if "projects" in text:
            return _Res("proj")
        return _Res("none")

    db = AsyncMock()
    db.execute = _execute
    return types.SimpleNamespace(
        db=db,
        project_id="p1",
        year=2025,
        wp_id="w1",
        business_category="manufacturing",
        classification=types.SimpleNamespace(sheet_name="递延所得税资产审定表N1-1"),
    )


def test_render_emits_new_keys_and_keeps_legacy(monkeypatch):
    monkeypatch.setattr(
        n1, "resolve_report_line_account_codes", AsyncMock(side_effect=[["1811"], ["2901"]])
    )
    monkeypatch.setattr(
        n1,
        "_fetch_tb_for_codes",
        AsyncMock(side_effect=[{"end_balance": 8048699.80}, {"end_balance": 233512.19}]),
    )
    monkeypatch.setattr(
        n1,
        "_build_adjudication_prefill",
        AsyncMock(return_value={"资产减值准备": {"opening": 1.0, "closing": 2.0}}),
    )
    monkeypatch.setattr(
        n1,
        "_build_liability_prefill",
        AsyncMock(return_value={"lease": {"opening": 3.0, "closing": 4.0}}),
    )

    out = _run(n1.render(_render_ctx()))

    # 新增键
    assert out["trial_balance_liability"] == {"end_balance": 233512.19}
    assert out["liability_prefill"] == {"lease": {"opening": 3.0, "closing": 4.0}}
    assert out["tb_source_codes"] == {
        "asset": {"row_code": "BS-036", "codes": ["1811"]},
        "liability": {"row_code": "BS-067", "codes": ["2901"]},
    }
    # 既有键零回归（前端 useN1FormData / N1TabAdjudication 已在消费）
    for legacy in (
        "account_code",
        "sheet_name",
        "project_context",
        "responses_snapshot",
        "adjudicated_amount",
        "trial_balance",
        "adjudication_prefill",
        "formula_direction",
        "n1_metadata",
        "sheets",
        "component_type",
    ):
        assert legacy in out, f"既有键 {legacy} 丢失（前端会静默取不到数）"
    assert out["adjudicated_amount"] == 123.45
    assert out["trial_balance"] == {"end_balance": 8048699.80}


def test_render_liability_fetch_uses_absolute_normalization(monkeypatch):
    """负债侧必须以 absolute=True 调用，否则符号约定不一致时披露表出负数。"""
    monkeypatch.setattr(
        n1, "resolve_report_line_account_codes", AsyncMock(side_effect=[["1811"], ["2901"]])
    )
    calls: list[dict] = []

    async def _spy(ctx, codes, **kw):
        calls.append({"codes": codes, **kw})
        return {"end_balance": 0}

    monkeypatch.setattr(n1, "_fetch_tb_for_codes", _spy)
    monkeypatch.setattr(n1, "_build_adjudication_prefill", AsyncMock(return_value={}))
    monkeypatch.setattr(n1, "_build_liability_prefill", AsyncMock(return_value={}))

    _run(n1.render(_render_ctx()))

    assert len(calls) == 2
    assert calls[0]["direction"] == "debit" and not calls[0].get("absolute")
    assert calls[1]["direction"] == "credit" and calls[1]["absolute"] is True
