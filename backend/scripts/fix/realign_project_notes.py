"""存量项目附注按现行种子对齐（spec disclosure-note-template-word-realignment Phase 3，design §4）。

仓库根执行（默认 dry-run：只读、事务回滚）::

    .venv\\Scripts\\python.exe backend/scripts/fix/realign_project_notes.py --all-targets
    .venv\\Scripts\\python.exe backend/scripts/fix/realign_project_notes.py --project <id> --apply
    .venv\\Scripts\\python.exe backend/scripts/fix/realign_project_notes.py --restore backend/backups/note_realign_x.json

``--apply``：每个项目每个年度一个 REPEATABLE READ 事务 —— 锁行 → 备份到 ``--backup-dir`` → 执行 → 重算计划须为空 →
已有行正文 / 表格哈希逐行不变 → 把操作后像（逐行摘要）补记进备份 → 提交，任一不满足即回滚该项目。

``--restore <备份>``：默认只预演（会删 / 插 / 改多少行、后像围栏判定）；``--apply`` 才恢复，且现状须与备份补记的后像
逐行一致（操作提交后又有人改过就拒绝，免得把别人的改动一起抹掉）；备份没有后像或围栏不放行时，看过预演后
加 ``--force-restore`` 才继续。恢复同样一个事务、恢复后逐字核对。

``--rebuild --project <id> --year <年度> [--apply]``：整年度推倒重建（Phase 6，``note_project_rebuild``）—— 备份 → 删除该
年度全部附注（含软删）与附注推送状态 / 章节锁 → 按现行模板生成（不调大模型）→ 提交后公式推送 → 校验；推送在提交
后另跑，备份没有后像围栏，恢复须 ``--restore <备份> --apply --force-restore``。

``--push --project <id> --year <年度> [--apply]``：按现有附注做一次公式推送 —— 一个事务里 预演 → 备份（附注 / 推送状态 /
底稿条目，推送会写底稿）→ 推送 → 再预演 → 判定（有底稿失败 / 并发冲突、或再预演仍要写 ⇒ 整体回滚）→ 补记后像 →
提交，提交后才发 SSE / 附注章节事件并校验；``--restore`` 连底稿条目一起恢复。

退出码：1 = 有项目失败（已回滚）；2 = 已完成但有待人工项（推送不到的目标、恢复预演围栏不放行）；0 = 全部干净。
完整报告（含每条动作与待人工项）写 ``--report``（默认 ``backend/backups/``，该目录不入库）。
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
from datetime import datetime
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

#: 本 spec 的存量修复目标（和平药房 2aa00f57 走 Phase 6 重建，不在此列）
TARGETS: dict[str, str] = {
    "94a40b23-21a2-4d7a-a38d-9fd059d57717": "【测试】附注批量甲",
    "989cebf5-c53e-4643-a5b4-e4eef6d04c6d": "【测试】附注批量乙",
    "0ec33ac9-3de5-4e65-b3bf-f9dccd7b2a49": "重药控股安徽",
    "52c04ed1-efcf-4b7c-9800-ce5a5e840d8d": "重庆医药集团医疗器械",
    "a7fc75e5-b67f-436d-a126-42423018b6ce": "陕西华氏医药",
    "c8621493-70aa-46a9-8285-e0674e4e1418": "宜宾新健康大药房临港店",
    "df5b8403-abbb-48af-b6a4-6fd44dfae5c9": "首汽租车（合并）",
}
DEFAULT_DIR = BACKEND / "backups"


async def _years(session_factory, project_id: uuid.UUID) -> list[int]:
    import sqlalchemy as sa

    async with session_factory() as db:
        return sorted((await db.execute(sa.text(
            "SELECT DISTINCT year FROM disclosure_notes WHERE project_id = :p"), {"p": project_id})).scalars().all())


async def _run_one(session_factory, project_id: uuid.UUID, year: int, *, apply: bool, backup_dir: Path,
                   stamp: str) -> dict:
    from app.services.note_project_realign_apply import (
        RealignError, RealignSkipped, begin_snapshot, realign_project, record_postimage,
    )

    backup = backup_dir / f"note_realign_{project_id}_{year}_{stamp}.json" if apply else None
    async with session_factory() as db:
        try:
            if apply:
                await begin_snapshot(db)
            report = await realign_project(db, project_id, year, apply=apply, backup_path=backup)
            if apply and "backup" in report:
                report["postimage"] = await record_postimage(db, backup)
        except RealignSkipped as err:
            await db.rollback()
            return {"project_id": str(project_id), "year": year, "skipped": str(err)}
        except RealignError as err:
            await db.rollback()
            return {"project_id": str(project_id), "year": year, "error": str(err)}
        if apply:
            await db.commit()
        else:
            await db.rollback()
    report["applied"] = apply and "after" in report
    return report


async def _tables_one(session_factory, project_id: uuid.UUID, year: int, *, apply: bool, backup_dir: Path,
                      stamp: str) -> dict:
    """表格结构搬值（Task 12）：dry-run 只读预演；``--apply`` 锁行 → 备份 → 搬 → 硬断言，失败回滚。"""
    from app.services.note_project_realign_apply import (
        RealignError, RealignSkipped, apply_table_realignment, begin_snapshot, plan_table_realignment,
        record_postimage,
    )

    async with session_factory() as db:
        try:
            if not apply:
                report = await plan_table_realignment(db, project_id, year)
                await db.rollback()
                return report
            await begin_snapshot(db)
            backup = backup_dir / f"note_tables_{project_id}_{year}_{stamp}.json"
            report = await apply_table_realignment(db, project_id, year, backup_path=backup)
            report["postimage"] = await record_postimage(db, backup)
        except RealignSkipped as err:
            await db.rollback()
            return {"project_id": str(project_id), "year": year, "skipped": str(err)}
        except RealignError as err:
            await db.rollback()
            return {"project_id": str(project_id), "year": year, "error": str(err)}
        await db.commit()
    report["applied"] = True
    return report


def _tables_summary(report: dict) -> str:
    name = TARGETS.get(report["project_id"], report["project_id"])
    if "skipped" in report:
        return f"- {name} {report['year']}：跳过（{report['skipped']}）"
    if "error" in report:
        return f"✗ {name} {report['year']}：{report['error']}"
    if report.get("applied"):
        return (f"✓ {name} {report['year']}：写 {report['written_sections']} 节，孤儿值 {report['orphan_values']}；"
                f"备份 {report.get('backup')}")
    return (f"· {name} {report['year']}：比对 {report['compared_sections']} 节，"
            f"会改 {report['changed_sections']}，孤儿 {report['orphan_sections']} 节 / "
            f"{report['orphan_values']} 值，不安全 {report['unsafe_sections']} 节")


async def _rebuild(session_factory, project_id: uuid.UUID, year: int, *, apply: bool, backup_dir: Path,
                   stamp: str) -> dict:
    """整年度推倒重建（Phase 6）：dry-run 只报现状；``--apply`` 备份 → 删 → 生成（一个事务）→ 提交后公式推送 → 校验。"""
    from app.services.formula_push import engine as push
    from app.services.note_project_realign_apply import RealignError
    from app.services.note_project_rebuild import plan_rebuild, rebuild_project

    async with session_factory() as db:
        try:
            if not apply:
                report = await plan_rebuild(db, project_id, year)
                report.pop("_codes", None)
                # 推送也会写底稿（系统值 / 派生值，人工值保留）：先看它对底稿的影响（按现有附注算，附注部分仅供参考）
                report["push_dry_run"] = _push_summary(await push.run(
                    db, project_id=project_id, year=year, trigger=push.MANUAL, dry_run=True))
                await db.rollback()
                return report
            backup = backup_dir / f"note_rebuild_{project_id}_{year}_{stamp}.json"
            report = await rebuild_project(db, project_id, year, backup_path=backup)
        except Exception as err:  # noqa: BLE001 — 生成链 strict 抛的任何错都整体回滚，删除一行不留
            await db.rollback()
            kind = "" if isinstance(err, RealignError) else f"{type(err).__name__}: "
            return {"project_id": str(project_id), "year": year, "error": f"{kind}{err}（已回滚，未改库）"}
        await db.commit()
    from app.services.note_readiness_service import run_validation_best_effort

    # 重建已提交、推送在提交后另跑 ⇒ 备份没有后像围栏，恢复须先 dry-run 看差异再 --apply --force-restore
    report["backup_fence"] = "unfenced"
    try:
        async with session_factory() as db:  # 推送自管保存点与提交；事件触发同口径（无操作人，不记编辑人）
            pushed = await push.run_and_commit(db, project_id=project_id, year=year, trigger=push.MANUAL)
    except Exception as err:  # noqa: BLE001 — 重建已提交：推送失败如实报错（退出码 1），不吞
        report["error"] = f"重建已提交，但公式推送失败：{type(err).__name__}: {err}"
        return report
    report["push"] = _push_summary(pushed)
    report["attention"] = _push_attention(pushed)
    async with session_factory() as db:
        validation = await run_validation_best_effort(db, project_id, year)
        report["validation"] = {k: v for k, v in (validation or {}).items() if not isinstance(v, (list, dict))}
    return report


async def _push(session_factory, project_id: uuid.UUID, year: int, *, apply: bool, backup_dir: Path,
                stamp: str) -> dict:
    """按现有附注做一次公式推送：dry-run 只预演；``--apply`` 在一个 REPEATABLE READ 事务里 预演 → 备份（附注 / 推送状态 /
    底稿条目）→ 推送 → 再预演 → 判定（:func:`_push_blocking`，不过整体回滚）→ 补记后像 → 提交，提交后才发通知、校验。"""
    from app.services.formula_push import engine as push
    from app.services.note_project_realign_apply import RealignError, begin_snapshot, record_postimage, write_backup

    report: dict = {"project_id": str(project_id), "year": year}
    async with session_factory() as db:
        try:
            if apply:
                await begin_snapshot(db)
            preview = await push.run(db, project_id=project_id, year=year, trigger=push.MANUAL, dry_run=True)
            report["push_dry_run"] = _push_summary(preview)
            if not apply:
                await db.rollback()
                report["attention"] = _push_attention(preview)
                return report
            backup = backup_dir / f"note_push_{project_id}_{year}_{stamp}.json"
            report["backup"] = await write_backup(db, project_id, year, backup, include_workpapers=True)
            # 无操作人 ⇒ 不记编辑人（与事件触发同口径）；只 flush，提交由本函数在判定通过后做
            result = await push.run(db, project_id=project_id, year=year, trigger=push.MANUAL)
            report["push"] = _push_summary(result)
            again = await push.run(db, project_id=project_id, year=year, trigger=push.MANUAL, dry_run=True)
            report["push_again"] = _push_summary(again)
            blocking = _push_blocking(result, again)
            if blocking:
                raise RealignError("；".join(blocking))
            report["postimage"] = await record_postimage(db, backup)
            await db.commit()
        except Exception as err:  # noqa: BLE001 — 任何一步失败整体回滚，库里不留半次推送
            await db.rollback()
            kind = "" if isinstance(err, RealignError) else f"{type(err).__name__}: "
            report["error"] = f"{kind}{err}（已回滚，未改库）"
            return report
    report["attention"] = _push_attention(again)
    await push.notify_committed(result)
    from app.services.note_readiness_service import run_validation_best_effort

    async with session_factory() as db:
        validation = await run_validation_best_effort(db, project_id, year)
        report["validation"] = {k: v for k, v in (validation or {}).items() if not isinstance(v, (list, dict))}
    return report


def _push_blocking(result, again) -> list[str]:
    """不能提交的推送：本次有底稿失败 / 并发冲突（``partial``），或推送后再预演仍要写（不幂等）。"""
    problems = []
    if result.status != "succeeded":
        problems.append(f"推送状态 {result.status}（有底稿失败或并发冲突）：{result.warnings[:3]}")
    if again.status != "succeeded":
        problems.append(f"推送后再预演状态 {again.status}：{again.warnings[:3]}")
    if again.written_count:
        problems.append(f"推送后再预演仍有 {again.written_count} 格要写（不幂等）")
    return problems


def _push_attention(result) -> dict | None:
    """推送不到的目标（skipped / conflict）与非 succeeded 状态：不挡提交，但退出码 2，逐条进报告待人工处理。"""
    from collections import Counter

    from app.services.formula_push.results import CONFLICT, SKIPPED

    items = [i for i in result.items if i.action in (SKIPPED, CONFLICT)]
    if not items and result.status == "succeeded":
        return None
    return {"status": result.status, "unresolved": len(items),
            "by_reason": dict(Counter(f"{i.domain}:{i.reason}" for i in items).most_common(20)),
            "items": [i.as_dict() for i in items[:200]]}


def _exit_code(reports: list[dict]) -> int:
    """1 = 有失败（该项目已回滚）；2 = 已完成但有待人工项（推送不到的目标 / 后像围栏不放行）；0 = 全部干净。"""
    if any("error" in r for r in reports):
        return 1
    return 2 if any(r.get("attention") for r in reports) else 0


def _push_report_line(report: dict) -> str:
    head = f"{TARGETS.get(report['project_id'], report['project_id'])} {report['year']}"
    mark = "✗" if "error" in report else ("!" if report.get("attention") else "·")
    lines = [f"{mark} {head}"]
    for key, label in (("push_dry_run", "预演"), ("backup", "备份"), ("push", "推送"), ("push_again", "再预演"),
                       ("postimage", "后像"), ("validation", "校验"), ("error", "错误")):
        if key in report:
            lines.append(f"  {label}：{report[key]}")
    if report.get("attention"):
        att = report["attention"]
        lines.append(f"  待人工：状态 {att['status']}，推送不到 {att['unresolved']} 项：{att['by_reason']}")
    return "\n".join(lines)


def _push_summary(result) -> dict:
    from collections import Counter

    return {"status": result.status, "by_domain_action": dict(Counter(f"{i.domain}:{i.action}" for i in result.items)),
            "workpaper_items_written": len(result.changed_items), "note_sections_written": len(result.note_sections),
            "warnings": result.warnings[:10]}


def _rebuild_summary(report: dict) -> str:
    if "error" in report:
        return f"✗ {report['project_id']} {report['year']}：{report['error']}"
    head = (f"{report['project_id']} {report['year']}（{report['template_type']}/{report['report_scope']}，模板 "
            f"{report['templates']} 节，前置 {'满足' if report['prerequisite'].get('ok') else report['prerequisite']}）")
    lines = [head, f"  现状：{report['before']}"]
    if "push_dry_run" in report:
        lines.append(f"  公式推送预演（按现有附注）：{report['push_dry_run']}")
    if "after" in report:
        lines += [f"  已删：{report['deleted']}；备份 {report['backup']}（无后像围栏：恢复先 dry-run，再 --apply "
                  "--force-restore）", f"  重建后：{report['after']}",
                  f"  推送：{report['push']}；校验：{report['validation']}"]
    if report.get("attention"):
        att = report["attention"]
        lines.append(f"  待人工：状态 {att['status']}，推送不到 {att['unresolved']} 项：{att['by_reason']}")
    return "\n".join(lines)


def _summary(report: dict) -> str:
    name = TARGETS.get(report["project_id"], report["project_id"])
    if "skipped" in report:
        return f"- {name} {report['year']}：跳过（{report['skipped']}）"
    if "error" in report:
        return f"✗ {name} {report['year']}：{report['error']}"
    counts = report["plan"]["counts"]
    acts = {k: v for k, v in counts.items() if v}
    tail = f"；执行后 {report['after']}" if report.get("after") is not None else ""
    return (f"{'✓' if report.get('applied') else '·'} {name} {report['year']}（{report['template_type']}/"
            f"{report['report_scope']}，行 {report['active_rows']}/{report['rows']}，模板 {report['templates']}）"
            f"：{acts or '无差异'}{tail}")


async def _drop(session_factory, project_id: uuid.UUID, year: int, sections: list[str], *, apply: bool,
                backup_dir: Path, stamp: str) -> dict:
    """软删重复编号行：dry-run 只报判据；``--apply`` 备份后软删并复核（一个事务）。"""
    from app.services.note_project_realign_apply import (
        RealignError,
        RealignSkipped,
        begin_snapshot,
        drop_duplicate_sections,
        record_postimage,
    )

    async with session_factory() as db:
        try:
            if apply:
                await begin_snapshot(db)
            report = await drop_duplicate_sections(db, project_id, year, sections, apply=apply,
                                                   backup_dir=backup_dir, stamp=stamp)
            if apply and report.get("dropped"):
                report["postimage"] = await record_postimage(db, Path(report["backup"]["path"]))
        except RealignSkipped as err:
            await db.rollback()
            return {"project_id": str(project_id), "year": year, "skipped": str(err)}
        except RealignError as err:
            await db.rollback()
            return {"project_id": str(project_id), "year": year, "error": str(err)}
        if apply and report.get("dropped"):
            await db.commit()
        else:
            await db.rollback()
    return report


def _drop_report_line(report: dict) -> str:
    head = f"{TARGETS.get(report['project_id'], report['project_id'])} {report.get('year')}"
    if "error" in report or "skipped" in report:
        return f"✗ {head}：{report.get('error') or report.get('skipped')}"
    lines = [f"{'✓' if report.get('dropped') else '·'} {head}（可删 {report['droppable_count']}）"]
    for code, c in report["candidates"].items():
        gates = "，".join(f"{k}={'✓' if v else '✗'}" for k, v in c["gates"].items())
        lines.append(f"  {code}「{c['section_title']}」droppable={c['droppable']}：{gates}"
                     f"；准则={c['current_standard']!r} 同标题现行={c['same_title_live']}")
        if c["business_values"]:
            lines.append(f"    业务实值：{c['business_values']}")
    if report.get("missing"):
        lines.append(f"  未找到：{report['missing']}")
    if "dropped" in report:
        lines.append(f"  已软删：{report['dropped']}；备份 {report['backup']}")
    return "\n".join(lines)


async def _restore(session_factory, path: Path, *, apply: bool, force: bool) -> dict:
    """按备份恢复：默认只预演（删 / 插 / 改行数与后像围栏判定）；``--apply`` 在 REPEATABLE READ 事务里过围栏后恢复。"""
    from app.services.note_project_realign_apply import RealignError, begin_snapshot, plan_restore, restore_backup

    async with session_factory() as db:
        try:
            if apply:
                await begin_snapshot(db)
                report = await restore_backup(db, path, force=force)
                await db.commit()
            else:
                report = await plan_restore(db, path)
                await db.rollback()
        except Exception as err:  # noqa: BLE001 — 恢复失败整体回滚
            await db.rollback()
            kind = "" if isinstance(err, RealignError) else f"{type(err).__name__}: "
            return {"path": str(path), "error": f"{kind}{err}（已回滚，未改库）"}
    report["path"] = str(path)
    if not apply and report["fence"] in ("unfenced", "mismatch"):
        report["attention"] = {"fence": report["fence"], "drift": {t: len(ids) for t, ids in report["drift"].items()}}
    return report


_FENCE_TEXT = {"ok": "现状与后像一致", "mismatch": "操作后有改动", "unfenced": "备份没有后像",
               "already_restored": "现状已与备份一致"}


def _restore_line(report: dict) -> str:
    if "error" in report:
        return f"✗ 恢复未执行：{report['error']}"
    head = f"{TARGETS.get(report['project_id'], report['project_id'])} {report['year']}"
    fence = _FENCE_TEXT[report["fence"]]
    if report.get("restored"):
        forced = "，--force-restore 放行" if report.get("forced") else ""
        return f"✓ 已恢复 {head}：{report['counts']}（围栏：{fence}{forced}）"
    if report["fence"] == "already_restored":
        return f"· {head}：{fence}，无需恢复"
    lines = [f"{'!' if report.get('attention') else '·'} 预演恢复 {head}：围栏 {fence}；将改动 {report['delta']}"]
    for table, ids in report["drift"].items():
        lines.append(f"  操作后变化 {table} {len(ids)} 行：{ids[:5]}")
    return "\n".join(lines)


async def main() -> int:
    parser = argparse.ArgumentParser(description="存量项目附注按现行种子对齐（默认 dry-run）")
    who = parser.add_mutually_exclusive_group(required=True)
    who.add_argument("--project", action="append", help="项目 id（可多次）")
    who.add_argument("--all-targets", action="store_true", help="本 spec 的 7 个存量目标项目")
    who.add_argument("--restore", type=Path, help="按备份文件恢复")
    parser.add_argument("--year", type=int, help="只处理该年度（默认该项目有附注的全部年度）")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="只出计划（默认）")
    mode.add_argument("--apply", action="store_true", help="备份后执行")
    parser.add_argument("--backup-dir", type=Path, default=DEFAULT_DIR)
    parser.add_argument("--report", type=Path, help="完整报告 JSON 路径")
    parser.add_argument("--rebuild", action="store_true",
                        help="整年度推倒重建（备份 → 删除该年度全部附注 → 按现行模板生成 → 公式推送）；需 --project 与 --year")
    parser.add_argument("--tables", action="store_true",
                        help="表格结构搬值（Task 12）：把库内表值搬进现行种子表结构，孤儿进 _realign_orphans；"
                             "默认 dry-run，--apply 时锁行 → 备份 → 搬 → 断言非空值多重集合与正文哈希不变")
    parser.add_argument("--push", action="store_true",
                        help="按现有附注做公式推送（一个事务：预演 → 备份附注 / 推送状态 / 底稿条目 → 推送 → 再预演须 0 写且无失败"
                             " → 提交；推送不到的目标退出码 2）；需 --project 与 --year")
    parser.add_argument("--drop", action="append", metavar="章节号",
                        help="软删跨准则同步进来的重复编号行（四道硬门全过才删）；需 --project 与 --year，可多次")
    parser.add_argument("--force-restore", action="store_true",
                        help="与 --restore --apply 合用：后像围栏不放行（备份无后像 / 操作后有人改过）时仍恢复；"
                             "先不带 --apply 看清 drift 与 delta")
    args = parser.parse_args()
    if (args.rebuild or args.push or args.drop) and not (args.project and args.year):
        parser.error("--rebuild / --push / --drop 需要 --project 与 --year")
    if sum(bool(x) for x in (args.rebuild, args.push, args.drop, args.tables)) > 1:
        parser.error("--rebuild / --push / --drop / --tables 互斥")
    if args.force_restore and not (args.restore and args.apply):
        parser.error("--force-restore 只能与 --restore --apply 合用")

    from app.core.database import async_session

    if args.tables:
        ids = list(TARGETS) if args.all_targets else (args.project or [])
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        reports = []
        for pid_text in ids:
            pid = uuid.UUID(pid_text)
            for year in ([args.year] if args.year else await _years(async_session, pid)):
                report = await _tables_one(async_session, pid, year, apply=args.apply, backup_dir=args.backup_dir,
                                           stamp=stamp)
                reports.append(report)
                print(_tables_summary(report))
        out = args.report or args.backup_dir / f"note_tables_report_{'apply' if args.apply else 'dry'}_{stamp}.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(reports, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        print(f"报告：{out}")
        return 1 if any("error" in r for r in reports) else 0

    if args.drop:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        reports = [await _drop(async_session, uuid.UUID(p), args.year, args.drop, apply=args.apply,
                               backup_dir=args.backup_dir, stamp=stamp) for p in args.project]
        print("\n".join(_drop_report_line(r) for r in reports))
        out = args.report or args.backup_dir / f"note_drop_report_{'apply' if args.apply else 'dry'}_{stamp}.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(reports, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        print(f"报告：{out}")
        return 1 if any("error" in r for r in reports) else 0

    if args.push:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        reports = [await _push(async_session, uuid.UUID(p), args.year, apply=args.apply, backup_dir=args.backup_dir,
                               stamp=stamp) for p in args.project]
        print("\n".join(_push_report_line(r) for r in reports))
        out = args.report or args.backup_dir / f"note_push_report_{'apply' if args.apply else 'dry'}_{stamp}.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(reports, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        print(f"报告：{out}")
        return _exit_code(reports)

    if args.rebuild:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        reports = [await _rebuild(async_session, uuid.UUID(p), args.year, apply=args.apply, backup_dir=args.backup_dir,
                                  stamp=stamp) for p in args.project]
        print("\n".join(_rebuild_summary(r) for r in reports))
        out = args.report or args.backup_dir / f"note_rebuild_report_{'apply' if args.apply else 'dry'}_{stamp}.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(reports, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        print(f"报告：{out}")
        return _exit_code(reports)

    if args.restore:
        report = await _restore(async_session, args.restore, apply=args.apply, force=args.force_restore)
        print(_restore_line(report))
        return _exit_code([report])

    ids = list(TARGETS) if args.all_targets else args.project
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    reports = []
    for pid_text in ids:
        pid = uuid.UUID(pid_text)
        for year in ([args.year] if args.year else await _years(async_session, pid)):
            report = await _run_one(async_session, pid, year, apply=args.apply, backup_dir=args.backup_dir,
                                    stamp=stamp)
            reports.append(report)
            print(_summary(report))
    out = args.report or args.backup_dir / f"note_realign_report_{'apply' if args.apply else 'dry'}_{stamp}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(reports, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(f"报告：{out}")
    return 1 if any("error" in r for r in reports) else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
