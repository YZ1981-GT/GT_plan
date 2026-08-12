"""Task 26 浏览器实测的基线抓取 / 漂移核对 / 复原（默认只读）。

Task 26 要在真实库上点 UI（建议态→逐条确认→canonical apply / 逐循环覆盖写入 /
委派应用），实测完必须复原，且 tasks.md 要求「以**独立查询**核实，不看操作脚本
自身输出」。本脚本就是那个独立口径。

三条**不可复原项**（如实登记，禁谎报「已完整复原」）：
1. `procedure_row_tasks.lock_version` / `assignment_version` 是单调计数器，任何一次
   委派都会推进它；写回旧值会破坏乐观锁语义 ⇒ 只报差值，不回写。
2. `procedure_row_task_history` 是 **append-only**（触发器拒 DELETE）⇒ 只报新增行数。
3. `workpaper_delegation_history` 同上。

JSONB 写回一律 `CAST(:v AS jsonb)` + `json.dumps`。少了 CAST 会存成 **JSON 字符串标量**，
`jsonb_typeof` 变 `string`，下游读取全失效而不报错 —— `--verify` 有一条断言专钉这个。

用法::

    python backend/scripts/e2e/trim_e2e_baseline.py --capture
    python backend/scripts/e2e/trim_e2e_baseline.py --verify
    python backend/scripts/e2e/trim_e2e_baseline.py --restore   # 唯一会写库的开关
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

import sqlalchemy as sa  # noqa: E402
from sqlalchemy.ext.asyncio import create_async_engine  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

from app.core.config import settings  # noqa: E402

# e2e 指定项目（与 globalSetup 的 seed_fix_projects.py 同一个；实测不碰真实客户项目）
DEFAULT_PROJECT = "2aa00f57-1df4-4fe8-9840-2d65d0fd8749"
DEFAULT_SNAP = "backend/data/trim_e2e_baseline.json"

_Q_PROC = sa.text(
    "SELECT id::text AS id, wp_code, audit_cycle, status, skip_reason, suggestion_state"
    " FROM procedure_instances"
    " WHERE project_id = CAST(:pid AS uuid) AND is_deleted = false ORDER BY id"
)
_Q_CR = sa.text(
    "SELECT id::text AS id, wp_id::text AS wp_id, item_id, conclusion, remark"
    " FROM checklist_responses"
    " WHERE project_id = CAST(:pid AS uuid) AND item_id LIKE 'B50-T3-%' ORDER BY item_id"
)
_Q_TASKS = sa.text(
    "SELECT id::text AS id, wp_code, assignee_staff_id::text AS assignee_staff_id,"
    " reviewer_staff_id::text AS reviewer_staff_id, assignment_version, lock_version,"
    " workflow_status, applicability_status FROM procedure_row_tasks"
    " WHERE project_id = CAST(:pid AS uuid) AND is_deleted = false ORDER BY id"
)
_Q_NOTES = sa.text(
    "SELECT id::text AS id, note_section, is_empty, template_lineage"
    " FROM disclosure_notes"
    " WHERE project_id = CAST(:pid AS uuid) AND is_deleted = false ORDER BY id"
)
_Q_PU = sa.text(
    "SELECT id::text AS id, user_id::text AS user_id, role::text AS role,"
    " permission_level::text AS permission_level, is_deleted"
    " FROM project_users WHERE project_id = CAST(:pid AS uuid) ORDER BY user_id"
)
_Q_PA = sa.text(
    "SELECT id::text AS id, staff_id::text AS staff_id, role, is_deleted"
    " FROM project_assignments WHERE project_id = CAST(:pid AS uuid) ORDER BY staff_id"
)
_Q_COUNTS = sa.text(
    "SELECT (SELECT count(*) FROM procedure_row_task_history h"
    "          JOIN procedure_row_tasks t ON t.id = h.task_id"
    "         WHERE t.project_id = CAST(:pid AS uuid)) AS task_history,"
    "       (SELECT count(*) FROM workpaper_delegation_history w"
    "         WHERE w.project_id = CAST(:pid AS uuid)) AS deleg_history"
)


async def _read(conn, pid):
    def rows(res):
        return [dict(r._mapping) for r in res.all()]

    snap = {
        "project_id": pid,
        "procedure_instances": rows(await conn.execute(_Q_PROC, {"pid": pid})),
        "checklist_b50": rows(await conn.execute(_Q_CR, {"pid": pid})),
        "row_tasks": rows(await conn.execute(_Q_TASKS, {"pid": pid})),
        "disclosure_notes": rows(await conn.execute(_Q_NOTES, {"pid": pid})),
        "project_users": rows(await conn.execute(_Q_PU, {"pid": pid})),
        "project_assignments": rows(await conn.execute(_Q_PA, {"pid": pid})),
    }
    try:
        snap["history_counts"] = dict((await conn.execute(_Q_COUNTS, {"pid": pid})).one()._mapping)
    except Exception as e:  # noqa: BLE001
        # 🔴 表/列不存在时如实记 ERROR，不静默当 0 —— 0 会让「复原后无新增」假成立
        snap["history_counts"] = {"error": "%s: %s" % (type(e).__name__, str(e)[:160])}
    return snap


_RESTORABLE_PROC = ("status", "skip_reason", "suggestion_state")
_RESTORABLE_TASK = ("assignee_staff_id", "reviewer_staff_id", "workflow_status",
                    "applicability_status")
_RESTORABLE_NOTE = ("is_empty", "template_lineage")
# 单调计数器：只报差值、绝不回写（回写会破坏乐观锁语义）
_COUNTER_TASK = ("assignment_version", "lock_version")


def _idx(rows, key="id"):
    return {r[key]: r for r in rows}


def _diff(base, cur):
    """返回 (可复原差异, 不可复原差异) 两个清单。"""
    fixable, noted = [], []
    specs = (("procedure_instances", _RESTORABLE_PROC),
             ("row_tasks", _RESTORABLE_TASK),
             ("disclosure_notes", _RESTORABLE_NOTE))
    for table, fields in specs:
        b, c = _idx(base[table]), _idx(cur[table])
        for k in sorted(set(b) | set(c)):
            if k not in b:
                noted.append("%s 新增行 id=%s（基线里没有，不自动删）" % (table, k))
                continue
            if k not in c:
                noted.append("%s 行消失 id=%s（不自动重建）" % (table, k))
                continue
            for f in fields:
                if b[k].get(f) != c[k].get(f):
                    fixable.append((table, k, f, b[k].get(f), c[k].get(f)))
            if table == "row_tasks":
                for f in _COUNTER_TASK:
                    if b[k].get(f) != c[k].get(f):
                        noted.append("row_tasks id=%s %s: %s -> %s（单调计数器，不回写）"
                                     % (k, f, b[k].get(f), c[k].get(f)))
    # checklist B50：按 (wp_id, item_id) 判，新增的要删、改过的要还原
    bk = {(r["wp_id"], r["item_id"]): r for r in base["checklist_b50"]}
    ck = {(r["wp_id"], r["item_id"]): r for r in cur["checklist_b50"]}
    for k in sorted(set(bk) | set(ck), key=lambda x: (x[1], x[0])):
        if k not in bk:
            fixable.append(("checklist_b50", ck[k]["id"], "<DELETE>", None, ck[k]["item_id"]))
        elif k not in ck:
            noted.append("checklist_b50 行消失 %s（不自动重建）" % (k[1],))
        else:
            for f in ("conclusion", "remark"):
                if bk[k].get(f) != ck[k].get(f):
                    fixable.append(("checklist_b50", ck[k]["id"], f, bk[k].get(f), ck[k].get(f)))
    # project_users：唯一索引是 (project_id, user_id) WHERE is_deleted = false ⇒ 按 user_id 判。
    # 🔴 只支持「新增成员 → 删除」这一对（26.3b 要给项目加成员才能产出委派预览）。
    #    `role` / `permission_level` 是 enum，改动一律落 NOTE 不自动回写 —— 盲目 CAST 到未知
    #    枚举类型会在事务里炸掉，把「复原」变成「更坏的写入」。
    # project_assignments 是**真源**（委派向导执行人下拉读它，`project_users` 只是
    # `save_assignments` 顺带 upsert 的派生结果）⇒ 两张表都要收，且删派工后要连派生行一起清。
    # 唯一索引 (project_id, staff_id) WHERE is_deleted = false ⇒ 按 staff_id 判。
    ba = {r["staff_id"]: r for r in (base.get("project_assignments") or [])}
    ca = {r["staff_id"]: r for r in (cur.get("project_assignments") or [])}
    for k in sorted(set(ba) | set(ca)):
        if k not in ba:
            fixable.append(("project_assignments", ca[k]["id"], "<DELETE>", None, k))
        elif k not in ca:
            noted.append("project_assignments 派工消失 staff_id=%s（不自动重建）" % k)
        else:
            for f in ("role", "is_deleted"):
                if ba[k].get(f) != ca[k].get(f):
                    fixable.append(("project_assignments", ca[k]["id"], f, ba[k].get(f), ca[k].get(f)))

    bp = {r["user_id"]: r for r in (base.get("project_users") or [])}
    cp = {r["user_id"]: r for r in (cur.get("project_users") or [])}
    for k in sorted(set(bp) | set(cp)):
        if k not in bp:
            fixable.append(("project_users", cp[k]["id"], "<DELETE>", None, k))
        elif k not in cp:
            noted.append("project_users 成员消失 user_id=%s（不自动重建）" % k)
        else:
            for f in ("role", "permission_level", "is_deleted"):
                if bp[k].get(f) != cp[k].get(f):
                    noted.append("project_users user_id=%s %s: %s -> %s（enum/软删，不自动回写）"
                                 % (k, f, bp[k].get(f), cp[k].get(f)))

    bh, chh = base.get("history_counts") or {}, cur.get("history_counts") or {}
    for f in ("task_history", "deleg_history"):
        if isinstance(bh.get(f), int) and isinstance(chh.get(f), int) and bh[f] != chh[f]:
            noted.append("%s: %d -> %d（append-only，不删）" % (f, bh[f], chh[f]))
    if "error" in bh or "error" in chh:
        noted.append("history_counts 查询异常（ERROR 态，不能当 0 处理）: base=%s cur=%s"
                     % (bh.get("error"), chh.get("error")))
    return fixable, noted


_UPD = {
    "procedure_instances": "UPDATE procedure_instances SET %s WHERE id = CAST(:id AS uuid)",
    "row_tasks": "UPDATE procedure_row_tasks SET %s WHERE id = CAST(:id AS uuid)",
    "disclosure_notes": "UPDATE disclosure_notes SET %s WHERE id = CAST(:id AS uuid)",
    "checklist_b50": "UPDATE checklist_responses SET %s WHERE id = CAST(:id AS uuid)",
    "project_assignments": "UPDATE project_assignments SET %s WHERE id = CAST(:id AS uuid)",
}
_DEL = {
    "checklist_b50": "DELETE FROM checklist_responses WHERE id = CAST(:id AS uuid)",
    "project_users": "DELETE FROM project_users WHERE id = CAST(:id AS uuid)",
    "project_assignments": "DELETE FROM project_assignments WHERE id = CAST(:id AS uuid)",
}
_JSONB = {"suggestion_state", "template_lineage"}
_UUIDCOL = {"assignee_staff_id", "reviewer_staff_id"}


async def _restore(engine, fixable):
    applied = []
    async with engine.begin() as conn:            # 单事务，失败整体回滚
        for table, rid, field, want, _got in fixable:
            if field == "<DELETE>":
                await conn.execute(sa.text(_DEL[table]), {"id": rid})
                applied.append("DELETE %s %s" % (table, rid))
                continue
            if field in _JSONB:
                frag, val = "%s = CAST(:v AS jsonb)" % field, (None if want is None else json.dumps(want))
            elif field in _UUIDCOL:
                frag, val = "%s = CAST(:v AS uuid)" % field, want
            else:
                frag, val = "%s = :v" % field, want
            await conn.execute(sa.text(_UPD[table] % frag), {"id": rid, "v": val})
            applied.append("%s %s.%s <- %r" % (table, rid, field, want))
    return applied


_Q_JSONB_TYPE = sa.text(
    "SELECT count(*) FROM procedure_instances"
    " WHERE project_id = CAST(:pid AS uuid) AND suggestion_state IS NOT NULL"
    "   AND jsonb_typeof(suggestion_state) <> 'object'"
)


async def _run(args):
    snap_path = Path(args.snapshot)
    engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
    lines = []
    try:
        async with engine.connect() as conn:
            cur = await _read(conn, args.project)
        if args.capture:
            snap_path.parent.mkdir(parents=True, exist_ok=True)
            snap_path.write_text(json.dumps(cur, ensure_ascii=False, indent=1, default=str),
                                 encoding="utf-8")
            lines.append("已抓基线 -> %s" % snap_path)
            for k in ("procedure_instances", "checklist_b50", "row_tasks",
                      "disclosure_notes", "project_users", "project_assignments"):
                lines.append("  %-22s %d 行" % (k, len(cur[k])))
            lines.append("  history_counts %s" % cur["history_counts"])
            trimmed = sum(1 for r in cur["procedure_instances"]
                          if r["status"] in ("not_applicable", "skip"))
            lines.append("  其中已裁剪 %d 条；suggestion_state 非空 %d 条"
                         % (trimmed, sum(1 for r in cur["procedure_instances"]
                                         if r["suggestion_state"] is not None)))
            return 0, lines
        if not snap_path.exists():
            return 2, ["缺基线文件 %s —— 先跑 --capture" % snap_path]
        base = json.loads(snap_path.read_text(encoding="utf-8"))
        fixable, noted = _diff(base, cur)
        lines.append("可复原差异 %d 项 / 不可复原或需人工判断 %d 项" % (len(fixable), len(noted)))
        for t, rid, f, want, got in fixable:
            lines.append("  [FIX] %s %s.%s: 现值 %r -> 基线 %r" % (t, rid, f, got, want))
        for n in noted:
            lines.append("  [NOTE] %s" % n)
        if args.restore and fixable:
            lines.append("--- 执行复原（单事务）---")
            lines.extend("  " + x for x in await _restore(engine, fixable))
            async with engine.connect() as conn:      # 复原后**独立重读**核对
                again = await _read(conn, args.project)
                bad = (await conn.execute(_Q_JSONB_TYPE, {"pid": args.project})).scalar()
            f2, n2 = _diff(base, again)
            lines.append("复原后独立复核：残留可复原差异 %d 项（应为 0）" % len(f2))
            for t, rid, f, want, got in f2:
                lines.append("  [STILL] %s %s.%s: %r != %r" % (t, rid, f, got, want))
            lines.append("jsonb_typeof(suggestion_state) 非 object 的行数 = %s（应为 0；"
                         "非 0 说明写成了 JSON 字符串标量）" % bad)
        elif args.restore:
            lines.append("无可复原差异，未写库。")
        return 0, lines
    finally:
        await engine.dispose()


def main():
    ap = argparse.ArgumentParser(description="Task 26 基线抓取/核对/复原（默认只读）")
    ap.add_argument("--project", default=DEFAULT_PROJECT)
    ap.add_argument("--snapshot", default=DEFAULT_SNAP)
    ap.add_argument("--capture", action="store_true", help="抓基线（只读）")
    ap.add_argument("--verify", action="store_true", help="与基线比对（只读）")
    ap.add_argument("--restore", action="store_true", help="唯一会写库的开关")
    ap.add_argument("--out", default="tmp_t26_baseline_report.txt")
    args = ap.parse_args()
    if not (args.capture or args.verify or args.restore):
        ap.error("须指定 --capture / --verify / --restore 之一")
    rc, lines = asyncio.run(_run(args))
    Path(args.out).write_text("\n".join(lines), encoding="utf-8")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
