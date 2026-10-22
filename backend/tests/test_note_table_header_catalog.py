"""标题行库目录测试（note_table_header_catalog）：入库目录与生成结果一致、四版表数、已知异常、对应与覆盖率棘轮。"""
from __future__ import annotations

import json

import pytest

from app.services.consol_note_headers import header_cells
from app.services.note_section_catalog import section_applies_to_scope, template_json_path
from app.services.note_table_header_catalog import (
    DATA_DIR,
    LIBRARY_PATH,
    build_catalog,
    check_catalog,
    render_catalog,
)


@pytest.fixture(scope="module")
def catalog() -> dict:
    return build_catalog()


def _by_id(catalog: dict, variant: str) -> dict[str, dict]:
    return {e["id"]: e for e in catalog["variants"][variant]}


def test_committed_catalog_is_up_to_date():
    """改了词表 / 种子 / 映射而没重新生成目录 ⇒ 打红（重跑 build_note_table_header_library.py）。"""
    assert check_catalog() == []


def test_rendering_is_deterministic_and_valid_json(catalog):
    text = render_catalog(catalog)
    assert text == render_catalog(build_catalog())
    assert json.loads(text)["stats"] == catalog["stats"]
    assert "generated_at" not in text and "timestamp" not in text


@pytest.mark.parametrize("std", ["soe", "listed"])
def test_variant_table_counts_match_seeds(catalog, std):
    seed = json.loads(template_json_path(std).read_text(encoding="utf-8"))
    standalone = sum(
        len([t for t in s.get("tables") or [] if isinstance(t, dict)])
        for s in seed["sections"] if section_applies_to_scope(s, "standalone")
    )
    consol = json.loads((DATA_DIR / f"consol_note_sections_{std}.json").read_text(encoding="utf-8"))
    assert len(catalog["variants"][f"{std}_standalone"]) == standalone
    assert len(catalog["variants"][f"{std}_consolidated"]) == len(consol)


def test_header_rows_cover_every_column(catalog):
    for variant, entries in catalog["variants"].items():
        for e in entries:
            if not e["header_rows"]:
                continue
            rows = [[{"text": t, "colspan": cs, "rowspan": rs} for t, cs, rs in row] for row in e["header_rows"]]
            header_cells(rows, len(e["columns"]))  # 跨度越界 / 重叠 / 漏列会抛错


def test_known_anomalies_are_listed(catalog):
    found = {(a["variant"], a["id"], a["kind"]) for a in catalog["anomalies"]}
    assert ("soe_standalone", "八、9#16", "continuation_self_reference") in found
    assert ("soe_standalone", "八、18#4", "continuation_self_reference") in found
    for sid in ("五-9-4", "五-9-5", "五-9-6", "五-9-7"):
        assert ("listed_consolidated", sid, "label_header_spans_data_columns") in found
    assert ("listed_consolidated", "五-9-6", "header_row_has_data") in found
    xu = {a["id"] for a in catalog["anomalies"] if a["kind"] == "xu_word_not_continuation"}
    assert "八、9#16" in xu  # 继续涉入
    assert any(i.startswith("八、51#") for i in xu)  # 永续债


def test_continuations(catalog):
    soe = _by_id(catalog, "soe_standalone")
    assert soe["八、4#3"]["continuation"] == {"of": "八、4#2", "kind": "columns", "via": "base"}
    assert "continuation" not in soe["八、9#16"]  # 继续涉入不是续表
    listed = _by_id(catalog, "listed_standalone")
    # 「应付债券（续）」续的是上一张「应付债券的增减变动」，不是同基名的「应付债券」汇总表
    assert listed["五、46#2"]["continuation"]["of"] == "五、46#1"


def test_receivable_prior_continuation_correspondence(catalog):
    """国企 五-4-3（期初数续表）：映射写的是「（续：期初数）」（原按表名对到单项计提表），全部金额列对上。"""
    item = next(i for i in catalog["correspondence"]["soe"] if i["consol"] == "五-4-3")
    assert item["mapping_table"] == item["chosen_name"] == "按坏账准备计提方法分类披露应收票据（续：期初数）"
    assert item["matched"] == item["amount_columns"] == 3


@pytest.mark.parametrize("std", ["soe", "listed"])
def test_mapping_agrees_with_runtime_choice(catalog, std):
    """映射 JSON 的单体子表名与运行时读取层选中的表一致（两边调同一个 choose_unit）。"""
    assert catalog["stats"][f"{std}_correspondence"]["mapping_disagreements"] == 0


#: 覆盖率只许变好、认不到的表只许变少（改词表 / 种子后更好就收紧）。
#: none 含主动拒绝的错配：上市 五-9-4~7 合并表头错列且单体两张组合表同构；国企 五-64-4/5、五-79-2
#: 章节映射错位（单体对应章节唯一一张表一列都对不上）—— 宁缺不错，见 design §13。
_RATCHET = {
    "soe": {"coverage": 0.7727, "none": 27},
    "listed": {"coverage": 0.8932, "none": 27},
}


@pytest.mark.parametrize("std", ["soe", "listed"])
def test_correspondence_ratchet(catalog, std):
    stats = catalog["stats"][f"{std}_correspondence"]
    assert stats["coverage"] >= _RATCHET[std]["coverage"]
    assert stats["by_via"].get("none", 0) <= _RATCHET[std]["none"]


def test_committed_file_location():
    assert LIBRARY_PATH.name == "note_table_header_library.json" and LIBRARY_PATH.exists()
