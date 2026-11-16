"""publication registry 端点级判据（list / instantiate）。

Spec: custom-workpaper-template-ingestion-and-sync-closure

## 为什么必须端点级

memory 铁律 ㉕：只测 service 会漏掉鉴权 —— 曾出现「新端点只挂 get_db、零鉴权、
任意 project_id 可未授权读」。本文件真发请求过鉴权链。

判据：
1. 未登录 → 401/403；
2. list 只返回本组织的 publication（跨组织不可见）；
3. instantiate 挂 `require_project_access("edit")` —— 实参必须是 `"edit"`；
4. **非 ACTIVE 不可实例化**（409）；
5. instantiate 的 sheetUid 必须来自 preflight 报告（凭空造的 422）；
6. 成功时真建册：返回 workbookInstanceId + entries，`instantiated: true`。
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
ARTIFACT_ID = "art-1"
WP_ID = uuid.UUID(int=2)
PROJECT_ID = uuid.UUID(int=1)

PREFLIGHT_SHEETS = [
    {"sheetUid": "sheet-0-alpha", "sheetName": "甲表", "order": 0, "state": "visible"},
]

#: 区分「未传 preflight（用默认报告）」与「显式传 None（产物无 preflight 键）」
_UNSET_PREFLIGHT = object()


def _stored(
    *,
    key: str = "pub-1",
    state: PublicationState = PublicationState.ACTIVE,
    organization_id: str = ORG,
    candidate_id: str = ARTIFACT_ID,
) -> StoredPublication:
    return StoredPublication(
        id=uuid.uuid4(),
        publication_key=key,
        organization_id=organization_id,
        candidate_id=candidate_id,
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
    """按查询意图分派的替身（导言见 test_publication_routes 历史注释）。"""

    def __init__(self, wp=None) -> None:
        self.wp = wp
        self.committed = 0

    async def execute(self, stmt):
        text = str(stmt).lower()
        if "working_paper" in text:
            return _Result(self.wp)
        if "project_users" in text:
            return _Result(SimpleNamespace(value="edit"))
        return _Result(None)

    async def get(self, _model, pid):  # noqa: ARG002
        return SimpleNamespace(
            id=pid, archived_at=None, status=SimpleNamespace(value="active")
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
        self._db.added = getattr(self._db, "added", [])
        self._db.added.append(obj)

    def flush(self):
        return None


class _Quarantine:
    """隔离区替身：preflight 报告是 sheet 白名单的唯一来源。"""

    def __init__(self, preflight: dict | None) -> None:
        self.preflight = preflight

    def load_manifest(self, organization_id, artifact_id):  # noqa: ARG002
        manifest: dict = {"state": "PREFLIGHT_READY"}
        if self.preflight is not None:
            manifest["preflight"] = self.preflight
        return manifest


def _client(
    monkeypatch,
    *,
    user: _User | None,
    db: _Db,
    publications: list[StoredPublication] | None = None,
    permission_calls: list[str] | None = None,
    preflight: object = _UNSET_PREFLIGHT,
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
    # dependency_overrides 拦不住；替换端点模块命名空间里的名字并记录 level 实参。
    captured = permission_calls if permission_calls is not None else []

    async def _record_permission(_db, _user, _pid, level, **_kw):
        captured.append(level)
        return None

    monkeypatch.setattr(module, "assert_project_permission", _record_permission)
    monkeypatch.setattr(
        module, "derive_implicit_scope",
        lambda *a, **k: SimpleNamespace(organization_id=ORG),
    )

    default_preflight = {"workbook": {"sheets": PREFLIGHT_SHEETS}}
    # 🔴 用哨兵区分「未传（用默认 preflight）」与「显式 None（产物无 preflight 键）」——
    # 直接 `preflight if preflight is not None else default` 会让显式 None 也拿到默认值，
    # 「缺少 preflight 报告」这条守卫就测不到（首版即如此）。
    effective = default_preflight if preflight is _UNSET_PREFLIGHT else preflight
    monkeypatch.setattr(module, "get_quarantine", lambda: _Quarantine(effective))

    pubs = publications or []
    from app.services.custom_template_ingestion import publication_registry_store as store
    from app.services.custom_template_ingestion import instantiate_from_publication as inst

    def _list(session, *, organization_id, states=None):
        return [
            p for p in pubs
            if p.organization_id == organization_id and (not states or p.state in states)
        ]

    def _get(session, *, organization_id, publication_key):
        for p in pubs:
            if p.organization_id == organization_id and p.publication_key == publication_key:
                return p
        return None

    def _pin(session, *, organization_id, project_id, publication_key):  # noqa: ARG001
        return uuid.uuid4()

    monkeypatch.setattr(store, "list_publications", _list)
    monkeypatch.setattr(store, "get_publication", _get)
    monkeypatch.setattr(store, "pin_project", _pin)
    return TestClient(app)


class TestListRequiresAuth:
    def test_unauthenticated_rejected(self, monkeypatch) -> None:
        client = _client(monkeypatch, user=None, db=_Db())
        assert client.get("/api/custom-template-ingestion/publications").status_code in (401, 403)

    def test_lists_own_org_only(self, monkeypatch) -> None:
        pubs = [
            _stored(key="pub-mine", organization_id=ORG),
            _stored(key="pub-other", organization_id="org-2"),
        ]
        client = _client(monkeypatch, user=_User(), db=_Db(), publications=pubs)
        body = client.get("/api/custom-template-ingestion/publications").json()
        assert [p["publicationKey"] for p in body["publications"]] == ["pub-mine"]

    def test_runtime_discoverable_follows_state(self, monkeypatch) -> None:
        pubs = [
            _stored(key="pub-active", state=PublicationState.ACTIVE),
            _stored(key="pub-pending", state=PublicationState.PENDING_VISIBILITY),
        ]
        client = _client(monkeypatch, user=_User(), db=_Db(), publications=pubs)
        by_key = {
            p["publicationKey"]: p
            for p in client.get("/api/custom-template-ingestion/publications").json()["publications"]
        }
        assert by_key["pub-active"]["runtimeDiscoverable"] is True
        assert by_key["pub-pending"]["runtimeDiscoverable"] is False

    def test_unknown_state_returns_400(self, monkeypatch) -> None:
        client = _client(monkeypatch, user=_User(), db=_Db())
        assert client.get(
            "/api/custom-template-ingestion/publications?state=BOGUS"
        ).status_code == 400


def _wp():
    return SimpleNamespace(id=WP_ID, project_id=PROJECT_ID, is_deleted=False)


def _instantiate_body(pub_key: str = "pub-1", sheets: list[dict] | None = None) -> dict:
    return {
        "publicationKey": pub_key,
        "workingPaperId": str(WP_ID),
        "sheets": sheets if sheets is not None else [
            {
                "sheetUid": "sheet-0-alpha",
                "wpCode": "F3",
                "componentType": "audit-sheet",
                "projectionMode": "editable_grid",
            }
        ],
    }


class TestInstantiateGate:
    def test_unauthenticated_rejected(self, monkeypatch) -> None:
        client = _client(monkeypatch, user=None, db=_Db(wp=_wp()))
        resp = client.post(
            "/api/custom-template-ingestion/publications/instantiate",
            json=_instantiate_body(),
        )
        assert resp.status_code in (401, 403)

    def test_non_active_publication_rejected(self, monkeypatch) -> None:
        client = _client(
            monkeypatch, user=_User(), db=_Db(wp=_wp()),
            publications=[_stored(key="pub-pending", state=PublicationState.PENDING_VISIBILITY)],
        )
        resp = client.post(
            "/api/custom-template-ingestion/publications/instantiate",
            json=_instantiate_body("pub-pending"),
        )
        assert resp.status_code == 409
        assert "不可实例化" in resp.json()["detail"]

    def test_unknown_publication_404(self, monkeypatch) -> None:
        client = _client(monkeypatch, user=_User(), db=_Db(wp=_wp()))
        resp = client.post(
            "/api/custom-template-ingestion/publications/instantiate",
            json=_instantiate_body("nope"),
        )
        assert resp.status_code == 404

    def test_missing_working_paper_404(self, monkeypatch) -> None:
        client = _client(monkeypatch, user=_User(), db=_Db(wp=None))
        resp = client.post(
            "/api/custom-template-ingestion/publications/instantiate",
            json=_instantiate_body(),
        )
        assert resp.status_code == 404

    def test_missing_preflight_manifest_409(self, monkeypatch) -> None:
        """隔离产物完全没有 preflight 键（finalize 后手工清空 / 旧产物）。"""
        client = _client(
            monkeypatch, user=_User(), db=_Db(wp=_wp()),
            publications=[_stored()], preflight=None,
        )
        resp = client.post(
            "/api/custom-template-ingestion/publications/instantiate",
            json=_instantiate_body(),
        )
        assert resp.status_code == 409
        # 🔴 断言具体文案：删掉「preflight 不是 dict」这一层后，下一层
        # 「缺少 sheet 列表」也会 409 —— 只看状态码会把两层守卫的变异都放过。
        assert "缺少 preflight 报告" in resp.json()["detail"]

    def test_missing_sheet_list_409(self, monkeypatch) -> None:
        """preflight 是 dict 但没有 workbook.sheets —— 第二层守卫，独立用例覆盖。"""
        client = _client(
            monkeypatch, user=_User(), db=_Db(wp=_wp()),
            publications=[_stored()], preflight={"workbook": {}},
        )
        resp = client.post(
            "/api/custom-template-ingestion/publications/instantiate",
            json=_instantiate_body(),
        )
        assert resp.status_code == 409
        assert "缺少 sheet 列表" in resp.json()["detail"]

    def test_invented_sheet_uid_rejected(self, monkeypatch) -> None:
        """🔴 凭空造的 sheetUid 必须 422，不能给不存在的页建 entry。"""
        client = _client(
            monkeypatch, user=_User(), db=_Db(wp=_wp()), publications=[_stored()]
        )
        resp = client.post(
            "/api/custom-template-ingestion/publications/instantiate",
            json=_instantiate_body(sheets=[{
                "sheetUid": "sheet-9-invented",
                "wpCode": "F3",
                "componentType": "audit-sheet",
                "projectionMode": "editable_grid",
            }]),
        )
        assert resp.status_code == 422
        assert "不在 preflight 报告中" in resp.json()["detail"]

    def test_active_publication_instantiates_and_pins(self, monkeypatch) -> None:
        db = _Db(wp=_wp())
        client = _client(
            monkeypatch, user=_User(), db=db, publications=[_stored()]
        )
        resp = client.post(
            "/api/custom-template-ingestion/publications/instantiate",
            json=_instantiate_body(),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["pinned"] is True
        assert body["instantiated"] is True
        assert body["workbookInstanceId"].startswith("pwi-")
        assert body["sheetCount"] == 1
        assert body["entries"][0]["sheetUid"] == "sheet-0-alpha"
        assert db.committed == 1


class TestPermissionLevel:
    def test_instantiate_uses_edit_level(self, monkeypatch) -> None:
        """instantiate 挂 edit 级（不是只登录），否则只读角色可建册。"""
        captured: list[str] = []
        client = _client(
            monkeypatch, user=_User(), db=_Db(wp=_wp()),
            publications=[_stored()], permission_calls=captured,
        )
        resp = client.post(
            "/api/custom-template-ingestion/publications/instantiate",
            json=_instantiate_body(),
        )
        assert resp.status_code == 200, resp.text
        assert captured == ["edit"]
