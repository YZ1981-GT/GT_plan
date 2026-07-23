"""后端方法学单一真源测试（voucher-sampling-hardening Task 9.3）

权威向量与前端 useSamplingAlgorithms.methodology.spec.ts 逐位一致（前后端一致性契约）：
- reliability_factor(0.95,0)=3.0 / (0.90,0)=2.31
- compute_mus_interval("100000",0.95,"0")="33333.33"
- compute_sample_size("1234567","100000","0",0.95)=38

Validates: Requirements 6.1, 6.2, 6.4, 10.1, 10.8
Properties: Property 13, Property 22
"""

from __future__ import annotations

from app.services.sampling_methodology import (
    ALGO_VERSION,
    build_methodology_snapshot,
    compute_mus_interval,
    compute_sample_size,
    reliability_factor,
)


class TestAuthoritativeVectorsParity:
    def test_reliability_factor_95(self):
        assert reliability_factor(0.95, 0) == 3.0

    def test_reliability_factor_90(self):
        assert reliability_factor(0.90, 0) == 2.31

    def test_mus_interval_vector(self):
        # 与前端 computeMusInterval("100000",0.95,"0") = "33333.33" 一致
        assert compute_mus_interval("100000", 0.95, "0") == "33333.33"

    def test_sample_size_vector(self):
        # 与前端 computeSampleSize("1234567","100000","0",0.95) = 38 一致
        assert compute_sample_size("1234567", "100000", "0", 0.95) == 38

    def test_zero_tolerable_returns_zero_interval(self):
        assert compute_mus_interval("0", 0.95, "0") == "0.00"

    def test_sample_size_monotonic_non_increasing_in_tolerable(self):
        # 可容忍错报增大 → 样本量不增（P18 同源）
        pop = "5000000"
        small = compute_sample_size(pop, "50000", "0", 0.95)
        large = compute_sample_size(pop, "150000", "0", 0.95)
        assert large <= small


class TestMethodologySnapshot:
    def test_mus_with_params_produces_interval(self):
        snap = build_methodology_snapshot(
            sampling_method="mus",
            population_amount="1234567",
            confidence_level=0.95,
            tolerable_misstatement="100000",
            expected_misstatement="0",
        )
        assert snap["algo_version"] == ALGO_VERSION
        assert snap["sampling_interval"] == "33333.33"
        assert snap["suggested_sample_size"] == 38
        assert snap["reliability_factor"] == 3.0

    def test_non_mus_no_interval(self):
        snap = build_methodology_snapshot(
            sampling_method="random",
            population_amount="1000000",
            confidence_level=0.95,
            tolerable_misstatement="100000",
            expected_misstatement="0",
        )
        assert snap["sampling_interval"] is None
        assert snap["suggested_sample_size"] is None
        assert snap["algo_version"] == ALGO_VERSION

    def test_mus_missing_params_no_interval(self):
        snap = build_methodology_snapshot(
            sampling_method="mus",
            population_amount="1000000",
            confidence_level=None,
            tolerable_misstatement=None,
            expected_misstatement=None,
        )
        assert snap["sampling_interval"] is None
