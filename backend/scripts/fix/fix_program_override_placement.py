"""修复程序表字段覆盖的写读对齐问题。

spec: audit-year-calendar-fallback-ratchet（R0 任务 0.5）

═══ 问题 ═══

前端写程序表字段覆盖（状态 / 执行说明）时：
1. 年度从路由取（今年 2026），而读取方按项目审计年度（2025）
2. scope 用传入的 sheetName 拼（整册嵌入时没传 ⇒ 写进 ``A1``；
   A 类顶层是「审计程序A7」这类表名），而读取方按表码

结果：用户改的状态 / 执行说明写入了读取方看不到的 (year, scope) 位置。

═══ 策略 ═══

1. 对每个项目取读取方的审计年度（`PROJECT_AUDIT_YEAR_BIZ_SQL` 口径）
2. 对每个 ``procedure_table:*`` 的 scope，判定是否「写错位置」：
   - scope 后缀含中文（表名而非表码） → 从后缀中提取码
   - year ≠ 项目审计年度
3. 计算目标 (year, scope)
4. 检查目标位置有无冲突（同 project_id + item_key + field 的行已存在）
5. dry-run：只报告；--apply：移动无冲突行、写审计日志

═══ 用法 ═══

    # 只读预演
    python backend/scripts/fix/fix_program_override_placement.py

    # 真实修复（须用户确认）
    python backend/scripts/fix/fix_program_override_placement.py --apply

    # 只处理一个项目（可重复 --project）
    python backend/scripts/fix/fix_program_override_placement.py --project <项目 id>

冲突（目标位置已有同一行同一字段的值，或两行错位到同一目标）一律不动、单列报告；
核心 :func:`fix_placement` 只执行语句不提交（测试在回滚事务里调用）。
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BACKEND = Path(__file__).resolve().parents[2]
ROOT = BACKEND.parent
sys.path.insert(0, str(BACKEND))


#: 修复留痕：平台操作日志 ``logs``（与 Log 模型同列；脚本无操作人，user_id 留空）
_AUDIT_LOG_SQL = (
    "INSERT INTO logs (id, user_id, action_type, object_type, object_id, new_value, created_at) "
    "VALUES (CAST(:id AS uuid), NULL, :action, :ttype, NULL, CAST(:detail AS jsonb), :ts)"
)


# ─── 读取方口径：提取程序表表码 ────────────────────────────────────────────

_SHEET_CODE_RE = re.compile(
    r"([A-Z]\d+(?:-\d+)?[A-Z](?:-\d+)*|[A-Z]\d+[A-Z](?:-\d+)*|[A-Z]\d+-\d+[A-Z]?)"
)


def _extract_code_from_scope_suffix(suffix: str) -> str | None:
    """尝试从 scope 后缀提取表码（与 resolve_program_template_code 同一逻辑）。

    返回 None 表示已经是纯表码（无中文、无异常）。
    返回字符串表示从「含中文的表名」里提取出的编码。
    """
    # 纯英文数字连字符 → 已经是表码格式，不需修正
    if re.fullmatch(r"[A-Z0-9][-A-Z0-9]*", suffix):
        return None
    # 含中文或其他字符 → 尝试提取
    # 优先用 resolve_program_template_code 同一正则（匹配 D2A/K1A/A1-2 等复合码）
    m = _SHEET_CODE_RE.search(suffix)
    if m:
        return m.group(1)
    # 退而求其次：提取纯字母+数字的连续片段（A7/A8/A17 这类简单码）
    # 与 resolve_program_template_code 回退到 wp_code 一致
    simple = re.search(r"([A-Z]\d+)", suffix)
    return simple.group(1) if simple else None


# ─── 主逻辑 ────────────────────────────────────────────────────────────────

async def run(apply: bool, project_ids: list[str] | None = None) -> dict[str, Any]:
    """自开连接跑 :func:`fix_placement`；``--apply`` 时提交。"""
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker as async_sessionmaker
    from sqlalchemy.pool import NullPool

    from app.core.config import settings

    db_url = str(settings.DATABASE_URL)
    if not db_url.startswith("postgresql"):
        raise SystemExit(f"本脚本需要真实 PostgreSQL；当前 DATABASE_URL 为 {db_url.split('://')[0]}")

    ssl_off = {"ssl": False} if getattr(settings, "DB_DISABLE_SSL", False) else {}
    engine = create_async_engine(db_url, poolclass=NullPool, connect_args=dict(ssl_off))
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with Session() as db:
            report = await fix_placement(db, apply=apply, project_ids=project_ids)
            if apply and report["moved"]:
                await db.commit()
                print(f"✅ 已移动 {len(report['moved'])} 行，{len(report['conflicts'])} 行冲突跳过")
            elif apply:
                print("✅ 无需移动的行")
            # dry-run 不提交（会话关闭即回滚）
    finally:
        await engine.dispose()
    return report


async def fix_placement(db, *, apply: bool, project_ids: list[str] | None = None) -> dict[str, Any]:
    """判定写错位置的行；``apply`` 时移动无冲突行并在 ``logs`` 留痕。只执行语句不提交，由调用方提交。

    ``project_ids``：只处理这些项目（默认全部 ``procedure_table:*`` 覆盖行）。
    """
    import sqlalchemy as sa
    from sqlalchemy import text

    report: dict[str, Any] = {
        "mode": "apply" if apply else "dry-run",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "misplaced": [],
        "conflicts": [],
        "moved": [],
        "skipped": [],
    }

    # 1) 取 procedure_table scope 的覆盖行（可按项目限定）
    sql = (
        "SELECT id, project_id, year, scope, item_key, field, value "
        "FROM workpaper_field_overrides "
        "WHERE scope LIKE 'procedure_table:%' "
    )
    order = "ORDER BY project_id, scope, item_key, field, year, id"  # 定序：两行错位到同一目标时谁先占位可复现
    params: dict[str, Any] = {}
    stmt = text(sql + order)
    if project_ids:
        stmt = text(sql + "AND project_id IN :pids " + order).bindparams(sa.bindparam("pids", expanding=True))
        params["pids"] = [uuid.UUID(str(p)) for p in project_ids]
    rows = (await db.execute(stmt, params)).mappings().all()

    if not rows:
        print("✅ 无 procedure_table 覆盖行")
        return report

    print(f"共 {len(rows)} 行 procedure_table 覆盖")

    # 2) 按项目取审计年度
    row_project_ids = sorted({str(r["project_id"]) for r in rows})
    project_years: dict[str, int | None] = {}
    project_names: dict[str, str] = {}
    for pid in row_project_ids:
        row = (await db.execute(text(
            "SELECT COALESCE("
            "  audit_year, "
            "  EXTRACT(YEAR FROM audit_period_end)::int, "
            "  EXTRACT(YEAR FROM audit_period_start)::int"
            "), "
            "COALESCE(client_name, name, '') "
            "FROM projects WHERE id = :pid"
        ), {"pid": pid})).first()
        project_years[pid] = int(row[0]) if row and row[0] else None
        project_names[pid] = row[1] if row else "?"

    # 3) 逐行判定。``claimed``：本次已占用的目标位置 —— 两行错位到同一目标时第二行按冲突处理，
    #    dry-run 与 --apply 结论一致（--apply 时第一行 UPDATE 后库里也查得到）
    claimed: set[tuple[str, int | None, str, str, str]] = set()
    for r in rows:
        rid = str(r["id"])
        pid = str(r["project_id"])
        stored_year = r["year"]
        stored_scope = r["scope"]
        item_key = r["item_key"]
        field = r["field"]
        value = r["value"]

        reader_year = project_years.get(pid)
        suffix = stored_scope.removeprefix("procedure_table:")

        # 判定 scope 是否需要修正
        extracted_code = _extract_code_from_scope_suffix(suffix)
        target_scope = f"procedure_table:{extracted_code}" if extracted_code else stored_scope

        # 判定 year 是否需要修正
        target_year = reader_year if reader_year else stored_year

        year_wrong = stored_year != target_year
        scope_wrong = stored_scope != target_scope

        if not year_wrong and not scope_wrong:
            continue

        entry = {
            "id": rid,
            "project": project_names.get(pid, "?"),
            "project_id": pid,
            "item_key": item_key,
            "field": field,
            "value": _json_preview(value),
            "stored_year": stored_year,
            "stored_scope": stored_scope,
            "target_year": target_year,
            "target_scope": target_scope,
            "year_wrong": year_wrong,
            "scope_wrong": scope_wrong,
        }
        report["misplaced"].append(entry)

        # 4) 检查目标位置有无冲突
        conflict_row = (await db.execute(text(
            "SELECT id FROM workpaper_field_overrides "
            "WHERE project_id = :pid AND year = :year AND scope = :scope "
            "  AND item_key = :item_key AND field = :field "
            "  AND id != :rid "
            "LIMIT 1"
        ), {
            "pid": pid,
            "year": target_year,
            "scope": target_scope,
            "item_key": item_key,
            "field": field,
            "rid": rid,
        })).first()

        target_key = (pid, target_year, target_scope, item_key, field)
        has_conflict = conflict_row is not None or target_key in claimed
        entry["has_conflict"] = has_conflict

        if has_conflict:
            # 冲突行不动：保留哪一份要人看两边的值与时间再定
            entry["conflict_id"] = str(conflict_row[0]) if conflict_row is not None else None
            report["conflicts"].append(entry)
            continue
        claimed.add(target_key)
        if apply:
            # 移动行
            await db.execute(text(
                "UPDATE workpaper_field_overrides "
                "SET year = :year, scope = :scope "
                "WHERE id = :rid"
            ), {
                "year": target_year,
                "scope": target_scope,
                "rid": rid,
            })
            report["moved"].append(entry)
        else:
            report["skipped"].append(entry)

    # 5) 写审计日志（apply 模式）—— 平台操作日志表是 ``logs``（库里没有 audit_logs；user_id 外键到 users，
    #    脚本没有操作人 ⇒ 留空）。原写法在 UPDATE 之后、提交之前抛错，整批不生效。
    if apply and report["moved"]:
        await db.execute(text(_AUDIT_LOG_SQL), {
            "id": str(uuid.uuid4()),
            "action": "fix_program_override_placement",
            "ttype": "workpaper_field_overrides",
            "detail": json.dumps({
                "moved_count": len(report["moved"]),
                "conflict_count": len(report["conflicts"]),
                "entries": [
                    {
                        "id": e["id"],
                        "from": f"year={e['stored_year']} scope={e['stored_scope']}",
                        "to": f"year={e['target_year']} scope={e['target_scope']}",
                    }
                    for e in report["moved"]
                ],
            }, ensure_ascii=False),
            "ts": datetime.now(timezone.utc),
        })

    return report


def _json_preview(value: Any) -> str:
    """值预览，截断过长的内容。"""
    s = json.dumps(value, ensure_ascii=False) if value is not None else "null"
    return s if len(s) <= 80 else s[:77] + "..."


def _print_report(report: dict[str, Any]) -> None:
    mode = report["mode"]
    misplaced = report["misplaced"]
    conflicts = report["conflicts"]
    moved = report["moved"]
    skipped = report["skipped"]

    print(f"\n{'='*70}")
    print(f"程序表字段覆盖位置修复报告 [{mode}]")
    print(f"{'='*70}")
    print(f"发现错位行: {len(misplaced)}")
    print(f"  其中有冲突: {len(conflicts)}")
    if mode == "apply":
        print(f"  已移动: {len(moved)}")
    else:
        print(f"  可移动: {len(skipped)}")
    print()

    for entry in misplaced:
        flag = "⚠️ 冲突" if entry.get("has_conflict") else ("✅ 已移动" if entry in moved else "📋 待移动")
        print(f"  {flag}")
        print(f"    项目: {entry['project']} ({entry['project_id'][:8]}…)")
        print(f"    item_key={entry['item_key']}  field={entry['field']}")
        if entry["year_wrong"]:
            print(f"    年度: {entry['stored_year']} → {entry['target_year']}")
        if entry["scope_wrong"]:
            print(f"    scope: {entry['stored_scope']} → {entry['target_scope']}")
        print(f"    值: {entry['value']}")
        print()


def main():
    parser = argparse.ArgumentParser(
        description="修复程序表字段覆盖的写读对齐（年度 / scope）"
    )
    parser.add_argument(
        "--apply", action="store_true",
        help="真实移动行（默认只报告）",
    )
    parser.add_argument(
        "--project", action="append", default=None, metavar="PROJECT_ID",
        help="只处理这个项目（可重复；默认全部项目）",
    )
    args = parser.parse_args()

    report = asyncio.run(run(apply=args.apply, project_ids=args.project))
    _print_report(report)


if __name__ == "__main__":
    main()
