"""S2 任务4（ADR-CCN-07）：门禁规则异常分支 ⇒ 命中（不放行）。

对改写的 27 处通用异常分支逐个注入数据库异常，断言：
- 结果不为 None，且为 `not_executed` 类命中（location.via == "not_executed"）；
- observe（默认）严重度 warning，enforce 下为 blocking（design D2）；
- 结构性不适用（QC-25 / QC-26 在表或列不存在时）为 `not_applicable`，任何模式都是 warning；
- 一致性引擎：报表→附注 / 附注→底稿 / 底稿→试算表三层返回 not_executed（不再冒充一致），
  第 1 层数据库异常时也返回 not_executed。
"""
from __future__ import annotations

import importlib
import uuid
from unittest.mock import AsyncMock

import pytest

from app.models.phase14_enums import GateSeverity
from app.services.consistency_replay_engine import ConsistencyReplayEngine

_INJECT_MSG = "注入：数据库不可用"

#: 改写的 27 处通用异常分支（模块, 规则类）。与 AST 现算结果一致（tmp_check_contract/baseline/）；AI 专属 fail-closed 分支另有专项测试。
_EXCEPTION_SITES: list[tuple[str, str]] = [
    ("app.services.gate_rules_b60", "B60AttachmentMatrixRule"),
    ("app.services.gate_rules_b60", "B60MaterialityRefRule"),
    ("app.services.gate_rules_b60", "B60dVersionConsistencyRule"),
    ("app.services.gate_rules_chain", "AllReportsGeneratedRule"),
    ("app.services.gate_rules_chain", "AllNotesGeneratedRule"),
    ("app.services.gate_rules_chain", "ConsistencyPassedRule"),
    ("app.services.gate_rules_cross_module_conflict", "CrossModuleConflictUnresolvedRule"),
    ("app.services.gate_rules_eqcr", "EqcrDomainCoverageRule"),
    ("app.services.gate_rules_eqcr", "EqcrNoUnresolvedDisagreementRule"),
    ("app.services.gate_rules_phase14", "QC19MandatoryTrimRule"),
    ("app.services.gate_rules_phase14", "QC20ConditionalNoEvidenceRule"),
    ("app.services.gate_rules_phase14", "QC21ConclusionWithoutEvidenceRule"),
    ("app.services.gate_rules_phase14", "QC22LowConfidenceSingleSourceRule"),
    ("app.services.gate_rules_phase14", "QC23LLMPendingConfirmationRule"),
    ("app.services.gate_rules_phase14", "QC24LLMTrimConflictRule"),
    ("app.services.gate_rules_phase14", "QC25ReportNoteVersionStaleRule"),
    ("app.services.gate_rules_phase14", "QC26NoteSourceMappingMissingRule"),
    ("app.services.gate_rules_phase14", "ConsistencyBlockingDiffRule"),
    ("app.services.gate_rules_phase14", "MisstatementExceedsMaterialityRule"),
    ("app.services.gate_rules_phase14", "UnconvertedRejectedAJERule"),
    ("app.services.gate_rules_phase14", "EventCascadeHealthRule"),
    ("app.services.gate_rules_phase14", "IndependenceDeclarationCompleteRule"),
    ("app.services.gate_rules_round6", "KamConfirmedRule"),
    ("app.services.gate_rules_round6", "IndependenceConfirmedRule"),
    ("app.services.gate_rules_round6", "SubsequentEventsReviewedRule"),
    ("app.services.gate_rules_round6", "GoingConcernEvaluatedRule"),
    ("app.services.gate_rules_round6", "MgmtRepresentationRule"),
]


class _InjectedCM:
    async def __aenter__(self):
        raise RuntimeError(_INJECT_MSG)

    async def __aexit__(self, *exc):
        return False


class _BoomDB:
    """任何数据库访问都抛错：模拟数据库不可用。"""

    def begin_nested(self):
        return _InjectedCM()

    def __getattr__(self, name):
        # 同步抛错：`await db.execute(...)` 与 `db.add(...)` 都在调用时抛出，不会留下未 await 的协程
        def _boom(*_a, **_k):
            raise RuntimeError(f"{_INJECT_MSG}（{name}）")

        return _boom


class _EmptyResult:
    def scalar(self):
        return None

    def scalar_one_or_none(self):
        return None

    def scalars(self):
        return self

    def all(self):
        return []

    def fetchall(self):
        return []

    def fetchone(self):
        return None

    def first(self):
        return None


class _EmptyDB:
    """表 / 列都查不到、数据为空的数据库：模拟结构性不适用（表不存在、本项目没有数据）。"""

    async def execute(self, *_a, **_k):
        return _EmptyResult()


#: 年度查询在 try 之外的规则：先给一个确定的审计年度，让注入的异常落在规则自己的 except 里。
_NEEDS_AUDIT_YEAR = {
    "AllReportsGeneratedRule",
    "AllNotesGeneratedRule",
    "ConsistencyPassedRule",
}


def _rule(module: str, cls: str):
    return getattr(importlib.import_module(module), cls)()


def _prepare(site: tuple[str, str], monkeypatch) -> None:
    if site[1] in _NEEDS_AUDIT_YEAR:
        monkeypatch.setattr(
            "app.services.project_audit_year.fetch_project_audit_year",
            AsyncMock(return_value=2025),
        )
    if site[1] == "ConsistencyPassedRule":
        monkeypatch.setattr(
            "app.services.consistency_gate.ConsistencyGate.run_all_checks",
            AsyncMock(side_effect=RuntimeError(_INJECT_MSG)),
        )


def _ctx() -> dict:
    return {
        "project_id": uuid.uuid4(),
        "wp_id": uuid.uuid4(),
        "actor_id": uuid.uuid4(),
        "gate_type": "sign_off",
        "year": 2025,
    }


def _site_id(site: tuple[str, str]) -> str:
    return site[1]


@pytest.mark.asyncio
@pytest.mark.parametrize("site", _EXCEPTION_SITES, ids=_site_id)
async def test_exception_returns_not_executed_hit_observe(site, monkeypatch):
    """注入异常 ⇒ 不为 None、为 not_executed 命中；observe 下 warning（不放行、不阻断）。"""
    monkeypatch.delenv("CONSISTENCY_GATE_ENFORCEMENT", raising=False)
    _prepare(site, monkeypatch)
    rule = _rule(*site)
    hit = await rule.check(_BoomDB(), _ctx())
    assert hit is not None, f"{site[1]} 异常时仍放行（返回 None）"
    assert hit.location.get("via") == "not_executed", hit.location
    assert hit.severity == GateSeverity.warning, hit.severity
    # 异常分支统一文案「检查异常，未执行」；一致性复算的层级错误文案为「…未能执行」，两者都要带原因
    assert ("检查异常，未执行" in hit.message) or ("未能执行" in hit.message), hit.message
    assert _INJECT_MSG in hit.message


@pytest.mark.asyncio
@pytest.mark.parametrize("site", _EXCEPTION_SITES, ids=_site_id)
async def test_exception_returns_blocking_under_enforce(site, monkeypatch):
    """enforce 下 not_executed 升为 blocking（design D2：可逐项确认，见 gate_acknowledgement）。"""
    monkeypatch.setenv("CONSISTENCY_GATE_ENFORCEMENT", "enforce")
    _prepare(site, monkeypatch)
    rule = _rule(*site)
    hit = await rule.check(_BoomDB(), _ctx())
    assert hit is not None and hit.location.get("via") == "not_executed"
    assert hit.severity == GateSeverity.blocking


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "site",
    [
        ("app.services.gate_rules_phase14", "QC25ReportNoteVersionStaleRule"),
        ("app.services.gate_rules_phase14", "QC26NoteSourceMappingMissingRule"),
    ],
    ids=["QC-25-table-absent", "QC-26-columns-absent"],
)
async def test_structural_absence_is_not_applicable(site, monkeypatch):
    """表或列不存在 ⇒ not_applicable：warning，且 enforce 下也不阻断。"""
    monkeypatch.delenv("CONSISTENCY_GATE_ENFORCEMENT", raising=False)
    rule = _rule(*site)
    hit = await rule.check(_EmptyDB(), _ctx())
    assert hit is not None
    assert hit.location.get("via") == "not_applicable", hit.location
    assert hit.severity == GateSeverity.warning
    monkeypatch.setenv("CONSISTENCY_GATE_ENFORCEMENT", "enforce")
    hit_enforce = await rule.check(_EmptyDB(), _ctx())
    assert hit_enforce.severity == GateSeverity.warning


def test_not_executed_and_not_applicable_helpers_build_hits():
    from app.services.gate_rules_round6 import KamConfirmedRule

    rule = KamConfirmedRule()
    na = rule.not_applicable("结构性不适用")
    ne = rule.not_executed("检查异常")
    assert (na.rule_code, na.error_code, na.message) == (rule.rule_code, rule.error_code, "结构性不适用")
    assert na.location == {"via": "not_applicable"}
    assert ne.location == {"via": "not_executed"}


@pytest.mark.asyncio
async def test_replay_layer1_database_error_is_not_executed():
    """第 1 层数据库异常 ⇒ not_executed（原先 debug 日志后返回「一致」的空层）。"""
    engine = ConsistencyReplayEngine()
    layer = await engine._check_layer1(_BoomDB(), uuid.uuid4(), 2025)
    assert layer.status == "not_executed"
    assert layer.reason.startswith("层1 未能执行")
    assert layer.diffs == []


@pytest.mark.asyncio
async def test_replay_layers_3_4_5_return_not_executed():
    """空实现层不再以「一致」的空层冒充通过。"""
    engine = ConsistencyReplayEngine()
    pid = uuid.uuid4()
    layers = [
        await engine._check_layer3(None, pid, 2025),
        await engine._check_layer4(None, pid, 2025),
        await engine._check_layer5(None, pid, 2025),
    ]
    assert [layer.status for layer in layers] == ["not_executed"] * 3
    assert all(layer.reason for layer in layers)


class _FakeSavepoint:
    async def commit(self):
        return None

    async def rollback(self):
        return None


class _FakeSession:
    """GateEngine.evaluate 用到的最小会话：savepoint、add、flush。"""

    async def begin_nested(self):
        return _FakeSavepoint()

    def add(self, _obj):
        return None

    async def flush(self):
        return None


@pytest.mark.asyncio
async def test_engine_turns_rule_exception_into_not_executed_hit(monkeypatch):
    """规则 check() 抛出的异常不被引擎静默丢弃：记为 not_executed 命中，决策不为 allow。"""
    from app.models.phase14_enums import GateDecisionResult, GateType
    from app.services.gate_engine import GateEngine, GateRule, RuleRegistry

    monkeypatch.delenv("CONSISTENCY_GATE_ENFORCEMENT", raising=False)

    class _Raising(GateRule):
        rule_code = "TEST-RAISE"
        error_code = "TEST_RAISE"

        async def check(self, db, context):
            raise RuntimeError(_INJECT_MSG)

    registry = RuleRegistry()
    registry.register(GateType.sign_off, _Raising())
    result = await GateEngine(registry).evaluate(
        _FakeSession(), GateType.sign_off, uuid.uuid4(), None, uuid.uuid4(), {"year": 2025}
    )
    assert len(result.hit_rules) == 1
    hit = result.hit_rules[0]
    assert hit.rule_code == "TEST-RAISE"
    assert hit.location.get("via") == "not_executed"
    assert hit.severity == GateSeverity.warning
    assert result.decision != GateDecisionResult.allow
