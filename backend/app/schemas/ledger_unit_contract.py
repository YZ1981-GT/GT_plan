"""
账套导入单位归一合同 schema。

三因子模型：yuan/qian/wan → factor 1/1000/10000，storage_unit 固定 yuan。
digest = sha256(canonical JSON of all fields except contract_digest)。

design §5, R8, AC-14~AC-17.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# ── 常量 ──────────────────────────────────────────────────

AmountUnit = Literal["yuan", "qian", "wan"]

UNIT_FACTORS: dict[str, Decimal] = {
    "yuan": Decimal("1"),
    "qian": Decimal("1000"),
    "wan": Decimal("10000"),
}

_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")


# ── 检测摘要 ──────────────────────────────────────────────

class UnitDetectionSummary(BaseModel):
    """upload bundle 上的单位检测结果。"""

    model_config = ConfigDict(extra="forbid")

    status: Literal["detected", "missing", "conflict", "unsupported"]
    candidates: list[AmountUnit]
    unsupported_labels: list[str] = Field(default_factory=list)
    suggested_unit: AmountUnit | None = None
    detector_version: str
    evidence_digest: str  # 64 位小写 SHA-256

    @field_validator("evidence_digest")
    @classmethod
    def _hex64_evidence(cls, v: str) -> str:
        if not _HEX64_RE.match(v):
            raise ValueError("evidence_digest 必须是 64 位小写十六进制")
        return v


# ── 确认输入 ──────────────────────────────────────────────

class UnitConfirmationInput(BaseModel):
    """用户确认来源金额单位。"""

    model_config = ConfigDict(extra="forbid")

    source_amount_unit: AmountUnit
    source_unit_confirmed: Literal[True]
    unit_evidence_digest: str  # 64 hex

    # 条件必填：检测 missing/conflict 或覆盖 suggested 时 1~200 字
    unit_confirmation_reason: str | None = None

    @field_validator("unit_evidence_digest")
    @classmethod
    def _hex64_evidence(cls, v: str) -> str:
        if not _HEX64_RE.match(v):
            raise ValueError("unit_evidence_digest 必须是 64 位小写十六进制")
        return v

    @field_validator("unit_confirmation_reason")
    @classmethod
    def _trim_reason(cls, v: str | None) -> str | None:
        if v is None:
            return None
        stripped = v.strip()
        if not stripped:
            return None
        if len(stripped) > 200:
            raise ValueError("unit_confirmation_reason 长度不得超过 200 字")
        return stripped


# ── 归一合同 ──────────────────────────────────────────────

class UnitNormalizationContract(BaseModel):
    """不可变的归一合同，用于持久化到 LedgerDataset.source_summary。"""

    model_config = ConfigDict(extra="forbid")

    source_unit: AmountUnit
    storage_unit: Literal["yuan"] = "yuan"
    factor: Decimal
    normalization_version: Literal["normalized_v1"] = "normalized_v1"
    fields_version: Literal["amount_fields_v1"] = "amount_fields_v1"
    detection: UnitDetectionSummary
    confirmation_reason: str | None = None
    confirmed_by: UUID
    confirmed_at: datetime
    contract_digest: str = ""  # 由 model_validator 填充

    @model_validator(mode="after")
    def _enforce_invariants(self) -> "UnitNormalizationContract":
        # ① storage_unit 固定 yuan
        if self.storage_unit != "yuan":
            raise ValueError("storage_unit 必须固定为 yuan")

        # ② factor 由 source_unit 唯一派生
        expected = UNIT_FACTORS.get(self.source_unit)
        if expected is None:
            raise ValueError(f"不支持的 source_unit: {self.source_unit}")
        if self.factor != expected:
            raise ValueError(
                f"factor 不一致：source_unit={self.source_unit} 要求 "
                f"factor={expected}，实际 factor={self.factor}"
            )

        # ③ unsupported 永不合法
        if self.detection.status == "unsupported":
            raise ValueError("unsupported 状态不可构造合同")

        # ④ confirmation_reason 条件必填
        #    detected 且 source_unit == suggested → reason 可空
        #    detected 但覆盖 suggested / missing / conflict → 必须有效
        if self.detection.status == "detected":
            if self.source_unit != self.detection.suggested_unit:
                if not self.confirmation_reason:
                    raise ValueError(
                        "覆盖建议单位时 confirmation_reason 不可为空"
                    )
        elif self.detection.status in ("missing", "conflict"):
            if not self.confirmation_reason:
                raise ValueError(
                    f"status={self.detection.status} 时 confirmation_reason 不可为空"
                )

        return self


# ── digest 计算 ───────────────────────────────────────────

def _canonical_json(contract: UnitNormalizationContract) -> str:
    """生成规范化 JSON（排除 contract_digest 自身）。

    枚举用 value、datetime 用 UTC ISO、Decimal 用规范字符串、key 排序。
    """
    payload = {
        "confirmation_reason": contract.confirmation_reason,
        "confirmed_at": contract.confirmed_at.astimezone(timezone.utc).isoformat(),
        "confirmed_by": str(contract.confirmed_by),
        "detection": contract.detection.model_dump(mode="json"),
        "factor": str(contract.factor),
        "fields_version": contract.fields_version,
        "normalization_version": contract.normalization_version,
        "source_unit": contract.source_unit,
        "storage_unit": contract.storage_unit,
    }
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def canonical_contract_digest(contract: UnitNormalizationContract) -> str:
    """计算规范化合同的 SHA-256 digest（64 位小写十六进制）。"""
    return hashlib.sha256(_canonical_json(contract).encode("utf-8")).hexdigest()


# ── 工厂函数 ──────────────────────────────────────────────

def build_contract(
    *,
    source_unit: AmountUnit,
    detection: UnitDetectionSummary,
    confirmed_by: UUID,
    confirmed_at: datetime | None = None,
    confirmation_reason: str | None = None,
) -> UnitNormalizationContract:
    """构造并签名一个 UnitNormalizationContract。

    factor 由 source_unit 自动派生，contract_digest 自动计算。
    """
    factor = UNIT_FACTORS[source_unit]
    now = confirmed_at or datetime.now(timezone.utc)

    contract = UnitNormalizationContract(
        source_unit=source_unit,
        storage_unit="yuan",
        factor=factor,
        detection=detection,
        confirmed_by=confirmed_by,
        confirmed_at=now,
        confirmation_reason=confirmation_reason,
    )
    contract.contract_digest = canonical_contract_digest(contract)
    return contract
