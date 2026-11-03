"""四套报表模板合计行与取错科目的明细行全局修正（全局发布，幂等）。

spec: .kiro/specs/citar-pages-data-wiring（报表模板部分）。目标定义的唯一来源：app/services/report_total_formulas.py

- 合计行：原公式是按行名套 CAS 模板的公式，行号却是 CAS 模板自己的（国企「资产总计 = 应收款项融资 + 应收资金集中管理款」），
  兜底的 SUM_ROW 区间求和又会把「其中：」子项一起加；改成逐行相加 / 相减。
- 明细行：其他非流动负债原取 2901（与递延所得税负债同码）、利息收入 / 利息费用原取整个财务费用、每股收益取 6901 等置空；
  其他应收款 / 其他应付款并入应收（付）利息与股利；存货不再用区间求和（把两个贷方备抵当正数加）。

经公式同步内核发布（``publish_global``，来源 ``seed``）：全局行版本 +1；跟随全局的项目随之更新、本项目改过的行进待确认
（不覆盖）。发布后对有效定义变化的项目按审计年度标报表过期并重算（与发布接口同一传播函数）。

用法（cwd = backend）::

    ..\\.venv\\Scripts\\python.exe scripts/fix/fix_report_total_formulas.py            # 预览（默认，只读）
    ..\\.venv\\Scripts\\python.exe scripts/fix/fix_report_total_formulas.py --apply --backup <留底.json>

幂等：每个准则固定 ``request_id``，重跑走发布记录回放；定义已是目标值的公式位不再发布。
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

from app.services.report_total_formulas import FIXES, STANDARD_FAMILY  # noqa: E402

DOMAIN = "report"
STANDARDS = tuple(STANDARD_FAMILY)
NOTE = "报表合计行改逐行相加、取错科目的明细行修正（spec citar-pages-data-wiring）"


def request_id(standard: str) -> str:
    """按目标定义的内容取哈希：同一组改动重跑走发布记录回放；目标定义变了（如 2026-11-02 第二轮补权益类）换新编号，
    不会被上一轮的发布记录回放吞掉。"""
    import hashlib
    import json

    digest = hashlib.sha256(json.dumps(targets(standard), sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    # formula_publish.request_id 是 VARCHAR(64)：最长准则名 listed_consolidated 时本串 45 字符
    return f"citar-totals-{standard}-{digest[:12]}"


def targets(standard: str) -> dict[str, tuple[str, dict]]:
    return {
        slot: (prefix, {"formula": formula, "formula_description": desc,
                        "formula_source": "total_fix" if formula else None})
        for slot, (prefix, formula, desc) in FIXES[STANDARD_FAMILY[standard]].items()
    }


async def _current_rows(db, standard: str) -> dict[str, object]:
    from app.services.formula_settings.stores import get_store

    return await get_store(DOMAIN).list_global_exact(db, standard)


def build_changes(standard: str, current: dict) -> list[dict]:
    """按现行全局行生成发布变更；行缺失或行名前缀不符即中止（行次编码漂移时不改错行）。"""
    changes = []
    for slot, (prefix, definition) in targets(standard).items():
        rec = current.get(slot)
        if rec is None:
            raise SystemExit(f"[{standard}] 找不到 {slot}，中止")
        name = ((rec.structure or {}).get("row_name") or "").strip()
        if not name.startswith(prefix):
            raise SystemExit(f"[{standard}] {slot} 的行名是 {name!r}，不以 {prefix!r} 开头，中止（行次编码可能漂移）")
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
        year = await fetch_project_audit_year_standalone(pid)
        result = await propagate_report(pid, year, list(ev["slot_keys"]))
        recalculated = result.get("recalculated") or {}
        print(f"  {pid} {year}: 标过期 {result.get('marked')} 行，重算 {recalculated.get('recalculated_count')} 行，"
              f"失败 {recalculated.get('failed_count')} 行"
              + (f"，出错：{result['error']}" if result.get("error") else "")
              + (f"，跳过：{result['skipped']}" if result.get("skipped") else ""))


async def backup(path: Path) -> None:
    """发布前留底（PG ``row_to_json`` 原文）：涉及的 report_config 行（全部准则 / 项目层）+
    全部未删项目的资产负债表 / 利润表 financial_report 行（重算会改写其中受影响的行）。"""
    import json

    import sqlalchemy as sa

    from app.core.database import async_session

    pairs = sorted({tuple(slot.split(":", 1)) for fam in FIXES.values() for slot in fam})
    async with async_session() as db:
        config = []
        for report_type, row_code in pairs:
            config += (await db.execute(sa.text(
                # 全部准则行 + 项目层行（applicable_standard = 'project:<id>'）
                "SELECT row_to_json(r)::text FROM report_config r WHERE r.report_type::text = :rt AND r.row_code = :rc "
                "ORDER BY r.applicable_standard"), {"rt": report_type, "rc": row_code})
            ).scalars().all()
        reports = (await db.execute(sa.text(
            "SELECT row_to_json(f)::text FROM financial_report f JOIN projects p ON p.id = f.project_id "
            "WHERE p.is_deleted = false AND f.report_type IN ('balance_sheet', 'income_statement') "
            "ORDER BY f.project_id, f.year, f.report_type, f.row_code"))).scalars().all()
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
