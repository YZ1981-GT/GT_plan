"""传播状态接口（spec formula-management-repair-closure R1.3）。

SQLite 真 ORM：直接写 outbox / 死信行，经服务与端点（生产鉴权链）读取。
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.database import get_db
from app.deps import get_current_user
from app.models.audit_platform_schemas import EventType
from app.models.dataset_models import EventOutboxDLQ, ImportEventConsumption, ImportEventOutbox, OutboxStatus
from app.routers import formula_settings as fs_router
from app.services.formula_settings.outbox import ORIGIN
from app.services.formula_settings.propagation_status import propagation_status

from ._env import add_member, add_project, add_user, make_db

OUTBOX_MODELS = (ImportEventOutbox, ImportEventConsumption, EventOutboxDLQ)
T0 = datetime(2026, 11, 3, 8, 0, tzinfo=timezone.utc)


def _row(pid, *, status, minutes, domain="report", origin=ORIGIN, attempts=0, error=None,
         event_type=EventType.FORMULA_CONFIG_CHANGED.value):
    return ImportEventOutbox(
        id=uuid.uuid4(), event_type=event_type, project_id=pid,
        payload={"origin": origin, "domain": domain, "slot_keys": ["balance_sheet:BS-001", "balance_sheet:BS-002"],
                 "source": "global_publish"},
        status=status, attempt_count=attempts, last_error=error, created_at=T0 + timedelta(minutes=minutes),
        published_at=(T0 + timedelta(minutes=minutes, seconds=5)) if status == OutboxStatus.published else None,
    )


async def _seed(db, pid, other):
    db.add_all([
        _row(pid, status=OutboxStatus.published, minutes=1),
        _row(pid, status=OutboxStatus.published, minutes=2, domain="wp"),
        _row(pid, status=OutboxStatus.pending, minutes=3, domain="note"),
        _row(pid, status=OutboxStatus.failed, minutes=4, attempts=2, error="报表重算失败（过期标记已保留，将自动重试）：注入"),
        _row(pid, status=OutboxStatus.failed, minutes=5, domain="cross_check", attempts=20, error="表间审核重跑失败"),
        # 非本域：旧发布方的公式事件（origin 不同）、别的事件类型、别的项目 —— 都不计入
        _row(pid, status=OutboxStatus.failed, minutes=6, origin="formula_settings", attempts=1, error="旧路径"),
        _row(pid, status=OutboxStatus.failed, minutes=7, event_type=EventType.WORKPAPER_SAVED.value, attempts=1),
        _row(other, status=OutboxStatus.failed, minutes=8, attempts=1, error="别的项目"),
    ])
    db.add_all([
        EventOutboxDLQ(id=uuid.uuid4(), event_type=EventType.FORMULA_CONFIG_CHANGED.value, project_id=pid,
                       payload={"origin": ORIGIN, "domain": "cross_check"}, failure_reason="表间审核重跑失败",
                       attempt_count=20),
        EventOutboxDLQ(id=uuid.uuid4(), event_type=EventType.FORMULA_CONFIG_CHANGED.value, project_id=pid,
                       payload={"origin": ORIGIN, "domain": "report"}, failure_reason="已处理",
                       attempt_count=20, resolved_at=T0),
        EventOutboxDLQ(id=uuid.uuid4(), event_type=EventType.FORMULA_CONFIG_CHANGED.value, project_id=pid,
                       payload={"origin": "formula_settings"}, failure_reason="旧路径", attempt_count=20),
    ])
    await db.flush()


async def test_status_counts_only_this_projects_formula_outbox_rows():
    async with make_db(extra_models=OUTBOX_MODELS) as factory:
        async with factory() as db:
            pid, other = await add_project(db, "传播状态"), await add_project(db, "别的项目")
            await _seed(db, pid, other)
            await db.commit()
            out = await propagation_status(db, pid, max_attempts=20)
    assert out["counts"] == {"pending": 1, "failed": 2, "published": 2}
    assert (out["state"], out["retrying"], out["gave_up"], out["dead_letter"]) == ("failed", 1, 1, 1)
    assert out["last_published_at"].startswith("2026-11-03T08:02:05")
    failures = out["recent_failures"]
    assert [f["domain"] for f in failures] == ["cross_check", "report"]  # 新的在前
    assert failures[0] == {**failures[0], "domain_label": "表间审核", "attempt_count": 20, "gave_up": True,
                           "last_error": "表间审核重跑失败", "slot_count": 2, "source": "global_publish"}
    assert failures[1]["gave_up"] is False and "将自动重试" in failures[1]["last_error"]


@pytest.mark.parametrize("statuses, state", [
    ([], "idle"),
    ([OutboxStatus.published], "idle"),
    ([OutboxStatus.published, OutboxStatus.pending], "running"),
    ([OutboxStatus.pending, OutboxStatus.failed], "failed"),
])
async def test_overall_state(statuses, state):
    async with make_db(extra_models=OUTBOX_MODELS) as factory:
        async with factory() as db:
            pid = await add_project(db, "状态")
            db.add_all([_row(pid, status=s, minutes=i, attempts=1) for i, s in enumerate(statuses)])
            await db.commit()
            assert (await propagation_status(db, pid, max_attempts=20))["state"] == state


@pytest_asyncio.fixture
async def api():
    async with make_db(extra_models=OUTBOX_MODELS) as factory:
        async with factory() as db:
            pid = await add_project(db, "鉴权")
            users = {n: await add_user(db, n, "auditor") for n in ("reader", "outsider")}
            await add_member(db, pid, users["reader"], "readonly")
            db.add(_row(pid, status=OutboxStatus.failed, minutes=1, attempts=1, error="注入"))
            await db.commit()
        app = FastAPI()
        app.include_router(fs_router.project_router)
        who: dict = {"u": None}

        async def _db():
            async with factory() as s:
                yield s

        async def _user():
            if who["u"] is None:
                from fastapi import HTTPException

                raise HTTPException(status_code=401, detail="未登录")
            return who["u"]

        app.dependency_overrides[get_db] = _db
        app.dependency_overrides[get_current_user] = _user
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
            yield {"c": client, "pid": pid, "as": lambda n: who.update(u=users[n] if n else None)}


async def test_endpoint_requires_project_membership(api):
    path = f"/api/projects/{api['pid']}/formula-settings/propagation"
    api["as"](None)
    assert (await api["c"].get(path)).status_code == 401
    api["as"]("outsider")
    assert (await api["c"].get(path)).status_code == 403
    api["as"]("reader")
    r = await api["c"].get(path)
    assert r.status_code == 200, r.text
    assert (r.json()["state"], r.json()["counts"]["failed"]) == ("failed", 1)
