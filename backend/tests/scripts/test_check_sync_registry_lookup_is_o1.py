# -*- coding: utf-8 -*-
"""`check_sync_registry_lookup_is_o1.py` 基准自测（P7 / D1-P7）。

spec: d1-sync-row-table-engine-and-d1-coverage · Task 4（可离线部分）· Requirements 3.5 / 8.2

覆盖：
  1. dict.get 查表耗时比(max/min) ≤ 容忍因子（O(1) 平坦）。
  2. 线性试探耗时比 > 容忍因子（反证：线性确实随规模上升）。
  3. run() 整体 ok=True。
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
if str(_BACKEND) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(_BACKEND))

_CHECK_PATH = _BACKEND / "scripts" / "check" / "check_sync_registry_lookup_is_o1.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("_check_sync_registry_lookup_is_o1", _CHECK_PATH)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_dict_lookup_is_flat_and_linear_scales() -> None:
    report = _load_module().run()
    assert report["dict_is_flat"], f"dict 查表不平坦：比={report['dict_ratio_max_over_min']}"
    assert report["linear_scales"], f"线性对照未随规模上升（反证不成立）：比={report['linear_ratio_max_over_min']}"
    assert report["ok"]
