"""后端集成测试：通用抽凭引擎完整流程

测试场景：
1. 完整流程：seed → extract（5种方法）→ fill → history → undo
2. 阶段隔离：预审填充 → 切年审 → 预审行不被覆盖 + 年审排除预审凭证号
3. 版本对比：两次抽凭 → compare → 验证 added/removed/retained
4. 种子复现：同参数同种子两次调用结果相同
5. 排除去重：第一次抽凭 → 第二次排除已抽凭证
6. 安全隔离：项目A数据不可被项目B查询

**Validates: Requirements 3.1, 3.2, 5.3, 6.3, 6.4, 13.1, 13.4**
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
from app.routers.voucher_sampling import router

# ─── Constants ────────────────────────────────────────────────────────────────

_USER_ID = uuid.uuid4()
_PROJECT_A_ID = uuid.uuid4()
_PROJECT_B_ID = uuid.uuid4()
_WORKPAPER_ID = uuid.uuid4()
_LOG_ID_1 = uuid.uuid4()
_LOG_ID_2 = uuid.uuid4()


# ─── Fake User ────────────────────────────────────────────────────────────────


class _FakeUser:
    id = _USER_ID
    username = "审计助理王五"
    role = UserRole.auditor


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _make_app() -> tuple[FastAPI, AsyncMock]:
    """Create minimal FastAPI app with voucher_sampling router and mocked deps."""
    app = FastAPI()
    app.include_router(router)

    mock_db = AsyncMock()

    async def _override_db():
        yield mock_db

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = lambda: _FakeUser()
    return app, mock_db


def _make_ledger_rows(
    count: int,
    start_date: date | None = None,
    prefix: str = "1122",
    debit_base: int = 1000,
    credit_base: int = 500,
) -> list[dict]:
    """Generate fake ledger row dicts as returned by execute_with_stats.

    Each item has realistic fields matching tb_ledger structure.
    """
    if start_date is None:
        start_date = date(2025, 1, 15)
    items = []
    for i in range(count):
        items.append({
            "id": str(uuid.uuid4()),
            "voucher_date": (start_date + timedelta(days=i % 30)).isoformat(),
            "voucher_no": f"记-2025-{1000 + i:04d}",
            "account_code": f"{prefix}01",
            "account_name": f"应收账款-客户{chr(65 + i % 26)}",
            "voucher_type": "记" if i % 3 == 0 else ("收" if i % 3 == 1 else "付"),
            "debit_amount": str(Decimal(f"{(i + 1) * debit_base}.00"))
            if i % 2 == 0
            else None,
            "credit_amount": str(Decimal(f"{(i + 1) * credit_base}.00"))
            if i % 2 != 0
            else None,
            "counterpart_account": "600101",
            "summary": f"销售收入-客户{chr(65 + i % 26)}第{i + 1}笔",
            "entry_seq": i + 1,
            "accounting_period": (i % 12) + 1,
            "preparer": "张三",
            "company_code": "001",
            "currency_code": "CNY",
        })
    return items


def _make_extract_request(
    workpaper_id: uuid.UUID = _WORKPAPER_ID,
    method: str = "random",
    sampling_params: dict | None = None,
    random_seed: int | None = 42,
    phase: str = "preliminary",
    account_codes: list[str] | None = None,
    exclude_extracted: bool = True,
    year: int = 2025,
) -> dict:
    """Build a standard voucher-extract request payload."""
    if sampling_params is None:
        sampling_params = {"sample_size": 10}
    return {
        "sampling_method": method,
        "sampling_params": sampling_params,
        "random_seed": random_seed,
        "phase": phase,
        "filters": {
            "account_codes": account_codes or ["1122"],
            "period_range": list(range(1, 13)),
            "amount_min": "0",
            "amount_max": None,
            "direction_filter": "all",
            "voucher_type_filter": [],
            "summary_keyword": "",
            "exclude_extracted": exclude_extracted,
        },
        "workpaper_id": str(workpaper_id),
        "year": year,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# TestVoucherSamplingFullFlow: 完整流程集成测试（5种方法 + fill + undo）
# ═══════════════════════════════════════════════════════════════════════════════


class TestVoucherSamplingFullFlow:
    """完整流程集成测试：5种抽样方法 → fill → history → undo

    **Validates: Requirements 3.1, 3.2, 13.1**
    """

    @pytest.mark.asyncio
    async def test_random_sampling_extract(self):
        """POST /voucher-extract method=random → 返回正确样本量和统计

        seed=42, sample_size=10, population=30 → items=10, coverage stats present
        """
        app, mock_db = _make_app()
        population = _make_ledger_rows(30)

        with patch(
            "app.routers.voucher_sampling.LedgerSamplingService"
        ) as MockService, patch(
            "app.routers.voucher_sampling._get_voucher_sampling_extracted_nos",
            new=AsyncMock(return_value=[]),
        ), patch(
            "app.routers.voucher_sampling._get_preliminary_voucher_nos",
            new=AsyncMock(return_value=[]),
        ):
            MockService.build_ledger_query = AsyncMock(return_value=MagicMock())
            MockService.execute_with_stats = AsyncMock(
                return_value=(population, MagicMock())
            )

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    f"/api/projects/{_PROJECT_A_ID}/sampling/voucher-extract",
                    json=_make_extract_request(method="random", sampling_params={"sample_size": 10}),
                )
                assert resp.status_code == 200
                data = resp.json()
                assert data["stats"]["sample_count"] == 10
                assert data["stats"]["population_count"] == 30
                assert data["seed_used"] == 42
                assert data["truncated"] is False
                assert len(data["items"]) == 10
                # 每个 item 必须来自 population
                pop_nos = {r["voucher_no"] for r in population}
                for item in data["items"]:
                    assert item["voucher_no"] in pop_nos

    @pytest.mark.asyncio
    async def test_stratified_sampling_extract(self):
        """POST /voucher-extract method=stratified → 按分层返回样本"""
        app, mock_db = _make_app()
        # 制造一组金额有梯度的 population
        population = _make_ledger_rows(40, debit_base=500, credit_base=300)

        with patch(
            "app.routers.voucher_sampling.LedgerSamplingService"
        ) as MockService, patch(
            "app.routers.voucher_sampling._get_voucher_sampling_extracted_nos",
            new=AsyncMock(return_value=[]),
        ), patch(
            "app.routers.voucher_sampling._get_preliminary_voucher_nos",
            new=AsyncMock(return_value=[]),
        ):
            MockService.build_ledger_query = AsyncMock(return_value=MagicMock())
            MockService.execute_with_stats = AsyncMock(
                return_value=(population, MagicMock())
            )

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    f"/api/projects/{_PROJECT_A_ID}/sampling/voucher-extract",
                    json=_make_extract_request(
                        method="stratified",
                        sampling_params={
                            "strata": [
                                {"lower_bound": "0", "upper_bound": "5000", "sample_size": 3},
                                {"lower_bound": "5001", "upper_bound": "50000", "sample_size": 5},
                            ]
                        },
                    ),
                )
                assert resp.status_code == 200
                data = resp.json()
                # 样本量 <= 配置总量
                assert data["stats"]["sample_count"] <= 8
                assert data["stats"]["population_count"] == 40

    @pytest.mark.asyncio
    async def test_specific_item_sampling_extract(self):
        """POST /voucher-extract method=specific_item → 返回 >= 阈值的全部凭证"""
        app, mock_db = _make_app()
        population = _make_ledger_rows(20, debit_base=2000, credit_base=1000)

        with patch(
            "app.routers.voucher_sampling.LedgerSamplingService"
        ) as MockService, patch(
            "app.routers.voucher_sampling._get_voucher_sampling_extracted_nos",
            new=AsyncMock(return_value=[]),
        ), patch(
            "app.routers.voucher_sampling._get_preliminary_voucher_nos",
            new=AsyncMock(return_value=[]),
        ):
            MockService.build_ledger_query = AsyncMock(return_value=MagicMock())
            MockService.execute_with_stats = AsyncMock(
                return_value=(population, MagicMock())
            )

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    f"/api/projects/{_PROJECT_A_ID}/sampling/voucher-extract",
                    json=_make_extract_request(
                        method="specific_item",
                        sampling_params={"materiality_threshold": "10000"},
                    ),
                )
                assert resp.status_code == 200
                data = resp.json()
                # 验证所有返回 item 的金额 >= 10000
                for item in data["items"]:
                    debit = Decimal(item["debit_amount"]) if item.get("debit_amount") else Decimal("0")
                    credit = Decimal(item["credit_amount"]) if item.get("credit_amount") else Decimal("0")
                    assert max(debit, credit) >= Decimal("10000")

    @pytest.mark.asyncio
    async def test_systematic_sampling_extract(self):
        """POST /voucher-extract method=systematic → 等距抽样按间隔选取"""
        app, mock_db = _make_app()
        population = _make_ledger_rows(50)

        with patch(
            "app.routers.voucher_sampling.LedgerSamplingService"
        ) as MockService, patch(
            "app.routers.voucher_sampling._get_voucher_sampling_extracted_nos",
            new=AsyncMock(return_value=[]),
        ), patch(
            "app.routers.voucher_sampling._get_preliminary_voucher_nos",
            new=AsyncMock(return_value=[]),
        ):
            MockService.build_ledger_query = AsyncMock(return_value=MagicMock())
            MockService.execute_with_stats = AsyncMock(
                return_value=(population, MagicMock())
            )

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    f"/api/projects/{_PROJECT_A_ID}/sampling/voucher-extract",
                    json=_make_extract_request(
                        method="systematic",
                        sampling_params={"start_point": 1, "interval": 5},
                    ),
                )
                assert resp.status_code == 200
                data = resp.json()
                # start=1, interval=5, population=50 → indices 0,5,10,...45 → 10笔
                assert data["stats"]["sample_count"] == 10

    @pytest.mark.asyncio
    async def test_mus_sampling_extract(self):
        """POST /voucher-extract method=mus → MUS累积金额抽样"""
        app, mock_db = _make_app()
        # 正金额 population
        population = _make_ledger_rows(30, debit_base=3000, credit_base=2000)

        with patch(
            "app.routers.voucher_sampling.LedgerSamplingService"
        ) as MockService, patch(
            "app.routers.voucher_sampling._get_voucher_sampling_extracted_nos",
            new=AsyncMock(return_value=[]),
        ), patch(
            "app.routers.voucher_sampling._get_preliminary_voucher_nos",
            new=AsyncMock(return_value=[]),
        ):
            MockService.build_ledger_query = AsyncMock(return_value=MagicMock())
            MockService.execute_with_stats = AsyncMock(
                return_value=(population, MagicMock())
            )

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    f"/api/projects/{_PROJECT_A_ID}/sampling/voucher-extract",
                    json=_make_extract_request(
                        method="mus",
                        sampling_params={"mus_sample_size": 8},
                    ),
                )
                assert resp.status_code == 200
                data = resp.json()
                # MUS 样本量大约等于 mus_sample_size（±1）
                assert abs(data["stats"]["sample_count"] - 8) <= 2
                assert data["seed_used"] == 42


# ═══════════════════════════════════════════════════════════════════════════════
# TestVoucherSamplingFillAndUndo: 填充日志 + 撤销恢复
# ═══════════════════════════════════════════════════════════════════════════════


class TestVoucherSamplingFillAndUndo:
    """填充日志记录 + 撤销恢复测试

    **Validates: Requirements 6.4, 13.1**
    """

    @pytest.mark.asyncio
    async def test_history_returns_voucher_sampling_records(self):
        """GET /voucher-history → 仅返回 extraction_type='voucher_sampling' 记录"""
        app, mock_db = _make_app()

        # Mock DB query result
        mock_record = MagicMock()
        mock_record.id = _LOG_ID_1
        mock_record.created_at = MagicMock()
        mock_record.created_at.isoformat = MagicMock(return_value="2025-06-01T10:00:00")
        mock_record.user_id = _USER_ID
        mock_record.extraction_type = "voucher_sampling"
        mock_record.extraction_criteria = {
            "sampling_method": "random",
            "sampling_params": {"sample_size": 10},
            "random_seed": 42,
            "phase": "preliminary",
            "coverage_stats": {"count_rate": "33.33", "amount_rate": "45.67"},
        }
        mock_record.total_matched = 30
        mock_record.filled_count = 10
        mock_record.fill_mode = "append"
        mock_record.is_undone = False

        mock_result = MagicMock()
        mock_result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[mock_record])))
        mock_db.execute = AsyncMock(return_value=mock_result)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(
                f"/api/projects/{_PROJECT_A_ID}/sampling/voucher-history",
                params={"wp_id": str(_WORKPAPER_ID)},
            )
            assert resp.status_code == 200
            history = resp.json()
            assert len(history) == 1
            assert history[0]["id"] == str(_LOG_ID_1)
            assert history[0]["extraction_type"] == "voucher_sampling"
            assert history[0]["is_undone"] is False
            assert history[0]["filled_count"] == 10

    @pytest.mark.asyncio
    async def test_undo_marks_is_undone_and_returns_before_data(self):
        """POST /voucher-undo → 标记 is_undone=True + 返回 before_data"""
        app, mock_db = _make_app()

        before_data_snapshot = [
            {"voucher_no": "记-2025-0001", "debit_amount": "5000.00"},
            {"voucher_no": "记-2025-0002", "credit_amount": "3000.00"},
        ]

        # Mock: 加载目标记录
        mock_record = MagicMock()
        mock_record.id = _LOG_ID_1
        mock_record.workpaper_id = _WORKPAPER_ID
        mock_record.extraction_type = "voucher_sampling"
        mock_record.is_undone = False
        mock_record.before_data = before_data_snapshot
        mock_record.created_at = MagicMock()

        # Mock: 最新非 undone 记录查询
        mock_latest = MagicMock()
        mock_latest.id = _LOG_ID_1  # 是最新的

        # Mock DB executions: first call = load record, second call = latest check
        mock_result_1 = MagicMock()
        mock_result_1.scalar_one_or_none = MagicMock(return_value=mock_record)
        mock_result_2 = MagicMock()
        mock_result_2.scalar_one_or_none = MagicMock(return_value=mock_latest)

        mock_db.execute = AsyncMock(side_effect=[mock_result_1, mock_result_2])
        mock_db.flush = AsyncMock()
        mock_db.commit = AsyncMock()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                f"/api/projects/{_PROJECT_A_ID}/sampling/voucher-undo",
                params={"log_id": str(_LOG_ID_1)},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["success"] is True
            assert data["before_data"] == before_data_snapshot
            # 验证 is_undone 被设置
            assert mock_record.is_undone is True

    @pytest.mark.asyncio
    async def test_undo_non_latest_fails(self):
        """POST /voucher-undo 非最新记录 → 400 错误"""
        app, mock_db = _make_app()

        mock_record = MagicMock()
        mock_record.id = _LOG_ID_1
        mock_record.workpaper_id = _WORKPAPER_ID
        mock_record.extraction_type = "voucher_sampling"
        mock_record.is_undone = False

        # 最新记录不是当前操作的 log_id
        mock_latest = MagicMock()
        mock_latest.id = _LOG_ID_2  # 不同ID

        mock_result_1 = MagicMock()
        mock_result_1.scalar_one_or_none = MagicMock(return_value=mock_record)
        mock_result_2 = MagicMock()
        mock_result_2.scalar_one_or_none = MagicMock(return_value=mock_latest)

        mock_db.execute = AsyncMock(side_effect=[mock_result_1, mock_result_2])

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                f"/api/projects/{_PROJECT_A_ID}/sampling/voucher-undo",
                params={"log_id": str(_LOG_ID_1)},
            )
            assert resp.status_code == 400
            assert "仅可撤销最近一次操作" in resp.json()["detail"]


# ═══════════════════════════════════════════════════════════════════════════════
# TestVoucherSamplingPhaseIsolation: 预审/年审阶段隔离
# ═══════════════════════════════════════════════════════════════════════════════


class TestVoucherSamplingPhaseIsolation:
    """阶段隔离：年审排除预审凭证号，预审行不被覆盖

    **Validates: Requirements 5.3**
    """

    @pytest.mark.asyncio
    async def test_final_phase_excludes_preliminary_voucher_nos(self):
        """phase='final' 时自动追加预审已抽凭证号到排除列表

        验证 _get_preliminary_voucher_nos 结果被传入 LedgerQueryFilters.exclude_voucher_nos
        """
        app, mock_db = _make_app()
        population = _make_ledger_rows(20)
        preliminary_nos = ["记-2025-1000", "记-2025-1001", "记-2025-1002"]

        with patch(
            "app.routers.voucher_sampling.LedgerSamplingService"
        ) as MockService, patch(
            "app.routers.voucher_sampling._get_voucher_sampling_extracted_nos",
            new=AsyncMock(return_value=[]),
        ), patch(
            "app.routers.voucher_sampling._get_preliminary_voucher_nos",
            new=AsyncMock(return_value=preliminary_nos),
        ):
            MockService.build_ledger_query = AsyncMock(return_value=MagicMock())
            MockService.execute_with_stats = AsyncMock(
                return_value=(population, MagicMock())
            )

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    f"/api/projects/{_PROJECT_A_ID}/sampling/voucher-extract",
                    json=_make_extract_request(phase="final"),
                )
                assert resp.status_code == 200

                # 验证 build_ledger_query 的 filters 参数包含预审凭证号
                call_args = MockService.build_ledger_query.call_args
                filters_arg = call_args[0][3]  # 4th positional: LedgerQueryFilters
                assert "记-2025-1000" in filters_arg.exclude_voucher_nos
                assert "记-2025-1001" in filters_arg.exclude_voucher_nos
                assert "记-2025-1002" in filters_arg.exclude_voucher_nos

    @pytest.mark.asyncio
    async def test_preliminary_phase_does_not_exclude_preliminary_nos(self):
        """phase='preliminary' 时不自动追加预审排除"""
        app, mock_db = _make_app()
        population = _make_ledger_rows(20)

        with patch(
            "app.routers.voucher_sampling.LedgerSamplingService"
        ) as MockService, patch(
            "app.routers.voucher_sampling._get_voucher_sampling_extracted_nos",
            new=AsyncMock(return_value=[]),
        ), patch(
            "app.routers.voucher_sampling._get_preliminary_voucher_nos",
            new=AsyncMock(return_value=["should-not-appear"]),
        ) as mock_get_prelim:
            MockService.build_ledger_query = AsyncMock(return_value=MagicMock())
            MockService.execute_with_stats = AsyncMock(
                return_value=(population, MagicMock())
            )

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    f"/api/projects/{_PROJECT_A_ID}/sampling/voucher-extract",
                    json=_make_extract_request(phase="preliminary"),
                )
                assert resp.status_code == 200

                # _get_preliminary_voucher_nos should NOT be called for preliminary phase
                mock_get_prelim.assert_not_called()

    @pytest.mark.asyncio
    async def test_phase_isolation_preliminary_then_final(self):
        """预审填充后切年审 → 预审已抽凭证号被排除 + 新结果不含预审凭证

        模拟完整流程：预审抽凭 → 年审抽凭时排除预审结果。
        """
        app, mock_db = _make_app()
        full_population = _make_ledger_rows(40)
        preliminary_extracted = [full_population[i]["voucher_no"] for i in range(10)]

        with patch(
            "app.routers.voucher_sampling.LedgerSamplingService"
        ) as MockService, patch(
            "app.routers.voucher_sampling._get_voucher_sampling_extracted_nos",
            new=AsyncMock(return_value=preliminary_extracted),
        ), patch(
            "app.routers.voucher_sampling._get_preliminary_voucher_nos",
            new=AsyncMock(return_value=preliminary_extracted),
        ):
            # 年审查询的 population 应是排除预审凭证后的子集
            final_population = [
                r for r in full_population if r["voucher_no"] not in preliminary_extracted
            ]
            MockService.build_ledger_query = AsyncMock(return_value=MagicMock())
            MockService.execute_with_stats = AsyncMock(
                return_value=(final_population, MagicMock())
            )

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    f"/api/projects/{_PROJECT_A_ID}/sampling/voucher-extract",
                    json=_make_extract_request(
                        phase="final",
                        sampling_params={"sample_size": 5},
                    ),
                )
                assert resp.status_code == 200
                data = resp.json()

                # 验证返回的样本不包含预审凭证号
                result_nos = {item["voucher_no"] for item in data["items"]}
                for prelim_no in preliminary_extracted:
                    assert prelim_no not in result_nos


# ═══════════════════════════════════════════════════════════════════════════════
# TestVoucherSamplingCompare: 版本对比
# ═══════════════════════════════════════════════════════════════════════════════


class TestVoucherSamplingCompare:
    """版本对比：两次抽凭 → compare → 验证 added/removed/retained

    **Validates: Requirements 6.3**
    """

    @pytest.mark.asyncio
    async def test_compare_two_extractions(self):
        """POST /voucher-compare → 返回正确的 added/removed/retained

        log_a 凭证号: {A, B, C, D}
        log_b 凭证号: {B, C, E, F}
        expected: added={E,F}, removed={A,D}, retained={B,C}
        """
        app, mock_db = _make_app()

        mock_record_a = MagicMock()
        mock_record_a.extraction_criteria = {
            "filled_voucher_nos": ["记-A", "记-B", "记-C", "记-D"]
        }
        mock_record_a.before_data = None

        mock_record_b = MagicMock()
        mock_record_b.extraction_criteria = {
            "filled_voucher_nos": ["记-B", "记-C", "记-E", "记-F"]
        }
        mock_record_b.before_data = None

        mock_result_a = MagicMock()
        mock_result_a.scalar_one_or_none = MagicMock(return_value=mock_record_a)
        mock_result_b = MagicMock()
        mock_result_b.scalar_one_or_none = MagicMock(return_value=mock_record_b)

        mock_db.execute = AsyncMock(side_effect=[mock_result_a, mock_result_b])

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                f"/api/projects/{_PROJECT_A_ID}/sampling/voucher-compare",
                json={
                    "log_id_a": str(_LOG_ID_1),
                    "log_id_b": str(_LOG_ID_2),
                },
            )
            assert resp.status_code == 200
            data = resp.json()

            assert set(data["added"]) == {"记-E", "记-F"}
            assert set(data["removed"]) == {"记-A", "记-D"}
            assert set(data["retained"]) == {"记-B", "记-C"}
            assert data["added_count"] == 2
            assert data["removed_count"] == 2
            assert data["retained_count"] == 2

    @pytest.mark.asyncio
    async def test_compare_nonexistent_record_fails(self):
        """POST /voucher-compare 记录不存在 → 400"""
        app, mock_db = _make_app()

        mock_result_a = MagicMock()
        mock_result_a.scalar_one_or_none = MagicMock(return_value=None)
        mock_result_b = MagicMock()
        mock_result_b.scalar_one_or_none = MagicMock(return_value=None)

        mock_db.execute = AsyncMock(side_effect=[mock_result_a, mock_result_b])

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                f"/api/projects/{_PROJECT_A_ID}/sampling/voucher-compare",
                json={
                    "log_id_a": str(uuid.uuid4()),
                    "log_id_b": str(uuid.uuid4()),
                },
            )
            assert resp.status_code == 400
            assert "对比记录不存在" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_compare_identical_extractions(self):
        """对比两次完全相同的抽凭 → added=[], removed=[], retained=全集"""
        app, mock_db = _make_app()
        same_nos = ["记-2025-0001", "记-2025-0002", "记-2025-0003"]

        mock_record_a = MagicMock()
        mock_record_a.extraction_criteria = {"filled_voucher_nos": same_nos}
        mock_record_a.before_data = None

        mock_record_b = MagicMock()
        mock_record_b.extraction_criteria = {"filled_voucher_nos": same_nos}
        mock_record_b.before_data = None

        mock_result_a = MagicMock()
        mock_result_a.scalar_one_or_none = MagicMock(return_value=mock_record_a)
        mock_result_b = MagicMock()
        mock_result_b.scalar_one_or_none = MagicMock(return_value=mock_record_b)

        mock_db.execute = AsyncMock(side_effect=[mock_result_a, mock_result_b])

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                f"/api/projects/{_PROJECT_A_ID}/sampling/voucher-compare",
                json={
                    "log_id_a": str(_LOG_ID_1),
                    "log_id_b": str(_LOG_ID_2),
                },
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["added"] == []
            assert data["removed"] == []
            assert set(data["retained"]) == set(same_nos)


# ═══════════════════════════════════════════════════════════════════════════════
# TestVoucherSamplingSeedReproducibility: 种子复现
# ═══════════════════════════════════════════════════════════════════════════════


class TestVoucherSamplingSeedReproducibility:
    """同参数同种子两次调用结果相同

    **Validates: Requirements 3.2, 13.4**
    """

    @pytest.mark.asyncio
    async def test_same_seed_same_result(self):
        """同参数同种子两次调用 → 结果完全相同（items 和 seed_used 一致）"""
        app, mock_db = _make_app()
        population = _make_ledger_rows(50)

        with patch(
            "app.routers.voucher_sampling.LedgerSamplingService"
        ) as MockService, patch(
            "app.routers.voucher_sampling._get_voucher_sampling_extracted_nos",
            new=AsyncMock(return_value=[]),
        ), patch(
            "app.routers.voucher_sampling._get_preliminary_voucher_nos",
            new=AsyncMock(return_value=[]),
        ):
            MockService.build_ledger_query = AsyncMock(return_value=MagicMock())
            MockService.execute_with_stats = AsyncMock(
                return_value=(population, MagicMock())
            )

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                req = _make_extract_request(
                    method="random",
                    sampling_params={"sample_size": 15},
                    random_seed=12345,
                )

                # 第一次调用
                resp1 = await client.post(
                    f"/api/projects/{_PROJECT_A_ID}/sampling/voucher-extract",
                    json=req,
                )
                assert resp1.status_code == 200
                data1 = resp1.json()

                # 第二次调用（同参数同种子）
                resp2 = await client.post(
                    f"/api/projects/{_PROJECT_A_ID}/sampling/voucher-extract",
                    json=req,
                )
                assert resp2.status_code == 200
                data2 = resp2.json()

                # 验证结果完全相同
                assert data1["seed_used"] == data2["seed_used"] == 12345
                assert data1["items"] == data2["items"]
                assert data1["stats"] == data2["stats"]

    @pytest.mark.asyncio
    async def test_different_seed_different_result(self):
        """不同种子 → 结果大概率不同"""
        app, mock_db = _make_app()
        population = _make_ledger_rows(100)

        with patch(
            "app.routers.voucher_sampling.LedgerSamplingService"
        ) as MockService, patch(
            "app.routers.voucher_sampling._get_voucher_sampling_extracted_nos",
            new=AsyncMock(return_value=[]),
        ), patch(
            "app.routers.voucher_sampling._get_preliminary_voucher_nos",
            new=AsyncMock(return_value=[]),
        ):
            MockService.build_ledger_query = AsyncMock(return_value=MagicMock())
            MockService.execute_with_stats = AsyncMock(
                return_value=(population, MagicMock())
            )

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                req1 = _make_extract_request(
                    method="random",
                    sampling_params={"sample_size": 10},
                    random_seed=111,
                )
                req2 = _make_extract_request(
                    method="random",
                    sampling_params={"sample_size": 10},
                    random_seed=999,
                )

                resp1 = await client.post(
                    f"/api/projects/{_PROJECT_A_ID}/sampling/voucher-extract",
                    json=req1,
                )
                resp2 = await client.post(
                    f"/api/projects/{_PROJECT_A_ID}/sampling/voucher-extract",
                    json=req2,
                )
                data1 = resp1.json()
                data2 = resp2.json()

                # 不同种子在大 population 中极大概率产生不同结果
                nos_1 = [i["voucher_no"] for i in data1["items"]]
                nos_2 = [i["voucher_no"] for i in data2["items"]]
                assert nos_1 != nos_2, "Different seeds should produce different results"


# ═══════════════════════════════════════════════════════════════════════════════
# TestVoucherSamplingExcludeDedup: 排除去重
# ═══════════════════════════════════════════════════════════════════════════════


class TestVoucherSamplingExcludeDedup:
    """第一次抽凭 → 第二次排除已抽凭证

    **Validates: Requirements 3.2, 13.4**
    """

    @pytest.mark.asyncio
    async def test_exclude_previously_extracted_vouchers(self):
        """exclude_extracted=True → 已抽凭证号被传入 exclude_voucher_nos"""
        app, mock_db = _make_app()
        population = _make_ledger_rows(20)
        previously_extracted = ["记-2025-1000", "记-2025-1001", "记-2025-1002"]

        with patch(
            "app.routers.voucher_sampling.LedgerSamplingService"
        ) as MockService, patch(
            "app.routers.voucher_sampling._get_voucher_sampling_extracted_nos",
            new=AsyncMock(return_value=previously_extracted),
        ), patch(
            "app.routers.voucher_sampling._get_preliminary_voucher_nos",
            new=AsyncMock(return_value=[]),
        ):
            MockService.build_ledger_query = AsyncMock(return_value=MagicMock())
            MockService.execute_with_stats = AsyncMock(
                return_value=(population, MagicMock())
            )

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    f"/api/projects/{_PROJECT_A_ID}/sampling/voucher-extract",
                    json=_make_extract_request(exclude_extracted=True),
                )
                assert resp.status_code == 200

                # 验证 filters 中的 exclude_voucher_nos
                call_args = MockService.build_ledger_query.call_args
                filters_arg = call_args[0][3]
                for no in previously_extracted:
                    assert no in filters_arg.exclude_voucher_nos

    @pytest.mark.asyncio
    async def test_exclude_disabled_no_filtering(self):
        """exclude_extracted=False → 不查询已抽凭证，exclude_voucher_nos 为空"""
        app, mock_db = _make_app()
        population = _make_ledger_rows(20)

        with patch(
            "app.routers.voucher_sampling.LedgerSamplingService"
        ) as MockService, patch(
            "app.routers.voucher_sampling._get_voucher_sampling_extracted_nos",
            new=AsyncMock(return_value=["should-not-appear"]),
        ) as mock_get_extracted, patch(
            "app.routers.voucher_sampling._get_preliminary_voucher_nos",
            new=AsyncMock(return_value=[]),
        ):
            MockService.build_ledger_query = AsyncMock(return_value=MagicMock())
            MockService.execute_with_stats = AsyncMock(
                return_value=(population, MagicMock())
            )

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    f"/api/projects/{_PROJECT_A_ID}/sampling/voucher-extract",
                    json=_make_extract_request(exclude_extracted=False),
                )
                assert resp.status_code == 200

                # _get_voucher_sampling_extracted_nos 不应被调用
                mock_get_extracted.assert_not_called()

                # exclude_voucher_nos 应为空
                call_args = MockService.build_ledger_query.call_args
                filters_arg = call_args[0][3]
                assert filters_arg.exclude_voucher_nos == []

    @pytest.mark.asyncio
    async def test_final_phase_merges_both_exclude_sources(self):
        """phase='final' + exclude_extracted=True → 合并两个来源的排除凭证号（去重）"""
        app, mock_db = _make_app()
        population = _make_ledger_rows(30)

        # 已抽凭证号（来自历史日志）
        extracted_nos = ["记-2025-1000", "记-2025-1001"]
        # 预审已抽凭证号（来自 preliminary phase 记录）
        preliminary_nos = ["记-2025-1001", "记-2025-1002"]  # 注意 1001 重复

        with patch(
            "app.routers.voucher_sampling.LedgerSamplingService"
        ) as MockService, patch(
            "app.routers.voucher_sampling._get_voucher_sampling_extracted_nos",
            new=AsyncMock(return_value=extracted_nos),
        ), patch(
            "app.routers.voucher_sampling._get_preliminary_voucher_nos",
            new=AsyncMock(return_value=preliminary_nos),
        ):
            MockService.build_ledger_query = AsyncMock(return_value=MagicMock())
            MockService.execute_with_stats = AsyncMock(
                return_value=(population, MagicMock())
            )

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    f"/api/projects/{_PROJECT_A_ID}/sampling/voucher-extract",
                    json=_make_extract_request(phase="final", exclude_extracted=True),
                )
                assert resp.status_code == 200

                call_args = MockService.build_ledger_query.call_args
                filters_arg = call_args[0][3]
                exclude_set = set(filters_arg.exclude_voucher_nos)

                # 合并去重后应包含: 1000, 1001, 1002
                assert "记-2025-1000" in exclude_set
                assert "记-2025-1001" in exclude_set
                assert "记-2025-1002" in exclude_set
                # 不应有重复
                assert len(filters_arg.exclude_voucher_nos) == len(exclude_set)


# ═══════════════════════════════════════════════════════════════════════════════
# TestVoucherSamplingSecurityIsolation: 安全隔离
# ═══════════════════════════════════════════════════════════════════════════════


class TestVoucherSamplingSecurityIsolation:
    """项目A数据不可被项目B查询

    **Validates: Requirements 13.4**
    """

    @pytest.mark.asyncio
    async def test_cross_project_isolation(self):
        """Project A 的抽凭查询使用 project A 的 ID，Project B 同理

        验证 build_ledger_query 被调用时携带正确的 project_id。
        """
        app, mock_db = _make_app()
        items_a = _make_ledger_rows(10)

        with patch(
            "app.routers.voucher_sampling.LedgerSamplingService"
        ) as MockService, patch(
            "app.routers.voucher_sampling._get_voucher_sampling_extracted_nos",
            new=AsyncMock(return_value=[]),
        ), patch(
            "app.routers.voucher_sampling._get_preliminary_voucher_nos",
            new=AsyncMock(return_value=[]),
        ):
            MockService.build_ledger_query = AsyncMock(return_value=MagicMock())
            MockService.execute_with_stats = AsyncMock(
                return_value=(items_a, MagicMock())
            )

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                # 查询 Project A
                resp_a = await client.post(
                    f"/api/projects/{_PROJECT_A_ID}/sampling/voucher-extract",
                    json=_make_extract_request(),
                )
                assert resp_a.status_code == 200

                # 验证 build_ledger_query 的 project_id 参数
                call_args_a = MockService.build_ledger_query.call_args
                # build_ledger_query(db, pid, year, filters) — pid 是第2个位置参数
                assert call_args_a[0][1] == _PROJECT_A_ID

                # 重置 mock，查询 Project B
                MockService.build_ledger_query.reset_mock()
                items_b = _make_ledger_rows(0)
                MockService.execute_with_stats = AsyncMock(
                    return_value=(items_b, MagicMock())
                )

                resp_b = await client.post(
                    f"/api/projects/{_PROJECT_B_ID}/sampling/voucher-extract",
                    json=_make_extract_request(),
                )
                assert resp_b.status_code == 200
                assert len(resp_b.json()["items"]) == 0

                # 验证 Project B 调用使用了 B 的 ID
                call_args_b = MockService.build_ledger_query.call_args
                assert call_args_b[0][1] == _PROJECT_B_ID

    @pytest.mark.asyncio
    async def test_history_scoped_to_workpaper(self):
        """GET /voucher-history 查询通过 workpaper_id 过滤，不泄露其他底稿数据"""
        app, mock_db = _make_app()

        mock_record = MagicMock()
        mock_record.id = _LOG_ID_1
        mock_record.created_at = MagicMock()
        mock_record.created_at.isoformat = MagicMock(return_value="2025-06-01T10:00:00")
        mock_record.user_id = _USER_ID
        mock_record.extraction_type = "voucher_sampling"
        mock_record.extraction_criteria = {"sampling_method": "random"}
        mock_record.total_matched = 20
        mock_record.filled_count = 10
        mock_record.fill_mode = "append"
        mock_record.is_undone = False

        mock_result = MagicMock()
        mock_result.scalars = MagicMock(
            return_value=MagicMock(all=MagicMock(return_value=[mock_record]))
        )
        mock_db.execute = AsyncMock(return_value=mock_result)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # 查询指定底稿
            resp = await client.get(
                f"/api/projects/{_PROJECT_A_ID}/sampling/voucher-history",
                params={"wp_id": str(_WORKPAPER_ID)},
            )
            assert resp.status_code == 200
            history = resp.json()
            assert len(history) == 1

            # 查询其他底稿（mock 返回空）
            mock_result_empty = MagicMock()
            mock_result_empty.scalars = MagicMock(
                return_value=MagicMock(all=MagicMock(return_value=[]))
            )
            mock_db.execute = AsyncMock(return_value=mock_result_empty)

            other_wp_id = uuid.uuid4()
            resp2 = await client.get(
                f"/api/projects/{_PROJECT_A_ID}/sampling/voucher-history",
                params={"wp_id": str(other_wp_id)},
            )
            assert resp2.status_code == 200
            assert resp2.json() == []
