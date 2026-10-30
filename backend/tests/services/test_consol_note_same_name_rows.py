"""同名多行映射按出现序（spec note-pull-followup-closure R11）。

来源表里同一行名出现多次（应收股利「其中：（1）」在「账龄一年以内」「一年以上」下各一行）：原先映射只按行名，两行都进
同一目标（模板里同名的最后一行），一年以内的数落到一年以上。现在读取层带出 ``_occurrence``，建议按出现序号逐个给，
映射可声明 ``source_occurrence``（不声明 = 全部同名行，兼容旧规则），apply 按（行名, 序号）取行、同一来源行只累加一次。
"""
from __future__ import annotations

from uuid import UUID

import pytest
import sqlalchemy as sa

from app.models.consol_note_data_models import ConsolNoteData
from app.models.consol_note_mapping_models import ConsolNoteMappingRule
from app.services.consol_note_auto_mapping import auto_map_sections
from app.services.consol_note_detail_apply_service import apply_detail_refresh
from app.services.consol_note_detail_source_service import compute_source_structure_hash, extract_source_rows
from app.services.consol_note_detail_suggest import suggest_template_rows
from app.services.consol_note_detail_template_service import bind_template_version, create_template
from app.services.consol_note_mapping_rule_service import MappingRuleError, _validate_mappings, confirm_mapping
from app.services.consol_note_standalone_reader import read_source_table
from tests.services.test_consol_note_detail_apply import (  # noqa: F401
    _SECTION,
    _YEAR,
    _seed_disclosure,
    child_projects,
    consol_project,
    db,
    user,
)

DUP = [["（1）", "10", ""], ["（2）", "20", ""], ["（1）", "30", ""]]


def _rows(rows):
    return [{"label": r[0], "values": [float(r[1]), None], "row_type": "data"} for r in rows]


def test_reader_numbers_same_name_rows_and_fingerprint_ignores_it():
    table = {"_tables": [{"name": "t", "headers": ["项目", "本期发生额", "上期发生额"], "rows": _rows(DUP)}]}
    src = read_source_table(table, consol_table={"headers": ["项目", "本期发生额", "上期发生额"]}, table_name="t")
    assert [(r["label"], r["_occurrence"]) for r in src.rows] == [("（1）", 0), ("（2）", 0), ("（1）", 1)]
    assert [i["occurrence"] for i in extract_source_rows(src.rows)] == [0, 0, 1]
    bare = [{k: v for k, v in r.items() if k != "_occurrence"} for r in src.rows]
    assert compute_source_structure_hash(_SECTION, src.rows) == compute_source_structure_hash(_SECTION, bare), (
        "出现序号不进结构指纹（否则已确认的企业全部变成「结构已变化」）")
    # 与 R11 之前的算法（HEAD 934e68f4c 实算）逐字相同：已确认的绑定不因本次改动失效。只比上面两份是不够的 ——
    # 不带 _occurrence 的行会按顺序数出同样的序号，把序号算进指纹两份照样相等
    assert compute_source_structure_hash("五-1-1", src.rows) == (
        "f28b1b842f174a01809c0a03262a6765dca843a2deb3fbd8060357f6968df704")


def _group(labels: list[str]) -> dict:
    return {"source_rows": extract_source_rows([{"label": lbl, "row_type": "data"} for lbl in labels])}


def test_suggestions_split_repeated_labels():
    tpl = [{"target_row_id": "t0", "canonical_name": "（1）"}, {"target_row_id": "t1", "canonical_name": "（1）"},
           {"target_row_id": "t2", "canonical_name": "（2）"}]
    got = suggest_template_rows([_group(["（1）", "（2）", "（1）"])], existing_template_rows=tpl)
    by = {(s["source_label"], s.get("source_occurrence")): s["suggested_target"]["target_row_id"] for s in got}
    assert by == {("（1）", 0): "t0", ("（1）", 1): "t1", ("（2）", None): "t2"}, "第 k 次出现对模板第 k 个同名行"

    single = [{"target_row_id": "t0", "canonical_name": "（1）"}, {"target_row_id": "t9", "canonical_name": "其他"}]
    got = suggest_template_rows([_group(["（1）", "（1）"])], existing_template_rows=single,
                                history_mappings=[{"source_label": "（1）", "source_occurrence": 1, "target_row_id": "t9"}])
    assert [(s["source_occurrence"], s["suggested_target"]["target_row_id"], s["match_type"]) for s in got] == [
        (0, "t0", "exact"), (1, "t9", "history")], "模板只有一个同名行：按名都对它，按序号确认过的历史优先"


@pytest.mark.parametrize("bad", [-1, "1", True, 1.5])
def test_occurrence_must_be_a_non_negative_int(bad):
    with pytest.raises(MappingRuleError) as exc:
        _validate_mappings([{"source_label": "（1）", "target_row_id": "t", "mapping_action": "map", "source_occurrence": bad}])
    assert exc.value.code == "INVALID_OCCURRENCE"
    _validate_mappings([{"source_label": "（1）", "target_row_id": "t", "mapping_action": "map", "source_occurrence": 0}])


async def _setup(db, user, consol_project, child_projects, mappings_of):
    for child in child_projects:
        await _seed_disclosure(db, child.id, DUP)
    tmpl = await create_template(db, template_type="soe", section_id=_SECTION, created_by=user.id, rows=[
        {"canonical_name": "一年以内（1）"}, {"canonical_name": "一年以上（1）"}, {"canonical_name": "（2）"},
        {"canonical_name": "合计", "row_type": "total"}])
    tr = [r["target_row_id"] for r in tmpl["latest_version"]["rows"]]
    vid = UUID(tmpl["latest_version"]["id"])
    await bind_template_version(db, project_id=consol_project.id, section_id=_SECTION, template_version_id=vid,
                                bound_by=user.id)
    h = compute_source_structure_hash(_SECTION, [[r[0]] for r in DUP])
    await confirm_mapping(
        db, project_id=consol_project.id, section_id=_SECTION, year=_YEAR, template_version_id=vid,
        source_structure_hash=h, mappings=mappings_of(tr), confirmed_by=user.id, entity_node_keys=[
            {"node_key": f"{c.company_code}:subsidiary", "project_id": str(c.id), "hash": h} for c in child_projects])
    await apply_detail_refresh(db, project_id=consol_project.id, section_id=_SECTION, year=_YEAR)
    record = (await db.execute(sa.select(ConsolNoteData).where(
        ConsolNoteData.project_id == consol_project.id, ConsolNoteData.section_id == _SECTION))).scalar_one()
    return {r[0]: r[1] for r in record.data["rows"]}


def _m(label, target, occurrence=None):
    return {"source_label": label, "target_row_id": target, "mapping_action": "map",
            **({"source_occurrence": occurrence} if occurrence is not None else {})}


@pytest.mark.asyncio
async def test_apply_takes_rows_by_occurrence(db, user, consol_project, child_projects):
    got = await _setup(db, user, consol_project, child_projects,
                       lambda tr: [_m("（1）", tr[0], 0), _m("（1）", tr[1], 1), _m("（2）", tr[2])])
    assert got["一年以内（1）"] == "20.00" and got["一年以上（1）"] == "60.00" and got["（2）"] == "40.00"
    assert got["合计"] == "120.00"


@pytest.mark.asyncio
async def test_apply_legacy_rule_sums_all_same_name_rows_once(db, user, consol_project, child_projects):
    """不声明序号 = 全部同名行（旧规则照旧）；同一来源行被两条映射认领时只加一次。"""
    got = await _setup(db, user, consol_project, child_projects,
                       lambda tr: [_m("（1）", tr[0]), _m("（1）", tr[1], 1), _m("（2）", tr[2])])
    assert got["一年以内（1）"] == "80.00", "旧规则：两行同名都进来（每家 10 + 30）"
    assert got["一年以上（1）"] == "", "第 2 次出现的那行已被上一条映射加过，不重复加"
    assert got["合计"] == "120.00"


@pytest.mark.asyncio
async def test_auto_mapping_confirms_each_occurrence(db, user, consol_project, child_projects):
    for child in child_projects:
        await _seed_disclosure(db, child.id, DUP)
    out = await auto_map_sections(db, project_id=consol_project.id, year=_YEAR, section_ids=[_SECTION], user_id=user.id)
    assert out["sections"][0]["status"] == "mapped", out
    [rule] = (await db.execute(sa.select(ConsolNoteMappingRule).where(
        ConsolNoteMappingRule.project_id == consol_project.id))).scalars().all()
    keys = sorted((m["source_label"], m.get("source_occurrence")) for m in rule.mappings)
    assert keys == [("（1）", 0), ("（1）", 1), ("（2）", None)]
