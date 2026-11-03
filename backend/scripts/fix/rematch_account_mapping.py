"""按新规则重做客户科目 → 标准科目自动映射，并重算试算表、重新生成报表（spec mapping-code-collision-and-fetch-by-mapping R4）。

方式：
- ``--mode rebuild``：客户科目表是旧导入、与当前有效余额表对不上时用（编码带「.0」、名称错一行）。
  按当前有效余额表重建客户科目表 → 自动映射按新规则逐条改（手工映射不动）。
- ``--mode collisions``（默认）：只改「按编码认、但一级科目名对不上」的自动映射（编码撞号），其余映射不动。
- ``--mode unmapped``：只给还没有映射的客户科目自动匹配（同底稿映射页「自动匹配」按钮），已有映射不动。
- ``--set 客户科目=标准科目``（可多次）：写手工映射（人工判断的结果，之后自动匹配 / 重做都不会动它）。

改完都全量重算试算表；本年度已生成过报表的重新生成。

用法（cwd = backend）::

    ..\\.venv\\Scripts\\python.exe scripts/fix/rematch_account_mapping.py --project <id 或名称片段> [--mode rebuild]       # 预览（只读）
    ..\\.venv\\Scripts\\python.exe scripts/fix/rematch_account_mapping.py --project ... --apply --backup backups/<文件>.json
    ..\\.venv\\Scripts\\python.exe scripts/fix/rematch_account_mapping.py --restore backups/<文件>.json                     # 还原并重算
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")


async def _projects(db, refs: list[str]) -> list[tuple[uuid.UUID, str]]:
    import sqlalchemy as sa

    from app.models.core import Project

    out = []
    for ref in refs:
        try:
            cond = Project.id == uuid.UUID(ref)
        except ValueError:
            cond = Project.name.like(f"%{ref}%")
        rows = (await db.execute(sa.select(Project.id, Project.name).where(cond, Project.is_deleted == sa.false()))).all()
        if len(rows) != 1:
            raise SystemExit(f"「{ref}」匹配到 {len(rows)} 个项目，请写得更具体或用项目 id：{[r[1] for r in rows]}")
        out.append((rows[0][0], rows[0][1]))
    return out


async def _year(db, pid: uuid.UUID, year: int | None) -> int:
    from app.services.mapping_service import _resolve_event_year

    resolved = year or await _resolve_event_year(pid, db)
    if not resolved:
        raise SystemExit(f"项目 {pid} 无可用年度，请用 --year 指定")
    return resolved


async def backup(path: Path, targets: list[tuple[uuid.UUID, str, int]]) -> None:
    """改动前留底（PG ``row_to_json`` 原文）：客户科目表、映射、试算表、报表。"""
    import sqlalchemy as sa

    from app.core.database import async_session

    data = {"created_at": datetime.now(timezone.utc).isoformat(), "projects": {}}
    async with async_session() as db:
        for pid, name, year in targets:
            def q(sql: str):
                return db.execute(sa.text(sql), {"pid": str(pid), "year": year})
            data["projects"][str(pid)] = {
                "name": name, "year": year,
                "account_chart": [json.loads(t) for t in (await q(
                    "SELECT row_to_json(a)::text FROM account_chart a WHERE a.project_id = :pid AND a.source = 'client' "
                    "ORDER BY a.account_code")).scalars().all()],
                "account_mapping": [json.loads(t) for t in (await q(
                    "SELECT row_to_json(m)::text FROM account_mapping m WHERE m.project_id = :pid "
                    "ORDER BY m.original_account_code")).scalars().all()],
                "trial_balance": [json.loads(t) for t in (await q(
                    "SELECT row_to_json(t)::text FROM trial_balance t WHERE t.project_id = :pid AND t.year = :year "
                    "ORDER BY t.standard_account_code")).scalars().all()],
                "financial_report": [json.loads(t) for t in (await q(
                    "SELECT row_to_json(f)::text FROM financial_report f WHERE f.project_id = :pid AND f.year = :year "
                    "ORDER BY f.report_type, f.row_code")).scalars().all()],
            }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    for pid, p in data["projects"].items():
        print(f"已留底 {p['name']}：客户科目 {len(p['account_chart'])}、映射 {len(p['account_mapping'])}、"
              f"试算表 {len(p['trial_balance'])}、报表 {len(p['financial_report'])} 行 → {path}")


async def _current_mappings(db, pid) -> dict[str, tuple[str, str]]:
    import sqlalchemy as sa

    from app.models.audit_platform_models import AccountMapping
    from app.services.mapping_level1_match import strip_dot_zero

    rows = (await db.execute(sa.select(AccountMapping.original_account_code, AccountMapping.standard_account_code,
                                       AccountMapping.mapping_type).where(
        AccountMapping.project_id == pid, AccountMapping.is_deleted == sa.false()))).all()
    return {strip_dot_zero(r[0]): (r[1], getattr(r[2], "value", str(r[2]))) for r in rows}


async def _std_names(db, pid) -> dict[str, str]:
    import sqlalchemy as sa

    from app.models.audit_platform_models import AccountChart, AccountSource

    return dict((await db.execute(sa.select(AccountChart.account_code, AccountChart.account_name).where(
        AccountChart.project_id == pid, AccountChart.source == AccountSource.standard,
        AccountChart.is_deleted == sa.false()))).all())


async def _chart_is_stale(db, pid, year: int) -> bool:
    """客户科目表与当前有效余额表的（编码, 名称）对不上 ⇒ 旧导入（编码带「.0」、名称错一行），需要重建。"""
    import sqlalchemy as sa

    from app.models.audit_platform_models import AccountChart, AccountSource, TbBalance
    from app.services.dataset_query import get_active_filter

    bal = TbBalance.__table__
    balance = set((await db.execute(sa.select(bal.c.account_code, bal.c.account_name).where(
        await get_active_filter(db, bal, pid, year)))).all())
    chart = set((await db.execute(sa.select(AccountChart.account_code, AccountChart.account_name).where(
        AccountChart.project_id == pid, AccountChart.source == AccountSource.client,
        AccountChart.is_deleted == sa.false()))).all())
    return bool(balance) and balance != chart


async def _rebuild(db, pid, year: int, apply: bool) -> None:
    """客户科目表过期就按有效余额表重建；自动映射按新规则逐条改（手工映射不动）。apply=False 时调用方回滚。

    ``account_mapping`` 唯一索引 (project_id, original_account_code) 不排除已删行 ⇒ 不能「删了再插」：
    同码的行原地更新（含复活已删行），新规则不再映射的自动映射停用，没有行的才插入。
    """
    import sqlalchemy as sa

    from app.models.audit_platform_models import AccountChart, AccountMapping, AccountSource, MappingType
    from app.services import mapping_service
    from app.services.mapping_level1_match import mapping_type_for, strip_dot_zero

    before = await _current_mappings(db, pid)
    names = await _std_names(db, pid)
    if await _chart_is_stale(db, pid, year):
        dropped = (await db.execute(sa.update(AccountChart).where(
            AccountChart.project_id == pid, AccountChart.source == AccountSource.client, AccountChart.is_deleted == sa.false(),
        ).values(is_deleted=True, deleted_at=datetime.now(timezone.utc)))).rowcount
        created = await mapping_service._generate_client_accounts_from_balance(pid, db, year=year)
        print(f"  客户科目表与有效余额表对不上：停用 {dropped} 行，按有效余额表重建 {created} 行")
    else:
        print("  客户科目表与有效余额表一致，不重建")

    suggestions = {strip_dot_zero(s.original_account_code): s for s in await mapping_service.auto_suggest(pid, db, year=year)}
    rows = (await db.execute(sa.select(AccountMapping).where(AccountMapping.project_id == pid))).scalars().all()
    manual = {strip_dot_zero(r.original_account_code) for r in rows
              if not r.is_deleted and r.mapping_type == MappingType.manual}
    by_exact = {r.original_account_code: r for r in rows}
    counts = {"updated": 0, "inserted": 0, "dropped": 0}
    for r in rows:  # 新规则不再映射（或换了编码写法）的自动映射停用；手工映射不动
        code = strip_dot_zero(r.original_account_code)
        keep = code in suggestions and suggestions[code].original_account_code == r.original_account_code
        if not r.is_deleted and r.mapping_type != MappingType.manual and not keep:
            r.is_deleted = True
            counts["dropped"] += 1
    for code, s in suggestions.items():
        if code in manual:
            continue
        row = by_exact.get(s.original_account_code)
        if row is None:
            db.add(AccountMapping(project_id=pid, original_account_code=s.original_account_code,
                                  original_account_name=s.original_account_name,
                                  standard_account_code=s.suggested_standard_code, mapping_type=mapping_type_for(s.confidence)))
            counts["inserted"] += 1
        elif (row.is_deleted or row.standard_account_code != s.suggested_standard_code
              or row.mapping_type != mapping_type_for(s.confidence) or row.original_account_name != s.original_account_name):
            row.is_deleted = False
            row.standard_account_code = s.suggested_standard_code
            row.original_account_name = s.original_account_name
            row.mapping_type = mapping_type_for(s.confidence)
            counts["updated"] += 1
    await db.flush()
    print(f"  自动映射：改 {counts['updated']}、新增 {counts['inserted']}、停用 {counts['dropped']}（手工映射 {len(manual)} 条不动）")
    after = {code: (s.suggested_standard_code, s.match_method) for code, s in suggestions.items()}
    after.update({code: before[code] for code in manual if code in before})
    _print_diff(before, after, names)
    if apply:
        await db.commit()


def _print_diff(before: dict, after: dict, names: dict[str, str]) -> None:
    changed = unchanged = 0
    lines = []
    for code in sorted(set(before) | set(after)):
        old = before.get(code)
        new = after.get(code)
        if old and new and old[0] == new[0]:
            unchanged += 1
            continue
        if old and old[1] == "manual":
            continue
        changed += 1
        o = f"{old[0]} {names.get(old[0], '')}" if old else "（未映射）"
        n = f"{new[0]} {names.get(new[0], '')}（{new[1]}）" if new else "（不自动映射，留给人工）"
        lines.append(f"    {code}: {o} → {n}")
    print(f"  映射变化 {changed} 条，不变 {unchanged} 条：")
    for line in lines:
        print(line)


async def _collisions(db, pid, year: int, apply: bool) -> None:
    import sqlalchemy as sa

    from app.models.audit_platform_models import AccountMapping, MappingType
    from app.services.mapping_level1_match import find_code_collisions

    found = await find_code_collisions(pid, db, year=year)
    print(f"  编码撞号的自动映射 {len(found)} 条：")
    for c in found:
        new = f"{c['new_code']} {c['new_name']}（{c['method']}）" if c["new_code"] else "（不自动映射，留给人工）"
        print(f"    {c['code']}（一级科目「{c['level1_name']}」）: {c['old_code']} {c['old_name']} → {new}")
    if not apply:
        return
    for c in found:
        values = ({"standard_account_code": c["new_code"], "mapping_type": MappingType.auto_exact}
                  if c["new_code"] else {"is_deleted": True})
        await db.execute(sa.update(AccountMapping).where(AccountMapping.id == c["mapping_id"]).values(**values))
    await db.commit()


async def _unmapped(db, pid, year: int, apply: bool) -> None:
    """只给还没有映射的客户科目按新规则自动匹配（与底稿映射页「自动匹配」按钮同一函数 ``auto_match``），已有映射不动。"""
    import sqlalchemy as sa

    from app.models.audit_platform_models import AccountMapping
    from app.services import mapping_service
    from app.services.mapping_level1_match import strip_dot_zero

    names = await _std_names(db, pid)
    mapped = {strip_dot_zero(c) for c in (await db.execute(sa.select(AccountMapping.original_account_code).where(
        AccountMapping.project_id == pid, AccountMapping.is_deleted == sa.false()))).scalars().all()}
    new = [s for s in await mapping_service.auto_suggest(pid, db, year=year) if strip_dot_zero(s.original_account_code) not in mapped]
    print(f"  未映射科目按新规则可配上 {len(new)} 条：")
    for s in new:
        print(f"    {s.original_account_code} {s.original_account_name}: → {s.suggested_standard_code} "
              f"{names.get(s.suggested_standard_code, '')}（{s.match_method}）")
    if apply:
        result = await mapping_service.auto_match(pid, db, year=year)  # 内部 commit
        print(f"  自动匹配：新增 {result.saved_count}，仍未匹配 {result.unmatched_count}")


def _parse_sets(items: list[str]) -> list[tuple[str, str]]:
    pairs = []
    for item in items:
        code, sep, std = item.partition("=")
        if not sep or not code.strip() or not std.strip():
            raise SystemExit(f"--set 格式是 客户科目编码=标准科目编码：{item!r}")
        pairs.append((code.strip(), std.strip()))
    return pairs


async def _manual(db, pid, pairs: list[tuple[str, str]], apply: bool) -> None:
    """按指定的「客户科目 → 标准科目」写手工映射（mapping_type=manual，自动匹配 / 重做都不会再动）。

    客户科目必须在客户科目表里、标准科目必须在本项目标准科目表里；同码已有映射（含已停用的）原地改，没有才新增
    （唯一索引 (project_id, original_account_code) 不排除已删行）。
    """
    import sqlalchemy as sa

    from app.models.audit_platform_models import AccountChart, AccountMapping, AccountSource, MappingType
    from app.services.mapping_level1_match import strip_dot_zero

    names = await _std_names(db, pid)
    clients = {strip_dot_zero(c): (c, n) for c, n in (await db.execute(sa.select(AccountChart.account_code, AccountChart.account_name).where(
        AccountChart.project_id == pid, AccountChart.source == AccountSource.client, AccountChart.is_deleted == sa.false()))).all()}
    rows = {strip_dot_zero(r.original_account_code): r for r in (await db.execute(sa.select(AccountMapping).where(
        AccountMapping.project_id == pid))).scalars().all()}
    for code, std in pairs:
        if strip_dot_zero(code) not in clients:
            raise SystemExit(f"客户科目表里没有 {code}，中止")
        if std not in names:
            raise SystemExit(f"本项目标准科目表里没有 {std}，中止")
    for code, std in pairs:
        client_code, client_name = clients[strip_dot_zero(code)]
        row = rows.get(strip_dot_zero(code))
        old = f"{row.standard_account_code} {names.get(row.standard_account_code, '')}" if row is not None and not row.is_deleted else "（未映射）"
        print(f"    {client_code} {client_name}: {old} → {std} {names[std]}（手工）")
        if row is None:
            db.add(AccountMapping(project_id=pid, original_account_code=client_code, original_account_name=client_name,
                                  standard_account_code=std, mapping_type=MappingType.manual))
        else:
            row.is_deleted = False
            row.standard_account_code = std
            row.original_account_name = client_name
            row.mapping_type = MappingType.manual
    await db.flush()
    if apply:
        await db.commit()


async def _recalc_and_reports(pid, year: int) -> None:
    """全量重算试算表（同 POST /trial-balance/recalc）；本年度已生成过报表的重新生成（同 POST /reports/generate）。"""
    import sqlalchemy as sa

    from app.core.database import async_session
    from app.models.report_models import FinancialReport
    from app.services.report_config_service import ReportConfigService
    from app.services.report_engine import ReportEngine
    from app.services.trial_balance_service import TrialBalanceService

    async with async_session() as db:
        await TrialBalanceService(db).full_recalc(pid, year)
        await db.commit()
        try:
            from app.services.prefill_engine import resolve_stale_after_recalc
            await resolve_stale_after_recalc(db, pid, year)
            await db.commit()
        except Exception as exc:  # noqa: BLE001 —— 与重算接口一致：收敛 stale 失败不阻断
            await db.rollback()
            print(f"  （底稿过期标记收敛失败，不影响重算：{exc!r}）")
        has_reports = (await db.execute(sa.select(sa.func.count()).select_from(FinancialReport).where(
            FinancialReport.project_id == pid, FinancialReport.year == year,
            FinancialReport.is_deleted == sa.false()))).scalar_one()
        if not has_reports:
            print("  试算表已重算；本年度没有生成过报表，跳过")
            return
        standard = await ReportConfigService.resolve_applicable_standard(db, pid)
        results = await ReportEngine(db).generate_all_reports(pid, year, standard)
        await db.commit()
        print(f"  试算表已重算；报表已重新生成（{standard}，{', '.join(f'{k} {len(v)} 行' for k, v in results.items() if isinstance(v, list))}）")


async def restore(path: Path) -> None:
    """按留底还原客户科目表与映射（逐行按 id 还原停用标记 / 名称 / 标准科目码；留底里没有的新行停用），再重算。"""
    import sqlalchemy as sa

    from app.core.database import async_session
    from app.models.audit_platform_models import AccountChart, AccountMapping, AccountSource, MappingType

    data = json.loads(path.read_text(encoding="utf-8"))
    for pid_text, p in data["projects"].items():
        pid = uuid.UUID(pid_text)
        async with async_session() as db:
            now = datetime.now(timezone.utc)
            chart_ids = [uuid.UUID(r["id"]) for r in p["account_chart"]]
            map_ids = [uuid.UUID(r["id"]) for r in p["account_mapping"]]
            await db.execute(sa.update(AccountChart).where(
                AccountChart.project_id == pid, AccountChart.source == AccountSource.client,
                AccountChart.id.notin_(chart_ids), AccountChart.is_deleted == sa.false()).values(is_deleted=True, deleted_at=now))
            await db.execute(sa.update(AccountMapping).where(
                AccountMapping.project_id == pid, AccountMapping.id.notin_(map_ids),
                AccountMapping.is_deleted == sa.false()).values(is_deleted=True))
            for r in p["account_chart"]:
                await db.execute(sa.update(AccountChart).where(AccountChart.id == uuid.UUID(r["id"])).values(
                    account_name=r["account_name"], is_deleted=r["is_deleted"],
                    deleted_at=datetime.fromisoformat(r["deleted_at"]) if r.get("deleted_at") else None))
            for r in p["account_mapping"]:
                await db.execute(sa.update(AccountMapping).where(AccountMapping.id == uuid.UUID(r["id"])).values(
                    standard_account_code=r["standard_account_code"], original_account_name=r["original_account_name"],
                    mapping_type=MappingType(r["mapping_type"]), is_deleted=r["is_deleted"]))
            await db.commit()
        print(f"已还原 {p['name']}：客户科目 {len(chart_ids)} 行、映射 {len(map_ids)} 条")
        await _recalc_and_reports(pid, p["year"])


async def main(args) -> int:
    from app.core.database import async_session, engine

    try:
        if args.restore:
            await restore(args.restore)
            return 0
        if args.apply and args.backup is None:
            raise SystemExit("--apply 必须同时给 --backup <文件>（会改映射、重算试算表与报表，先留底）")
        async with async_session() as db:
            targets = [(pid, name, await _year(db, pid, args.year)) for pid, name in await _projects(db, args.project)]
        if args.apply:
            await backup(args.backup, targets)
        for pid, name, year in targets:
            print(f"\n=== {name} {year}（{'手工映射' if args.set else args.mode}）===")
            async with async_session() as db:
                if args.set:
                    await _manual(db, pid, _parse_sets(args.set), args.apply)
                elif args.mode == "rebuild":
                    await _rebuild(db, pid, year, args.apply)
                elif args.mode == "unmapped":
                    await _unmapped(db, pid, year, args.apply)
                else:
                    await _collisions(db, pid, year, args.apply)
                if not args.apply:
                    await db.rollback()
            if args.apply:
                await _recalc_and_reports(pid, year)
        if not args.apply:
            print("\n（预览，未写库；加 --apply --backup <文件> 执行）")
        return 0
    finally:
        await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--project", action="append", default=[], help="项目 id 或名称片段（可多次）")
    parser.add_argument("--year", type=int, help="年度（默认：有效账套年度 → 项目审计年度）")
    parser.add_argument("--mode", choices=["collisions", "rebuild", "unmapped"], default="collisions")
    parser.add_argument("--set", action="append", default=[], metavar="客户科目=标准科目",
                        help="写手工映射（可多次；给了就不看 --mode）")
    parser.add_argument("--apply", action="store_true", help="执行（默认只预览）")
    parser.add_argument("--backup", type=Path, help="--apply 时必填：留底文件（JSON）")
    parser.add_argument("--restore", type=Path, help="按留底还原客户科目表与映射，并重算")
    args = parser.parse_args()
    if not args.restore and not args.project:
        parser.error("需要 --project 或 --restore")
    sys.exit(asyncio.run(main(args)))
