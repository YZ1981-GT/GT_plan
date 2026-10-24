"""按试算表科目选底稿（全链路「生成底稿」步骤）：开关码表 + 真实映射表的匹配结果。

映射表科目码改正后，这一读取方的行为随之改变（M5 不再被本年利润触发、J2 / M10 / H8 / H9 可被触发、L7 / M8 不再按科目触发、
G6 / G8 各自只被自己的科目触发、K2 不再被无形资产触发）；租赁 / 研发两个条件开关原先取错码（1631 油气资产、2802 全库不存在、
5401 主营业务成本）。这里用字面量期望值逐个钉住，期望值不从被测代码派生。

spec: .kiro/specs/formula-fetch-followup-defect-closure/ R1.6
"""
from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from app.services.wp_generation_matching import TB_ACCOUNT_FLAGS, match_workpapers, tb_account_flags

_BACKEND = Path(__file__).resolve().parents[1]
_MAPPING = json.loads((_BACKEND / "data" / "wp_account_mapping.json").read_text(encoding="utf-8"))["mappings"]
_ORCHESTRATOR = _BACKEND / "app" / "services" / "chain_orchestrator.py"


def _triggered_by(tb_accounts: set[str]) -> set[str]:
    """只由这些科目（及其打开的开关）带出的主编码：扣掉空试算表也会生成的（must_have 等）。"""
    base, _ = match_workpapers(_MAPPING, set(), {})
    matched, _ = match_workpapers(_MAPPING, tb_accounts, tb_account_flags(tb_accounts))
    return matched - base


@pytest.mark.parametrize(
    ("tb_accounts", "expected"),
    [
        ({"4103"}, set()),  # 本年利润：不再触发 M5 盈余公积
        ({"4101"}, {"M5", "M5A"}),  # 盈余公积
        ({"4002"}, {"M4", "M4A"}),  # 资本公积
        ({"4201"}, {"M3", "M3A"}),  # 库存股
        ({"4301"}, {"M7", "M7A"}),  # 专项储备（不再触发 M8 一般风险准备）
        ({"4003"}, {"M9", "M9A"}),  # 其他综合收益
        ({"4401"}, {"M10", "M10A"}),  # 其他权益工具（不再触发 M9）
        ({"2705"}, {"J2", "J2A"}),  # 长期应付职工薪酬
        ({"2611"}, set()),  # 旧错码，全库不存在
        ({"2711"}, {"L6"}),  # 专项应付款（不再触发 J3 股份支付）
        ({"2801"}, {"K5"}),  # 预计负债（不再触发 L7 其他非流动负债）
        ({"1901"}, {"K2"}),  # 其他流动资产（报表 BS-014 取 1901）
        ({"1701"}, {"I1", "I1A", "C8"}),  # 无形资产（不再触发 K2）
        ({"1506"}, {"G6"}),  # 其他债权投资
        ({"1507"}, {"G8"}),  # 其他权益工具投资
        ({"1503"}, set()),  # 旧准则可供出售金融资产：要人工拆分，不自动归入 G6 / G8
        ({"1641"}, {"H8", "C14"}),  # 使用权资产（含租赁循环控制测试）
        ({"1651"}, {"H8", "C14"}),
        ({"2601"}, {"H9", "C14"}),  # 租赁负债
        ({"2651"}, {"H9", "C14"}),
        ({"1631"}, {"H5"}),  # 油气资产：不再打开租赁开关
        ({"2802"}, set()),
        ({"6604"}, {"I6", "C9"}),  # 研发费用
        ({"1704"}, {"I2", "I6", "C9"}),  # 开发支出（I6-3 资本化费用化分类同看开发支出）
        ({"5401"}, set()),  # standard 侧是主营业务成本：不再打开研发开关
        ({"5301"}, set()),  # 两套科目表里分别是研发支出 / 营业外收入：不用
    ],
)
def test_workpapers_triggered_by_accounts(tb_accounts, expected):
    assert _triggered_by(tb_accounts) == expected


def test_condition_flag_codes():
    flagged = {code: flag for code, flag in TB_ACCOUNT_FLAGS.items() if flag in ("has_lease", "has_rd")}
    assert flagged == {
        "1641": "has_lease", "1651": "has_lease", "2601": "has_lease", "2651": "has_lease",
        "6604": "has_rd", "1704": "has_rd",
    }
    assert tb_account_flags({"1631", "2802", "5401", "5301"}) == {}


def test_subtable_hits_collapse_to_primary():
    matched, subtables = match_workpapers(_MAPPING, {"1506"}, {})
    assert "G6" in matched and "G6-1" not in matched
    assert {"G6-1", "G6-2"} <= set(subtables["G6"])


def _function_node(tree: ast.AST, name: str) -> ast.AST:
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    raise AssertionError(f"chain_orchestrator 里找不到 {name}")


def test_orchestrator_uses_the_shared_rules():
    """生成底稿步骤必须调用本模块，不得在函数体里另写一份科目码表。"""
    fn = _function_node(ast.parse(_ORCHESTRATOR.read_text(encoding="utf-8")), "_step_generate_workpapers")
    called = {n.func.id for n in ast.walk(fn) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    assert {"match_workpapers", "tb_account_flags"} <= called
    inline_code_keys = [
        k.value
        for d in ast.walk(fn)
        if isinstance(d, ast.Dict)
        for k in d.keys
        if isinstance(k, ast.Constant) and isinstance(k.value, str) and k.value.isdigit() and len(k.value) == 4
    ]
    assert inline_code_keys == [], f"函数体里另写了科目码表：{inline_code_keys}"


def test_inline_table_check_would_catch_a_planted_table():
    """自检：同一判据对植入的码表打红（证明上一条不是恒绿）。"""
    planted = "async def _step_generate_workpapers(self):\n    flags = {'1631': 'has_lease'}\n    return match_workpapers(1, 2, 3)\n"
    fn = _function_node(ast.parse(planted), "_step_generate_workpapers")
    keys = [k.value for d in ast.walk(fn) if isinstance(d, ast.Dict) for k in d.keys if isinstance(k, ast.Constant)]
    assert keys == ["1631"]
