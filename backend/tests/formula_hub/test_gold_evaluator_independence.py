"""金标准求值器独立性守卫（spec formula-hub-integrity-closure 任务 17；需求 5.4；ADR-FHIC-24）。不连库。

``tests/formula_hub/gold_report_evaluator.py`` 只许 import 标准库、``sqlalchemy`` 与测试夹具（``tests.formula_hub._pg_harness``）：

- AST 逐个核对 ``import`` / ``from … import``（含函数体内）的来源；ADR 点名的六个生产模块（报表引擎、取数器、叶子、逐行计算、
  L1 内核、预载）单独报名字；相对导入、``importlib``、``__import__`` / ``import_module``、``sys.modules``、``exec`` / ``eval``
  一律算违规（绕开 import 语句取模块的写法）；
- 扫描器自检：违规样本逐条必报、干净样本不报；
- 子进程只导入该文件，``sys.modules`` 里不得出现 ``app`` 包（探针自检：导入 ``app`` 时必须报出来）。

另两条让真库守卫的「未识别 0 条」与比对不空转：扫描没出现过的语法样本逐条记为未识别、出现过的四种形态能解析；
小样本口径（叶子、两个列名、求值顺序、``ROW`` 未算出、``SUM_ROW`` 同表区间、宽集合全部相加的对照值）与手算一致。
"""
from __future__ import annotations

import ast
import os
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

import pytest

from tests.formula_hub import gold_report_evaluator as gold

GOLD = Path(__file__).with_name("gold_report_evaluator.py")
BACKEND = GOLD.resolve().parents[2]
#: ADR-FHIC-24 点名禁止的生产模块
FORBIDDEN = (
    "app.services.report_engine", "app.services.amount_resolver", "app.services.tb_leaf_codes",
    "app.services.report_row_compute", "app.services.formula_engine", "app.services.formula_preloader",
)
#: 允许导入的测试夹具模块
FIXTURES = frozenset({"tests.formula_hub._pg_harness"})
_DYNAMIC_NAMES = frozenset({"__import__", "import_module"})
_DYNAMIC_CALLS = frozenset({"exec", "eval"})


def _named(module: str) -> str | None:
    return next((f for f in FORBIDDEN if module == f or module.startswith(f + ".")), None)


def violations(source: str) -> list[str]:
    """违规清单（空 = 合规）。"""
    found: list[str] = []

    def check(module: str, line: int) -> None:
        root = module.partition(".")[0]
        hit = _named(module)
        if hit:
            found.append(f"第 {line} 行导入生产模块 {hit}")
        elif root == "importlib":
            found.append(f"第 {line} 行导入 importlib（动态取模块）")
        elif not (root in ("__future__", "sqlalchemy") or module in FIXTURES or root in sys.stdlib_module_names):
            found.append(f"第 {line} 行导入 {module}（只许标准库、sqlalchemy 与测试夹具）")

    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            for alias in node.names:
                check(alias.name, node.lineno)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                found.append(f"第 {node.lineno} 行相对导入")
                continue
            module = node.module or ""
            check(module, node.lineno)
            for alias in node.names:  # from app.services import tb_leaf_codes：拼上被导入名再认一次点名模块
                hit = _named(f"{module}.{alias.name}")
                if hit and not _named(module):
                    found.append(f"第 {node.lineno} 行导入生产模块 {hit}")
        elif isinstance(node, ast.Name) and node.id in _DYNAMIC_NAMES:
            found.append(f"第 {node.lineno} 行使用 {node.id}（动态取模块）")
        elif isinstance(node, ast.Attribute) and node.attr in _DYNAMIC_NAMES:
            found.append(f"第 {node.lineno} 行使用 .{node.attr}（动态取模块）")
        elif isinstance(node, ast.Attribute) and node.attr == "modules" and getattr(node.value, "id", None) == "sys":
            found.append(f"第 {node.lineno} 行读 sys.modules")
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _DYNAMIC_CALLS:
            found.append(f"第 {node.lineno} 行调用 {node.func.id}()")
    return found


def _imported(source: str) -> set[str]:
    out: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            out.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            out.add(node.module)
    return out


VIOLATING = {
    "import app.services.report_engine": "生产模块 app.services.report_engine",
    "from app.services import amount_resolver": "生产模块 app.services.amount_resolver",
    "from app.services.tb_leaf_codes import leaf_code_set": "生产模块 app.services.tb_leaf_codes",
    "def f():\n    from app.services.report_row_compute import compute_row\n": "生产模块 app.services.report_row_compute",
    "import app.services.formula_engine as fe": "生产模块 app.services.formula_engine",
    "from app.services import formula_preloader as fp": "生产模块 app.services.formula_preloader",
    "from app.models.report_models import FinancialReport": "导入 app.models.report_models",
    "import numpy": "导入 numpy",
    "from . import _report_compute_world": "相对导入",
    "from tests.formula_hub import _report_compute_world": "导入 tests.formula_hub",
    "import importlib\nimportlib.import_module('json')": "importlib",
    "__import__('json')": "使用 __import__",
    "import sys\nsys.modules.get('json')": "sys.modules",
    "exec('import json')": "调用 exec()",
}
CLEAN = [
    "from __future__ import annotations",
    "import re\nfrom decimal import Decimal\nfrom dataclasses import dataclass, field",
    "import sqlalchemy as sa\nfrom sqlalchemy import text",
    "from tests.formula_hub._pg_harness import SNAPSHOT_PREFIX",
    "'''说明里提到 app.services.report_engine 不算导入'''\nNOTE = 'app.services.tb_leaf_codes'",
    "def f():\n    import json\n    return json.dumps({})",
]


def test_gold_imports_only_allowed():
    source = GOLD.read_text(encoding="utf-8")
    assert violations(source) == []
    assert {"decimal", "sqlalchemy"} <= _imported(source), _imported(source)  # 扫描器确实看到了导入（不空转）
    missing = [f for f in FORBIDDEN if not (BACKEND / (f.replace(".", "/") + ".py")).is_file()]
    assert missing == [], f"禁止清单里的模块不存在（名字写错会让守卫空转）：{missing}"


@pytest.mark.parametrize("source, expected", list(VIOLATING.items()))
def test_scanner_reports_violation(source, expected):
    found = violations(source)
    assert any(expected in item for item in found), found


@pytest.mark.parametrize("source", CLEAN)
def test_scanner_accepts_clean(source):
    assert violations(source) == []


_PROBE = ("import sys, importlib; importlib.import_module(sys.argv[1]); "
          "print('APP=' + ','.join(sorted(m for m in sys.modules if m == 'app' or m.startswith('app.'))))")


def _loaded_app_modules(module: str) -> list[str]:
    """新进程里只导入 ``module`` 后已加载的 ``app`` 包模块（cwd = backend，不连库）。"""
    env = {k: v for k, v in os.environ.items() if k not in {"DATABASE_URL", "GT_REQUIRE_PG"}}
    env["PYTHONIOENCODING"] = "utf-8"
    proc = subprocess.run([sys.executable, "-c", _PROBE, module], cwd=BACKEND, env=env, capture_output=True,
                          text=True, encoding="utf-8", errors="replace", timeout=120)
    assert proc.returncode == 0, (proc.stderr or "")[-2000:]
    lines = [line for line in (proc.stdout or "").splitlines() if line.startswith("APP=")]
    assert len(lines) == 1, proc.stdout
    return [name for name in lines[0][len("APP="):].split(",") if name]


def test_import_loads_no_app_modules():
    assert _loaded_app_modules("tests.formula_hub.gold_report_evaluator") == []
    assert "app" in _loaded_app_modules("app"), "探针自检：导入 app 包时应能看到它"


#: 扫描没出现过的语法：逐条必须记为未识别（守卫「未识别 0 条」不空转）
UNSUPPORTED = [
    "TB('1001', '期末余额')", "TB('1001','期末余额')*2", "TB('1001','期末余额')/TB('1002','期末余额')",
    "TB('1001','期末余额')+100", "-TB('1001','期末余额')", "(TB('1001','期末余额'))", "ABS(TB('1001','期末余额'))",
    "TB('1001','未审数')", 'TB("1001","期末余额")', "TB('1001'，'期末余额')", "SUM_TB('1001','期末余额')",
    "ROW('BS-001','BS-002')", "TB('1001','期末余额'", "TB('1001','期末余额')TB('1002','期末余额')",
]
SUPPORTED = [
    "TB('1122','期末余额')-TB('1231','期末余额')", "SUM_TB('1400~1499','期末余额')", "SUM_ROW('BS-002','BS-026')",
    "ROW('BS-027')+ROW('BS-052')", "TB('6001','本期发生额')",
]


@pytest.mark.parametrize("formula", UNSUPPORTED)
def test_unsupported_syntax_is_unrecognized(formula):
    with pytest.raises(gold.Unrecognized):
        gold.parse(formula)


@pytest.mark.parametrize("formula", SUPPORTED)
def test_supported_syntax_parses(formula):
    assert gold.calls_of(gold.parse(formula))


def _d(value: str) -> Decimal:
    return Decimal(value)


_TB = [gold.TbRow(code, _d(audited), None if opening is None else _d(opening)) for code, audited, opening in [
    ("1122", "500", "0"), ("1231", "-100", "-30"), ("1231-01", "-60", "-20"), ("1231-02", "-40", "-10"),
    ("1401", "70", None), ("1499", "5", "1"), ("1499-01", "3", "1"), ("1500", "999", "0"),
    ("6001", "1000", "200"), ("6001", "50", None),
]]
_CONFIGS = [gold.ConfigRow(rt, code, num, formula) for rt, code, num, formula in [
    ("income_statement", "IS-001", 1, "TB('6001','本期发生额')"),
    ("balance_sheet", "BS-003", 3, "SUM_ROW('BS-001','BS-002')"),
    ("balance_sheet", "BS-001", 1, "TB('1122','期末余额')-TB('1231','期末余额')"),
    ("balance_sheet", "BS-002", 2, None),
    ("balance_sheet", "BS-004", 4, "ROW('BS-005')"),
    ("balance_sheet", "BS-005", 5, "SUM_TB('1400~1499','期末余额')"),
    ("balance_sheet", "BS-006", 6, "ROW('BS-099')"),
    ("balance_sheet", "BS-007", 7, "SUM_ROW('BS-004','BS-005')"),
    ("income_statement", "IS-002", 2, "ROW('BS-003')+SUM_ROW('IS-001','IS-001')"),
]]


def test_gold_semantics_on_small_sample():
    result = gold.evaluate(_CONFIGS, _TB)
    values = {code: v.value for (_, code), v in result.values.items()}
    assert result.unrecognized == []
    # 叶子：1231 父行不计（−60 − 40）；本期发生额 = 审定 − 期初、同码两行都计（800 + 50）；SUM_TB 止码下级并入、父行 1499 与
    # 区间外 1500 不计；IS 在 BS 之后求值可引用 BS-003；BS-004 引用后算的 BS-005、BS-007 区间含不可算的 BS-004 ⇒ 不可算
    assert values == {"BS-001": _d("600"), "BS-002": _d("0"), "BS-003": _d("600"), "BS-004": None, "BS-005": _d("73"),
                      "BS-006": None, "BS-007": None, "IS-001": _d("850"), "IS-002": _d("1450")}
    reasons = {code: v.reason for (_, code), v in result.values.items() if v.value is None}
    assert reasons == {"BS-004": "引用行 BS-005 未算出", "BS-006": "引用行 BS-099 在定义里不存在",
                       "BS-007": "引用行 BS-004 未算出"}
    doubled = gold.evaluate(_CONFIGS, _TB, leaves_only=False)
    assert {code: v.value for (_, code), v in doubled.values.items() if code in ("BS-001", "BS-003", "BS-005")} == {
        "BS-001": _d("700"), "BS-003": _d("700"), "BS-005": _d("78")}
    assert gold.mixed_family_refs(_CONFIGS[2].formula, _TB) == ["TB('1231')"]
    assert gold.mixed_family_refs("SUM_TB('1400~1499','期末余额')", _TB) == ["SUM_TB('1400~1499')"]
    assert gold.mixed_family_refs("TB('1122','期末余额')", _TB) == []


def test_unrecognized_rows_are_collected_not_evaluated():
    rows = [gold.ConfigRow("balance_sheet", "BS-001", 1, "TB('1122','期末余额')*2"),
            gold.ConfigRow("balance_sheet", "BS-001", 2, "TB('1122','期末余额')"),
            gold.ConfigRow("notes", "NT-001", 1, "TB('1122','期末余额')")]
    result = gold.evaluate(rows, _TB)
    assert len(result.unrecognized) == 3, result.unrecognized  # 乘号、同表行次重复、报表类型不在求值顺序里
    assert result.values[("balance_sheet", "BS-001")].value is None
