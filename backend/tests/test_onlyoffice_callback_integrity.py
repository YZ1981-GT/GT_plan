"""OnlyOffice 回调完整性（deliverable-writeback-and-online-edit-integrity Phase C）。

真 SQLite + 真 ORM；httpx 下载替身返回指定字节。覆盖 status 6 落版本、key 校验、幂等、
陈旧底版留痕、编辑人（admin 免成员表 / 停用拒绝 / 非成员拒绝）、席位只在 2/3/4 释放。
"""
from __future__ import annotations

import asyncio
import hashlib
import uuid
from types import SimpleNamespace

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import tests.conftest  # noqa: F401 — SQLite JSONB/UUID 兼容
from app.models.audit_log_models import AuditLogEntry
from app.models.base import Base, PermissionLevel, ProjectStatus, ProjectUserRole, UserRole
from app.models.core import Project, ProjectUser, User
from app.models.phase13_models import WordExportStatus, WordExportTask, WordExportTaskVersion
from app.services import onlyoffice_callback_service as oo_module
from app.services.deliverable_doc_key import deliverable_doc_key
from app.services.deliverable_hash_service import DeliverableHashService
from app.services.onlyoffice_callback_service import OnlyOfficeCallbackService

TABLES = [
    User.__table__, Project.__table__, ProjectUser.__table__,
    WordExportTask.__table__, WordExportTaskVersion.__table__, AuditLogEntry.__table__,
]


class _FakeResp:
    def __init__(self, content: bytes) -> None:
        self.content = content

    def raise_for_status(self) -> None:
        return None


def _fake_httpx(content: bytes):
    class _Client:
        def __init__(self, *a, **k) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, _url):
            return _FakeResp(content)

    return SimpleNamespace(AsyncClient=_Client)


class _World:
    def __init__(self, db, factory, project_id, task_id, admin_id, member_id, outsider_id, inactive_id):
        self.db, self.factory = db, factory
        self.project_id, self.task_id = project_id, task_id
        self.admin_id, self.member_id = admin_id, member_id
        self.outsider_id, self.inactive_id = outsider_id, inactive_id


def _run(scenario):
    async def _main():
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as conn:
            await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=TABLES))
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        try:
            async with factory() as db:
                ids = {k: uuid.uuid4() for k in ("project", "task", "admin", "member", "outsider", "inactive")}
                db.add_all([
                    User(id=ids["admin"], username="oo-admin", email="a@x.com", hashed_password="x",
                         role=UserRole.admin, is_active=True),
                    User(id=ids["member"], username="oo-member", email="m@x.com", hashed_password="x",
                         role=UserRole.auditor, is_active=True),
                    User(id=ids["outsider"], username="oo-out", email="o@x.com", hashed_password="x",
                         role=UserRole.auditor, is_active=True),
                    User(id=ids["inactive"], username="oo-inactive", email="i@x.com", hashed_password="x",
                         role=UserRole.auditor, is_active=False),
                ])
                db.add(Project(id=ids["project"], name="OO_2025", client_name="OO", status=ProjectStatus.execution))
                db.add(ProjectUser(project_id=ids["project"], user_id=ids["member"],
                                   role=ProjectUserRole.auditor, permission_level=PermissionLevel.edit))
                db.add(WordExportTask(id=ids["task"], project_id=ids["project"], doc_type="disclosure_notes",
                                      status=WordExportStatus.editing.value, created_by=ids["admin"]))
                await db.flush()
                db.add(WordExportTaskVersion(
                    word_export_task_id=ids["task"], version_no=1, created_by=ids["admin"],
                    created_via="generate", file_hash=hashlib.sha256(b"v1-bytes").hexdigest(), file_size=8,
                ))
                await db.flush()
                world = _World(db, factory, ids["project"], ids["task"],
                               ids["admin"], ids["member"], ids["outsider"], ids["inactive"])
                return await scenario(world)
        finally:
            await engine.dispose()

    return asyncio.run(_main())


async def _callback(world: _World, body: dict, *, content: bytes, user_id=None):
    """执行一次回调；隔离磁盘落盘与 hash 绑定，file_hash 直接取入库字节的 SHA-256。"""
    import unittest.mock as mock

    orig = oo_module.httpx
    oo_module.httpx = _fake_httpx(content)

    async def _bind(self, version, task, uid):
        return None  # file_hash 已在 persist 替身回传后由 render_and_store 绑定

    def _persist(content, final_path, delivery_root=None):
        return SimpleNamespace(size=len(content), sha256=hashlib.sha256(content).hexdigest())

    try:
        with mock.patch.object(DeliverableHashService, "bind_version_hash", new=_bind), \
                mock.patch("app.services.file_fingerprint_service.persist_file_fail_closed", new=_persist):
            svc = OnlyOfficeCallbackService(world.db)
            return await svc.handle_callback(
                world.task_id, body, user_id=user_id or world.admin_id, year=2025
            )
    finally:
        oo_module.httpx = orig


async def _versions(world: _World) -> list[WordExportTaskVersion]:
    rows = await world.db.execute(
        sa.select(WordExportTaskVersion)
        .where(WordExportTaskVersion.word_export_task_id == world.task_id)
        .order_by(WordExportTaskVersion.version_no)
    )
    return list(rows.scalars().all())


async def _security_log_count(world: _World) -> int:
    rows = await world.db.execute(
        sa.select(sa.func.count()).select_from(AuditLogEntry).where(
            AuditLogEntry.action_type == "onlyoffice_callback_rejected"
        )
    )
    return int(rows.scalar_one())


async def _stale_log_count(world: _World) -> int:
    rows = await world.db.execute(
        sa.select(sa.func.count()).select_from(AuditLogEntry).where(
            AuditLogEntry.action_type == "deliverable_oo_stale_base_save"
        )
    )
    return int(rows.scalar_one())


def _key(world: _World, version_no: int) -> str:
    return deliverable_doc_key(world.task_id, version_no)


# ─── status 6 落版本 ───────────────────────────────────────────────────

def test_status_6_force_save_creates_version():
    async def _s(world):
        before = len(await _versions(world))
        result = await _callback(
            world,
            {"status": 6, "url": "http://oo/edited.docx", "key": _key(world, 1)},
            content=b"force-saved-content",
        )
        after = await _versions(world)
        return before, result, after

    before, result, after = _run(_s)
    assert result == {"error": 0}
    assert len(after) == before + 1
    v2 = after[-1]
    assert v2.version_no == 2 and v2.created_via == "onlyoffice_edit"
    assert v2.base_version_no == 1 and v2.oo_doc_key == deliverable_doc_key(after[0].word_export_task_id, 1)


# ─── key 校验 ─────────────────────────────────────────────────────────

def test_missing_or_foreign_key_is_rejected_with_security_log():
    async def _s(world):
        other_key = deliverable_doc_key(uuid.uuid4(), 1)
        no_key = await _callback(world, {"status": 2, "url": "http://oo/e.docx"}, content=b"x")
        foreign = await _callback(
            world, {"status": 2, "url": "http://oo/e.docx", "key": other_key}, content=b"y",
        )
        return no_key, foreign, len(await _versions(world)), await _security_log_count(world)

    no_key, foreign, versions, logs = _run(_s)
    assert no_key == {"error": 1} and foreign == {"error": 1}
    assert versions == 1  # 两次都不建版本
    assert logs == 2  # 两次都写安全日志


# ─── 幂等 ─────────────────────────────────────────────────────────────

def test_same_content_as_latest_is_idempotent():
    async def _s(world):
        content = b"identical-save-bytes"
        first = await _callback(
            world, {"status": 6, "url": "http://oo/e.docx", "key": _key(world, 1)}, content=content,
        )
        after_first = await _versions(world)
        # 关闭时 Document Server 发 status 2，内容与强制保存后的最新版本一致 ⇒ 幂等
        second = await _callback(
            world, {"status": 2, "url": "http://oo/e.docx", "key": _key(world, 1)}, content=content,
        )
        after_second = await _versions(world)
        return first, second, len(after_first), len(after_second)

    first, second, n1, n2 = _run(_s)
    assert first == {"error": 0} and second == {"error": 0}
    assert n1 == 2 and n2 == 2  # 第二次幂等，不新增


# ─── 陈旧底版 ─────────────────────────────────────────────────────────

def test_stale_base_still_saves_but_logs_overwrite():
    async def _s(world):
        # 编辑会话以 v1 为底打开；期间别人刷新产生 v2（非本会话）
        world.db.add(WordExportTaskVersion(
            word_export_task_id=world.task_id, version_no=2, created_by=world.admin_id,
            created_via="refresh_section", file_hash=hashlib.sha256(b"v2-refresh").hexdigest(), file_size=10,
        ))
        await world.db.flush()
        result = await _callback(
            world, {"status": 2, "url": "http://oo/e.docx", "key": _key(world, 1)}, content=b"editor-content",
        )
        after = await _versions(world)
        return result, after, await _stale_log_count(world)

    result, after, stale_logs = _run(_s)
    assert result == {"error": 0}
    # 不丢编辑：仍落 v3
    assert [v.version_no for v in after] == [1, 2, 3]
    v3 = after[-1]
    assert v3.base_version_no == 1
    assert stale_logs == 1  # 覆盖 v2 的留痕


def test_same_session_force_save_then_close_is_not_stale():
    async def _s(world):
        key1 = _key(world, 1)
        # 本会话先强制保存 → v2（oo_doc_key=key1）
        await _callback(world, {"status": 6, "url": "http://oo/e.docx", "key": key1}, content=b"draft-1")
        # 本会话关闭 → v3，底版仍是 v1，v2 属同一会话 ⇒ 不算陈旧
        await _callback(world, {"status": 2, "url": "http://oo/e.docx", "key": key1}, content=b"final-2")
        return [v.version_no for v in await _versions(world)], await _stale_log_count(world)

    versions, stale_logs = _run(_s)
    assert versions == [1, 2, 3]
    assert stale_logs == 0


# ─── 编辑人口径 ───────────────────────────────────────────────────────

def test_admin_editor_recorded_even_though_not_project_member():
    async def _s(world):
        await _callback(
            world, {"status": 2, "url": "http://oo/e.docx", "key": _key(world, 1),
                    "users": [str(world.admin_id)]},
            content=b"admin-edit",
        )
        return (await _versions(world))[-1].edited_by

    assert _run(_s) is not None


def test_project_member_editor_recorded():
    async def _s(world):
        await _callback(
            world, {"status": 2, "url": "http://oo/e.docx", "key": _key(world, 1),
                    "users": [str(world.member_id)]},
            content=b"member-edit",
        )
        return (await _versions(world))[-1].edited_by, world.member_id

    edited_by, member_id = _run(_s)
    assert edited_by == member_id


def test_inactive_user_and_outsider_recorded_as_unknown():
    async def _s(world):
        await _callback(
            world, {"status": 2, "url": "http://oo/e.docx", "key": _key(world, 1),
                    "users": [str(world.inactive_id)]},
            content=b"inactive-edit",
        )
        inactive_version = (await _versions(world))[-1].edited_by
        await _callback(
            world, {"status": 2, "url": "http://oo/e.docx", "key": _key(world, 1),
                    "users": [str(world.outsider_id)]},
            content=b"outsider-edit",
        )
        outsider_version = (await _versions(world))[-1].edited_by
        return inactive_version, outsider_version

    inactive_edited, outsider_edited = _run(_s)
    assert inactive_edited is None  # 停用用户不采信
    assert outsider_edited is None  # 非成员非 admin 不采信


# ─── 非保存状态 ───────────────────────────────────────────────────────

def test_non_save_status_is_noop():
    async def _s(world):
        for status in (1, 4):
            result = await _callback(
                world, {"status": status, "url": "http://oo/e.docx", "key": _key(world, 1)},
                content=b"should-not-save",
            )
            assert result == {"error": 0}
        return len(await _versions(world))

    assert _run(_s) == 1


# ─── 席位释放只在会话结束（2/3/4），强制保存 6 保持占用 ───────────────────

def test_seat_release_only_on_session_end_not_on_force_save():
    """源码级契约：交付中心回调路由释放席位的 status 集合是 {2,3,4}，不含 6。

    6=强制保存=仍在编辑；把 6 当释放会让「编辑中点一次保存」立即腾出名额，使并发上限失效。
    """
    import ast
    import inspect

    from app.routers import deliverable

    tree = ast.parse(inspect.getsource(deliverable))
    fn = next(
        n for n in ast.walk(tree)
        if isinstance(n, ast.AsyncFunctionDef) and n.name == "onlyoffice_callback"
    )
    release_sets: list[frozenset[int]] = []
    for node in ast.walk(fn):
        # 匹配 `if status in (2, 3, 4):` 形式
        if isinstance(node, ast.Compare) and len(node.ops) == 1 and isinstance(node.ops[0], ast.In):
            right = node.comparators[0]
            if isinstance(right, (ast.Tuple, ast.List, ast.Set)):
                values = {e.value for e in right.elts if isinstance(e, ast.Constant) and isinstance(e.value, int)}
                if values and values <= {1, 2, 3, 4, 6, 7}:
                    release_sets.append(frozenset(values))
    assert frozenset({2, 3, 4}) in release_sets, release_sets
    assert all(6 not in s for s in release_sets), f"status 6 不得触发席位释放：{release_sets}"
