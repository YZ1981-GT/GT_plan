"""S2 ADR-CCN-06: 门禁逐项确认 — 权限配方表测试

按 D1 分级:
- comparison-fail 类确认仅签字合伙人（partner 角色）
- data-missing / check-exception 类需 edit 级权限
"""

import os
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.routers.gate_acknowledgements import router


def _make_app(role: str = "partner"):
    from app.core.database import get_db
    from app.deps import get_current_user

    app = FastAPI()
    app.include_router(router)

    mock_user = MagicMock()
    mock_user.id = uuid.uuid4()
    mock_user.role = role
    mock_user.system_role = role

    mock_db = AsyncMock()
    mock_db.commit = AsyncMock()

    app.dependency_overrides[get_current_user] = lambda: mock_user
    app.dependency_overrides[get_db] = lambda: mock_db

    return app, mock_user


def _ack_body(check_class: str = "data-missing") -> dict:
    return {
        "year": 2025,
        "check_name": "R4-CROSS-CHECK",
        "status": "failed",
        "result_fingerprint": "abc123",
        "reason": "这是一个足够长的确认原因说明",
        "check_class": check_class,
    }


class TestPermissionRecipeTable:

    @pytest.mark.parametrize(
        "role, check_class, expected_status",
        [
            pytest.param("partner", "comparison-fail", 200, id="partner_comparison_fail_200"),
            pytest.param("manager", "comparison-fail", 403, id="manager_comparison_fail_403"),
            pytest.param("partner", "data-missing", 200, id="partner_data_missing_200"),
            pytest.param("manager", "data-missing", 200, id="manager_data_missing_200"),
            pytest.param("auditor", "data-missing", 200, id="auditor_data_missing_200"),
        ],
    )
    def test_permission_recipe(self, role, check_class, expected_status):
        app, _ = _make_app(role=role)

        with (
            patch.dict(os.environ, {"CONSISTENCY_GATE_ENFORCEMENT": "enforce"}),
            patch("app.deps.assert_project_permission", new=AsyncMock(
                side_effect=lambda db, user, pid, perm: user,
            )),
            patch(
                "app.routers.gate_acknowledgements.ack_svc.acknowledge",
                new=AsyncMock(return_value={"id": str(uuid.uuid4()), "check_name": "R4"}),
            ),
        ):
            client = TestClient(app)
            resp = client.post(
                f"/api/projects/{uuid.uuid4()}/consistency-gate/acknowledgements",
                json=_ack_body(check_class),
            )

        assert resp.status_code == expected_status, (
            f"角色={role} check_class={check_class} "
            f"期望={expected_status} 实际={resp.status_code}"
        )

    def test_review_only_cannot_create(self):
        """review 级用户不能创建确认 → 403"""
        from app.core.database import get_db
        from app.deps import get_current_user

        app = FastAPI()
        app.include_router(router)

        mock_db = AsyncMock()
        app.dependency_overrides[get_db] = lambda: mock_db

        # get_current_user 抛 403 模拟权限不足
        def raise_403():
            raise HTTPException(status_code=403, detail="权限不足")

        app.dependency_overrides[get_current_user] = raise_403

        with patch.dict(os.environ, {"CONSISTENCY_GATE_ENFORCEMENT": "enforce"}):
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.post(
                f"/api/projects/{uuid.uuid4()}/consistency-gate/acknowledgements",
                json=_ack_body(),
            )

        assert resp.status_code == 403

    def test_unauthenticated_401(self):
        """未登录 → 401"""
        from app.core.database import get_db
        from app.deps import get_current_user

        app = FastAPI()
        app.include_router(router)

        mock_db = AsyncMock()
        app.dependency_overrides[get_db] = lambda: mock_db

        def raise_401():
            raise HTTPException(status_code=401, detail="未登录")

        app.dependency_overrides[get_current_user] = raise_401

        with patch.dict(os.environ, {"CONSISTENCY_GATE_ENFORCEMENT": "enforce"}):
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.post(
                f"/api/projects/{uuid.uuid4()}/consistency-gate/acknowledgements",
                json=_ack_body(),
            )

        assert resp.status_code == 401
