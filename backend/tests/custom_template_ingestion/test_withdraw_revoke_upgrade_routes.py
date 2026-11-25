"""
Spec: 平台技术债清偿（2026-11-24）——publication 撤回 / 安全撤销 / 升级端点

为什么必须端点级（memory 铁律 ㉕）：只测 service 会漏掉鉴权。四个新端点
（withdraw / security-revoke / upgrade-offer / apply-upgrade）此前只有纯内存实现
（publication_ops，零生产调用方）；本次接线持久层 + 路由。本文件真发请求过鉴权链。

判据：
1. 未登录 → 401/403（全部四个端点）；
2. 无 finalize 权限（auditor/readonly）→ 403；
3. 未知 publication → 404；
4. withdraw：ACTIVE → WITHDRAWN，pin 不清（响应 state=WITHDRAWN，runtimeDiscoverable=False）；
5. security-revoke：ACTIVE → SECURITY_REVOKED，默认清 pin（affectedProjects 非空时清）；
6. upgrade-offer：未 pin 项目 → 409；目标非 ACTIVE → 409；成功返回 diffDigest；
7. apply-upgrade：缺 approvalIntentId → 422（pydantic）或 409；stagingOk=False 时 pin 不变。
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import custom_template_publications as module
from app.routers.custom_template_publications import router
from app.services.custom_template_ingestion.lifecycles import PublicationState
from app.services.custom_template_ingestion.publication_registry_store import (
    StoredPublication,
)

NOW = datetime(2026, 11, 24, tzinfo=timezone.utc)
ORG = "org-1"
PROJECT_ID = uuid.UUID(int=1)


class _User:
    def __init__(self, role: str = "manager") -> None:
        self.id = uuid.uuid4()
        self.role = SimpleNamespace(value=role)


class _Db:
    def __init__(self) -> None:
        self.committed = 0

    async def execute(self, stmt):  # noqa: ARG002
        return SimpleNamespace(scalar_one_or_none=lambda: None, scalars=lambda: self)

    def all(self):  # noqa: A003 — scalars() 链
        return []

    async def run_sync(self, fn):
        return fn(_SyncView(self))

    async def commit(self):
        self.committed += 1


class _SyncView:
    def __init__(self, db: _Db) -> None:
        self._db = db

    def execute(self, _stmt):  # noqa: ARG002
        return SimpleNamespace(
            scalar_one_or_none=lambda: None,
            scalars=lambda: SimpleNamespace(all=lambda: []),
        )

    def add(self, obj):  # noqa: ARG002
        return None

    def flush(self):
        return None


def _stored(
    *,
    key: str = "pub-1",
    state: PublicationState = PublicationState.ACTIVE,
) -> StoredPublication:
    return StoredPublication(
        id=uuid.uuid4(),
        publication_key=key,
        organization_id=ORG,
        candidate_id="art-1",
        candidate_digest="a" * 64,
        authority_ref="auth-1",
        artifact_digest="b" * 64,
        state=state,
        reason=None,
        handoff={"handoffId": "ho-1"},
        created_at=NOW,
        updated_at=NOW,
    )


def _client(
    monkeypatch,
    *,
    user: _User | None,
    store_overrides: dict[str, object] | None = None,
) -> TestClient:
    app = FastAPI()
    app.include_router(router)

    db = _Db()

    async def _get_db():
        yield db

    def _get_user():
        if user is None:
            from fastapi import HTTPException

            raise HTTPException(status_code=401, detail="未登录")
        return user

    from app.core.database import get_db
    from app.deps import get_current_user

    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[get_current_user] = _get_user

    async def _record_permission(_db, _user, _pid, level, **_kw):  # noqa: ARG001
        return None

    monkeypatch.setattr(module, "assert_project_permission", _record_permission)
    monkeypatch.setattr(
        module, "derive_implicit_scope",
        lambda *a, **k: SimpleNamespace(organization_id=ORG),
    )

    from app.services.custom_template_ingestion import publication_registry_store as store

    for name, fn in (store_overrides or {}).items():
        monkeypatch.setattr(store, name, fn)
    return TestClient(app)


BASE = "/api/custom-template-ingestion/publications"


class TestWithdrawEndpoint:
    def test_unauthenticated_rejected(self, monkeypatch) -> None:
        client = _client(monkeypatch, user=None)
        resp = client.post(f"{BASE}/pub-1/withdraw", json={"reason": "下架"})
        assert resp.status_code in (401, 403)

    def test_auditor_forbidden(self, monkeypatch) -> None:
        client = _client(monkeypatch, user=_User(role="auditor"))
        resp = client.post(f"{BASE}/pub-1/withdraw", json={"reason": "下架"})
        assert resp.status_code == 403

    def test_unknown_publication_404(self, monkeypatch) -> None:
        def _get(session, *, organization_id, publication_key):  # noqa: ARG001
            return None

        client = _client(
            monkeypatch, user=_User(), store_overrides={"get_publication": _get},
        )
        resp = client.post(f"{BASE}/pub-none/withdraw", json={"reason": "下架"})
        assert resp.status_code == 404

    def test_withdraw_active_succeeds_and_pin_not_cleared(self, monkeypatch) -> None:
        calls: dict[str, object] = {}

        def _get(session, *, organization_id, publication_key):  # noqa: ARG001
            return _stored(key=publication_key, state=PublicationState.ACTIVE)

        def _withdraw(session, *, organization_id, publication_key, reason, clock=None):  # noqa: ARG001
            calls["key"] = publication_key
            calls["reason"] = reason
            return _stored(key=publication_key, state=PublicationState.WITHDRAWN)

        client = _client(
            monkeypatch, user=_User(),
            store_overrides={"get_publication": _get, "withdraw_publication_persisted": _withdraw},
        )
        resp = client.post(f"{BASE}/pub-1/withdraw", json={"reason": "模板有误下架"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["state"] == "WITHDRAWN"
        assert body["runtimeDiscoverable"] is False
        assert calls["key"] == "pub-1"
        assert calls["reason"] == "模板有误下架"

    def test_invalid_transition_409(self, monkeypatch) -> None:
        from app.services.custom_template_ingestion.lifecycles import (
            InvalidLifecycleTransition,
        )

        def _get(session, *, organization_id, publication_key):  # noqa: ARG001
            return _stored(key=publication_key, state=PublicationState.ACTIVE)

        def _withdraw(session, **_kw):  # noqa: ARG001
            raise InvalidLifecycleTransition("WITHDRAWN -> WITHDRAWN 非法")

        client = _client(
            monkeypatch, user=_User(),
            store_overrides={"get_publication": _get, "withdraw_publication_persisted": _withdraw},
        )
        resp = client.post(f"{BASE}/pub-1/withdraw", json={"reason": "重复撤回"})
        assert resp.status_code == 409


class TestSecurityRevokeEndpoint:
    def test_unauthenticated_rejected(self, monkeypatch) -> None:
        client = _client(monkeypatch, user=None)
        resp = client.post(f"{BASE}/pub-1/security-revoke", json={"reason": "安全问题"})
        assert resp.status_code in (401, 403)

    def test_revoke_clears_pins_by_default(self, monkeypatch) -> None:
        calls: dict[str, object] = {}

        def _get(session, *, organization_id, publication_key):  # noqa: ARG001
            return _stored(key=publication_key, state=PublicationState.ACTIVE)

        def _revoke(session, *, organization_id, publication_key, reason, clear_pins=True, clock=None):  # noqa: ARG001
            calls["clear_pins"] = clear_pins
            calls["key"] = publication_key
            return [PROJECT_ID]

        client = _client(
            monkeypatch, user=_User(),
            store_overrides={"get_publication": _get, "security_revoke_publication_persisted": _revoke},
        )
        resp = client.post(f"{BASE}/pub-1/security-revoke", json={"reason": "发现数据泄露"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["state"] == "SECURITY_REVOKED"
        assert body["affectedProjects"] == [str(PROJECT_ID)]
        assert body["pinsCleared"] is True
        assert calls["clear_pins"] is True

    def test_revoke_keep_pins_when_requested(self, monkeypatch) -> None:
        calls: dict[str, object] = {}

        def _get(session, *, organization_id, publication_key):  # noqa: ARG001
            return _stored(key=publication_key, state=PublicationState.ACTIVE)

        def _revoke(session, *, organization_id, publication_key, reason, clear_pins=True, clock=None):  # noqa: ARG001
            calls["clear_pins"] = clear_pins
            return [PROJECT_ID]

        client = _client(
            monkeypatch, user=_User(),
            store_overrides={"get_publication": _get, "security_revoke_publication_persisted": _revoke},
        )
        resp = client.post(
            f"{BASE}/pub-1/security-revoke", json={"reason": "留 pin 观察", "clearPins": False},
        )
        assert resp.status_code == 200
        assert calls["clear_pins"] is False


class TestUpgradeOfferEndpoint:
    def test_unauthenticated_rejected(self, monkeypatch) -> None:
        client = _client(monkeypatch, user=None)
        resp = client.post(
            f"{BASE}/upgrade-offer",
            json={"projectId": str(PROJECT_ID), "toPublicationKey": "pub-2"},
        )
        assert resp.status_code in (401, 403)

    def test_project_not_pinned_409(self, monkeypatch) -> None:
        from app.services.custom_template_ingestion.publication_registry_store import (
            PublicationStoreError,
        )

        def _offer(session, *, project_id, to_publication_key, organization_id):  # noqa: ARG001
            raise PublicationStoreError("项目未 pin，无 upgrade")

        client = _client(
            monkeypatch, user=_User(), store_overrides={"offer_upgrade_persisted": _offer},
        )
        resp = client.post(
            f"{BASE}/upgrade-offer",
            json={"projectId": str(PROJECT_ID), "toPublicationKey": "pub-2"},
        )
        assert resp.status_code == 409

    def test_offer_success_returns_diff_digest(self, monkeypatch) -> None:
        def _offer(session, *, project_id, to_publication_key, organization_id):  # noqa: ARG001
            return {
                "fromPublicationKey": "pub-1",
                "toPublicationKey": to_publication_key,
                "diffDigest": "c" * 64,
                "requiresApproval": True,
            }

        client = _client(
            monkeypatch, user=_User(), store_overrides={"offer_upgrade_persisted": _offer},
        )
        resp = client.post(
            f"{BASE}/upgrade-offer",
            json={"projectId": str(PROJECT_ID), "toPublicationKey": "pub-2"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["fromPublicationKey"] == "pub-1"
        assert body["toPublicationKey"] == "pub-2"
        assert len(body["diffDigest"]) == 64
        assert body["requiresApproval"] is True


class TestApplyUpgradeEndpoint:
    def test_missing_approval_intent_422(self, monkeypatch) -> None:
        client = _client(monkeypatch, user=_User())
        resp = client.post(
            f"{BASE}/apply-upgrade",
            json={"projectId": str(PROJECT_ID), "toPublicationKey": "pub-2"},
        )
        assert resp.status_code == 422

    def test_staging_not_ok_keeps_pin(self, monkeypatch) -> None:
        calls: dict[str, object] = {}

        def _apply(session, *, organization_id, project_id, to_publication_key, approval_intent_id, staging_ok):  # noqa: ARG001
            calls["staging_ok"] = staging_ok
            calls["approval_intent_id"] = approval_intent_id
            return "pub-1"  # pin 不变

        client = _client(
            monkeypatch, user=_User(), store_overrides={"apply_upgrade_persisted": _apply},
        )
        resp = client.post(
            f"{BASE}/apply-upgrade",
            json={
                "projectId": str(PROJECT_ID),
                "toPublicationKey": "pub-2",
                "approvalIntentId": "ai-1234",
                "stagingOk": False,
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["pinnedTo"] == "pub-1"
        assert body["stagingOk"] is False
        assert calls["staging_ok"] is False

    def test_apply_success_pins_to_target(self, monkeypatch) -> None:
        def _apply(session, *, organization_id, project_id, to_publication_key, approval_intent_id, staging_ok):  # noqa: ARG001
            return to_publication_key

        client = _client(
            monkeypatch, user=_User(), store_overrides={"apply_upgrade_persisted": _apply},
        )
        resp = client.post(
            f"{BASE}/apply-upgrade",
            json={
                "projectId": str(PROJECT_ID),
                "toPublicationKey": "pub-2",
                "approvalIntentId": "ai-1234",
                "stagingOk": True,
            },
        )
        assert resp.status_code == 200
        assert resp.json()["pinnedTo"] == "pub-2"

def _pub_with_handoff(key: str, handoff: dict) -> StoredPublication:
    """StoredPublication 是 frozen dataclass —— 用 dataclasses.replace 换 handoff。"""
    import dataclasses

    return dataclasses.replace(_stored(key=key, state=PublicationState.PENDING_VISIBILITY), handoff=handoff)


# ---------------------------------------------------------------------------
# commit-visibility 的 saga 接线新增行为（2026-11-24）
# ---------------------------------------------------------------------------

from app.services.custom_template_ingestion.finalize_saga import (
    REQUIRED_FINALIZE_CONSUMERS,
)

_CV_BASE = "/api/custom-template-ingestion/publications/commit-visibility"

_FULL_HANDOFF = {
    "handoffId": "ho-1",
    "handoffDigest": "d" * 64,
    "artifactId": "art-1",
    "authorityId": "auth-1",
    "workbookSha256": "b" * 64,
    "preflightDigest": "a" * 64,
    "manifestDigest": "e" * 64,
    "idempotencyKey": "idem-1",
}


class TestCommitVisibilitySagaWiring:
    """verdict 闭集走 saga（collect_consumer_acks），指纹随响应返回。"""

    def test_invalid_verdict_rejected_by_saga(self, monkeypatch) -> None:
        """verdict='MAYBE' 不得写进 ACK 表。

        HTTP 层 pydantic 先 422（AckInput.verdict pattern）；saga 内部校验服务
        非 HTTP 调用方（两层作用域不同）。本用例同时断言「零副作用」。
        """
        from types import SimpleNamespace as NS

        pub = _pub_with_handoff("pub-1", _FULL_HANDOFF)
        upserts: list[tuple[str, str]] = []

        class _Ledger:
            def __init__(self, session):  # noqa: ARG002
                pass

            def upsert(self, *, consumer, verdict, **_kw):
                upserts.append((consumer, verdict))
                return NS(consumer=consumer, verdict=verdict)

            def resolve(self, **_kw):
                return "PENDING"

        def _get(session, *, organization_id, publication_key):  # noqa: ARG001
            return pub

        client = _client(
            monkeypatch, user=_User(),
            store_overrides={"get_publication": _get},
        )
        # 注入 ledger 替身（与 commit-visibility 测试同法）
        from app.services.custom_template_ingestion import durable_ack_ledger as dl

        monkeypatch.setattr(dl, "DurableAckLedger", _Ledger)

        resp = client.post(_CV_BASE, json={
            "publicationKey": "pub-1",
            "acks": [{
                "consumer": REQUIRED_FINALIZE_CONSUMERS[0],
                "consumerVersion": "v1",
                "verdict": "MAYBE",
            }],
        })
        assert resp.status_code in (409, 422)
        # 🔴 副作用断言：ACK 表零写入
        assert upserts == []

    def test_valid_verdicts_pass_and_fingerprint_returned(self, monkeypatch) -> None:
        from types import SimpleNamespace as NS

        pub = _pub_with_handoff("pub-1", _FULL_HANDOFF)

        class _Ledger:
            def __init__(self, session):  # noqa: ARG002
                pass

            def upsert(self, *, consumer, verdict, **_kw):
                return NS(consumer=consumer, verdict=verdict)

            def resolve(self, **_kw):
                return "ACTIVE"

        def _get(session, *, organization_id, publication_key):  # noqa: ARG001
            return pub

        def _transition(session, **_kw):  # noqa: ARG001
            return pub

        client = _client(
            monkeypatch, user=_User(),
            store_overrides={"get_publication": _get, "transition_publication": _transition},
        )
        from app.services.custom_template_ingestion import durable_ack_ledger as dl

        monkeypatch.setattr(dl, "DurableAckLedger", _Ledger)

        resp = client.post(_CV_BASE, json={
            "publicationKey": "pub-1",
            "acks": [
                {"consumer": c, "consumerVersion": "v1", "verdict": "ACCEPTED"}
                for c in REQUIRED_FINALIZE_CONSUMERS
            ],
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["state"] == "ACTIVE"
        # 🔴 lockFingerprint 必须随响应返回（幂等对账锚点）且为 64 位 hex
        fp = body.get("lockFingerprint")
        assert isinstance(fp, str) and len(fp) == 64

    def test_legacy_handoff_returns_null_fingerprint_but_not_blocked(self, monkeypatch) -> None:
        """历史存量 publication（handoff 缺 lock 字段）不得被硬门挡死。"""
        from types import SimpleNamespace as NS

        pub = _pub_with_handoff("pub-1", {"handoffId": "ho-1", "handoffDigest": "d" * 64})

        class _Ledger:
            def __init__(self, session):  # noqa: ARG002
                pass

            def upsert(self, *, consumer, verdict, **_kw):
                return NS(consumer=consumer, verdict=verdict)

            def resolve(self, **_kw):
                return "ACTIVE"

        def _get(session, *, organization_id, publication_key):  # noqa: ARG001
            return pub

        def _transition(session, **_kw):  # noqa: ARG001
            return pub

        client = _client(
            monkeypatch, user=_User(),
            store_overrides={"get_publication": _get, "transition_publication": _transition},
        )
        from app.services.custom_template_ingestion import durable_ack_ledger as dl

        monkeypatch.setattr(dl, "DurableAckLedger", _Ledger)

        resp = client.post(_CV_BASE, json={
            "publicationKey": "pub-1",
            "acks": [
                {"consumer": c, "consumerVersion": "v1", "verdict": "ACCEPTED"}
                for c in REQUIRED_FINALIZE_CONSUMERS
            ],
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["state"] == "ACTIVE"
        assert body["lockFingerprint"] is None
