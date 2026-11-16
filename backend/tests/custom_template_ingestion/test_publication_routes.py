"""publication registry 端点级判据（list / instantiate）。

Spec: custom-workpaper-template-ingestion-and-sync-closure

## 为什么必须端点级

memory 铁律 ㉕：只测 service 会漏掉鉴权 —— 前几轮出现过「新端点只挂 get_db、
零鉴权、任意 project_id 可未授权读」。本文件真发请求过鉴权链。

判据：
1. 未登录 → 401/403；
2. list 只返回本组织的 publication（跨组织不可见）；
3. instantiate 必须 `require_project_access("edit")` —— 只读角色被拒；
4. **非 ACTIVE 的 publication 不可实例化**（409），响应里 runtimeDiscoverable
   与 state 一起自证；
5. instantiate 成功时显式返回 `instantiated: false`（pin ≠ 完成实例化）。
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import custom_template_ingestion as module
from app.routers.custom_template_ingestion import router
from app.services.custom_template_ingestion.lifecycles import PublicationState
from app.services.custom_template_ingestion.publication_registry_store import (
    StoredPublication,
)

NOW = datetime(2026, 11, 15, tzinfo=timezone.utc)
ORG = "org-1"


def _stored(
    *,
    key: str = "pub-1",
    state: PublicationState = PublicationState.ACTIVE,
    organization_id: str = ORG,
) -> StoredPublication:
    return StoredPublication(
        id=uuid.uuid4(),
        publication_key=key,
        organization_id=organization_id,
        candidate_id="cand-1",
        candidate_digest="a" * 64,
        authority_ref="auth-1",
        artifact_digest="b" * 64,
        state=state,
        reason=None,
        handoff={"handoffId": "ho-1"},
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
    """按查询意图分派的替身。

    🔴 端点会连续发三种查询：WorkingPaper / publication-存在性 / 成员级别。
    首版固定返回同一个对象，导致 `_load_member_level` 拿到 SimpleNamespace
    再 `.value` 就 AttributeError ⇒ 必须按语句特征分派。
    """

    def __init__(self, wp=None) -> None:
        self.wp = wp
        self.committed = 0

    async def execute(self, stmt):
        text = str(stmt)
        if "working_paper" in text.lower():
            return _Result(self.wp)
        if "project_users" in text.lower():
            # 成员级别行：放行到 "edit"
            return _Result(SimpleNamespace(value="edit"))
        return _Result(None)

    async def get(self, _model, pid):  # noqa: ARG002
        """`_check_project_not_archived` 会 db.get(Project)，读 status.value。"""
        return SimpleNamespace(
            id=pid,
            archived_at=None,
            status=SimpleNamespace(value="active"),
        )

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


def _client(
    monkeypatch,
    *,
    user: _User | None,
    db: _Db,
    publications: list[StoredPublication] | None = None,
    permission_calls: list[str] | None = None,
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

    # 🔴 `assert_project_permission` 是普通函数（不是依赖工厂），端点里直接调用，
    # 不能靠 dependency_overrides 拦住 —— 它的真实链路会一路走到 ORM 的
    # `get_bind`，用 SimpleNamespace 替身喂不动。故替换**端点模块命名空间**里的
    # 那个名字，同时把 level 实参记下来（这正是要断言的判据）。
    captured = permission_calls if permission_calls is not None else []

    async def _record_permission(_db, _user, _pid, level, **_kw):
        captured.append(level)
        return None

    monkeypatch.setattr(module, "assert_project_permission", _record_permission)

    monkeypatch.setattr(
        module,
        "derive_implicit_scope",
        lambda *a, **k: SimpleNamespace(organization_id=ORG),
    )

    pubs = publications or []
    from app.services.custom_template_ingestion import publication_registry_store as store

    def _list(session, *, organization_id, states=None):
        return [
            p
            for p in pubs
            if p.organization_id == organization_id and (not states or p.state in states)
        ]

    def _get(session, *, organization_id, publication_key):
        for p in pubs:
            if p.organization_id == organization_id and p.publication_key == publication_key:
                return p
        return None

    def _pin(session, *, organization_id, project_id, publication_key):  # noqa: ARG001
        pubs.append(
            StoredPublication(
                id=uuid.uuid4(),
                publication_key=f"pin-{publication_key}",
                organization_id=organization_id,
                candidate_id="pinned",
                candidate_digest="c" * 64,
                authority_ref="auth-1",
                artifact_digest="d" * 64,
                state=PublicationState.ACTIVE,
                reason=None,
                handoff={},
                created_at=NOW,
                updated_at=NOW,
            )
        )
        return uuid.uuid4()

    monkeypatch.setattr(store, "list_publications", _list)
    monkeypatch.setattr(store, "get_publication", _get)
    monkeypatch.setattr(store, "pin_project", _pin)
    return TestClient(app)


class TestListRequiresAuth:
    def test_unauthenticated_rejected(self, monkeypatch) -> None:
        client = _client(monkeypatch, user=None, db=_Db())
        resp = client.get("/api/custom-template-ingestion/publications")
        assert resp.status_code in (401, 403)

    def test_lists_own_org_only(self, monkeypatch) -> None:
        pubs = [
            _stored(key="pub-mine", organization_id=ORG),
            _stored(key="pub-other", organization_id="org-2"),
        ]
        client = _client(monkeypatch, user=_User(), db=_Db(), publications=pubs)
        resp = client.get("/api/custom-template-ingestion/publications")
        assert resp.status_code == 200
        keys = [p["publicationKey"] for p in resp.json()["publications"]]
        assert keys == ["pub-mine"]

    def test_runtime_discoverable_follows_state(self, monkeypatch) -> None:
        pubs = [
            _stored(key="pub-active", state=PublicationState.ACTIVE),
            _stored(key="pub-pending", state=PublicationState.PENDING_VISIBILITY),
        ]
        client = _client(monkeypatch, user=_User(), db=_Db(), publications=pubs)
        body = client.get("/api/custom-template-ingestion/publications").json()
        by_key = {p["publicationKey"]: p for p in body["publications"]}
        assert by_key["pub-active"]["runtimeDiscoverable"] is True
        assert by_key["pub-pending"]["runtimeDiscoverable"] is False

    def test_unknown_state_returns_400(self, monkeypatch) -> None:
        client = _client(monkeypatch, user=_User(), db=_Db())
        resp = client.get("/api/custom-template-ingestion/publications?state=BOGUS")
        assert resp.status_code == 400


class TestInstantiateGate:
    def _wp(self):
        return SimpleNamespace(id=uuid.UUID(int=2), project_id=uuid.UUID(int=1), is_deleted=False)

    def test_unauthenticated_rejected(self, monkeypatch) -> None:
        client = _client(monkeypatch, user=None, db=_Db(wp=self._wp()))
        resp = client.post(
            "/api/custom-template-ingestion/publications/instantiate",
            json={"publicationKey": "pub-1", "workingPaperId": str(uuid.UUID(int=2))},
        )
        assert resp.status_code in (401, 403)

    def test_non_active_publication_rejected(self, monkeypatch) -> None:
        pubs = [_stored(key="pub-pending", state=PublicationState.PENDING_VISIBILITY)]
        client = _client(monkeypatch, user=_User(), db=_Db(wp=self._wp()), publications=pubs)
        resp = client.post(
            "/api/custom-template-ingestion/publications/instantiate",
            json={"publicationKey": "pub-pending", "workingPaperId": str(uuid.UUID(int=2))},
        )
        assert resp.status_code == 409
        assert "不可实例化" in resp.json()["detail"]

    def test_unknown_publication_404(self, monkeypatch) -> None:
        client = _client(monkeypatch, user=_User(), db=_Db(wp=self._wp()))
        resp = client.post(
            "/api/custom-template-ingestion/publications/instantiate",
            json={"publicationKey": "nope", "workingPaperId": str(uuid.UUID(int=2))},
        )
        assert resp.status_code == 404

    def test_missing_working_paper_404(self, monkeypatch) -> None:
        client = _client(monkeypatch, user=_User(), db=_Db(wp=None))
        resp = client.post(
            "/api/custom-template-ingestion/publications/instantiate",
            json={"publicationKey": "pub-1", "workingPaperId": str(uuid.UUID(int=2))},
        )
        assert resp.status_code == 404

    def test_active_publication_pins_but_does_not_claim_instantiated(self, monkeypatch) -> None:
        """🔴 pin ≠ 完成实例化：响应必须显式 instantiated=false + 原因。"""
        pubs = [_stored(key="pub-1", state=PublicationState.ACTIVE)]
        db = _Db(wp=self._wp())
        client = _client(monkeypatch, user=_User(), db=db, publications=pubs)
        resp = client.post(
            "/api/custom-template-ingestion/publications/instantiate",
            json={"publicationKey": "pub-1", "workingPaperId": str(uuid.UUID(int=2))},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["pinned"] is True
        assert body["instantiated"] is False
        assert body["reason"]
        assert db.committed == 1


class TestPermissionLevel:
    def test_instantiate_uses_edit_level(self, monkeypatch) -> None:
        """instantiate 挂的是 edit 级（而不是只登录），否则只读角色可 pin。

        判据：捕获端点调用 `assert_project_permission` 的 level 实参。
        """
        captured: list[str] = []
        wp = SimpleNamespace(id=uuid.UUID(int=2), project_id=uuid.UUID(int=1), is_deleted=False)
        client = _client(
            monkeypatch,
            user=_User(),
            db=_Db(wp=wp),
            publications=[_stored()],
            permission_calls=captured,
        )
        resp = client.post(
            "/api/custom-template-ingestion/publications/instantiate",
            json={"publicationKey": "pub-1", "workingPaperId": str(uuid.UUID(int=2))},
        )
        assert resp.status_code == 200
        assert captured == ["edit"]
