"""守卫：单体附注模板（上市 / 国企）的表头按底稿披露表（spec consol-note-header-library-and-node-reaggregate R8.4
批 9b，design §17.5）。

权威 = 底稿模板 xlsx 的附注披露 sheet（用户 2026-10-16「表格以底稿 xlsx 为准」、2026-10-24「单体都按底稿披露表格式，
包括上市版」）。``note_workpaper_disclosure`` 切表，``note_template_workpaper_alignment`` 配对、逐列比；白名单
``data/note_template_workpaper_alignment_allowlist.json`` 的 ``corrections``（底稿笔误 / 提示）先套到底稿表上，
``exceptions`` 是整张表不按底稿的（带理由；「批 9b-2 待改」= 结构差异，改完删条目）。

取代 spec 69 的 ``test_note_template_header_alignment.py``（单体按合并模板对齐，与用户口径相反）；单体 ↔ 合并的列对应
由标题行库目录的棘轮守（``test_note_table_header_catalog.py``）。
"""
from __future__ import annotations

import json

import pytest

from app.services import note_template_workpaper_alignment as A
from app.services import note_workpaper_disclosure as W


# ─── 切表（真底稿册） ────────────────────────────────────────────────────────


def _tables(wp_code: str, std: str, sheet: str) -> list[W.WpTable]:
    return list(W.workpaper_tables(wp_code, std, sheet))


def _at(tables: list[W.WpTable], row: int) -> W.WpTable:
    return next(t for t in tables if t.header_rows[0] == row)


def test_group_names_strip_hints_and_keep_both_periods():
    """D2 上市「组合计提项目：组合1」：两行表头、合并的期间分组（标签列表头底稿留白，比对时不比）；表名候选到上一张表的
    数据行为止。"""
    t = _at(_tables("D2", "listed", "附注披露信息(上市公司)"), 66)
    assert t.title == "组合计提项目：组合1"
    assert ["/".join(p) for p in t.paths] == [
        "", "期末余额/应收账款", "期末余额/坏账准备", "期末余额/预期信用损失率(%)",
        "上年年末余额/应收账款", "上年年末余额/坏账准备", "上年年末余额/预期信用损失率(%)"]
    assert t.row_labels[:2] == ["1年以内", "1-2年"]


def test_hint_title_is_skipped_for_pairing():
    """K2 国企：表上方最近一行是提示「（根据性质选择披露方式）」，配对用更上面的「其他流动资产」。"""
    t = _at(_tables("K2", "soe", "附注披露信息（国企）"), 7)
    assert W.name_key(t.title_candidates[0]) == "" and "其他流动资产" in t.title_candidates
    assert ["/".join(p) for p in t.paths] == ["项目", "期末账面价值", "年初账面价值"]


def test_multi_cell_hint_is_not_a_title_and_first_table_takes_section_title():
    """K6 国企 A5「【注：1.…；」~ A8「4.…。】」是一段提示（只有 A5 带「【」）：首表上方没有表名；配对时以本节标题
    「持有待售资产」作表名，配上模板同名表（原以提示末行配给了模板里以这行字为名的重复表）。"""
    t = _tables("K6", "soe", "附注披露信息（国企）")[0]
    assert t.header_rows[0] == 9 and t.title_candidates == []
    sec = next(s for s in A.load_templates()["soe"]["sections"] if s["section_number"] == "八、12")
    res = A.pair_section("soe", "八、12", sec["tables"], W.section_entries()[("soe", "八、12")], sec["section_title"])
    assert ([0], 9) in [(p.tpl_idx, p.wp[0].header_rows[0]) for p in res.pairs]
    # 以提示末行为名的重复表批 9b-2 已删（`fix_note_k_complex_structure.py` k6-soe drops）；模板表全部配上底稿
    assert not any("应披露" in str(t.get("name")) for t in sec["tables"]) and res.tpl_only == []


def test_unmerged_group_name_covers_the_cells_to_its_right():
    """H10 上市「试运行销售损益」：「本期发生额」只写在 B 格、没合并，盖住右侧留空的 C 格。"""
    t = _at(_tables("H10", "listed", "附注披露信息（上市公司）"), 27)
    assert ["/".join(p) for p in t.paths] == ["项目", "本期发生额/收入", "本期发生额/成本", "上期发生额/收入", "上期发生额/成本"]


def test_three_level_table_collapses_or_splits_by_period():
    """F1 国企「预付款项按账龄列示」三层两期：一张模板表时父表头取期间、子列名写「账面余额-金额」（也认只留一段的
    「账面余额 / 比例(%)」），按期间拆表时每张两层。"""
    t = _at(_tables("F1", "soe", "附注披露信息(国企)"), 8)
    assert "/".join(t.paths[1]) == "期末数/账面余额/金额"
    qualified, collapsed = A.two_level_forms(t)
    assert ["/".join(p) for p in qualified.paths][:4] == [
        "账龄", "期末数/账面余额-金额", "期末数/账面余额-比例(%)", "期末数/坏账准备"]
    assert ["/".join(p) for p in collapsed.paths] == [
        "账龄", "期末数/账面余额", "期末数/比例(%)", "期末数/坏账准备", "期初数/账面余额", "期初数/比例(%)", "期初数/坏账准备"]
    parts = A.split_by_period(t)
    assert parts is not None and len(parts) == 2
    assert ["/".join(p) for p in A.two_level_forms(parts[1], "（续：期初数）")[0].paths] == [
        "账龄", "账面余额/金额", "账面余额/比例(%)", "坏账准备"]


def test_stacked_cells_with_the_same_span_are_one_label():
    """J2 国企「设定受益计划情况」：「设定受益计划净负债」与下一行「（净资产）」盖同样两列，是一个词拆两行。"""
    t = _at(_tables("J2", "soe", "附注披露信息（国有企业）"), 13)
    form = A.two_level_forms(t)[0]
    assert {c.raw[0] for c in form.columns[1:]} >= {"设定受益计划净负债（净资产）"}
    assert all({c.raw[0] for c in f.columns[1:]} >= {"设定受益计划净负债（净资产）"} for f in A.two_level_forms(t)), \
        "盖多列的上下两段在每种写法里都连成一段"


def test_single_column_stacked_cells_are_one_label_and_two_levels_also_match():
    """G7 国企 B323「发起」/ B324「规模」都只盖这一列：读作一段「发起规模」；模板沿用 G7 底稿 / 前端的两层写法
    （分组「发起」+ 列名「规模」，g7_column_source_facts），逐段连起来的字相同，也算一致；只写「规模」不算。"""
    t = _at(_tables("G7", "soe", "附注披露信息（国企）"), 323)
    assert [["/".join(p) for p in f.paths][:3] for f in A.two_level_forms(t)] == [["项目", "发起规模", "期末数/账面价值"]]
    cols = [("项目",), ("发起", "规模"), ("期末数", "账面价值"), ("期末数", "最大损失敞口"),
            ("期初数", "账面价值"), ("期初数", "最大损失敞口"), ("列报项目",)]
    assert A.same_as_workpaper(cols, t)
    assert A.same_as_workpaper([cols[0], ("发起规模",), *cols[2:]], t)
    assert not A.same_as_workpaper([cols[0], ("规模",), *cols[2:]], t)


def test_stage_label_written_in_one_cell_is_two_levels():
    """K1 国企三阶段表把「第一阶段」与「未来12个月预期信用损失」写在同一格里换行：按两层（与 G2 同表一致）。"""
    t = _at(_tables("K1", "soe", "附注披露信息（国企）"), 63)
    assert A.two_level_forms(t)[0].columns[1].raw == ("第一阶段", "未来12个月预期信用损失")


def test_name_key_strips_circled_numbers_before_nfkc():
    assert W.name_key("① 按账龄披露") == "按账龄披露"
    assert W.name_key("（2）按坏账计提方法分类披露（不适用的，删除）：") == "按坏账计提方法分类披露"


@pytest.mark.parametrize("tpl, wp", [
    (("期末余额",), ("期末数",)),  # 用户 2026-10-24「期末余额和期末数…都算通过，是一个意思的」
    (("上年年末余额",), ("期初数",)),
    (("年初余额",), ("期初余额",)),
    (("期末余额", "账面余额"), ("期末数", "账面余额")),  # 分组里的期间词
    (("期初账面价值",), ("年初账面价值",)),  # 期间开头 + 计量词
    (("期末数", "金额"), ("期末余额", "余额")),  # 纯计量词不计
    (("本期变动情况", "计提"), ("本期变动金额", "计提")),  # measure_aliases
    (("减值准备",), ("坏账准备",)),  # measure_synonyms
    (("实际利率(%)",), ("实际利率",)),  # 单位注记
])
def test_same_meaning_wording_passes(tpl, wp):
    assert A.same_text(tpl, wp) and A.same_text(wp, tpl)


@pytest.mark.parametrize("tpl, wp", [
    (("主营业务收入",), ("收入",)),  # 意思不同（营业收入表的行分主营 / 其他业务）
    (("期末余额",), ("金额",)),  # 「金额」不带期间
    (("期末余额",), ("期初余额",)),
    (("期末余额", "余额"), ("期末余额",)),  # 层数不同（长期借款两层 → 底稿一层）
    (("期末余额", "利率区间"), ("利率区间",)),
    (("账面余额/金额",), ("账面余额-金额",)),  # 分组子列名带「/」编辑器只显示最后一段，不算同一写法
])
def test_different_meaning_or_structure_fails(tpl, wp):
    assert not A.same_text(tpl, wp)


def test_lone_amount_column_takes_the_table_period():
    """整张表没有期间词、只有一列「金额」：按表名期间认（K3 上市「项目 | 金额 | 未偿还或未结转的原因」≡ 模板「期末余额」）。"""
    tpl = [("项目",), ("期末余额",), ("未偿还或未结转的原因",)]
    wp = [("项目",), ("金额",), ("未偿还或未结转的原因",)]
    assert A._same_paths(tpl, wp, "其中，账龄超过1年的重要其他应付款")
    assert not A._same_paths(tpl, wp, "账龄超过1年的重要其他应付款（续：上年年末余额）"), "表名是期初，模板写期末不算"
    assert not A._same_paths([("项目",), ("期末余额",), ("期初余额",)], [("项目",), ("金额",), ("金额",)]), "两列「金额」不认"


def test_label_column_accepts_one_of_the_alternatives():
    """标签列：底稿 K7 国企 A7「项目/类别」二选一，模板写「项目」也算一致；底稿留白不比。"""
    assert A._same_paths([("项目",), ("期初余额",)], [("项目/类别",), ("期初余额",)])
    assert A._same_paths([("项目",), ("期初余额",)], [(), ("期初数",)])
    assert not A._same_paths([("类别",), ("期末余额",)], [("项目",), ("期末余额",)])


def test_corrections_only_touch_the_named_segment():
    t = _at(_tables("F2", "listed", "附注披露信息（上市公司）"), 49)
    fixed, used = A.apply_corrections(t, [{"workpaper": "比例(%", "template": "比例(%)"}])
    assert used == {0}
    assert {W.norm(c.raw[-1]) for c in t.columns if "比例" in c.raw[-1]} == {"比例(%)", "比例(%"}
    assert {W.norm(c.raw[-1]) for c in fixed.columns if "比例" in c.raw[-1]} == {"比例(%)"}
    assert [c.raw[:-1] for c in fixed.columns] == [c.raw[:-1] for c in t.columns], "只换这一段"
    assert "比例(%" in {W.norm(c.raw[-1]) for c in t.columns}, "不改缓存里的原表"


# ─── 配对 ────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def checked():
    allow = A.load_allowlist()
    templates = A.load_templates()
    mismatches, results = A.compare_all(templates, corrections=allow["corrections"])
    return allow, templates, mismatches, results


def _pair(results, std: str, section: str, wp_code: str, row: int) -> list[int]:
    res = next(r for r in results if (r.std, r.section) == (std, section))
    return next(p.tpl_idx for p in res.pairs if p.wp_code == wp_code and p.wp[0].header_rows[0] == row)


def test_section_heading_above_the_table_does_not_win_the_pairing(checked):
    """K1 上市「其他应收款」标题下第一张是「① 按账龄披露」：配给模板的账龄表，不配同名汇总表 T0。行名也指向账龄表，
    去掉两张模板表的行名再比，单靠名字也要分得开（最近的表名完全相同 3 分，更上面的章节标题只按包含计）。"""
    _a, templates, _m, results = checked
    j = _pair(results, "listed", "五、8", "K1", 7)
    tables = next(s for s in templates["listed"]["sections"] if s["section_number"] == "五、8")["tables"]
    assert tables[j[0]]["name"] == "按账龄披露" and tables[0]["name"] == "其他应收款"
    entry = next(e for e in W.section_entries()[("listed", "五、8")] if e["wp_code"] == "K1")
    wp = _at(_tables("K1", "listed", entry["sheet_listed"]), 7)
    aging, summary = (A._pair_score(wp, dict(tables[k], rows=[])) for k in (j[0], 0))
    assert aging > summary, (aging, summary)


def test_row_labels_separate_same_named_tables(checked):
    """K1 国企账龄表只有标题「其他应收款」：行名（1年以内…）把它配给账龄表，不配同名的汇总表。"""
    _a, templates, _m, results = checked
    j = _pair(results, "soe", "八、9", "K1", 6)
    tables = next(s for s in templates["soe"]["sections"] if s["section_number"] == "八、9")["tables"]
    assert tables[j[0]]["name"] == "按账龄披露其他应收款项"


# ─── 守卫 ────────────────────────────────────────────────────────────────────

#: 配上底稿表的模板表张数（2026-10-24 批 9b-1：407 张，38 张没有对应的底稿表）。只比配上的表，配对退化会让
#: 守卫静默变绿 ⇒ 钉住；改模板 / 配对规则使它变化时核对多配上 / 少配上的是哪几张，再改这个数。
#: 批 9b-2：国企 八、4 删重复表后续表单元 3 张 → 2 张（−1）；八、5 两个组合表拆期末 / 期初（+2）；八、9 补回
#: 「其他应收款项账面余额变动」（+1，配 K1 国企第 77 行）；八、18 合营表两层后按底稿配对（原 3 张都配第 230 行，
#: 现合营两张配第 229 行、联营两张配第 257 行），补「②对合营企业或联营企业发生超额亏损的分担额」配第 301 行（+2）⇒ 411；
#: 上市 五、34「…2025年公允价值的变动情况…」原套主表五列、配不上，改按底稿四列后配 G10 上市第 26 行（+1）⇒ 412。
_PAIRED_TEMPLATE_TABLES = 412


def test_paired_template_tables_are_pinned(checked):
    _a, _t, _m, results = checked
    n = sum(len(p.tpl_idx) for r in results for p in r.pairs)
    assert n == _PAIRED_TEMPLATE_TABLES, (
        f"配上底稿的模板表 {n} 张 ≠ 登记的 {_PAIRED_TEMPLATE_TABLES}：少了 = 配对退化（没配上的表不比）；"
        f"多了 = 核对新配上的表后改登记数")


def test_no_mismatch_outside_allowlist(checked):
    allow, _t, mismatches, _r = checked
    outside, _stale = A.check_against_allowlist(mismatches, allow["exceptions"])
    assert not outside, "单体模板表头与底稿披露表不一致（白名单外）：\n" + "\n".join(
        f"  {m.std} {m.section} t{m.table} {m.kind}：{m.detail}" for m in outside)


def test_no_stale_exceptions(checked):
    allow, _t, mismatches, _r = checked
    _outside, stale = A.check_against_allowlist(mismatches, allow["exceptions"])
    assert not stale, f"白名单 exceptions 已失效（模板已与底稿一致，删条目）：{stale}"


def test_every_correction_is_used(checked):
    allow, _t, _m, results = checked
    unused = A.unused_corrections(results, allow["corrections"])
    assert not unused, f"白名单 corrections 没用上（底稿已改 / 表序变了 / 写错字）：{unused}"


def test_allowlist_entries_name_their_template_table(checked):
    allow, templates, _m, _r = checked
    by_sec = {std: {s["section_number"]: s.get("tables") or [] for s in templates[std]["sections"]} for std in W.STDS}
    bad = []
    for e in [*allow["corrections"], *allow["exceptions"], *allow["names"]]:
        tables = by_sec[e["std"]].get(e["section"]) or []
        name = tables[int(e["table"])].get("name") if int(e["table"]) < len(tables) else None
        if name != e["name"] or not str(e.get("reason") or "").strip():
            bad.append((e["std"], e["section"], e["table"], e["name"], name))
    assert not bad, f"白名单条目的表名与模板该序号的表对不上（表序变了）或缺理由：{bad}"


def test_every_registered_sheet_is_found(checked):
    _a, _t, _m, results = checked
    assert not [(r.std, r.section, r.missing_sheets) for r in results if r.missing_sheets]
    assert W.stale_sheet_overrides() == []


def test_column_groups_stay_flat():
    """编辑器 / Word 导出只认一层分组：``_column_groups`` 为扁平 {group,start,span}，``columns[].group`` 不含「/」。"""
    bad = []
    for std in W.STDS:
        doc = json.loads((W.DATA_DIR / f"note_template_{std}.json").read_text(encoding="utf-8"))
        for s in doc["sections"]:
            for j, t in enumerate(s.get("tables") or []):
                for g in t.get("_column_groups") or []:
                    if not (isinstance(g, dict) and {"group", "start", "span"} <= set(g) and "children" not in g
                            and "/" not in str(g["group"])):
                        bad.append((std, s["section_number"], j, g))
                bad += [(std, s["section_number"], j, c) for c in t.get("columns") or []
                        if isinstance(c, dict) and "/" in str(c.get("group") or "")]
    assert not bad, bad


# ─── 表名（spec note-disclosure-pull-regression-and-headless-backend R3.4） ──────────────────────

#: 比过表名的配对表张数（2026-11-04：412 张配上的表按配对单元取首表、去掉底稿那边没有可比表名的 = 381）。
#: 配对退化 / 候选表名抽不到会让表名判据静默变绿 ⇒ 钉住；变化时核对多比 / 少比的是哪几张再改。
_COMPARED_TABLE_NAMES = 381
#: 白名单 names 里 todo 类条数（模板表名待改：上市 五、54 t0「参考披露格式」、五、69 t1 / 五、76 t0「项  目」）。只许减少：
#: 改好一张就删条目并把这个数减一；新增 todo 须先说明为什么不能现在改。
_NAME_TODO = 3


@pytest.fixture(scope="module")
def names_checked(checked):
    allow, templates, _m, results = checked
    mismatches, compared = A.name_mismatches(results, templates)
    return allow, templates, results, mismatches, compared


def test_table_names_match_workpaper_or_allowlist(names_checked):
    allow, _t, _r, mismatches, _c = names_checked
    outside, _stale = A.check_names(mismatches, allow["names"])
    assert not outside, "单体模板表名与底稿披露表名不一致（白名单外）：\n" + "\n".join(
        f"  {m.std} {m.section} t{m.table}「{m.template}」vs 底稿 {m.where}{list(m.workpaper)}（{m.why}）" for m in outside)


def test_no_stale_name_entries(names_checked):
    allow, _t, _r, mismatches, _c = names_checked
    _outside, stale = A.check_names(mismatches, allow["names"])
    assert not stale, f"白名单 names 已失效（表名已一致 / 底稿改了字 / 表序变了，删或改条目）：{stale}"


def test_compared_table_names_are_pinned(names_checked):
    *_rest, compared = names_checked
    assert compared == _COMPARED_TABLE_NAMES, (
        f"比过表名的配对表 {compared} 张 ≠ 登记的 {_COMPARED_TABLE_NAMES}：少了 = 配对退化或底稿候选表名抽不到"
        f"（没比的表不报）；多了 = 核对新比上的表后改登记数")


def test_name_todo_entries_only_shrink(names_checked):
    allow, *_rest = names_checked
    todo = [e for e in allow["names"] if e["category"] == "todo"]
    assert len(todo) == _NAME_TODO, (
        f"names 里 todo {len(todo)} 条 ≠ 登记的 {_NAME_TODO}：少了 ⇒ 把 _NAME_TODO 下调到 {len(todo)}；"
        f"多了 ⇒ 新增的待改表名先说明为什么不能现在改")


def test_name_entries_require_reason_and_known_category():
    m = A.NameMismatch("listed", "五、1", 0, "货币资金", ("货币资金明细",), "differ")
    base = {"std": "listed", "section": "五、1", "table": 0, "name": "货币资金", "workpaper": "货币资金明细"}
    assert A.check_names([m], [dict(base, category="synonym", reason="同义")]) == ([], [])
    with pytest.raises(ValueError, match="缺理由"):
        A.check_names([m], [dict(base, category="synonym", reason=" ")])
    with pytest.raises(ValueError, match="类别"):
        A.check_names([m], [dict(base, reason="没写类别")])
    with pytest.raises(ValueError, match="类别"):
        A.check_names([m], [dict(base, category="looks_fine", reason="类别不在集合里")])
    # 底稿改了字（登记的原字不在现算候选里）⇒ 失效
    _out, stale = A.check_names([m], [dict(base, category="synonym", reason="同义", workpaper="旧字")])
    assert stale and stale[0]["workpaper"] == "旧字"


def test_table_name_key_strips_only_writing_noise():
    k = A.table_name_key
    assert k("其中，重要的应收票据核销情况如下（逐项披露）：") == k("重要的应收票据核销情况（逐项披露）")
    assert k("对于…金融负债，2023年公允价值的变动情况如下表所示：") == k("对于…金融负债，2025年公允价值的变动情况")
    assert k("A、已确认递延所得税资产") == k("已确认递延所得税资产")
    assert k("应付账款附注披露信息：") == k("应付账款")
    assert k("期末发行在外的优先股、永续债等其他金融工具变动情况表") == k("期末发行在外的优先股、永续债等其他金融工具变动")
    assert k("销售费用(合并报表)") == k("销售费用")
    assert k("期末，处于第一阶段的坏账准备：") == k("期末处于第一阶段的坏账准备")
    # 真差异不归一
    assert k("重要的应收账款核销情况") != k("重要的其他应收款核销情况")
    assert k("组合计提项目：组合1") != k("组合计提项目：应收中央企业客户")
    # 一边带期间词、另一边不带算同名；两边期间词不同不算
    assert A.same_table_name(k("上年年末处于第一阶段的坏账准备"), k("处于第一阶段的坏账准备"))
    assert not A.same_table_name(k("期末处于第一阶段的坏账准备"), k("期初处于第一阶段的坏账准备"))


def test_renaming_a_paired_template_table_is_caught(names_checked):
    """改一个已配上底稿的模板表名（配对不变）⇒ 表名判据报出这一张；模板表名是通用占位的也报。"""
    allow, templates, results, _m, _c = names_checked
    import copy

    t2 = copy.deepcopy(templates)
    sec = next(s for s in t2["listed"]["sections"] if s["section_number"] == "五、1")
    assert sec["tables"][0]["name"] == "货币资金"
    sec["tables"][0]["name"] = "受限制的货币资金"
    mismatches, _compared = A.name_mismatches(results, t2)
    outside, _stale = A.check_names(mismatches, allow["names"])
    assert [(m.std, m.section, m.table, m.why) for m in outside] == [("listed", "五、1", 0, "differ")]
    sec["tables"][0]["name"] = "项  目"
    mismatches, _compared = A.name_mismatches(results, t2)
    outside, _stale = A.check_names(mismatches, allow["names"])
    assert [(m.section, m.why) for m in outside] == [("五、1", "template_generic")]
