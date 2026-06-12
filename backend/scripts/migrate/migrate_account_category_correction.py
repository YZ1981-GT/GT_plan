"""存量 account_chart.category 错配修复 + 级联重算 trial_balance.category。

背景（2026-06-11 排查）：
旧 naive 前缀映射（6→expense / 4→revenue 一刀切）写入的 account_chart.category
大面积错配（6xxx 收入类标 expense / 4xxx 权益类标 revenue），导致 trial_balance
按 account_category 分方向汇总时假性借贷不平（"试算差额 44M"）。

本脚本：
1. 用修正后的 `_infer_category`（编码+名称双保险）重判 account_chart.category。
2. 级联：trial_balance.category 取自 account_chart（trial_balance_service `cat=std.category`），
   故按 standard_account_code 关联修正后的 account_chart category 回填 trial_balance。
3. dry-run 默认仅预览；--commit 才写库；快照备份表支持回滚；写 app_audit_log。

安全：
- dry-run 默认，--commit 显式开启。
- 仅改 category 字段，不动金额/方向（direction 另由符号约定迁移负责）。
- 快照备份 (project_id, table, record_id, old_category) → _category_correction_backup。
- PG-only：to_regclass 探测；非 PG 报错退出。

用法（Windows：python 非 python3）：
    # 全库预览
    python backend/scripts/migrate/migrate_account_category_correction.py --dry-run
    # 单项目预览
    python backend/scripts/migrate/migrate_account_category_correction.py --project <uuid> --dry-run
    # 执行
    python backend/scripts/migrate/migrate_account_category_correction.py --commit --operator <uuid|name>
    # 回滚
    python backend/scripts/migrate/migrate_account_category_correction.py --rollback --batch-id <uuid>
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import sqlalchemy as sa  # noqa: E402

import app.models  # noqa: E402,F401  注册 ORM metadata
from app.core.database import async_session  # noqa: E402
from app.services.account_chart_service import _infer_category  # noqa: E402

BACKUP_TABLE = "_category_correction_backup"
AUDIT_ACTION = "account_category_correction"


_BACKUP_DDL = f"""
CREATE TABLE IF NOT EXISTS {BACKUP_TABLE} (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    batch_id      uuid NOT NULL,
    table_name    text NOT NULL,
    record_id     uuid NOT NULL,
    project_id    uuid,
    account_code  text,
    old_category  text,
    new_category  text,
    created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_{BACKUP_TABLE}_batch ON {BACKUP_TABLE}(batch_id);
"""


async def _is_postgres(db) -> bool:
    return db.bind.dialect.name == "postgresql"


async def _table_exists(db, name: str) -> bool:
    r = await db.execute(sa.text("SELECT to_regclass(:n)"), {"n": name})
    return r.scalar() is not None


async def _ensure_backup_table(db) -> None:
    for stmt in _BACKUP_DDL.strip().split(";"):
        s = stmt.strip()
        if s:
            await db.execute(sa.text(s))


async def _scan_account_chart(db, project: str | None) -> list[dict]:
    """扫描 account_chart，返回需修正的行。"""
    where = "is_deleted = false"
    params: dict = {}
    if project:
        where += " AND project_id = :pid"
        params["pid"] = project
    rows = (await db.execute(sa.text(f"""
        SELECT id, project_id, account_code, account_name, category
        FROM account_chart WHERE {where}
    """), params)).all()
    out = []
    for rid, pid, code, name, cat in rows:
        r = _infer_category(code, name or "")
        rv = r.value if hasattr(r, "value") else str(r)
        if rv != cat:
            out.append({
                "id": rid, "project_id": pid, "account_code": code,
                "account_name": name, "old": cat, "new": rv,
            })
    return out


async def _scan_trial_balance(db, project: str | None) -> list[dict]:
    """扫描 trial_balance，按修正后的 _infer_category(name) 找出错配行.

    trial_balance.account_category 源自 account_chart，但部分行 account_name 可能为空；
    用 standard_account_code + account_name 重判（与 _infer_category 同口径）。
    """
    where = "is_deleted = false"
    params: dict = {}
    if project:
        where += " AND project_id = :pid"
        params["pid"] = project
    rows = (await db.execute(sa.text(f"""
        SELECT id, project_id, standard_account_code, account_name, account_category
        FROM trial_balance WHERE {where}
    """), params)).all()
    out = []
    for rid, pid, code, name, cat in rows:
        cur = cat.value if hasattr(cat, "value") else str(cat)
        r = _infer_category(code or "", name or "")
        rv = r.value if hasattr(r, "value") else str(r)
        if rv != cur:
            out.append({
                "id": rid, "project_id": pid, "account_code": code,
                "account_name": name, "old": cur, "new": rv,
            })
    return out


async def _apply(db, table: str, changes: list[dict], batch_id: str) -> None:
    """写快照 + set-based UPDATE category。"""
    for ch in changes:
        await db.execute(sa.text(f"""
            INSERT INTO {BACKUP_TABLE}
              (batch_id, table_name, record_id, project_id, account_code, old_category, new_category)
            VALUES (:b, :t, :rid, :pid, :code, :old, :new)
        """), {
            "b": batch_id, "t": table, "rid": str(ch["id"]),
            "pid": str(ch["project_id"]) if ch["project_id"] else None,
            "code": ch["account_code"], "old": ch["old"], "new": ch["new"],
        })
        await db.execute(sa.text(f"""
            UPDATE {table} SET account_category = :new, updated_at = now()
            WHERE id = :rid
        """) if table == "trial_balance" else sa.text(f"""
            UPDATE {table} SET category = :new, updated_at = now()
            WHERE id = :rid
        """), {"new": ch["new"], "rid": str(ch["id"])})


async def _audit(db, batch_id: str, operator: str, summary: dict) -> None:
    try:
        from app.services.audit_logger_enhanced import audit_logger
        await audit_logger.log_action(
            user_id=operator,
            action=AUDIT_ACTION,
            object_type="trial_balance",
            details={"batch_id": batch_id, **summary},
        )
    except Exception:
        # 审计失败不阻断主流程；快照备份表已可完整回溯
        pass


async def run(project: str | None, commit: bool, operator: str) -> None:
    async with async_session() as db:
        if not await _is_postgres(db):
            print("ERROR: 仅支持 PostgreSQL")
            return
        ac_changes = await _scan_account_chart(db, project)
        tb_changes = await _scan_trial_balance(db, project)

        print(f"=== account_chart 待修正: {len(ac_changes)} 行 ===")
        _print_breakdown(ac_changes)
        print(f"\n=== trial_balance 待修正: {len(tb_changes)} 行 ===")
        _print_breakdown(tb_changes)

        if not commit:
            print("\n[dry-run] 未写库。加 --commit 执行。")
            return

        if not ac_changes and not tb_changes:
            print("\n无需修正。")
            return

        batch_id = str(uuid.uuid4())
        await _ensure_backup_table(db)
        await _apply(db, "account_chart", ac_changes, batch_id)
        await _apply(db, "trial_balance", tb_changes, batch_id)
        await _audit(db, batch_id, operator, {
            "account_chart_fixed": len(ac_changes),
            "trial_balance_fixed": len(tb_changes),
        })
        await db.commit()
        print(f"\n[committed] batch_id={batch_id}")
        print(f"  account_chart 修正 {len(ac_changes)} / trial_balance 修正 {len(tb_changes)}")
        print(f"  回滚：--rollback --batch-id {batch_id}")


async def rollback(batch_id: str) -> None:
    async with async_session() as db:
        if not await _table_exists(db, BACKUP_TABLE):
            print("无备份表，无法回滚。")
            return
        rows = (await db.execute(sa.text(f"""
            SELECT table_name, record_id, old_category FROM {BACKUP_TABLE}
            WHERE batch_id = :b
        """), {"b": batch_id})).all()
        if not rows:
            print(f"batch_id={batch_id} 无备份记录。")
            return
        for table, rid, old in rows:
            col = "account_category" if table == "trial_balance" else "category"
            await db.execute(sa.text(f"""
                UPDATE {table} SET {col} = :old, updated_at = now() WHERE id = :rid
            """), {"old": old, "rid": str(rid)})
        await db.execute(sa.text(f"DELETE FROM {BACKUP_TABLE} WHERE batch_id = :b"),
                         {"b": batch_id})
        await db.commit()
        print(f"[rolled back] batch_id={batch_id}, 恢复 {len(rows)} 行。")


def _print_breakdown(changes: list[dict]) -> None:
    from collections import Counter
    c = Counter(f"{ch['old']}→{ch['new']}" for ch in changes)
    for k, n in sorted(c.items(), key=lambda x: -x[1]):
        print(f"  {k}: {n}")
    for ch in changes[:8]:
        print(f"    e.g. {ch['account_code']} [{ch['old']}→{ch['new']}] {ch['account_name']}")


def main() -> None:
    p = argparse.ArgumentParser(description="account_chart/trial_balance category 错配修复")
    p.add_argument("--project", help="限定项目 UUID（默认全库）")
    p.add_argument("--commit", action="store_true", help="执行写库（默认 dry-run）")
    p.add_argument("--dry-run", action="store_true", help="仅预览")
    p.add_argument("--operator", default="system", help="操作者（审计留痕）")
    p.add_argument("--rollback", action="store_true", help="回滚模式")
    p.add_argument("--batch-id", help="回滚的批次 ID")
    args = p.parse_args()

    if args.rollback:
        if not args.batch_id:
            print("回滚需 --batch-id")
            sys.exit(1)
        asyncio.run(rollback(args.batch_id))
        return

    commit = args.commit and not args.dry_run
    asyncio.run(run(args.project, commit, args.operator))


if __name__ == "__main__":
    main()
