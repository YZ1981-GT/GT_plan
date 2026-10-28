"""合并附注空表头不写「列N」（spec note-pull-followup-closure R6）。

旧版 md 种子把整列留白的标签列表头写成「列1」（上市 12 张「组合计提项目：…」表）。现在：生成时整列留白写空、标签列取单体同名表
的首列表头（取不到留空）；种子与已存数据都不再有「列N」占位；Word 同步工具新建 / 重建条目走同一补法。
"""
from __future__ import annotations

import ast
import asyncio
import contextlib
import copy
import importlib.util
import json
import re
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

_BACKEND = Path(__file__).resolve().parents[1]
DATA = _BACKEND / "data"


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, _BACKEND / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


SEED = _load("seed_consol_note_sections", "scripts/seed/seed_consol_note_sections.py")
FIX = _load("fix_consol_note_placeholder_headers", "scripts/fix/fix_consol_note_placeholder_headers.py")
_PLACEHOLDER = re.compile(r"列\d+")


def test_blank_columns_are_not_named_lie_n():
    mh = [["", "期末余额", "", "上年年末余额", ""], ["", "账面余额", "坏账准备", "账面余额", "坏账准备"]]
    merged = SEED.merge_multi_headers([list(r) for r in mh])
    assert merged[0] == "" and merged[1] == "期末余额/账面余额"
    assert not any(_PLACEHOLDER.fullmatch(h) for h in merged)


def test_label_header_comes_from_same_name_standalone_table():
    entry = {"title": "组合计提项目：应收中央企业客户", "headers": ["", "期末余额/账面余额"]}
    assert SEED.fill_label_header(entry, "listed") is True and entry["headers"] == ["账龄", "期末余额/账面余额"]
    assert SEED.fill_label_header(entry, "listed") is False, "已有表头不再改"
    legacy = {"title": "组合计提项目：工程施工", "headers": ["列1", "x"]}
    assert SEED.fill_label_header(legacy, "listed") is True and legacy["headers"][0] == "账  龄", "旧占位「列N」同样补"
    unknown = {"title": "没有这张单体表", "headers": ["列1", "x"]}
    assert SEED.fill_label_header(unknown, "listed") is True and unknown["headers"] == ["", "x"], "取不到留空"
    assert SEED.fill_label_header({"title": "没有这张单体表", "headers": ["", "x"]}, "listed") is False, "本就留空：不算改"
    real = {"title": "组合计提项目：应收中央企业客户", "headers": ["项目", "x"]}
    assert SEED.fill_label_header(real, "listed") is False, "有字的表头不动"


@pytest.mark.parametrize("std", ["soe", "listed"])
def test_consol_seed_has_no_lie_n_headers(std):
    seed = json.loads((DATA / f"consol_note_sections_{std}.json").read_text(encoding="utf-8"))
    bad = [t["section_id"] for t in seed if any(_PLACEHOLDER.fullmatch(str(h or "").strip()) for h in t.get("headers") or [])]
    assert bad == []
    if std == "listed":
        by = {t["section_id"]: t for t in seed}
        assert by["五-5-6"]["headers"][0] == "账龄" and by["五-10-6"]["headers"][0] == "账  龄"
        assert by["五-5-6"]["multi_header"][0][0] == "", "多级表头照 Word 原样（标签列格留白），Word 同步工具按它比对"


def test_fix_tool_only_rewrites_placeholder_label_header():
    assert FIX.fixed_headers({"headers": ["列1", "期末"]}, ["账龄", "期末"]) == ["账龄", "期末"]
    assert FIX.fixed_headers({"headers": ["列1", "期末"]}, ["列1", "期末"]) == ["", "期末"], "模板也是占位 ⇒ 留空"
    assert FIX.fixed_headers({"headers": ["列1", "期末"]}, []) == ["", "期末"]
    assert FIX.fixed_headers({"headers": ["项目", "列2"]}, ["账龄"]) is None, "只看标签列"
    assert FIX.fixed_headers({"rows": []}, ["账龄"]) is None


def test_label_header_title_match_ignores_whitespace():
    entry = {"title": " 组合计提项目： 应收中央企业客户 ", "headers": ["", "x"]}
    assert SEED.fill_label_header(entry, "listed") is True and entry["headers"][0] == "账龄"


def test_standalone_label_header_takes_first_nonblank_same_name_table(tmp_path, monkeypatch):
    (tmp_path / "data").mkdir()
    tpl = {"sections": [{"tables": [
        {"name": "甲 表", "headers": ["", "期末"]},          # 首列表头为空的不收
        {"name": "甲表", "headers": ["账龄", "期末"]},
        {"name": "甲表", "headers": ["项目", "期末"]},       # 同名表取第一张
    ]}]}
    (tmp_path / "data" / "note_template_soe.json").write_text(json.dumps(tpl, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(SEED, "ROOT", tmp_path)
    SEED._standalone_label_headers.cache_clear()
    try:
        assert SEED.standalone_label_header("soe", "甲表") == "账龄"
        assert SEED.standalone_label_header("soe", "乙表") == ""
    finally:
        SEED._standalone_label_headers.cache_clear()


def test_build_tree_json_fills_label_header():
    tables = [{"parent_section": "应收账款", "parent_seq": 5, "title": "组合计提项目：应收中央企业客户",
               "headers": ["", "期末余额/账面余额"], "rows": [], "multi_header": [["", "期末余额"], ["", "账面余额"]]}]
    [entry] = SEED.build_tree_json(tables, "listed")
    assert entry["headers"] == ["账龄", "期末余额/账面余额"] and entry["multi_header"][0][0] == ""


class _FakeDb:
    """``run()`` 的假会话：第 1 条查已存数据，之后都是更新语句（记下来）。"""

    def __init__(self, rows):
        self.rows, self.updates, self.commits, self._n = rows, [], 0, 0

    async def execute(self, stmt):
        self._n += 1
        if self._n == 1:
            return SimpleNamespace(all=lambda: self.rows)
        self.updates.append(stmt)
        return SimpleNamespace()

    async def commit(self):
        self.commits += 1

    def session(self):
        @contextlib.asynccontextmanager
        async def _cm():
            yield self
        return _cm()


@pytest.mark.parametrize("name, writes", [("某集团_2025", False), ("【测试】集团", True)])
def test_fix_tool_run_writes_only_test_projects_with_backup(tmp_path, monkeypatch, name, writes):
    original = {"headers": ["列1", "期末"], "rows": [["1年以内", "1"]]}
    record = SimpleNamespace(id=uuid4(), project_id=uuid4(), section_id="五-5-6", node_key=None,
                             data=copy.deepcopy(original))
    db = _FakeDb([(record, name)])
    monkeypatch.setattr(FIX, "BACKUP_DIR", tmp_path)
    with (patch("app.core.database.async_session", db.session),
          patch("app.services.consol_note_detail_source_service.resolve_section_template_type",
                AsyncMock(return_value="listed")),
          patch("app.services.consol_note_formula_service.find_table", return_value={"headers": ["账龄", "期末"]})):
        assert asyncio.run(FIX.run(None, True)) == 0
    backups = list(tmp_path.glob("consol_note_placeholder_headers_*.json"))
    assert (len(db.updates), db.commits, len(backups)) == ((1, 1, 1) if writes else (0, 0, 0)), "真实项目只出报告"
    assert record.data == original, "已读出的原对象不动"
    if writes:
        saved = json.loads(backups[0].read_text(encoding="utf-8"))
        assert saved == [{"id": str(record.id), "section_id": "五-5-6", "node_key": None, "data": original}]
        assert db.updates[0].compile().params["data"] == {"headers": ["账龄", "期末"], "rows": [["1年以内", "1"]]}


def test_fix_tool_all_projects_is_report_only(monkeypatch):
    run = AsyncMock(return_value=0)
    monkeypatch.setattr(FIX, "run", run)
    with pytest.raises(SystemExit):
        FIX.main(["--all", "--apply"])
    run.assert_not_called()


def test_word_sync_tool_fills_label_header_where_it_builds_entries():
    """Word 同步工具三处建 / 重建条目（Phase 1 列数不一致重建、Phase 2 新增、Phase 3 非报表章节）都补标签列表头。"""
    tree = ast.parse((_BACKEND / "scripts/seed/sync_note_templates_from_word.py").read_text(encoding="utf-8"))
    calls = {fn.name: sum(1 for n in ast.walk(fn) if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "fill_label_header")
             for fn in tree.body if isinstance(fn, ast.FunctionDef)}
    assert {k: v for k, v in calls.items() if v} == {"phase1_consol": 1, "phase2_consol": 1, "phase3_consol": 1}
