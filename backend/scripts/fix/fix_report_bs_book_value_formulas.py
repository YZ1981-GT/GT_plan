"""报表 BS-028 固定资产 / BS-032 无形资产补减减值准备、BS-037 其他非流动资产公式置空（全局发布，幂等）。

spec: .kiro/specs/formula-fetch-followup-defect-closure R6.4

- BS-028 固定资产 = 1601 固定资产 − 1602 累计折旧 − 1603 固定资产减值准备 + 1606 固定资产清理（四个准则一致）。
  原先只有 soe_standalone 加了 1606，四个准则都没减 1603：资产负债表「固定资产」把减值准备算在账面价值里。
  各准则都没有单列「固定资产清理」行（2026-10-24 现查 report_config），按现行报表格式并入固定资产行。
- BS-032 无形资产 = 1701 无形资产 − 1702 累计摊销 − 1703 无形资产减值准备。
- BS-037 其他非流动资产：原公式 TB('1911') 的 1911 在标准科目表与各项目试算表里都不存在（取数恒空），
  「其他非流动资产」没有对应的标准科目 ⇒ 全局公式置空，需要的项目在本项目公式里按客户科目配置。

经公式同步内核发布（``publish_global``，来源 ``seed``）：全局行版本 +1；跟随全局的项目随之更新、本项目改过的行
进待确认（不覆盖）。发布后对有效定义变化的项目按审计年度标报表过期并重算（与发布接口同一传播函数）。

用法（cwd = backend）::

    ..\\.venv\\Scripts\\python.exe scripts/fix/fix_report_bs_book_value_formulas.py            # 预览（默认，只读）
    ..\\.venv\\Scripts\\python.exe scripts/fix/fix_report_bs_book_value_formulas.py --apply --backup <留底.json>
                                                                                          # 留底 + 发布 + 传播

幂等：每个准则固定 ``request_id``，重跑走发布记录回放；定义已是目标值的公式位不再发布。
注意：脚本在独立进程里发布，正在运行的后端进程内「谁引用了该单元格」反向索引缓存要等下一次公式发布或重启才刷新。
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

DOMAIN = "report"
STANDARDS = ("soe_consolidated", "soe_standalone", "listed_consolidated", "listed_standalone")
#: 公式位 → (各准则必须是的行名, 目标定义)。只给要改的字段，其余字段沿用现行全局（补丁语义）
TARGETS: dict[str, tuple[str, dict]] = {
    "balance_sheet:BS-028": ("固定资产", {
        "formula": "TB('1601','期末余额') - TB('1602','期末余额') - TB('1603','期末余额') + TB('1606','期末余额')",
        "formula_description": "固定资产 − 累计折旧 − 固定资产减值准备 + 固定资产清理",
    }),
    "balance_sheet:BS-032": ("无形资产", {
        "formula": "TB('1701','期末余额') - TB('1702','期末余额') - TB('1703','期末余额')",
        "formula_description": "无形资产 − 累计摊销 − 无形资产减值准备",
    }),
    "balance_sheet:BS-037": ("其他非流动资产", {
        "formula": None,
        "formula_description": "没有对应的标准科目，需要的项目在本项目公式里按客户科目配置",
    }),
}
NOTE = "BS-028 / BS-032 补减减值准备、BS-028 并入固定资产清理、BS-037 置空（spec formula-fetch-followup-defect-closure R6.4）"


def request_id(standard: str) -> str:
    return f"formula-fetch-followup-R6.4-{standard}"


async def _current_rows(db, standard: str) -> dict[str, object]:
    from app.services.formula_settings.stores import get_store

    return await get_store(DOMAIN).list_global_exact(db, standard)


def build_changes(standard: str, current: dict) -> list[dict]:
    """按现行全局行生成发布变更；行缺失或行名不符即中止（行次编码漂移时不改错行）。"""
    changes = []
    for slot, (row_name, definition) in TARGETS.items():
        rec = current.get(slot)
        if rec is None:
            raise SystemExit(f"[{standard}] 找不到 {slot}，中止")
        name = (rec.structure or {}).get("row_name")
        if (name or "").strip() != row_name:
            raise SystemExit(f"[{standard}] {slot} 的行名是 {name!r}，不是 {row_name!r}，中止（行次编码可能漂移）")
        changes.append({"slot_key": slot, "label": rec.label, "definition": dict(definition),
                        "expected_version": rec.version})
    return changes


def _print_preview(standard: str, preview: dict) -> None:
    print(f"\n=== {standard} ===")
    for c in preview["changes"]:
        old = (c.get("old") or {}).get("formula")
        new = (c.get("new") or {}).get("formula")
        print(f"  {c['slot_key']}  v{c['old_version']} → v{c['new_version']}\n    旧：{old}\n    新：{new}")
    if not preview["changes"]:
        print("  已是目标定义，无需发布")
    if preview["version_problems"]:
        print("  版本问题：", preview["version_problems"])
    summary = preview.get("summary") or {}
    print("  项目影响：", summary.get("counts"), "待确认", summary.get("pending_total"))
    for it in preview.get("items") or []:
        print(f"    - {it.get('project_name') or it.get('project_id')}  {it.get('slot_key')}  {it.get('category')}")


async def _propagate(events: list[dict]) -> None:
    """与发布接口同一传播函数：按项目审计年度标报表过期并重算。"""
    import uuid

    from app.services.formula_settings.propagation import propagate_report
    from app.services.project_audit_year import fetch_project_audit_year_standalone

    for ev in events:
        pid = uuid.UUID(str(ev["project_id"]))
        # 与事件总线派发口补年度同一函数（event_bus._backfill_year）
        year = await fetch_project_audit_year_standalone(pid)
        result = await propagate_report(pid, year, list(ev["slot_keys"]))
        recalculated = result.get("recalculated") or {}
        print(f"  {pid} {year}: 标过期 {result.get('marked')} 行，重算 {recalculated.get('recalculated_count')} 行，"
              f"失败 {recalculated.get('failed_count')} 行"
              + (f"，出错：{result['error']}" if result.get("error") else "")
              + (f"，跳过：{result['skipped']}" if result.get("skipped") else ""))


async def backup(path: Path) -> None:
    """发布前留底（PG ``row_to_json`` 原文）：三个公式位在全部准则 / 项目层的 report_config 行 +
    四个准则下全部未删项目的资产负债表 financial_report 行（重算会改写其中受影响的行）。"""
    import json

    import sqlalchemy as sa

    from app.core.database import async_session

    codes = sorted(slot.partition(":")[2] for slot in TARGETS)
    async with async_session() as db:
        config = (await db.execute(sa.text(
            "SELECT row_to_json(r)::text FROM report_config r WHERE r.report_type = 'balance_sheet' "
            "AND r.row_code = ANY(:codes) ORDER BY r.applicable_standard, r.row_code"), {"codes": codes})).scalars().all()
        reports = (await db.execute(sa.text(
            "SELECT row_to_json(f)::text FROM financial_report f JOIN projects p ON p.id = f.project_id "
            "WHERE p.is_deleted = false AND f.report_type = 'balance_sheet' ORDER BY f.project_id, f.year, f.row_code"
        ))).scalars().all()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"report_config": [json.loads(t) for t in config],
                                "financial_report": [json.loads(t) for t in reports]},
                               ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"已留底 {path}：report_config {len(config)} 行，financial_report {len(reports)} 行")


async def main(apply: bool, backup_path: Path | None = None) -> int:
    from app.core.database import async_session, engine
    from app.services.formula_settings.publish import preview_global, publish_global

    if apply and backup_path is None:
        raise SystemExit("--apply 必须同时给 --backup <文件>（发布会重算各项目报表，先留底）")
    try:
        # 第一步：四个准则全部校验、预览（只读）；任一准则行名不符 / 版本冲突，一个都不发布
        plans: list[tuple[str, list[dict], bool]] = []
        for standard in STANDARDS:
            async with async_session() as db:
                changes = build_changes(standard, await _current_rows(db, standard))
                preview = await preview_global(db, domain=DOMAIN, scope=standard, changes=changes)
                await db.rollback()
            _print_preview(standard, preview)
            if preview["version_problems"]:
                return 2
            plans.append((standard, changes, bool(preview["changes"])))
        if not apply:
            print("\n（预览，未写库；加 --apply --backup <文件> 发布）")
            return 0
        if not any(needed for _s, _c, needed in plans):
            print("\n四个准则都已是目标定义，无需发布")
            return 0
        # 第二步：留底 → 逐准则发布（各自一个事务；固定 request_id，中途失败重跑即补齐）→ 传播
        await backup(backup_path)
        events: list[dict] = []
        for standard, changes, needed in plans:
            if not needed:
                continue
            async with async_session() as db:
                result = await publish_global(db, domain=DOMAIN, scope=standard, changes=changes, user_id=None,
                                              request_id=request_id(standard), source="seed", note=NOTE)
                await db.commit()
            events.extend(result.get("events") or [])
            print(f"  [{standard}] 已发布 publish_id={result['publish_id']} 回放={result['idempotent']} "
                  f"版本={result['versions']} 有效定义变化的项目 {len(result.get('events') or [])} 个")
        if events:
            print("\n传播：")
            await _propagate(events)
        return 0
    finally:
        await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="发布并传播（默认只预览）")
    parser.add_argument("--backup", type=Path, help="--apply 时必填：发布前留底文件（JSON）")
    args = parser.parse_args()
    sys.exit(asyncio.run(main(args.apply, args.backup)))
