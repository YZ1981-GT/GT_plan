"""T10：发布目录的停用条目行为（design §3.3 / §3.4，读真实目录）。

- 孤儿计数 0（含停用条目，父 sheet 都在目录内）；
- sheet_verdicts 判 deprecate 的 25 个孤儿 cell 与 14 个超范围 cell 发布后都是 `deprecated=true` 条目，
  逐个 `full_resolve` 命中、带可解析的 `replaced_by`；判 keep_semantic_unverified 的 33 格仍是有效条目；
- 「无物理来源的有效 cell」为 0：判 deprecate 的 cell 没有一个仍是有效条目；
- K14~K18 五个 sheet 逐个 `full_resolve` 带 `replaced_by`；
- `/api/acnr/entries`（TestClient）默认列 5 张补登 sheet、不列 K14~K18，`include_deprecated=true` 时列出；
  `/api/acnr/anchors` 不受影响（停用 cell 仍随 anchors 返回、带 deprecated 标记，前端选址自行过滤）。
acnr_targets 对停用条目返回 422 属 T14（端点尚未接线），此处不测。
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.deps import get_current_user
from app.routers import acnr as acnr_router
from app.services.acnr.catalog import get_catalog
from app.services.acnr.resolver import full_resolve

_DATA = Path(__file__).resolve().parents[2] / "data" / "acnr"
_VERDICTS = json.loads((_DATA / "sources" / "sheet_verdicts.json").read_text(encoding="utf-8"))
_ADD_PLATFORM = sorted(v["sheet_code"] for v in _VERDICTS["sheet_verdicts"] if v["verdict"] == "add_platform_sheet")
_DEPRECATED_SHEETS = sorted(v["sheet_code"] for v in _VERDICTS["sheet_verdicts"] if v["verdict"] == "deprecate")
_DEPRECATE_CELLS = [v for v in _VERDICTS["cell_verdicts"] if v["verdict"] == "deprecate"]
_KEEP_CELLS = [v for v in _VERDICTS["cell_verdicts"] if v["verdict"] == "keep_semantic_unverified"]


def test_verdict_counts_are_design_counts():
    assert _ADD_PLATFORM == ["I6-7", "J2-5", "J3-4", "J3-5", "M6-5"]
    assert _DEPRECATED_SHEETS == ["K14", "K15", "K16", "K17", "K18"]
    assert sum(1 for v in _DEPRECATE_CELLS if v.get("kind") == "orphan") == 25
    assert sum(1 for v in _DEPRECATE_CELLS if v.get("kind") == "seed_name_mismatch") == 14
    assert len(_KEEP_CELLS) == 33


def test_no_orphan_cells_including_deprecated():
    cat = get_catalog()
    orphans = [c["addr_id"] for c in cat.cells_by_addr_id.values() if c.get("parent_addr_id") not in cat.sheets_by_addr_id]
    assert orphans == []


def test_no_live_cell_without_physical_source():
    """判 deprecate 的 cell 发布后都必须是停用条目（否则即「无物理来源的有效 cell」）。"""
    cat = get_catalog()
    live = [v["addr_id"] for v in _DEPRECATE_CELLS if not (cat.cells_by_addr_id.get(v["addr_id"]) or {}).get("deprecated")]
    assert live == [], f"无物理来源的有效 cell：{live}"
    kept_dep = [v["addr_id"] for v in _KEEP_CELLS if (cat.cells_by_addr_id.get(v["addr_id"]) or {}).get("deprecated")]
    assert kept_dep == [], f"判保留的 cell 被停用：{kept_dep}"


async def _resolve_all(addr_ids: list[str]) -> list:
    return [await full_resolve(addr_id=a) for a in addr_ids]


def test_deprecated_cells_resolve_with_resolvable_replacement():
    rs = asyncio.run(_resolve_all([v["addr_id"] for v in _DEPRECATE_CELLS]))
    bad = []
    for v, r in zip(_DEPRECATE_CELLS, rs):
        if not (r.found and r.deprecated is True and r.replaced_by == v["replaced_by"] and r.reason):
            bad.append((v["addr_id"], r.found, r.deprecated, r.replaced_by))
    assert not bad, bad[:5]
    keys = sorted({v["replaced_by"] for v in _DEPRECATE_CELLS})
    targets = dict(zip(keys, asyncio.run(_resolve_all(keys))))
    # 替代地址是父 sheet，或模板核对后的新坐标（spec wp-deeplink-locate-coverage-closure 改指的 cell）
    wrong = [(v["addr_id"], v["replaced_by"], t.found, t.entry_type, t.deprecated) for v in _DEPRECATE_CELLS
             if not ((t := targets[v["replaced_by"]]).found and not t.deprecated
                     and t.entry_type == ("sheet" if v["replaced_by"] == v["parent_sheet_code"] else "cell"))]
    assert not wrong, wrong[:5]
    assert any(t.entry_type == "cell" for t in targets.values()), "改指新坐标的停用格应至少一个（防空转）"


@pytest.mark.parametrize("code", ["K14", "K15", "K16", "K17", "K18"])
def test_deprecated_sheets_resolve_with_replacement(code):
    want = next(v["replaced_by"] for v in _VERDICTS["sheet_verdicts"] if v["sheet_code"] == code)
    r = asyncio.run(full_resolve(addr_id=f"{code}/{code}"))
    assert r.found and r.deprecated is True and r.replaced_by == want
    assert "该地址已停用，建议改用" in r.reason


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(acnr_router.router)
    app.dependency_overrides[get_current_user] = lambda: {"id": "test", "role": "auditor"}
    return TestClient(app)


def test_entries_hide_deprecated_sheets_by_default():
    client = _client()
    default = {s["sheet_code"] for s in client.get("/api/acnr/entries").json()}
    full = {s["sheet_code"] for s in client.get("/api/acnr/entries", params={"include_deprecated": "true"}).json()}
    assert set(_ADD_PLATFORM) <= default
    assert not (set(_DEPRECATED_SHEETS) & default)
    assert set(_DEPRECATED_SHEETS) <= full
    assert len(full) - len(default) == len(_DEPRECATED_SHEETS)


def test_anchors_unaffected_by_deprecation():
    client = _client()
    cells = client.get("/api/acnr/anchors", params={"wp_code": "I6", "sheet": "I6-7"}).json()
    ids = {c["addr_id"] for c in cells}
    orphan_i6 = {v["addr_id"] for v in _DEPRECATE_CELLS if v["addr_id"].startswith("I6/I6-7/")}
    assert orphan_i6 and orphan_i6 <= ids
    assert all(c.get("deprecated") for c in cells if c["addr_id"] in orphan_i6)
