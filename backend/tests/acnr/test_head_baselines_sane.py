"""T01：HEAD 基线夹具守卫（design §1.2 / §6.5 / R2-F2；段四审计 F4-04 返工）。

夹具按设计口径从 HEAD 导出并冻结（导出脚本 tmp_acnr_foundation/probes/fix4/export_t01_baselines.py，
导出时已断言与设计固定数逐值相等），之后不随目录变化。本守卫不再用「现行代码重算 HEAD 结果再比夹具」
（那是同义反复，T10 按设计删掉 catalog 子串启发式就会红），而是：

1. 冻结：五份夹具的 LF 内容 sha256 钉住，固定计数与设计逐值相等（372 / 26 / 2599 = 2434 + 147 + 18 /
   errmatch 14 处 7 组，成员与 R2-F2 逐条相同）。HEAD 结果（head_addr_id / head_step）是冻结数据，不重算。
2. 生产代码联动：在冻结目录 head_catalog_identity.json 上用生产代码重算**新规则**结果——
   exact_identity.sheet_of / name_owner / cell_of 与 loader load_wp_account_mapping_aliases——必须与夹具记录的
   新规则结果逐条相等。改坏 exact_identity 或 loader 会红；改 catalog._formula_ref_to_addr_id 不会红。
3. 下游可依赖：platform_name_writings 记「写法 → 期望 addr_id」，T06 用它验证生成器名称规则；
   head_resolvable 的 14 处带 head_resolvable_at，T10 发布后逐条断言仍可解析或有登记处置。
"""
from __future__ import annotations

import collections
import json
from functools import lru_cache
from pathlib import Path

import pytest

from app.services.acnr import exact_identity as ei
from app.services.acnr.catalog import CatalogIndex
from app.services.acnr.catalog_integrity import content_sha256
from app.services.acnr.loaders.from_wp_account_mapping import load_wp_account_mapping_aliases

FIX = Path(__file__).resolve().parent / "fixtures"

#: 冻结夹具的 LF 内容 sha256（重导须同时更新这里并在 tasks T01 记原因）。
_FIXTURE_SHA256 = {
    "head_catalog_identity.json": "25e090ec5fbfd79e89f687dea8ef05bf2a7fcbc48fa864f4468cc4582dd2443d",
    "platform_name_writings.json": "10e20256b3a41bf6911268b4c7899497e1a1702dcf3120e52d7563c059135fcc",
    "same_name_group_writings.json": "4724138e7f2bc9d5717c2f4532eebd5dbb1394c81ac1a99283c3583560d3a81c",
    "resolvable_writings_baseline.json": "47a0dac2dff4c7fbba992c222a95adc4bb0e401b47a4128308bd920088a95e80",
    "head_resolvable_static_writings.json": "fd19e2bcd2e358693de58d5ed36629ea4a4e0fd68003b00e0b9a011e46bcec05",
}

#: design §6.5 R2-F2：只靠子串一步命中、按编码词元规则变 not_found 的 7 组（父级, 写法）→ 处数。
_ERRMATCH_GROUPS = {
    ("D5", "D5-1"): 2,
    ("I1", "I1-1"): 2,
    ("I1", "审定表I1-1"): 4,
    ("B23", "B23-2 货币资金控制了解"): 2,
    ("I1", "摊销测算表（不含减值）I1-10（剩余年限法）"): 2,
    ("A13", "A13-3 评价识别出的错报"): 1,
    ("A13", "错报明细A13-2"): 1,
}


def _load(name: str) -> dict:
    return json.loads((FIX / name).read_bytes().decode("utf-8"))


@lru_cache(maxsize=1)
def _frozen_index() -> CatalogIndex:
    return CatalogIndex(_load("head_catalog_identity.json"))


@lru_cache(maxsize=1)
def _frozen_index_with_platform_aliases() -> CatalogIndex:
    """冻结目录 + 生产 loader 产出的平台名别名（可并入的并入，禁止别名也并入以触发第 3 步拒绝）。"""
    data = _load("head_catalog_identity.json")
    res = load_wp_account_mapping_aliases(data["sheets"])
    by_code = {s["sheet_code"]: s for s in data["sheets"]}

    def _add(code: str, name: str) -> None:
        s = by_code.get(code)
        if s is not None and name not in s.setdefault("sheet_name_aliases", []):
            s["sheet_name_aliases"].append(name)

    for code, names in res.aliases.items():
        for n in names:
            _add(code, n)
    for (_parent, name), codes in res.forbidden.items():
        for code in codes:
            _add(code, name)
    return CatalogIndex(data)


# ── 1. 冻结 ─────────────────────────────────────────────────────────────────


def test_fixtures_content_pinned():
    got = {n: content_sha256((FIX / n).read_bytes()) for n in _FIXTURE_SHA256}
    assert got == _FIXTURE_SHA256, "基线夹具被改动（T01 夹具冻结，重导须更新 _FIXTURE_SHA256 并在 tasks 记原因）"


def test_fixtures_share_one_head_snapshot():
    metas = {n: (_load(n)["head"], _load(n)["catalog_content_sha256"]) for n in _FIXTURE_SHA256}
    assert len(set(metas.values())) == 1, f"五份夹具不是同一次 HEAD 导出：{metas}"
    ident = _load("head_catalog_identity.json")
    assert len(ident["sheets"]) == 1215 and len(ident["cells"]) == 474


# ── 2. 平台索引名写法 372 ─────────────────────────────────────────────────────


def test_platform_name_writings_fixed_counts():
    fx = _load("platform_name_writings.json")
    assert fx["count"] == len(fx["writings"]) == 372
    assert fx["breakdown"] == {"roundtrip_ok": 30, "index_name": 372, "three_names_differ": 47, "orphan": 25}
    for w in fx["writings"]:
        assert w["addr_id"] == f"{w['parent']}/{w['sheet_code']}/{w['a1']}", w
        assert f"'{w['index_name']}'" in w["writing"] and w["index_name"] != w["template_name"], w
        assert w["head_addr_id"] != w["addr_id"], f"HEAD 已能往返的写法不该在清单里：{w['writing']}"


def test_platform_name_writings_roundtrip_with_loader_aliases():
    """并入生产 loader 的平台名别名后，非禁止名写法经 cell_of 回到本 cell；禁止名被第 3 步拒绝。"""
    idx = _frozen_index_with_platform_aliases()
    fail = []
    for w in _load("platform_name_writings.json")["writings"]:
        cm = ei.cell_of(w["parent"], w["index_name"], w["a1"], index=idx)
        if w["index_name_forbidden"]:
            if cm.state != "alias_forbidden":
                fail.append((w["writing"], cm.state))
        elif not (cm.ok and cm.addr_id == w["addr_id"]):
            fail.append((w["writing"], cm.state, cm.addr_id))
    assert not fail, f"平台名写法往返失败 {len(fail)} 条（前 5）：{fail[:5]}"


# ── 3. 同名组写法 26 ─────────────────────────────────────────────────────────


def test_same_name_group_fixed_counts_and_frozen_groups():
    fx = _load("same_name_group_writings.json")
    assert fx["count"] == len(fx["writings"]) == 26
    assert fx["by_source"] == {"ccr_target": 15, "preset_expr": 5, "preset_ref": 5, "prefill": 1}
    groups = collections.Counter(
        (s["parent_wp_code"], s["sheet_name"]) for s in _load("head_catalog_identity.json")["sheets"])
    same = [k for k, n in groups.items() if n > 1]
    none = [k for k in same if ei.name_owner(k[0], k[1], index=_frozen_index()) is None]
    assert (len(same), len(same) - len(none), len(none)) == (78, 70, 8)
    assert sorted(f"{p}:{n}" for p, n in none) == fx["none_groups"]


def test_same_name_group_owner_recomputed_on_frozen_catalog():
    idx = _frozen_index()
    fail = []
    for w in _load("same_name_group_writings.json")["writings"]:
        assert w["writing"].startswith("WP(") and w["source"] != "ccr_source"
        assert w["head_sheet_addr_id"] != w["name_owner_addr_id"], "HEAD 应给了借名的父级"
        owner = ei.name_owner(w["parent"], w["name"], index=idx)
        if (owner or {}).get("addr_id") != w["name_owner_addr_id"]:
            fail.append((w["writing"], (owner or {}).get("addr_id"), w["name_owner_addr_id"]))
    assert not fail, f"名称归属与冻结基线不符：{fail[:5]}"


# ── 4. 可解析写法基线 2599 ───────────────────────────────────────────────────


def test_resolvable_baseline_fixed_counts():
    fx = _load("resolvable_writings_baseline.json")
    assert fx["count"] == len(fx["writings"]) == 2599
    assert (fx["unchanged"], fx["reclassified"], fx["ambiguous"]) == (2434, 147, 18)
    kinds = collections.Counter(w["kind"] for w in fx["writings"])
    assert kinds == {"sheet_code": 1215, "sheet_name": 1215, "alias": 169}
    for w in fx["writings"]:
        expect = "ambiguous" if w["new_state"] == "ambiguous" else (
            "unchanged" if w["new_state"] == "ok" and w["new_addr_id"] == w["head_addr_id"] else "reclassified")
        assert w["verdict"] == expect, w


def test_resolvable_new_rule_recomputed_on_frozen_catalog():
    idx = _frozen_index()
    drift = []
    for w in _load("resolvable_writings_baseline.json")["writings"]:
        sm = ei.sheet_of(w["parent"], w["writing"], index=idx)
        got = (sm.state, (sm.entry or {}).get("addr_id") if sm.ok else None)
        if got != (w["new_state"], w["new_addr_id"]):
            drift.append((w["parent"], w["writing"], got, (w["new_state"], w["new_addr_id"])))
    assert not drift, f"exact_identity 在冻结目录上的结果与基线不符 {len(drift)} 条（前 5）：{drift[:5]}"


# ── 5. HEAD 可解析集与 errmatch 14 处 / 7 组 ─────────────────────────────────


def test_head_resolvable_errmatch_is_design_fourteen():
    fx = _load("head_resolvable_static_writings.json")
    assert fx["count"] == len(fx["static_writings"]) == 1193
    assert fx["by_source"] == {"ccr_target": 288, "ccr_source": 425, "preset_expr": 41, "preset_ref": 40,
                               "prefill": 399}
    em = [w for w in fx["static_writings"] if "head_resolvable_at" in w]
    assert fx["errmatch_count"] == len(em) == 14
    got = collections.Counter((w["args"][0], w["args"][1]) for w in em)
    assert dict(got) == _ERRMATCH_GROUPS
    assert collections.Counter(w["source"].split("_")[0] for w in em) == {"ccr": 10, "preset": 4}
    for w in em:
        assert w["head_step"] == "substring" and w["new_state"] == "not_found", w
        assert w["head_resolvable_at"] == w["head_addr_id"] and w["head_sheet_addr_id"], w
    others = [w for w in fx["static_writings"] if "head_resolvable_at" not in w
              and w.get("head_step") == "substring" and w.get("new_state") == "not_found"]
    assert not others, f"有子串独命中且变 not_found 却未登记 head_resolvable_at：{others[:3]}"


def test_head_resolvable_new_rule_recomputed_on_frozen_catalog():
    idx = _frozen_index()
    drift = []
    fx = _load("head_resolvable_static_writings.json")
    for w in fx["static_writings"] + fx["pg_writings"]:
        if len(w["args"]) < 2:
            continue
        sm = ei.sheet_of(w["args"][0], w["args"][1], index=idx)
        got = (sm.state, (sm.entry or {}).get("addr_id") if sm.ok else None)
        if got != (w["new_state"], w["new_sheet_addr_id"]):
            drift.append((w["writing"], got, (w["new_state"], w["new_sheet_addr_id"])))
    assert not drift, f"exact_identity 在冻结目录上的结果与基线不符 {len(drift)} 条（前 5）：{drift[:5]}"


def test_head_resolvable_pg_writings():
    fx = _load("head_resolvable_static_writings.json")
    assert fx["pg_columns_scanned"] >= 1
    assert fx["pg_rows_with_wp"] == {"wp_formula.expression": 18}
    assert fx["pg_count"] == len(fx["pg_writings"]) == 18
    assert sum(1 for w in fx["pg_writings"] if len(w["args"]) == 3) == 0
    assert not [w for w in fx["pg_writings"] if "head_resolvable_at" in w]


@pytest.mark.parametrize("name", sorted(_FIXTURE_SHA256))
def test_fixture_is_valid_json_object(name):
    assert isinstance(_load(name), dict)
