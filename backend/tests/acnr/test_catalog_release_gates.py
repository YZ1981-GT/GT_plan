"""T07 发布门禁 run_release_gates 单元测试（design §5.2 / §5.6 / §7.4；段四审计 F4-08 补齐六处语义）。

用合成目录逐个门禁做正反两例（干净目录无违规 + 注入缺陷后该门禁红并点名），不写任何仓库产物。
段四 F4-08 补的六处：sheet_code 全局唯一；cell 自带 formula_ref / uri、`cell:{code}!{A1}`、`sheet:{code}`
往返；alias_policy 真正被读取（禁止别名不相交、non_address_label / merge_into 失效条目）；immutable 比对
不可变字段；ack「所指问题已不存在」= 失效条目；verdict「判 deprecate 的条目仍为有效条目」。

真实目录：T07 发布前的目录必须被门禁报出已知阻断项（孤儿 25、formula_ref / uri 往返失败），与 T01 冻结
夹具交叉核对；「blocking == 0」是 T07 首个合规发布批次之后的验收口径（届时改写该用例）。
"""
from __future__ import annotations

import copy
import json
from datetime import date
from pathlib import Path

import pytest

from app.services.acnr import catalog_release as cr
from app.services.acnr.catalog_release import GateViolation, run_release_gates, group_by_check

_TODAY = date(2026, 10, 27)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_CATALOG_PATH = _REPO_ROOT / "backend" / "data" / "acnr" / "global_catalog.json"


def _clean_catalog() -> dict:
    """一个通过全部门禁的最小合成目录（两 sheet + 两 cell）。"""
    return {
        "version": "1",
        "registry_version": "20261027000000",
        "sheets": [
            {
                "addr_id": "D2/D2-1",
                "domain": "wp",
                "parent_wp_code": "D2",
                "sheet_code": "D2-1",
                "sheet_name": "应收账款审定表",
            },
            {
                "addr_id": "D2/D2-2",
                "domain": "wp",
                "parent_wp_code": "D2",
                "sheet_code": "D2-2",
                "sheet_name": "应收账款明细表",
            },
        ],
        "cells": [
            {
                "addr_id": "D2/D2-1/E10",
                "parent_addr_id": "D2/D2-1",
                "domain": "wp",
                "formula_ref": "WP('D2','D2-1','E10')",
                "uri": "wp://D2/应收账款审定表#E10",
                "cell_address": "E10",
            },
            {
                "addr_id": "D2/D2-2/F20",
                "parent_addr_id": "D2/D2-2",
                "domain": "wp",
                "formula_ref": "WP('D2','D2-2','F20')",
                "uri": "wp://D2/应收账款明细表#F20",
                "cell_address": "F20",
            },
        ],
    }


# ─── 正例：干净目录无违规 ────────────────────────────────────────────────────


def test_clean_catalog_has_no_violations():
    v = run_release_gates(_clean_catalog(), previous=None, report=None, today=_TODAY)
    assert v == [], f"干净目录不应有违规，却有：{[str(x) for x in v]}"


# ─── duplicate ──────────────────────────────────────────────────────────────


def test_duplicate_addr_id_blocked():
    cat = _clean_catalog()
    cat["sheets"].append(copy.deepcopy(cat["sheets"][0]))  # 复制 D2/D2-1
    g = group_by_check(run_release_gates(cat, None, None, today=_TODAY))
    assert "duplicate" in g
    assert any(x.addr_id == "D2/D2-1" for x in g["duplicate"])


def test_sheet_cell_cross_collision_blocked():
    cat = _clean_catalog()
    # 让一个 cell 的 addr_id 与一个 sheet 的 addr_id 相同
    cat["cells"][0]["addr_id"] = "D2/D2-1"
    cat["cells"][0]["parent_addr_id"] = "D2/D2-1"
    g = group_by_check(run_release_gates(cat, None, None, today=_TODAY))
    assert "duplicate" in g
    assert any("同时是 sheet 与 cell" in x.detail for x in g["duplicate"])


# ─── sheet_code（cell addr_id 前缀 == parent） ──────────────────────────────


def test_cell_prefix_mismatch_blocked():
    cat = _clean_catalog()
    cat["cells"][0]["parent_addr_id"] = "D2/D2-2"  # 前缀仍是 D2/D2-1，与 parent 不符
    g = group_by_check(run_release_gates(cat, None, None, today=_TODAY))
    assert "sheet_code" in g
    assert any(x.addr_id == "D2/D2-1/E10" for x in g["sheet_code"])


# ─── orphan（cell 父 sheet 存在） ───────────────────────────────────────────


def test_orphan_cell_parent_missing_blocked():
    cat = _clean_catalog()
    cat["sheets"].pop(0)  # 删掉 D2/D2-1，其 cell 变孤儿
    g = group_by_check(run_release_gates(cat, None, None, today=_TODAY))
    assert "orphan" in g
    assert any("D2/D2-1" in x.detail for x in g["orphan"])


# ─── a1 ─────────────────────────────────────────────────────────────────────


def test_bad_a1_blocked():
    cat = _clean_catalog()
    cat["cells"][0]["cell_address"] = "10E"  # 非法 A1
    cat["cells"][0]["addr_id"] = "D2/D2-1/10E"
    g = group_by_check(run_release_gates(cat, None, None, today=_TODAY))
    assert "a1" in g


def test_a1_addr_tail_mismatch_blocked():
    cat = _clean_catalog()
    cat["cells"][0]["cell_address"] = "E11"  # addr_id 末段仍是 E10
    g = group_by_check(run_release_gates(cat, None, None, today=_TODAY))
    assert "a1" in g
    assert any("不一致" in x.detail for x in g["a1"])


# ─── roundtrip（用新目录解析回本身） ────────────────────────────────────────


def test_roundtrip_broken_by_sheet_code_collision_blocked():
    cat = _clean_catalog()
    # 让第二张 sheet 的 sheet_code 也等于 D2-1（同父级 sheet_code 撞车）：
    # sheet_of("D2","D2-1") 命中两条 → ambiguous → 两张的往返都回不到自身。
    cat["sheets"][1]["sheet_code"] = "D2-1"
    # cell 前缀同步改，避免 sheet_code 门禁先行报（专验 roundtrip）
    cat["cells"][1]["parent_addr_id"] = "D2/D2-2"
    g = group_by_check(run_release_gates(cat, None, None, today=_TODAY))
    assert "roundtrip" in g


# ─── immutable（已发布 addr_id 不得消失） ───────────────────────────────────


def test_immutable_dropped_addr_id_blocked():
    prev = _clean_catalog()
    new = _clean_catalog()
    new["sheets"].pop(1)  # 删 D2/D2-2，但其 cell 还在 → orphan 也会报；immutable 必报
    g = group_by_check(run_release_gates(new, previous=prev, report=None, today=_TODAY))
    assert "immutable" in g
    assert any(x.addr_id == "D2/D2-2" for x in g["immutable"])


def test_immutable_deprecate_in_place_ok():
    prev = _clean_catalog()
    new = _clean_catalog()
    new["sheets"][1]["deprecated"] = True
    new["sheets"][1]["replaced_by"] = "D2/D2-1"
    # 停用但保留 → immutable 不报（roundtrip 跳过 deprecated）
    g = group_by_check(run_release_gates(new, previous=prev, report=None, today=_TODAY))
    assert "immutable" not in g


# ─── ack（豁免清单可伪证 + 到期） ───────────────────────────────────────────


def test_ack_clean():
    acks = {
        "seed_semantic_unverified": [
            {"addr_id": "D2/D2-2/F20", "owner": "acnr", "reason": "语义待核对",
             "expires_on": "2027-04-30"}
        ]
    }
    v = run_release_gates(_clean_catalog(), None, None, today=_TODAY, acknowledgements=acks)
    assert v == []


def test_ack_expired_blocked():
    acks = {
        "ccr_unresolved": [
            {"addr_id": "X", "owner": "acnr", "reason": "缺模板", "expires_on": "2020-01-01"}
        ]
    }
    g = group_by_check(run_release_gates(_clean_catalog(), None, None, today=_TODAY, acknowledgements=acks))
    assert "ack" in g
    assert any("过期" in x.detail for x in g["ack"])


def test_ack_missing_owner_blocked():
    acks = {"ccr_unresolved": [{"addr_id": "X", "reason": "r", "expires_on": "2099-01-01"}]}
    g = group_by_check(run_release_gates(_clean_catalog(), None, None, today=_TODAY, acknowledgements=acks))
    assert "ack" in g
    assert any("缺 owner" in x.detail for x in g["ack"])


# ─── verdict（deprecate 必有可解析 replaced_by） ────────────────────────────


def test_verdict_replaced_by_unresolvable_blocked():
    cat = _clean_catalog()
    cat["sheets"][1]["deprecated"] = True
    verdicts = {
        "sheet_verdicts": [
            {"addr_id": "D2/D2-2", "verdict": "deprecate", "replaced_by": "ZZ/NOPE"}
        ]
    }
    g = group_by_check(run_release_gates(cat, None, None, today=_TODAY, sheet_verdicts=verdicts))
    assert "verdict" in g
    assert any(x.addr_id == "D2/D2-2" for x in g["verdict"])


def test_verdict_resolvable_replaced_by_ok():
    cat = _clean_catalog()
    cat["sheets"][1]["deprecated"] = True
    verdicts = {
        "sheet_verdicts": [
            {"addr_id": "D2/D2-2", "verdict": "deprecate", "replaced_by": "D2/D2-1"}
        ]
    }
    g = group_by_check(run_release_gates(cat, None, None, today=_TODAY, sheet_verdicts=verdicts))
    assert "verdict" not in g


# ─── override（owner/reason/source + 所指存在） ─────────────────────────────


def test_override_missing_source_blocked():
    overrides = {
        "overrides": [
            {"addr_id": "D2/D2-1", "owner": "acnr", "reason": "补 ie", "fields": {}}
        ]
    }
    g = group_by_check(run_release_gates(_clean_catalog(), None, None, today=_TODAY, overrides=overrides))
    assert "override" in g
    assert any("缺 source" in x.detail for x in g["override"])


def test_override_target_missing_blocked():
    overrides = {
        "overrides": [
            {"addr_id": "ZZ/NOPE", "owner": "acnr", "reason": "r", "source": "s", "fields": {}}
        ]
    }
    g = group_by_check(run_release_gates(_clean_catalog(), None, None, today=_TODAY, overrides=overrides))
    assert "override" in g
    assert any("不在目录中" in x.detail for x in g["override"])


def test_override_clean():
    overrides = {
        "overrides": [
            {"addr_id": "D2/D2-1", "owner": "acnr", "reason": "补 ie",
             "source": "fix_acnr_catalog_ie_gap:SAFE:recv", "fields": {}}
        ]
    }
    v = run_release_gates(_clean_catalog(), None, None, today=_TODAY, overrides=overrides)
    assert v == []


# ─── alias（禁止别名与 sheet_name/sheet_code 不相交） ───────────────────────


def test_alias_forbidden_overlaps_sheet_name_blocked():
    cat = _clean_catalog()
    # 构造同父级一名多码 → 禁止别名；再让该别名也是某 sheet 的 sheet_name
    cat["sheets"][0]["sheet_name_aliases"] = ["重名表"]
    cat["sheets"][1]["sheet_name_aliases"] = ["重名表"]
    cat["sheets"][0]["sheet_name"] = "重名表"  # 别名「重名表」又是本父级 sheet_name
    g = group_by_check(run_release_gates(cat, None, None, today=_TODAY))
    assert "alias" in g


# ─── schema ─────────────────────────────────────────────────────────────────


def test_schema_registry_version_bad_blocked():
    cat = _clean_catalog()
    cat["registry_version"] = "2026.1.1"  # 不符 ^\d{14}$
    g = group_by_check(run_release_gates(cat, None, None, today=_TODAY))
    assert "schema" in g


def test_schema_missing_sheet_code_blocked():
    cat = _clean_catalog()
    del cat["sheets"][0]["sheet_code"]
    g = group_by_check(run_release_gates(cat, None, None, today=_TODAY))
    assert "schema" in g


# ─── 真实目录可被门禁模块加载（结构可用，不断言 blocking==0） ────────────────


def test_use_catalog_overrides_get_catalog():
    """use_catalog(index) 作用域内 get_catalog() 返回被覆盖的索引（门禁往返依赖）。"""
    from app.services.acnr import catalog as cat_mod

    synthetic = cat_mod.CatalogIndex(_clean_catalog())
    with cat_mod.use_catalog(synthetic):
        assert cat_mod.get_catalog() is synthetic
    # 退出作用域后恢复（不再是合成索引）
    assert cat_mod.get_catalog() is not synthetic


# ═══ 段四审计 F4-08：六处门禁语义（每处正反两例） ═══════════════════════════════


def _two_parent_catalog() -> dict:
    """D2 一张 + E1 一张，cell 自带 formula_ref 与 uri（审计 A8 合成样例同形）。"""
    return {
        "version": "1",
        "registry_version": "20261027000000",
        "sheets": [
            {"addr_id": "D2/D2-1", "domain": "wp", "parent_wp_code": "D2", "sheet_code": "D2-1", "sheet_name": "明细表D2-1"},
            {"addr_id": "E1/E1-1", "domain": "wp", "parent_wp_code": "E1", "sheet_code": "E1-1", "sheet_name": "审定表E1-1"},
        ],
        "cells": [
            {"addr_id": "D2/D2-1/E10", "parent_addr_id": "D2/D2-1", "domain": "wp",
             "formula_ref": "WP('D2','明细表D2-1','E10')", "uri": "wp://D2/明细表D2-1#E10", "cell_address": "E10"},
        ],
    }


def _ids(g: dict, check: str) -> set[str]:
    return {x.addr_id for x in g.get(check, [])}


def _details(g: dict, check: str) -> list[str]:
    return [x.detail for x in g.get(check, [])]


def test_two_parent_catalog_is_clean():
    assert run_release_gates(_two_parent_catalog(), None, None, today=_TODAY) == []


# ─── 1. sheet_code 全局唯一（需求 4.1 第 2 条） ──────────────────────────────


def test_sheet_code_duplicated_across_parents_blocked():
    cat = _two_parent_catalog()
    cat["sheets"].append({"addr_id": "E1/D2-1", "domain": "wp", "parent_wp_code": "E1",
                          "sheet_code": "D2-1", "sheet_name": "借用编码"})
    g = group_by_check(run_release_gates(cat, None, None, today=_TODAY))
    assert {"D2/D2-1", "E1/D2-1"} <= _ids(g, "sheet_code")
    assert any("全局重复" in d for d in _details(g, "sheet_code"))


# ─── 2. 往返：cell 自带 formula_ref / uri、cell:{code}!{A1}、sheet:{code} ──────


def test_roundtrip_formula_ref_unresolvable_blocked():
    cat = _two_parent_catalog()
    cat["cells"][0]["formula_ref"] = "WP('D2','平台索引名-无此别名','E10')"
    g = group_by_check(run_release_gates(cat, None, None, today=_TODAY))
    assert any("formula_ref 往返" in d for d in _details(g, "roundtrip"))
    assert _ids(g, "roundtrip") == {"D2/D2-1/E10"}


def test_roundtrip_formula_ref_resolving_elsewhere_blocked():
    cat = _two_parent_catalog()
    cat["cells"][0]["formula_ref"] = "WP('E1','审定表E1-1','E10')"  # 能解析，但落到 E1/E1-1/E10
    g = group_by_check(run_release_gates(cat, None, None, today=_TODAY))
    assert any("formula_ref 往返未回本身（得 E1/E1-1/E10）" in d for d in _details(g, "roundtrip"))


def test_roundtrip_formula_ref_not_three_args_blocked():
    cat = _two_parent_catalog()
    cat["cells"][0]["formula_ref"] = "WP('D2','E10')"
    g = group_by_check(run_release_gates(cat, None, None, today=_TODAY))
    assert any("不是三参 WP 写法" in d for d in _details(g, "roundtrip"))


def test_roundtrip_uri_unresolvable_blocked():
    cat = _two_parent_catalog()
    cat["cells"][0]["uri"] = "wp://D2/不存在的表#E10"
    g = group_by_check(run_release_gates(cat, None, None, today=_TODAY))
    assert any("uri 往返" in d for d in _details(g, "roundtrip"))
    assert not any("formula_ref 往返" in d for d in _details(g, "roundtrip"))


def test_roundtrip_sheet_and_cell_index_refs_use_production_parser():
    """sheet_code 跨父级重复 ⇒ 生产解析函数 _index_ref_to_addr_id 对 sheet: / cell: 写法返回 None ⇒ 往返红。"""
    cat = _two_parent_catalog()
    cat["sheets"].append({"addr_id": "E1/D2-1", "domain": "wp", "parent_wp_code": "E1",
                          "sheet_code": "D2-1", "sheet_name": "借用编码"})
    g = group_by_check(run_release_gates(cat, None, None, today=_TODAY))
    details = _details(g, "roundtrip")
    assert any(d.startswith("sheet:D2-1 往返未回本身（得 None）") for d in details)
    assert any(d.startswith("cell:D2-1!E10 往返未回本身（得 None）") for d in details)


def test_roundtrip_skips_deprecated_and_orphan_cells():
    cat = _two_parent_catalog()
    cat["cells"][0]["deprecated"] = True
    cat["cells"][0]["replaced_by"] = "D2/D2-1"
    cat["cells"][0]["formula_ref"] = "WP('D2','平台索引名-无此别名','E10')"  # 停用条目不参与往返
    cat["cells"].append({"addr_id": "Z9/Z9-1/A1", "parent_addr_id": "Z9/Z9-1", "domain": "wp",
                         "formula_ref": "WP('Z9','无','A1')", "cell_address": "A1"})
    g = group_by_check(run_release_gates(cat, None, None, today=_TODAY))
    assert "roundtrip" not in g, [str(x) for x in g.get("roundtrip", [])]
    assert _ids(g, "orphan") == {"Z9/Z9-1/A1"}  # 孤儿只由 orphan 报


# ─── 3. immutable：不可变字段改值（接 check_addr_id_immutable 同一判据） ──────


@pytest.mark.parametrize("seg,idx,field,value", [
    ("cells", 0, "cell_address", "E11"),
    ("sheets", 0, "sheet_code", "D2-9"),
    ("sheets", 1, "parent_wp_code", "E9"),
])
def test_immutable_field_changed_blocked(seg, idx, field, value):
    prev = _two_parent_catalog()
    new = copy.deepcopy(prev)
    new[seg][idx][field] = value
    g = group_by_check(run_release_gates(new, previous=prev, report=None, today=_TODAY))
    assert prev[seg][idx]["addr_id"] in _ids(g, "immutable")
    assert any("不可变字段被改值" in d and field in d for d in _details(g, "immutable"))


def test_immutable_same_catalog_ok():
    prev = _two_parent_catalog()
    g = group_by_check(run_release_gates(copy.deepcopy(prev), previous=prev, report=None, today=_TODAY))
    assert "immutable" not in g


# ─── 4. alias：alias_policy 被真正读取 ───────────────────────────────────────


def _alias_entry(alias: str, disposition: str, **kw) -> dict:
    return {"alias": alias, "disposition": disposition, "owner": "acnr", "reason": "r", **kw}


def test_alias_policy_forbidden_mapping_equals_sheet_name_blocked():
    g = group_by_check(run_release_gates(_two_parent_catalog(), None, None, today=_TODAY,
                                         alias_policy={"forbidden": {"D2": {"明细表D2-1": ["D2-1"]}}}))
    assert any("又是 D2 内的 sheet_name / sheet_code" in d for d in _details(g, "alias"))


def test_alias_policy_forbidden_entry_equals_sheet_code_blocked():
    policy = {"entries": [_alias_entry("D2-1", "forbidden", sheet_codes=["D2-1"])]}
    g = group_by_check(run_release_gates(_two_parent_catalog(), None, None, today=_TODAY, alias_policy=policy))
    assert any("又是 D2 内的 sheet_name / sheet_code" in d for d in _details(g, "alias"))


def test_alias_policy_forbidden_entry_unknown_code_is_stale():
    policy = {"entries": [_alias_entry("通用名", "forbidden", sheet_codes=["D2-9"])]}
    g = group_by_check(run_release_gates(_two_parent_catalog(), None, None, today=_TODAY, alias_policy=policy))
    assert any("失效条目" in d and "D2-9" in d for d in _details(g, "alias"))


def test_alias_policy_valid_entries_ok():
    policy = {"entries": [
        _alias_entry("通用名", "forbidden", sheet_codes=["D2-1"]),
        _alias_entry("D2-目录", "non_address_label"),
        _alias_entry("E1-1旧", "merge_into", target="E1/E1-1"),
    ]}
    report = {"open_problems": {"unregistered_alias_keys": ["D2-目录", "E1-1旧"]}}
    g = group_by_check(run_release_gates(_two_parent_catalog(), None, report, today=_TODAY, alias_policy=policy))
    assert "alias" not in g, [str(x) for x in g.get("alias", [])]


def test_alias_policy_non_address_label_is_catalog_code_stale():
    policy = {"entries": [_alias_entry("E1-1", "non_address_label")]}
    report = {"open_problems": {"unregistered_alias_keys": ["E1-1"]}}
    g = group_by_check(run_release_gates(_two_parent_catalog(), None, report, today=_TODAY, alias_policy=policy))
    assert any("已是目录 sheet_code" in d for d in _details(g, "alias"))


def test_alias_policy_label_key_no_longer_open_is_stale():
    policy = {"entries": [_alias_entry("D2-目录", "non_address_label")]}
    report = {"open_problems": {"unregistered_alias_keys": ["别的键"]}}
    g = group_by_check(run_release_gates(_two_parent_catalog(), None, report, today=_TODAY, alias_policy=policy))
    assert any("所指问题已不存在" in d for d in _details(g, "alias"))


def test_alias_policy_label_key_unverifiable_without_open_problems():
    policy = {"entries": [_alias_entry("D2-目录", "non_address_label")]}
    g = group_by_check(run_release_gates(_two_parent_catalog(), None, None, today=_TODAY, alias_policy=policy))
    assert any("无法核实" in d for d in _details(g, "alias"))


def test_alias_policy_merge_into_missing_target_blocked():
    policy = {"entries": [_alias_entry("E1-1旧", "merge_into", target="E1/E1-9")]}
    report = {"open_problems": {"unregistered_alias_keys": ["E1-1旧"]}}
    g = group_by_check(run_release_gates(_two_parent_catalog(), None, report, today=_TODAY, alias_policy=policy))
    assert any("merge_into 目标「E1/E1-9」不在目录中" in d for d in _details(g, "alias"))


def test_alias_policy_bad_disposition_and_missing_owner_blocked():
    policy = {"entries": [{"alias": "x", "disposition": "whatever", "reason": "r"}]}
    g = group_by_check(run_release_gates(_two_parent_catalog(), None, None, today=_TODAY, alias_policy=policy))
    details = _details(g, "alias")
    assert any("缺 owner" in d for d in details) and any("不在" in d and "whatever" in d for d in details)


# ─── 5. ack：所指问题已不存在 = 失效条目 ─────────────────────────────────────


def _ack(kind: str, **kw) -> dict:
    return {"kind": kind, "owner": "acnr", "reason": "r", "expires_on": "2027-04-30", **kw}


def _run_ack(acks: list[dict], report: dict | None = None, cat: dict | None = None) -> dict:
    return group_by_check(run_release_gates(cat or _two_parent_catalog(), None, report, today=_TODAY,
                                            acknowledgements={"entries": acks}))


def test_ack_ccr_ids_unverifiable_without_open_problems():
    g = _run_ack([_ack("ccr_unresolved", covers={"ccr_ids": ["CCR-NOT-EXIST"]})])
    assert any("无法核实" in d for d in _details(g, "ack"))


def test_ack_ccr_id_no_longer_unresolved_is_stale():
    g = _run_ack([_ack("ccr_unresolved", covers={"ccr_ids": ["CW-1"]})],
                 report={"open_problems": {"ccr_unresolved": ["CW-2"]}})
    assert "CW-1" in _ids(g, "ack")
    assert any("已不在本批次问题清单" in d for d in _details(g, "ack"))


def test_ack_ccr_id_still_unresolved_ok():
    g = _run_ack([_ack("ccr_unresolved", covers={"ccr_ids": ["CW-1"]})],
                 report={"open_problems": {"ccr_unresolved": ["CW-1", "CW-2"]}})
    assert "ack" not in g, [str(x) for x in g.get("ack", [])]


def test_ack_alias_covered_problem_gone_is_stale():
    g = _run_ack([_ack("ccr_unresolved", covers={"aliases": ["旧冲突名"]})],
                 report={"open_problems": {"alias_conflicts": ["别的冲突名"]}})
    assert "旧冲突名" in _ids(g, "ack")


def test_ack_seed_semantic_cell_already_labeled_is_stale():
    cat = _two_parent_catalog()
    cat["cells"][0]["semantic_label"] = "期末余额"
    g = _run_ack([_ack("seed_semantic_unverified", covers={"addr_ids": ["D2/D2-1/E10"]})], cat=cat)
    assert any("已有语义名" in d for d in _details(g, "ack"))


def test_ack_seed_semantic_cell_deprecated_is_stale():
    cat = _two_parent_catalog()
    cat["cells"][0].update({"deprecated": True, "replaced_by": "D2/D2-1"})
    g = _run_ack([_ack("seed_semantic_unverified", covers={"addr_ids": ["D2/D2-1/E10"]})], cat=cat)
    assert any("已停用" in d for d in _details(g, "ack"))


def test_ack_seed_semantic_unverified_cell_ok():
    g = _run_ack([_ack("seed_semantic_unverified", covers={"addr_ids": ["D2/D2-1/E10"]})])
    assert "ack" not in g, [str(x) for x in g.get("ack", [])]


def test_ack_covered_addr_missing_is_stale():
    g = _run_ack([_ack("seed_semantic_unverified", covers={"addr_ids": ["D2/D2-1/Z99"]})])
    assert any("已不在目录" in d for d in _details(g, "ack"))


def test_ack_head_resolvable_writing_now_resolves_is_stale():
    """HEAD 时错配到 E1/E1-1 的写法，新目录里已解析到 D2/D2-1（不再错配）⇒ 豁免失效。"""
    ack = _ack("head_resolvable_errmatch", covers={"ccr_ids": ["CW-9"]}, head_resolvable_at="E1/E1-1",
               writing={"wp_code": "D2", "sheet": "明细表D2-1"})
    g = _run_ack([ack], report={"open_problems": {"ccr_unresolved": ["CW-9"]}})
    assert any("不再错配" in d for d in _details(g, "ack"))


def test_ack_head_resolvable_writing_still_unresolved_ok():
    ack = _ack("head_resolvable_errmatch", covers={"ccr_ids": ["CW-9"]}, head_resolvable_at="D2/D2-1",
               writing={"wp_code": "D2", "sheet": "D2-1 不在本册的写法"})
    g = _run_ack([ack], report={"open_problems": {"ccr_unresolved": ["CW-9"]}})
    assert "ack" not in g, [str(x) for x in g.get("ack", [])]


def test_ack_head_resolvable_without_writing_blocked():
    ack = _ack("head_resolvable_errmatch", covers={"ccr_ids": ["CW-9"]}, head_resolvable_at="D2/D2-1")
    g = _run_ack([ack], report={"open_problems": {"ccr_unresolved": ["CW-9"]}})
    assert any("缺 writing" in d for d in _details(g, "ack"))


def test_ack_unknown_kind_and_empty_covers_blocked():
    g = _run_ack([_ack("whatever")])
    details = _details(g, "ack")
    assert any("whatever" in d and "不在" in d for d in details)
    assert any("未声明覆盖对象" in d for d in details)


# ─── 6. verdict：判 deprecate 的条目在新目录里仍是有效条目 ───────────────────


def _verdicts(seg: str, aid: str, verdict: str = "deprecate", replaced_by: str | None = "D2/D2-1") -> dict:
    rec = {"addr_id": aid, "verdict": verdict}
    if replaced_by is not None:
        rec["replaced_by"] = replaced_by
    return {"sheet_verdicts": [], "cell_verdicts": [], seg: [rec]}


def test_verdict_deprecated_cell_still_valid_blocked():
    g = group_by_check(run_release_gates(_two_parent_catalog(), None, None, today=_TODAY,
                                         sheet_verdicts=_verdicts("cell_verdicts", "D2/D2-1/E10")))
    assert any("无物理来源的有效 cell" in d for d in _details(g, "verdict"))


def test_verdict_deprecated_sheet_still_valid_blocked():
    g = group_by_check(run_release_gates(_two_parent_catalog(), None, None, today=_TODAY,
                                         sheet_verdicts=_verdicts("sheet_verdicts", "E1/E1-1")))
    assert any("判定停用的 sheet 仍是有效条目" in d for d in _details(g, "verdict"))


def test_verdict_deprecated_entry_missing_blocked():
    g = group_by_check(run_release_gates(_two_parent_catalog(), None, None, today=_TODAY,
                                         sheet_verdicts=_verdicts("cell_verdicts", "D2/D2-1/Z99")))
    assert any("不在新目录" in d for d in _details(g, "verdict"))


def test_verdict_deprecated_entry_kept_as_deprecated_ok():
    cat = _two_parent_catalog()
    cat["cells"][0].update({"deprecated": True, "replaced_by": "D2/D2-1"})
    g = group_by_check(run_release_gates(cat, None, None, today=_TODAY,
                                         sheet_verdicts=_verdicts("cell_verdicts", "D2/D2-1/E10")))
    assert "verdict" not in g, [str(x) for x in g.get("verdict", [])]


def test_verdict_add_platform_sheet_not_written_blocked():
    g = group_by_check(run_release_gates(_two_parent_catalog(), None, None, today=_TODAY,
                                         sheet_verdicts=_verdicts("sheet_verdicts", "I6/I6-7", "add_platform_sheet", None)))
    assert any("判定补登的 sheet 未写入新目录" in d for d in _details(g, "verdict"))


# ─── 真实目录：现在报出已知阻断项（审计 A8：对真实数据报 0 即门禁有问题） ─────


def test_real_catalog_reports_current_blockers():
    """T07 发布前的真实目录：门禁必须报出 25 个孤儿与 formula_ref / uri 往返失败。

    往返失败集合与 T01 冻结夹具交叉核对（夹具按 HEAD 目录独立导出）：失败数 = 索引名 372 + 三名都不同 47，
    且包含夹具里 372 条平台索引名写法的全部 addr_id。T07 首个合规批次重生成目录后，本用例须改为 blocking == 0。
    """
    from app.services.acnr.catalog_integrity import content_sha256

    raw = _CATALOG_PATH.read_bytes()
    fixture = json.loads((Path(__file__).parent / "fixtures" / "platform_name_writings.json").read_text(encoding="utf-8"))
    assert content_sha256(raw) == fixture["catalog_content_sha256"], (
        "真实目录已重生成：本用例须由 T07 改为「发布门禁 blocking == 0」验收")
    data = json.loads(raw.decode("utf-8"))
    g = group_by_check(run_release_gates(data, previous=None, report=None, today=_TODAY))
    sheet_ids = {s["addr_id"] for s in data["sheets"]}
    orphans = {c["addr_id"] for c in data["cells"] if c["parent_addr_id"] not in sheet_ids}
    assert _ids(g, "orphan") == orphans and len(orphans) == fixture["breakdown"]["orphan"]
    fr_fail = {x.addr_id for x in g["roundtrip"] if x.detail.startswith("formula_ref 往返")}
    uri_fail = {x.addr_id for x in g["roundtrip"] if x.detail.startswith("uri 往返")}
    bd = fixture["breakdown"]
    assert len(fr_fail) == bd["index_name"] + bd["three_names_differ"]
    assert {w["addr_id"] for w in fixture["writings"]} <= fr_fail
    assert uri_fail == fr_fail
    assert not (fr_fail & orphans), "孤儿 cell 只由 orphan 门禁报告"
