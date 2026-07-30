"""诊断：全库附注章节与模板的结构差异（只读，不写库）。

用途：
- 回流前预览差异规模（Task 2.5 / 6 的预览与执行共用 `diff_project`）
- 核对「模板改了但既有项目看不到」的实际影响面

用法：
    python backend/scripts/diagnose/diagnose_note_template_drift.py               # 全库摘要
    python ... --project <uuid> --year 2025                                        # 单项目明细
    python ... --section 五、9                                                     # 只看某章节号
    python ... --only-changes                                                      # 只列有差异的

Spec: .kiro/specs/disclosure-note-follow-actual-content/ Task 2.5
"""

from __future__ import annotations

import argparse
import asyncio
import io
import os
import sys
from collections import Counter
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


async def _run(args: argparse.Namespace) -> int:
    import sqlalchemy as sa

    from app.core.database import async_session
    from app.services.note_template_reflow_service import diff_section

    lines: list[str] = []
    counter: Counter[str] = Counter()

    async with async_session() as db:
        where = ["dn.is_deleted = false"]
        params: dict[str, object] = {}
        if args.project:
            where.append("dn.project_id = :pid")
            params["pid"] = args.project
        if args.year:
            where.append("dn.year = :year")
            params["year"] = args.year
        if args.section:
            where.append("dn.note_section = :sec")
            params["sec"] = args.section

        rows = (
            await db.execute(
                sa.text(
                    "SELECT dn.id, dn.note_section, dn.section_title, p.name AS project "
                    "FROM disclosure_notes dn JOIN projects p ON p.id = dn.project_id "
                    f"WHERE {' AND '.join(where)} "
                    "ORDER BY p.name, dn.sort_index, dn.note_section "
                    f"LIMIT {int(args.limit)}"
                ),
                params,
            )
        ).mappings().all()

        lines.append(f"扫描 {len(rows)} 个附注章节")
        for r in rows:
            try:
                d = await diff_section(db, r["id"])
            except Exception as exc:  # noqa: BLE001
                lines.append(f"  [ERR] {r['project']} / {r['note_section']}: {exc}")
                counter["error"] += 1
                continue

            if args.only_changes and not d.has_changes and not d.has_legacy_snapshot:
                continue

            counter["scanned"] += 1
            if d.has_changes:
                counter["with_changes"] += 1
            if d.has_legacy_snapshot:
                counter["legacy_snapshot"] += 1
            counter["missing"] += len(d.missing)
            counter["renamed"] += len(d.renamed)
            counter["column_drift"] += len(d.column_drift)
            counter["guidance_missing"] += len(d.guidance_missing)
            counter["extra"] += len(d.extra)

            head = f"\n[{r['project']}] {d.note_section} {d.section_title}"
            flags = []
            if d.is_local_override:
                flags.append("local_override")
            if d.has_legacy_snapshot:
                flags.append("LEGACY快照")
            if flags:
                head += f"  ({', '.join(flags)})"
            lines.append(head)
            if d.missing:
                lines.append(f"    缺表 {len(d.missing)}: {d.missing}")
            if d.renamed:
                for rc in d.renamed:
                    amb = " ⚠️歧义" if rc.is_ambiguous else ""
                    lines.append(
                        f"    疑似改名[{rc.basis}]{amb}: {rc.note_name} → {list(rc.template_candidates)}"
                    )
            if d.column_drift:
                for c in d.column_drift:
                    lines.append(f"    列头漂移[{c.reason}]: {c.table}")
            if d.guidance_missing:
                lines.append(f"    缺 guidance {len(d.guidance_missing)}: {d.guidance_missing}")
            if d.extra:
                lines.append(f"    模板外的表 {len(d.extra)}: {d.extra}（只报告不删）")
            for n in d.notes:
                lines.append(f"    注: {n}")

    lines.append("\n" + "=" * 60)
    lines.append("汇总：")
    for k in (
        "scanned", "with_changes", "legacy_snapshot",
        "missing", "renamed", "column_drift", "guidance_missing", "extra", "error",
    ):
        lines.append(f"  {k:<18}{counter[k]}")

    text = "\n".join(lines)
    if args.out:
        with io.open(args.out, "w", encoding="utf-8") as f:
            f.write(text + "\n")
        print(f"written -> {args.out} ({len(lines)} lines)")
    else:
        print(text)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="附注章节 ↔ 模板结构差异诊断（只读）")
    ap.add_argument("--project", help="项目 UUID")
    ap.add_argument("--year", type=int, help="年度")
    ap.add_argument("--section", help="章节号，如 五、9")
    ap.add_argument("--only-changes", action="store_true", help="只列有差异或 legacy 的章节")
    ap.add_argument("--limit", type=int, default=500, help="最多扫描多少章节")
    ap.add_argument("--out", help="输出到文件（UTF-8）")
    args = ap.parse_args()
    os.environ.setdefault("DB_DISABLE_SSL", "True")
    # Windows 控制台默认 GBK，报告里的 ⚠️ 等字符会 UnicodeEncodeError
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    except Exception:  # noqa: BLE001
        pass
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
