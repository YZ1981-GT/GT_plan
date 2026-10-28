"""V2 依赖图规范化与 stale 身份内核（acnr-foundation-defect-closure T21，需求 9.1~9.3，design §10.2 / §10.4）。

全部读真实数据文件与真实目录，不 mock exact_identity：
- ``canonical_node`` 各分类的结果 addr_id 与 unresolved_reason 恰有其一，原因是中文；
- V2 四个读端点（/resolve、/anchors、/stale-impact、/dependencies）经 TestClient 返回的每个节点与边端点都恰有其一，
  非空 addr_id 经 ``full_resolve`` 回到同一物理格；/resolve 的包含匹配只作候选；
- stale 写路径：碰撞组样本起点只含该格自身；无法确定身份（只能包含匹配）的输入不写库并返回原因；
  ``editor_save_inputs.json`` 夹具里旧逻辑正确命中的起点，新规则都命中。
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.deps import get_current_user
from app.routers import address_registry_v2 as v2
from app.services.acnr import v2_canonical
from app.services.acnr.catalog import get_catalog
from app.services.acnr.reasons import NODE_UNRESOLVED_REASONS
from app.services.acnr.resolver import full_resolve
from app.services.stale_propagation_engine import StalePropagationEngine

_FIX = Path(__file__).resolve().parent / "fixtures" / "editor_save_inputs.json"
_DATA = Path(__file__).resolve().parents[2] / "data"
G12_OWN = "WP:G12:净敞口套期收益审计程序表G12A-修订前:B5"   # G12 本身的表名（旧正则猜成 G12A）
G12A = "WP:G12:净敞口套期收益审计程序表G12A:B5"


def _has_chinese(text: str) -> bool:
    return any("\u4e00" <= ch <= "\u9fff" for ch in text or "")


def _exactly_one(fields: dict) -> bool:
    return (fields.get("addr_id") is None) != (fields.get("unresolved_reason") is None)


# ─── canonical_node 分类 ──────────────────────────────────────────────────────


def _registered_cell():
    cat = get_catalog()
    for c in cat.cells_by_addr_id.values():
        sheet = cat.sheets_by_addr_id.get(c.get("parent_addr_id"))
        if not c.get("deprecated") and sheet and not sheet.get("deprecated"):
            from app.services.acnr import exact_identity
            sm = exact_identity.sheet_of(sheet["parent_wp_code"], sheet["sheet_name"], index=cat)
            if sm.ok and sm.entry["addr_id"] == sheet["addr_id"]:
                return sheet, c
    raise AssertionError("目录里没有可用的登记 cell")


def test_canonical_node_classes_have_exactly_one_and_chinese_reason():
    sheet, cell = _registered_cell()
    cases = {
        "registered": (sheet["parent_wp_code"], sheet["sheet_name"], cell["cell_address"]),
        "cell_not_in_catalog": (sheet["parent_wp_code"], sheet["sheet_name"], "ZZZ9999"),
        "label_not_a1": (sheet["parent_wp_code"], sheet["sheet_name"], "审定数"),
        "ambiguous_sheet_name": ("F2", "底稿目录", "A1"),
        "alias_forbidden": ("D5", "底稿目录", "A1"),
        "sheet_not_in_catalog": ("D2", "并不存在的表", "A1"),
        "wp_not_in_catalog": ("不存在的底稿ZZ", "某表", "A1"),
        "not_wellformed": ("D2", "", "A1"),
    }
    for expect, args in cases.items():
        node = v2_canonical.canonical_node(*args)
        assert _exactly_one(node.response_fields()), (expect, node)
        if expect == "registered":
            assert node.addr_id == cell["addr_id"] and node.identity_key == cell["addr_id"]
            continue
        assert node.unresolved_code == expect, (expect, node)
        assert _has_chinese(node.unresolved_reason), node
    assert v2_canonical.canonical_node(*cases["cell_not_in_catalog"]).identity_key == f"{sheet['addr_id']}/ZZZ9999"
    assert v2_canonical.canonical_node(*cases["label_not_a1"]).identity_key == f"{sheet['addr_id']}#审定数"
    custom = v2_canonical.canonical_uri("WP:K0::total")
    assert custom.unresolved_code == "not_wellformed" and custom.identity_key == "custom:K0:total"


def test_every_graph_wp_key_classified_with_reason():
    """真实统一依赖图的全部 WP 键：恰有其一，原因码都在中文原因表里。"""
    graph = json.loads((_DATA / "unified_dependency_graph.json").read_bytes())
    keys = {k for e in graph["edges"] for k in (e.get("source"), e.get("target")) if k and k.startswith("WP:")}
    assert len(keys) > 40000  # 防空转（现算 47073）
    cat = get_catalog()
    codes = set()
    for key in keys:
        node = v2_canonical.canonical_uri(key, index=cat)
        assert _exactly_one(node.response_fields()), key
        if node.unresolved_code:
            codes.add(node.unresolved_code)
    assert codes <= set(NODE_UNRESOLVED_REASONS) and all(_has_chinese(NODE_UNRESOLVED_REASONS[c]) for c in codes)


# ─── V2 四个读端点 ────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def client():
    app = FastAPI()
    app.include_router(v2.router)
    app.dependency_overrides[get_current_user] = lambda: object()
    return TestClient(app)


def _nodes(payload, out):
    """收集响应里带四个规范字段的 dict。"""
    if isinstance(payload, dict):
        if all(k in payload for k in v2_canonical.RESPONSE_FIELDS):
            out.append(payload)
        for value in payload.values():
            _nodes(value, out)
    elif isinstance(payload, list):
        for value in payload:
            _nodes(value, out)
    return out


def _check_nodes(nodes):
    assert nodes, "响应里没有带规范字段的节点"
    addr_ids = set()
    for node in nodes:
        assert _exactly_one(node), node
        if node["addr_id"]:
            addr_ids.add(node["addr_id"])
        else:
            assert _has_chinese(node["unresolved_reason"]), node
    results = asyncio.run(_resolve_all(sorted(addr_ids)))
    bad = [(a, r.found, r.addr_id) for a, r in zip(sorted(addr_ids), results)
           if not (r.found and r.addr_id == a and r.entry_type == "cell")]
    assert not bad, bad


async def _resolve_all(addr_ids):
    return [await full_resolve(addr_id=a) for a in addr_ids]


def test_anchors_nodes(client):
    body = client.get("/api/address-registry/v2/anchors", params={"wp_code": "D2"}).json()
    assert body["total"] > 0
    nodes = _nodes(body, [])
    assert len(nodes) == body["total"]
    _check_nodes(nodes)


def test_endpoint_addr_ids_round_trip_non_vacuous(client):
    """经端点返回的非空 addr_id 回到同一物理格（M6：anchors 与 dependencies 现算各有登记 cell，防空转）。"""
    anchors = _nodes(client.get("/api/address-registry/v2/anchors", params={"wp_code": "M6"}).json(), [])
    deps = _nodes(client.get("/api/address-registry/v2/dependencies", params={"wp_code": "M6"}).json(), [])
    assert any(n["addr_id"] for n in anchors) and any(n["addr_id"] for n in deps)
    _check_nodes(anchors + deps)


def test_stale_impact_and_dependencies_nodes(client):
    body = client.get("/api/address-registry/v2/stale-impact",
                      params={"wp_code": "H1", "sheet": "折旧分配分析表H1-13"}).json()
    assert body["total_affected"] > 0 and _exactly_one(body["source"])
    _check_nodes(_nodes(body, []))
    deps = client.get("/api/address-registry/v2/dependencies", params={"wp_code": "H1"}).json()
    for item in deps["downstream"] + deps["upstream"]:
        assert _exactly_one(item["source"]) and _exactly_one(item["target"]), item
    for item in deps["formula_dependencies"]:
        assert _exactly_one(item["source_identity"]) and _exactly_one(item["target_identity"]), item
    assert deps["downstream"] and deps["formula_dependencies"]
    _check_nodes(_nodes(deps, []))


def test_registered_cell_addr_id_round_trips():
    """非空 addr_id 经 full_resolve 回到同一物理格（登记 cell，经 canonical_node 得到）。"""
    sheet, cell = _registered_cell()
    node = v2_canonical.canonical_node(sheet["parent_wp_code"], sheet["sheet_name"], cell["cell_address"])
    _check_nodes([node.response_fields()])


def _contains_only_case():
    l2 = json.loads((_DATA / "address_registry_l2_semantic.json").read_bytes())
    resolved = json.loads((_DATA / "address_registry_resolved_refs.json").read_bytes())["resolved"]
    for wp, files in l2.items():
        descs = {r["source"].get("description_cell") for r in resolved if r["source"].get("wp_code") == wp}
        anchors_all = {a for sheets in files.values() for sd in sheets.values() for a in sd.get("anchors", {})}
        for sheets in files.values():
            for sn, sd in sheets.items():
                for anc in sd.get("anchors", {}):
                    probe = anc[:-1]
                    if len(probe) >= 3 and probe not in anchors_all and probe not in descs:
                        return wp, sn, anc, probe
    raise AssertionError("找不到只能包含匹配的样本")


def test_resolve_contains_is_candidate_not_matched(client):
    wp, sn, anc, probe = _contains_only_case()
    exact = client.get("/api/address-registry/v2/resolve",
                       params={"wp_code": wp, "sheet": sn, "cell_desc": anc}).json()
    assert exact["matched"] is True and exact["match_kind"] == "exact" and "candidate" not in exact
    assert _exactly_one(exact)
    loose = client.get("/api/address-registry/v2/resolve",
                       params={"wp_code": wp, "sheet": sn, "cell_desc": probe}).json()
    assert loose["matched"] is False and loose["candidate"] is True and loose["match_kind"] == "contains", loose
    assert _exactly_one(loose)
    _check_nodes([exact, loose])


# ─── stale 写路径 ─────────────────────────────────────────────────────────────


def _engine(graph: dict[str, list[str]] | None = None) -> StalePropagationEngine:
    eng = StalePropagationEngine()
    if graph is not None:
        eng._graph = graph
        eng._identity_version = None
    eng._mark_stale_by_uri = AsyncMock(return_value={})
    eng._notify_frontend = AsyncMock()
    eng._write_audit_log = AsyncMock()
    return eng


def test_collision_sample_starts_only_from_itself():
    """旧正则把两张表都猜成 G12A（G12/G12A/B5），新规则按 exact_identity 分开。"""
    eng = _engine({G12_OWN: ["NOTE:own"], G12A: ["NOTE:other"]})
    keys, unresolved = eng._start_keys(G12_OWN)
    assert unresolved is None and keys == [G12_OWN]
    result = asyncio.run(eng.on_change(G12_OWN, "00000000-0000-0000-0000-000000000001", 2025))
    assert result["affected"] == ["NOTE:own"]
    eng._mark_stale_by_uri.assert_awaited_once()
    assert eng._mark_stale_by_uri.await_args.args[0] == ["NOTE:own"]


def test_real_collision_groups_start_only_from_same_sheet():
    """真实依赖图：旧正则把显示名里的编码抠出来后撞到同一 addr_id 的图键组（碰撞组），每个成员作输入时，
    起点只含它自己和同一张表、同一末段的其他写法；表身份算不出的成员没有起点。期望身份直接按
    exact_identity.sheet_of 算（不经 v2_canonical），与被测实现独立。"""
    import re
    from collections import defaultdict

    from app.services.acnr import exact_identity

    old_code = re.compile(r"([A-Z]\d+(?:-\d+)?[A-Z]?)")
    cat = get_catalog()
    eng = _engine()
    groups: dict[tuple, set] = defaultdict(set)
    for key in eng._graph:
        parts = key.split(":", 3)
        if key.startswith("WP:") and len(parts) == 4 and all(parts[1:]):
            m = old_code.search(parts[2])
            groups[(parts[1], m.group(1) if m else parts[2], parts[3])].add(key)
    collisions = [sorted(ks) for ks in groups.values() if len(ks) > 1]
    assert len(collisions) > 100  # 防空转（现算 125 组 266 个图键）
    problems, identified = [], 0
    for members in collisions:
        for key in members:
            _, wp, sheet, last = key.split(":", 3)
            sm = exact_identity.sheet_of(wp, sheet, index=cat)
            keys, _ = eng._start_keys(key)
            if not sm.ok:
                if keys:
                    problems.append(("身份算不出却有起点", key, keys))
                continue
            identified += 1
            if key not in keys:
                problems.append(("起点不含自身", key, keys))
            for start in keys:
                _, w2, s2, l2 = start.split(":", 3)
                other = exact_identity.sheet_of(w2, s2, index=cat)
                if not (other.ok and other.entry["addr_id"] == sm.entry["addr_id"] and l2 == last):
                    problems.append(("起点不是同一张表同一末段", key, start))
    assert identified > 100 and not problems, problems[:10]


def test_multi_writing_same_identity_merged():
    """同一张表的别名写法（I1 目录名「审定表I1」与别名「审定表I1-1」）并入同一起点。"""
    eng = _engine({"WP:I1:审定表I1-1:审定数": ["NOTE:i1"]})
    keys, unresolved = eng._start_keys("WP:I1:审定表I1:审定数")
    assert unresolved is None and keys == ["WP:I1:审定表I1-1:审定数"]


def test_contains_only_input_not_written_and_returns_reason():
    """表名只是真实表名的一部分（只能包含匹配）：不写库、不推送、返回中文原因。"""
    eng = _engine({G12_OWN: ["NOTE:own"]})
    uri = "WP:G12:净敞口套期收益审计程序表G12A-修订:B5"
    result = asyncio.run(eng.on_change(uri, "00000000-0000-0000-0000-000000000001", 2025))
    assert result["affected"] == [] and result["unresolved_code"] == "sheet_not_in_catalog"
    assert _has_chinese(result["unresolved_reason"])
    assert eng._mark_stale_by_uri.await_count == 0 and eng._notify_frontend.await_count == 0
    preview = eng.preview_impact(uri)
    assert preview["affected"] == [] and preview["unresolved_code"] == "sheet_not_in_catalog"


def test_identity_known_but_not_in_graph_is_empty_not_error():
    eng = _engine({G12A: ["NOTE:other"]})
    result = asyncio.run(eng.on_change(G12_OWN, "00000000-0000-0000-0000-000000000001", 2025))
    assert result == {"affected": [], "total": 0, "degraded": False}
    assert eng._mark_stale_by_uri.await_count == 0


def test_editor_save_inputs_new_rule_covers_old_correct_hits():
    data = json.loads(_FIX.read_bytes())
    rows = data["inputs"]
    assert len(rows) > 1000  # 防空转（现算 2098）
    eng = _engine()
    lost, drift = [], []
    old_hits: dict[str, int] = {}
    new_hits: dict[str, int] = {}
    for row in rows:
        keys, unresolved = eng._start_keys(row["input"])
        code = unresolved.unresolved_code if unresolved else None
        if sorted(keys) != row["new_start_keys"] or code != row["unresolved_code"]:
            drift.append((row["input"], sorted(keys), code))
        if row["old_correct_start"]:
            old_hits[row["group"]] = old_hits.get(row["group"], 0) + 1
            if row["old_correct_start"] not in keys:
                lost.append(row["input"])
        if keys:
            new_hits[row["group"]] = new_hits.get(row["group"], 0) + 1
    assert not lost, f"旧逻辑正确命中、新规则丢失起点：{lost[:10]}"
    assert not drift, f"与夹具不一致（目录或图变了须重生成夹具）：{drift[:10]}"
    assert old_hits and all(new_hits.get(g, 0) >= n for g, n in old_hits.items()), (old_hits, new_hits)


def test_editor_save_fixture_reproducible_by_generator():
    """夹具（含冻结的旧逻辑判定）可由仓库内生成器逐值复现：``gen_editor_save_inputs.py --check``。"""
    from scripts.acnr.gen_editor_save_inputs import build_payload

    assert build_payload() == json.loads(_FIX.read_bytes())


def test_edges_injected_after_index_built_still_start():
    """启动后注入的注册表边（``WP:{码}::data``）在身份索引建好之后加入，仍能作为起点（图键数变化即重建）。
    第二段用别名写法注入：输入与图键字面不同、只能经重建后的身份索引命中（不重建则起点为空）。"""
    eng = _engine({G12_OWN: ["NOTE:own"]})
    assert eng._start_keys(G12_OWN)[0] == [G12_OWN]
    eng._graph.setdefault("WP:A1::data", []).append("WP:A2::data")
    assert eng._start_keys("WP:A1::data") == (["WP:A1::data"], None)
    eng._graph.setdefault("WP:I1:审定表I1-1:审定数", []).append("NOTE:i1")
    assert eng._start_keys("WP:I1:审定表I1:审定数") == (["WP:I1:审定表I1-1:审定数"], None)


def test_non_wp_input_is_literal_without_loading_catalog(monkeypatch):
    """TB: / REPORT: 等非 WP 域按字面查图，不依赖目录（目录不可用时这类传播不受影响）。"""
    import app.services.acnr.catalog as catalog_mod

    def _boom(*_a, **_k):
        raise RuntimeError("目录不可用")

    monkeypatch.setattr(catalog_mod, "get_catalog", _boom)
    eng = _engine({"TB:1001::期末余额": ["WP:E1:审定表E1-1:审定数"]})
    assert eng._start_keys("TB:1001::期末余额") == (["TB:1001::期末余额"], None)
    assert eng._start_keys("TB:9999::期末余额") == ([], None)


def test_write_path_does_not_use_regex_normalizer():
    """AST：stale 引擎不导入 linkage_graph_builder、不调用 _normalize_wp_uri_to_addr_id；写入口 on_change /
    preview_impact 都经 _start_keys，_start_keys 经 _identity_of；v2_canonical 只依赖本包身份模块。"""
    import ast

    app_dir = Path(__file__).resolve().parents[2] / "app"
    stale = ast.parse((app_dir / "services" / "stale_propagation_engine.py").read_text(encoding="utf-8"))
    canon = ast.parse((app_dir / "services" / "acnr" / "v2_canonical.py").read_text(encoding="utf-8"))

    def _mods(tree):
        return {(n.module or "") + ":" + a.name for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)
                for a in n.names} | {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}

    def _calls(tree, fn=None):
        roots = [tree] if fn is None else [n for n in ast.walk(tree)
                                           if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == fn]
        assert roots, fn
        return {(c.func.id if isinstance(c.func, ast.Name) else getattr(c.func, "attr", ""))
                for r in roots for c in ast.walk(r) if isinstance(c, ast.Call)}

    assert not any("linkage_graph_builder" in m for m in _mods(stale))
    assert "_normalize_wp_uri_to_addr_id" not in _calls(stale)
    assert "_start_keys" in _calls(stale, "on_change") and "_start_keys" in _calls(stale, "preview_impact")
    assert "_identity_of" in _calls(stale, "_start_keys")
    assert {m.split(":")[0] for m in _mods(canon)} <= {"__future__", "re", "dataclasses", "typing", "", "catalog",
                                                       "catalog_contract"}, _mods(canon)
    assert {"sheet_of", "cell_of"} <= _calls(canon, "canonical_node")
