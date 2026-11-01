"""报告：已被底稿推送过的附注章节，其推送列头与附注模板是否一致（只读）。

spec: note-table-structure-formula-pull-closure R16（design §7）

**为什么要有这张报告**：附注表格的表头有两个来源 ——
  ① 模板种子化：`_tables[].headers` 直接取 `note_template_{soe,listed}.json`，必然对；
  ② 底稿推送：前端 `buildXSyncPayload` 的 `columns` 写进 `table_data._sub_table_columns`，
     投影器据此产出表头 ⇒ **前端那份硬编码列头一旦与模板不一致，附注里显示的就是错的**。

R13 在 D2 上实测到这类不一致（4 处标签列头），并给 D2 建了逐位对拍守卫。本脚本把同一判据
铺到**全部已推送章节**，量化存量影响面：哪些项目、哪个章节、哪张表、哪一列与模板不符。

🔴 只读：不写任何表。修正存量需重新推送（载荷权威源在前端，后端无法单独重建），
或用 `backend/scripts/fix/fix_pushed_note_header_labels.py` 只改标签列文字。

用法：
    python backend/scripts/analyze/report_pushed_note_header_drift.py
    python backend/scripts/analyze/report_pushed_note_header_drift.py --section 八、5
    python backend/scripts/analyze/report_pushed_note_header_drift.py --json out.json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from collections import Counter
from pathlib import Path
from typing import Any

BACKEND = Path(__file__).resolve().parents[2]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import sqlalchemy as sa  # noqa: E402

DATA = BACKEND / "data"


def _load_templates() -> dict[tuple[str, str, str], list[str]]:
    """{(口径, 章节号, 表名): headers}；两版都读，口径只用于回报。"""
    out: dict[tuple[str, str, str], list[str]] = {}
    for std in ("soe", "listed"):
        raw = json.loads((DATA / f"note_template_{std}.json").read_text(encoding="utf-8"))
        for sec in raw.get("sections") or []:
            num = str(sec.get("section_number") or "").strip()
            if not num:
                continue
            for t in sec.get("tables") or []:
                name = str((t or {}).get("name") or "").strip()
                headers = [str(h) for h in ((t or {}).get("headers") or [])]
                if name and headers:
                    out[(std, num, name)] = headers
    return out


def _pushed_labels(cols: Any) -> list[str]:
    if not isinstance(cols, list):
        return []
    return [str((c or {}).get("label") or "") for c in cols if isinstance(c, dict)]


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--section", help="只看某个章节号（如 八、5）")
    ap.add_argument("--json", dest="json_out", help="把结果写成 JSON")
    args = ap.parse_args()

    os.environ.setdefault(
        "DATABASE_URL", "postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/audit_platform")
    from app.core.database import engine  # noqa: PLC0415

    tpl = _load_templates()
    stats = Counter()
    findings: list[dict[str, Any]] = []

    async with engine.connect() as conn:
        rows = (await conn.execute(sa.text("""
            SELECT d.project_id, p.name AS project_name, p.template_type,
                   d.note_section, d.section_title, d.table_data
              FROM disclosure_notes d
              JOIN projects p ON p.id = d.project_id
             WHERE d.table_data ? '_sub_table_columns'
               AND (p.is_deleted IS NULL OR p.is_deleted = false)
             ORDER BY p.name, d.note_section
        """))).mappings().all()

        for r in rows:
            section = str(r["note_section"] or "").strip()
            if args.section and section != args.section:
                continue
            td = r["table_data"]
            if isinstance(td, str):
                td = json.loads(td)
            pushed = (td or {}).get("_sub_table_columns") or {}
            if not isinstance(pushed, dict):
                continue
            stats["sections"] += 1
            std = "soe" if str(r["template_type"] or "").lower().startswith("soe") else "listed"
            for table_name, cols in pushed.items():
                stats["tables"] += 1
                labels = _pushed_labels(cols)
                want = tpl.get((std, section, table_name)) or tpl.get(
                    ("soe" if std == "listed" else "listed", section, table_name))
                if want is None:
                    stats["table_not_in_template"] += 1
                    continue
                if labels == want:
                    stats["match"] += 1
                    continue
                stats["mismatch"] += 1
                # 只差空白 ⇒ 典型的「前端自编列头」；列数不同 ⇒ 结构性差异
                squashed_same = [x.replace(" ", "").replace("\u3000", "") for x in labels] == \
                    [x.replace(" ", "").replace("\u3000", "") for x in want]
                kind = ("whitespace_only" if squashed_same
                        else "column_count" if len(labels) != len(want) else "text")
                stats[f"mismatch_{kind}"] += 1
                findings.append({
                    "project": r["project_name"],
                    "project_id": str(r["project_id"]),
                    "section": section,
                    "section_title": r["section_title"],
                    "table": table_name,
                    "kind": kind,
                    "pushed": labels,
                    "template": want,
                })

    print("=" * 72)
    print("已推送附注章节的列头 vs 模板")
    for k in sorted(stats):
        print(f"  {k:28} {stats[k]}")
    print("=" * 72)
    by_kind: Counter = Counter(f["kind"] for f in findings)
    print(f"不一致 {len(findings)} 张表，按类型：{dict(by_kind)}\n")
    for f in findings[:60]:
        print(f"[{f['kind']}] {f['project']} / {f['section']} 「{f['table']}」")
        print(f"    推送 {f['pushed']}")
        print(f"    模板 {f['template']}")
    if len(findings) > 60:
        print(f"……共 {len(findings)} 张")

    if args.json_out:
        Path(args.json_out).write_text(
            json.dumps({"stats": dict(stats), "findings": findings}, ensure_ascii=False, indent=2),
            encoding="utf-8")
        print(f"\n已写 {args.json_out}")

    await engine.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
