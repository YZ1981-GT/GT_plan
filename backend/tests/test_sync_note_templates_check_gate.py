"""Word 同步门禁 ``sync_note_templates_from_word.py --check`` 必须量「真跑一遍会写出什么」。

spec: note-disclosure-pull-regression-and-headless-backend 任务 5（R3.2，design §4.2）。

原缺陷：``--check`` = dry-run，dry_run 一路传进各 phase，phase 在 dry-run 下什么都不改 ⇒ ``write_json`` 比出
「无变化」⇒ 门禁恒绿（2026-11-01 实测：Phase 6 报单体 81 / 116 处更新，同时判「✅ --check 通过」）。
三条判据：①注入一处种子与 Word 的不一致 ⇒ exit 2 且点名该章节（原实现 exit 0）②不注入任何改动 ⇒ exit 0
（防修成永红）③单体 text_after 按位置同步已退役（位置对 Word 会整体错位，不能再改模板）。
"""
from __future__ import annotations

import copy
import json
import shutil
import sys
from pathlib import Path

from scripts.seed import sync_note_templates_from_word as S

DATA = Path(__file__).resolve().parents[1] / "data"


def _run(monkeypatch, capsys, *argv: str) -> tuple[int, str]:
    monkeypatch.setattr(S, "IDENTITY_MISMATCHES", [])
    monkeypatch.setattr(S, "KNOWN_GAP_HITS", set())
    monkeypatch.setattr(sys, "argv", ["sync_note_templates_from_word.py", *argv])
    code = 0
    try:
        S.main()
    except SystemExit as exc:
        code = int(exc.code or 0)
    return code, capsys.readouterr().out


def test_check_passes_on_current_seeds(monkeypatch, capsys):
    """反向断言：现有种子与 Word 一致时 --check 必须通过 —— 否则门禁永红，等于没有门禁。"""
    code, out = _run(monkeypatch, capsys, "--check")
    assert code == 0, out[-3000:]
    assert "✅ --check 通过" in out


def test_check_names_the_section_a_seed_lost(monkeypatch, capsys, tmp_path):
    """种子丢了一张 Word 里有的表：Phase 2 会补回 ⇒ 真跑一遍文件会变 ⇒ --check 必须 exit 2 并点名该章节。

    原实现在 --check 下不让 Phase 2 补（dry_run），文件比出「无变化」，这里会是 exit 0。"""
    for name in ("consol_note_sections_soe.json", "note_template_soe.json"):
        shutil.copy2(DATA / name, tmp_path / name)
    path = tmp_path / "consol_note_sections_soe.json"
    seeds = json.loads(path.read_text(encoding="utf-8"))
    target = "五-1-1"
    assert any(e.get("section_id") == target for e in seeds), "前提：国企合并种子有 五-1-1"
    path.write_text(json.dumps([e for e in seeds if e.get("section_id") != target], ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")
    monkeypatch.setattr(S, "DATA_DIR", tmp_path)

    code, out = _run(monkeypatch, capsys, "--check", "--std", "soe", "--phase", "2")
    assert code == 2, out[-3000:]
    assert f"[新增] consol_note_sections_soe.json {target}" in out
    assert json.loads(path.read_text(encoding="utf-8")) == [e for e in seeds if e.get("section_id") != target], \
        "--check 不得写盘"


def test_standalone_text_after_positional_sync_is_retired():
    """单体表按底稿拆表，按 (节号, 表序) 位置对 Word 表会从第一处拆表起整体错位：Phase 6 不再改单体模板。"""
    data = json.loads((DATA / "note_template_soe.json").read_text(encoding="utf-8"))
    before = copy.deepcopy(data)
    word = S.extract_all_word_tables(S.DOCX_DIR / "soe_standalone.docx")
    assert word, "前提：读得到国企单体 Word 的表"
    assert S.phase6_text_after_and_parent(word, data, "soe", "standalone", False, False) == (0, 0)
    assert data == before


def test_report_changed_sections_names_added_removed_and_changed(tmp_path, capsys):
    """点名口径：合并种子按 section_id、单体模板按 section_number；新增 / 删除 / 内容变化三类都报。"""
    path = tmp_path / "x.json"
    path.write_text(json.dumps([{"section_id": "A", "v": 1}, {"section_id": "B", "v": 1}]), encoding="utf-8")
    keys = S.report_changed_sections(path, [{"section_id": "A", "v": 2}, {"section_id": "C", "v": 1}])
    out = capsys.readouterr().out
    assert keys == ["A", "B", "C"]
    assert "[变化] x.json A" in out and "[删除] x.json B" in out and "[新增] x.json C" in out
    path.write_text(json.dumps({"sections": [{"section_number": "八、1", "v": 1}]}), encoding="utf-8")
    assert S.report_changed_sections(path, {"sections": [{"section_number": "八、1", "v": 1}]}) == []
