"""publication commit-visibility 端点级判据。

Spec: custom-workpaper-template-ingestion-and-sync-closure, Task 16

## 为什么必须有这个端点

`POST /publications/instantiate` 已就绪，但 publication 停在 PENDING_VISIBILITY
时永远 409。没有 commit-visibility 就**没有任何生产路径**能把状态推到 ACTIVE
（`run_finalize_saga` 与 `resolve_visibility` 此前都零调用方）。

判据分五层：
1. **鉴权**：未登录 401/403；只读角色 403（要 APPROVE_PUBLISH_ORGANIZATION）；
2. **未知 consumer 422**（不能给任意 consumer 灌 ACK）；
3. **缺 ACK 保持 PENDING**，不得提前 ACTIVE；
4. **全 ACCEPTED → ACTIVE**，且响应 `runtimeDiscoverable` 跟随；
5. **已 ACTIVE 幂等返回**（不重复写、不报错）。
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import custom_template_publications as module
from app.routers.custom_template_publications import router
from app.services.custom_template_ingestion.finalize_saga import (
    REQUIRED_FINALIZE_CONSUMERS,
)
from app.services.custom_template_ingestion.lifecycles import PublicationState
from app.services.custom_template_ingestion.publication_registry_store import (
    StoredPublication,
)

NOW = datetime(2026, 11, 15, tzinfo=timezone.utc)
ORG = "org-1"
HANDOFF_ID = "handoff-1"
HANDOFF_DIGEST = "c" * 64


def _stored(
    *,
    key: str = "pub-1",
    state: PublicationState = PublicationState.PENDING_VISIBILITY,
    handoff: dict | None = None,
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
        handoff=handoff if handoff is not None else {
            "handoffId": HANDOFF_ID, "handoffDigest": HANDOFF_DIGEST,
        },
        created_at=NOW,
        updated_at=NOW,
    )


class _User:
    def __init__(self, role: str = "manager") -> None:
        self.id = uuid.uuid4()
        self.role = SimpleNamespace(value=role)


class _Result:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class _Db:
    def __init__(self) -> None:
        self.committed = 0
        self.transitions: list[tuple[str, str]] = []

    async def execute(self, _stmt):
        return _Result(None)

    async def run_sync(self, fn):
        return fn(_SyncView(self))

    async def commit(self):
        self.committed += 1


class _SyncView:
    def __init__(self, db: _Db) -> None:
        self._db = db

    def execute(self, _stmt):
        return _Result(None)

    def add(self, obj):
        return None

    def flush(self):
        return None

    def query(self, *_a, **_k):
        raise AssertionError("commit-visibility 用例不应走到 ORM query 路径")


class _FakeLedger:
    """替身：只记录 upsert / resolve 调用，按注入的 state 返回。"""

    instances: list["_FakeLedger"] = []
    next_state = "PENDING"

    def __init__(self, session) -> None:  # noqa: ARG002
        self.acks: list[tuple[str, str]] = []
        self.resolved = 0
        _FakeLedger.instances.append(self)

    def upsert(self, *, handoff_id, handoff_digest, consumer, consumer_version, verdict, reason_codes=()):
        self.acks.append((consumer, verdict))
        return SimpleNamespace(
            consumer=consumer, consumer_version=consumer_version,
            verdict=verdict, reason_codes=tuple(reason_codes), ack_id=f"ack-{consumer}",
        )

    def resolve(self, *, handoff_id, handoff_digest, required=()):
        self.resolved += 1
        return _FakeLedger.next_state


def _client(
    monkeypatch,
    *,
    user: _User | None,
    db: _Db,
    publication: StoredPublication | None,
    ledger_state: str = "PENDING",
) -> TestClient:
    app = FastAPI()
    app.include_router(router)

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

    monkeypatch.setattr(
        module, "derive_implicit_scope",
        lambda *a, **k: SimpleNamespace(organization_id=ORG),
    )

    from app.services.custom_template_ingestion import publication_registry_store as store
    from app.services.custom_template_ingestion import durable_ack_ledger as dl

    monkeypatch.setattr(
        store, "get_publication",
        lambda session, *, organization_id, publication_key: (
            publication
            if publication is not None and publication.publication_key == publication_key
            else None
        ),
    )

    def _transition(session, *, organization_id, publication_key, to_state, reason, clock=None):
        db.transitions.append((to_state.value, reason))
        return publication

    monkeypatch.setattr(store, "transition_publication", _transition)

    _FakeLedger.instances = []
    _FakeLedger.next_state = ledger_state
    monkeypatch.setattr(dl, "DurableAckLedger", _FakeLedger)
    return TestClient(app)


def _body(pub: str = "pub-1", acks: list[dict] | None = None) -> dict:
    return {"publicationKey": pub, "acks": acks if acks is not None else []}


def _all_acks() -> list[dict]:
    return [
        {"consumer": c, "consumerVersion": "v1", "verdict": "ACCEPTED"}
        for c in REQUIRED_FINALIZE_CONSUMERS
    ]


class TestAuth:
    def test_unauthenticated_rejected(self, monkeypatch) -> None:
        client = _client(monkeypatch, user=None, db=_Db(), publication=_stored())
        assert client.post(
            "/api/custom-template-ingestion/publications/commit-visibility",
            json=_body(),
        ).status_code in (401, 403)

    def test_readonly_role_rejected(self, monkeypatch) -> None:
        client = _client(monkeypatch, user=_User("readonly"), db=_Db(), publication=_stored())
        resp = client.post(
            "/api/custom-template-ingestion/publications/commit-visibility",
            json=_body(),
        )
        assert resp.status_code == 403

    def test_auditor_rejected(self, monkeypatch) -> None:
        """auditor 只有 UPLOAD，不得推进发布可见性。"""
        client = _client(monkeypatch, user=_User("auditor"), db=_Db(), publication=_stored())
        assert client.post(
            "/api/custom-template-ingestion/publications/commit-visibility",
            json=_body(),
        ).status_code == 403

    def test_partner_allowed(self, monkeypatch) -> None:
        """partner 有 FINALIZE_PROJECT，可推进可见性。"""
        client = _client(
            monkeypatch, user=_User("partner"), db=_Db(),
            publication=_stored(), ledger_state="ACTIVE",
        )
        assert client.post(
            "/api/custom-template-ingestion/publications/commit-visibility",
            json=_body(acks=_all_acks()),
        ).status_code == 200

    def test_admin_allowed(self, monkeypatch) -> None:
        """🔴 admin 必须有 FINALIZE_PROJECT —— 浏览器实测曾因误用 approve 权限
        让 admin 直接 403，而库里 partner/qc 用户数为 0 ⇒ 端点实际无人可用。"""
        client = _client(
            monkeypatch, user=_User("admin"), db=_Db(),
            publication=_stored(), ledger_state="ACTIVE",
        )
        assert client.post(
            "/api/custom-template-ingestion/publications/commit-visibility",
            json=_body(acks=_all_acks()),
        ).status_code == 200

    def test_manager_allowed(self, monkeypatch) -> None:
        client = _client(
            monkeypatch, user=_User("manager"), db=_Db(),
            publication=_stored(), ledger_state="ACTIVE",
        )
        assert client.post(
            "/api/custom-template-ingestion/publications/commit-visibility",
            json=_body(acks=_all_acks()),
        ).status_code == 200

    def test_qc_rejected(self, monkeypatch) -> None:
        """qc 只有 APPROVE_PUBLISH_ORGANIZATION（双人复核批准），没有 FINALIZE_PROJECT
        ⇒ 不得推进可见性（语义分离：批准发布 ≠ 技术推进）。"""
        client = _client(monkeypatch, user=_User("qc"), db=_Db(), publication=_stored())
        assert client.post(
            "/api/custom-template-ingestion/publications/commit-visibility",
            json=_body(),
        ).status_code == 403


class TestGates:
    def test_unknown_publication_404(self, monkeypatch) -> None:
        client = _client(monkeypatch, user=_User(), db=_Db(), publication=None)
        assert client.post(
            "/api/custom-template-ingestion/publications/commit-visibility",
            json=_body(),
        ).status_code == 404

    def test_unknown_consumer_422(self, monkeypatch) -> None:
        """🔴 不能给任意 consumer 灌 ACK。"""
        client = _client(monkeypatch, user=_User(), db=_Db(), publication=_stored())
        resp = client.post(
            "/api/custom-template-ingestion/publications/commit-visibility",
            json=_body(acks=[{
                "consumer": "bogus_consumer", "consumerVersion": "v1", "verdict": "ACCEPTED",
            }]),
        )
        assert resp.status_code == 422
        assert "未知 consumer" in resp.json()["detail"]

    def test_missing_handoff_identity_409(self, monkeypatch) -> None:
        client = _client(
            monkeypatch, user=_User(), db=_Db(),
            publication=_stored(handoff={}),
        )
        resp = client.post(
            "/api/custom-template-ingestion/publications/commit-visibility",
            json=_body(),
        )
        assert resp.status_code == 409
        assert "缺少 handoff 身份" in resp.json()["detail"]

    def test_withdrawn_publication_409(self, monkeypatch) -> None:
        client = _client(
            monkeypatch, user=_User(), db=_Db(),
            publication=_stored(state=PublicationState.WITHDRAWN),
        )
        resp = client.post(
            "/api/custom-template-ingestion/publications/commit-visibility",
            json=_body(),
        )
        assert resp.status_code == 409
        assert "不可推进可见性" in resp.json()["detail"]


class TestVisibility:
    def test_partial_acks_stay_pending(self, monkeypatch) -> None:
        db = _Db()
        client = _client(
            monkeypatch, user=_User(), db=db,
            publication=_stored(), ledger_state="PENDING",
        )
        resp = client.post(
            "/api/custom-template-ingestion/publications/commit-visibility",
            json=_body(acks=[{
                "consumer": REQUIRED_FINALIZE_CONSUMERS[0],
                "consumerVersion": "v1", "verdict": "ACCEPTED",
            }]),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["visibilityState"] == "PENDING"
        assert body["state"] == PublicationState.PENDING_VISIBILITY.value
        assert body["runtimeDiscoverable"] is False
        assert db.transitions == []  # 未推进

    def test_all_accepted_becomes_active(self, monkeypatch) -> None:
        db = _Db()
        client = _client(
            monkeypatch, user=_User(), db=db,
            publication=_stored(), ledger_state="ACTIVE",
        )
        acks = _all_acks()
        resp = client.post(
            "/api/custom-template-ingestion/publications/commit-visibility",
            json=_body(acks=acks),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["visibilityState"] == "ACTIVE"
        assert body["state"] == PublicationState.ACTIVE.value
        assert body["runtimeDiscoverable"] is True
        assert db.transitions == [("ACTIVE", "all_acks_accepted")]
        assert db.committed == 1
        # 🔴 ACK 必须真的转发进 ledger —— 只断言状态会漏掉「acks 循环被清空」
        # 的变异（首轮存活：ledger 拿不到任何 ACK 也返回注入的 ACTIVE）。
        ledger = _FakeLedger.instances[-1]
        assert len(ledger.acks) == len(acks)
        assert {c for c, _ in ledger.acks} == set(REQUIRED_FINALIZE_CONSUMERS)
        assert all(v == "ACCEPTED" for _, v in ledger.acks)
        assert ledger.resolved == 1

    def test_rejected_becomes_failed(self, monkeypatch) -> None:
        db = _Db()
        client = _client(
            monkeypatch, user=_User(), db=db,
            publication=_stored(), ledger_state="REJECTED",
        )
        resp = client.post(
            "/api/custom-template-ingestion/publications/commit-visibility",
            json=_body(acks=_all_acks()),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["visibilityState"] == "REJECTED"
        assert body["state"] == PublicationState.FAILED.value
        assert body["runtimeDiscoverable"] is False
        assert db.transitions == [("FAILED", "ack_rejected")]

    def test_already_active_is_idempotent(self, monkeypatch) -> None:
        db = _Db()
        client = _client(
            monkeypatch, user=_User(), db=db,
            publication=_stored(state=PublicationState.ACTIVE),
        )
        resp = client.post(
            "/api/custom-template-ingestion/publications/commit-visibility",
            json=_body(),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["idempotent"] is True
        assert body["runtimeDiscoverable"] is True
        assert db.transitions == []
        assert db.committed == 0

    def test_required_consumers_are_four(self, monkeypatch) -> None:
        client = _client(
            monkeypatch, user=_User(), db=_Db(),
            publication=_stored(), ledger_state="PENDING",
        )
        body = client.post(
            "/api/custom-template-ingestion/publications/commit-visibility",
            json=_body(),
        ).json()
        assert len(body["requiredConsumers"]) == 4
