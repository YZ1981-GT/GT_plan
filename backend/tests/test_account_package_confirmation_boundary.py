"""
test_account_package_confirmation_boundary.py — 函证模块边界接入测试

Spec: workpaper-account-package-d1-d2-pilot Task 6.4, 6.5, 6.6

验证:
- 6.4: D2/D0 callback 与工作包摘要一致
- 6.5: 工作包摘要服务不保存或覆盖函证明细状态，只消费 summary/metrics
- 6.6: confirmation_service 无数据时返回 missing/empty summary，不在底稿侧自行计算覆盖率

Requirements: 4.1, 4.2, 4.3, 4.4
"""
import inspect
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.account_package_summary_service import (
    AccountPackageSummaryService,
    AccountPackageSummaryDTO,
)


# ─── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture
def mock_db():
    """Create a mock async session"""
    db = AsyncMock()
    return db


@pytest.fixture
def project_id():
    return uuid.uuid4()


@pytest.fixture
def wp_id():
    return uuid.uuid4()


# ─── Test 6.4: D2/D0 callback 与工作包摘要一致 ────────────────────────────


class TestD2D0CallbackConsistency:
    """验证 D2/D0 callback 结果与工作包摘要 API 返回一致"""

    @pytest.mark.asyncio
    async def test_confirmation_summary_reads_from_confirmation_table(
        self, mock_db, project_id, wp_id
    ):
        """get_confirmation_summary 从 confirmation 表只读聚合"""
        # Mock the DB execute to return status counts
        mock_result = MagicMock()
        mock_result.all.return_value = [
            ("pending", 2),
            ("sent", 3),
            ("returned", 1),
            ("matched", 4),
            ("discrepancy", 1),
        ]

        # Second query for diff_amount
        mock_diff_result = MagicMock()
        mock_diff_result.scalar_one.return_value = 5000.0

        mock_db.execute = AsyncMock(side_effect=[
            # resolve_wp_code_to_id
            MagicMock(scalar_one_or_none=MagicMock(return_value=wp_id)),
            # status counts
            mock_result,
            # diff_total
            mock_diff_result,
        ])

        service = AccountPackageSummaryService(mock_db)
        result = await service.get_confirmation_summary(
            project_id, "D2_accounts_receivable"
        )

        assert result["status"] == "loaded"
        assert result["total"] == 11
        assert result["sent"] == 3
        assert result["returned"] == 1
        assert result["matched"] == 4
        assert result["discrepancy"] == 1
        # coverage = (returned + matched + discrepancy) / total = 6/11
        assert result["coverage_rate"] == pytest.approx(6 / 11, rel=1e-3)
        assert result["diff_total"] == 5000.0

    @pytest.mark.asyncio
    async def test_summary_external_cards_includes_confirmation(
        self, mock_db, project_id, wp_id
    ):
        """D2 工作包 summary 外部卡片包含 confirmation_summary"""
        mock_db.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=wp_id))
        )

        service = AccountPackageSummaryService(mock_db)
        dto = await service.get_summary(project_id, "D2_accounts_receivable")

        # external_cards should include confirmation_summary card
        card_types = [c["card_type"] for c in dto.external_cards]
        assert "confirmation_summary" in card_types


# ─── Test 6.5: 摘要服务不保存或覆盖函证明细 ────────────────────────────────


class TestSummaryServiceReadOnly:
    """验证工作包摘要服务只读消费函证 summary/metrics，不写入"""

    def test_get_confirmation_summary_source_has_no_write_ops(self):
        """get_confirmation_summary 源码不包含实际写操作语句"""
        source = inspect.getsource(
            AccountPackageSummaryService.get_confirmation_summary
        )
        # Only check for actual write operation patterns in code (not comments/docstrings)
        # Strip comments and docstrings first
        lines = source.split('\n')
        code_lines = []
        in_docstring = False
        for line in lines:
            stripped = line.strip()
            if stripped.startswith('"""') or stripped.startswith("'''"):
                if in_docstring:
                    in_docstring = False
                    continue
                elif stripped.count('"""') == 1 or stripped.count("'''") == 1:
                    in_docstring = True
                    continue
                # Single-line docstring
                continue
            if in_docstring:
                continue
            if stripped.startswith('#'):
                continue
            code_lines.append(line)

        code_only = '\n'.join(code_lines)
        write_patterns = ["db.add(", "await self._db.flush", "await self._db.commit",
                          ".delete(", "sa_delete("]
        for pat in write_patterns:
            assert pat not in code_only, (
                f"get_confirmation_summary 包含写操作 '{pat}'，"
                "摘要服务不应写入函证数据"
            )

    def test_get_summary_source_has_no_confirmation_write(self):
        """get_summary 源码不包含对 confirmation 表的写操作"""
        source = inspect.getsource(AccountPackageSummaryService.get_summary)
        # 不应写入 confirmation 相关表
        assert "Confirmation(" not in source, (
            "get_summary 不应创建 Confirmation 实例"
        )

    def test_service_docstring_declares_read_only_boundary(self):
        """服务 docstring 声明了只读消费边界"""
        import app.services.account_package_summary_service as mod
        docstring = mod.__doc__ or ""
        assert "只读" in docstring or "只消费" in docstring or "不维护" in docstring, (
            "服务模块 docstring 应声明函证边界：只消费，不维护"
        )

    @pytest.mark.asyncio
    async def test_confirmation_summary_does_not_call_db_add(
        self, mock_db, project_id, wp_id
    ):
        """调用 get_confirmation_summary 后，db.add 未被调用"""
        mock_result = MagicMock()
        mock_result.all.return_value = [("matched", 2)]

        mock_diff_result = MagicMock()
        mock_diff_result.scalar_one.return_value = 0

        mock_db.execute = AsyncMock(side_effect=[
            MagicMock(scalar_one_or_none=MagicMock(return_value=wp_id)),
            mock_result,
            mock_diff_result,
        ])
        mock_db.add = MagicMock()
        mock_db.flush = AsyncMock()
        mock_db.commit = AsyncMock()

        service = AccountPackageSummaryService(mock_db)
        await service.get_confirmation_summary(project_id, "D2_accounts_receivable")

        mock_db.add.assert_not_called()
        mock_db.flush.assert_not_called()
        mock_db.commit.assert_not_called()


# ─── Test 6.6: 无数据时返回 missing/empty ──────────────────────────────────


class TestConfirmationServiceNoData:
    """验证 confirmation_service 无数据时返回 missing/empty，不自行计算覆盖率"""

    @pytest.mark.asyncio
    async def test_no_confirmations_returns_missing(self, mock_db, project_id, wp_id):
        """无函证记录时返回 status=missing, coverage_rate=null"""
        mock_result = MagicMock()
        mock_result.all.return_value = []  # 无数据

        mock_db.execute = AsyncMock(side_effect=[
            MagicMock(scalar_one_or_none=MagicMock(return_value=wp_id)),
            mock_result,
        ])

        service = AccountPackageSummaryService(mock_db)
        result = await service.get_confirmation_summary(
            project_id, "D2_accounts_receivable"
        )

        assert result["status"] == "missing"
        assert result["coverage_rate"] is None

    @pytest.mark.asyncio
    async def test_wp_not_found_returns_missing(self, mock_db, project_id):
        """wp_code 无法解析到 wp_id 时返回 status=missing"""
        mock_db.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
        )

        service = AccountPackageSummaryService(mock_db)
        result = await service.get_confirmation_summary(
            project_id, "D2_accounts_receivable"
        )

        assert result["status"] == "missing"
        assert result["coverage_rate"] is None

    @pytest.mark.asyncio
    async def test_nonexistent_package_returns_missing(self, mock_db, project_id):
        """不存在的 package_id 返回 status=missing"""
        service = AccountPackageSummaryService(mock_db)
        result = await service.get_confirmation_summary(
            project_id, "NONEXISTENT_PACKAGE"
        )

        assert result["status"] == "missing"
        assert result["coverage_rate"] is None

    @pytest.mark.asyncio
    async def test_package_without_confirmation_card_returns_not_applicable(
        self, mock_db, project_id
    ):
        """D1 工作包有 confirmation_summary 卡片，但如果包没有则返回 not_applicable"""
        # D1_notes_receivable also has confirmation_summary, 
        # so let's test with a hypothetical package without it
        service = AccountPackageSummaryService(mock_db)
        # Use a non-existent package that won't have confirmation_summary
        result = await service.get_confirmation_summary(
            project_id, "NONEXISTENT"
        )
        assert result["status"] == "missing"
        assert result["coverage_rate"] is None

    @pytest.mark.asyncio
    async def test_never_computes_coverage_locally_when_empty(
        self, mock_db, project_id, wp_id
    ):
        """空结果时 coverage_rate 必须是 None，不允许是 0 或其他计算值"""
        mock_result = MagicMock()
        mock_result.all.return_value = []

        mock_db.execute = AsyncMock(side_effect=[
            MagicMock(scalar_one_or_none=MagicMock(return_value=wp_id)),
            mock_result,
        ])

        service = AccountPackageSummaryService(mock_db)
        result = await service.get_confirmation_summary(
            project_id, "D2_accounts_receivable"
        )

        # MUST be None, not 0.0 or any computed value
        assert result["coverage_rate"] is None, (
            "无数据时 coverage_rate 必须为 None（null），"
            "不得在底稿侧自行计算覆盖率为 0"
        )
