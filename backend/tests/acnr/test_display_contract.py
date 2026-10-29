"""T29：统一显示名下沉为后端单一函数并由生成器写入（需求 12.1 / D10，design §13.2~13.3）。

跨语言契约夹具 `fixtures/display_contract.json` 从真实目录抽样（同组序号、科目简称前缀、停用、语义待核对、
停用 cell）；真实目录没有纯编码 sheet，纯编码与去尾编码、停用不参与序号另用合成组。断言：

- `display.py` 在已提交输入上重算的显示名与已发布目录全部条目逐字相等（生成器写入的就是这个函数的结果）；
- 夹具值与已发布目录、`/api/acnr/resolve`（POST / GET）、`/api/acnr/entries`、acnr_targets 预览、V2 节点逐字相等；
- 候选（多义 / 禁止别名、cell 多命中）的显示名取目录字段；L3 / 非底稿域结果用同一函数现算。
"""
from __future__ import annotations

import asyncio
import copy
import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.deps import get_current_user
from app.routers import acnr as acnr_router
from app.services.acnr import display, resolve_identity, v2_canonical
from app.services.acnr.catalog import get_catalog
from app.services.acnr.resolver import full_resolve
from app.services.custom_query.acnr_target_values import AcnrQueryPlan
from app.services.custom_query.addressing_service import ResolvedTarget

_BACKEND = Path(__file__).resolve().parents[2]
_FIXTURE = json.loads((Path(__file__).resolve().parent / "fixtures" / "display_contract.json").read_text(encoding="utf-8"))
_CATALOG = json.loads((_BACKEND / "data" / "acnr" / "global_catalog.json").read_text(encoding="utf-8"))
_SHEETS = {s["addr_id"]: s for s in _CATALOG["sheets"]}
_CELLS = {c["addr_id"]: c for c in _CATALOG["cells"]}
_LIVE_CELLS = [c for c in _FIXTURE["cells"] if not c["deprecated"]]


def _recomputed(catalog: dict) -> dict:
    out = copy.deepcopy(catalog)
    display.apply_display_labels(out, display.load_name_sources(_BACKEND))
    return out


def test_fixture_covers_required_cases_and_exists_in_catalog():
    """防空转：夹具覆盖 design §13.3 的五类情形，真实样本都在目录里。"""
    cases = " ".join(x["case"] for x in _FIXTURE["sheets"] + _FIXTURE["cells"] + _FIXTURE["synthetic"])
    for need in ("同组序号", "科目简称前缀", "纯编码", "停用", "语义待核对"):
        assert need in cases, f"夹具缺「{need}」样本"
    assert all(x["addr_id"] in _SHEETS for x in _FIXTURE["sheets"])
    assert all(x["addr_id"] in _CELLS for x in _FIXTURE["cells"])
    assert any(x["deprecated"] for x in _FIXTURE["sheets"]) and any(x["deprecated"] for x in _FIXTURE["cells"])
    assert len(_LIVE_CELLS) >= 2


def test_published_catalog_equals_fixture():
    for x in _FIXTURE["sheets"]:
        assert _SHEETS[x["addr_id"]]["display_label"] == x["display_label"], x["addr_id"]
        assert bool(_SHEETS[x["addr_id"]].get("deprecated")) is x["deprecated"]
    for x in _FIXTURE["cells"]:
        c = _CELLS[x["addr_id"]]
        assert (c["cell_label"], c["display_label"]) == (x["cell_label"], x["display_label"]), x["addr_id"]


def test_display_py_recomputes_every_published_label():
    """生成器写入的显示名 == display.py 在已提交输入上的重算结果（全部 sheet 与 cell，逐字）。"""
    again = _recomputed(_CATALOG)
    bad = [e["addr_id"] for e, f in zip(_CATALOG["sheets"] + _CATALOG["cells"], again["sheets"] + again["cells"])
           if (e.get("display_label"), e.get("cell_label")) != (f.get("display_label"), f.get("cell_label"))]
    assert not bad, f"目录显示名与 display.py 重算不一致 {len(bad)} 处，前 5：{bad[:5]}"
    assert len(_CATALOG["sheets"]) > 1000 and all(e.get("display_label") for e in _CATALOG["sheets"] + _CATALOG["cells"])


@pytest.mark.parametrize("case", _FIXTURE["synthetic"], ids=lambda c: c["case"])
def test_synthetic_groups(case):
    src = display.NameSources(mapping=case["sources"]["mapping"], sheet_names=case["sources"]["sheet_names"])
    assert display.compose_sheet_labels(case["group"], src) == case["expected"]


def test_cell_labels_rules():
    assert display.cell_labels("S", {"cell_address": "E5", "semantic_label": "合计"}) == ("E5 合计", "S › E5 合计")
    assert display.cell_labels("S", {"cell_address": "E5", "semantic_label": None}) == ("E5", "S › E5")
    assert display.cell_labels("S", {"cell_address": "E5", "cell_label": "E5（语义待核对）"})[1] == "S › E5（语义待核对）"
    assert resolve_identity.computed_display_label("D2", "E5", "合计") == display.cell_labels("D2", {
        "cell_address": "E5", "semantic_label": "合计"})[1]


@pytest.fixture()
def client():
    app = FastAPI()
    app.include_router(acnr_router.router)

    async def _db():
        yield None

    app.dependency_overrides[get_current_user] = lambda: object()
    app.dependency_overrides[get_db] = _db
    return TestClient(app)


def test_resolve_endpoints_output_catalog_display_label(client):
    for x in _FIXTURE["sheets"] + _FIXTURE["cells"]:
        post = client.post("/api/acnr/resolve", json={"addr_id": x["addr_id"]})
        got = client.get("/api/acnr/resolve", params={"addr_id": x["addr_id"]})
        assert post.status_code == 200 and got.status_code == 200, x["addr_id"]
        for body in (post.json(), got.json()):
            assert body["found"] is True and body["addr_id"] == x["addr_id"], body
            assert body["display_label"] == x["display_label"], (x["addr_id"], body)


def test_entries_output_catalog_display_label(client):
    rows = {r["addr_id"]: r for r in client.get("/api/acnr/entries", params={"include_deprecated": True}).json()}
    for x in _FIXTURE["sheets"]:
        assert rows[x["addr_id"]]["display_label"] == x["display_label"], x["addr_id"]


def test_acnr_targets_preview_outputs_catalog_display_label():
    plan = AcnrQueryPlan(resolved=[ResolvedTarget(raw=x["addr_id"], found=True, addr_id=x["addr_id"])
                                   for x in _LIVE_CELLS], project_id="", year=2025)
    items = asyncio.run(plan.preview(None))
    assert [i["display_label"] for i in items] == [x["display_label"] for x in _LIVE_CELLS]


def test_v2_node_outputs_catalog_display_label():
    cat = get_catalog()
    for x in _LIVE_CELLS:
        c = cat.cells_by_addr_id[x["addr_id"]]
        s = cat.sheets_by_addr_id[c["parent_addr_id"]]
        node = v2_canonical.canonical_node(s["parent_wp_code"], s["sheet_code"], c["cell_address"])
        assert node.addr_id == x["addr_id"] and node.response_fields()["display_label"] == x["display_label"]
    miss = v2_canonical.canonical_node("D1", "D1-2", "Z99999")
    assert miss.addr_id is None and miss.display_label is None


def test_candidates_use_catalog_display_label():
    raw = _CATALOG.get("alias_policy", {}).get("forbidden") or {}
    parent = sorted(raw)[0]
    alias = sorted(raw[parent])[0]
    r = asyncio.run(full_resolve(formula_ref=f"WP('{parent}','{alias}','A1')"))
    assert r.found is False and r.candidates
    for cand in r.candidates:
        assert cand["display_label"] == _SHEETS[cand["addr_id"]]["display_label"], cand
    cell = _CELLS[_LIVE_CELLS[0]["addr_id"]]
    assert resolve_identity.cell_candidate(cell)["display_label"] == _LIVE_CELLS[0]["display_label"]
