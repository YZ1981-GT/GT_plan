"""note_template_{soe,listed}.json 一次性治理脚本（幂等）.

Spec: .kiro/specs/disclosure-note-full-revamp/ Sprint 0 Task 0.1
Design: D1 row_type sidecar 字段（不替代现有 row 字段）

职责：
1. 删除每个 table.headers 数组中的空字符串 / 纯空白占位（约 800+ 处）
2. 给每个 row 打 ``row_type``（按 label vs is_total / 关键字 / 占位符 启发式判断）
3. 输出 diff 报告 ``scripts/cleanup_report.txt``
4. 幂等：重复跑 --apply 不重复添加 row_type、不重复删除 headers

启发式规则（与 design.md D1 对齐）：
    1. row.is_total == True              → "total"
    2. label 含「合计」「小计」「总计」 → "subtotal" (无 is_total) / "total" (有)
    3. label == headers[0]（标题/分组行）→ "header_label"
    4. label 含 ``${...}`` 或 ``dynamic_`` → "dynamic_detail"
    5. label 含 ``=`` 或 row 含 formula_type → "formula"
    6. 其他                               → "data"

使用：
    python scripts/cleanup_note_templates.py --dry-run        # 预览
    python scripts/cleanup_note_templates.py --apply           # 实际写入

CI 卡点：见 backend/tests/services/test_note_template_row_type.py
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# 路径配置
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_FILES: list[Path] = [
    PROJECT_ROOT / "backend" / "data" / "note_template_soe.json",
    PROJECT_ROOT / "backend" / "data" / "note_template_listed.json",
]
REPORT_FILE = PROJECT_ROOT / "scripts" / "cleanup_report.txt"

# 合法 row_type 枚举（与 design.md D1 对齐）
VALID_ROW_TYPES: tuple[str, ...] = (
    "data",
    "header_label",
    "subtotal",
    "total",
    "dynamic_detail",
    "formula",
)

# 中文小计/合计/总计 关键字
SUBTOTAL_KEYWORDS = ("小计",)
TOTAL_KEYWORDS = ("合计", "总计")

# 动态占位符 / 公式模式
DYNAMIC_PATTERN = re.compile(r"\$\{[^}]+\}|^dynamic_")
FORMULA_PATTERN = re.compile(r"^\s*=")


# ---------------------------------------------------------------------------
# 启发式 row_type 判定
# ---------------------------------------------------------------------------


def _normalize(text: str) -> str:
    """全角空格 / 多空白归一，便于"项  目"==headers[0] 匹配."""
    return re.sub(r"\s+", "", text or "")


def detect_row_type(row: dict[str, Any], headers: list[str]) -> str:
    """根据 row 内容 + 当前表 headers，推断 row_type."""
    label_raw = row.get("label") or ""
    label = _normalize(label_raw)

    # 规则 5：显式公式（最高优先级，避开误判）
    if "formula_type" in row or FORMULA_PATTERN.search(label_raw):
        return "formula"

    # 规则 4：动态占位符
    if DYNAMIC_PATTERN.search(label_raw):
        return "dynamic_detail"

    # 规则 1 + 2：合计 / 小计 / 总计
    is_total_flag = bool(row.get("is_total"))
    has_total_kw = any(kw in label for kw in TOTAL_KEYWORDS)
    has_subtotal_kw = any(kw in label for kw in SUBTOTAL_KEYWORDS)

    if is_total_flag:
        # 显式 is_total：根据关键字细化 subtotal/total，缺省 total
        if has_subtotal_kw and not has_total_kw:
            return "subtotal"
        return "total"
    if has_total_kw or has_subtotal_kw:
        # 没设 is_total 但 label 有合计/小计 → subtotal（保守：让人工 review 升 total）
        return "subtotal"

    # 规则 3：label == headers[0]（纯标题/分组标签行）
    if headers:
        h0 = _normalize(headers[0])
        if h0 and label == h0:
            return "header_label"

    # 规则 6：默认
    return "data"


# ---------------------------------------------------------------------------
# 治理执行
# ---------------------------------------------------------------------------


def _clean_headers(headers: list[Any]) -> tuple[list[Any], int]:
    """删除 None / 空串 / 纯空白字符串占位，返回 (新 headers, 删除数)."""
    if not isinstance(headers, list):
        return headers, 0
    cleaned: list[Any] = []
    removed = 0
    for h in headers:
        if h is None:
            removed += 1
            continue
        if isinstance(h, str) and not h.strip():
            removed += 1
            continue
        cleaned.append(h)
    return cleaned, removed


def _process_table(table: dict[str, Any], stats: dict[str, Any]) -> None:
    """就地清理一张 table 的 headers + 标记 rows."""
    if not isinstance(table, dict):
        return

    # ① headers 治理
    if "headers" in table:
        new_headers, removed = _clean_headers(table["headers"])
        if removed:
            stats["empty_headers_removed"] += removed
            table["headers"] = new_headers

    headers = table.get("headers") or []

    # ② rows 标 row_type
    rows = table.get("rows") or []
    for r in rows:
        if not isinstance(r, dict):
            continue
        stats["rows_total"] += 1
        existing = r.get("row_type")
        if existing in VALID_ROW_TYPES:
            # 幂等：已有合法 row_type 不动
            stats["rows_already_tagged"] += 1
            stats["row_type_counter"][existing] += 1
            continue
        rt = detect_row_type(r, headers)
        r["row_type"] = rt
        stats["row_type_counter"][rt] += 1
        stats["rows_tagged"] += 1
        # 收集需要人工 review 的边界（label 为空 但被标 data 等）
        lbl = (r.get("label") or "").strip()
        if not lbl:
            stats["rows_review_needed"].append(
                {
                    "section": stats["_current_section"],
                    "table_name": table.get("name"),
                    "row_type": rt,
                    "reason": "empty_label",
                    "row": r,
                }
            )


def _process_section(section: dict[str, Any], stats: dict[str, Any]) -> None:
    stats["sections_total"] += 1
    stats["_current_section"] = section.get("section_number")

    # 主路径：sections[*].tables[*]
    for tbl in section.get("tables") or []:
        stats["tables_total"] += 1
        _process_table(tbl, stats)

    # 防御性：若未来出现 _tables / 顶层 headers+rows，也兼容处理
    for tbl in section.get("_tables") or []:
        stats["tables_total"] += 1
        _process_table(tbl, stats)
    if "headers" in section or "rows" in section:
        # 把 section 自身当一张"伪表"处理
        pseudo = {"headers": section.get("headers"), "rows": section.get("rows")}
        _process_table(pseudo, stats)
        if "headers" in section and pseudo.get("headers") is not None:
            section["headers"] = pseudo["headers"]


def _process_file(path: Path, apply: bool) -> dict[str, Any]:
    """处理一个 template JSON，返回该文件的统计."""
    with path.open(encoding="utf-8") as f:
        data = json.load(f)

    stats: dict[str, Any] = {
        "file": str(path.relative_to(PROJECT_ROOT)),
        "sections_total": 0,
        "tables_total": 0,
        "rows_total": 0,
        "rows_tagged": 0,
        "rows_already_tagged": 0,
        "empty_headers_removed": 0,
        "row_type_counter": Counter(),
        "rows_review_needed": [],
        "_current_section": None,
    }

    sections = data.get("sections") or []
    for s in sections:
        _process_section(s, stats)

    if apply:
        # 写回（保留中文 + 缩进风格）
        with path.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")

    # 清理临时键
    stats.pop("_current_section", None)
    return stats


# ---------------------------------------------------------------------------
# 报告输出
# ---------------------------------------------------------------------------


def _format_report(per_file_stats: list[dict[str, Any]], apply: bool) -> str:
    lines: list[str] = []
    lines.append("=" * 72)
    lines.append(
        f"note_template cleanup report  (mode={'APPLY' if apply else 'DRY-RUN'})"
    )
    lines.append("=" * 72)
    grand = Counter()
    grand_review: list[Any] = []

    for st in per_file_stats:
        lines.append("")
        lines.append(f"[file] {st['file']}")
        lines.append(f"  sections processed       : {st['sections_total']}")
        lines.append(f"  tables  processed        : {st['tables_total']}")
        lines.append(f"  rows total               : {st['rows_total']}")
        lines.append(
            f"  rows tagged this run     : {st['rows_tagged']}"
            f"   (already tagged: {st['rows_already_tagged']})"
        )
        lines.append(
            f"  empty headers removed    : {st['empty_headers_removed']}"
        )
        rt_dist = st["row_type_counter"]
        lines.append("  row_type distribution:")
        for rt in VALID_ROW_TYPES:
            lines.append(f"    {rt:<14}: {rt_dist.get(rt, 0)}")
            grand[rt] += rt_dist.get(rt, 0)
        unknown = {k: v for k, v in rt_dist.items() if k not in VALID_ROW_TYPES}
        if unknown:
            lines.append(f"    UNKNOWN(!) : {unknown}")
        if st["rows_review_needed"]:
            lines.append(
                f"  rows needing manual review: {len(st['rows_review_needed'])}"
            )
            grand_review.extend(st["rows_review_needed"])

    # 汇总
    lines.append("")
    lines.append("-" * 72)
    lines.append("[grand total row_type distribution]")
    grand_total = sum(grand.values())
    for rt in VALID_ROW_TYPES:
        cnt = grand.get(rt, 0)
        pct = (cnt * 100.0 / grand_total) if grand_total else 0
        lines.append(f"  {rt:<14}: {cnt:>5}  ({pct:5.1f}%)")
    lines.append(f"  {'TOTAL':<14}: {grand_total:>5}")

    # 边界 review
    if grand_review:
        lines.append("")
        lines.append("-" * 72)
        lines.append(f"[manual review needed]  {len(grand_review)} entries")
        for i, item in enumerate(grand_review[:50], 1):
            lines.append(
                f"  {i:>3}. section={item['section']!r}"
                f" table={item['table_name']!r}"
                f" row_type={item['row_type']}"
                f" reason={item['reason']}"
            )
        if len(grand_review) > 50:
            lines.append(f"  ... ({len(grand_review) - 50} more truncated)")

    lines.append("")
    lines.append("=" * 72)
    if apply:
        lines.append("[OK] Files have been updated in place.")
    else:
        lines.append("(dry-run) - no files written. Re-run with --apply to commit.")

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--dry-run",
        dest="dry_run",
        action="store_true",
        help="Preview changes without writing files.",
    )
    group.add_argument(
        "--apply",
        dest="apply",
        action="store_true",
        help="Actually write changes to template JSON files.",
    )
    args = parser.parse_args(argv)
    apply = bool(args.apply)

    per_file_stats: list[dict[str, Any]] = []
    for path in TEMPLATE_FILES:
        if not path.exists():
            print(f"[WARN] template missing: {path}", file=sys.stderr)
            continue
        per_file_stats.append(_process_file(path, apply=apply))

    report = _format_report(per_file_stats, apply=apply)
    REPORT_FILE.parent.mkdir(parents=True, exist_ok=True)
    REPORT_FILE.write_text(report, encoding="utf-8")

    # Windows GBK 控制台兼容：sys.stdout 默认编码可能是 cp936，
    # 用 buffer 直接写 UTF-8 字节，避免 ✓/中文字符触发 UnicodeEncodeError。
    try:
        sys.stdout.buffer.write(report.encode("utf-8", errors="replace"))
    except AttributeError:
        # 测试环境下 stdout 可能被 capsys 包了一层 没有 buffer
        print(report)
    print(f"[report] written to {REPORT_FILE.relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
