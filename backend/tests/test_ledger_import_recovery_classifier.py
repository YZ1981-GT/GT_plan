"""
test_ledger_import_recovery_classifier.py

账套导入恢复判定：`activation_only` / `resume_finish` / `rebuild`
（spec platform-global-display-settings-closure 任务 8 / design §5）。

判据：
1. **无 attempt ⇒ rebuild**（旧 job / attempt 从未创建）。
2. **activated ⇒ resume_finish**（只补收尾，不碰数据）。
3. **sealed + 五项全一致 ⇒ activation_only**；缺任一项 ⇒ rebuild。
4. **activating / building / cleanup_pending ⇒ rebuild**（activating 已动过 active，
   重复激活不安全）。
5. **attempt 定位优先用 job.options.attempt_id**（并发提交时按 project+year
   反查会取到别人的 attempt）。
6. `assert_rebuild_cleanup_needed` 的幂等与边界。
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from app.services.ledger_import.recovery_classifier import (
    RecoveryDecision,
    assert_rebuild_cleanup_needed,
    decide_recovery,
)
from app.services.ledger_import.attempt_service import BaseToken, SealEvidence


# ── 假 db：只支持本模块用到的两种 execute 形态 ─────────────

class _Scalars:
    def __init__(self, value):
        self._value = value

    def first(self):
        return self._value


class _ExecResult:
    def __init__(self, value):
        self._value = value

    def scalars(self):
        return _Scalars(self._value)


class _FakeDb:
    """按调用顺序返回预置 attempt（`decide_recovery` 的两次查询）。"""

    def __init__(self, attempts: list):
        self._attempts = list(attempts)
        self._idx = 0

    async def execute(self, _stmt):
        if self._idx < len(self._attempts):
            value = self._attempts[self._idx]
            self._idx += 1
            return _ExecResult(value)
        return _ExecResult(None)


def _attempt(**overrides):
    base = dict(
        id=uuid.uuid4(),
        status="building",
        dataset_id=None,
        base_dataset_id=None,
        base_unit_contract_digest=None,
        unit_contract_digest=None,
        bundle_digest=None,
        unit_confirmation={},
        current_phase=None,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


@pytest.fixture(autouse=True)
def _stub_base_token(monkeypatch):
    """把 `resolve_base_token` 换成可控返回值（避免碰真库）。"""
    from app.services.ledger_import import base_token_resolver

    async def _fake(db, *, project_id, year):
        return BaseToken(None, None)

    monkeypatch.setattr(base_token_resolver, "resolve_base_token", _fake)


# ── 1. 无 attempt ────────────────────────────────────────

@pytest.mark.asyncio
async def test_no_attempt_means_rebuild() -> None:
    db = _FakeDb([None, None])  # options 里没 id → 跳过首次查询；反查也 None
    decision = await decide_recovery(
        db, project_id=uuid.uuid4(), year=2025, job_options=None
    )
    assert decision.action == "rebuild"
    assert decision.attempt_id is None
    assert "没有 attempt" in decision.reason


# ── 2. activated ⇒ resume_finish ─────────────────────────

@pytest.mark.asyncio
async def test_activated_means_resume_finish() -> None:
    att = _attempt(status="activated", dataset_id=uuid.uuid4())
    db = _FakeDb([att])
    decision = await decide_recovery(
        db, project_id=uuid.uuid4(), year=2025,
        job_options={"attempt_id": str(att.id)},
    )
    assert decision.action == "resume_finish"
    assert decision.attempt_id == att.id
    assert "只补收尾" in decision.reason


# ── 3. sealed 的两个分支 ─────────────────────────────────

def _sealed(**overrides):
    common = dict(
        status="sealed",
        base_dataset_id=None,
        base_unit_contract_digest=None,
        unit_contract_digest="a" * 64,
        bundle_digest="b" * 64,
        unit_confirmation={"row_counts": {"tb_balance": 10}, "post_hash": "c" * 64},
    )
    common.update(overrides)
    return _attempt(**common)


@pytest.mark.asyncio
async def test_sealed_all_match_means_activation_only() -> None:
    att = _sealed(dataset_id=uuid.uuid4())
    db = _FakeDb([att])
    decision = await decide_recovery(
        db, project_id=uuid.uuid4(), year=2025,
        job_options={"attempt_id": str(att.id)},
    )
    assert decision.action == "activation_only"
    assert decision.staged_dataset_id == att.dataset_id
    assert "不重跑 converter" in decision.reason


@pytest.mark.asyncio
async def test_sealed_but_contract_mismatch_means_rebuild(monkeypatch) -> None:
    """contract digest 不一致 ⇒ rebuild（不能激活半成品）。"""
    att = _sealed()

    async def _tok(db, *, project_id, year):
        return BaseToken(None, "z" * 64)  # 与 attempt 的 "a"*64 不同

    from app.services.ledger_import import base_token_resolver
    monkeypatch.setattr(base_token_resolver, "resolve_base_token", _tok)

    db = _FakeDb([att])
    decision = await decide_recovery(
        db, project_id=uuid.uuid4(), year=2025,
        job_options={"attempt_id": str(att.id)},
    )
    assert decision.action == "rebuild"
    assert "证据不一致" in decision.reason


# ── 4. 其他状态一律 rebuild ──────────────────────────────

@pytest.mark.parametrize("status", [
    "building", "activating", "cleanup_pending", "cleanup_done",
])
@pytest.mark.asyncio
async def test_other_states_mean_rebuild(status: str) -> None:
    att = _attempt(status=status, dataset_id=uuid.uuid4())
    db = _FakeDb([att])
    decision = await decide_recovery(
        db, project_id=uuid.uuid4(), year=2025,
        job_options={"attempt_id": str(att.id)},
    )
    assert decision.action == "rebuild"
    assert status in decision.reason


@pytest.mark.asyncio
async def test_activating_reason_mentions_double_activation_risk() -> None:
    att = _attempt(status="activating", dataset_id=uuid.uuid4())
    db = _FakeDb([att])
    decision = await decide_recovery(
        db, project_id=uuid.uuid4(), year=2025,
        job_options={"attempt_id": str(att.id)},
    )
    assert "重复激活" in decision.reason or "动过 active" in decision.reason


# ── 5. attempt 定位优先 job.options ──────────────────────

@pytest.mark.asyncio
async def test_prefers_job_options_attempt_id() -> None:
    """有 options.attempt_id 时**只**查它，不按 project+year 反查。"""
    att = _attempt(status="activated", dataset_id=uuid.uuid4())
    db = _FakeDb([att])
    decision = await decide_recovery(
        db, project_id=uuid.uuid4(), year=2025,
        job_options={"attempt_id": str(att.id)},
    )
    assert decision.action == "resume_finish"
    assert "job.options.attempt_id" in decision.reason
    # 只消费了第一个预置值（未反查）
    assert db._idx == 1


@pytest.mark.asyncio
async def test_falls_back_to_latest_when_no_option() -> None:
    att = _attempt(status="activated", dataset_id=uuid.uuid4())
    db = _FakeDb([att])
    decision = await decide_recovery(
        db, project_id=uuid.uuid4(), year=2025, job_options={}
    )
    assert decision.action == "resume_finish"
    assert "latest_by_project_year" in decision.reason


@pytest.mark.asyncio
async def test_bad_attempt_id_in_options_falls_back() -> None:
    """非法 attempt_id 字符串不得抛，应回退到反查。"""
    att = _attempt(status="activated", dataset_id=uuid.uuid4())
    db = _FakeDb([att])
    decision = await decide_recovery(
        db, project_id=uuid.uuid4(), year=2025,
        job_options={"attempt_id": "not-a-uuid"},
    )
    assert decision.action == "resume_finish"
    assert "latest_by_project_year" in decision.reason


# ── 6. assert_rebuild_cleanup_needed ─────────────────────

@pytest.mark.asyncio
async def test_cleanup_not_needed_without_attempt() -> None:
    assert await assert_rebuild_cleanup_needed(_FakeDb([None]), attempt_id=None) is False


@pytest.mark.asyncio
async def test_cleanup_not_needed_when_cleanup_done() -> None:
    att = _attempt(status="cleanup_done", dataset_id=uuid.uuid4())
    assert await assert_rebuild_cleanup_needed(_FakeDb([att]), attempt_id=att.id) is False


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["building", "activating", "cleanup_pending"])
async def test_cleanup_needed_for_in_flight_states(status: str) -> None:
    att = _attempt(status=status, dataset_id=uuid.uuid4())
    assert await assert_rebuild_cleanup_needed(_FakeDb([att]), attempt_id=att.id) is True


@pytest.mark.asyncio
async def test_cleanup_needed_when_dataset_present_even_if_activated() -> None:
    """`activated` 但有 dataset_id ⇒ 有 stage 残留，仍需清。"""
    att = _attempt(status="activated", dataset_id=uuid.uuid4())
    assert await assert_rebuild_cleanup_needed(_FakeDb([att]), attempt_id=att.id) is True


@pytest.mark.asyncio
async def test_cleanup_idempotent_missing_attempt() -> None:
    """attempt 查不到 ⇒ False（幂等，不抛）。"""
    assert await assert_rebuild_cleanup_needed(_FakeDb([None]), attempt_id=uuid.uuid4()) is False


# ── 7. RecoveryDecision 是不可变数据 ─────────────────────

def test_decision_is_frozen() -> None:
    d = RecoveryDecision(action="rebuild", attempt_id=None, reason="x")
    with pytest.raises(Exception):
        d.action = "activation_only"  # type: ignore[misc]


# ── 8. recover_jobs 接线（AST 判据）──────────────────────


class TestRecoverJobsWiring:
    """分类器必须真的接进 `recover_jobs`，且不再用 `current_phase` 授权。"""

    def _src(self) -> str:
        from pathlib import Path

        p = Path(__file__).resolve().parents[1] / "app" / "services" / "import_job_runner.py"
        return p.read_text(encoding="utf-8")

    def test_recover_jobs_calls_decide_recovery(self) -> None:
        import ast
        from pathlib import Path

        p = Path(__file__).resolve().parents[1] / "app" / "services" / "import_job_runner.py"
        tree = ast.parse(p.read_text(encoding="utf-8"))
        names: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                f = node.func
                names.add(f.id if isinstance(f, ast.Name) else getattr(f, "attr", ""))
        assert "decide_recovery" in names, (
            "recover_jobs 未调用 decide_recovery；分类器成了死代码"
        )

    def test_no_longer_uses_current_phase_to_authorize_resume(self) -> None:
        """旧判据 `if ij.current_phase:` 必须已被替换。

        🔴 design §5：`current_phase` 仅作进度显示，不能授权复用 staged 行。
        变异实证过的风险：以它为准会在旧 stage 上重跑 normalizer，
        产出「混合两批数据」的静默错误（导入显示成功、数据是错的）。
        """
        src = self._src()
        assert "if ij.current_phase:" not in src, (
            "recover_jobs 仍在用 `current_phase` 授权恢复；"
            "应改为 attempt 判定（decide_recovery）"
        )

    @pytest.mark.parametrize("action", ["activation_only", "resume_finish", "rebuild"])
    def test_all_three_actions_handled_in_messages(self, action: str) -> None:
        """三种结论都必须有对应的进度文案分支（不能被静默吞成一种）。"""
        src = self._src()
        assert f'"{action}"' in src, f"recover_jobs 未处理结论 {action}"

    def test_decision_failure_falls_back_not_blocks(self) -> None:
        """判定异常必须回退旧口径，不能阻断恢复。"""
        src = self._src()
        assert "恢复判定失败" in src
        assert "回退" in src
