"""目录报告四组分组、别名逐条处置与豁免清单（acnr-foundation-defect-closure T09，design §7 / 需求 6）。

真实产物：四组 count == len(items)、blocking 0；open_problems 的 28 个未登记键与 4 条冲突逐条有处置，分类与
design §7.3 一致（1 + 12 + 10 + 2 + 2 + 1）；问题清单与生成器现算相等（不是抄来的常量）。
门禁：在真实目录 + 真实输入上逐类改坏（豁免到期、所指问题消失、删禁止别名、非地址标签改成真实编码、删一条处置、
豁免漏一格），发布门禁都必须红并点名。
"""
from __future__ import annotations

import copy
import json
import sys
from datetime import date
from pathlib import Path

import pytest

from app.services.acnr.catalog_release import group_by_check, run_release_gates
from app.services.acnr.catalog_report_buckets import BUCKETS, bucket_problems

_ACNR = Path(__file__).resolve().parents[2] / "data" / "acnr"
_TODAY = date(2026, 10, 27)


def _load(rel: str):
    return json.loads((_ACNR / rel).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def real():
    return {"catalog": _load("global_catalog.json"), "report": _load("catalog_report.json"),
            "alias_policy": _load("sources/alias_policy.json"), "acks": _load("sources/acknowledgements.json")}


def _gates(real, *, report=None, alias_policy=None, acks=None, catalog=None, today=_TODAY):
    return group_by_check(run_release_gates(
        catalog or real["catalog"], None, report or real["report"], today=today,
        alias_policy=alias_policy if alias_policy is not None else real["alias_policy"],
        acknowledgements=acks if acks is not None else real["acks"]))


def _details(g, check):
    return [v.detail for v in g.get(check, [])]


# ─── 真实产物 ────────────────────────────────────────────────────────────────


def test_real_report_four_buckets_and_blocking_zero(real):
    r = real["report"]
    assert bucket_problems(r) == []
    assert r["blocking"] == {"count": 0, "items": []}
    assert set(r["summary"]) == {"total_sheets", "total_cells", *BUCKETS}
    assert r["summary"]["total_sheets"] == len(real["catalog"]["sheets"])


def test_real_buckets_reflect_catalog_and_inputs(real):
    r, cat = real["report"], real["catalog"]
    deprecated = {e["addr_id"] for seg in ("sheets", "cells") for e in cat[seg] if e.get("deprecated")}
    assert {i["addr_id"] for i in r["deprecated"]["items"]} == deprecated
    forbidden = {(p, a) for p, by in cat["alias_policy"]["forbidden"].items() for a in by}
    assert {(i["parent_wp_code"], i["alias"]) for i in r["info"]["items"] if i["kind"] == "forbidden_alias"} == forbidden
    assert [i["id"] for i in r["acknowledged"]["items"]] == [e["id"] for e in real["acks"]["entries"]]


def test_open_problems_equal_generator_recompute(real):
    """问题清单是生成器现算结果：标签源未登记键与冲突逐条相等（改标签源不重新发布即不等）。"""
    sys.path.insert(0, str(_ACNR.parents[1] / "scripts" / "acnr"))
    from generate_catalog import generate_catalog

    _cat, base, _b = generate_catalog(offline=True, registry_version=real["catalog"]["registry_version"])
    op = real["report"]["open_problems"]
    assert op["unregistered_alias_keys"] == sorted({u["sheet_code"] for u in base["unregistered_aliases"]})
    assert op["alias_conflict_members"] == {c["alias"]: sorted(c["sheet_codes"]) for c in base["alias_conflicts"]}
    assert len(op["unregistered_alias_keys"]) == 28 and len(op["alias_conflicts"]) == 4


def test_every_key_and_conflict_disposed_per_design(real):
    op, entries = real["report"]["open_problems"], real["alias_policy"]["entries"]
    by_alias = {e["alias"]: e for e in entries}
    codes = {s["sheet_code"] for s in real["catalog"]["sheets"]}
    disp = {k: by_alias[k]["disposition"] for k in op["unregistered_alias_keys"]}
    assert sorted(disp.values()).count("merge_into") == 1 and by_alias["D5-1"]["target"] == "D5/D5"
    nal = [k for k, d in disp.items() if d == "non_address_label"]
    assert (sum(k.endswith("-目录") for k in nal), sum(k.endswith(("附注上市", "附注国企")) for k in nal)) == (12, 10)
    assert {"D4-31T", "D4-访谈模板", "D4A", "D4-22A", "参考中证协"} <= set(nal) and len(nal) == 27
    for alias, members in op["alias_conflict_members"].items():
        in_cat = [m for m in members if m in codes]
        if in_cat:
            assert by_alias[alias]["disposition"] == "forbidden" and sorted(by_alias[alias]["sheet_codes"]) == sorted(in_cat)
        assert all(m in codes or m in disp for m in members)
    assert len(by_alias["底稿目录"]["sheet_codes"]) == 11
    d5 = next(s for s in real["catalog"]["sheets"] if s["addr_id"] == "D5/D5")
    assert "应收款项融资审定表D5-1" in d5["sheet_name_aliases"]
    assert {p for p, by in real["catalog"]["alias_policy"]["forbidden"].items() if "底稿目录" in by} == {
        s["parent_wp_code"] for s in real["catalog"]["sheets"] if s["sheet_code"] in by_alias["底稿目录"]["sheet_codes"]}


def test_real_inputs_pass_alias_and_ack_gates(real):
    g = _gates(real)
    assert "alias" not in g and "ack" not in g, {k: [str(v) for v in vs] for k, vs in g.items()}


# ─── 门禁变异（真实目录 + 真实输入，逐类改坏） ─────────────────────────────────


def test_ack_expired_blocked(real):
    acks = copy.deepcopy(real["acks"])
    acks["entries"][0]["expires_on"] = "2026-10-26"
    assert any("已于 2026-10-26 过期" in d for d in _details(_gates(real, acks=acks), "ack"))


def test_ack_covered_cell_gone_blocked(real):
    cat = copy.deepcopy(real["catalog"])
    aid = real["acks"]["entries"][0]["covers"]["addr_ids"][0]
    next(c for c in cat["cells"] if c["addr_id"] == aid)["semantic_label"] = "已核对的语义"
    assert any("已有语义名" in d for d in _details(_gates(real, catalog=cat), "ack"))


def test_semantic_cell_not_acknowledged_blocked(real):
    acks = copy.deepcopy(real["acks"])
    dropped = acks["entries"][0]["covers"]["addr_ids"].pop()
    g = _gates(real, acks=acks)
    assert dropped in {v.addr_id for v in g.get("ack", [])} and any("未登记 seed_semantic_unverified" in d for d in _details(g, "ack"))


def test_label_source_key_gone_makes_disposition_stale(real):
    report = copy.deepcopy(real["report"])
    report["open_problems"]["unregistered_alias_keys"].remove("D4-31T")
    assert any("non_address_label「D4-31T」已不是本批次的未登记别名键" in d for d in _details(_gates(real, report=report), "alias"))


def test_forbidden_conflict_disposition_removed_blocked(real):
    policy = copy.deepcopy(real["alias_policy"])
    policy["entries"] = [e for e in policy["entries"] if e["alias"] != "底稿目录"]
    assert any("别名冲突「底稿目录」在目录 sheet「D5」上未处置" in d for d in _details(_gates(real, alias_policy=policy), "alias"))


def test_non_address_label_key_is_real_sheet_code_blocked(real):
    policy = copy.deepcopy(real["alias_policy"])
    next(e for e in policy["entries"] if e["alias"] == "参考中证协")["alias"] = "D5"
    details = _details(_gates(real, alias_policy=policy), "alias")
    assert any("non_address_label「D5」已是目录 sheet_code" in d for d in details)
    assert any("未登记别名键「参考中证协」未处置" in d for d in details)


def test_conflict_disposition_without_conflict_is_stale(real):
    report = copy.deepcopy(real["report"])
    report["open_problems"]["alias_conflicts"].remove("底稿目录")
    assert any("forbidden「底稿目录」所指别名冲突已不存在" in d for d in _details(_gates(real, report=report), "alias"))


def test_missing_conflict_members_unverifiable(real):
    report = copy.deepcopy(real["report"])
    del report["open_problems"]["alias_conflict_members"]
    assert any("alias_conflict_members" in d for d in _details(_gates(real, report=report), "alias"))
