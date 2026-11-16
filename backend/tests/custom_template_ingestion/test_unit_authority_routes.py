"""custom workbook unit-authority PUT 端点级守卫。

覆盖 ingest → preflight → authority PUT 的第二阶段：
- artifact sha256 + preflight digest + manifest digest 三重 CAS；
- WorkingPaper project_id 归属 + edit 权限；
- 同 workbook hash 同 manifest digest 幂等；不同 authority 冲突 409；
- amount region 的 stable id / unit / divisor 与 ratio scale 契约。
"""

from __future__ import annotations

import hashlib
import json
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import custom_template_ingestion as module
from app.routers.custom_template_ingestion import router


class _User:
    id = uuid.uuid4()
    role = SimpleNamespace(value="manager")


class _Result:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class _Db:
    def __init__(self, wp):
        self.wp = wp
        self.authority = None
        self.calls = 0
        self.added = []

    async def execute(self, _stmt):
        self.calls += 1
        # Each endpoint request queries WorkingPaper first, then authority.
        if self.calls % 2 == 1:
            return _Result(self.wp)
        return _Result(self.authority)

    def add(self, obj):
        self.added.append(obj)
        self.authority = obj
        if obj.id is None:
            obj.id = uuid.uuid4()

    async def flush(self):
        return None

    async def commit(self):
        return None


class _Quarantine:
    def __init__(self, manifest):
        self.manifest = manifest

    def load_manifest(self, organization_id, artifact_id):  # noqa: ARG002
        return dict(self.manifest)


def _manifest():
    return {
        "regions": [
            {
                "stableId": "sheet-amount-1",
                "measureKind": "amount",
                "unit": "wan",
                "divisor": 10000,
            },
            {
                "stableId": "sheet-ratio-1",
                "measureKind": "ratio",
                "ratioScale": "fraction",
            },
        ],
        "sheetCount": 1,
    }


def _body(manifest=None):
    manifest = manifest or _manifest()
    return {
        "workingPaperId": str(uuid.UUID(int=2)),
        "workbookSha256": "a" * 64,
        "preflightDigest": "b" * 64,
        "manifest": manifest,
        "manifestDigest": hashlib.sha256(
            json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
    }


def _client(db, quarantine):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[module.get_current_user] = lambda: _User()
    app.dependency_overrides[module.get_db] = lambda: db
    return TestClient(app), patch.object(
        module,
        "get_quarantine",
        return_value=quarantine,
    ), patch.object(module, "assert_project_permission", new_callable=AsyncMock)


def test_unit_authority_put_is_project_scoped_and_idempotent():
    project_id = uuid.UUID(int=1)
    wp_id = uuid.UUID(int=2)
    db = _Db(SimpleNamespace(id=wp_id, project_id=project_id, is_deleted=False))
    quarantine = _Quarantine({
        "organizationId": "org-1",
        "state": "PREFLIGHT_READY",
        "sha256": "a" * 64,
        "preflightDigest": "b" * 64,
    })
    client, q_patch, permission = _client(db, quarantine)
    with q_patch, permission as check:
        first = client.put(
            "/api/custom-template-ingestion/artifacts/art-1/unit-authority",
            json=_body(),
        )
        second = client.put(
            "/api/custom-template-ingestion/artifacts/art-1/unit-authority",
            json=_body(),
        )

    assert first.status_code == 200, first.text
    assert first.json()["idempotent"] is False
    assert second.status_code == 200, second.text
    assert second.json()["idempotent"] is True
    assert check.await_count == 2
    for call in check.await_args_list:
        assert call.args[0] is db
        assert call.args[2] == project_id
        assert call.args[3] == "edit"
    assert len(db.added) == 1


def test_unit_authority_rejects_artifact_digest_mismatch():
    project_id = uuid.UUID(int=1)
    db = _Db(SimpleNamespace(id=uuid.UUID(int=2), project_id=project_id, is_deleted=False))
    quarantine = _Quarantine({
        "organizationId": "org-1",
        "state": "PREFLIGHT_READY",
        "sha256": "c" * 64,
        "preflightDigest": "b" * 64,
    })
    client, q_patch, permission = _client(db, quarantine)
    with q_patch, permission:
        response = client.put(
            "/api/custom-template-ingestion/artifacts/art-1/unit-authority",
            json=_body(),
        )
    assert response.status_code == 409
    assert "sha256" in response.text
    assert not db.added


def test_unit_authority_rejects_manifest_digest_mismatch():
    project_id = uuid.UUID(int=1)
    db = _Db(SimpleNamespace(id=uuid.UUID(int=2), project_id=project_id, is_deleted=False))
    quarantine = _Quarantine({
        "organizationId": "org-1",
        "state": "PREFLIGHT_READY",
        "sha256": "a" * 64,
        "preflightDigest": "b" * 64,
    })
    body = _body()
    body["manifestDigest"] = "c" * 64
    client, q_patch, permission = _client(db, quarantine)
    with q_patch, permission:
        response = client.put(
            "/api/custom-template-ingestion/artifacts/art-1/unit-authority",
            json=body,
        )
    assert response.status_code == 409
    assert "manifest digest" in response.text
    assert not db.added


def test_unit_authority_rejects_invalid_region_contract():
    project_id = uuid.UUID(int=1)
    db = _Db(SimpleNamespace(id=uuid.UUID(int=2), project_id=project_id, is_deleted=False))
    quarantine = _Quarantine({
        "organizationId": "org-1",
        "state": "PREFLIGHT_READY",
        "sha256": "a" * 64,
        "preflightDigest": "b" * 64,
    })
    manifest = {"regions": [{"stableId": "r", "measureKind": "ratio"}]}
    client, q_patch, permission = _client(db, quarantine)
    with q_patch, permission:
        response = client.put(
            "/api/custom-template-ingestion/artifacts/art-1/unit-authority",
            json=_body(manifest),
        )
    assert response.status_code == 422
    assert "ratio" in response.text
    assert not db.added


def test_unit_authority_rejects_non_ready_artifact():
    project_id = uuid.UUID(int=1)
    db = _Db(SimpleNamespace(id=uuid.UUID(int=2), project_id=project_id, is_deleted=False))
    quarantine = _Quarantine({
        "organizationId": "org-1",
        "state": "QUARANTINED",
        "sha256": "a" * 64,
        "preflightDigest": "b" * 64,
    })
    client, q_patch, permission = _client(db, quarantine)
    with q_patch, permission:
        response = client.put(
            "/api/custom-template-ingestion/artifacts/art-1/unit-authority",
            json=_body(),
        )
    assert response.status_code == 409
    assert "preflight" in response.text
    assert not db.added


def test_unit_authority_rejects_same_hash_different_manifest():
    project_id = uuid.UUID(int=1)
    db = _Db(SimpleNamespace(id=uuid.UUID(int=2), project_id=project_id, is_deleted=False))
    quarantine = _Quarantine({
        "organizationId": "org-1",
        "state": "PREFLIGHT_READY",
        "sha256": "a" * 64,
        "preflightDigest": "b" * 64,
    })
    client, q_patch, permission = _client(db, quarantine)
    first_body = _body()
    changed_manifest = {"regions": [{"stableId": "different", "measureKind": "amount", "unit": "yuan", "divisor": 1}]}
    second_body = _body(changed_manifest)
    with q_patch, permission:
        first = client.put(
            "/api/custom-template-ingestion/artifacts/art-1/unit-authority",
            json=first_body,
        )
        second = client.put(
            "/api/custom-template-ingestion/artifacts/art-1/unit-authority",
            json=second_body,
        )
    assert first.status_code == 200
    assert second.status_code == 409
    assert "不同 authority" in second.text


def test_unit_authority_rejects_preflight_digest_mismatch():
    project_id = uuid.UUID(int=1)
    db = _Db(SimpleNamespace(id=uuid.UUID(int=2), project_id=project_id, is_deleted=False))
    quarantine = _Quarantine({
        "organizationId": "org-1",
        "state": "PREFLIGHT_READY",
        "sha256": "a" * 64,
        "preflightDigest": "b" * 64,
    })
    body = _body()
    body["preflightDigest"] = "c" * 64
    client, q_patch, permission = _client(db, quarantine)
    with q_patch, permission:
        response = client.put(
            "/api/custom-template-ingestion/artifacts/art-1/unit-authority",
            json=body,
        )
    assert response.status_code == 409
    assert "preflight digest" in response.text
    assert not db.added
