"""
账套导入金额单位：检测摘要、严格合同解析与持久化合同复验。

本模块是 **R8 的运行时单源**，与 `app/schemas/ledger_unit_contract.py` 的分工：

- `schemas/ledger_unit_contract.py` 只定义 wire shape（Pydantic 合同）与 canonical digest；
- 本模块负责 **从真实检测结果生成摘要**、**从持久化 JSON 严格反解合同**
  并复验「确认人 / 检测摘要 / canonical digest」三者互相一致。

design §5；R8；AC-14、AC-15、AC-17。

🔴 三条纪律（每条都对应一次真实踩坑）：

1. **标签映射闭集**：`元/千元/万元` 映射三枚举；`百元/亿元/外币` 等进入
   `unsupported` —— 绝不「猜一个最近的」。
2. **证据 digest 必须可复算**：`evidence_digest` 由 bundle 文件 hash/size、
   `detector_version` 与逐 file/sheet 的 (raw label → verdict) 规范 JSON 算出。
   不是随机数、不是时间戳（memory 铁律 ㉗①：非确定性输入 = 永假门禁）。
3. **持久化合同复验 fail closed**：`parse_persisted_unit_contract` 对缺失、
   篡改、确认人不符、检测摘要不符**一律抛**，返回 None 的写法等于放行。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Iterable, Literal
from uuid import UUID

from app.schemas.ledger_unit_contract import (
    UNIT_FACTORS,
    AmountUnit,
    UnitConfirmationInput,
    UnitDetectionSummary,
    UnitNormalizationContract,
    build_contract,
    canonical_contract_digest,
)

#: 检测器版本。改变映射表或标签正则时必须同步 +1 ——
#: 否则历史 `evidence_digest` 会被新口径重算成不同值，
#: 而已提交的作业会被判 `UNIT_DETECTION_CHANGED`。
DETECTOR_VERSION = "ledger-unit-detector-v1"

#: 中文标签 → 三枚举。**闭集**：不在此表的标签一律进 unsupported。
SUPPORTED_UNIT_LABELS: dict[str, AmountUnit] = {
    "元": "yuan",
    "人民币元": "yuan",
    "千元": "qian",
    "千": "qian",
    "万元": "wan",
    "万": "wan",
}

#: 明确识别但**不支持**换算的标签（进 unsupported，不静默当元）。
UNSUPPORTED_UNIT_LABELS: frozenset[str] = frozenset(
    {
        "百元",
        "十元",
        "亿元",
        "亿",
        "百万",
        "千万",
        "美元",
        "港元",
        "港币",
        "欧元",
        "日元",
        "英镑",
        "外币",
        "原币",
    }
)


class UnitContractError(Exception):
    """持久化合同无法严格解析 / 复验不通过。"""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


# ── 检测摘要 ──────────────────────────────────────────────


@dataclass(frozen=True)
class DetectedLabel:
    """单个 sheet 的原始单位标签与其归一判定。"""

    file_name: str
    sheet_name: str
    raw_label: str
    verdict: Literal["yuan", "qian", "wan", "unsupported"]


@dataclass
class UnitDetection:
    """`summarize_detected_units` 的完整产物（摘要 + 逐标签明细）。"""

    summary: UnitDetectionSummary
    labels: list[DetectedLabel] = field(default_factory=list)


def _canonical_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def compute_evidence_digest(
    *,
    labels: Iterable[DetectedLabel],
    file_hashes: dict[str, tuple[str, int]] | None = None,
    detector_version: str = DETECTOR_VERSION,
) -> str:
    """计算 `evidence_digest`（64 位小写 SHA-256）。

    payload 组成（全部参与，任一变化即换 digest）：

    - `detector_version`
    - `files`：`{文件名: {sha256, size}}`（按文件名排序；缺 hash 时该文件不入 payload，
      由上层据「旧 bundle 缺 hash」拒绝，而不是在这里伪造一个值）
    - `labels`：逐条 `{file, sheet, raw_label, verdict}`，按四元组排序
    """
    ordered_labels = sorted(
        (
            {
                "file": item.file_name,
                "sheet": item.sheet_name,
                "raw_label": item.raw_label,
                "verdict": item.verdict,
            }
            for item in labels
        ),
        key=lambda d: (d["file"], d["sheet"], d["raw_label"], d["verdict"]),
    )
    files_payload = {
        name: {"sha256": digest, "size": int(size)}
        for name, (digest, size) in sorted((file_hashes or {}).items())
    }
    payload = {
        "detector_version": detector_version,
        "files": files_payload,
        "labels": ordered_labels,
    }
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def classify_unit_label(raw_label: str | None) -> Literal["yuan", "qian", "wan", "unsupported"] | None:
    """把原始标签映射为三枚举或 `unsupported`；`None` 表示「没写单位」。

    🔴 空白标签返回 `None` 而不是 `unsupported` ——
    「没写单位」与「写了一个我们不支持的单位」是两种不同的业务事实，
    混为一谈会让 missing 与 unsupported 两个状态永远无法区分。
    """
    if raw_label is None:
        return None
    label = raw_label.strip()
    if not label:
        return None
    if label in SUPPORTED_UNIT_LABELS:
        return SUPPORTED_UNIT_LABELS[label]
    if label in UNSUPPORTED_UNIT_LABELS:
        return "unsupported"
    # 形如「金额单位：万元」的整句（detector 已抽过一层，这里兜底再剥一次）
    for prefix in ("金额单位", "单位"):
        if label.startswith(prefix):
            inner = label[len(prefix) :].lstrip("：: （(").rstrip("）)")
            return classify_unit_label(inner)
    return "unsupported"


def summarize_detected_units(
    *,
    sheets: Iterable[tuple[str, str, str | None]],
    file_hashes: dict[str, tuple[str, int]] | None = None,
    detector_version: str = DETECTOR_VERSION,
) -> UnitDetection:
    """从逐 sheet 的原始标签生成同一份 `UnitDetectionSummary`。

    Parameters
    ----------
    sheets:
        `(file_name, sheet_name, raw_label)` 三元组序列。`raw_label=None`
        表示该 sheet 没有单位横幅。
    file_hashes:
        `{文件名: (sha256, size)}`。旧 bundle 缺 hash 时调用方应先拒绝上传，
        不应把空 dict 传进来当作「无 hash 也算完整证据」。

    状态判定（与 design §5 一致）：

    - 出现任何 `unsupported` → `unsupported`（优先级最高：写了不支持的
      单位时，即使其它 sheet 都写元也不能当成「全是元」）；
    - 有 ≥2 个不同的受支持单位 → `conflict`；
    - 恰好 1 个受支持单位 → `detected`；
    - 一个都没有 → `missing`。
    """
    labels: list[DetectedLabel] = []
    for file_name, sheet_name, raw_label in sheets:
        verdict = classify_unit_label(raw_label)
        if verdict is None:
            continue
        labels.append(
            DetectedLabel(
                file_name=file_name,
                sheet_name=sheet_name,
                raw_label=(raw_label or "").strip(),
                verdict=verdict,
            )
        )

    supported = sorted({item.verdict for item in labels if item.verdict != "unsupported"})
    unsupported_labels = sorted(
        {item.raw_label for item in labels if item.verdict == "unsupported"}
    )

    if unsupported_labels:
        status: Literal["detected", "missing", "conflict", "unsupported"] = "unsupported"
        candidates: list[AmountUnit] = supported  # type: ignore[assignment]
        suggested: AmountUnit | None = None
    elif len(supported) > 1:
        status = "conflict"
        candidates = supported  # type: ignore[assignment]
        suggested = None
    elif len(supported) == 1:
        status = "detected"
        candidates = supported  # type: ignore[assignment]
        suggested = supported[0]  # type: ignore[assignment]
    else:
        status = "missing"
        candidates = []
        suggested = None

    summary = UnitDetectionSummary(
        status=status,
        candidates=candidates,
        unsupported_labels=unsupported_labels,
        suggested_unit=suggested,
        detector_version=detector_version,
        evidence_digest=compute_evidence_digest(
            labels=labels,
            file_hashes=file_hashes,
            detector_version=detector_version,
        ),
    )
    return UnitDetection(summary=summary, labels=labels)


# ── 严格合同构造 / 反解 ────────────────────────────────────


def build_confirmed_unit_contract(
    *,
    detection: UnitDetectionSummary,
    confirmation: UnitConfirmationInput,
    confirmed_by: UUID,
    confirmed_at=None,
    job_created_by: UUID | None = None,
) -> UnitNormalizationContract:
    """由检测摘要 + 用户确认构造不可变合同（**唯一入口**）。

    复验（任一不符即抛 `UnitContractError`）：

    1. `confirmation.unit_evidence_digest` 必须等于 `detection.evidence_digest`
       —— 确认必须绑定到「本次看到的检测结果」。
    2. `detection.status == 'unsupported'` 不可构造合同（schema 层也会拒）。
    3. `job_created_by` 给出时必须等于 `confirmed_by`（design §5：
       「确认人与 job.created_by 不同」是必须拒绝的篡改形态）。
    """
    if confirmation.unit_evidence_digest != detection.evidence_digest:
        raise UnitContractError(
            "UNIT_DETECTION_CHANGED",
            "确认使用的检测摘要与当前检测结果不一致，请重新预览后再确认",
        )
    if job_created_by is not None and job_created_by != confirmed_by:
        raise UnitContractError(
            "UNIT_CONTRACT_INVALID",
            "确认人与作业创建人不一致",
        )
    return build_contract(
        source_unit=confirmation.source_amount_unit,
        detection=detection,
        confirmed_by=confirmed_by,
        confirmed_at=confirmed_at,
        confirmation_reason=confirmation.unit_confirmation_reason,
    )


def parse_persisted_unit_contract(
    raw: Any,
    *,
    job_created_by: UUID | None = None,
) -> UnitNormalizationContract:
    """从 `ImportJob.options` 里的持久化合同严格反解并复验。

    **每次 claim / retry / resume 都必须调用**（design §5）——
    部署时已排队但缺失或被篡改的旧作业必须 fail closed，不能「按默认值补齐」。

    复验四项：

    1. 结构可解析（Pydantic 严格模式，`extra='forbid'`）；
    2. `contract_digest` 与重算值逐值相等（防篡改）；
    3. `confirmed_by == job_created_by`（给出时）；
    4. `detection.status != 'unsupported'`（schema 已拒，这里再挡一层防御）。

    任一不符抛 `UnitContractError`；**绝不返回 None 表示失败**。
    """
    if raw is None:
        raise UnitContractError(
            "SOURCE_UNIT_CONFIRMATION_REQUIRED",
            "作业缺少单位确认合同（历史作业或未确认提交），需重新预览并确认",
        )
    if isinstance(raw, UnitNormalizationContract):
        contract = raw
    elif isinstance(raw, dict):
        try:
            contract = UnitNormalizationContract.model_validate(raw)
        except Exception as exc:  # noqa: BLE001 - pydantic 异常类型很多，统一转换
            raise UnitContractError(
                "UNIT_CONTRACT_INVALID",
                f"持久化单位合同无法解析：{exc}",
            ) from exc
    else:
        raise UnitContractError(
            "UNIT_CONTRACT_INVALID",
            f"持久化单位合同类型非法：{type(raw).__name__}",
        )

    recomputed = canonical_contract_digest(contract)
    if contract.contract_digest != recomputed:
        raise UnitContractError(
            "UNIT_CONTRACT_INVALID",
            "持久化单位合同的 digest 与重算值不一致（疑似被篡改）",
        )
    if job_created_by is not None and contract.confirmed_by != job_created_by:
        raise UnitContractError(
            "UNIT_CONTRACT_INVALID",
            "持久化单位合同的确认人与作业创建人不一致",
        )
    if contract.detection.status == "unsupported":
        raise UnitContractError(
            "UNIT_CONTRACT_INVALID",
            "unsupported 检测状态不可构造有效合同",
        )
    return contract


def factor_for(source_unit: str) -> Decimal:
    """来源单位 → 换算因子（闭集；非法值抛而不是回落 1）。"""
    factor = UNIT_FACTORS.get(source_unit)
    if factor is None:
        raise UnitContractError(
            "UNIT_CONTRACT_INVALID",
            f"不支持的来源单位：{source_unit!r}",
        )
    return factor


__all__ = [
    "DETECTOR_VERSION",
    "SUPPORTED_UNIT_LABELS",
    "UNSUPPORTED_UNIT_LABELS",
    "DetectedLabel",
    "UnitContractError",
    "UnitDetection",
    "build_confirmed_unit_contract",
    "classify_unit_label",
    "compute_evidence_digest",
    "factor_for",
    "parse_persisted_unit_contract",
    "summarize_detected_units",
]
