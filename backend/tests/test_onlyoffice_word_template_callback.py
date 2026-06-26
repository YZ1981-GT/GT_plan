"""OnlyOffice 回调持久化测试 — word-template (docx) 场景

验证 task 9.1：
- callback status=2/6 时下载文档内容到 storage/{project_id}/workpapers/{wp_code}.docx
- 更新 workpaper.updated_at 时间戳
- 错误时返回 {"error": 1} 触发 DocServer 重试

Validates: Requirements 6.2
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.config import settings as app_settings
from app.routers.wp_onlyoffice_router import router


@pytest.mark.asyncio
async def test_word_template_callback_saves_docx(tmp_path, monkeypatch):
    """word-template 底稿 status=2 回调：保存到 storage/{project_id}/workpapers/{wp_code}.docx"""
    monkeypatch.setattr(app_settings, "STORAGE_ROOT", str(tmp_path))
    monkeypatch.setattr(app_settings, "ONLYOFFICE_URL", "http://onlyoffice:8080")
    monkeypatch.setattr(app_settings, "ONLYOFFICE_JWT_SECRET", "")

    project_id = uuid.uuid4()
    wp_code = "A9-1"

    # Mock DB: _load_wp_or_404
    fake_wp = MagicMock()
    fake_wp.project_id = project_id
    fake_wp.updated_at = datetime(2020, 1, 1, tzinfo=timezone.utc)
    fake_row = MagicMock()
    fake_row.__getitem__ = lambda self, idx: fake_wp if idx == 0 else wp_code

    fake_wp_result = MagicMock()
    fake_wp_result.first.return_value = fake_row

    fake_proj_result = MagicMock()
    fake_proj_result.scalar.return_value = False

    fake_db = AsyncMock()
    fake_db.execute = AsyncMock(side_effect=[fake_wp_result, fake_proj_result])
    fake_db.commit = AsyncMock()

    new_content = b"PK\x03\x04word-template-docx-content"

    app = FastAPI()
    app.include_router(router)

    async def _override_db():
        yield fake_db

    from app.core.database import get_db
    app.dependency_overrides[get_db] = _override_db

    wp_id = uuid.uuid4()

    with patch("app.routers.wp_onlyoffice_router.httpx.AsyncClient") as mock_client_cls, \
         patch("app.services.wp_classification_service._WP_CODE_OVERRIDE", {"A9-1": "word-template"}):
        mock_response = MagicMock()
        mock_response.content = new_content
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                f"/api/workpapers/{wp_id}/sheets/__word__/onlyoffice-callback",
                json={
                    "status": 2,
                    "url": "http://onlyoffice:8080/cached/edited.docx",
                },
            )

        assert resp.status_code == 200
        assert resp.json() == {"error": 0}

    # 验证文件保存到正确路径
    expected_path = Path(f"storage/{project_id}/workpapers/{wp_code}.docx")
    assert expected_path.exists()
    assert expected_path.read_bytes() == new_content

    # 验证 updated_at 被更新
    assert fake_wp.updated_at > datetime(2020, 1, 1, tzinfo=timezone.utc)
    fake_db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_word_template_callback_status_6_force_save(tmp_path, monkeypatch):
    """word-template 底稿 status=6（强制保存）同样保存到 docx 路径"""
    monkeypatch.setattr(app_settings, "STORAGE_ROOT", str(tmp_path))
    monkeypatch.setattr(app_settings, "ONLYOFFICE_URL", "http://onlyoffice:8080")
    monkeypatch.setattr(app_settings, "ONLYOFFICE_JWT_SECRET", "")

    project_id = uuid.uuid4()
    wp_code = "A16-1"

    fake_wp = MagicMock()
    fake_wp.project_id = project_id
    fake_wp.updated_at = datetime(2020, 1, 1, tzinfo=timezone.utc)
    fake_row = MagicMock()
    fake_row.__getitem__ = lambda self, idx: fake_wp if idx == 0 else wp_code

    fake_wp_result = MagicMock()
    fake_wp_result.first.return_value = fake_row

    fake_proj_result = MagicMock()
    fake_proj_result.scalar.return_value = False

    fake_db = AsyncMock()
    fake_db.execute = AsyncMock(side_effect=[fake_wp_result, fake_proj_result])
    fake_db.commit = AsyncMock()

    new_content = b"PK\x03\x04force-saved-docx"

    app = FastAPI()
    app.include_router(router)

    async def _override_db():
        yield fake_db

    from app.core.database import get_db
    app.dependency_overrides[get_db] = _override_db

    wp_id = uuid.uuid4()

    with patch("app.routers.wp_onlyoffice_router.httpx.AsyncClient") as mock_client_cls, \
         patch("app.services.wp_classification_service._WP_CODE_OVERRIDE", {"A16-1": "word-template"}):
        mock_response = MagicMock()
        mock_response.content = new_content
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                f"/api/workpapers/{wp_id}/sheets/__word__/onlyoffice-callback",
                json={
                    "status": 6,
                    "url": "http://onlyoffice:8080/cached/force-saved.docx",
                },
            )

        assert resp.status_code == 200
        assert resp.json() == {"error": 0}

    # 验证文件保存到 docx 路径
    expected_path = Path(f"storage/{project_id}/workpapers/{wp_code}.docx")
    assert expected_path.exists()
    assert expected_path.read_bytes() == new_content


@pytest.mark.asyncio
async def test_xlsx_callback_still_saves_to_onlyoffice_dir(tmp_path, monkeypatch):
    """非 word-template 底稿仍保存到 onlyoffice 存储目录（回归测试）"""
    monkeypatch.setattr(app_settings, "STORAGE_ROOT", str(tmp_path))
    monkeypatch.setattr(app_settings, "ONLYOFFICE_URL", "http://onlyoffice:8080")
    monkeypatch.setattr(app_settings, "ONLYOFFICE_JWT_SECRET", "")

    project_id = uuid.uuid4()
    wp_code = "D0"

    fake_wp = MagicMock()
    fake_wp.project_id = project_id
    fake_wp.updated_at = datetime(2020, 1, 1, tzinfo=timezone.utc)
    fake_row = MagicMock()
    fake_row.__getitem__ = lambda self, idx: fake_wp if idx == 0 else wp_code

    fake_wp_result = MagicMock()
    fake_wp_result.first.return_value = fake_row

    fake_proj_result = MagicMock()
    fake_proj_result.scalar.return_value = False

    fake_db = AsyncMock()
    fake_db.execute = AsyncMock(side_effect=[fake_wp_result, fake_proj_result])
    fake_db.commit = AsyncMock()

    new_content = b"PK\x03\x04xlsx-content"

    app = FastAPI()
    app.include_router(router)

    async def _override_db():
        yield fake_db

    from app.core.database import get_db
    app.dependency_overrides[get_db] = _override_db

    wp_id = uuid.uuid4()

    # D0 is NOT a word-template (it's a confirmation-hub or similar)
    with patch("app.routers.wp_onlyoffice_router.httpx.AsyncClient") as mock_client_cls, \
         patch("app.services.wp_classification_service._WP_CODE_OVERRIDE", {"D0": "confirmation-hub"}):
        mock_response = MagicMock()
        mock_response.content = new_content
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                f"/api/workpapers/{wp_id}/sheets/test_sheet/onlyoffice-callback",
                json={
                    "status": 2,
                    "url": "http://onlyoffice:8080/cached/edited.xlsx",
                },
            )

        assert resp.status_code == 200
        assert resp.json() == {"error": 0}

    # 验证保存到 onlyoffice 目录（旧行为）
    expected_path = tmp_path / "projects" / str(project_id) / "workpapers" / "onlyoffice" / f"{wp_code}.xlsx"
    assert expected_path.exists()
    assert expected_path.read_bytes() == new_content


@pytest.mark.asyncio
async def test_callback_download_failure_returns_error_1(tmp_path, monkeypatch):
    """下载失败时返回 {"error": 1} 触发 DocServer 重试"""
    monkeypatch.setattr(app_settings, "STORAGE_ROOT", str(tmp_path))
    monkeypatch.setattr(app_settings, "ONLYOFFICE_URL", "http://onlyoffice:8080")
    monkeypatch.setattr(app_settings, "ONLYOFFICE_JWT_SECRET", "")

    project_id = uuid.uuid4()
    wp_code = "A9-1"

    fake_wp = MagicMock()
    fake_wp.project_id = project_id
    fake_row = MagicMock()
    fake_row.__getitem__ = lambda self, idx: fake_wp if idx == 0 else wp_code

    fake_wp_result = MagicMock()
    fake_wp_result.first.return_value = fake_row

    fake_proj_result = MagicMock()
    fake_proj_result.scalar.return_value = False

    fake_db = AsyncMock()
    fake_db.execute = AsyncMock(side_effect=[fake_wp_result, fake_proj_result])

    app = FastAPI()
    app.include_router(router)

    async def _override_db():
        yield fake_db

    from app.core.database import get_db
    app.dependency_overrides[get_db] = _override_db

    wp_id = uuid.uuid4()

    with patch("app.routers.wp_onlyoffice_router.httpx.AsyncClient") as mock_client_cls, \
         patch("app.services.wp_classification_service._WP_CODE_OVERRIDE", {"A9-1": "word-template"}):
        # 模拟下载失败
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=Exception("network error"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                f"/api/workpapers/{wp_id}/sheets/__word__/onlyoffice-callback",
                json={
                    "status": 2,
                    "url": "http://onlyoffice:8080/cached/fail.docx",
                },
            )

        assert resp.status_code == 200
        assert resp.json() == {"error": 1}


# ---------------------------------------------------------------------------
# Property 13: OnlyOffice 回调持久化 (PBT)
# Feature: a-cycle-docx-online, Property 13: OnlyOffice 回调持久化
# Validates: Requirements 6.2
# ---------------------------------------------------------------------------

from hypothesis import given, settings as hyp_settings
from hypothesis import strategies as st


# Strategy: valid callback status codes (2=ready to save, 6=force save)
valid_callback_status = st.sampled_from([2, 6])

# Strategy: word-template wp_codes
word_template_wp_codes = st.sampled_from([
    "A8-1", "A8-2", "A9-1", "A9-2", "A10-1", "A11-1", "A12-1",
    "A16-1", "A16-2", "A16-3", "A16-4", "A16-5", "A16-6", "A16-7",
    "A17-2-1", "A17-3", "A17-3-1", "A17-4", "A17-6", "A18-1",
    "A26-1", "A26-2", "A26-3", "A26-4", "A27-1",
])


@pytest.mark.asyncio
@hyp_settings(max_examples=5, deadline=None)
@given(status=valid_callback_status, wp_code=word_template_wp_codes)
async def test_property_13_callback_persistence(status, wp_code):
    """**Validates: Requirements 6.2**

    Property 13: OnlyOffice 回调持久化
    For any valid OnlyOffice save callback (status=2 or status=6), the system SHALL:
    - persist the document content to storage/{project_id}/workpapers/{wp_code}.docx
    - update the workpaper's last_modified timestamp to a value ≥ the callback reception time
    """
    import tempfile
    from datetime import datetime, timezone
    from pathlib import Path
    from unittest.mock import AsyncMock, MagicMock, patch

    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient

    from app.core.config import settings as app_settings
    from app.core.database import get_db
    from app.routers.wp_onlyoffice_router import router as oo_router

    with tempfile.TemporaryDirectory() as tmp_dir:
        with patch.object(app_settings, "STORAGE_ROOT", tmp_dir), \
             patch.object(app_settings, "ONLYOFFICE_URL", "http://onlyoffice:8080"), \
             patch.object(app_settings, "ONLYOFFICE_JWT_SECRET", ""):

            project_id = uuid.uuid4()

            # Record time before callback
            time_before = datetime.now(timezone.utc)

            # Mock DB
            fake_wp = MagicMock()
            fake_wp.project_id = project_id
            fake_wp.updated_at = datetime(2020, 1, 1, tzinfo=timezone.utc)
            fake_row = MagicMock()
            fake_row.__getitem__ = lambda self, idx: fake_wp if idx == 0 else wp_code

            fake_wp_result = MagicMock()
            fake_wp_result.first.return_value = fake_row

            fake_proj_result = MagicMock()
            fake_proj_result.scalar.return_value = False

            fake_db = AsyncMock()
            fake_db.execute = AsyncMock(side_effect=[fake_wp_result, fake_proj_result])
            fake_db.commit = AsyncMock()

            new_content = f"PK\x03\x04docx-content-{wp_code}-{status}".encode()

            app = FastAPI()
            app.include_router(oo_router)

            async def _override_db():
                yield fake_db

            app.dependency_overrides[get_db] = _override_db

            wp_id = uuid.uuid4()

            with patch("app.routers.wp_onlyoffice_router.httpx.AsyncClient") as mock_client_cls, \
                 patch("app.services.wp_classification_service._WP_CODE_OVERRIDE", {wp_code: "word-template"}):
                mock_response = MagicMock()
                mock_response.content = new_content
                mock_response.raise_for_status = MagicMock()

                mock_client = AsyncMock()
                mock_client.get = AsyncMock(return_value=mock_response)
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=None)
                mock_client_cls.return_value = mock_client

                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as client:
                    resp = await client.post(
                        f"/api/workpapers/{wp_id}/sheets/__word__/onlyoffice-callback",
                        json={
                            "status": status,
                            "url": f"http://onlyoffice:8080/cached/{wp_code}.docx",
                        },
                    )

                assert resp.status_code == 200
                assert resp.json() == {"error": 0}

            # Property assertion 1: snapshot file exists at expected path
            expected_path = Path(f"storage/{project_id}/workpapers/{wp_code}.docx")
            assert expected_path.exists(), (
                f"Snapshot file should exist at {expected_path} after callback status={status}"
            )
            assert expected_path.read_bytes() == new_content

            # Property assertion 2: last_modified (updated_at) >= time before callback
            assert fake_wp.updated_at >= time_before, (
                f"last_modified ({fake_wp.updated_at}) should be >= callback time ({time_before})"
            )
