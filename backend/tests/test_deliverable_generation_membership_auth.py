"""生成 / 查看附注与交付件的项目成员鉴权 —— 项目组成员只能生成自己项目的附注，项目组外的人 403。

2026-10-19 补。此前以下入口只看登录与全局角色，不看是不是本项目成员 ⇒ 任意登录用户可为任意项目生成附注：
word-exports 整组（一键生成全套等）、交付中心（``deliverable._guard_action``）、导出附注 Word（note_export）、
全链路工作流（chain_workflow：生成附注 / 附注同步与裁剪 / 组合导出包 / 批量执行）、附注 AI（note_ai 四个）。现定级：

- 查看（含 AI 预览，不落库）：本项目成员 readonly 及以上；
- 生成交付件（交付中心 / 一键全套 / 导出附注 Word / 组合导出包）：同一判定 ``_guard_action`` —— 本项目成员
  review 及以上 + 角色矩阵 + EQCR 只读。review 而非 edit：合伙人 / 经理 / 质控在项目里是 review 级（ROLE_MAP）；
- 编制（全链路执行 / 重试 / 附注同步与裁剪，会改写试算表 / 报表 / 附注）：edit，与附注模块写端点同级。

做法同 test_phase8_endpoint_role_levels（memory ㉕）：不 override 鉴权依赖，只替换其下的取数点（权限缓存返回指定
级别，None = 查库查无此人；归档守卫与 RLS 置空），让真实 ``assert_project_permission`` 判定；业务层打桩并记账 ——
被拦下的请求一次业务调用都不能有。
"""
from __future__ import annotations

import io
import uuid
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.deps as deps
from app.core.database import get_db
from app.routers import chain_workflow, deliverable, note_ai, note_export, word_export
from app.services.assignment_service import ROLE_MAP

PID = uuid.UUID("7a1c0d6e-0000-4000-8000-000000000001")
OTHER = uuid.UUID("7a1c0d6e-0000-4000-8000-000000000002")
ME = uuid.UUID("11111111-1111-1111-1111-111111111111")
JOB = uuid.UUID("55555555-5555-5555-5555-555555555555")
TASK = uuid.UUID("66666666-6666-6666-6666-666666666666")
EXEC = "77777777-7777-7777-7777-777777777777"
GATE_DENIED = "权限不足"  # assert_project_permission 与 _guard_action 的 403 文案

_INCONSISTENT = {
    "consistent": False,
    "never_synced": [{"note_section": "八、1", "section_title": "货币资金", "wp_codes": ["E1"]}],
    "stale": [],
}


class _Result:
    def __init__(self, value=None):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _FakeDB:
    """project_users / chain_executions 查询恒查无此人 / 无记录；其余查询给一个最小项目（取文件名用）。"""

    project = SimpleNamespace(report_scope="standalone", wizard_state={}, client_name="测试客户", name="测试项目")

    def __init__(self, sql_log: list[str]):
        self.sql_log = sql_log

    async def execute(self, stmt, *_a, **_k):
        sql = str(stmt)
        self.sql_log.append(sql)
        return _Result(None if ("project_users" in sql or "chain_executions" in sql) else self.project)

    async def commit(self):
        return None

    async def rollback(self):
        return None


async def _noop(*_a, **_k):
    return None


def _async_return(value):
    async def _f(*_a, **_k):
        return value

    return _f


def _recorder(calls: list[str], name: str, value):
    async def _f(*_a, **_k):
        calls.append(name)
        return value

    return _f


def _service(calls: list[str], name: str, **methods):
    """造一个「构造即记账」的服务桩类：methods 名 → 返回值。"""

    def _init(self, *_a, **_k):
        calls.append(name)

    attrs = {"__init__": _init}
    for meth, value in methods.items():
        attrs[meth] = _recorder(calls, f"{name}.{meth}", value)
    return type(f"_{name}", (), attrs)


def _stub_business(monkeypatch: pytest.MonkeyPatch, calls: list[str]) -> None:
    """业务层打桩：每个桩被调到就记一笔，用来证明「被拦下的请求没碰业务」。"""
    job = SimpleNamespace(
        id=JOB, project_id=PID, job_type="full_deliverables", status="succeeded", payload={},
        progress_total=3, progress_done=3, failed_count=0, initiated_by=ME, created_at=None, updated_at=None,
    )
    task = SimpleNamespace(id=TASK, project_id=PID, doc_type="disclosure_notes", status="generated", created_by=ME)
    execution = SimpleNamespace(id=EXEC, status="completed", steps={}, total_duration_ms=1,
                                started_at=None, completed_at=None)
    patches = {
        # 交付中心生成附注：不一致 ⇒ 200 + 待确认清单，不再往下导出
        "app.services.deliverable_note_consistency.check_note_consistency":
            _recorder(calls, "check_note_consistency", _INCONSISTENT),
        "app.services.export_job_service.ExportJobService":
            _service(calls, "ExportJobService", get_job=job, get_job_items=[], retry_failed=0),
        "app.services.full_deliverables_executor.FullDeliverablesExecutor":
            _service(calls, "FullDeliverablesExecutor", run=SimpleNamespace(job_id=JOB)),
        "app.services.note_word_exporter.NoteWordExporter":
            _service(calls, "NoteWordExporter", export=io.BytesIO(b"PK\x03\x04 docx")),
        "app.services.export_package_service.ExportPackageService":
            _service(calls, "ExportPackageService", export_package=io.BytesIO(b"PK\x03\x04 zip")),
        "app.services.consistency_gate.ConsistencyGate":
            _service(calls, "ConsistencyGate", run_all_checks=SimpleNamespace(overall="pass", checks=[])),
        "app.services.data_health_monitor.DataHealthMonitor":
            _service(calls, "DataHealthMonitor", calculate_health_score=SimpleNamespace(score=100, checks=[])),
        "app.services.report_note_sync_service.ReportNoteSyncService":
            _service(calls, "ReportNoteSyncService", sync_report_to_notes={"synced": 0}),
        "app.services.note_trim_sort_service.NoteTrimSortService":
            _service(calls, "NoteTrimSortService", trim_and_sort={"trimmed": 0}),
        "app.services.reference_doc_service.ReferenceDocService.load_context": _recorder(calls, "load_context", []),
        "app.services.llm_client.chat_completion": _recorder(calls, "chat_completion", "生成的文本"),
    }
    for target, value in patches.items():
        monkeypatch.setattr(target, value)
    monkeypatch.setattr(word_export, "ExportTaskService",
                        _service(calls, "ExportTaskService", create_task=task, update_status=task, get_history=[]))
    monkeypatch.setattr(deliverable.DeliverableService, "list_deliverables", _recorder(calls, "list_deliverables", []))
    orch = chain_workflow.chain_orchestrator
    monkeypatch.setattr(orch, "execute_full_chain", _recorder(calls, "execute_full_chain", execution))
    monkeypatch.setattr(orch, "retry_execution", _recorder(calls, "retry_execution", execution))
    monkeypatch.setattr(orch, "get_execution_history", _recorder(calls, "get_execution_history", []))


def _client(
    monkeypatch: pytest.MonkeyPatch,
    level: str | None,
    *,
    role: str = "auditor",
    eqcr: bool = False,
    authenticated: bool = True,
    calls: list[str] | None = None,
    sql_log: list[str] | None = None,
) -> TestClient:
    """level=None：不是项目成员（缓存未命中 → 查库查无此人）。role 是全局角色；eqcr=本项目委派了 EQCR。"""
    monkeypatch.setattr(deps, "_get_cached_permission", _async_return(level))
    monkeypatch.setattr(deps, "_set_cached_permission", _noop)
    monkeypatch.setattr(deps, "_check_project_not_archived", _noop)
    monkeypatch.setattr(deps, "set_rls_context", _noop)
    monkeypatch.setattr(deliverable, "_is_project_eqcr", _async_return(eqcr))
    _stub_business(monkeypatch, calls if calls is not None else [])

    app = FastAPI()
    for r in (word_export.router, deliverable.router, note_export.router, chain_workflow.router,
              chain_workflow.batch_router, note_ai.router):
        app.include_router(r)
    log = sql_log if sql_log is not None else []

    async def _db():
        yield _FakeDB(log)

    app.dependency_overrides[get_db] = _db
    if authenticated:
        user = SimpleNamespace(id=ME, role=SimpleNamespace(value=role))

        async def _user():  # 🔴 override 不能带 *args/**kwargs：FastAPI 会把它们当成必填查询参数（422）
            return user

        app.dependency_overrides[deps.get_current_user] = _user
    return TestClient(app, raise_server_exceptions=False)


_P = f"/api/projects/{PID}"
_N = f"/api/disclosure-notes/{PID}"
# (说明, METHOD, 路径, 请求体)
_GENERATE = [  # 生成交付件：_guard_action（review 及以上 + 角色矩阵 + EQCR 只读）
    ("一键生成全套", "post", f"{_P}/word-exports/full-deliverables", {"year": 2025, "confirm_inconsistent": True}),
    ("生成附注（word-exports）", "post", f"{_P}/word-exports/disclosure-notes/generate", None),
    ("重试失败项", "post", f"{_P}/word-exports/jobs/{JOB}/retry", None),
    ("交付中心生成附注", "post", f"{_P}/deliverables/disclosure-notes/render", {"year": 2025}),
    ("导出附注 Word", "post", f"{_P}/notes/export-word", {"year": 2025}),
    ("组合导出包", "post", f"{_P}/workflow/export-package", {"year": 2025}),
]
_PREPARE = [  # 编制：edit
    ("全链路生成", "post", f"{_P}/workflow/execute-full-chain", {"year": 2025}),
    ("全链路重试", "post", f"{_P}/workflow/retry/{EXEC}", None),
    ("报表同步到附注", "post", f"{_P}/workflow/notes/sync-from-report?year=2025", None),
    ("附注裁剪排序", "post", f"{_P}/workflow/notes/trim-and-sort?year=2025", None),
]
_VIEW = [  # 查看 / AI 预览：readonly 及以上
    ("导出历史", "get", f"{_P}/word-exports/history", None),
    ("任务进度", "get", f"{_P}/word-exports/jobs/{JOB}", None),
    ("交付件列表", "get", f"{_P}/deliverables/", None),
    ("执行历史", "get", f"{_P}/workflow/executions", None),
    ("一致性检查", "get", f"{_P}/workflow/consistency-check?year=2025", None),
    ("数据健康度", "get", f"{_P}/workflow/data-health?year=2025", None),
    ("AI 生成会计政策", "post", f"{_N}/ai/generate-policy", {"section_number": "五、1"}),
    ("AI 生成变动分析", "post", f"{_N}/ai/generate-analysis", {"section_number": "五、1"}),
    ("AI 披露完整性检查", "post", f"{_N}/ai/check-completeness", None),
    ("AI 表述规范检查", "post", f"{_N}/ai/check-expression?section_number=x", None),
]
_ALL = _GENERATE + _PREPARE + _VIEW + [("全链路进度流", "get", f"{_P}/workflow/progress/{EXEC}", None)]


def _ids(cases):
    return [c[0] for c in cases]


def _call(client: TestClient, method: str, path: str, body):
    return getattr(client, method)(path, json=body) if body is not None else getattr(client, method)(path)


def _assert_denied(resp, name: str, who: str) -> None:
    assert resp.status_code == 403 and GATE_DENIED in resp.text, f"{name}：{who}未被拦 {resp.status_code} {resp.text}"


def test_premise_reviewers_are_review_level() -> None:
    """定级依据：复核人在项目里是 review 级、编制人是 edit 级。ROLE_MAP 一变，本文件的定级就要重审。"""
    for role in ("signing_partner", "partner", "manager", "qc", "eqcr"):
        assert ROLE_MAP[role][1].value == "review", role
    for role in ("auditor", "assistant"):
        assert ROLE_MAP[role][1].value == "edit", role


@pytest.mark.parametrize("name,method,path,body", _ALL, ids=_ids(_ALL))
def test_non_member_is_blocked_before_any_business_call(monkeypatch, name, method, path, body) -> None:
    calls: list[str] = []
    _assert_denied(_call(_client(monkeypatch, None, calls=calls), method, path, body), name, "项目组外的人")
    assert calls == [], f"{name}：被拦下的请求仍调到了业务层 {calls}"


@pytest.mark.parametrize("name,method,path,body", _VIEW, ids=_ids(_VIEW))
def test_readonly_member_can_view(monkeypatch, name, method, path, body) -> None:
    resp = _call(_client(monkeypatch, "readonly"), method, path, body)
    assert resp.status_code == 200, f"{name}：只读成员看不了 {resp.status_code} {resp.text}"


@pytest.mark.parametrize("name,method,path,body", _GENERATE + _PREPARE, ids=_ids(_GENERATE + _PREPARE))
def test_readonly_member_cannot_generate(monkeypatch, name, method, path, body) -> None:
    calls: list[str] = []
    _assert_denied(_call(_client(monkeypatch, "readonly", calls=calls), method, path, body), name, "只读成员")
    assert calls == []


@pytest.mark.parametrize("level", ["review", "edit"])
@pytest.mark.parametrize("name,method,path,body", _GENERATE, ids=_ids(_GENERATE))
def test_team_member_can_generate_deliverables(monkeypatch, name, method, path, body, level) -> None:
    """review（合伙人 / 经理 / 质控）与 edit（审计员 / 助理）都能生成本项目交付件。"""
    calls: list[str] = []
    resp = _call(_client(monkeypatch, level, calls=calls), method, path, body)
    assert resp.status_code == 200, f"{name}：{level} 级成员被拒 {resp.status_code} {resp.text}"
    assert calls, f"{name}：放行了却没进业务层"


@pytest.mark.parametrize("name,method,path,body", _PREPARE, ids=_ids(_PREPARE))
def test_only_preparers_can_rerun_the_chain(monkeypatch, name, method, path, body) -> None:
    """全链路 / 附注同步与裁剪会改写试算表、报表、附注：只有 edit 级（编制人）能触发，复核人（review）不能。"""
    _assert_denied(_call(_client(monkeypatch, "review"), method, path, body), name, "复核人")
    calls: list[str] = []
    resp = _call(_client(monkeypatch, "edit", calls=calls), method, path, body)
    assert resp.status_code == 200 and calls, f"{name}：编制人被拒 {resp.status_code} {resp.text}"


@pytest.mark.parametrize("name,method,path,body", _GENERATE + _PREPARE + _VIEW, ids=_ids(_GENERATE + _PREPARE + _VIEW))
def test_admin_bypasses_membership(monkeypatch, name, method, path, body) -> None:
    resp = _call(_client(monkeypatch, None, role="admin"), method, path, body)
    assert resp.status_code == 200, f"{name}：admin 被拒 {resp.status_code} {resp.text}"


def test_eqcr_on_project_can_view_but_not_generate(monkeypatch) -> None:
    """EQCR 是本项目 review 级成员，但交付件只读 —— 生成的各入口同一结论（此前一键全套 / 导出附注 Word 等绕过）。"""
    for name, method, path, body in _GENERATE:
        calls: list[str] = []
        resp = _call(_client(monkeypatch, "review", role="partner", eqcr=True, calls=calls), method, path, body)
        _assert_denied(resp, name, "EQCR ")
        assert calls == [], name
    for name, method, path, body in _VIEW:
        resp = _call(_client(monkeypatch, "review", role="partner", eqcr=True), method, path, body)
        assert resp.status_code == 200, f"{name}：EQCR 看不了 {resp.status_code}"


def test_role_matrix_applies_to_one_click_too(monkeypatch) -> None:
    """全局角色无导出权（readonly）时，即便是 edit 级成员也不能一键生成 —— 与交付中心逐项生成同一角色矩阵。"""
    name, method, path, body = _GENERATE[0]
    _assert_denied(_call(_client(monkeypatch, "edit", role="readonly"), method, path, body), name, "无导出权的角色")


@pytest.mark.parametrize("name,method,path,body", [_GENERATE[0], _GENERATE[3], _PREPARE[0], _VIEW[0]],
                         ids=_ids([_GENERATE[0], _GENERATE[3], _PREPARE[0], _VIEW[0]]))
def test_anonymous_is_rejected(monkeypatch, name, method, path, body) -> None:
    resp = _call(_client(monkeypatch, None, authenticated=False), method, path, body)
    assert resp.status_code in (401, 403), f"{name}：未登录 {resp.status_code}"


def test_compare_only_reads_this_projects_execution(monkeypatch) -> None:
    """版本对比此前只按 execution_id 取执行记录 ⇒ 本项目成员可读别的项目的执行快照；现必须同时按本项目过滤。"""
    sql_log: list[str] = []
    resp = _client(monkeypatch, "readonly", sql_log=sql_log).get(f"{_P}/workflow/compare/{EXEC}")
    assert resp.status_code == 404 and "执行记录不存在" in resp.text, resp.text
    chain_sql = [s for s in sql_log if "FROM chain_executions" in s]
    # 🔴 只看 WHERE 之后：SELECT 列表本就含 chain_executions.project_id，整句匹配恒真（磁盘变异实测抓到过）
    assert chain_sql and "WHERE" in chain_sql[0], chain_sql
    assert "chain_executions.project_id" in chain_sql[0].split("WHERE", 1)[1], chain_sql


def test_batch_execute_skips_projects_without_edit(monkeypatch) -> None:
    """批量执行全链路逐项目校验 edit：有权的照常执行，无权的跳过并写明原因（不再替别人的项目跑全链路）。"""
    calls: list[str] = []
    client = _client(monkeypatch, None, calls=calls)

    async def _level(_user_id, project_id):
        return "edit" if project_id == PID else None

    monkeypatch.setattr(deps, "_get_cached_permission", _level)
    resp = client.post("/api/workflow/batch-execute", json={"project_ids": [str(PID), str(OTHER)], "year": 2025})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert (body["success"], body["skipped"], body["failed"]) == (1, 1, 0), body
    skipped = next(r for r in body["results"] if r["project_id"] == str(OTHER))
    assert skipped["status"] == "skipped" and GATE_DENIED in skipped["reason"], skipped
    assert calls.count("execute_full_chain") == 1


def test_every_generate_entry_shares_the_deliverable_guard() -> None:
    """生成附注的各入口（交付中心 / word-exports / 导出附注 Word / 组合导出包）是同一个判定函数，不是几份拷贝。"""
    for mod in (word_export, note_export, chain_workflow):
        assert mod._guard_action is deliverable._guard_action, mod.__name__


def test_mutation_guard_without_membership_lets_outsider_generate(monkeypatch) -> None:
    """变异：把 _guard_action 里的成员校验换成空操作，项目组外的人立刻能生成 ⇒ 拦人的就是这一步。

    故障注在被测函数的下一层（memory：不替换被测函数本身）—— _guard_action 照常运行，只是它调用的成员校验失效。
    """
    monkeypatch.setattr(deliverable, "assert_project_permission", _noop)
    for name, method, path, body in _GENERATE:
        resp = _call(_client(monkeypatch, None), method, path, body)
        assert resp.status_code == 200, f"{name}：去掉成员校验后仍 {resp.status_code}，说明拦人的不是它"


def test_mutation_dependency_without_membership_lets_outsider_in(monkeypatch) -> None:
    """变异：require_project_access 下层的成员校验失效 ⇒ 挂它的端点对外人放行（证明这些端点挂的就是它）。"""

    async def _no_membership_check(_db, current_user, *_a, **_k):
        return current_user

    monkeypatch.setattr(deps, "assert_project_permission", _no_membership_check)
    cases = [c for c in _PREPARE + _VIEW if "/deliverables/" not in c[2]]  # 交付中心走 _guard_action，另测
    for name, method, path, body in cases:
        resp = _call(_client(monkeypatch, None), method, path, body)
        assert resp.status_code == 200, f"{name}：去掉成员校验后仍 {resp.status_code}"
