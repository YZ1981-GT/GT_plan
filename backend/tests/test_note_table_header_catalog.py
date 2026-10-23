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
    # 合并种子多级表头按 Word 修复后（R6.3）：表头里没有数据行，标签列表头不盖数据列（原上市 五-9-4~7 等 11 处）
    header_defects = {a for a in found if a[2] in ("header_row_has_data", "label_header_spans_data_columns")}
    assert header_defects == set()
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
#: none 含主动拒绝的错配：上市 五-9-4~7 单体两张组合表同构；国企 五-64-5、五-78-2 单体对应章节没有一列对得上的表
#: —— 宁缺不错，见 design §13。
#: 2026-10-22 R6.3 种子多级表头修复 + 纯期间列对唯一余额列：国企 656→660 列、上市 803→815 列，上市 五-11-3 由 none 转为对上。
#: 2026-10-23 R7.6 国企章节号按 Word 重对齐、两版去掉重复条目：国企 0.7774→0.9031、none 27→11（原错位章节的表对上了），
#:   上市 0.9015→0.9089（9 张重复表不再计入）。
#: 2026-10-23 R7.7 只写「金额」的无键金额列计入取数列并按表头文字对（国企分母 +7、对上 +6，五-54-5 单体表头与 Word 不符
#:   对不上；上市 +4 / +4），上市 6 张表头占位列按单体模板实例化（对上 +8）：口径变了，国企 0.9031→0.9027（对上 606→612），
#:   上市 0.9103→0.9261（R7.8 上市 五-10 改号后 0.9103）；对上列数一并钉住，分母口径再变也不会把退步藏在比例里。
#: 2026-10-23 R7.7 收尾复核：「只写了期间」对上的两列须是同一项，去掉 3 处错配（国企 五-50-2「期初余额」↔ 单体「年初应付利息」、
#:   上市 五-12-2 两列「面值」↔ 单体「期末余额 / 上年年末余额」）；上市 五-19-2 表名按单体模板改回「期末其他权益工具投资情况」
#:   后选中同表（对上 1→4）：国企 0.9027→0.9012（对上 612→611）、上市 0.9261→0.9272（对上 814→815）。
_RATCHET = {
    "soe": {"coverage": 0.9012, "matched": 611, "none": 11},
    "listed": {"coverage": 0.9272, "matched": 815, "none": 26},
}


def test_period_only_requires_same_item_and_listed_19_2_title(catalog):
    """R7.7 收尾复核：「只写了期间」不把另一项（应付利息 / 面值）当成余额；上市 五-19-2 按表名选中单体同表、逐列对上。"""
    items = {(std, i["consol"]): i for std in ("soe", "listed") for i in catalog["correspondence"][std]}
    assert "期初余额" in items[("soe", "五-50-2")]["unmatched"]  # 单体只有「年初应付利息」，不是期初余额
    assert {"期末余额/面值", "上年年末余额/面值"} <= set(items[("listed", "五-12-2")]["unmatched"])  # 单体只有余额没有面值
    item = items[("listed", "五-19-2")]
    assert item["standalone"] == "五、19#1" and item["chosen_name"] == "期末其他权益工具投资情况"
    assert item["unmatched"] == [] and item["matched"] == item["amount_columns"] == 4


def test_bare_amount_and_instantiated_placeholder_columns_correspond(catalog):
    """R7.7：只写「金额」的单金额列表按表头文字对上；上市表头占位列按单体实例化后逐列对上（不再有没对上的列）。"""
    items = {(std, i["consol"]): i for std in ("soe", "listed") for i in catalog["correspondence"][std]}
    assert items[("soe", "五-87-1")]["columns"] == [[1, "八、87#0", 1, "bare_label"]]
    assert items[("listed", "五-49-5")]["columns"] == [[1, "五、49#4", 1, "bare_label"]]
    for sid in ("五-22-2", "五-24-1", "五-24-2", "五-25-1", "五-28-1", "五-28-2"):
        item = items[("listed", sid)]
        assert item["unmatched"] == [] and item["matched"] == item["amount_columns"], sid


def test_receivable_aging_pure_period_correspondence(catalog):
    """国企 五-5-1 账龄表（期末数/账面余额 | 期末数/坏账准备 …）↔ 单体「账龄 | 期末数 | 期初数」：纯期间列对账面余额列。

    种子多级表头修复前，五-5-1 只有期末账面余额一列在「期末」下，碰巧对上；修复后坏账准备也在期末下，按唯一余额列认（R6.3）。
    """
    item = next(i for i in catalog["correspondence"]["soe"] if i["consol"] == "五-5-1")
    assert item["columns"] == [[1, "八、5#0", 1, "period_balance"], [3, "八、5#0", 2, "period_balance"]]


@pytest.mark.parametrize("std", ["soe", "listed"])
def test_correspondence_ratchet(catalog, std):
    stats = catalog["stats"][f"{std}_correspondence"]
    assert stats["coverage"] >= _RATCHET[std]["coverage"]
    assert stats["matched_columns"] >= _RATCHET[std]["matched"]
    assert stats["by_via"].get("none", 0) <= _RATCHET[std]["none"]


def test_committed_file_location():
    assert LIBRARY_PATH.name == "note_table_header_library.json" and LIBRARY_PATH.exists()
