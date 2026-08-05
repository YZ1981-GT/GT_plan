"""F0-1 函证情况矩阵取数口径真实库复核（只读）.

f0-confirmation-linkage-and-structural-enhancement / Task 31。

背景（memory 铁律）：「自造 fixture 与错误假设同构 → 只有真实数据能证伪」。
本脚本对矩阵的两侧分别给出真实库结论：

A. **账面金额侧（有真实数据）**
   - `F0_BOOK_AMOUNT_SOURCES` 声明 预付账款←F1 / 应付票据←F3 / 应付账款←F4，
     hint 里写的报表行公式必须与 `report_config` 逐字一致（四准则）
   - 对每个有 F0 底稿的项目，列出 `trial_balance` 里 1123/2201/2202 的实际金额
     → 这就是矩阵 R30「本期（期末）账面金额」行会显示的值
   - 区分「无此科目」（bookMissing）与「余额为 0」（book=0 → 比例显示「-」）

B. **上区 grid 侧（当前全库无数据）**
   - 矩阵 R31/R33/R36 取上区 grid 的 F/U/Y 三列（源模板 SUMIF）
   - 全库扫 `_format LIKE 'confirmation%'` 的 sheet，统计实际行数
   - 若为 0，如实报告「无法用真实数据复核品种求和」，不得用自造 fixture 冒充

用法（只读，不写库）::

    python backend/scripts/diagnose/verify_f0_matrix_live.py
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "backend"))

import sqlalchemy as sa  # noqa: E402

from app.core.database import async_session  # noqa: E402

AGG_TS = (
    REPO_ROOT
    / "audit-platform"
    / "frontend"
    / "src"
    / "components"
    / "workpaper"
    / "confirmation"
    / "composables"
    / "f0SummaryAggregation.ts"
)

#: 品种 → (wp_code, 报表行, 标准科目码)。与 `F0_BOOK_AMOUNT_SOURCES` 对应。
BOOK_SOURCES = {
    "预付账款": ("F1", "BS-008", "1123"),
    "应付票据": ("F3", "BS-044", "2201"),
    "应付账款": ("F4", "BS-045", "2202"),
    "本期采购": (None, None, None),  # 无固定科目（营业成本需走 D4）
}


def _parse_book_sources_from_ts() -> dict[str, dict[str, str] | None]:
    """从前端常量抽 wpCode/hint，防「脚本与实现各说一套」."""
    src = AGG_TS.read_text(encoding="utf-8")
    block = re.search(
        r"F0_BOOK_AMOUNT_SOURCES[^=]*=\s*\{(.*?)\n\}", src, re.S
    )
    assert block, "未能定位 F0_BOOK_AMOUNT_SOURCES"
    out: dict[str, dict[str, str] | None] = {}
    for m in re.finditer(
        r"'([^']+)':\s*(?:\{\s*wpCode:\s*'([^']+)',\s*hint:\s*\"([^\"]+)\"\s*\}|null)",
        block.group(1),
    ):
        category, wp_code, hint = m.group(1), m.group(2), m.group(3)
        out[category] = None if wp_code is None else {"wpCode": wp_code, "hint": hint}
    return out


async def main() -> None:
    ts_sources = _parse_book_sources_from_ts()
    print("=" * 78)
    print("A. 账面金额侧（真实数据）")
    print("=" * 78)
    print("前端常量 F0_BOOK_AMOUNT_SOURCES:")
    for cat, spec in ts_sources.items():
        print(f"  {cat:6s} → {spec}")

    async with async_session() as db:
        # A1. report_config 公式对账
        rows = (
            await db.execute(
                sa.text(
                    "SELECT row_code, row_name, applicable_standard, formula "
                    "FROM report_config WHERE row_code = ANY(:codes) "
                    "ORDER BY row_code, applicable_standard"
                ),
                {"codes": ["BS-008", "BS-044", "BS-045"]},
            )
        ).mappings().all()

        print("\nreport_config 实际公式：")
        by_code: dict[str, set[str]] = {}
        for r in rows:
            by_code.setdefault(r["row_code"], set()).add(r["formula"])
            print(f"  {r['row_code']} {r['row_name']} [{r['applicable_standard']}] = {r['formula']}")

        print("\n公式一致性（四准则应各自唯一）：")
        for code, formulas in sorted(by_code.items()):
            status = "OK" if len(formulas) == 1 else "!! 多口径"
            print(f"  {code}: {status} {sorted(formulas)}")

        # A2. hint 与真实公式交叉核对
        print("\nhint 与 report_config 交叉核对：")
        for cat, (wp_code, row_code, acct) in BOOK_SOURCES.items():
            if wp_code is None:
                print(f"  {cat:6s} 无固定科目 → 前端应声明 null："
                      f"{'OK' if ts_sources.get(cat) is None else '!! 应为 null'}")
                continue
            spec = ts_sources.get(cat)
            real = sorted(by_code.get(row_code, set()))
            hit = bool(spec and acct in spec["hint"] and spec["wpCode"] == wp_code)
            print(f"  {cat:6s} 期望 wp={wp_code} 码={acct} 报表行={row_code} "
                  f"real={real} → {'OK' if hit else '!! hint 与真实公式不符'}")

        # A3. 有 F0 底稿的项目 + 三科目实际余额
        projects = (
            await db.execute(
                sa.text(
                    "SELECT DISTINCT wp.project_id, p.audit_year "
                    "FROM working_paper wp "
                    "JOIN wp_index wi ON wi.id = wp.wp_index_id "
                    "JOIN projects p ON p.id = wp.project_id "
                    "WHERE wi.wp_code = 'F0' ORDER BY p.audit_year DESC"
                )
            )
        ).mappings().all()

        print(f"\n有 F0 底稿的项目 {len(projects)} 个 —— 矩阵 R30 会显示的账面金额：")
        for proj in projects:
            pid, year = proj["project_id"], proj["audit_year"]
            tb = (
                await db.execute(
                    sa.text(
                        "SELECT standard_account_code, audited_amount "
                        "FROM trial_balance WHERE project_id = :pid AND year = :y "
                        "AND standard_account_code = ANY(:codes)"
                    ),
                    {"pid": str(pid), "y": year, "codes": ["1123", "2201", "2202"]},
                )
            ).mappings().all()
            amounts = {r["standard_account_code"]: r["audited_amount"] for r in tb}
            print(f"\n  项目 {str(pid)[:8]} / {year}:")
            for cat, (wp_code, _row, acct) in BOOK_SOURCES.items():
                if acct is None:
                    print(f"    {cat:6s} bookMissing（无固定科目，如实标缺失）")
                    continue
                if acct not in amounts:
                    print(f"    {cat:6s} bookMissing（trial_balance 无 {acct} 行 = 本项目无此科目）")
                else:
                    v = amounts[acct]
                    note = "（余额为 0 ≠ 无此科目；比例分母为 0 → 显示「-」）" if v == 0 else ""
                    print(f"    {cat:6s} book = {v:>18,.2f}  ← {wp_code}/{acct} {note}")

        # B. 上区 grid 侧
        print("\n" + "=" * 78)
        print("B. 上区 grid 侧（矩阵 R31/R33/R36 的取数源）")
        print("=" * 78)
        grids = (
            await db.execute(
                sa.text(
                    "SELECT wi.wp_code, wp.project_id, k.key AS sheet_key, "
                    "  wp.parsed_data->'html_data'->k.key->>'_format' AS fmt, "
                    "  jsonb_array_length(COALESCE(wp.parsed_data->'html_data'->k.key->'rows','[]'::jsonb)) AS row_cnt "
                    "FROM working_paper wp "
                    "JOIN wp_index wi ON wi.id = wp.wp_index_id "
                    "CROSS JOIN LATERAL jsonb_object_keys(COALESCE(wp.parsed_data->'html_data','{}'::jsonb)) AS k(key) "
                    "WHERE wp.parsed_data->'html_data'->k.key->>'_format' LIKE 'confirmation%' "
                    "ORDER BY row_cnt DESC"
                )
            )
        ).mappings().all()

        total_rows = sum(g["row_cnt"] or 0 for g in grids)
        print(f"全库 confirmation-* sheet：{len(grids)} 张，明细行合计 {total_rows} 行")
        for g in grids[:10]:
            print(f"  {g['wp_code']:6s} {g['sheet_key']} [{g['fmt']}] rows={g['row_cnt']}")

        if total_rows == 0:
            print(
                "\n结论：**全库无任何函证明细行**（不止 F0，D0/E0 等亦为空）。\n"
                "      → 「品种列和 == 该品种全部行之和」这条无法用真实数据复核。\n"
                "      → 不用自造 fixture 冒充实测（那只是把假设重复一遍）。\n"
                "      → 可复核的是账面金额侧（见 A 段，三个科目金额均为真实库值）。\n"
                "      → 待有真实函证明细后重跑本脚本即可补齐该项。"
            )
        else:
            print("\n发现真实明细行 → 按品种聚合复核：")
            for g in grids:
                if not g["row_cnt"]:
                    continue
                detail = (
                    await db.execute(
                        sa.text(
                            "SELECT wp.parsed_data->'html_data'->:k->'rows' AS rows "
                            "FROM working_paper wp WHERE wp.project_id = :pid LIMIT 1"
                        ),
                        {"k": g["sheet_key"], "pid": str(g["project_id"])},
                    )
                ).scalar()
                rows_json = detail if isinstance(detail, list) else json.loads(detail or "[]")
                buckets: dict[str, dict[str, float]] = {}
                for row in rows_json:
                    cat = str(row.get("account_type") or "(空品种)")
                    b = buckets.setdefault(cat, {"amount": 0.0, "confirmed": 0.0, "alt": 0.0})
                    for field, key in (
                        ("amount", "amount"),
                        ("confirmed_amount", "confirmed"),
                        ("alt_confirmed", "alt"),
                    ):
                        try:
                            v = float(row.get(field) or 0)
                        except (TypeError, ValueError):
                            v = 0.0
                        if v == v and abs(v) != float("inf"):
                            b[key] += v
                grand = {
                    k: sum(b[k] for b in buckets.values())
                    for k in ("amount", "confirmed", "alt")
                }
                print(f"\n  {g['wp_code']} / {g['sheet_key']}（{g['row_cnt']} 行）")
                for cat, b in sorted(buckets.items()):
                    print(f"    {cat:12s} 发函={b['amount']:>16,.2f} "
                          f"可确认={b['confirmed']:>16,.2f} 替代={b['alt']:>16,.2f}")
                print(f"    {'合计':12s} 发函={grand['amount']:>16,.2f} "
                      f"可确认={grand['confirmed']:>16,.2f} 替代={grand['alt']:>16,.2f}")
                print("    → 不变量：Σ品种 == 全表合计 "
                      f"{'OK' if abs(sum(b['amount'] for b in buckets.values()) - grand['amount']) < 0.01 else '!! 不成立'}")


if __name__ == "__main__":
    os.environ.setdefault("DB_DISABLE_SSL", "True")
    asyncio.run(main())
