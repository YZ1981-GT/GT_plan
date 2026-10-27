"""T05：孤儿与历史移除判定记录 sheet_verdicts（需求 2 / D2 / R2-F1；段四审计 F4-06 返工）。

判定记录的每条证据都要能现算复现，不是常量：
  1. 两段结构 + verdict 枚举（sheet ∈ {add_platform_sheet,fix_parent,deprecate}，cell 恒 deprecate）。
  2. 离线证据逐项现算并与记录相等（design §3.2）：模板册 tab（openpyxl）、渲染组件 schema 的 tab 与跨引
     （YAML 解析）、地址种子、I/E manifest、wp_account_mapping、classification 缓存、是否已在目录；
     孤儿 cell 的 static_refs（backend/data 全 JSON/YAML 对 addr_id / formula_ref 命中）、formula_ref 与目录一致、
     A1 在父 sheet 的种子坐标里。
  3. pg_only（真库只读）：记录的 wp_index / project_files 是 as_of 当日的快照，逐值等于真库现算（10 个 sheet 编码
     的在用项目数、sheet 级底稿数、有文件数、parsed_data 是否全空，25 个孤儿 cell 的 project_files 等于父 sheet 的
     现算值；真库变化即红，须重录证据并复核判定）；判定前提——10 个编码在用、5 张补登父 sheet 的 sheet 级底稿都有
     文件但没有单元格数据；17 个 formula / expression 文本列对 25 个孤儿 addr_id / formula_ref 命中为 0（= 记录的
     pg_formula_refs）。
  4. 「删 I6-7 → 门禁点名 I6/I6-7」的门禁级变异须等 T07 门禁接上判定记录后重做（本任务因此仍为 [ ]）。
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import pytest

from app.services.acnr.loaders.from_sheet_verdicts import (
    CELL_VERDICTS,
    SHEET_VERDICTS,
    SheetVerdictError,
    load_sheet_verdicts,
)

_BACKEND = Path(__file__).resolve().parents[2]  # backend/
_REPO = _BACKEND.parent
_DATA = _BACKEND / "data"
_ACNR = _DATA / "acnr"
_TEMPLATES = _BACKEND / "wp_templates"
_RENDER_DIRS = (_BACKEND / "app" / "data" / "wp_render_schema", _DATA / "ledger_adapters" / "wp_render_schema")

# R2-F1：25 个孤儿 cell（parent sheet 不在目录 ⇒ 孤儿）
_ORPHAN_CELLS = {
    "I6/I6-7/B25", "I6/I6-7/C5", "I6/I6-7/E20", "I6/I6-7/F20", "I6/I6-7/G20",
    "J2/J2-5/E10", "J2/J2-5/E20", "J2/J2-5/F10", "J2/J2-5/F20", "J2/J2-5/G10",
    "J3/J3-4/C10", "J3/J3-4/C5", "J3/J3-4/C6", "J3/J3-4/C7", "J3/J3-4/C8", "J3/J3-4/C9",
    "J3/J3-5/E10", "J3/J3-5/F10", "J3/J3-5/G10", "J3/J3-5/H10",
    "M6/M6-5/C5", "M6/M6-5/C6", "M6/M6-5/C7", "M6/M6-5/D7", "M6/M6-5/E7",
}
# K14~K18 → 替代审定表 addr_id + 科目
_DEPRECATE_EXPECT = {
    "K14/K14": ("H10/H10-1", "6115"),
    "K15/K15": ("K10/K10-1", "6117"),
    "K16/K16": ("G11/G11-1", "6111"),
    "K17/K17": ("G13/G13-1", "6101"),
    "K18/K18": ("K7/K7-1", "2401"),
}
_ADD_PLATFORM = {"I6/I6-7", "J2/J2-5", "J3/J3-4", "J3/J3-5", "M6/M6-5"}


# ─── 离线证据现算（与 sheet_verdicts.json 的 evidence 字段一一对应） ────────────


def _rel(p: Path) -> str:
    return p.relative_to(_REPO).as_posix()


def ev_template_tabs(parent_wp_code: str, sheet_code: str, seed_name: str | None) -> dict[str, Any]:
    """父级模板册：册文件、tab 数、是否有本 sheet 的 tab（tab 名以编码结尾或等于种子名）。"""
    import openpyxl

    folder = _TEMPLATES / parent_wp_code[:1]
    files = sorted(p for p in folder.glob("*.xlsx") if re.match(rf"^{re.escape(parent_wp_code)} ", p.name))
    if not files:
        return {"file": None, "tab_count": 0, "has_tab": False}
    wb = openpyxl.load_workbook(files[0], read_only=True)
    try:
        names = list(wb.sheetnames)
    finally:
        wb.close()
    has = any(n.endswith(sheet_code) or (seed_name is not None and n == seed_name) for n in names)
    return {"file": _rel(files[0]), "tab_count": len(names), "has_tab": has}


@lru_cache(maxsize=1)
def _render_schemas() -> tuple[tuple[Path, dict], ...]:
    import yaml

    out = []
    for d in _RENDER_DIRS:
        for p in sorted(d.rglob("*.yaml")):
            try:
                data = yaml.safe_load(p.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001 - 解析不了的 schema 不作证据来源
                continue
            if isinstance(data, dict):
                out.append((p, data))
    return tuple(out)


@lru_cache(maxsize=1)
def _component_of() -> dict[str, str]:
    return json.loads((_BACKEND / "app" / "data" / "wp_code_overrides.json").read_text(encoding="utf-8"))


def _schema_tabs(data: dict) -> list[tuple[str, str]]:
    sheets = data.get("sheets")
    if isinstance(sheets, dict):
        return [(str(k), "") for k in sheets]
    if isinstance(sheets, list):
        return [(str(s.get("name") or s.get("sheet_name") or ""), str(s.get("wp_code") or ""))
                for s in sheets if isinstance(s, dict)]
    return []


def ev_renderer_tabs(sheet_code: str, seed_name: str | None) -> dict[str, Any]:
    """渲染组件 schema（component_type 取 wp_code_overrides）是否有本 sheet 的 tab。"""
    component = _component_of().get(sheet_code)
    files, has = [], False
    for p, data in _render_schemas():
        if component and data.get("component_type") == component:
            files.append(_rel(p))
            for name, code in _schema_tabs(data):
                if code == sheet_code or name.endswith(sheet_code) or (seed_name is not None and name == seed_name):
                    has = True
    return {"component_type": component, "schema_files": files, "has_tab": has}


def ev_renderer_cross_refs(sheet_code: str) -> list[str]:
    """声明了 cross_refs / cross_wp_references 指向本 sheet 编码的渲染 schema（数据流声明，不带坐标）。"""
    hits = []
    for p, data in _render_schemas():
        refs = list(data.get("cross_refs") or []) + list(data.get("cross_wp_references") or [])
        if any(isinstance(r, dict) and r.get("target_wp") == sheet_code for r in refs):
            hits.append(_rel(p))
    return sorted(hits)


def ev_seeds(sheet_code: str) -> dict[str, Any] | None:
    for p in sorted(_DATA.glob("*_address_registry_seed.json")):
        data = json.loads(p.read_text(encoding="utf-8"))
        blocks = data.values() if isinstance(data, dict) else []
        for block in blocks:
            if not isinstance(block, list):
                continue
            for item in block:
                if isinstance(item, dict) and item.get("wp_code") == sheet_code:
                    cells = sorted(c.get("cell_address") for c in item.get("coordinates", []) if c.get("cell_address"))
                    return {"file": _rel(p), "sheet_name": item.get("sheet_name"), "cells": cells}
    return None


def ev_ie_manifest(sheet_code: str) -> bool:
    import yaml

    def walk(o: Any) -> bool:
        if isinstance(o, dict):
            return o.get("wp_code") == sheet_code or o.get("sheet_code") == sheet_code or any(walk(v) for v in o.values())
        if isinstance(o, list):
            return any(walk(v) for v in o)
        return False

    return any(walk(yaml.safe_load(p.read_text(encoding="utf-8")))
               for p in sorted((_ACNR / "sources").glob("*_cycle_ie_manifest.yaml")))


def ev_wp_account_mapping(sheet_code: str) -> list[str]:
    data = json.loads((_DATA / "wp_account_mapping.json").read_text(encoding="utf-8"))
    return sorted({m.get("wp_name") for m in data.get("mappings", []) if m.get("wp_code") == sheet_code and m.get("wp_name")})


@lru_cache(maxsize=1)
def _classification() -> list[dict]:
    return json.loads((_ACNR / "sources" / "classification_cache.json").read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _catalog() -> dict:
    return json.loads((_ACNR / "global_catalog.json").read_text(encoding="utf-8"))


def offline_sheet_evidence(sheet_code: str, parent_wp_code: str, addr_id: str) -> dict[str, Any]:
    """一条 sheet 判定的离线证据（全部现算）。"""
    seed = ev_seeds(sheet_code)
    seed_name = seed["sheet_name"] if seed else None
    return {
        "classification_count": sum(1 for r in _classification() if r.get("wp_code") == sheet_code),
        "in_catalog_as_sheet": addr_id in {s.get("addr_id") for s in _catalog().get("sheets", [])},
        "template_tabs": ev_template_tabs(parent_wp_code, sheet_code, seed_name),
        "renderer_tabs": ev_renderer_tabs(sheet_code, seed_name),
        "renderer_cross_refs": ev_renderer_cross_refs(sheet_code),
        "seeds": seed,
        "ie_manifest": ev_ie_manifest(sheet_code),
        "wp_account_mapping": ev_wp_account_mapping(sheet_code),
    }


_OFFLINE_KEYS = ("classification_count", "in_catalog_as_sheet", "template_tabs", "renderer_tabs",
                 "renderer_cross_refs", "seeds", "ie_manifest", "wp_account_mapping")


@lru_cache(maxsize=1)
def _static_texts() -> tuple[str, ...]:
    """backend/data 全 JSON/YAML 文本（排除目录、快照与本判定记录）。"""
    skip_files = {_ACNR / "global_catalog.json", _ACNR / "sources" / "sheet_verdicts.json"}
    out = []
    for p in _DATA.rglob("*"):
        if not p.is_file() or p.suffix.lower() not in (".json", ".yaml", ".yml"):
            continue
        if "catalog_snapshots" in p.parts or p in skip_files:
            continue
        try:
            out.append(p.read_text(encoding="utf-8"))
        except (UnicodeDecodeError, OSError):
            continue
    assert out, "backend/data 没有可扫描的 JSON/YAML（防空转）"
    return tuple(out)


def _static_hits(needle: str) -> int:
    """needle 在 backend/data 全 JSON/YAML 中的命中文件数（排除目录、快照与本判定记录）。"""
    return sum(1 for t in _static_texts() if needle in t)


# ─── fixtures ─────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def verdicts():
    return load_sheet_verdicts()


@pytest.fixture(scope="module")
def wp_mapping():
    data = json.loads((_DATA / "wp_account_mapping.json").read_text(encoding="utf-8"))
    return data.get("mappings", [])


# ── 1. 两段结构 + 枚举 ───────────────────────────────────────────────────────


def test_two_sections_and_verdict_enums(verdicts):
    assert verdicts.sheet_verdicts, "sheet_verdicts 段为空"
    assert verdicts.cell_verdicts, "cell_verdicts 段为空"
    for sv in verdicts.sheet_verdicts:
        assert sv.verdict in SHEET_VERDICTS
    for cv in verdicts.cell_verdicts:
        assert cv.verdict in CELL_VERDICTS
    # 孤儿 cell（R2-F1）恒 deprecate；§6.4 的 47 格由 test_name_system 核对
    orphans = verdicts.cells_of_kind("orphan")
    assert len(orphans) == 25 and all(cv.verdict == "deprecate" for cv in orphans)


def test_loader_rejects_bad_verdict(tmp_path):
    bad = {
        "sheet_verdicts": [
            {"sheet_code": "X1", "parent_wp_code": "X1", "addr_id": "X1/X1",
             "verdict": "wat", "sheet_name": "x", "reason": "r"}
        ],
        "cell_verdicts": [],
    }
    p = tmp_path / "bad.json"
    p.write_text(json.dumps(bad, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(SheetVerdictError, match="verdict 非法"):
        load_sheet_verdicts(p)


def test_loader_rejects_deprecate_without_replaced_by(tmp_path):
    bad = {
        "sheet_verdicts": [
            {"sheet_code": "X1", "parent_wp_code": "X1", "addr_id": "X1/X1",
             "verdict": "deprecate", "sheet_name": "x", "replaced_by": None, "reason": "r"}
        ],
        "cell_verdicts": [],
    }
    p = tmp_path / "bad.json"
    p.write_text(json.dumps(bad, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(SheetVerdictError, match="replaced_by"):
        load_sheet_verdicts(p)


# ── 2. 判定集合 ──────────────────────────────────────────────────────────────


def test_add_platform_covers_all_orphan_parents(verdicts):
    """5 张父 sheet 恰好覆盖 25 个孤儿 cell 的全部父级（删 I6-7 则此断言红并点名）。"""
    declared = {v.addr_id for v in verdicts.add_platform_sheets()}
    orphan_parents = {c.rsplit("/", 1)[0] for c in _ORPHAN_CELLS}
    assert declared == _ADD_PLATFORM == orphan_parents, (
        f"add_platform 集合与孤儿父级不一致：declared={sorted(declared)} orphan_parents={sorted(orphan_parents)}"
    )


def test_orphan_cells_all_deprecate(verdicts):
    declared = {c.addr_id for c in verdicts.cells_of_kind("orphan") if c.verdict == "deprecate"}
    assert declared == _ORPHAN_CELLS, (
        f"孤儿 cell 集合不一致：缺 {sorted(_ORPHAN_CELLS - declared)} 多 {sorted(declared - _ORPHAN_CELLS)}"
    )


def test_orphan_cells_currently_in_catalog_as_orphans():
    """25 格当前在目录 cells，但父 sheet 不在 sheets ⇒ 孤儿（这正是 T05 要处置的对象）。"""
    cell_addrs = {c.get("addr_id") for c in _catalog().get("cells", [])}
    sheet_addrs = {s.get("addr_id") for s in _catalog().get("sheets", [])}
    for addr in _ORPHAN_CELLS:
        assert addr in cell_addrs, f"孤儿 cell {addr} 现不在目录 cells，判定过期"
        assert addr.rsplit("/", 1)[0] not in sheet_addrs, f"{addr} 的父 sheet 已在目录，非孤儿"


# ── 3. 离线证据逐项现算 ──────────────────────────────────────────────────────


def test_sheet_offline_evidence_recomputed(verdicts):
    """10 条 sheet 判定的离线证据与现算逐项相等（变了即红）。"""
    problems = []
    for v in verdicts.sheet_verdicts:
        live = offline_sheet_evidence(v.sheet_code, v.parent_wp_code, v.addr_id)
        for k in _OFFLINE_KEYS:
            if v.evidence.get(k) != live[k]:
                problems.append(f"{v.addr_id}.{k}: 记录 {v.evidence.get(k)!r} ≠ 现算 {live[k]!r}")
    assert not problems, "判定证据与离线来源现算不符：\n" + "\n".join(problems)


def test_add_platform_sheets_have_no_physical_tab(verdicts):
    """补登父 sheet 的判定前提：模板册与渲染组件都没有这张 tab、classification 0、不在 I/E manifest，但种子与映射有它。"""
    for v in verdicts.add_platform_sheets():
        live = offline_sheet_evidence(v.sheet_code, v.parent_wp_code, v.addr_id)
        assert live["classification_count"] == 0 and live["in_catalog_as_sheet"] is False, v.addr_id
        assert live["template_tabs"]["file"] and live["template_tabs"]["has_tab"] is False, v.addr_id
        assert live["renderer_tabs"]["has_tab"] is False, v.addr_id
        assert live["ie_manifest"] is False, v.addr_id
        assert live["seeds"] is not None and live["wp_account_mapping"] == [live["seeds"]["sheet_name"]], v.addr_id


def test_deprecate_sheets_replaced_by_exist_and_same_account(verdicts, wp_mapping):
    sheet_addrs = {s.get("addr_id") for s in _catalog().get("sheets", [])}
    acct: dict[str, list[str]] = {}
    for m in wp_mapping:
        acct.setdefault(m.get("wp_code", ""), m.get("account_codes", []) or [])
    for v in verdicts.deprecated_sheets():
        expect = _DEPRECATE_EXPECT.get(v.addr_id)
        assert expect is not None, f"未预期的 deprecate sheet {v.addr_id}"
        repl_addr, account = expect
        assert v.replaced_by == repl_addr, f"{v.addr_id} replaced_by 应为 {repl_addr}"
        assert repl_addr in sheet_addrs, f"{v.addr_id} 的 replaced_by {repl_addr} 不在目录"
        assert v.evidence.get("replaced_by_in_catalog") is True
        repl_wp = repl_addr.rsplit("/", 1)[1]
        assert account in acct.get(repl_wp, []), f"{v.addr_id} 替代表 {repl_wp} 科目 {acct.get(repl_wp)} 不含 {account}"
        assert v.evidence.get("account_code") == account


def test_k14_6115_basis_in_prefill(verdicts):
    """K14 的 6115 依据：prefill H10 含 资产处置收益 = TB('6115',...)。"""
    prefill = json.loads((_DATA / "prefill_formula_mapping.json").read_text(encoding="utf-8"))
    h10 = [m for m in prefill.get("mappings", []) if m.get("wp_code") == "H10"]
    blob = json.dumps(h10, ensure_ascii=False)
    assert "6115" in blob and "资产处置收益" in blob, "prefill H10 缺 6115/资产处置收益 依据"
    k14 = next(v for v in verdicts.deprecated_sheets() if v.addr_id == "K14/K14")
    assert "6115" in json.dumps(k14.evidence, ensure_ascii=False)


def test_orphan_cells_offline_evidence_recomputed(verdicts):
    """孤儿 cell：formula_ref 与目录一致、A1 在父 sheet 种子坐标里、static_refs 现算为 0、渲染组件无该 tab。"""
    by_addr = {c["addr_id"]: c for c in _catalog().get("cells", [])}
    parents = {v.addr_id: v for v in verdicts.sheet_verdicts}
    problems = []
    for cv in verdicts.cells_of_kind("orphan"):
        cat_cell = by_addr.get(cv.addr_id, {})
        fr = cv.evidence.get("formula_ref")
        if fr != cat_cell.get("formula_ref"):
            problems.append(f"{cv.addr_id}: formula_ref 与目录不一致")
        parent = parents[cv.parent_sheet_code]
        seed = ev_seeds(parent.sheet_code)
        if not seed or cv.addr_id.rsplit("/", 1)[1] not in seed["cells"]:
            problems.append(f"{cv.addr_id}: A1 不在父 sheet 的种子坐标里")
        live_static = _static_hits(fr) + _static_hits(cv.addr_id)
        if live_static != cv.evidence.get("static_refs"):
            problems.append(f"{cv.addr_id}: static_refs 记录 {cv.evidence.get('static_refs')} ≠ 现算 {live_static}")
        live_has_tab = ev_renderer_tabs(parent.sheet_code, seed["sheet_name"] if seed else None)["has_tab"]
        if cv.evidence.get("renderer_tabs", {}).get("has_tab") != live_has_tab:
            problems.append(f"{cv.addr_id}: renderer_tabs.has_tab 与现算不符")
        if cv.evidence.get("static_refs") != 0:
            problems.append(f"{cv.addr_id}: 有静态引用却判无物理来源")
    assert not problems, "\n".join(problems)


# ── 4. pg_only：在用、无数据、无公式引用 ─────────────────────────────────────


def _pg_conn():
    import psycopg2

    conn = psycopg2.connect(dbname="audit_platform", user="postgres", password="postgres",
                            host="localhost", port=5432, connect_timeout=5)
    conn.set_session(readonly=True, autocommit=False)
    return conn


def _pg_available() -> bool:
    try:
        _pg_conn().close()
        return True
    except Exception:  # noqa: BLE001
        return False


_PG = pytest.mark.skipif(not _pg_available(), reason="需要本机 PG（audit_platform）只读")


def _live_db_evidence(codes: list[str]) -> tuple[dict[str, int], dict[str, dict[str, Any]]]:
    """真库只读现算：sheet 编码 → 在用项目数；sheet 编码 → sheet 级底稿 {数量, 有文件, parsed_data 全空}。"""
    conn = _pg_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT wi.wp_code, count(DISTINCT wi.project_id) FROM wp_index wi JOIN projects p ON p.id = wi.project_id "
            "WHERE wi.wp_code = ANY(%s) AND COALESCE(p.is_deleted, false) = false GROUP BY wi.wp_code",
            (codes,),
        )
        projects = {r[0]: r[1] for r in cur.fetchall()}
        cur.execute(
            "SELECT wi.wp_code, count(*), count(*) FILTER (WHERE wp.file_path IS NOT NULL), "
            "bool_and(wp.parsed_data IS NULL OR wp.parsed_data::text IN ('null', '{}')) "
            "FROM wp_index wi JOIN projects p ON p.id = wi.project_id "
            "JOIN working_paper wp ON wp.wp_index_id = wi.id "
            "WHERE wi.wp_code = ANY(%s) AND COALESCE(p.is_deleted, false) = false GROUP BY wi.wp_code",
            (codes,),
        )
        files = {r[0]: {"sheet_level_workpapers": r[1], "with_file": r[2], "parsed_data_null": bool(r[3])}
                 for r in cur.fetchall()}
        conn.rollback()
    finally:
        conn.close()
    return projects, files


def _pf_values(pf: dict[str, Any]) -> dict[str, Any]:
    return {k: pf.get(k) for k in ("sheet_level_workpapers", "with_file", "parsed_data_null")}


@_PG
def test_db_evidence_snapshot_matches_live_pg(verdicts):
    """记录的 wp_index / project_files 是 as_of 当日的快照：逐值等于真库现算（段四复审 F4-06：此前只做阈值核对）。

    真库变化（新生成 / 删除了这些编码的底稿）即红：须按现算重录证据、更新 as_of，并复核判定是否仍成立。
    """
    codes = sorted(v.sheet_code for v in verdicts.sheet_verdicts)
    projects, files = _live_db_evidence(codes)
    problems = []
    for v in verdicts.sheet_verdicts:
        wi, pf = v.evidence["wp_index"], v.evidence["project_files"]
        assert wi.get("as_of") and pf.get("as_of"), f"{v.addr_id} 证据缺 as_of"
        if wi.get("projects") != projects.get(v.sheet_code, 0):
            problems.append(f"{v.addr_id}.wp_index.projects: 记录 {wi.get('projects')}（as_of {wi.get('as_of')}）"
                            f" ≠ 真库 {projects.get(v.sheet_code, 0)}")
        live_pf = files.get(v.sheet_code, {"sheet_level_workpapers": 0, "with_file": 0, "parsed_data_null": None})
        if _pf_values(pf) != live_pf:
            problems.append(f"{v.addr_id}.project_files: 记录 {_pf_values(pf)}（as_of {pf.get('as_of')}） ≠ 真库 {live_pf}")
    parents = {v.addr_id: v.sheet_code for v in verdicts.sheet_verdicts}
    for cv in verdicts.cells_of_kind("orphan"):
        live_pf = files.get(parents[cv.parent_sheet_code], {})
        if _pf_values(cv.evidence["project_files"]) != live_pf:
            problems.append(f"{cv.addr_id}.project_files: 记录 {_pf_values(cv.evidence['project_files'])} ≠ 父 sheet 真库 {live_pf}")
    assert not problems, "判定记录的数据库证据与真库不符（重录证据并复核判定）：\n" + "\n".join(problems)


@_PG
def test_db_evidence_supports_verdicts_pg(verdicts):
    """判定前提：10 个 sheet 编码在未删项目 wp_index 里在用（导航落点 / 停用不得静默消失）；5 张补登父 sheet 的
    sheet 级底稿都有文件但 parsed_data 里没有单元格数据（无物理来源）。"""
    codes = sorted(v.sheet_code for v in verdicts.sheet_verdicts)
    projects, files = _live_db_evidence(codes)
    missing = [c for c in codes if projects.get(c, 0) < 1]
    assert not missing, f"这些 sheet 编码已无在用项目（判定前提变化，须复核）：{missing}"
    add_codes = sorted(v.sheet_code for v in verdicts.add_platform_sheets())
    assert set(add_codes) <= set(files), f"补登 sheet 的 sheet 级底稿不全：{sorted(set(add_codes) - set(files))}"
    with_data = [c for c in add_codes if not files[c]["parsed_data_null"]]
    assert not with_data, f"这些补登 sheet 的底稿已有数据（无物理来源判定须复核）：{with_data}"
    no_file = [c for c in add_codes if files[c]["with_file"] != files[c]["sheet_level_workpapers"]]
    assert not no_file, f"这些补登 sheet 有底稿没有文件（与记录的证据前提不符）：{no_file}"


@_PG
def test_orphan_cells_pg_formula_refs_zero(verdicts):
    """17 个 formula / expression 文本列对 25 个孤儿 addr_id / formula_ref 的命中为 0（= 记录的 pg_formula_refs）。"""
    conn = _pg_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT table_name, column_name FROM information_schema.columns WHERE table_schema='public' "
            "AND (column_name ILIKE '%%formula%%' OR column_name ILIKE '%%expression%%') "
            "AND data_type IN ('text','character varying','jsonb','json')"
        )
        cols = cur.fetchall()
        assert cols, "没有找到公式类列（防空转）"
        hits: dict[str, int] = {}
        for cv in verdicts.cells_of_kind("orphan"):
            n = 0
            for t, c in cols:
                for needle in (cv.addr_id, cv.evidence["formula_ref"]):
                    cur.execute(f'SELECT count(*) FROM "{t}" WHERE "{c}"::text LIKE %s', (f"%{needle}%",))
                    n += cur.fetchone()[0]
            hits[cv.addr_id] = n
        conn.rollback()
    finally:
        conn.close()
    bad = {k: v for k, v in hits.items() if v}
    assert not bad, f"孤儿 cell 在 PG 公式存储里有引用（不得静默停用）：{bad}"
    assert all(cv.evidence.get("pg_formula_refs") == hits[cv.addr_id] for cv in verdicts.cells_of_kind("orphan"))
