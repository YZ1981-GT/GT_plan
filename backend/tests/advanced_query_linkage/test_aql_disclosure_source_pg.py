"""附注源与项目章节树（advanced-query-linkage-closure 任务 19，ADR-AQL-16，design §3.2 / §3.8；R5.4、R10.4 后端）。

改造前（AQ-10）：指标树附注叶子按合并附注模板种子编号（「五-1-1」），与华氏的附注编号「八、1」交集为 0，点任何叶子都
是 0 行；「附注（全部）」把全部表摊平、只取第一张表的表头（列错位）。金标准：章节集合与顺序 = 附注编辑器同一函数
``DisclosureEngine.get_notes_tree``（口径对照）；表的行数、行序、表头 = ``disclosure_notes.table_data`` 原始 JSON（独立读取）。
华氏行只读；版本变化用例在回滚事务里新建【测试】项目并复制华氏「八、1」。
"""
from __future__ import annotations

import json
import uuid

import pytest
import sqlalchemy as sa

from app.models.core import Project
from app.models.report_models import DisclosureNote
from app.services.disclosure_engine import DisclosureEngine
from tests.advanced_query_linkage.gold import AUDIT_YEAR, HS

pytestmark = pytest.mark.pg_only
IND = "/api/custom-query/indicators"
NOTE_SQL = ("SELECT table_data::text FROM disclosure_notes WHERE project_id = :pid AND year = :year "
            "AND note_section = :sec AND NOT is_deleted")


async def _tables(gold, section: str) -> list[dict]:
    raw = await gold.scalar(NOTE_SQL, pid=HS, year=AUDIT_YEAR, sec=section)
    tables = json.loads(raw)["_tables"]
    assert len(tables) >= 2, f"前置：华氏「{section}」至少两张表"
    return tables


def _leaves(tree: list[dict]) -> list[dict]:
    return [leaf for node in tree for leaf in ([node] if "children" not in node else node["children"])]


async def test_hs_note_branch_follows_the_editor_catalog(business, pg_rollback_session) -> None:
    """附注分支 = 「附注目录」+ 本项目章节（集合与顺序同附注编辑器目录）；分支 / 骨架 / 全量都带 X-Notes-Version。"""
    editor = [n["note_section"] for n in await DisclosureEngine(pg_rollback_session).get_notes_tree(HS, AUDIT_YEAR)]
    assert len(editor) > 100, "前置：华氏附注已生成"
    branch = await business.http.get(IND, params={"project_id": str(HS), "year": AUDIT_YEAR, "branch": "disclosure"})
    assert branch.status_code == 200, branch.text[:500]
    leaves = _leaves(branch.json())
    assert leaves[0] == {"key": "disclosure", "label": "附注目录", "columns": [], "supports_conditions": False}
    assert [leaf["key"] for leaf in leaves[1:]] == [f"disclosure_note:{s}" for s in editor]
    assert all(leaf["supports_conditions"] is False and leaf["columns"] == [] for leaf in leaves[1:])
    version = branch.headers["X-Notes-Version"]
    assert len(version) == 12 and version not in ("none", "no-year")
    for params in ({"depth": 1}, {}):
        response = await business.http.get(IND, params={"project_id": str(HS), "year": AUDIT_YEAR, **params})
        assert response.status_code == 200 and response.headers["X-Notes-Version"] == version, params
    full = {n["key"]: n for n in response.json()}
    assert _leaves(full["disclosure"]["children"]) == leaves, "全量树的附注分支与按分支加载的一致"
    # 缺省年度 = 项目审计年度（华氏 2025），不用日历年
    default = await business.http.get(IND, params={"project_id": str(HS), "branch": "disclosure"})
    assert default.headers["X-Notes-Version"] == version


async def test_hs_81_returns_first_table_in_original_order(business, gold) -> None:
    """「八、1」默认第一张表：列 = 三列 + 该表表头，行数、行序、取值 = table_data（变异 #17：行序用例）。"""
    tables = await _tables(gold, "八、1")
    data = await business.ok(HS, "disclosure_note:八、1")
    first = tables[0]
    assert data["columns"] == ["note_section", "section_title", "table_name", *first["headers"]]
    assert data["total"] == len(first["rows"]) and len(data["rows"]) == len(first["rows"])
    assert [r[first["headers"][0]] for r in data["rows"]] == [row["label"] for row in first["rows"]], "行序同原表"
    for got, row in zip(data["rows"], first["rows"]):
        assert [got[h] for h in first["headers"][1:]] == list(row["values"])[:len(first["headers"]) - 1]
        assert got["table_name"] == first["name"] and got["note_section"] == "八、1"
    assert data["meta"]["tables"] == [{"index": i, "name": t["name"], "row_count": len(t["rows"])}
                                      for i, t in enumerate(tables)]
    assert "_row_index" not in data["columns"]


async def test_hs_81_table_switch_and_bad_index(business, gold) -> None:
    tables = await _tables(gold, "八、1")
    second = await business.ok(HS, "disclosure_note:八、1", filters={"table_index": 1})
    assert [r[tables[1]["headers"][0]] for r in second["rows"]] == [row["label"] for row in tables[1]["rows"]]
    assert second["rows"][-1][tables[1]["headers"][0]] == "合计", "第二张表合计行在最后"
    assert second["meta"]["table_index"] == 1
    for bad in (len(tables), "x"):
        detail = await business.error(HS, "disclosure_note:八、1", 400, filters={"table_index": bad})
        assert detail["error_code"] == "INVALID_FILTER_VALUE", detail


async def test_catalog_lists_every_section_and_table(business, gold, pg_rollback_session) -> None:
    """附注目录 = 章节（编辑器目录顺序）× 表，一行一表：表名、行数与原始 JSON 一致。"""
    editor = [n["note_section"] for n in await DisclosureEngine(pg_rollback_session).get_notes_tree(HS, AUDIT_YEAR)]
    raw = {r[0]: (json.loads(r[1]) if r[1] else None, r[2]) for r in await gold.rows(
        "SELECT note_section, table_data::text, is_stale FROM disclosure_notes WHERE project_id = :pid "
        "AND year = :year AND NOT is_deleted", pid=HS, year=AUDIT_YEAR)}
    expected = []
    for section in editor:
        data, stale = raw[section]
        if not isinstance(data, dict):
            continue
        tables = data.get("_tables") if isinstance(data.get("_tables"), list) and data.get("_tables") else [data]
        for table in tables:
            if isinstance(table, dict) and (table.get("rows") or table.get("headers") or table.get("name")):
                expected.append((section, str(table.get("name") or ""), len(table.get("rows") or []), bool(stale)))
    page, rows = await business.all_rows(HS, "disclosure")
    assert page["columns"] == ["note_section", "section_title", "table_name", "row_count", "is_stale"]
    assert [(r["note_section"], r["table_name"], r["row_count"], r["is_stale"]) for r in rows] == expected
    assert page["total"] == len(expected) > 0


async def test_notes_version_changes_when_notes_change(business, pg_rollback_session) -> None:
    """回滚事务：【测试】项目复制华氏「八、1」→ 改它的更新时间 ⇒ X-Notes-Version 变化；再加一节 ⇒ 再变（变异 B6-a）。"""
    session = pg_rollback_session
    pid = uuid.uuid4()
    session.add(Project(id=pid, name="【测试】B6 附注版本", client_name="【测试】B6 附注版本", template_type="soe",
                        report_scope="standalone"))
    await session.flush()
    src = (await session.execute(sa.select(DisclosureNote).where(
        DisclosureNote.project_id == HS, DisclosureNote.year == AUDIT_YEAR, DisclosureNote.note_section == "八、1",
        DisclosureNote.is_deleted == sa.false()))).scalar_one()
    session.add(DisclosureNote(project_id=pid, year=AUDIT_YEAR, note_section="八、1", section_title=src.section_title,
                               table_data=src.table_data, sort_order=src.sort_order, content_type=src.content_type,
                               source_template=src.source_template))
    await session.flush()

    async def _version() -> str:
        response = await business.http.get(IND, params={"project_id": str(pid), "year": AUDIT_YEAR, "depth": 1})
        assert response.status_code == 200, response.text[:500]
        return response.headers["X-Notes-Version"]

    v1 = await _version()
    branch = await business.http.get(IND, params={"project_id": str(pid), "year": AUDIT_YEAR, "branch": "disclosure"})
    assert [leaf["key"] for leaf in _leaves(branch.json())] == ["disclosure", "disclosure_note:八、1"]
    await session.execute(sa.text("UPDATE disclosure_notes SET updated_at = updated_at + interval '1 minute' "
                                  "WHERE project_id = :pid"), {"pid": pid})
    v2 = await _version()
    session.add(DisclosureNote(project_id=pid, year=AUDIT_YEAR, note_section="八、2", section_title="【测试】B6",
                               sort_order=(src.sort_order or 0) + 1))
    await session.flush()
    v3 = await _version()
    assert len({v1, v2, v3}) == 3, (v1, v2, v3)
    # 没有项目 ⇒ none；项目取不到年度 ⇒ no-year（附注分支不建，其余骨架照常）
    none = await business.http.get(IND, params={"depth": 1})
    assert none.headers["X-Notes-Version"] == "none"
