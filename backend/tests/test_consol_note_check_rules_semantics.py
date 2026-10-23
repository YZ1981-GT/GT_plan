"""合并附注勾稽规则语义守卫（R7.5）：每条规则两侧都是标题行库语义上可比的单元格，说明与两侧表一致。

原 38 条跨表规则多数两侧不可比（拿期初比期末、拿合计比某一行、拿减值准备比原值、规则错挂到别的科目表上），24 条跨期规则
在同一年度内比续表期初与前表期末，种子里手写的列平衡列号 16 条与表头不符 —— 页面读不到数时从没真正校验过，读到后全是假报。
逐条核对后（design §16.9 批 8c），这里钉住：

- 跨表：对照表存在、同一父章节、不是自己；两侧行名各恰好命中一行；两侧列是金额列、同期间、同计量类别（毛额 / 减值准备 /
  账面价值；列上没写计量时取行名、再取表名，如「存货跌价准备…」变动表的期末数是跌价准备）；说明以父章节开头、是「本表 =
  对照表」一式，等号左边写本表的行、期间与计量，右边写对照表的。
- 列平衡：种子不写列号，标题行库认得出这张变动表；同一张表只挂一条。
- 规则编号在本口径内唯一。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.note_check_rules import rollforward_for
from app.services.note_table_header_library import column_keys, load_vocabulary, norm

DATA = Path(__file__).resolve().parents[1] / "data"
ALLOWANCE = ("坏账准备", "减值准备", "跌价准备")
NEUTRAL = ((), ("合计",))  # 列上没写计量（纯期间列 / 分阶段表的合计列）：计量取行名、表名
PERIOD_WORDS = {"end": ("期末",), "prior": ("期初", "上年年末")}


def _seed(std: str) -> dict[str, dict]:
    return {e["section_id"]: e for e in json.loads((DATA / f"consol_note_sections_{std}.json").read_text(encoding="utf-8"))}


def _rules(std: str) -> list[tuple[dict, dict]]:
    return [(e, r) for e in _seed(std).values() for r in e.get("check_rules") or []]


def _rows_named(entry: dict, label: str) -> list[int]:
    key = norm(label)
    return [i for i, r in enumerate(entry.get("rows") or []) if isinstance(r, list) and r and norm(r[0]) == key]


def _period(entry: dict, key, row_label: str) -> str | None:
    """行名就是期间（分阶段表「期末余额」行）＞ 列路径期间 ＞ 表名期间词。"""
    words = load_vocabulary().period_words
    if words.get(norm(row_label)) in ("end", "prior"):
        return words[norm(row_label)]
    if key.period:
        return key.period
    title = entry.get("title") or ""
    if "期末" in title:
        return "end"
    if any(w in title for w in PERIOD_WORDS["prior"]):
        return "prior"
    return None


def _measure(entry: dict, key, row_label: str) -> str:
    """计量类别：allowance（坏账 / 减值 / 跌价准备）、net（账面价值）、gross（账面余额 / 纯余额）、其余原样。"""
    text = "".join(key.measure) if key.measure not in NEUTRAL else f"{row_label}{entry.get('title') or ''}"
    if any(w in text for w in ALLOWANCE):
        return "allowance"
    if key.measure in NEUTRAL or key.measure == ("账面余额",):
        return "gross"
    return "net" if key.measure == ("账面价值",) else "/".join(key.measure)


MEASURE_WORDS = {"allowance": ALLOWANCE, "gross": ("余额",), "net": ("账面价值",)}


def _side(entry: dict, row_label: str, col: int) -> tuple[str | None, str, list[str]]:
    """(期间, 计量类别, 问题)。"""
    problems = []
    keys = column_keys(entry)
    if not 0 < col < len(keys):
        return None, "", [f"列 {col} 越界（{len(keys)} 列）"]
    key = keys[col]
    if key.kind != "amount":
        problems.append(f"列 {col}「{key.label}」不是金额列（{key.kind}）")
    hits = _rows_named(entry, row_label)
    if len(hits) != 1:
        problems.append(f"行「{row_label}」命中 {len(hits)} 行")
    return _period(entry, key, row_label), _measure(entry, key, row_label), problems


def _cross_problems(std: str, entry: dict, rule: dict, seed: dict[str, dict]) -> list[str]:
    peer = seed.get(rule.get("peer_section_id"))
    if peer is None or peer is entry:
        return [f"对照表 {rule.get('peer_section_id')} 不存在或是自己"]
    out = []
    if (peer.get("parent_section"), peer.get("parent_seq")) != (entry.get("parent_section"), entry.get("parent_seq")):
        out.append(f"对照表不在同一父章节（{peer.get('parent_section')} ≠ {entry.get('parent_section')}）")
    sp, sm, s_bad = _side(entry, rule["self_row_label"], rule["self_col_index"])
    pp, pm, p_bad = _side(peer, rule["peer_row_label"], rule["peer_col_index"])
    out += [f"本表{x}" for x in s_bad] + [f"对照表{x}" for x in p_bad]
    if sp is None or sp != pp:
        out.append(f"期间不同（本表 {sp}，对照表 {pp}）")
    if sm != pm:
        out.append(f"计量不可比（本表 {sm}，对照表 {pm}）")
    desc = rule.get("description") or ""
    if not desc.startswith(f"{entry.get('parent_section')}："):
        out.append("说明没以父章节开头")
    parts = desc.split("=")
    if len(parts) != 2:
        return out + [f"说明不是「本表 = 对照表」一式（{desc.count('=')} 个等号）"]
    # 逐侧核对：左边写本表的行 / 期间 / 计量，右边写对照表的（只核全文会放过「对照行改成本表也有的行名」）
    for side, text, label, period, measure in (("本表", parts[0], rule["self_row_label"], sp, sm),
                                               ("对照表", parts[1], rule["peer_row_label"], pp, pm)):
        if f"「{norm(label)}」" not in text:
            out.append(f"说明{side}一侧没写行「{norm(label)}」")
        if period and not any(w in text for w in PERIOD_WORDS[period]):
            out.append(f"说明{side}一侧没写期间 {period}")
        if not any(w in text for w in MEASURE_WORDS.get(measure, (measure,))):
            out.append(f"说明{side}一侧没写计量 {measure}")
    return out


@pytest.mark.parametrize("std", ["soe", "listed"])
def test_cross_table_rules_compare_comparable_cells(std):
    seed = _seed(std)
    bad = {}
    for entry, rule in _rules(std):
        if rule.get("mode", "cross_table") == "cross_table":
            problems = _cross_problems(std, entry, rule, seed)
            if problems:
                bad[f"{entry['section_id']} {rule['check_id']}"] = problems
    assert bad == {}


@pytest.mark.parametrize("std", ["soe", "listed"])
def test_column_balance_rules_use_header_library_once_per_table(std):
    per_table: dict[str, int] = {}
    for entry, rule in _rules(std):
        if rule.get("mode") != "column_balance":
            continue
        sid = entry["section_id"]
        per_table[sid] = per_table.get(sid, 0) + 1
        assert not {"opening_col", "increase_col", "decrease_col", "closing_col"} & set(rule), (sid, rule["check_id"])
        assert rollforward_for(std, sid) is not None, f"{sid} {rule['check_id']}：标题行库认不出变动表"
    assert {sid: n for sid, n in per_table.items() if n > 1} == {}


@pytest.mark.parametrize("std", ["soe", "listed"])
def test_check_ids_unique(std):
    ids = [rule["check_id"] for _entry, rule in _rules(std)]
    assert sorted({i for i in ids if ids.count(i) > 1}) == []


def test_guard_catches_the_old_defects():
    """守卫打得出原来的缺陷（判据可伪证）：拿期初比期末、拿合计比明细行、错挂到别的科目、计量不可比。"""
    seed = _seed("soe")
    base = {"check_id": "X", "self_row_label": "合  计", "peer_row_label": "合  计"}
    cases = {
        "期间不同": ("五-10-2", {**base, "self_col_index": 1, "peer_section_id": "五-10-1", "peer_col_index": 1,
                              "description": "存货：跌价准备变动表「合计」期初数 = 存货分类表「合计」期末账面余额"}),
        "计量不可比": ("五-10-2", {**base, "self_col_index": 7, "peer_section_id": "五-10-1", "peer_col_index": 1,
                                "description": "存货：跌价准备变动表「合计」期末数 = 存货分类表「合计」期末账面余额"}),
        "不在同一父章节": ("五-42-2", {**base, "self_col_index": 1, "peer_section_id": "五-41-1", "peer_col_index": 1,
                                    "description": "其他应付款：应付利息「合计」期末余额 = 应交税费「合计」期末余额"}),
        "对照表一侧没写行「短期薪酬」": ("五-40-2", {**base, "self_col_index": 4, "peer_section_id": "五-40-1",
                                             "peer_col_index": 4, "peer_row_label": "短期薪酬",
                                             "description": "应付职工薪酬：短期薪酬列示表「合计」期末余额 = 主表「合计」期末余额"}),
        # 对照行改成本表一侧写过的行名：全文里有「合计」，只有逐侧核对认得出
        "对照表一侧没写行「合计」": ("五-40-2", {**base, "self_col_index": 4, "peer_section_id": "五-40-1", "peer_col_index": 4,
                                          "description": "应付职工薪酬：短期薪酬列示表「合计」期末余额 = "
                                                         "应付职工薪酬列示表「短期薪酬」行期末余额"}),
        "一式": ("五-40-2", {**base, "self_col_index": 4, "peer_section_id": "五-40-1", "peer_col_index": 4,
                           "description": "应付职工薪酬：短期薪酬列示表「合计」期末余额等于主表「合计」期末余额"}),
    }
    for expect, (sid, rule) in cases.items():
        problems = _cross_problems("soe", seed[sid], rule, seed)
        assert any(expect in p for p in problems), (expect, problems)
