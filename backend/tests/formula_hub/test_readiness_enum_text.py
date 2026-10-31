"""就绪页按门禁枚举的取值判定与输出（第 2 轮 S1；需求 16.4 / 16.5 的就绪页一侧）。

缺陷：``GateSeverity`` / ``GateDecisionResult`` 是 ``(str, Enum)``，``str(GateSeverity.blocking)`` 得
``'GateSeverity.blocking'``。readiness_facade（finding 严重级、gate_decision）、partner_service 与
qc_dashboard_service（ready 与存进 gate_eval 的 decision）都拿这个文本去比 ``'blocking'`` / ``'block'`` ⇒ 恒假：
阻断命中不让 ready 变 false、分组状态停在「通过」、界面严重级标签显示原文。既有 ``test_readiness_facade.py``
的替身用普通字符串（``severity="warning"``），看不到生产里的枚举。

本文件用生产类型（枚举成员）的门禁结果驱动两个就绪服务（SQLite；只替换 ``gate_engine.evaluate`` 与「门禁未覆盖的
业务类目」——后者在空项目上本身就是 blocking，会让 ready 与门禁命中无关地恒为 false）：
- 决策只是「提示」但有一条阻断级命中：按命中判未就绪（readiness_facade 文档化的合同「任一类目含 blocking ⇒ ready=False」），
  存进 gate_eval 的 ready 也为 false —— 杀掉「severity 比较改回 str()」的变异（决策为 block 时它被决策条件掩盖）；
- 决策为 block：响应与存储的 decision 都是 ``'block'``；
- 输出里不出现 ``GateSeverity.`` / ``GateDecisionResult.`` 原文，分组状态与严重级是 ``warning`` / ``blocking``。
"""
from __future__ import annotations

import json
import uuid

import pytest
import pytest_asyncio
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.models.phase14_models  # noqa: F401 —— create_all 建门禁相关表
import app.models.phase15_models  # noqa: F401
from app.models.base import Base
from app.models.core import Project, ProjectStatus, ProjectType
from app.models.phase14_enums import GateDecisionResult, GateSeverity
from app.services.gate_engine import GateEvaluateResult, GateRuleHit
from app.services.readiness_facade import build_readiness_response, enum_text

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
RULE = "CHAIN-CONSISTENCY"
RAW = ("GateSeverity.", "GateDecisionResult.")


def _hit(severity: GateSeverity) -> GateRuleHit:
    return GateRuleHit(rule_code=RULE, error_code="CONSISTENCY_CHECK_FAILED", severity=severity,
                       message="一致性检查有 3 项未通过或未执行（当前为只提示模式）", location={"items": []},
                       suggested_action="请关注未通过的检查项")


@pytest_asyncio.fixture
async def db() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)() as session:
        yield session
    await engine.dispose()


@pytest_asyncio.fixture
async def project_id(db) -> uuid.UUID:
    pid = uuid.uuid4()
    db.add(Project(id=pid, name="【测试】fh_r2_enum_text", client_name="【测试】", project_type=ProjectType.annual,
                   status=ProjectStatus.planning, created_by=uuid.uuid4(), wizard_state={}, audit_year=2025))
    await db.commit()
    return pid


@pytest.fixture
def gate(monkeypatch):
    """``gate_engine.evaluate`` 换成可控结果（生产类型：枚举成员）；就绪服务的补充类目换成空；gate_eval 走本地存储。"""
    from app.services import gate_engine as ge_module
    from app.services import gate_eval_store as ges
    from app.services.partner_service import SignReadinessService
    from app.services.qc_dashboard_service import ArchiveReadinessService

    class _Stub:
        decision = GateDecisionResult.allow
        hit_rules: list[GateRuleHit] = []

        async def evaluate(self, db, gate_type, project_id, wp_id, actor_id, context):
            return GateEvaluateResult(decision=self.decision, hit_rules=list(self.hit_rules), trace_id="trc_s1")

    async def _none(self, project_id, proj):
        return {}

    async def _no_redis():
        return None

    stub = _Stub()
    monkeypatch.setattr(ge_module, "gate_engine", stub)
    monkeypatch.setattr(SignReadinessService, "_compute_sign_extra_findings", _none)
    monkeypatch.setattr(ArchiveReadinessService, "_compute_archive_extra_findings", _none)
    monkeypatch.setattr(ges, "_get_redis_client", _no_redis)
    ges._reset_local_for_tests()
    yield stub
    ges._reset_local_for_tests()


async def _readiness(kind: str, db, pid):
    from app.services.gate_eval_store import get_gate_eval
    from app.services.partner_service import SignReadinessService
    from app.services.qc_dashboard_service import ArchiveReadinessService

    if kind == "sign_off":
        body = await SignReadinessService(db).check_sign_readiness(pid, actor_id=uuid.uuid4())
    else:
        body = await ArchiveReadinessService(db).check_readiness(pid, actor_id=uuid.uuid4())
    stored = await get_gate_eval(body["gate_eval_id"])
    assert stored is not None
    return body, stored


def _chain(body: dict) -> tuple[dict, dict]:
    [(group, finding)] = [(g, f) for g in body["groups"] for f in g["findings"] if f["rule_code"] == RULE]
    return group, finding


def test_enum_text_reads_value_and_keeps_plain_strings():
    assert enum_text(GateSeverity.blocking) == "blocking" and enum_text(GateDecisionResult.block) == "block"
    assert str(GateSeverity.blocking) == "GateSeverity.blocking", "前提：(str, Enum) 的 str() 是「类名.成员」"
    assert enum_text("warning") == "warning" and enum_text(None, "info") == "info"


def test_facade_outputs_values_and_groups_by_them():
    body = build_readiness_response(
        gate_type="sign_off", gate_result=GateEvaluateResult(decision=GateDecisionResult.warn,
                                                             hit_rules=[_hit(GateSeverity.warning)], trace_id="t"),
        extra_findings={}, gate_eval_id="e", expires_at_iso="x")
    group, finding = _chain(body)
    assert (group["id"], group["name"], group["status"], finding["severity"]) == ("misc", "其他门禁规则", "warning",
                                                                                 "warning")
    assert (body["gate_decision"], body["ready"]) == ("warn", True)
    assert not any(raw in json.dumps(body, ensure_ascii=False) for raw in RAW)


@pytest.mark.parametrize("kind", ["sign_off", "export_package"])
async def test_blocking_hit_makes_not_ready_even_if_decision_only_warns(db, project_id, gate, kind):
    gate.decision, gate.hit_rules = GateDecisionResult.warn, [_hit(GateSeverity.blocking)]
    body, stored = await _readiness(kind, db, project_id)
    group, finding = _chain(body)
    assert (group["status"], finding["severity"]) == ("blocking", "blocking")
    assert body["ready"] is False, "任一类目含 blocking ⇒ 未就绪"
    assert (stored["ready"], stored["decision"]) == (False, "warn"), stored
    assert not any(raw in json.dumps(body, ensure_ascii=False) for raw in RAW)


@pytest.mark.parametrize("kind", ["sign_off", "export_package"])
async def test_block_decision_is_stored_and_returned_as_value(db, project_id, gate, kind):
    gate.decision, gate.hit_rules = GateDecisionResult.block, [_hit(GateSeverity.blocking)]
    body, stored = await _readiness(kind, db, project_id)
    assert (body["gate_decision"], body["ready"]) == ("block", False)
    assert (stored["decision"], stored["ready"]) == ("block", False), stored


@pytest.mark.parametrize("kind", ["sign_off", "export_package"])
async def test_warning_hit_keeps_ready(db, project_id, gate, kind):
    gate.decision, gate.hit_rules = GateDecisionResult.warn, [_hit(GateSeverity.warning)]
    body, stored = await _readiness(kind, db, project_id)
    group, finding = _chain(body)
    assert (group["status"], finding["severity"], body["ready"]) == ("warning", "warning", True)
    assert (stored["ready"], stored["decision"]) == (True, "warn"), stored
