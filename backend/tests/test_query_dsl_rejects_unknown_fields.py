"""高级查询顶层请求模型拒收未声明字段与 ``acnr_targets`` 输入校验（acnr-foundation-defect-closure T14，需求 1.4 / 1.5）。

- 模型层：``QueryDSL`` / ``ExportDSL`` / 业务视图 ``QueryRequest`` 含未知键 ⇒ ``unknown_field``，中文消息点名该键；
  ``acnr_targets`` 是声明字段（删掉声明 ⇒ 带 acnr_targets 的合法请求被当成未知键拒收，本文件红）；
  ``AcnrTargetList``：超 50 条、单项空白、超 512 字符拒收，不去重、原样保留；
- 端点层：权限世界真发请求（只 override 当前用户与会话），未知键 ⇒ 422 且 ``detail[0].msg`` 是中文、点名该键，
  不是 pydantic 英文；嵌套模型（``FilterCond``）不受严格模式影响。
"""
from __future__ import annotations

import pytest
import pytest_asyncio
from pydantic import ValidationError

from app.routers import custom_query as cq_router
from app.routers import query_builder as qb_router
from app.routers.custom_query import QueryRequest
from app.services.acnr.limits import ACNR_BATCH_LIMIT
from app.services.custom_query.builder_dsl import ExportDSL, QueryDSL
from app.services.custom_query.strict_model import ACNR_TARGET_MAX_CHARS, StrictRequestModel
from tests.authz_world import TARGET_PROJECT_ID, sqlite_world

_DSL = {"table": "trial_balance"}
_BIZ = {"project_id": str(TARGET_PROJECT_ID), "year": 2025, "source": "trial_balance"}


def _errors(model, payload) -> list[dict]:
    with pytest.raises(ValidationError) as info:
        model.model_validate(payload)
    return info.value.errors()


@pytest.mark.parametrize("model, base", [(QueryDSL, _DSL), (ExportDSL, _DSL), (QueryRequest, _BIZ)])
def test_unknown_key_rejected_with_chinese_message(model, base):
    errs = _errors(model, {**base, "page": 2})
    assert [e["type"] for e in errs] == ["unknown_field"], errs
    assert errs[0]["msg"] == "请求包含未声明的字段「page」，已拒绝"


@pytest.mark.parametrize("model", [QueryDSL, ExportDSL, QueryRequest])
def test_models_inherit_strict_base(model):
    assert issubclass(model, StrictRequestModel)
    assert model.model_config.get("extra") == "forbid"


@pytest.mark.parametrize("model, base", [(QueryDSL, _DSL), (ExportDSL, _DSL), (QueryRequest, _BIZ)])
def test_acnr_targets_is_declared_and_kept_verbatim(model, base):
    """声明字段：原样保留、不去重、顺序不变（需求 1.1 逐项对应）。"""
    targets = ["E1/E1-14/C10", " E1/E1-14/C10 ", "E1/E1-15/C8"]
    got = model.model_validate({**base, "acnr_targets": targets})
    assert got.acnr_targets == targets
    assert model.model_validate(base).acnr_targets == []


@pytest.mark.parametrize("targets, code, needle", [
    (["E1/E1-14/C10"] * (ACNR_BATCH_LIMIT + 1), "acnr_targets_too_many", f"单次最多选择 {ACNR_BATCH_LIMIT} 个单元格"),
    (["E1/E1-14/C10", "   "], "acnr_target_empty", "第 2 个单元格引用为空"),
    (["x" * (ACNR_TARGET_MAX_CHARS + 1)], "acnr_target_too_long", f"超过 {ACNR_TARGET_MAX_CHARS} 个字符"),
], ids=["over_limit", "blank", "too_long"])
@pytest.mark.parametrize("model, base", [(QueryDSL, _DSL), (QueryRequest, _BIZ)])
def test_acnr_targets_input_limits(model, base, targets, code, needle):
    errs = _errors(model, {**base, "acnr_targets": targets})
    assert [e["type"] for e in errs] == [code], errs
    assert needle in errs[0]["msg"]


def test_limits_at_boundary_accepted():
    QueryDSL.model_validate({**_DSL, "acnr_targets": ["E1/E1-14/C10"] * ACNR_BATCH_LIMIT})
    QueryDSL.model_validate({**_DSL, "acnr_targets": [" " + "x" * ACNR_TARGET_MAX_CHARS + " "]})


def test_nested_models_not_strict():
    """严格模式只作用于顶层：嵌套的 FilterCond 照旧（多余键忽略），既有前端不受影响。"""
    got = QueryDSL.model_validate({**_DSL, "filters": [{"field": "year", "op": "eq", "value": 2025, "extra": 1}]})
    assert got.filters[0].field == "year"


# ── 端点层（权限世界：生产注册、真实门禁，只 override 当前用户与会话） ─────────────

@pytest_asyncio.fixture
async def world(monkeypatch: pytest.MonkeyPatch):
    async with sqlite_world(monkeypatch) as w:
        yield w


@pytest.mark.parametrize("path", ["/api/query/execute", "/api/query/preview", "/api/query/export-excel"])
async def test_builder_endpoints_reject_unknown_key(world, path):
    user = (await world.identity("admin_non_member")).user
    async with world.client(qb_router.router, user=user) as client:
        resp = await client.post(path, json={**_DSL, "acnr_target": ["E1/E1-14/C10"]})
    assert resp.status_code == 422, resp.text
    msgs = [e.get("msg") for e in resp.json()["detail"]]
    assert msgs == ["请求包含未声明的字段「acnr_target」，已拒绝"], msgs


async def test_business_execute_rejects_unknown_key(world):
    user = (await world.identity("admin_non_member")).user
    async with world.client(cq_router.router, user=user) as client:
        resp = await client.post("/api/custom-query/execute", json={**_BIZ, "acnr_target": ["E1/E1-14/C10"]})
    assert resp.status_code == 422, resp.text
    assert [e.get("msg") for e in resp.json()["detail"]] == ["请求包含未声明的字段「acnr_target」，已拒绝"]


async def test_business_execute_over_limit_is_chinese_422(world):
    user = (await world.identity("admin_non_member")).user
    async with world.client(cq_router.router, user=user) as client:
        resp = await client.post("/api/custom-query/execute",
                                 json={**_BIZ, "acnr_targets": ["E1/E1-14/C10"] * (ACNR_BATCH_LIMIT + 1)})
    assert resp.status_code == 422, resp.text
    assert f"单次最多选择 {ACNR_BATCH_LIMIT} 个单元格" in resp.json()["detail"][0]["msg"]
