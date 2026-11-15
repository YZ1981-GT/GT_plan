"""
test_ledger_import_attempt_service.py

账套导入 attempt 生命周期与三次 base token CAS
（spec platform-global-display-settings-closure 任务 8 / AC-15~AC-17）。

判据：
1. **状态机**：只允许 `ALLOWED_TRANSITIONS` 的边，其余一律拒。
2. **base token 双向**：attempt 记的与当前不同 ⇒ 拒；attempt 为 None 而当前有 active ⇒ 也拒。
3. **activation-only 五条件**：缺一即 False（不能激活半成品）。
4. **current_phase 不参与判定**：改它不影响任何结果。
5. **base token 不含 dataset version**：加 version 会让合法重算被判漂移。
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from app.services.ledger_import.attempt_service import (
    ALLOWED_TRANSITIONS,
    DISPLAY_PHASES,
    AttemptStateError,
    BaseToken,
    BaseTokenDriftError,
    SealEvidence,
    assert_base_token,
    assert_transition,
    can_activation_only,
)


# ── 1. 状态机 ────────────────────────────────────────────

class TestStateMachine:
    @pytest.mark.parametrize("src,dst", [
        ("building", "sealed"),
        ("building", "cleanup_pending"),
        ("sealed", "activating"),
        ("sealed", "cleanup_pending"),
        ("activating", "activated"),
        ("activating", "cleanup_pending"),
        ("activated", "cleanup_pending"),
        ("cleanup_pending", "cleanup_done"),
    ])
    def test_allowed_edges(self, src: str, dst: str) -> None:
        assert_transition(src, dst)  # 不抛

    @pytest.mark.parametrize("src,dst", [
        ("building", "activating"),      # 跳过 seal
        ("building", "activated"),       # 跳过 seal + activation
        ("sealed", "building"),          # 回退
        ("activated", "activating"),     # 回退
        ("cleanup_done", "cleanup_pending"),  # 已终结
        ("cleanup_done", "activated"),
    ])
    def test_forbidden_edges(self, src: str, dst: str) -> None:
        with pytest.raises(AttemptStateError, match="非法状态流转"):
            assert_transition(src, dst)

    def test_unknown_status_rejected(self) -> None:
        with pytest.raises(AttemptStateError, match="未知的 attempt 状态"):
            assert_transition("bogus", "sealed")

    def test_cleanup_done_is_terminal(self) -> None:
        assert ALLOWED_TRANSITIONS["cleanup_done"] == frozenset()


# ── 2. base token 双向校验 ────────────────────────────────

def _attempt(**overrides):
    defaults = dict(
        status="building",
        base_dataset_id=None,
        base_unit_contract_digest=None,
        unit_contract_digest=None,
        bundle_digest=None,
        unit_confirmation={},
        current_phase="bundle_stored",
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


class TestBaseToken:
    def test_same_token_passes(self) -> None:
        ds = uuid.uuid4()
        att = _attempt(base_dataset_id=ds, base_unit_contract_digest="a" * 64)
        assert_base_token(att, BaseToken(ds, "a" * 64))  # 不抛

    def test_dataset_drift_rejected(self) -> None:
        att = _attempt(base_dataset_id=uuid.uuid4(), base_unit_contract_digest="a" * 64)
        with pytest.raises(BaseTokenDriftError, match="base token 已漂移"):
            assert_base_token(att, BaseToken(uuid.uuid4(), "a" * 64))

    def test_contract_drift_rejected(self) -> None:
        ds = uuid.uuid4()
        att = _attempt(base_dataset_id=ds, base_unit_contract_digest="a" * 64)
        with pytest.raises(BaseTokenDriftError):
            assert_base_token(att, BaseToken(ds, "b" * 64))

    def test_attempt_none_but_current_has_active_rejected(self) -> None:
        """attempt 建在「首次无 active」时期，现在有 active ⇒ 必须拒。

        🔴 反方向也要判：只判「attempt 有值时才比较」会让这种漂移静默通过，
        结果把基于空 base 算的金额激活成新 active。
        """
        att = _attempt(base_dataset_id=None, base_unit_contract_digest=None)
        with pytest.raises(BaseTokenDriftError):
            assert_base_token(att, BaseToken(uuid.uuid4(), "a" * 64))

    def test_both_none_passes(self) -> None:
        """首次导入（两边都无 active）是合法状态。"""
        att = _attempt(base_dataset_id=None, base_unit_contract_digest=None)
        assert_base_token(att, BaseToken(None, None))

    def test_token_has_no_dataset_version(self) -> None:
        """design §13 第 7 条：base token 只含 dataset UUID + contract digest。"""
        fields = BaseToken.__dataclass_fields__
        assert set(fields) == {"dataset_id", "unit_contract_digest"}, (
            f"base token 字段变了：{sorted(fields)}；不得加 dataset version"
        )

    def test_describe_is_readable(self) -> None:
        t = BaseToken(uuid.UUID(int=1), "a" * 64)
        desc = t.describe()
        assert "dataset=" in desc and "contract=" in desc


# ── 3. activation-only 五条件 ────────────────────────────

def _evidence(**overrides) -> SealEvidence:
    defaults = dict(
        unit_contract_digest="a" * 64,
        bundle_digest="b" * 64,
        row_counts={"tb_balance": 10, "tb_ledger": 20},
        post_hash="c" * 64,
    )
    defaults.update(overrides)
    return SealEvidence(**defaults)


def _sealed_attempt(evidence: SealEvidence, ds: uuid.UUID) -> SimpleNamespace:
    return _attempt(
        status="sealed",
        base_dataset_id=ds,
        base_unit_contract_digest=evidence.unit_contract_digest,
        unit_contract_digest=evidence.unit_contract_digest,
        bundle_digest=evidence.bundle_digest,
        unit_confirmation={
            "row_counts": evidence.row_counts,
            "post_hash": evidence.post_hash,
        },
    )


class TestActivationOnly:
    def test_all_five_conditions_pass(self) -> None:
        ds = uuid.uuid4()
        ev = _evidence()
        att = _sealed_attempt(ev, ds)
        assert can_activation_only(att, current=BaseToken(ds, ev.unit_contract_digest), evidence=ev) is True

    def test_not_sealed_returns_false(self) -> None:
        ds = uuid.uuid4()
        ev = _evidence()
        att = _sealed_attempt(ev, ds)
        att.status = "building"
        assert can_activation_only(att, current=BaseToken(ds, ev.unit_contract_digest), evidence=ev) is False

    def test_base_drift_returns_false(self) -> None:
        ds = uuid.uuid4()
        ev = _evidence()
        att = _sealed_attempt(ev, ds)
        assert can_activation_only(att, current=BaseToken(uuid.uuid4(), ev.unit_contract_digest), evidence=ev) is False

    def test_contract_mismatch_returns_false(self) -> None:
        ds = uuid.uuid4()
        ev = _evidence()
        att = _sealed_attempt(ev, ds)
        other = _evidence(unit_contract_digest="z" * 64)
        assert can_activation_only(att, current=BaseToken(ds, ev.unit_contract_digest), evidence=other) is False

    def test_bundle_mismatch_returns_false(self) -> None:
        ds = uuid.uuid4()
        ev = _evidence()
        att = _sealed_attempt(ev, ds)
        other = _evidence(bundle_digest="z" * 64)
        assert can_activation_only(att, current=BaseToken(ds, ev.unit_contract_digest), evidence=other) is False

    def test_row_counts_mismatch_returns_false(self) -> None:
        ds = uuid.uuid4()
        ev = _evidence()
        att = _sealed_attempt(ev, ds)
        other = _evidence(row_counts={"tb_balance": 999})
        assert can_activation_only(att, current=BaseToken(ds, ev.unit_contract_digest), evidence=other) is False

    def test_post_hash_mismatch_returns_false(self) -> None:
        ds = uuid.uuid4()
        ev = _evidence()
        att = _sealed_attempt(ev, ds)
        other = _evidence(post_hash="z" * 64)
        assert can_activation_only(att, current=BaseToken(ds, ev.unit_contract_digest), evidence=other) is False


# ── 4. current_phase 不参与判定 ──────────────────────────

class TestCurrentPhaseIsDisplayOnly:
    @pytest.mark.parametrize("phase", DISPLAY_PHASES)
    def test_phase_does_not_affect_activation_only(self, phase: str) -> None:
        """改 current_phase 不影响 activation-only 结果（它只是显示）。"""
        ds = uuid.uuid4()
        ev = _evidence()
        att = _sealed_attempt(ev, ds)
        att.current_phase = phase
        assert can_activation_only(att, current=BaseToken(ds, ev.unit_contract_digest), evidence=ev) is True

    @pytest.mark.parametrize("phase", DISPLAY_PHASES)
    def test_phase_does_not_affect_transition(self, phase: str) -> None:
        """改 current_phase 不影响状态机（它不参与判定）。"""
        assert_transition("building", "sealed")  # 与 phase 无关
