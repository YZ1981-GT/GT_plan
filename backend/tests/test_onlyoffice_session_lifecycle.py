"""席位生命周期集成测试 — OnlyOffice 编辑会话 acquire→release 全流程

从路由端点视角验证完整的席位管理生命周期：
1. 编辑模式获取席位 → 成功 200
2. 席位满额 → 429 拒绝
3. 幂等续期 → 同 user_id+doc_key 再次请求成功
4. callback status=3/4/7 → 释放席位
5. 缺 user_id/doc_key → 跳过释放（无报错，返回 error=0）
6. 只读模式 → 不调用 acquire_session

Mock 策略：patch Redis 层（onlyoffice_session_limiter 的 acquire/release），
测试通过 httpx AsyncClient → 真实路由端点。

Validates: Requirements R1, R2, R3
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.config import settings as app_settings
from app.routers.wp_onlyoffice_router import public_router, router


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

FAKE_USER_ID = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
FAKE_USER_ID_STR = str(FAKE_USER_ID)


class _FakeUser:
    id = FAKE_USER_ID
    username = "test_auditor"
    role = MagicMock(value="admin")


def _sequenced_execute(*head: object) -> AsyncMock:
    """前 N 次 execute 依次返回 `head`，之后**恒**返回「查不到行」的空结果。

    🔴 不用固定长度的 `side_effect=[...]`：Task 21 起 config 端点多了一次 room 查询
    （doc_key 由 room 身份派生，不再由文件 mtime 派生），统一门在同一个注入 session 上
    还会再查若干次。固定列表一旦被耗尽就抛 `StopAsyncIteration`，测试失败原因与被测行为
    完全无关。尾部的空结果不是「造数据」，而是如实表达「这一路查询都查不到行」——
    对 room 查询来说正是生产的基线代际路径（无存活 room ⇒ 按 generation 1 派生 doc_key）。
    """
    queue = list(head)

    def _empty() -> MagicMock:
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        result.scalar.return_value = None
        result.first.return_value = None
        result.scalars.return_value.all.return_value = []
        return result

    async def _execute(*_args: object, **_kwargs: object) -> object:
        return queue.pop(0) if queue else _empty()

    return AsyncMock(side_effect=_execute)


def _make_app_with_edit_wp(tmp_path, project_id, wp_code="D0", wp_status="draft"):
    """构建测试 app + 文件 + mock DB（编辑模式底稿）"""
    # 创建 xlsx 文件
    storage_dir = tmp_path / "projects" / str(project_id) / "workpapers" / "onlyoffice"
    storage_dir.mkdir(parents=True)
    target = storage_dir / f"{wp_code}.xlsx"
    target.write_bytes(b"PK\x03\x04" + b"\x00" * 100)

    # Mock DB: 底稿存在，状态由参数控制
    fake_wp = MagicMock()
    fake_wp.project_id = project_id
    fake_wp.status = wp_status
    fake_row = MagicMock()
    fake_row.__getitem__ = lambda self, idx: fake_wp if idx == 0 else wp_code

    fake_wp_result = MagicMock()
    fake_wp_result.first.return_value = fake_row

    fake_proj_result = MagicMock()
    fake_proj_result.scalar.return_value = False  # project not deleted

    fake_db = AsyncMock()
    # 🔴 Task 21 起 `resolve_room_doc_key()` 多一次 room 查询（doc_key 由 room 身份派生，
    #    不再是 mtime）。side_effect 只喂两条时第三次 execute 会 StopAsyncIteration。
    #    `scalar_one_or_none() -> None` = 「本入口还没有存活 room」，正是生产基线代际路径。
    fake_room_result = MagicMock()
    fake_room_result.scalar_one_or_none.return_value = None
    fake_db.execute = _sequenced_execute(fake_wp_result, fake_proj_result, fake_room_result)

    app = FastAPI()
    app.include_router(router)
    # 🔴 callback / wopi.contents / onlyoffice.health 挂在 `public_router`（机对机入口，
    #    绕过 dedicated_wp_gate 的 get_current_user）。只挂 `router` 的测试 app 里它们
    #    根本不存在 ⇒ 全部 404，与生产 `router_registry.workpaper` 同时注册两个 router
    #    不一致（Task 30 关门时修）。
    app.include_router(public_router)

    fake_user = _FakeUser()

    async def _override_db():
        yield fake_db

    from app.core.database import get_db
    from app.deps import get_current_user

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = lambda: fake_user

    return app, fake_user


# ---------------------------------------------------------------------------
# Test: acquire → release 完整流程
# ---------------------------------------------------------------------------


class TestAcquireReleaseFlow:
    """编辑模式获取席位 → callback 释放席位的完整生命周期

    Validates: Requirements R1, R2, R3
    """

    @pytest.mark.asyncio
    async def test_edit_mode_acquires_seat_then_callback_releases(
        self, tmp_path, monkeypatch
    ):
        """完整流程：config(edit) 获取席位 → callback status=2 释放席位"""
        monkeypatch.setattr(app_settings, "ONLYOFFICE_URL", "http://onlyoffice:80")
        monkeypatch.setattr(app_settings, "ONLYOFFICE_JWT_SECRET", "")
        monkeypatch.setattr(app_settings, "ONLYOFFICE_CALLBACK_BASE", "http://backend:9980")
        monkeypatch.setattr(app_settings, "STORAGE_ROOT", str(tmp_path))

        project_id = uuid.uuid4()
        wp_id = uuid.uuid4()
        sheet_name = "函证检查表"

        app, fake_user = _make_app_with_edit_wp(tmp_path, project_id)

        with patch(
            "app.services.onlyoffice_session_limiter.acquire_session",
            new_callable=AsyncMock,
            return_value=True,
        ) as mock_acquire, patch(
            "app.services.wp_template_finder.find_template_file_any",
            return_value=None,
        ), patch(
            "app.deps.set_rls_context", new_callable=AsyncMock
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                # Step 1: 获取配置（占席位）
                resp = await client.get(
                    f"/api/workpapers/{wp_id}/sheets/{sheet_name}/onlyoffice-config",
                    params={"project_id": str(project_id)},
                )

            assert resp.status_code == 200
            data = resp.json()
            assert data["mode"] == "edit"
            mock_acquire.assert_awaited_once()
            # 验证 acquire 传入了正确的 user_id
            call_args = mock_acquire.call_args[0]
            assert call_args[0] == fake_user.id

        # Step 2: callback status=2 释放席位（需要新的 DB mock）
        fake_wp2 = MagicMock()
        fake_wp2.project_id = project_id
        fake_row2 = MagicMock()
        fake_row2.__getitem__ = lambda self, idx: fake_wp2 if idx == 0 else "D0"

        fake_wp_result2 = MagicMock()
        fake_wp_result2.first.return_value = fake_row2
        fake_proj_result2 = MagicMock()
        fake_proj_result2.scalar.return_value = False

        fake_db2 = AsyncMock()
        # 🔴 Task 21 起 `resolve_room_doc_key()` 多一次 room 查询（doc_key 由 room 身份派生，
        #    不再是 mtime）。side_effect 只喂两条时第三次 execute 会 StopAsyncIteration。
        #    `scalar_one_or_none() -> None` = 「本入口还没有存活 room」，正是生产基线代际路径。
        fake_room_result2 = MagicMock()
        fake_room_result2.scalar_one_or_none.return_value = None
        fake_db2.execute = _sequenced_execute(fake_wp_result2, fake_proj_result2, fake_room_result2)

        app2 = FastAPI()
        app2.include_router(router)
        # 🔴 callback 挂在 `public_router` 上（同上）。只挂 `router` 时它不存在 ⇒ 404。
        app2.include_router(public_router)

        async def _override_db2():
            yield fake_db2

        from app.core.database import get_db

        app2.dependency_overrides[get_db] = _override_db2

        doc_key_str = "abc123def456"

        with patch(
            "app.services.onlyoffice_session_limiter.release_session",
            new_callable=AsyncMock,
        ) as mock_release, patch(
            "app.routers.wp_onlyoffice_router.httpx.AsyncClient"
        ) as mock_client_cls:
            mock_response = MagicMock()
            mock_response.content = b"new-content"
            mock_response.raise_for_status = MagicMock()
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_cls.return_value = mock_client

            async with AsyncClient(
                transport=ASGITransport(app=app2), base_url="http://test"
            ) as client:
                resp = await client.post(
                    f"/api/workpapers/{wp_id}/sheets/{sheet_name}/onlyoffice-callback",
                    json={
                        "status": 2,
                        "url": "http://onlyoffice/file.xlsx",
                        "key": doc_key_str,
                        "actions": [{"type": 1, "userid": FAKE_USER_ID_STR}],
                    },
                )

            assert resp.status_code == 200
            assert resp.json() == {"error": 0}
            mock_release.assert_awaited_once_with(FAKE_USER_ID_STR, doc_key_str)


# ---------------------------------------------------------------------------
# Test: 满额 429
# ---------------------------------------------------------------------------


class TestSeatCapacity429:
    """编辑席位满额时返回 429

    Validates: Requirements R1, R2
    """

    @pytest.mark.asyncio
    async def test_full_capacity_returns_429(self, tmp_path, monkeypatch):
        """MAX_SESSIONS 达到上限时 config 端点返回 429"""
        monkeypatch.setattr(app_settings, "ONLYOFFICE_URL", "http://onlyoffice:80")
        monkeypatch.setattr(app_settings, "ONLYOFFICE_JWT_SECRET", "")
        monkeypatch.setattr(app_settings, "ONLYOFFICE_CALLBACK_BASE", "http://backend:9980")
        monkeypatch.setattr(app_settings, "STORAGE_ROOT", str(tmp_path))

        project_id = uuid.uuid4()
        wp_id = uuid.uuid4()

        app, _ = _make_app_with_edit_wp(tmp_path, project_id)

        with patch(
            "app.services.onlyoffice_session_limiter.acquire_session",
            new_callable=AsyncMock,
            return_value=False,  # 席位满
        ) as mock_acquire, patch(
            "app.services.wp_template_finder.find_template_file_any",
            return_value=None,
        ), patch(
            "app.deps.set_rls_context", new_callable=AsyncMock
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get(
                    f"/api/workpapers/{wp_id}/sheets/函证检查表/onlyoffice-config",
                    params={"project_id": str(project_id)},
                )

            assert resp.status_code == 429
            assert "编辑人数已满" in resp.json()["detail"]
            mock_acquire.assert_awaited_once()


# ---------------------------------------------------------------------------
# Test: 幂等续期
# ---------------------------------------------------------------------------


class TestIdempotentRenewal:
    """同一 user_id + doc_key 重复请求 config 端点应幂等成功

    Validates: Requirements R1
    """

    @pytest.mark.asyncio
    async def test_same_user_same_doc_key_succeeds_twice(self, tmp_path, monkeypatch):
        """同用户同文档二次请求 config — acquire_session 返回 True（幂等续期）"""
        monkeypatch.setattr(app_settings, "ONLYOFFICE_URL", "http://onlyoffice:80")
        monkeypatch.setattr(app_settings, "ONLYOFFICE_JWT_SECRET", "")
        monkeypatch.setattr(app_settings, "ONLYOFFICE_CALLBACK_BASE", "http://backend:9980")
        monkeypatch.setattr(app_settings, "STORAGE_ROOT", str(tmp_path))

        project_id = uuid.uuid4()
        wp_id = uuid.uuid4()
        wp_code = "D0"

        # 为两次请求准备两套 DB mock
        def _make_db_mock():
            fake_wp = MagicMock()
            fake_wp.project_id = project_id
            fake_wp.status = "draft"
            fake_row = MagicMock()
            fake_row.__getitem__ = lambda self, idx: fake_wp if idx == 0 else wp_code

            fake_wp_result = MagicMock()
            fake_wp_result.first.return_value = fake_row
            fake_proj_result = MagicMock()
            fake_proj_result.scalar.return_value = False

            fake_db = AsyncMock()
            # 🔴 Task 21 起 `resolve_room_doc_key()` 多一次 room 查询（doc_key 由 room 身份派生，
            #    不再是 mtime）。side_effect 只喂两条时第三次 execute 会 StopAsyncIteration。
            #    `scalar_one_or_none() -> None` = 「本入口还没有存活 room」，正是生产基线代际路径。
            fake_room_result = MagicMock()
            fake_room_result.scalar_one_or_none.return_value = None
            fake_db.execute = _sequenced_execute(fake_wp_result, fake_proj_result, fake_room_result)
            return fake_db

        # 创建文件
        storage_dir = tmp_path / "projects" / str(project_id) / "workpapers" / "onlyoffice"
        storage_dir.mkdir(parents=True)
        (storage_dir / f"{wp_code}.xlsx").write_bytes(b"PK\x03\x04" + b"\x00" * 100)

        # acquire_session 两次都返回 True（模拟幂等续期行为）
        with patch(
            "app.services.onlyoffice_session_limiter.acquire_session",
            new_callable=AsyncMock,
            return_value=True,
        ) as mock_acquire, patch(
            "app.services.wp_template_finder.find_template_file_any",
            return_value=None,
        ), patch(
            "app.deps.set_rls_context", new_callable=AsyncMock
        ):
            # 第一次请求
            app1 = FastAPI()
            app1.include_router(router)
            from app.core.database import get_db
            from app.deps import get_current_user

            db1 = _make_db_mock()

            async def _db1():
                yield db1

            app1.dependency_overrides[get_db] = _db1
            app1.dependency_overrides[get_current_user] = lambda: _FakeUser()

            async with AsyncClient(
                transport=ASGITransport(app=app1), base_url="http://test"
            ) as client:
                resp1 = await client.get(
                    f"/api/workpapers/{wp_id}/sheets/函证检查表/onlyoffice-config",
                    params={"project_id": str(project_id)},
                )

            assert resp1.status_code == 200

            # 第二次请求（同用户同文档）
            app2 = FastAPI()
            app2.include_router(router)
            db2 = _make_db_mock()

            async def _db2():
                yield db2

            app2.dependency_overrides[get_db] = _db2
            app2.dependency_overrides[get_current_user] = lambda: _FakeUser()

            async with AsyncClient(
                transport=ASGITransport(app=app2), base_url="http://test"
            ) as client:
                resp2 = await client.get(
                    f"/api/workpapers/{wp_id}/sheets/函证检查表/onlyoffice-config",
                    params={"project_id": str(project_id)},
                )

            assert resp2.status_code == 200
            # acquire_session 被调用两次均成功
            assert mock_acquire.await_count == 2


# ---------------------------------------------------------------------------
# Test: status=3/4/7 释放席位
# ---------------------------------------------------------------------------


class TestReleaseStatusCodes:
    """callback 的 status=3/4/7 正确触发席位释放

    Validates: Requirements R3
    """

    @pytest.mark.asyncio
    @pytest.mark.parametrize("status_code", [3, 4, 7])
    async def test_release_statuses_call_release_session(
        self, tmp_path, monkeypatch, status_code
    ):
        """status=3（保存出错）/4（关闭无修改）/7（强制保存出错）均释放席位"""
        monkeypatch.setattr(app_settings, "STORAGE_ROOT", str(tmp_path))
        monkeypatch.setattr(app_settings, "ONLYOFFICE_JWT_SECRET", "")

        user_id_str = FAKE_USER_ID_STR
        doc_key_str = f"key-for-status-{status_code}"

        app = FastAPI()
        app.include_router(router)
        # 🔴 callback / wopi.contents / onlyoffice.health 挂在 `public_router`（机对机入口，
        #    绕过 dedicated_wp_gate 的 get_current_user）。只挂 `router` 的测试 app 里它们
        #    根本不存在 ⇒ 全部 404，与生产 `router_registry.workpaper` 同时注册两个 router
        #    不一致（Task 30 关门时修）。
        app.include_router(public_router)

        async def _override_db():
            yield MagicMock()

        from app.core.database import get_db

        app.dependency_overrides[get_db] = _override_db

        wp_id = uuid.uuid4()

        with patch(
            "app.services.onlyoffice_session_limiter.release_session",
            new_callable=AsyncMock,
        ) as mock_release:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    f"/api/workpapers/{wp_id}/sheets/test_sheet/onlyoffice-callback",
                    json={
                        "status": status_code,
                        "key": doc_key_str,
                        "actions": [{"type": 0, "userid": user_id_str}],
                    },
                )

            assert resp.status_code == 200
            assert resp.json() == {"error": 0}
            mock_release.assert_awaited_once_with(user_id_str, doc_key_str)


# ---------------------------------------------------------------------------
# Test: 缺 user_id / doc_key 跳过释放
# ---------------------------------------------------------------------------


class TestMissingFieldsSkipRelease:
    """缺少 user_id 或 doc_key 时跳过释放（无错误，返回 error=0）

    Validates: Requirements R3
    """

    @pytest.mark.asyncio
    async def test_missing_user_id_skips_release(self, tmp_path, monkeypatch):
        """body 无 actions/users → user_id=None → 跳过 release"""
        monkeypatch.setattr(app_settings, "STORAGE_ROOT", str(tmp_path))
        monkeypatch.setattr(app_settings, "ONLYOFFICE_JWT_SECRET", "")

        app = FastAPI()
        app.include_router(router)
        # 🔴 callback / wopi.contents / onlyoffice.health 挂在 `public_router`（机对机入口，
        #    绕过 dedicated_wp_gate 的 get_current_user）。只挂 `router` 的测试 app 里它们
        #    根本不存在 ⇒ 全部 404，与生产 `router_registry.workpaper` 同时注册两个 router
        #    不一致（Task 30 关门时修）。
        app.include_router(public_router)

        async def _override_db():
            yield MagicMock()

        from app.core.database import get_db

        app.dependency_overrides[get_db] = _override_db

        wp_id = uuid.uuid4()

        with patch(
            "app.services.onlyoffice_session_limiter.release_session",
            new_callable=AsyncMock,
        ) as mock_release:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    f"/api/workpapers/{wp_id}/sheets/test_sheet/onlyoffice-callback",
                    json={
                        "status": 4,
                        "key": "some-doc-key",
                        # No actions, no users → user_id = None
                    },
                )

            assert resp.status_code == 200
            assert resp.json() == {"error": 0}
            mock_release.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_missing_doc_key_skips_release(self, tmp_path, monkeypatch):
        """body 无 key 字段 → doc_key=None → 跳过 release"""
        monkeypatch.setattr(app_settings, "STORAGE_ROOT", str(tmp_path))
        monkeypatch.setattr(app_settings, "ONLYOFFICE_JWT_SECRET", "")

        app = FastAPI()
        app.include_router(router)
        # 🔴 callback / wopi.contents / onlyoffice.health 挂在 `public_router`（机对机入口，
        #    绕过 dedicated_wp_gate 的 get_current_user）。只挂 `router` 的测试 app 里它们
        #    根本不存在 ⇒ 全部 404，与生产 `router_registry.workpaper` 同时注册两个 router
        #    不一致（Task 30 关门时修）。
        app.include_router(public_router)

        async def _override_db():
            yield MagicMock()

        from app.core.database import get_db

        app.dependency_overrides[get_db] = _override_db

        wp_id = uuid.uuid4()

        with patch(
            "app.services.onlyoffice_session_limiter.release_session",
            new_callable=AsyncMock,
        ) as mock_release:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    f"/api/workpapers/{wp_id}/sheets/test_sheet/onlyoffice-callback",
                    json={
                        "status": 4,
                        # No "key" field
                        "actions": [{"type": 0, "userid": FAKE_USER_ID_STR}],
                    },
                )

            assert resp.status_code == 200
            assert resp.json() == {"error": 0}
            mock_release.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_both_missing_still_returns_error_0(self, tmp_path, monkeypatch):
        """user_id 和 doc_key 都缺时返回 error=0（TTL 兜底）"""
        monkeypatch.setattr(app_settings, "STORAGE_ROOT", str(tmp_path))
        monkeypatch.setattr(app_settings, "ONLYOFFICE_JWT_SECRET", "")

        app = FastAPI()
        app.include_router(router)
        # 🔴 callback / wopi.contents / onlyoffice.health 挂在 `public_router`（机对机入口，
        #    绕过 dedicated_wp_gate 的 get_current_user）。只挂 `router` 的测试 app 里它们
        #    根本不存在 ⇒ 全部 404，与生产 `router_registry.workpaper` 同时注册两个 router
        #    不一致（Task 30 关门时修）。
        app.include_router(public_router)

        async def _override_db():
            yield MagicMock()

        from app.core.database import get_db

        app.dependency_overrides[get_db] = _override_db

        wp_id = uuid.uuid4()

        with patch(
            "app.services.onlyoffice_session_limiter.release_session",
            new_callable=AsyncMock,
        ) as mock_release:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    f"/api/workpapers/{wp_id}/sheets/test_sheet/onlyoffice-callback",
                    json={
                        "status": 3,
                        # No key, no actions, no users
                    },
                )

            assert resp.status_code == 200
            assert resp.json() == {"error": 0}
            mock_release.assert_not_awaited()


# ---------------------------------------------------------------------------
# Test: 只读模式不占席位
# ---------------------------------------------------------------------------


class TestViewModeNoSeat:
    """只读模式（view）不调用 acquire_session

    Validates: Requirements R1, R2
    """

    @pytest.mark.asyncio
    async def test_view_mode_bypasses_acquire(self, tmp_path, monkeypatch):
        """status=review_passed → mode=view → 不调 acquire_session"""
        monkeypatch.setattr(app_settings, "ONLYOFFICE_URL", "http://onlyoffice:80")
        monkeypatch.setattr(app_settings, "ONLYOFFICE_JWT_SECRET", "")
        monkeypatch.setattr(app_settings, "ONLYOFFICE_CALLBACK_BASE", "http://backend:9980")
        monkeypatch.setattr(app_settings, "STORAGE_ROOT", str(tmp_path))

        from app.models.workpaper_models import WpFileStatus

        project_id = uuid.uuid4()
        wp_id = uuid.uuid4()

        # 使用 review_passed 状态 → view mode
        app, _ = _make_app_with_edit_wp(
            tmp_path, project_id, wp_status=WpFileStatus.review_passed
        )

        with patch(
            "app.services.onlyoffice_session_limiter.acquire_session",
            new_callable=AsyncMock,
            return_value=True,
        ) as mock_acquire, patch(
            "app.services.wp_template_finder.find_template_file_any",
            return_value=None,
        ), patch(
            "app.deps.set_rls_context", new_callable=AsyncMock
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get(
                    f"/api/workpapers/{wp_id}/sheets/函证检查表/onlyoffice-config",
                    params={"project_id": str(project_id)},
                )

            assert resp.status_code == 200
            data = resp.json()
            assert data["mode"] == "view"
            # acquire_session 不应被调用
            mock_acquire.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_archived_mode_bypasses_acquire(self, tmp_path, monkeypatch):
        """status=archived → mode=view → 不调 acquire_session"""
        monkeypatch.setattr(app_settings, "ONLYOFFICE_URL", "http://onlyoffice:80")
        monkeypatch.setattr(app_settings, "ONLYOFFICE_JWT_SECRET", "")
        monkeypatch.setattr(app_settings, "ONLYOFFICE_CALLBACK_BASE", "http://backend:9980")
        monkeypatch.setattr(app_settings, "STORAGE_ROOT", str(tmp_path))

        from app.models.workpaper_models import WpFileStatus

        project_id = uuid.uuid4()
        wp_id = uuid.uuid4()

        app, _ = _make_app_with_edit_wp(
            tmp_path, project_id, wp_status=WpFileStatus.archived
        )

        with patch(
            "app.services.onlyoffice_session_limiter.acquire_session",
            new_callable=AsyncMock,
            return_value=True,
        ) as mock_acquire, patch(
            "app.services.wp_template_finder.find_template_file_any",
            return_value=None,
        ), patch(
            "app.deps.set_rls_context", new_callable=AsyncMock
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get(
                    f"/api/workpapers/{wp_id}/sheets/函证检查表/onlyoffice-config",
                    params={"project_id": str(project_id)},
                )

            assert resp.status_code == 200
            data = resp.json()
            assert data["mode"] == "view"
            mock_acquire.assert_not_awaited()
