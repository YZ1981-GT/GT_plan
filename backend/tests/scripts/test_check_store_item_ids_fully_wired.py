# -*- coding: utf-8 -*-
"""`check_store_item_ids_fully_wired.py` 门禁自测。

spec: d4-html-to-oo-store-contract-alignment · Task 7 · Requirement 3.3

覆盖：
  1. 真 provider 现状通过（ok=True，无漏项、无重复）。
  2. 报告覆盖了关键声明（STORE_ITEM_IDS + 各 *_DICT）。
  3. D4-35 / D4-13 的 item 确实在 all_store_item_ids() 里（缺陷 C 已修的正向断言）。
  4. 变异反证：从 all_store_item_ids() 里剔掉 D4-13 两项，门禁必须报出漏项。
"""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
if str(_BACKEND) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

_CHECK_PATH = _BACKEND / "scripts" / "check" / "check_store_item_ids_fully_wired.py"


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "_check_store_item_ids_fully_wired", _CHECK_PATH
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_real_provider_passes() -> None:
    report = _load_module().run()
    assert report["ok"], f"现状应通过，实得漏项={report['missing']} 重复={report['duplicates']}"
    assert report["missing"] == []
    assert report["duplicates"] == []


def test_report_covers_key_declarations() -> None:
    report = _load_module().run()
    scanned = set(report["declarations_scanned"])
    assert "STORE_ITEM_IDS" in scanned
    assert "STORE_ITEM_ID_D435_DICT" in scanned


def test_d435_and_d413_are_wired() -> None:
    """D4-35 与 D4-13 两条 fixed item 必须在 all_store_item_ids() 里（缺陷 C 正向断言）。"""
    from app.services.workpaper_sync import phase5_d4_revenue_detail as P

    all_ids = set(P.all_store_item_ids())
    assert "D4-35-data" in all_ids
    assert "D4-13-process" in all_ids
    assert "D4-13-conclusion" in all_ids


def test_mutation_missing_item_is_detected(monkeypatch: pytest.MonkeyPatch) -> None:
    """变异反证：让 all_store_item_ids() 漏掉 D4-13 两项，门禁 run() 必须报漏项。"""
    from app.services.workpaper_sync import phase5_d4_revenue_detail as P

    real = P.all_store_item_ids

    def _crippled() -> tuple[str, ...]:
        return tuple(x for x in real() if not str(x).startswith("D4-13-"))

    monkeypatch.setattr(P, "all_store_item_ids", _crippled)
    report = _load_module().run()
    assert not report["ok"], "变异后门禁仍通过 —— 判据空转"
    missing_items = {m["item_id"] for m in report["missing"]}
    assert "D4-13-process" in missing_items
    assert "D4-13-conclusion" in missing_items
