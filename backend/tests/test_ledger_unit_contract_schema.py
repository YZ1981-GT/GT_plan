"""
test_ledger_unit_contract_schema.py

三因子 digest 稳定、factor 不一致 422、confirmation digest 64 hex。
design §5, R8, AC-14~AC-17.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas.ledger_unit_contract import (
    UNIT_FACTORS,
    UnitConfirmationInput,
    UnitDetectionSummary,
    UnitNormalizationContract,
    build_contract,
    canonical_contract_digest,
)

_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")

# ── helpers ───────────────────────────────────────────────

_EVIDENCE = "a" * 64


def _detection(
    status: str = "detected",
    suggested: str | None = "yuan",
    unsupported_labels: list[str] | None = None,
) -> UnitDetectionSummary:
    return UnitDetectionSummary(
        status=status,
        candidates=["yuan"] if suggested else [],
        unsupported_labels=unsupported_labels or [],
        suggested_unit=suggested,
        detector_version="test_v1",
        evidence_digest=_EVIDENCE,
    )


def _build(
    source_unit: str = "yuan",
    detection: UnitDetectionSummary | None = None,
    reason: str | None = None,
) -> UnitNormalizationContract:
    return build_contract(
        source_unit=source_unit,
        detection=detection or _detection(suggested=source_unit),
        confirmed_by=uuid4(),
        confirmed_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        confirmation_reason=reason,
    )


# ── 1. 三因子 digest 稳定 ────────────────────────────────

class TestThreeFactorDigestStable:
    """三因子 yuan/qian/wan 各自有确定 factor 且 digest 是 64 hex。"""

    @pytest.mark.parametrize(
        "unit,expected_factor",
        [("yuan", Decimal("1")), ("qian", Decimal("1000")), ("wan", Decimal("10000"))],
    )
    def test_factor_matches_and_digest_is_hex64(
        self, unit: str, expected_factor: Decimal
    ) -> None:
        c = _build(source_unit=unit)
        assert c.factor == expected_factor
        assert c.storage_unit == "yuan"
        assert _HEX64_RE.match(c.contract_digest)

    def test_same_input_produces_same_digest(self) -> None:
        user_id = uuid4()
        ts = datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
        det = _detection(suggested="wan")
        c1 = build_contract(
            source_unit="wan",
            detection=det,
            confirmed_by=user_id,
            confirmed_at=ts,
        )
        c2 = build_contract(
            source_unit="wan",
            detection=det,
            confirmed_by=user_id,
            confirmed_at=ts,
        )
        assert c1.contract_digest == c2.contract_digest

    def test_different_source_unit_produces_different_digest(self) -> None:
        user_id = uuid4()
        ts = datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
        c_yuan = build_contract(
            source_unit="yuan",
            detection=_detection(suggested="yuan"),
            confirmed_by=user_id,
            confirmed_at=ts,
        )
        c_wan = build_contract(
            source_unit="wan",
            detection=_detection(suggested="wan"),
            confirmed_by=user_id,
            confirmed_at=ts,
        )
        assert c_yuan.contract_digest != c_wan.contract_digest

    def test_recomputed_digest_matches_stored(self) -> None:
        c = _build(source_unit="qian")
        recomputed = canonical_contract_digest(c)
        assert c.contract_digest == recomputed


# ── 2. factor 不一致 → ValidationError ───────────────────

class TestFactorMismatch:
    """source_unit 与 factor 不一致必须被 model_validator 拒绝。"""

    def test_yuan_with_wrong_factor(self) -> None:
        with pytest.raises(ValidationError, match="factor 不一致"):
            UnitNormalizationContract(
                source_unit="yuan",
                factor=Decimal("1000"),
                detection=_detection(),
                confirmed_by=uuid4(),
                confirmed_at=datetime.now(timezone.utc),
            )

    def test_wan_with_factor_1(self) -> None:
        with pytest.raises(ValidationError, match="factor 不一致"):
            UnitNormalizationContract(
                source_unit="wan",
                factor=Decimal("1"),
                detection=_detection(suggested="wan"),
                confirmed_by=uuid4(),
                confirmed_at=datetime.now(timezone.utc),
            )

    def test_qian_with_factor_10000(self) -> None:
        with pytest.raises(ValidationError, match="factor 不一致"):
            UnitNormalizationContract(
                source_unit="qian",
                factor=Decimal("10000"),
                detection=_detection(suggested="qian"),
                confirmed_by=uuid4(),
                confirmed_at=datetime.now(timezone.utc),
            )


# ── 3. confirmation digest 必须 64 hex ───────────────────

class TestConfirmationDigestHex:
    """UnitConfirmationInput.unit_evidence_digest 必须为 64 位小写十六进制。"""

    def test_valid_hex64_accepted(self) -> None:
        inp = UnitConfirmationInput(
            source_amount_unit="yuan",
            source_unit_confirmed=True,
            unit_evidence_digest="a" * 64,
        )
        assert inp.unit_evidence_digest == "a" * 64

    def test_short_hex_rejected(self) -> None:
        with pytest.raises(ValidationError, match="64 位小写十六进制"):
            UnitConfirmationInput(
                source_amount_unit="yuan",
                source_unit_confirmed=True,
                unit_evidence_digest="a" * 63,
            )

    def test_uppercase_hex_rejected(self) -> None:
        with pytest.raises(ValidationError, match="64 位小写十六进制"):
            UnitConfirmationInput(
                source_amount_unit="yuan",
                source_unit_confirmed=True,
                unit_evidence_digest="A" * 64,
            )

    def test_non_hex_chars_rejected(self) -> None:
        with pytest.raises(ValidationError, match="64 位小写十六进制"):
            UnitConfirmationInput(
                source_amount_unit="yuan",
                source_unit_confirmed=True,
                unit_evidence_digest="z" * 64,
            )

    def test_empty_string_rejected(self) -> None:
        with pytest.raises(ValidationError, match="64 位小写十六进制"):
            UnitConfirmationInput(
                source_amount_unit="yuan",
                source_unit_confirmed=True,
                unit_evidence_digest="",
            )


# ── 4. unsupported 永不合法 ──────────────────────────────

class TestUnsupportedRejected:
    def test_unsupported_detection_rejected(self) -> None:
        with pytest.raises(ValidationError, match="unsupported.*不可构造"):
            UnitNormalizationContract(
                source_unit="yuan",
                factor=Decimal("1"),
                detection=_detection(status="unsupported", suggested=None),
                confirmed_by=uuid4(),
                confirmed_at=datetime.now(timezone.utc),
            )


# ── 5. confirmation_reason 条件必填 ──────────────────────

class TestConfirmationReasonRequired:
    def test_detected_matching_suggestion_reason_optional(self) -> None:
        c = _build(source_unit="yuan")
        assert c.confirmation_reason is None

    def test_detected_override_requires_reason(self) -> None:
        det = _detection(suggested="qian")
        with pytest.raises(ValidationError, match="覆盖建议"):
            UnitNormalizationContract(
                source_unit="yuan",
                factor=Decimal("1"),
                detection=det,
                confirmed_by=uuid4(),
                confirmed_at=datetime.now(timezone.utc),
            )

    def test_missing_requires_reason(self) -> None:
        det = _detection(status="missing", suggested=None)
        with pytest.raises(ValidationError, match="confirmation_reason 不可为空"):
            UnitNormalizationContract(
                source_unit="yuan",
                factor=Decimal("1"),
                detection=det,
                confirmed_by=uuid4(),
                confirmed_at=datetime.now(timezone.utc),
            )

    def test_conflict_requires_reason(self) -> None:
        det = _detection(status="conflict", suggested=None)
        with pytest.raises(ValidationError, match="confirmation_reason 不可为空"):
            UnitNormalizationContract(
                source_unit="yuan",
                factor=Decimal("1"),
                detection=det,
                confirmed_by=uuid4(),
                confirmed_at=datetime.now(timezone.utc),
            )

    def test_missing_with_reason_accepted(self) -> None:
        det = _detection(status="missing", suggested=None)
        c = build_contract(
            source_unit="yuan",
            detection=det,
            confirmed_by=uuid4(),
            confirmation_reason="手工确认来源单位",
        )
        assert c.confirmation_reason == "手工确认来源单位"


# ── 6. extra fields 拒绝 ─────────────────────────────────

class TestExtraFieldsRejected:
    def test_confirmation_extra_field(self) -> None:
        with pytest.raises(ValidationError):
            UnitConfirmationInput(
                source_amount_unit="yuan",
                source_unit_confirmed=True,
                unit_evidence_digest="a" * 64,
                bogus="x",
            )

    def test_detection_extra_field(self) -> None:
        with pytest.raises(ValidationError):
            UnitDetectionSummary(
                status="detected",
                candidates=["yuan"],
                suggested_unit="yuan",
                detector_version="v1",
                evidence_digest="a" * 64,
                bogus="x",
            )
