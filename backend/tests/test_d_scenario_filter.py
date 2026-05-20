"""scenario 文件级过滤纯函数单测（spec workpaper-d-sales-cycle 任务 2.3 / F4）。

Validates: Requirements F4（D 销售循环 spec — scenario 字段驱动 D4 IPO 应对裁剪）
ADR: D4（5 档 scenario 通用文件级裁剪规则）

覆盖 5 档 scenario：
  - normal: 排除 IPO/上市/新三板/重组/舞弊应对/舞弊/反舞弊 关键字命中文件
  - ipo / listed / transfer / restructure / fraud_response: 加载全部

测试 ``_filter_files_by_scenario`` 纯函数行为（不涉及 DB / 文件 IO），
导入路径走 spec 任务 2.1 文本约定 ``app.services.chain_orchestrator``
（实际定义位于 ``wp_template_init_service``，re-export 经 chain_orchestrator）。
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.services.chain_orchestrator import (
    SCENARIO_TO_FILE_FILTER,
    _filter_files_by_scenario,
)


# ---------------------------------------------------------------------------
# 辅助：构造 Path 列表
# ---------------------------------------------------------------------------


def _paths(*names: str) -> list[Path]:
    """构造模板路径列表（仅用文件名做过滤匹配，目录前缀仅为可读性）。"""
    return [Path("D") / n for n in names]


# ---------------------------------------------------------------------------
# 1. normal 场景排除 IPO 关键字
# ---------------------------------------------------------------------------


def test_normal_excludes_ipo_files() -> None:
    """normal 场景：包含 'IPO' 关键字的文件应被排除。"""
    inputs = _paths(
        "D2-1 应收账款审定表.xlsx",                   # 保留
        "D4-22至D4-32营业收入-IPO 上市 新三板.xlsx",  # 排除（含 IPO）
    )
    out = _filter_files_by_scenario(inputs, "normal")

    assert len(out) == 1, f"应保留 1 个清洁文件，实际 {len(out)}: {out}"
    assert out[0].name == "D2-1 应收账款审定表.xlsx"
    assert all("IPO" not in p.name for p in out)


# ---------------------------------------------------------------------------
# 2. parametrize 5 个排除关键字（IPO / 上市 / 新三板 / 重组 / 舞弊应对）
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "keyword",
    ["IPO", "上市", "新三板", "重组", "舞弊应对"],
)
def test_normal_excludes_all_keyword_categories(keyword: str) -> None:
    """normal 场景：5 大排除关键字各自命中时都应被过滤。"""
    clean_file = "D2-1 应收账款审定表.xlsx"
    dirty_file = f"D4-99 含{keyword}应对场景.xlsx"

    inputs = _paths(clean_file, dirty_file)
    out = _filter_files_by_scenario(inputs, "normal")

    assert [p.name for p in out] == [clean_file], (
        f"keyword={keyword!r} 未被过滤：out={[p.name for p in out]}"
    )


# ---------------------------------------------------------------------------
# 3-6. 其他 4 档 scenario 应加载全部文件（不过滤）
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "scenario",
    ["ipo", "listed", "restructure", "fraud_response"],
)
def test_non_normal_scenarios_load_all_files(scenario: str) -> None:
    """ipo / listed / restructure / fraud_response 加载全部 17 文件（含 IPO 应对）。"""
    inputs = _paths(
        "D2-1 应收账款审定表.xlsx",
        "D4-22至D4-32营业收入-IPO 上市 新三板 重组 舞弊应对.xlsx",
        "D7-1 合同负债审定表.xlsx",
        "D4-30 客户访谈记录-上市公司.xlsx",
        "D5 应收款项融资审定表-新三板.xlsx",
    )
    out = _filter_files_by_scenario(inputs, scenario)

    assert len(out) == len(inputs), (
        f"scenario={scenario} 不应过滤任何文件，输入 {len(inputs)}，输出 {len(out)}"
    )
    assert [p.name for p in out] == [p.name for p in inputs], (
        f"scenario={scenario} 应保持原顺序"
    )


def test_ipo_loads_all_files() -> None:
    """显式覆盖 ipo 档：含 IPO 关键字的 D4-22A 文件应被保留。"""
    inputs = _paths(
        "D2-1 应收账款审定表.xlsx",
        "D4-22至D4-32营业收入-IPO 上市 新三板 重组 舞弊应对.xlsx",
    )
    out = _filter_files_by_scenario(inputs, "ipo")
    assert len(out) == 2
    assert any("IPO" in p.name for p in out), "ipo 档必须保留含 IPO 的文件"


def test_listed_loads_all_files() -> None:
    """显式覆盖 listed 档：含 上市 关键字的文件应被保留。"""
    inputs = _paths(
        "D2-1 应收账款审定表.xlsx",
        "D4-30 客户访谈-上市公司.xlsx",
    )
    out = _filter_files_by_scenario(inputs, "listed")
    assert len(out) == 2
    assert any("上市" in p.name for p in out)


def test_restructure_loads_all_files() -> None:
    """显式覆盖 restructure 档：含 重组 关键字的文件应被保留。"""
    inputs = _paths(
        "D2-1 应收账款审定表.xlsx",
        "D4-29 重组背景下的收入确认.xlsx",
    )
    out = _filter_files_by_scenario(inputs, "restructure")
    assert len(out) == 2
    assert any("重组" in p.name for p in out)


def test_fraud_response_loads_all_files() -> None:
    """显式覆盖 fraud_response 档：含 舞弊应对 关键字的文件应被保留。"""
    inputs = _paths(
        "D2-1 应收账款审定表.xlsx",
        "D4-32 舞弊应对程序.xlsx",
    )
    out = _filter_files_by_scenario(inputs, "fraud_response")
    assert len(out) == 2
    assert any("舞弊应对" in p.name for p in out)


# ---------------------------------------------------------------------------
# 7. 未知 scenario 退化为 normal（保守过滤）
# ---------------------------------------------------------------------------


def test_unknown_scenario_falls_back_to_normal() -> None:
    """未知 scenario（如 'unknown' / 'garbage'）应退化走 normal 排除规则，
    避免误把 IPO 应对文件加载到不熟悉的项目场景。"""
    inputs = _paths(
        "D2-1 应收账款审定表.xlsx",
        "D4-22至D4-32营业收入-IPO 上市.xlsx",
    )
    out_unknown = _filter_files_by_scenario(inputs, "unknown")
    out_normal = _filter_files_by_scenario(inputs, "normal")

    assert [p.name for p in out_unknown] == [p.name for p in out_normal], (
        "未知 scenario 必须与 normal 过滤结果一致"
    )
    assert len(out_unknown) == 1
    assert "IPO" not in out_unknown[0].name


# ---------------------------------------------------------------------------
# 8. 空输入
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "scenario",
    ["normal", "ipo", "listed", "transfer", "restructure", "fraud_response", "unknown"],
)
def test_empty_file_paths_returns_empty(scenario: str) -> None:
    """空路径列表对所有 scenario 都应返回空列表。"""
    out = _filter_files_by_scenario([], scenario)
    assert out == [], f"scenario={scenario} 空输入应返回 []，实际 {out}"


# ---------------------------------------------------------------------------
# 9. 普通文件名（无任何排除关键字）应全部保留
# ---------------------------------------------------------------------------


def test_no_keyword_match_passes_through() -> None:
    """文件名不含任何排除关键字时，normal 档亦应全部保留。"""
    inputs = _paths(
        "D1-1 销售与收款循环风险评估.xlsx",
        "D2-1 应收账款审定表.xlsx",
        "D3-1 合同审计程序.xlsx",
        "D4-1 营业收入审计程序表.xlsx",
        "D5 应收款项融资审定表.xlsx",
        "D6 合同资产审定表.xlsx",
        "D7 合同负债审定表.xlsx",
    )
    out = _filter_files_by_scenario(inputs, "normal")
    assert len(out) == len(inputs), (
        f"清洁文件不应被过滤：输入 {len(inputs)}，输出 {len(out)}"
    )
    assert [p.name for p in out] == [p.name for p in inputs]


# ---------------------------------------------------------------------------
# 10. 部分匹配（关键字作为子串出现在文件名中）应被排除
# ---------------------------------------------------------------------------


def test_partial_match_excluded() -> None:
    """关键字作为文件名子串出现（非全名）时也应被排除。

    覆盖现实模板命名场景，如 'D4-22 营业收入 IPO 应对.xlsx'（IPO 子串）。
    """
    inputs = _paths(
        "D4-22 营业收入 IPO 应对.xlsx",          # 子串 IPO
        "D4-30 上市公司客户访谈.xlsx",            # 子串 上市
        "D4-25 新三板挂牌应对.xlsx",              # 子串 新三板
        "D4-29 重组背景下的收入确认.xlsx",        # 子串 重组
        "D4-32 反舞弊应对程序.xlsx",              # 子串 舞弊应对（同时也命中"反舞弊"/"舞弊"）
        "D2-1 应收账款审定表.xlsx",               # 保留
    )
    out = _filter_files_by_scenario(inputs, "normal")

    assert [p.name for p in out] == ["D2-1 应收账款审定表.xlsx"], (
        f"5 个含关键字的文件应全部被过滤，实际保留：{[p.name for p in out]}"
    )


# ---------------------------------------------------------------------------
# 11. 过滤后保持原顺序
# ---------------------------------------------------------------------------


def test_filter_preserves_order() -> None:
    """过滤前后文件顺序应保持稳定（不做 sort / reverse）。"""
    inputs = _paths(
        "D7 合同负债审定表.xlsx",
        "D4-22 IPO 应对.xlsx",                    # 排除
        "D2-1 应收账款审定表.xlsx",
        "D4-30 上市公司客户访谈.xlsx",            # 排除
        "D6 合同资产审定表.xlsx",
        "D1-1 销售与收款循环风险评估.xlsx",
    )
    out = _filter_files_by_scenario(inputs, "normal")

    assert [p.name for p in out] == [
        "D7 合同负债审定表.xlsx",
        "D2-1 应收账款审定表.xlsx",
        "D6 合同资产审定表.xlsx",
        "D1-1 销售与收款循环风险评估.xlsx",
    ]


# ---------------------------------------------------------------------------
# 12. SCENARIO_TO_FILE_FILTER 字典本身的 schema 校验（防止配置漂移）
# ---------------------------------------------------------------------------


def test_scenario_dict_contains_six_required_keys() -> None:
    """SCENARIO_TO_FILE_FILTER 必须包含 6 档 scenario 配置。"""
    expected_keys = {"normal", "ipo", "listed", "transfer", "restructure", "fraud_response"}
    actual_keys = set(SCENARIO_TO_FILE_FILTER.keys())
    assert expected_keys.issubset(actual_keys), (
        f"缺失 scenario 键：{expected_keys - actual_keys}"
    )


def test_normal_exclude_patterns_cover_required_keywords() -> None:
    """normal 档的 exclude_patterns 必须覆盖 5 大业务关键字（IPO/上市/新三板/重组/舞弊应对）。"""
    rules = SCENARIO_TO_FILE_FILTER.get("normal", {})
    patterns = rules.get("exclude_patterns") or []

    required = ["IPO", "上市", "新三板", "重组", "舞弊应对"]
    missing = [kw for kw in required if kw not in patterns]
    assert not missing, f"normal 排除关键字缺失：{missing}"
