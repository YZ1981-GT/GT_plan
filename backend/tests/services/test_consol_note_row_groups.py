"""合并附注明细映射：同名行按分组判别（spec note-chain-followup-optimizations R3 / ADR-4）。

判据：①分组键（一级分组头 / 冒号头 / 表内唯一行细分）对真库常见形态逐行正确，同一处结构重复的只剩组内序号 ②来源少一组 /
组序不同 ⇒ 按分组对到模板同组的行（可自动确认），不再按第几次出现配到别的组 ③模板里同名行不止一个、来源只有一处 ⇒ 按分组对
（原先落到模板最后一个同名行）④只能按位置配的 ⇒ ``position``、不自动确认 ⑤apply 按（行名, 分组）取行：同一映射规则下组序不同
的两家企业各自取对的行 ⑥旧映射（只按行名 / 按第几次出现）照旧 ⑦分组不进结构指纹 ⑧映射校验。
"""
from __future__ import annotations

from uuid import UUID

import pytest
import sqlalchemy as sa

from app.models.consol_note_data_models import ConsolNoteData
from app.services.consol_note_detail_apply_service import apply_detail_refresh
from app.services.consol_note_detail_source_service import compute_source_structure_hash, extract_source_rows
from app.services.consol_note_detail_suggest import is_auto_confirmable, suggest_template_rows
from app.services.consol_note_detail_template_service import bind_template_version, create_template
from app.services.consol_note_mapping_rule_service import MappingRuleError, _validate_mappings, confirm_mapping
from app.services.consol_note_row_groups import group_label, row_groups
from tests.services.test_consol_note_detail_apply import (  # noqa: F401
    _SECTION,
    _YEAR,
    _seed_disclosure,
    child_projects,
    consol_project,
    db,
    user,
)

FIXED = ["一、账面原值合计", "其中：房屋、建筑物", "机器设备", "二、累计折旧合计", "其中：房屋、建筑物", "机器设备"]
FIXED_TYPES = ["total", "data", "data", "total", "data", "data"]


def test_groups_follow_level_one_heads_colon_heads_and_unique_anchors():
    assert row_groups(FIXED, FIXED_TYPES) == [
        ("", 0), ("一、账面原值合计", 0), ("一、账面原值合计", 0), ("", 0), ("二、累计折旧合计", 0), ("二、累计折旧合计", 0)]
    jv = ["合营企业：", "净利润", "综合收益总额", "联营企业：", "净利润", "综合收益总额"]
    assert [g for g, _o in row_groups(jv)] == ["", "合营企业", "合营企业", "", "联营企业", "联营企业"]
    # 没有分组头：按最近的表内唯一行细分（「其中：」成员不算锚点）
    dividends = ["账龄一年以内的应收股利", "其中：（1）", "（2）", "账龄一年以上的应收股利", "其中：（1）", "（2）", "小计："]
    groups = row_groups(dividends, ["data"] * 6 + ["subtotal"])
    assert groups[1] == ("›账龄一年以内的应收股利", 0) and groups[4] == ("›账龄一年以上的应收股利", 0)
    assert groups[2] == ("›账龄一年以内的应收股利", 0) and groups[5] == ("›账龄一年以上的应收股利", 0)
    assert group_label(groups[4][0]) == "账龄一年以上的应收股利"
    # 同一一级分组里还重复：一级分组 + 锚点
    oci = ["二、将重分类进损益的其他综合收益", "1、权益法下可转损益的其他综合收益", "减：前期计入其他综合收益当期转入损益", "小计",
           "2、其他债权投资公允价值变动", "减：前期计入其他综合收益当期转入损益", "小计"]
    groups = row_groups(oci, ["data", "data", "data", "subtotal", "data", "data", "subtotal"])
    assert groups[2][0] == "二、将重分类进损益的其他综合收益›1、权益法下可转损益的其他综合收益"
    assert groups[5][0] == "二、将重分类进损益的其他综合收益›2、其他债权投资公允价值变动"
    assert groups[3][0] != groups[6][0], "两个小计各在自己的细分组"
    # 同一处结构重复（没有任何可分的上下文）：只剩组内序号
    assert row_groups(["（1）", "（2）", "（1）", "（2）"]) == [("", 0), ("", 0), ("", 1), ("", 1)]


def _source(labels: list[str], types: list[str] | None = None) -> dict:
    types = types or ["data"] * len(labels)
    return {"source_rows": extract_source_rows([{"label": lb, "row_type": rt} for lb, rt in zip(labels, types)])}


def _tpl(labels: list[str], types: list[str] | None = None) -> list[dict]:
    types = types or ["data"] * len(labels)
    return [{"target_row_id": f"t{i}", "canonical_name": lb, "row_type": rt} for i, (lb, rt) in enumerate(zip(labels, types))]


def _by(got: list[dict]) -> dict:
    return {(s["source_label"], s.get("source_group")): (s["suggested_target"]["target_row_id"], s["match_type"])
            for s in got}


def test_missing_group_pairs_by_group_not_by_position():
    """来源只有「二、累计折旧合计」一组：原先第 1 次出现对模板第 1 个同名行（一、账面原值下）并可自动确认 ⇒ 错组。"""
    got = suggest_template_rows([_source(FIXED[3:], FIXED_TYPES[3:])], existing_template_rows=_tpl(FIXED, FIXED_TYPES))
    by = _by(got)
    assert by[("其中：房屋、建筑物", "二、累计折旧合计")] == ("t4", "exact")
    assert by[("机器设备", "二、累计折旧合计")] == ("t5", "exact")
    assert all(is_auto_confirmable(s) for s in got)


def test_reordered_groups_and_template_only_duplicates():
    reordered = FIXED[3:] + FIXED[:3]
    got = suggest_template_rows([_source(reordered, FIXED_TYPES[3:] + FIXED_TYPES[:3])],
                                existing_template_rows=_tpl(FIXED, FIXED_TYPES))
    by = _by(got)
    assert by[("机器设备", "一、账面原值合计")] == ("t2", "exact") and by[("机器设备", "二、累计折旧合计")] == ("t5", "exact")
    # 模板里同名行两个、来源只出现一次（在一、下）：原先按行名落到模板最后一个同名行（二、下）
    got = suggest_template_rows([_source(FIXED[:3], FIXED_TYPES[:3])], existing_template_rows=_tpl(FIXED, FIXED_TYPES))
    assert _by(got)[("机器设备", "一、账面原值合计")] == ("t2", "exact")


def test_extra_same_name_row_inside_a_group_still_pairs_within_that_group():
    """来源在「二、」组里多加了一行「其他」（组内重复 ⇒ 细分键）、模板这一组只有一个「其他」⇒ 两行都对这一组的「其他」，
    不会因细分键对不上而退回按位置配到「一、」组。"""
    tpl = ["一、递延所得税资产", "其他", "小计", "二、递延所得税负债", "其他", "小计"]
    tpl_types = ["data", "data", "subtotal", "data", "data", "subtotal"]
    src = ["一、递延所得税资产", "其他", "小计", "二、递延所得税负债", "其他", "租赁形成", "其他", "小计"]
    src_types = ["data", "data", "subtotal", "data", "data", "data", "data", "subtotal"]
    got = suggest_template_rows([_source(src, src_types)], existing_template_rows=_tpl(tpl, tpl_types))
    others = {s["source_group"]: (s["suggested_target"]["target_row_id"], s["match_type"])
              for s in got if s["source_label"] == "其他"}
    assert others == {"一、递延所得税资产": ("t1", "exact"), "二、递延所得税负债": ("t4", "exact"),
                      "二、递延所得税负债›租赁形成": ("t4", "exact")}, others


def test_qizhong_members_are_not_anchors():
    """「其中：」开头的成员行随企业而变（模板「其中：xxx」、企业写实际项目）⇒ 不作细分锚点，锚点取它的上级行。"""
    tpl = ["离职后福利", "其中：基本养老保险费", "失业保险费", "其他", "其他长期职工福利", "其中：xxx", "其他", "合计"]
    src = ["离职后福利", "其中：基本养老保险费", "失业保险费", "其他", "其他长期职工福利", "其中：长期服务奖", "其他", "合计"]
    types = ["data"] * 7 + ["total"]
    got = suggest_template_rows([_source(src, types)], existing_template_rows=_tpl(tpl, types))
    others = sorted((s["suggested_target"]["target_row_id"], s["match_type"]) for s in got if s["source_label"] == "其他")
    assert others == [("t3", "exact"), ("t6", "exact")], others


def test_reader_rows_carry_their_group():
    from app.services.consol_note_standalone_reader import read_source_table

    headers = ["项目", "期末余额", "期初余额"]
    rows = [{"label": lb, "values": [1.0, None], "row_type": rt} for lb, rt in zip(FIXED, FIXED_TYPES)]
    src = read_source_table({"_tables": [{"name": "t", "headers": headers, "rows": rows}]},
                            consol_table={"headers": headers}, table_name="t")
    assert [(r["label"], r["_group"], r["_group_occurrence"]) for r in src.rows][3:] == [
        ("二、累计折旧合计", "", 0), ("其中：房屋、建筑物", "二、累计折旧合计", 0), ("机器设备", "二、累计折旧合计", 0)]


def test_position_only_pairs_need_review():
    got = suggest_template_rows([_source(["（1）", "（2）", "（1）", "（2）"])],
                                existing_template_rows=_tpl(["（1）", "（2）", "（1）", "（2）"]))
    assert {s["match_type"] for s in got} == {"position"} and not any(is_auto_confirmable(s) for s in got)
    assert [s["suggested_target"]["target_row_id"] for s in got] == ["t0", "t2", "t1", "t3"], "仍按第几次出现给建议，供复核"


def test_group_fields_stay_out_of_the_fingerprint():
    rows = [{"label": lb, "row_type": rt} for lb, rt in zip(FIXED, FIXED_TYPES)]
    tagged = [{**r, "_group": "随便", "_group_occurrence": 3} for r in rows]
    assert compute_source_structure_hash(_SECTION, rows) == compute_source_structure_hash(_SECTION, tagged)
    assert [(i["group"], i["group_occurrence"]) for i in extract_source_rows(tagged)][:2] == [("随便", 3), ("随便", 3)], (
        "读取层带出的分组优先")


@pytest.mark.parametrize("bad, code", [
    ({"source_group": 1}, "INVALID_GROUP"),
    ({"source_group": "x" * 501}, "INVALID_GROUP"),
    ({"source_group_occurrence": 0}, "INVALID_GROUP"),
    ({"source_group": "一、", "source_group_occurrence": -1}, "INVALID_GROUP"),
    ({"source_group": "一、", "source_occurrence": 0}, "INVALID_GROUP"),
])
def test_group_selector_validation(bad, code):
    with pytest.raises(MappingRuleError) as exc:
        _validate_mappings([{"source_label": "x", "target_row_id": "t", "mapping_action": "map", **bad}])
    assert exc.value.code == code
    _validate_mappings([{"source_label": "x", "target_row_id": "t", "mapping_action": "map",
                         "source_group": "", "source_group_occurrence": 0}])


# ─── apply：同一映射规则下组序不同的两家企业 ─────────────────────────────────

A_ROWS = [["一、账面原值合计", "", ""], ["其中：房屋、建筑物", "100", ""], ["机器设备", "10", ""],
          ["二、累计折旧合计", "", ""], ["其中：房屋、建筑物", "40", ""], ["机器设备", "4", ""]]
B_ROWS = A_ROWS[3:] + A_ROWS[:3]  # 组序相反、行名集合相同 ⇒ 同一结构指纹、同一条规则


async def _apply(db, user, consol_project, child_projects, mappings_of):
    await _seed_disclosure(db, child_projects[0].id, A_ROWS)
    await _seed_disclosure(db, child_projects[1].id, B_ROWS)
    tmpl = await create_template(db, template_type="soe", section_id=_SECTION, created_by=user.id, rows=[
        {"canonical_name": r[0]} for r in A_ROWS])
    tr = [r["target_row_id"] for r in tmpl["latest_version"]["rows"]]
    vid = UUID(tmpl["latest_version"]["id"])
    await bind_template_version(db, project_id=consol_project.id, section_id=_SECTION, template_version_id=vid,
                                bound_by=user.id)
    h = compute_source_structure_hash(_SECTION, [[r[0]] for r in A_ROWS])
    assert h == compute_source_structure_hash(_SECTION, [[r[0]] for r in B_ROWS]), "夹具：两家同一结构指纹"
    await confirm_mapping(
        db, project_id=consol_project.id, section_id=_SECTION, year=_YEAR, template_version_id=vid,
        source_structure_hash=h, mappings=mappings_of(tr), confirmed_by=user.id, entity_node_keys=[
            {"node_key": f"{c.company_code}:subsidiary", "project_id": str(c.id), "hash": h} for c in child_projects])
    await apply_detail_refresh(db, project_id=consol_project.id, section_id=_SECTION, year=_YEAR)
    record = (await db.execute(sa.select(ConsolNoteData).where(
        ConsolNoteData.project_id == consol_project.id, ConsolNoteData.section_id == _SECTION))).scalar_one()
    return [r[1] for r in record.data["rows"]]


def _gm(label, target, group):
    return {"source_label": label, "target_row_id": target, "mapping_action": "map", "source_group": group,
            "source_group_occurrence": 0}


@pytest.mark.asyncio
async def test_apply_takes_rows_by_group_for_entities_with_different_group_order(db, user, consol_project, child_projects):
    got = await _apply(db, user, consol_project, child_projects, lambda tr: [
        _gm("其中：房屋、建筑物", tr[1], "一、账面原值合计"), _gm("机器设备", tr[2], "一、账面原值合计"),
        _gm("其中：房屋、建筑物", tr[4], "二、累计折旧合计"), _gm("机器设备", tr[5], "二、累计折旧合计")])
    assert got[1:3] == ["200.00", "20.00"] and got[4:6] == ["80.00", "8.00"], "两家各自按分组取行"


@pytest.mark.asyncio
async def test_apply_by_occurrence_misattributes_for_reordered_entity(db, user, consol_project, child_projects):
    """对照：同一夹具按第几次出现取行（R11 旧口径）⇒ 乙公司组序相反，原值行拿到折旧数（分组判别要修的就是这个）。"""
    def occ(label, target, k):
        return {"source_label": label, "target_row_id": target, "mapping_action": "map", "source_occurrence": k}

    got = await _apply(db, user, consol_project, child_projects, lambda tr: [
        occ("其中：房屋、建筑物", tr[1], 0), occ("机器设备", tr[2], 0),
        occ("其中：房屋、建筑物", tr[4], 1), occ("机器设备", tr[5], 1)])
    assert got[1] == "140.00" and got[4] == "140.00", "旧映射行为不变（对照组）"
