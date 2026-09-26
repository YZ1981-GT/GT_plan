# -*- coding: utf-8 -*-
"""F2-P11：既有 contract golden digest 零回归。

spec: f2-sync-coverage-four-entry-lanes · Task 5 · Requirements 7.3
Property 11: F2 新增 provider 不得改变既有契约文件的任何字节。

判据：逐文件 sha256(file_bytes) 与基线逐字比对。
"""
from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

CONTRACTS_DIR = _BACKEND / "data" / "workpaper_sync_contracts"

# ── 基线：2026-09-26 现算（Task 5 冻结）──────────────────────────────────
# key = filename, value = sha256 前 16 位（足够唯一，全长见证据文件）
GOLDEN_BASELINE: dict[str, str] = {
    "_example.candidate.json": "4e85a633550b8f60",
    "b60.hour_budget.json": "91beaa2a284fd8d2",
    "d1.notes_receivable_detail.json": "62b589551bd99050",
    "d2.receivable_detail.json": "078b04377a34054f",
    "d3.prepaid_receipts_detail.json": "4f5b71fd73c1c412",
    "d4.revenue_detail.json": "5bd890211ac8f897",
    "d5.receivables_financing_detail.json": "03900069af256db6",
    "d6.contract_assets_detail.json": "a8ba5bf29129728c",
    "d7.contract_liabilities_detail.json": "84b266b5e9efc45f",
    "e1.monetary_fund_detail.json": "4a0cf6c928566c96",
    "f1.prepayment_detail.json": "9ea57f744d34533a",
    "g7.soe_subsidiary_disclosure.json": "3c992e2f31540f14",
    "h1.disposal_check.json": "e7d6c1b75af2d600",
}


class TestF2P11GoldenDigestZeroRegression:
    """既有 13 个契约文件在 F2 开发期间不得被改动。"""

    @pytest.mark.parametrize("filename,expected_prefix", list(GOLDEN_BASELINE.items()))
    def test_contract_file_unchanged(self, filename: str, expected_prefix: str) -> None:
        path = CONTRACTS_DIR / filename
        assert path.is_file(), f"契约文件丢失: {filename}"
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        assert digest.startswith(expected_prefix), (
            f"{filename} 的 digest 变了: {digest[:16]} != {expected_prefix}"
        )

    def test_no_baseline_file_deleted(self) -> None:
        """基线里的文件不得被删除。"""
        for filename in GOLDEN_BASELINE:
            assert (CONTRACTS_DIR / filename).is_file(), f"基线文件 {filename} 被删除"

    def test_baseline_count_is_13(self) -> None:
        """基线包含 13 个文件（含 example.candidate）。"""
        assert len(GOLDEN_BASELINE) == 13
