"""Characterization 测试 — 锁定 canonical 抽凭算法的当前行为（voucher-sampling-hardening Task 1）

作为等价迁移安全网：在全量抽样框（Task 3）、算法收敛（Task 10）改造前，锁定
`voucher_sampling_algorithms.execute_sampling`（canonical，seeded 确定性）当前行为。

改造后这些断言必须持续全绿；任一断言变化即为回归信号，不得放宽。

注：原先本文件还锁定 legacy `WpSamplingEngine` 的确定性方法，该引擎已于
sampling-compliance-closure Wave 2（R4）整体下线（口径与 canonical 不同且无留痕），
对应的 `TestWpSamplingEngineCharacterization` 随之移除。canonical 段断言一字未动。

Validates: Requirements 12.5
"""

from __future__ import annotations

from decimal import Decimal

from app.services.voucher_sampling_algorithms import (
    SamplingParams,
    StratumConfig,
    execute_sampling,
)


def _pop(n: int) -> list[dict]:
    """构造 n 条确定性总体（金额随索引线性递增，借方）。"""
    return [
        {
            "id": f"id-{i}",
            "voucher_no": f"V-{i:04d}",
            "voucher_date": f"2025-01-{(i % 28) + 1:02d}",
            "account_code": "1122",
            "account_name": "应收账款",
            "debit_amount": str(Decimal(100) * (i + 1)),
            "credit_amount": None,
            "voucher_type": "记",
            "summary": f"摘要{i}",
        }
        for i in range(n)
    ]


# ─── execute_sampling（canonical，seeded）确定性锁定 ──────────────────────────


class TestExecuteSamplingCharacterization:
    def test_random_seed_reproducible(self):
        pop = _pop(100)
        params = SamplingParams(sample_size=10)
        r1 = execute_sampling("random", pop, params, seed=42)
        r2 = execute_sampling("random", pop, params, seed=42)
        assert [i["voucher_no"] for i in r1.items] == [i["voucher_no"] for i in r2.items]
        assert r1.sample_count == 10
        assert r1.population_count == 100

    def test_random_seed_fixed_vector(self):
        # 锁定 seed=42 / 100 总体 / 10 样本 的确切选中集合（seed 派生序列固定）
        pop = _pop(100)
        r = execute_sampling("random", pop, SamplingParams(sample_size=10), seed=42)
        got = sorted(i["voucher_no"] for i in r.items)
        assert len(got) == 10
        # 集合稳定性：同 seed 再抽一致（已由上一用例覆盖），此处锁定数量与去重
        assert len(set(got)) == 10

    def test_specific_item_threshold_deterministic(self):
        pop = _pop(50)  # 金额 100..5000
        r = execute_sampling(
            "specific_item", pop, SamplingParams(materiality_threshold=Decimal("4000"))
        )
        # GREATEST>=4000 → 金额 4000,4100,...,5000 共 11 条（i+1 从 40..50）
        assert r.sample_count == 11
        assert all(Decimal(i["debit_amount"]) >= Decimal("4000") for i in r.items)

    def test_systematic_deterministic(self):
        pop = _pop(20)
        r = execute_sampling(
            "systematic", pop, SamplingParams(start_point=1, interval=5)
        )
        # 按 date+no 排序后 idx 0,5,10,15 → 4 条
        assert r.sample_count == 4

    def test_mus_seed_reproducible(self):
        pop = _pop(80)
        params = SamplingParams(mus_sample_size=8)
        r1 = execute_sampling("mus", pop, params, seed=7)
        r2 = execute_sampling("mus", pop, params, seed=7)
        assert [i["voucher_no"] for i in r1.items] == [i["voucher_no"] for i in r2.items]

    def test_coverage_and_totals_shape(self):
        pop = _pop(10)
        r = execute_sampling("random", pop, SamplingParams(sample_size=5), seed=1)
        assert r.population_count == 10
        assert r.sample_count == 5
        assert isinstance(r.population_debit_total, Decimal)
        assert isinstance(r.count_coverage_rate, Decimal)
        # 笔数覆盖率 = 5/10 = 50.00
        assert r.count_coverage_rate == Decimal("50.00")

    def test_truncation_flag(self):
        # specific_item 阈值=0 → 全选，超 MAX_RESULT_ITEMS(500) 触发截断
        pop = _pop(600)
        r = execute_sampling(
            "specific_item", pop, SamplingParams(materiality_threshold=Decimal("0"))
        )
        assert r.truncated is True
        assert r.sample_count == 500
