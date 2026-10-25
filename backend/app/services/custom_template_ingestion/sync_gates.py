"""Task 14：四 sync gate 只读探测（未归零则诚实 BLOCKED）。"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.services.custom_template_ingestion.namespace_migration import probe_namespace_gates

__all__ = [
    "SyncGateReport",
    "probe_all_sync_gates",
    "assert_all_sync_gates_clear",
]

_REPO = Path(__file__).resolve().parents[4]
_ELIGIBILITY = _REPO / "backend" / "data" / "workpaper_sync_task72_pre_delete_eligibility.json"


@dataclass(frozen=True, slots=True)
class SyncGateReport:
    unified_room: bool
    multi_resolver: bool
    durable_application: bool
    entry_namespace: bool
    blockers: tuple[str, ...]

    @property
    def all_clear(self) -> bool:
        return (
            self.unified_room
            and self.multi_resolver
            and self.durable_application
            and self.entry_namespace
        )


def probe_all_sync_gates() -> SyncGateReport:
    ns = probe_namespace_gates()
    blockers = list(ns.blockers)

    unified_room = False
    durable = False
    if _ELIGIBILITY.exists():
        data = json.loads(_ELIGIBILITY.read_text(encoding="utf-8"))
        # durable / room 旗标仍登记在 writer_gate / legacy baseline —— 诚实读 five_counts 不可用时记 blocker
        live = data.get("multi_resolver_live") or {}
        # Room / durable 尚未有独立 PASS artifact：缺省视为未清
        if not data.get("sync_unified_room_cleared"):
            blockers.append("SYNC-UNIFIED-ROOM: not cleared in eligibility artifact")
        else:
            unified_room = True
        if not data.get("sync_durable_application_cleared"):
            blockers.append("SYNC-DURABLE-APPLICATION: not cleared in eligibility artifact")
        else:
            durable = True
        _ = live  # reserved for future room binding checks
    else:
        blockers.append("eligibility artifact missing")

    return SyncGateReport(
        unified_room=unified_room,
        multi_resolver=ns.multi_resolver_cleared,
        durable_application=durable,
        entry_namespace=ns.entry_namespace_unified,
        blockers=tuple(dict.fromkeys(blockers)),
    )


def assert_all_sync_gates_clear() -> None:
    report = probe_all_sync_gates()
    if not report.all_clear:
        raise RuntimeError("SYNC gates not clear: " + "; ".join(report.blockers))
