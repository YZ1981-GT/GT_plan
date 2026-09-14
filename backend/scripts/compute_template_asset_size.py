#!/usr/bin/env python3
"""计算 audit_report_templates 活跃资产总字节数并写入 manifest.metadata.

Task 12.2。统计 report_body（不含 _archive_doc 归档）+ financial_statements +
disclosure_notes 三类活跃资产字节数，写入 template_manifest.json 的 metadata 块。

Usage:
    python backend/scripts/compute_template_asset_size.py            # 仅打印
    python backend/scripts/compute_template_asset_size.py --write    # 写回 manifest
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent
ROOT = _BACKEND / "data" / "audit_report_templates"
MANIFEST = ROOT / "template_manifest.json"

ASSET_DIRS = ["report_body", "financial_statements", "disclosure_notes"]
EXCLUDE_PARTS = {"_archive_doc"}


def _dir_size(path: Path) -> int:
    if not path.exists():
        return 0
    total = 0
    for f in path.rglob("*"):
        if not f.is_file():
            continue
        if EXCLUDE_PARTS & set(f.parts):
            continue
        total += f.stat().st_size
    return total


def compute() -> dict[str, int]:
    per = {d: _dir_size(ROOT / d) for d in ASSET_DIRS}
    per["total"] = sum(per.values())
    return per


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    sizes = compute()
    for k, v in sizes.items():
        print(f"  {k}: {v:,} bytes")

    if args.write:
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        meta = manifest.setdefault("metadata", {})
        meta["asset_size_bytes"] = {
            **sizes,
            "_note": (
                "活跃模板资产字节数（不含 report_body/_archive_doc 归档原始 .doc）；"
                "由 scripts/compute_template_asset_size.py 生成"
            ),
        }
        MANIFEST.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"Wrote {MANIFEST}")


if __name__ == "__main__":
    main()
