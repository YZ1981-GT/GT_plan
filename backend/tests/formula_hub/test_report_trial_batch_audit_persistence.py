"""报表试算批量的留痕在生产会话生命周期下能否落库（spec formula-hub-integrity-closure 第 2 轮 C3；交接
spec audit-log-chain-integrity，即 S10）。

S10 批 B（``12e28aa49``，ADR-ALC-07）把 ``execute_formulas_batch`` 的审计写法改为逐行 ``begin_nested`` + best_effort，
同时删掉了函数内的 ``commit``。本 spec 已把该函数体搬到 ``services/report_config_execute._audit``，按「后落地方只接线、
不改先落地方语义」照搬这一写法（调用点登记键随之改为 ``services/report_config_execute.py:_audit``）。生产 ``get_db``
只 yield 会话、不提交 ⇒ 请求结束会话关闭，这批留痕随之回滚：批量试算在公式历史页与审计链里都查不到。

只在真 PG 上有判别力：SQLite（pysqlite / aiosqlite）在没有外层事务时执行 ``SAVEPOINT`` 会自己开事务，最外层
``RELEASE`` 等于 ``COMMIT``，同一用例在 SQLite 上「落库」了（实测 XPASS），与生产 PG 的行为相反。

本用例按生产生命周期跑（快照库 ``committed_project`` 真提交的【测试】项目与用户）：每个请求一个新会话（与 ``get_db``
相同，只 yield 不提交），请求后另开会话查审计链。前置条件（请求 200、试算值正确、请求内 ``append_audit_log`` 确实写成
1 条）不成立时 ``pytest.fail``（不算本用例钉住的缺陷）；只有「请求结束后查不到」以 ``AssertionError`` 落进
``xfail(strict=True)``。S10 补上提交（端点或 ``_audit`` 自己提交）后本用例转为通过，strict 让它立刻打红，提醒删掉
xfail 标记并给落库的留痕补清理登记。
"""
from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa
from httpx import ASGITransport, AsyncClient

from app.core.database import get_db
from app.deps import get_current_user
from app.models.base import UserRole
from app.models.core import User
from tests.authz_world import assert_gates_are_production, assert_world_overrides, build_app

pytestmark = pytest.mark.pg_only


@pytest.mark.asyncio
@pytest.mark.xfail(strict=True, raises=AssertionError,
                   reason="S10 批 B 删了批量试算留痕的 commit，生产 get_db 不提交 ⇒ 留痕随会话关闭回滚；交接 S10")
async def test_batch_trial_run_audit_persists_after_request(committed_project, monkeypatch):
    from app.routers import report_config
    from app.services import audit_log_helper

    handle = committed_project
    tag = uuid.uuid4().hex[:10]
    admin = User(id=uuid.uuid4(), username=f"fh_batch_audit_{tag}", email=f"fh_batch_audit_{tag}@example.com",
                 hashed_password="x", role=UserRole.admin, is_active=True)
    await handle.add(admin)

    written: list[str] = []
    real_append = audit_log_helper.append_audit_log

    async def _spy(db, payload):  # 请求内是否真的写成功（不吞异常：失败照样抛，best_effort 由 _audit 自己兜）
        entry_id = await real_append(db, payload)
        written.append(payload["resource_id"])
        return entry_id

    monkeypatch.setattr(audit_log_helper, "append_audit_log", _spy)
    api = build_app(report_config.router)

    async def _db():  # 与生产 get_db 相同：每个请求一个会话，只 yield、不提交
        async with handle.session() as session:
            yield session

    async def _user() -> User:
        async with handle.session() as session:
            return await session.get(User, admin.id)

    api.dependency_overrides[get_db] = _db
    api.dependency_overrides[get_current_user] = _user
    assert_world_overrides(api)
    assert_gates_are_production()
    async with AsyncClient(transport=ASGITransport(app=api), base_url="http://fhic-batch-audit") as http:
        resp = await http.post("/api/report-config/execute-formulas-batch", json={
            "project_id": str(handle.project_id), "year": 2025,
            "formulas": [{"row_code": "BS-001", "formula": "100"}]})
    if resp.status_code != 200 or resp.json()["results"][0]["value"] != 100:
        pytest.fail(f"前置条件不成立（不是本用例钉住的缺陷）：{resp.status_code} {resp.text}")
    if written != ["BS-001"]:
        pytest.fail(f"前置条件不成立：请求内 append_audit_log 应恰好写成 1 条，实际 {written}")

    async with handle.engine.connect() as conn:
        persisted = (await conn.execute(sa.text(
            "SELECT count(*) FROM audit_log_entries WHERE object_type = 'report_config' "
            "AND payload->>'project_id' = :pid"), {"pid": str(handle.project_id)})).scalar_one()
    assert persisted == 1, f"批量试算留痕请求结束后查不到（会话未提交即关闭），落库 {persisted} 条"
