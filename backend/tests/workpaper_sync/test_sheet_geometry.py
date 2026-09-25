# -*- coding: utf-8 -*-
"""框架层 `sheet_geometry` 纯函数自测（Task 5）。

spec: d1-sync-row-table-engine-and-d1-coverage · Requirements 1.4 / 4.2

覆盖：
  1. col_index 已知点（A/Z/AA/AM/AB）。
  2. snake 已知点（camelCase / nested 前缀 / 已是 snake）。
  3. 与四家 provider 原实现逐字节等价（对 provider 真实用到的键穷举比对）。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

from app.services.workpaper_sync.sheet_geometry import col_index, snake


def test_col_index_known_points() -> None:
    assert col_index("A") == 1
    assert col_index("Z") == 26
    assert col_index("AA") == 27
    assert col_index("AB") == 28
    assert col_index("AM") == 39
    assert col_index("AA") == col_index("A") * 26 + col_index("A")


def test_snake_known_points() -> None:
    assert snake("priorAudited") == "prior_audited"
    assert snake("agingPrior") == "aging_prior"
    assert snake("customerName") == "customer_name"
    assert snake("remark") == "remark"  # 已是小写，原样


def test_equivalent_to_provider_originals() -> None:
    """对 D2/D3/D6/D7 真实用到的 json 前缀键，本模块输出 ≡ 原 _snake/_col_index。"""
    # 用一组覆盖大小写/多段/纯小写的样本穷举
    samples_snake = [
        "agingPrior", "agingAudited", "agePrior1y", "customerName", "priorUnadjusted",
        "endAudited", "isConfirmed", "postPeriodSettlement", "remark", "companyCode",
    ]
    # 复刻原实现（四家逐字相同）做对照
    def _orig_snake(camel: str) -> str:
        out: list[str] = []
        for ch in camel:
            if ch.isupper():
                out.append("_")
                out.append(ch.lower())
            else:
                out.append(ch)
        return "".join(out)

    def _orig_col(letters: str) -> int:
        idx = 0
        for ch in letters:
            idx = idx * 26 + (ord(ch) - 64)
        return idx

    for s in samples_snake:
        assert snake(s) == _orig_snake(s)
    for col in ["A", "B", "H", "O", "Q", "T", "AA", "AB", "AM", "AN", "AZ", "BA"]:
        assert col_index(col) == _orig_col(col)
