"""真实 PostgreSQL：提交复核 / 通过的状态变更与站内通知同一事务落库（spec adjustment-hall-entry-review-closure 需求 4.4、7.1）。

SQLite 用例看不出两件 PG 才有的事：①通知按真实表结构写入（varchar(50) 的类型、jsonb metadata、uuid 绑定）；
②一条通知写失败会让 PG 事务进入 aborted —— 所以每条通知各自一个 SAVEPOINT。本用例带反向对照：同样的坏数据
不经保存点直接 flush，后续语句确实报「current transaction is aborted」；对照不报说明判据空转。

隔离：同一连接上一个事务里新建【测试】项目、用户与分录，全部回滚；审计日志装饰器（独立会话写 logs 表）与
事件总线（ADJUSTMENT_CREATED 会触发别的会话做重算）替换成空操作，不在共享库留任何东西。
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
import sqlalchemy as sa

pytestmark = pytest.mark.pg_only

YEAR = 2025


async def _scenario() -> dict:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.database import engine
    from app.models.audit_platform_models import (
        AccountCategory, AccountChart, AccountDirection, AccountSource, AdjustmentType, ReviewStatus,
    )
    from app.models.audit_platform_schemas import AdjustmentCreate, AdjustmentLineItem
    from app.models.base import PermissionLevel, ProjectUserRole, UserRole
    from app.models.core import Notification, Project, ProjectStatus, ProjectType, ProjectUser, User
    from app.models.staff_models import ProjectAssignment, StaffMember
    from app.services import adjustment_hall_notify as notify
    from app.services import adjustment_review_service as review
    from app.services.adjustment_service import AdjustmentService

    out: dict = {}
    tag = uuid.uuid4().hex[:8]
    async with engine.connect() as conn:
        trans = await conn.begin()
        try:
            db = AsyncSession(bind=conn, expire_on_commit=False)
            project = Project(id=uuid.uuid4(), name=f"【测试】调整大厅通知PG_{tag}", client_name=f"【测试】调整大厅通知PG_{tag}",
                              project_type=ProjectType.annual, status=ProjectStatus.execution)
            db.add(project)
            users: dict[str, User] = {}
            for key, role, prole, level in [("prep", UserRole.auditor, "auditor", PermissionLevel.edit),
                                            ("rev", UserRole.manager, "manager", PermissionLevel.edit)]:
                u = User(id=uuid.uuid4(), username=f"t_adjpg_{key}_{tag}", email=f"t_adjpg_{key}_{tag}@t.com",
                         hashed_password="x", role=role)
                db.add(u)
                await db.flush()
                staff = StaffMember(id=uuid.uuid4(), user_id=u.id, name=f"测试{key}{tag}")
                db.add(staff)
                await db.flush()
                db.add(ProjectUser(id=uuid.uuid4(), project_id=project.id, user_id=u.id, permission_level=level,
                                   role=ProjectUserRole.manager if prole == "manager" else ProjectUserRole.auditor))
                db.add(ProjectAssignment(id=uuid.uuid4(), project_id=project.id, staff_id=staff.id, role=prole,
                                         assigned_at=date.today()))
                users[key] = u
            for code, name in [("1231", "坏账准备"), ("6702", "信用减值损失")]:
                db.add(AccountChart(project_id=project.id, account_code=code, account_name=name, level=1,
                                    direction=AccountDirection.debit, category=AccountCategory.asset,
                                    source=AccountSource.standard))
            await db.flush()
            entry = await AdjustmentService(db).create_entry(project.id, AdjustmentCreate(
                adjustment_type=AdjustmentType.aje, year=YEAR, description="补提坏账",
                line_items=[AdjustmentLineItem(standard_account_code="6702", debit_amount=Decimal("100")),
                            AdjustmentLineItem(standard_account_code="1231", credit_amount=Decimal("100"))],
            ), users["prep"].id)
            gid = entry.entry_group_id

            out["candidates"] = [c["user_id"] for c in await notify.review_candidates(db, project.id)]
            submitted = await review.submit_for_review(db, project.id, group_ids=[gid], actor=users["prep"])
            out["submitted"] = ([s["entry_group_id"] for s in submitted["succeeded"]], [n["user_id"] for n in submitted["notified"]])
            approved = await review.review_groups(db, project.id, group_ids=[gid], status=ReviewStatus.approved,
                                                  actor=users["rev"])
            out["approved_notified"] = [n["user_id"] for n in approved["notified"]]
            rows = (await db.execute(
                sa.select(Notification.recipient_id, Notification.message_type, Notification.notification_metadata)
                .where(Notification.recipient_id.in_([users["prep"].id, users["rev"].id]))
            )).all()
            # 同一事务内 now() 相同，按类型排序断言
            out["notifications"] = sorted((t, str(r), (m or {}).get("object_id"), (m or {}).get("year")) for r, t, m in rows)
            out["status"] = (await db.execute(sa.text(
                "SELECT DISTINCT review_status::text FROM adjustments WHERE entry_group_id = :g AND NOT is_deleted"
            ), {"g": gid})).scalars().all()

            # 坏数据（类型超 varchar(50)）经保存点写：失败只丢这一条，事务仍可用
            out["bad_sent"] = await notify.write_notifications(db, [users["prep"].id], "x" * 60, "t", "c",
                                                               {"object_id": str(gid)})
            out["after_bad"] = (await db.execute(sa.text("SELECT 1"))).scalar_one()

            out["ids"] = {k: str(u.id) for k, u in users.items()}
            out["gid"] = str(gid)

            # 反向对照：同样的坏数据不经保存点直接写，PG 事务进入 aborted，后续语句全被拒
            try:
                await conn.execute(sa.text(
                    "INSERT INTO notifications (id, recipient_id, message_type, title, is_read) "
                    "VALUES (:id, :r, :t, 't', false)"
                ), {"id": uuid.uuid4(), "r": users["prep"].id, "t": "x" * 60})
                out["control"] = "坏数据居然写进去了"
            except sa.exc.DBAPIError:
                out["control"] = "insert 失败"
            try:
                await conn.execute(sa.text("SELECT 1"))
                out["control_after"] = "事务仍可用"
            except sa.exc.DBAPIError as exc:
                out["control_after"] = str(exc.orig if exc.orig is not None else exc)
        finally:
            if trans.is_active:
                await trans.rollback()
    await engine.dispose()
    return out


def test_review_flow_writes_notifications_in_same_transaction(monkeypatch):
    import app.core.audit_decorator as audit_decorator
    from app.services.event_bus import event_bus

    monkeypatch.setattr(audit_decorator, "_write_audit_log", AsyncMock())
    monkeypatch.setattr(type(event_bus), "publish", AsyncMock())
    out = asyncio.run(_scenario())
    ids = out["ids"]

    assert ids["rev"] in out["candidates"] and ids["prep"] not in out["candidates"], "审计员没有复核权限，不是候选"
    assert out["submitted"] == ([out["gid"]], [ids["rev"]])
    assert out["approved_notified"] == [ids["prep"]], "通过 → 通知编制人（不通知操作人自己）"
    assert out["notifications"] == [
        ("adjustment.review_approved", ids["prep"], out["gid"], YEAR),
        ("adjustment.review_submitted", ids["rev"], out["gid"], YEAR),
    ]
    assert out["status"] == ["approved"]
    assert out["bad_sent"] == [] and out["after_bad"] == 1, "经保存点写的坏通知只丢自己，事务仍可用"
    assert out["control"] == "insert 失败"
    assert "current transaction is aborted" in out["control_after"], (
        f"反向对照没复现 PG 的 aborted 语义（{out['control_after']}），本用例判据空转"
    )
