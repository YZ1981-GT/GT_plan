"""后端集成测试：截止测试自动提取完整流程

测试场景：
- 完整流程：seed → extract → fill → history → undo → verify
- 安全隔离：项目A数据不可被项目B查询
- 分页：page=1 size=10 返回前10条
- 空结果：条件过严返回 0 条
- Dataset 可见性：仅 active dataset 可见

**Validates: Requirements 2.1, 2.2, 2.3, 2.12, 5.5, 5.6**
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.database import get_db
from app.deps import get_current_user
from app.models.base import UserRole
from app.routers.cutoff_sampling import router

# ─── Constants ────────────────────────────────────────────────────────────────

_USER_ID = uuid.uuid4()
_PROJECT_A_ID = uuid.uuid4()
_PROJECT_B_ID = uuid.uuid4()
_WORKPAPER_ID = uuid.uuid4()
_LOG_ID = uuid.uuid4()


# ─── Fake User ────────────────────────────────────────────────────────────────


class _FakeUser:
    id = _USER_ID
    username = "审计助理李四"
    role = UserRole.auditor


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _make_app(service_mock=None) -> FastAPI:
    """Create minimal FastAPI app with router and mocked deps."""
    app = FastAPI()
    app.include_router(router)

    mock_db = AsyncMock()

    async def _override_db():
        yield mock_db

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = lambda: _FakeUser()
    return app, mock_db


def _make_ledger_rows(count: int, project_id: uuid.UUID, start_date: date = None):
    """Generate fake ledger row dicts as returned by execute_with_stats."""
    if start_date is None:
        start_date = date(2025, 12, 28)
    items = []
    for i in range(count):
        items.append({
            "id": str(uuid.uuid4()),
            "voucher_date": (start_date + timedelta(days=i % 15)).isoformat(),
            "voucher_no": f"记-2025-{1000 + i:04d}",
            "account_code": "112201",
            "account_name": "应收账款-客户A",
            "voucher_type": "记" if i % 2 == 0 else "收",
            "debit_amount": str(Decimal(f"{(i + 1) * 1000}.00")) if i % 2 == 0 else None,
            "credit_amount": str(Decimal(f"{(i + 1) * 500}.00")) if i % 2 != 0 else None,
            "counterpart_account": "600101",
            "summary": f"测试摘要{i}",
            "entry_seq": i + 1,
            "accounting_period": 12,
            "preparer": "张三",
            "company_code": "001",
            "currency_code": "CNY",
        })
    return items


def _make_stats(total_count: int, debit_total: str = "50000.00", credit_total: str = "25000.00"):
    """Create a stats dict as returned by the API."""
    return {
        "total_count": total_count,
        "debit_total": debit_total,
        "credit_total": credit_total,
        "by_voucher_type": {"记": total_count // 2, "收": total_count - total_count // 2},
        "truncated": total_count > 500,
    }


def _make_extract_request(
    workpaper_id: uuid.UUID = _WORKPAPER_ID,
    page: int = 1,
    page_size: int = 50,
    account_codes: list[str] = None,
    exclude_extracted: bool = True,
):
    """Build a standard cutoff-extract request payload."""
    return {
        "cutoff_date": "2025-12-31",
        "days_before": 5,
        "days_after": 10,
        "amount_threshold": "0",
        "account_codes": account_codes or ["1122"],
        "direction_filter": "all",
        "voucher_type_filter": [],
        "summary_keyword": "",
        "exclude_extracted": exclude_extracted,
        "workpaper_id": str(workpaper_id),
        "page": page,
        "page_size": page_size,
    }


def _make_fill_request(
    workpaper_id: uuid.UUID = _WORKPAPER_ID,
    filled_count: int = 5,
    fill_mode: str = "append",
    before_data: list | None = None,
):
    """Build a standard cutoff-fill request payload."""
    return {
        "workpaper_id": str(workpaper_id),
        "extraction_type": "cutoff",
        "extraction_criteria": {
            "cutoff_date": "2025-12-31",
            "days_before": 5,
            "days_after": 10,
            "account_codes": ["1122"],
        },
        "total_matched": 20,
        "filled_count": filled_count,
        "fill_mode": fill_mode,
        "before_data": before_data or [],
        "filled_voucher_nos": [f"记-2025-{1000 + i:04d}" for i in range(filled_count)],
    }


# ═══════════════════════════════════════════════════════════════════════════════
# TestCutoffSamplingIntegration: 完整流程集成测试
# ═══════════════════════════════════════════════════════════════════════════════


class TestCutoffSamplingIntegration:
    """完整流程集成测试：extract → fill → history → undo

    **Validates: Requirements 2.1, 2.2, 2.3, 2.12, 5.5, 5.6**
    """

    @pytest.mark.asyncio
    async def test_full_flow_extract_fill_undo(self):
        """Seed data → extract → fill → verify log → undo → verify restore

        完整流程：
        1. POST /cutoff-extract → 验证返回 items + stats
        2. POST /cutoff-fill → 验证日志创建
        3. GET /cutoff-history → 验证历史记录
        4. POST /cutoff-undo → 验证撤销恢复
        """
        app, mock_db = _make_app()
        items = _make_ledger_rows(20, _PROJECT_A_ID)
        stats_dict = _make_stats(20)

        # Mock LedgerSamplingService methods
        with patch(
            "app.routers.cutoff_sampling.LedgerSamplingService"
        ) as MockService, patch(
            "app.routers.cutoff_sampling._get_extracted_voucher_nos",
            new=AsyncMock(return_value=[]),
        ):
            # Step 1: Extract
            from app.services.ledger_sampling_service import StatsResult

            mock_stats = StatsResult(**stats_dict)
            MockService.build_ledger_query = AsyncMock(return_value=MagicMock())
            MockService.execute_with_stats = AsyncMock(
                return_value=(items, mock_stats)
            )

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                # Step 1: POST /cutoff-extract
                extract_resp = await client.post(
                    f"/api/projects/{_PROJECT_A_ID}/sampling/cutoff-extract",
                    json=_make_extract_request(),
                )
                assert extract_resp.status_code == 200
                data = extract_resp.json()
                assert len(data["items"]) == 20
                assert data["stats"]["total_count"] == 20
                assert data["page"] == 1
                assert data["page_size"] == 50

                # Step 2: POST /cutoff-fill — record log
                MockService.record_extraction_log = AsyncMock(
                    return_value={
                        "id": str(_LOG_ID),
                        "created_at": "2025-12-31T10:00:00",
                    }
                )
                mock_db.commit = AsyncMock()

                fill_resp = await client.post(
                    f"/api/projects/{_PROJECT_A_ID}/sampling/cutoff-fill",
                    json=_make_fill_request(before_data=[{"existing": "sample"}]),
                )
                assert fill_resp.status_code == 200
                fill_data = fill_resp.json()
                assert fill_data["id"] == str(_LOG_ID)
                assert "created_at" in fill_data

                # Step 3: GET /cutoff-history
                MockService.get_extraction_history = AsyncMock(
                    return_value=[
                        {
                            "id": str(_LOG_ID),
                            "created_at": "2025-12-31T10:00:00",
                            "user_id": str(_USER_ID),
                            "extraction_type": "cutoff",
                            "extraction_criteria": {"cutoff_date": "2025-12-31"},
                            "total_matched": 20,
                            "filled_count": 5,
                            "fill_mode": "append",
                            "is_undone": False,
                        }
                    ]
                )

                history_resp = await client.get(
                    f"/api/projects/{_PROJECT_A_ID}/sampling/cutoff-history",
                    params={"wp_id": str(_WORKPAPER_ID)},
                )
                assert history_resp.status_code == 200
                history = history_resp.json()
                assert len(history) == 1
                assert history[0]["id"] == str(_LOG_ID)
                assert history[0]["is_undone"] is False
                assert history[0]["fill_mode"] == "append"

                # Step 4: POST /cutoff-undo
                MockService.undo_extraction = AsyncMock(
                    return_value={
                        "success": True,
                        "before_data": [{"existing": "sample"}],
                    }
                )

                undo_resp = await client.post(
                    f"/api/projects/{_PROJECT_A_ID}/sampling/cutoff-undo",
                    params={
                        "log_id": str(_LOG_ID),
                        "wp_id": str(_WORKPAPER_ID),
                    },
                )
                assert undo_resp.status_code == 200
                undo_data = undo_resp.json()
                assert undo_data["success"] is True
                assert undo_data["before_data"] == [{"existing": "sample"}]

    @pytest.mark.asyncio
    async def test_security_isolation_cross_project(self):
        """Project A data must NOT be visible to Project B query.

        验证 build_ledger_query 被调用时使用的 project_id 是 URL 路径中的 pid，
        确保跨项目隔离。
        """
        app, mock_db = _make_app()

        with patch(
            "app.routers.cutoff_sampling.LedgerSamplingService"
        ) as MockService, patch(
            "app.routers.cutoff_sampling._get_extracted_voucher_nos",
            new=AsyncMock(return_value=[]),
        ):
            from app.services.ledger_sampling_service import StatsResult

            # Project A: 返回 10 条数据
            items_a = _make_ledger_rows(10, _PROJECT_A_ID)
            stats_a = StatsResult(**_make_stats(10))
            MockService.build_ledger_query = AsyncMock(return_value=MagicMock())
            MockService.execute_with_stats = AsyncMock(
                return_value=(items_a, stats_a)
            )

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                # Query project A
                resp_a = await client.post(
                    f"/api/projects/{_PROJECT_A_ID}/sampling/cutoff-extract",
                    json=_make_extract_request(),
                )
                assert resp_a.status_code == 200

                # Verify build_ledger_query was called with project A's ID
                call_args = MockService.build_ledger_query.call_args
                assert call_args[1].get("project_id") == _PROJECT_A_ID or \
                    call_args[0][1] == _PROJECT_A_ID, (
                    "build_ledger_query must be called with project A's ID"
                )

                # Query project B — service should be called with project B's ID
                MockService.build_ledger_query.reset_mock()
                items_b = _make_ledger_rows(0, _PROJECT_B_ID)
                stats_b = StatsResult(**_make_stats(0, "0", "0"))
                MockService.execute_with_stats = AsyncMock(
                    return_value=(items_b, stats_b)
                )

                resp_b = await client.post(
                    f"/api/projects/{_PROJECT_B_ID}/sampling/cutoff-extract",
                    json=_make_extract_request(),
                )
                assert resp_b.status_code == 200
                assert len(resp_b.json()["items"]) == 0

                # Verify isolation: build_ledger_query called with project B's ID
                call_args_b = MockService.build_ledger_query.call_args
                assert call_args_b[1].get("project_id") == _PROJECT_B_ID or \
                    call_args_b[0][1] == _PROJECT_B_ID, (
                    "build_ledger_query must be called with project B's ID, not A's"
                )

    @pytest.mark.asyncio
    async def test_pagination(self):
        """page=1 size=10 returns exactly 10 items.

        验证分页参数正确传递到 execute_with_stats。
        """
        app, mock_db = _make_app()

        with patch(
            "app.routers.cutoff_sampling.LedgerSamplingService"
        ) as MockService, patch(
            "app.routers.cutoff_sampling._get_extracted_voucher_nos",
            new=AsyncMock(return_value=[]),
        ):
            from app.services.ledger_sampling_service import StatsResult

            # 总共 30 条，但分页返回 10 条
            items_page1 = _make_ledger_rows(10, _PROJECT_A_ID)
            stats = StatsResult(**_make_stats(30))
            MockService.build_ledger_query = AsyncMock(return_value=MagicMock())
            MockService.execute_with_stats = AsyncMock(
                return_value=(items_page1, stats)
            )

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    f"/api/projects/{_PROJECT_A_ID}/sampling/cutoff-extract",
                    json=_make_extract_request(page=1, page_size=10),
                )
                assert resp.status_code == 200
                data = resp.json()
                assert len(data["items"]) == 10
                assert data["page"] == 1
                assert data["page_size"] == 10
                assert data["stats"]["total_count"] == 30

                # Verify execute_with_stats was called with correct page/page_size
                exec_call = MockService.execute_with_stats.call_args
                # positional: (db, query, page, page_size)
                assert exec_call[0][2] == 1, "page should be 1"
                assert exec_call[0][3] == 10, "page_size should be 10"

    @pytest.mark.asyncio
    async def test_empty_result_strict_conditions(self):
        """Overly strict conditions return 0 items.

        验证条件过严时返回空列表和零统计。
        """
        app, mock_db = _make_app()

        with patch(
            "app.routers.cutoff_sampling.LedgerSamplingService"
        ) as MockService, patch(
            "app.routers.cutoff_sampling._get_extracted_voucher_nos",
            new=AsyncMock(return_value=[]),
        ):
            from app.services.ledger_sampling_service import StatsResult

            empty_stats = StatsResult(
                total_count=0,
                debit_total=Decimal("0"),
                credit_total=Decimal("0"),
                by_voucher_type={},
                truncated=False,
            )
            MockService.build_ledger_query = AsyncMock(return_value=MagicMock())
            MockService.execute_with_stats = AsyncMock(
                return_value=([], empty_stats)
            )

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                # Use very strict conditions: amount_threshold=999999999
                strict_req = _make_extract_request()
                strict_req["amount_threshold"] = "999999999.00"
                strict_req["summary_keyword"] = "不存在的关键词XYZ"

                resp = await client.post(
                    f"/api/projects/{_PROJECT_A_ID}/sampling/cutoff-extract",
                    json=strict_req,
                )
                assert resp.status_code == 200
                data = resp.json()
                assert len(data["items"]) == 0
                assert data["stats"]["total_count"] == 0
                assert data["stats"]["truncated"] is False

    @pytest.mark.asyncio
    async def test_dataset_visibility(self):
        """Only active dataset data is visible.

        验证 build_ledger_query 内部调用 get_active_filter，
        确保仅查询 active dataset 数据。
        """
        app, mock_db = _make_app()

        with patch(
            "app.routers.cutoff_sampling.LedgerSamplingService"
        ) as MockService, patch(
            "app.routers.cutoff_sampling._get_extracted_voucher_nos",
            new=AsyncMock(return_value=[]),
        ):
            from app.services.ledger_sampling_service import StatsResult

            # Simulate: active dataset only has 5 items
            active_items = _make_ledger_rows(5, _PROJECT_A_ID)
            active_stats = StatsResult(**_make_stats(5, "15000.00", "7500.00"))
            MockService.build_ledger_query = AsyncMock(return_value=MagicMock())
            MockService.execute_with_stats = AsyncMock(
                return_value=(active_items, active_stats)
            )

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    f"/api/projects/{_PROJECT_A_ID}/sampling/cutoff-extract",
                    json=_make_extract_request(),
                )
                assert resp.status_code == 200
                data = resp.json()

                # Only active dataset items are returned
                assert len(data["items"]) == 5
                assert data["stats"]["total_count"] == 5

                # Verify build_ledger_query was called (it internally uses get_active_filter)
                MockService.build_ledger_query.assert_called_once()

                # The service's build_ledger_query is responsible for calling
                # get_active_filter internally — this is verified in PBT Property 3.
                # Here we verify the router correctly passes db session to the service.
                call_args = MockService.build_ledger_query.call_args
                # First positional arg is db session
                assert call_args[0][0] is not None, (
                    "db session must be passed to build_ledger_query"
                )


# ═══════════════════════════════════════════════════════════════════════════════
# TestCutoffExcludeExtracted: 排除已提取凭证集成验证
# ═══════════════════════════════════════════════════════════════════════════════


class TestCutoffExcludeExtracted:
    """验证 exclude_extracted 功能通过 _get_extracted_voucher_nos 正确排除。

    **Validates: Requirements 2.12**
    """

    @pytest.mark.asyncio
    async def test_exclude_extracted_passes_voucher_nos(self):
        """When exclude_extracted=True, previously filled voucher_nos are passed to filters."""
        app, mock_db = _make_app()
        previously_extracted = ["记-2025-0001", "记-2025-0002", "记-2025-0003"]

        with patch(
            "app.routers.cutoff_sampling.LedgerSamplingService"
        ) as MockService, patch(
            "app.routers.cutoff_sampling._get_extracted_voucher_nos",
            new=AsyncMock(return_value=previously_extracted),
        ):
            from app.services.ledger_sampling_service import StatsResult

            items = _make_ledger_rows(5, _PROJECT_A_ID)
            stats = StatsResult(**_make_stats(5))
            MockService.build_ledger_query = AsyncMock(return_value=MagicMock())
            MockService.execute_with_stats = AsyncMock(
                return_value=(items, stats)
            )

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    f"/api/projects/{_PROJECT_A_ID}/sampling/cutoff-extract",
                    json=_make_extract_request(exclude_extracted=True),
                )
                assert resp.status_code == 200

                # Verify the filters passed to build_ledger_query include excluded nos
                call_args = MockService.build_ledger_query.call_args
                filters_arg = call_args[0][3]  # 4th positional: filters
                assert filters_arg.exclude_voucher_nos == previously_extracted, (
                    f"exclude_voucher_nos should contain previously extracted voucher nos. "
                    f"Got: {filters_arg.exclude_voucher_nos}"
                )

    @pytest.mark.asyncio
    async def test_exclude_extracted_disabled(self):
        """When exclude_extracted=False, no voucher_nos are excluded."""
        app, mock_db = _make_app()

        with patch(
            "app.routers.cutoff_sampling.LedgerSamplingService"
        ) as MockService, patch(
            "app.routers.cutoff_sampling._get_extracted_voucher_nos",
            new=AsyncMock(return_value=["should-not-be-called"]),
        ) as mock_get_extracted:
            from app.services.ledger_sampling_service import StatsResult

            items = _make_ledger_rows(5, _PROJECT_A_ID)
            stats = StatsResult(**_make_stats(5))
            MockService.build_ledger_query = AsyncMock(return_value=MagicMock())
            MockService.execute_with_stats = AsyncMock(
                return_value=(items, stats)
            )

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    f"/api/projects/{_PROJECT_A_ID}/sampling/cutoff-extract",
                    json=_make_extract_request(exclude_extracted=False),
                )
                assert resp.status_code == 200

                # _get_extracted_voucher_nos should NOT be called when disabled
                mock_get_extracted.assert_not_called()

                # filters should have empty exclude_voucher_nos
                call_args = MockService.build_ledger_query.call_args
                filters_arg = call_args[0][3]
                assert filters_arg.exclude_voucher_nos == [], (
                    "exclude_voucher_nos should be empty when exclude_extracted=False"
                )


# ═══════════════════════════════════════════════════════════════════════════════
# TestCutoffUndoValidation: 撤销操作验证
# ═══════════════════════════════════════════════════════════════════════════════


class TestCutoffUndoValidation:
    """验证撤销操作的错误处理。

    **Validates: Requirements 5.5, 5.6**
    """

    @pytest.mark.asyncio
    async def test_undo_non_latest_record_fails(self):
        """Undo of non-latest record should return 400 error."""
        app, mock_db = _make_app()

        with patch(
            "app.routers.cutoff_sampling.LedgerSamplingService"
        ) as MockService:
            MockService.undo_extraction = AsyncMock(
                side_effect=ValueError("仅可撤销最近一次操作")
            )
            mock_db.commit = AsyncMock()

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    f"/api/projects/{_PROJECT_A_ID}/sampling/cutoff-undo",
                    params={
                        "log_id": str(uuid.uuid4()),
                        "wp_id": str(_WORKPAPER_ID),
                    },
                )
                assert resp.status_code == 400
                assert "仅可撤销最近一次操作" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_undo_nonexistent_record_fails(self):
        """Undo of nonexistent record should return 400 error."""
        app, mock_db = _make_app()

        with patch(
            "app.routers.cutoff_sampling.LedgerSamplingService"
        ) as MockService:
            MockService.undo_extraction = AsyncMock(
                side_effect=ValueError("提取记录不存在")
            )
            mock_db.commit = AsyncMock()

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    f"/api/projects/{_PROJECT_A_ID}/sampling/cutoff-undo",
                    params={
                        "log_id": str(uuid.uuid4()),
                        "wp_id": str(_WORKPAPER_ID),
                    },
                )
                assert resp.status_code == 400
                assert "提取记录不存在" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_undo_wrong_workpaper_fails(self):
        """Undo with mismatched workpaper_id should return 400."""
        app, mock_db = _make_app()

        with patch(
            "app.routers.cutoff_sampling.LedgerSamplingService"
        ) as MockService:
            MockService.undo_extraction = AsyncMock(
                side_effect=ValueError("无权操作此记录")
            )
            mock_db.commit = AsyncMock()

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                other_wp_id = uuid.uuid4()
                resp = await client.post(
                    f"/api/projects/{_PROJECT_A_ID}/sampling/cutoff-undo",
                    params={
                        "log_id": str(_LOG_ID),
                        "wp_id": str(other_wp_id),
                    },
                )
                assert resp.status_code == 400
                assert "无权操作此记录" in resp.json()["detail"]
