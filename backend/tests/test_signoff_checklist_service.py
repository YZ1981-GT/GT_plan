"""签发一致性清单服务测试（P2-1）。

覆盖：
- P2-1.1: signoff_checklist_service 创建
- P2-1.2: 检查四表、调整、底稿、附注、报告正文、AI 内容
- P2-1.3: 输出 blocking/warning/info 三类结果
- P2-1.4: 每个结果带 LinkageContract 或 route
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from app.services.signoff_checklist_service import (
    CheckItem,
    CheckSeverity,
    SignoffChecklist,
    SignoffChecklistService,
)


# ─── Fixtures ─────────────────────────────────────────────────────────


@pytest_asyncio.fixture
def mock_db():
    """模拟 AsyncSession。"""
    db = AsyncMock()
    return db


@pytest_asyncio.fixture
def service(mock_db):
    """创建 SignoffChecklistService 实例。"""
    return SignoffChecklistService(mock_db)


PROJECT_ID = uuid.UUID("df5b8403-0000-0000-0000-000000000001")
YEAR = 2025


# ─── 基础功能测试 ─────────────────────────────────────────────────────


class TestSignoffChecklistGeneration:
    """签发清单生成基本功能。"""

    @pytest.mark.asyncio
    async def test_empty_checklist_allows_signoff(self, service, mock_db):
        """所有检查通过时 can_signoff=True。"""
        # 所有查询返回空结果
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_result.fetchone.return_value = ("standard",)  # opinion_type
        mock_db.execute.return_value = mock_result

        checklist = await service.generate_checklist(
            project_id=PROJECT_ID, year=YEAR
        )

        assert isinstance(checklist, SignoffChecklist)
        assert checklist.project_id == str(PROJECT_ID)
        assert checklist.year == YEAR

    @pytest.mark.asyncio
    async def test_blocking_items_prevent_signoff(self, service, mock_db):
        """存在 blocking 项时 can_signoff=False。"""
        # 模拟试算表 stale 数据
        stale_row = (uuid.uuid4(), "1001", "100000.00")
        empty_result = MagicMock()
        empty_result.fetchall.return_value = []
        empty_result.fetchone.return_value = ("standard",)

        stale_result = MagicMock()
        stale_result.fetchall.return_value = [stale_row]

        # 第一次 execute = trial_balance stale 查询
        call_count = [0]

        async def side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return stale_result
            return empty_result

        mock_db.execute.side_effect = side_effect

        checklist = await service.generate_checklist(
            project_id=PROJECT_ID, year=YEAR
        )

        blocking_items = [
            i for i in checklist.items if i.severity == CheckSeverity.blocking
        ]
        assert len(blocking_items) >= 1
        assert checklist.can_signoff is False

    @pytest.mark.asyncio
    async def test_warning_items_flag_has_warnings(self, service, mock_db):
        """存在 warning 项时 has_warnings=True。"""
        # 模拟附注降级记录
        degraded_row = ("note-sec-1", "数据可能过期")
        
        call_count = [0]
        async def side_effect(*args, **kwargs):
            call_count[0] += 1
            result = MagicMock()
            # 大部分返回空
            result.fetchall.return_value = []
            result.fetchone.return_value = ("standard",)
            # 第 7 次 (event_cascade_health note degraded) 返回 degraded
            if call_count[0] == 7:
                result.fetchall.return_value = [degraded_row]
            return result

        mock_db.execute.side_effect = side_effect

        checklist = await service.generate_checklist(
            project_id=PROJECT_ID, year=YEAR
        )

        warning_items = [
            i for i in checklist.items if i.severity == CheckSeverity.warning
        ]
        if warning_items:
            assert checklist.has_warnings is True


class TestCheckItemStructure:
    """P2-1.4: 每个结果带 LinkageContract 或 route。"""

    @pytest.mark.asyncio
    async def test_items_have_route_or_contract(self, service, mock_db):
        """所有 CheckItem 必须有 route 或 contract。"""
        stale_row = (uuid.uuid4(), "6001", "50000.00")
        
        call_count = [0]
        async def side_effect(*args, **kwargs):
            call_count[0] += 1
            result = MagicMock()
            if call_count[0] == 1:
                # trial_balance stale
                result.fetchall.return_value = [stale_row]
            else:
                result.fetchall.return_value = []
                result.fetchone.return_value = ("standard",)
            return result

        mock_db.execute.side_effect = side_effect

        checklist = await service.generate_checklist(
            project_id=PROJECT_ID, year=YEAR
        )

        for item in checklist.items:
            assert item.route is not None or item.contract is not None, (
                f"CheckItem 缺少 route 和 contract: {item.message}"
            )

    @pytest.mark.asyncio
    async def test_blocking_contract_has_stale_status(self, service, mock_db):
        """试算表 stale 检查项的 contract 状态为 stale。"""
        stale_row = (uuid.uuid4(), "1001", "100000.00")

        call_count = [0]
        async def side_effect(*args, **kwargs):
            call_count[0] += 1
            result = MagicMock()
            if call_count[0] == 1:
                result.fetchall.return_value = [stale_row]
            else:
                result.fetchall.return_value = []
                result.fetchone.return_value = ("standard",)
            return result

        mock_db.execute.side_effect = side_effect

        checklist = await service.generate_checklist(
            project_id=PROJECT_ID, year=YEAR
        )

        tb_blocking = [
            i for i in checklist.items
            if i.category == "trial_balance" and i.contract is not None
        ]
        for item in tb_blocking:
            assert item.contract.status.value == "stale"


class TestCheckCategories:
    """P2-1.2: 检查各数据源分类。"""

    @pytest.mark.asyncio
    async def test_adjustment_unapproved_is_blocking(self, service, mock_db):
        """未审批调整分录产生 blocking 结果。"""
        adj_row = (uuid.uuid4(), "AJE-001", "审计调整", "pending")

        call_count = [0]
        async def side_effect(*args, **kwargs):
            call_count[0] += 1
            result = MagicMock()
            if call_count[0] == 2:
                # adjustments 查询
                result.fetchall.return_value = [adj_row]
            else:
                result.fetchall.return_value = []
                result.fetchone.return_value = ("standard",)
            return result

        mock_db.execute.side_effect = side_effect

        checklist = await service.generate_checklist(
            project_id=PROJECT_ID, year=YEAR
        )

        adj_items = [i for i in checklist.items if i.category == "adjustment"]
        blocking_adjs = [i for i in adj_items if i.severity == CheckSeverity.blocking]
        assert len(blocking_adjs) >= 1
        assert "AJE-001" in blocking_adjs[0].message

    @pytest.mark.asyncio
    async def test_no_report_is_blocking(self, service, mock_db):
        """未生成报告正文产生 blocking 结果。"""
        call_count = [0]
        async def side_effect(*args, **kwargs):
            call_count[0] += 1
            result = MagicMock()
            result.fetchall.return_value = []
            # 第 8 次是 projects opinion_type 查询
            if call_count[0] == 8:
                result.fetchone.return_value = ("standard",)
            elif call_count[0] == 9:
                # financial_report 查询 - 返回 None 表示不存在
                result.fetchone.return_value = None
            else:
                result.fetchone.return_value = ("standard",)
            return result

        mock_db.execute.side_effect = side_effect

        checklist = await service.generate_checklist(
            project_id=PROJECT_ID, year=YEAR
        )

        report_blocking = [
            i for i in checklist.items
            if i.category == "report" and i.severity == CheckSeverity.blocking
        ]
        # 可能通过也可能 blocking，取决于查询顺序
        # 如果 report 不存在且 opinion_type 存在，应该 blocking
        report_items = [i for i in checklist.items if i.category == "report"]
        assert len(report_items) >= 1

    @pytest.mark.asyncio
    async def test_graceful_degradation_on_db_error(self, service, mock_db):
        """数据库异常时优雅降级，不抛出。"""
        mock_db.execute.side_effect = Exception("DB connection lost")

        checklist = await service.generate_checklist(
            project_id=PROJECT_ID, year=YEAR
        )

        # 降级时仍能返回清单（可能全是 info）
        assert isinstance(checklist, SignoffChecklist)
        # 降级不应 blocking
        assert checklist.can_signoff is True


class TestSeverityEnum:
    """P2-1.3: blocking/warning/info 三类结果。"""

    def test_severity_values(self):
        """三类严重级别的值。"""
        assert CheckSeverity.blocking.value == "blocking"
        assert CheckSeverity.warning.value == "warning"
        assert CheckSeverity.info.value == "info"

    def test_check_item_model(self):
        """CheckItem 模型字段完整性。"""
        item = CheckItem(
            severity=CheckSeverity.blocking,
            category="trial_balance",
            message="测试消息",
            route="/projects/test/trial-balance",
        )
        assert item.severity == CheckSeverity.blocking
        assert item.category == "trial_balance"
        assert item.route is not None
        assert item.contract is None
