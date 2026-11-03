"""合并附注「前 N 名」表跨企业重排（spec note-pull-followup-closure R10 / ADR-7）。

SQLite 真 ORM，企业树同 ``test_consol_note_subtree_reaggregate``：
  G:consol ─ G:consol_elim / G:parent（无单体项目）/ A:consol / B:subsidiary
  A:consol ─ A:consol_elim / A:parent（A本部）/ A1:subsidiary
各企业单体附注「八、5 应收账款」的「（5）按欠款方归集的期末余额前五名的应收账款」→ 合并「五-5-10」；比例列分母 = 同章
「五-5-1 按账龄披露」本节点已保存的期末账面余额合计。
"""
from __future__ import annotations

from decimal import Decimal

import pytest
import sqlalchemy as sa

from app.models.consol_note_data_models import ConsolNoteData
from app.models.report_models import DisclosureNote
from app.services.consol_note_auto_mapping import auto_map_sections
from app.services.consol_note_detail_apply_service import apply_detail_refresh
from app.services.consol_note_formula_service import consol_note_tables
from app.services.consol_note_subtree_reaggregate import reaggregate_subtree
from app.services.consol_note_topn import (
    TopNEntry,
    rerank,
    topn_columns,
    topn_denominator_table,
    topn_limit,
)
from tests.services.test_consol_note_subtree_reaggregate import db, factory, group, user  # noqa: F401

_YEAR = 2025
_TOPN = "五-5-10"
_AGING = "五-5-1"
_TABLE = "（5）按欠款方归集的期末余额前五名的应收账款"
_HEADERS = ["债务人名称", "账面余额", "占应收账款合计的比例（%）", "坏账准备"]
D = Decimal


# ── 纯函数 ────────────────────────────────────────────────────────────────────


def test_topn_limit_and_every_template_table_is_resolvable():
    assert [topn_limit(t) for t in ("前五名", "前 10 名", "前十二名", "前十名", "按账龄披露")] == [5, 10, 12, 10, None]
    seen = 0
    for tt in ("soe", "listed"):
        for table in consol_note_tables(tt):
            if not topn_limit(table.get("title")):
                continue
            seen += 1
            cols = topn_columns(table.get("headers") or [])
            assert cols is not None and cols.ratio and "准备" not in table["headers"][cols.balance], table["section_id"]
            aging, col, why = topn_denominator_table(tt, table["section_id"])
            assert aging is not None and col is not None, (table["section_id"], why)
            assert aging["parent_section"] == table["parent_section"] and "账龄" in aging["title"]
    assert seen == 4, "国企 应收 / 预付 / 其他应收、上市 其他应收 四张前五名表"


def test_rerank_merges_units_excludes_group_and_takes_top_n():
    cols = topn_columns(["单位名称", "款项性质", "期末余额", "账龄", "比例(%)", "坏账准备"])
    entries = [
        TopNEntry("甲公司", {1: "往来款", 2: "300", 3: "1年以内", 5: "3"}),
        TopNEntry("甲 公司", {1: "保证金", 2: "150", 3: "1年以内", 5: "1.5"}),
        TopNEntry("集团内B", {2: "999"}),
        TopNEntry("乙公司", {2: "200"}),
        TopNEntry("丙公司", {2: "100"}),
        TopNEntry("", {2: "88"}),
    ]
    result = rerank(entries, columns=cols, limit=2, width=6, exclude=["集团内B"], denominator=D("1000"))
    assert [r[0] for r in result.rows] == ["甲公司", "乙公司", "合  计"]
    assert result.rows[0] == ["甲公司", "往来款、保证金", "450.00", "1年以内", "45.00", "4.50"]
    assert result.rows[2] == ["合  计", "", "650.00", "", "65.00", "4.50"]
    assert result.excluded == ["集团内B"] and result.beyond == 1 and result.reasons == []
    blank = rerank(entries, columns=cols, limit=2, width=6, denominator=None, denominator_reason="分母没有数")
    assert blank.rows[0][4] == "" and blank.reasons == ["分母没有数"]
    assert blank.rows[0][0] == "集团内B", "不传集团内单位就照常排名（判据不空转）"


# ── 真 ORM：拉数 / 汇总 ───────────────────────────────────────────────────────


def _row(name: str, balance, provision=None, *, total: bool = False) -> dict:
    return {"label": name, "values": [balance, None, provision], "is_total": total,
            "row_type": "total" if total else "data"}


async def _seed_topn_note(db, project, rows: list[dict]) -> None:
    db.add(DisclosureNote(
        project_id=project.id, year=_YEAR, note_section="八、5", section_title="应收账款", status="draft",
        table_data={"_tables": [{"name": _TABLE, "headers": _HEADERS, "rows": rows}]},
    ))
    await db.flush()


async def _seed(db, group) -> None:
    await _seed_topn_note(db, group["A"], [
        _row("甲公司", 300.0, 30.0), _row("乙公司", 200.0), _row("B子公司", 500.0), _row("丙公司", 100.0),
        _row("丁公司", 50.0), _row("合计", 1150.0, 30.0, total=True)])
    await _seed_topn_note(db, group["A1"], [
        _row("甲 公司", 150.0, 5.0), _row("戊公司", 400.0), _row("己公司", 10.0), _row("合计", 560.0, total=True)])
    await _seed_topn_note(db, group["B"], [_row("庚公司", 250.0), _row("辛公司", 60.0), _row("合计", 310.0, total=True)])
    for key, den in (("A:parent", "2000.00"), ("A1:subsidiary", "1000.00"), ("A:consol", "3000.00"),
                     ("G:consol", "5000.00")):
        db.add(ConsolNoteData(project_id=group["G"].id, year=_YEAR, section_id=_AGING, node_key=key,
                              data={"rows": [["1年以内（含1年）", den, ""], ["合  计", den, ""]]}))
    await db.flush()


async def _rec(db, group, node_key: str) -> ConsolNoteData:
    return (await db.execute(sa.select(ConsolNoteData).where(
        ConsolNoteData.project_id == group["G"].id, ConsolNoteData.section_id == _TOPN,
        ConsolNoteData.node_key == node_key).execution_options(populate_existing=True))).scalar_one()


@pytest.mark.asyncio
async def test_leaf_pull_needs_no_mapping_and_drops_group_units(db, group):
    await _seed(db, group)
    res = await apply_detail_refresh(db, project_id=group["G"].id, section_id=_TOPN, year=_YEAR, node_key="A:parent")
    assert res["status"] == "applied" and res["applied_entity_count"] == 1
    data = (await _rec(db, group, "A:parent")).data
    assert data["rows"] == [
        ["甲公司", "300.00", "15.00", "30.00"], ["乙公司", "200.00", "10.00", ""], ["丙公司", "100.00", "5.00", ""],
        ["丁公司", "50.00", "2.50", ""], ["合  计", "650.00", "32.50", "30.00"]]
    assert data["_topn"]["excluded_group_units"] == ["B子公司"] and data["_topn"]["approximate"] is False
    assert "按账龄披露" in data["_topn"]["denominator_source"] and data["_topn"]["denominator"] == "2000.00"


@pytest.mark.asyncio
async def test_reaggregate_reranks_children_top_n_and_marks_approximate(db, group):
    await _seed(db, group)
    result = await reaggregate_subtree(db, group["G"].id, _YEAR, node_key="G:consol", section_ids=[_TOPN])
    assert result["status"] == "persisted", result["failures"]
    a = (await _rec(db, group, "A:consol")).data
    assert [r[0] for r in a["rows"]] == ["甲公司", "戊公司", "乙公司", "丙公司", "丁公司", "合  计"]
    assert a["rows"][0][1] == "450.00" and a["rows"][0][3] == "35.00", "同名单位跨企业合并（「甲 公司」= 甲公司）"
    assert a["_topn"]["approximate"] is True and a["_topn"]["beyond_count"] == 1
    elim = next(c for c in a["_subtree_provenance"]["children"] if c["node_key"] == "A:consol_elim")
    assert elim["included"] is False and elim["reason"] == "差额户不参与前 N 名重排"
    g = (await _rec(db, group, "G:consol")).data
    assert [r[0] for r in g["rows"]] == ["甲公司", "戊公司", "庚公司", "乙公司", "丙公司", "合  计"]
    assert g["rows"][-1][1] == "1400.00" and g["rows"][-1][2] == "28.00", "合计 = 前 5 名之和；比例按 G 节点分母 5000"
    assert g["_topn"]["beyond_count"] == 2 and g["_last_write_source"] == "subtree_aggregate"


@pytest.mark.asyncio
async def test_manual_cells_follow_the_unit_and_missing_denominator_is_reported(db, group):
    await _seed(db, group)
    await reaggregate_subtree(db, group["G"].id, _YEAR, node_key="G:consol", section_ids=[_TOPN])
    record = await _rec(db, group, "G:consol")
    rows = [list(r) for r in record.data["rows"]]
    wu = next(i for i, r in enumerate(rows) if r[0] == "戊公司")
    bing = next(i for i, r in enumerate(rows) if r[0] == "丙公司")
    rows[wu][3], rows[bing][3] = "77.00", "11.00"
    record.data = {**record.data, "rows": rows, "manual_cells": [{"row": wu, "col": 3}, {"row": bing, "col": 3}]}
    await db.execute(sa.delete(ConsolNoteData).where(ConsolNoteData.section_id == _AGING,
                                                       ConsolNoteData.node_key == "G:consol"))
    b_note = (await db.execute(sa.select(DisclosureNote).where(DisclosureNote.project_id == group["B"].id))).scalar_one()
    b_note.table_data = {"_tables": [{"name": _TABLE, "headers": _HEADERS, "rows": [
        _row("壬公司", 900.0), _row("癸公司", 700.0), _row("合计", 1600.0, total=True)]}]}
    await db.flush()

    await reaggregate_subtree(db, group["G"].id, _YEAR, node_key="G:consol", section_ids=[_TOPN])
    g = (await _rec(db, group, "G:consol")).data
    names = [r[0] for r in g["rows"]]
    assert names == ["壬公司", "癸公司", "甲公司", "戊公司", "乙公司", "合  计"], "B 换了单位：丙公司掉出前 5"
    assert g["rows"][names.index("戊公司")][3] == "77.00", "手工格跟着单位走，不按位置"
    assert g["rows"][-1][3] == "112.00", "合计按含手工值的行重算（甲 35 + 戊手工 77）"
    assert g["manual_cells"] == [{"row": names.index("戊公司"), "col": 3}], "掉出前 5 的丙公司的手工格不落到别的行上"
    assert all(r[2] == "" for r in g["rows"]) and any("还没有数" in r for r in g["_topn"]["reasons"]), "分母取不到留空并回报"


@pytest.mark.asyncio
async def test_denominator_prefers_gross_subtotal_over_net_total(db, group):
    """账龄表有「小计 / 减：坏账准备 / 合计」时取小计（扣准备前的毛额）；只有合计取合计；本节点没有数回报原因。"""
    from app.services.consol_note_topn import topn_denominator

    rows = [["1年以内", "800.00", ""], ["1至2年", "200.00", ""], ["小计", "1000.00", ""],
            ["减：坏账准备", "100.00", ""], ["合  计", "900.00", ""]]
    db.add(ConsolNoteData(project_id=group["G"].id, year=_YEAR, section_id=_AGING, node_key="B:subsidiary",
                          data={"rows": rows}))
    db.add(ConsolNoteData(project_id=group["G"].id, year=_YEAR, section_id=_AGING, node_key="A:parent",
                          data={"rows": [["1年以内", "70.00", ""], ["合  计", "70.00", ""]]}))
    await db.flush()

    async def den(node_key):
        return await topn_denominator(db, project_id=group["G"].id, year=_YEAR, template_type="soe",
                                      section_id=_TOPN, node_key=node_key)

    value, note = await den("B:subsidiary")
    assert value == D("1000.00") and note.endswith("期末账面余额小计")
    value, note = await den("A:parent")
    assert value == D("70.00") and note.endswith("期末账面余额合计")
    value, note = await den("A1:subsidiary")
    assert value is None and "还没有数" in note


async def _exclude(db, group, user, node_key: str, entity) -> None:
    """映射弹窗里把该企业排除（前 N 名表不需逐行映射，但排除照样生效）。"""
    from app.models.consol_note_mapping_models import (
        ConsolNoteDetailTemplate,
        ConsolNoteDetailTemplateVersion,
        ConsolNoteMappingBinding,
        ConsolNoteMappingRule,
    )

    tmpl = ConsolNoteDetailTemplate(template_type="soe", section_id=_TOPN, name="前五名", visibility="project",
                                    created_by=user.id)
    db.add(tmpl)
    await db.flush()
    ver = ConsolNoteDetailTemplateVersion(template_id=tmpl.id, version_number=1, rows=[], created_by=user.id)
    db.add(ver)
    await db.flush()
    rule = ConsolNoteMappingRule(project_id=group["G"].id, section_id=_TOPN, template_version_id=ver.id,
                                 source_structure_hash="e" * 64, version_number=1, mappings=[], is_active=True)
    db.add(rule)
    await db.flush()
    db.add(ConsolNoteMappingBinding(project_id=group["G"].id, section_id=_TOPN, entity_node_key=node_key,
                                    entity_project_id=entity.id, rule_id=rule.id, bound_source_hash="e" * 64,
                                    status="excluded"))
    await db.flush()


@pytest.mark.asyncio
async def test_excluded_entity_is_not_ranked_when_pulling_an_aggregate_node(db, group, user):
    """直接对汇总节点拉数（范围 = 其下全部数据叶子）：映射里排除了的企业不计入。"""
    await _seed(db, group)
    await _exclude(db, group, user, "A1:subsidiary", group["A1"])
    res = await apply_detail_refresh(db, project_id=group["G"].id, section_id=_TOPN, year=_YEAR, node_key="A:consol")
    assert res["status"] == "applied" and res["applied_entity_count"] == 1
    rows = (await _rec(db, group, "A:consol")).data["rows"]
    assert [r[0] for r in rows] == ["甲公司", "乙公司", "丙公司", "丁公司", "合  计"], "A1 的戊公司 / 己公司不进排名"
    assert rows[0][1] == "300.00", "A1 的「甲 公司」150 不加进来"


@pytest.mark.asyncio
async def test_auto_mapping_skips_top_n_tables(db, group):
    await _seed(db, group)
    out = await auto_map_sections(db, project_id=group["G"].id, year=_YEAR, section_ids=[_TOPN])
    [section] = out["sections"]
    assert section["status"] == "skipped" and "前 5 名" in section["reason"] and section["template_action"] is None
