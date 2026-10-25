"""E1 binding：规则 → 目标展开 / 写入叠加层 / 取数严格性。

spec: chain-closure-phase2-formula-push-engine · 任务 7 / 8

纯计算的前后端同式由 `test_formula_push_e1_parity.py` 守卫；本文件守卫 binding 自己的决定：
- 只推四表带入的行（种子 id 命中已保存行），用户自加行 / 缺行 / 应计利息段 / 外币行都不推且给原因；
- composable 自动补的人民币默认行（全 0、无备注）金额视为空 ⇒ 首推可写；
- 多币种原币权威的本位币行推原币列并镜像本位币列；
- 试算表尚未生成 ⇒ 试算平衡表数跳过（不写 0）；
- 叠加层逐级生效：行写入后明细合计 / 审定合计读到新值；
- 四表取数失败上抛，不退化成空（否则会把真实金额刷成 0）。
"""
from __future__ import annotations

import asyncio
import json
from decimal import Decimal

import pytest

from app.services.formula_push.bindings import get_binding, supported_wp_codes
from app.services.formula_push.bindings import e1_calc
from app.services.formula_push.bindings.e1 import DERIVATIONS, E1Binding, E1Sources, load_e1_sources
from app.services.formula_push.rules import RULES_PATH, load_rules
from app.services.formula_push.sources import FormulaSources, TbAuditedSnapshot

from app.services.formula_push.bindings.k1 import DERIVATIONS as K1_DERIVATIONS

RULES = {r.rule_id: r for r in load_rules()}
B = E1Binding()


def _sources(**over) -> E1Sources:
    prefill = {
        "cash": [
            {"code": "1001.01", "currency": "CNY", "opening": 286.73, "increase": 90, "decrease": 0, "ending": 376.73},
            {"code": "1001.02", "currency": "USD", "opening": 10, "increase": 5, "decrease": 1, "ending": 14},
            {"code": "1001.03", "currency": "HKD", "opening": 1, "increase": 0, "decrease": 0, "ending": 1},
        ],
        "bank": [{"code": "1002.01", "currency": "", "opening": 100, "increase": 50, "decrease": 30, "ending": 120}],
        "other": [{"code": "1012.01", "currency": "", "opening": 7, "increase": 0, "decrease": 0, "ending": 7}],
        "finance_co": [], "digital": [],
    }
    tb = TbAuditedSnapshot(
        tb_data={"1001": {"期末余额": Decimal("376.73"), "年初余额": Decimal("286.73")},
                 "1002": {"期末余额": Decimal("120"), "年初余额": Decimal("100")},
                 "1012": {"期末余额": Decimal("7"), "年初余额": Decimal("7")}},
        available=True, company_codes=("001",),
    )
    base = dict(
        four_table_prefill=prefill,
        account_prefill={"accounts": {"bank": [], "other": [], "finance_co": [], "unassigned": []}},
        formula=FormulaSources(tb=tb, hall_adj={"1001": {"aje_net": Decimal("100"), "rje_net": Decimal("5")}}),
        template_type="listed",
    )
    base.update(over)
    return E1Sources(**base)


def test_registry_and_derivations_cover_rules():
    assert "E1" in supported_wp_codes() and "K1" in supported_wp_codes() and isinstance(get_binding("E1"), E1Binding)
    with pytest.raises(KeyError, match="尚未接入"):
        get_binding("Z9")
    names = {r.source.name for r in RULES.values() if r.source.kind == "derivation"}
    assert set(DERIVATIONS | K1_DERIVATIONS) <= names, "E1+K1 的全部 derivation 必须在规则中"


# ── 行目标 ────────────────────────────────────────────────────────────────


def _cash_rows(*rows) -> str:
    return json.dumps(list(rows), ensure_ascii=False)


def test_cash_rows_push_only_seeded_rows_and_report_missing():
    entries = {e1_calc.CASH_ROWS_KEY: _cash_rows(
        {"id": "fixed-rmb", "currency": "人民币", "opening": 200, "increase": 90, "decrease": 0, "fxRate": 1,
         "adjustment": 0, "note": "四表取数 1001.01"},
        {"id": "cash-ft-1001.02", "currency": "USD", "opening": 10, "increase": 5, "decrease": 1, "fxRate": 7.1},
        {"id": "cash-u1", "currency": "欧元", "opening": 3, "increase": 0, "decrease": 0, "fxRate": 7.9},
    )}
    targets, skips = B.workpaper_targets(RULES["E1.cash_rows.four_table"], entries, _sources())
    assert {(t.row_id, t.field) for t in targets} == {
        (rid, f) for rid in ("fixed-rmb", "cash-ft-1001.02") for f in ("opening", "increase", "decrease")
    }
    opening = next(t for t in targets if t.row_id == "fixed-rmb" and t.field == "opening")
    assert (opening.formula_value, opening.current_value) == (286.73, 200.0)
    assert opening.addr_id == "E1/E1-2/E1-cash-detail-rows[fixed-rmb].opening"
    assert [s.addr_id for s in skips] == ["E1/E1-2/E1-cash-detail-rows[cash-ft-1001.03]"]
    assert "重新取数" in skips[0].reason


def test_untouched_default_cash_row_counts_as_blank():
    entries = {e1_calc.CASH_ROWS_KEY: _cash_rows(
        {"id": "fixed-rmb", "currency": "人民币", "opening": 0, "increase": 0, "decrease": 0, "fxRate": 1,
         "adjustment": 0, "note": ""})}
    targets, _ = B.workpaper_targets(RULES["E1.cash_rows.four_table"], entries, _sources())
    assert {t.current_value for t in targets if t.row_id == "fixed-rmb"} == {None}
    # 有备注即不是占位行
    entries = {e1_calc.CASH_ROWS_KEY: _cash_rows(
        {"id": "fixed-rmb", "opening": 0, "increase": 0, "decrease": 0, "adjustment": 0, "note": "盘点无现金"})}
    targets, _ = B.workpaper_targets(RULES["E1.cash_rows.four_table"], entries, _sources())
    assert {t.current_value for t in targets if t.row_id == "fixed-rmb"} == {0.0}


def test_cash_rows_missing_item_skips_every_seed():
    targets, skips = B.workpaper_targets(RULES["E1.cash_rows.four_table"], {}, _sources())
    assert targets == [] and len(skips) == 3 and all("尚未建立" in s.reason for s in skips)


def test_bank_rows_multi_forms():
    account_prefill = {"accounts": {
        "bank": [
            {"account_code": "1002", "account_no": "A1", "currency": "CNY", "opening": 1000, "debit": 200, "credit": 50},
            {"account_code": "1002", "account_no": "U1", "currency": "USD", "opening": 7200, "debit": 0, "credit": 0},
            {"account_code": "1002", "account_no": "B1", "currency": "", "opening": 5, "debit": 1, "credit": 0},
        ],
        "other": [], "finance_co": [], "unassigned": [],
    }}
    entries = {
        e1_calc.BANK_VARIANT_KEY: "multi",
        e1_calc.BANK_ROWS_KEY: json.dumps([
            {"id": "bank-principal-institution-acct-A1", "section": "principal", "group": "institution",
             "opening": 900, "increase": 200, "decrease": 50, "fxCurrency": "人民币", "fxRate": 1,
             "openingFc": 900, "increaseFc": 200, "decreaseFc": 50},
            {"id": "bank-principal-institution-acct-U1", "section": "principal", "group": "institution",
             "fxCurrency": "USD", "fxRate": 0},
            {"id": "bank-principal-institution-acct-B1", "section": "accrued", "group": "institution", "opening": 5},
        ]),
    }
    targets, skips = B.workpaper_targets(RULES["E1.bank_rows.four_table"], entries, _sources(account_prefill=account_prefill))
    a1 = {t.field: t for t in targets if t.row_id == "bank-principal-institution-acct-A1"}
    assert set(a1) == {"openingFc", "increaseFc", "decreaseFc"}
    assert a1["openingFc"].mirror_field == "opening" and a1["openingFc"].formula_value == 1000.0
    reasons = {s.addr_id.split("[")[1].rstrip("]"): s.reason for s in skips}
    assert "外币行" in reasons["bank-principal-institution-acct-U1"]
    assert "应计利息段" in reasons["bank-principal-institution-acct-B1"]


def test_apply_row_target_writes_field_and_mirror():
    entries = {e1_calc.BANK_VARIANT_KEY: "multi", e1_calc.BANK_ROWS_KEY: json.dumps([
        {"id": "bank-principal-institution-acct-A1", "section": "principal", "group": "institution",
         "opening": 900, "fxCurrency": "人民币", "fxRate": 1, "openingFc": 900, "note": "保留"}])}
    account_prefill = {"accounts": {"bank": [{"account_code": "1002", "account_no": "A1", "currency": "CNY",
                                              "opening": 1000, "debit": 0, "credit": 0}],
                                    "other": [], "finance_co": [], "unassigned": []}}
    targets, _ = B.workpaper_targets(RULES["E1.bank_rows.four_table"], entries, _sources(account_prefill=account_prefill))
    opening = next(t for t in targets if t.field == "openingFc")
    B.apply(entries, opening, opening.formula_value)
    row = json.loads(entries[e1_calc.BANK_ROWS_KEY])[0]
    assert (row["openingFc"], row["opening"], row["note"]) == (1000, 1000, "保留")


# ── 公式 / 派生目标 ───────────────────────────────────────────────────────


def test_tb_amount_and_hall_adjustment_targets():
    s = _sources()
    [t], _ = B.workpaper_targets(RULES["E1.tb_amount.ending"], {}, s)
    assert (t.item_id, t.formula_value, t.current_value) == ("E1-adj-tb-amount-ending", 503.73, None)
    [t], _ = B.workpaper_targets(RULES["E1.tb_amount.opening"], {"E1-adj-tb-amount-opening": "1"}, s)
    assert (t.formula_value, t.current_value) == (393.73, "1")
    [t], _ = B.workpaper_targets(RULES["E1.hall_adj.cash.ending"], {}, s)
    assert t.formula_value == 100.0  # 只取 aje_net，rje 不进审定表


def test_tb_unavailable_skips_instead_of_writing_zero():
    s = _sources(formula=FormulaSources(tb=TbAuditedSnapshot(tb_data={}, available=False)))
    targets, skips = B.workpaper_targets(RULES["E1.tb_amount.ending"], {}, s)
    assert targets == [] and "试算表尚未生成" in skips[0].reason


def test_overlay_propagates_row_writes_into_derived_totals():
    entries = {e1_calc.CASH_ROWS_KEY: _cash_rows(
        {"id": "fixed-rmb", "currency": "人民币", "opening": 1, "increase": 1, "decrease": 0, "fxRate": 1,
         "adjustment": 0, "note": "四表取数 1001.01"})}
    s = _sources()
    targets, _ = B.workpaper_targets(RULES["E1.cash_rows.four_table"], entries, s)
    for t in targets:
        B.apply(entries, t, t.formula_value)
    [ending], _ = B.workpaper_targets(RULES["E1.cash_detail.ending"], entries, s)
    assert ending.formula_value == 376.73
    B.apply(entries, ending, ending.formula_value)
    [total], _ = B.workpaper_targets(RULES["E1.adj_total.1001.ending"], entries, s)
    assert total.formula_value == 376.73
    assert entries["E1-cash-detail-total-unaudited"] == "376.73"


def test_slot_blank_and_finance_unavailable():
    s = _sources()
    [slot], _ = B.workpaper_targets(RULES["E1.adj_slot.digital.ending"], {"E1-adj-slot-digital": "9"}, s)
    assert slot.formula_value is None and slot.current_value == "9"
    B.apply(entries := {"E1-adj-slot-digital": "9"}, slot, None)
    assert entries["E1-adj-slot-digital"] == ""
    targets, skips = B.workpaper_targets(RULES["E1.bank_detail.finance.ending"], {}, s)
    assert targets == [] and "财务公司" in skips[0].reason


def test_note_rows_follow_template_type():
    rows = B.note_rows({"E1-adj-total-1001": "5"}, "soe", RULES["E1.note.main_rows"])
    assert rows[0]["note_label"] == "库存现金" and rows[0]["ending"] == 5.0


# ── 取数严格性 ─────────────────────────────────────────────────────────────


def test_source_loading_raises_instead_of_empty(monkeypatch):
    """四表查询失败必须上抛；render 路径（strict=False）仍 fail-open。"""
    import app.routers.wp_render_strategies._e1_monetary_fund as strategy

    calls: list[bool] = []

    async def boom(db, project_id, year, prefixes, *, strict=False):
        calls.append(strict)
        if strict:
            raise RuntimeError("tb_balance 查询失败")
        return []

    async def fake_accounts(ctx, spec):
        from app.services.four_table.semantic_account_resolver import SemanticAccountResult
        return SemanticAccountResult(slots={}, chart_available=True)

    monkeypatch.setattr(strategy, "fetch_tb_subtree", boom)
    monkeypatch.setattr(strategy, "resolve_semantic_accounts", fake_accounts)
    with pytest.raises(RuntimeError, match="tb_balance"):
        asyncio.run(load_e1_sources(object(), "p", 2025, None))
    asyncio.run(strategy._build_four_table_extraction(
        type("C", (), {"db": object(), "project_id": "p", "wp_id": None, "year": 2025})(), 2025))
    assert calls == [True, False]


class _BrokenDb:
    """任何查询都失败的会话替身（rollback 也失败，验证 strict 不去碰 rollback）。"""

    async def execute(self, *args, **kwargs):
        raise RuntimeError("连接已断开")

    async def rollback(self):
        raise RuntimeError("不应在 strict 模式下 rollback")


def _ctx():
    return type("C", (), {"db": _BrokenDb(), "project_id": "p", "wp_id": None, "year": 2025})()


def test_each_strict_fetcher_raises_while_default_stays_fail_open(monkeypatch):
    import app.routers.wp_render_strategies._e1_monetary_fund as strategy
    from app.services.four_table import e1_bank_accounts, tb_query

    async def fake_active(*args, **kwargs):
        import sqlalchemy as sa
        return sa.true()

    monkeypatch.setattr(tb_query, "get_active_filter", fake_active)
    monkeypatch.setattr(strategy, "get_active_filter", fake_active)
    monkeypatch.setattr("app.services.dataset_query.get_active_filter", fake_active)

    db = _BrokenDb()
    with pytest.raises(RuntimeError, match="连接已断开"):
        asyncio.run(tb_query.fetch_tb_subtree(db, "p", 2025, ["1001"], strict=True))
    assert asyncio.run(tb_query.fetch_tb_subtree(db, "p", 2025, ["1001"])) == []

    with pytest.raises(RuntimeError, match="连接已断开"):
        asyncio.run(strategy._fetch_currency_map(_ctx(), 2025, ["1001"], strict=True))
    assert asyncio.run(strategy._fetch_currency_map(_ctx(), 2025, ["1001"])) == {}

    with pytest.raises(RuntimeError, match="连接已断开"):
        asyncio.run(e1_bank_accounts.fetch_e1_bank_accounts(db, "p", 2025, account_prefixes=["1002"], strict=True))
    assert asyncio.run(e1_bank_accounts.fetch_e1_bank_accounts(db, "p", 2025, account_prefixes=["1002"])) == []

    from app.services.four_table.semantic_account_resolver import ResolvedSlot, SemanticAccountResult
    accounts = SemanticAccountResult(
        slots={"bank": ResolvedSlot(key="bank", label="银行存款", codes=["1002"], standard_codes=["1002"])},
        chart_available=True,
    )
    with pytest.raises(RuntimeError, match="连接已断开"):
        asyncio.run(strategy._build_account_prefill(_ctx(), 2025, accounts, {}, strict=True))
    empty = asyncio.run(strategy._build_account_prefill(_ctx(), 2025, accounts, {}))
    assert empty == strategy._empty_account_prefill()


class _RollbackSpyDb:
    """只记录 rollback 调用的会话替身（active dataset 查询由 monkeypatch 控制）。"""

    def __init__(self):
        self.rollbacks = 0

    async def rollback(self):
        self.rollbacks += 1


def test_active_filter_strict_raises_without_rollback(monkeypatch):
    """strict：active dataset 查询失败原样上抛且不 rollback（rollback 会撤销调用方已 flush 的写入）；
    默认：rollback + 退化为基础过滤（render 路径行为不变）。"""
    import sqlalchemy as sa

    from app.models.audit_platform_models import TbBalance
    from app.services import dataset_query
    from app.services.dataset_service import DatasetService

    async def broken(db, project_id, year):
        raise RuntimeError("ledger_datasets 不存在")

    monkeypatch.setattr(DatasetService, "get_active_dataset_id", staticmethod(broken))
    table = TbBalance.__table__

    strict_db = _RollbackSpyDb()
    with pytest.raises(RuntimeError, match="ledger_datasets"):
        asyncio.run(dataset_query.get_active_filter(strict_db, table, "p", 2025, strict=True))
    assert strict_db.rollbacks == 0

    lenient_db = _RollbackSpyDb()
    clause = asyncio.run(dataset_query.get_active_filter(lenient_db, table, "p", 2025))
    assert lenient_db.rollbacks == 1
    assert isinstance(clause, sa.ColumnElement)
    assert "dataset_id" not in str(clause) and "is_deleted" in str(clause)


def test_each_fetcher_propagates_strict_to_active_filter(monkeypatch):
    """三处取数都把 strict 透传给 get_active_filter —— 否则 strict 取数仍会在过滤层静默 rollback。"""
    import app.routers.wp_render_strategies._e1_monetary_fund as strategy
    from app.services.four_table import e1_bank_accounts, tb_query

    seen: list[tuple[str, bool]] = []

    def spy(label):
        async def fake_active(db, table, project_id, year, **kwargs):
            seen.append((label, kwargs.get("strict", False)))
            raise RuntimeError("过滤层失败")
        return fake_active

    monkeypatch.setattr(tb_query, "get_active_filter", spy("tb_subtree"))
    monkeypatch.setattr(strategy, "get_active_filter", spy("currency_map"))
    monkeypatch.setattr("app.services.dataset_query.get_active_filter", spy("bank_accounts"))

    db = _RollbackSpyDb()
    for strict in (True, False):
        seen.clear()
        runs = [
            lambda: tb_query.fetch_tb_subtree(db, "p", 2025, ["1001"], strict=strict),
            lambda: strategy._fetch_currency_map(
                type("C", (), {"db": db, "project_id": "p"})(), 2025, ["1001"], strict=strict),
            lambda: e1_bank_accounts.fetch_e1_bank_accounts(
                db, "p", 2025, account_prefixes=["1002"], strict=strict),
        ]
        for make in runs:
            if strict:
                with pytest.raises(RuntimeError, match="过滤层失败"):
                    asyncio.run(make())
            else:
                asyncio.run(make())
        assert seen == [("tb_subtree", strict), ("currency_map", strict), ("bank_accounts", strict)]


def test_entry_warnings_report_defaulted_bank_variant():
    assert B.entry_warnings({}) == []
    assert B.entry_warnings({e1_calc.BANK_ROWS_KEY: "[]", e1_calc.BANK_VARIANT_KEY: "rmb"}) == []
    [w] = B.entry_warnings({e1_calc.BANK_ROWS_KEY: "[{}]"})
    assert "人民币及外币" in w


def test_temporary_binding_is_the_single_registry_source(monkeypatch):
    """临时 binding 同时驱动清单、科目前缀和规则校验，撤销后全部失效。"""
    from app.services.formula_push import triggers
    from app.services.formula_push.rules import PushRuleError, parse_rules

    from tests._formula_push_binding import DummyPushBinding

    class FakeBinding(DummyPushBinding):
        wp_code = "Z9"
        account_prefixes = ("9901",)

    from app.services.formula_push.bindings import register_binding, watched_prefixes

    revoke = register_binding("Z9", FakeBinding)
    try:
        assert "Z9" in supported_wp_codes()
        assert watched_prefixes()["Z9"] == ("9901",)
        assert triggers._watched_prefixes()["Z9"] == ("9901",)

        # 用真清单的首条规则改成 Z9，避免测试另造一套规则结构。
        raw = json.loads(RULES_PATH.read_text(encoding="utf-8"))["rules"][0]
        raw["rule_id"] = "Z9.tb_amount.ending"
        raw["page_key"] = "workpaper:Z9"
        raw["target"]["wp_code"] = "Z9"
        raw["target"]["sheet_code"] = "Z9-1"
        raw["target"]["item_id"] = "Z9-tb-amount-ending"
        doc = {"version": 1, "rules": [raw]}
        assert parse_rules(doc)
    finally:
        revoke()

    assert "Z9" not in supported_wp_codes()
    assert "Z9" not in watched_prefixes()
    assert "Z9" not in triggers._watched_prefixes()
    with pytest.raises(KeyError):
        get_binding("Z9")
    with pytest.raises(PushRuleError, match="未注册"):
        parse_rules(doc)


# ── 试算表上下文口径覆盖（Task 8 守卫）─────────────────────────────────────


def test_occurrence_context_returns_tb_data_with_period_amount():
    """trial_balance_audited_occurrence 口径：context_for 返回含本期发生额的 tb_data。"""
    tb = TbAuditedSnapshot(
        tb_data={"1001": {"期末余额": Decimal("100"), "年初余额": Decimal("60"), "本期发生额": Decimal("40")}},
        available=True,
    )
    fs = FormulaSources(tb=tb, hall_adj={})
    ctx = fs.context_for({"tb": "trial_balance_audited_occurrence"})
    assert ctx.tb_data["1001"]["本期发生额"] == Decimal("40")
    assert ctx.tb_data["1001"]["期末余额"] == Decimal("100")
    # 同一 snapshot 的旧口径也正常返回
    ctx_old = fs.context_for({"tb": "trial_balance_audited"})
    assert ctx_old.tb_data["1001"]["本期发生额"] == Decimal("40")


def test_occurrence_context_unavailable_when_tb_missing():
    """试算表未生成时两种口径都返回不可用原因。"""
    fs = FormulaSources(tb=None, hall_adj={})
    for ctx_name in ("trial_balance_audited", "trial_balance_audited_occurrence"):
        reason = fs.unavailable_reason({"tb": ctx_name})
        assert reason is not None and "试算表" in reason
