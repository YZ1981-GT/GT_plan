"""render-config 共享载荷（spec platform-perf-hotspots R1）。

- ``share_duplicated_html_data``：只按对象身份分组，展开后与原响应逐页深度相等，不改入参；
- 路由：不带参数（含直接调用拿到 Query 默认对象）响应不变；``share_html_data=1`` 下发共享形状。
"""

from __future__ import annotations

import copy
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.routers._wp_gate as wp_gate
from app.core.database import get_db
from app.deps import get_current_user
from app.routers import wp_render_config as rc
from app.routers.wp_render_config_helpers import share_duplicated_html_data
from app.schemas.render_config_contract import RenderConfigResponse


def _expand(response: dict) -> dict:
    """前端 expandSharedHtmlData 的同口径实现（逐页深拷贝共享块 + 页签差异键）。"""
    shared = response.get("shared_html_data") or {}
    sheets = []
    for sheet in response["sheets"]:
        ref = sheet.get("html_data_ref")
        if ref is None:
            sheets.append(sheet)
            continue
        restored = {key: value for key, value in sheet.items() if key != "html_data_ref"}
        restored["html_data"] = {**copy.deepcopy(shared[ref]), **(sheet.get("html_data") or {})}
        sheets.append(restored)
    return {**{k: v for k, v in response.items() if k != "shared_html_data"}, "sheets": sheets}


def _sheet(name: str, html_data, component_type: str = "d2-accounts-receivable") -> dict:
    return {"sheet_name": name, "componentType": component_type, "schema": None,
            "html_data": html_data, "cross_refs": []}


def _d2_like_response() -> dict:
    """D2 形态：b-index 自有数据 + 3 个 D2 渲染器页（memo 浅拷贝）+ OnlyOffice 占位 + 空页。"""
    memo = {
        "sheet_name": "审定表D2-1",
        "project_context": {"year": 2025, "applicable_standards": ["soe"]},
        "responses_snapshot": {"D2-1-adj-0": {"remark": "x"}},
        "parent_check": [],
        "tier": "A",
    }
    d2_pages = [_sheet(n, {**memo, "sheet_name": n}) for n in ("审定表D2-1", "明细表D2-2", "坏账准备D2-3")]
    return {
        "wp_id": "wp", "wp_code": "D2", "project_id": "p", "scope": "standalone",
        "is_real_workpaper": True, "template_version": None, "audit_year": 2025,
        "applicable_standards": ["soe"], "fill_results": {}, "guidance": None,
        "sheets": [
            _sheet("底稿目录", {"cells": [["D2", "应收账款"]]}, "b-index"),
            *d2_pages,
            _sheet("附注", {"onlyoffice": True, "sheet_name": "附注"}, "onlyoffice-sheet"),
            _sheet("说明", None, "skip-like"),
        ],
    }


# ─── share_duplicated_html_data 分组规则 ────────────────────────────────────


def test_memo_copies_share_one_payload_and_expand_back_exactly() -> None:
    resp = _d2_like_response()
    before = copy.deepcopy(resp)
    got = share_duplicated_html_data(resp)

    assert resp == before, "不得改入参"
    assert list(got["shared_html_data"]) == ["h1"]
    assert "sheet_name" not in got["shared_html_data"]["h1"]
    shared_pages = [s for s in got["sheets"] if s.get("html_data_ref") == "h1"]
    assert [s["html_data"] for s in shared_pages] == [
        {"sheet_name": "审定表D2-1"}, {"sheet_name": "明细表D2-2"}, {"sheet_name": "坏账准备D2-3"},
    ]
    # 其余页签原样（同一对象），不带引用
    for i in (0, 4, 5):
        assert got["sheets"][i] is resp["sheets"][i]
    assert _expand(got) == resp


def test_whole_dedicated_same_object_keeps_first_page_sheet_name() -> None:
    whole = {"sheet_name": "第一页", "data": {"rows": [1]}}
    resp = {**_d2_like_response(), "sheets": [_sheet(n, whole, "j1-x") for n in ("第一页", "第二页")]}
    got = share_duplicated_html_data(resp)
    assert [s["html_data"] for s in got["sheets"]] == [{"sheet_name": "第一页"}] * 2
    assert _expand(got) == resp


def test_payload_without_sheet_name_leaves_empty_page_html_data() -> None:
    same = {"rows": [{"a": 1}], "project_context": {}}
    resp = {**_d2_like_response(), "sheets": [_sheet(n, same, "d3-prepaid-accounts") for n in ("A", "B")]}
    got = share_duplicated_html_data(resp)
    assert [s["html_data"] for s in got["sheets"]] == [{}, {}]
    assert got["shared_html_data"] == {"h1": same}
    assert _expand(got) == resp


def test_equal_content_in_distinct_objects_is_not_shared() -> None:
    """只认对象身份：逐页独立渲染出的同值载荷照旧各自下发（不做序列化比较）。"""
    resp = {**_d2_like_response(), "sheets": [
        _sheet("A", {"rows": [1], "sheet_name": "A"}), _sheet("B", {"rows": [1], "sheet_name": "B"}),
    ]}
    assert share_duplicated_html_data(resp) is resp


def test_scalar_only_payloads_and_singletons_are_not_shared() -> None:
    ctx, empty = {"k": 1}, []
    resp = {**_d2_like_response(), "sheets": [
        _sheet("OO1", {"onlyoffice": True, "sheet_name": "OO1"}, "onlyoffice-sheet"),
        _sheet("OO2", {"onlyoffice": True, "sheet_name": "OO2"}, "onlyoffice-sheet"),
        _sheet("solo", {"project_context": ctx}),
        # 同一个空容器：同组但没有可省的载荷，不共享
        _sheet("empty1", {"rows": empty}), _sheet("empty2", {"rows": empty}),
    ]}
    assert share_duplicated_html_data(resp) is resp


def test_scalar_type_is_part_of_the_key() -> None:
    """True 与 1 在 Python 里相等，序列化却不同（true / 1），不得并组。"""
    ctx = {"k": 1}
    resp = {**_d2_like_response(), "sheets": [
        _sheet("A", {"project_context": ctx, "flag": True}), _sheet("B", {"project_context": ctx, "flag": 1}),
    ]}
    assert share_duplicated_html_data(resp) is resp


def test_two_groups_get_distinct_refs_in_first_appearance_order() -> None:
    m1, m2 = {"rows": [1], "sheet_name": "a"}, {"rows": [2], "sheet_name": "b"}
    resp = {**_d2_like_response(), "sheets": [
        _sheet("x1", {**m1, "sheet_name": "x1"}), _sheet("y1", {**m2, "sheet_name": "y1"}),
        _sheet("x2", {**m1, "sheet_name": "x2"}), _sheet("y2", {**m2, "sheet_name": "y2"}),
    ]}
    got = share_duplicated_html_data(resp)
    assert [s["html_data_ref"] for s in got["sheets"]] == ["h1", "h2", "h1", "h2"]
    assert _expand(got) == resp


def test_shared_shape_passes_strict_wire_model() -> None:
    got = share_duplicated_html_data(_d2_like_response())
    dumped = RenderConfigResponse.model_validate(got).model_dump(by_alias=True, exclude_unset=True, mode="json")
    assert dumped == got


# ─── 路由 ────────────────────────────────────────────────────────────────────


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch):
    calls: list[int] = []

    async def _no_gate(*_args, **_kwargs):
        return None

    async def _impl(*_args, **_kwargs):
        calls.append(1)
        return _d2_like_response()

    monkeypatch.setattr(wp_gate, "enforce_wp_gate", _no_gate)
    monkeypatch.setattr(rc, "_get_render_config_impl", _impl)
    app = FastAPI()
    app.include_router(rc.router)
    app.dependency_overrides[get_db] = lambda: None
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=uuid4())
    with TestClient(app) as test_client:
        yield test_client, calls


def _baseline_wire() -> dict:
    return RenderConfigResponse.model_validate(_d2_like_response()).model_dump(
        by_alias=True, exclude_unset=True, mode="json")


@pytest.mark.parametrize("query", ["", "?share_html_data=0", "?share_html_data=false"])
def test_route_without_param_is_unchanged(client, query: str) -> None:
    test_client, calls = client
    res = test_client.get(f"/api/workpapers/{uuid4()}/render-config{query}")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body == _baseline_wire()
    assert "shared_html_data" not in body
    assert all("html_data_ref" not in s for s in body["sheets"])
    assert calls == [1]


def test_route_with_param_sends_shared_shape_that_expands_to_baseline(client) -> None:
    test_client, _ = client
    res = test_client.get(f"/api/workpapers/{uuid4()}/render-config?share_html_data=1")
    assert res.status_code == 200, res.text
    body = res.json()
    assert set(body["shared_html_data"]) == {"h1"}
    assert sum(1 for s in body["sheets"] if s.get("html_data_ref") == "h1") == 3
    assert _expand(body) == _baseline_wire()


async def test_direct_call_without_param_does_not_share(monkeypatch: pytest.MonkeyPatch) -> None:
    """测试 / 内部直接调用路由函数时 share_html_data 是 Query 默认对象（真值），不得当成开启。"""
    payload = _d2_like_response()

    async def _no_gate(*_args, **_kwargs):
        return None

    async def _impl(*_args, **_kwargs):
        return payload

    monkeypatch.setattr(wp_gate, "enforce_wp_gate", _no_gate)
    monkeypatch.setattr(rc, "_get_render_config_impl", _impl)
    got = await rc.get_render_config(
        wp_id=uuid4(), sheet_name=None, component_type=None, db=None,
        current_user=SimpleNamespace(id=uuid4()),
    )
    assert got is payload
