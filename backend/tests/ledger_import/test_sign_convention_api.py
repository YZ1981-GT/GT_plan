"""符号约定 API 测试。

Tasks: 5.4, 5.5, 7.1, 7.6
Requirements: 4.4, 4.5, 6.3, 6.6

使用 ASGI in-process transport 直连，无需外部服务。
"""

from __future__ import annotations

import uuid

import pytest
import httpx

from app.routers.sign_convention import (
    BatchConfirmRequest,
    BatchConfirmResponse,
    DirectionOverrideRequest,
    DirectionOverrideResponse,
    SignAnomalyListResponse,
    TrialBalanceDirectionFields,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def project_id() -> str:
    return str(uuid.uuid4())


@pytest.fixture
def dataset_id() -> str:
    return str(uuid.uuid4())


def _base_url(project_id: str, dataset_id: str) -> str:
    return f"/api/projects/{project_id}/datasets/{dataset_id}/sign-convention"


# ---------------------------------------------------------------------------
# 5.4: anomaly list API returns structured response
# ---------------------------------------------------------------------------


class TestAnomalyListAPI:
    """Task 5.4: 方向异常列表 API。"""

    @pytest.mark.asyncio
    async def test_anomaly_list_returns_structured_response(
        self, project_id: str, dataset_id: str
    ):
        """异常列表 API 返回正确结构。"""
        from app.main import app

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            url = f"{_base_url(project_id, dataset_id)}/anomalies"
            resp = await client.get(url)

        assert resp.status_code == 200
        body = resp.json()
        # ResponseWrapperMiddleware 信封解包
        data = body.get("data", body)
        parsed = SignAnomalyListResponse(**data)
        assert parsed.total == 0
        assert parsed.anomalies == []
        assert parsed.sign_convention_version == "v2_category_natural_positive"

    @pytest.mark.asyncio
    async def test_anomaly_list_accepts_filters(
        self, project_id: str, dataset_id: str
    ):
        """异常列表 API 接受 review_status / limit / offset 参数。"""
        from app.main import app

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            url = f"{_base_url(project_id, dataset_id)}/anomalies"
            resp = await client.get(
                url, params={"review_status": "pending", "limit": 50, "offset": 10}
            )

        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# 5.5: direction override saves to direction_override table
# ---------------------------------------------------------------------------


class TestDirectionOverrideAPI:
    """Task 5.5: 用户方向覆盖 API。"""

    @pytest.mark.asyncio
    async def test_direction_override_returns_structured_response(
        self, project_id: str, dataset_id: str
    ):
        """方向覆盖 API 返回包含留痕信息的结构。"""
        from app.main import app

        payload = {
            "table_name": "tb_balance",
            "record_id": str(uuid.uuid4()),
            "override_direction": "credit",
            "override_reason": "该科目为留抵税额，实际借方余额正确",
        }

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            url = f"{_base_url(project_id, dataset_id)}/direction-override"
            resp = await client.post(url, json=payload)

        assert resp.status_code == 200
        body = resp.json()
        data = body.get("data", body)
        parsed = DirectionOverrideResponse(**data)
        assert parsed.override_direction == "credit"
        assert parsed.override_reason == payload["override_reason"]
        assert parsed.override_by is not None
        assert parsed.override_at is not None

    @pytest.mark.asyncio
    async def test_direction_override_validates_reason(
        self, project_id: str, dataset_id: str
    ):
        """覆盖原因不能为空。"""
        from app.main import app

        payload = {
            "table_name": "tb_balance",
            "record_id": str(uuid.uuid4()),
            "override_direction": "debit",
            "override_reason": "",  # 空原因
        }

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            url = f"{_base_url(project_id, dataset_id)}/direction-override"
            resp = await client.post(url, json=payload)

        # Pydantic 校验 min_length=1 → 422
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# 7.1: trial balance response model includes direction fields
# ---------------------------------------------------------------------------


class TestTrialBalanceDirectionFields:
    """Task 7.1: 试算表 API 方向字段模型。"""

    def test_direction_fields_model_accepts_full_data(self):
        """完整方向字段可正常解析。"""
        fields = TrialBalanceDirectionFields(
            direction="debit",
            direction_source="split_columns",
            direction_review_status="accepted",
            sign_anomaly_flags={"both_debit_credit_nonzero": True},
        )
        assert fields.direction == "debit"
        assert fields.direction_source == "split_columns"
        assert fields.direction_review_status == "accepted"
        assert fields.sign_anomaly_flags == {"both_debit_credit_nonzero": True}

    def test_direction_fields_model_accepts_none(self):
        """所有字段可为空（旧数据兼容）。"""
        fields = TrialBalanceDirectionFields()
        assert fields.direction is None
        assert fields.direction_source is None
        assert fields.direction_review_status is None
        assert fields.sign_anomaly_flags is None


# ---------------------------------------------------------------------------
# 7.6: batch confirm processes multiple accounts
# ---------------------------------------------------------------------------


class TestBatchConfirmAPI:
    """Task 7.6: 批量确认 API。"""

    @pytest.mark.asyncio
    async def test_batch_confirm_returns_count(
        self, project_id: str, dataset_id: str
    ):
        """批量确认返回确认数量。"""
        from app.main import app

        payload = {
            "anomaly_ids": ["1001", "2221", "6001"],
            "confirm_reason": "审计师已核实，属于真实业务余额",
        }

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            url = f"{_base_url(project_id, dataset_id)}/anomalies/batch-confirm"
            resp = await client.post(url, json=payload)

        assert resp.status_code == 200
        body = resp.json()
        data = body.get("data", body)
        parsed = BatchConfirmResponse(**data)
        assert parsed.confirmed_count == 3
        assert parsed.failed_ids == []

    @pytest.mark.asyncio
    async def test_batch_confirm_validates_reason(
        self, project_id: str, dataset_id: str
    ):
        """批量确认原因不能为空。"""
        from app.main import app

        payload = {
            "anomaly_ids": ["1001"],
            "confirm_reason": "",
        }

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            url = f"{_base_url(project_id, dataset_id)}/anomalies/batch-confirm"
            resp = await client.post(url, json=payload)

        assert resp.status_code == 422
