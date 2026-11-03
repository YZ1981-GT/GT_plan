"""回写隔离与预览门的真 PG 回归（advanced-query-linkage-closure 任务 14；R4.1、R4.2、R4.5；变异 #11、#21、B4-b、B4-d）。

design §10.2 两行：
- 「回写不锁他项目行」：目标 = 活项目中 updated_at 最早的一张已提交底稿、【UAT】合成集团母公司的一条 consol_note_data。
  会话 A（回滚事务）以【UAT】子公司A 为请求项目直调写入方，分别得 ``WritebackTargetNotFound`` / ``NoteRecordNotFound``；
  A 的事务**未结束**时，会话 B 对目标行 ``SELECT … FOR UPDATE NOWAIT`` 必须成功（证明 A 既没读到也没锁住它）；
  两会话都回滚，目标行指纹（``md5(row_to_json(...))``）前后一致。先做 NOWAIT 再判异常类型：取行条件被改坏时红在
  「会话 A 锁住了他项目行（LockNotAvailable）」上，而不是只红在异常类型上。
- 「回写预览门」：同一底稿目标经 writeback-preview ⇒ 条目 ``target_not_in_project``（不解析地址、不读旧值）、
  ``enter_confirmation=false`` + 提示；writeback-confirm ⇒ 409 ``WRITEBACK_CONFLICT``，写入方（在类上替换的下一层）零调用。

另：cell-writeback module=tb ⇒ 422 且【UAT】子公司B 的试算行逐值不变（R4.1，design §10.2 的「UB 试算行不变」）；
writeback-confirm 的写入方异常按 cell-writeback 同口径映射、整批回滚（design §3.7：任一目标失败，一个都不写）。

请求经 httpx ASGI 真发到生产注册的 custom_query / custom_query_writeback router，只替换 ``get_current_user``（系统 admin）
与 ``get_db``（真库回滚事务会话）。真实项目只读（只读查询与 NOWAIT 加锁验证）；写入只在回滚事务里、只写【UAT】项目。
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import fakeredis
import fakeredis.aioredis
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

import app.core.redis as core_redis
from app.core.database import get_db
from app.deps import get_current_user
from app.models.base import UserRole
from app.models.core import User
from app.routers import custom_query, custom_query_writeback
from app.services.custom_query import addressing_service as addressing_module
from app.services.custom_query.addressing_service import AddressingService, ResolvedTarget
from app.services.custom_query.snapshot_writer import (
    SnapshotWriter,
    WritebackTargetNotFound,
    snapshot_writer,
)
from app.services.custom_query.snapshot_writer_modules import NoteRecordNotFound
from tests.advanced_query_linkage.gold import UA, UB, UP
from tests.authz_world import build_app, pg_engine

pytestmark = pytest.mark.pg_only
CQ = "/api/custom-query"
FUTURE = datetime.now(timezone.utc) + timedelta(days=1)  # 乐观锁不会碰巧给出 409
WRITER = SimpleNamespace(id=uuid.uuid4(), username="aql-b4-writer")
_WP_FINGERPRINT = "SELECT md5(row_to_json(w)::text) FROM working_paper w WHERE w.id = :id"
_NOTE_FINGERPRINT = "SELECT md5(row_to_json(c)::text) FROM consol_note_data c WHERE c.id = :id"
_TB_FINGERPRINT = (
    "SELECT count(*), md5(string_agg(id::text || ':' || coalesce(audited_amount::text, '') || ':' || "
    "coalesce(updated_at::text, ''), ',' ORDER BY id)) FROM trial_balance WHERE project_id = :pid"
)


@pytest.fixture(autouse=True)
def _singletons_have_no_instance_overrides():
    """本文件的桩一律打在类上；模块单例上若残留同名**实例属性**，类级替换会被挡住、调到真实实现。

    来源：前序用例对单例实例 ``monkeypatch.setattr``（方法本在类上），撤销时 monkeypatch 把原方法写回成实例属性。
    BM 时本文件 4 例排在 ``test_writeback_pbt.py`` 之后才红（advanced-query-linkage-closure B6 已在那边改为
    ``monkeypatch.setitem(vars(单例), …)``，撤销时删键）；这里先拦下并点名，不让它静默变成「调到真实 resolve_target」。
    """
    # 只守本文件真正依赖的类级替换（AddressingService.resolve_target、SnapshotWriter.write_cell）；audit_logger.log_action
    # 的同类残留另有来源（范围外的 ledger_import/test_upload_security.py），本文件不替换它、不受影响，登记在 B6 的 impl-progress
    leaked = [
        f"{type(obj).__name__}.{name}"
        for obj, name in ((addressing_module.addressing_service, "resolve_target"), (snapshot_writer, "write_cell"))
        if name in vars(obj)
    ]
    assert not leaked, (
        f"模块单例上残留实例属性 {leaked}：前序用例在单例实例上 monkeypatch.setattr 了方法、撤销时写回成实例属性，"
        "会挡住本文件的类级替换（单例的桩改用 monkeypatch.setitem(vars(单例), 方法名, 桩)，撤销时删键）"
    )
    yield


async def _foreign_workpaper(gold) -> tuple[uuid.UUID, str]:
    """活项目里 updated_at 最早的一张已提交底稿（不属于请求项目【UAT】子公司A）。"""
    rows = await gold.rows(
        "SELECT w.id, coalesce(i.wp_code, '') FROM working_paper w JOIN projects p ON p.id = w.project_id "
        "LEFT JOIN wp_index i ON i.id = w.wp_index_id "
        "WHERE NOT p.is_deleted AND NOT w.is_deleted AND w.project_id <> :ua "
        "ORDER BY w.updated_at ASC NULLS LAST, w.id LIMIT 1",
        ua=UA,
    )
    assert rows, "前置：活项目里应有已提交底稿"
    return rows[0][0], rows[0][1]


async def _foreign_note(gold) -> tuple[uuid.UUID, str, int, str | None]:
    rows = await gold.rows(
        "SELECT id, section_id, year, node_key FROM consol_note_data WHERE project_id = :up ORDER BY updated_at, id LIMIT 1",
        up=UP,
    )
    assert rows, "前置：【UAT】合成集团母公司应有 consol_note_data"
    return rows[0]


async def _nowait(table: str, row_id: uuid.UUID) -> None:
    """会话 B：对目标行 FOR UPDATE NOWAIT（被锁即失败、不等待），随即回滚。``table`` 只取本文件的固定值。"""
    engine = pg_engine()
    try:
        async with engine.connect() as conn:
            await conn.begin()
            try:
                await conn.execute(text(f"SELECT id FROM {table} WHERE id = :id FOR UPDATE NOWAIT"), {"id": row_id})
            except DBAPIError as exc:
                pytest.fail(f"会话 B 对 {table} 目标行 FOR UPDATE NOWAIT 失败——会话 A 锁住了他项目的行"
                            f"（LockNotAvailable）：{exc.orig!r}")
            finally:
                await conn.rollback()
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def client(pg_rollback_session, monkeypatch):
    redis = fakeredis.aioredis.FakeRedis(server=fakeredis.FakeServer(), decode_responses=True)
    monkeypatch.setattr(core_redis, "redis_client", redis)
    monkeypatch.setattr(core_redis, "_redis_client", redis)
    api = build_app(custom_query.router, custom_query_writeback.router)
    admin = User(id=uuid.uuid4(), username="aql-b4-admin", email="aql-b4@test.invalid", hashed_password="x",
                 role=UserRole.admin, is_active=True)

    async def _db():
        yield pg_rollback_session

    async def _user() -> User:
        return admin

    api.dependency_overrides[get_db] = _db
    api.dependency_overrides[get_current_user] = _user
    async with AsyncClient(transport=ASGITransport(app=api), base_url="http://aql-b4") as http:
        yield http
    await redis.aclose()


# ─── 回写不锁他项目行（R4.2；变异 #11、B4-b）──────────────────────────────────


async def test_workpaper_of_other_project_is_neither_read_nor_locked(pg_rollback_session, gold) -> None:
    wp_id, _ = await _foreign_workpaper(gold)
    before = await gold.scalar(_WP_FINGERPRINT, id=wp_id)
    raised: BaseException | None = None
    try:
        await snapshot_writer.write_cell(
            db=pg_rollback_session, user=WRITER, wp_id=str(wp_id), sheet_name="审定表", cell_ref="B7", new_value=1,
            opened_at=FUTURE, module="workpaper", project_id=str(UA),
        )
    except Exception as exc:  # 先验锁、再判类型（见模块说明）
        raised = exc
    await _nowait("working_paper", wp_id)  # 会话 A 的事务此刻仍未结束
    assert isinstance(raised, WritebackTargetNotFound), f"以【UAT】子公司A 定位他项目底稿应查不到，实得 {raised!r}"
    assert raised.message == "目标不存在或不属于本项目"
    assert await gold.scalar(_WP_FINGERPRINT, id=wp_id) == before


async def test_note_record_of_other_project_is_neither_read_nor_locked(pg_rollback_session, gold) -> None:
    note_id, section_id, year, node_key = await _foreign_note(gold)
    before = await gold.scalar(_NOTE_FINGERPRINT, id=note_id)
    raised: BaseException | None = None
    try:
        await snapshot_writer.write_cell(
            db=pg_rollback_session, user=WRITER, wp_id=str(note_id), sheet_name=f"note_{section_id}", cell_ref="C2",
            new_value=1, opened_at=FUTURE, module="note", note_record_id=str(note_id), note_section_id=section_id,
            note_year=year, note_node_key=node_key, note_project_id=str(UA),
        )
    except Exception as exc:
        raised = exc
    await _nowait("consol_note_data", note_id)
    assert isinstance(raised, NoteRecordNotFound), f"以【UAT】子公司A 定位合并集团的附注记录应查不到，实得 {raised!r}"
    assert await gold.scalar(_NOTE_FINGERPRINT, id=note_id) == before


# ─── 回写预览门（R4.5；变异 #21）──────────────────────────────────────────────


@pytest_asyncio.fixture
async def gate_spies(monkeypatch) -> dict[str, list]:
    """在类上替换预览门的下一层（地址解析恒能解析、写入方只记录），观测预览门有没有放行：他项目目标不该走到这两步。

    地址解析恒返回 found=True：没有归属核对时目标就会被当成「可定位」放进确认——不靠「地址恰好解析不到」碰巧挡住。
    """
    seen: dict[str, list] = {"resolved": [], "written": []}

    async def _resolve_spy(self, raw, *, project_id=None, db=None, timeout_s=5.0):
        seen["resolved"].append(raw)
        return ResolvedTarget(raw=raw, found=True, addr_id=f"ADDR/{raw}")

    async def _write_spy(self, **kwargs):
        seen["written"].append(kwargs)
        return {"success": True}

    monkeypatch.setattr(AddressingService, "resolve_target", _resolve_spy)
    monkeypatch.setattr(SnapshotWriter, "write_cell", _write_spy)
    return seen


def _other_project_target(wp_id: uuid.UUID, wp_code: str) -> dict:
    return {"project_id": str(UA), "targets": [{
        "module": "workpaper", "wp_id": str(wp_id), "wp_code": wp_code or "C1-1", "sheet_name": "审定表",
        "cell_ref": "B7", "new_value": 1,
    }]}


async def test_preview_endpoint_is_retired_without_touching_targets(client, gold, gate_spies) -> None:
    wp_id, wp_code = await _foreign_workpaper(gold)
    before = await gold.scalar(_WP_FINGERPRINT, id=wp_id)
    response = await client.post(f"{CQ}/writeback-preview", json=_other_project_target(wp_id, wp_code))
    assert response.status_code == 410, response.text[:800]
    assert response.json()["detail"]["error_code"] == "ADVANCED_QUERY_WRITEBACK_RETIRED"
    assert gate_spies == {"resolved": [], "written": []}
    assert await gold.scalar(_WP_FINGERPRINT, id=wp_id) == before


async def test_confirm_endpoint_is_retired_without_writing(client, gold, gate_spies) -> None:
    wp_id, wp_code = await _foreign_workpaper(gold)
    before = await gold.scalar(_WP_FINGERPRINT, id=wp_id)
    response = await client.post(f"{CQ}/writeback-confirm", json=_other_project_target(wp_id, wp_code))
    assert response.status_code == 410, response.text[:800]
    assert response.json()["detail"]["error_code"] == "ADVANCED_QUERY_WRITEBACK_RETIRED"
    assert gate_spies == {"resolved": [], "written": []}
    assert await gold.scalar(_WP_FINGERPRINT, id=wp_id) == before


# ─── 写入收窄（R4.1）：module=tb 422，试算行不变 ─────────────────────────────


async def test_cell_writeback_endpoint_is_retired_and_trial_balance_rows_unchanged(client, gold) -> None:
    before = await gold.rows(_TB_FINGERPRINT, pid=UB)
    response = await client.post(f"{CQ}/cell-writeback", json={"malformed": True})
    assert response.status_code == 410, response.text[:800]
    assert response.json()["detail"]["error_code"] == "ADVANCED_QUERY_WRITEBACK_RETIRED"
    assert await gold.rows(_TB_FINGERPRINT, pid=UB) == before


# ─── 退役桩不消费请求体 ────────────────────────────────────────────────────────


async def test_retired_confirm_ignores_large_or_invalid_payload(client) -> None:
    response = await client.post(f"{CQ}/writeback-confirm", json={
        "project_id": "not-a-uuid",
        "targets": [{"unexpected": "value"}] * 10_001,
    })
    assert response.status_code == 410, response.text[:800]
    assert response.json()["detail"]["error_code"] == "ADVANCED_QUERY_WRITEBACK_RETIRED"
