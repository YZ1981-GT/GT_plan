"""修正存量：已推送附注章节里 `_sub_table_columns` 的列头文字与模板不一致的，按模板改回。

spec: note-table-structure-formula-pull-closure R16（design §7）

**为什么需要**：附注表格的表头有两个来源 —— 模板种子化（必然对）与底稿推送
（前端 `buildXSyncPayload` 的 `columns` → `table_data._sub_table_columns`，投影器据此渲染）。
旧版前端的硬编码列头与模板不一致（典型：`账龄` vs 模板 `账 龄`、`类别` vs `类 别`），
推送后就把错的列头留在了库里 ⇒ 附注与 Word 显示不一致。
当前前端代码已对齐（R13 修 D2；12 个循环 107 张表现算逐位全对），但**存量不会自愈**。

**只改显示文字，不动数据**：逐位替换 `label`，`key` / `group` / `flat` / `format` 与行数据一概不碰。

🔴 **列数不同的表不处理**（结构性差异，改 label 会错位）⇒ 只报告，需在界面上重新推送。
🔴 默认 dry-run；`--apply` 需配 `--confirm`；写前整行备份 JSON。

用法：
    python backend/scripts/fix/fix_pushed_note_header_labels.py
    python backend/scripts/fix/fix_pushed_note_header_labels.py --project <uuid>
    python backend/scripts/fix/fix_pushed_note_header_labels.py --apply --confirm
"""
from __future__ import annotations

import argparse
import asyncio
import copy
import json
import os
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

BACKEND = Path(__file__).resolve().parents[2]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import sqlalchemy as sa  # noqa: E402

DATA = BACKEND / "data"
BACKUPS = BACKEND / "backups"


def _load_templates() -> dict[tuple[str, str, str], list[str]]:
    out: dict[tuple[str, str, str], list[str]] = {}
    for std in ("soe", "listed"):
        raw = json.loads((DATA / f"note_template_{std}.json").read_text(encoding="utf-8"))
        for sec in raw.get("sections") or []:
            num = str(sec.get("section_number") or "").strip()
            for t in sec.get("tables") or []:
                name = str((t or {}).get("name") or "").strip()
                headers = [str(h) for h in ((t or {}).get("headers") or [])]
                if num and name and headers:
                    out[(std, num, name)] = headers
    return out


def _template_for(tpl: dict, std: str, section: str, name: str) -> list[str] | None:
    other = "listed" if std == "soe" else "soe"
    return tpl.get((std, section, name)) or tpl.get((other, section, name))


def reordered_columns(pushed: list[str], template: list[str]) -> bool:
    """列序错位（而非措辞差异）：某个推送列名在模板里**存在但位置不同**。

    这种表不能只改 label —— 那等于把一列的数据贴上另一列的名字。

    实测反例（本脚本 dry-run 自己抓到的）：陕西华氏 八、57「其他非流动负债」
    推送 ``[项目, 期末余额, 期初余额]`` vs 模板 ``[项目, 年初余额, 期末余额]``，
    「期末余额」两边都有、位置不同 ⇒ 逐位改 label 会把期末数标成「年初余额」。

    对照（这些该改、不该被这道门拦住）：
      ``账龄 → 账 龄``（模板里没有「账龄」）、``年初余额 → 期初余额``（模板里没有「年初余额」）、
      ``余额 → 期末余额``（模板里没有「余额」）—— 推送名在模板里不存在 ⇒ 纯措辞差异。
    """
    tpl_pos: dict[str, list[int]] = {}
    for i, name in enumerate(template):
        tpl_pos.setdefault(name, []).append(i)
    for i, name in enumerate(pushed):
        if i < len(template) and name == template[i]:
            continue  # 这一列本来就对得上
        where = tpl_pos.get(name)
        if where and i not in where:
            return True  # 这个名字在模板里有、但不在这个位置 ⇒ 列序错位
    return False


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", help="只处理某个项目 id")
    ap.add_argument("--apply", action="store_true", help="真写库（需同时给 --confirm）")
    ap.add_argument("--confirm", action="store_true")
    args = ap.parse_args()
    if args.apply and not args.confirm:
        print("!! --apply 必须同时给 --confirm")
        return 2

    os.environ.setdefault(
        "DATABASE_URL", "postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/audit_platform")
    from app.core.database import engine  # noqa: PLC0415

    tpl = _load_templates()
    stats = Counter()
    plan: list[dict[str, Any]] = []
    backup: list[dict[str, Any]] = []

    where = "AND d.project_id = :pid" if args.project else ""
    params: dict[str, Any] = {"pid": args.project} if args.project else {}

    async with engine.begin() as conn:
        rows = (await conn.execute(sa.text(f"""
            SELECT d.id, d.project_id, p.name AS project_name, p.template_type,
                   d.note_section, d.table_data
              FROM disclosure_notes d
              JOIN projects p ON p.id = d.project_id
             WHERE d.table_data ? '_sub_table_columns'
               AND (p.is_deleted IS NULL OR p.is_deleted = false)
               {where}
             ORDER BY p.name, d.note_section
        """), params)).mappings().all()

        for r in rows:
            td = r["table_data"]
            if isinstance(td, str):
                td = json.loads(td)
            pushed = (td or {}).get("_sub_table_columns")
            if not isinstance(pushed, dict):
                continue
            std = "soe" if str(r["template_type"] or "").lower().startswith("soe") else "listed"
            # 🔴 原地改 JSONB 再赋回同一对象，ORM/驱动可能不发 UPDATE ⇒ 深拷贝后整体替换
            new_td = copy.deepcopy(td)
            changed_tables: list[dict[str, Any]] = []

            for name, cols in pushed.items():
                if not isinstance(cols, list) or name.startswith("_"):
                    continue
                stats["tables"] += 1
                want = _template_for(tpl, std, r["note_section"], name)
                if want is None:
                    stats["table_not_in_template"] += 1
                    continue
                got = [str((c or {}).get("label") or "") for c in cols if isinstance(c, dict)]
                if got == want:
                    stats["already_match"] += 1
                    continue
                if len(got) != len(want):
                    stats["skip_column_count"] += 1
                    plan.append({"project": r["project_name"], "section": r["note_section"],
                                 "table": name, "action": "skip_column_count",
                                 "pushed": got, "template": want})
                    continue
                if reordered_columns(got, want):
                    # 🔴 列序错位，不是措辞差异：只改 label 会把「期末的数」标成「年初」，
                    # 比现状更糟。实测反例见 `misordered_sample`。
                    stats["skip_reordered"] += 1
                    plan.append({"project": r["project_name"], "section": r["note_section"],
                                 "table": name, "action": "skip_reordered",
                                 "pushed": got, "template": want})
                    continue
                diffs = [(i, a, b) for i, (a, b) in enumerate(zip(got, want)) if a != b]
                for i, _a, b in diffs:
                    new_td["_sub_table_columns"][name][i]["label"] = b
                stats["fixed_tables"] += 1
                stats["fixed_labels"] += len(diffs)
                changed_tables.append({"table": name, "diffs": diffs})
                plan.append({"project": r["project_name"], "section": r["note_section"],
                             "table": name, "action": "fix_labels",
                             "diffs": [[i, a, b] for i, a, b in diffs]})

            if changed_tables and args.apply:
                backup.append({
                    "note_id": str(r["id"]), "project_id": str(r["project_id"]),
                    "project": r["project_name"], "section": r["note_section"],
                    "old_sub_table_columns": (td or {}).get("_sub_table_columns"),
                })
                await conn.execute(sa.text("""
                    UPDATE disclosure_notes SET table_data = CAST(:td AS jsonb) WHERE id = :id
                """), {"td": json.dumps(new_td, ensure_ascii=False), "id": r["id"]})
                stats["updated_rows"] += 1

        if not args.apply:
            # dry-run：确保事务不留痕
            await conn.rollback()

    print("=" * 72)
    for k in sorted(stats):
        print(f"  {k:24} {stats[k]}")
    print("=" * 72)
    for p in plan[:50]:
        if p["action"] == "fix_labels":
            print(f"[改] {p['project']} / {p['section']} 「{p['table']}」")
            for i, a, b in p["diffs"]:
                print(f"      第{i}列 {a!r} → {b!r}")
        elif p["action"] == "skip_reordered":
            print(f"[跳过·列序错位] {p['project']} / {p['section']} 「{p['table']}」"
                  f" —— 只改名会让数据错位，需在界面重新推送")
            print(f"      推送 {p['pushed']}")
            print(f"      模板 {p['template']}")
        else:
            print(f"[跳过·列数不同] {p['project']} / {p['section']} 「{p['table']}」"
                  f" 推送 {len(p['pushed'])} 列 / 模板 {len(p['template'])} 列 —— 需在界面重新推送")
    if len(plan) > 50:
        print(f"……共 {len(plan)} 项")

    if args.apply:
        BACKUPS.mkdir(parents=True, exist_ok=True)
        path = BACKUPS / f"pushed_note_header_labels_{datetime.now():%Y%m%d_%H%M%S}.json"
        path.write_text(json.dumps(backup, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n已写库；备份 {path.relative_to(BACKEND).as_posix()}")
    else:
        print("\n（dry-run，未写库；真写加 --apply --confirm）")

    await engine.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
