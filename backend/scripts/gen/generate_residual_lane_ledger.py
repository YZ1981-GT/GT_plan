"""Task 4.1：residual lane 交接清册（机器生成，不手填）。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / task 4.1
AC: 12.1, 12.8, 12.9

从 current-state + manifest + cycle projection + representation 预检现算，
每条 independent entry 一行。4.2~4.8 逐循环消费本清册做对账。

输出幂等（不含时间戳），`--check` / `--write`。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
import sys
from typing import Any

_BACKEND = pathlib.Path(__file__).resolve().parents[2]
_REPO = _BACKEND.parent
_DATA = _BACKEND / "data"

SCHEMA_VERSION = "residual-lane-ledger:v1"
OWNER_TASK = "4.1"
SPEC = "workpaper-html-onlyoffice-bidirectional-writeback-closure"

OUTPUT_PATH = _DATA / "workpaper_sync_residual_lane_ledger.json"
CURRENT_STATE_PATH = _DATA / "workpaper_sync_current_state.json"
MANIFEST_PATH = _DATA / "workpaper_sync_entry_manifest.json"
CYCLE_PROJ_PATH = _DATA / "workpaper_sync_cycle_current_projection.json"
REPRESENTATION_PREFLIGHT_PATH = (
    _REPO / ".kiro" / "specs" / SPEC / "evidence" / "phase4-representation-preflight.json"
)

# cycle letter → task id 映射（从 tasks.md 现算，复用 task66 生成器的函数）
for _extra in (str(_BACKEND), str(_BACKEND / "scripts" / "gen")):
    if _extra not in sys.path:
        sys.path.insert(0, _extra)


class LedgerError(RuntimeError):
    pass


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _cycle_letter(entry_id: str) -> str | None:
    """从 entry_id 提取循环字母：`xlsx/gt-d4-…` → `D`、`docx/gt-a10-…` → `A`。"""
    m = re.search(r"/gt-([a-z])", entry_id)
    if m:
        return m.group(1).upper()
    # b60 特殊
    if "/b60/" in entry_id:
        return "B"
    # d4 子 tab
    if "/d4/" in entry_id:
        return "D"
    # cash-flow-verification
    if "cash-flow" in entry_id:
        return "A"
    return None


def _owner_task_for_cycle(letter: str | None) -> str:
    """cycle letter → 4.x owner task。"""
    mapping = {
        "D": "4.2", "E": "4.2",
        "F": "4.3",
        "G": "4.4", "H": "4.4", "I": "4.4",
        "J": "4.5", "K": "4.5", "L": "4.5",
        "M": "4.6", "N": "4.6",
        "A": "4.7", "B": "4.7", "C": "4.7",
        "S": "4.8",
    }
    if letter and letter in mapping:
        return mapping[letter]
    return "4.8"  # 跨循环共享 / Word / custom / opaque


def _representation_status(entry_id: str, preflight: dict[str, Any] | None) -> str:
    """从 representation 预检结果取状态。"""
    if preflight is None:
        return "preflight_not_available"
    by_entry = preflight.get("by_entry") or {}
    status = by_entry.get(entry_id, {}).get("status")
    return status or "not_in_preflight"


def build_record() -> dict[str, Any]:
    cs_bytes = CURRENT_STATE_PATH.read_bytes()
    cs = json.loads(cs_bytes.decode("utf-8"))
    manifest_bytes = MANIFEST_PATH.read_bytes()
    manifest = json.loads(manifest_bytes.decode("utf-8"))

    # representation preflight（可选——可能还没跑过）
    preflight: dict[str, Any] | None = None
    if REPRESENTATION_PREFLIGHT_PATH.is_file():
        preflight = json.loads(REPRESENTATION_PREFLIGHT_PATH.read_text(encoding="utf-8"))

    # 按 entry_id 索引 manifest entries
    manifest_by_id = {e["entry_id"]: e for e in manifest["entries"]}

    # cycle projection 按 entry_id 索引
    cycle_proj: dict[str, dict[str, Any]] = {}
    if CYCLE_PROJ_PATH.is_file():
        cp = json.loads(CYCLE_PROJ_PATH.read_text(encoding="utf-8"))
        groups = cp.get("groups") or {}
        if isinstance(groups, dict):
            for group_key, group in groups.items():
                if not isinstance(group, dict):
                    continue
                for entry in group.get("entries") or []:
                    if isinstance(entry, dict):
                        sel = group.get("selection")
                        cycle_proj[entry.get("entry_id", "")] = {
                            "cycle_group": group_key,
                            "selection_rule": sel if isinstance(sel, str) else (sel.get("rule") if isinstance(sel, dict) else None),
                        }

    rows: list[dict[str, Any]] = []
    for entry in cs["entries"]:
        eid = entry["entry_id"]
        if not entry.get("independent_entry"):
            continue  # parent duplicates 不进清册（跟随 effective_entry_id）

        cycle = _cycle_letter(eid)
        m_entry = manifest_by_id.get(eid, {})

        row: dict[str, Any] = {
            "entry_id": eid,
            "owner_task": _owner_task_for_cycle(cycle),
            "cycle": cycle,
            "document_type": entry.get("document_type"),
            "capability": entry.get("capability"),
            "capability_target": entry.get("capability_target"),
            "capability_target_blocked_by": entry.get("capability_target_blocked_by"),
            "migration_state": entry.get("migration_state"),
            "acceptance_state": entry.get("acceptance_state"),
            "adjudication_state": entry.get("adjudication_state"),
            "host_path": entry.get("host_path"),
            "html_counterpart_verdict": entry.get("html_counterpart_verdict"),
            "adapter_id": entry.get("adapter_id"),
            "contract_id": entry.get("contract_id"),
            "provider_module": entry.get("provider_module"),
            "runtime_readiness": entry.get("runtime_readiness"),
            "static_registration_blocked_reason": entry.get("static_registration_blocked_reason"),
            "representation_status": _representation_status(eid, preflight),
            "has_browser_evidence": bool(m_entry.get("hasBrowserEvidence")),
            "has_contract_evidence": bool(m_entry.get("hasContractEvidence")),
            "sync_editor_host_mounted": bool(m_entry.get("sync_editor_host_mounted")),
            "cycle_projection": cycle_proj.get(eid),
            "rollback_condition": (
                "revert overlay per-entry override + regenerate manifest"
                if entry.get("adjudication_state") == "terminal"
                else "no override to revert"
            ),
            "release_condition": (
                "representation already_consistent + runtime_readiness ready + browser evidence"
                if entry.get("capability") == "bidirectional"
                else f"resolve {entry.get('capability_target_blocked_by') or 'N/A'}"
            ),
        }
        rows.append(row)

    rows.sort(key=lambda r: (r["owner_task"], r["entry_id"]))

    # 按 owner_task 分组统计
    by_owner: dict[str, dict[str, int]] = {}
    for row in rows:
        ot = row["owner_task"]
        bucket = by_owner.setdefault(ot, {"total": 0, "bidirectional": 0, "pending": 0, "blocked": 0})
        bucket["total"] += 1
        if row["capability"] == "bidirectional":
            bucket["bidirectional"] += 1
        if row["acceptance_state"] != "accepted":
            bucket["pending"] += 1
        if row.get("capability_target_blocked_by"):
            bucket["blocked"] += 1

    return {
        "schema_version": SCHEMA_VERSION,
        "spec": SPEC,
        "owner_task": OWNER_TASK,
        "description": (
            "residual lane 交接清册：每条 independent entry 一行，"
            "含 owner / capability / representation / evidence / 回滚与解除条件。"
            "4.2~4.8 逐循环消费本清册做对账。"
        ),
        "generator": f"backend/scripts/gen/{pathlib.Path(__file__).name}",
        "input_digests": {
            "current_state": _sha256(cs_bytes),
            "manifest": _sha256(manifest_bytes),
            "representation_preflight_available": preflight is not None,
        },
        "summary": {
            "independent_entry_count": len(rows),
            "by_owner_task": dict(sorted(by_owner.items())),
        },
        "entries": rows,
    }


def _canonical_text(record: dict[str, Any]) -> str:
    return json.dumps(record, ensure_ascii=False, indent=2, sort_keys=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__ or "")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)

    record = build_record()
    text = _canonical_text(record)
    if args.write:
        OUTPUT_PATH.write_text(text, encoding="utf-8")
        print(f"[write] {OUTPUT_PATH.name}")
        print(json.dumps(record["summary"], ensure_ascii=False, indent=2))
        return 0
    if not OUTPUT_PATH.is_file():
        raise LedgerError(f"{OUTPUT_PATH.name} 不存在 —— 先 --write")
    on_disk = OUTPUT_PATH.read_text(encoding="utf-8")
    if on_disk != text:
        raise LedgerError(
            f"{OUTPUT_PATH.name} 与现算不一致（磁盘 "
            f"{_sha256(on_disk.encode('utf-8'))[:12]} vs 现算 "
            f"{_sha256(text.encode('utf-8'))[:12]}）—— 重跑 --write"
        )
    print(f"[check] {OUTPUT_PATH.name} 与现算逐字节一致")
    print(json.dumps(record["summary"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
