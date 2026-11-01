"""利润表公式单一来源守卫（spec income-statement-lower-section-formulas，ADR-ISL-04；需求 R1、R4）。

权威文本只有一处：种子 ``backend/data/report_config_seed.json`` 四套利润表（design §2 按官方模板逐行核对后落库）。
``ReportFormulaService.fill_all_formulas`` 是第二写入方（只填公式为空的行）—— 它对同一行名产出的公式必须
**要么为空、要么与种子逐字相等**，否则两套口径并存，哪一方先跑决定结果。

本文件按 ``fill_all_formulas`` 的五条策略逐条复算（直调生产函数，不复制实现）：
策略 1 特殊公式表、策略 2 CAS 表、策略 3 合计行关键词、策略 4 ``is_total_row``、策略 5 行名 → 科目码 fallback。
"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services.four_table.report_config_account_names import DERIVED_ROW_NAMES_WITHOUT_ACCOUNT
from app.services.report_formula_service import (
    _build_cas_name_formulas,
    _convert_formula,
    _generate_fallback_formula,
    _generate_sum_formula,
    _get_special,
    _normalize_name,
)

SEED = Path(__file__).resolve().parents[2] / "data" / "report_config_seed.json"
STANDARDS = ("soe_consolidated", "soe_standalone", "listed_consolidated", "listed_standalone")
IS = "income_statement"
COL = "本期发生额"
#: ADR-ISL-04 删掉的错误 / 双口径映射：这些行名在特殊表里必须查不到。
#: 前 5 条是 design §1 第 7 行登记的错误科目映射；后 3 条由本 spec 的同源守卫现场抓出
#: （「营业总成本」与权威模板恒等式口径并存；「利息费用」「利息收入」各自映到财务费用全额）。
DELETED_SPECIAL_NAMES = (
    "汇兑收益", "其他综合收益的税后净额", "综合收益总额", "基本每股收益", "稀释每股收益",
    "营业总成本", "利息费用", "利息收入", "以摊余成本计量的金融资产终止确认收益",
)


def seed_blocks() -> dict[str, list[dict]]:
    blocks = json.loads(SEED.read_text(encoding="utf-8-sig"))
    out = {b["applicable_standard"]: b["rows"] for b in blocks
           if b.get("report_type") == IS and b.get("applicable_standard") in STANDARDS}
    assert sorted(out) == sorted(STANDARDS), f"种子缺利润表块：{sorted(out)}"
    return out


def as_config(row: dict) -> SimpleNamespace:
    return SimpleNamespace(
        row_code=row["row_code"], row_name=row.get("row_name") or "", row_number=row["row_number"],
        indent_level=row.get("indent_level", 0), is_total_row=bool(row.get("is_total_row")),
        formula=row.get("formula"), formula_source=row.get("formula_source"),
    )


def generator_candidates(rows: list[SimpleNamespace], idx: int) -> dict[str, str | None]:
    """对一行复算五条策略各自的产出（与 ``fill_all_formulas`` 同序、同入参）。"""
    cfg = rows[idx]
    norm = _normalize_name(cfg.row_name)
    if norm in DERIVED_ROW_NAMES_WITHOUT_ACCOUNT:  # 派生行拦截门在任何策略之前
        return {}
    cas_map = _build_cas_name_formulas().get("IS", {})
    out: dict[str, str | None] = {
        "special": _get_special(cfg.row_name, IS),
        "cas": _convert_formula(cas_map[norm], COL) if norm in cas_map else None,
        "fallback": _generate_fallback_formula(cfg.row_code, cfg.row_name, COL),
    }
    if any(keyword in cfg.row_name for keyword in ("合计", "小计", "总计", "总额")):
        out["auto_total"] = _generate_sum_formula(rows, idx, [])
    if cfg.is_total_row:
        out["auto_total_flag"] = _generate_sum_formula(rows, idx, [])
    return out


@pytest.mark.parametrize("standard", STANDARDS)
def test_generator_never_contradicts_seed_formula(standard):
    """种子有公式的行：生成器任一策略的产出要么为空、要么与种子逐字相等。"""
    rows = [as_config(row) for row in seed_blocks()[standard]]
    conflicts: list[str] = []
    covered = 0
    for idx, cfg in enumerate(rows):
        seeded = (cfg.formula or "").strip()
        if not seeded:
            continue
        covered += 1
        for strategy, produced in generator_candidates(rows, idx).items():
            if produced and produced != seeded:
                conflicts.append(
                    f"{standard} {cfg.row_code}「{cfg.row_name}」策略 {strategy} 产出 {produced!r}，种子 {seeded!r}"
                )
    assert covered > 0, f"{standard} 种子利润表没有一行有公式：守卫空转"
    assert conflicts == [], "生成器与种子口径不一致：\n" + "\n".join(conflicts)


@pytest.mark.parametrize("standard", STANDARDS)
def test_input_rows_get_no_generated_formula(standard):
    """``formula_source='input'`` 的手工输入行：生成器不得给它们编公式（否则手工值被自动数顶掉）。"""
    rows = [as_config(row) for row in seed_blocks()[standard]]
    produced: list[str] = []
    inputs = 0
    for idx, cfg in enumerate(rows):
        if (cfg.formula_source or "") != "input":
            continue
        inputs += 1
        for strategy, formula in generator_candidates(rows, idx).items():
            if formula:
                produced.append(f"{standard} {cfg.row_code}「{cfg.row_name}」策略 {strategy} → {formula!r}")
    assert inputs > 0, f"{standard} 种子里没有 input 行：守卫空转"
    assert produced == [], "手工输入行被生成器编了公式：\n" + "\n".join(produced)


def test_deleted_special_mappings_are_gone():
    """ADR-ISL-04 删掉的 5 条错误映射不得回归（恢复任一条 ⇒ 本用例红）。"""
    present = [name for name in DELETED_SPECIAL_NAMES if _get_special(name, IS)]
    assert present == [], f"特殊公式表仍有已删除的错误映射：{present}"


@pytest.mark.parametrize(("name", "expected"), [
    ("信用减值损失", "-TB('6702','本期发生额')"),
    ("资产减值损失", "-TB('6701','本期发生额')"),
])
def test_impairment_losses_are_presented_negative(name, expected):
    """两条减值损失列报为负（行名「损失以“－”号填列」）：特殊表必须带负号。"""
    assert _get_special(name, IS) == expected


def test_seed_impairment_rows_carry_negative_sign():
    """四套种子里的减值损失行也必须是负号形态（与特殊表同源）。"""
    missing: list[str] = []
    for standard, rows in seed_blocks().items():
        for row in rows:
            norm = _normalize_name(row.get("row_name") or "")
            if norm in ("信用减值损失", "资产减值损失"):
                if not (row.get("formula") or "").startswith("-TB("):
                    missing.append(f"{standard} {row['row_code']} → {row.get('formula')!r}")
    assert missing == [], f"种子减值损失行缺负号：{missing}"
