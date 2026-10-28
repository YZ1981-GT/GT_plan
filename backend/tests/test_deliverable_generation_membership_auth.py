"""生成 / 查看附注与交付件的项目成员鉴权 —— 项目组成员只能生成自己项目的附注，项目组外的人 403。

2026-10-19 补。此前以下入口只看登录与全局角色，不看是不是本项目成员 ⇒ 任意登录用户可为任意项目生成附注：
word-exports 整组（一键生成全套等）、交付中心（``deliverable._guard_action``）、导出附注 Word（note_export）、
全链路工作流（chain_workflow：生成附注 / 附注同步与裁剪 / 组合导出包 / 批量执行）、附注 AI（note_ai 四个）。现定级：

- 查看（含 AI 预览，不落库）：本项目成员 readonly 及以上；
- 生成交付件（交付中心 / 一键全套 / 导出附注 Word / 组合导出包）：同一判定 ``_guard_action`` —— 本项目成员
  review 及以上 + 角色矩阵 + EQCR 只读。review 而非 edit：review 门禁放行 review 级的质控与 EQCR 的读与非写动作；
  合伙人 / 经理为 edit 级同样满足（EQCR 由 ``is_project_eqcr`` 判定后被矩阵拒绝写操作）；
- 编制（全链路执行 / 重试 / 附注同步与裁剪，会改写试算表 / 报表 / 附注）：edit，与附注模块写端点同级。

同日用户拍板「合伙人和经理都要用」：附注编辑器导出 Word、交付件章节刷新 / 报告正文回填原为 edit 门、合伙人 / 经理
用不了，改走同一个 ``_guard_action``（review 门）；partner-manager-edit-permission 起合伙人 / 经理已是 edit 级，
这几个入口留在 review 门是为了 review 级的质控也能用。溯源 / 章节状态 / 刷新 / 回填另须交付件属于路径上的项目
（防凭别的项目的交付件 id 越权）。

做法同 test_phase8_endpoint_role_levels（memory ㉕；partner-manager-edit-permission 需求 12.1）：请求经权限世界
（``tests/authz_world.py``）真发。身份是世界里的真实用户、成员行与委派：成员行取 ``ROLE_MAP`` 对委派角色给出的值
（未登记角色取 ``UNMAPPED_ROLE``），并带一条该角色的现行委派；EQCR 由真实的 ``eqcr`` 现行委派给出（``_guard_action``
经 ``is_project_eqcr`` 读委派表与人员库）。判定由生产的 ``require_project_access`` / ``assert_project_permission`` /
``_guard_action`` 作出，门禁、归档守卫与 EQCR 判定都不替换。端点另读的交付件、执行记录、报表三张表
在世界里补建（只建表，外键只留指向已建表的）。业务层打桩并计数 —— 被拦下的请求一次业务调用都不能有，放行的请求
恰好调到它该调的那几个。
"""
from __future__ import annotations

import io
import uuid
from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy import Enum as SAEnum
from sqlalchemy import event
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

import app.services.deliverable_note_consistency as note_consistency
import app.services.llm_client as llm_client
from app.models.base import PermissionLevel, ProjectUserRole
from app.models.chain_execution import ChainExecution
from app.models.phase13_models import WordExportTask
from app.models.report_models import FinancialReport
from app.routers import (
    chain_workflow, deliverable, deliverable_lineage, disclosure_notes, note_ai, note_export, word_export,
)
from app.services.assignment_service import EQCR_ROLE_ALIASES, ROLE_MAP, map_assignment_role
from app.services.consistency_gate import ConsistencyGate
from app.services.data_health_monitor import DataHealthMonitor
from app.services.deliverable_refresh_service import DeliverableRefreshService
from app.services.deliverable_writeback_service import DeliverableWritebackService
from app.services.eqcr_resolver import is_project_eqcr
from app.services.export_job_service import ExportJobService
from app.services.export_package_service import ExportPackageService
from app.services.full_deliverables_executor import FullDeliverablesExecutor
from app.services.note_trim_sort_service import NoteTrimSortService
from app.services.note_word_exporter import NoteWordExporter
from app.services.reference_doc_service import ReferenceDocService
from app.services.report_note_sync_service import ReportNoteSyncService
from tests.authz_world import (
    OTHER_PROJECT_ID, TARGET_PROJECT_ID, WORLD_TABLE_NAMES, AuthzWorld, Identity, ServiceStub, pg_world, sqlite_world,
)
from tests.role_map_expected import EXPECTED_EQCR_ALIASES, EXPECTED_ROLE_MAP

PID = TARGET_PROJECT_ID
CREATOR = uuid.UUID("11111111-1111-1111-1111-111111111111")  # 业务桩返回对象里的创建人（不是请求者）
JOB = uuid.UUID("55555555-5555-5555-5555-555555555555")
TASK = uuid.UUID("66666666-6666-6666-6666-666666666666")
EXEC = "77777777-7777-7777-7777-777777777777"
UNREGISTERED = "观察员"  # 未登记的委派角色 → UNMAPPED_ROLE（readonly, readonly）
GATE = "app.deps.assert_project_permission"
GATE_CLOSURE = "app.deps.require_project_access.<locals>.dependency"
GUARD = "app.routers.deliverable._guard_action"
GATE_DENIED = "权限不足"  # assert_project_permission 与 _guard_action 的 403 文案

_INCONSISTENT = {
    "consistent": False,
    "never_synced": [{"note_section": "八、1", "section_title": "货币资金", "wp_codes": ["E1"]}],
    "stale": [],
}
_ROUTERS = (word_export.router, deliverable.router, note_export.router, chain_workflow.router,
            chain_workflow.batch_router, note_ai.router, deliverable_lineage.router, disclosure_notes.router)
# 端点另读的表：交付件归属与门控（deliverable_lineage）、版本对比（chain_workflow.compare）
_EXTRA_TABLES = (WordExportTask.__table__, ChainExecution.__table__, FinancialReport.__table__)


def _create_extra_tables(session) -> None:
    """在世界的连接上补建三张表（外键只留指向已建表的；PG 上先在临时 schema 内建枚举类型）。"""
    conn = session.connection()
    known = WORLD_TABLE_NAMES | {table.name for table in _EXTRA_TABLES}
    for table in _EXTRA_TABLES:
        if conn.dialect.name == "postgresql":
            for column in table.columns:
                if isinstance(column.type, SAEnum):
                    postgresql.ENUM(*column.type.enums, name=column.type.name).create(conn, checkfirst=False)
        fks = [fk for fk in table.foreign_key_constraints
               if {element.target_fullname.split(".")[-2] for element in fk.elements} <= known]
        conn.execute(CreateTable(table, include_foreign_key_constraints=fks))


async def _furnish(world: AuthzWorld) -> None:
    """补建三张表，并在目标项目上建交付件 TASK（编辑中的报告正文）。"""
    await world.db.run_sync(_create_extra_tables)
    creator = await world.user()
    world.db.add(WordExportTask(id=TASK, project_id=PID, doc_type="audit_report", status="editing",
                                created_by=creator.id))
    await world.db.flush()


@pytest_asyncio.fixture
async def world(monkeypatch: pytest.MonkeyPatch):
    async with sqlite_world(monkeypatch) as w:
        await _furnish(w)
        yield w


def _stub_business(world: AuthzWorld) -> dict[str, ServiceStub]:
    """业务层全部打桩计数（键 = 桩名）：用来证明「被拦下的请求没碰业务」「放行的请求恰好调到该调的」。"""
    job = SimpleNamespace(
        id=JOB, project_id=PID, job_type="full_deliverables", status="succeeded", payload={},
        progress_total=3, progress_done=3, failed_count=0, initiated_by=CREATOR, created_at=None, updated_at=None,
    )
    task = SimpleNamespace(id=TASK, project_id=PID, doc_type="disclosure_notes", status="generated", created_by=CREATOR)
    execution = SimpleNamespace(id=EXEC, status="completed", steps={}, total_duration_ms=1,
                                started_at=None, completed_at=None)
    lineage = {"written": [], "rejected": [], "skipped": [], "failed": [], "refreshed": [], "messages": []}
    tasks, orch = word_export.ExportTaskService, type(chain_workflow.chain_orchestrator)
    targets = {
        "check_note_consistency": (note_consistency, "check_note_consistency", _INCONSISTENT),
        "get_job": (ExportJobService, "get_job", job),
        "get_job_items": (ExportJobService, "get_job_items", []),
        "retry_failed": (ExportJobService, "retry_failed", 0),
        "run_full_deliverables": (FullDeliverablesExecutor, "run", SimpleNamespace(job_id=JOB)),
        "export_note_word": (NoteWordExporter, "export", io.BytesIO(b"PK\x03\x04 docx")),
        "export_package": (ExportPackageService, "export_package", io.BytesIO(b"PK\x03\x04 zip")),
        "run_all_checks": (ConsistencyGate, "run_all_checks", SimpleNamespace(overall="pass", checks=[])),
        "calculate_health_score": (DataHealthMonitor, "calculate_health_score", SimpleNamespace(score=100, checks=[])),
        "sync_report_to_notes": (ReportNoteSyncService, "sync_report_to_notes", {"synced": 0}),
        "trim_and_sort": (NoteTrimSortService, "trim_and_sort", {"trimmed": 0}),
        "load_context": (ReferenceDocService, "load_context", []),
        "chat_completion": (llm_client, "chat_completion", "生成的文本"),
        "create_task": (tasks, "create_task", task),
        "update_status": (tasks, "update_status", task),
        "get_history": (tasks, "get_history", []),
        "list_deliverables": (deliverable.DeliverableService, "list_deliverables", []),
        "writeback": (DeliverableWritebackService, "writeback", lineage),
        "refresh_section": (DeliverableRefreshService, "refresh_section", lineage),
        "refresh_all_stale_sections": (DeliverableRefreshService, "refresh_all_stale_sections", lineage),
        "trace": (deliverable_lineage.LinkageFacadeService, "trace", []),
        "get_section_states": (deliverable_lineage.DeliverableSectionStateService, "get_section_states", []),
        "capability": (deliverable_lineage, "_require_capability", "ok"),
        "audit_log": (type(deliverable_lineage.audit_logger), "log_action", None),
        "execute_full_chain": (orch, "execute_full_chain", execution),
        "retry_execution": (orch, "retry_execution", execution),
        "get_execution_history": (orch, "get_execution_history", []),
    }
    return {key: world.stub(owner, attr, returns=value) for key, (owner, attr, value) in targets.items()}


def _counts(stubs: dict[str, ServiceStub]) -> dict[str, int]:
    return {key: stub.count for key, stub in stubs.items() if stub.count}


def _reset(stubs: dict[str, ServiceStub]) -> None:
    for stub in stubs.values():
        stub.calls.clear()


async def _delegated(world: AuthzWorld, alias: str, *, global_role: str = "auditor") -> Identity:
    """委派为 ``alias`` 的成员：成员行取 ROLE_MAP 对该角色给出的值（未登记取 UNMAPPED_ROLE），另建一条该角色的
    现行委派（``eqcr_assignment`` 按任意委派角色建人员库记录与委派；EQCR 别名集合中的角色会被 ``is_project_eqcr`` 认作 EQCR）。"""
    role, level = map_assignment_role(alias)
    identity = await world.member(level, role, global_role=global_role)
    await world.eqcr_assignment(alias, user=identity.user)
    return identity


def _member_row(identity: Identity) -> tuple[str, str]:
    return identity.member.role.value, identity.member.permission_level.value


async def _send(world: AuthzWorld, user, method: str, path: str, body):
    async with world.client(*_ROUTERS, user=user) as client:
        response = await client.request(method.upper(), path, **({"json": body} if body is not None else {}))
    return response, client


_P = f"/api/projects/{PID}"
_N = f"/api/disclosure-notes/{PID}"
_CASE_ARGS = ("name", "method", "path", "body", "calls")
# (说明, METHOD, 路径, 请求体, 放行时各业务桩的调用次数)
_GENERATE = [  # 生成交付件：_guard_action（review 及以上 + 角色矩阵 + EQCR 只读）
    ("一键生成全套", "post", f"{_P}/word-exports/full-deliverables", {"year": 2025, "confirm_inconsistent": True},
     {"run_full_deliverables": 1, "get_job": 1, "get_job_items": 1}),
    ("生成附注（word-exports）", "post", f"{_P}/word-exports/disclosure-notes/generate", None,
     {"create_task": 1, "update_status": 2}),
    ("重试失败项", "post", f"{_P}/word-exports/jobs/{JOB}/retry", None, {"get_job": 1, "retry_failed": 1}),
    ("交付中心生成附注", "post", f"{_P}/deliverables/disclosure-notes/render", {"year": 2025},
     {"check_note_consistency": 1}),  # 附注与底稿不一致 ⇒ 200 + 待确认清单，不再往下导出
    ("导出附注 Word", "post", f"{_P}/notes/export-word", {"year": 2025}, {"export_note_word": 1}),
    ("组合导出包", "post", f"{_P}/workflow/export-package", {"year": 2025}, {"export_package": 1}),
    ("附注编辑器导出 Word", "post", f"{_N}/2025/export-word", None, {"export_note_word": 1}),
    ("交付件单节刷新", "post", f"{_P}/deliverables/{TASK}/refresh-section", {"year": 2025, "section_code": "八、1"},
     {"capability": 1, "audit_log": 1, "refresh_section": 1}),
    ("交付件批量刷新", "post", f"{_P}/deliverables/{TASK}/refresh-stale", {"year": 2025},
     {"capability": 1, "get_section_states": 1, "audit_log": 1, "refresh_all_stale_sections": 1}),
    ("报告正文回填", "post", f"{_P}/deliverables/{TASK}/writeback", {"year": 2025},
     {"capability": 1, "get_section_states": 1, "writeback": 1, "audit_log": 1}),
]
_PREPARE = [  # 编制：edit
    ("全链路生成", "post", f"{_P}/workflow/execute-full-chain", {"year": 2025}, {"execute_full_chain": 1}),
    ("全链路重试", "post", f"{_P}/workflow/retry/{EXEC}", None, {"retry_execution": 1}),
    ("报表同步到附注", "post", f"{_P}/workflow/notes/sync-from-report?year=2025", None, {"sync_report_to_notes": 1}),
    ("附注裁剪排序", "post", f"{_P}/workflow/notes/trim-and-sort?year=2025", None, {"trim_and_sort": 1}),
]
_VIEW = [  # 查看 / AI 预览：readonly 及以上
    ("导出历史", "get", f"{_P}/word-exports/history", None, {"get_history": 1}),
    ("任务进度", "get", f"{_P}/word-exports/jobs/{JOB}", None, {"get_job": 1, "get_job_items": 1}),
    ("交付件列表", "get", f"{_P}/deliverables/", None, {"list_deliverables": 1}),
    ("执行历史", "get", f"{_P}/workflow/executions", None, {"get_execution_history": 1}),
    ("一致性检查", "get", f"{_P}/workflow/consistency-check?year=2025", None, {"run_all_checks": 1}),
    ("数据健康度", "get", f"{_P}/workflow/data-health?year=2025", None, {"calculate_health_score": 1}),
    # 这三个端点不再按固定 2025 取上年附注 / 知识库：年度取请求里的，缺省取项目审计年度，都没有 ⇒ 422（权限世界的
    # 目标项目没填年度）。这里与前端一样显式带年度；缺年度的行为见 test_note_ai_without_year_is_422_after_membership
    ("AI 生成会计政策", "post", f"{_N}/ai/generate-policy", {"section_number": "五、1", "year": 2025},
     {"load_context": 1, "chat_completion": 1}),
    ("AI 生成变动分析", "post", f"{_N}/ai/generate-analysis", {"section_number": "五、1", "year": 2025},
     {"load_context": 1, "chat_completion": 1}),
    ("AI 披露完整性检查", "post", f"{_N}/ai/check-completeness?year=2025", None,
     {"load_context": 1, "chat_completion": 1}),
    ("AI 表述规范检查", "post", f"{_N}/ai/check-expression?section_number=x", None, {}),  # 端点本身不调业务
    ("交付件溯源", "get", f"{_P}/deliverables/{TASK}/trace?section_code=x", None, {"trace": 1, "get_section_states": 1}),
    ("交付件章节状态", "get", f"{_P}/deliverables/{TASK}/section-states", None, {"get_section_states": 1}),
]
_LINEAGE = [c for c in _GENERATE + _VIEW if f"/deliverables/{TASK}/" in c[2]]
_ALL = _GENERATE + _PREPARE + _VIEW + [("全链路进度流", "get", f"{_P}/workflow/progress/{EXEC}", None, {})]
# 生成交付件：非 EQCR 的四种成员行取值各取一个别名 ——（qc, review）（partner, edit）（manager, edit）（auditor, edit）
_GENERATORS = ("qc", "partner", "manager", "auditor")


def _ids(cases):
    return [c[0] for c in cases]


def _assert_denied(resp, name: str, who: str) -> None:
    assert (resp.status_code, resp.json()) == (403, {"detail": GATE_DENIED}), (
        f"{name}：{who}未被拦 {resp.status_code} {resp.text}")


def test_premise_role_map_matches_expected_table() -> None:
    """定级依据：``ROLE_MAP`` 逐键等于需求 2.5 期望表（``tests/role_map_expected.py``）—— 合伙人（含签字合伙人）、
    经理、审计员 / 助理是 edit 级，质控、EQCR 是 review 级；取值为 (partner, review) 的键恰是 EQCR 别名集合。
    增删任一键、改动任一取值都打红：ROLE_MAP 一变，本文件的定级就要重审。"""
    actual, expected = set(ROLE_MAP), set(EXPECTED_ROLE_MAP)
    assert actual == expected, (
        f"ROLE_MAP 的键与期望表不一致：多出 {sorted(actual - expected)}，缺少 {sorted(expected - actual)}")
    for key, (want_role, want_level) in EXPECTED_ROLE_MAP.items():
        role, level = ROLE_MAP[key]
        assert (type(role), type(level)) == (ProjectUserRole, PermissionLevel), (
            f"{key}：取值类型为 {type(role).__name__} / {type(level).__name__}")
        assert (role.value, level.value) == (want_role, want_level), (
            f"{key}：ROLE_MAP 为 ({role.value}, {level.value})，期望表为 ({want_role}, {want_level})")
    partner_review = {k for k, (r, lv) in ROLE_MAP.items() if (r.value, lv.value) == ("partner", "review")}
    assert partner_review == EXPECTED_EQCR_ALIASES, (
        f"取值为 (partner, review) 的键 {sorted(partner_review)} 不等于 EQCR 别名集合 {sorted(EXPECTED_EQCR_ALIASES)}")
    assert EQCR_ROLE_ALIASES == EXPECTED_EQCR_ALIASES, f"EQCR_ROLE_ALIASES 为 {sorted(EQCR_ROLE_ALIASES)}"


@pytest.mark.parametrize(_CASE_ARGS, _ALL, ids=_ids(_ALL))
async def test_non_member_is_blocked_before_any_business_call(world, name, method, path, body, calls) -> None:
    """非成员（目标项目没有成员行，另一项目上是 edit 级）：403，业务 0 次。"""
    stubs = _stub_business(world)
    identity = await world.non_member()
    resp, client = await _send(world, identity.user, method, path, body)
    _assert_denied(resp, name, "项目组外的人")
    assert _counts(stubs) == {}, f"{name}：被拦下的请求仍调到了业务层 {_counts(stubs)}"
    client.assert_passed(GATE, times=1)


@pytest.mark.parametrize(_CASE_ARGS, _VIEW, ids=_ids(_VIEW))
async def test_readonly_member_can_view(world, name, method, path, body, calls) -> None:
    stubs = _stub_business(world)
    identity = await _delegated(world, UNREGISTERED)
    assert _member_row(identity) == ("readonly", "readonly")
    resp, _ = await _send(world, identity.user, method, path, body)
    assert resp.status_code == 200, f"{name}：只读成员看不了 {resp.status_code} {resp.text}"
    assert _counts(stubs) == calls, name


@pytest.mark.parametrize(_CASE_ARGS, _GENERATE + _PREPARE, ids=_ids(_GENERATE + _PREPARE))
async def test_readonly_member_cannot_generate(world, name, method, path, body, calls) -> None:
    stubs = _stub_business(world)
    identity = await _delegated(world, UNREGISTERED)
    resp, _ = await _send(world, identity.user, method, path, body)
    _assert_denied(resp, name, "只读成员")
    assert _counts(stubs) == {}, name


@pytest.mark.parametrize("alias", _GENERATORS)
@pytest.mark.parametrize(_CASE_ARGS, _GENERATE, ids=_ids(_GENERATE))
async def test_team_member_can_generate_deliverables(world, name, method, path, body, calls, alias) -> None:
    """review 级（质控）与 edit 级（合伙人 / 经理 / 审计员）成员都能生成本项目交付件，业务恰好调到该调的那几个。

    EQCR 虽是 review 级，但交付件只读，见 ``test_eqcr_on_project_can_view_but_not_generate``。"""
    stubs = _stub_business(world)
    identity = await _delegated(world, alias)
    assert _member_row(identity) == EXPECTED_ROLE_MAP[alias]
    resp, client = await _send(world, identity.user, method, path, body)
    assert resp.status_code == 200, f"{name}：{alias} {_member_row(identity)} 被拒 {resp.status_code} {resp.text}"
    assert _counts(stubs) == calls, name
    client.assert_passed(GUARD, times=1)


@pytest.mark.parametrize(_CASE_ARGS, _PREPARE, ids=_ids(_PREPARE))
async def test_only_preparers_can_rerun_the_chain(world, name, method, path, body, calls) -> None:
    """全链路 / 附注同步与裁剪会改写试算表、报表、附注：只有 edit 级成员（合伙人 / 经理 / 审计员 / 助理）能触发，
    review 级成员（质控 / EQCR）不能。"""
    stubs = _stub_business(world)
    for alias in ("qc", "eqcr"):
        reviewer = await _delegated(world, alias)
        resp, _ = await _send(world, reviewer.user, method, path, body)
        _assert_denied(resp, name, f"review 级成员（{alias}）")
    assert _counts(stubs) == {}, name
    for alias in ("partner", "manager", "auditor"):
        preparer = await _delegated(world, alias)
        resp, _ = await _send(world, preparer.user, method, path, body)
        assert resp.status_code == 200, f"{name}：edit 级成员（{alias}）被拒 {resp.status_code} {resp.text}"
        assert _counts(stubs) == calls, f"{name}：{alias}"
        _reset(stubs)


@pytest.mark.parametrize(_CASE_ARGS, _GENERATE + _PREPARE + _VIEW, ids=_ids(_GENERATE + _PREPARE + _VIEW))
async def test_admin_bypasses_membership(world, name, method, path, body, calls) -> None:
    """全局 admin、不是本项目成员：照常放行。"""
    stubs = _stub_business(world)
    identity = await world.admin_non_member()
    resp, _ = await _send(world, identity.user, method, path, body)
    assert resp.status_code == 200, f"{name}：admin 被拒 {resp.status_code} {resp.text}"
    assert _counts(stubs) == calls, name


async def test_eqcr_on_project_can_view_but_not_generate(world) -> None:
    """EQCR 是本项目 review 级成员，但交付件只读 —— 生成的各入口同一结论（此前一键全套 / 导出附注 Word 等绕过）。

    EQCR 由真实的 ``eqcr`` 现行委派给出：成员行（partner, review）+ 人员库记录 + 委派，全局角色 partner。"""
    stubs = _stub_business(world)
    identity = await _delegated(world, "eqcr", global_role="partner")
    assert _member_row(identity) == EXPECTED_ROLE_MAP["eqcr"]
    assert await is_project_eqcr(world.db, identity.user, PID) is True
    for name, method, path, body, _calls in _GENERATE:
        resp, client = await _send(world, identity.user, method, path, body)
        _assert_denied(resp, name, "EQCR ")
        assert _counts(stubs) == {}, name
        client.assert_passed(GUARD, times=1)
    for name, method, path, body, calls in _VIEW:
        resp, _ = await _send(world, identity.user, method, path, body)
        assert resp.status_code == 200, f"{name}：EQCR 看不了 {resp.status_code}"
        assert _counts(stubs) == calls, name
        _reset(stubs)


async def test_eqcr_chinese_alias_can_view_but_not_generate(world) -> None:
    """委派角色为「独立复核合伙人」（EQCR 中文别名）的成员同样只读 —— 生成类写操作 403，列表 / 预览 / 下载放行。

    需求 7.4：交付中心门禁改用 ``is_project_eqcr`` 后，中文别名「独立复核合伙人」也被识别为 EQCR。"""
    stubs = _stub_business(world)
    identity = await _delegated(world, "独立复核合伙人", global_role="partner")
    assert _member_row(identity) == EXPECTED_ROLE_MAP["独立复核合伙人"]
    assert await is_project_eqcr(world.db, identity.user, PID) is True
    for name, method, path, body, _calls in _GENERATE:
        resp, client = await _send(world, identity.user, method, path, body)
        _assert_denied(resp, name, "独立复核合伙人 ")
        assert _counts(stubs) == {}, name
        client.assert_passed(GUARD, times=1)
    for name, method, path, body, calls in _VIEW:
        resp, _ = await _send(world, identity.user, method, path, body)
        assert resp.status_code == 200, f"{name}：独立复核合伙人看不了 {resp.status_code}"
        assert _counts(stubs) == calls, name
        _reset(stubs)


async def test_role_matrix_applies_to_one_click_too(world) -> None:
    """全局角色无导出权（readonly）时，即便是 edit 级成员（经理）也不能一键生成 —— 与交付中心逐项生成同一角色矩阵。"""
    stubs = _stub_business(world)
    identity = await _delegated(world, "manager", global_role="readonly")
    assert _member_row(identity) == ("manager", "edit")
    name, method, path, body, _calls = _GENERATE[0]
    resp, client = await _send(world, identity.user, method, path, body)
    _assert_denied(resp, name, "无导出权的角色")
    assert _counts(stubs) == {}
    client.assert_passed(GUARD, times=1)
    client.assert_passed(GATE, times=1)  # 成员校验已执行（edit 级过了 review 门），拦人的是其后的角色矩阵


_ANONYMOUS = [_GENERATE[0], _GENERATE[3], _PREPARE[0], _VIEW[0]]


@pytest.mark.parametrize(_CASE_ARGS, _ANONYMOUS, ids=_ids(_ANONYMOUS))
async def test_anonymous_is_rejected(world, name, method, path, body, calls) -> None:
    stubs = _stub_business(world)
    resp, client = await _send(world, None, method, path, body)
    assert (resp.status_code, resp.json()) == (401, {"detail": "Not authenticated"}), f"{name}：未登录 {resp.status_code}"
    assert _counts(stubs) == {}, name
    client.assert_passed(GATE, times=0)


@pytest.mark.pg_only
async def test_compare_only_reads_this_projects_execution(monkeypatch: pytest.MonkeyPatch) -> None:
    """版本对比此前只按 execution_id 取执行记录 ⇒ 本项目成员可读别的项目的执行快照；现必须同时按本项目过滤。

    真 PG：端点以字符串绑定 uuid 列（路径参数 ``execution_id: str``），SQLite 上 SQLAlchemy 的 uuid 绑定处理器拒收
    字符串（``'str' object has no attribute 'hex'``），只有 PG 能真跑这条查询（需求 12.9）。"""
    async with pg_world(monkeypatch) as world:
        await _furnish(world)
        await world.other_project()
        execution = ChainExecution(id=uuid.UUID(EXEC), project_id=OTHER_PROJECT_ID, year=2025, steps={})
        world.db.add(execution)
        await world.db.flush()
        identity = await _delegated(world, UNREGISTERED)
        sql_log: list[str] = []
        event.listen(world.db.sync_session, "do_orm_execute", lambda state: sql_log.append(str(state.statement)))
        resp, client = await _send(world, identity.user, "get", f"{_P}/workflow/compare/{EXEC}", None)
        assert (resp.status_code, resp.json()) == (404, {"detail": "执行记录不存在"}), resp.text
        client.assert_passed(GATE, times=1)
        chain_sql = [s for s in sql_log if "FROM chain_executions" in s]
        # 🔴 只看 WHERE 之后：SELECT 列表本就含 chain_executions.project_id，整句匹配恒真（磁盘变异实测抓到过）
        assert chain_sql and "WHERE" in chain_sql[0], chain_sql
        assert "chain_executions.project_id" in chain_sql[0].split("WHERE", 1)[1], chain_sql
        # 对照：同一条执行记录改属本项目即可读到 ⇒ 上面的 404 来自项目过滤，而不是 id 对不上或表里没有
        execution.project_id = PID
        await world.db.flush()
        resp, _ = await _send(world, identity.user, "get", f"{_P}/workflow/compare/{EXEC}", None)
        assert (resp.status_code, resp.json()) == (
            200, {"execution_id": EXEC, "year": 2025, "changes": [], "total_changes": 0}), resp.text


async def test_batch_execute_skips_projects_without_edit(world) -> None:
    """批量执行全链路逐项目校验 edit：有权的照常执行，无权的跳过并写明原因（不再替别人的项目跑全链路）。"""
    stubs = _stub_business(world)
    identity = await _delegated(world, "manager")  # 目标项目 edit 级；在另一项目不是成员
    await world.other_project()
    body = {"project_ids": [str(PID), str(OTHER_PROJECT_ID)], "year": 2025}
    resp, client = await _send(world, identity.user, "post", "/api/workflow/batch-execute", body)
    assert resp.status_code == 200, resp.text
    result = resp.json()
    assert (result["total"], result["success"], result["skipped"], result["failed"]) == (2, 1, 1, 0), result
    assert result["results"] == [
        {"project_id": str(PID), "status": "success", "execution_id": EXEC},
        {"project_id": str(OTHER_PROJECT_ID), "status": "skipped", "reason": f"无权执行：{GATE_DENIED}"},
    ]
    assert [kwargs["project_id"] for _, kwargs in stubs["execute_full_chain"].calls] == [PID]
    assert _counts(stubs) == {"execute_full_chain": 1}
    client.assert_passed(GATE, times=2)


@pytest.mark.parametrize(_CASE_ARGS, _LINEAGE, ids=_ids(_LINEAGE))
async def test_lineage_only_touches_deliverables_of_this_project(world, name, method, path, body, calls) -> None:
    """交付件属于别的项目 ⇒ 403「交付物不属于该项目」（此前只按交付件 id 取，本项目成员可读写别的项目的交付件）；不存在 ⇒ 404。"""
    stubs = _stub_business(world)
    identity = await _delegated(world, "manager")
    task = await world.db.get(WordExportTask, TASK)
    task.project_id = (await world.other_project()).id
    await world.db.flush()
    resp, _ = await _send(world, identity.user, method, path, body)
    assert (resp.status_code, resp.json()) == (403, {"detail": "交付物不属于该项目"}), f"{name}：{resp.status_code} {resp.text}"
    assert _counts(stubs) == {}, f"{name}：归属不符仍调到了业务层 {_counts(stubs)}"
    await world.db.delete(task)
    await world.db.flush()
    resp, _ = await _send(world, identity.user, method, path, body)
    assert (resp.status_code, resp.json()) == (404, {"detail": "交付物不存在"}), f"{name}：{resp.status_code} {resp.text}"
    assert _counts(stubs) == {}, name


def test_every_generate_entry_shares_the_deliverable_guard() -> None:
    """生成附注的各入口（交付中心 / word-exports / 导出附注 Word / 组合导出包）是同一个判定函数，不是几份拷贝。"""
    for mod in (word_export, note_export, chain_workflow, deliverable_lineage, disclosure_notes):
        assert mod._guard_action is deliverable._guard_action, mod.__name__


async def test_guard_blocks_outsider_only_for_missing_membership(world) -> None:
    """拦外人的就是 ``_guard_action`` 里的成员校验：同一个外人只差一条本项目成员行 —— 没有时 403、业务 0 次
    （``_guard_action`` 与成员校验的代码都执行过），补一条（qc, review）成员行后同一请求放行。

    改写自变异用例 ``test_mutation_guard_without_membership_lets_outsider_generate``：原用例把 ``deliverable`` 里的成员
    校验换成空操作，需求 12.1 不允许替换 ``assert_project_permission``，改以成员行数据对照证明同一结论。"""
    stubs = _stub_business(world)
    role, level = map_assignment_role("qc")
    for name, method, path, body, calls in _GENERATE:
        outsider = await world.non_member()
        denied, client = await _send(world, outsider.user, method, path, body)
        _assert_denied(denied, name, "项目组外的人")
        assert _counts(stubs) == {}, name
        client.assert_passed(GUARD, times=1)
        client.assert_passed(GATE, times=1)
        await world.member(level, role, user=outsider.user)
        allowed, _ = await _send(world, outsider.user, method, path, body)
        assert allowed.status_code == 200, f"{name}：补成员行后仍 {allowed.status_code}，说明拦人的不是成员校验"
        assert _counts(stubs) == calls, name
        _reset(stubs)


async def test_dependency_blocks_outsider_only_for_missing_membership(world) -> None:
    """挂 ``require_project_access`` 的端点：拦外人的就是该依赖下的成员校验 —— 同一个外人只差一条本项目成员行，没有时
    403、业务 0 次，补一条（manager, edit）成员行后放行（证明这些端点挂的就是它）。

    改写自变异用例 ``test_mutation_dependency_without_membership_lets_outsider_in``（理由同上）。"""
    stubs = _stub_business(world)
    role, level = map_assignment_role("manager")
    cases = [c for c in _PREPARE + _VIEW if not c[2].endswith("/deliverables/")]  # 交付件列表走 _guard_action，另测
    for name, method, path, body, calls in cases:
        outsider = await world.non_member()
        denied, client = await _send(world, outsider.user, method, path, body)
        _assert_denied(denied, name, "项目组外的人")
        assert _counts(stubs) == {}, name
        client.assert_passed(GATE_CLOSURE, times=1)
        client.assert_passed(GUARD, times=0)
        await world.member(level, role, user=outsider.user)
        allowed, _ = await _send(world, outsider.user, method, path, body)
        assert allowed.status_code == 200, f"{name}：补成员行后仍 {allowed.status_code}"
        assert _counts(stubs) == calls, name
        _reset(stubs)


_NOTE_AI_WITHOUT_YEAR = [  # 与 _VIEW 里那三条同端点，只是请求不带年度
    ("AI 生成会计政策", "post", f"{_N}/ai/generate-policy", {"section_number": "五、1"}),
    ("AI 生成变动分析", "post", f"{_N}/ai/generate-analysis", {"section_number": "五、1"}),
    ("AI 披露完整性检查", "post", f"{_N}/ai/check-completeness", None),
]
_YEAR_MISSING = {"detail": "未设置审计年度，请先在项目基本信息中填写"}


async def test_note_ai_without_year_is_422_after_membership(world) -> None:
    """请求不带年度、项目也没填审计年度：成员得到 422「未设置审计年度」，业务 0 次（此前按固定 2025 取上年附注）；
    外人照旧 403 —— 年度在成员校验之后才解析。项目填了 2024 后同一请求放行，取数用的是 2024 而不是 2025。"""
    stubs = _stub_business(world)
    member = await _delegated(world, UNREGISTERED)
    outsider = await world.non_member()
    for name, method, path, body in _NOTE_AI_WITHOUT_YEAR:
        denied, _ = await _send(world, outsider.user, method, path, body)
        _assert_denied(denied, name, "项目组外的人")
        resp, _ = await _send(world, member.user, method, path, body)
        assert (resp.status_code, resp.json()) == (422, _YEAR_MISSING), (
            f"{name}：缺年度时 {resp.status_code} {resp.text}")
        assert _counts(stubs) == {}, name
    world.target.audit_year = 2024
    await world.db.flush()
    for name, method, path, body in _NOTE_AI_WITHOUT_YEAR:
        resp, _ = await _send(world, member.user, method, path, body)
        assert resp.status_code == 200, f"{name}：项目已填年度仍 {resp.status_code} {resp.text}"
        (args, _kwargs), = stubs["load_context"].calls
        assert args[2] == 2024, f"{name}：取数年度为 {args[2]!r}，应为项目审计年度 2024"
        _reset(stubs)
