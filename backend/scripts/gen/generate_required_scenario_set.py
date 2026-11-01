"""Task 6.1：从 manifest 的 scenario_profile 为每条 independent entry 生成 required scenario set。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / task 6.1
AC: 12.1

每条 entry 自己的 digest——不得用代表 entry、同循环或历史 run 替代。
输出幂等，`--check` / `--write`。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
from typing import Any

_BACKEND = pathlib.Path(__file__).resolve().parents[2]
_DATA = _BACKEND / "data"

SCHEMA_VERSION = "required-scenario-set:v1"
OUTPUT_PATH = _DATA / "workpaper_sync_required_scenario_set.json"
MANIFEST_PATH = _DATA / "workpaper_sync_entry_manifest.json"


class ScenarioSetError(RuntimeError):
    pass


def _sha256(data: bytes) -> str:
    # Windows 的 Git checkout 可能把文本换成 CRLF；输入摘要描述提交中的 JSON 载荷，
    # 因此先归一换行，保证 Windows / Linux 结果一致。
    canonical = data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return hashlib.sha256(canonical).hexdigest()


def _scenario_digest(profile: dict[str, Any]) -> str:
    """scenario profile 的确定性 digest——按排序后的 JSON 算。"""
    canonical = json.dumps(profile, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_record() -> dict[str, Any]:
    manifest_bytes = MANIFEST_PATH.read_bytes()
    manifest = json.loads(manifest_bytes.decode("utf-8"))

    entries: list[dict[str, Any]] = []
    for e in manifest["entries"]:
        if not e.get("independent_entry", True):
            continue  # parent duplicates 跟随 effective_entry_id
        profile = e.get("scenario_profile") or {}
        cap = e.get("capability")
        entries.append({
            "entry_id": e["entry_id"],
            "capability": cap,
            "document_type": e.get("document_type"),
            "scenario_profile_digest": _scenario_digest(profile),
            "scenario_profile_ids": sorted(profile.get("scenario_profile_ids") or []),
            "editability": profile.get("editability"),
            "room_model": profile.get("room_model"),
            "requires_browser_evidence": cap == "bidirectional",
            "requires_contract_evidence": cap == "bidirectional",
        })

    entries.sort(key=lambda r: r["entry_id"])

    # 按 capability 统计
    from collections import Counter
    by_cap = dict(Counter(e["capability"] for e in entries))

    # 按 scenario_profile_digest 统计去重
    unique_profiles = len({e["scenario_profile_digest"] for e in entries})

    return {
        "schema_version": SCHEMA_VERSION,
        "spec": "workpaper-html-onlyoffice-bidirectional-writeback-closure",
        "owner_task": "6.1",
        "description": (
            "每条 independent entry 的 required scenario set digest + evidence 要求。"
            "4.2~4.8 / 6.3 消费本产物判断「哪些 entry 需要哪些 scenario evidence」。"
        ),
        "generator": f"backend/scripts/gen/{pathlib.Path(__file__).name}",
        "manifest_digest": _sha256(manifest_bytes),
        "summary": {
            "independent_entry_count": len(entries),
            "unique_scenario_profiles": unique_profiles,
            "by_capability": by_cap,
            "requiring_browser_evidence": sum(1 for e in entries if e["requires_browser_evidence"]),
            "requiring_contract_evidence": sum(1 for e in entries if e["requires_contract_evidence"]),
        },
        "entries": entries,
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
        raise ScenarioSetError(f"{OUTPUT_PATH.name} 不存在 —— 先 --write")
    on_disk = OUTPUT_PATH.read_text(encoding="utf-8")
    if on_disk != text:
        raise ScenarioSetError(f"{OUTPUT_PATH.name} 与现算不一致 —— 重跑 --write")
    print(f"[check] {OUTPUT_PATH.name} 与现算逐字节一致")
    print(json.dumps(record["summary"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
