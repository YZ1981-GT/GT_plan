"""前端请求体契约夹具对后端请求模型成立（acnr-foundation-defect-closure T16，design §2.8 / R2-F10）。

``fixtures/query_request_fields.json`` 是前端 ``queryPayloads.contract.spec.ts`` 读的「后端模型允许的字段与必填项」：
构建器 ``QueryDSL`` / ``ExportDSL`` 与业务视图 ``QueryRequest``。这里用 pydantic 的 ``model_fields``（不是解析源码文本）
现取字段与必填集合，断言夹具没有过期：夹具里的每个字段后端仍声明（删字段而夹具没跟上 ⇒ 前端会对着过期字段表判绿，
生产上 422）、后端的每个必填字段夹具都列为必填（加必填字段 ⇒ 前端必须发）。后端只加可选字段不影响前端契约，不打红，
避免与并发修改这两个模型的会话互相阻塞。
"""
from __future__ import annotations

import json
from pathlib import Path

from app.routers.custom_query import QueryRequest
from app.services.custom_query.builder_dsl import ExportDSL, QueryDSL

FIXTURE = Path(__file__).with_name("fixtures") / "query_request_fields.json"
MODELS = {"QueryDSL": QueryDSL, "ExportDSL": ExportDSL, "QueryRequest": QueryRequest}


def _shape(model) -> dict:
    return {"fields": sorted(model.model_fields),
            "required": sorted(name for name, info in model.model_fields.items() if info.is_required())}


def test_fixture_holds_for_backend_models():
    data = json.loads(FIXTURE.read_text("utf-8"))
    assert set(data) == set(MODELS)
    for name, model in MODELS.items():
        live = _shape(model)
        stale = sorted(set(data[name]["fields"]) - set(live["fields"]))
        assert not stale, f"{name} 夹具含后端已不声明的字段：{stale}"
        missing = sorted(set(live["required"]) - set(data[name]["required"]))
        assert not missing, f"{name} 后端必填而夹具未列为必填：{missing}"
        assert set(data[name]["required"]) <= set(data[name]["fields"])


def test_fixture_is_not_vacuous():
    """反向自检：三个模型都有 acnr_targets，业务视图 project_id / year / source 必填，构建器 table 必填。"""
    data = json.loads(FIXTURE.read_text("utf-8"))
    assert all("acnr_targets" in data[name]["fields"] for name in MODELS)
    assert {"project_id", "year", "source"} <= set(data["QueryRequest"]["required"])
    assert data["QueryDSL"]["required"] == ["table"]
