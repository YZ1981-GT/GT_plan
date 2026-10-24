"""M 循环（股东权益）科目码 / 报表行单一来源守卫。

spec: .kiro/specs/formula-fetch-followup-defect-closure/ R1.4

2026-10-24 前 M 循环后端各处写死的码各自错位：
- M3 服务 tb-seed 取 4002（客户科目表里是资本公积）；
- M4 / M5 / M7 / M9 render 的溯源报表行指向别的行（BS-079 国企是持有待售负债、BS-083 是资本公积、
  BS-082 是其他权益工具、BS-081 是实收资本）；
- M9 回写请求默认 4103（本年利润）；
- phase5 元数据写 4102 / 4104 / 4103 / 4001。

单一来源 = ``four_table/m_cycle_specs``（兜底码经客户科目表逐项实证），前端
``mCycleAccountScope.ts`` 由 vitest 守卫逐项比对同一张表。本文件锁后端：
1. 兜底码 / 报表行与实证值一致（独立判据，写成字面量）；
2. render 策略、服务、路由、phase5 元数据取值 = 单一来源；
3. M 循环后端文件里不再写 4xxx / 3xxx / 2232 码字面量（phase5 元数据除外，由第 2 条逐值核对）。
"""
from __future__ import annotations

import ast
import importlib
import re
from pathlib import Path

import pytest

from app.services.four_table.m_cycle_specs import M_CYCLE_SPECS, fallback_code_of, row_code_of

APP = Path(__file__).resolve().parents[2] / "app"

#: 客户科目表实证（design §1）。M8 一般风险准备没有标准科目。
EXPECTED_CODE = {
    "M1": "2232", "M2": "4001", "M3": "4201", "M4": "4002", "M5": "4101",
    "M6": "4104", "M7": "4301", "M8": "", "M9": "4003", "M10": "4401",
}
#: report_config 四个准则同号同名（2026-10-24 现查）
EXPECTED_ROW = {"M4": "BS-083", "M5": "BS-087", "M7": "BS-086", "M9": "BS-085"}


@pytest.mark.parametrize("wp", sorted(EXPECTED_CODE))
def test_fallback_code_matches_evidence(wp):
    assert fallback_code_of(wp) == EXPECTED_CODE[wp]


def test_specs_cover_m1_to_m10_and_unknown_raises():
    assert set(M_CYCLE_SPECS) == set(EXPECTED_CODE)
    with pytest.raises(KeyError):
        fallback_code_of("X1")
    with pytest.raises(KeyError):
        row_code_of("")


_RENDER = "app.routers.wp_render_strategies."

#: (模块, 属性, 循环, 种类)
_CONSTANT_SITES = [
    (_RENDER + "_m3_treasury_stock", "_M3_ACCOUNT_CODE", "M3", "code"),
    (_RENDER + "_m4_capital_reserve", "_M4_ACCOUNT_CODE", "M4", "code"),
    (_RENDER + "_m4_capital_reserve", "_M4_ROW_CODE", "M4", "row"),
    (_RENDER + "_m5_surplus_reserve", "_M5_ACCOUNT_CODE", "M5", "code"),
    (_RENDER + "_m5_surplus_reserve", "_M5_ROW_CODE", "M5", "row"),
    (_RENDER + "_m6_retained_earnings", "M6_ACCOUNT_CODE", "M6", "code"),
    (_RENDER + "_m7_special_reserve", "_M7_ACCOUNT_CODE", "M7", "code"),
    (_RENDER + "_m7_special_reserve", "_M7_ROW_CODE", "M7", "row"),
    (_RENDER + "_m9_other_comprehensive_income", "_M9_ACCOUNT_CODE", "M9", "code"),
    (_RENDER + "_m9_other_comprehensive_income", "_M9_ROW_CODE", "M9", "row"),
    (_RENDER + "_m10_other_equity_instruments", "_M10_ACCOUNT_CODE", "M10", "code"),
    ("app.services.m3_treasury_stock_service", "_M3_ACCOUNT_CODE", "M3", "code"),
    ("app.services.m4_capital_reserve_service", "_M4_ACCOUNT_CODE", "M4", "code"),
    ("app.services.m5_surplus_reserve_service", "_M5_ACCOUNT_CODE", "M5", "code"),
] + [
    (f"app.services.workpaper_sync.phase5_{name}", "ACCOUNT_CODE", wp, "code")
    for name, wp in (
        ("m2_paid_in_capital", "M2"), ("m3_treasury_stock", "M3"), ("m4_capital_reserve", "M4"),
        ("m5_surplus_reserve", "M5"), ("m6_retained_earnings", "M6"), ("m7_special_reserve", "M7"),
        ("m8_general_risk_reserve", "M8"), ("m9_other_comprehensive_income", "M9"),
        ("m10_other_equity_instruments", "M10"),
    )
]


@pytest.mark.parametrize("module,attr,wp,kind", _CONSTANT_SITES, ids=lambda v: str(v))
def test_constant_sites_equal_single_source(module, attr, wp, kind):
    value = getattr(importlib.import_module(module), attr)
    if kind == "code":
        assert value == fallback_code_of(wp) == EXPECTED_CODE[wp], f"{module}.{attr}"
    else:
        assert value == row_code_of(wp) == EXPECTED_ROW[wp], f"{module}.{attr}"


def test_m9_writeback_request_defaults_to_oci():
    """不传科目码时默认写其他综合收益（原默认 4103 本年利润 —— 会把 OCI 写进本年利润）。"""
    from app.routers.m9_other_comprehensive_income import TBWritebackRequest

    assert TBWritebackRequest(audited_amount=1.0).account_code == "4003"


def test_j3_cross_account_capital_reserve_is_4002():
    """J3 跨科目清单里的资本公积取 M4 口径（原写旧制 3002，现行科目表是「货币兑换」）。"""
    src = (APP / "routers/wp_render_strategies/_j3_share_based_payment.py").read_text(encoding="utf-8")
    assert '"3002"' not in src
    assert 'fallback_code_of("M4")' in src


# ── 字面量扫描 ────────────────────────────────────────────────────────────────

_LITERAL = re.compile(r"^(?:4\d{3}|3\d{3}|2232)(?:[-.]\d+)?$")


def _m_backend_files() -> list[Path]:
    rs = APP / "routers" / "wp_render_strategies"
    files = [p for p in rs.glob("_m*.py") if re.match(r"_m\d+_", p.name)]
    files += [p for p in (APP / "routers").glob("m*_*.py") if re.match(r"m\d+_", p.name)]
    files += [p for p in (APP / "services").glob("m*_service.py") if re.match(r"m\d+_", p.name)]
    files += [APP / "routers" / "wp_surfaced_m.py", APP / "services" / "equity_method_service.py"]
    return sorted(set(files))


def _docstring_nodes(tree: ast.AST) -> set[int]:
    out: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                out.add(id(first.value))
    return out


def _code_literals(src: str) -> list[tuple[int, str]]:
    tree = ast.parse(src)
    docs = _docstring_nodes(tree)
    return [
        (node.lineno, node.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
        and id(node) not in docs and _LITERAL.match(node.value)
    ]


def test_scan_covers_m_files():
    names = {p.name for p in _m_backend_files()}
    # 反向自检：扫描集合真的包含 M 循环的 render / 路由 / 服务（找不到 = 扫了空气）
    for must in ("_m3_treasury_stock.py", "_m9_other_comprehensive_income.py", "m3_treasury_stock.py",
                 "m9_other_comprehensive_income.py", "m3_treasury_stock_service.py", "wp_surfaced_m.py"):
        assert must in names, must
    assert len(names) >= 20


def test_scanner_catches_literals_but_not_docstrings():
    sample = '"""科目 4002"""\nA = "4002"\nB = {"account_code": "4104"}\nC = "BS-086"\n'
    assert [v for _, v in _code_literals(sample)] == ["4002", "4104"]


def test_no_code_literals_in_m_backend_files():
    bad = [
        f"{p.relative_to(APP).as_posix()}:{ln} {value!r}"
        for p in _m_backend_files()
        for ln, value in _code_literals(p.read_text(encoding="utf-8"))
    ]
    assert bad == [], "M 循环后端科目码只能取自 four_table.m_cycle_specs:\n" + "\n".join(bad)


# ── 全 app「科目名 ↔ 码」配对（文案 / 注释 / docstring / 字符串都算）─────────────

#: 名 → 正确码。'' = 没有统一码（不得与任何码配对）；'*' = 只为挡前缀误配、不校验
_NAME_CODE = {
    "实收资本": "4001", "股本": "4001", "资本公积": "4002", "其他综合收益": "4003",
    "盈余公积": "4101", "本年利润": "4103", "利润分配": "4104", "未分配利润": "4104",
    "库存股": "4201", "专项储备": "4301", "其他权益工具": "4401", "一般风险准备": "",
    "应付股利": "2232", "其他权益工具投资": "*",
}
_NAMES = "|".join(map(re.escape, sorted(_NAME_CODE, key=len, reverse=True)))
_CODE = r"(?<![\d.\-])(4\d{3}|3\d{3}|2232)(?!\d)"
_PAIRS = [
    (re.compile(_CODE + r"[ \t]*(?:-[ \t]*)?(" + _NAMES + r")"), True),
    (re.compile(r"(" + _NAMES + r")[ \t]*[（(][ \t]*" + _CODE + r"[ \t]*[)）]"), False),
]

#: 已知、暂不改的错配（逐条写原因；失效条目会打红）
_PAIR_ALLOWLIST = {
    ("services/workpaper_sync/phase5_m3_treasury_stock.py", "库存股", "4102"):
        "契约冻结文本 reviewed_basis（与磁盘契约逐字相等）；改它要重生成 m3 契约与 golden digest，"
        "登记 design §10（ACCOUNT_CODE 元数据已改 4201，构建器不读该文本）",
    ("services/workpaper_sync/phase5_m10_other_equity_instruments.py", "其他权益工具", "4001"):
        "契约冻结文本 reviewed_basis；同上（ACCOUNT_CODE 元数据已改 4401）",
}


def _pair_mismatches(text: str) -> list[tuple[str, str]]:
    out = []
    for pat, code_first in _PAIRS:
        for m in pat.finditer(text):
            code, name = (m.group(1), m.group(2)) if code_first else (m.group(2), m.group(1))
            want = _NAME_CODE[name]
            if want != "*" and code != want:
                out.append((name, code))
    return out


def test_pair_scanner_self_check():
    assert _pair_mismatches("科目4002库存股") == [("库存股", "4002")]
    assert _pair_mismatches("其他综合收益（4103）") == [("其他综合收益", "4103")]
    assert _pair_mismatches("4104 一般风险准备") == [("一般风险准备", "4104")]
    assert _pair_mismatches("贷记资本公积(3002)") == [("资本公积", "3002")]
    assert _pair_mismatches("4201 库存股 / 其他综合收益(4003) / 1503 其他权益工具投资") == []


def test_no_name_code_mismatch_in_backend_app():
    found: set[tuple[str, str, str]] = set()
    bad: list[str] = []
    for p in sorted(APP.rglob("*.py")):
        rel = p.relative_to(APP).as_posix()
        for name, code in _pair_mismatches(p.read_text(encoding="utf-8")):
            key = (rel, name, code)
            if key in _PAIR_ALLOWLIST:
                found.add(key)
                continue
            bad.append(f"{rel}: {name}<-{code}（应为 {_NAME_CODE[name] or '无统一码'}）")
    assert bad == [], "科目名与码错配:\n" + "\n".join(bad)
    assert found == set(_PAIR_ALLOWLIST), f"白名单失效条目（已修就删）：{sorted(set(_PAIR_ALLOWLIST) - found)}"
