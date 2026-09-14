"""I 类六循环真实库验收（**只读**，无 `--apply`，不写库、不经 HTTP）。

spec: i-cycle-extraction-formula-and-disclosure-closure Task 23 / Requirement 11.6

对**全部**含 I 循环数据的项目 × I1~I6 直跑 `load_i_cycle_extraction`，六态输出：

    resolved_from / 码集 / parent_check.diff / tb_values 非零键数 / prefill 段数 / unmapped 数

## 🔴 判据偏离 tasks.md 原文（连库实证后改判，2026-08-14）

原文：``resolved_from 全为 report_config（I5 除外，其 found=False）``。**实测不成立**，
且不成立的原因是**正常业务形态**而非缺陷：

* `BS-032 无形资产 = TB('1701','期末余额') - TB('1702','期末余额')` —— 公式**本就不含
  `1703`（无形资产减值准备）**。故 I1 的 `impairment` 段永远认领不到、必然 `fallback`
  （靠段自己声明的兜底码 `1703`）。同理 I3 的 `impairment`（`BS-034` 只有 `1711`）。
* `1704`（开发支出）只在 **3/32** 个项目的 standard 科目表里存在 → I2 的 `cost` 段在其余
  项目上必然 `fallback`。这是**数据依赖**（该项目没建这个科目），不是取数逻辑错。
* `1911`（其他非流动资产）全库 `account_chart` 两个 source 都**零命中** → I5 `standard=[]`，
  与 `I_CYCLE_ROW_CODES` 的「宁缺勿造」设计一致。

⇒ 若照原文判「全为 report_config」，会把上述正常形态判成失败（**守卫把错值当基线**的镜像
错误：把对值当错值）。

## 🔴 D4 判据的两次修正（第一版也是错的，留证防重犯）

**第一版 D4**（错）：``set(seg.standard) ∩ formula_codes ≠ ∅ ⇒ 必须 report_config``。
实跑打红 6 条，全是 I2 的 `cost` 段。但代码是对的 —— 错在判据：
`resolve_i_cycle_accounts` 在认领失败时会把 ``std`` **覆盖为 ``spec.fallback``**::

    std = list(claimed.get(spec.segment) or ())
    seg_from = REPORT if std else FALLBACK
    if not std:
        std = list(spec.fallback)      # ← 覆盖

而 I2 的兜底码**恰好也是 `1704`**（与公式码相同）。故「`seg.standard` 与公式有交集」
推不出「被公式认领」—— 巧合被当成了因果。

**连库实证的因果链**（8 个含 I 数据的项目）::

    claim_segments: name = name_lookup.get(code); if not name: unclaimed（不按码序猜段）
    name_lookup  ← fetch_standard_chart_rows(ctx)  ← account_chart 的 **standard 源**

    account_chart source='standard' 且 code='1704' 的项目：仅 2/8
      · 重药控股安徽有限公司_2025（template_type=listed）→ I2 cost = report_config ✓
      · 陕西华氏医药有限公司_2025                        → I2 cost = report_config ✓
      · 其余 6 个                                        → 认领失败 → fallback（正确）

    其中「宜宾医药新健康大药房临港店_2025」`client` 源**有** 1704 但 `standard` 源没有
    ⇒ 反证 I 循环认领只看 standard 源，客户自建科目不参与（见 D7 软判据）。

**第二版 D4**（现行）：脚本**独立重算**一遍认领结果再比对最终产物::

    claimed, _ = claim_segments(extract_codes_from_formula(formula), name_lookup, specs)
    对每段： should_claim = bool(claimed[seg])
      · should_claim ⇒ resolved_from == report_config 且 standard == claimed[seg]
      · 否则         ⇒ resolved_from == fallback      且 standard == list(spec.fallback)

边界说明（防自证）：重算的是**中间量**（认领结果），比对的是**最终产物**
（`resolved_from` + `standard` 码集），中间隔着 `resolve_i_cycle_accounts` 的赋值逻辑。
故本判据能抓「赋值逻辑写错」（`seg_from` 判反、`std` 被误覆盖、段错位），
**抓不到** `claim_segments` 自身错 —— 后者由 `test_i_cycle_accounts.py::test_i2_1703_unclaimed`
等单元守卫覆盖，分工明确。

## 判据清单

| 编号 | 判据 | 强度 |
|---|---|---|
| D1 | `row_code` == `I_CYCLE_ROW_CODES[wp]` | 硬 |
| D2 | `diagnostics` 无 `row_name_mismatch`（行名校验闸未触发 = 没取错行） | 硬 |
| D3 | `parent_check` 全部 \|diff\| <= 0.01（叶子和 == 父科目额） | 硬 |
| D4 | 段级 `resolved_from` + `standard` 与**独立重算的**认领结果双向自洽（见上） | 硬 |
| D5 | I5 `cost` 段 `standard == []`（宁缺勿造，不得凭空造码） | 硬 |
| D6 | `unmapped` / 诊断如实列出 | 软（只报告） |
| D7 | 认领失败但 `client` 源科目表有该码 → 提示可做科目映射（改进机会，非缺陷） | 软（只报告） |

## 无法验收的诚实输出

DB 不可达 / 无候选项目 → 打印 ``VERDICT: 无法验收（原因）`` 且 **rc=2**。
**不得**用 fixture 或造数冒充真实库验收。

用法::

    python backend/scripts/diagnose/verify_i_cycle_live.py
    python backend/scripts/diagnose/verify_i_cycle_live.py --json out.json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import sqlalchemy as sa  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.services.four_table.i_cycle_accounts import (  # noqa: E402
    I_CYCLE_ROW_CODES,
    I_CYCLE_SEGMENTS,
    RESOLVED_FROM_FALLBACK,
    RESOLVED_FROM_REPORT,
    build_name_lookup,
    claim_segments,
)
from app.services.four_table.i_cycle_extraction import load_i_cycle_extraction  # noqa: E402
from app.services.four_table.report_line_accounts import fetch_standard_chart_rows  # noqa: E402
from app.services.report_account_mapping import extract_codes_from_formula  # noqa: E402

CYCLES = ("I1", "I2", "I3", "I4", "I5", "I6")

#: 含 I 循环数据的项目（17xx 无形/开发/商誉、18xx 长期待摊、66xx 损益）
_PROJECT_SQL = sa.text(
    "SELECT p.id, p.name, p.audit_year, p.template_type,"
    " p.applicable_standard_v2->>'entity_type' AS ent"
    " FROM projects p WHERE p.is_deleted = false"
    " AND EXISTS (SELECT 1 FROM tb_balance t"
    "   WHERE t.project_id = p.id AND t.year = p.audit_year"
    "     AND (t.account_code LIKE '17%' OR t.account_code LIKE '18%'"
    "          OR t.account_code LIKE '66%'))"
    " ORDER BY p.template_type DESC, p.name"
)


def _judge(
    wp: str,
    ex: Any,
    name_lookup: dict[str, str],
    client_codes: set[str],
) -> tuple[list[str], dict[str, Any]]:
    """对单个 (项目, 循环) 施加 D1~D7，返回 (硬性失败描述, 六态快照)。

    Args:
        name_lookup: 本项目 **standard 源**科目表的 `{码: 名}`（用于独立重算认领）。
        client_codes: 本项目 **client 源**科目码集（仅供 D7 软提示）。
    """
    a = ex.accounts
    fails: list[str] = []
    notes: list[str] = []

    # ── D1 row_code ────────────────────────────────────────────────────────
    expected_row = I_CYCLE_ROW_CODES[wp]["listed"]  # listed == soe（Task 4 已收敛）
    if a.row_code != expected_row:
        fails.append(f"D1 row_code={a.row_code!r} != 期望 {expected_row!r}")

    # ── D2 行名校验闸 ──────────────────────────────────────────────────────
    mismatch = [d for d in (a.diagnostics or []) if d.get("kind") == "row_name_mismatch"]
    if mismatch:
        fails.append(f"D2 行名不符致公式被丢弃: {mismatch[0].get('row_name')!r}")

    # ── D3 parent_check ────────────────────────────────────────────────────
    bad_diff = {
        k: v.get("diff")
        for k, v in (ex.parent_check or {}).items()
        if abs(float(v.get("diff") or 0)) > 0.01
    }
    if bad_diff:
        fails.append(f"D3 叶子和≠父科目额: {bad_diff}")

    # ── D4 独立重算认领结果，再比对最终产物（resolved_from + standard 码集）──────
    formula_codes_ordered = list(extract_codes_from_formula(a.formula) or [])
    specs = I_CYCLE_SEGMENTS[wp]
    recomputed, unclaimed = claim_segments(formula_codes_ordered, name_lookup, specs)
    spec_by_seg = {sp.segment: sp for sp in specs}

    seg_view: list[dict[str, Any]] = []
    for s in a.segments:
        want_codes = list(recomputed.get(s.segment) or ())
        should_claim = bool(want_codes)
        want_from = RESOLVED_FROM_REPORT if should_claim else RESOLVED_FROM_FALLBACK
        if s.resolved_from != want_from:
            fails.append(
                f"D4 段 {s.segment}: 重算认领={want_codes or '空'} "
                f"⇒ resolved_from 应为 {want_from}，实为 {s.resolved_from}"
            )
        expect_std = want_codes if should_claim else list(spec_by_seg[s.segment].fallback)
        if list(s.standard) != expect_std:
            fails.append(
                f"D4 段 {s.segment}: standard 应为 {expect_std}（"
                f"{'公式认领' if should_claim else '声明兜底'}），实为 {list(s.standard)}"
            )
        # D7 软提示：认领失败但客户科目表里有这个兜底码 → 建议做科目映射
        if not should_claim:
            hit_client = [c for c in expect_std if c in client_codes]
            if hit_client:
                notes.append(
                    f"D7 段 {s.segment}: 标准科目表无 {hit_client}（故走兜底），"
                    f"但客户科目表有 —— 可做科目映射以恢复 report_config 溯源"
                )
        seg_view.append(
            {
                "segment": s.segment,
                "standard": list(s.standard),
                "original": list(s.original),
                "resolved_from": s.resolved_from,
                "claimed_by_formula": should_claim,
                "recomputed_claim": want_codes,
                "exact": bool(s.exact),
            }
        )
    if unclaimed:
        notes.append(f"D6 公式中未被任何段认领的码: {unclaimed}")

    # ── D5 I5 宁缺勿造 ─────────────────────────────────────────────────────
    if wp == "I5":
        cost = a.segment("cost")
        if cost is None:
            fails.append("D5 I5 缺 cost 段")
        elif list(cost.standard):
            fails.append(f"D5 I5 cost 段凭空造码 standard={list(cost.standard)}（1911 全库不存在）")

    # ── 六态快照 ───────────────────────────────────────────────────────────
    prefill = ex.adjudication_prefill or {}
    tb_values = ex.tb_values or {}
    snapshot = {
        "wp_code": wp,
        "row_code": a.row_code,
        "row_name": a.row_name,
        "formula": a.formula,
        "resolved_from_top": a.resolved_from,
        "formula_codes": formula_codes_ordered,
        "segments": seg_view,
        "parent_check_diffs": {k: v.get("diff") for k, v in (ex.parent_check or {}).items()},
        "parent_check_bad": bad_diff,
        "tb_values_nonzero": sum(1 for v in tb_values.values() if v),
        "tb_values_total": len(tb_values),
        "prefill_segments": len(prefill.get("segments") or []),
        "prefill_keys": sorted(prefill.keys()),
        "unmapped": len(prefill.get("unmapped") or []),
        "diagnostics": list(a.diagnostics or []),
        "fails": fails,
        "notes": notes,
    }
    return fails, snapshot


async def run() -> tuple[int, dict[str, Any]]:
    url = settings.DATABASE_URL
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)

    report: dict[str, Any] = {"projects": [], "verdict": "", "unable_reason": ""}
    try:
        engine = create_async_engine(url, poolclass=NullPool)
    except Exception as exc:  # noqa: BLE001
        report["verdict"] = "无法验收"
        report["unable_reason"] = f"引擎创建失败: {type(exc).__name__}: {exc}"
        return 2, report

    Session = async_sessionmaker(engine, expire_on_commit=False)
    total_fails = 0
    total_cells = 0
    exc_cells = 0
    try:
        async with Session() as db:
            try:
                rs = await db.execute(_PROJECT_SQL)
                projects = rs.fetchall()
            except Exception as exc:  # noqa: BLE001
                report["verdict"] = "无法验收"
                report["unable_reason"] = f"数据库不可达或查询失败: {type(exc).__name__}: {exc}"
                return 2, report

            if not projects:
                report["verdict"] = "无法验收"
                report["unable_reason"] = (
                    "库中没有含 I 循环数据（17xx/18xx/66xx）的项目 —— "
                    "不用 fixture 冒充真实库验收"
                )
                return 2, report

            for p in projects:
                pj: dict[str, Any] = {
                    "project_id": str(p.id),
                    "name": p.name,
                    "year": p.audit_year,
                    "template_type": p.template_type,
                    "entity_type": p.ent,
                    "cycles": [],
                }
                ctx = SimpleNamespace(db=db, project_id=str(p.id), year=p.audit_year)

                # D4 要独立重算认领 ⇒ 需与被测代码同源的 standard 科目表；
                # D7 另取 client 源码集（只作软提示，不参与硬判据）。
                try:
                    chart_rows = await fetch_standard_chart_rows(ctx)
                    name_lookup = build_name_lookup(chart_rows)
                except Exception as exc:  # noqa: BLE001
                    name_lookup = {}
                    pj["chart_error"] = f"{type(exc).__name__}: {exc}"
                rs2 = await db.execute(
                    sa.text(
                        "SELECT DISTINCT account_code FROM account_chart"
                        " WHERE project_id = :pid AND is_deleted = false AND source = 'client'"
                    ),
                    {"pid": str(p.id)},
                )
                client_codes = {str(r[0]).strip() for r in rs2.fetchall()}
                pj["standard_chart_codes"] = len(name_lookup)
                pj["client_chart_codes"] = len(client_codes)

                for wp in CYCLES:
                    total_cells += 1
                    try:
                        ex = await load_i_cycle_extraction(ctx, wp)
                    except Exception as exc:  # noqa: BLE001
                        exc_cells += 1
                        total_fails += 1
                        pj["cycles"].append(
                            {"wp_code": wp, "fails": [f"EXC {type(exc).__name__}: {exc}"]}
                        )
                        continue
                    fails, snap = _judge(wp, ex, name_lookup, client_codes)
                    total_fails += len(fails)
                    pj["cycles"].append(snap)
                report["projects"].append(pj)
    finally:
        await engine.dispose()

    report["summary"] = {
        "projects": len(report["projects"]),
        "cells": total_cells,
        "exception_cells": exc_cells,
        "hard_fails": total_fails,
    }
    report["verdict"] = "通过" if total_fails == 0 else "未通过"
    return (0 if total_fails == 0 else 1), report


def _print(report: dict[str, Any]) -> None:
    if report.get("verdict") == "无法验收":
        print("=" * 78)
        print("VERDICT: 无法验收")
        print(f"原因: {report.get('unable_reason')}")
        print("=" * 78)
        return

    for pj in report["projects"]:
        print("=" * 78)
        print(
            f"项目 {pj['name']} | {pj['year']} | tmpl={pj['template_type']} "
            f"| ent={pj['entity_type']}"
        )
        print(
            f"       {pj['project_id']}  标准科目 {pj.get('standard_chart_codes', '?')} 个"
            f" / 客户科目 {pj.get('client_chart_codes', '?')} 个"
        )
        print("=" * 78)
        for c in pj["cycles"]:
            wp = c.get("wp_code")
            if "row_code" not in c:
                print(f"  [{wp}] {c['fails'][0]}")
                continue
            segs = " ".join(
                f"{s['segment']}[std={s['standard']},from={s['resolved_from']}"
                f",{'认领' if s['claimed_by_formula'] else '兜底'}]"
                for s in c["segments"]
            )
            print(f"  [{wp}] row_code={c['row_code']}({c['row_name']}) top={c['resolved_from_top']}")
            print(f"        段: {segs}")
            print(
                f"        tb_values 非零 {c['tb_values_nonzero']}/{c['tb_values_total']}"
                f" | prefill 段数 {c['prefill_segments']}"
                f" | unmapped {c['unmapped']}"
                f" | parent_check {len(c['parent_check_diffs'])} 项，超差 {len(c['parent_check_bad'])}"
            )
            for d in c["diagnostics"]:
                print(f"        诊断: {d.get('kind')} {d.get('code', '')} {d.get('chart_name', '')}")
            for n in c.get("notes") or []:
                print(f"        提示 {n}")
            for f in c["fails"]:
                print(f"        🔴 {f}")
        print()

    s = report["summary"]
    print("=" * 78)
    print(
        f"VERDICT: {report['verdict']}   项目 {s['projects']} 个 × 6 循环 = {s['cells']} 格"
        f"，异常 {s['exception_cells']} 格，硬性判据失败 {s['hard_fails']} 条"
    )
    print("=" * 78)


def main() -> int:
    ap = argparse.ArgumentParser(description="I 循环真实库验收（只读）")
    ap.add_argument("--json", help="附加输出 JSON 报告路径")
    args = ap.parse_args()

    rc, report = asyncio.run(run())
    _print(report)
    if args.json:
        Path(args.json).write_text(
            json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
        )
        print(f"[JSON] {args.json}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
