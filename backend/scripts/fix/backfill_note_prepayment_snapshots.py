"""回填既有项目附注「预付款项」章节的结构快照（幂等，默认 dry-run）。

**背景**：`disclosure_notes.table_data._tables` 是**生成时快照** —— 修订
`note_template_{listed,soe}.json` 只对新建项目 / 重新生成附注生效。存量项目的
预付款项章节仍带修订前的缺陷：

1. 按账龄表 `headers` 只有 3 项（两级表头被压平），行 `values` 只有 2 列；
2. 残留 `row_type: header_label` 假数据行；
3. **第 3 张表与第 2 张表重名**（国企 `账龄超过1年的大额预付款项` ×2；更早的
   生成版本甚至用 `headers[0]` 当表名，如 `账  龄` / `债权单位` / `债务人名称`）；
4. 全部表缺 `columns` / `_column_groups` / `guidance`。

**做什么**：把这些章节的 `_tables` 按修订后的模板重建（表名 / headers /
columns / _column_groups / guidance / 行骨架），并同步顶层 `headers` / `rows`
（沿用「顶层 = 第一张表」的既有约定）与 `sub_table_data` 旧键改名。

**安全边界（关键）**：

- 只处理 `_tables` 内**所有 `values` 均为空**（None / 空串）的章节 —— 即用户
  尚未录入任何数据的骨架。任何一格有值 → **跳过并报告**，改由「底稿披露表 →
  同步到附注」整表覆盖（同步路径带正确的 `columns`，无需本脚本）。
- 默认 `--dry-run`；`--apply` 才写库；`--check` 只报告仍需回填的章节数（供 CI）。
- 逐行 UPDATE 单条 `table_data`，不动其它列（不改 `status` / `updated_by` /
  `last_sync_*`），失败即回滚。

Usage::

    python backend/scripts/fix/backfill_note_prepayment_snapshots.py            # dry-run
    python backend/scripts/fix/backfill_note_prepayment_snapshots.py --apply
    python backend/scripts/fix/backfill_note_prepayment_snapshots.py --check

spec: .kiro/specs/f1-prepayment-disclosure-template-alignment/ R1（存量回填）
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

_BACKEND = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_BACKEND))

from sqlalchemy import select, update  # noqa: E402

from app.core.database import async_session, engine  # noqa: E402
from app.models.report_models import DisclosureNote  # noqa: E402

DATA_DIR = _BACKEND / "data"

# note_section → (模板文件, 章节号)
TARGETS = {
    "五、7": ("note_template_listed.json", "五、7"),
    "八、7": ("note_template_soe.json", "八、7"),
}

# 金额列语义（沿用既有快照口径，仅金额列打 semantic/binding_id）
_AMOUNT_SEMANTIC = {"end_amount": "closing_balance", "prior_amount": "opening_balance"}

# 上市第 3 张表的历史键（同步载荷同样上报为 `_removed_table_keys`）
_OBSOLETE_SUB_TABLE_KEYS = {"五、7": ["单位名称"]}


# ─────────────────────────── 模板读取 ───────────────────────────

def _load_template_section(file_name: str, section_number: str) -> dict[str, Any]:
    doc = json.loads((DATA_DIR / file_name).read_text(encoding="utf-8"))
    sec = next(
        (s for s in doc.get("sections") or [] if str(s.get("section_number")) == section_number),
        None,
    )
    if sec is None:
        raise SystemExit(f"[FATAL] {file_name} 缺少章节 {section_number}")
    return sec


# ─────────────────────────── 快照构造 ───────────────────────────

def _is_blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def snapshot_has_data(table_data: dict[str, Any] | None) -> bool:
    """`_tables` / 顶层 rows / sub_table_data 中是否存在任何非空值。"""
    if not isinstance(table_data, dict):
        return False

    def _rows_have_data(rows: Any) -> bool:
        if not isinstance(rows, list):
            return False
        for row in rows:
            if not isinstance(row, dict):
                continue
            for v in row.get("values") or []:
                if not _is_blank(v):
                    return True
            meta = row.get("_cell_meta")
            if isinstance(meta, dict):
                for cell in meta.values():
                    if isinstance(cell, dict) and not _is_blank(cell.get("manual_value")):
                        return True
        return False

    if _rows_have_data(table_data.get("rows")):
        return True
    for tbl in table_data.get("_tables") or []:
        if isinstance(tbl, dict) and _rows_have_data(tbl.get("rows")):
            return True

    sub = table_data.get("sub_table_data")
    if isinstance(sub, dict):
        for key, rows in sub.items():
            if str(key).startswith("_"):
                continue
            if not isinstance(rows, list):
                continue
            for row in rows:
                if not isinstance(row, dict):
                    continue
                for k, v in row.items():
                    if k in ("label", "is_total", "row_type") or str(k).startswith("_"):
                        continue
                    if not _is_blank(v) and v != 0:
                        return True
    return False


def _build_row(
    label: str,
    row_type: str,
    is_total: bool,
    value_keys: list[str],
    note_section: str,
) -> dict[str, Any]:
    cell_meta: dict[str, Any] = {}
    cell_modes: dict[str, Any] = {}
    for idx, key in enumerate(value_keys):
        semantic = _AMOUNT_SEMANTIC.get(key)
        cell_modes[str(idx)] = "manual"
        if semantic and row_type == "data" and label:
            cell_meta[str(idx)] = {
                "semantic": semantic,
                "binding_id": f"{note_section}.{label}.{semantic}",
                "manual_value": None,
            }
    return {
        "label": label,
        "values": [None] * len(value_keys),
        "is_total": is_total,
        "row_type": row_type,
        "_cell_meta": cell_meta,
        "_cell_modes": cell_modes,
    }


def build_tables_from_template(
    section: dict[str, Any],
    note_section: str,
) -> list[dict[str, Any]]:
    """模板 tables → 快照 `_tables`（含 columns / _column_groups / guidance / 行骨架）。"""
    built: list[dict[str, Any]] = []
    for tbl in section.get("tables") or []:
        columns = tbl.get("columns") or []
        value_keys = [c["key"] for c in columns[1:]]
        item: dict[str, Any] = {
            "name": tbl.get("name"),
            "headers": list(tbl.get("headers") or []),
            "columns": json.loads(json.dumps(columns, ensure_ascii=False)),
            "rows": [
                _build_row(
                    str(r.get("label") or ""),
                    str(r.get("row_type") or "data"),
                    bool(r.get("is_total")),
                    value_keys,
                    note_section,
                )
                for r in tbl.get("rows") or []
                if str(r.get("row_type")) != "header_label"
            ],
        }
        groups = tbl.get("_column_groups")
        if groups:
            item["_column_groups"] = json.loads(json.dumps(groups, ensure_ascii=False))
        guidance = str(tbl.get("guidance") or "").strip()
        if guidance:
            item["guidance"] = guidance
        built.append(item)
    return built


def rebuild_table_data(
    table_data: dict[str, Any] | None,
    section: dict[str, Any],
    note_section: str,
) -> tuple[dict[str, Any], list[str]]:
    """就地重建 `table_data`（返回新对象 + 变更摘要）。"""
    data = json.loads(json.dumps(table_data or {}, ensure_ascii=False))
    changes: list[str] = []

    old_names = [str(t.get("name")) for t in data.get("_tables") or [] if isinstance(t, dict)]
    tables = build_tables_from_template(section, note_section)
    new_names = [str(t["name"]) for t in tables]

    if old_names != new_names:
        changes.append(f"_tables 表名：{old_names} → {new_names}")
    data["_tables"] = tables

    # 顶层 headers/rows 沿用「= 第一张表」的既有约定
    first = tables[0]
    if data.get("headers") != first["headers"]:
        changes.append(f"顶层 headers：{data.get('headers')} → {first['headers']}")
    data["headers"] = list(first["headers"])
    data["rows"] = json.loads(json.dumps(first["rows"], ensure_ascii=False))

    # sub_table_data / _sub_table_columns 旧键清理（改名后残留会成为空 TAB）
    for bucket in ("sub_table_data", "_sub_table_columns"):
        holder = data.get(bucket)
        if not isinstance(holder, dict):
            continue
        for obsolete in _OBSOLETE_SUB_TABLE_KEYS.get(note_section, []):
            if obsolete in holder:
                holder.pop(obsolete)
                changes.append(f"{bucket} 删除旧键「{obsolete}」")

    return data, changes


# ─────────────────────────── 主流程 ───────────────────────────

async def run(*, apply: bool, check_only: bool) -> int:
    sections = {
        note_section: _load_template_section(file_name, number)
        for note_section, (file_name, number) in TARGETS.items()
    }

    pending = 0
    skipped_with_data = 0
    already_ok = 0
    updated = 0

    async with async_session() as db:
        rows = (
            await db.execute(
                select(DisclosureNote).where(
                    DisclosureNote.note_section.in_(list(TARGETS)),
                    DisclosureNote.is_deleted.is_(False),
                )
            )
        ).scalars().all()

        targets = [n for n in rows if "预付" in str(n.section_title or n.account_name or "")]
        print(f"命中预付款项章节 {len(targets)} 条（note_section ∈ {list(TARGETS)}）\n")

        for note in targets:
            tag = f"{note.project_id} {note.year} §{note.note_section}"
            new_data, changes = rebuild_table_data(
                note.table_data, sections[str(note.note_section)], str(note.note_section)
            )

            if not changes:
                already_ok += 1
                print(f"[OK]   {tag} 已对齐")
                continue

            if snapshot_has_data(note.table_data):
                skipped_with_data += 1
                print(f"[SKIP] {tag} 已有录入数据 → 请用底稿披露表「同步到附注」整表覆盖")
                continue

            pending += 1
            for c in changes:
                print(f"       - {c}")
            if check_only:
                print(f"[NEED] {tag} 需回填")
                continue
            if not apply:
                print(f"[DRY]  {tag} 将回填（未写库）")
                continue

            await db.execute(
                update(DisclosureNote)
                .where(DisclosureNote.id == note.id)
                .values(table_data=new_data)
            )
            updated += 1
            print(f"[FIX]  {tag} 已回填")

        if apply and updated:
            await db.commit()
            print(f"\n已提交 {updated} 条")

    await engine.dispose()

    print(
        f"\n汇总：已对齐 {already_ok} / 需回填 {pending} / "
        f"有数据跳过 {skipped_with_data} / 实际写入 {updated}"
    )
    if check_only and pending:
        print("[FAIL] 存在未回填章节（跑 --apply 修复）")
        return 1
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="回填附注预付款项章节结构快照（幂等）")
    ap.add_argument("--apply", action="store_true", help="真正写库（默认只 dry-run）")
    ap.add_argument("--check", action="store_true", help="只报告需回填条数（供 CI）")
    args = ap.parse_args()
    return asyncio.run(run(apply=args.apply, check_only=args.check))


if __name__ == "__main__":
    sys.exit(main())
