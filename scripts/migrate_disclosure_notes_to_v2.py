"""DisclosureNote.table_data v2 升级脚本（幂等）.

Spec: .kiro/specs/disclosure-note-full-revamp/ Sprint 0 Task 0.2
Design: D1 row 新增 `row_type` + `_cell_meta` sidecar 字段（不替代现有结构）

职责：
1. 历史 DisclosureNote.table_data.row 升级为含 `row_type + _cell_meta`
2. 跳过已升级行（幂等可重复跑）
3. _cell_modes[i] == "manual" 时把当前 values[i] 备份到 _cell_meta[str(i)].manual_value
   （承接 R1.3 验收 11：恢复自动提数能找回手工原始值）
4. 输出迁移报告 scripts/migrate_report.txt

支持两种 schema：
  - 单表：table_data = {"headers": [...], "rows": [...]}
  - 多表：table_data = {"_tables": [{"headers":..., "rows":...}, ...], ...}

启发式规则：复用 scripts/cleanup_note_templates.py 的 detect_row_type，
保持模板治理（Task 0.1）与运行时 DB 数据迁移（本脚本 Task 0.2）一致。

使用：
    # 试跑（不写库）
    .venv\\Scripts\\python.exe scripts/migrate_disclosure_notes_to_v2.py --dry-run

    # 实际写库
    .venv\\Scripts\\python.exe scripts/migrate_disclosure_notes_to_v2.py --apply

    # 单项目跑
    .venv\\Scripts\\python.exe scripts/migrate_disclosure_notes_to_v2.py --apply --project-id <UUID>

    # 试跑前 N 条
    .venv\\Scripts\\python.exe scripts/migrate_disclosure_notes_to_v2.py --dry-run --limit 5

注意：本脚本是幂等迁移（用完不删，可被 CI / 部署重复触发）；命名不加 `_` 前缀。

实现说明：
- DB 访问走 SQLAlchemy raw text SQL（仅 SELECT/UPDATE 必要的 id/project_id/table_data
  /is_deleted 列），**避开完整 ORM**——避免本地 DB schema 与 ORM 列定义偏移
  （如 is_stale 等较新列在某些环境未跑迁移）导致脚本无法启动。
- 通过 SQLAlchemy `async_session` 连接（读 backend/app/core/database.py 的 `DATABASE_URL`）。
- 只 update table_data 列；不依赖 `flag_modified`（raw SQL 直接 SET）。
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from collections import Counter
from copy import deepcopy
from pathlib import Path
from typing import Any
from uuid import UUID

# 确保 backend 在 sys.path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

# 复用 Task 0.1 治理脚本的 row_type 启发式
sys.path.insert(0, str(ROOT / "scripts"))
from cleanup_note_templates import VALID_ROW_TYPES, detect_row_type  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

REPORT_FILE = ROOT / "scripts" / "migrate_report.txt"


# ---------------------------------------------------------------------------
# 纯函数 transformer（独立可测，不依赖 DB）
# ---------------------------------------------------------------------------


def _make_empty_cell_meta(values_len: int) -> dict[str, dict[str, Any]]:
    """根据 values 长度生成空 _cell_meta dict（key 字符串索引，与 _cell_modes 对齐）."""
    return {
        str(i): {"manual_value": None, "semantic": None, "binding_id": None}
        for i in range(max(values_len, 0))
    }


def upgrade_row(row: dict[str, Any], headers: list[Any]) -> dict[str, str]:
    """就地升级单个 row，返回 {"row_type": <added|skipped>, "_cell_meta": <added|skipped>}.

    Args:
        row: 待升级的 row dict（被就地修改）
        headers: 当前表的 headers，用于 row_type 启发式判定

    Returns:
        {"row_type": "added"|"skipped", "_cell_meta": "added"|"skipped",
         "row_type_value": <最终的 row_type 值>}
    """
    result: dict[str, str] = {}

    # ① row_type sidecar
    existing_rt = row.get("row_type")
    if existing_rt in VALID_ROW_TYPES:
        # 幂等：已有合法 row_type 不动
        result["row_type"] = "skipped"
        result["row_type_value"] = existing_rt
    else:
        rt = detect_row_type(row, [str(h) if h is not None else "" for h in headers])
        row["row_type"] = rt
        result["row_type"] = "added"
        result["row_type_value"] = rt

    # ② _cell_meta sidecar
    existing_meta = row.get("_cell_meta")
    if isinstance(existing_meta, dict):
        # 幂等：已有 _cell_meta dict 不动（即便是空 dict 也认为已迁移）
        result["_cell_meta"] = "skipped"
    else:
        values = row.get("values") or []
        if not isinstance(values, list):
            values = []
        meta = _make_empty_cell_meta(len(values))

        # 特殊：若 _cell_modes[i] == "manual"，把当前 values[i] 备份到 manual_value
        # 实现 R1.3 验收 11：恢复自动提数能找回手工原始值
        modes = row.get("_cell_modes") or {}
        if isinstance(modes, dict):
            for k, mode in modes.items():
                if mode != "manual":
                    continue
                # _cell_modes 的 key 已经是 "0"/"1" 字符串，直接对齐
                slot = meta.get(str(k))
                if slot is None:
                    continue
                # 仅在槽位无 manual_value 时备份
                if slot.get("manual_value") is None:
                    try:
                        idx = int(k)
                    except (ValueError, TypeError):
                        continue
                    if 0 <= idx < len(values):
                        slot["manual_value"] = values[idx]

        row["_cell_meta"] = meta
        result["_cell_meta"] = "added"

    return result


def _iter_tables(table_data: Any) -> list[tuple[str | None, dict[str, Any]]]:
    """从 note.table_data 中收集所有"伪表"(name, table_dict)；同时支持单表 + 多表 schema.

    返回:
        [(table_name, table_dict), ...]，table_dict 引用原对象，可就地修改其 rows.
    """
    if not isinstance(table_data, dict):
        return []

    out: list[tuple[str | None, dict[str, Any]]] = []
    multi = table_data.get("_tables")
    if isinstance(multi, list) and multi:
        # 多表：以 _tables 为准（顶层 headers/rows 是首表镜像，避免重复处理）
        for t in multi:
            if isinstance(t, dict):
                out.append((t.get("name"), t))
        return out

    # 单表：直接把 table_data 当一张表处理
    if "rows" in table_data or "headers" in table_data:
        out.append((table_data.get("name"), table_data))

    return out


def upgrade_table_data(table_data: Any) -> dict[str, Any]:
    """就地升级一个 note.table_data，返回统计 dict.

    Returns:
        {
            "tables": <张数>,
            "rows_total": <总 row 数>,
            "row_type_added": <本次新增 row_type 行数>,
            "row_type_skipped": <已含 row_type 行数>,
            "_cell_meta_added": <本次新增 _cell_meta 行数>,
            "_cell_meta_skipped": <已含 _cell_meta 行数>,
            "row_type_counter": Counter,
            "manual_values_backed_up": <备份 manual_value 次数>,
        }
    """
    stats: dict[str, Any] = {
        "tables": 0,
        "rows_total": 0,
        "row_type_added": 0,
        "row_type_skipped": 0,
        "_cell_meta_added": 0,
        "_cell_meta_skipped": 0,
        "row_type_counter": Counter(),
        "manual_values_backed_up": 0,
    }

    for _name, tbl in _iter_tables(table_data):
        stats["tables"] += 1
        headers = tbl.get("headers") or []
        rows = tbl.get("rows") or []
        if not isinstance(rows, list):
            continue
        for r in rows:
            if not isinstance(r, dict):
                continue
            stats["rows_total"] += 1
            # 检测是否会触发 manual_value 备份（before upgrade）
            had_meta = isinstance(r.get("_cell_meta"), dict)
            modes_before = r.get("_cell_modes") or {}
            values_before = r.get("values") or []
            will_backup = 0
            if not had_meta and isinstance(modes_before, dict):
                for k, mode in modes_before.items():
                    if mode != "manual":
                        continue
                    try:
                        idx = int(k)
                    except (ValueError, TypeError):
                        continue
                    if 0 <= idx < len(values_before) and values_before[idx] is not None:
                        will_backup += 1

            res = upgrade_row(r, headers)
            stats["row_type_counter"][res["row_type_value"]] += 1
            stats[f"row_type_{res['row_type']}"] += 1
            stats[f"_cell_meta_{res['_cell_meta']}"] += 1
            if res["_cell_meta"] == "added":
                stats["manual_values_backed_up"] += will_backup

    return stats


# ---------------------------------------------------------------------------
# 异步 DB 主流程
# ---------------------------------------------------------------------------


async def migrate_db(
    *,
    dry_run: bool,
    project_id: UUID | None,
    limit: int | None,
) -> dict[str, Any]:
    """连接 PG 异步迁移所有 DisclosureNote.table_data 到 v2.

    注意：用 raw SQL 仅 SELECT/UPDATE table_data 列，**不依赖完整 ORM**，
    以避免本机 DB schema 与 ORM 列定义偏移（如 is_stale 列在某些环境未迁移）
    导致整个脚本无法运行。
    """
    # 延迟导入：纯函数测试不需要 DB
    import json as _json

    from sqlalchemy import text as _sa_text

    from app.core.database import async_session

    grand: dict[str, Any] = {
        "notes_total": 0,
        "notes_changed": 0,
        "notes_unchanged": 0,
        "tables": 0,
        "rows_total": 0,
        "row_type_added": 0,
        "row_type_skipped": 0,
        "_cell_meta_added": 0,
        "_cell_meta_skipped": 0,
        "row_type_counter": Counter(),
        "manual_values_backed_up": 0,
        "errors": [],
    }

    async with async_session() as db:
        # 绕过 RLS（superuser 直连无 RLS 影响；非 superuser 用 set_config 兜底）
        try:
            await db.execute(
                _sa_text("SELECT set_config('app.bypass_rls', 'true', false)")
            )
        except Exception as _e:
            logger.debug("set_config bypass_rls 失败（可能数据库无该配置）: %s", _e)

        # 仅查必要列（id / project_id / table_data），避开 ORM 列漂移
        sql_select = """
            SELECT id, project_id, table_data
            FROM disclosure_notes
            WHERE is_deleted = false
        """
        params: dict[str, Any] = {}
        if project_id is not None:
            sql_select += " AND project_id = :pid"
            params["pid"] = str(project_id)
        sql_select += " ORDER BY id"
        if limit is not None and limit > 0:
            sql_select += " LIMIT :lim"
            params["lim"] = int(limit)

        result = await db.execute(_sa_text(sql_select), params)
        rows = list(result.all())
        grand["notes_total"] = len(rows)
        logger.info("待迁移 DisclosureNote 数：%d", len(rows))

        sql_update = _sa_text(
            "UPDATE disclosure_notes "
            "SET table_data = CAST(:td AS JSONB), updated_at = NOW() "
            "WHERE id = :id"
        )

        for note_id, _proj_id, td in rows:
            if td is None:
                grand["notes_unchanged"] += 1
                continue

            try:
                # 深拷贝再升级，便于 dry-run 不改原对象 + diff 判断
                td_new = deepcopy(td)
                stats = upgrade_table_data(td_new)
            except Exception as e:
                logger.error("note %s 升级失败：%s", note_id, e)
                grand["errors"].append({"note_id": str(note_id), "error": str(e)})
                continue

            # 累计统计
            grand["tables"] += stats["tables"]
            grand["rows_total"] += stats["rows_total"]
            grand["row_type_added"] += stats["row_type_added"]
            grand["row_type_skipped"] += stats["row_type_skipped"]
            grand["_cell_meta_added"] += stats["_cell_meta_added"]
            grand["_cell_meta_skipped"] += stats["_cell_meta_skipped"]
            grand["row_type_counter"].update(stats["row_type_counter"])
            grand["manual_values_backed_up"] += stats["manual_values_backed_up"]

            changed = (
                stats["row_type_added"] > 0 or stats["_cell_meta_added"] > 0
            )
            if changed:
                grand["notes_changed"] += 1
                if not dry_run:
                    await db.execute(
                        sql_update,
                        {
                            "td": _json.dumps(td_new, ensure_ascii=False),
                            "id": str(note_id),
                        },
                    )
            else:
                grand["notes_unchanged"] += 1

        if not dry_run:
            await db.commit()
            logger.info("commit 完成（影响 %d 条 note）", grand["notes_changed"])
        else:
            await db.rollback()
            logger.info("dry-run：已回滚（无写入）")

    return grand


# ---------------------------------------------------------------------------
# 报告输出
# ---------------------------------------------------------------------------


def _format_report(grand: dict[str, Any], *, dry_run: bool) -> str:
    lines: list[str] = []
    lines.append("=" * 72)
    lines.append(
        f"DisclosureNote table_data v2 migration  "
        f"(mode={'DRY-RUN' if dry_run else 'APPLY'})"
    )
    lines.append("=" * 72)
    lines.append(f"  notes total              : {grand['notes_total']}")
    lines.append(f"  notes changed this run   : {grand['notes_changed']}")
    lines.append(f"  notes unchanged          : {grand['notes_unchanged']}")
    lines.append(f"  tables processed         : {grand['tables']}")
    lines.append(f"  rows total               : {grand['rows_total']}")
    lines.append(
        f"  row_type added           : {grand['row_type_added']}"
        f"   (already tagged: {grand['row_type_skipped']})"
    )
    lines.append(
        f"  _cell_meta added         : {grand['_cell_meta_added']}"
        f"   (already tagged: {grand['_cell_meta_skipped']})"
    )
    lines.append(
        f"  manual_value backups     : {grand['manual_values_backed_up']}"
    )

    rt_dist = grand["row_type_counter"]
    lines.append("  row_type distribution:")
    rt_total = sum(rt_dist.values())
    for rt in VALID_ROW_TYPES:
        cnt = rt_dist.get(rt, 0)
        pct = (cnt * 100.0 / rt_total) if rt_total else 0
        lines.append(f"    {rt:<14}: {cnt:>5}  ({pct:5.1f}%)")

    if grand["errors"]:
        lines.append("")
        lines.append("-" * 72)
        lines.append(f"[errors] {len(grand['errors'])}")
        for i, err in enumerate(grand["errors"][:20], 1):
            lines.append(f"  {i:>3}. note={err['note_id']} err={err['error']}")
        if len(grand["errors"]) > 20:
            lines.append(f"  ... ({len(grand['errors']) - 20} more truncated)")

    lines.append("")
    lines.append("=" * 72)
    if dry_run:
        lines.append("(dry-run) - no DB writes. Re-run with --apply to commit.")
    else:
        lines.append("[OK] DB has been updated.")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="DisclosureNote.table_data v2 migration (idempotent)"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--dry-run",
        dest="dry_run",
        action="store_true",
        help="Preview changes without committing.",
    )
    group.add_argument(
        "--apply",
        dest="apply",
        action="store_true",
        help="Actually write changes to the DB.",
    )
    parser.add_argument(
        "--project-id",
        dest="project_id",
        type=str,
        default=None,
        help="只迁移指定 project_id（UUID）的附注（可选）",
    )
    parser.add_argument(
        "--limit",
        dest="limit",
        type=int,
        default=None,
        help="只处理前 N 条 DisclosureNote（试跑用）",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    dry_run = bool(args.dry_run)

    project_id: UUID | None = None
    if args.project_id:
        try:
            project_id = UUID(args.project_id)
        except ValueError:
            print(f"[ERROR] --project-id 不是合法 UUID: {args.project_id}", file=sys.stderr)
            return 2

    try:
        grand = asyncio.run(
            migrate_db(dry_run=dry_run, project_id=project_id, limit=args.limit)
        )
    except Exception as e:
        # DB 连接失败等非业务异常单独打印 + 退出
        logger.error("迁移执行失败：%s", e, exc_info=True)
        return 1

    report = _format_report(grand, dry_run=dry_run)
    REPORT_FILE.parent.mkdir(parents=True, exist_ok=True)
    REPORT_FILE.write_text(report, encoding="utf-8")

    # Windows GBK 控制台兼容（同 cleanup_note_templates.py）
    try:
        sys.stdout.buffer.write(report.encode("utf-8", errors="replace"))
    except AttributeError:
        print(report)
    print(f"[report] written to {REPORT_FILE.relative_to(ROOT)}")

    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
