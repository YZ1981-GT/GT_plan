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

    async def run_sync(self, fn):
        """模拟 AsyncSession.run_sync：把自身当作 sync Session 交给回调。

        🔴 publication 落库走 run_sync（仓储是 sync Session 友好的），
        替身不提供会让 finalize 用例全部 AttributeError。
        注意：仓储内部用**同步** `session.execute()`，而本替身的 execute 是
        async，故这里包一层同步适配器，按当前轮次序号直接返回下一个预置结果。
        """
        return fn(_SyncDbView(self))

    def query(self, *args, **kwargs):  # noqa: ARG002
        """仓储的 register_publication 用 query(...).filter(...).one_or_none()。"""
        raise AssertionError(
            "finalize 用例不应触发 publication 查询路径；"
            "若新增断言需要，请为本替身补 query 实现"
        )


class _SyncDbView:
    """把 `_Db` 的 async execute 包装成同步接口，仅供 run_sync 内的仓储使用。

    `register_publication` 只做 `select(...).scalar_one_or_none()` 判存在与
    `session.add/flush`。这里让 select 恒返回 None（= 尚无 publication），
    并把 add/flush 转发给替身记账。
    """

    def __init__(self, db: "_Db") -> None:
        self._db = db

    def execute(self, _stmt):
        self._db.selects = getattr(self._db, "selects", 0) + 1
        return _Result(None)

    def add(self, obj):
        self._db.publications = getattr(self._db, "publications", [])
        self._db.publications.append(obj)

    def flush(self):
        return None


class _Quarantine:
    def __init__(self, manifest):
        self.manifest = manifest

    def load_manifest(self, organization_id, artifact_id):  # noqa: ARG002
        return dict(self.manifest)

    def update_manifest_fields(self, organization_id, artifact_id, fields, *, state=None):  # noqa: ARG002
        self.manifest.update(fields)
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


def test_finalize_authority_creates_non_active_handoff_and_is_idempotent():
    """finalize 只冻结 handoff，不绕过到 ACTIVE/instantiate。"""
    project_id = uuid.UUID(int=1)
    db = _Db(SimpleNamespace(id=uuid.UUID(int=2), project_id=project_id, is_deleted=False))
    quarantine = _Quarantine({
        "organizationId": "org-1",
        "state": "PREFLIGHT_READY",
        "sha256": "a" * 64,
        "preflightDigest": "b" * 64,
    })
    client, q_patch, permission = _client(db, quarantine)
    with q_patch, permission:
        authority_response = client.put(
            "/api/custom-template-ingestion/artifacts/art-1/unit-authority",
            json=_body(),
        )
        assert authority_response.status_code == 200, authority_response.text
        authority_id = authority_response.json()["authorityId"]
        body = {
            "workingPaperId": str(uuid.UUID(int=2)),
            "authorityId": authority_id,
            "manifestDigest": _body()["manifestDigest"],
            "idempotencyKey": "finalize-key-1",
        }
        first = client.post(
            "/api/custom-template-ingestion/artifacts/art-1/finalize",
            json=body,
        )
        second = client.post(
            "/api/custom-template-ingestion/artifacts/art-1/finalize",
            json=body,
        )

    assert first.status_code == 200, first.text
    assert first.json()["phase"] == "finalized"
    assert first.json()["runtimeDiscoverable"] is False
    assert first.json()["idempotent"] is False
    assert second.status_code == 200, second.text
    assert second.json()["handoffDigest"] == first.json()["handoffDigest"]
    assert second.json()["idempotent"] is True
    assert second.json()["runtimeDiscoverable"] is False

    # 🔴 finalize 必须真的把 publication 落库（PENDING_VISIBILITY），
    # 否则进程重启就丢，且 instantiate 链路根本接不上。
    # 首版只断言 handoff 字段 ⇒ 把 register_publication 换成不存在的名字仍然全绿。
    pubs = getattr(db, "publications", [])
    assert len(pubs) == 1, "finalize 未登记 publication"
    assert pubs[0].state == "PENDING_VISIBILITY"
    assert pubs[0].artifact_digest == "a" * 64
    assert pubs[0].publication_key.startswith("pub-art-1-")
    assert pubs[0].handoff["phase"] == "finalized"
    # 幂等重放不得再登记第二条
    assert first.json()["publicationKey"] == second.json()["publicationKey"]


def test_finalize_rejects_authority_manifest_digest_drift():
    project_id = uuid.UUID(int=1)
    db = _Db(SimpleNamespace(id=uuid.UUID(int=2), project_id=project_id, is_deleted=False))
    quarantine = _Quarantine({
        "organizationId": "org-1",
        "state": "PREFLIGHT_READY",
        "sha256": "a" * 64,
        "preflightDigest": "b" * 64,
    })
    client, q_patch, permission = _client(db, quarantine)
    with q_patch, permission:
        authority_response = client.put(
            "/api/custom-template-ingestion/artifacts/art-1/unit-authority",
            json=_body(),
        )
        authority_id = authority_response.json()["authorityId"]
        response = client.post(
            "/api/custom-template-ingestion/artifacts/art-1/finalize",
            json={
                "workingPaperId": str(uuid.UUID(int=2)),
                "authorityId": authority_id,
                "manifestDigest": "c" * 64,
                "idempotencyKey": "finalize-key-2",
            },
        )
    assert response.status_code == 409
    assert "manifest digest" in response.text


def test_finalize_rejects_non_preflight_artifact():
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
        response = client.post(
            "/api/custom-template-ingestion/artifacts/art-1/finalize",
            json={
                "workingPaperId": str(uuid.UUID(int=2)),
                "authorityId": str(uuid.uuid4()),
                "manifestDigest": "a" * 64,
                "idempotencyKey": "finalize-key-3",
            },
        )
    assert response.status_code == 409
    assert "preflight" in response.text


def test_finalize_rejects_different_idempotency_handoff():
    project_id = uuid.UUID(int=1)
    db = _Db(SimpleNamespace(id=uuid.UUID(int=2), project_id=project_id, is_deleted=False))
    quarantine = _Quarantine({
        "organizationId": "org-1",
        "state": "PREFLIGHT_READY",
        "sha256": "a" * 64,
        "preflightDigest": "b" * 64,
    })
    client, q_patch, permission = _client(db, quarantine)
    with q_patch, permission:
        authority_response = client.put(
            "/api/custom-template-ingestion/artifacts/art-1/unit-authority",
            json=_body(),
        )
        authority_id = authority_response.json()["authorityId"]
        base = {
            "workingPaperId": str(uuid.UUID(int=2)),
            "authorityId": authority_id,
            "manifestDigest": _body()["manifestDigest"],
        }
        first = client.post(
            "/api/custom-template-ingestion/artifacts/art-1/finalize",
            json={**base, "idempotencyKey": "finalize-key-a"},
        )
        second = client.post(
            "/api/custom-template-ingestion/artifacts/art-1/finalize",
            json={**base, "idempotencyKey": "finalize-key-b"},
        )
    assert first.status_code == 200
    assert second.status_code == 409
    assert "不同 finalize" in second.text
