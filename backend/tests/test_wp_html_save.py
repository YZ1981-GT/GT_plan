"""Tests for POST /api/workpapers/{wp_id}/save endpoint.

Validates: Requirements 2.2 原则 4（决策可追踪）+ 3.11.4（跨底稿引用传播）
"""

from __future__ import annotations

import contextlib
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User, UserRole
from app.routers.wp_html_save import router
from app.services.cross_ref_service import CrossRefChange, CrossRefService
from app.services.workpaper_sync.artifacts import PublishedArtifact
from app.services.workpaper_sync.content_mutation import (
    HTML_ONLY_ENTRY_PREFIX,
    HtmlOnlyCommitPlan,
    HtmlOnlyCommitReceipt,
    StagedHtmlProjection,
)
from app.services.workpaper_sync.entry_profile import Capability
from app.services.workpaper_sync.models import (
    ArtifactKind,
    ArtifactState,
    RevisionConflictError,
)


# ─── Fixtures ────────────────────────────────────────────────────────────────

_USER_ID = uuid.uuid4()
_WP_ID = uuid.uuid4()
_PROJECT_ID = uuid.uuid4()


class _FakeUser:
    id = _USER_ID
    username = "test_user"
    role = UserRole.admin


class _FakeWorkingPaper:
    """Simulates a WorkingPaper ORM object.

    ``file_version`` / ``prefill_stale`` 是 ``WorkingPaper`` 的真实列，也是
    ``WorkpaperSaveOrchestrator.after_save`` 第 2/3 步读写的两个字段。它们原来缺席仍能
    通过，只因为 ``wp_html_save`` 把整个 after_save 包在 ``except Exception →
    logger.warning`` 里 —— 替身缺列抛的 ``AttributeError`` 被吞掉，测试实际断言的是
    "后处理整段被跳过后接口仍返回 200"。Requirement 13.4 禁止这种 best-effort 降级，
    该 except 已被移除（spec workpaper-html-onlyoffice-bidirectional-writeback-closure
    Task 16），替身必须补齐这两列才是对 ORM 的忠实模拟。

    Task 18 又补两列：``content_revision`` 与 ``current_content_version_id``。它们是
    V151 给 ``working_paper`` 加的真实列，也是本端点新的乐观锁域与 parent version 来源
    （Requirement 2.1）。
    """

    def __init__(
        self,
        parsed_data=None,
        is_deleted=False,
        file_version=0,
        content_revision=0,
        current_content_version_id=None,
    ):
        self.id = _WP_ID
        self.project_id = _PROJECT_ID
        self.parsed_data = parsed_data
        self.is_deleted = is_deleted
        self.updated_by = None
        self.updated_at = None
        self.file_version = file_version
        self.prefill_stale = False
        self.content_revision = content_revision
        self.current_content_version_id = current_content_version_id


# ─── `single_html` lane 替身 ─────────────────────────────────────────────────
#
# 本文件是**路由层**用例：校验、409/422 分支、cross_ref 联动与响应体形态。业务
# commit 的真实语义（一次 revision CAS、单事务、单次 commit、并发裁决）由真库用例
# `workpaper_sync/test_task18_html_save_unified_revision_pg.py` 验证 —— 那里跑真
# PostgreSQL，因为 `_TransactionWitness` 的判据是 `pg_current_xact_id()`，在 mock
# session 上根本不可判定。
#
# 这个替身记录每一次 stage/commit 调用，因此本文件能断言 Task 18 的路由侧承诺：
# 「一次保存恰调用一次 commit_html_projection」「plan 的 expected_revision 取自
# content_revision」「capability 声明为 single_html」。


class _RecordingHtmlLane:
    """记录 stage/commit 调用的 `ContentMutationService` 替身。"""

    def __init__(self, wp: _FakeWorkingPaper, *, conflict: bool = False) -> None:
        self._wp = wp
        self._conflict = conflict
        self.staged_calls: list[tuple[HtmlOnlyCommitPlan, dict]] = []
        self.commit_calls: list[HtmlOnlyCommitPlan] = []

    def stage_html_projection(self, *, plan, html_data):
        self.staged_calls.append((plan, dict(html_data)))
        return StagedHtmlProjection(
            artifact=PublishedArtifact(
                kind=ArtifactKind.projection,
                state=ArtifactState.published,
                path=Path("/tmp/fake.projection.json"),
                relative_path=(
                    f"storage/{plan.project_id}/workpapers/.versions/{plan.wp_id}"
                    f"/content/{plan.target_revision:09d}-abc123abc123.projection.json"
                ),
                sha256="a" * 64,
                size_bytes=42,
                document_type="json.gz",
                reused=False,
                verified_before_publish=True,
                verified_after_publish=True,
            ),
            payload_sha256="a" * 64,
            payload_bytes=42,
            revision=plan.target_revision,
        )

    async def commit_html_projection(self, *, plan, staged):
        self.commit_calls.append(plan)
        if self._conflict:
            raise RevisionConflictError(
                f"business revision 乐观锁失败：expected={plan.expected_revision}"
            )
        # 真实 lane 在这一步做 CAS；替身直接把 fake ORM 的列推到目标值，让路由层能
        # 断言"响应里的 data_version 来自 receipt，而不是请求开始时算的期望值"。
        self._wp.content_revision = plan.target_revision
        return HtmlOnlyCommitReceipt(
            wp_id=plan.wp_id,
            entry_id=plan.entry_id,
            content_version_id=uuid.uuid4(),
            revision=plan.target_revision,
            projection_sha256=staged.artifact.sha256,
            authority_model=plan.authority_model.value,
            commit_count=1,
            transaction_ids=("4242",),
            pending_event=None,
            event_payload={},
        )


@contextlib.contextmanager
def _patched_lane(wp: _FakeWorkingPaper, *, conflict: bool = False):
    """把 `single_html` lane 与提交后发布替换成可观察替身。"""
    lane = _RecordingHtmlLane(wp, conflict=conflict)
    outbox = MagicMock()
    outbox.publish_pending = AsyncMock()
    with (
        patch(
            "app.routers.wp_html_save.build_html_content_mutation_service",
            return_value=lane,
        ),
        patch("app.routers.wp_html_save.DurableEventOutboxService", outbox),
    ):
        yield lane, outbox


def _make_app() -> FastAPI:
    """Create a minimal FastAPI app with the save router."""
    app = FastAPI()
    app.include_router(router)

    async def _user():
        return _FakeUser()

    app.dependency_overrides[get_current_user] = _user
    return app


# ─── Unit tests for CrossRefService ─────────────────────────────────────────


class TestCrossRefService:
    """Test cross_ref_service.detect_changes logic."""

    def test_no_references_returns_empty(self):
        svc = CrossRefService()
        svc._references = []
        result = svc.detect_changes("D2", "sheet1", None, {"rows": []})
        assert result == []

    def test_first_save_with_matching_ref(self):
        svc = CrossRefService()
        svc._references = [
            {
                "ref_id": "CW-001",
                "source_wp": "D2",
                "source_sheet": "sheet1",
                "target_wp": "A1",
                "target_sheet": "BS",
                "target_cell": "B7",
            }
        ]
        result = svc.detect_changes("D2", "sheet1", None, {"rows": [1, 2]})
        assert len(result) == 1
        assert result[0].ref_id == "CW-001"
        assert result[0].target_wp_code == "A1"

    def test_no_change_returns_empty(self):
        svc = CrossRefService()
        svc._references = [
            {
                "ref_id": "CW-001",
                "source_wp": "D2",
                "source_sheet": "sheet1",
                "target_wp": "A1",
            }
        ]
        same_data = {"rows": [1, 2]}
        result = svc.detect_changes("D2", "sheet1", same_data, same_data)
        assert result == []

    def test_data_change_with_matching_ref(self):
        svc = CrossRefService()
        svc._references = [
            {
                "ref_id": "CW-002",
                "source_wp": "D2",
                "target_wp": "E1",
                "target_sheet": "控制测试",
            }
        ]
        old = {"rows": [1]}
        new = {"rows": [1, 2]}
        result = svc.detect_changes("D2", "sheet1", old, new)
        assert len(result) == 1
        assert result[0].target_wp_code == "E1"

    def test_unrelated_wp_code_not_matched(self):
        svc = CrossRefService()
        svc._references = [
            {
                "ref_id": "CW-003",
                "source_wp": "E1",
                "target_wp": "A1",
            }
        ]
        result = svc.detect_changes("D2", "sheet1", None, {"rows": []})
        assert result == []

    def test_changed_cells_filter(self):
        svc = CrossRefService()
        svc._references = [
            {
                "ref_id": "CW-004",
                "source_wp": "D2",
                "source_cell": "B17",
                "target_wp": "A1",
            }
        ]
        # changed_cells does NOT include B17
        result = svc.detect_changes(
            "D2", "sheet1", None, {"rows": []}, changed_cells=["C5", "D10"]
        )
        assert result == []

        # changed_cells includes B17
        result = svc.detect_changes(
            "D2", "sheet1", None, {"rows": []}, changed_cells=["B17", "C5"]
        )
        assert len(result) == 1

    def test_source_sheet_filter(self):
        svc = CrossRefService()
        svc._references = [
            {
                "ref_id": "CW-005",
                "source_wp": "D2",
                "source_sheet": "审定表D2-1",
                "target_wp": "A1",
            }
        ]
        # Different sheet name
        result = svc.detect_changes("D2", "程序表D2A", None, {"rows": []})
        assert result == []

        # Matching sheet name
        result = svc.detect_changes("D2", "审定表D2-1", None, {"rows": []})
        assert len(result) == 1

    def test_to_dict(self):
        change = CrossRefChange(
            ref_id="CW-001",
            source_wp_code="D2",
            source_sheet="sheet1",
            target_wp_code="A1",
            target_sheet="BS",
            target_cell="B7",
        )
        d = change.to_dict()
        assert d["ref_id"] == "CW-001"
        assert d["source_wp_code"] == "D2"
        assert d["target_wp_code"] == "A1"


# ─── Endpoint integration tests ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_save_404_when_wp_not_found():
    """Non-existent wp_id returns 404."""
    app = _make_app()

    # Mock db that returns no working paper
    mock_db = AsyncMock(spec=AsyncSession)
    mock_result = MagicMock()
    mock_scalars = MagicMock()
    mock_scalars.first.return_value = None
    mock_result.scalars.return_value = mock_scalars
    mock_db.execute.return_value = mock_result

    async def _db():
        yield mock_db

    app.dependency_overrides[get_db] = _db

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            f"/api/workpapers/{uuid.uuid4()}/save",
            json={
                "sheet_name": "测试sheet",
                "html_data": {"rows": []},
                "schema_version": "v2025-R5",
            },
        )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_save_409_schema_version_conflict():
    """schema_version mismatch returns 409."""
    app = _make_app()

    fake_wp = _FakeWorkingPaper(parsed_data={"schema_version": "v2025-R5"})

    mock_db = AsyncMock(spec=AsyncSession)
    mock_result = MagicMock()
    mock_scalars = MagicMock()
    mock_scalars.first.return_value = fake_wp
    mock_result.scalars.return_value = mock_scalars
    mock_db.execute.return_value = mock_result

    async def _db():
        yield mock_db

    app.dependency_overrides[get_db] = _db

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            f"/api/workpapers/{_WP_ID}/save",
            json={
                "sheet_name": "测试sheet",
                "html_data": {"rows": []},
                "schema_version": "v2024-R3",  # Different version
            },
        )
    assert resp.status_code == 409
    data = resp.json()
    assert data["detail"]["error"] == "schema_version_conflict"
    assert data["detail"]["server_version"] == "v2025-R5"
    assert data["detail"]["client_version"] == "v2024-R3"


@pytest.mark.asyncio
async def test_save_422_empty_sheet_name():
    """Empty sheet_name returns 422."""
    app = _make_app()

    fake_wp = _FakeWorkingPaper(parsed_data={})

    mock_db = AsyncMock(spec=AsyncSession)
    mock_result = MagicMock()
    mock_scalars = MagicMock()
    mock_scalars.first.return_value = fake_wp
    mock_result.scalars.return_value = mock_scalars
    mock_db.execute.return_value = mock_result

    async def _db():
        yield mock_db

    app.dependency_overrides[get_db] = _db

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            f"/api/workpapers/{_WP_ID}/save",
            json={
                "sheet_name": "   ",
                "html_data": {"rows": []},
                "schema_version": "v2025-R5",
            },
        )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_save_200_success():
    """Successful save returns 200 with saved_at."""
    app = _make_app()

    fake_wp = _FakeWorkingPaper(parsed_data={"schema_version": "v2025-R5"})

    # We need to mock multiple db.execute calls
    call_count = [0]

    mock_db = AsyncMock(spec=AsyncSession)

    def _execute_side_effect(*args, **kwargs):
        call_count[0] += 1
        mock_result = MagicMock()
        if call_count[0] == 1:
            # First call: SELECT working_paper
            mock_scalars = MagicMock()
            mock_scalars.first.return_value = fake_wp
            mock_result.scalars.return_value = mock_scalars
        elif call_count[0] == 2:
            # Second call: get_wp_code_for_wp_id
            mock_result.scalar_one_or_none.return_value = "D2"
        else:
            # Third call: UPDATE
            pass
        return mock_result

    mock_db.execute.side_effect = _execute_side_effect
    mock_db.commit = AsyncMock()

    async def _db():
        yield mock_db

    app.dependency_overrides[get_db] = _db

    with patch(
        "app.routers.wp_html_save.cross_ref_service"
    ) as mock_crs:
        mock_crs.get_wp_code_for_wp_id = AsyncMock(return_value="D2")
        mock_crs.detect_changes.return_value = []

        with _patched_lane(fake_wp) as (lane, outbox):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as ac:
                resp = await ac.post(
                    f"/api/workpapers/{_WP_ID}/save",
                    json={
                        "sheet_name": "应收账款实质性程序表D2A",
                        "html_data": {"rows": [{"cell": "B17", "value": 100}]},
                        "schema_version": "v2025-R5",
                    },
                )

    assert resp.status_code == 200
    data = resp.json()
    assert "saved_at" in data
    assert data["stale_impact"] == []
    # 后处理必须真的跑过，而不是被 except 吞掉后接口照样 200（Requirement 13.4）。
    # 断言落在 after_save 的可观察写入上：只看 200 的话，把 after_save 整段删掉或重新
    # 包上 `except Exception: logger.warning` 都仍然绿。
    assert fake_wp.prefill_stale is True, "after_save 未执行：prefill_stale 未置位"
    assert fake_wp.updated_at is not None, "after_save 未执行：updated_at 未写"
    # 🔴 Task 18：after_save 不再动 file_version（Requirement 2.12）。这条断言从
    #    「递增了」翻成「没动」，与生产改动同向。file_version 的所有者是**真正写文件**
    #    的三条路径（univer / OO callback / custom 回写），HTML save 不写文件。
    assert fake_wp.file_version == 0, (
        "HTML save 不写文件，不该推进 file_version（Requirement 2.1）"
    )

    # ─── Task 18：恰一次 business revision ───────────────────────────────
    assert len(lane.commit_calls) == 1, (
        f"一次 single_html 保存必须恰调一次 commit_html_projection，实得 "
        f"{len(lane.commit_calls)}"
    )
    assert len(lane.staged_calls) == 1
    plan = lane.commit_calls[0]
    assert plan.expected_revision == 0, "expected_revision 必须取自 content_revision"
    assert plan.target_revision == 1
    assert plan.capability is Capability.single_html
    assert plan.entry_id.startswith(HTML_ONLY_ENTRY_PREFIX)
    assert plan.sheet_name == "应收账款实质性程序表D2A"
    assert data["data_version"] == 1, "响应回传的是 CAS 实际推进到的 content_revision"
    assert data["content_version_id"], "响应必须带 immutable content version id"
    # 发布必须发生（Requirement 13.1；次序判据在 task16 wiring 守卫里按行号断言）
    outbox.publish_pending.assert_awaited_once()


@pytest.mark.asyncio
async def test_save_200_with_cross_ref_changes():
    """Save with cross-ref changes returns stale_impact list."""
    app = _make_app()

    fake_wp = _FakeWorkingPaper(
        parsed_data={
            "schema_version": "v2025-R5",
            "html_data": {"程序表D2A": {"rows": [{"cell": "B17", "value": 50}]}},
        }
    )

    call_count = [0]
    mock_db = AsyncMock(spec=AsyncSession)

    def _execute_side_effect(*args, **kwargs):
        call_count[0] += 1
        mock_result = MagicMock()
        if call_count[0] == 1:
            mock_scalars = MagicMock()
            mock_scalars.first.return_value = fake_wp
            mock_result.scalars.return_value = mock_scalars
        elif call_count[0] == 2:
            mock_result.scalar_one_or_none.return_value = "D2"
        else:
            pass
        return mock_result

    mock_db.execute.side_effect = _execute_side_effect
    mock_db.commit = AsyncMock()

    async def _db():
        yield mock_db

    app.dependency_overrides[get_db] = _db

    mock_changes = [
        CrossRefChange(
            ref_id="CW-136",
            source_wp_code="D2",
            source_sheet="程序表D2A",
            target_wp_code="A1",
            target_sheet="BS",
            target_cell="B7",
        )
    ]

    with patch(
        "app.routers.wp_html_save.cross_ref_service"
    ) as mock_crs:
        mock_crs.get_wp_code_for_wp_id = AsyncMock(return_value="D2")
        mock_crs.detect_changes.return_value = mock_changes

        with (
            patch("app.routers.wp_html_save._publish_cross_ref_updated") as mock_pub,
            _patched_lane(fake_wp),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as ac:
                resp = await ac.post(
                    f"/api/workpapers/{_WP_ID}/save",
                    json={
                        "sheet_name": "程序表D2A",
                        "html_data": {"rows": [{"cell": "B17", "value": 100}]},
                        "schema_version": "v2025-R5",
                    },
                )

            # Verify SSE was published
            mock_pub.assert_called_once()
            call_args = mock_pub.call_args
            assert call_args[1]["source_wp_code"] == "D2"
            assert "A1" in call_args[1]["affected_targets"]

    assert resp.status_code == 200
    data = resp.json()
    assert len(data["stale_impact"]) == 1
    assert data["stale_impact"][0]["ref_id"] == "CW-136"
    assert data["stale_impact"][0]["target_wp_code"] == "A1"


@pytest.mark.asyncio
async def test_save_schema_version_none_allows_any():
    """When server has no schema_version yet, any version is accepted."""
    app = _make_app()

    # parsed_data without schema_version
    fake_wp = _FakeWorkingPaper(parsed_data={"html_data": {}})

    call_count = [0]
    mock_db = AsyncMock(spec=AsyncSession)

    def _execute_side_effect(*args, **kwargs):
        call_count[0] += 1
        mock_result = MagicMock()
        if call_count[0] == 1:
            mock_scalars = MagicMock()
            mock_scalars.first.return_value = fake_wp
            mock_result.scalars.return_value = mock_scalars
        elif call_count[0] == 2:
            mock_result.scalar_one_or_none.return_value = "D2"
        else:
            pass
        return mock_result

    mock_db.execute.side_effect = _execute_side_effect
    mock_db.commit = AsyncMock()

    async def _db():
        yield mock_db

    app.dependency_overrides[get_db] = _db

    with patch(
        "app.routers.wp_html_save.cross_ref_service"
    ) as mock_crs:
        mock_crs.get_wp_code_for_wp_id = AsyncMock(return_value="D2")
        mock_crs.detect_changes.return_value = []

        with _patched_lane(fake_wp):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as ac:
                resp = await ac.post(
                    f"/api/workpapers/{_WP_ID}/save",
                    json={
                        "sheet_name": "新sheet",
                        "html_data": {"rows": []},
                        "schema_version": "v2025-R5",
                    },
                )

    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_save_409_data_version_conflict():
    """data_version mismatch returns 409 with conflict info.

    **Validates: Requirements 2.1**

    🔴 Task 18：服务端版本取自 ``working_paper.content_revision``，不再是
    ``parsed_data['_version']``。这里刻意让两者**不同**（``_version`` 是 99 的历史
    脏数据，``content_revision`` 是 3）：如果比对目标退回 ``_version``，客户端发
    ``data_version=2`` 就会被判成"和 99 不符"，``server_version`` 会回 99 —— 断言
    落在回传值上，所以这条能把"读错域"直接照出来。
    """
    app = _make_app()

    fake_wp = _FakeWorkingPaper(
        parsed_data={"schema_version": "v2025-R5", "_version": 99},
        content_revision=3,
    )

    mock_db = AsyncMock(spec=AsyncSession)
    mock_result = MagicMock()
    mock_scalars = MagicMock()
    mock_scalars.first.return_value = fake_wp
    mock_result.scalars.return_value = mock_scalars
    mock_db.execute.return_value = mock_result

    async def _db():
        yield mock_db

    app.dependency_overrides[get_db] = _db

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            f"/api/workpapers/{_WP_ID}/save",
            json={
                "sheet_name": "测试sheet",
                "html_data": {"rows": []},
                "schema_version": "v2025-R5",
                "data_version": 2,  # Client has older version
            },
        )
    assert resp.status_code == 409
    data = resp.json()
    assert data["detail"]["error"] == "data_version_conflict"
    assert data["detail"]["server_version"] == 3
    assert data["detail"]["client_version"] == 2


@pytest.mark.asyncio
async def test_save_200_force_overwrite_bypasses_version_check():
    """force_overwrite=True bypasses the early data_version check.

    **Validates: Requirements 2.1**

    注意 ``force_overwrite`` 只跳过 Step 2b 那道**早检查**；事务内的 CAS 仍然按
    服务端当前 ``content_revision`` 走（这里 3 → 4），所以"强制覆盖"不等于"绕过
    并发保护"，只是"不因客户端拿着旧号就拒绝"。
    """
    app = _make_app()

    fake_wp = _FakeWorkingPaper(
        parsed_data={"schema_version": "v2025-R5", "_version": 99},
        content_revision=3,
    )

    call_count = [0]
    mock_db = AsyncMock(spec=AsyncSession)

    def _execute_side_effect(*args, **kwargs):
        call_count[0] += 1
        mock_result = MagicMock()
        if call_count[0] == 1:
            mock_scalars = MagicMock()
            mock_scalars.first.return_value = fake_wp
            mock_result.scalars.return_value = mock_scalars
        elif call_count[0] == 2:
            mock_result.scalar_one_or_none.return_value = "D2"
        else:
            pass
        return mock_result

    mock_db.execute.side_effect = _execute_side_effect
    mock_db.commit = AsyncMock()

    async def _db():
        yield mock_db

    app.dependency_overrides[get_db] = _db

    with patch(
        "app.routers.wp_html_save.cross_ref_service"
    ) as mock_crs:
        mock_crs.get_wp_code_for_wp_id = AsyncMock(return_value="D2")
        mock_crs.detect_changes.return_value = []

        with _patched_lane(fake_wp) as (lane, _outbox):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as ac:
                resp = await ac.post(
                    f"/api/workpapers/{_WP_ID}/save",
                    json={
                        "sheet_name": "测试sheet",
                        "html_data": {"rows": []},
                        "schema_version": "v2025-R5",
                        "data_version": 2,  # Older version
                        "force_overwrite": True,  # Force overwrite
                    },
                )

    assert resp.status_code == 200
    data = resp.json()
    assert data["data_version"] == 4  # content_revision 3 + 1
    assert len(lane.commit_calls) == 1, "force_overwrite 也只许恰一次 revision"
    assert lane.commit_calls[0].expected_revision == 3, (
        "force_overwrite 跳过的是早检查，CAS 仍按服务端当前 content_revision 走"
    )


@pytest.mark.asyncio
async def test_save_409_when_the_cas_loses_a_real_race():
    """CAS 命中 0 行（真并发）必须回 409，而不是 500。

    **Validates: Requirements 2.1**

    Step 2b 的早检查读的是请求开始时的快照，两个请求可以同时通过它；真正的裁决在
    事务内那条 ``UPDATE ... WHERE content_revision = :expected``。这条用例证明
    ``RevisionConflictError`` 被翻译成用户可行动的 409，没有漏成未捕获异常。
    """
    app = _make_app()

    fake_wp = _FakeWorkingPaper(
        parsed_data={"schema_version": "v2025-R5"}, content_revision=5
    )

    call_count = [0]
    mock_db = AsyncMock(spec=AsyncSession)

    def _execute_side_effect(*args, **kwargs):
        call_count[0] += 1
        mock_result = MagicMock()
        if call_count[0] == 1:
            mock_scalars = MagicMock()
            mock_scalars.first.return_value = fake_wp
            mock_result.scalars.return_value = mock_scalars
        return mock_result

    mock_db.execute.side_effect = _execute_side_effect

    async def _db():
        yield mock_db

    app.dependency_overrides[get_db] = _db

    with patch("app.routers.wp_html_save.cross_ref_service") as mock_crs:
        mock_crs.get_wp_code_for_wp_id = AsyncMock(return_value="D2")
        mock_crs.detect_changes.return_value = []

        with _patched_lane(fake_wp, conflict=True):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as ac:
                resp = await ac.post(
                    f"/api/workpapers/{_WP_ID}/save",
                    json={
                        "sheet_name": "测试sheet",
                        "html_data": {"rows": []},
                        "schema_version": "v2025-R5",
                    },
                )

    assert resp.status_code == 409
    detail = resp.json()["detail"]
    assert detail["error"] == "data_version_conflict"
    assert detail["server_version"] == 5
