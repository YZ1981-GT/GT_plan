"""``{pid}`` 路径端点的项目级鉴权（spec project-pid-path-authz-coverage 任务 3）

这些端点的项目段参数叫 ``pid``，鉴权基线守卫原先只认字面 ``{project_id}``，从未看见它们：AI 批量复核 / 进度 / 导出
三个一个鉴权依赖都没有，单底稿 AI 复核与改复核发现状态也没有；截止测试四个、抽凭历史 / 对比只校验登录。

这里逐个端点真发请求：SQLite 真 ORM 行 + 真实的 ``assert_project_permission`` / ``authorize_wp_read`` /
``authorize_wp_edit``，只替换取当前用户与数据库，以及门禁之后的下游（大模型、序时账查询、版本快照）。下游替身先记一笔：
被拒绝的请求一笔都不许记，放行的请求必须走到下游 —— 只看状态码分不清「放行」与「门禁之后别处报错」。
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import get_db
from app.deps import get_current_user
from app.models.ai_models import AIContent, AIContentType
from app.models.audit_platform_models import WorkpaperExtractionLog
from app.models.base import Base, UserRole
from app.models.core import Project, ProjectStatus, ProjectType, ProjectUser, User
from app.models.workpaper_models import WorkingPaper, WpIndex, WpSourceType, WpStatus
from app.routers import cutoff_sampling, review_prompt, voucher_sampling
from tests._test_auth_helper import FakeAuthUser

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

ADMIN, PARTNER, OUTSIDER, READER, REVIEWER, EDITOR = (uuid.uuid4() for _ in range(6))
_ROLE = {ADMIN: UserRole.admin, PARTNER: UserRole.partner, OUTSIDER: UserRole.auditor,
         READER: UserRole.auditor, REVIEWER: UserRole.qc, EDITOR: UserRole.auditor}
P, Q = uuid.uuid4(), uuid.uuid4()  # 本项目 / 别的项目
WP_P, WP_Q = uuid.uuid4(), uuid.uuid4()
FINDING_P = uuid.uuid4()
# LOG_MIXED：记在本项目、底稿却属于别的项目（数据不一致的形态，对比时必须按底稿再核一次）
LOG_P1, LOG_P2, LOG_Q, LOG_MIXED = (uuid.uuid4() for _ in range(4))
_GATE_PASSED = "门禁之后"


def _log(log_id, project_id, wp_id, nos: list[str]) -> WorkpaperExtractionLog:
    return WorkpaperExtractionLog(
        id=log_id, project_id=project_id, workpaper_id=wp_id, user_id=EDITOR,
        extraction_type="voucher_sampling", extraction_criteria={"filled_voucher_nos": nos},
        total_matched=3, filled_count=len(nos), fill_mode="append", is_undone=False, status="filled",
    )


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        for uid, role in _ROLE.items():
            session.add(User(id=uid, username=f"u{uid.hex[:8]}", email=f"{uid.hex[:8]}@test.local",
                             hashed_password="x", role=role.value))
        for pid, wp_id, name in ((P, WP_P, "【测试】pid 鉴权"), (Q, WP_Q, "【测试】别的项目")):
            session.add(Project(id=pid, name=name, client_name="测试", project_type=ProjectType.annual,
                                status=ProjectStatus.execution, created_by=EDITOR, audit_year=2025))
            idx = WpIndex(id=uuid.uuid4(), project_id=pid, wp_code="D2", wp_name="应收账款", audit_cycle="D",
                          status=WpStatus.not_started)
            session.add(idx)
            session.add(WorkingPaper(id=wp_id, project_id=pid, wp_index_id=idx.id, file_path="x.xlsx",
                                     source_type=WpSourceType.template, file_version=1))
        for pid, uid, level in ((P, READER, "readonly"), (P, REVIEWER, "review"), (P, EDITOR, "edit"),
                                (Q, EDITOR, "edit")):
            session.add(ProjectUser(project_id=pid, user_id=uid, role="auditor", permission_level=level,
                                    is_deleted=False))
        session.add(AIContent(id=FINDING_P, project_id=P, workpaper_id=WP_P,
                              content_type=AIContentType.review_finding, content_text="期初不符"))
        session.add_all([
            _log(LOG_P1, P, WP_P, ["A1", "B1"]), _log(LOG_P2, P, WP_P, ["B1", "C1"]),
            _log(LOG_Q, Q, WP_Q, ["Q1"]), _log(LOG_MIXED, P, WP_Q, ["M1"]),
        ])
        await session.commit()
        yield session
    await engine.dispose()


@pytest.fixture
def downstream(monkeypatch) -> list[tuple]:
    """门禁之后的下游替身：每次调用记 (名字, 参数)。截止测试的替身记完抛 ValueError，端点转成 400 带原文。"""
    from app.services.batch_review_service import BatchReviewReport, BatchStatistics, ExecutionMetadata

    calls: list[tuple] = []

    def _raising(name: str):
        async def _fn(*args, **kwargs):
            calls.append((name, kwargs))
            raise ValueError(_GATE_PASSED)
        return _fn

    async def _wp_code(wp_id):
        calls.append(("review._get_wp_code", {"wp_id": wp_id}))
        return None  # ⇒ 404「底稿不存在或未关联 wp_index」，与门禁的「底稿不存在」不是同一句

    async def _set_status(db, finding_id, status):
        calls.append(("review._set_finding_status", {"finding_id": finding_id, "status": status}))
        return 1  # 生产实现是 PG jsonb_set，SQLite 跑不了

    async def _load_report(project_id, wp_code_prefix, session_id):
        calls.append(("review._load_review_report_from_db", {"project_id": project_id, "prefix": wp_code_prefix}))
        return None

    class _BatchService:
        async def execute_batch(self, **kwargs):
            calls.append(("review.execute_batch", {k: kwargs[k] for k in ("project_id", "wp_code_prefix", "year")}))
            return BatchReviewReport(
                session_id="s", wp_code_prefix=kwargs["wp_code_prefix"], project_id=kwargs["project_id"],
                results=[], statistics=BatchStatistics(0, 0, 0, 0, 0, {"high": 0, "medium": 0, "low": 0}),
                execution=ExecutionMetadata("t0", "t1", 0.0, "stub"),
            )

    async def _year(db, pid):
        calls.append(("voucher._resolve_project_year", {"pid": pid}))
        return None  # 生产实现走 PG 方言；年度未知时抽凭历史照常返回、只是不判抽样框过期

    monkeypatch.setattr(review_prompt, "_get_wp_code", _wp_code)
    monkeypatch.setattr(review_prompt, "_set_finding_status", _set_status)
    monkeypatch.setattr(review_prompt, "_load_review_report_from_db", _load_report)
    monkeypatch.setattr(review_prompt, "BatchReviewService", _BatchService)
    monkeypatch.setattr(cutoff_sampling, "collect_exclusions", _raising("cutoff.collect_exclusions"))
    monkeypatch.setattr(cutoff_sampling, "VersionTrailService",
                        SimpleNamespace(create_snapshot_fire_and_forget=_raising("cutoff.snapshot")))
    monkeypatch.setattr(cutoff_sampling, "LedgerSamplingService", SimpleNamespace(
        undo_extraction=_raising("cutoff.undo_extraction"),
        get_extraction_history=_raising("cutoff.get_extraction_history"),
    ))
    monkeypatch.setattr(voucher_sampling, "_resolve_project_year", _year)
    return calls


def _app(db: AsyncSession) -> FastAPI:
    app = FastAPI()
    for module in (review_prompt, cutoff_sampling, voucher_sampling):
        app.include_router(module.router)

    async def _db():
        yield db

    app.dependency_overrides[get_db] = _db
    return app


@pytest_asyncio.fixture
async def client(db):
    """已登录：``client.as_user(uid)`` 切换身份（真实成员行判权）。"""
    app = _app(db)
    state: dict = {}

    async def _user():
        uid = state["user"]
        return FakeAuthUser(user_id=uid, username=f"u{uid.hex[:8]}", role=_ROLE[uid])

    app.dependency_overrides[get_current_user] = _user
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        c.as_user = lambda uid: state.update(user=uid)  # type: ignore[attr-defined]
        yield c


@pytest_asyncio.fixture
async def anon(db):
    """未登录：取当前用户走真实实现（没有 Authorization 头）。"""
    async with AsyncClient(transport=ASGITransport(app=_app(db)), base_url="http://test") as c:
        yield c


_SAMPLING = "/api/projects/{pid}/sampling"


def _cutoff(c: AsyncClient, name: str, wp_id: uuid.UUID, pid: uuid.UUID = P):
    base = _SAMPLING.format(pid=pid)
    if name == "extract":
        return c.post(f"{base}/cutoff-extract",
                      json={"cutoff_date": "2025-12-31", "account_codes": ["6001"], "workpaper_id": str(wp_id)})
    if name == "fill":
        return c.post(f"{base}/cutoff-fill", json={
            "workpaper_id": str(wp_id), "extraction_criteria": {}, "total_matched": 1, "filled_count": 1,
            "fill_mode": "append"})
    if name == "undo":
        return c.post(f"{base}/cutoff-undo", params={"log_id": str(LOG_P1), "wp_id": str(wp_id)})
    assert name == "history"
    return c.get(f"{base}/cutoff-history", params={"wp_id": str(wp_id)})


def _voucher_history(c: AsyncClient, wp_id: uuid.UUID, pid: uuid.UUID = P):
    return c.get(f"{_SAMPLING.format(pid=pid)}/voucher-history", params={"wp_id": str(wp_id)})


def _voucher_compare(c: AsyncClient, a: uuid.UUID, b: uuid.UUID, pid: uuid.UUID = P):
    return c.post(f"{_SAMPLING.format(pid=pid)}/voucher-compare", json={"log_id_a": str(a), "log_id_b": str(b)})


def _detail(resp) -> object:
    return resp.json().get("detail")


# ─── 未登录 ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_every_endpoint_rejects_unauthenticated(anon, downstream):
    """13 个端点没有登录一律 401，下游一笔都没走到（原先 AI 复核三个 {pid} 端点 + 单底稿复核 + 改发现状态 + 两个诊断
    端点不登录也能调）。"""
    requests = [
        anon.post(f"/api/workpapers/{WP_P}/review", json={}),
        anon.get("/api/review-prompts/coverage"),
        anon.get("/api/review-prompts/metrics"),
        anon.patch(f"/api/review-findings/{FINDING_P}/status", json={"status": "resolved"}),
        anon.get(f"/api/projects/{P}/batch-review-progress", params={"session_id": "s"}),
        anon.post(f"/api/projects/{P}/batch-review", json={"wp_code_prefix": "D2", "year": 2025}),
        anon.get(f"/api/projects/{P}/review-export", params={"wp_code_prefix": "D2"}),
        *(_cutoff(anon, name, WP_P) for name in ("extract", "fill", "undo", "history")),
        _voucher_history(anon, WP_P),
        _voucher_compare(anon, LOG_P1, LOG_P2),
    ]
    statuses = [(await r).status_code for r in requests]
    assert statuses == [401] * 13
    assert downstream == []


# ─── AI 复核 ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_single_review_needs_review_level_on_the_workpapers_project(client, downstream):
    """单底稿 AI 复核：底稿所属项目 review 级（与批量复核同级）。合伙人不是成员也不行 —— 底稿只读门对合伙人全局放行，
    项目门不放。"""
    url = f"/api/workpapers/{WP_P}/review"
    for uid in (OUTSIDER, PARTNER, READER):
        client.as_user(uid)
        assert (await client.post(url, json={})).status_code == 403, uid
    client.as_user(REVIEWER)
    resp = await client.post(f"/api/workpapers/{uuid.uuid4()}/review", json={})
    assert (resp.status_code, _detail(resp)) == (404, "底稿不存在")
    assert downstream == []

    for uid in (REVIEWER, ADMIN):
        client.as_user(uid)
        resp = await client.post(url, json={})
        assert (resp.status_code, _detail(resp)) == (404, "底稿不存在或未关联 wp_index"), uid
    assert downstream == [("review._get_wp_code", {"wp_id": WP_P})] * 2


@pytest.mark.asyncio
async def test_finding_status_needs_review_level_on_the_findings_project(client, downstream):
    """改复核发现状态：按发现所属项目 review 级；发现不存在（含 id 不是 UUID）404。"""
    body = {"status": "resolved"}
    client.as_user(REVIEWER)
    for bad in ("not-a-uuid", str(uuid.uuid4())):
        resp = await client.patch(f"/api/review-findings/{bad}/status", json=body)
        assert (resp.status_code, _detail(resp)) == (404, "Finding 不存在"), bad
    for uid in (OUTSIDER, PARTNER, READER):
        client.as_user(uid)
        assert (await client.patch(f"/api/review-findings/{FINDING_P}/status", json=body)).status_code == 403, uid
    assert downstream == []

    client.as_user(REVIEWER)
    resp = await client.patch(f"/api/review-findings/{FINDING_P}/status", json=body)
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"id": str(FINDING_P), "status": "resolved"}
    assert downstream == [("review._set_finding_status", {"finding_id": str(FINDING_P), "status": "resolved"})]


@pytest.mark.asyncio
async def test_batch_review_needs_review_level(client, downstream):
    """批量复核逐张调大模型并写复核结果：项目 review 级，只读成员 403。"""
    url, body = f"/api/projects/{P}/batch-review", {"wp_code_prefix": "D2", "year": 2025}
    for uid in (OUTSIDER, PARTNER, READER):
        client.as_user(uid)
        assert (await client.post(url, json=body)).status_code == 403, uid
    assert downstream == []

    client.as_user(REVIEWER)
    resp = await client.post(url, json=body)
    assert resp.status_code == 200, resp.text
    assert resp.json()["project_id"] == str(P)
    assert downstream == [("review.execute_batch", {"project_id": str(P), "wp_code_prefix": "D2", "year": 2025})]


@pytest.mark.asyncio
async def test_batch_progress_and_export_are_readonly_level(client, downstream):
    """进度与导出只读：只读成员能用；非成员 403。路径参数叫 pid —— 不带 ``?project_id=`` 也不是 422
    （``require_project_access`` 挂在这里会把 project_id 变成必填查询参数）。"""
    progress = f"/api/projects/{P}/batch-review-progress"
    export = f"/api/projects/{P}/review-export"
    client.as_user(OUTSIDER)
    assert (await client.get(progress, params={"session_id": "s"})).status_code == 403
    assert (await client.get(export, params={"wp_code_prefix": "D2"})).status_code == 403
    assert downstream == []

    client.as_user(READER)
    resp = await client.get(progress, params={"session_id": "s"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "not_found"
    resp = await client.get(export, params={"wp_code_prefix": "D2"})
    assert (resp.status_code, _detail(resp)) == (404, "无复核结果，请先执行批量复核")
    assert downstream == [("review._load_review_report_from_db", {"project_id": str(P), "prefix": "D2"})]


@pytest.mark.asyncio
async def test_prompt_diagnostics_need_login_only(client):
    """提示词覆盖率与调用指标不含项目数据：登录即可（非成员也能看）。"""
    client.as_user(OUTSIDER)
    resp = await client.get("/api/review-prompts/coverage")
    assert resp.status_code == 200, resp.text
    assert resp.json()["total_subjects"] > 0
    resp = await client.get("/api/review-prompts/metrics")
    assert resp.status_code == 200, resp.text
    assert "total_calls" in resp.json()


# ─── 截止测试 ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["extract", "fill", "undo"])
async def test_cutoff_writes_need_edit_on_a_workpaper_of_this_project(client, downstream, name):
    """取数 / 回填 / 撤销：底稿编辑权，且底稿属于路径项目 —— admin 也不能拿别的项目的底稿走本项目的路径。
    原先只校验登录：任意登录用户可按任意项目取序时账、往任意底稿写抽样日志与版本快照。"""
    for uid, wp_id in ((OUTSIDER, WP_P), (READER, WP_P), (REVIEWER, WP_P), (EDITOR, WP_Q), (ADMIN, WP_Q)):
        client.as_user(uid)
        assert (await _cutoff(client, name, wp_id)).status_code == 403, (uid, wp_id)
    client.as_user(EDITOR)
    resp = await _cutoff(client, name, WP_Q)
    assert _detail(resp) == "底稿不属于该项目"
    resp = await _cutoff(client, name, uuid.uuid4())
    assert (resp.status_code, _detail(resp)) == (404, "底稿不存在")
    assert downstream == []

    for uid in (EDITOR, ADMIN):
        client.as_user(uid)
        resp = await _cutoff(client, name, WP_P)
        assert (resp.status_code, _detail(resp)) == (400, _GATE_PASSED), uid
    assert len(downstream) == 2


@pytest.mark.asyncio
async def test_cutoff_history_needs_read_on_a_workpaper_of_this_project(client, downstream):
    """提取历史：底稿只读权（只读成员、质控能看），底稿属于路径项目。"""
    for uid, wp_id in ((OUTSIDER, WP_P), (EDITOR, WP_Q)):
        client.as_user(uid)
        assert (await _cutoff(client, "history", wp_id)).status_code == 403, (uid, wp_id)
    assert downstream == []

    for uid in (READER, REVIEWER):
        client.as_user(uid)
        resp = await _cutoff(client, "history", WP_P)
        assert (resp.status_code, _detail(resp)) == (400, _GATE_PASSED), uid
    assert [name for name, _ in downstream] == ["cutoff.get_extraction_history"] * 2


# ─── 抽凭历史 / 对比 ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_voucher_history_needs_read_on_a_workpaper_of_this_project(client, downstream):
    """抽凭历史：底稿只读权且底稿属于路径项目（原先按任意底稿 id 跨项目读）。"""
    for uid, wp_id, detail in ((OUTSIDER, WP_P, "无底稿访问权限"), (EDITOR, WP_Q, "底稿不属于该项目"),
                               (ADMIN, WP_Q, "底稿不属于该项目")):
        client.as_user(uid)
        resp = await _voucher_history(client, wp_id)
        assert (resp.status_code, _detail(resp)) == (403, detail), (uid, wp_id)
    assert downstream == []

    client.as_user(READER)
    resp = await _voucher_history(client, WP_P)
    assert resp.status_code == 200, resp.text
    assert {row["id"] for row in resp.json()} == {str(LOG_P1), str(LOG_P2)}
    assert downstream == [("voucher._resolve_project_year", {"pid": P})]


@pytest.mark.asyncio
async def test_voucher_compare_records_must_belong_to_this_project(client, downstream):
    """两条记录都须属于路径项目（否则 404，不暴露别的项目的记录是否存在，admin 同样），且对记录所在底稿有只读权。"""
    for uid, (a, b) in ((EDITOR, (LOG_P1, LOG_Q)), (ADMIN, (LOG_Q, LOG_P1)), (EDITOR, (LOG_P1, uuid.uuid4()))):
        client.as_user(uid)
        resp = await _voucher_compare(client, a, b)
        assert (resp.status_code, _detail(resp)) == (404, "对比记录不存在"), (uid, a, b)
    client.as_user(EDITOR)
    resp = await _voucher_compare(client, LOG_P1, LOG_MIXED)  # 记在本项目、底稿却在别的项目
    assert (resp.status_code, _detail(resp)) == (403, "底稿不属于该项目")
    client.as_user(OUTSIDER)
    assert (await _voucher_compare(client, LOG_P1, LOG_P2)).status_code == 403

    client.as_user(READER)
    resp = await _voucher_compare(client, LOG_P1, LOG_P2)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert (body["added"], body["removed"], body["retained"], body["compare_by"]) == (
        ["C1"], ["A1"], ["B1"], "voucher_no")
