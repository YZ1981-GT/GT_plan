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
from app.services.note_table_header_library import _override_table_key, load_vocabulary, table_identity


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
    # 2026-10-25 R8.4 批 9b-2：原登记的两处「续表指向自己」随表清单修正消失 —— 国企 八、9 补回「其他应收款项账面余额变动」后
    # 继续涉入表在 #17、指向 #16 终止确认表（与 十二、其他应收款、上市 五、8 同一约定）；八、18 补「重要联营企业的主要财务信息」
    # 后「续：重要联营企业…」(#5) 指向它（#4）。今后不许再有
    assert not {a for a in found if a[2] == "continuation_self_reference"}
    assert ("soe_standalone", "八、9#17", "continuation_index_not_continuation") in found
    # 合并种子多级表头按 Word 修复后（R6.3）：表头里没有数据行，标签列表头不盖数据列（原上市 五-9-4~7 等 11 处）
    header_defects = {a for a in found if a[2] in ("header_row_has_data", "label_header_spans_data_columns")}
    assert header_defects == set()
    xu = {a["id"] for a in catalog["anomalies"] if a["kind"] == "xu_word_not_continuation"}
    assert "八、9#17" in xu  # 继续涉入
    assert any(i.startswith("八、51#") for i in xu)  # 永续债


def test_continuations(catalog):
    soe = _by_id(catalog, "soe_standalone")
    # 2026-10-25 批 9b-2 删国企 八、4 重复的「按坏账准备计提方法分类披露应收票据」后，期初数续表在 #2、续 #1（期末数）
    assert soe["八、4#2"]["continuation"] == {"of": "八、4#1", "kind": "columns", "via": "base"}
    assert "continuation" not in soe["八、9#17"]  # 继续涉入不是续表（补回账面余额变动表后从 #16 移到 #17）
    assert soe["八、18#5"]["continuation"] == {"of": "八、18#4", "kind": "rows", "via": "previous"}
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
#: 2026-10-23 R8.2 上市 五-10-1 / 五-11-1 网格死列折成逻辑列（用户拍板）：两张表 6 列全对上（各 4→6），
#:   上市 0.9272→0.9360（对上 815→819，分母 879→875）。
#: 2026-10-24 R8.4 批 9b-1 单体模板表头按底稿披露表（用户「单体都按底稿披露表格式」，design §17.5）：国企 0.9012→0.9306、
#:   对上 611→617；none 11→14 是三张原先按错表名「配上」却一列都对不上的合并表（五-18-4 / 五-18-6 / 五-18-8：单体
#:   八、18 表名与内容错位已改正，单体本就没有超额亏损表）。五-18-9「发起规模」仍对不上（与 HEAD 同）：单体沿用 G7
#:   底稿 B323「发起」/ B324「规模」的两层读法（g7_column_source_facts），合并按 Word 写一格；是文字列，不取数。
#:   上市 0.9360→0.9339、对上 819→819：五-62-3 单体按底稿写
#:   「主营业务收入 / 主营业务成本」（合并是「收入 / 成本」，−4），五-23-5 / 五-23-6 单体在建工程两张表名改正后对上
#:   （+2 / +2）；none 26→25。底稿合并单元格漏并的三张（国企 八、4 第 8 张「其他变动」、上市 五、15 第 4 / 5 张
#:   「逾期本金」，白名单 exceptions）单体保留原分组，五-4-6 / 五-15-4 照旧逐列对上。
#: 2026-10-25 R8.4 批 9b-2 单体表名按底稿复位（5914e315b 改成的 Word 提示段换回业务名）、删重复表、补表，映射生成器加
#:   「合并表标题 ↔ 单体表名」对照（gen_consol_standalone_note_mapping._TITLE_ALIASES：合并 Word 提示句 / 「期末本公司…」
#:   说法认回单体表）：国企 0.9306→0.9418、对上 617→631、none 14→11（五-18-8 超额亏损表补上；五-54-4 单体是三组列合表，
#:   如实不对）；上市 0.9339→0.9375、对上 819→825、none 25→23。
#: 2026-10-26 note-pull-header-formula-closure 浏览器实测（自动映射后映射弹窗报「未对上的列」）：上市 五-5-6~10 组合计提表
#:   单体按底稿 D2 写「期末余额/应收账款」、合并按 Word 写「期末余额/账面余额」→ 词表同义计量词；五-30-2 合并
#:   「…上年年末互抵金额」↔ 单体「…期初互抵金额」（期间词在计量词中间）→ 计量词别名：上市 0.9375→0.9500、对上 825→836。
#: 2026-10-29 note-chain-followup-optimizations R4 逐条核对「未对上的列」（词表按表覆盖 + 两条长词别名，ADR-5）：国企
#:   五-31-2「互抵后的递延所得税资产或负债」= 抵销后余额（+2；「互抵金额」两列单体没有）、五-51-2 单体只列金额即账面价值
#:   （+4；数量列单体没有）、十一-合营企业「持股比例/直接 · 间接」是比例不加总（取数列 670→668）：0.9418→0.9536、对上 631→637；
#:   上市 五-23-3 带勾稽字母的纯期间列（+2）、五-28-4 单期商誉减值（+1）、五-57-2「减：税后归属于少数股东」（+1）、五-13-2
#:   「[佣金支出]」占位括号（+1）、十七-境内外两张单期表（+4）、十七-每股收益不加总（取数列 880→878）：0.9500→0.9624、
#:   对上 836→845；none 不变。收入 ↔ 主营业务收入（国企 五-64-3、上市 五-62-3）语义待用户定，未改。
_RATCHET = {
    "soe": {"coverage": 0.9536, "matched": 637, "none": 11},
    "listed": {"coverage": 0.9624, "matched": 845, "none": 23},
}


def test_period_only_requires_same_item_and_listed_19_2_title(catalog):
    """R7.7 收尾复核：「只写了期间」不把另一项（应付利息 / 面值）当成余额；上市 五-19-2 按表名选中单体同表、逐列对上。"""
    items = {(std, i["consol"]): i for std in ("soe", "listed") for i in catalog["correspondence"][std]}
    assert "期初余额" in items[("soe", "五-50-2")]["unmatched"]  # 单体只有「年初应付利息」，不是期初余额
    assert {"期末余额/面值", "上年年末余额/面值"} <= set(items[("listed", "五-12-2")]["unmatched"])  # 单体只有余额没有面值
    item = items[("listed", "五-19-2")]
    assert item["standalone"] == "五、19#1" and item["chosen_name"] == "期末其他权益工具投资情况"
    assert item["unmatched"] == [] and item["matched"] == item["amount_columns"] == 4


def test_listed_logical_column_tables_fully_correspond(catalog):
    """R8.2：上市 五-10-1 / 五-11-1 折成逻辑列后与单体同表逐列精确对上（原网格存时两列同键，按多列认领全部放弃）。"""
    items = {i["consol"]: i for i in catalog["correspondence"]["listed"]}
    for sid, table in (("五-10-1", "五、10#0"), ("五-11-1", "五、11#0")):
        assert items[sid]["unmatched"] == [] and items[sid]["columns"] == [[c, table, c, "exact"] for c in range(1, 7)]
    dup = {a["id"] for a in catalog["anomalies"] if a["kind"] == "duplicate_column_keys" and a["variant"] == "listed_consolidated"}
    assert not dup & {"五-10-1", "五-11-1"}


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


def test_listed_portfolio_tables_take_carrying_amount_via_synonym(catalog):
    """上市 五-5-6~10 组合计提表：合并「期末余额/账面余额」↔ 单体（底稿）「期末余额/应收账款」按同义计量词对上，
    坏账准备照旧精确；五-30-2 上年年末互抵金额按别名对上单体期初互抵金额（2026-10-26）。"""
    items = {i["consol"]: i for i in catalog["correspondence"]["listed"]}
    for n in range(6, 11):
        item = items[f"五-5-{n}"]
        table = f"五、5#{n - 1}"
        assert item["standalone"] == table and item["unmatched"] == [], item
        assert item["columns"] == [[1, table, 1, "synonym"], [2, table, 2, "exact"], [4, table, 4, "synonym"],
                                   [5, table, 5, "exact"]], item
    item = items["五-30-2"]
    assert item["unmatched"] == [] and [3, "五、30#1", 3, "exact"] in item["columns"], item


def test_r4_overrides_and_aliases_correspond(catalog):
    """note-chain-followup-optimizations R4：逐条核对未对上的列后，按表覆盖 / 长词别名修好的对应（ADR-5）。"""
    items = {(std, i["consol"]): i for std in ("soe", "listed") for i in catalog["correspondence"][std]}
    # 国企 五-31-2：单体「报告期末 / 报告年初互抵后的递延所得税资产或负债」按别名对上抵销后余额；「互抵金额」两列单体没有
    item = items[("soe", "五-31-2")]
    assert item["columns"] == [[2, "八、31#1", 1, "exact"], [4, "八、31#1", 3, "exact"]], item
    assert item["unmatched"] == ["期末/递延所得税资产和负债互抵金额", "期初/递延所得税资产和负债互抵金额"], item
    # 国企 五-51-2：单体只列金额（= 账面价值），数量列单体没有
    item = items[("soe", "五-51-2")]
    assert item["columns"] == [[c, "八、51#1", c // 2, "exact"] for c in (2, 4, 6, 8)], item
    assert item["unmatched"] == ["期初余额/数量", "本期增加/数量", "本期减少/数量", "期末余额/数量"], item
    # 上市：带勾稽字母的纯期间列、「减：」勾稽式、Word 占位方括号 —— 逐列全对上
    for sid in ("五-23-3", "五-57-2", "五-13-2"):
        item = items[("listed", sid)]
        assert item["unmatched"] == [] and item["matched"] == item["amount_columns"], (sid, item)
    assert {(1, 1), (8, 8)} <= {(c, s) for c, _t, s, _r in items[("listed", "五-23-3")]["columns"]}
    assert [4, "五、57#1", 6, "exact"] in items[("listed", "五-57-2")]["columns"]
    assert items[("listed", "五-13-2")]["columns"] == [[1, "五、13#1", 1, "exact"], [3, "五、13#1", 2, "exact"]]
    # 单体只有一期：商誉减值金额 = 本期；业绩承诺四列与上期减值单体没有
    assert items[("listed", "五-28-4")]["columns"] == [[7, "五、28#3", 2, "exact"]]
    for n in (1, 2):
        table = f"十七、境内外会计准则下会计数据差异#{n - 1}"
        item = items[("listed", f"十七-境内外会计准则下会计数据差异-{n}")]
        assert item["columns"] == [[1, table, 1, "exact"], [3, table, 2, "exact"]], item
        assert item["unmatched"] == ["净利润/上期发生额", "净资产/上年年末余额"], item


def test_r4_ratio_overrides_leave_amount_columns(catalog):
    """持股比例（直接 / 间接）与每股收益是比例 / 每股金额，不跨企业相加：移出取数列，不再报「未对上」。"""
    items = {(std, i["consol"]): i for std in ("soe", "listed") for i in catalog["correspondence"][std]}
    for std, sid, cols in (("soe", "十一-本公司的合营企业-1", (4, 5)), ("listed", "十七-净资产收益率和每股收益-1", (2, 3))):
        assert items[(std, sid)]["amount_columns"] == 0 and items[(std, sid)]["unmatched"] == [], sid
        entry = _by_id(catalog, f"{std}_consolidated")[sid]
        assert all(entry["columns"][c][1].endswith("|ratio") for c in cols), entry["columns"]


def test_column_overrides_hit_existing_columns(catalog):
    """词表逐表覆盖每条都命中现存表的数据列：表改名 / 删表后覆盖会静默失效，覆盖行名列（第 0 列）也不允许。"""
    vocab = load_vocabulary()
    assert vocab.column_overrides  # 判据抽不到值时不许空转
    hit: set[tuple[str, str, int]] = set()
    for variant, entries in catalog["variants"].items():
        consol = variant.endswith("_consolidated")
        for e in entries:
            prefix = _override_table_key(*table_identity(variant, e["id"] if consol else f"{e['section']}#{e['name']}"))
            hit.update((*prefix, c) for c in range(1, len(e["columns"])) if (*prefix, c) in vocab.column_overrides)
    assert set(vocab.column_overrides) - hit == set()


def test_committed_file_location():
    assert LIBRARY_PATH.name == "note_table_header_library.json" and LIBRARY_PATH.exists()
