"""W3 系统预置目录、参数解析与模板 resolve 端点（任务 41）。"""
from __future__ import annotations

import copy
import json
import uuid
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.models.audit_platform_models import Materiality
from app.models.base import UserRole
from app.models.custom_query_models import CustomQueryTemplate
from app.routers import custom_query
from app.services.custom_query import template_presets
from app.services.custom_query.template_preset_params import resolve_parameter_values
from tests.authz_world import TARGET_PROJECT_ID, sqlite_world

CQ = "/api/custom-query"
X = TARGET_PROJECT_ID
EXPECTED_IDS = {
    "je_account_ledger", "je_reversal", "je_negative_amount", "je_cutoff", "je_large_amount",
    "je_weekend", "je_special_event", "je_vague_keywords", "je_both_sides", "je_no_summary",
}


class _Savepoint:
    def __init__(self, db):
        self.db = db

    async def __aenter__(self):
        self.db.entered += 1
        return self

    async def __aexit__(self, exc_type, _exc, _tb):
        self.db.exited.append(exc_type)
        return False


class _ScalarResult:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class _ParamDB:
    def __init__(self, audit_period_end: date | None = None):
        self.audit_period_end = audit_period_end
        self.entered = 0
        self.exited: list[type[BaseException] | None] = []

    def begin_nested(self):
        return _Savepoint(self)

    async def execute(self, _statement):
        return _ScalarResult(self.audit_period_end)


@pytest.fixture(autouse=True)
def _reset_preset_cache():
    template_presets.load_presets.cache_clear()
    yield
    template_presets.load_presets.cache_clear()


def test_authoritative_json_has_exact_ten_valid_presets() -> None:
    document = json.loads(template_presets.PRESETS_PATH.read_text("utf-8"))
    presets = document["presets"]
    assert {item["id"] for item in presets} == EXPECTED_IDS
    assert len(presets) == len(EXPECTED_IDS) == 10
    seen: set[str] = set()
    for preset in presets:
        assert template_presets.validate_preset(
            preset, keyword_sets=document["keyword_sets"], seen_ids=seen,
        ) == [], preset["id"]
    assert len(template_presets.load_presets()) == 10
    listed = template_presets.list_presets()
    assert all(item["read_only"] is True and item["data_source"] == "ledger_entries" for item in listed)
    params = {item["id"]: item["params"] for item in listed}
    assert params["je_large_amount"] == ["materiality_performance"]
    assert params["je_cutoff"] == ["cutoff_start", "cutoff_end"]


def test_one_bad_preset_is_logged_and_skipped_without_hiding_valid_ones(tmp_path, monkeypatch, caplog) -> None:
    document = json.loads(template_presets.PRESETS_PATH.read_text("utf-8"))
    bad = copy.deepcopy(document["presets"][0])
    bad["id"] = "BAD ID"
    bad["config"]["conditions"] = [{"field": "missing", "op": "nope", "value": 1}]
    document["presets"].insert(0, bad)
    path = tmp_path / "presets.json"
    path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(template_presets, "PRESETS_PATH", path)

    loaded = template_presets.load_presets()
    assert {item.id for item in loaded} == EXPECTED_IDS
    assert "跳过无效高级查询预置" in caplog.text and "BAD ID" in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("raw", "value", "missing"),
    [
        (Decimal("1234567.00"), "1234567.00", None),
        (None, None, "2025 年度未设置重要性水平"),
        (Decimal("-507095295.59"), None, "-507,095,295.59"),
        (Decimal("0"), None, "必须大于 0"),
    ],
)
async def test_materiality_parameter_has_no_default(raw, value, missing, monkeypatch) -> None:
    db = _ParamDB()

    async def _current(_self, _project_id, _year):
        return None if raw is None else SimpleNamespace(performance_materiality=raw)

    monkeypatch.setattr("app.services.materiality_service.MaterialityService.get_current", _current)
    items = await resolve_parameter_values(db, X, 2025, ["materiality_performance"])
    item = items["materiality_performance"]
    assert item["value"] == value
    assert (item["missing_reason"] is None) is (missing is None)
    if missing:
        assert missing in item["missing_reason"]
    else:
        assert item["basis"] == "本项目 2025 年度实际执行的重要性水平 1,234,567.00 元"
    assert db.entered == 1 and db.exited == [None]


@pytest.mark.asyncio
async def test_materiality_read_failure_stays_inside_savepoint(monkeypatch) -> None:
    db = _ParamDB()

    async def _boom(_self, _project_id, _year):
        raise RuntimeError("database detail must not reach client")

    monkeypatch.setattr("app.services.materiality_service.MaterialityService.get_current", _boom)
    item = (await resolve_parameter_values(db, X, 2025, ["materiality_performance"]))["materiality_performance"]
    assert item["value"] is None
    assert item["missing_reason"] == "重要性水平读取失败，请填写阈值"
    assert db.entered == 1 and db.exited == [RuntimeError]


@pytest.mark.asyncio
async def test_cutoff_parameters_reuse_project_period_and_default_five_days() -> None:
    db = _ParamDB(date(2025, 11, 30))
    values = await resolve_parameter_values(db, X, 2025, ["cutoff_start", "cutoff_end"])
    assert values["cutoff_start"]["value"] == "2025-11-25"
    assert values["cutoff_end"]["value"] == "2025-12-05"
    assert "前 5 天、后 5 天" in values["cutoff_start"]["basis"]


@pytest.mark.asyncio
async def test_keyword_sets_expand_and_missing_param_reason_reaches_condition(monkeypatch) -> None:
    db = _ParamDB()

    async def _missing(_self, _project_id, _year):
        return None

    monkeypatch.setattr("app.services.materiality_service.MaterialityService.get_current", _missing)
    reversal = await template_presets.resolve(db, "je_reversal", project_id=X, year=2025)
    assert [c["value"] for c in reversal["config"]["conditions"]] == ["冲销", "红字", "冲红", "冲回"]
    large = await template_presets.resolve(db, "je_large_amount", project_id=X, year=2025)
    condition = large["config"]["conditions"][0]
    assert condition["value"] == "" and condition["params"] == ["materiality_performance"]
    assert condition["missing_reason"] == "本项目 2025 年度未设置重要性水平，请填写阈值"


@pytest.fixture
async def world(monkeypatch: pytest.MonkeyPatch):
    tables = (CustomQueryTemplate.__table__, Materiality.__table__)
    async with sqlite_world(monkeypatch, extra_tables=tables) as value:
        yield value


async def _materiality_row(world, *, amount: Decimal = Decimal("800000")) -> None:
    world.db.add(Materiality(
        project_id=X, year=2025, benchmark_type="revenue", benchmark_amount=Decimal("10000000"),
        overall_percentage=Decimal("5"), overall_materiality=Decimal("1000000"),
        performance_ratio=Decimal("80"), performance_materiality=amount,
        trivial_ratio=Decimal("5"), trivial_threshold=Decimal("50000"),
    ))
    await world.db.flush()


async def test_preset_routes_list_resolve_and_unknown(world) -> None:
    user = (await world.member("edit", "auditor")).user
    await _materiality_row(world)
    async with world.client(custom_query.router, user=user) as client:
        listed = await client.get(f"{CQ}/template-presets")
        resolved = await client.get(
            f"{CQ}/template-presets/je_large_amount/resolve?project_id={X}&year=2025"
        )
        missing = await client.get(f"{CQ}/template-presets/no_such/resolve?project_id={X}&year=2025")
    assert listed.status_code == 200 and len(listed.json()["presets"]) == 10
    assert resolved.status_code == 200, resolved.text
    body = resolved.json()
    assert body["config"]["conditions"][0]["value"] == "800000.00"
    assert body["params"][0]["basis"].endswith("800,000.00 元")
    assert (missing.status_code, missing.json()["detail"]["error_code"]) == (404, "TEMPLATE_PRESET_NOT_FOUND")


async def test_user_template_resolve_rebinds_target_project_parameters(world) -> None:
    user = (await world.member("edit", "auditor")).user
    await _materiality_row(world, amount=Decimal("600000"))
    template = CustomQueryTemplate(
        id=uuid.uuid4(), name="【测试】参数模板", data_source="ledger_entries", scope="private",
        config={"source": "ledger_entries", "conditions": [{
            "field": "line_amount", "op": "gte", "value": {"$param": "materiality_performance"},
        }]}, creator_id=user.id, created_by=user.id,
    )
    world.db.add(template)
    await world.db.flush()
    async with world.client(custom_query.router, user=user) as client:
        response = await client.get(f"{CQ}/templates/{template.id}/resolve?project_id={X}&year=2025")
    assert response.status_code == 200, response.text
    condition = response.json()["config"]["conditions"][0]
    assert condition == {
        "field": "line_amount", "op": "gte", "value": "600000.00",
        "params": ["materiality_performance"],
    }


@pytest.mark.parametrize("method", ["post", "put"])
async def test_unregistered_param_cannot_be_saved_or_updated(world, method: str) -> None:
    user = await world.user(UserRole.auditor)
    bad_config = {"source": "ledger_entries", "conditions": [{
        "field": "line_amount", "op": "gte", "value": {"$param": "not_registered"},
    }]}
    async with world.client(custom_query.router, user=user) as client:
        if method == "post":
            response = await client.post(f"{CQ}/templates", json={
                "name": "【测试】坏参数", "data_source": "ledger_entries",
                "scope": "private", "config": bad_config,
            })
        else:
            template = CustomQueryTemplate(
                id=uuid.uuid4(), name="【测试】已有模板", data_source="ledger_entries", scope="private",
                config={"source": "ledger_entries"}, creator_id=user.id, created_by=user.id,
            )
            world.db.add(template)
            await world.db.flush()
            response = await client.put(f"{CQ}/templates/{template.id}", json={"config": bad_config})
    assert response.status_code == 400
    assert response.json()["detail"] == {
        "error_code": "TEMPLATE_INVALID", "message": "模板参数「not_registered」未登记",
    }
