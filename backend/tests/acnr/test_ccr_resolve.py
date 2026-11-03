"""CCR 源身份检查与豁免、V2 双读对账产物（acnr-foundation-defect-closure T22，需求 9.4~9.5，design §10.2~§10.3）。

真实数据：目录、`cross_wp_references.json`、豁免清单、模板册都读仓库里的真实文件，不 mock。
- 检查器只经 `ccr_sources`（委托 exact_identity）判身份，无私有匹配；只依赖标准库（`python -S` 子进程能跑）。
- 不可解析源 == 豁免清单 ccr_unresolved == 生成器报告 open_problems.ccr_unresolved；逐条豁免的证据由模板册现算。
- 相对基线 b5fc200e0 的 source_sheet 改写都须两项证据。
- 停用条目引用计入 deprecated 组（RV7-03 变异：D4 子表与 G14-2 标停用）。
- 对账产物 `--check` 一致、每类有中文原因、计数自洽。
"""
from __future__ import annotations

import ast
import copy
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from app.services.acnr import exact_identity
from app.services.acnr.catalog import CatalogIndex

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _ccr_evidence as ev  # noqa: E402

_BACKEND = Path(__file__).resolve().parents[2]
_REPO = _BACKEND.parent
_DATA = _BACKEND / "data"
_ACNR = _DATA / "acnr"
_CHECKER = _BACKEND / "scripts" / "acnr" / "check_ccr_resolve.py"
_RECONCILE = _BACKEND / "scripts" / "acnr" / "reconcile_v2_canonical.py"
_CCR_SOURCES = _BACKEND / "app" / "services" / "acnr" / "ccr_sources.py"
_HEAD_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "ccr_sources_head.json"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _json(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def chk():
    return _load_module("t22_check_ccr_resolve", _CHECKER)


@pytest.fixture(scope="module")
def real():
    return {"catalog": _json(_ACNR / "global_catalog.json"), "ccr": _json(_DATA / "cross_wp_references.json"),
            "acks": _json(_ACNR / "sources" / "acknowledgements.json"), "report": _json(_ACNR / "catalog_report.json")}


@pytest.fixture(scope="module")
def result(chk, real):
    return chk.run(real["catalog"], real["ccr"], real["acks"])


def _run(args: list[str]) -> subprocess.CompletedProcess:
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    return subprocess.run([sys.executable, *args], cwd=_REPO, capture_output=True, encoding="utf-8",
                          errors="replace", env=env, stdin=subprocess.DEVNULL, timeout=300)


def _ccr_acks(acks: dict) -> list[dict]:
    return [e for e in acks["entries"] if e.get("kind") == "ccr_unresolved"]


# ─── 检查器委托 exact_identity、只依赖标准库 ──────────────────────────────────────────


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:
                base = "app.services.acnr" + (f".{base}" if base else "")
            out |= {f"{base}.{a.name}" if node.level and not node.module else base for a in node.names}
    return out


def test_checker_has_no_private_matching_and_uses_ccr_sources():
    tree = ast.parse(_CHECKER.read_text(encoding="utf-8"))
    defs = {n.name for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
    assert not defs & {"_find_sheet", "OfflineCatalog", "_resolve_3arg", "_resolve_2arg"}, defs
    called = {n.func.attr for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
              and isinstance(n.func.value, ast.Name) and n.func.value.id == "ccr_sources"}
    assert {"source_end", "target_ends", "is_deprecated"} <= called
    src = ast.parse(_CCR_SOURCES.read_text(encoding="utf-8"))
    via = {n.func.attr for n in ast.walk(src) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
           and isinstance(n.func.value, ast.Name) and n.func.value.id == "exact_identity"}
    assert {"sheet_of", "cell_of"} <= via


def test_ccr_sources_imports_only_stdlib_and_package():
    allowed_pkg = {"app.services.acnr.exact_identity", "app.services.acnr.catalog_contract", "app.services.acnr.catalog"}
    for mod in _imports(_CCR_SOURCES):
        top = mod.split(".")[0]
        assert mod in allowed_pkg or top in sys.stdlib_module_names, mod


@pytest.mark.parametrize("script,args", [(_CHECKER, ["--blocking"]), (_RECONCILE, ["--check"])])
def test_scripts_run_without_site_packages(script, args):
    """CI 作业不装依赖：`python -S`（不加载 site-packages）能跑通并退出 0。"""
    proc = _run(["-S", str(script), *args])
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "OK" in proc.stdout


# ─── 不可解析源、豁免清单与生成器报告三处一致 ─────────────────────────────────────────


def test_blocking_green_and_counts_recomputed(real, result):
    index = CatalogIndex(real["catalog"])
    direct = sorted(r["ref_id"] for r in real["ccr"]["references"]
                    if not exact_identity.sheet_of(r.get("source_wp") or "", r.get("source_sheet") or "", index=index).ok)
    assert sorted(u["ref_id"] for u in result["unresolved"]) == direct
    assert result["total"] == len(real["ccr"]["references"]) == 425
    assert result["resolved"] + len(result["unresolved"]) == result["total"]
    assert len(direct) == 49  # 统一判定现算（design §10.3 预计 52，T10 合并别名后 I1-1 三条可解析）
    assert result["outside_list"] == [] and result["stale_acknowledgements"] == []
    assert all(u["reason"] for u in result["unresolved"])


def test_acks_equal_unresolved_and_generator_report(real, result, chk):
    acked = chk.acknowledged_ccr_ids(real["acks"])
    unresolved = sorted(u["ref_id"] for u in result["unresolved"])
    assert sorted(acked) == unresolved
    assert real["report"]["open_problems"]["ccr_unresolved"] == unresolved
    for e in _ccr_acks(real["acks"]):
        assert len(e["covers"]["ccr_ids"]) == 1 and e["id"] == f"ack-ccr-unresolved-{e['covers']['ccr_ids'][0]}"


def test_each_ack_has_owner_expiry_reason_and_recomputed_evidence(real):
    index = CatalogIndex(real["catalog"])
    by_parent: dict[str, list[dict]] = {}
    for s in real["catalog"]["sheets"]:
        by_parent.setdefault(s["parent_wp_code"], []).append(s)
    refs = {r["ref_id"]: r for r in real["ccr"]["references"]}
    missing_text = {"evidence_1": "缺证据①", "evidence_2": "缺证据②", "evidence_2_no_field_text": "证据②无从核对"}
    for e in _ccr_acks(real["acks"]):
        ref = refs[e["covers"]["ccr_ids"][0]]
        assert e["owner"].endswith("）") and "循环" in e["owner"]
        assert e["expires_on"] == "2027-04-30"
        sm = exact_identity.sheet_of(ref["source_wp"], ref["source_sheet"], index=index)
        assert e["evidence"]["identity"] == {"state": sm.state, "reason": sm.reason}
        assert e["evidence"]["ccr_source"] == {k: ref.get(k) for k in ("source_wp", "source_sheet", "source_cell",
                                                                       "source_cell_label")}
        got = ev.source_evidence(ref, by_parent.get(ref["source_wp"], []))
        assert {k: e["evidence"][k] for k in got} == got, ref["ref_id"]
        assert got["text_found"] == [] and got["missing"] != "none", f"{ref['ref_id']} 两项证据齐备，应改写而非豁免"
        assert missing_text[got["missing"]] in e["reason"], ref["ref_id"]


def test_b60_and_s14_cannot_be_rewritten(real):
    """R2-F3：B60 的 6 条与 S14 的 1 条都在豁免里（不改写到工时预算看板 / S14-1）。"""
    acked = {e["covers"]["ccr_ids"][0] for e in _ccr_acks(real["acks"])}
    assert {"CW-60", "CW-417", "CW-418", "CW-419", "CW-420", "CW-421", "CW-79"} <= acked


# ─── 相对基线的改写须两项证据 ─────────────────────────────────────────────────────


def rewrite_violations(refs: list[dict], catalog: dict, head: dict) -> list[str]:
    """source_wp / source_sheet 相对基线改过的条目：改写目标须是目录表，且两项证据齐备。"""
    index = CatalogIndex(catalog)
    out = []
    for r in refs:
        base = head["sources"].get(r["ref_id"])
        cur = {"source_wp": r.get("source_wp"), "source_sheet": r.get("source_sheet")}
        if base is None or base == cur:
            continue
        sm = exact_identity.sheet_of(cur["source_wp"] or "", cur["source_sheet"] or "", index=index)
        if not sm.ok or sm.entry is None:
            out.append(f"{r['ref_id']}: 改写后的表不在目录（{sm.reason}）")
            continue
        e = ev.target_evidence(r, sm.entry)
        if not e["tab_found"]:
            out.append(f"{r['ref_id']}: 缺证据①（{sm.entry['addr_id']} 在模板册里没有 tab）")
        elif not e["text_found"]:
            out.append(f"{r['ref_id']}: 缺证据②（字段文字「{ev.field_text(r)}」不在 {sm.entry['addr_id']} 的 tab 里）")
    return out


def test_head_fixture_matches_base_commit():
    head = _json(_HEAD_FIXTURE)
    proc = subprocess.run(["git", "show", f"{head['base_commit']}:backend/data/cross_wp_references.json"], cwd=_REPO,
                          capture_output=True)
    if proc.returncode != 0:
        pytest.skip("无 git 历史，无法复核基线夹具")
    import hashlib

    raw = proc.stdout.replace(b"\r\n", b"\n")
    assert hashlib.sha256(raw).hexdigest() == head["base_file_sha256"]
    base = json.loads(raw.decode("utf-8"))["references"]
    assert head["sources"] == {r["ref_id"]: {"source_wp": r.get("source_wp"), "source_sheet": r.get("source_sheet")}
                               for r in base}


def test_current_rewrites_have_two_evidence(real):
    assert rewrite_violations(real["ccr"]["references"], real["catalog"], _json(_HEAD_FIXTURE)) == []


def test_rewriting_b60_to_workload_board_is_rejected(real):
    """变异（内存）：把 CW-60 的源表改写成 B60 唯一目录子表（工时预算看板）→ 缺证据②红。"""
    refs = copy.deepcopy(real["ccr"]["references"])
    board = next(s for s in real["catalog"]["sheets"] if s["addr_id"] == "B60/B60-1")
    cw60 = next(r for r in refs if r["ref_id"] == "CW-60")
    cw60["source_sheet"] = board["sheet_name"]
    v = rewrite_violations(refs, real["catalog"], _json(_HEAD_FIXTURE))
    assert len(v) == 1 and v[0].startswith("CW-60: 缺证据")


# ─── 清单外与失效豁免 ──────────────────────────────────────────────────────────


def test_stale_ack_and_outside_list_are_reported(chk, real):
    acks = copy.deepcopy(real["acks"])
    dropped = next(e for e in acks["entries"] if e.get("id") == "ack-ccr-unresolved-CW-60")
    acks["entries"].remove(dropped)
    acks["entries"].append({**copy.deepcopy(dropped), "id": "ack-ccr-unresolved-CW-01", "covers": {"ccr_ids": ["CW-01"]}})
    acks["entries"].append({**copy.deepcopy(dropped), "id": "ack-ccr-unresolved-CW-9999", "covers": {"ccr_ids": ["CW-9999"]}})
    r = chk.run(real["catalog"], real["ccr"], acks)
    assert [u["ref_id"] for u in r["outside_list"]] == ["CW-60"]
    assert {(s["ccr_id"], s["detail"]) for s in r["stale_acknowledgements"]} == {
        ("CW-01", "该 CCR 源已可解析"), ("CW-9999", "CCR 里已没有这条引用")}


def test_main_exit_codes(chk, real, tmp_path, monkeypatch, capsys):
    assert chk.main(["--blocking"]) == 0
    acks = copy.deepcopy(real["acks"])
    acks["entries"] = [e for e in acks["entries"] if e.get("id") != "ack-ccr-unresolved-CW-422"]
    p = tmp_path / "acks.json"
    p.write_text(json.dumps(acks, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(chk, "ACK_PATH", p)
    assert chk.main(["--blocking"]) == 1
    assert chk.main([]) == 0  # 报告模式不阻断
    monkeypatch.setattr(chk, "ACK_PATH", tmp_path / "缺失.json")
    assert chk.main(["--blocking"]) == 2  # 输入缺失不放行
    out = capsys.readouterr().out
    assert "CW-422" in out


def test_blocking_fails_on_stale_ack_alone(chk, real, tmp_path, monkeypatch, capsys):
    """只有失效豁免、没有清单外（评审 RV9.3-01）：--blocking 退出 1 并点名该豁免；报告模式仍退出 0。"""
    acks = copy.deepcopy(real["acks"])
    template = next(e for e in acks["entries"] if e.get("id") == "ack-ccr-unresolved-CW-60")
    acks["entries"].append({**copy.deepcopy(template), "id": "ack-ccr-unresolved-CW-01", "covers": {"ccr_ids": ["CW-01"]}})
    r = chk.run(real["catalog"], real["ccr"], acks)
    assert r["outside_list"] == []
    assert [(s["ack_id"], s["detail"]) for s in r["stale_acknowledgements"]] == [
        ("ack-ccr-unresolved-CW-01", "该 CCR 源已可解析")]
    p = tmp_path / "acks.json"
    p.write_text(json.dumps(acks, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(chk, "ACK_PATH", p)
    capsys.readouterr()
    assert chk.main(["--blocking"]) == 1
    out = capsys.readouterr().out
    assert "[失效豁免] ack-ccr-unresolved-CW-01（CW-01）：该 CCR 源已可解析" in out
    assert "清单外 0 条、失效豁免 1 条，blocking 模式退出 1" in out
    assert chk.main([]) == 0  # 报告模式不阻断


# ─── 停用条目引用计入 deprecated 组（RV7-03） ─────────────────────────────────────────


def test_deprecated_group_counts(chk, real, result):
    assert result["deprecated"] == {"count": 0, "items": []}
    mut = copy.deepcopy(real["catalog"])
    marked = set()
    for s in mut["sheets"]:
        if (s["parent_wp_code"] == "D4" and s["sheet_code"] != "D4") or s["addr_id"] == "G14/G14-2":
            s["deprecated"] = True
            marked.add(s["addr_id"])
    r = chk.run(mut, real["ccr"], real["acks"])
    # 旧检查器同一变异得 30（源 22 + 目标 8）；统一判定下源多 2 条：CW-D424-D27 / CW-D424-E131 的 source_wp 是表编码
    # D4-24，旧私有判定解析不了，exact_identity 第 1 步按表编码定位父级后可解析（D4/D4-24/A24）
    assert r["deprecated"]["count"] == 32
    roles = [d["role"] for d in r["deprecated"]["items"]]
    assert roles.count("source") == 24 and roles.count("target") == 8
    assert all("/".join(d["addr_id"].split("/")[:2]) in marked for d in r["deprecated"]["items"])
    assert {"CW-D424-D27", "CW-D424-E131"} <= {d["ref_id"] for d in r["deprecated"]["items"]}


# ─── V2 双读对账产物 ────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def recon():
    return _load_module("t22_reconcile", _RECONCILE)


@pytest.fixture(scope="module")
def recon_artifact():
    return _json(_ACNR / "v2_canonical_reconcile.json")


def test_reconcile_check_passes():
    proc = _run([str(_RECONCILE), "--check"])
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_reconcile_counts_self_consistent_and_reasons_chinese(recon_artifact, real):
    files = recon_artifact["files"]
    assert list(files) == [f"backend/data/{n}" for n in (
        "address_registry_l2_semantic.json", "address_registry_resolved_refs.json",
        "address_registry_l3_dependencies.json", "cross_wp_references.json")]
    total = 0
    for f, body in files.items():
        assert body["nodes"] == sum(c["count"] for c in body["by_class"].values()), f
        for code, c in body["by_class"].items():
            assert c["reason"] and any("\u4e00" <= ch <= "\u9fff" for ch in c["reason"]), (f, code)
            assert 0 < len(c["samples"]) <= min(20, c["count"])
            for s in c["samples"]:
                assert bool(s["addr_id"]) == (code == "addr_id")
                assert (s["unresolved_reason"] is None) == (code == "addr_id")
        total += body["nodes"]
    assert recon_artifact["totals"]["nodes"] == total
    refs = real["ccr"]["references"]
    assert files["backend/data/cross_wp_references.json"]["nodes"] == len(refs) + sum(len(r.get("targets") or []) for r in refs)
    deps = _json(_DATA / "address_registry_l3_dependencies.json")["dependencies"]
    assert files["backend/data/address_registry_l3_dependencies.json"]["nodes"] == 2 * len(deps)
    assert recon_artifact["registry_version"] == real["catalog"]["registry_version"]


def test_reconcile_diff_names_changed_bucket(recon, recon_artifact):
    """变异（内存）：改一个计数 → 比对点名该「文件 × 分类」。"""
    tampered = copy.deepcopy(recon_artifact)
    bucket = tampered["files"]["backend/data/cross_wp_references.json"]["by_class"]["label_not_a1"]
    bucket["count"] += 1
    lines = recon._diff(tampered, recon_artifact)
    assert any("cross_wp_references.json × label_not_a1" in x for x in lines), lines
