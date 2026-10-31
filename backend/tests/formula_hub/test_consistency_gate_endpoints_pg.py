"""一致性门禁的启动注册与消费方端点（第 2 轮 D-4 / S1，需求 16.4、16.5；design §10.4 #38 的打红判据）。

阶段 D 浏览器实测：``gate_rules_chain`` 在 ``backend/app`` 里零引用，``ConsistencyPassedRule`` 从未注册进签发 /
导出包门禁 ⇒「…（当前为只提示模式）」在运行中的平台上不会出现；``test_consistency_gate_enforcement.py`` 直接 import
规则模块，看不到未注册。第 2 轮又现查到就绪页把门禁枚举用 ``str()`` 取文本再比字面量（S1，按用户追加确认第 1 条修，
``.agents/tasks/formula-suite-decisions-2026-10-30.md``）：
enforce 下 ready 不变 false、分组停在「通过」、严重级标签显示 ``GateSeverity.warning`` 原文。本文件：

- 注册：夹具先把注册表里已有的 CHAIN-CONSISTENCY 摘掉（模块导入或其他用例留下的注册不替生产注册点作证），再执行
  生产启动清单 ``STARTUP_TASKS`` 里的 ``register_phase_handlers`` 本身；结束时注册表与事件总线订阅原样恢复。
- 端点：按生产注册挂 router（``tests.authz_world.build_app``），只替换 ``get_current_user`` / ``get_db``，鉴权与
  ``gate_engine`` 都真实运行；只把导出包里的报表 Excel / 附注 Word 生成换成小桩（下游文件生成，不是判定）。
  - ``GET /api/projects/{pid}/sign-readiness``（sign_off 门禁，签字决策页）
  - ``GET /api/projects/{pid}/qc-dashboard/archive-readiness``（export_package 门禁，归档向导第 1 步）
  - ``POST /api/projects/{pid}/workflow/export-package``（导出包服务自身的判定）
  - 归档编排的门禁步骤 ``archive_gate.archive_gate_problems``（实际归档会不会被拦，读归档就绪的同一响应）
- 「一致性规则是唯一信号」的隔离：两个门禁的规则表只留它、就绪服务的补充类目换成空（空项目上这些类目本身就是
  blocking，会让 ready 与本规则无关地恒为 false，判据空转）；隔离后的响应规整后写成快照，前端就绪页挂载用例读同一份。
- 数据：回滚事务内新建的【测试】空项目（审计年度 2025：阻断级检查全部「未执行」、没有「失败」）；导出包的「改造前口径
  拒绝」另用和平药房 2025（只读：同一回滚事务，真实行不改）—— 它有阻断级「失败」。
"""
from __future__ import annotations

import json
import os
import re
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from io import BytesIO
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.deps import get_current_user
from app.models.base import UserRole
from app.models.core import Project, User
from tests.authz_world import assert_gates_are_production, assert_world_overrides, build_app
from tests.formula_hub._pg_harness import TEST_PROJECT_PREFIX, pg_tx_session

pytestmark = pytest.mark.pg_only

RULE = "CHAIN-CONSISTENCY"
MISC = ("misc", "其他门禁规则")
OBSERVE_HINT = re.compile(r"^一致性检查有 (\d+) 项未通过或未执行（当前为只提示模式）$")
ENFORCE_HINT = re.compile(r"^一致性检查有 (\d+) 项未通过或未执行，请补齐数据后重新检查$")
PRE_CHANGE_REFUSAL = "一致性检查未通过，无法导出"
RAW_ENUM_TEXT = ("GateSeverity.", "GateDecisionResult.", "GateType.")
SNAP_DIR = Path(__file__).resolve().parent / "_snapshots"


# ─── 生产注册 ────────────────────────────────────────────────────────────────


def _strip_rule(registry) -> None:
    for gate, rules in registry._rules.items():
        registry._rules[gate] = [r for r in rules if r.rule_code != RULE]


@pytest.fixture
def production_gate_registry():
    """执行生产启动清单里的 ``register_phase_handlers``；注册表与事件总线订阅在用例后原样恢复。"""
    from app.core.startup_registry import STARTUP_TASKS, StartupContext
    from app.models.phase14_enums import GateType
    from app.services.event_bus import event_bus
    from app.services.gate_engine import rule_registry

    saved_rules = {gate: list(rules) for gate, rules in rule_registry._rules.items()}
    saved_handlers = {kind: list(handlers) for kind, handlers in event_bus._handlers.items()}
    try:
        _strip_rule(rule_registry)
        [task] = [t for t in STARTUP_TASKS if t.name == "register_phase_handlers"]
        task.run(StartupContext())
        for gate in (GateType.sign_off, GateType.export_package):
            codes = [r.rule_code for r in rule_registry.get_rules(gate)]
            assert codes.count(RULE) == 1, (gate, "启动注册后该门禁应恰有一条一致性规则", codes.count(RULE))
        yield rule_registry
    finally:
        rule_registry._rules.clear()
        rule_registry._rules.update(saved_rules)
        event_bus._handlers.clear()
        event_bus._handlers.update(saved_handlers)


@contextmanager
def _rule_absent(registry) -> Iterator[None]:
    """临时摘掉一致性规则（= 改造前：从未注册），用于 observe 等效对照。"""
    saved = {gate: list(rules) for gate, rules in registry._rules.items()}
    _strip_rule(registry)
    try:
        yield
    finally:
        registry._rules.clear()
        registry._rules.update(saved)


@pytest.fixture
def mode(request, monkeypatch):
    """门禁模式：``gate_decision`` 读 settings，``gate_engine`` 的确认豁免读环境变量 —— 两处一起设（与生产同源）。"""
    from app.core.config import settings

    value = request.param
    monkeypatch.setattr(settings, "CONSISTENCY_GATE_ENFORCEMENT", value)
    monkeypatch.setenv("CONSISTENCY_GATE_ENFORCEMENT", value)
    return value


@pytest.fixture
def light_exporters(monkeypatch):
    """导出包里的报表 Excel / 附注 Word 生成换成小桩（判定发生在它们之前，与本条无关）。"""
    from app.services.note_word_exporter import NoteWordExporter
    from app.services.report_excel_exporter import ReportExcelExporter

    calls: list[str] = []

    async def _excel(self, **_kw):
        calls.append("excel")
        return BytesIO(b"xlsx")

    async def _word(self, **_kw):
        calls.append("word")
        return BytesIO(b"docx")

    monkeypatch.setattr(ReportExcelExporter, "export", _excel)
    monkeypatch.setattr(NoteWordExporter, "export", _word)
    return calls


# ─── 端点 ────────────────────────────────────────────────────────────────────


@contextmanager
def _client() -> Iterator[tuple[TestClient, Any, Any]]:
    from app.routers import chain_workflow, partner_dashboard, qc_dashboard

    api = build_app(partner_dashboard.router, qc_dashboard.router, chain_workflow.router)
    with TestClient(api) as client:
        with client.portal.wrap_async_context_manager(pg_tx_session()) as session:
            async def _db():
                yield session

            api.dependency_overrides[get_db] = _db
            yield client, session, api


async def _seed(session) -> dict[str, Any]:
    tag = uuid.uuid4().hex[:8]
    project = Project(name=f"{TEST_PROJECT_PREFIX}fh_r2_gate_{tag}", client_name=f"{TEST_PROJECT_PREFIX}一致性门禁端点",
                      audit_year=2025)
    admin = User(username=f"fh_r2_gate_admin_{tag}", email=f"fh_r2_gate_admin_{tag}@example.test",
                 hashed_password="x", role=UserRole.admin, is_active=True)
    session.add_all([project, admin])
    await session.flush()
    heping = (await session.execute(sa.select(Project.id).where(
        Project.name.like("%和平药房%"), Project.is_deleted == sa.false(), Project.audit_year == 2025))).scalars().all()
    assert len(heping) == 1, ("快照库应恰有一个和平药房 2025 项目（导出包「改造前口径拒绝」的真实数据）", heping)
    await session.commit()  # 只释放保存点；外层事务结束时回滚
    return {"empty": project.id, "heping": heping[0], "admin": admin}


def _login(client: TestClient, api, user: User) -> None:
    async def _user() -> User:
        return user

    api.dependency_overrides[get_current_user] = _user
    assert_world_overrides(api)
    assert_gates_are_production()


def _chain_findings(body: dict) -> list[tuple[dict, dict]]:
    return [(g, f) for g in body["groups"] for f in g["findings"] if f.get("rule_code") == RULE]


def _assert_no_raw_enum_text(body: dict) -> None:
    text = json.dumps(body, ensure_ascii=False)
    assert not any(raw in text for raw in RAW_ENUM_TEXT), [raw for raw in RAW_ENUM_TEXT if raw in text]


def _assert_chain_hint(body: dict, mode: str) -> tuple[dict, dict]:
    found = _chain_findings(body)
    assert len(found) == 1, (mode, "就绪响应里应恰有一条一致性门禁提示", found)
    [(group, hit)] = found
    assert (group["id"], group["name"]) == MISC, group
    pattern = OBSERVE_HINT if mode == "observe" else ENFORCE_HINT
    match = pattern.match(hit["message"])
    assert match, (mode, hit["message"])
    items = hit["location"]["items"]
    assert int(match.group(1)) == len(items) >= 1, (hit["message"], len(items))
    assert {i["status"] for i in items} <= {"failed", "not_executed", "error"}, items
    assert all(i["reason"] for i in items), "每个触发项都带原因"
    expected = ("warning", "请关注未通过的检查项") if mode == "observe" else ("blocking", "请补齐数据后重新检查")
    assert (hit["severity"], hit["action_hint"]) == expected, hit
    _assert_no_raw_enum_text(body)
    return group, hit


READINESS = {
    "sign_off": "/api/projects/{pid}/sign-readiness",
    "export_package": "/api/projects/{pid}/qc-dashboard/archive-readiness",
}


@pytest.mark.parametrize("mode", ["observe", "enforce"], indirect=True)
@pytest.mark.parametrize("gate", sorted(READINESS))
def test_readiness_endpoints_carry_consistency_hint(production_gate_registry, mode, gate):
    """签字就绪（sign_off）/ 归档就绪（export_package）经 gate_engine 触达已注册的规则：observe 给 warning 级提示
    「…（当前为只提示模式）」且 ready 与改造前（规则不在）相同；enforce 给 blocking 级「请补齐数据后重新检查」。
    全部门禁规则的 finding / gate_decision 都输出取值（响应里没有 ``GateSeverity.`` 等原文）。"""
    with _client() as (client, session, api):
        world = client.portal.call(_seed, session)
        _login(client, api, world["admin"])
        url = READINESS[gate].format(pid=world["empty"])
        resp = client.get(url)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        _assert_chain_hint(body, mode)
        if mode == "observe":
            with _rule_absent(production_gate_registry):
                before = client.get(url)
            assert before.status_code == 200, before.text
            assert _chain_findings(before.json()) == []
            assert body["ready"] == before.json()["ready"], "observe 下 ready 必须与改造前（规则不在）相同"


@contextmanager
def _only_consistency_rule(registry, monkeypatch) -> Iterator[None]:
    """就绪页只剩一致性规则这一个信号：两个门禁的规则表只留它，就绪服务的「门禁未覆盖的业务类目」换成空。"""
    from app.models.phase14_enums import GateType
    from app.services.partner_service import SignReadinessService
    from app.services.qc_dashboard_service import ArchiveReadinessService

    async def _none(self, project_id, proj):
        return {}

    monkeypatch.setattr(SignReadinessService, "_compute_sign_extra_findings", _none)
    monkeypatch.setattr(ArchiveReadinessService, "_compute_archive_extra_findings", _none)
    saved = {gate: list(rules) for gate, rules in registry._rules.items()}
    for gate in (GateType.sign_off, GateType.export_package):
        registry._rules[gate] = [r for r in registry._rules[gate] if r.rule_code == RULE]
        assert len(registry._rules[gate]) == 1, gate
    try:
        yield
    finally:
        registry._rules.clear()
        registry._rules.update(saved)


async def _stored_and_archive_gate(session, eval_id: str, pid, actor_id) -> tuple[dict, list[str]]:
    from app.services import archive_gate
    from app.services.gate_eval_store import get_gate_eval

    stored = await get_gate_eval(eval_id)
    assert stored is not None, eval_id
    return stored, await archive_gate.archive_gate_problems(session, pid, actor_id)


def _isolated(registry, monkeypatch, gate: str) -> tuple[dict, dict, list[str]]:
    with _client() as (client, session, api), _only_consistency_rule(registry, monkeypatch):
        world = client.portal.call(_seed, session)
        _login(client, api, world["admin"])
        resp = client.get(READINESS[gate].format(pid=world["empty"]))
        assert resp.status_code == 200, resp.text
        body = resp.json()
        stored, problems = client.portal.call(_stored_and_archive_gate, session, body["gate_eval_id"],
                                              world["empty"], world["admin"].id)
    return body, stored, problems


def _normalized(body: dict) -> dict:
    """快照只留与展示有关的字段：去掉评估 id / 过期时间 / 追踪 id 与 location（含项目 id），条数改成 N。"""
    keep = {k: body[k] for k in ("ready", "gate_decision", "passed_count", "total_checks") if k in body}
    if "ready_to_sign" in body:
        keep["ready_to_sign"] = body["ready_to_sign"]
    keep["groups"] = [{"id": g["id"], "name": g["name"], "status": g["status"], "findings": [
        {k: (re.sub(r"\d+ 项", "N 项", f[k]) if k == "message" else f[k])
         for k in ("rule_code", "error_code", "severity", "message", "action_hint")}
        for f in g["findings"]]} for g in body["groups"]]
    keep["checks"] = body["checks"]
    return keep


def _check_snapshot(name: str, data: dict) -> None:
    path = SNAP_DIR / f"{name}.json"
    text = json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True) + "\n"
    if os.environ.get("FHIC_UPDATE_SNAPSHOTS") == "1":
        path.write_text(text, encoding="utf-8", newline="\n")
    assert path.exists(), f"缺快照 {path}（FHIC_UPDATE_SNAPSHOTS=1 生成并人工核对；前端就绪页挂载用例读同一份）"
    assert json.loads(path.read_text(encoding="utf-8")) == json.loads(text), f"{name} 与快照不符"


@pytest.mark.parametrize("mode", ["observe", "enforce"], indirect=True)
@pytest.mark.parametrize("gate", sorted(READINESS))
def test_consistency_rule_as_the_only_signal(production_gate_registry, mode, gate, monkeypatch):
    """一致性规则是唯一信号时：observe ⇒ ready=true、分组「其他门禁规则」状态 warning、决策 warn，归档门禁不因它拦截；
    enforce ⇒ ready=false、分组 blocking、决策 block，存进 gate_eval 的 ready=false / decision=block，归档门禁拦截。"""
    body, stored, problems = _isolated(production_gate_registry, monkeypatch, gate)
    group, hit = _assert_chain_hint(body, mode)
    archive_problem = f"就绪检查｜{MISC[1]}｜{hit['message']}"
    if mode == "observe":
        assert (body["ready"], body["gate_decision"], group["status"]) == (True, "warn", "warning"), body
        assert (stored["ready"], stored["decision"]) == (True, "warn"), stored
        assert archive_problem not in problems, problems
    else:
        assert (body["ready"], body["gate_decision"], group["status"]) == (False, "block", "blocking"), body
        assert (stored["ready"], stored["decision"]) == (False, "block"), stored
        assert archive_problem in problems, problems
    _check_snapshot(f"readiness_{gate}_{mode}", _normalized(body))


@pytest.mark.parametrize("mode", ["observe", "enforce"], indirect=True)
def test_export_package_decision_by_mode(production_gate_registry, mode, light_exporters):
    """导出包服务：空项目只有阻断级「未执行」——observe 按改造前口径放行（只看阻断级「失败」），enforce 拒绝并
    提示「请补齐数据后重新检查」；和平药房有阻断级「失败」——observe 照改造前口径与原文拒绝，enforce 同样拒绝。"""
    with _client() as (client, session, api):
        world = client.portal.call(_seed, session)
        _login(client, api, world["admin"])
        empty = client.post(f"/api/projects/{world['empty']}/workflow/export-package", json={"year": 2025})
        heping = client.post(f"/api/projects/{world['heping']}/workflow/export-package", json={"year": 2025})
    if mode == "observe":
        assert empty.status_code == 200, empty.text[:500]
        assert empty.headers["content-type"].startswith("application/zip"), empty.headers
        assert light_exporters == ["excel", "word"], light_exporters
        assert heping.status_code == 400, heping.text[:500]
        assert heping.json()["detail"]["message"] == PRE_CHANGE_REFUSAL, heping.text[:500]
    else:
        for resp in (empty, heping):
            assert resp.status_code == 400, resp.text[:500]
            assert ENFORCE_HINT.match(resp.json()["detail"]["message"]), resp.text[:500]
        assert light_exporters == [], "拒绝发生在生成文件之前"
    assert all({"check_name", "passed", "severity"} <= set(c) for c in heping.json()["detail"]["checks"])
