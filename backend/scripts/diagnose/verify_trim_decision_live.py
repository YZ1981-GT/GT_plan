"""Task 25 真实库验收：裁剪三维判据上下文的只读实测。

═══ 为什么本脚本**不**输出 verdict 计数 / 汇总闸结果 / 豁免判据层级分布 ═══

tasks.md Task 25 列了这三项，但它们的实现按 design.md 的架构决定**全在前端 TS**
（`procedureTrimDecision.ts` 的 9 档内核 / `trimAggregateGate.ts` / `completenessExemption.ts`；
design.md「不把决策内核搬到后端：裁剪是交互式决策」）。在 Python 里重算一遍就是**第二真源**
—— 两侧一旦分叉，无从裁决谁对，而这正是平台反复登记的最贵一类缺陷。

故本脚本只输出后端**能正当产出**的部分（判据输入 + 降级 + 项目状态分类），三项前端产物
一律标 `UNVERIFIABLE(kernel is frontend-only by design)`。要验它们只能走 Task 26 浏览器实测。

═══ 连库约定（平台踩坑铁律）═══

- **专用一次性 engine**（`poolclass=NullPool`）+ 同一 loop 内 `dispose()`：共享连接池绑定
  首个事件循环，借用会让第二个 `asyncio.run` 报 `Event loop is closed` 并双向污染。
- **一次 `asyncio.run` 取完全部快照**，不是每个项目各跑一次。
- **默认只读**：全部语句是 SELECT；无 `--apply` 之类的开关。
- **中文输出落盘不 print**：GBK 控制台会在写完前 `UnicodeEncodeError`，那时退出码非零而
  数据其实已取到（平台已登记「判成败查数据不看 exit code」）。

用法::

    python backend/scripts/diagnose/verify_trim_decision_live.py
    python backend/scripts/diagnose/verify_trim_decision_live.py --out tmp_t25_live.txt
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

os.environ.setdefault("PYTHONIOENCODING", "utf-8")

import sqlalchemy as sa  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.services.trim_decision_context import build_trim_decision_context  # noqa: E402

# 前端 TS 独占的三项产物（禁在 Python 里重算 —— 会成第二真源）
FRONTEND_ONLY = (
    ("verdict 计数", "procedureTrimDecision.ts 的 9 档内核"),
    ("汇总闸结果", "trimAggregateGate.ts"),
    ("完整性豁免命中数与判据层级分布", "completenessExemption.ts 的 COMPLETENESS_CYCLE_RULES"),
)

_PROJECTS_SQL = sa.text(
    """
    SELECT p.id                                        AS project_id,
           p.name                                      AS project_name,
           p.audit_year                                AS audit_year,
           (SELECT count(*) FROM procedure_instances pi
              WHERE pi.project_id = p.id)              AS proc_total,
           (SELECT count(*) FROM procedure_instances pi
              WHERE pi.project_id = p.id
                AND pi.status IN ('not_applicable', 'skip')) AS proc_trimmed,
           (SELECT count(*) FROM materiality m
              WHERE m.project_id = p.id)               AS mat_rows,
           (SELECT count(*) FROM checklist_responses cr
              JOIN wp_index wi ON wi.id = cr.wp_id
              WHERE wi.project_id = p.id
                AND cr.item_id LIKE 'B50-T3-%')        AS b50_rows,
           (SELECT count(*) FROM tb_balance tb
              WHERE tb.project_id = p.id)              AS tb_rows
      FROM projects p
     WHERE p.is_deleted = false
       AND EXISTS (SELECT 1 FROM procedure_instances pi WHERE pi.project_id = p.id)
     ORDER BY proc_total DESC
    """
)

STATE_MAT_NO_B50 = "有重要性无 B50"
STATE_NO_MAT_NO_B50 = "无重要性无 B50"
STATE_HAS_TB = "有试算表数据"
STATE_HAS_B50 = "有 B50"


def _classify(row: dict) -> list[str]:
    """一个项目可同时命中多个状态（状态之间不互斥，硬分桶会漏报）。"""
    states = []
    if row["b50_rows"] > 0:
        states.append(STATE_HAS_B50)
    if row["mat_rows"] > 0 and row["b50_rows"] == 0:
        states.append(STATE_MAT_NO_B50)
    if row["mat_rows"] == 0 and row["b50_rows"] == 0:
        states.append(STATE_NO_MAT_NO_B50)
    if row["tb_rows"] > 0:
        states.append(STATE_HAS_TB)
    return states


async def _snapshot() -> dict:
    engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
    try:
        async with engine.connect() as conn:
            rows = [dict(r._mapping) for r in (await conn.execute(_PROJECTS_SQL)).all()]

        by_state: dict[str, list[dict]] = {}
        for r in rows:
            for s in _classify(r):
                by_state.setdefault(s, []).append(r)

        # 每个状态取一个代表项目（proc_total 最大者）做上下文实测
        picks: dict[str, dict] = {}
        for s in (STATE_MAT_NO_B50, STATE_NO_MAT_NO_B50, STATE_HAS_TB, STATE_HAS_B50):
            if by_state.get(s):
                picks[s] = by_state[s][0]

        contexts: dict[str, dict] = {}
        async with AsyncSession(engine, expire_on_commit=False) as db:
            for state, proj in picks.items():
                year = proj["audit_year"] or 2025
                try:
                    ctx = await build_trim_decision_context(
                        db, proj["project_id"], int(year), []
                    )
                    contexts[state] = {"ok": True, "ctx": ctx}
                except Exception as e:  # noqa: BLE001
                    # 🔴 如实记 ERROR 态：fail-open 吞成 warning 会让「接线错误」表现成
                    #    「本项目无此数据」，那是平台最贵的一类假绿。
                    contexts[state] = {"ok": False, "error": "%s: %s" % (type(e).__name__, e)}
        return {"rows": rows, "by_state": by_state, "picks": picks, "contexts": contexts}
    finally:
        await engine.dispose()


def _fmt(snap: dict) -> str:
    out: list[str] = []
    rows = snap["rows"]
    out.append("Task 25 真实库验收 · 裁剪三维判据上下文（只读）")
    out.append("=" * 78)
    out.append("有 procedure_instances 的项目数: %d" % len(rows))
    out.append("已裁剪(status IN not_applicable/skip)合计: %d"
               % sum(r["proc_trimmed"] for r in rows))
    out.append("")
    out.append("--- 状态覆盖 ---")
    for s in (STATE_MAT_NO_B50, STATE_NO_MAT_NO_B50, STATE_HAS_TB, STATE_HAS_B50):
        hit = snap["by_state"].get(s) or []
        if hit:
            out.append("  %-16s 命中 %d 个项目，代表: %s"
                       % (s, len(hit), (snap["picks"][s]["project_name"] or "")[:40]))
        else:
            out.append("  %-16s UNVERIFIABLE —— 库中不存在该状态的项目（不用 fixture 冒充）" % s)
    out.append("")
    for state, res in snap["contexts"].items():
        proj = snap["picks"][state]
        out.append("=" * 78)
        out.append("状态: %s" % state)
        out.append("项目: %s  (%s, FY%s)"
                   % ((proj["project_name"] or "")[:48], proj["project_id"], proj["audit_year"]))
        out.append("  procedure_instances: 总 %d / 已裁剪 %d   materiality 行 %d   B50-T3 行 %d   tb_balance 行 %d"
                   % (proj["proc_total"], proj["proc_trimmed"], proj["mat_rows"],
                      proj["b50_rows"], proj["tb_rows"]))
        if not res["ok"]:
            out.append("  🔴 上下文装配失败（ERROR 态，非降级）: %s" % res["error"])
            continue
        ctx = res["ctx"]
        acc = ctx.get("accounts") or {}
        mat = ctx.get("materiality")
        risk = ctx.get("risk") or {}
        ov = ctx.get("completeness_override")
        entry = ctx.get("workpaper_entry") or {}
        degs = ctx.get("degradations") or []
        out.append("  --- 三维可用性 ---")
        out.append("    accounts(科目金额)     : %d 个科目" % len(acc))
        out.append("    materiality(重要性)    : %s"
                   % ("缺失（不推算）" if not mat else
                      "performance=%s trivial=%s" % (mat.get("performance_materiality"),
                                                     mat.get("trivial_threshold"))))
        out.append("    risk(B50 风险)         : %d 个科目, risk_dimension_available=%s"
                   % (len(risk), ctx.get("risk_dimension_available")))
        out.append("    completeness_override  : %s"
                   % ("读取失败/未知(None)" if ov is None else "%d 个循环有项目级覆盖" % len(ov)))
        out.append("    workpaper_entry        : %d 个 wp_code, 其中已录入 %d"
                   % (len(entry), sum(1 for v in entry.values() if v)))
        out.append("  --- degradations（前端降级标注的唯一来源）---")
        if not degs:
            out.append("    （无）")
        for d in degs:
            out.append("    [%s] %s%s" % (d.get("dimension"), d.get("reason"),
                                          ("  cause=%s" % d["cause"]) if d.get("cause") else ""))
        out.append("  --- 本脚本不产出的三项（前端 TS 独占，重算即第二真源）---")
        for what, where in FRONTEND_ONLY:
            out.append("    %-28s UNVERIFIABLE(kernel is frontend-only by design; 真源 %s)"
                       % (what, where))
    out.append("")
    out.append("=" * 78)
    out.append("结论：三维判据上下文可在真实库上装配；verdict / 汇总闸 / 豁免分布须走 Task 26 浏览器实测。")
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description="Task 25 真实库验收（只读）")
    ap.add_argument("--out", default="tmp_t25_live_report.txt", help="报告落盘路径")
    args = ap.parse_args()
    snap = asyncio.run(_snapshot())
    text = _fmt(snap)
    Path(args.out).write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
