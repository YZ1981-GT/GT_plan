"""K1 其他应收款附注章节结构契约（spec: k1-other-receivable-disclosure-alignment）.

锁定三件事：
1. §五、8 / §八、9 的表清单、两级表头（``_column_groups``）、``guidance`` 齐备；
2. 新增的 4 张国企表存在且列头逐字对齐 K1 国企披露 sheet；
3. 生成期 seed 元数据透传：``_carry_seed_column_meta`` 带 ``_column_groups``，
   ``_carry_seed_table_guidance`` 让 seed 显式 guidance 覆盖段落推断结果。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.disclosure_engine import (
    _carry_seed_column_meta,
    _carry_seed_table_guidance,
)

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
LISTED_SECTION = "五、8"
SOE_SECTION = "八、9"

SOE_NEW_TABLES = {
    "其他应收款项账面余额变动": ["账面余额", "第一阶段", "第二阶段", "第三阶段", "合计"],
    "由金融资产转移而终止确认的其他应收款项": [
        "债务人名称", "终止确认金额", "与终止确认相关的利得或损失",
    ],
    "其他应收款项转移继续涉入形成的资产、负债的金额": ["项  目", "期末金额"],
    "涉及政府补助的应收款项": [
        "单位名称", "政府补助项目名称", "期末余额", "期末账龄", "预计收取的时间、金额及依据",
    ],
}

# 两级表头表 → 期望的 group 名（顺序即 _column_groups 顺序）
GROUPED_TABLES = {
    "listed": {"按款项性质披露": ["期末金额", "上年年末金额"]},
    "soe": {
        "按账龄披露其他应收款项": ["期末数", "期初数"],
        "按坏账准备计提方法分类披露其他应收款项": ["账面余额", "坏账准备"],
        "续：": ["账面余额", "坏账准备"],
        "单项计提坏账准备的其他应收款项": ["期末余额"],
        "账龄组合": ["期末数", "期初数"],
        "采用余额百分比法或其他组合方法计提坏账准备的其他应收款项": ["期末数", "期初数"],
    },
}


def _section(std: str) -> dict:
    path = DATA_DIR / f"note_template_{std}.json"
    raw = json.loads(path.read_text(encoding="utf-8-sig"))
    target = LISTED_SECTION if std == "listed" else SOE_SECTION
    hit = [s for s in raw["sections"] if str(s.get("section_number", "")).strip() == target]
    assert hit, f"{path.name} 缺少章节 {target}"
    return hit[0]


@pytest.fixture(scope="module")
def listed() -> dict:
    return _section("listed")


@pytest.fixture(scope="module")
def soe() -> dict:
    return _section("soe")


# ─── 表清单与列头 ────────────────────────────────────────────────────────────

def test_soe_has_four_new_tables(soe: dict) -> None:
    names = {t["name"] for t in soe["tables"]}
    missing = set(SOE_NEW_TABLES) - names
    assert not missing, f"§八、9 缺表：{sorted(missing)}"


@pytest.mark.parametrize("name,headers", sorted(SOE_NEW_TABLES.items()))
def test_soe_new_table_headers(soe: dict, name: str, headers: list[str]) -> None:
    tbl = next(t for t in soe["tables"] if t["name"] == name)
    assert tbl["headers"] == headers


@pytest.mark.parametrize("std", ["listed", "soe"])
def test_every_table_has_guidance(std: str, listed: dict, soe: dict) -> None:
    sec = listed if std == "listed" else soe
    missing = [t["name"] for t in sec["tables"] if not str(t.get("guidance") or "").strip()]
    assert not missing, f"{std} 缺 guidance：{missing}"


@pytest.mark.parametrize("std", ["listed", "soe"])
def test_two_level_headers_declared(std: str, listed: dict, soe: dict) -> None:
    sec = listed if std == "listed" else soe
    by_name = {t["name"]: t for t in sec["tables"]}
    for name, groups in GROUPED_TABLES[std].items():
        tbl = by_name.get(name)
        assert tbl is not None, f"{std} 缺表 {name}"
        declared = tbl.get("_column_groups")
        assert isinstance(declared, list) and declared, f"{name} 缺 _column_groups"
        assert [g["group"] for g in declared] == groups
        # group 覆盖范围不得越界，且不得与标签列（index 0）重叠
        for g in declared:
            assert g["start"] >= 1
            assert g["start"] + g["span"] <= len(tbl["headers"])


def test_headers_have_no_blank(listed: dict, soe: dict) -> None:
    """两级表头用全限定列名 + _column_groups 表达，禁止空串占位。"""
    for sec in (listed, soe):
        for t in sec["tables"]:
            for h in t.get("headers") or []:
                assert str(h).strip(), f'{t["name"]} 存在空列名'


def test_listed_stage_tables_have_unit_rows(listed: dict) -> None:
    """6 张三阶段表都应在「按单项计提坏账准备」下挂示例单位行（源模板 R34/R35）。"""
    stage_names = [t["name"] for t in listed["tables"] if "阶段的坏账准备" in t["name"]]
    assert len(stage_names) == 6
    for name in stage_names:
        labels = [r.get("label") for r in next(t for t in listed["tables"] if t["name"] == name)["rows"]]
        assert "其他应收款单位1" in labels and "其他应收款单位2" in labels, name


def test_soe_text_sections_cover_new_blocks(soe: dict) -> None:
    joined = "\n".join(soe.get("text_sections") or [])
    for keyword in (
        "其他应收款项账面余额变动",
        "由金融资产转移而终止确认的其他应收款项",
        "其他应收款项转移继续涉入形成的资产、负债的金额",
        "涉及政府补助的应收款项",
        "本期坏账准备计提金额以及评估金融工具的信用风险是否显著增加的采用依据",
    ):
        assert keyword in joined, f"text_sections 缺 {keyword}"


# ─── 生成期透传 ──────────────────────────────────────────────────────────────

def test_carry_seed_column_meta_passes_column_groups() -> None:
    seed = {"_column_groups": [{"group": "期末数", "start": 1, "span": 2}]}
    built: dict = {"headers": ["账  龄", "a", "b"], "rows": []}
    _carry_seed_column_meta(seed, built)
    assert built["_column_groups"] == seed["_column_groups"]


def test_carry_seed_column_meta_does_not_override_existing() -> None:
    seed = {"_column_groups": [{"group": "seed", "start": 1, "span": 1}]}
    built = {"_column_groups": [{"group": "existing", "start": 1, "span": 1}]}
    _carry_seed_column_meta(seed, built)
    assert built["_column_groups"][0]["group"] == "existing"


def test_seed_guidance_overrides_inferred() -> None:
    seed_tables = [{"name": "A", "guidance": "源模板红字"}, {"name": "B"}]
    built_tables = [{"name": "A", "guidance": "段落推断"}, {"name": "B", "guidance": "段落推断"}]
    _carry_seed_table_guidance(seed_tables, built_tables)
    assert built_tables[0]["guidance"] == "源模板红字"
    # seed 未声明 guidance 的表保持推断结果（其余 300+ 章节零影响）
    assert built_tables[1]["guidance"] == "段落推断"


def test_seed_guidance_tolerates_length_mismatch() -> None:
    built_tables = [{"name": "A"}]
    _carry_seed_table_guidance([{"guidance": "x"}, {"guidance": "y"}], built_tables)
    assert built_tables[0]["guidance"] == "x"
    _carry_seed_table_guidance([], built_tables)
    assert built_tables[0]["guidance"] == "x"
