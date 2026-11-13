"""Word 白名单类别与证据的判定规则（合成输入，不读真实模板 / 底稿）。

spec: note-disclosure-pull-regression-and-headless-backend 任务 6 / R3.3（design §4.3）；真实文件守卫在
``test_note_template_word_tree_alignment``（类别 / 证据 / todo 棘轮 / 与生成器同步）。
"""
from __future__ import annotations

from pathlib import Path

from app.services.note_word_allowlist import WordSide, derive, evidence_problems, split_key
from app.services.note_word_tree import Diff

SEED = {"section_number": "五、8", "section_id": "s8", "parent_section_id": "c5", "_aligned_by": "fix_x",
        "tables": [{"name": "汇总"}, {"name": "账龄"}, {"name": "阶段", "_aligned_by": "spec_y"}]}
BY_ID = {"c5": {"section_id": "c5", "_aligned_by": "chapter_z"}}


def _derive(key, kind="table_columns", *, seed=SEED, paired=None, registered=True, word=None, diff_keys=()):
    return derive(Diff("listed_standalone", kind, key), seed=seed, by_id=BY_ID, paired=paired or {},
                  registered=registered, word=word, table_diff_keys=set(diff_keys))


def test_split_key():
    assert split_key("五、8#t2") == ("五、8", 2)
    assert split_key("五、8") == ("五、8", None)
    assert split_key("七、1#2#t0") == ("七、1", 0)  # 同号第 2 个按编号算


def test_paired_table_is_workpaper_authority():
    got = _derive("五、8#t1", paired={1: "K1", 2: "K1"})
    assert (got["category"], got["evidence"]) == ("workpaper_authority", {"paired_with": "K1"})


def test_unpaired_table_in_registered_section_is_todo_with_marker():
    got = _derive("五、8#t2", paired={1: "K1"})
    assert got["category"] == "todo"
    assert got["evidence"] == {"pairing": "unpaired", "aligned_by": "spec_y"}  # 表级标记优先于节级
    assert "过程标记" in got["reason"]


def test_unregistered_section_is_todo_even_with_section_marker():
    got = _derive("五、8#t0", registered=False)
    assert (got["category"], got["evidence"]) == ("todo", {"pairing": "unregistered", "aligned_by": "fix_x"})


def test_section_count_needs_every_table_paired_or_word_consistent():
    word = WordSide(tables=2, placeholder="")
    # 三张都配上
    got = _derive("五、8", "table_count", paired={0: "G2", 1: "K1", 2: "K1"}, word=word)
    assert (got["category"], got["evidence"]) == ("workpaper_authority", {"paired_tables": "3/3"})
    # t0 没配上，但与 Word 同位置那张一致（没有 五、8#t0 的差异）
    got = _derive("五、8", "table_count", paired={1: "K1", 2: "K1"}, word=word, diff_keys={"五、8#t1"})
    assert got["evidence"] == {"paired_tables": "2/3", "word_consistent": [0]}
    # t0 没配上且与 Word 不一致 ⇒ todo
    got = _derive("五、8", "table_count", paired={1: "K1", 2: "K1"}, word=word, diff_keys={"五、8#t0"})
    assert (got["category"], got["evidence"]["paired_tables"]) == ("todo", "2/3")
    # 没配上的 t2 超出 Word 表数（Word 没有这一张，不能算一致）⇒ todo
    got = _derive("五、8", "table_count", paired={0: "G2", 1: "K1"}, word=word)
    assert got["category"] == "todo"


def test_word_reference_without_tables_is_placeholder():
    word = WordSide(tables=0, placeholder="应收票据（披露格式参考附注五、4）")
    got = _derive("十六、应收票据", "table_count", registered=False, word=word, seed=dict(SEED, tables=[{}]))
    assert (got["category"], got["evidence"]) == (
        "word_placeholder", {"word_tables": 0, "word_text": "应收票据（披露格式参考附注五、4）"})
    # Word 有表就不是占位
    got = _derive("十六、应收票据", "table_count", registered=False, word=WordSide(1, "参照附注八"),
                  seed=dict(SEED, tables=[{}]))
    assert got["category"] == "todo"


def test_user_decision_evidence_is_checked_against_the_document(tmp_path: Path):
    doc = tmp_path / "decision.md"
    doc.write_text("## 用户 2026-10-17 拍板\n原话：国企「八、94 一般风险准备」要留。\n", encoding="utf-8")
    ok = {"category": "user_decision", "evidence": {"decided_on": "2026-10-17", "decision_ref": "decision.md",
                                                    "quote": "国企「八、94 一般风险准备」要留"}}
    assert evidence_problems(ok, tmp_path) == []
    wrong_quote = {**ok, "evidence": {**ok["evidence"], "quote": "八、94 删掉"}}
    assert any("quote" in p for p in evidence_problems(wrong_quote, tmp_path))
    wrong_date = {**ok, "evidence": {**ok["evidence"], "decided_on": "2026-10-18"}}
    assert any("decided_on" in p for p in evidence_problems(wrong_date, tmp_path))
    missing = {**ok, "evidence": {**ok["evidence"], "decision_ref": "nope.md"}}
    assert any("不存在" in p for p in evidence_problems(missing, tmp_path))
    assert any("类别" in p for p in evidence_problems({"category": "fine"}, tmp_path))
