"""N1 递延所得税附注「读时投影 + guidance 回填」端到端（服务层）。

用**真实同步载荷形状**的 `table_data` 走 `get_note_detail` 里的那两步
（`note_sub_table_projector.project_sub_tables` → `note_table_guidance.carry_template_guidance`），
断言附注 TAB 最终拿到的东西：

1. 表数 = 该变体子表名全集（listed 4 / soe 5）
2. 表 1 两级表头 `_column_groups` 正确，且**两版子列序相反**（源模板 B11:E11）
3. 其余表 `_column_groups == []`（显式单级，`flat` 生效 → 不被前缀推断塞凭空父表头）
4. 全部表拿到非空 `guidance`（TAB 编制提示）

为什么要这一层：`guidance` 不在同步载荷里，投影只认推送的业务数据 → 项目同步过一次后
附注 TAB 提示会永久变空。本测试锁死回填后的最终形态。

spec: `.kiro/specs/n1-deferred-tax-disclosure-template-alignment/` R4.6 / R7.1
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.note_sub_table_projector import project_sub_tables
from app.services.note_table_guidance import carry_template_guidance

_DATA = Path(__file__).resolve().parents[2] / "data"

_DIFF = "可抵扣/应纳税暂时性差异"
_TAX = "递延所得税资产/负债"

# 两版表 1 的子列序（源模板实测：上市暂时性差异在前 / 国企资产负债在前）
_SUB_ORDER = {
    "listed": [("end_diff", _DIFF), ("end_tax", _TAX)],
    "soe": [("end_tax", _TAX), ("end_diff", _DIFF)],
}
_PRIOR_GROUP = {"listed": "上年年末余额", "soe": "年初余额"}
_SECTION = {"listed": "五、30", "soe": "八、31"}
_TEMPLATE = {"listed": "note_template_listed.json", "soe": "note_template_soe.json"}

_UNOFFSET = "未经抵销的递延所得税资产和递延所得税负债"


def _template_tables(variant: str) -> list[dict]:
    data = json.loads((_DATA / _TEMPLATE[variant]).read_text(encoding="utf-8"))
    sec = [s for s in data["sections"] if s.get("section_number") == _SECTION[variant]][0]
    return sec["tables"]


def _build_table_data(variant: str) -> dict:
    """按模板表名/列定义造一份「底稿刚推送完」形状的 table_data。"""
    sub: dict[str, list[dict]] = {}
    cols: dict[str, list[dict]] = {}
    for t in _template_tables(variant):
        name = t["name"]
        defs = t["columns"]
        cols[name] = defs
        row = {d["key"]: (None if d.get("format") == "amount" else "") for d in defs}
        row[defs[0]["key"]] = "示例行"
        sub[name] = [row]
    return {"_source": "workpaper", "sub_table_data": sub, "_sub_table_columns": cols}


def _project(variant: str) -> list[dict]:
    tables = project_sub_tables(_build_table_data(variant))
    assert tables is not None
    carry_template_guidance(tables, variant, _SECTION[variant])
    return tables


@pytest.mark.parametrize(("variant", "expected"), [("listed", 4), ("soe", 5)])
def test_projected_table_count(variant: str, expected: int) -> None:
    assert len(_project(variant)) == expected


@pytest.mark.parametrize("variant", ["listed", "soe"])
def test_projected_names_match_template(variant: str) -> None:
    got = {t["name"] for t in _project(variant)}
    assert got == {t["name"] for t in _template_tables(variant)}


@pytest.mark.parametrize("variant", ["listed", "soe"])
def test_unoffset_is_two_level_with_variant_specific_sub_order(variant: str) -> None:
    t = next(x for x in _project(variant) if x["name"] == _UNOFFSET)
    order = [label for _, label in _SUB_ORDER[variant]]
    assert t["headers"] == ["项目", *order, *order]
    assert t["_column_groups"] == [
        {"group": "期末余额", "start": 1, "span": 2},
        {"group": _PRIOR_GROUP[variant], "start": 3, "span": 2},
    ]


def test_sub_order_is_mirrored_between_variants() -> None:
    """反向断言：两版子列序不得被"统一"（统一后附注列会串味）。"""
    listed = next(x for x in _project("listed") if x["name"] == _UNOFFSET)["headers"]
    soe = next(x for x in _project("soe") if x["name"] == _UNOFFSET)["headers"]
    assert listed[1:3] == [_DIFF, _TAX]
    assert soe[1:3] == [_TAX, _DIFF]


@pytest.mark.parametrize("variant", ["listed", "soe"])
def test_single_level_tables_get_empty_groups(variant: str) -> None:
    """`flat` 三态：显式单级 → `[]`，不得为 None（None 会回退前缀推断）。"""
    for t in _project(variant):
        if t["name"] == _UNOFFSET:
            continue
        assert t["_column_groups"] == [], t["name"]


@pytest.mark.parametrize("variant", ["listed", "soe"])
def test_all_projected_tables_carry_guidance(variant: str) -> None:
    missing = [t["name"] for t in _project(variant) if not str(t.get("guidance") or "").strip()]
    assert missing == []


def test_soe_offset_detail_table_is_projected() -> None:
    """源模板（2）B 互抵明细（本 spec 新增），此前整张缺失。"""
    t = next(x for x in _project("soe") if x["name"] == "递延所得税资产和递延所得税负债互抵明细")
    assert t["headers"] == ["项目", "本期互抵金额"]
    assert t["_column_groups"] == []


@pytest.mark.parametrize("variant", ["listed", "soe"])
def test_guidance_is_noop_without_carry(variant: str) -> None:
    """不调回填时 guidance 恒空 —— 证明本测试断言的是回填带来的效果，而非投影自带。"""
    tables = project_sub_tables(_build_table_data(variant))
    assert all(not (t.get("guidance") or "") for t in tables)
