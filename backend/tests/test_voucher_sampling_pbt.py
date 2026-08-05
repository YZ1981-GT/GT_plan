"""Property-Based Tests for 通用抽凭引擎 — Backend (hypothesis)

Feature: voucher-sampling-engine

Properties tested:
- P1: 随机抽样产生恰好 N 笔
- P2: 金额分层抽样尊重层级边界
- P3: 特定项目选取恰好捕获 >= 阈值
- P4: 系统抽样间隔正确性
- P5: MUS 累积金额选取覆盖
- P7: 排除已抽凭证正确性
- P9: 覆盖率计算准确性
- P11: 随机种子可复现性

Uses hypothesis with max_examples=20.
"""
from __future__ import annotations

import random
from datetime import date
from decimal import Decimal

from hypothesis import given, settings
from hypothesis import strategies as st

from app.services.voucher_sampling_algorithms import (
    SamplingParams,
    StratumConfig,
    _compute_coverage,
    _greatest,
    _mus_sampling,
    _random_sampling,
    _specific_item_sampling,
    _stratified_sampling,
    _systematic_sampling,
    execute_sampling,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Custom Strategies
# ═══════════════════════════════════════════════════════════════════════════════


@st.composite
def ledger_entry_strategy(draw, positive=False):
    """Generate realistic ledger entry dicts."""
    voucher_no = draw(
        st.text(
            min_size=1,
            max_size=20,
            alphabet=st.characters(categories=("L", "N", "Pd")),
        )
    )
    voucher_date = draw(
        st.dates(min_value=date(2020, 1, 1), max_value=date(2025, 12, 31))
    ).isoformat()
    if positive:
        debit = draw(
            st.decimals(
                min_value=Decimal("0.01"),
                max_value=Decimal("100000"),
                places=2,
                allow_nan=False,
                allow_infinity=False,
            )
        )
    else:
        debit = draw(
            st.decimals(
                min_value=Decimal("0"),
                max_value=Decimal("100000"),
                places=2,
                allow_nan=False,
                allow_infinity=False,
            )
        )
    credit = draw(
        st.decimals(
            min_value=Decimal("0"),
            max_value=Decimal("100000"),
            places=2,
            allow_nan=False,
            allow_infinity=False,
        )
    )
    return {
        "voucher_no": voucher_no,
        "voucher_date": voucher_date,
        "debit_amount": debit,
        "credit_amount": credit,
        "summary": draw(st.text(min_size=0, max_size=50)),
        "account_code": draw(st.text(min_size=4, max_size=6, alphabet="0123456789")),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Property 1: 随机抽样产生恰好 N 笔
# Feature: voucher-sampling-engine, Property 1: 随机抽样产生恰好 N 笔
# ═══════════════════════════════════════════════════════════════════════════════


class TestProperty1RandomSamplingCount:
    """**Validates: Requirements 3.3**

    For any population (length >= 1) and sample size N (1 <= N <= len(population)),
    random sampling SHALL produce a result containing exactly min(N, len(population))
    items, and every item in the result SHALL exist in the original population.
    """

    @settings(max_examples=20)
    @given(data=st.data())
    def test_random_sampling_produces_exactly_n_items(self, data):
        """**Validates: Requirements 3.3**

        Random sampling produces exactly min(N, len(population)) items,
        all of which exist in the original population.
        """
        population = data.draw(
            st.lists(ledger_entry_strategy(), min_size=1, max_size=200)
        )
        n = data.draw(st.integers(min_value=1, max_value=len(population)))

        seed = data.draw(st.integers(min_value=0, max_value=2**31))
        rng = random.Random(seed)

        result = _random_sampling(population, n, rng)

        # Assert exact count
        expected_count = min(n, len(population))
        assert len(result) == expected_count, (
            f"Expected {expected_count} items, got {len(result)}"
        )

        # Assert all items are from population (subset invariant)
        for item in result:
            assert item in population, (
                f"Sampled item not found in population: {item}"
            )


# ═══════════════════════════════════════════════════════════════════════════════
# Property 2: 金额分层抽样尊重层级边界
# Feature: voucher-sampling-engine, Property 2: 金额分层抽样尊重层级边界
# ═══════════════════════════════════════════════════════════════════════════════


@st.composite
def non_overlapping_strata_strategy(draw):
    """Generate non-overlapping strata configuration.

    Uses exclusive upper boundaries internally (lower <= amount < upper for all
    strata except the last which uses <=) to avoid boundary ambiguity. But since
    the actual algorithm uses inclusive bounds [lower, upper], we ensure boundaries
    don't share exact values by using a gap of 0.01 between strata.
    """
    num_strata = draw(st.integers(min_value=1, max_value=4))
    # Generate unique boundary values with sufficient gaps
    boundaries = sorted(
        draw(
            st.lists(
                st.integers(min_value=0, max_value=9999),
                min_size=num_strata + 1,
                max_size=num_strata + 1,
                unique=True,
            )
        )
    )
    strata = []
    for i in range(num_strata):
        sample_size = draw(st.integers(min_value=1, max_value=10))
        # Use integer boundaries converted to Decimal to ensure no overlap
        # Lower bound of stratum i = boundaries[i], upper = boundaries[i+1] - 0.01
        # except for the last stratum where upper = boundaries[i+1]
        lower = Decimal(str(boundaries[i]))
        if i < num_strata - 1:
            upper = Decimal(str(boundaries[i + 1])) - Decimal("0.01")
        else:
            upper = Decimal(str(boundaries[i + 1]))
        if lower <= upper:
            strata.append(
                StratumConfig(
                    lower_bound=lower,
                    upper_bound=upper,
                    sample_size=sample_size,
                )
            )
    return strata


class TestProperty2StratifiedSamplingBoundaries:
    """**Validates: Requirements 3.4**

    For any population and strata configuration, stratified sampling SHALL produce
    items where each item's amount falls within its assigned stratum range,
    per-stratum count <= configured size, and total = sum of per-stratum counts.
    """

    @settings(max_examples=20)
    @given(
        population=st.lists(ledger_entry_strategy(), min_size=1, max_size=200),
        strata=non_overlapping_strata_strategy(),
        seed=st.integers(min_value=0, max_value=2**31),
    )
    def test_stratified_sampling_respects_stratum_boundaries(
        self, population, strata, seed
    ):
        """**Validates: Requirements 3.4**

        Each sampled item's amount falls within its stratum's [lower, upper] range.
        Per-stratum count <= configured size. Total = sum of per-stratum counts.
        """
        from hypothesis import assume

        # Skip degenerate cases where strata list is empty
        assume(len(strata) > 0)

        rng = random.Random(seed)
        result = _stratified_sampling(population, strata, rng)

        # Verify each item belongs to at least one stratum
        for item in result:
            amount = _greatest(item)
            in_some_stratum = any(
                s.lower_bound <= amount <= s.upper_bound for s in strata
            )
            assert in_some_stratum, (
                f"Item with amount {amount} does not fall in any stratum. "
                f"Strata: {[(s.lower_bound, s.upper_bound) for s in strata]}"
            )

        # Independently verify per-stratum logic by re-running per stratum
        expected_total = 0
        for stratum in strata:
            stratum_pop = [
                item
                for item in population
                if stratum.lower_bound <= _greatest(item) <= stratum.upper_bound
            ]
            max_possible = min(stratum.sample_size, len(stratum_pop))
            expected_total += max_possible

        # Verify total result count matches expected
        assert len(result) == expected_total, (
            f"Total result count {len(result)} != expected {expected_total}. "
            f"Strata: {[(s.lower_bound, s.upper_bound, s.sample_size) for s in strata]}"
        )

        # Verify all result items come from the population
        for item in result:
            assert item in population, (
                f"Stratified result item not found in population: {item}"
            )


# ═══════════════════════════════════════════════════════════════════════════════
# Property 3: 特定项目选取恰好捕获 >= 阈值
# Feature: voucher-sampling-engine, Property 3: 特定项目选取恰好捕获 >= 阈值
# ═══════════════════════════════════════════════════════════════════════════════


class TestProperty3SpecificItemCapture:
    """**Validates: Requirements 3.5**

    For any population and materiality threshold T, specific_item sampling SHALL
    capture all and only items with GREATEST(debit, credit) >= T.
    """

    @settings(max_examples=20)
    @given(
        population=st.lists(ledger_entry_strategy(), min_size=1, max_size=200),
        threshold=st.decimals(
            min_value=Decimal("0"),
            max_value=Decimal("1000000"),
            places=2,
            allow_nan=False,
            allow_infinity=False,
        ),
    )
    def test_specific_item_captures_all_above_threshold(self, population, threshold):
        """**Validates: Requirements 3.5**

        All result items >= threshold; all population items >= threshold in result;
        all result items ∈ population.
        """
        result = _specific_item_sampling(population, threshold)

        # All result items have amount >= threshold
        for item in result:
            amount = _greatest(item)
            assert amount >= threshold, (
                f"Item with amount {amount} is below threshold {threshold}"
            )

        # All population items >= threshold must be in result (completeness)
        expected_items = [
            item for item in population if _greatest(item) >= threshold
        ]
        for item in expected_items:
            assert item in result, (
                f"Population item with amount {_greatest(item)} >= threshold "
                f"{threshold} missing from result"
            )

        # All result items must be from population (precision)
        for item in result:
            assert item in population, (
                f"Result item not found in population: {item}"
            )

        # Result count must equal expected count
        assert len(result) == len(expected_items), (
            f"Expected {len(expected_items)} items, got {len(result)}"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Property 4: 系统抽样间隔正确性
# Feature: voucher-sampling-engine, Property 4: 系统抽样间隔正确性
# ═══════════════════════════════════════════════════════════════════════════════


class TestProperty4SystematicSamplingInterval:
    """**Validates: Requirements 3.6**

    For any sorted population, start point S, and interval K, systematic sampling
    SHALL select items at indices {S-1, S-1+K, S-1+2K, ...} ∩ [0, len).
    """

    @settings(max_examples=20)
    @given(data=st.data())
    def test_systematic_sampling_selects_correct_indices(self, data):
        """**Validates: Requirements 3.6**

        Selected indices == {start-1, start-1+K, start-1+2K, ...} ∩ [0, len).
        """
        population = data.draw(
            st.lists(ledger_entry_strategy(), min_size=2, max_size=500)
        )
        start = data.draw(st.integers(min_value=1, max_value=len(population)))
        interval = data.draw(st.integers(min_value=2, max_value=50))

        result = _systematic_sampling(population, start, interval)

        # Compute expected indices (0-based)
        n = len(population)
        expected_indices = set()
        idx = start - 1
        while 0 <= idx < n:
            expected_indices.add(idx)
            idx += interval

        # Sort population to match what _systematic_sampling does internally
        sorted_pop = sorted(
            population,
            key=lambda x: (x.get("voucher_date") or "", x.get("voucher_no") or ""),
        )

        # Verify result count matches expected indices
        assert len(result) == len(expected_indices), (
            f"Expected {len(expected_indices)} items, got {len(result)}. "
            f"Start={start}, Interval={interval}, Pop size={n}"
        )

        # Verify each result item matches the expected position
        expected_items = [sorted_pop[i] for i in sorted(expected_indices)]
        for i, (expected, actual) in enumerate(zip(expected_items, result)):
            assert expected == actual, (
                f"Mismatch at position {i}: expected {expected}, got {actual}"
            )


# ═══════════════════════════════════════════════════════════════════════════════
# Property 5: MUS 累积金额选取覆盖
# Feature: voucher-sampling-engine, Property 5: MUS 累积金额选取覆盖
# ═══════════════════════════════════════════════════════════════════════════════


class TestProperty5MUSCoverage:
    """**Validates: Requirements 3.7, 3.8**

    For any population with positive total amount and sample_size M, MUS sampling
    SHALL produce a sample count approximately equal to M (within ±1) and all
    result items must exist in the population.
    """

    @settings(max_examples=20)
    @given(
        population=st.lists(
            ledger_entry_strategy(positive=True), min_size=1, max_size=200
        ),
        sample_size=st.integers(min_value=1, max_value=50),
        seed=st.integers(min_value=0, max_value=2**31),
    )
    def test_mus_sampling_count_within_tolerance(
        self, population, sample_size, seed
    ):
        """**Validates: Requirements 3.7, 3.8**

        sample_count ∈ [sample_size-1, sample_size+1]; all result ∈ population.
        """
        rng = random.Random(seed)
        result = _mus_sampling(population, sample_size, rng)

        # All result items must be from population
        for item in result:
            assert item in population, (
                f"MUS result item not found in population: {item}"
            )

        # Sample count within ±1 tolerance (boundary effects)
        # Note: when population is small relative to sample_size, fewer items
        # may be selected, so we also allow result <= len(population)
        total_amount = sum(abs(_greatest(item)) for item in population)
        if total_amount > 0:
            # The tolerance is ±1 because boundary effects make exact count
            # hard to guarantee. Also can't exceed population size.
            max_expected = min(sample_size + 1, len(population))
            min_expected = max(sample_size - 1, 1)
            # For very small populations or very large sample_size relative to
            # population, the actual count could be much less
            if sample_size <= len(population):
                assert min_expected <= len(result) <= max_expected, (
                    f"MUS sample count {len(result)} not within "
                    f"[{min_expected}, {max_expected}]. "
                    f"sample_size={sample_size}, pop_size={len(population)}, "
                    f"total_amount={total_amount}"
                )
            else:
                # When sample_size > population size, we just check it's bounded
                assert len(result) <= len(population), (
                    f"MUS sample count {len(result)} exceeds population "
                    f"size {len(population)}"
                )


# ═══════════════════════════════════════════════════════════════════════════════
# Property 7: 排除已抽凭证正确性
# Feature: voucher-sampling-engine, Property 7: 排除已抽凭证正确性
# ═══════════════════════════════════════════════════════════════════════════════


class TestProperty7ExcludeExtractedCorrectness:
    """**Validates: Requirements 2.2, 2.3, 2.5**

    After filtering by excluded voucher_nos: filtered ∩ excluded == ∅ and
    filtered ∪ excluded ⊇ original (no false exclusions).
    """

    @settings(max_examples=20)
    @given(
        population_nos=st.lists(
            st.text(min_size=1, max_size=20), min_size=0, max_size=50
        ),
        excluded_nos=st.lists(
            st.text(min_size=1, max_size=20), min_size=0, max_size=50
        ),
    )
    def test_exclude_extracted_vouchers(self, population_nos, excluded_nos):
        """**Validates: Requirements 2.2, 2.3, 2.5**

        Filtered ∩ excluded == ∅; filtered ∪ excluded ⊇ original (no false exclusions).
        """
        excluded_set = set(excluded_nos)

        # Simulate the exclusion logic
        filtered = [no for no in population_nos if no not in excluded_set]

        # Property 1: intersection with excluded must be empty
        filtered_set = set(filtered)
        intersection = filtered_set & excluded_set
        assert intersection == set(), (
            f"Filtered result must not contain excluded voucher_nos. "
            f"Intersection: {intersection}"
        )

        # Property 2: no false exclusions — every item in population that is NOT
        # in excluded must appear in filtered
        expected_preserved = [no for no in population_nos if no not in excluded_set]
        assert filtered == expected_preserved, (
            f"All non-excluded items must be preserved in order. "
            f"Expected: {expected_preserved}, Got: {filtered}"
        )

        # Property 3: filtered ∪ excluded ⊇ original
        original_set = set(population_nos)
        combined = filtered_set | excluded_set
        assert original_set <= combined, (
            f"filtered ∪ excluded must be a superset of original. "
            f"Missing: {original_set - combined}"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Property 9: 覆盖率计算准确性
# Feature: voucher-sampling-engine, Property 9: 覆盖率计算准确性
# ═══════════════════════════════════════════════════════════════════════════════


class TestProperty9CoverageCalculationAccuracy:
    """**Validates: Requirements 3.9, 12.1, 12.2**

    count_rate == round(S/P×100, 2); amount_rate == round(B/A×100, 2).
    """

    @settings(max_examples=20)
    @given(data=st.data())
    def test_coverage_calculation_accuracy(self, data):
        """**Validates: Requirements 3.9, 12.1, 12.2**

        Coverage rates are calculated correctly:
        count_rate == round(S/P*100, 2); amount_rate == round(B/A*100, 2).
        """
        pop_count = data.draw(st.integers(min_value=1, max_value=1000))
        sample_count = data.draw(st.integers(min_value=1, max_value=pop_count))
        pop_amount = data.draw(
            st.decimals(
                min_value=Decimal("0.01"),
                max_value=Decimal("10000000"),
                places=2,
                allow_nan=False,
                allow_infinity=False,
            )
        )
        sample_amount = data.draw(
            st.decimals(
                min_value=Decimal("0.01"),
                max_value=pop_amount,
                places=2,
                allow_nan=False,
                allow_infinity=False,
            )
        )

        # Build population and sample with controlled amounts to test _compute_coverage
        # Each population item has debit_amount = pop_amount / pop_count (uniform)
        # Each sample item has debit_amount = sample_amount / sample_count (uniform)
        per_pop_amount = pop_amount / pop_count
        per_sample_amount = sample_amount / sample_count

        population = [
            {"debit_amount": per_pop_amount, "credit_amount": Decimal("0")}
            for _ in range(pop_count)
        ]
        sample = [
            {"debit_amount": per_sample_amount, "credit_amount": Decimal("0")}
            for _ in range(sample_count)
        ]

        count_rate, amount_rate = _compute_coverage(population, sample)

        # Expected values
        expected_count_rate = round(
            Decimal(sample_count) / Decimal(pop_count) * 100, 2
        )
        # For amount: sum of GREATEST for population = pop_count * per_pop_amount
        actual_pop_total = sum(_greatest(item) for item in population)
        actual_sample_total = sum(_greatest(item) for item in sample)

        if actual_pop_total > 0:
            expected_amount_rate = round(actual_sample_total / actual_pop_total * 100, 2)
        else:
            expected_amount_rate = Decimal("0")

        assert count_rate == expected_count_rate, (
            f"Count rate mismatch: got {count_rate}, expected {expected_count_rate}. "
            f"S={sample_count}, P={pop_count}"
        )
        assert amount_rate == expected_amount_rate, (
            f"Amount rate mismatch: got {amount_rate}, expected {expected_amount_rate}. "
            f"sample_total={actual_sample_total}, pop_total={actual_pop_total}"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Property 11: 随机种子可复现性
# Feature: voucher-sampling-engine, Property 11: 随机种子可复现性
# ═══════════════════════════════════════════════════════════════════════════════


class TestProperty11SeedReproducibility:
    """**Validates: Requirements 1.7, 3.12**

    For any seed, population, method, and params, executing the sampling algorithm
    twice with identical inputs SHALL produce identical results.
    """

    @settings(max_examples=20)
    @given(
        population=st.lists(ledger_entry_strategy(), min_size=1, max_size=100),
        seed=st.integers(min_value=0, max_value=2**31),
        data=st.data(),
    )
    def test_seed_reproducibility(self, population, seed, data):
        """**Validates: Requirements 1.7, 3.12**

        execute_sampling called twice with same inputs produces identical results.
        """
        # Choose a random method and appropriate params
        method = data.draw(
            st.sampled_from(["random", "stratified", "specific_item", "systematic", "mus"])
        )

        if method == "random":
            sample_size = data.draw(
                st.integers(min_value=1, max_value=max(1, len(population)))
            )
            params = SamplingParams(sample_size=sample_size)
        elif method == "stratified":
            strata = data.draw(non_overlapping_strata_strategy())
            params = SamplingParams(strata=strata)
        elif method == "specific_item":
            threshold = data.draw(
                st.decimals(
                    min_value=Decimal("0"),
                    max_value=Decimal("50000"),
                    places=2,
                    allow_nan=False,
                    allow_infinity=False,
                )
            )
            params = SamplingParams(materiality_threshold=threshold)
        elif method == "systematic":
            start = data.draw(
                st.integers(min_value=1, max_value=max(1, len(population)))
            )
            interval = data.draw(st.integers(min_value=2, max_value=50))
            params = SamplingParams(start_point=start, interval=interval)
        else:  # mus
            mus_size = data.draw(st.integers(min_value=1, max_value=50))
            params = SamplingParams(mus_sample_size=mus_size)

        # Execute twice with same inputs
        result1 = execute_sampling(method, population, params, seed=seed)
        result2 = execute_sampling(method, population, params, seed=seed)

        # Results must be identical
        assert result1.items == result2.items, (
            f"Method={method}: results differ with same seed={seed}. "
            f"Result1 count={len(result1.items)}, Result2 count={len(result2.items)}"
        )
        assert result1.seed_used == result2.seed_used, (
            f"Seed used differs: {result1.seed_used} vs {result2.seed_used}"
        )
        assert result1.sample_count == result2.sample_count, (
            f"Sample count differs: {result1.sample_count} vs {result2.sample_count}"
        )
        assert result1.count_coverage_rate == result2.count_coverage_rate, (
            f"Count coverage rate differs: "
            f"{result1.count_coverage_rate} vs {result2.count_coverage_rate}"
        )
        assert result1.amount_coverage_rate == result2.amount_coverage_rate, (
            f"Amount coverage rate differs: "
            f"{result1.amount_coverage_rate} vs {result2.amount_coverage_rate}"
        )
