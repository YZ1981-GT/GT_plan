"""账套导入直传合同门的单元与 TestClient 验证。

本文件只使用独立 FastAPI app 和 mock session，不连接共享 PG，不创建 bundle、job
或四表数据。bundle-only 请求的旧兼容路径由 service mock 验证。
"""

from __future__ import annotations

import json
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.routers.account_chart import router as account_chart_router
from app.routers.ledger_penetration import router as ledger_router
from app.schemas.ledger_unit_contract import UnitConfirmationInput
from app.services.ledger_import.unit_confirmation_gate import (
    SOURCE_UNIT_CONFIRMATION_REQUIRED,
    UNIT_CONFIRMATION_INVALID,
    parse_unit_confirmation,
    require_direct_file_confirmation,
)


def _confirmation_json() -> str:
    return json.dumps({
        "source_amount_unit": "yuan",
        "source_unit_confirmed": True,
        "unit_evidence_digest": "a" * 64,
    })


def test_direct_file_requires_token_and_schema_contract() -> None:
    with pytest.raises(HTTPException) as exc_info:
        require_direct_file_confirmation(file=object())

    assert exc_info.value.status_code == 428
    assert exc_info.value.detail["error_code"] == SOURCE_UNIT_CONFIRMATION_REQUIRED


def test_confirmation_is_parsed_by_pydantic_not_string_matching() -> None:
    parsed = parse_unit_confirmation(_confirmation_json())
    assert isinstance(parsed, UnitConfirmationInput)
    assert parsed.unit_evidence_digest == "a" * 64

    with pytest.raises(HTTPException) as exc_info:
        parse_unit_confirmation(json.dumps({
            "source_amount_unit": "yuan",
            "source_unit_confirmed": True,
            "unit_evidence_digest": "not-a-digest",
        }))
    assert exc_info.value.status_code == 422
    assert exc_info.value.detail["error_code"] == UNIT_CONFIRMATION_INVALID


def test_bundle_only_path_keeps_legacy_compatibility() -> None:
    assert require_direct_file_confirmation(upload_token="preview-token") is None


def _test_app() -> TestClient:
    api = FastAPI()
    api.include_router(account_chart_router)
    api.include_router(ledger_router)
    actor = SimpleNamespace(id=uuid.uuid4())

    async def _db():
        yield AsyncMock()

    api.dependency_overrides[get_db] = _db

    def _override_access():
        return actor

    def _walk(dependant):
        yield dependant
        for child in dependant.dependencies:
            yield from _walk(child)

    for route in api.routes:
        if not isinstance(route, APIRoute):
            continue
        for dependant in _walk(route.dependant):
            call = dependant.call
            if getattr(call, "__module__", "") == "app.deps":
                api.dependency_overrides[call] = _override_access

    return TestClient(api, raise_server_exceptions=False)


@pytest.mark.parametrize(
    "path",
    [
        "/api/projects/{project_id}/account-chart/import-async",
        "/api/projects/{project_id}/ledger/smart-import",
    ],
)
def test_direct_file_returns_428_before_import_job_or_writer(path: str) -> None:
    project_id = uuid.uuid4()
    with _test_app() as client, patch(
        "app.services.ledger_import_application_service.LedgerImportApplicationService.submit_import_job",
        new_callable=AsyncMock,
    ) as submit:
        response = client.post(
            path.format(project_id=project_id),
            files=[("files", ("ledger.csv", b"account_code,amount\n1001,1\n", "text/csv"))],
        )

    assert response.status_code == 428, response.text
    assert response.json()["detail"]["error_code"] == SOURCE_UNIT_CONFIRMATION_REQUIRED
    submit.assert_not_awaited()


def test_validated_direct_contract_reaches_existing_submit_service() -> None:
    project_id = uuid.uuid4()
    with _test_app() as client, patch(
        "app.services.ledger_import_application_service.LedgerImportApplicationService.submit_import_job",
        new_callable=AsyncMock,
        return_value={"status": "accepted"},
    ) as submit:
        response = client.post(
            f"/api/projects/{project_id}/ledger/smart-import?upload_token=preview-token",
            files=[("files", ("ledger.csv", b"account_code,amount\n1001,1\n", "text/csv"))],
            data={"unit_confirmation": _confirmation_json()},
        )

    assert response.status_code == 200, response.text
    assert submit.await_count == 1
    assert isinstance(submit.await_args.kwargs["unit_confirmation"], UnitConfirmationInput)


def test_retired_account_chart_endpoint_is_real_410_with_edit_gate() -> None:
    project_id = uuid.uuid4()
    with _test_app() as client:
        response = client.post(
            f"/api/projects/{project_id}/account-chart/import",
            files={"file": ("ledger.csv", b"not-used", "text/csv")},
        )

    assert response.status_code == 410, response.text
    assert response.json()["detail"]["error_code"] == "LEDGER_IMPORT_MOVED_TO_CONFIRMED_JOB"
