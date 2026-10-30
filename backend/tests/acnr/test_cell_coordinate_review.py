"""目录单元格坐标复核守卫（spec wp-deeplink-locate-coverage-closure 需求 1.5，design §2.3）。

1. ``review_cell_coordinates.py --check``：停用判定（kind=seed_coordinate_mismatch）与 ``t_address_registry_seed.json``
   都等于读模板现算（模板、旧种子或改指规则变了即红）；
2. 目录里未停用、且不在 ``keep_semantic_unverified`` 里的单元格全部来自 t_ 种子：以后新增坐标不经模板复核即红；
3. t_ 种子每个坐标按其 rule 成立：``conclusion_label`` 的模板现值是「审计结论」标签；``explicit`` 只来自显式改指表；
4. 本 kind 的停用格都在目录、已停用、``replaced_by`` 是父 sheet 或 t_ 种子里声明替代它的新坐标（两边互相对得上）；
5. （pg_only）PG 公式类列对本 kind 停用格的 addr_id / formula_ref 引用为 0（与 T05 孤儿判定同口径）；
6. 前端 ``generated/catalogTextAnchors.ts`` 与目录现算一致（``generate_cell_text_anchors.py --check``），只含复核过的
   「审计结论」格；该 ``--check`` 接在 CI 作业 ``acnr-cell-text-anchors-generated`` 上（需求 2.2）。
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

import pytest

from app.services.acnr.catalog import get_catalog
from scripts.acnr import review_cell_coordinates as rcc

_BACKEND = Path(__file__).resolve().parents[2]
_ACNR = _BACKEND / "data" / "acnr"


@lru_cache(maxsize=1)
def _verdicts() -> list[dict]:
    raw = json.loads((_ACNR / "sources" / "sheet_verdicts.json").read_text(encoding="utf-8"))
    return raw["cell_verdicts"]


@lru_cache(maxsize=1)
def _seed() -> dict:
    return json.loads(rcc.T_SEED.read_text(encoding="utf-8"))


def _seed_coords() -> dict[str, tuple[dict, dict]]:
    """t_ 种子坐标 addr_id → (entry, coordinate)。"""
    out = {}
    for e in _seed()["entries"]:
        for c in e["coordinates"]:
            out[f"{rcc._parent_code(e['wp_code'])}/{e['wp_code']}/{c['cell_address']}"] = (e, c)
    return out


def test_check_mode_matches_templates():
    assert rcc.run(write=False) == 0


def test_live_cells_come_from_reviewed_seed():
    cat = get_catalog()
    unverified = {v["addr_id"] for v in _verdicts() if v["verdict"] == "keep_semantic_unverified"}
    live = {a for a, c in cat.cells_by_addr_id.items() if not c.get("deprecated")}
    stray = sorted(live - unverified - set(_seed_coords()))
    assert stray == [], f"未经模板复核的有效单元格（须经 review_cell_coordinates.py 登记）：{stray[:10]}"
    assert set(_seed_coords()) <= live, "t_ 种子坐标应全部是目录里的有效单元格"
    assert len(_seed_coords()) >= 3 and {"E1/E1-14/I18", "E1/E1-14/C34", "E1/E1-14/A50"} <= set(_seed_coords())


def test_seed_coordinates_satisfy_their_rule():
    explicit = {(old.split("/")[1], v["a1"]): old for old, v in rcc.EXPLICIT.items()}
    for aid, (entry, c) in _seed_coords().items():
        if c["rule"] == "conclusion_label":
            text = re.sub(r"\s+", "", str(c["evidence"].get("cell_value") or ""))
            assert rcc.CONCLUSION_RE.match(text), (aid, text)
            assert (c["description"], c["purpose"]) == (rcc.CONCLUSION_LABEL, "conclusion"), aid
        else:
            assert c["rule"] == "explicit" and (entry["wp_code"], c["cell_address"]) in explicit, aid
            assert c["replaces"] == [explicit[(entry["wp_code"], c["cell_address"])]], aid
        assert c["replaces"] and c["evidence"]["template_tab"] == entry["sheet_name"], aid


def test_deprecated_cells_point_to_parent_or_declared_replacement():
    cat = get_catalog()
    coords = _seed_coords()
    declared = {old: new for new, (_e, c) in coords.items() for old in c["replaces"]}
    mine = [v for v in _verdicts() if v.get("kind") == rcc.KIND]
    assert len(mine) >= 300, "防空转：本 kind 的停用判定应有数百条"
    bad = []
    for v in mine:
        cell = cat.cells_by_addr_id.get(v["addr_id"]) or {}
        want = declared.get(v["addr_id"], v["parent_sheet_code"])
        if not (cell.get("deprecated") and cell.get("replaced_by") == v["replaced_by"] == want):
            bad.append((v["addr_id"], v["replaced_by"], want, cell.get("deprecated")))
    assert bad == [], bad[:5]
    assert set(declared) <= {v["addr_id"] for v in mine}, "t_ 种子声明替代的旧坐标都应有停用判定"


def test_text_anchor_artifact_matches_catalog():
    from scripts.acnr import generate_cell_text_anchors as gta

    assert gta.main(["--check"]) == 0, "catalogTextAnchors.ts 与目录现算不一致：运行 generate_cell_text_anchors.py --write"
    anchors = gta.build(json.loads(gta.CATALOG.read_text(encoding="utf-8")))
    ids = {f"{rcc._parent_code(code)}/{code}/{a1}" for code, cells in anchors.items() for a1 in cells}
    assert len(ids) >= 60 and "E1/E1-14/A50" in ids, "防空转：结论格文字锚点应有数十条且含 E1-14 A50"
    assert {t for cells in anchors.values() for t in cells.values()} == {"审计结论"}
    conclusion_seed = {a for a, (_e, c) in _seed_coords().items() if c["rule"] == "conclusion_label"}
    unverified = {v["addr_id"] for v in _verdicts() if v["verdict"] == "keep_semantic_unverified"}
    assert ids <= conclusion_seed | unverified, sorted(ids - conclusion_seed - unverified)[:5]


def test_text_anchor_check_wired_into_ci():
    import yaml

    wf = _BACKEND.parent / ".github" / "workflows" / "governance-checks.yml"
    job = (yaml.safe_load(wf.read_bytes().decode("utf-8")).get("jobs") or {}).get("acnr-cell-text-anchors-generated") or {}
    assert job, "governance-checks.yml 缺作业 acnr-cell-text-anchors-generated"
    assert not job.get("continue-on-error")
    assert any(s.get("run") == "python backend/scripts/acnr/generate_cell_text_anchors.py --check"
               for s in job.get("steps") or [])


def _pg_texts() -> list[str]:
    import psycopg2

    conn = psycopg2.connect(dbname="audit_platform", user="postgres", password="postgres",
                            host="localhost", port=5432, connect_timeout=5)
    conn.set_session(readonly=True, autocommit=True)
    try:
        cur = conn.cursor()
        cur.execute("SELECT table_name, column_name FROM information_schema.columns WHERE table_schema='public' "
                    "AND (column_name ILIKE '%%formula%%' OR column_name ILIKE '%%expression%%') "
                    "AND data_type IN ('text','character varying','jsonb','json')")
        cols = cur.fetchall()
        assert cols, "没有找到公式类列（防空转）"
        texts = []
        for t, c in cols:
            cur.execute(f'SELECT "{c}"::text FROM "{t}" WHERE "{c}" IS NOT NULL')
            texts += [r[0] for r in cur.fetchall() if r[0]]
        return texts
    finally:
        conn.close()


@pytest.mark.pg_only
def test_no_pg_formula_references_to_deprecated_seed_coordinates():
    cat = get_catalog()
    texts = _pg_texts()
    hits = {}
    for v in _verdicts():
        if v.get("kind") != rcc.KIND:
            continue
        fr = (cat.cells_by_addr_id.get(v["addr_id"]) or {}).get("formula_ref") or ""
        n = sum(1 for t in texts for needle in (v["addr_id"], fr) if needle and needle in t)
        if n:
            hits[v["addr_id"]] = n
    assert hits == {}, f"停用的种子坐标在 PG 公式里有引用（不得静默停用）：{hits}"
