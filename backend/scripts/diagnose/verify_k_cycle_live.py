#!/usr/bin/env python
"""K 循环真实库验收（**只读**）—— Task 24 / Requirement 14.1~14.3, 14.8。

对**全部在册项目 × 14 个循环**（K0~K13）逐组合直跑取数链路，并用**独立 SQL**
交叉核对聚合口径。判据不是「函数没抛异常」，而是四条：

① **覆盖**：每个「项目 × 循环」组合都有明确结论，不许静默跳过；
② **独立交叉核对**：「叶子和 == 父额」用纯 SQL 重算一遍，与 `parent_check`
   的输出比对 —— **不拿被测函数证明自己**。两条路径口径已实证一致
   （同一项目 all_rows=400 / leaf_rows=297 逐一相等）；
③ **三级归因**：取不到数的组合逐条归因到 ``ACTIVE_WRONG`` / ``SILENT_EMPTY`` /
   ``TRACE_ONLY`` / ``NOT_IN_PROJECT`` / ``NO_ACCOUNT``，不笼统报「无数据」；
④ **诚实报空**：无数据组合如实输出「本项目无此科目」，不用 0.00 冒充。

**只读保证**：全程只有 SELECT；不 commit、不写任何表。连接用 ``NullPool``
且在 finally 里 dispose。

**为什么零回归不用 HEAD-swap**（Requirement 14.8）：本 spec 改的
`prefill_formula_mapping.json` / `note_template_*.json` 混着并发会话的未提交成果，
把文件换成 HEAD 版会把别人的改动一起换掉、对照结果无法归因。改用
「当前态 → 施加幂等脚本 → 对照」：`fix_k_cycle_prefill_presets.py --check` 归零
即证明当前态已是幂等收敛态。

用法::

    python backend/scripts/diagnose/verify_k_cycle_live.py              # 全量
    python backend/scripts/diagnose/verify_k_cycle_live.py --wp K6      # 单循环
    python backend/scripts/diagnose/verify_k_cycle_live.py --json-only  # 只出 JSON

spec: .kiro/specs/k-cycle-extraction-formula-and-disclosure-closure/
      Task 24 / Property 50, 52
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "backend"))

import sqlalchemy as sa  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

#: 三口径互认容差（元）——与 `four_table.parent_check.TOLERANCE` 同值
TOLERANCE = 0.01


def _utf8() -> None:
    for s in (sys.stdout, sys.stderr):
        rc = getattr(s, "reconfigure", None)
        if rc is not None:
            try:
                rc(encoding="utf-8", errors="replace")
            except Exception:  # noqa: BLE001
                pass


# ─────────────────────────────────────────────────────────────────────────────
# 独立 SQL：叶子和 / 父额（不经任何被测的 Python 聚合函数）
# ─────────────────────────────────────────────────────────────────────────────

#: 🔴 叶子定义必须与 `leaf_aggregation.select_leaves` 一致：**同 dataset 内**
#: 不存在以 ``本码 + '.'`` 开头的兄弟行。漏掉 ``dataset_id`` 分桶会把
#: staged/superseded 数据集的子科目当成 active 的子科目，叶子集就错了。
#: 🔴 必须同时算出**两种符号约定**下的叶子和（2026-08-14 实测踩到）。
#:
#: `tb_balance` 里同一份业务数据存在两种存储约定，没有一种对所有项目都对
#: （`leaf_aggregation.resolve_leaf_totals` 的 docstring 有 13 组实证）：
#:   - ``as_stored``    余额已带符号，直接求和
#:   - ``directional``  余额存无符号绝对值，与父科目方向不同的叶子取负
#:
#: 初版只算裸求和，结果 K3 上出现 2 处「不一致」—— ``py_leaf=2,189,098.79`` 而
#: ``sql=4,118,101.21``，差值正好是 ``2 × 964,501.21``（一个 contra 子科目被
#: 多加了两倍）。那不是生产缺陷，是**本核对脚本口径不全**。
#:
#: 交叉核对的正确形态：SQL 独立算出两个候选值，再验证「被测函数选中的那个
#: 恰好与父额勾稽成立」—— 这样既独立又能判对错。
_SQL_CROSS_CHECK = sa.text(
    """
    WITH active AS (
        SELECT d.id AS dataset_id
        FROM ledger_datasets d
        WHERE d.project_id = :pid AND d.status = 'active'
    ),
    rows0 AS (
        SELECT t.account_code, t.dataset_id, t.closing_direction,
               t.closing_balance, t.debit_amount, t.credit_amount
        FROM tb_balance t
        JOIN active a ON a.dataset_id = t.dataset_id
        WHERE t.project_id = :pid AND t.is_deleted = false
    ),
    leaves AS (
        SELECT r.* FROM rows0 r
        WHERE NOT EXISTS (
            SELECT 1 FROM rows0 c
            WHERE c.dataset_id = r.dataset_id
              AND c.account_code <> r.account_code
              AND c.account_code LIKE r.account_code || '.%'
        )
    ),
    scoped AS (
        SELECT * FROM leaves
        WHERE account_code = :code OR account_code LIKE :pfx
    ),
    parent AS (
        SELECT closing_direction, closing_balance, debit_amount, credit_amount
        FROM rows0 WHERE account_code = :code LIMIT 1
    )
    SELECT
        COALESCE((SELECT SUM(closing_balance) FROM scoped), 0)          AS leaf_as_stored,
        COALESCE((
            SELECT SUM(CASE
                WHEN p.closing_direction IS NULL
                     OR s.closing_direction IS NULL
                     OR s.closing_direction = p.closing_direction
                THEN s.closing_balance ELSE -s.closing_balance END)
            FROM scoped s CROSS JOIN parent p
        ), 0)                                                           AS leaf_directional,
        COALESCE((SELECT SUM(closing_balance) FROM rows0
                  WHERE account_code = :code), 0)                       AS parent_amt,
        (SELECT COUNT(*) FROM scoped)                                   AS leaf_hits,
        COALESCE((SELECT SUM(debit_amount) FROM scoped), 0)             AS leaf_debit,
        COALESCE((SELECT SUM(credit_amount) FROM scoped), 0)            AS leaf_credit,
        -- 🔴 父额也必须给发生额口径：损益科目的 `closing_balance` 恒 0，
        --    只给余额口径会让全部损益组合的 `sql_parent` 恒 0、与
        --    `parent_check` 的 occurrence 分支对不上（本脚本第二版踩到）。
        COALESCE((SELECT SUM(debit_amount) FROM rows0
                  WHERE account_code = :code), 0)                       AS parent_debit,
        COALESCE((SELECT SUM(credit_amount) FROM rows0
                  WHERE account_code = :code), 0)                       AS parent_credit
    """
)

_SQL_TRIAL = sa.text(
    """
    SELECT COALESCE(SUM(unadjusted_amount), 0)
    FROM trial_balance
    WHERE project_id = :pid AND year = :year AND is_deleted = false
      AND standard_account_code = ANY(:codes)
    """
)


async def cross_check(
    db, pid: str, year: int, prefixes: list[str], std: list[str], *, occurrence: bool
) -> dict:
    """纯 SQL 重算叶子和（两种符号约定）/ 父额 / trial 合计。

    Args:
        occurrence: 损益类置 ``True`` —— 用**发生额**而非期末余额。
            🔴 损益科目不结转期末余额（`tb_balance.closing_balance` 恒 0），
            用余额核对会把 34 个损益组合全报成「与 trial 不一致」（本脚本初版踩到）。
    """
    as_stored = directional = parent_bal = 0.0
    debit = credit = p_debit = p_credit = 0.0
    leaf_hits = 0
    for code in prefixes:
        r = (
            await db.execute(_SQL_CROSS_CHECK, {"pid": pid, "code": code, "pfx": f"{code}.%"})
        ).first()
        as_stored += float(r[0] or 0)
        directional += float(r[1] or 0)
        parent_bal += float(r[2] or 0)
        leaf_hits += int(r[3] or 0)
        debit += float(r[4] or 0)
        credit += float(r[5] or 0)
        p_debit += float(r[6] or 0)
        p_credit += float(r[7] or 0)
    trial = 0.0
    if std:
        trial = float(
            (await db.execute(_SQL_TRIAL, {"pid": pid, "year": year, "codes": std})).scalar()
            or 0
        )
    # 损益类口径 = 正方向单侧发生额（与 parent_check 的 occurrence 分支同口径）
    occ = credit if abs(credit) >= abs(debit) else debit
    p_occ = p_credit if abs(p_credit) >= abs(p_debit) else p_debit
    return {
        "sql_leaf_as_stored": round(as_stored, 2),
        "sql_leaf_directional": round(directional, 2),
        "sql_leaf_occurrence": round(occ, 2),
        "sql_parent": round(p_occ if occurrence else parent_bal, 2),
        "sql_parent_balance": round(parent_bal, 2),
        "sql_parent_occurrence": round(p_occ, 2),
        "sql_trial": round(trial, 2),
        "sql_leaf_hits": leaf_hits,
        "sql_occurrence_mode": occurrence,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 归因
# ─────────────────────────────────────────────────────────────────────────────


def classify(spec, accounts, sql: dict) -> str:
    """把「取不到数」归因到具体分类，而不是笼统报「无数据」。"""
    if spec is None:
        return "EXEMPT"  # K0 函证循环，无科目余额口径
    if not spec.has_account:
        return "NO_ACCOUNT"  # 标准科目表里就没这科目（设计期结论，K4）
    if not accounts.gross:
        return "UNRESOLVED"  # 报表映射与兜底都没解析出科目
    if sql["sql_leaf_hits"] == 0:
        return "NOT_IN_PROJECT"  # 科目存在但本项目没用（运行期降级）
    # 损益类看发生额、余额类看期末余额（损益不结转余额，用余额判会全报零值）
    amount = (
        sql["sql_leaf_occurrence"] if spec.is_pl else sql["sql_leaf_as_stored"]
    )
    if abs(amount) < TOLERANCE and abs(sql["sql_parent"]) < TOLERANCE:
        return "ZERO_BALANCE"  # 有该科目且金额确为 0（合法零值，区别于上一条）
    return "OK"


# ─────────────────────────────────────────────────────────────────────────────
# 主流程
# ─────────────────────────────────────────────────────────────────────────────


async def run(wp_filter: str | None) -> dict:
    from app.core.config import settings
    from app.services.four_table.k_cycle_specs import (
        CYCLES_EXEMPT_FROM_ACCOUNT_SPEC,
        K_CYCLE_SPECS,
        liability_spec_for,
    )
    from app.services.four_table.parent_check import (
        SLOT_GROSS,
        build_report_line_parent_check,
    )
    from app.services.four_table.report_line_accounts import resolve_report_line_accounts
    from app.services.four_table.tb_fetch import fetch_tb_balance_all
    from app.services.four_table.tb_query import fetch_trial_balance_rows

    all_cycles = ["K0"] + [f"K{i}" for i in range(1, 14)]
    cycles = [wp_filter.upper()] if wp_filter else all_cycles

    engine = create_async_engine(str(settings.DATABASE_URL), poolclass=NullPool)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    report: dict = {"combos": [], "errors": [], "summary": {}}

    try:
        async with Session() as db:
            projects = (
                await db.execute(
                    sa.text(
                        """
                        SELECT id::text, name, audit_year,
                               COALESCE(applicable_standard_v2->>'entity_type','soe') AS ent,
                               COALESCE(report_scope,'standalone') AS scope
                        FROM projects
                        WHERE is_deleted = false AND audit_year IS NOT NULL
                        ORDER BY name, audit_year
                        """
                    )
                )
            ).all()

            for pid, name, year, ent, scope in projects:
                stds = [f"{ent}_{scope}", str(ent), str(scope)]
                ctx = SimpleNamespace(db=db, project_id=str(pid), year=int(year))
                tb_rows = await fetch_tb_balance_all(ctx, label="verify_k_live")

                for wp in cycles:
                    if wp in CYCLES_EXEMPT_FROM_ACCOUNT_SPEC:
                        report["combos"].append(
                            {
                                "proj": str(name)[:22],
                                "year": int(year),
                                "wp": wp,
                                "verdict": "EXEMPT",
                                "note": CYCLES_EXEMPT_FROM_ACCOUNT_SPEC[wp][:40],
                            }
                        )
                        continue

                    spec = K_CYCLE_SPECS.get(wp)
                    if spec is None:
                        report["errors"].append(f"{wp} 既不在声明表也不在豁免表")
                        continue

                    # 资产/主体侧 + K6 负债侧
                    sides = [("main", spec.spec_for(stds))]
                    if wp == "K6":
                        sides.append(("liability", liability_spec_for(stds)))

                    for side, rl_spec in sides:
                        try:
                            acc = await resolve_report_line_accounts(ctx, rl_spec)
                            std = list(acc.gross_standard) + list(acc.provision_standard)
                            trial_rows = await fetch_trial_balance_rows(
                                db, str(pid), int(year), std
                            )
                            pc = build_report_line_parent_check(
                                acc, tb_rows, trial_rows, occurrence=spec.is_pl
                            )
                            sql = await cross_check(
                                db,
                                str(pid),
                                int(year),
                                list(acc.gross),
                                list(acc.gross_standard),
                                occurrence=spec.is_pl,
                            )
                        except Exception as exc:  # noqa: BLE001
                            report["errors"].append(
                                f"{name}/{wp}/{side}: {type(exc).__name__}: {exc}"
                            )
                            continue

                        verdict = classify(spec, acc, sql)
                        g = pc.get(SLOT_GROSS) or {}
                        py_leaf = round(float(g.get("leaf_sum") or 0), 2)
                        py_parent = round(float(g.get("parent") or 0), 2)

                        # ② 独立交叉核对：被测函数选中的 leaf_sum 必须**恰好等于**
                        #    SQL 独立算出的某个候选值。余额类有两个候选（两种符号
                        #    约定），损益类走发生额候选。只要落在候选集内即算一致 ——
                        #    这样既是独立核对，又不会因约定选择差异误报。
                        candidates = (
                            [sql["sql_leaf_occurrence"]]
                            if spec.is_pl
                            else [sql["sql_leaf_as_stored"], sql["sql_leaf_directional"]]
                        )
                        xmatch = any(
                            abs(py_leaf - c) <= TOLERANCE for c in candidates
                        ) and abs(py_parent - sql["sql_parent"]) <= TOLERANCE
                        report["combos"].append(
                            {
                                "proj": str(name)[:22],
                                "year": int(year),
                                "wp": wp,
                                "side": side,
                                "verdict": verdict,
                                "row_code": acc.row_code,
                                "resolved_from": acc.resolved_from,
                                "gross": list(acc.gross),
                                "py_leaf": py_leaf,
                                "py_parent": py_parent,
                                **sql,
                                "cross_match": xmatch,
                                "diff_parent": round(py_leaf - py_parent, 2),
                                "diff_trial": round(
                                    float(g.get("diff_trial") or 0), 2
                                ),
                                "severity": (
                                    None if verdict == "OK" else _severity_of(spec)
                                ),
                            }
                        )
    finally:
        await engine.dispose()

    _summarize(report)
    return report


def _severity_of(spec) -> str | None:
    from app.services.four_table.k_cycle_specs import severity_of

    return severity_of(spec.wp_code)


def _summarize(report: dict) -> None:
    combos = report["combos"]
    by_verdict: dict[str, int] = {}
    for c in combos:
        by_verdict[c["verdict"]] = by_verdict.get(c["verdict"], 0) + 1

    scored = [c for c in combos if "cross_match" in c]
    mismatch = [c for c in scored if not c["cross_match"]]
    parent_off = [c for c in scored if abs(c["diff_parent"]) > TOLERANCE]
    # 🔴 trial 差异必须分两类，否则真问题会被符号噪声埋掉：
    #   sign_only —— |leaf| == |trial| 仅符号相反。属**既有跨表符号口径差**
    #                （`tb_balance` 备抵/损益存负、`trial_balance` v2 正数口径），
    #                不是数据错误，Task 9 实录已登记。
    #   real      —— 绝对值也不等。这才是审计价值所在（如 K1 的 1.69 亿）。
    trial_all = [
        c for c in scored if abs(c["diff_trial"]) > TOLERANCE and c["sql_trial"] != 0
    ]
    sign_only = [
        c
        for c in trial_all
        if abs(abs(c["py_leaf"]) - abs(c["sql_trial"])) <= TOLERANCE
    ]
    trial_off = [c for c in trial_all if c not in sign_only]

    report["summary"] = {
        "projects": len({(c["proj"], c["year"]) for c in combos}),
        "cycles": len({c["wp"] for c in combos}),
        "combos": len(combos),
        "by_verdict": dict(sorted(by_verdict.items())),
        "cross_checked": len(scored),
        "cross_mismatch": len(mismatch),
        "leaf_vs_parent_off": len(parent_off),
        "trial_sign_convention_only": len(sign_only),
        "trial_real_discrepancies": len(trial_off),
        "errors": len(report["errors"]),
    }
    report["cross_mismatch_detail"] = mismatch[:20]
    report["leaf_vs_parent_off_detail"] = parent_off[:20]
    report["trial_discrepancy_detail"] = [
        {
            k: c.get(k)
            for k in (
                "proj", "year", "wp", "side", "verdict",
                "py_leaf", "sql_trial", "diff_trial", "sql_occurrence_mode",
            )
        }
        for c in trial_off[:20]
    ]


def main() -> None:
    _utf8()
    ap = argparse.ArgumentParser(description="K 循环真实库只读验收")
    ap.add_argument("--wp", help="只验单个循环（如 K6）")
    ap.add_argument("--json-only", action="store_true", help="只写 JSON 不打印明细")
    args = ap.parse_args()

    report = asyncio.run(run(args.wp))
    out = ROOT / "_k_cycle_live_verification.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")

    s = report["summary"]
    print(json.dumps(s, ensure_ascii=False, indent=1))
    if not args.json_only:
        if report["errors"]:
            print("\n=== 异常（应为 0）===")
            for e in report["errors"][:10]:
                print("  ", e)
        if report["cross_mismatch_detail"]:
            print("\n=== 独立 SQL 与 parent_check 不一致（应为 0）===")
            for c in report["cross_mismatch_detail"][:8]:
                print(
                    f"   {c['proj']}/{c['wp']}/{c.get('side')}: py_leaf={c['py_leaf']}"
                    f"  sql候选=[as_stored={c['sql_leaf_as_stored']},"
                    f" directional={c['sql_leaf_directional']},"
                    f" occurrence={c['sql_leaf_occurrence']}]"
                    f"  py_parent={c['py_parent']} sql_parent={c['sql_parent']}"
                )
        if report["trial_discrepancy_detail"]:
            print("\n=== trial_balance 与叶子和差异（审计价值，非缺陷）===")
            for c in report["trial_discrepancy_detail"][:8]:
                print(
                    f"   {c['proj']}/{c['wp']}: leaf={c['py_leaf']} "
                    f"trial={c['sql_trial']} diff={c['diff_trial']}"
                )
    print(f"\n报告已写入 {out.name}")

    # 判据：异常必须为 0，独立核对必须全一致，叶子和必须等于父额
    bad = s["errors"] or s["cross_mismatch"] or s["leaf_vs_parent_off"]
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
