"""生成 positional 迁移的人工裁决清单（只读，不迁移）。

spec: note-template-columns-and-legacy-snapshot-closure（Task 20）

背景
----
Task 15 dry-run 实测 172 个 legacy 章节判为 ``positional``（表数相等但表名对不上）。
``positional`` **不能自动迁移** —— 按序对齐会搬错表（表名重名 / 非业务名 / 顺序无法保证）。
本脚本把这 172 条逐条列出：legacy 表名/表数 vs 模板表名/表数 + 建议对齐方式 + 风险，
落 ``backend/data/note_legacy_positional_pending.json`` 供人工审阅，**不写库**。

判据真源
--------
复用 ``migrate_legacy_note_snapshots`` 的 ``build_note_plan`` / ``_scan``（同一套分类逻辑），
不另写一份。

用法
----
    python backend/scripts/diagnose/build_note_legacy_positional_pending.py            # dry-run 打印摘要
    python backend/scripts/diagnose/build_note_legacy_positional_pending.py --write    # 落盘 JSON
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
BACKEND = _HERE.parents[2]
REPO_ROOT = _HERE.parents[3]
OUT = BACKEND / "data" / "note_legacy_positional_pending.json"

if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


def _load_migrator():
    path = BACKEND / "scripts" / "fix" / "migrate_legacy_note_snapshots.py"
    spec = importlib.util.spec_from_file_location("mig_for_pending", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


MIG = _load_migrator()


async def _collect() -> list[dict[str, Any]]:
    from app.core.database import async_session

    # limit 必须是整数（_scan 内部 `LIMIT {int(args.limit)}`）；取全量用大值
    ns = argparse.Namespace(
        project=None, year=None, section=None, limit=100000, quiet=True
    )
    async with async_session() as db:
        plans = await MIG._scan(db, ns)

    rows: list[dict[str, Any]] = []
    for plan in plans:
        if plan.kind != "positional":
            continue
        # NotePlan.tables 是 TablePlan 列表（target_name = 按序对齐到的模板表名）
        target_names = [str(getattr(t, "target_name", "") or "") for t in plan.tables]
        dup_targets = [n for n, c in Counter(target_names).items() if c > 1 and n]
        rows.append(
            {
                "project": plan.project,
                "note_section": plan.note_section,
                "section_title": plan.section_title,
                "reason": plan.reason,
                "legacy_table_count": plan.legacy_table_count,
                "planned_table_count": len(plan.tables),
                "legacy_row_total": plan.legacy_row_total,
                "target_names": target_names,
                "duplicate_target_names": dup_targets,
                "suggested": (
                    "先按 target_name 正名 legacy 表 -> 走 by_name"
                    if not dup_targets
                    else "先解重名再对齐（重名表按序对齐会搬错）"
                ),
                "risk": (
                    "HIGH：对齐后目标表名重名，按序搬运可能张冠李戴"
                    if dup_targets
                    else "MED：表数相等且目标名唯一，人工核对顺序后可迁"
                ),
            }
        )
    return rows

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__ or "")
    ap.add_argument("--write", action="store_true", help="落盘 JSON（默认只打印摘要）")
    args = ap.parse_args(argv)

    rows = asyncio.run(_collect())

    by_project: Counter = Counter(r["project"] for r in rows)
    by_risk: Counter = Counter(r["risk"].split("：")[0] for r in rows)
    with_dup = sum(1 for r in rows if r["duplicate_target_names"])

    print(f"[OK] positional 待裁决章节 {len(rows)} 条")
    print(f"[OK] 按项目: {dict(by_project)}")
    print(f"[OK] 按风险: {dict(by_risk)}")
    print(f"[OK] 含重名表(HIGH): {with_dup}")

    if args.write:
        payload = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "_source": "backend/scripts/diagnose/build_note_legacy_positional_pending.py（只读）",
            "_policy": (
                "positional 不得自动迁移（migrate 默认不带 --include-positional）；"
                "本清单供人工逐条裁决：能正名的先正名走 by_name，重名表须先解重名"
            ),
            "summary": {
                "total": len(rows),
                "by_project": dict(by_project),
                "by_risk": dict(by_risk),
                "with_duplicate_names": with_dup,
            },
            "items": rows,
        }
        OUT.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"[OK] wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
