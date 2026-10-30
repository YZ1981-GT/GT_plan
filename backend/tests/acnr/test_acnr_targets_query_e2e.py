"""acnr_targets 三个入口的端到端（acnr-foundation-defect-closure T15，design §2.2 / §2.3 / §2.8；pg_only）。

真 PG：一个外层事务里建【测试】项目、E1 底稿（``parsed_data.html_data`` 写 E1-14!C10=0.125、E1-14!B30=「结论文本」、
E1-15!C8=222，以及同 A1 的 E1-18!B20=11 与 E1-19!B20=22）、只有 ``checklist_responses`` 的 S15 程序表底稿，以及没有年度的另一个【测试】项目；会话以 SAVEPOINT 方式加入
（端点里的 commit 只释放保存点），结束整体回滚，不留数据。经生产注册的 router（``tests/authz_world.build_app``）用 httpx 真发
请求，只 override ``get_current_user`` 与 ``get_db``；Redis 换成独立的 fakeredis（不连本机 Redis、不留缓存）。

覆盖：业务视图 execute、模板执行、构建器 execute 三入口逐字段断言 §2.2；两张表同一 A1（目录里的 ``E1/E1-18/B20`` 与
``E1/E1-19/B20``）各取各值并带各自的 ``source.sheet_code``；文本格 ``text``；
表单底稿 ``value_in_form_storage``；未生成底稿 ``wp_missing``；顺序与重复逐项对应；构建器 ``/preview`` 只解析不取值、
``/export-excel`` 追加「单元格取值」工作表；权限矩阵（非成员合伙人、只有委派的经理、无关经理）两入口放行一致；缺年度且项目
无年度 ⇒ ``YEAR_REQUIRED``；不带 acnr_targets 的旧请求与带目标的响应除 ``acnr_results`` 外逐字段相等；模板存非法
acnr_targets ⇒ 422 不 500；拒绝时取数函数调用 0 次。
"""
from __future__ import annotations

import io
import uuid

import pytest
from openpyxl import load_workbook
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

import app.core.redis as core_redis
from app.models.base import ProjectStatus, UserRole
from app.models.core import Project
from app.models.custom_query_models import CustomQueryTemplate
from app.models.workpaper_models import WorkingPaper, WpIndex, WpSourceType
from app.routers import custom_query, query_builder
from app.services.acnr import wp_cell_target
from app.services.acnr.catalog import get_catalog
from tests.authz_world import AuthzWorld, build_app

pytestmark = pytest.mark.pg_only

_E1_14 = "货币资金分析表E1-14"
_E1_15 = get_catalog().sheets_by_addr_id["E1/E1-15"]["sheet_name"]
#: 目录里真实存在的同底稿同 A1 目标对（E1/E1-18/B20 与 E1/E1-19/B20），两张表写不同数值
_E1_18, _E1_19 = (get_catalog().sheets_by_addr_id[f"E1/E1-{n}"]["sheet_name"] for n in (18, 19))
_PAPERS = {"E1": {_E1_14: {"C10": "0.125", "B30": "结论文本"}, _E1_15: {"C8": "222"},
                  _E1_18: {"B20": "11"}, _E1_19: {"B20": "22"}}}
TARGETS = ["E1/E1-14/C10", "E1/E1-15/C8", "E1/E1-18/B20", "E1/E1-19/B20", "E1/E1-14/B30", "S15/S15/C12",
           "D2/D2-2/E100", "E1/E1-14/C10"]
#: (addr_id, state, value, text, reason_code, 实际读取的底稿)
EXPECTED = [
    ("E1/E1-14/C10", "ok", "0.125", "0.125", None, "E1"),
    ("E1/E1-15/C8", "ok", "222", "222", None, "E1"),
    ("E1/E1-18/B20", "ok", "11", "11", None, "E1"),
    ("E1/E1-19/B20", "ok", "22", "22", None, "E1"),
    ("E1/E1-14/B30", "text", None, "结论文本", "non_numeric", "E1"),
    ("S15/S15/C12", "missing", None, None, "value_in_form_storage", "S15"),
    ("D2/D2-2/E100", "missing", None, None, "wp_missing", "D2"),
    ("E1/E1-14/C10", "ok", "0.125", "0.125", None, "E1"),
]
BUSINESS = "/api/custom-query/execute"
BUILDER = "/api/query/execute"


class World:
    def __init__(self, aw: AuthzWorld, project_id: uuid.UUID, no_year_project_id: uuid.UUID, wp_ids: dict) -> None:
        self.aw, self.x, self.z, self.wp_ids = aw, str(project_id), str(no_year_project_id), wp_ids
        self.api = build_app(custom_query.router, query_builder.router)

    def client(self, user):
        return self.aw.client_for_app(self.api, user=user, replace_rls=False)


def _project(pid: uuid.UUID, name: str, year: int | None) -> Project:
    return Project(id=pid, name=name, client_name=name, status=ProjectStatus.execution, template_type="listed",
                   report_scope="standalone", audit_year=year, scenario="normal")


async def _paper(s: AsyncSession, pid: uuid.UUID, code: str, parsed: dict) -> uuid.UUID:
    idx = WpIndex(id=uuid.uuid4(), project_id=pid, wp_code=code, wp_name=f"【测试】{code}")
    s.add(idx)
    await s.flush()
    wp = WorkingPaper(id=uuid.uuid4(), project_id=pid, wp_index_id=idx.id, file_path=f"{code}.xlsx",
                      source_type=WpSourceType.template, parsed_data=parsed)
    s.add(wp)
    await s.flush()
    return wp.id


@pytest.fixture
async def world(monkeypatch):
    from app.core.config import settings

    engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
    try:
        async with engine.connect() as conn:
            outer = await conn.begin()
            try:
                async with AsyncSession(bind=conn, expire_on_commit=False,
                                        join_transaction_mode="create_savepoint") as s:
                    aw = AuthzWorld(s, monkeypatch)
                    monkeypatch.setattr(core_redis, "redis_client", aw.redis)
                    monkeypatch.setattr(core_redis, "_redis_client", aw.redis)
                    x, z = uuid.uuid4(), uuid.uuid4()
                    s.add(_project(x, "【测试】acnr_targets 端到端", 2025))
                    s.add(_project(z, "【测试】acnr_targets 无年度项目", None))
                    await s.flush()
                    ids = {"E1": await _paper(s, x, "E1", {"html_data": {k: {"cells": v}
                                                                         for k, v in _PAPERS["E1"].items()}}),
                           "S15": await _paper(s, x, "S15", {})}
                    await s.execute(text("INSERT INTO checklist_responses (project_id, wp_id, item_id, conclusion) "
                                         "VALUES (:p, :w, 'S15-step-1', '已执行')"), {"p": x, "w": ids["S15"]})
                    try:
                        yield World(aw, x, z, ids)
                    finally:
                        await aw.redis.aclose()
            finally:
                await outer.rollback()
    finally:
        await engine.dispose()


def _business(pid: str, targets=TARGETS, **extra) -> dict:
    return {"project_id": pid, "year": 2025, "source": "tb_detail", "acnr_targets": list(targets), **extra}


def _builder(pid: str | None, targets=TARGETS, **extra) -> dict:
    body = {"table": "trial_balance", "fields": ["standard_account_code"], "acnr_targets": list(targets), **extra}
    if pid is not None:
        body["project_id"] = pid
    return body


def _assert_block(world: World, block: dict) -> None:
    """design §2.2 逐字段：目录版本、年度、逐项状态 / 值 / 原文 / 原因码与来源，顺序与重复逐项对应。"""
    cat = get_catalog()
    assert block["registry_version"] == cat.registry_version and block["year"] == 2025
    assert len(block["items"]) == len(EXPECTED)
    for item, (addr, state, value, raw, code, bound) in zip(block["items"], EXPECTED, strict=True):
        cell = cat.cells_by_addr_id[addr]
        sheet = cat.sheets_by_addr_id[cell["parent_addr_id"]]
        assert (item["input"], item["addr_id"], item["state"], item["value"], item["text"], item["reason_code"]) == \
            (addr, addr, state, value, raw, code), item
        assert item["formula_ref"] == cell["formula_ref"]
        assert item["display_label"] and cell["cell_address"] in item["display_label"]
        assert (item["reason"] is None) == (code is None), item
        src = item["source"]
        assert (src["wp_code"], src["sheet_code"], src["cell"]) == (bound, sheet["sheet_code"], cell["cell_address"])
        if bound in world.wp_ids:
            assert src["wp_id"] == str(world.wp_ids[bound])
            assert src["jump_route"] and f"sheet={sheet['sheet_code']}" in src["jump_route"], src
        else:
            assert src["wp_id"] is None and src["jump_route"] is None


async def test_three_entries_return_the_same_block(world: World):
    admin = await world.aw.user(UserRole.admin)
    async with world.client(admin) as c:
        business = await c.post(BUSINESS, json=_business(world.x))
        builder = await c.post(BUILDER, json=_builder(world.x, year=2025))
        created = await c.post("/api/custom-query/templates", json={
            "name": "【测试】acnr_targets 模板", "data_source": "tb_detail", "scope": "public",
            "config": {"source": "tb_detail", "year": 2025, "acnr_targets": TARGETS}})
        assert created.status_code == 201, created.text
        template = await c.post(f"/api/custom-query/templates/{created.json()['id']}/execute",
                                json={"project_id": world.x})
    for resp in (business, builder, template):
        assert resp.status_code == 200, resp.text
        _assert_block(world, resp.json()["acnr_results"])
    assert business.json()["acnr_results"] == builder.json()["acnr_results"] == template.json()["acnr_results"]


async def test_two_sheets_same_a1_each_read_their_own(world: World):
    """同一底稿两张表的同一 A1：两个入口各取各的值、``source`` 指向各自的表（跨表取首个同 A1 格会打红）。"""
    pair = ["E1/E1-18/B20", "E1/E1-19/B20"]
    admin = await world.aw.user(UserRole.admin)
    async with world.client(admin) as c:
        got = [await c.post(BUSINESS, json=_business(world.x, targets=pair)),
               await c.post(BUILDER, json=_builder(world.x, targets=pair, year=2025))]
    for resp in got:
        assert resp.status_code == 200, resp.text
        assert [(i["addr_id"], i["value"], i["source"]["sheet_code"], i["source"]["cell"])
                for i in resp.json()["acnr_results"]["items"]] == [
            ("E1/E1-18/B20", "11", "E1-18", "B20"), ("E1/E1-19/B20", "22", "E1-19", "B20")]


async def test_builder_year_is_filled_from_project_and_required_when_unknown(world: World):
    admin = await world.aw.user(UserRole.admin)
    async with world.client(admin) as c:
        filled = await c.post(BUILDER, json=_builder(world.x))
        missing_year = await c.post(BUILDER, json=_builder(world.z))
        missing_project = await c.post(BUILDER, json=_builder(None))
    assert filled.status_code == 200, filled.text
    assert filled.json()["acnr_results"]["year"] == 2025
    assert missing_year.status_code == 422
    assert missing_year.json()["detail"] == {"error_code": "YEAR_REQUIRED", "message": "项目审计年度未知，请指定年度后再取值"}
    assert missing_project.status_code == 422
    assert missing_project.json()["detail"]["error_code"] == "PROJECT_REQUIRED"


async def test_requests_without_targets_are_unchanged(world: World):
    """不带 acnr_targets：响应没有 acnr_results 键，其余字段与带目标的同一查询逐字段相等。"""
    admin = await world.aw.user(UserRole.admin)
    async with world.client(admin) as c:
        plain_business = await c.post(BUSINESS, json=_business(world.x, targets=[]))
        with_business = await c.post(BUSINESS, json=_business(world.x))
        plain_builder = await c.post(BUILDER, json=_builder(world.x, targets=[], year=2025))
        with_builder = await c.post(BUILDER, json=_builder(world.x, year=2025))
    for plain, with_targets in ((plain_business, with_business), (plain_builder, with_builder)):
        assert plain.status_code == with_targets.status_code == 200
        a, b = plain.json(), with_targets.json()
        assert "acnr_results" not in a and "acnr_results" in b
        b.pop("acnr_results")
        a.pop("cache_hit", None)
        b.pop("cache_hit", None)
        assert a == b


async def test_values_are_read_fresh_even_on_cache_hit(world: World):
    """构建器同一查询第二次命中查询缓存（``X-Cache: HIT``），单元格取值仍现读：两次之间改库内值，命中的响应给新值。

    业务视图的同类判据在编排器单元测试 ``test_cache_hit_returns_cached_without_compute``（缓存命中仍现读取值）；
    端到端里业务视图缓存在本夹具下未命中（同键重复达阈值后仍为 cache_hit=False，缓存实现归 advanced-query），
    这里只断言两次都现读到当时的库内值。
    """
    admin = await world.aw.user(UserRole.admin)
    body_b, body_q = _business(world.x, targets=["E1/E1-14/C10"]), _builder(world.x, targets=["E1/E1-14/C10"], year=2025)
    async with world.client(admin) as c:
        first_b, first_q = await c.post(BUSINESS, json=body_b), await c.post(BUILDER, json=body_q)
        await world.aw.db.execute(text(
            "UPDATE working_paper SET parsed_data = jsonb_set(parsed_data, ARRAY['html_data', :s, 'cells', 'C10'], "
            "'\"0.5\"'::jsonb) WHERE id = :id"), {"s": _E1_14, "id": world.wp_ids["E1"]})
        second_b, second_q = await c.post(BUSINESS, json=body_b), await c.post(BUILDER, json=body_q)
    assert second_q.headers.get("X-Cache") == "HIT" and first_q.headers.get("X-Cache") is None
    for first, second in ((first_b, second_b), (first_q, second_q)):
        assert first.json()["acnr_results"]["items"][0]["value"] == "0.125"
        assert second.json()["acnr_results"]["items"][0]["value"] == "0.5"


async def test_preview_resolves_without_reading_and_export_appends_sheet(world: World, monkeypatch):
    calls = {"n": 0}
    real = wp_cell_target.resolve_wp_cell

    async def _counting(*args, **kwargs):
        calls["n"] += 1
        return await real(*args, **kwargs)

    monkeypatch.setattr(wp_cell_target, "resolve_wp_cell", _counting)
    admin = await world.aw.user(UserRole.admin)
    async with world.client(admin) as c:
        preview = await c.post("/api/query/preview", json=_builder(world.x, year=2025))
        assert calls["n"] == 0
        export = await c.post("/api/query/export-excel", json=_builder(world.x, year=2025))
    assert preview.status_code == 200, preview.text
    cat = get_catalog()
    assert [(i["input"], i["addr_id"], i["formula_ref"]) for i in preview.json()["acnr_resolved"]] == \
        [(a, a, cat.cells_by_addr_id[a]["formula_ref"]) for a in TARGETS]
    assert "acnr_results" not in preview.json()
    assert export.status_code == 200, export.text
    wb = load_workbook(io.BytesIO(export.content), read_only=True)
    assert "单元格取值" in wb.sheetnames
    rows = [list(r) for r in wb["单元格取值"].iter_rows(values_only=True)]
    assert rows[0] == ["中文名", "引用", "状态", "值", "原因"]
    assert [(r[1], r[2], r[3]) for r in rows[1:]] == [
        (cat.cells_by_addr_id[a]["formula_ref"], {"ok": "已取值", "text": "文本", "missing": "取不到"}[st],
         value if value is not None else raw)
        for a, st, value, raw, _code, _b in EXPECTED]
    assert calls["n"] > 0


@pytest.mark.parametrize("url,body_of", [(BUSINESS, _business), (BUILDER, lambda pid, t: _builder(pid, t, year=2025))])
async def test_rejection_is_422_with_chinese_issues_and_reads_nothing(world: World, monkeypatch, url, body_of):
    calls = {"n": 0}

    async def _never(*args, **kwargs):
        calls["n"] += 1
        raise AssertionError("拒绝时不得取数")

    monkeypatch.setattr(wp_cell_target, "resolve_wp_cell", _never)
    admin = await world.aw.user(UserRole.admin)
    async with world.client(admin) as c:
        resp = await c.post(url, json=body_of(world.x, ["E1/E1-14/C10", "E1/E1-14", "tb:1001"]))
    assert resp.status_code == 422, resp.text
    detail = resp.json()["detail"]
    assert detail["error_code"] == "ACNR_TARGETS_REJECTED"
    assert detail["message"] == "所选单元格中有 2 项无法取值，未执行查询"
    assert [(i["ref"], i["error_code"]) for i in detail["issues"]] == [
        ("E1/E1-14", "sheet_level"), ("tb:1001", "unsupported_domain")]
    assert all(i["message"] for i in detail["issues"])
    assert calls["n"] == 0


async def test_permission_matrix_is_the_same_for_both_entries(world: World):
    """非成员合伙人、只有委派的经理放行；无关经理 403——两入口的项目归属结论一致。

    「只有委派的经理」（没有成员行、只有一条委派）在两入口都过了项目归属；但 advanced-query-linkage-closure
    ADR-AQL-19（B6）起它是审计循环受限身份（平台口径：没有成员行 ⇒ 链路不唯一 ⇒ 受限）：业务视图按循环过滤后照常 200，
    构建器无法按循环过滤，按设计在显式指定项目时 403 ``CYCLE_SCOPED_PROJECT``（该口径另由 advanced_query_linkage
    配方表 23c / 25c / 26c / 28c 钉住）。B6 起本用例原先的 (200, 200) 断言一直红（KeyError: 'acnr_results'），
    按设计改为逐入口断言，归属一致性仍由「无关经理」两入口同为 403 ``FORBIDDEN_PROJECT`` 判定。
    """
    aw = world.aw
    partner = await aw.user(UserRole.partner)
    delegated = await aw.user(UserRole.manager)
    x_project = await aw.db.get(Project, uuid.UUID(world.x))
    await aw.eqcr_assignment("auditor", user=delegated, project=x_project)
    outsider = await aw.user(UserRole.manager)
    got = {}
    for label, user in (("非成员合伙人", partner), ("只有委派的经理", delegated), ("无关经理", outsider)):
        async with world.client(user) as c:
            b = await c.post(BUSINESS, json=_business(world.x, targets=["E1/E1-14/C10"]))
            q = await c.post(BUILDER, json=_builder(world.x, targets=["E1/E1-14/C10"], year=2025))
        got[label] = (b.status_code, q.status_code)
        if b.status_code == 200:
            assert b.json()["acnr_results"]["items"][0]["value"] == "0.125"
        if q.status_code == 200:
            assert q.json()["acnr_results"]["items"][0]["value"] == "0.125"
        if (b.status_code, q.status_code) == (403, 403):
            assert b.json()["detail"]["error_code"] == q.json()["detail"]["error_code"] == "FORBIDDEN_PROJECT"
        if label == "只有委派的经理":
            assert q.json()["detail"]["error_code"] == "CYCLE_SCOPED_PROJECT", q.text[:300]
    assert got == {"非成员合伙人": (200, 200), "只有委派的经理": (200, 403), "无关经理": (403, 403)}


async def test_template_with_illegal_targets_is_422_not_500(world: World):
    admin = await world.aw.user(UserRole.admin)
    stored = CustomQueryTemplate(
        id=uuid.uuid4(), name="【测试】acnr_targets 非法模板", data_source="tb_detail",
        config={"source": "tb_detail", "year": 2025, "acnr_targets": ["E1/E1-14/C10", "   "]},
        scope="private", shared_project_ids=[], creator_id=admin.id, created_by=admin.id)
    world.aw.db.add(stored)
    await world.aw.db.flush()
    async with world.client(admin) as c:
        save = await c.post("/api/custom-query/templates", json={
            "name": "【测试】acnr_targets 非法", "data_source": "tb_detail", "scope": "public",
            "config": {"source": "tb_detail", "year": 2025, "acnr_targets": ["E1/E1-14/C10", ""]}})
        too_many = await c.post("/api/custom-query/templates", json={
            "name": "【测试】acnr_targets 超量", "data_source": "tb_detail", "scope": "public",
            "config": {"source": "tb_detail", "year": 2025, "acnr_targets": ["E1/E1-14/C10"] * 51}})
        run = await c.post(f"/api/custom-query/templates/{stored.id}/execute", json={"project_id": world.x})
    assert save.status_code == 422, save.text
    assert "模板里的单元格取值目标不合法：第 2 个单元格引用为空" in save.text
    assert too_many.status_code == 422 and "单次最多选择 50 个单元格" in too_many.text
    assert run.status_code == 422, run.text
    assert run.json()["detail"]["error_code"] == "TEMPLATE_CONFIG_INVALID"
    assert "单元格取值目标：第 2 个单元格引用为空" in run.json()["detail"]["message"]
