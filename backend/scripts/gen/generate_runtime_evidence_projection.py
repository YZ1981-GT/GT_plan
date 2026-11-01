"""Task 6.2：runtime evidence current projection（从 PG 现读 + manifest 交叉）。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / task 6.2
AC: 12.1

从 PG 的 working_paper_sync_test_run + manifest 的 required scenario set 现算
每条 independent entry 的 acceptance 状态。不信 overlay 布尔摘要。

🔴 本脚本可以在 PG 不可达时降级运行（把全部 entry 标为 evidence_missing），
因为 PG 连不上恰恰证明「没有 runtime evidence」这一事实。

输出幂等（不含时间戳），`--check` / `--write`。
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import pathlib
import sys
from typing import Any

_BACKEND = pathlib.Path(__file__).resolve().parents[2]
_DATA = _BACKEND / "data"

if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

SCHEMA_VERSION = "runtime-evidence-projection:v1"
OUTPUT_PATH = _DATA / "workpaper_sync_runtime_evidence_projection.json"
SCENARIO_SET_PATH = _DATA / "workpaper_sync_required_scenario_set.json"


class ProjectionError(RuntimeError):
    pass


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


async def _query_test_runs() -> dict[str, Any]:
    """从 PG 读 working_paper_sync_test_run，降级为空。"""
    try:
        from app.core.config import settings
        if not str(settings.DATABASE_URL).startswith("postgresql"):
            return {"status": "not_postgresql", "runs": [], "total": 0}
        from sqlalchemy.ext.asyncio import create_async_engine
        from sqlalchemy.pool import NullPool
        import sqlalchemy as sa

        engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
        try:
            async with engine.connect() as conn:
                rows = (await conn.execute(
                    sa.text("SELECT COUNT(*) FROM working_paper_sync_test_run")
                )).scalar()
                # 如果有行，取 entry_id 分组计数
                if rows and rows > 0:
                    result = (await conn.execute(
                        sa.text(
                            "SELECT entry_id, COUNT(*) as cnt "
                            "FROM working_paper_sync_test_run "
                            "GROUP BY entry_id ORDER BY entry_id"
                        )
                    )).mappings().all()
                    return {
                        "status": "connected",
                        "total": rows,
                        "runs": [dict(r) for r in result],
                    }
                return {"status": "connected", "total": 0, "runs": []}
        finally:
            await engine.dispose()
    except Exception as exc:  # noqa: BLE001
        return {"status": f"degraded:{type(exc).__name__}", "total": 0, "runs": []}


def build_record() -> dict[str, Any]:
    sc_bytes = SCENARIO_SET_PATH.read_bytes()
    scenario_set = json.loads(sc_bytes.decode("utf-8"))

    pg_facts = asyncio.run(_query_test_runs())
    runs_by_entry = {r["entry_id"]: r["cnt"] for r in pg_facts["runs"]}

    entries: list[dict[str, Any]] = []
    for sc in scenario_set["entries"]:
        eid = sc["entry_id"]
        run_count = runs_by_entry.get(eid, 0)
        needs_evidence = sc["requires_browser_evidence"] or sc["requires_contract_evidence"]
        entries.append({
            "entry_id": eid,
            "capability": sc["capability"],
            "scenario_profile_digest": sc["scenario_profile_digest"],
            "requires_browser_evidence": sc["requires_browser_evidence"],
            "requires_contract_evidence": sc["requires_contract_evidence"],
            "test_run_count": run_count,
            "evidence_status": (
                "not_required" if not needs_evidence
                else "covered" if run_count > 0
                else "missing"
            ),
        })

    entries.sort(key=lambda r: r["entry_id"])
    from collections import Counter
    by_status = dict(Counter(e["evidence_status"] for e in entries))

    return {
        "schema_version": SCHEMA_VERSION,
        "spec": "workpaper-html-onlyoffice-bidirectional-writeback-closure",
        "owner_task": "6.2",
        "description": (
            "runtime evidence current projection：从 PG test_run + required scenario set "
            "现算每条 entry 的 acceptance 状态。"
        ),
        "generator": f"backend/scripts/gen/{pathlib.Path(__file__).name}",
        "scenario_set_digest": _sha256(sc_bytes),
        "pg_facts": {
            "status": pg_facts["status"],
            "total_test_runs": pg_facts["total"],
            "entries_with_runs": len(runs_by_entry),
        },
        "summary": {
            "independent_entry_count": len(entries),
            "evidence_status_distribution": by_status,
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
        print(f"pg: {record['pg_facts']}")
        return 0
    if not OUTPUT_PATH.is_file():
        raise ProjectionError(f"{OUTPUT_PATH.name} 不存在 —— 先 --write")
    on_disk = OUTPUT_PATH.read_text(encoding="utf-8")
    if on_disk != text:
        raise ProjectionError(f"{OUTPUT_PATH.name} 与现算不一致 —— 重跑 --write")
    print(f"[check] {OUTPUT_PATH.name} 与现算逐字节一致")
    print(json.dumps(record["summary"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
