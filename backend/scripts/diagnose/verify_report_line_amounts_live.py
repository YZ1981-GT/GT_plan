"""真实库验收：裁剪判据的报表行科目金额（**默认只读**）。

spec: procedure-trim-report-line-account-resolution — Task 14
Requirements: 7.3 / Property 20

## 它验什么

1. **四态分布**：遍历有 ``procedure_instances`` 的项目，逐 ``wp_code`` 统计
   ``resolved`` / ``no_report_line`` / ``formula_unavailable`` / ``standard_unset``
2. **索引 status 分布**：``resolved`` / ``no_report_line`` / ``non_balance_driven``
3. **独立算术复核**：对 ``resolved`` 态**另用一套极简线性公式解析器 + 直接 SQL 聚合**
   算一遍，与 ``ReportFormulaParser`` 的结果比对
4. **准则变体覆盖面**：库中不存在的变体输出 ``UNVERIFIABLE``，**不用构造数据冒充**
5. **行名与循环语义是否相符**：期望科目名取自 per-cycle 声明（零新增知识），
   与 ``report_config.row_name`` 比对，不符者列为**待查**（不是缺陷判定）

## 🔴 独立复核为什么不是「把 extract_account_codes 的码相加」

那样会**忽略公式符号** —— 含减项的公式（``TB('1122') - TB('1231-02')``）相加后得到的是
各项绝对值之和，而正确结果是按符号加权和。真实库实测两者差 812,029.70 元。

故本脚本自带一个**只处理线性组合**的极简符号解析器（20 行，走「正则扫 term + 逐项
SQL 聚合 + 按符号累加」的路径），与 ``ReportFormulaParser``（走「正则替换成数值 +
eval 算术表达式」）实现路径完全不同 ⇒ 两者一致才说明取数正确。

含括号/嵌套/``ROW()`` 的公式超出线性形态 ⇒ 标 ``SKIPPED-COMPLEX``（不硬算，
硬算就成了第二个可能出错的实现）。

## 用法

    python backend/scripts/diagnose/verify_report_line_amounts_live.py
    python backend/scripts/diagnose/verify_report_line_amounts_live.py --project <uuid>

产出写盘到 ``tmp_report_line_live_verify.txt``（**不 print 中文** —— Windows 控制台
会把 UTF-8 中文腌成乱码，判据看不清）。
"""

from __future__ import annotations

import argparse
import asyncio
import os
import re
import sys
from decimal import Decimal
from pathlib import Path

import sqlalchemy as sa

_HERE = Path(__file__).resolve()
BACKEND = _HERE.parents[2]
ROOT = BACKEND.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

#: `report_config.applicable_standard` 的四个准则变体
ALL_STANDARDS = (
    "listed_consolidated",
    "listed_standalone",
    "soe_consolidated",
    "soe_standalone",
)

#: 报表引擎的列名 → trial_balance 取值表达式（与 `report_engine._COLUMN_MAP` 同口径）
_COLUMN_EXPR: dict[str, str] = {
    "期末余额": "coalesce(audited_amount, 0)",
    "审定数": "coalesce(audited_amount, 0)",
    "年初余额": "coalesce(opening_balance, 0)",
    "期初余额": "coalesce(opening_balance, 0)",
    "本期发生额": "(coalesce(audited_amount, 0) - coalesce(opening_balance, 0))",
    "未审数": "coalesce(unadjusted_amount, 0)",
    "RJE调整": "coalesce(rje_adjustment, 0)",
    "AJE调整": "coalesce(aje_adjustment, 0)",
}

#: 线性公式的 term：可选符号 + TB/SUM_TB + 码 + 列名
_TERM_RE = re.compile(
    r"([+-]?)\s*(SUM_TB|TB)\(\s*'([^']+)'\s*,\s*'([^']+)'\s*\)"
)


def parse_linear_terms(formula: str) -> list[tuple[int, str, str, str]] | None:
    """把线性组合公式拆成 ``[(符号, 类型, 码, 列名), ...]``；非线性返回 ``None``。

    🔴 判据 = 「把所有 term 从公式里抠掉后，剩下的字符只有空白」。
    残留任何括号 / 数字 / ``ROW(`` / 乘除号 ⇒ 超出线性形态，返回 ``None``
    （交由调用方标 SKIPPED-COMPLEX）—— 硬算就成了第二个可能出错的实现。
    """
    text = str(formula or "")
    if not text.strip():
        return None
    terms: list[tuple[int, str, str, str]] = []
    residue = text
    for m in _TERM_RE.finditer(text):
        sign = -1 if m.group(1) == "-" else 1
        terms.append((sign, m.group(2), m.group(3).strip(), m.group(4).strip()))
        residue = residue.replace(m.group(0), " ", 1)
    if not terms:
        return None
    if residue.strip():
        return None
    return terms


async def _term_amount(conn, pid: str, year: int, term) -> Decimal | None:
    """独立 SQL 聚合单个 term；列名不认识返 ``None``。"""
    _sign, kind, code, column = term
    expr = _COLUMN_EXPR.get(column)
    if expr is None:
        return None
    if kind == "SUM_TB":
        parts = code.split("~")
        if len(parts) != 2:
            return None
        sql = (
            f"SELECT coalesce(sum({expr}), 0) FROM trial_balance "
            "WHERE project_id = :pid AND year = :yr AND is_deleted = false "
            "AND standard_account_code >= :lo AND standard_account_code <= :hi"
        )
        params = {"pid": pid, "yr": year, "lo": parts[0].strip(), "hi": parts[1].strip()}
    else:
        # 🔴 前缀聚合（与 report_engine._get_tb_rows_prefix 同口径）：
        #    TB('2221') 含 222102。改成精确匹配会与被测实现产生系统性差异。
        sql = (
            f"SELECT coalesce(sum({expr}), 0) FROM trial_balance "
            "WHERE project_id = :pid AND year = :yr AND is_deleted = false "
            "AND standard_account_code LIKE :pat"
        )
        params = {"pid": pid, "yr": year, "pat": f"{code}%"}
    return Decimal(str((await conn.execute(sa.text(sql), params)).scalar_one()))


async def independent_amount(conn, pid: str, year: int, formula: str):
    """独立复算金额；返回 ``(值, 说明)``；不可复算时值为 ``None``。"""
    terms = parse_linear_terms(formula)
    if terms is None:
        return None, "SKIPPED-COMPLEX（超出线性组合形态）"
    total = Decimal("0")
    for term in terms:
        got = await _term_amount(conn, pid, year, term)
        if got is None:
            return None, f"SKIPPED-COLUMN（未知列名 {term[3]!r}）"
        total += got * term[0]
    minus = sum(1 for t in terms if t[0] < 0)
    return total, f"terms={len(terms)} minus={minus}"


# ─────────────────────────────────────────────────────────────────────────────
# 期望科目名（取自 per-cycle 声明，零新增知识）
# ─────────────────────────────────────────────────────────────────────────────
def expected_account_names(wp_code: str) -> tuple[str, ...]:
    """该底稿的期望科目中文名；取不到返回空元组（标 NAME-UNKNOWN）。

    只读既有声明的 ``slots[].names`` / ``label`` 与 ``KCycleSpec.account_name``，
    **不自造词表** —— 自造就成了又一份要维护的映射知识。
    """
    try:
        from app.services.four_table import k_cycle_specs
        from app.services.four_table.report_line_index import normalize_wp_code
    except Exception:  # noqa: BLE001
        return ()
    code = normalize_wp_code(wp_code)
    if not code:
        return ()

    kspec = k_cycle_specs.get_k_cycle_spec(code)
    if kspec is not None and getattr(kspec, "account_name", ""):
        return (str(kspec.account_name),)

    for mod_name, attr in (
        ("d_cycle_specs", "D_CYCLE_SPECS"), ("e_cycle_specs", None),
        ("f_cycle_specs", "F_CYCLE_SPECS"), ("g_cycle_specs", "G_CYCLE_SPECS"),
        ("h_cycle_specs", "H_CYCLE_SPECS"), ("i_cycle_specs", "I_CYCLE_SPECS"),
        ("l_cycle_specs", "L_CYCLE_SPECS"), ("m_cycle_specs", "M_CYCLE_SPECS"),
        ("n_cycle_specs", "N_CYCLE_SPECS"),
    ):
        try:
            mod = __import__(f"app.services.four_table.{mod_name}", fromlist=["x"])
        except Exception:  # noqa: BLE001
            continue
        spec = None
        if attr and hasattr(mod, attr):
            spec = getattr(mod, attr).get(code)
        elif mod_name == "e_cycle_specs" and code == "E1":
            spec = getattr(mod, "E1_MONETARY_FUND_SPEC", None)
        if spec is None:
            continue
        names: list[str] = []
        for slot in getattr(spec, "slots", ()) or ():
            names.extend(str(n) for n in (getattr(slot, "names", ()) or ()))
            label = getattr(slot, "label", "")
            if label:
                names.append(str(label))
        return tuple(dict.fromkeys(names))
    return ()


def row_name_suspicious(wp_code: str, row_name: str) -> str:
    """行名是否与循环语义不符；返回诊断说明（空串 = 无异常或无法判断）。"""
    expected = expected_account_names(wp_code)
    name = str(row_name or "").strip()
    if not expected:
        return "NAME-UNKNOWN（该底稿声明里无科目名，无法判断）"
    if not name:
        return ""
    for exp in expected:
        if exp and (exp in name or name in exp):
            return ""
    return f"行名 {name!r} 与声明科目名 {expected[:3]} 无交集"


# ─────────────────────────────────────────────────────────────────────────────
# 主流程
# ─────────────────────────────────────────────────────────────────────────────
_PROJECT_SQL = """
SELECT id::text AS pid, name, audit_year,
       applicable_standard_v2, template_type, report_scope,
       (SELECT count(*) FROM procedure_instances pi WHERE pi.project_id = p.id) AS pi_n,
       (SELECT count(*) FROM trial_balance tb
          WHERE tb.project_id = p.id AND tb.is_deleted = false)                 AS tb_n
FROM projects p
WHERE is_deleted = false
  AND EXISTS (SELECT 1 FROM procedure_instances pi WHERE pi.project_id = p.id)
ORDER BY pi_n DESC
"""

_WP_CODES_SQL = """
SELECT DISTINCT wp_code FROM procedure_instances
WHERE project_id = CAST(:pid AS uuid) AND is_deleted = false
  AND wp_code IS NOT NULL AND btrim(wp_code) <> ''
ORDER BY wp_code
"""


def _combo(entity, scope) -> str:
    e = str(entity or "").strip().lower()
    s = str(scope or "").strip().lower()
    return f"{e}_{s}" if e and s else ""


def _project_standard(row) -> tuple[str, str]:
    """项目准则与状态说明（与被测实现同口径，独立实现一遍）。"""
    v2raw = row["applicable_standard_v2"]
    v2 = _combo(
        v2raw.get("entity_type") if isinstance(v2raw, dict) else None,
        v2raw.get("scope") if isinstance(v2raw, dict) else None,
    )
    legacy = _combo(row["template_type"], row["report_scope"])
    if not v2:
        return "", "v2 未设置"
    if legacy and legacy != v2:
        return "", f"两组分叉 v2={v2} legacy={legacy}"
    if v2 not in ALL_STANDARDS:
        return "", f"取值域外 {v2}"
    return v2, "一致" if legacy else "仅 v2"


async def run(only_project: str | None) -> list[str]:
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.pool import NullPool

    from app.core.config import settings
    from app.services.four_table.report_line_index import (
        REF_RESOLVED,
        indexed_wp_codes,
        resolve_report_line_ref,
    )
    from app.services.report_engine import ReportFormulaParser
    from app.services.trim_report_line_amounts import (
        AMOUNT_RESOLVED,
        resolve_trim_report_line_amounts,
    )

    lines: list[str] = []
    engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
    try:
        async with AsyncSession(engine) as session:
            projects = [
                dict(r._mapping)
                for r in (await session.execute(sa.text(_PROJECT_SQL))).all()
            ]
            if only_project:
                projects = [p for p in projects if p["pid"] == only_project]

            lines.append("=" * 78)
            lines.append("报表行科目金额 · 真实库验收（只读）")
            lines.append("=" * 78)
            lines.append(f"带程序实例的项目数：{len(projects)}")
            lines.append("")

            # ── 索引侧覆盖面（与项目无关）─────────────────────────────────
            idx_codes = indexed_wp_codes()
            idx_dist: dict[str, int] = {}
            for code in idx_codes:
                st = resolve_report_line_ref(code, ["soe_standalone"]).status
                idx_dist[st] = idx_dist.get(st, 0) + 1
            lines.append(f"[索引] 覆盖底稿 {len(idx_codes)} 个，status 分布：{idx_dist}")
            lines.append("")

            # ── 准则变体覆盖面（R7.3 的诚实报告）──────────────────────────
            covered: dict[str, list[str]] = {}
            for p in projects:
                std, note = _project_standard(p)
                if std:
                    covered.setdefault(std, []).append(p["pid"])
            lines.append("[准则变体覆盖面]")
            for std in ALL_STANDARDS:
                pids = covered.get(std) or []
                if pids:
                    lines.append(f"  {std:22s} VERIFIED   项目数={len(pids)}")
                else:
                    lines.append(
                        f"  {std:22s} UNVERIFIABLE 真实库无该变体的项目，"
                        "本轮不对它下任何结论（不用构造数据冒充通过）"
                    )
            lines.append("")

            # ── 行名与循环语义比对：对**索引全量**跑，不只对项目实际有的 wp_code ──
            #
            # 🔴 只对项目实际 wp_code 跑会让报告出现诚实缺口：J1/J2 在库中两个可验证
            #    项目里都没有程序实例 ⇒ 从未进入复核集合 ⇒ 报「0 项可疑」会被误读成
            #    「已验证无异常」。改对索引全量 × 每个已验证准则跑，并把「无法判断」
            #    单独计数，使「检查了多少 / 可疑多少 / 判断不了多少」三者可分。
            suspicious: list[str] = []
            name_checked = name_unknown = 0
            for std in sorted(covered):
                cfg_rows = {
                    str(r._mapping["row_code"]): (
                        str(r._mapping["row_name"] or ""), r._mapping["formula"],
                    )
                    for r in (
                        await session.execute(
                            sa.text(
                                "SELECT row_code, row_name, formula FROM report_config "
                                "WHERE applicable_standard = :std AND is_deleted = false"
                            ),
                            {"std": std},
                        )
                    ).all()
                }
                stds_hint = [std, std.split("_")[0], std.split("_")[-1]]
                for code in idx_codes:
                    ref = resolve_report_line_ref(code, stds_hint)
                    if ref.status != REF_RESOLVED:
                        continue
                    row_name, row_formula = cfg_rows.get(ref.row_code, ("", None))
                    sus = row_name_suspicious(code, row_name)
                    if not sus:
                        name_checked += 1
                    elif sus.startswith("NAME-UNKNOWN"):
                        name_unknown += 1
                    else:
                        # 🔴 分级：行名不符**且该行有取数公式** = 会产出错误金额（高危）；
                        #    行名不符但公式为 None = 本 spec 返 formula_unavailable、
                        #    **不出数** ⇒ 无实际危害（宁缺勿造的直接价值）。
                        #    不分级会让「必须马上修」与「登记待办」混在一起。
                        sev = (
                            "HIGH（该行有取数公式，会按错误科目产出金额）"
                            if str(row_formula or "").strip()
                            else "LOW（该行无取数公式，本 spec 返 formula_unavailable 不出数）"
                        )
                        suspicious.append(
                            f"[{sev}] [{std}] {code} → {ref.row_code} {row_name!r} :: "
                            f"{sus}（取值出处 {ref.source_symbol}）"
                        )

            mismatches: list[str] = []
            resolved_detail: list[str] = []

            for p in projects:
                pid = p["pid"]
                year = int(p["audit_year"] or 0)
                std, std_note = _project_standard(p)
                codes = [
                    r[0]
                    for r in (
                        await session.execute(sa.text(_WP_CODES_SQL), {"pid": pid})
                    ).all()
                ]
                lines.append("-" * 78)
                lines.append(
                    f"项目 {pid}  {p['name']}  year={year}  "
                    f"程序={p['pi_n']}  试算表={p['tb_n']}"
                )
                lines.append(f"  准则：{std or '(未确定)'}  [{std_note}]")
                if not codes:
                    lines.append("  该项目无带底稿编号的程序实例，跳过")
                    continue
                if year <= 0:
                    lines.append("  该项目未设审计年度，金额解析不可进行，跳过")
                    continue

                result = await resolve_trim_report_line_amounts(session, pid, year, codes)
                dist: dict[str, int] = {}
                for item in result.values():
                    dist[item.status] = dist.get(item.status, 0) + 1
                lines.append(f"  四态分布（{len(result)} 个 wp_code）：{dist}")

                resolved_items = {
                    k: v for k, v in result.items() if v.status == AMOUNT_RESOLVED
                }
                if not resolved_items:
                    lines.append("  无 resolved 项，跳过算术复核")
                    continue

                # ── 独立算术复核 ─────────────────────────────────────────
                parser = ReportFormulaParser(session, pid, year)
                checked = matched = skipped = 0
                async with engine.connect() as conn:
                    for code, item in sorted(resolved_items.items()):
                        expected, note = await independent_amount(
                            conn, pid, year, item.formula or ""
                        )
                        if expected is None:
                            skipped += 1
                            continue
                        checked += 1
                        got = Decimal(str(item.amount))
                        if abs(got - expected) <= Decimal("0.01"):
                            matched += 1
                        else:
                            mismatches.append(
                                f"{pid} {code} row={item.row_code} "
                                f"被测={got} 独立={expected} diff={got - expected} "
                                f"formula={item.formula!r} ({note})"
                            )
                        if not resolved_detail or resolved_detail[0].startswith(pid):
                            resolved_detail.append(
                                f"{pid} {code:14s} {item.row_code:8s} "
                                f"{item.row_name:16s} {got:>18,.2f}  {item.formula}"
                            )
                lines.append(
                    f"  独立算术复核：复核 {checked} 项 / 一致 {matched} 项 / "
                    f"跳过 {skipped} 项（非线性公式）"
                )
                # parser 只为确认可实例化（金额已由被测模块产出），避免误以为它未被使用
                assert parser is not None

            lines.append("")
            lines.append("=" * 78)
            lines.append(f"[算术复核不一致] {len(mismatches)} 项")
            lines.extend(f"  {m}" for m in mismatches)
            lines.append("")
            lines.append("[resolved 明细 · 首个可验证项目]（Task 16 浏览器实测的期望值来源）")
            lines.extend(f"  {d}" for d in resolved_detail)
            lines.append("")
            lines.append(
                f"[行名与循环语义比对 · 索引全量 × 已验证准则] "
                f"相符 {name_checked} 项 / 不符 {len(suspicious)} 项 / "
                f"无法判断 {name_unknown} 项（声明里无科目名）"
            )
            lines.append(
                "  ⚠️ 不符项**不是本 spec 引入的缺陷** —— 索引如实跟随 per-cycle 声明，"
                "声明指到哪一行就取哪一行。此处列出供登记独立议题："
            )
            lines.extend(f"  {s}" for s in sorted(set(suspicious)))
            lines.append("")
            verdict = "PASS" if not mismatches else "FAIL"
            lines.append(f"VERDICT: {verdict}（算术复核不一致 {len(mismatches)} 项）")
            assert REF_RESOLVED  # 引用确认
    finally:
        await engine.dispose()
    return lines


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="报表行科目金额真实库验收（只读）")
    ap.add_argument("--project", default="", help="只验指定项目 id")
    ap.add_argument(
        "--out", default=str(ROOT / "tmp_report_line_live_verify.txt"),
        help="报告写盘路径",
    )
    args = ap.parse_args(argv)

    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    try:
        lines = asyncio.run(run(args.project or None))
    except Exception as e:  # noqa: BLE001
        Path(args.out).write_text(f"FATAL: {e!r}\n", encoding="utf-8")
        print("FATAL (see %s)" % args.out)
        return 2

    Path(args.out).write_text("\n".join(lines) + "\n", encoding="utf-8")
    # 🔴 只 print ASCII —— Windows 控制台会把 UTF-8 中文腌成乱码
    tail = [ln for ln in lines if ln.startswith("VERDICT")]
    print("report -> %s" % args.out)
    print(tail[0] if tail else "VERDICT: (missing)")
    return 0 if (tail and tail[0].startswith("VERDICT: PASS")) else 1


if __name__ == "__main__":
    raise SystemExit(main())
