"""只读验证 pending entry 在假设终裁 bidirectional 后能否通过真实目标注册。

不会修改 manifest、overlay 或数据库。探针把 patched manifest 放仓库根 tmp 目录，逐 entry
绑定一张现有 current representation；结果用于决定哪些 entry 可进入 reviewed 终裁，不能
替代真实 OnlyOffice scenario evidence。
"""
from __future__ import annotations

import argparse
import asyncio
import copy
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import sqlalchemy as sa

ROOT = Path(__file__).resolve().parents[3]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.core.database import async_session
from app.services.workpaper_sync import entry_profile as EP
from app.services.workpaper_sync.adapters.registry import (
    DELIVERED_PER_ENTRY_CONTRACTS,
    build_production_registry,
)
from app.services.workpaper_sync.target_bound_registration import (
    bind_registration_to_target,
    clear_target_registration_cache,
)

MANIFEST = BACKEND / "data/workpaper_sync_entry_manifest.json"
TMP = ROOT / "tmp_workpaper_sync_runtime_probe"
PROBE_MANIFEST = TMP / "pending_probe_manifest.json"
OUTPUT = (
    ROOT / ".kiro/specs/workpaper-html-onlyoffice-bidirectional-writeback-closure/"
    "evidence/phase4-pending-runtime-readiness.json"
)


async def collect() -> dict[str, Any]:
    original = json.loads(MANIFEST.read_text(encoding="utf-8"))
    ledger = {str(row["entry_id"]): row for row in DELIVERED_PER_ENTRY_CONTRACTS}
    pending = [
        row for row in original["entries"]
        if row.get("independent_entry") and row.get("capability") is None
        and row["entry_id"] in ledger
    ]
    results: list[dict[str, Any]] = []
    old_path = EP.ENTRY_MANIFEST_PATH
    TMP.mkdir(parents=True, exist_ok=True)
    try:
        async with async_session() as session:
            for source in pending:
                entry_id = str(source["entry_id"])
                wp_id = (
                    await session.execute(
                        sa.text(
                            "SELECT wp_id FROM working_paper_sync_entry_state "
                            "WHERE entry_id=:entry_id ORDER BY wp_id LIMIT 1"
                        ),
                        {"entry_id": entry_id},
                    )
                ).scalar_one_or_none()
                if wp_id is None:
                    results.append({
                        "entry_id": entry_id,
                        "verdict": "no_current_representation",
                    })
                    continue
                patched = copy.deepcopy(original)
                target = next(
                    row for row in patched["entries"] if row["entry_id"] == entry_id
                )
                target.update({
                    "capability": "bidirectional",
                    "adjudication_state": "terminal",
                    "adjudication_source": "pending_runtime_probe",
                    "adapter_id": str(ledger[entry_id]["contract_id"]),
                })
                for key in (
                    "capability_verdict_stage", "capability_target",
                    "capability_target_blocked_by",
                ):
                    target.pop(key, None)
                PROBE_MANIFEST.write_text(
                    json.dumps(patched, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                EP.ENTRY_MANIFEST_PATH = PROBE_MANIFEST
                EP.load_entry_manifest.cache_clear()
                clear_target_registration_cache()
                registry = build_production_registry(manifest=patched)
                try:
                    registration = await bind_registration_to_target(
                        session=session,
                        registry=registry,
                        entry_id=entry_id,
                        wp_id=wp_id,
                    )
                except Exception as exc:  # 每条失败必须继续形成完整清册
                    results.append({
                        "entry_id": entry_id,
                        "verdict": "failed",
                        "error_type": type(exc).__name__,
                        "error_code": str(getattr(exc, "error_code", "")),
                        "message": str(exc)[:800],
                    })
                else:
                    results.append({
                        "entry_id": entry_id,
                        "verdict": "runtime_ready",
                        "adapter_id": registration.adapter_id,
                        "bundle_sha256": registration.bundle.bundle_sha256,
                    })
    finally:
        EP.ENTRY_MANIFEST_PATH = old_path
        EP.load_entry_manifest.cache_clear()
        clear_target_registration_cache()
        PROBE_MANIFEST.unlink(missing_ok=True)
    counts = Counter(row["verdict"] for row in results)
    return {
        "schema_version": "pending-entry-runtime-readiness:v1",
        "manifest_digest": original.get("manifest_digest"),
        "source_digest": original.get("source_digest"),
        "candidate_count": len(pending),
        "counts": dict(sorted(counts.items())),
        "database_mutated": False,
        "real_onlyoffice_executed": False,
        "meaning": "runtime_ready 只证明目标 representation 上 adapter/bundle/contract 可注册，不等于验收完成",
        "results": results,
    }


async def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    report = await collect()
    rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.check:
        actual = OUTPUT.read_text(encoding="utf-8") if OUTPUT.is_file() else None
        if actual != rendered:
            print(f"[FAIL] stale: {OUTPUT.relative_to(ROOT)}")
            return 1
        print(f"[OK] pending runtime projection {report['counts']}")
        return 0
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(rendered, encoding="utf-8", newline="\n")
    print(f"[OK] wrote {OUTPUT.relative_to(ROOT)} {report['counts']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run()))
