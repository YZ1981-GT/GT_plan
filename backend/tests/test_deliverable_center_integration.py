"""P1-2: 交付件中心对齐测试

验证：
- P1-2.1: 复用 audit-report-deliverable-center 的版本链
- P1-2.2: 报告、附注、PDF、签发文件进入交付件中心
- P1-2.3: 终态再导出新建版本或交付物
- P1-2.4: 历史版本不可覆盖

Validates: Requirements 4.1, 4.2, 4.3
Property 3：交付件历史不可覆盖
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import pytest

from app.services.deliverable_center_integration import DeliverableCenterIntegration
from app.services.deliverable_service import (
    DeliverableService,
    StoreResult,
    TERMINAL_REEXPORT_STATUSES,
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _make_task(
    task_id: uuid.UUID | None = None,
    project_id: uuid.UUID | None = None,
    doc_type: str = "audit_report",
    status: str = "draft",
):
    task = MagicMock()
    task.id = task_id or uuid.uuid4()
    task.project_id = project_id or uuid.uuid4()
    task.doc_type = doc_type
    task.status = status
    task.file_path = None
    task.html_path = None
    task.file_size = None
    task.source_snapshot_refs = None
    task.selected_sections = None
    task.template_type = None
    task.created_by = uuid.uuid4()
    return task


def _make_version(task_id: uuid.UUID, version_no: int):
    v = MagicMock()
    v.id = uuid.uuid4()
    v.word_export_task_id = task_id
    v.version_no = version_no
    v.file_path = f"/storage/deliverables/{task_id}/report_v{version_no}.docx"
    v.html_path = None
    v.file_size = 12345
    v.created_by = uuid.uuid4()
    v.created_at = datetime.now(timezone.utc)
    return v


# ---------------------------------------------------------------------------
# P1-2.1: 复用版本链
# ---------------------------------------------------------------------------

class TestVersionChainReuse:
    """P1-2.1: 通过 EvidenceRef 引用 deliverable-center 版本"""

    @pytest.mark.asyncio
    async def test_get_version_chain_as_refs(self):
        """版本链以 EvidenceRef 列表返回"""
        db = AsyncMock()
        integration = DeliverableCenterIntegration(db)

        task_id = uuid.uuid4()
        project_id = uuid.uuid4()
        versions = [_make_version(task_id, 1), _make_version(task_id, 2)]

        with patch.object(
            integration._deliverable_svc,
            "get_version_chain",
            return_value=versions,
        ):
            refs = await integration.get_version_chain_as_refs(task_id, project_id)

        assert len(refs) == 2
        assert refs[0]["evidence_type"] == "deliverable"
        assert refs[0]["evidence_id"] == str(task_id)
        assert refs[0]["version"] == "1"
        assert refs[1]["version"] == "2"


# ---------------------------------------------------------------------------
# P1-2.2: 报告/附注/PDF/签发进入交付件中心
# ---------------------------------------------------------------------------

class TestSubmitToDeliverableCenter:
    """P1-2.2: 文件提交到交付件中心并返回 EvidenceRef"""

    @pytest.mark.asyncio
    async def test_submit_returns_evidence_ref(self):
        """提交后返回包含 EvidenceRef 的结果"""
        db = AsyncMock()
        integration = DeliverableCenterIntegration(db)

        task = _make_task(doc_type="audit_report")
        version = _make_version(task.id, 1)
        store_result = StoreResult(
            version=version,
            download_url=f"/api/projects/{task.project_id}/deliverables/{task.id}/versions/1/download",
            platform_persist_failed=False,
        )

        with patch.object(
            integration._deliverable_svc,
            "export_or_new_deliverable",
            return_value=(task, True),
        ), patch.object(
            integration._deliverable_svc,
            "render_and_store",
            return_value=store_result,
        ):
            result = await integration.submit_to_deliverable_center(
                project_id=task.project_id,
                doc_type="audit_report",
                user_id=uuid.uuid4(),
                file_bytes=b"fake docx content",
                file_name="审计报告_2025.docx",
            )

        assert "evidence_ref" in result
        assert result["evidence_ref"]["evidence_type"] == "deliverable"
        assert result["evidence_ref"]["evidence_id"] == str(task.id)
        assert result["version_no"] == 1


# ---------------------------------------------------------------------------
# P1-2.3: 终态再导出
# ---------------------------------------------------------------------------

class TestTerminalReexport:
    """P1-2.3: 终态交付物再导出新建独立交付物"""

    @pytest.mark.asyncio
    async def test_terminal_reexport_creates_new_task(self):
        """终态（confirmed/signed/archived）再导出时新建交付物"""
        db = AsyncMock()
        integration = DeliverableCenterIntegration(db)

        old_task = _make_task(status="signed")
        new_task = _make_task(doc_type="audit_report")
        version = _make_version(new_task.id, 1)
        store_result = StoreResult(
            version=version,
            download_url=f"/api/projects/{new_task.project_id}/deliverables/{new_task.id}/versions/1/download",
        )

        with patch.object(
            integration._deliverable_svc,
            "export_or_new_deliverable",
            return_value=(new_task, True),
        ), patch.object(
            integration._deliverable_svc,
            "render_and_store",
            return_value=store_result,
        ):
            result = await integration.reexport_terminal(
                project_id=old_task.project_id,
                doc_type="audit_report",
                existing_task_id=old_task.id,
                user_id=uuid.uuid4(),
                file_bytes=b"new version content",
            )

        assert result["is_new_task"] is True
        assert result["task_id"] == str(new_task.id)


# ---------------------------------------------------------------------------
# P1-2.4: 历史版本不可覆盖
# ---------------------------------------------------------------------------

class TestVersionImmutability:
    """P1-2.4: Property 3 — 交付件历史不可覆盖

    验证：版本一旦创建，无法通过 create_version 覆盖已有版本号。
    新的导出只能新增 version_no，不能替换已有。
    """

    @pytest.mark.asyncio
    async def test_create_version_always_increments(self):
        """新版本总是 max(version_no) + 1，不可能覆盖"""
        db = AsyncMock()
        svc = DeliverableService(db)

        task_id = uuid.uuid4()
        user_id = uuid.uuid4()

        # 模拟已有 3 个版本
        mock_max_result = MagicMock()
        mock_max_result.scalar_one.return_value = 3
        db.execute = AsyncMock(return_value=mock_max_result)
        db.add = MagicMock()
        db.flush = AsyncMock()

        version = await svc.create_version(
            task_id,
            file_path="/storage/v4.docx",
            html_path=None,
            user_id=user_id,
        )

        # 验证新版本号为 4（不是覆盖 1/2/3）
        added = db.add.call_args[0][0]
        assert added.version_no == 4

    @pytest.mark.asyncio
    async def test_verify_version_immutability_true(self):
        """已存在的版本返回 immutable=True"""
        db = AsyncMock()
        integration = DeliverableCenterIntegration(db)

        version = _make_version(uuid.uuid4(), 2)
        with patch.object(
            integration._deliverable_svc,
            "get_version",
            return_value=version,
        ):
            result = await integration.verify_version_immutability(
                task_id=version.word_export_task_id,
                version_no=2,
            )

        assert result is True

    @pytest.mark.asyncio
    async def test_verify_version_immutability_false_nonexistent(self):
        """不存在的版本返回 False"""
        db = AsyncMock()
        integration = DeliverableCenterIntegration(db)

        with patch.object(
            integration._deliverable_svc,
            "get_version",
            return_value=None,
        ):
            result = await integration.verify_version_immutability(
                task_id=uuid.uuid4(),
                version_no=999,
            )

        assert result is False

    def test_terminal_statuses_include_all_expected(self):
        """确认终态集合包含 confirmed/signed/archived"""
        assert "confirmed" in TERMINAL_REEXPORT_STATUSES
        assert "signed" in TERMINAL_REEXPORT_STATUSES
        assert "archived" in TERMINAL_REEXPORT_STATUSES
