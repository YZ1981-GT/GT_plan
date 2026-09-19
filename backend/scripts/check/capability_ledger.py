"""Capability Ledger v2 model and legacy-reader compatibility.

The v2 schema stores status, evidence and exemption per capability.  Legacy
entry-level exemptions are never treated as blanket exemptions: they are
migrated only when their reason identifies exactly one capability.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

SCHEMA_VERSION = 2
CAPABILITIES = (
    "displayPrefs",
    "agingConfig",
    "version",
    "review",
    "ai",
    "importExport",
    "acnr",
    "persistence",
)
STATUSES = frozenset({"covered", "missing", "exempt", "unknown"})
RUNTIME_CAPABILITIES = frozenset(
    {"displayPrefs", "agingConfig", "version", "review", "ai"}
)

_EXEMPTION_HINTS = {
    "displayPrefs": ("displayprefs", "金额", "余额", "表格", "非结构化"),
    "agingConfig": ("agingconfig", "aging", "账龄"),
    "version": ("version", "版本"),
    "review": ("review", "复核"),
    "ai": (" ai ", "人工智能", "智能生成"),
    "importExport": ("importexport", "导入", "导出"),
    "acnr": ("acnr", "地址坐标", "索引"),
    "persistence": ("persistence", "持久化", "保存", "checklist"),
}


class LedgerFormatError(ValueError):
    """Raised when a v2 document violates the capability-level model."""


def capability_record(
    status: str = "unknown",
    evidence: list[str] | None = None,
    exemption: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build one canonical capability record and reject invalid combinations."""
    if status not in STATUSES:
        raise LedgerFormatError(f"invalid capability status: {status}")
    if evidence is not None and not isinstance(evidence, list):
        raise LedgerFormatError("capability evidence must be a list of strings")
    normalized_evidence = list(evidence or [])
    if any(not isinstance(item, str) or not item.strip() for item in normalized_evidence):
        raise LedgerFormatError(
            "capability evidence must contain non-empty strings only"
        )
    if status == "exempt" and not isinstance(exemption, dict):
        raise LedgerFormatError("exempt status requires capability exemption")
    if status != "exempt" and exemption is not None:
        raise LedgerFormatError("capability exemption requires exempt status")
    return {
        "status": status,
        "evidence": normalized_evidence,
        "exemption": deepcopy(exemption),
    }


def infer_legacy_exemption_capability(exemption: Any) -> str | None:
    """Infer one capability from a legacy exemption, never more than one."""
    if not isinstance(exemption, dict):
        return None
    explicit = exemption.get("capability")
    if explicit in CAPABILITIES:
        return explicit
    reason = str(exemption.get("reason", "")).lower()
    matches = {
        capability
        for capability, hints in _EXEMPTION_HINTS.items()
        if any(hint in reason for hint in hints)
    }
    return next(iter(matches)) if len(matches) == 1 else None


def _normalize_exemption(exemption: dict[str, Any]) -> dict[str, Any]:
    normalized = {
        key: deepcopy(value)
        for key, value in exemption.items()
        if key != "capability"
    }
    if "at" in normalized:
        normalized.setdefault("approvedAt", normalized.pop("at"))
    normalized.setdefault("reviewAt", normalized.get("approvedAt"))
    normalized["legacySource"] = "entry-exemption"
    return normalized


def migrate_legacy_ledger(ledger: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Convert a legacy ledger in memory and return migration warnings."""
    result: dict[str, Any] = {
        "schemaVersion": SCHEMA_VERSION,
        "generatedAt": ledger.get("generatedAt"),
        "capabilities": list(CAPABILITIES),
        "entries": {},
    }
    warnings: list[str] = []
    for wp_code, old_entry in ledger.get("entries", {}).items():
        detected = old_entry.get("detected", {})
        shell_wrapped = bool(old_entry.get("shellWrapped"))
        records = {
            capability: capability_record()
            for capability in CAPABILITIES
        }
        for capability in CAPABILITIES:
            if detected.get(capability) is True:
                records[capability] = capability_record(
                    "covered", [f"legacy:detected.{capability}"]
                )
            elif shell_wrapped and capability in RUNTIME_CAPABILITIES:
                records[capability] = capability_record(
                    "covered", ["legacy:shellWrapped"]
                )

        old_exemption = old_entry.get("exemption")
        exempt_capability = infer_legacy_exemption_capability(old_exemption)
        if old_exemption and exempt_capability is None:
            warnings.append(
                f"{wp_code}: entry exemption cannot be assigned to exactly one capability"
            )
        elif exempt_capability and records[exempt_capability]["status"] != "covered":
            records[exempt_capability] = capability_record(
                "exempt", exemption=_normalize_exemption(old_exemption)
            )

        new_entry = {
            key: deepcopy(old_entry.get(key))
            for key in ("componentType", "entryFile")
            if old_entry.get(key) is not None
        }
        new_entry["capabilities"] = records
        result["entries"][wp_code] = new_entry
    return result, warnings


def normalize_ledger(ledger: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Read v1 or v2 and return one canonical v2 representation."""
    if ledger.get("schemaVersion") != SCHEMA_VERSION:
        return migrate_legacy_ledger(ledger)

    normalized = deepcopy(ledger)
    normalized["capabilities"] = list(CAPABILITIES)
    for wp_code, entry in normalized.get("entries", {}).items():
        if "exemption" in entry:
            raise LedgerFormatError(
                f"{wp_code}: v2 forbids entry-level exemption"
            )
        records = entry.setdefault("capabilities", {})
        unknown = set(records) - set(CAPABILITIES)
        if unknown:
            raise LedgerFormatError(
                f"{wp_code}: unknown capabilities: {sorted(unknown)}"
            )
        for capability in CAPABILITIES:
            raw = records.get(capability, {})
            status = raw.get("status", "unknown")
            exemption = raw.get("exemption")
            if status == "exempt" and not isinstance(exemption, dict):
                raise LedgerFormatError(
                    f"{wp_code}.{capability}: exempt status requires exemption"
                )
            if status != "exempt" and exemption is not None:
                raise LedgerFormatError(
                    f"{wp_code}.{capability}: exemption requires exempt status"
                )
            records[capability] = capability_record(
                status, raw.get("evidence", []), exemption
            )
    return normalized, []
