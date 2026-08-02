"""历史 DisclosureNote.table_data 升级为含 row_type + _cell_meta sidecar 字段（幂等）。

spec: .kiro/specs/_archive/08-disclosure-notes/disclosure-note-full-revamp/ Sprint 0 Task 0.2
design: D1 — row 新增两个 sidecar 字段，不动现有 values/_cell_modes/formula_type/is_total/label。

═══════════════════════════════════════════════════════════════════════════════
为什么需要这两个字段
═══════════════════════════════════════════════════════════════════════════════

历史 ``DisclosureNote.table_data`` 的 row 只有 ``label`` / ``values`` / ``_cell_modes``
（+ 可选 ``is_total``）。引擎重生成时区分不出「这一行是普通数据行还是合计行」、
也没地方记录「用户手填的原值」和「这个单元格是被哪条绑定规则算出来的」。

新增两个 **sidecar** 字段（旧前端读到未知字段会忽略，故不破坏兼容）：

- ``row_type``：``data`` / ``header_label`` / ``subtotal`` / ``total`` /
  ``dynamic_detail`` / ``formula`` —— 按 ``is_total`` / label 关键字启发式判定。
- ``_cell_meta[i]``：``{manual_value, semantic, binding_id}`` —— 与 ``values[i]``
  按下标对齐；``_cell_modes[i] == "manual"`` 时把当前 ``values[i]`` 备份进
  ``manual_value``（引擎重生成 auto 值时，manual 单元格的原值不会丢）。

═══════════════════════════════════════════════════════════════════════════════
幂等性
═══════════════════════════════════════════════════════════════════════════════

已有 ``row_type`` 的行不重新判定（不覆盖人工可能已修正的分类）；已有 ``_cell_meta``
的行不重新生成（不清空可能已被绑定引擎写入的 ``binding_id``）。两个字段各自独立
判断「已迁移」，故支持「先跑 0.1 模板治理判过 row_type，再跑本脚本只补 _cell_meta」
这种部分迁移场景。

用法：
    python scripts/migrate_disclosure_notes_to_v2.py --dry-run   # 预览统计，不写库
    python scripts/migrate_disclosure_notes_to_v2.py --apply     # 实际写库

本模块顶层 **不** import 任何 DB/ORM 符号 —— `upgrade_row` / `upgrade_table_data`
是纯函数，供单测直接调用；真实 DB 访问延迟到 `migrate_db()` 内部 import，
保证 `import migrate_disclosure_notes_to_v2` 不会触发数据库连接。
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections import Counter
from typing import Any

# ─────────────────────────── 纯函数（无 I/O，可单测） ───────────────────────────

VALID_ROW_TYPES = (
    "data",
    "header_label",
    "subtotal",
    "total",
    "dynamic_detail",
    "formula",
    # 「不属于任何段」的表级兜底行（多段共享表的行级合并据此排除该行）。
    # 与 `tests/services/test_note_template_row_type.VALID_ROW_TYPES` 保持一致。
    # spec: restricted-assets-note-row-scope-rollout Requirement 2
    "unowned",
)

#: label 关键字 → row_type（顺序即优先级；「小计」判定须先于默认 data）。
_SUBTOTAL_KEYWORDS = ("小计", "合  计", "本期小计", "分部小计")


def _make_empty_cell_meta(n: int) -> dict[str, dict[str, Any]]:
    """构造 ``n`` 个空 `_cell_meta` 槽位（key 为字符串下标，与 `_cell_modes` 一致）。

    ``n <= 0``（含防御性负数）返回空 dict，不抛异常。
    """
    if n <= 0:
        return {}
    return {
        str(i): {"manual_value": None, "semantic": None, "binding_id": None}
        for i in range(n)
    }


def _infer_row_type(row: dict[str, Any]) -> str:
    """按 `is_total` / label 关键字启发式判定 row_type。

    优先级：``is_total=True`` → ``total``；label 含小计关键字 → ``subtotal``；
    否则 → ``data``（其余三种类型 —— header_label/dynamic_detail/formula ——
    历史数据里无法用启发式安全判定，一律不臆造，只在模板治理脚本 0.1 或
    人工复核时精确指定）。
    """
    if row.get("is_total") is True:
        return "total"
    label = str(row.get("label") or "")
    if any(kw in label for kw in _SUBTOTAL_KEYWORDS):
        return "subtotal"
    return "data"


def upgrade_row(row: dict[str, Any], headers: list[str]) -> dict[str, str]:
    """就地升级单个 row，补齐 `row_type` 与 `_cell_meta`（幂等）。

    Args:
        row: 待升级的行字典（原地修改）。
        headers: 该表表头（供未来按列语义精确判定；当前实现只用其长度兜底）。

    Returns:
        ``{"row_type": "added"|"skipped", "_cell_meta": "added"|"skipped"}``。
    """
    result: dict[str, str] = {}

    if "row_type" in row:
        result["row_type"] = "skipped"
    else:
        row["row_type"] = _infer_row_type(row)
        result["row_type"] = "added"

    if "_cell_meta" in row:
        result["_cell_meta"] = "skipped"
    else:
        values = row.get("values")
        n = len(values) if isinstance(values, list) else max(0, len(headers) - 1)
        meta = _make_empty_cell_meta(n)

        cell_modes = row.get("_cell_modes")
        if isinstance(cell_modes, dict) and isinstance(values, list):
            for idx_str, mode in cell_modes.items():
                if mode != "manual" or idx_str not in meta:
                    continue
                try:
                    idx = int(idx_str)
                except ValueError:
                    continue
                if 0 <= idx < len(values):
                    meta[idx_str]["manual_value"] = values[idx]

        row["_cell_meta"] = meta
        result["_cell_meta"] = "added"

    return result


def _iter_rows(table_data: dict[str, Any]) -> list[list[dict[str, Any]]]:
    """按 `_tables` 多表 / 单表 `rows` 两种 schema 统一取出行分组列表。

    多表 schema（``_tables`` 为非空 list）时，顶层 ``rows`` 只是首表镜像，
    不重复计入（否则同一批行会被统计两次）。
    """
    tables = table_data.get("_tables")
    if isinstance(tables, list) and tables:
        return [t.get("rows") or [] for t in tables if isinstance(t, dict)]
    rows = table_data.get("rows")
    return [rows] if isinstance(rows, list) else []


def upgrade_table_data(table_data: dict[str, Any] | None) -> dict[str, Any]:
    """就地升级一个 `table_data`（单表或多表 `_tables`），返回统计信息。

    Returns:
        ``{tables, rows_total, row_type_added, row_type_skipped,
        _cell_meta_added, _cell_meta_skipped, manual_values_backed_up,
        row_type_counter}``。``table_data`` 为 ``None`` / 非 dict / 不含
        ``rows``/``_tables`` 时安全返回全零统计，不抛异常。
    """
    stats: dict[str, Any] = {
        "tables": 0,
        "rows_total": 0,
        "row_type_added": 0,
        "row_type_skipped": 0,
        "_cell_meta_added": 0,
        "_cell_meta_skipped": 0,
        "manual_values_backed_up": 0,
        "row_type_counter": Counter(),
    }
    if not isinstance(table_data, dict):
        return stats

    row_groups = _iter_rows(table_data)
    if not row_groups:
        return stats

    headers = table_data.get("headers") or []
    stats["tables"] = len(row_groups)

    for rows in row_groups:
        for row in rows:
            if not isinstance(row, dict):
                continue
            stats["rows_total"] += 1
            had_cell_meta = "_cell_meta" in row

            res = upgrade_row(row, headers)

            stats[f"row_type_{res['row_type']}"] += 1
            stats[f"_cell_meta_{res['_cell_meta']}"] += 1
            stats["row_type_counter"][row["row_type"]] += 1

            if res["_cell_meta"] == "added" and not had_cell_meta:
                backed_up = sum(
                    1
                    for slot in row["_cell_meta"].values()
                    if slot.get("manual_value") is not None
                )
                stats["manual_values_backed_up"] += backed_up

    return stats


# ─────────────────────────── DB 访问（延迟 import） ───────────────────────────


async def migrate_db(*, apply: bool, project_id: str | None = None) -> dict[str, Any]:
    """扫描全部（或指定项目）`disclosure_notes`，跑 `upgrade_table_data` 并按需落库。

    Args:
        apply: ``False``（默认，对应 ``--dry-run``）只统计不写库；
            ``True``（``--apply``）实际 `flag_modified` + commit。
        project_id: 可选，仅迁移该项目（调试/分批用）。

    Returns:
        汇总统计（含每个 note 的 `upgrade_table_data` 结果之和）。
    """
    import sqlalchemy as sa
    from sqlalchemy.orm.attributes import flag_modified

    from app.core.database import async_session
    from app.models.report_models import DisclosureNote

    total: dict[str, Any] = {
        "notes_scanned": 0,
        "notes_changed": 0,
        "tables": 0,
        "rows_total": 0,
        "row_type_added": 0,
        "_cell_meta_added": 0,
        "manual_values_backed_up": 0,
        "row_type_counter": Counter(),
    }

    async with async_session() as db:
        stmt = sa.select(DisclosureNote).where(
            DisclosureNote.table_data.is_not(None)
        )
        if project_id:
            stmt = stmt.where(DisclosureNote.project_id == project_id)
        notes = (await db.execute(stmt)).scalars().all()

        for note in notes:
            total["notes_scanned"] += 1
            table_data = note.table_data
            if not isinstance(table_data, dict):
                continue
            stats = upgrade_table_data(table_data)
            if stats["row_type_added"] == 0 and stats["_cell_meta_added"] == 0:
                continue

            total["notes_changed"] += 1
            total["tables"] += stats["tables"]
            total["rows_total"] += stats["rows_total"]
            total["row_type_added"] += stats["row_type_added"]
            total["_cell_meta_added"] += stats["_cell_meta_added"]
            total["manual_values_backed_up"] += stats["manual_values_backed_up"]
            total["row_type_counter"].update(stats["row_type_counter"])

            if apply:
                note.table_data = table_data
                flag_modified(note, "table_data")

        if apply:
            await db.commit()
        else:
            await db.rollback()

    return total


def _print_report(stats: dict[str, Any], *, apply: bool) -> None:
    mode = "APPLY（已写库）" if apply else "DRY-RUN（未写库）"
    print(f"=== migrate_disclosure_notes_to_v2 [{mode}] ===")
    print(f"  扫描 notes:        {stats['notes_scanned']}")
    print(f"  需要升级 notes:    {stats['notes_changed']}")
    print(f"  表数:              {stats['tables']}")
    print(f"  行数:              {stats['rows_total']}")
    print(f"  新增 row_type:     {stats['row_type_added']}")
    print(f"  新增 _cell_meta:   {stats['_cell_meta_added']}")
    print(f"  manual_value 备份: {stats['manual_values_backed_up']}")
    if stats["row_type_counter"]:
        print("  row_type 分布:")
        for rt, n in sorted(stats["row_type_counter"].items()):
            print(f"    {rt:16s} {n}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true", help="只统计，不写库")
    group.add_argument("--apply", action="store_true", help="实际写库（不可逆）")
    parser.add_argument("--project", default=None, help="仅迁移该 project_id（调试用）")
    args = parser.parse_args()

    stats = asyncio.run(migrate_db(apply=args.apply, project_id=args.project))
    _print_report(stats, apply=args.apply)
    return 0


if __name__ == "__main__":
    sys.exit(main())
