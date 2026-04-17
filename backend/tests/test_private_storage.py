"""Phase 10 Task 3.1-3.3: 私人库+归档+存储统计测试"""

import pytest
import tempfile
import os
from uuid import uuid4
from pathlib import Path
from unittest.mock import patch


class TestPrivateStorageService:

    @pytest.mark.asyncio
    async def test_empty_quota(self):
        from app.services.private_storage_service import PrivateStorageService
        svc = PrivateStorageService()
        with patch.object(svc, '_user_dir', return_value=Path("/nonexistent")):
            result = await svc.check_quota(uuid4())
        assert result["used"] == 0
        assert result["warning"] is False

    @pytest.mark.asyncio
    async def test_upload_and_list(self):
        from app.services.private_storage_service import PrivateStorageService, STORAGE_ROOT
        uid = uuid4()
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("app.services.private_storage_service.STORAGE_ROOT", Path(tmpdir)):
                svc = PrivateStorageService()
                # Upload
                result = await svc.upload_file(uid, "test.txt", b"hello world")
                assert result["name"] == "test.txt"
                assert result["size"] == 11
                # List
                files = await svc.list_files(uid)
                assert len(files) == 1
                assert files[0]["name"] == "test.txt"
                # Quota
                quota = await svc.check_quota(uid)
                assert quota["used"] == 11
                # Delete
                ok = await svc.delete_file(uid, "test.txt")
                assert ok is True
                files2 = await svc.list_files(uid)
                assert len(files2) == 0

    @pytest.mark.asyncio
    async def test_upload_exceeds_quota(self):
        from app.services.private_storage_service import PrivateStorageService
        uid = uuid4()
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("app.services.private_storage_service.STORAGE_ROOT", Path(tmpdir)):
                svc = PrivateStorageService()
                svc.MAX_SIZE_BYTES = 100  # 100 bytes limit
                with pytest.raises(ValueError, match="容量不足"):
                    await svc.upload_file(uid, "big.bin", b"x" * 200)


class TestStorageStatsService:

    @pytest.mark.asyncio
    async def test_empty_stats(self):
        from app.services.private_storage_service import StorageStatsService
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("app.services.private_storage_service.STORAGE_ROOT", Path(tmpdir)):
                svc = StorageStatsService()
                result = await svc.get_stats()
                assert result["total_size"] == 0
                assert result["by_project"] == []
                assert result["by_user"] == []


class TestRouterImport:

    def test_private_storage_router(self):
        from app.routers.private_storage import router
        paths = [r.path for r in router.routes]
        assert any("private-storage" in p for p in paths)

    def test_storage_stats_route(self):
        from app.routers.private_storage import router
        paths = [r.path for r in router.routes]
        assert any("storage-stats" in p for p in paths)
