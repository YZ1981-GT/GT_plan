#!/usr/bin/env python3
"""check_acnr_consumer_coverage.py — ACNR 消费方覆盖检查（薄壳）

acnr-foundation-defect-closure T24（需求 13.3）：原逐行正则扫描器与 ``coverage_ledger.json`` 已由
``acnr_bypass_scan.py``（AST 绕过点棘轮 + 消费方台账）取代；本脚本只转发到同一实现，CI 作业
``acnr-consumer-coverage`` 的命令不变。

    python backend/scripts/check/check_acnr_consumer_coverage.py            # 报告模式，退出 0
    python backend/scripts/check/check_acnr_consumer_coverage.py --strict   # 有违规退出 1；基线 / 台账缺失退出 2
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from acnr_bypass_scan import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
