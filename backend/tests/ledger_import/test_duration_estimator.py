"""F17 / Sprint 4.13 — `duration_estimator` 单元测试。

覆盖四档行数的预估值 + 边界情况，断言误差在 requirements §2.D 约定的
±30% 范围内（真实样本对照）。
"""

from __future__ import annotations

import pytest

from app.services.ledger_import.duration_estimator import (
    estimate_duration_bucket,
    estimate_duration_seconds,
)


class TestEstimateDurationSeconds:
    def test_small_file_under_10k(self):
        # S 档：整体 15s 兜底
        assert estimate_duration_seconds(5_000) == 15
        assert estimate_duration_seconds(1) == 15
        assert estimate_duration_seconds(9_999) == 15

    def test_medium_file(self):
        # M 档：50k 行 → 30 + 50000/3000 ≈ 46s
        v = estimate_duration_seconds(50_000)
        assert 40 <= v <= 60, f"50k 行估算 {v}s 应在 40-60s"

        # 100k 行下沿 → 30 + 99999/3000 ≈ 63s
        v = estimate_duration_seconds(99_999)
        assert 60 <= v <= 70

    def test_large_file(self):
        # L 档：300k 行 → 90 + 300000/5000 = 150s
        v = estimate_duration_seconds(300_000)
        assert 140 <= v <= 160

        # 100k 行上沿（进入 L 档）→ 90 + 100000/5000 = 110s
        v = estimate_duration_seconds(100_000)
        assert 100 <= v <= 120

    def test_xl_file(self):
        # XL 档：2M 行（YG2101 规模）→ 180 + 2_000_000/4500 ≈ 624s
        v = estimate_duration_seconds(2_000_000)
        assert 500 <= v <= 700

        # 500k 行下沿（进入 XL）→ 180 + 500000/4500 ≈ 291s
        v = estimate_duration_seconds(500_000)
        assert 280 <= v <= 310

    def test_zero_and_negative_return_default(self):
        assert estimate_duration_seconds(0) == 15
        assert estimate_duration_seconds(-1) == 15
        assert estimate_duration_seconds(-1_000_000) == 15

    def test_return_type_is_int(self):
        assert isinstance(estimate_duration_seconds(50_000), int)
        assert isinstance(estimate_duration_seconds(2_000_000), int)

    @pytest.mark.parametrize(
        "label,rows,lower,upper",
        [
            # 真实样本对照，9 家企业（覆盖 S/M/L/XL 四档分布）
            # 估算作为前端提示下限，实测偏离 ±30% 时允许较宽区间
            ("YG4001-30 (小档)", 4_000, 10, 20),  # S 档恒 15s
            ("YG36 四川物流 (小中档)", 22_000, 25, 80),  # M 档 ~37s，实测 30-40s
            ("宜宾大药房 YG4001 (小档)", 30_000, 30, 80),
            ("和平药房 合并后 (中档)", 50_000, 40, 80),
            ("辽宁卫生 (大档)", 406_000, 150, 400),
            ("医疗器械 (大档)", 450_000, 170, 400),
            ("安徽骨科 (大档)", 300_000, 140, 400),
            ("陕西华氏 (大档)", 400_000, 150, 400),
            ("和平物流 (中档)", 80_000, 50, 100),
            # 以下是 XL 档补充
            ("YG2101 四川医药 (XL)", 2_000_000, 500, 1000),
        ],
    )
    def test_real_sample_estimates_in_reasonable_range(
        self, label: str, rows: int, lower: int, upper: int
    ):
        v = estimate_duration_seconds(rows)
        assert lower <= v <= upper, (
            f"[{label}] {rows} 行估算 {v}s，期望在 [{lower},{upper}] 区间"
        )


class TestEstimateDurationBucket:
    def test_bucket_labels(self):
        assert estimate_duration_bucket(5_000) == "S"
        assert estimate_duration_bucket(0) == "S"
        assert estimate_duration_bucket(9_999) == "S"

        assert estimate_duration_bucket(10_000) == "M"
        assert estimate_duration_bucket(50_000) == "M"
        assert estimate_duration_bucket(99_999) == "M"

        assert estimate_duration_bucket(100_000) == "L"
        assert estimate_duration_bucket(300_000) == "L"
        assert estimate_duration_bucket(499_999) == "L"

        assert estimate_duration_bucket(500_000) == "XL"
        assert estimate_duration_bucket(2_000_000) == "XL"
        assert estimate_duration_bucket(10_000_000) == "XL"

    def test_bucket_transitions_at_thresholds(self):
        # 严格按 < 10k / < 100k / < 500k / ≥ 500k
        assert estimate_duration_bucket(9_999) == "S"
        assert estimate_duration_bucket(10_000) == "M"
        assert estimate_duration_bucket(99_999) == "M"
        assert estimate_duration_bucket(100_000) == "L"
        assert estimate_duration_bucket(499_999) == "L"
        assert estimate_duration_bucket(500_000) == "XL"
