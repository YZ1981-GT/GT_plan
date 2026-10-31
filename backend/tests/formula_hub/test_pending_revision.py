"""待确认事项修订号（spec formula-hub-integrity-closure 需求 8.1、8.2；ADR-FHIC-11；D10；F14；变异 #31）。

生产函数一律不 mock；场景用试算表明细域（``tb_detail``，两层都在 ``formula_setting``、作用范围 ``*``）：
来源项目甲、乙各有本项目适配，目标项目有自己的改动 ⇒ 其他项目推送过来是冲突、交目标项目确认。

一、SQLite（``tests/formula_settings/_env`` 真 ORM）
   1. ``upsert_pending`` 直调：新建修订号 1，每次覆盖 +1 且是同一行；覆盖只换上游 / 上游版本 / 本项目当前 / 发布记录 /
      来源，基线与原因不变，标签为空不覆盖；同会话先前读到的对象随 RETURNING 刷新；已结案后再写入是新的一行、从 1 起。
   2. 三种来源（全局发布 / 模板新版本 / 其他项目推送）经生产路径建出并覆盖待确认：修订号 1 → 2，列表输出带修订号。
   3. F14 三步回归：甲推送 ⇒ 待确认（上游版本恒为空）→ 乙再推送原地覆盖（修订号 2，上游版本仍为空，只比上游版本
      看不出变化）→ 拿第 1 步列表里的修订号「采用新定义」⇒ 409，目标定义、待确认项、审计都不变；用新修订号处理才生效，
      采用的是第 2 步的定义。
   4. 缺修订号 ⇒ 428；同批另一条带了修订号也整体拒绝、不写入。
二、真 PG（``pg_only``；TestClient 按生产注册只挂 ``formula_settings.project_router``，只替换身份与会话，鉴权链真实运行；
   ``pg_tx`` 会话建在 TestClient 的事件循环线程里，用例结束回滚）：同一 F14 场景经端点 —— 列表带 ``revision``；
   缺 ⇒ 428 ``FORMULA_VERSION_REQUIRED``，旧修订号 ⇒ 409 ``FORMULA_SYNC_ITEM_STALE``（detail 带当前与回传的修订号），
   两次拒绝前后三个项目的 ``formula_sync_item`` / ``formula_setting`` 行逐行不变、不发变更事件；新修订号 ⇒ 200。
"""
from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

import pytest
import sqlalchemy as sa
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text

import app.routers.formula_settings as formula_settings_router
from app.core.database import get_db
from app.deps import get_current_user
from app.models.base import PermissionLevel, ProjectUserRole, UserRole
from app.models.core import Project, ProjectUser, User
from app.models.formula_setting_models import FormulaSyncItem
from app.services.formula_settings import apply_ops, project_ops
from app.services.formula_settings import template_service as tpl_service
from app.services.formula_settings import template_sync
from app.services.formula_settings.definitions import display_formula
from app.services.formula_settings.engine import Decisions
from app.services.formula_settings.errors import SyncItemStale, VersionRequired
from app.services.formula_settings.pending import close_pending, item_to_dict, upsert_pending
from app.services.formula_settings.publish import publish_global
from app.services.formula_settings.stores import get_store
from app.services.formula_settings.template_access import Viewer
from tests.authz_world import ServiceStub, _assert_stubbable, assert_gates_are_production, assert_world_overrides, build_app
from tests.formula_hub._pg_harness import TEST_PROJECT_PREFIX, pg_tx_session

DOMAIN, SLOT, LABEL = "tb_detail", "FH-T6-1001", "库存现金"
DEF_A = {"formula": "TB('1001','期末余额')", "formula_category": "auto_calc"}
DEF_B = {"formula": "TB('1001','期末余额')*2", "formula_category": "auto_calc"}
MINE = {"formula": "TB('1001','审定数')", "formula_category": "auto_calc"}


# ─── 场景（SQLite / PG 同一份写法） ──────────────────────────────────────────


@dataclass(frozen=True)
class Scenario:
    src_a: uuid.UUID
    src_b: uuid.UUID
    target: uuid.UUID

    @property
    def projects(self) -> list[uuid.UUID]:
        return [self.src_a, self.src_b, self.target]


async def _project(session, label: str) -> uuid.UUID:
    project = Project(name=f"{TEST_PROJECT_PREFIX}fh_t6_{label}_{uuid.uuid4().hex[:8]}",
                      client_name=f"{TEST_PROJECT_PREFIX}待确认修订号")
    session.add(project)
    await session.flush()
    return project.id


async def _write_local(session, project_id: uuid.UUID, definition: dict, slot: str = SLOT) -> None:
    await get_store(DOMAIN).write_project(session, project_id, slot, definition=definition, base_definition=None,
                                          base_version=None, pinned=False, base_origin=None, base_template_id=None,
                                          user_id=None, label=LABEL)


async def seed_scenario(session) -> Scenario:
    """甲、乙、目标三个项目，各有本项目适配（甲 = DEF_A、乙 = DEF_B、目标 = MINE）。"""
    scenario = Scenario(*[await _project(session, key) for key in ("src_a", "src_b", "target")])
    for project_id, definition in zip(scenario.projects, (DEF_A, DEF_B, MINE)):
        await _write_local(session, project_id, definition)
    await session.commit()
    return scenario


async def push(session, scenario: Scenario, source: uuid.UUID) -> None:
    """来源项目把 SLOT 推到目标项目（生产 ``apply_to_projects``；冲突默认交目标项目确认）。"""
    await apply_ops.apply_to_projects(session, domain=DOMAIN, project_id=source, slot_keys=[SLOT],
                                      target_ids=[scenario.target], decisions=Decisions(), user_id=None)
    await session.commit()


async def _local_formula(session, project_id: uuid.UUID) -> str | None:
    record = (await get_store(DOMAIN).list_project(session, project_id)).get(SLOT)
    return (record.definition or {}).get("formula") if record is not None else None


async def _listed(session, project_id: uuid.UUID) -> list[dict[str, Any]]:
    """列表输出（与 GET pending 同一个 ``item_to_dict``），读之前刷新会话里的旧对象。"""
    rows = (await session.execute(sa.select(FormulaSyncItem).where(
        FormulaSyncItem.project_id == project_id, FormulaSyncItem.status == "pending",
    ).order_by(FormulaSyncItem.slot_key), execution_options={"populate_existing": True})).scalars().all()
    return [item_to_dict(r) for r in rows]


# ─── 一、SQLite ─────────────────────────────────────────────────────────────


def _sqlite_db():
    from tests.formula_settings._env import make_db

    return make_db()


async def test_upsert_pending_revision_and_preserved_fields() -> None:
    async with _sqlite_db() as factory, factory() as db:
        pid = await _project(db, "target")
        key = dict(project_id=pid, domain=DOMAIN, slot_key=SLOT)
        first = await upsert_pending(db, **key, slot_label=LABEL, reason="conflict", base_definition=MINE,
                                     upstream_definition=DEF_A, upstream_version=None, local_definition=MINE,
                                     publish_id=None, upstream_origin="project")
        first_id = first.id
        assert first.revision == 1 and item_to_dict(first)["revision"] == 1
        publish_id, template_id = uuid.uuid4(), uuid.uuid4()
        second = await upsert_pending(db, **key, slot_label="", reason="deferred", base_definition=DEF_B,
                                      upstream_definition=DEF_B, upstream_version=7, local_definition=DEF_A,
                                      publish_id=publish_id, upstream_origin="template",
                                      upstream_template_id=template_id)
        assert second is first, "同会话先前读到的同一行对象随 RETURNING 刷新"
        assert (second.id, second.revision) == (first_id, 2)
        assert (second.reason, second.base_definition, second.slot_label) == ("conflict", MINE, LABEL), \
            "覆盖保留原因、基线；标签为空不覆盖"
        assert (second.upstream_definition, second.upstream_version, second.local_definition) == (DEF_B, 7, DEF_A)
        assert (second.publish_id, second.upstream_origin, second.upstream_template_id) == (
            publish_id, "template", template_id)
        third = await upsert_pending(db, **key, slot_label="现金", reason="conflict", base_definition=None,
                                     upstream_definition=None, upstream_version=None, local_definition=MINE,
                                     publish_id=None, upstream_origin="global")
        await db.commit()
        assert (third.id, third.revision, third.slot_label, third.upstream_definition) == (first_id, 3, "现金", None)
        (listed,) = await _listed(db, pid)
        assert (listed["id"], listed["revision"], listed["upstream_deleted"]) == (str(first_id), 3, True)

        await close_pending(db, pid, DOMAIN, [SLOT], status="resolved", resolution="keep")
        fresh = await upsert_pending(db, **key, slot_label=LABEL, reason="conflict", base_definition=None,
                                     upstream_definition=DEF_A, upstream_version=None, local_definition=MINE,
                                     publish_id=None, upstream_origin="project")
        await db.commit()
        assert fresh.id != first_id and fresh.revision == 1, "已结案的事项不再被覆盖：新的一行、修订号从 1 起"
        rows = (await db.execute(sa.select(FormulaSyncItem.status, FormulaSyncItem.revision).where(
            FormulaSyncItem.project_id == pid).order_by(FormulaSyncItem.revision))).all()
        assert [tuple(r) for r in rows] == [("pending", 1), ("resolved", 3)]


@pytest.mark.parametrize("origin", ["global", "template", "project"])
async def test_three_origins_create_at_one_and_overwrite_to_two(origin: str) -> None:
    """全局发布 / 模板新版本 / 其他项目推送：建出待确认修订号 1，再来一次覆盖为 2（同一行），列表输出带修订号。"""
    from tests.formula_settings._env import add_user

    async with _sqlite_db() as factory, factory() as db:
        admin = await add_user(db, "adm", "admin")
        scenario = await seed_scenario(db)
        target, tpl = scenario.target, None
        if origin == "template":
            tpl = await tpl_service.create_template(
                db, viewer=await Viewer.load(db, admin), name="现金口径", description=None, share_scope="firm",
                owner_project_id=None, applicable_scope="*", source="project", domains=[DOMAIN],
                source_project_id=scenario.src_a)

        async def upstream_changes(step: int) -> None:
            definition = DEF_A if step == 1 else DEF_B
            if origin == "global":
                change = {"slot_key": SLOT, "definition": definition} | ({"expected_version": 1} if step == 2 else {})
                await publish_global(db, domain=DOMAIN, scope="*", user_id=admin.id, changes=[change])
            elif origin == "template" and step == 1:  # 订阅：模板（= 甲的定义）与目标项目的改动冲突
                await template_sync.subscribe(db, project_id=target, tpl=tpl, domain=DOMAIN, decisions=None,
                                              user_id=admin.id)
            elif origin == "template":
                await template_sync.publish_template(db, tpl, expected_version=1, user_id=admin.id, changes=[
                    {"domain": DOMAIN, "slot_key": SLOT, "definition": definition}])
            else:
                await push(db, scenario, scenario.src_a if step == 1 else scenario.src_b)
            await db.commit()

        await upstream_changes(1)
        (one,) = await _listed(db, target)
        await upstream_changes(2)
        (two,) = await _listed(db, target)
    assert (one["upstream_origin"], one["revision"], one["upstream_formula"]) == (
        origin, 1, display_formula(DOMAIN, DEF_A))
    assert (two["id"], two["upstream_origin"], two["revision"], two["upstream_formula"]) == (
        one["id"], origin, 2, display_formula(DOMAIN, DEF_B))


async def test_f14_three_step_regression() -> None:
    from tests.formula_settings._env import audit_actions

    async with _sqlite_db() as factory, factory() as db:
        scenario = await seed_scenario(db)
        # 第 1 步：甲推送 ⇒ 目标项目待确认；目标成员打开弹窗看到的列表
        await push(db, scenario, scenario.src_a)
        (seen,) = await _listed(db, scenario.target)
        assert (seen["upstream_origin"], seen["upstream_version"], seen["revision"]) == ("project", None, 1)
        # 第 2 步：乙再推送 ⇒ 同一事项原地覆盖：上游版本仍为空（只比上游版本看不出变化），修订号 +1
        await push(db, scenario, scenario.src_b)
        (now,) = await _listed(db, scenario.target)
        assert (now["id"], now["upstream_version"], now["revision"], now["upstream_formula"]) == (
            seen["id"], None, 2, display_formula(DOMAIN, DEF_B))
        audits = await audit_actions(db)
        # 第 3 步：拿第 1 步看到的修订号「采用新定义」⇒ 409，什么都不写（核对先于任何写入，不靠回滚）
        with pytest.raises(SyncItemStale) as stale:
            await project_ops.resolve_items(db, project_id=scenario.target, user_id=None, resolutions=[
                {"item_id": seen["id"], "choice": "adopt", "revision": seen["revision"]}])
        assert stale.value.status_code == 409
        assert (stale.value.detail["revision"], stale.value.detail["expected_revision"]) == (2, 1)
        assert await _local_formula(db, scenario.target) == MINE["formula"], "目标项目定义不变"
        assert await _listed(db, scenario.target) == [now] and await audit_actions(db) == audits
        await db.rollback()
        # 用列表里的新修订号处理：采用的是第 2 步（乙）的定义
        out = await project_ops.resolve_items(db, project_id=scenario.target, user_id=None, resolutions=[
            {"item_id": now["id"], "choice": "adopt", "revision": now["revision"]}])
        await db.commit()
        assert out["resolved"] == [now["id"]] and await _listed(db, scenario.target) == []
        assert await _local_formula(db, scenario.target) == DEF_B["formula"]


async def test_missing_revision_is_428_and_nothing_written() -> None:
    async with _sqlite_db() as factory, factory() as db:
        scenario = await seed_scenario(db)
        await _write_local(db, scenario.src_a, DEF_A, slot=f"{SLOT}-2")
        await _write_local(db, scenario.target, MINE, slot=f"{SLOT}-2")
        await db.commit()
        await apply_ops.apply_to_projects(db, domain=DOMAIN, project_id=scenario.src_a, slot_keys=[SLOT, f"{SLOT}-2"],
                                          target_ids=[scenario.target], decisions=Decisions(), user_id=None)
        await db.commit()
        listed = await _listed(db, scenario.target)
        assert [i["revision"] for i in listed] == [1, 1]
        with_revision, without = listed
        with pytest.raises(VersionRequired) as required:
            await project_ops.resolve_items(db, project_id=scenario.target, user_id=None, resolutions=[
                {"item_id": with_revision["id"], "choice": "adopt", "revision": with_revision["revision"]},
                {"item_id": without["id"], "choice": "adopt"}])
        assert required.value.status_code == 428 and required.value.detail["item_ids"] == [without["id"]]
        assert await _listed(db, scenario.target) == listed
        assert await _local_formula(db, scenario.target) == MINE["formula"]


# ─── 二、真 PG：端点合同 ─────────────────────────────────────────────────────


@contextmanager
def _endpoint() -> Iterator[tuple[TestClient, Any, FastAPI]]:
    api = build_app(formula_settings_router.project_router)
    with TestClient(api) as client:
        with client.portal.wrap_async_context_manager(pg_tx_session()) as session:
            async def _db():
                yield session

            api.dependency_overrides[get_db] = _db
            yield client, session, api


async def _add_editor(session, project_id: uuid.UUID) -> User:
    tag = uuid.uuid4().hex[:8]
    user = User(username=f"fh_t6_editor_{tag}", email=f"fh_t6_editor_{tag}@example.test", hashed_password="x",
                role=UserRole.auditor, is_active=True)
    session.add(user)
    await session.flush()
    session.add(ProjectUser(project_id=project_id, user_id=user.id, role=ProjectUserRole.auditor,
                            permission_level=PermissionLevel.edit))
    await session.commit()
    return user


async def _rows_state(session, scenario: Scenario) -> dict[str, str]:
    """三个项目的 formula_sync_item / formula_setting 行（``row_to_json`` 按 id 排序），同一外层事务内读。"""
    state = {}
    for table in ("formula_sync_item", "formula_setting"):
        state[table] = (await session.execute(text(
            f"SELECT coalesce(json_agg(row_to_json(t) ORDER BY t.id)::text, '[]') FROM {table} t "
            "WHERE t.project_id = ANY(:pids)"), {"pids": scenario.projects})).scalar_one()
    return state


@pytest.mark.pg_only
def test_resolve_endpoint_revision_contract_pg(monkeypatch: pytest.MonkeyPatch) -> None:
    _assert_stubbable(formula_settings_router, "publish_events")
    events = ServiceStub(target="app.routers.formula_settings.publish_events", returns=0)
    monkeypatch.setattr(formula_settings_router, "publish_events", events)
    with _endpoint() as (client, session, api):
        def call(fn, *args):
            return client.portal.call(fn, session, *args)

        scenario = call(seed_scenario)
        editor_id = call(_add_editor, scenario.target).id

        async def _user() -> User:
            # 被拒请求在路由里回滚（只回滚到保存点）会让会话里的对象过期：每个请求重读身份
            return await session.get(User, editor_id)

        api.dependency_overrides[get_current_user] = _user
        assert_world_overrides(api)
        assert_gates_are_production()
        base = f"/api/projects/{scenario.target}/formula-settings/pending"
        # 第 1 步：甲推送；目标成员拉到的列表带修订号 1（上游版本为空）
        call(push, scenario, scenario.src_a)
        seen = client.get(base).json()["items"]
        assert [(i["upstream_origin"], i["upstream_version"], i["revision"]) for i in seen] == [("project", None, 1)]
        # 第 2 步：乙再推送，原地覆盖
        call(push, scenario, scenario.src_b)
        before = call(_rows_state, scenario)
        # 缺修订号 ⇒ 428；第 3 步：第 1 步的修订号 ⇒ 409（detail 带当前与回传的修订号）
        missing = client.post(f"{base}/resolve", json={"resolutions": [{"item_id": seen[0]["id"], "choice": "adopt"}]})
        assert (missing.status_code, missing.json()["detail"]["error_code"]) == (428, "FORMULA_VERSION_REQUIRED"), \
            missing.text
        stale = client.post(f"{base}/resolve", json={"resolutions": [
            {"item_id": seen[0]["id"], "choice": "adopt", "revision": seen[0]["revision"]}]})
        assert stale.status_code == 409, stale.text
        detail = stale.json()["detail"]
        assert (detail["error_code"], detail["revision"], detail["expected_revision"]) == (
            "FORMULA_SYNC_ITEM_STALE", 2, 1), stale.text
        assert call(_rows_state, scenario) == before, "拒绝的两次请求改了待确认项或定义"
        assert events.count == 0, "拒绝的请求发了变更事件"
        # 重新拉取：同一事项、修订号 2、新定义是乙的；用它处理才生效
        current = client.get(base).json()["items"]
        assert [(i["id"], i["revision"], i["upstream_formula"]) for i in current] == [
            (seen[0]["id"], 2, display_formula(DOMAIN, DEF_B))]
        ok = client.post(f"{base}/resolve", json={"resolutions": [
            {"item_id": current[0]["id"], "choice": "adopt", "revision": current[0]["revision"]}]})
        assert ok.status_code == 200, ok.text
        assert (ok.json()["resolved"], ok.json()["recalc_domains"]) == ([seen[0]["id"]], [DOMAIN])
        assert (call(_local_formula, scenario.target), call(_listed, scenario.target), events.count) == (
            DEF_B["formula"], [], 1)
