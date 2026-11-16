"""
test_ledger_unit_normalization_apply.py

账套单位归一化 apply / rollback 双闸门与可逆证据
（spec platform-global-display-settings-closure 任务 9 / AC-18）。

覆盖 design §13 第 9 条要求的四类：
1. **逐个缺闸门**：环境变量 / `--apply` 语义 / 双录 / source unit，缺一即拒。
2. **presence-aware 快照**：`键缺失` 与 `显式 null` 回滚后必须可区分。
3. **hash 闭合**：rollback 前 `current → after_hash` 必须相等；篡改即拒。
4. **非最后版本拒绝**：只能回滚最后一个未回滚版本。
5. **金额内核**：None 原样、非法非空值 / NaN / ±Inf 抛错、正负半分 ROUND_HALF_UP。
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.services.ledger_unit_normalization_apply import (
    APPLY_ENV_FLAG,
    ROLLBACK_ENV_FLAG,
    UNIT_FACTORS,
    ApplyRequest,
    RollbackRequest,
    UnitApplyGateError,
    UnitApplyStateError,
    assert_last_uncancelled_version,
    build_apply_history,
    build_rollback_history,
    canonical_hash,
    normalize_amount,
    restore_unit_metadata,
    snapshot_unit_metadata,
)

_OK_ENV = {APPLY_ENV_FLAG: "1"}
_OK_RB_ENV = {ROLLBACK_ENV_FLAG: "1"}


# ── 1. apply 三重闸门 ─────────────────────────────────────

class TestApplyGates:
    def test_all_gates_pass(self) -> None:
        ApplyRequest(
            dataset_id="ds-1", source_unit="wan",
            confirm_dataset_id="ds-1", env=_OK_ENV,
        ).validate()

    def test_missing_env_flag_rejected(self) -> None:
        with pytest.raises(UnitApplyGateError, match=APPLY_ENV_FLAG):
            ApplyRequest(
                dataset_id="ds-1", source_unit="wan",
                confirm_dataset_id="ds-1", env={},
            ).validate()

    def test_env_flag_must_be_exactly_one(self) -> None:
        """`0` / `true` / 空串都不算开（避免「设了个值就当开了」）。"""
        for bad in ("0", "true", "", "yes"):
            with pytest.raises(UnitApplyGateError):
                ApplyRequest(
                    dataset_id="ds-1", source_unit="wan",
                    confirm_dataset_id="ds-1", env={APPLY_ENV_FLAG: bad},
                ).validate()

    def test_double_entry_mismatch_rejected(self) -> None:
        with pytest.raises(UnitApplyGateError, match="双录"):
            ApplyRequest(
                dataset_id="ds-1", source_unit="wan",
                confirm_dataset_id="ds-2", env=_OK_ENV,
            ).validate()

    def test_missing_dataset_id_rejected(self) -> None:
        with pytest.raises(UnitApplyGateError, match="dataset-id"):
            ApplyRequest(
                dataset_id="", source_unit="wan",
                confirm_dataset_id="", env=_OK_ENV,
            ).validate()

    def test_invalid_source_unit_rejected(self) -> None:
        with pytest.raises(UnitApplyGateError, match="source-unit"):
            ApplyRequest(
                dataset_id="ds-1", source_unit="yuan2",
                confirm_dataset_id="ds-1", env=_OK_ENV,
            ).validate()


# ── 2. rollback 额外闸门 ──────────────────────────────────

class TestRollbackGates:
    def test_all_gates_pass(self) -> None:
        RollbackRequest(
            dataset_id="ds-1", normalization_version=1,
            confirm_dataset_id="ds-1", env=_OK_RB_ENV,
        ).validate()

    def test_missing_env_flag_rejected(self) -> None:
        with pytest.raises(UnitApplyGateError, match=ROLLBACK_ENV_FLAG):
            RollbackRequest(
                dataset_id="ds-1", normalization_version=1,
                confirm_dataset_id="ds-1", env=_OK_ENV,  # apply 的 flag 不管用
            ).validate()

    def test_version_must_be_positive_int(self) -> None:
        for bad in (0, -1):
            with pytest.raises(UnitApplyGateError, match="normalization-version"):
                RollbackRequest(
                    dataset_id="ds-1", normalization_version=bad,
                    confirm_dataset_id="ds-1", env=_OK_RB_ENV,
                ).validate()


# ── 3. presence-aware 快照 ────────────────────────────────

class TestPresenceAwareSnapshot:
    def test_missing_key_vs_explicit_null_are_distinguishable(self) -> None:
        """🔴 这是本模块存在的主要理由：`get()` 读两者都是 None。"""
        missing = snapshot_unit_metadata({})
        explicit_null = snapshot_unit_metadata({"unit_normalization": None})
        assert missing["unit_normalization"] == {"present": False, "value": None}
        assert explicit_null["unit_normalization"] == {"present": True, "value": None}
        assert canonical_hash(missing) != canonical_hash(explicit_null)

    def test_restore_removes_key_that_was_absent(self) -> None:
        snapshot = snapshot_unit_metadata({})
        restored = restore_unit_metadata(
            {"unit_normalization": {"v": 1}, "other": "keep"}, snapshot
        )
        assert "unit_normalization" not in restored
        assert restored["other"] == "keep"

    def test_restore_keeps_explicit_null(self) -> None:
        snapshot = snapshot_unit_metadata({"unit_normalization": None})
        restored = restore_unit_metadata({"unit_normalization": {"v": 1}}, snapshot)
        assert "unit_normalization" in restored
        assert restored["unit_normalization"] is None

    def test_restore_preserves_other_keys(self) -> None:
        snapshot = snapshot_unit_metadata({"source_unit": "wan"})
        restored = restore_unit_metadata(
            {"a": 1, "b": 2, "unit_normalization": {"v": 9}}, snapshot
        )
        assert restored["a"] == 1 and restored["b"] == 2
        assert restored["source_unit"] == "wan"
        assert "unit_normalization" not in restored


# ── 4. history 与 hash 闭合 ───────────────────────────────

class TestHistoryClosure:
    def _apply(self, *, before: dict, after: dict, version: int = 1):
        return build_apply_history(
            dataset_id="ds-1", normalization_version=version,
            source_unit="wan", before_summary=before, after_summary=after,
        )

    def test_apply_history_records_before_and_after(self) -> None:
        rec = self._apply(
            before={}, after={"unit_normalization": {"version": 1, "source_unit": "wan"}}
        )
        assert rec.action == "apply"
        assert rec.before_hash != rec.after_hash
        assert rec.metadata_snapshot["unit_normalization"]["present"] is False

    def test_rollback_closes_current_to_before(self) -> None:
        after = {"unit_normalization": {"version": 1, "source_unit": "wan"}}
        apply_rec = self._apply(before={}, after=after)
        rb = build_rollback_history(
            apply_record=apply_rec, current_summary=after, normalization_version=2,
        )
        assert rb.action == "rollback"
        assert rb.before_hash == apply_rec.after_hash  # 闭合
        assert rb.after_hash == apply_rec.before_hash  # 反向

    def test_rollback_rejects_tampered_current(self) -> None:
        after = {"unit_normalization": {"version": 1, "source_unit": "wan"}}
        apply_rec = self._apply(before={}, after=after)
        with pytest.raises(UnitApplyStateError, match="已被改动"):
            build_rollback_history(
                apply_record=apply_rec,
                current_summary={"unit_normalization": {"version": 1, "source_unit": "qian"}},
                normalization_version=2,
            )

    def test_rollback_rejects_missing_key_when_apply_added_it(self) -> None:
        """apply 加了键、之后被删掉 ⇒ 当前 hash 与 after 不等 ⇒ 拒回滚。"""
        after = {"unit_normalization": {"version": 1}}
        apply_rec = self._apply(before={}, after=after)
        with pytest.raises(UnitApplyStateError):
            build_rollback_history(
                apply_record=apply_rec, current_summary={}, normalization_version=2,
            )


# ── 5. 只能回滚最后一个未回滚版本 ─────────────────────────

class TestLastVersionOnly:
    def test_last_version_allowed(self) -> None:
        assert_last_uncancelled_version(
            target_version=3, history_versions=[1, 2, 3], rolled_back=set(),
        )

    def test_non_last_version_rejected(self) -> None:
        with pytest.raises(UnitApplyStateError, match="只能回滚最后一个"):
            assert_last_uncancelled_version(
                target_version=2, history_versions=[1, 2, 3], rolled_back=set(),
            )

    def test_already_rolled_back_version_rejected(self) -> None:
        with pytest.raises(UnitApplyStateError, match="只能回滚最后一个"):
            assert_last_uncancelled_version(
                target_version=3, history_versions=[1, 2, 3], rolled_back={3},
            )

    def test_empty_history_rejected(self) -> None:
        with pytest.raises(UnitApplyStateError, match="没有可回滚"):
            assert_last_uncancelled_version(
                target_version=1, history_versions=[], rolled_back=set(),
            )


# ── 6. 金额唯一内核 ───────────────────────────────────────

class TestNormalizeAmount:
    def test_none_preserved(self) -> None:
        assert normalize_amount(None, "wan") is None

    def test_zero_preserved_as_zero(self) -> None:
        assert normalize_amount(0, "wan") == Decimal("0.00")

    def test_three_factors(self) -> None:
        assert normalize_amount(Decimal("1"), "yuan") == Decimal("1.00")
        assert normalize_amount(Decimal("1"), "qian") == Decimal("1000.00")
        assert normalize_amount(Decimal("1"), "wan") == Decimal("10000.00")

    def test_round_half_up_positive(self) -> None:
        # 0.005 半分向上
        assert normalize_amount(Decimal("0.005"), "yuan") == Decimal("0.01")

    def test_round_half_up_negative(self) -> None:
        assert normalize_amount(Decimal("-0.005"), "yuan") == Decimal("-0.01")

    def test_nan_rejected(self) -> None:
        with pytest.raises(UnitApplyStateError, match="NOT_FINITE"):
            normalize_amount(Decimal("NaN"), "yuan")

    def test_infinity_rejected(self) -> None:
        with pytest.raises(UnitApplyStateError, match="NOT_FINITE"):
            normalize_amount(Decimal("Infinity"), "yuan")

    def test_invalid_string_rejected(self) -> None:
        with pytest.raises(UnitApplyStateError, match="INVALID"):
            normalize_amount("not-a-number", "yuan")

    def test_unknown_unit_rejected(self) -> None:
        with pytest.raises(UnitApplyGateError, match="未知 source_unit"):
            normalize_amount(Decimal("1"), "bogus")

    def test_factors_are_pinned(self) -> None:
        assert UNIT_FACTORS == {
            "yuan": Decimal("1"),
            "qian": Decimal("1000"),
            "wan": Decimal("10000"),
        }
