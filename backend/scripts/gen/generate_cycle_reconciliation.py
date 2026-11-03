"""Tasks 4.2~4.8：从 residual lane 清册按 owner_task 逐循环对账。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / tasks 4.2~4.8
AC: 1.4, 12.1, 12.8, 12.9

消费 residual_lane_ledger.json + required_scenario_set.json + runtime_evidence_projection.json，
逐 entry 确认事实一致性。输出不含时间戳，`--check` / `--write`。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
from typing import Any

_BACKEND = pathlib.Path(__file__).resolve().parents[2]
_DATA = _BACKEND / "data"

SCHEMA_VERSION = "cycle-reconciliation:v1"
OUTPUT_PATH = _DATA / "workpaper_sync_cycle_reconciliation.json"
LANE_PATH = _DATA / "workpaper_sync_residual_lane_ledger.json"
SCENARIO_PATH = _DATA / "workpaper_sync_required_scenario_set.json"
EVIDENCE_PATH = _DATA / "workpaper_sync_runtime_evidence_projection.json"


class ReconcileError(RuntimeError):
    pass


def _sha256(data: bytes) -> str:
    # Windows 的 Git checkout 可能把文本换成 CRLF；输入摘要描述提交中的 JSON 载荷，
    # 因此先归一换行，保证 Windows / Linux 结果一致。
    canonical = data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return hashlib.sha256(canonical).hexdigest()


def build_record() -> dict[str, Any]:
    lane_bytes = LANE_PATH.read_bytes()
    lane = json.loads(lane_bytes.decode("utf-8"))
    sc = json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))
    ev = json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))

    sc_by_id = {e["entry_id"]: e for e in sc["entries"]}
    ev_by_id = {e["entry_id"]: e for e in ev["entries"]}

    groups: dict[str, dict[str, Any]] = {}
    for row in lane["entries"]:
        ot = row["owner_task"]
        group = groups.setdefault(ot, {
            "owner_task": ot,
            "entries": [],
            "counts": {"total": 0, "bidirectional": 0, "pending": 0, "blocked": 0,
                       "evidence_covered": 0, "evidence_missing": 0, "evidence_not_required": 0},
        })
        eid = row["entry_id"]
        sc_entry = sc_by_id.get(eid, {})
        ev_entry = ev_by_id.get(eid, {})

        reconciled: dict[str, Any] = {
            "entry_id": eid,
            "capability": row["capability"],
            "migration_state": row["migration_state"],
            "acceptance_state": row["acceptance_state"],
            "adapter_id": row["adapter_id"],
            "contract_id": row["contract_id"],
            "provider_module": row["provider_module"],
            "representation_status": row["representation_status"],
            "evidence_status": ev_entry.get("evidence_status", "unknown"),
            "scenario_profile_digest": sc_entry.get("scenario_profile_digest"),
            "has_browser_evidence": row.get("has_browser_evidence", False),
            "has_contract_evidence": row.get("has_contract_evidence", False),
            "blocked_by": row.get("capability_target_blocked_by"),
            "release_condition": row["release_condition"],
        }

        # 一致性标记
        issues: list[str] = []
        if reconciled["capability"] == "bidirectional" and not reconciled["adapter_id"]:
            issues.append("bidirectional_without_adapter")
        if reconciled["capability"] == "bidirectional" and reconciled["evidence_status"] == "missing":
            issues.append("bidirectional_without_runtime_evidence")
        if reconciled["representation_status"] not in ("already_consistent", "preflight_not_available", "not_in_preflight"):
            issues.append(f"representation_{reconciled['representation_status']}")
        reconciled["issues"] = issues

        group["entries"].append(reconciled)
        c = group["counts"]
        c["total"] += 1
        if reconciled["capability"] == "bidirectional":
            c["bidirectional"] += 1
        if reconciled["acceptance_state"] != "accepted":
            c["pending"] += 1
        if reconciled.get("blocked_by"):
            c["blocked"] += 1
        es = reconciled["evidence_status"]
        if es == "covered":
            c["evidence_covered"] += 1
        elif es == "missing":
            c["evidence_missing"] += 1
        else:
            c["evidence_not_required"] += 1

    for g in groups.values():
        g["entries"].sort(key=lambda r: r["entry_id"])

    return {
        "schema_version": SCHEMA_VERSION,
        "spec": "workpaper-html-onlyoffice-bidirectional-writeback-closure",
        "owner_tasks": "4.2~4.8",
        "description": "逐循环对账报告：从 residual lane + scenario set + evidence projection 交叉核。",
        "generator": f"backend/scripts/gen/{pathlib.Path(__file__).name}",
        "input_digests": {
            "lane": _sha256(lane_bytes),
            "scenario_set": _sha256(SCENARIO_PATH.read_bytes()),
            "evidence_projection": _sha256(EVIDENCE_PATH.read_bytes()),
        },
        "groups": dict(sorted(groups.items())),
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
        for ot, g in sorted(record["groups"].items()):
            print(f"  {ot}: {json.dumps(g['counts'], ensure_ascii=False)}")
        return 0
    if not OUTPUT_PATH.is_file():
        raise ReconcileError(f"{OUTPUT_PATH.name} 不存在 —— 先 --write")
    on_disk = OUTPUT_PATH.read_text(encoding="utf-8")
    if on_disk != text:
        raise ReconcileError(f"{OUTPUT_PATH.name} 与现算不一致 —— 重跑 --write")
    print(f"[check] {OUTPUT_PATH.name} 与现算逐字节一致")
    for ot, g in sorted(record["groups"].items()):
        print(f"  {ot}: {json.dumps(g['counts'], ensure_ascii=False)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
