"""公式推送规则清单 `formula_push_rules.json` + 加载校验 `rules.py`。

spec: chain-closure-phase2-formula-push-engine · 任务 6 · 需求 1.1~1.3

三组判据：
1. 真清单：加载零错误、E1 规则全集与分布、目标不重复；公式规则以**有区分度的上下文**
   真求值，钉住语义（试算平衡表数 = Σ(期末余额+AJE+RJE)，大厅调整只取 ADJ 净额）。
2. 校验器逐项反向用例：每一类坏规则都必须被拒，且错误信息点名规则。
3. 一次加载报告全部问题（不在第一个错误处停下）；缓存随文件修改重载。
"""
from __future__ import annotations

import copy
import json
import os
import time
from collections import Counter
from decimal import Decimal
from pathlib import Path

import pytest

from app.services.formula_engine import FormulaContext, execute
from app.services.formula_push.rules import (
    BindingSpec,
    RULES_PATH,
    PushRuleError,
    load_rules,
    note_addr_id,
    parse_rules,
    rules_for,
    workpaper_addr_id,
)

_DOC = json.loads(RULES_PATH.read_text(encoding="utf-8"))
_RULES = load_rules()
_BY_ID = {r.rule_id: r for r in _RULES}


# ── 1. 真清单 ─────────────────────────────────────────────────────────────


def test_real_rules_load_and_distribution():
    assert Counter(r.stage for r in _RULES) == Counter(item["stage"] for item in _DOC["rules"])
    assert Counter(r.policy for r in _RULES) == Counter(item["policy"] for item in _DOC["rules"])
    assert len(_RULES) == len(_DOC["rules"])
    assert {r.wp_code for r in _RULES} == {
        "E1", "K1",
        "D1", "D2", "D3", "D4", "D5", "D6", "D7",
        "F1", "F2", "F3", "F4", "F5",
        "G1", "G2", "G3", "G4", "G5", "G6", "G7", "G8", "G9", "G10",
        "G11", "G12", "G13", "G14",
        "H1", "H2", "H3", "H4", "H5", "H6", "H7", "H8", "H9", "H10",
        "I1", "I2", "I3", "I4", "I5", "I6",
        "J1", "J2",
        "K2", "K3", "K4", "K5", "K6", "K7", "K8", "K9", "K10", "K11", "K12", "K13",
        "L1", "L2", "L3", "L4", "L5", "L6", "L7", "L8",
        "M1", "M2", "M3", "M4", "M5", "M6", "M7", "M8", "M9", "M10",
        "N1", "N2", "N3", "N4", "N5",
    }
    assert len({r.target.identity() for r in _RULES}) == len(_RULES)


def test_every_e1_backend_owned_key_has_exactly_one_rule():
    """design §四 的后端独占键全集 —— 少一条即某个键无人维护，多一条即键名漂移。"""
    e1_items = {r.target.item_id for r in _RULES if r.target.domain == "workpaper" and r.wp_code == "E1"}
    e1_expected = {
        "E1-cash-detail-rows", "E1-bank-detail-rows",
        "E1-adj-tb-amount-ending", "E1-adj-tb-amount-opening",
        "E1-hall-adj-cash-ending", "E1-hall-adj-bank_principal-ending", "E1-hall-adj-other_mf-ending",
        "E1-cash-detail-opening-unaudited", "E1-cash-detail-total-unaudited",
        *(f"E1-bank-detail-{g}-{p}-unaudited"
          for g in ("principal", "institution", "finance", "other") for p in ("opening", "total")),
        *(f"E1-adj-total-{c}{s}" for c in ("1001", "1002", "1012") for s in ("", "-opening")),
        *(f"E1-adj-slot-{k}{s}" for k in ("finance_co", "accrued", "digital") for s in ("", "-opening")),
    }
    assert e1_items == e1_expected

    k1_items = {r.target.item_id for r in _RULES if r.target.domain == "workpaper" and r.wp_code == "K1"}
    k1_expected = {
        "K1-1-audited-receivable", "K1-1-audited-baddebt", "K1-1-audited-net",
        *(f"K1-1-receivable-r{i}-unadj" for i in range(4)),
        *(f"K1-1-baddebt-r{i}-unadj" for i in range(4)),
    }
    assert k1_items == k1_expected


def test_workpaper_saved_only_fires_derived_and_note_rules():
    """E1 保存不改四表 / 试算表 / 大厅 ⇒ 只重算派生与附注，源值规则不跑。"""
    fired = rules_for(_RULES, wp_code="E1", trigger="WORKPAPER_SAVED")
    assert {r.stage for r in fired} == {"derived", "note"}
    assert len(rules_for(_RULES, trigger="manual")) == len(_RULES)


def _tb(code: str) -> dict[str, Decimal]:
    base = {"1001": 1, "1002": 100, "1012": 10000}[code]
    return {
        "期末余额": Decimal(base), "年初余额": Decimal(base * 2),
        "AJE调整": Decimal(base * 3), "RJE调整": Decimal(base * 5),
    }


def test_tb_amount_formulas_mean_audited_and_opening():
    """trial_balance_audited 口径：期末余额键 = 持久化审定数；AJE/RJE 列不得再叠加（否则双计）。"""
    ctx = FormulaContext(tb_data={c: _tb(c) for c in ("1001", "1002", "1012")})
    ending = execute(_BY_ID["E1.tb_amount.ending"].source.expression, ctx)
    opening = execute(_BY_ID["E1.tb_amount.opening"].source.expression, ctx)
    assert not ending.errors and not opening.errors
    # 期末 = Σ 期末余额（1 倍基数，AJE 3 倍 / RJE 5 倍都不得混入）；年初 = 2 倍基数
    assert ending.value == Decimal(1 + 100 + 10000)
    assert opening.value == Decimal(2 * (1 + 100 + 10000))
    for rid in ("E1.tb_amount.ending", "E1.tb_amount.opening"):
        assert _BY_ID[rid].source.context_map == {"tb": "trial_balance_audited"}
        assert "AJE" not in _BY_ID[rid].source.expression and "RJE" not in _BY_ID[rid].source.expression


def test_hall_adjustment_formulas_read_adj_net_only():
    adj = {c: {"aje_net": Decimal(i + 1) * 7, "rje_net": Decimal(999)} for i, c in enumerate(("1001", "1002", "1012"))}
    ctx = FormulaContext(tb_data={c: _tb(c) for c in adj}, adj_data=adj)
    for rid, code in (("E1.hall_adj.cash.ending", "1001"),
                      ("E1.hall_adj.bank_principal.ending", "1002"),
                      ("E1.hall_adj.other_mf.ending", "1012")):
        result = execute(_BY_ID[rid].source.expression, ctx)
        assert not result.errors
        assert result.value == adj[code]["aje_net"], rid
        assert _BY_ID[rid].source.context_map == {"adj": "hall_approved_excluding_workpaper"}


def test_note_rule_targets_both_templates():
    note = _BY_ID["E1.note.main_rows"]
    assert note.target.sections == {"listed": "五、1", "soe": "八、1"}
    assert note.target.table == "货币资金"
    assert note.target.fields == ("end_amount", "prior_amount")


def test_known_derivations_check_accepts_real_names():
    names = {r.source.name for r in _RULES if r.source.kind == "derivation"}
    # 动态集合：随 binding 增加而增长，用现算值
    assert "e1_cash_detail_total" in names
    assert "k1_audited_total" in names
    assert "k2_audited_total" in names
    assert len(load_rules(known_derivations=names)) == len(_RULES)


def _binding_spec(
    *,
    four_table_slots=("cash",),
    derivations=("e1_cash_detail_total",),
    tb_columns=("期末余额",),
) -> BindingSpec:
    return BindingSpec(
        four_table_slots=frozenset(four_table_slots),
        derivations=frozenset(derivations),
        tb_columns=frozenset(tb_columns),
    )


def test_binding_specs_isolate_derivations_and_four_table_slots():
    doc = _doc_with(lambda rules: None)
    doc["rules"] = [copy.deepcopy(_rule(doc["rules"], "E1.cash_rows.four_table"))]
    raw = doc["rules"][0]
    raw["rule_id"] = "A1.cash_rows.four_table"
    raw["page_key"] = "workpaper:A1"
    raw["target"].update(wp_code="A1", sheet_code="A1-1", item_id="A1-cash-detail-rows")
    raw["source"]["slots"] = ["bank"]
    raw["source"]["formula_text"] = "银行明细行"
    raw["source"]["kind"] = "four_table_leaves"
    specs = {
        "A1": _binding_spec(four_table_slots=("cash",), derivations=("a_only",)),
        "B1": _binding_spec(four_table_slots=("bank",), derivations=("b_only",)),
    }
    with pytest.raises(PushRuleError) as exc:
        parse_rules(doc, binding_specs=specs)
    assert any("四表槽" in error and "bank" in error for error in exc.value.errors)

    raw["source"]["slots"] = ["cash"]
    raw["source"]["kind"] = "derivation"
    raw["source"].pop("slots", None)
    raw["source"].update(name="b_only", params={}, formula_text="B 科目派生值")
    with pytest.raises(PushRuleError) as exc:
        parse_rules(doc, binding_specs=specs)
    assert any("未实现" in error and "b_only" in error for error in exc.value.errors)


def test_binding_spec_rejects_unloaded_tb_column_for_tb_and_sum_tb():
    doc = copy.deepcopy(_DOC)
    raw = _rule(doc["rules"], "E1.tb_amount.opening")
    doc["rules"] = [raw]
    raw["source"]["expression"] = "TB('1001','期末余额') + SUM_TB('1002~1002','本期发生额')"
    spec = {"E1": _binding_spec(tb_columns=("期末余额",))}
    with pytest.raises(PushRuleError) as exc:
        parse_rules(doc, binding_specs=spec)
    errors = exc.value.errors
    assert any("tb_columns" in error and "本期发生额" in error and "未装载" in error for error in errors)


def test_e1_rules_pass_with_explicit_binding_spec():
    from app.services.formula_push.rules import _binding_specs_from_registry
    from app.services.formula_push.bindings import supported_wp_codes as _swc
    # 真实注册表全部 binding 的 spec（20 个），确保 56 条规则全部通过
    all_specs = _binding_specs_from_registry(_swc())
    assert len(load_rules(binding_specs=all_specs)) == len(_RULES)


def test_load_rules_cache_key_includes_binding_specs(tmp_path: Path):
    path = tmp_path / "rules.json"
    path.write_text(json.dumps(_DOC, ensure_ascii=False), encoding="utf-8")
    restricted = _binding_spec(
        four_table_slots=("cash",),
        derivations=("e1_cash_detail_total",),
        tb_columns=("期末余额",),
    )
    with pytest.raises(PushRuleError):
        load_rules(path, binding_specs={"E1": restricted})
    k1_spec = _binding_spec(
        four_table_slots=(),
        derivations=(
            "k1_audited_total",
            "k1_detail_combo_unadj",
            "k1_detail_combo_baddebt",
            "k1_note_main",
        ),
        tb_columns=("期末余额", "年初余额", "本期发生额"),
    )
    complete = _binding_spec(
        four_table_slots=("cash", "bank", "other", "finance_co", "digital"),
        derivations=(
            "e1_cash_detail_total", "e1_bank_detail_total", "e1_adjudicated_total",
            "e1_main_row_slot", "e1_disclosure_main_rows",
        ),
        tb_columns=("期末余额", "年初余额", "本期发生额"),
    )
    from app.services.formula_push.rules import _binding_specs_from_registry
    from app.services.formula_push.bindings import supported_wp_codes as _swc
    all_specs = dict(_binding_specs_from_registry(_swc()))
    all_specs["E1"] = complete
    all_specs["K1"] = k1_spec
    assert len(load_rules(path, binding_specs=all_specs)) == len(_RULES)


# ── 2. 校验器反向用例 ─────────────────────────────────────────────────────


def _doc_with(mutate) -> dict:
    doc = copy.deepcopy(_DOC)
    mutate(doc["rules"])
    return doc


def _rule(rules: list, rule_id: str) -> dict:
    return next(r for r in rules if r["rule_id"] == rule_id)


def _set(rule_id: str, path: tuple, value):
    def mutate(rules):
        node = _rule(rules, rule_id)
        for key in path[:-1]:
            node = node[key]
        node[path[-1]] = value
    return mutate


_BAD_CASES = [
    ("rule_id 重复", lambda rs: rs.append(copy.deepcopy(rs[0])), "rule_id 重复"),
    ("两条规则写同一目标", _set("E1.tb_amount.opening", ("target", "item_id"), "E1-adj-tb-amount-ending"),
     "写同一目标"),
    ("禁用列名 审定数", _set("E1.tb_amount.opening", ("source", "expression"), "TB('1001','审定数')"),
     "禁用列名"),
    ("禁用列名 未审数", _set("E1.tb_amount.opening", ("source", "expression"), "TB('1001','未审数')"),
     "禁用列名"),
    ("TB 缺列名", _set("E1.tb_amount.opening", ("source", "expression"), "TB('1001')"), "显式写列名"),
    ("未知函数", _set("E1.tb_amount.opening", ("source", "expression"), "FOO('1001','期末余额')"),
     "未知函数"),
    ("未注册列名", _set("E1.tb_amount.opening", ("source", "expression"), "TB('1001','期末余额X')"),
     "公式试算失败"),
    ("ADJ 口径拼错", _set("E1.hall_adj.cash.ending", ("source", "expression"), "ADJ('1001','aje_dr')"),
     "公式试算失败"),
    ("括号不配", _set("E1.tb_amount.opening", ("source", "expression"), "TB('1001','年初余额'"),
     "括号不匹配"),
    ("TB 未声明 tb 口径", _set("E1.tb_amount.opening", ("source", "context"), {"adj": "hall_approved_excluding_workpaper"}),
     "未声明 tb"),
    ("context 取值未登记", _set("E1.hall_adj.cash.ending", ("source", "context"), {"adj": "all"}),
     "context.adj"),
    ("tb 口径拼错", _set("E1.tb_amount.opening", ("source", "context"), {"tb": "trial_balance"}),
     "context.tb"),
    ("未知策略", _set("E1.tb_amount.opening", ("policy",), "overwrite"), "policy="),
    ("stage 与 policy 不搭", _set("E1.cash_detail.opening", ("policy",), "editable"), "不允许 policy"),
    ("缺 manual 触发", _set("E1.cash_detail.opening", ("triggers",), ["WORKPAPER_SAVED"]), "须含 manual"),
    ("未知触发事件", _set("E1.cash_detail.opening", ("triggers",), ["manual", "ON_LOGIN"]), "触发事件"),
    ("说明非中文", _set("E1.cash_detail.opening", ("description",), "cash detail opening"), "中文说明"),
    ("sheet 不属于底稿", _set("E1.cash_detail.opening", ("target", "sheet_code"), "D2-1"), "不属于底稿"),
    ("item_id 前缀不符", _set("E1.cash_detail.opening", ("target", "item_id"), "D2-foo"), "不以 E1- 开头"),
    ("page_key 与 rule_id 不符", _set("E1.cash_detail.opening", ("page_key",), "workpaper:D2"), "须以 D2. 开头"),
    ("派生缺算式说明", _set("E1.cash_detail.opening", ("source", "formula_text"), ""), "formula_text"),
    ("未知四表槽", _set("E1.cash_rows.four_table", ("source", "slots"), ["cash", "bonds"]), "四表槽"),
    ("行集缺字段", _set("E1.cash_rows.four_table", ("target", "fields"), []), "同时出现"),
    ("附注章节键非法", _set("E1.note.main_rows", ("target", "section_by_template"), {"ifrs": "1"}),
     "section_by_template 键"),
    ("附注规则指向底稿域", _set("E1.note.main_rows", ("target",),
                          {"domain": "workpaper", "wp_code": "E1", "sheet_code": "E1-1", "item_id": "E1-x"}),
     "必须是附注域"),
    ("附注目标含未登记字段", _set("E1.note.main_rows", ("target", "fields"), ["end_amount", "bogus_field"]),
     "未登记字段"),
    ("rule_id 格式", _set("E1.cash_detail.opening", ("rule_id",), "e1 cash"), "格式不合法"),
]


@pytest.mark.parametrize("name,mutate,fragment", _BAD_CASES, ids=[c[0] for c in _BAD_CASES])
def test_validator_rejects(name, mutate, fragment):
    with pytest.raises(PushRuleError) as exc:
        parse_rules(_doc_with(mutate))
    assert any(fragment in e for e in exc.value.errors), exc.value.errors


def test_unknown_derivation_rejected_when_registry_given():
    with pytest.raises(PushRuleError) as exc:
        parse_rules(_DOC, known_derivations={"e1_cash_detail_total"})
    assert any("未实现" in e and "e1_adjudicated_total" in e for e in exc.value.errors)


def test_all_problems_reported_at_once_and_nothing_returned():
    def mutate(rules):
        _set("E1.tb_amount.opening", ("source", "expression"), "TB('1001','审定数')")(rules)
        _set("E1.cash_detail.opening", ("description",), "english only")(rules)
    with pytest.raises(PushRuleError) as exc:
        parse_rules(_doc_with(mutate))
    rule_ids = {e.split(":", 1)[0] for e in exc.value.errors}
    assert {"E1.tb_amount.opening", "E1.cash_detail.opening"} <= rule_ids


@pytest.mark.parametrize("doc", [None, {"version": 2, "rules": [{}]}, {"version": 1, "rules": []}])
def test_rejects_malformed_root(doc):
    with pytest.raises(PushRuleError):
        parse_rules(doc)


# ── 3. addr_id / 筛选 / 缓存 ───────────────────────────────────────────────


def test_addr_id_helpers():
    assert workpaper_addr_id("E1", "E1-1", "E1-adj-tb-amount-ending") == "E1/E1-1/E1-adj-tb-amount-ending"
    assert (workpaper_addr_id("E1", "E1-2", "E1-cash-detail-rows", row_id="fixed-rmb", field_name="opening")
            == "E1/E1-2/E1-cash-detail-rows[fixed-rmb].opening")
    assert note_addr_id("五、1", "货币资金", "库存现金", "end") == "note://五、1/货币资金/库存现金.end"
    with pytest.raises(ValueError):
        note_addr_id("五、1", "货币资金", "库存现金", "ending")


def test_load_rules_reloads_after_file_change(tmp_path: Path):
    path = tmp_path / "rules.json"
    path.write_text(json.dumps(_DOC, ensure_ascii=False), encoding="utf-8")
    assert len(load_rules(path)) == len(_RULES)
    smaller = copy.deepcopy(_DOC)
    smaller["rules"] = smaller["rules"][:3]
    path.write_text(json.dumps(smaller, ensure_ascii=False), encoding="utf-8")
    stat = path.stat()
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000))
    time.sleep(0.01)
    assert len(load_rules(path)) == 3


def test_unknown_binding_is_rejected_before_running():
    doc = copy.deepcopy(_DOC)
    doc["rules"] = [_rule(doc["rules"], "E1.tb_amount.opening")]
    doc["rules"][0]["page_key"] = "workpaper:Z9"
    doc["rules"][0]["rule_id"] = "Z9.tb_amount.opening"
    doc["rules"][0]["target"].update(wp_code="Z9", sheet_code="Z9-1", item_id="Z9-tb-amount-opening")
    with pytest.raises(PushRuleError, match="未注册"):
        parse_rules(doc)
