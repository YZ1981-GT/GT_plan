"""跨变体 row_code 差异诊断（只读）.

spec: soe-listed-note-conversion-correctness Task 6

按 `report_config.applicable_standard` 四值逐一比对 `(report_type, row_name)`，
输出两张互斥的表：

- **同义两码**：同一 `row_name` 在 soe 侧与 listed 侧各恰有 1 个 row_code 且两者不等
  ⇒ 跨变体转换时公式引用**需要**改写。
- **一码两义**：同一 row_code 在 soe 侧与 listed 侧的 `row_name` 不同
  ⇒ 跨变体转换时**禁止**改写（改写会把明细行指向另一科目甚至合计行）。

用途：生成 `app/services/note_conversion_row_codes.py` 两个冻结常量的候选清单，
人工确认后冻结。**本脚本只读，不写库、不改代码。**

用法::

    python backend/scripts/diagnose/diagnose_cross_variant_row_codes.py
    python backend/scripts/diagnose/diagnose_cross_variant_row_codes.py --out tmp_rowcodes.txt
    python backend/scripts/diagnose/diagnose_cross_variant_row_codes.py --check

`--check` 比对实测结果与已冻结常量是否一致，不一致以非零退出码结束。

🔴 输出一律 ASCII 标记（`[OK]`/`[ERR]`），禁 emoji —— Windows GBK 控制台会
`UnicodeEncodeError` 且崩点在写盘之后。
"""
from __future__ import annotations

import argparse
import asyncio
import pathlib
import sys
from collections import defaultdict
from dataclasses import dataclass, field

_BACKEND = pathlib.Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

import sqlalchemy as sa  # noqa: E402

SOE_STANDARDS = ("soe_standalone", "soe_consolidated")
LISTED_STANDARDS = ("listed_standalone", "listed_consolidated")


@dataclass
class SynonymPair:
    """同义两码：同一 row_name，soe/listed 各一个不同的 row_code。"""

    report_type: str
    row_name: str
    soe_code: str
    listed_code: str


@dataclass
class OneCodeTwoMeanings:
    """一码两义：同一 row_code，soe/listed 下 row_name 不同。"""

    row_code: str
    report_type: str
    listed_row_name: str
    soe_row_name: str


@dataclass
class DiagnoseResult:
    synonyms: list[SynonymPair] = field(default_factory=list)
    one_code_two_meanings: list[OneCodeTwoMeanings] = field(default_factory=list)
    total_rows: int = 0
    formula_refs_to_synonyms: int = 0
    report_config_has_project_column: bool = False


async def _load_rows(db) -> list[dict]:
    result = await db.execute(
        sa.text(
            "SELECT row_code, applicable_standard, report_type::text AS report_type, "
            "       row_name, formula "
            "FROM report_config "
            "WHERE is_deleted = false AND applicable_standard IS NOT NULL "
            "ORDER BY row_code, applicable_standard"
        )
    )
    return [dict(r) for r in result.mappings().all()]


def _side_of(applicable_standard: str) -> str | None:
    if applicable_standard in SOE_STANDARDS:
        return "soe"
    if applicable_standard in LISTED_STANDARDS:
        return "listed"
    return None


def analyze(rows: list[dict]) -> DiagnoseResult:
    """纯函数：从 report_config 行集算出两张表。"""
    res = DiagnoseResult(total_rows=len(rows))

    # ── 同义两码：(report_type, row_name) → {side: set(row_code)} ──
    by_name: dict[tuple[str, str], dict[str, set[str]]] = defaultdict(
        lambda: {"soe": set(), "listed": set()}
    )
    # ── 一码两义：row_code → {side: set(row_name)} ──
    by_code: dict[str, dict[str, set[str]]] = defaultdict(
        lambda: {"soe": set(), "listed": set()}
    )
    code_report_type: dict[str, str] = {}

    for r in rows:
        side = _side_of(r["applicable_standard"] or "")
        if side is None:
            continue
        rt = r["report_type"] or ""
        name = (r["row_name"] or "").strip()
        code = (r["row_code"] or "").strip()
        if not code:
            continue
        code_report_type.setdefault(code, rt)
        if name:
            by_name[(rt, name)][side].add(code)
        by_code[code][side].add(name)

    for (rt, name), sides in sorted(by_name.items()):
        soe_codes = sides["soe"]
        listed_codes = sides["listed"]
        # 判据：两侧各恰有 1 个 row_code 且两者不等
        if len(soe_codes) == 1 and len(listed_codes) == 1:
            soe_code = next(iter(soe_codes))
            listed_code = next(iter(listed_codes))
            if soe_code != listed_code:
                res.synonyms.append(
                    SynonymPair(
                        report_type=rt,
                        row_name=name,
                        soe_code=soe_code,
                        listed_code=listed_code,
                    )
                )

    for code, sides in sorted(by_code.items()):
        soe_names = {n for n in sides["soe"] if n}
        listed_names = {n for n in sides["listed"] if n}
        if not soe_names or not listed_names:
            continue
        if soe_names != listed_names:
            res.one_code_two_meanings.append(
                OneCodeTwoMeanings(
                    row_code=code,
                    report_type=code_report_type.get(code, ""),
                    listed_row_name=" | ".join(sorted(listed_names)),
                    soe_row_name=" | ".join(sorted(soe_names)),
                )
            )

    # ── 公式引用面：全库 formula 里对同义两码的引用数 ──
    synonym_codes = {p.soe_code for p in res.synonyms} | {
        p.listed_code for p in res.synonyms
    }
    for r in rows:
        f = r.get("formula") or ""
        if not f:
            continue
        for code in synonym_codes:
            if f"'{code}'" in f:
                res.formula_refs_to_synonyms += 1
                break

    return res


async def _has_project_column(db) -> bool:
    result = await db.execute(
        sa.text(
            "SELECT count(*) FROM information_schema.columns "
            "WHERE table_name = 'report_config' AND column_name = 'project_id'"
        )
    )
    return bool((result.scalar() or 0) > 0)


def render(res: DiagnoseResult) -> str:
    lines: list[str] = []
    lines.append("=" * 78)
    lines.append("跨变体 row_code 差异诊断（report_config，只读）")
    lines.append("=" * 78)
    lines.append(f"report_config 行数（四变体合计）: {res.total_rows}")
    lines.append(
        f"report_config 是否有 project_id 列: "
        f"{'YES' if res.report_config_has_project_column else 'NO（纯模板表）'}"
    )
    lines.append("")

    lines.append(f"[1] 同义两码（需要改写）: {len(res.synonyms)} 条")
    lines.append("-" * 78)
    lines.append(
        f"{'report_type':<24}{'soe':<10}{'listed':<10}row_name"
    )
    for p in res.synonyms:
        lines.append(
            f"{p.report_type:<24}{p.soe_code:<10}{p.listed_code:<10}{p.row_name}"
        )
    lines.append("")

    lines.append(
        f"[2] 一码两义（禁止改写）: {len(res.one_code_two_meanings)} 条"
    )
    lines.append("-" * 78)
    for m in res.one_code_two_meanings:
        lines.append(f"{m.row_code:<10}{m.report_type}")
        lines.append(f"           listed: {m.listed_row_name}")
        lines.append(f"           soe   : {m.soe_row_name}")
    lines.append("")

    lines.append("[3] 公式引用面")
    lines.append("-" * 78)
    lines.append(
        f"全库 report_config.formula 中引用「同义两码」的行数: "
        f"{res.formula_refs_to_synonyms}"
    )
    if res.formula_refs_to_synonyms == 0:
        lines.append(
            "  => 无任何公式引用这些 row_code；`_update_formula_references` "
            "在 report_config 域内无可改写对象（原因码 no_mapping_needed）。"
        )
    lines.append("")
    return "\n".join(lines)


def _compare_with_frozen(res: DiagnoseResult) -> tuple[bool, list[str]]:
    """比对实测与已冻结常量。返回 (ok, messages)。"""
    msgs: list[str] = []
    try:
        from app.services.note_conversion_row_codes import (
            CROSS_VARIANT_ROW_CODE_MAP,
            ONE_CODE_TWO_MEANINGS_FORBIDDEN,
        )
    except ImportError as exc:
        return False, [f"[ERR] 无法导入冻结常量: {exc}"]

    live_map = {p.soe_code: p.listed_code for p in res.synonyms}
    if live_map != dict(CROSS_VARIANT_ROW_CODE_MAP):
        only_live = set(live_map.items()) - set(CROSS_VARIANT_ROW_CODE_MAP.items())
        only_frozen = set(CROSS_VARIANT_ROW_CODE_MAP.items()) - set(live_map.items())
        msgs.append("[ERR] 同义两码清单与实测不一致")
        if only_live:
            msgs.append(f"       实测独有: {sorted(only_live)}")
        if only_frozen:
            msgs.append(f"       冻结独有: {sorted(only_frozen)}")
    else:
        msgs.append(f"[OK] 同义两码清单一致（{len(live_map)} 条）")

    live_forbidden = {m.row_code for m in res.one_code_two_meanings}
    frozen_forbidden = set(ONE_CODE_TWO_MEANINGS_FORBIDDEN)
    if not frozen_forbidden <= live_forbidden:
        msgs.append(
            f"[ERR] 禁止清单中有实测已不存在的 row_code: "
            f"{sorted(frozen_forbidden - live_forbidden)}"
        )
    else:
        msgs.append(
            f"[OK] 禁止清单 {len(frozen_forbidden)} 条全部仍是实测的一码两义"
            f"（实测共 {len(live_forbidden)} 条）"
        )

    ok = all(not m.startswith("[ERR]") for m in msgs)
    return ok, msgs


async def _main_async(args: argparse.Namespace) -> int:
    from app.core.database import async_session

    async with async_session() as db:
        rows = await _load_rows(db)
        has_proj = await _has_project_column(db)

    res = analyze(rows)
    res.report_config_has_project_column = has_proj

    text = render(res)
    if args.out:
        pathlib.Path(args.out).write_text(text, encoding="utf-8")
        print(f"[OK] 已写入 {args.out}")
    else:
        print(text)

    if args.check:
        ok, msgs = _compare_with_frozen(res)
        for m in msgs:
            print(m)
        return 0 if ok else 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", help="输出文件路径（默认打印到 stdout）")
    parser.add_argument(
        "--check",
        action="store_true",
        help="比对实测与已冻结常量，不一致以非零退出码结束",
    )
    args = parser.parse_args()
    return asyncio.run(_main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
