"""已生成又被裁掉的底稿收口（spec procedure-trim-generation-delegation-chain 需求 8 / 任务 19）。

仓库根执行（默认 dry-run：只读、事务回滚）::

    .venv\\Scripts\\python.exe backend/scripts/fix/recycle_trimmed_workpapers.py --project-id <id> --restore-misjudged
    .venv\\Scripts\\python.exe backend/scripts/fix/recycle_trimmed_workpapers.py --project-id <id> --restore-misjudged --apply

``--apply``：① 一个事务：算计划（裁剪预览凭证）→ 备份现状到 ``--backup-dir``（``recycle_trimmed_<项目>_<时间>.json``）→
执行（``--restore-misjudged`` 时恢复系统误裁的；其余粗裁原样重放：已生成的已裁底稿移入回收站、范围内任务级联取消）→
对账不变式不成立即回滚 → 提交；② 另一个事务按项目用过的模板集重新生成（已裁 / 在回收站 / 已存在的不新建）；③ 只读复核：
对账 + 复算计划（应为空，可重跑）。有编制内容的底稿须加 ``--confirm-substantive`` 才处理。

恢复：回收站页面逐张恢复（仍被裁剪的须先在「配置裁剪」恢复执行），备份文件留存全部原值。核心逻辑见
``app/services/procedure_trim_cleanup.py``。
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import uuid
from datetime import datetime
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))
DEFAULT_DIR = BACKEND / "backups"


async def _actor_id(db, username: str) -> uuid.UUID:
    import sqlalchemy as sa

    from app.models.core import User

    uid = (await db.execute(sa.select(User.id).where(
        User.username == username, User.is_active == sa.true()))).scalar_one_or_none()
    if uid is None:
        raise SystemExit(f"用户 {username} 不存在或已停用")
    return uid


def _codes(items) -> str:
    items = list(items or [])
    return "、".join(items) if items else "无"


def _summary(report: dict) -> str:
    plan, before = report["plan"], report["before"]
    rp = plan["recycle_preview"] or {}
    lines = [
        f"项目 {report['project_id']}（{plan['year']} 年度），模板集「{report['template_set']['name']}」"
        f"（{report['template_set']['codes']} 个编码）",
        f"现状：在用底稿 {before['wp_index_live']} 张，回收站 {before['wp_index_in_recycle']} 张；"
        f"在用但已裁 {len(before['live_trimmed'])} 张；按模板集生成将新建 {len(before['generation']['would_create'])} 张",
        f"误裁恢复执行：{_codes(m['code'] for m in plan['misjudged'])}",
    ] + [f"  {m['code']}：{m['correction']}" for m in plan["misjudged"]] + [
        f"粗裁原样重放：{len(plan['kept'])} 个编码；移入回收站 {len(rp.get('to_recycle') or [])} 张"
        f"（有编制内容 {len(rp.get('substantive') or [])} 张），从回收站恢复 {len(rp.get('to_restore') or [])} 张，"
        f"级联取消任务 {len(plan['cascade_tasks'])} 条",
    ]
    if plan["data_but_manual"]:
        lines.append(f"有数据但不是系统自动裁的（未动，请人工确认）：{_codes(d['code'] for d in plan['data_but_manual'])}")
    if plan["manual_review"]:
        lines.append(f"跳过（{'；'.join(m['code'] + m['reason'] for m in plan['manual_review'])}）")
    if "applied" in report:
        a = report["applied"]
        lines.append(f"已执行：移入回收站 {len(a.get('recycled_codes') or [])} 张，恢复 {len(a.get('restored_codes') or [])}"
                     f" 张，更正 {_codes(a.get('corrected'))}；备份 {report.get('backup')}")
    if "regenerated" in report:
        g = report["regenerated"]
        lines.append(f"重新生成：新建 {_codes(g['created'])}；已裁跳过 {len(g['skipped_trimmed_codes'])} 个，"
                     f"在回收站 {len(g['in_recycle_codes'])} 个")
    if "after" in report:
        af = report["after"]
        lines.append(f"对账：在用底稿 {af['wp_index_live']} 张，回收站 {af['wp_index_in_recycle']} 张"
                     f"（{af['in_recycle_by_kind']}）；在用但已裁 {_codes(af['live_trimmed'])}；回收站底稿下未终结任务 "
                     f"{af['open_tasks_under_recycled']} 条；复算计划为空：{report.get('replan_is_empty')}")
    if report.get("error"):
        lines.append(f"失败（已回滚）：{report['error']}")
    return "\n".join(lines)


async def main() -> int:
    parser = argparse.ArgumentParser(description="已生成又被裁掉的底稿收口（默认 dry-run）")
    parser.add_argument("--project-id", required=True, type=uuid.UUID)
    parser.add_argument("--restore-misjudged", action="store_true",
                        help="系统按无数据自动裁剪、新判定有数据的恢复执行（记「系统误判更正」）")
    parser.add_argument("--apply", action="store_true", help="备份后执行（默认只出计划）")
    parser.add_argument("--confirm-substantive", action="store_true", help="有编制内容的底稿也移入回收站")
    parser.add_argument("--actor", default="admin", help="操作人用户名（记入裁剪与回收站留痕）")
    parser.add_argument("--template-set-id", type=uuid.UUID, help="重新生成用的模板集（默认与本项目底稿重合最多的）")
    parser.add_argument("--no-regenerate", action="store_true", help="--apply 时不重新生成")
    parser.add_argument("--backup-dir", type=Path, default=DEFAULT_DIR)
    args = parser.parse_args()
    os.chdir(BACKEND)  # 生成时按相对路径建项目底稿目录，与后端服务同一工作目录

    from fastapi import HTTPException

    from app.core.database import async_session
    from app.services import procedure_trim_cleanup as cleanup

    pid = args.project_id
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report: dict = {"project_id": str(pid), "mode": "apply" if args.apply else "dry-run", "stamp": stamp}
    ok = True
    async with async_session() as db:
        actor = await _actor_id(db, args.actor)
        ts = await cleanup.pick_template_set(db, pid, args.template_set_id)
        ts_id, ts_codes = ts.id, list(ts.template_codes or [])
        report["template_set"] = {"id": str(ts_id), "name": ts.set_name, "codes": len(ts_codes)}
        plan = await cleanup.plan_cleanup(db, pid, actor_user_id=actor, restore_misjudged=args.restore_misjudged)
        report["plan"] = plan.to_dict()
        report["before"] = await cleanup.reconcile(db, pid, template_codes=ts_codes)
        if args.apply and not plan.is_empty:
            backup = args.backup_dir / f"recycle_trimmed_{pid}_{stamp}.json"
            backup.parent.mkdir(parents=True, exist_ok=True)
            backup.write_text(json.dumps(await cleanup.snapshot(db, plan), ensure_ascii=False, indent=1, default=str),
                              encoding="utf-8")
            report["backup"] = str(backup)
            try:
                report["applied"] = await cleanup.apply_cleanup(
                    db, plan, actor_user_id=actor, request_id=f"recycle-trimmed-{stamp}",
                    confirm_substantive=args.confirm_substantive)
            except (HTTPException, cleanup.CleanupError) as exc:
                await db.rollback()
                report["error"] = getattr(exc, "detail", None) or str(exc)
                ok = False
            else:
                await db.commit()
        else:
            await db.rollback()

    if args.apply and ok:
        if not args.no_regenerate:
            async with async_session() as db:
                report["regenerated"] = await cleanup.regenerate(db, pid, template_set_id=ts_id, year=plan.year,
                                                                 actor_user_id=actor)
                await db.commit()
        async with async_session() as db:
            report["after"] = await cleanup.reconcile(db, pid, template_codes=ts_codes)
            replan = await cleanup.plan_cleanup(db, pid, actor_user_id=actor, restore_misjudged=args.restore_misjudged)
            report["replan_is_empty"] = replan.is_empty
            if not replan.is_empty:
                report["replan"] = replan.to_dict()
            await db.rollback()
        # 重新生成新建的若是已裁编码，也会落进 live_trimmed
        ok = (not report["after"]["live_trimmed"] and not report["after"]["open_tasks_under_recycled"]
              and report["replan_is_empty"])

    out = args.backup_dir / f"recycle_trimmed_report_{report['mode']}_{pid}_{stamp}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(_summary(report))
    print(f"报告：{out}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
