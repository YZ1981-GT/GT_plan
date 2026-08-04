#!/usr/bin/env python
"""verify_h0_book_amounts_live.py — H0-1 九品种账面金额真实库直跑（只读）.

spec: h0-confirmation-source-fidelity-and-linkage · Task 24 / Requirement 12.7

只读校验三件事：
1. 九品种逐个打印 ``amount`` / ``resolved_from`` / 解析出的码，区分
   「本项目无此科目（None）」与「余额为 0」；
2. 客户使用非标准码的项目（H8 用 ``1651/1652``、H9 用 ``2651``）必须取到数
   —— 这是「语义定位而非按标准码硬查」的硬证据；
3. ``conflicts`` 如实回报（`report_config` 与项目科目表不一致）。

用法::

    python backend/scripts/diagnose/verify_h0_book_amounts_live.py            # 全部项目
    python backend/scripts/diagnose/verify_h0_book_amounts_live.py --limit 3
    python backend/scripts/diagnose/verify_h0_book_amounts_live.py --out tmp.txt

🔴 只读：不执行任何 INSERT/UPDATE/DELETE。
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import sqlalchemy as sa  # noqa: E402

from app.core.database import async_session  # noqa: E402
from app.services.four_table.h0_book_amounts import (  # noqa: E402
    H0_MATRIX_CATEGORY_SPECS,
    resolve_h0_book_amounts,
)
from app.services.four_table.semantic_account_resolver import ResolverContext  # noqa: E402

#: 客户使用非标准码的实证样本（h-cycle spec 已记录）
NON_STANDARD_HINTS = {
    "使用权资产": ("1651", "1652"),
    "租赁负债": ("2651",),
}


def _fmt(v: float | None) -> str:
    if v is None:
        return "None（本项目无此科目）"
    return f"{v:,.2f}"


async def _run(limit: int | None, out_path: str | None) -> int:
    lines: list[str] = []

    def emit(s: str = "") -> None:
        lines.append(s)

    async with async_session() as db:
        # 取有 tb_balance 数据的项目
        rows = (
            await db.execute(
                sa.text(
                    """
                    SELECT DISTINCT tb.project_id, tb.year, p.name
                    FROM tb_balance tb
                    JOIN projects p ON p.id = tb.project_id
                    WHERE tb.is_deleted = false
                    ORDER BY tb.year DESC, tb.project_id
                    """
                )
            )
        ).all()
        if limit:
            rows = rows[:limit]

        emit(f"候选项目 {len(rows)} 个（有 tb_balance 数据）")
        emit("=" * 100)

        non_standard_hits: dict[str, list[str]] = {k: [] for k in NON_STANDARD_HINTS}
        any_amount = False

        for project_id, year, project_name in rows:
            ctx = ResolverContext(db=db, project_id=project_id, year=year)
            res = await resolve_h0_book_amounts(ctx)

            emit(f"\n项目 {str(project_id)[:8]} / {year} / {project_name}")
            emit(f"{'品种':<14}{'账面金额':>22}  {'来源':<26}{'码'}")
            emit("-" * 100)
            for spec in H0_MATRIX_CATEGORY_SPECS:
                cat = spec.category
                amt = res.amounts.get(cat)
                src = res.source_codes.get(cat) or {}
                resolved_from = str(src.get("resolved_from") or "-")
                gross = list(src.get("gross") or [])
                net_of = list(src.get("net_of") or [])
                codes = gross + net_of
                codes_s = (
                    f"{','.join(gross) or '-'}"
                    + (f" − {','.join(net_of)}" if net_of else "")
                )
                emit(f"{cat:<14}{_fmt(amt):>22}  {resolved_from:<26}{codes_s}")
                if amt is not None and amt < 0:
                    emit(f"    ⚠ 账面金额为负 → 检查备抵槽是否跨循环串味: {codes_s}")

                if amt is not None:
                    any_amount = True
                # 非标准码命中登记
                hints = NON_STANDARD_HINTS.get(cat)
                if hints and any(str(c).startswith(h) for c in codes for h in hints):
                    non_standard_hits[cat].append(
                        f"{str(project_id)[:8]}/{year} codes={codes_s} amount={_fmt(amt)}"
                    )

            if res.conflicts:
                emit("  ⚠ conflicts:")
                for c in res.conflicts:
                    emit(f"    - {c}")

        emit()
        emit("=" * 100)
        emit("非标准码命中（语义定位有效性的硬证据）：")
        for cat, hits in non_standard_hits.items():
            if hits:
                for h in hits:
                    emit(f"  ✅ {cat}: {h}")
            else:
                emit(f"  ·  {cat}: 本轮候选项目中未出现 {NON_STANDARD_HINTS[cat]}")

        emit()
        emit(f"至少一个品种取到非 None 金额: {any_amount}")

    text = "\n".join(lines)
    if out_path:
        Path(out_path).write_text(text, encoding="utf-8")
        print(f"[OK] 已写入 {out_path}（{len(lines)} 行）")
    else:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        print(text)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="H0 九品种账面金额真实库直跑（只读）")
    ap.add_argument("--limit", type=int, default=None, help="只跑前 N 个项目")
    ap.add_argument("--out", type=str, default=None, help="写入文件（避免控制台编码问题）")
    args = ap.parse_args()
    return asyncio.run(_run(args.limit, args.out))


if __name__ == "__main__":
    sys.exit(main())
