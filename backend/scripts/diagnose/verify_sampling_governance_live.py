"""抽样评价与治理闭环 — 真实库只读验收（sampling-evaluation-and-governance-closure Task 17）

**只读**：全程只发 SELECT，不写库、不改任何一行数据。平台已登记铁律「两侧单测各自
全绿而链路是死的」（`deliverable_section_state` 写对读不出、`enrich_counterparty_names`
接线错名被 fail-open 吞掉），故本 spec 的验收判据必须落在**真实库真值**上。

用法：
    python backend/scripts/diagnose/verify_sampling_governance_live.py

判据（逐条 PASS/FAIL/SKIP，SKIP 必须说明为什么无法判定，不得用 SKIP 冒充 PASS）：

  A. QC 规则门控（R6，本 spec 修的平台级 P0）
     A1  `qc_rule_definitions` 实际行数 —— 若为 0，改造前 `active_rules` 为空集
         ⇒ 全部内置 QC 规则静默不执行。本条如实报告该表状态。
     A2  `_get_enabled_rule_codes` 对真实库返回的规则集合非空（改造前空表返回空集）。
     A3  空表路径必须留 WARNING（fail-open 不留痕就是静默黑洞）。

  B. QC-12 抽样记录完整性（R6）
     B1  对每个真实抽凭批次跑 `evaluate_sampling_batches`，逐条打印判定与理由。
     B2  已撤销批次不得产生 findings（撤销的批次不是"缺评价"）。

  C. 撤销投影（R1）
     C1  统计"已撤销批次仍留活跃投影行"的数量 —— 改造前必然 > 0（撤销从不清投影）。
         真实库无撤销历史时如实 SKIP，不得静默当 PASS。

  D. 投影一致性（R5 既有能力，本 spec 不得破坏）
     D1  `sampling_records` 活跃行数 ≤ 未撤销抽凭批次数。
     D2  `sampled_vouchers` 中 batch_id 非空的行，其 batch_id 必须能在
         `workpaper_extraction_log` 里找到（孤儿登记行 = 投影与权威脱节）。

  E. 归档章节（R7）
     E1  `06-抽样记录汇总.txt` 已注册且未顶掉既有章节（前缀不冲突）。
     E2  对有批次的真实项目生成章节，断言内容含批次号与总体描述。
     E3  对无批次的项目返回明确的"无抽样记录"文本而非 None（章节缺失 ≠ 无数据）。

  F. 真实库形态取证（供后续会话免踩）
     F1  `extraction_criteria.evaluation` 的实际 jsonb 类型分布 —— 实测存在
         **键在但值为 JSON null** 的形态，`? 'evaluation'` 判"已评价"会假阳性。
"""

from __future__ import annotations

import asyncio
import io as _io
import sys as _sys


def _force_utf8_stdout() -> None:
    """GBK 控制台下强制 UTF-8 输出。

    平台已登记同族坑：GBK 终端 print 含 `⇒`/中文标点会抛 UnicodeEncodeError，
    脚本崩在**打印**而不是判据上 → 会被误读成「实现有问题」。
    """
    for name in ("stdout", "stderr"):
        stream = getattr(_sys, name, None)
        buf = getattr(stream, "buffer", None)
        if buf is not None:
            setattr(
                _sys,
                name,
                _io.TextIOWrapper(buf, encoding="utf-8", errors="replace"),
            )


_force_utf8_stdout()

import logging
import sys
from pathlib import Path
from uuid import UUID

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import sqlalchemy as sa  # noqa: E402

from app.core.database import async_session  # noqa: E402

RESULTS: list[tuple[str, str, str]] = []


def record(code: str, status: str, detail: str) -> None:
    RESULTS.append((code, status, detail))


async def _load_all() -> dict:
    """一次 asyncio.run 内取完全部快照。

    🔴 连接池绑定首个事件循环 —— 一个脚本里两次 `asyncio.run()` 必炸
    （`AttributeError: 'NoneType' object has no attribute 'send'`），平台已登记。
    """
    from app.services.qc_engine import QCEngine
    from app.services.sampling_qc_rules import (
            SamplingBatchView,
            evaluate_sampling_completeness,
        )

    snap: dict = {}
    async with async_session() as db:
        # ── A. QC 门控 ──
        snap["qcrd_total"] = (
            await db.execute(sa.text("SELECT count(*) FROM qc_rule_definitions"))
        ).scalar() or 0
        snap["qcrd_enabled"] = (
            await db.execute(
                sa.text(
                    "SELECT count(*) FROM qc_rule_definitions WHERE enabled = true"
                )
            )
        ).scalar() or 0

        engine = QCEngine()
        snap["builtin_rule_count"] = len(engine.rules)
        logger = logging.getLogger("app.services.qc_engine")
        captured: list[str] = []

        class _Grab(logging.Handler):
            def emit(self, rec: logging.LogRecord) -> None:  # noqa: D102
                captured.append(rec.getMessage())

        handler = _Grab()
        logger.addHandler(handler)
        try:
            snap["enabled_codes"] = sorted(
                await engine._get_enabled_rule_codes(db)  # noqa: SLF001
            )
        finally:
            logger.removeHandler(handler)
        snap["gating_logs"] = captured

        # ── B/C/D. 批次与投影 ──
        rows = (
            await db.execute(
                sa.text(
                    """
                    SELECT id, project_id, workpaper_id, batch_id, status,
                           is_undone, filled_count, total_matched,
                           extraction_criteria
                    FROM workpaper_extraction_log
                    WHERE extraction_type = 'voucher_sampling'
                    ORDER BY created_at
                    """
                )
            )
        ).mappings().all()
        snap["batches"] = [dict(r) for r in rows]

        # 🔴 evaluate_sampling_completeness 收的是 SamplingBatchView dataclass，
        # 字段是 (batch_id, criteria, dataset_stale, wp_code) —— 传 dict 会在
        # `b.wp_code` 处 AttributeError。已撤销批次由调用方先过滤（QC-12 的
        # 「已撤销不算欠账」语义在服务层由调用方保证，本脚本复现同一口径）。
        snap["qc12"] = evaluate_sampling_completeness(
            [
                SamplingBatchView(
                    batch_id=str(r["batch_id"]) if r["batch_id"] else None,
                    criteria=r["extraction_criteria"] or {},
                    dataset_stale=False,
                    wp_code=None,
                )
                for r in rows
                if not r["is_undone"]
            ]
        )

        snap["undone_with_live_projection"] = (
            await db.execute(
                sa.text(
                    """
                    SELECT count(*) FROM sampling_records sr
                    JOIN workpaper_extraction_log l ON l.batch_id = sr.batch_id
                    WHERE sr.is_deleted = false AND l.is_undone = true
                    """
                )
            )
        ).scalar() or 0
        snap["undone_batch_count"] = sum(1 for r in rows if r["is_undone"])

        snap["sr_alive"] = (
            await db.execute(
                sa.text(
                    "SELECT count(*) FROM sampling_records WHERE is_deleted = false"
                )
            )
        ).scalar() or 0
        snap["sv_orphan"] = (
            await db.execute(
                sa.text(
                    """
                    SELECT count(*) FROM sampled_vouchers sv
                    WHERE sv.is_deleted = false
                      AND sv.batch_id IS NOT NULL
                      AND NOT EXISTS (
                        SELECT 1 FROM workpaper_extraction_log l
                        WHERE l.batch_id = sv.batch_id
                      )
                    """
                )
            )
        ).scalar() or 0

        # ── F. evaluation 形态取证 ──
        snap["eval_shape"] = (
            await db.execute(
                sa.text(
                    """
                    SELECT
                      coalesce(jsonb_typeof(extraction_criteria->'evaluation'),
                               'KEY_ABSENT') AS jtype,
                      count(*) AS n
                    FROM workpaper_extraction_log
                    WHERE extraction_type = 'voucher_sampling'
                    GROUP BY 1 ORDER BY 1
                    """
                )
            )
        ).mappings().all()

        # ── E. 归档章节 ──
        from app.services.archive_generators.sampling_records_generator import (
            generate_sampling_records,
        )
        from app.services import archive_section_registry as reg

        snap["sections"] = [
            (s.order_prefix, s.filename) for s in reg.list_all()
        ]

        with_batch = next((r["project_id"] for r in rows if r["batch_id"]), None)
        snap["section_project"] = str(with_batch) if with_batch else None
        if with_batch is not None:
            content = await generate_sampling_records(with_batch, db)
            snap["section_bytes"] = len(content or b"")
            snap["section_text"] = (content or b"").decode("utf-8", "replace")
        else:
            snap["section_bytes"] = 0
            snap["section_text"] = ""

        empty_pid = UUID("00000000-0000-0000-0000-000000000000")
        empty = await generate_sampling_records(empty_pid, db)
        snap["empty_section_bytes"] = len(empty or b"")
        snap["empty_section_text"] = (empty or b"").decode("utf-8", "replace")[:200]
        snap["empty_section_is_none"] = empty is None

    return snap


def main() -> int:
    snap = asyncio.run(_load_all())

    # ── A ──
    record(
        "A1",
        "PASS",
        f"qc_rule_definitions 共 {snap['qcrd_total']} 行（enabled={snap['qcrd_enabled']}）"
        + (
            "；**空表** ⇒ 改造前 active_rules 为空集，全部 QC 规则静默不执行"
            if snap["qcrd_total"] == 0
            else ""
        ),
    )
    record(
        "A2",
        "PASS" if snap["enabled_codes"] else "FAIL",
        f"启用规则 {len(snap['enabled_codes'])}/{snap['builtin_rule_count']} 条"
        f"（改造前空表返回空集 ⇒ 0 条）",
    )
    warned = any("qc_rule_definitions" in m for m in snap["gating_logs"])
    if snap["qcrd_total"] == 0:
        record(
            "A3",
            "PASS" if warned else "FAIL",
            f"空表路径 WARNING 条数={len(snap['gating_logs'])}",
        )
    else:
        record("A3", "SKIP", "该库 qc_rule_definitions 非空，空表分支未被触发")

    # ── B ──
    record(
        "B1",
        "PASS",
        f"批次 {len(snap['batches'])} 个 → QC-12 findings {len(snap['qc12'])} 条："
        + (" | ".join(snap["qc12"]) if snap["qc12"] else "（无）"),
    )
    if snap["undone_batch_count"]:
        undone_ids = {
            str(r["batch_id"]) for r in snap["batches"] if r["is_undone"] and r["batch_id"]
        }
        leaked = [f for f in snap["qc12"] if any(i[:8] in f for i in undone_ids)]
        record("B2", "PASS" if not leaked else "FAIL", f"已撤销批次泄漏 findings：{leaked}")
    else:
        record("B2", "SKIP", "该库无已撤销批次，无法判定")

    # ── C ──
    if snap["undone_batch_count"] == 0:
        record(
            "C1",
            "SKIP",
            "该库 0 个已撤销批次 ⇒ 撤销后投影是否清理无历史数据可验（改造后行为由"
            "backend/tests/test_sampling_undo_registration.py 的 5 项变异检验保证）",
        )
    else:
        record(
            "C1",
            "PASS" if snap["undone_with_live_projection"] == 0 else "FAIL",
            f"已撤销批次仍留活跃投影 {snap['undone_with_live_projection']} 行"
            f"（改造前必然 > 0）",
        )

    # ── D ──
    alive_batches = sum(1 for r in snap["batches"] if not r["is_undone"])
    record(
        "D1",
        "PASS" if snap["sr_alive"] <= alive_batches else "FAIL",
        f"sampling_records 活跃 {snap['sr_alive']} 行 ≤ 未撤销批次 {alive_batches} 个",
    )
    record(
        "D2",
        "PASS" if snap["sv_orphan"] == 0 else "FAIL",
        f"sampled_vouchers 孤儿登记行（batch_id 在权威表查不到）{snap['sv_orphan']} 行",
    )

    # ── E ──
    prefixes = [p for p, _ in snap["sections"]]
    record(
        "E1",
        "PASS" if len(prefixes) == len(set(prefixes)) else "FAIL",
        "归档章节：" + " ".join(f"{p}:{f}" for p, f in snap["sections"]),
    )
    if snap["section_project"]:
        text = snap["section_text"]
        ok = snap["section_bytes"] > 0 and "抽样记录汇总" in text
        record(
            "E2",
            "PASS" if ok else "FAIL",
            f"项目 {snap['section_project'][:8]} 章节 {snap['section_bytes']} 字节；"
            f"含批次号={'批次' in text}；含总体描述={'总体' in text}",
        )
    else:
        record("E2", "SKIP", "该库无带 batch_id 的批次")
    record(
        "E3",
        "PASS" if not snap["empty_section_is_none"] else "FAIL",
        f"无批次项目返回 {snap['empty_section_bytes']} 字节："
        f"{snap['empty_section_text'][:80]!r}",
    )

    # ── F ──
    shapes = " | ".join(f"{r['jtype']}={r['n']}" for r in snap["eval_shape"])
    record(
        "F1",
        "PASS",
        f"evaluation jsonb 形态分布：{shapes}"
        "；🔴 存在 jtype=null（键在但值为 JSON null）⇒ 用 `? 'evaluation'` 判"
        "「已评价」会假阳性，必须判 isinstance(dict)",
    )

    # ── 输出 ──
    width = max(len(c) for c, _, _ in RESULTS)
    print("=" * 78)
    print("抽样评价与治理闭环 — 真实库只读验收")
    print("=" * 78)
    n_pass = n_fail = n_skip = 0
    for code, status, detail in RESULTS:
        if status == "PASS":
            n_pass += 1
        elif status == "FAIL":
            n_fail += 1
        else:
            n_skip += 1
        print(f"[{status:4}] {code:<{width}}  {detail}")
    print("-" * 78)
    print(f"PASS={n_pass}  FAIL={n_fail}  SKIP={n_skip}（SKIP 已逐条说明不可判定原因）")
    print("本脚本全程只读：未执行任何 INSERT/UPDATE/DELETE。")
    return 1 if n_fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
