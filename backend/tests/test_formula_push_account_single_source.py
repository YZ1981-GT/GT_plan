"""推送取数科目以四表口径单一来源为准（spec formula-fetch-and-wp-generation-defect-closure R1）。

背景（2026-10-23 现查）：推送 binding / 规则的科目码原先多处手写或抄映射表 ``wp_account_mapping.json``——
映射表字母后缀（H6 ``1606B``、I1 ``1703B``）、不存在的码（I2 ``1717``、I5 ``1911``、H9 ``2802``、J2 ``2611``、M10 ``4501``）、
别的科目（H8 ``1901`` 待处理财产损溢、H9 ``2205`` 合同负债、I6 ``6602`` 管理费用、G6 / G8 ``1503`` 可供出售金融资产、
M3~M9 整体错位一格、L7 ``2801`` 预计负债、K1 ``1231`` 全部坏账准备）。推送因此恒为 0，或把别的科目的数写进审定表与附注
（真库和平药房_2025 盈余公积附注期末 = 本年利润 53,384,067.82；重药控股安徽_2025 其他应收款附注期初多出 1,639 万）。

本守卫钉住：

1. binding 科目一律是试算表标准码形态（不带映射表字母后缀）
2. 每个已注册 binding 的科目 ⊆ 该底稿在口径单一来源里声明的科目（原值 / 备抵 / 附加槽 + 双族互斥写法）；
   不符的逐条登记原因（``KNOWN_ACCOUNT_DEVIATIONS``，只许减少，失效条目打红）
3. 本 spec 改正过的底稿逐码钉住（单一来源本身被改错也会在这里打红）
4. 没有标准科目的 binding 写明原因，且规则清单里没有取试算表的规则、没有附注主表规则
5. Tier A 预设与推送规则同一锚点的公式逐字相同
6. H/I 预设契约检查（含 I5 移除声明）严格模式通过，且移除声明可被现状证伪
"""
from __future__ import annotations

import importlib
import importlib.util
import json
import re
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services.formula_push.bindings import get_binding, supported_wp_codes
from app.services.formula_push.rules import load_rules
from app.services.four_table.dual_family_codes import ALL_DUAL_FAMILY_CODES

_BACKEND = Path(__file__).resolve().parents[1]
_PRESETS_PATH = _BACKEND / "data" / "d_cycle_extraction" / "d_cycle_extraction_presets.json"
_CHECK_SCRIPT = _BACKEND / "scripts" / "check" / "check_hi_extraction_presets_contract.py"
_TB_RE = re.compile(r"TB\(\s*'([^']+)'")

#: 与口径单一来源不一致、但有意如此（或待别处裁定）的 binding 科目。键 = 底稿编码，值 = (多出的科目, 原因)。
#: 只许减少：修好一条删一条；条目失效（已一致 / 底稿不再注册）会打红。
KNOWN_ACCOUNT_DEVIATIONS: dict[str, tuple[tuple[str, ...], str]] = {
    "D4": (("6051",), "营业收入审定表同时推主营业务收入（6001）与其他业务收入（6051）两个锚点；"
                      "d_cycle_specs 的 D4 只给主营的兜底码，其他业务收入按科目名定位"),
    "F2": (("1402", "1403", "1405", "1408", "1461"),
           "存货按科目族推送（材料采购 / 在途物资 / 原材料 / 库存商品 / 委托加工物资 / 存货跌价准备），"
           "f_cycle_specs 只给 1401 兜底码、其余按名定位。🔴 附注合计把 1461 存货跌价准备当正数相加、1405 / 1408 "
           "在两套编码体系里含义不同 —— 待按存货类别重做（本 spec 只登记，design §9）"),
    "F5": (("6402",), "营业成本 = 主营业务成本（6401）+ 其他业务成本（6402）；f_cycle_specs 只给主营的兜底码"),
    "K6": (("2245",), "持有待售资产和负债同一张底稿推资产（1481）与负债（2245）两侧；k_cycle_specs 只给资产侧兜底码"),
}

#: 本 spec 改正过的底稿：期望科目逐码钉住（顺序即 binding 声明顺序）
CORRECTED_CODES: dict[str, tuple[str, ...]] = {
    "H6": ("1606",),               # 原 1606B
    "H8": ("1641", "1651"),        # 原 1901 待处理财产损溢；双族并取
    "H9": ("2601", "2651"),        # 原 2802（不存在）；未确认融资费用 2602 另列
    "I1": ("1701", "1702", "1703"),  # 原 1703B
    "I2": ("1704",),
    "I3": ("1711",),
    "I4": ("1801",),
    "I5": (),                      # 原 1901；其他非流动资产没有标准科目
    "I6": ("6604",),               # 原 6602 管理费用
    "G6": ("1506",),               # 原 1503 可供出售金融资产
    "G8": ("1507",),               # 原 1503
    "J2": ("2705",),               # 原 2611（不存在）
    "L7": (),                      # 原 2801 预计负债（K5 的科目）
    "M3": ("4201",),               # 原 4002 资本公积
    "M4": ("4002",),               # 原 4101 盈余公积
    "M5": ("4101",),               # 原 4103 本年利润
    "M7": ("4301",),               # 原 4201 库存股
    "M8": (),                      # 原 4301 专项储备；一般风险准备没有标准科目
    "M9": ("4003",),               # 原 4401 其他权益工具
    "M10": ("4401",),              # 原 4501（不存在）
    "K1": ("1221", "1231-03"),     # 原 1231（按前缀含全部坏账准备）
    # spec formula-fetch-followup-defect-closure R6.2：全库不存在的码 ⇒ 无科目声明
    "D5": (),                      # 原 1124
    "K4": (),                      # 原 2261
}


def _single_source_codes(wp_code: str) -> tuple[str, ...] | None:
    """该底稿在四表口径单一来源里声明的全部科目（原值 / 备抵 / 附加槽）；None = 没有声明。"""
    from app.services.four_table.e_cycle_specs import E1_MONETARY_FUND_SPEC
    from app.services.four_table.j_cycle_account_scope import j_semantic_spec_of
    from app.services.four_table.k_cycle_specs import K_CYCLE_SPECS

    if wp_code in K_CYCLE_SPECS:
        k = K_CYCLE_SPECS[wp_code]
        return tuple(dict.fromkeys(
            [c for c in (k.fallback_standard,) if c] + list(k.fallback_provision) + list(k.extra_standard_codes)
        ))
    if wp_code == "E1":
        spec = E1_MONETARY_FUND_SPEC
    elif wp_code[:1] == "J":
        spec = j_semantic_spec_of(wp_code)
    else:
        spec = None
        for module, name in (("d_cycle_specs", "D_CYCLE_SPECS"), ("f_cycle_specs", "F_CYCLE_SPECS"),
                             ("g_cycle_specs", "G_CYCLE_SPECS"), ("h_cycle_specs", "H_CYCLE_SPECS"),
                             ("i_cycle_specs", "I_CYCLE_SPECS"), ("l_cycle_specs", "L_CYCLE_SPECS"),
                             ("m_cycle_specs", "M_CYCLE_SPECS"), ("n_cycle_specs", "N_CYCLE_SPECS")):
            specs = getattr(importlib.import_module(f"app.services.four_table.{module}"), name)
            if wp_code in specs:
                spec = specs[wp_code]
                break
    if spec is None:
        return None
    return tuple(dict.fromkeys(c for slot in spec.slots for c in slot.fallback_standard_codes))


def _extra_codes(wp_code: str) -> tuple[str, ...]:
    """binding 里不在口径单一来源声明之内的科目（双族互斥写法视同声明）。"""
    declared = _single_source_codes(wp_code)
    assert declared is not None, f"{wp_code} 在四表口径单一来源里没有科目声明（新接入的底稿须先在 four_table 声明）"
    return tuple(c for c in get_binding(wp_code).account_prefixes
                 if c not in declared and c not in ALL_DUAL_FAMILY_CODES)


def _deviations() -> dict[str, tuple[str, ...]]:
    return {code: extra for code in supported_wp_codes() if (extra := _extra_codes(code))}


# ── 1. 标准码形态 ─────────────────────────────────────────────────────────────


def test_binding_codes_are_plain_standard_codes():
    """试算表标准码是 4 位数字（可带 ``-NN`` 子目）；映射表的字母后缀（1606B / 1703B）在试算表里取不到数。"""
    pattern = re.compile(r"^\d{4}(-\d{2})?$")
    bad = {code: [c for c in get_binding(code).account_prefixes if not pattern.fullmatch(c)]
           for code in supported_wp_codes()}
    assert {k: v for k, v in bad.items() if v} == {}


# ── 2. 与口径单一来源一致 ──────────────────────────────────────────────────────


def test_every_binding_follows_single_source_or_is_registered():
    """科目不在口径单一来源之内的 binding 必须登记且多出的科目与登记一致（双向：登记了就必须仍然不一致）。"""
    actual = _deviations()
    registered = {code: codes for code, (codes, _reason) in KNOWN_ACCOUNT_DEVIATIONS.items()}
    assert actual == registered, (
        "binding 科目与口径单一来源的偏差和登记不一致。\n"
        f"未登记的偏差：{ {k: v for k, v in actual.items() if registered.get(k) != v} }\n"
        f"已失效的登记（修好了请删掉）：{ {k: v for k, v in registered.items() if actual.get(k) != v} }"
    )
    assert all(reason.strip() for _codes, reason in KNOWN_ACCOUNT_DEVIATIONS.values())


def test_deviation_checker_catches_a_planted_wrong_code(monkeypatch):
    """反向自检：把 M4 资本公积的取数改回映射表的错码 4101、H6 改回 1606B，偏差判据必须点名它们。"""
    real = get_binding
    planted = {"M4": ("4101",), "H6": ("1606B",)}
    monkeypatch.setattr(sys.modules[__name__], "get_binding",
                        lambda code: SimpleNamespace(account_prefixes=planted[code]) if code in planted else real(code))
    found = _deviations()
    assert found["M4"] == ("4101",) and found["H6"] == ("1606B",)


# ── 3. 改正过的底稿逐码钉住 ────────────────────────────────────────────────────


@pytest.mark.parametrize("wp_code", sorted(CORRECTED_CODES))
def test_corrected_bindings_pinned(wp_code: str):
    assert tuple(get_binding(wp_code).account_prefixes) == CORRECTED_CODES[wp_code]


def test_corrected_formula_rules_use_binding_codes():
    """改正过的底稿：取试算表的规则只引用本 binding 的科目（规则与 binding 同一口径）。"""
    offenders = []
    for rule in load_rules():
        if rule.wp_code in CORRECTED_CODES and rule.source.kind == "formula":
            codes = set(_TB_RE.findall(rule.source.expression or ""))
            if not codes <= set(CORRECTED_CODES[rule.wp_code]):
                offenders.append((rule.rule_id, rule.source.expression))
    assert offenders == []


# ── 4. 没有标准科目 ────────────────────────────────────────────────────────────


def test_no_account_bindings_have_reason_and_no_tb_or_note_main_rules():
    no_account = [code for code in supported_wp_codes() if not get_binding(code).account_prefixes]
    assert sorted(no_account) == ["D5", "I5", "K4", "L7", "M8"]
    rules = load_rules()
    for code in no_account:
        assert getattr(get_binding(code), "no_account_reason", "").strip(), code
        own = [r for r in rules if r.wp_code == code]
        assert not [r.rule_id for r in own if r.source.kind == "formula"], f"{code} 不得有取试算表的规则"
        assert not [r.rule_id for r in own if r.stage == "note"], f"{code} 不得有附注推送规则"


# ── 5. 预设与推送规则同口径 ────────────────────────────────────────────────────


def test_tier_a_presets_equal_push_rules_for_same_anchor():
    """渲染期预设（公式管理面板显示的系统公式）与推送规则同一锚点的公式必须逐字相同，且每条预设都有推送规则。"""
    raw = json.loads(_PRESETS_PATH.read_text(encoding="utf-8"))
    presets = {(wp, e["anchor"]): e["expression"]
               for wp, entries in raw.items() if not wp.startswith("_") and isinstance(entries, list)
               for e in entries}
    rules = {(r.wp_code, r.target.item_id): r.source.expression
             for r in load_rules() if r.target.domain == "workpaper" and r.source.kind == "formula"}
    assert len(presets) >= 19
    assert {k: (v, rules.get(k)) for k, v in presets.items() if rules.get(k) != v} == {}


# ── 6. H/I 预设契约检查 ────────────────────────────────────────────────────────


def _load_check_module(tmp_path: Path | None = None):
    spec = importlib.util.spec_from_file_location(f"_hi_presets_check_{id(tmp_path)}", _CHECK_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_hi_presets_contract_check_passes_strict(monkeypatch, capsys):
    module = _load_check_module()
    monkeypatch.setattr(sys, "argv", [str(_CHECK_SCRIPT), "--strict"])
    assert module.main() == 0, capsys.readouterr().out
    assert "1 removed, 0 errors" in capsys.readouterr().out


@pytest.mark.parametrize("mutate, message", [
    (lambda d: d["_I5_removed"].pop("_why"), "移除声明缺少"),
    (lambda d: d.__setitem__("I5", [{"anchor": "I5-1-tb-amount", "expression": "TB('1911','期末余额')"}]),
     "已声明移除却仍有"),
    (lambda d: d.pop("_I5_removed"), "预设库无条目"),
])
def test_hi_presets_removal_declaration_is_falsifiable(monkeypatch, capsys, tmp_path, mutate, message):
    """移除声明不是加一行就放行的后门：缺字段、与现状矛盾、删掉声明都必须打红。"""
    data = json.loads(_PRESETS_PATH.read_text(encoding="utf-8"))
    mutate(data)
    planted = tmp_path / "presets.json"
    planted.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    module = _load_check_module(tmp_path)
    monkeypatch.setattr(module, "PRESETS_PATH", planted)
    monkeypatch.setattr(sys, "argv", [str(_CHECK_SCRIPT), "--strict"])
    assert module.main() == 1
    assert message in capsys.readouterr().out


def test_hi_presets_removed_anchor_with_rule_is_rejected(monkeypatch, capsys, tmp_path):
    """声明移除的锚点若在推送规则里还在（规则被加回），检查必须打红。"""
    rules = json.loads((_BACKEND / "data" / "formula_push_rules.json").read_text(encoding="utf-8"))
    rules["rules"].append({"rule_id": "I5.1_tb_amount", "target": {"domain": "workpaper", "item_id": "I5-1-tb-amount"}})
    planted = tmp_path / "rules.json"
    planted.write_text(json.dumps(rules, ensure_ascii=False), encoding="utf-8")
    module = _load_check_module(tmp_path)
    monkeypatch.setattr(module, "RULES_PATH", planted)
    monkeypatch.setattr(sys, "argv", [str(_CHECK_SCRIPT), "--strict"])
    assert module.main() == 1
    assert "仍有推送规则" in capsys.readouterr().out


# ── 7. 双族并取：附注主表只出一行 ──────────────────────────────────────────────


@pytest.mark.parametrize("wp_code, codes, name", [
    ("H8", ("1641", "1651"), "使用权资产"),
    ("H9", ("2601", "2651"), "租赁负债"),
])
def test_dual_family_note_rows_merge_into_one_row(wp_code: str, codes: tuple[str, str], name: str):
    """双族科目是同一报表项目的互斥写法（逐项目只用一族）：附注主表出一行（各码合计）+ 同值合计行。

    每码各出一行时两行都对上附注同一行 ⇒ 撞行、一格都不写（和平药房_2025 使用权资产附注推成 0 即此）。
    """
    from decimal import Decimal

    from app.services.formula_push.bindings.balance_adj import binding_for

    binding = binding_for(wp_code)
    binding._last_tb_data = {
        codes[0]: {"期末余额": Decimal("100"), "年初余额": Decimal("40")},
        codes[1]: {"期末余额": Decimal("176203072.87"), "年初余额": Decimal("242642143.01")},
    }
    rule = next(r for r in load_rules() if r.rule_id == f"{wp_code}.note.main")
    rows = binding.note_rows({}, "soe", rule)
    data = [r for r in rows if not r["is_total"]]
    assert [r["label"] for r in data] == [name]
    assert data[0]["ending"] == pytest.approx(176203172.87) and data[0]["opening"] == pytest.approx(242642183.01)
    assert data[0]["ending_resolved"] and data[0]["opening_resolved"]
    totals = [r for r in rows if r["is_total"]]
    assert len(totals) == 1 and totals[0]["ending"] == data[0]["ending"]


def test_non_dual_family_multi_code_note_rows_are_not_merged():
    """不是双族的多科目底稿（I1 原价 / 累计摊销 / 减值准备）不按双族并成一行：按四段合计各出一行，备抵按减项
    （spec formula-fetch-followup-defect-closure R6.3；原先各码一行 + 正数合计行）。"""
    from decimal import Decimal

    from app.services.formula_push.bindings.balance_adj import binding_for

    binding = binding_for("I1")
    binding._last_tb_data = {c: {"期末余额": Decimal("1"), "年初余额": Decimal("1")} for c in ("1701", "1702", "1703")}
    rule = next(r for r in load_rules() if r.rule_id == "I1.note.main")
    rows = binding.note_rows({}, "soe", rule)
    assert [r["ending"] for r in rows] == [1.0, 1.0, 1.0, -1.0]
    assert not [r for r in rows if r["is_total"]]


def test_bindings_without_account_must_state_reason():
    """没有科目又没写原因的 binding 构造即报错（防止把「取不到科目」静默当成「推 0」）。"""
    from app.services.formula_push.bindings.balance_adj import AdjudicationSpec, BalanceAdjudicationBinding
    from app.services.formula_push.bindings.note_direct import NoteDirectBinding

    with pytest.raises(ValueError, match="no_account_reason"):
        BalanceAdjudicationBinding(AdjudicationSpec(wp_code="X1", account_codes=(), sheet_code="X1-1"))
    with pytest.raises(ValueError, match="no_account_reason"):
        NoteDirectBinding("X2", (), "某科目")
    # 写明原因即可构造，且不提供附注主表派生
    ok = NoteDirectBinding("X3", (), "某科目", no_account_reason="没有标准科目")
    assert ok.no_account_reason and ok.derivations == frozenset()
