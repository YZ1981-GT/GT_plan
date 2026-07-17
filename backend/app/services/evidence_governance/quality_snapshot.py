"""固定不可变质量快照的确定性可复算计算（纯函数，无 IO / 无 now() / 无随机）。

Feature: attachment-ocr-ai-evidence-governance-hardening
Task: 9.6 (Wave 8 — migration-quality 属性组)
Requirements: R16（可证明历史增强、固定质量快照与问题清单）
Design: §9 质量快照；§P30
Property: P30（固定不可变快照重复计算得到相同指标、账龄桶、问题清单且不改业务结论）

设计约束（P30 / R16）：

- 快照是 **固定不可变输入**：调用方在采集时把参与计算的全部证据记录冻结进 payload
  （``records`` + ``as_of_day`` 参考日），本模块 **只对该固定输入计算**，绝不读取数据库、
  当前时间或任何在线容量数据（P30 独立于 UAT-15：不以在线变化数据代替固定快照）。
- **确定性**：相同固定输入重复计算 → 完全相同的 ``metrics`` / ``aging_buckets`` /
  ``issue_list`` / ``business_conclusion`` / ``input_hash``。输出与记录输入顺序无关
  （permutation-invariant）。
- **不改业务结论**：``business_conclusion`` 由确定性规则从指标派生，重复计算不漂移。
- 计算与 ``EvidenceQualitySnapshot`` 持久模型对齐（metrics / aging_buckets / issue_list /
  input_hash 列），持久化/触发器不可变由迁移在 DB 层保证；本模块只负责纯计算。

本模块与 IO 分离，供 P30 独立固定快照 PBT 直接调用。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from app.services.evidence_governance.frozen_contracts import (
    canonical_json,
    content_hash_of,
)

# ---------------------------------------------------------------------------
# 固定账龄桶（上闭下开，最后一桶含 +∞）—— 与 evidence 治理账龄语义一致，确定性边界。
# 顺序即报告顺序；键稳定，供跨进程复算比对。
# ---------------------------------------------------------------------------
AGING_BUCKETS: tuple[tuple[str, int, int], ...] = (
    ("0-30", 0, 31),
    ("31-90", 31, 91),
    ("91-180", 91, 181),
    ("181-365", 181, 366),
    ("365+", 366, 10**9),
)

AGING_BUCKET_KEYS: tuple[str, ...] = tuple(name for name, _lo, _hi in AGING_BUCKETS)

# ---------------------------------------------------------------------------
# 问题码（确定性、封闭集合）。每条记录按下列规则产生零到多个问题码。
# ---------------------------------------------------------------------------
ISSUE_MISSING_ACTOR = "MISSING_ACTOR"
ISSUE_MISSING_HASH = "MISSING_HASH"
ISSUE_REF_INACTIVE = "REF_INACTIVE"
ISSUE_UNVERIFIED_CHAIN = "UNVERIFIED_CHAIN"
ISSUE_STALE = "STALE"
ISSUE_OCR_UNCONFIRMED = "OCR_UNCONFIRMED"
ISSUE_AI_UNCONFIRMED = "AI_UNCONFIRMED"
ISSUE_CITATION_NOT_LOCATABLE = "CITATION_NOT_LOCATABLE"

#: 阻断业务结论（archive_ready=false）的关键问题码集合。
BLOCKING_ISSUE_CODES: frozenset[str] = frozenset(
    {
        ISSUE_MISSING_ACTOR,
        ISSUE_MISSING_HASH,
        ISSUE_REF_INACTIVE,
        ISSUE_STALE,
        ISSUE_OCR_UNCONFIRMED,
        ISSUE_AI_UNCONFIRMED,
        ISSUE_CITATION_NOT_LOCATABLE,
    }
)

#: 非阻断但影响质量评级的问题码。
ADVISORY_ISSUE_CODES: frozenset[str] = frozenset({ISSUE_UNVERIFIED_CHAIN})


@dataclass(frozen=True)
class QualitySnapshotResult:
    """固定快照的确定性计算结果。"""

    snapshot_key: str
    metrics: dict[str, Any]
    aging_buckets: dict[str, int]
    issue_list: list[dict[str, Any]]
    business_conclusion: dict[str, Any]
    input_hash: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "snapshot_key": self.snapshot_key,
            "metrics": self.metrics,
            "aging_buckets": self.aging_buckets,
            "issue_list": self.issue_list,
            "business_conclusion": self.business_conclusion,
            "input_hash": self.input_hash,
        }


def _as_bool(value: Any) -> bool | None:
    """None 保持 None（不适用）；其余按真值判定。"""
    if value is None:
        return None
    return bool(value)


def _normalize_record(rec: Mapping[str, Any]) -> dict[str, Any]:
    """把一条原始证据记录规范化为确定性字段集合（缺失字段取保守默认）。

    仅使用固定快照自带字段，绝不读取外部状态。
    """
    etype = str(rec.get("evidence_type") or "unknown")
    rid = str(rec.get("id"))
    age_raw = rec.get("age_days")
    try:
        age_days = int(age_raw) if age_raw is not None else 0
    except (TypeError, ValueError):
        age_days = 0
    if age_days < 0:
        age_days = 0
    return {
        "id": rid,
        "evidence_type": etype,
        "has_actor": bool(rec.get("has_actor", False)),
        "content_hash": rec.get("content_hash"),
        "version": rec.get("version"),
        "is_active_ref": bool(rec.get("is_active_ref", True)),
        "unverified_chain": bool(rec.get("unverified_chain", False)),
        "is_stale": bool(rec.get("is_stale", False)),
        "ocr_confirmed": _as_bool(rec.get("ocr_confirmed")),
        "ai_human_confirmed": _as_bool(rec.get("ai_human_confirmed")),
        "citation_locatable": _as_bool(rec.get("citation_locatable")),
        "age_days": age_days,
    }


def _record_issues(rec: dict[str, Any]) -> list[str]:
    """确定性地为单条记录派生排序后的问题码列表。"""
    issues: list[str] = []

    if not rec["has_actor"]:
        issues.append(ISSUE_MISSING_ACTOR)

    # 有版本却无内容哈希 → 缺哈希（历史无字节可复算的情况调用方置 version=None，避免误报）。
    if rec["version"] is not None and not rec["content_hash"]:
        issues.append(ISSUE_MISSING_HASH)

    if not rec["is_active_ref"]:
        issues.append(ISSUE_REF_INACTIVE)

    if rec["unverified_chain"]:
        issues.append(ISSUE_UNVERIFIED_CHAIN)

    if rec["is_stale"]:
        issues.append(ISSUE_STALE)

    if rec["evidence_type"] == "ocr_result" and rec["ocr_confirmed"] is False:
        issues.append(ISSUE_OCR_UNCONFIRMED)

    if rec["evidence_type"] == "ai_content" and rec["ai_human_confirmed"] is False:
        issues.append(ISSUE_AI_UNCONFIRMED)

    if rec["evidence_type"] == "citation" and rec["citation_locatable"] is False:
        issues.append(ISSUE_CITATION_NOT_LOCATABLE)

    return sorted(set(issues))


def _bucket_of(age_days: int) -> str:
    for name, lo, hi in AGING_BUCKETS:
        if lo <= age_days < hi:
            return name
    return AGING_BUCKET_KEYS[-1]


def build_snapshot_input_hash(payload: Mapping[str, Any]) -> str:
    """固定快照输入的 canonical 内容哈希（记录顺序无关：先按 id 排序）。

    相同逻辑输入 → 相同哈希；任意固定输入变化 → 哈希变化。供跨进程复算比对。
    """
    scope = payload.get("scope") or {}
    as_of_day = payload.get("as_of_day")
    records = payload.get("records") or []
    normalized = [_normalize_record(r) for r in records]
    normalized.sort(key=lambda r: r["id"])
    canonical_input = {
        "scope": {
            "project_id": str(scope.get("project_id")) if scope.get("project_id") is not None else None,
            "audit_year": scope.get("audit_year"),
        },
        "as_of_day": as_of_day,
        "records": normalized,
    }
    return content_hash_of(canonical_input)


def compute_quality_snapshot(payload: Mapping[str, Any]) -> QualitySnapshotResult:
    """对固定不可变快照 payload 做确定性质量计算（P30）。

    payload 结构::

        {
          "scope": {"project_id": ..., "audit_year": ...},
          "as_of_day": <int, 参考日序数（快照采集时冻结，不使用 now()）>,
          "records": [
            {"id": ..., "evidence_type": ..., "has_actor": ...,
             "content_hash": ..., "version": ..., "is_active_ref": ...,
             "unverified_chain": ..., "is_stale": ...,
             "ocr_confirmed": ..., "ai_human_confirmed": ...,
             "citation_locatable": ..., "age_days": ...},
            ...
          ]
        }

    返回 ``QualitySnapshotResult``：``metrics`` / ``aging_buckets`` / ``issue_list`` /
    ``business_conclusion`` / ``input_hash``。输出与 records 输入顺序无关，重复计算完全一致。
    """
    scope = payload.get("scope") or {}
    records = list(payload.get("records") or [])

    # 规范化 + 按 id 稳定排序（permutation invariance 的关键）。
    normalized = [_normalize_record(r) for r in records]
    normalized.sort(key=lambda r: r["id"])

    total = len(normalized)
    with_hash = 0
    missing_actor = 0
    inactive_ref = 0
    unverified_chain = 0
    stale = 0
    ocr_total = 0
    ocr_confirmed = 0
    ocr_unconfirmed = 0
    ai_total = 0
    ai_confirmed = 0
    ai_unconfirmed = 0
    citation_total = 0
    citation_locatable = 0
    citation_not_locatable = 0

    aging: dict[str, int] = {k: 0 for k in AGING_BUCKET_KEYS}
    issue_list: list[dict[str, Any]] = []
    type_counts: dict[str, int] = {}
    blocking_records = 0

    for rec in normalized:
        etype = rec["evidence_type"]
        type_counts[etype] = type_counts.get(etype, 0) + 1

        if rec["content_hash"]:
            with_hash += 1
        if not rec["has_actor"]:
            missing_actor += 1
        if not rec["is_active_ref"]:
            inactive_ref += 1
        if rec["unverified_chain"]:
            unverified_chain += 1
        if rec["is_stale"]:
            stale += 1

        if etype == "ocr_result":
            ocr_total += 1
            if rec["ocr_confirmed"] is True:
                ocr_confirmed += 1
            elif rec["ocr_confirmed"] is False:
                ocr_unconfirmed += 1
        if etype == "ai_content":
            ai_total += 1
            if rec["ai_human_confirmed"] is True:
                ai_confirmed += 1
            elif rec["ai_human_confirmed"] is False:
                ai_unconfirmed += 1
        if etype == "citation":
            citation_total += 1
            if rec["citation_locatable"] is True:
                citation_locatable += 1
            elif rec["citation_locatable"] is False:
                citation_not_locatable += 1

        aging[_bucket_of(rec["age_days"])] += 1

        rec_issues = _record_issues(rec)
        if rec_issues:
            issue_list.append(
                {
                    "id": rec["id"],
                    "evidence_type": etype,
                    "issues": rec_issues,
                }
            )
            if any(code in BLOCKING_ISSUE_CODES for code in rec_issues):
                blocking_records += 1

    # issue_list 确定性排序（先 id 后类型）。
    issue_list.sort(key=lambda x: (x["id"], x["evidence_type"]))

    def _ratio(num: int, den: int) -> float:
        # 整数比率保留 4 位小数（确定性，避免浮点漂移）。
        if den == 0:
            return 0.0
        return round(num / den, 4)

    metrics: dict[str, Any] = {
        "total_records": total,
        "with_content_hash": with_hash,
        "missing_content_hash": total - with_hash,
        "missing_actor": missing_actor,
        "inactive_ref": inactive_ref,
        "unverified_chain": unverified_chain,
        "stale": stale,
        "ocr_total": ocr_total,
        "ocr_confirmed": ocr_confirmed,
        "ocr_unconfirmed": ocr_unconfirmed,
        "ai_total": ai_total,
        "ai_confirmed": ai_confirmed,
        "ai_unconfirmed": ai_unconfirmed,
        "citation_total": citation_total,
        "citation_locatable": citation_locatable,
        "citation_not_locatable": citation_not_locatable,
        "records_with_issues": len(issue_list),
        "blocking_records": blocking_records,
        "hash_coverage_ratio": _ratio(with_hash, total),
        "actor_coverage_ratio": _ratio(total - missing_actor, total),
        "type_counts": dict(sorted(type_counts.items())),
    }

    # 业务结论（确定性派生，不漂移）。
    archive_ready = blocking_records == 0
    if blocking_records > 0:
        grade = "blocked"
    elif unverified_chain > 0:
        grade = "advisory"
    else:
        grade = "clean"
    business_conclusion: dict[str, Any] = {
        "archive_ready": archive_ready,
        "grade": grade,
        "blocking_records": blocking_records,
        "advisory_records": unverified_chain,
    }

    input_hash = build_snapshot_input_hash(payload)

    project_id = scope.get("project_id")
    audit_year = scope.get("audit_year")
    snapshot_key = (
        f"quality:{project_id if project_id is not None else '-'}:"
        f"{audit_year if audit_year is not None else '-'}:{input_hash}"
    )

    return QualitySnapshotResult(
        snapshot_key=snapshot_key,
        metrics=metrics,
        aging_buckets=dict(aging),
        issue_list=issue_list,
        business_conclusion=business_conclusion,
        input_hash=input_hash,
    )


__all__ = [
    "AGING_BUCKETS",
    "AGING_BUCKET_KEYS",
    "BLOCKING_ISSUE_CODES",
    "ADVISORY_ISSUE_CODES",
    "ISSUE_MISSING_ACTOR",
    "ISSUE_MISSING_HASH",
    "ISSUE_REF_INACTIVE",
    "ISSUE_UNVERIFIED_CHAIN",
    "ISSUE_STALE",
    "ISSUE_OCR_UNCONFIRMED",
    "ISSUE_AI_UNCONFIRMED",
    "ISSUE_CITATION_NOT_LOCATABLE",
    "QualitySnapshotResult",
    "compute_quality_snapshot",
    "build_snapshot_input_hash",
]
