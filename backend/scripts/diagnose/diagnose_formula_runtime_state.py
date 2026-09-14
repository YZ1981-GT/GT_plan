"""公式运行时状态只读诊断。

spec: formula-management-runtime-closure Task 18
  (Requirements 10.1, 10.2, 10.3 / Property 23, 24)

**只读**：全程只 SELECT，不写库、不改文件。可对生产库直接跑。

回答四个问题：

1. **公式定义到底有没有？** —— `wp_formula` 行数 + 按 `formula_source` /
   `formula_type` / `lifecycle_state` 分布，以及 `parsed_data` 侧遗留键规模。
   立项实测该表 **0 行** ⇒ `FormulaRuntimeCoordinator._load_formulas` 每次返空并
   early-return，整条运行时链从上线起没有真实数据流经过。
2. **三张运行时表是否仍空？** —— `cross_check_results` / `draft_marker` /
   `draft_refresh_audit` / `formula_runtime_outbox`。它们是"表在但空"的最坏状态：
   无法跨底稿查「是否都有结论」，而空表又让人误以为功能在跑。
3. **未注册列名的公式格还有多少？** —— 修复前 **48**（本期借方 19 / 本期贷方 17 /
   贷方发生额 7 / 借方发生额 5），修复后应为 **0**。这两个数字由
   `test_formula_column_alias_coverage.py` 钉死，本脚本只做独立复算。
4. **每个公式格的取数是四态里的哪一态？**（Property 23，**禁合并成「无数据」**）

   | 态 | 含义 | 处置 |
   |---|---|---|
   | `ok` | 取到值 | 同时输出取值路径（科目码 + 解析后列名 + 数据源表） |
   | `missing_column` | 列名未注册（**配置错**） | 修 `COLUMN_ALIASES` |
   | `no_data` | 列名合法但该科目该列无数据（**数据缺**） | 查四表入库 |
   | `no_formula` | 该格压根没有公式定义 | 不是缺陷 |

   🔴 前三态**必须可区分**：改造前 `TB()` 对未注册列名**静默回退期末余额**，
   于是 `missing_column` 伪装成 `ok`（数字错而非取不到）—— 这正是 48 格数字错
   长期无人发现的原因。

用法::

    python backend/scripts/diagnose/diagnose_formula_runtime_state.py
    python backend/scripts/diagnose/diagnose_formula_runtime_state.py --project <uuid> --year 2025
    python backend/scripts/diagnose/diagnose_formula_runtime_state.py --out report.txt

无 DB 连接时**不报错退出**，只跳过库侧章节并如实标注 `UNVERIFIABLE`
（禁用 fixture 冒充真实库结论）。
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from collections import Counter
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

REPO_ROOT = BACKEND.parent

# 立项实测基线（2026-08-06），供本脚本独立复算时对照
BASELINE_UNREGISTERED_CELLS = 48
BASELINE_UNREGISTERED_BREAKDOWN = {
    "本期借方": 19,
    "本期贷方": 17,
    "贷方发生额": 7,
    "借方发生额": 5,
}

RUNTIME_TABLES = (
    "wp_formula",
    "cross_check_results",
    "draft_marker",
    "draft_refresh_audit",
    "formula_runtime_outbox",
)


# ---------------------------------------------------------------------------
# 1. 预设公式的列名四态复算（不连库，纯文件分析）
# ---------------------------------------------------------------------------


def analyze_preset_columns() -> list[str]:
    """扫 `prefill_formula_mapping.json`，统计每个公式格的列名注册状态。

    🔴 路径是 `backend/data/`，**不是** `backend/data/ledger_adapters/`
    （后者是 render schema 的目录；memory 已登记该踩坑）。
    """
    out: list[str] = []
    mapping_path = BACKEND / "data" / "prefill_formula_mapping.json"
    out.append(f"预设映射文件：{mapping_path.relative_to(REPO_ROOT)}")
    if not mapping_path.exists():
        out.append("  !! 文件不存在 —— UNVERIFIABLE")
        return out

    try:
        from app.services.formula_engine import COLUMN_ALIASES
    except Exception as exc:  # noqa: BLE001
        out.append(f"  !! 无法导入 COLUMN_ALIASES：{exc!r} —— UNVERIFIABLE")
        return out

    data = json.loads(mapping_path.read_text(encoding="utf-8"))
    blocks = data.get("mappings") or []

    total_cells = 0
    col_usage: Counter[str] = Counter()
    unregistered: Counter[str] = Counter()
    unregistered_cells: list[str] = []
    func_usage: Counter[str] = Counter()

    # TB('code','col') / SUM_TB('a~b','col') 的第二实参即列名
    col_re = re.compile(r"\b(?:SUM_)?TB\(\s*'[^']*'\s*,\s*'([^']*)'\s*\)")
    func_re = re.compile(r"\b([A-Z_]+)\s*\(")

    for blk in blocks:
        wp = blk.get("wp_code") or blk.get("wp") or "?"
        sheet = blk.get("sheet") or ""
        for cell in blk.get("cells") or []:
            total_cells += 1
            expr = cell.get("formula") or ""
            ref = cell.get("cell_ref") or ""
            for fn in func_re.findall(expr):
                func_usage[fn] += 1
            for col in col_re.findall(expr):
                col_usage[col] += 1
                if col not in COLUMN_ALIASES:
                    unregistered[col] += 1
                    unregistered_cells.append(f"{wp}/{sheet}/{ref}: {expr}")

    out.append(f"  公式格总数 = {total_cells}")
    out.append(f"  COLUMN_ALIASES 已注册键数 = {len(COLUMN_ALIASES)}")
    out.append(f"  列名使用分布（TB/SUM_TB 第二实参）= {dict(col_usage.most_common())}")
    out.append(f"  函数使用分布 = {dict(func_usage.most_common())}")
    out.append("")
    out.append(f"  【missing_column】未注册列名的公式格 = {sum(unregistered.values())}")
    if unregistered:
        out.append(f"    分解 = {dict(unregistered.most_common())}")
        for line in unregistered_cells[:20]:
            out.append(f"      - {line}")
        if len(unregistered_cells) > 20:
            out.append(f"      … 另 {len(unregistered_cells) - 20} 格")
    else:
        out.append("    （0 格 —— Wave 2 修复已生效）")

    out.append("")
    out.append(
        f"  对照立项基线：修复前 {BASELINE_UNREGISTERED_CELLS} 格"
        f"（{BASELINE_UNREGISTERED_BREAKDOWN}）"
    )
    got = sum(unregistered.values())
    if got == 0:
        out.append("  ✔ 与预期一致（修复后应为 0）")
    elif got == BASELINE_UNREGISTERED_CELLS:
        out.append("  !! 仍是修复前的 48 格 —— Wave 2 可能被回退，先查 COLUMN_ALIASES 键数")
    else:
        out.append(f"  !! 既非 0 也非 48（实测 {got}）—— 预设文件或别名表被改动，需人工核")
    return out


# ---------------------------------------------------------------------------
# 2. 列名四态判定（纯函数，供库侧与文件侧共用）
# ---------------------------------------------------------------------------


def classify_cell(expr: str, tb_data: dict, column_aliases: dict) -> tuple[str, str]:
    """判定一个公式格的取数状态（Property 23 的四态，禁合并）。

    Returns:
        (state, detail) — state ∈ {ok, missing_column, no_data, no_formula}
    """
    if not expr or not expr.strip():
        return "no_formula", "该格无公式定义"

    col_re = re.compile(r"\b(?:SUM_)?TB\(\s*'([^']*)'\s*,\s*'([^']*)'\s*\)")
    refs = col_re.findall(expr)
    if not refs:
        return "no_formula", "公式不含 TB/SUM_TB 取数（可能是纯算术或其他函数）"

    for code, col in refs:
        if col not in column_aliases:
            return (
                "missing_column",
                f"列名「{col}」未注册（配置错，修 COLUMN_ALIASES；"
                f"改造前此处会静默回退期末余额 = 数字错）",
            )
        canonical = column_aliases[col]
        acct = tb_data.get(code)
        if acct is None:
            return "no_data", f"科目 {code} 不在 tb_data（数据缺，查四表入库）"
        if canonical not in acct:
            return (
                "no_data",
                f"科目 {code} 有记录但缺列「{canonical}」（数据缺，非配置错）",
            )
    code, col = refs[0]
    canonical = column_aliases[col]
    return (
        "ok",
        f"取值路径：科目 {code} → 列名「{col}」解析为规范名「{canonical}」"
        f" → 数据源 trial_balance/tb_balance（发生额列来自 tb_balance）",
    )


# ---------------------------------------------------------------------------
# 3. 库侧：表行数与分布
# ---------------------------------------------------------------------------


async def analyze_db(project: str | None, year: int | None) -> list[str]:
    out: list[str] = []
    try:
        import sqlalchemy as sa

        from app.core.database import async_session
    except Exception as exc:  # noqa: BLE001
        out.append(f"!! 无法导入 DB 层：{exc!r} —— 库侧章节 UNVERIFIABLE")
        return out

    try:
        async with async_session() as db:
            # 表存在性 + 行数
            out.append("【运行时表行数】")
            for tbl in RUNTIME_TABLES:
                exists = (
                    await db.execute(sa.text(f"SELECT to_regclass('public.{tbl}')"))
                ).scalar()
                if exists is None:
                    out.append(f"  {tbl:<28} 表不存在")
                    continue
                n = (
                    await db.execute(sa.text(f"SELECT count(*) FROM {tbl}"))
                ).scalar()
                flag = ""
                if n == 0:
                    flag = "  ← 「表在但空」：无法跨底稿查询，且空表让人误以为功能在跑"
                out.append(f"  {tbl:<28} {n} 行{flag}")

            # wp_formula 分布
            n_wf = (
                await db.execute(sa.text("SELECT count(*) FROM wp_formula"))
            ).scalar()
            out.append("")
            out.append("【wp_formula 分布】")
            if n_wf == 0:
                out.append(
                    "  0 行 ⇒ FormulaRuntimeCoordinator._load_formulas 每次返空并"
                    " early-return（Task 11 已让该情形进 scope_failures 可见）"
                )
            else:
                for col in ("formula_source", "formula_type", "lifecycle_state"):
                    rows = (
                        await db.execute(
                            sa.text(
                                f"SELECT {col}, count(*) FROM wp_formula "
                                f"GROUP BY {col} ORDER BY 2 DESC"
                            )
                        )
                    ).all()
                    out.append(f"  按 {col}: {[(r[0], r[1]) for r in rows]}")

            # parsed_data 遗留键规模
            out.append("")
            out.append("【parsed_data 遗留键】")
            legacy = (
                await db.execute(
                    sa.text(
                        "SELECT count(*) FROM working_paper "
                        "WHERE parsed_data ? 'user_formulas'"
                    )
                )
            ).scalar()
            out.append(
                f"  parsed_data ? 'user_formulas' = {legacy} 行"
                "（GET 读时合并保留该兼容分支；PUT 只回写 original_preset 溯源）"
            )
            cells = (
                await db.execute(
                    sa.text(
                        "SELECT count(*) FROM working_paper "
                        "WHERE parsed_data ? 'cells'"
                    )
                )
            ).scalar()
            out.append(f"  parsed_data ? 'cells' = {cells} 行（WP()/PREV() 取值源）")

            # 四态实测（需 project/year）
            if project and year:
                out.append("")
                out.append(f"【四态实测】project={project} year={year}")
                rows = (
                    await db.execute(
                        sa.text(
                            "SELECT sheet_name, target_cell, expression "
                            "FROM wp_formula WHERE project_id = CAST(:p AS uuid) "
                            "ORDER BY sheet_name, target_cell LIMIT 200"
                        ),
                        {"p": project},
                    )
                ).all()
                if not rows:
                    out.append("  该项目 wp_formula 无行 → 全部 no_formula")
                else:
                    from app.services.formula_engine import COLUMN_ALIASES

                    tb_rows = (
                        await db.execute(
                            sa.text(
                                "SELECT standard_account_code, audited_amount, "
                                "unadjusted_amount, opening_balance "
                                "FROM trial_balance "
                                "WHERE project_id = CAST(:p AS uuid) AND year = :y "
                                "AND is_deleted = false"
                            ),
                            {"p": project, "y": year},
                        )
                    ).all()
                    tb_data = {
                        r[0]: {
                            "期末余额": r[1],
                            "未审数": r[2],
                            "年初余额": r[3],
                        }
                        for r in tb_rows
                        if r[0]
                    }
                    states: Counter[str] = Counter()
                    samples: dict[str, str] = {}
                    for sheet, cell, expr in rows:
                        st, detail = classify_cell(expr, tb_data, COLUMN_ALIASES)
                        states[st] += 1
                        samples.setdefault(st, f"{sheet}!{cell}: {expr} → {detail}")
                    out.append(f"  四态分布 = {dict(states)}")
                    for st in ("ok", "missing_column", "no_data", "no_formula"):
                        if st in samples:
                            out.append(f"    [{st}] {samples[st]}")
            else:
                out.append("")
                out.append(
                    "【四态实测】未指定 --project/--year，跳过"
                    "（禁用 fixture 冒充真实库结论）"
                )
    except Exception as exc:  # noqa: BLE001
        out.append(f"!! 库侧查询失败：{type(exc).__name__}: {exc} —— UNVERIFIABLE")
    return out


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--project", help="项目 UUID（做四态实测时必填）")
    ap.add_argument("--year", type=int, help="审计年度")
    ap.add_argument("--out", help="输出文件（默认打印到 stdout）")
    ap.add_argument(
        "--no-db", action="store_true", help="只做文件侧分析，不连库"
    )
    args = ap.parse_args()

    lines: list[str] = []
    lines.append("=" * 78)
    lines.append("公式运行时状态只读诊断（formula-management-runtime-closure Task 18）")
    lines.append("=" * 78)
    lines.append("")
    lines.append("── 一、预设公式列名注册状态（文件侧，不连库）──")
    lines.extend(analyze_preset_columns())
    lines.append("")

    if args.no_db:
        lines.append("── 二、库侧（已按 --no-db 跳过）──")
    else:
        lines.append("── 二、库侧运行时状态 ──")
        lines.extend(asyncio.run(analyze_db(args.project, args.year)))

    text = "\n".join(lines) + "\n"
    if args.out:
        # 🔴 一律脚本自己写盘（GBK 控制台会让含特殊字符的输出 UnicodeEncodeError；
        #    PowerShell 的 `>` 重定向还会腌坏 UTF-8 中文）
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"written: {args.out}")
    else:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
