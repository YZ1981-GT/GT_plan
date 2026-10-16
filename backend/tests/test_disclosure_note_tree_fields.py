"""Task 10（AC-3.1）：附注生成链透传模板树形字段 + 「全文顺序」口径守卫。

- ``_load_templates`` 把 Word 对齐模板 JSON 的 section_id / level / parent_section_id / sort_index 原样带出；
- ``generate_notes`` 新行写入、旧行**只补空不覆盖**（回填幂等），同项目年度已占用的 section_id 不重复写；
- 读全文顺序一律以 ``sort_order`` 打头：``sort_index`` 是 V019「同层级内序号」，真库 6 个项目里 4 个全为 0，
  首版按它排 ⇒ 汉字码位序「一、三、二」（本组在本 spec 两处 + 他处 4 处同类一并修正）。
"""

from __future__ import annotations

import ast
import json
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.report_models import DisclosureNote
from app.services.note_section_catalog import DATA_DIR, filter_template_sections
from app.services.note_template_merge import merge_templates
from tests.test_disclosure_note_generation_text_order import _added_note, _make_engine, _minimal_template

APP = Path(__file__).resolve().parents[1] / "app"
TREE = {"section_id": "chapter-05-cun-huo", "level": 2, "parent_section_id": "chapter-05", "sort_index": 3}


@pytest.mark.asyncio
@pytest.mark.parametrize("tt", ["soe", "listed"])
@pytest.mark.parametrize("rs", ["standalone", "consolidated"])
async def test_load_templates_passes_tree_fields_from_template_json(tt: str, rs: str) -> None:
    sections = json.loads((DATA_DIR / f"note_template_{tt}.json").read_text(encoding="utf-8-sig"))["sections"]
    # 与生成链同口径先合并（上市版 JSON 有两条「三、研发支出」，合并按编号去重只留一条——模板数据问题，另登记）
    expected = {s["section_id"]: (s["level"], s["parent_section_id"], s["sort_index"])
                for s in filter_template_sections(merge_templates(sections, []), rs)}
    got = await _make_engine()._load_templates(uuid.uuid4(), tt, report_scope=rs)
    assert len(got) == len(expected) and all(t["section_id"] for t in got)
    assert {t["section_id"]: (t["level"], t["parent_section_id"], t["sort_index"]) for t in got} == expected


def _engine(template: dict, *, existing: DisclosureNote | None = None, taken: list[str] | None = None,
            taken_fails: bool = False):
    eng = _make_engine()
    eng._load_templates = AsyncMock(return_value=[template])
    eng._build_table_data = AsyncMock(return_value=None)
    eng._generate_text_with_llm = AsyncMock(return_value=None)

    async def _no_prior(_pid, _yr):
        eng._prior_notes_cache = {}

    eng._preload_data_for_notes = _no_prior

    async def _execute(stmt, *_a, **_k):
        res = MagicMock()
        if [c.key for c in getattr(stmt, "selected_columns", [])] == ["section_id"]:  # 已占用 section_id 查询
            if taken_fails:
                raise RuntimeError("boom")
            res.scalars.return_value.all.return_value = list(taken or [])
        res.scalar_one_or_none.return_value = existing
        res.scalar.return_value = None
        return res

    eng.db.execute = AsyncMock(side_effect=_execute)
    return eng


@pytest.mark.asyncio
async def test_new_note_gets_template_tree_fields() -> None:
    eng = _engine({**_minimal_template(), **TREE})
    await eng.generate_notes(uuid.uuid4(), 2025, "soe")
    note = _added_note(eng)
    assert (note.section_id, note.level, note.parent_section_id, note.sort_index) == tuple(TREE.values())


@pytest.mark.asyncio
async def test_existing_note_filled_only_when_empty() -> None:
    blank = DisclosureNote(project_id=uuid.uuid4(), year=2025, note_section="五、1 存货", section_title="存货")
    await _engine({**_minimal_template(), **TREE}, existing=blank).generate_notes(uuid.uuid4(), 2025, "soe")
    assert (blank.section_id, blank.level, blank.parent_section_id, blank.sort_index) == tuple(TREE.values())

    kept = DisclosureNote(project_id=uuid.uuid4(), year=2025, note_section="五、1 存货", section_title="存货",
                          section_id="converted-sid", level=3, parent_section_id="converted-parent", sort_index=7)
    await _engine({**_minimal_template(), **TREE}, existing=kept).generate_notes(uuid.uuid4(), 2025, "soe")
    assert (kept.section_id, kept.level, kept.parent_section_id, kept.sort_index) == (
        "converted-sid", 3, "converted-parent", 7)


@pytest.mark.asyncio
@pytest.mark.parametrize("taken,fails", [(["chapter-05-cun-huo"], False), ([], True)])
async def test_taken_or_unknown_section_id_is_not_written(taken: list[str], fails: bool) -> None:
    """同项目年度已有行占用该 section_id ⇒ 不补（不制造重复）；占用表都取不到 ⇒ 宁可留空。"""
    blank = DisclosureNote(project_id=uuid.uuid4(), year=2025, note_section="五、1 存货", section_title="存货")
    eng = _engine({**_minimal_template(), **TREE}, existing=blank, taken=taken, taken_fails=fails)
    await eng.generate_notes(uuid.uuid4(), 2025, "soe")
    assert (blank.section_id, blank.level, blank.parent_section_id) == (None, None, None)


def _order_by_first_keys() -> list[tuple[str, str, str, int]]:
    """全仓 ``*.order_by(...)`` 首个排序键（剥掉 .asc()/.desc()/.nulls_last()）为 ``X.sort_index|sort_order`` 的位置。"""
    def _root(node: ast.AST) -> ast.AST:
        while isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            node = node.func.value
        return node

    out = []
    for f in APP.rglob("*.py"):
        tree = ast.parse(f.read_text(encoding="utf-8-sig"))  # 个别文件带 BOM
        for n in ast.walk(tree):
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "order_by" and n.args:
                first = _root(n.args[0])
                if isinstance(first, ast.Attribute) and first.attr in ("sort_index", "sort_order"):
                    out.append((first.attr, ast.unparse(first.value), f.relative_to(APP).as_posix(), n.lineno))
    return out


def test_disclosure_note_reads_order_by_sort_order_first() -> None:
    """附注读全文顺序不得以 sort_index 打头（V019「同层级内序号」，多数项目全为 0）。"""
    keys = [k for k in _order_by_first_keys() if k[1] == "DisclosureNote"]
    assert len(keys) >= 15, f"扫描器没扫到既有的附注排序点，判据空转：{keys}"
    assert [k for k in keys if k[0] == "sort_index"] == []
