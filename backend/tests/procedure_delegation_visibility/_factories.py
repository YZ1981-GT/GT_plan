# Feature: procedure-delegation-visibility-isolation — shared test factories
"""共享测试数据工厂 + 每-example PG 隔离 runner。

真实 PostgreSQL（audit_platform）承载 user/staff/assignment/project_user/wp_index/
working_paper/procedure_* 数据；每个用例/每个 Hypothesis example 在独立事务内插入并回滚，
绝不污染 dev 库。SQL 语义（唯一 active 映射、反向唯一、scope 上界、procedure→wp_index 唯一解析、
sheet 绑定）必须在 PG 验证，不用 sqlite。

Task 3（角色分类 / staff↔user 映射）与 Task 4（ProcedureWpResolver / SheetBindingCatalog）
共用本文件。
"""
from __future__ import annotations

import asyncio
import random
import time
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.config import settings as app_settings
from app.models.base import ProjectUserRole, UserRole
from app.models.core import Project, ProjectUser, User
from app.models.procedure_models import (
    ProcedureInstance,
    ProcedureRowDefinition,
    ProcedureRowTask,
)
from app.models.staff_models import ProjectAssignment, StaffMember
from app.models.workpaper_models import WorkingPaper, WpIndex, WpSourceType

IS_PG = app_settings.DATABASE_URL.startswith("postgresql")

_HASH64 = "0" * 64  # CHAR(64) 占位 revision hash


# ---------------------------------------------------------------------------
# 基础实体（Task 3）
# ---------------------------------------------------------------------------
async def mk_user(s: AsyncSession, role: str = "auditor") -> User:
    u = User(
        username=f"u_{uuid4().hex[:16]}",
        email=f"{uuid4().hex[:16]}@t.example",
        hashed_password="x",
        role=UserRole(role),
        is_active=True,
    )
    s.add(u)
    await s.flush()
    return u


async def mk_project(s: AsyncSession) -> Project:
    p = Project(name=f"proj_{uuid4().hex[:8]}", client_name="测试客户")
    s.add(p)
    await s.flush()
    return p


async def mk_staff(s: AsyncSession, user_id=None, is_deleted: bool = False) -> StaffMember:
    st_ = StaffMember(name=f"staff_{uuid4().hex[:8]}", user_id=user_id)
    st_.is_deleted = is_deleted
    s.add(st_)
    await s.flush()
    return st_


async def mk_assignment(
    s: AsyncSession, project_id, staff_id, role: str = "manager", is_deleted: bool = False
) -> ProjectAssignment:
    a = ProjectAssignment(project_id=project_id, staff_id=staff_id, role=role)
    a.is_deleted = is_deleted
    s.add(a)
    await s.flush()
    return a


async def mk_project_user(
    s: AsyncSession,
    project_id,
    user_id,
    role: str = "auditor",
    scope_cycles: str | None = None,
    is_deleted: bool = False,
) -> ProjectUser:
    pu = ProjectUser(
        project_id=project_id,
        user_id=user_id,
        role=ProjectUserRole(role),
        scope_cycles=scope_cycles,
    )
    pu.is_deleted = is_deleted
    s.add(pu)
    await s.flush()
    return pu


# ---------------------------------------------------------------------------
# 底稿索引 / 文件 / 程序实例 / 程序行（Task 4）
# ---------------------------------------------------------------------------
async def mk_wp_index(
    s: AsyncSession,
    project_id,
    wp_code: str | None = None,
    wp_name: str = "测试底稿",
    audit_cycle: str | None = "D",
    is_deleted: bool = False,
) -> WpIndex:
    wi = WpIndex(
        project_id=project_id,
        wp_code=wp_code or f"WP-{uuid4().hex[:8]}",
        wp_name=wp_name,
        audit_cycle=audit_cycle,
    )
    wi.is_deleted = is_deleted
    s.add(wi)
    await s.flush()
    return wi


async def mk_working_paper(
    s: AsyncSession,
    project_id,
    wp_index_id,
    file_version: int = 1,
    is_deleted: bool = False,
) -> WorkingPaper:
    wp = WorkingPaper(
        project_id=project_id,
        wp_index_id=wp_index_id,
        file_path=f"/tmp/{uuid4().hex[:8]}.xlsx",
        source_type=WpSourceType.template,
        file_version=file_version,
    )
    wp.is_deleted = is_deleted
    s.add(wp)
    await s.flush()
    return wp


async def mk_procedure_instance(
    s: AsyncSession,
    project_id,
    audit_cycle: str = "D",
    procedure_code: str | None = None,
    wp_code: str | None = None,
    wp_id=None,
    is_custom: bool = False,
    is_deleted: bool = False,
) -> ProcedureInstance:
    """procedure 实例。``procedure_code`` 可独立指定（同 code 多实例场景）；缺省回退 wp_code/随机。"""
    pi = ProcedureInstance(
        project_id=project_id,
        audit_cycle=audit_cycle,
        procedure_code=procedure_code or wp_code or f"P-{uuid4().hex[:8]}",
        procedure_name="测试程序",
        wp_code=wp_code,
        wp_id=wp_id,
        is_custom=is_custom,
    )
    pi.is_deleted = is_deleted
    s.add(pi)
    await s.flush()
    return pi


async def mk_row_definition(
    s: AsyncSession,
    sheet_key: str = "D2A",
    template_code: str = "D2",
    definition_key: str | None = None,
    procedure_text: str = "执行审计程序",
) -> ProcedureRowDefinition:
    d = ProcedureRowDefinition(
        definition_key=definition_key or f"def-{uuid4().hex[:12]}",
        template_code=template_code,
        template_revision_hash=_HASH64,
        sheet_key=sheet_key,
        procedure_text=procedure_text,
    )
    s.add(d)
    await s.flush()
    return d


async def mk_row_task(
    s: AsyncSession,
    project_id,
    wp_index_id,
    sheet_key: str = "D2A",
    sheet_name: str | None = None,
    definition_key: str | None = None,
    wp_id=None,
    wp_code: str | None = None,
    assignee_staff_id=None,
    reviewer_staff_id=None,
    audit_cycle: str = "D",
    is_deleted: bool = False,
) -> ProcedureRowTask:
    if definition_key is None:
        d = await mk_row_definition(s, sheet_key=sheet_key)
        definition_key = d.definition_key
    t = ProcedureRowTask(
        project_id=project_id,
        wp_index_id=wp_index_id,
        wp_id=wp_id,
        definition_key=definition_key,
        sheet_key=sheet_key,
        sheet_name=sheet_name,
        wp_code=wp_code,
        definition_revision_hash=_HASH64,
        audit_cycle_snapshot=audit_cycle,
        assignee_staff_id=assignee_staff_id,
        reviewer_staff_id=reviewer_staff_id,
    )
    t.is_deleted = is_deleted
    s.add(t)
    await s.flush()
    return t


# ---------------------------------------------------------------------------
# 瞬时锁竞争（deadlock / lock-timeout / serialization）识别 —— 全库并行收集下，
# Task 2 的 V113 schema-contract DDL（DROP/CREATE TABLE + trigger，取 AccessExclusiveLock）
# 会与本模块的 PBT example（INSERT 到 V113 表 + FK 父表，持 RowExclusive/RowShare）在同一
# dev 库上产生锁竞争。V113 那侧已用 lock_timeout(<deadlock_timeout) 主动让路+重试拆环；此处
# 作为 DML 侧的兜底：若某 example 恰被选为死锁牺牲者，则在全新连接/事务上原样重跑该 example
# （幂等：整例回滚），绝不放宽断言、不降低有效样例数、不跳过属性 —— 仅消除瞬时锁竞争。
# ---------------------------------------------------------------------------
_TRANSIENT_LOCK_SQLSTATES = {"40P01", "55P03", "40001"}  # deadlock / lock_not_available / serialization
_TRANSIENT_LOCK_TEXT = ("deadlock detected", "locknotavailable", "lock timeout", "canceling statement due to lock timeout")


def _is_transient_lock_error(exc: BaseException) -> bool:
    seen: set[int] = set()
    cur: BaseException | None = exc
    while cur is not None and id(cur) not in seen:
        seen.add(id(cur))
        code = getattr(cur, "sqlstate", None) or getattr(cur, "pgcode", None)
        if code in _TRANSIENT_LOCK_SQLSTATES:
            return True
        text = f"{type(cur).__name__}: {cur}".lower()
        if any(t in text for t in _TRANSIENT_LOCK_TEXT):
            return True
        cur = getattr(cur, "orig", None) or getattr(cur, "__cause__", None)
    return False


def run_isolated(coro_fn, *, max_attempts: int = 6):
    """每 example 独立引擎/连接/事务 + 回滚（新 loop，避免跨 loop 复用）。

    与 tests/procedure_delegation/test_procedure_authorization.py 的 `_run` 同构，供
    Hypothesis PBT 逐 example 隔离使用。

    全库并行收集兜底：若整例因瞬时锁竞争（deadlock/lock-timeout/serialization）失败，则在
    全新引擎/连接/事务上原样重跑（整例回滚，天然幂等），最多 ``max_attempts`` 次。此重试只吞
    锁竞争类异常，任何断言失败/业务异常照常向上抛出。
    """

    async def _wrap():
        engine = create_async_engine(app_settings.DATABASE_URL)
        conn = await engine.connect()
        trans = await conn.begin()
        s = AsyncSession(bind=conn)
        try:
            return await coro_fn(s)
        finally:
            await s.close()
            await trans.rollback()
            await conn.close()
            await engine.dispose()

    last_exc: BaseException | None = None
    for attempt in range(max_attempts):
        try:
            return asyncio.run(_wrap())
        except Exception as exc:  # noqa: BLE001
            if _is_transient_lock_error(exc) and attempt < max_attempts - 1:
                last_exc = exc
                time.sleep(0.1 * (attempt + 1) + random.random() * 0.1)
                continue
            raise
    raise last_exc  # pragma: no cover — 循环内必 return 或 raise
