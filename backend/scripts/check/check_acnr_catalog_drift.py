#!/usr/bin/env python3
"""
check_acnr_catalog_drift.py — ACNR 目录报告结构守卫（acnr-foundation-defect-closure T09，design §7.1 / R2-N2）

校验 catalog_report.json：
1. 四组 blocking / acknowledged / deprecated / info 都是 `{count, items}`，`count == len(items)`，summary 计数一致
   （判据与生成器同一实现：`app.services.acnr.catalog_report_buckets.bucket_problems`）；
2. blocking 为 0（生成器只在门禁 0 违规时写出，已提交报告恒为 0）。

旧版的 gap_count 守恒与「generated_at 不超过 7 天」陈旧度判据已删除：前者随旧字段一起删除，后者与「内容不变则
不重写、时间戳沿用」的幂等规则冲突（内容不变时报告必然变旧）。目录与生成器重算是否一致由
`backend/scripts/acnr/generate_catalog.py --check` 判定。

Usage:
    python check_acnr_catalog_drift.py             # 报告模式（退出码恒 0）
    python check_acnr_catalog_drift.py --strict    # 严格模式（有违规退出码 1）
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_ROOT = SCRIPT_DIR.parent.parent
REPORT_PATH = BACKEND_ROOT / "data" / "acnr" / "catalog_report.json"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.acnr.catalog_report_buckets import BUCKETS, bucket_problems  # noqa: E402


def load_report(path: Path) -> dict:
    if not path.exists():
        print(f"[ERROR] catalog_report.json 不存在：{path}", file=sys.stderr)
        sys.exit(1)
    return json.loads(path.read_text(encoding="utf-8"))


def check_report(report: dict) -> list[str]:
    """结构自检 + blocking 为 0。"""
    errors = bucket_problems(report)
    blocking = report.get("blocking")
    if isinstance(blocking, dict) and blocking.get("count"):
        errors.append(f"blocking={blocking.get('count')}（已提交报告必须为 0）：" + "；".join(
            f"{i.get('check')} {i.get('addr_id')} {i.get('detail')}" for i in (blocking.get("items") or [])[:5]))
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ACNR 目录报告结构守卫（四组分组 + blocking 为 0）")
    parser.add_argument("--strict", action="store_true", help="严格模式（有违规则退出码 1）")
    parser.add_argument("--report-path", type=Path, default=REPORT_PATH, help="catalog_report.json 路径")
    args = parser.parse_args(argv)

    report = load_report(args.report_path)
    errors = check_report(report)
    summary = report.get("summary") or {}
    print("[ACNR 报告] " + " / ".join(f"{name} {summary.get(name, '?')}" for name in BUCKETS))
    if errors:
        print(f"[FAIL] {len(errors)} 处问题：")
        for err in errors:
            print(f"  - {err}")
        return 1 if args.strict else 0
    print("[OK] 四组分组结构一致，blocking 为 0")
    return 0


if __name__ == "__main__":
    sys.exit(main())
