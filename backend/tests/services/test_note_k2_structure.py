"""附注「其他流动资产」章节结构守卫（K2）。

锁住 ``fix_note_k2_structure.py`` 的修订成果，防 md 重建 / 并发会话回退：

- 上市 §五、13 恰 3 张表、国企 §八、14 恰 1 张表，表名逐字
- 历史表名（段落文本泄漏 / 表头首格泄漏）已清除
- 每张表带 ``columns``（显式 ``flat``）+ ``guidance``，且无 ``_column_groups``
- 无 ``header_label`` 假数据行
- 固定行名与列头逐字对齐

spec: .kiro/specs/k2-other-current-assets-disclosure-alignment/ Task 5.3
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from scripts.fix.fix_note_k2_structure import (
    LISTED_SECTION,
    SOE_SECTION,
    T_CARBON,
    T_CARBON_OBSOLETE,
    T_CONTRACT_COST,
    T_CONTRACT_COST_OBSOLETE,
    T_MAIN,
    validate_section,
)

_DATA = Path(__file__).resolve().parents[2] / "data"

LISTED_MAIN_ROWS = [
    "进项税额",
    "多交或预缴的增值税额",
    "待抵扣进项税额",
    "待认证进项税额",
    "增值税留抵税额",
    "预缴所得税",
    "委托贷款",
    "预缴其他税费",
    "短期债权投资",
    "短期其他债权投资",
    "合同取得成本",
    "应收退货成本",
    "碳排放权资产",
    "合计",
]

SOE_MAIN_ROWS = [
    "待抵扣进项税额",
    "预缴税金",
    "委托贷款",
    "短期债权投资",
    "短期其他债权投资",
    "合同取得成本",
    "应收退货成本",
    "碳排放权资产",
    "合计",
]

CONTRACT_COST_ROWS = ["期初余额", "本年增加", "本年摊销", "本年计提减值损失", "期末余额"]

CARBON_ROWS = [
    "1．本期期初碳排放配额",
    "2．本期增加的碳排放配额",
    "（1）免费分配取得的配额",
    "（2）购入取得的配额",
    "（3）其他方式增加的配额",
    "3．本期减少的碳排放配额",
    "（1）履约使用的配额",
    "（2）出售的配额",
    "（3）其他方式减少的配额",
    "4．本期期末碳排放配额",
]


def _load(variant: str, section_number: str) -> dict[str, Any]:
    doc = json.loads((_DATA / f"note_template_{variant}.json").read_text(encoding="utf-8"))
    for sec in doc.get("sections", []):
        if str(sec.get("section_number", "")) == section_number:
            return sec
    raise AssertionError(f"note_template_{variant}.json 缺章节 {section_number}")


@pytest.fixture(scope="module")
def listed() -> dict[str, Any]:
    return _load("listed", LISTED_SECTION)


@pytest.fixture(scope="module")
def soe() -> dict[str, Any]:
    return _load("soe", SOE_SECTION)


def _labels(table: dict[str, Any]) -> list[str]:
    return [str(r.get("label", "")) for r in table.get("rows") or []]


def _by_name(section: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(t.get("name", "")): t for t in section.get("tables") or []}


# ── 表集合 ────────────────────────────────────────────────────────────────────

def test_listed_has_exactly_three_tables_in_order(listed: dict[str, Any]) -> None:
    assert [str(t.get("name")) for t in listed["tables"]] == [T_MAIN, T_CONTRACT_COST, T_CARBON]


def test_soe_has_exactly_one_table(soe: dict[str, Any]) -> None:
    assert [str(t.get("name")) for t in soe["tables"]] == [T_MAIN]


@pytest.mark.parametrize("legacy", [T_CONTRACT_COST_OBSOLETE, T_CARBON_OBSOLETE])
def test_legacy_table_names_removed(listed: dict[str, Any], legacy: str) -> None:
    assert legacy not in _by_name(listed)


# ── 列结构 ────────────────────────────────────────────────────────────────────

def test_headers_are_three_columns(listed: dict[str, Any], soe: dict[str, Any]) -> None:
    by_listed = _by_name(listed)
    assert by_listed[T_MAIN]["headers"] == ["项目", "期末余额", "上年年末余额"]
    assert by_listed[T_CONTRACT_COST]["headers"] == ["项目", "佣金支出", "合计"]
    assert by_listed[T_CARBON]["headers"] == ["项目", "本期发生额", "上期发生额"]
    assert _by_name(soe)[T_MAIN]["headers"] == ["项目", "期末余额", "期初余额"]


def test_every_table_declares_flat_and_has_no_column_groups(
    listed: dict[str, Any], soe: dict[str, Any]
) -> None:
    for section in (listed, soe):
        for table in section["tables"]:
            cols = table.get("columns") or []
            assert cols, f"{table.get('name')} 缺 columns"
            assert any(c.get("flat") for c in cols), f"{table.get('name')} 未显式 flat"
            assert not any(c.get("group") for c in cols), f"{table.get('name')} 不应有 group"
            assert "_column_groups" not in table, f"{table.get('name')} 标 flat 却留 _column_groups"


def test_label_column_is_first_and_matches_headers(
    listed: dict[str, Any], soe: dict[str, Any]
) -> None:
    for section in (listed, soe):
        for table in section["tables"]:
            cols = table["columns"]
            assert cols[0].get("is_label") is True
            assert cols[0]["label"] == table["headers"][0]
            assert len(cols) == len(table["headers"])


def test_column_keys_are_expected(listed: dict[str, Any], soe: dict[str, Any]) -> None:
    by_listed = _by_name(listed)
    assert [c["key"] for c in by_listed[T_MAIN]["columns"]] == ["label", "end_amount", "prior_amount"]
    assert [c["key"] for c in by_listed[T_CONTRACT_COST]["columns"]] == ["label", "cat_1", "total"]
    assert [c["key"] for c in by_listed[T_CARBON]["columns"]] == [
        "label",
        "current_amount",
        "prior_amount",
    ]
    assert [c["key"] for c in _by_name(soe)[T_MAIN]["columns"]] == [
        "label",
        "end_amount",
        "prior_amount",
    ]


# ── 行 ────────────────────────────────────────────────────────────────────────

def test_no_header_label_fake_rows(listed: dict[str, Any], soe: dict[str, Any]) -> None:
    for section in (listed, soe):
        for table in section["tables"]:
            assert not [
                r for r in table.get("rows") or [] if str(r.get("row_type", "")) == "header_label"
            ], f"{table.get('name')} 残留 header_label 假数据行"


def test_fixed_row_labels(listed: dict[str, Any], soe: dict[str, Any]) -> None:
    by_listed = _by_name(listed)
    assert _labels(by_listed[T_MAIN]) == LISTED_MAIN_ROWS
    assert _labels(by_listed[T_CONTRACT_COST]) == CONTRACT_COST_ROWS
    assert _labels(by_listed[T_CARBON]) == CARBON_ROWS
    assert _labels(_by_name(soe)[T_MAIN]) == SOE_MAIN_ROWS


def test_total_row_flagged(listed: dict[str, Any], soe: dict[str, Any]) -> None:
    for section in (listed, soe):
        main = _by_name(section)[T_MAIN]
        assert main["rows"][-1].get("is_total") is True


# ── guidance ─────────────────────────────────────────────────────────────────

def test_every_table_has_guidance(listed: dict[str, Any], soe: dict[str, Any]) -> None:
    for section in (listed, soe):
        for table in section["tables"]:
            assert str(table.get("guidance", "")).strip(), f"{table.get('name')} 缺 guidance"


def test_guidance_carries_check_preset_ids(listed: dict[str, Any], soe: dict[str, Any]) -> None:
    """主表 guidance 须写明勾稽来源（F13-1 / F13-1a / F13-2）。"""
    for section in (listed, soe):
        guidance = _by_name(section)[T_MAIN]["guidance"]
        for preset in ("F13-1", "F13-1a", "F13-2"):
            assert preset in guidance


# ── 幂等标记与脚本自校验 ─────────────────────────────────────────────────────

def test_aligned_by_stamp(listed: dict[str, Any], soe: dict[str, Any]) -> None:
    for section in (listed, soe):
        assert section.get("_aligned_by") == "k2-other-current-assets-disclosure-alignment"


def test_script_validator_reports_no_error(listed: dict[str, Any], soe: dict[str, Any]) -> None:
    assert validate_section(listed, LISTED_SECTION) == []
    assert validate_section(soe, SOE_SECTION) == []


def test_script_validator_catches_regression(listed: dict[str, Any]) -> None:
    """反向自检：把 flat 摘掉后校验器必须报错（防守卫空转）。"""
    broken = json.loads(json.dumps(listed, ensure_ascii=False))
    for col in broken["tables"][0]["columns"]:
        col.pop("flat", None)
    errs = validate_section(broken, LISTED_SECTION)
    assert any("未表态" in e for e in errs), errs
