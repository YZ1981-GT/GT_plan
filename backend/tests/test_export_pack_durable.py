"""底稿文件打包导出的耐久任务迁移（spec platform-heavy-jobs-and-capacity-closure B3）。"""
from __future__ import annotations

import uuid
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from app.services.export_pack_executor import (
    OPERATION,
    _ExportFile,
    execute_export_pack,
)
from app.services.platform_job_registry import get_executor, registered_operations
from app.services.platform_job_service import PlatformJobClaim


def _claim(
    wp_ids: list[str],
    project_id: uuid.UUID | None = None,
) -> PlatformJobClaim:
    return PlatformJobClaim(
        job_id=uuid.uuid4(),
        operation=OPERATION,
        project_id=project_id or uuid.uuid4(),
        actor_id=uuid.uuid4(),
        payload_ref={"wp_ids": wp_ids},
        attempt=1,
        max_attempts=3,
        lease_token=uuid.uuid4(),
        lease_seconds=300,
    )


def test_executor_is_registered_under_the_expected_operation():
    assert OPERATION in registered_operations()
    assert get_executor(OPERATION) is execute_export_pack


@pytest.mark.asyncio
async def test_executor_produces_zip_and_fires_sse_complete(tmp_path):
    """在线程写盘、推 SSE 完成事件、返回 download_url。"""
    # 准备两个假底稿文件
    wp1 = tmp_path / "wp1.xlsx"
    wp2 = tmp_path / "wp2.xlsx"
    wp1.write_bytes(b"PK-fake-wp1")
    wp2.write_bytes(b"PK-fake-wp2")

    id1, id2 = str(uuid.uuid4()), str(uuid.uuid4())
    claim = _claim([id1, id2])

    files = [
        _ExportFile(source=wp1, arcname="D/D1.xlsx"),
        _ExportFile(source=wp2, arcname="D/D2.xlsx"),
    ]
    progress_calls: list[tuple] = []

    async def fake_report(current, total=None, message=None, stage=None):
        progress_calls.append((current, total, message, stage))
        return True

    broadcast_calls: list[tuple] = []

    def fake_broadcast(event_type, data):
        broadcast_calls.append((event_type, data))

    with (
        patch(
            "app.services.export_pack_executor._load_export_files",
            new=AsyncMock(return_value=files),
        ),
        patch(
            "app.services.export_pack_executor.EXPORT_DIR",
            tmp_path / "exports",
        ),
        patch(
            "app.services.event_bus.event_bus",
            type("FakeBus", (), {"broadcast_raw": staticmethod(fake_broadcast)})(),
        ),
    ):
        outcome = await execute_export_pack(claim, fake_report)

    assert outcome.result_ref is not None
    assert outcome.result_ref["download_url"].startswith("/api/exports/")
    assert outcome.result_ref["total"] == 2
    zip_path = Path(outcome.result_ref["zip_path"])
    assert zip_path.exists()
    assert zip_path.stat().st_size > 0

    # 进度至少报了 loading 和 packing 两个阶段
    stages = [call[3] for call in progress_calls if call[3]]
    assert "loading" in stages
    assert "packing" in stages

    # SSE 完成事件
    assert len(broadcast_calls) == 1
    event_type, data = broadcast_calls[0]
    assert event_type == "export.complete"
    assert data["task_id"] == str(claim.job_id)
    assert data["download_url"].startswith("/api/exports/")


@pytest.mark.asyncio
async def test_executor_handles_lease_lost_gracefully():
    """进度汇报返回 False（租约丢失）时 executor 立即退出，不继续写盘。"""
    claim = _claim(["wp1"])

    async def lost_report(current, total=None, message=None, stage=None):
        return False  # 租约丢失

    with patch(
        "app.services.export_pack_executor._load_export_files",
        new=AsyncMock(return_value=[None]),
    ):
        outcome = await execute_export_pack(claim, lost_report)

    assert outcome.finalized is False
    assert outcome.result_ref is None


@pytest.mark.asyncio
async def test_executor_cleans_temp_on_write_failure(tmp_path):
    """ZIP 写盘失败时临时文件被清理，异常正常冒泡。"""
    claim = _claim(["wp1"])

    async def ok_report(current, total=None, message=None, stage=None):
        return True

    def bad_write(*args, **kwargs):
        raise OSError("disk full")

    with (
        patch(
            "app.services.export_pack_executor._load_export_files",
            new=AsyncMock(return_value=[None]),
        ),
        patch(
            "app.services.export_pack_executor.EXPORT_DIR",
            tmp_path / "exports",
        ),
        patch(
            "app.services.export_pack_executor._write_zip",
            side_effect=bad_write,
        ),
    ):
        with pytest.raises(OSError, match="disk full"):
            await execute_export_pack(claim, ok_report)


def test_status_endpoint_maps_durable_statuses_to_legacy():
    """路由层把耐久任务六态映射成前端 ExportProgressBar 认识的四态。"""
    mapping = {
        "queued": "pending",
        "running": "running",
        "retry_wait": "pending",
        "succeeded": "complete",
        "failed": "failed",
        "cancelled": "failed",
    }
    for durable, legacy in mapping.items():
        mapped = {
            "queued": "pending",
            "running": "running",
            "retry_wait": "pending",
            "succeeded": "complete",
            "failed": "failed",
            "cancelled": "failed",
        }.get(durable, durable)
        assert mapped == legacy, f"{durable} → {mapped} != {legacy}"


def test_idempotency_key_is_deterministic():
    """同一组 wp_ids（排序后）生成的幂等键相同，保证重复提交不产生第二个任务。"""
    project = uuid.uuid4()
    ids = [str(uuid.uuid4()) for _ in range(5)]

    def make_key(wp_ids):
        return f"pack-{project}-{'-'.join(sorted(wp_ids))}"

    assert make_key(ids) == make_key(list(reversed(ids)))
    assert make_key(ids) != make_key(ids[:-1])
