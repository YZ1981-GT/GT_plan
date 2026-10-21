"""符号约定 API 测试。

Tasks: 5.4, 5.5, 7.1, 7.6
Requirements: 4.4, 4.5, 6.3, 6.6

请求经权限世界（``tests/authz_world.py``）以 ASGI in-process transport 直连，无需外部服务。
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio

from app.routers import sign_convention
from app.routers.sign_convention import (
    BatchConfirmResponse,
    DirectionOverrideResponse,
    SignAnomalyListResponse,
    TrialBalanceDirectionFields,
)
from app.services.assignment_service import ROLE_MAP
from tests.authz_world import TARGET_PROJECT_ID, sqlite_world

GATE = "app.deps.assert_project_permission"  # 生产成员判定；每个请求都核对它的代码确实执行过


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def world(monkeypatch: pytest.MonkeyPatch):
    async with sqlite_world(monkeypatch) as w:
        yield w


@pytest_asyncio.fixture
async def client(world):
    """以 edit 级项目成员身份请求。

    Phase 8 Task 8 起这三个端点挂了项目级鉴权（列表 readonly / 两个写端点 edit）。本文件测的是
    stub 接口的响应结构与入参校验，不是鉴权；鉴权由 test_phase8_endpoint_auth_fires /
    test_phase8_endpoint_role_levels 覆盖。身份是权限世界里的真实用户，与目标项目上的一条成员行
    （取 ``ROLE_MAP["auditor"]``，即 (auditor, edit)）；由生产的 ``require_project_access`` /
    ``assert_project_permission`` 判定，门禁不替换（partner-manager-edit-permission
    需求 12.1）。应用只挂本路由（前缀与生产注册相同），不经 ResponseWrapperMiddleware，响应体即端点的响应模型。
    """
    role, level = ROLE_MAP["auditor"]
    member = await world.member(level, role)
    async with world.client(sign_convention.router, user=member.user) as c:
        yield c


@pytest.fixture
def project_id() -> str:
    return str(TARGET_PROJECT_ID)  # 成员行所在的项目


@pytest.fixture
def dataset_id() -> str:
    return str(uuid.uuid4())


def _base_url(project_id: str, dataset_id: str) -> str:
    return f"/api/projects/{project_id}/datasets/{dataset_id}/sign-convention"


def _validation_errors(resp) -> list[tuple[str, list]]:
    """422 响应里每条校验错误的（类型，位置）。"""
    return [(error["type"], error["loc"]) for error in resp.json()["detail"]]


# ---------------------------------------------------------------------------
# 5.4: anomaly list API returns structured response
# ---------------------------------------------------------------------------


class TestAnomalyListAPI:
    """Task 5.4: 方向异常列表 API。"""

    @pytest.mark.asyncio
    async def test_anomaly_list_returns_structured_response(
        self, client, project_id: str, dataset_id: str
    ):
        """异常列表 API 返回正确结构。"""
        url = f"{_base_url(project_id, dataset_id)}/anomalies"
        resp = await client.get(url)

        assert resp.status_code == 200
        parsed = SignAnomalyListResponse(**resp.json())
        assert parsed.total == 0
        assert parsed.anomalies == []
        assert parsed.sign_convention_version == "v2_category_natural_positive"
        client.assert_passed(GATE, times=1)

    @pytest.mark.asyncio
    async def test_anomaly_list_accepts_filters(
        self, client, project_id: str, dataset_id: str
    ):
        """异常列表 API 接受 review_status / limit / offset 参数。"""
        url = f"{_base_url(project_id, dataset_id)}/anomalies"
        resp = await client.get(
            url, params={"review_status": "pending", "limit": 50, "offset": 10}
        )

        assert resp.status_code == 200
        assert resp.json() == {
            "anomalies": [],
            "total": 0,
            "sign_convention_version": "v2_category_natural_positive",
        }
        client.assert_passed(GATE, times=1)


# ---------------------------------------------------------------------------
# 5.5: direction override saves to direction_override table
# ---------------------------------------------------------------------------


class TestDirectionOverrideAPI:
    """Task 5.5: 用户方向覆盖 API。"""

    @pytest.mark.asyncio
    async def test_direction_override_returns_structured_response(
        self, client, project_id: str, dataset_id: str
    ):
        """方向覆盖 API 返回包含留痕信息的结构。"""
        payload = {
            "table_name": "tb_balance",
            "record_id": str(uuid.uuid4()),
            "override_direction": "credit",
            "override_reason": "该科目为留抵税额，实际借方余额正确",
        }

        url = f"{_base_url(project_id, dataset_id)}/direction-override"
        resp = await client.post(url, json=payload)

        assert resp.status_code == 200
        parsed = DirectionOverrideResponse(**resp.json())
        assert parsed.override_direction == "credit"
        assert parsed.override_reason == payload["override_reason"]
        assert parsed.override_by is not None
        assert parsed.override_at is not None
        client.assert_passed(GATE, times=1)

    @pytest.mark.asyncio
    async def test_direction_override_validates_reason(
        self, client, project_id: str, dataset_id: str
    ):
        """覆盖原因不能为空。"""
        payload = {
            "table_name": "tb_balance",
            "record_id": str(uuid.uuid4()),
            "override_direction": "debit",
            "override_reason": "",  # 空原因
        }

        url = f"{_base_url(project_id, dataset_id)}/direction-override"
        resp = await client.post(url, json=payload)

        # Pydantic 校验 min_length=1 → 422（edit 门禁先放行，再校验请求体）
        assert resp.status_code == 422
        assert _validation_errors(resp) == [("string_too_short", ["body", "override_reason"])]
        client.assert_passed(GATE, times=1)


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
        self, client, project_id: str, dataset_id: str
    ):
        """批量确认返回确认数量。"""
        payload = {
            "anomaly_ids": ["1001", "2221", "6001"],
            "confirm_reason": "审计师已核实，属于真实业务余额",
        }

        url = f"{_base_url(project_id, dataset_id)}/anomalies/batch-confirm"
        resp = await client.post(url, json=payload)

        assert resp.status_code == 200
        parsed = BatchConfirmResponse(**resp.json())
        assert parsed.confirmed_count == 3
        assert parsed.failed_ids == []
        client.assert_passed(GATE, times=1)

    @pytest.mark.asyncio
    async def test_batch_confirm_validates_reason(
        self, client, project_id: str, dataset_id: str
    ):
        """批量确认原因不能为空。"""
        payload = {
            "anomaly_ids": ["1001"],
            "confirm_reason": "",
        }

        url = f"{_base_url(project_id, dataset_id)}/anomalies/batch-confirm"
        resp = await client.post(url, json=payload)

        assert resp.status_code == 422
        assert _validation_errors(resp) == [("string_too_short", ["body", "confirm_reason"])]
        client.assert_passed(GATE, times=1)
