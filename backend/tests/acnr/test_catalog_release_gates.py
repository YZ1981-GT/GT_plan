"""T07 发布门禁 run_release_gates 单元测试（design §5.2 / §5.6）。

用合成目录逐个门禁做正反两例（干净目录无违规 + 注入缺陷后该门禁红），
并验证真实目录能被门禁模块加载（结构可用）。不写任何仓库产物。

说明：真实目录「blocking == 0」属 T07 生成器重写 + 迁回 57 张补丁之后的
验收口径（当前目录未重生成、仍含 25 个未停用孤儿 cell、缺 alias_policy /
acknowledgements），本轮不做、不假装做；此处只验证门禁模块本身对合成目录
的判定正确。
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
                "cell_address": "E10",
            },
            {
                "addr_id": "D2/D2-2/F20",
                "parent_addr_id": "D2/D2-2",
                "domain": "wp",
                "formula_ref": "WP('D2','D2-2','F20')",
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


def test_real_catalog_loads_in_gate_module():
    data = json.loads(_CATALOG_PATH.read_text(encoding="utf-8"))
    # 门禁对真实目录能跑完不抛（往返构造真实 CatalogIndex）
    v = run_release_gates(data, previous=None, report=None, today=_TODAY)
    # 当前真实目录未经 T07 重生成，允许有违规；仅断言跑通且返回的是违规列表
    assert isinstance(v, list)
    assert all(isinstance(x, GateViolation) for x in v)
