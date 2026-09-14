#!/usr/bin/env python
"""verify_l0_book_amounts_live.py — L0-1 矩阵账面金额真实库直跑（只读）.

spec: l0-confirmation-source-alignment · Task 8 / Requirements 3.3 / 3.4 / 8.1

逐「项目 × 年度 × 品种」打印语义定位结果，用于验证：

- ``resolved_from`` —— 走的是 ``account_chart_client`` / ``account_chart_standard``
  / ``report_config`` / ``fallback`` 哪一层（按科目名在**本项目**科目表定位是正确性前提）
- ``codes`` —— 解析出的**客户原始码**（不是硬编码标准码）
- ``amount`` —— ``None`` = 本项目无此科目（**≠ 0**，两态必须可区分）
- ``parent_check`` —— 「叶子和 == 父额」勾稽差额（应为 0.0；非 0 即符号约定或父子双算）
- ``conflicts`` —— ``report_config`` 与项目科目表不一致的告警

🔴 **只读**：全程只 SELECT，不写库、不改任何数据。

用法::

    python backend/scripts/diagnose/verify_l0_book_amounts_live.py
    python backend/scripts/diagnose/verify_l0_book_amounts_live.py --limit 3
    python backend/scripts/diagnose/verify_l0_book_amounts_live.py --project <uuid>

🔴 全程**单次 `asyncio.run`** —— 连接池绑定首个事件循环，一个脚本里两次
   `asyncio.run()` 会拿到已关闭的 transport 并抛
   ``AttributeError: 'NoneType' object has no attribute 'send'``。
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

import sqlalchemy as sa  # noqa: E402

from app.core.database import async_session  # noqa: E402
from app.services.four_table.l0_book_amounts import (  # noqa: E402
    L0_MATRIX_CATEGORY_SPECS,
    ResolverContext,
    resolve_l0_book_amounts,
)


def _fmt(v) -> str:
    if v is None:
        return "None（本项目无此科目）"
    return f"{v:,.2f}"


async def _run(limit: int | None, only_project: str | None) -> int:
    async with async_session() as db:
        # 有 tb_balance 数据的「项目 × 年度」组合（只读）
        #
        # 🔴 不能写 `WHERE (:pid IS NULL OR ...)` —— asyncpg 对裸参数无类型信息，
        #    会抛 `AmbiguousParameterError: could not determine data type of parameter $1`
        #    （同族：`sa.table()` 的裸 `sa.column()` 让 UUID 比较报
        #     `operator does not exist: uuid = character varying`）。
        #    正解 = Python 侧分支构造 SQL，参数一律显式 CAST。
        if only_project:
            q = sa.text(
                """
                SELECT DISTINCT tb.project_id, tb.year
                FROM tb_balance tb
                WHERE tb.project_id = CAST(:pid AS uuid)
                ORDER BY tb.project_id, tb.year
                """
            )
            rows = (await db.execute(q, {"pid": only_project})).fetchall()
        else:
            q = sa.text(
                """
                SELECT DISTINCT tb.project_id, tb.year
                FROM tb_balance tb
                ORDER BY tb.project_id, tb.year
                """
            )
            rows = (await db.execute(q)).fetchall()
        if not rows:
            print("没有 tb_balance 数据（或指定项目无数据），无法实证。")
            return 1

        pairs = [(r[0], r[1]) for r in rows]
        if limit:
            pairs = pairs[:limit]

        print(f"品种规格：{[c.category for c in L0_MATRIX_CATEGORY_SPECS]}")
        print(f"待验「项目 × 年度」组合：{len(pairs)}（总 {len(rows)}）\n")

        stat = {"found": 0, "absent": 0, "diff_nonzero": 0, "conflicts": 0}
        resolved_from_hist: dict[str, int] = {}

        for pid, year in pairs:
            print("=" * 92)
            print(f"project={pid}  year={year}")
            result = await resolve_l0_book_amounts(
                ResolverContext(db=db, project_id=pid, year=year)
            )
            for cat in [c.category for c in L0_MATRIX_CATEGORY_SPECS]:
                amt = result.amounts.get(cat)
                src = result.source_codes.get(cat) or {}
                rf = str(src.get("resolved_from") or "none")
                resolved_from_hist[rf] = resolved_from_hist.get(rf, 0) + 1
                if src.get("found"):
                    stat["found"] += 1
                else:
                    stat["absent"] += 1
                pc = src.get("parent_check") or {}
                bad = {k: v for k, v in pc.items() if abs(float(v or 0)) > 0.005}
                if bad:
                    stat["diff_nonzero"] += 1
                print(f"  [{cat}]")
                print(f"      amount        = {_fmt(amt)}")
                print(f"      row_code      = {src.get('row_code')}")
                print(f"      resolved_from = {rf}")
                print(f"      codes         = {src.get('gross')}")
                print(f"      std_codes     = {src.get('gross_standard')}")
                print(f"      net_of        = {src.get('net_of')}  "
                      f"skipped={src.get('net_of_skipped') or []}")
                print(f"      parent_check  = {pc}"
                      + ("   <-- 勾稽不成立！" if bad else ""))
                if src.get("absent_reason"):
                    print(f"      absent_reason = {src.get('absent_reason')}")
            if result.conflicts:
                stat["conflicts"] += 1
                print(f"  conflicts: {result.conflicts}")
            print()

        print("=" * 92)
        print("汇总")
        print(f"  品种命中(found=True)   : {stat['found']}")
        print(f"  品种缺失(本项目无科目) : {stat['absent']}")
        print(f"  parent_check 非 0      : {stat['diff_nonzero']}  （应为 0）")
        print(f"  含 conflicts 的组合    : {stat['conflicts']}")
        print(f"  resolved_from 分布     : {resolved_from_hist}")
        print("\n判读要点：")
        print("  - amount=None 与 amount=0.00 是两回事，前者是「本项目无此科目」")
        print("  - resolved_from 出现 account_chart_client 说明按科目名在客户科目表定位成功")
        print("  - parent_check 全 0 才说明叶子聚合与父额勾稽成立")
        return 0 if stat["diff_nonzero"] == 0 else 2


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=None, help="只验前 N 个组合")
    ap.add_argument("--project", type=str, default=None, help="只验指定 project_id")
    ap.add_argument(
        "--out", type=str, default=None,
        help="报告写入该文件（UTF-8）。🔴 PowerShell 的 `>` 重定向会把中文腌成乱码，"
             "要机器/人眼读全文一律用本参数由脚本自己写盘。",
    )
    args = ap.parse_args()

    if not args.out:
        return asyncio.run(_run(args.limit, args.project))

    import io
    import contextlib

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = asyncio.run(_run(args.limit, args.project))
    Path(args.out).write_text(buf.getvalue(), encoding="utf-8")
    tail = buf.getvalue().splitlines()[-8:]
    print(f"[OK] 报告已写入 {args.out}（{len(buf.getvalue())} 字节）")
    for line in tail:
        print("   ", line.encode(sys.stdout.encoding or "utf-8", "replace")
              .decode(sys.stdout.encoding or "utf-8", "replace"))
    return rc


if __name__ == "__main__":
    sys.exit(main())
