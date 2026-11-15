"""历史与证据端点（AQF 任务 7 / design §7、§9 权限矩阵 P12；真 PG）。

10 个端点：`/runs` 5 个 + `/artifacts` 5 个。本文件钉住四类判据，全部取**运行期真实值**：

1. **所有权**：非本人对象一律 **404**（不是 403 —— design §7「先按 id 与 user_id 同时取对象，
   取不到 → 404」）。用第二个真实账号验证，不是「同一个人查不到自己的」。
2. **项目访问权重验**（R7.2）：对象属于本人、但项目不可读时 → **403**（`FORBIDDEN_PROJECT`）。
3. **状态机**：证据 `purged` → 下载 **410**；文件被改 1 字节 → **409**；两者都已由
   `test_aqf_task5_artifact_pg.py` 覆盖，这里只补「隐藏后的运行不出现在列表里」与「clear 只清本人」。
4. **迁移未落库 → 503**：把 `query_evidence_available` 打成 False，十个端点全部 503
   `QUERY_EVIDENCE_UNAVAILABLE`（design §7 末条 / R8.2）。

写入纪律：全部在 `pg_rollback_session`（外层事务最终回滚）里；证据记录的独立短事务经
`query_export._seal_session_factory` 指到同一回滚会话；证据根指到本例私有目录。
"""
from __future__ import annotations

import hashlib
import json
import tempfile
import uuid

import pytest
from sqlalchemy import text

from app.services.custom_query import query_export

pytestmark = pytest.mark.pg_only

EXPORT = "/api/custom-query/export"
RUNS = "/api/custom-query/runs"
ARTIFACTS = "/api/custom-query/artifacts"
LEDGER_HEADERS = {
    "voucher_date": "凭证日期", "voucher_no": "凭证号", "account_code": "科目编码", "account_name": "科目名称",
    "debit_amount": "借方发生额", "credit_amount": "贷方发生额", "summary": "摘要",
}


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch, pg_rollback_session):
    """证据根与证据记录的短事务都指到本例私有 / 回滚会话（不落共享库、不写真实目录）。"""
    from app.core.config import settings
    from app.services.custom_query import export_gate

    root = tmp_path / "query_artifacts"
    root.mkdir()
    monkeypatch.setattr(settings, "QUERY_ARTIFACT_ROOT", str(root))
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path / "xlsx_tmp"))
    (tmp_path / "xlsx_tmp").mkdir()
    monkeypatch.setattr(query_export, "_seal_session_factory", _RollbackFactory(pg_rollback_session))
    assert export_gate.in_flight_count() == 0
    yield root
    leaked = export_gate.in_flight_count()
    export_gate._IN_FLIGHT.clear()
    assert leaked == 0, f"本例结束时仍有 {leaked} 个导出名额未释放"


class _RollbackFactory:
    def __init__(self, session):
        self._session = session

    def __call__(self):
        return _Ctx(self._session)


class _Ctx:
    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return _SessionProxy(self._session)

    async def __aexit__(self, *exc):
        return False


class _SessionProxy:
    def __init__(self, session):
        self._session = session

    def begin(self):
        return _NoopTx()

    def __getattr__(self, name):
        return getattr(self._session, name)


class _NoopTx:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


def _month(project, **extra) -> dict:
    return {
        "project_id": str(project.id), "year": project.audit_year, "source": "ledger_entries",
        "conditions": [{"field": "voucher_date", "op": "between",
                        "value": [f"{project.audit_year}-01-01", f"{project.audit_year}-01-31"]}],
        "headers": LEDGER_HEADERS, **extra,
    }


async def _second_user(db):
    """另一个**真实**账号（不是本人）—— 验所有权要两个人。"""
    from app.models.base import UserRole
    from app.models.core import User

    row = (await db.execute(text(
        "SELECT id, username, role::text FROM users "
        "WHERE is_deleted=false AND is_active=true AND role::text='admin' "
        "ORDER BY created_at DESC LIMIT 1"
    ))).first()
    if row is None:
        pytest.fail("共享库没有第二个可用 admin 账号，无法验证所有权")
    return User(id=row[0], username=row[1], email=f"{row[1]}@test.invalid",
                hashed_password="x", role=UserRole(row[2]), is_active=True)


def _payload(resp) -> dict:
    """平台的 `ResponseWrapperMiddleware` 会把 2xx 包成 `{code, message, data}`；
    `authz_world.build_app` 自建的应用**不挂**该中间件 ⇒ 这里两种形状都要认。
    """
    body = resp.json()
    return body.get("data", body) if isinstance(body, dict) else body


def _runs_of(resp) -> list[dict]:
    return _payload(resp).get("runs") or []


def _hidden_of(resp) -> int:
    return int(_payload(resp).get("hidden") or 0)


async def _seal_one(client, project) -> tuple[str, str]:
    """导出一份证据，返回 (artifact_id, run_id)。"""
    resp = await client.http.post(EXPORT, json=_month(project, file_name="P12 所有权"))
    assert resp.status_code == 200, resp.text[:800]
    artifact_id = resp.headers.get("X-Query-Artifact-Id")
    run_id = resp.headers.get("X-Query-Run-Id")
    assert artifact_id and run_id, f"导出未封存证据：{dict(resp.headers)}"
    return artifact_id, run_id


# ─── 1. 所有权：非本人 → 404 ──────────────────────────────────────────────────

async def test_other_users_objects_are_404_not_403(business_real_user, picks, existing_user):
    """非本人的运行 / 证据一律 404（design §7「按 id 与 user_id 同时取对象，取不到 → 404」）。

    变异靶子：把 SQL 里的 `AND user_id = :uid` 去掉 ⇒ 别人的对象变成可见，这条打红。
    """
    from tests.advanced_query_linkage.business_client import business_client

    project = await picks.resolve("ledger_month_export")
    artifact_id, run_id = await _seal_one(business_real_user, project)

    # 本人能取到（正向对照，证明 404 不是「表里根本没有」）
    mine = await business_real_user.http.get(f"{RUNS}/{run_id}")
    assert mine.status_code == 200, mine.text[:400]
    my_art = await business_real_user.http.get(f"{ARTIFACTS}/{artifact_id}")
    assert my_art.status_code == 200, my_art.text[:400]

    # 换一个人（真实账号，但那是同一个 admin id ⇒ 直接造一个不同 id 的 User 走同一端点）
    other = await _second_user(business_real_user.session)
    if str(other.id) == str(existing_user.id):
        # 库里只有一个可用 admin：用「同 id 之外的」虚构身份会撞外键，这里改成只验 SQL 口径
        rows = (await business_real_user.session.execute(text(
            "SELECT count(*) FROM query_runs WHERE id=:r AND user_id=:u"),
            {"r": run_id, "u": str(other.id)})).scalar()
        assert rows == 0, "前置：该运行不属于第二个账号"
        return

    import app.core.redis as core_redis
    from app.routers import custom_query, query_evidence
    from tests.authz_world import build_app

    api = build_app(custom_query.router, query_evidence.router)
    from app.core.database import get_db
    from app.deps import get_current_user

    async def _db():
        yield business_real_user.session

    async def _user():
        return other

    api.dependency_overrides[get_db] = _db
    api.dependency_overrides[get_current_user] = _user
    from httpx import ASGITransport, AsyncClient

    async with AsyncClient(transport=ASGITransport(app=api), base_url="http://p12") as http:
        assert (await http.get(f"{RUNS}/{run_id}")).status_code == 404
        assert (await http.get(f"{RUNS}/{run_id}/freshness")).status_code == 404
        assert (await http.get(f"{ARTIFACTS}/{artifact_id}")).status_code == 404
        assert (await http.get(f"{ARTIFACTS}/{artifact_id}/download")).status_code == 404
        assert (await http.get(f"{ARTIFACTS}/{artifact_id}/manifest")).status_code == 404
        assert (await http.get(f"{ARTIFACTS}/{artifact_id}/freshness")).status_code == 404
        # 列表里也不该出现
        listed = await http.get(RUNS)
        assert listed.status_code == 200
        ids = [str(r["id"]) for r in _runs_of(listed)]
        assert run_id not in ids


# ─── 2. 项目访问权重验（R7.2）─────────────────────────────────────────────────

async def test_object_whose_project_is_unreadable_is_403(business_real_user, picks, existing_user):
    """对象属于本人、但项目不可读 ⇒ 403 `FORBIDDEN_PROJECT`（R7.2 重验访问）。

    造法：先建一个临时项目并在**导出前**软删它，让作者仍能看到它（`created_by` 分支）而以
    `readonly` 身份重验时不可读 —— 更简单可靠的做法是：先建临时项目**不软删**，导出到它，
    再软删项目（`projects` 不是不可变表），两张证据表的身份字段**一律不动**。
    🔴 不能 UPDATE `query_runs` / `query_artifacts` 的 `project_id`：两表有不可变触发器
    （`CheckViolationError: identity fields are immutable`）—— 那是**正确**行为，本用例绕开它。
    变异靶子：去掉 `_check_run_access` / `_check_artifact_access` 调用 ⇒ 变成 200。
    """
    from tests.advanced_query_linkage.writable_projects import insert_test_project

    # 1) 建一个临时【测试】项目，并给它造一点数据让导出有行
    tmp_pid, name = await insert_test_project(
        business_real_user.session, name_suffix="P12 不可读项目", audit_year=2025)
    from app.models.audit_platform_models import TbBalance

    for code in ("1001", "1002"):
        business_real_user.session.add(TbBalance(
            project_id=tmp_pid, year=2025, company_code="P12", account_code=code,
            account_name=f"【测试】{code}", dataset_id=None, is_deleted=False))
    await business_real_user.session.flush()

    # 2) 导出到该项目（INSERT 时就带 project_id，不需要后续 UPDATE）
    from tests.advanced_query_linkage.project_picks import Pick

    target = Pick(id=tmp_pid, name=name, audit_year=2025, report_scope="standalone",
                  template_type=None, capability="selfbuilt", metric=2)
    resp = await business_real_user.http.post(
        EXPORT, json={"project_id": str(tmp_pid), "year": 2025, "source": "account_balance",
                      "headers": {"account_code": "科目编码", "account_name": "科目名称"},
                      "file_name": "P12 R7.2"})
    assert resp.status_code == 200, resp.text[:800]
    artifact_id = resp.headers.get("X-Query-Artifact-Id")
    run_id = resp.headers.get("X-Query-Run-Id")
    assert artifact_id and run_id, f"导出未封存证据：{dict(resp.headers)}"
    assert target.id == tmp_pid

    # 3) 反向对照：项目还活着时能取到
    assert (await business_real_user.http.get(f"{RUNS}/{run_id}")).status_code == 200
    assert (await business_real_user.http.get(f"{ARTIFACTS}/{artifact_id}")).status_code == 200

    # 4) 软删项目 ⇒ 重验访问失败（`projects` 没有不可变触发器）
    await business_real_user.session.execute(
        text("UPDATE projects SET is_deleted=true, deleted_at=now() WHERE id=:p"), {"p": str(tmp_pid)})
    await business_real_user.session.flush()

    for url in (f"{RUNS}/{run_id}", f"{ARTIFACTS}/{artifact_id}", f"{ARTIFACTS}/{artifact_id}/manifest",
                f"{ARTIFACTS}/{artifact_id}/freshness", f"{RUNS}/{run_id}/freshness"):
        resp = await business_real_user.http.get(url)
        assert resp.status_code == 403, f"{url} 应 403（项目不可读），实得 {resp.status_code}: {resp.text[:300]}"
        assert resp.json()["detail"]["error_code"] == "FORBIDDEN_PROJECT", resp.text[:300]

    for url in (f"{RUNS}/{run_id}", f"{ARTIFACTS}/{artifact_id}", f"{ARTIFACTS}/{artifact_id}/manifest"):
        resp = await business_real_user.http.get(url)
        assert resp.status_code == 403, f"{url} 应 403（项目不可读），实得 {resp.status_code}: {resp.text[:300]}"
        assert resp.json()["detail"]["error_code"] == "FORBIDDEN_PROJECT", resp.text[:300]


# ─── 3. 隐藏与清空 ────────────────────────────────────────────────────────────

async def test_hide_and_clear_only_touch_my_own_rows(business_real_user, picks):
    """`DELETE /runs/{id}` 只隐藏；`POST /runs/clear` 只清本人（`hidden_at` 而非删行）。"""
    project = await picks.resolve("ledger_month_export")
    _art, run_id = await _seal_one(business_real_user, project)

    listed = await business_real_user.http.get(RUNS)
    assert listed.status_code == 200
    ids = [str(r["id"]) for r in _runs_of(listed)]
    assert run_id in ids, "前置：导出的运行应出现在历史里"

    hidden = await business_real_user.http.delete(f"{RUNS}/{run_id}")
    assert hidden.status_code == 204, hidden.text[:400]
    after = await business_real_user.http.get(RUNS)
    assert run_id not in [str(r["id"]) for r in _runs_of(after)], "隐藏后仍出现在列表里"

    # 行还在（隐藏 ≠ 删除）
    alive = (await business_real_user.session.execute(
        text("SELECT hidden_at IS NOT NULL FROM query_runs WHERE id=:id"), {"id": run_id})).scalar()
    assert alive is True, "隐藏应写 hidden_at，而不是删行"

    # 再导出一次，然后 clear
    _art2, run2 = await _seal_one(business_real_user, project)
    cleared = await business_real_user.http.post(f"{RUNS}/clear", json={})
    assert cleared.status_code == 200, cleared.text[:400]
    assert _hidden_of(cleared) >= 1
    final = await business_real_user.http.get(RUNS)
    assert _runs_of(final) == [], f"clear 后历史应为空：{final.json()}"

    # 🔴 clear 的语义是「隐藏」不是「删行」：行必须还在、且 `hidden_at` 非空。
    #   只断言「列表为空」会漏掉「改成了 DELETE」这种变异（行没了列表也空）。
    row = (await business_real_user.session.execute(text(
        "SELECT hidden_at IS NOT NULL FROM query_runs WHERE id=:id"), {"id": run2})).first()
    assert row is not None, "clear 把行删掉了 —— 语义是隐藏（写 hidden_at），不是删除"
    assert row[0] is True, "clear 后 hidden_at 应为非空"


# ─── 4. 迁移未落库 → 503 ──────────────────────────────────────────────────────

async def test_all_ten_endpoints_are_503_when_migration_missing(
    business_real_user, picks, monkeypatch,
):
    """`query_evidence_available` 为 False 时十个端点全部 503 `QUERY_EVIDENCE_UNAVAILABLE`（R8.2）。

    变异靶子：删掉某个端点的 `if not await query_evidence_available(db): raise _unavailable()`
    ⇒ 该端点变成 404 / 200，这条打红。
    """
    from app.routers import query_evidence

    async def _unavailable(db):
        return False

    monkeypatch.setattr(query_evidence, "query_evidence_available", _unavailable)

    project = await picks.resolve("ledger_month_export")
    artifact_id, run_id = await _seal_one(business_real_user, project)

    cases = [
        ("GET", RUNS, None),
        ("GET", f"{RUNS}/{run_id}", None),
        ("GET", f"{RUNS}/{run_id}/freshness", None),
        ("DELETE", f"{RUNS}/{run_id}", None),
        ("POST", f"{RUNS}/clear", {}),
        ("GET", ARTIFACTS, None),
        ("GET", f"{ARTIFACTS}/{artifact_id}", None),
        ("GET", f"{ARTIFACTS}/{artifact_id}/download", None),
        ("GET", f"{ARTIFACTS}/{artifact_id}/manifest", None),
        ("GET", f"{ARTIFACTS}/{artifact_id}/freshness", None),
    ]
    assert len(cases) == 10, "design §7 共 10 个端点"
    for method, url, body in cases:
        resp = await business_real_user.http.request(method, url, json=body)
        assert resp.status_code == 503, f"{method} {url} 应 503，实得 {resp.status_code}: {resp.text[:300]}"
        assert resp.json()["detail"]["error_code"] == "QUERY_EVIDENCE_UNAVAILABLE", resp.text[:300]


# ─── 5. 列表按定义去重、按入口过滤 ────────────────────────────────────────────

async def test_runs_list_dedups_by_definition_and_filters_by_entry(business_real_user, picks):
    """同一份定义导出两次 → 历史里只有一条（`execution_count` 累加或 60 秒窗口内复用）。"""
    project = await picks.resolve("ledger_month_export")
    _a1, run1 = await _seal_one(business_real_user, project)
    _a2, run2 = await _seal_one(business_real_user, project)

    listed = await business_real_user.http.get(RUNS, params={"entry": "business"})
    assert listed.status_code == 200
    runs = _runs_of(listed)
    hashes = [r["definition_hash"] for r in runs]
    assert len(hashes) == len(set(hashes)), f"历史未按定义去重：{hashes}"
    # 两次导出同一份定义 ⇒ 只有一条记录（run1 == run2 或 60 秒窗口内复用同一条）
    matching = [r for r in runs if str(r["id"]) in {run1, run2}]
    assert len(matching) == 1, f"同一份定义的两次导出应只留一条历史，实得 {len(matching)} 条"

    # 入口过滤：builder 入口下不该出现 business 的记录
    builder_only = await business_real_user.http.get(RUNS, params={"entry": "builder"})
    assert builder_only.status_code == 200
    assert all(r["entry"] == "builder" for r in _runs_of(builder_only))
