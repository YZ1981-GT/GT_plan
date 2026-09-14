"""幂等修订 N2 应交税费附注章节行集（§五、41 / §八、41）扩充到源模板 13 种 + 合计。

权威源
------
``backend/wp_templates/N/N2 应交税费.xlsx`` 的
``附注披露信息（上市公司）`` R8~R20 / ``附注披露信息（国企）`` R8~R20，
两版 A 列逐字一致（13 行）。

修订内容
--------
- 两版 ``tables[0].rows`` 替换为 13 固定行（``row_type: data``）+ 合计行（``is_total + row_type: total``）。
- ``_aligned_by`` 更新为 ``"n2-disclosure-and-extraction-alignment"``。
- 幂等：若已是 13 + 合计（14 行）且 label 逐字一致，则不动。

用法::

    python -m scripts.fix.fix_note_n2_tax_structure --dry-run   # 打印变更不写盘
    python -m scripts.fix.fix_note_n2_tax_structure --check     # 不一致则 exit 1（CI）
    python -m scripts.fix.fix_note_n2_tax_structure             # 就地修订（默认 apply）
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
LISTED_PATH = DATA_DIR / "note_template_listed.json"
SOE_PATH = DATA_DIR / "note_template_soe.json"

ALIGNED_BY = "n2-disclosure-and-extraction-alignment"

SECTION_LISTED = "五、41"
SECTION_SOE = "八、41"

# 源模板 R8~R20 逐字 13 固定税种（两版完全一致）
N2_FIXED_LABELS: list[str] = [
    "企业所得税",
    "增值税",
    "消费税",
    "资源税",
    "土地增值税",
    "城市维护建设税",
    "车船牌照税",
    "房产税",
    "土地使用税",
    "教育费附加",
    "矿产资源补偿费",
    "代扣代缴外国企业所得税",
    "代扣代缴个人所得税",
]


def _build_rows() -> list[dict[str, Any]]:
    """构建源模板 13 行 + 合计行。"""
    rows: list[dict[str, Any]] = []
    for label in N2_FIXED_LABELS:
        rows.append({"label": label, "row_type": "data"})
    rows.append({"label": "合计", "is_total": True, "row_type": "total"})
    return rows


def _find_section(data: dict[str, Any], section_number: str) -> dict[str, Any] | None:
    hits = [s for s in data.get("sections", []) if s.get("section_number") == section_number]
    if len(hits) != 1:
        return None
    return hits[0]


def _rows_match(existing: list[dict[str, Any]], target: list[dict[str, Any]]) -> bool:
    """比对行集是否已对齐。"""
    if len(existing) != len(target):
        return False
    for a, b in zip(existing, target):
        if a.get("label") != b.get("label"):
            return False
        if a.get("row_type") != b.get("row_type"):
            return False
        if a.get("is_total") != b.get("is_total"):
            return False
    return True


def apply(*, check_only: bool = False, dry_run: bool = False) -> bool:
    """返回 True 表示有待修订内容。"""
    target_rows = _build_rows()
    any_changed = False

    plans: list[tuple[str, Path, str]] = [
        ("N2/listed", LISTED_PATH, SECTION_LISTED),
        ("N2/soe", SOE_PATH, SECTION_SOE),
    ]

    pending: dict[Path, dict[str, Any]] = {}

    for label, path, section_number in plans:
        data = pending.get(path)
        if data is None:
            data = json.loads(path.read_text(encoding="utf-8"))
            pending[path] = data

        section = _find_section(data, section_number)
        if section is None:
            print(f"[{label}] 未找到 section {section_number}，跳过")
            continue

        tables = section.get("tables") or []
        if not tables:
            print(f"[{label}] section {section_number} 无 tables，跳过")
            continue

        tbl = tables[0]
        existing_rows = tbl.get("rows") or []

        if _rows_match(existing_rows, target_rows) and section.get("_aligned_by") == ALIGNED_BY:
            print(f"[{label}] {section_number} 已对齐（{len(target_rows)} 行），无需修改")
            continue

        any_changed = True
        if check_only or dry_run:
            print(f"[{label}] {section_number} 行集待扩充：{len(existing_rows)} 行 → {len(target_rows)} 行")
            continue

        tbl["rows"] = target_rows
        section["_aligned_by"] = ALIGNED_BY
        print(f"[{label}] {section_number} 已修订为 {len(target_rows)} 行（13 种 + 合计）")

    if any_changed and not (check_only or dry_run):
        for path, data in pending.items():
            path.write_bytes(json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8"))

    return any_changed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="只校验不写盘，不一致则 exit 1")
    parser.add_argument("--dry-run", action="store_true", help="只打印差异摘要，不写盘")
    args = parser.parse_args()
    changed = apply(check_only=args.check, dry_run=args.dry_run)
    if args.check and changed:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
