"""全量抽样框选择逻辑测试（voucher-sampling-hardening Task 3.4）

验证两阶段全量框的算法核心：当总体 > 内存上限时，endpoint 在**全量单位**（阶段 A 最小
投影合成的 synthetic_pop）上跑 execute_sampling，使超出前 10000 的单位仍可被抽中。
这是消除"仅从前 N 条抽样"选择偏差的关键保证。

DB plumbing（locate_sampling_units/fetch_by_unit_ids）由 test_ledger_sampling_full_frame
（构造）+ Playwright（Task 17，>1万行项目）覆盖。

Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.6
Properties: Property 1, Property 3, Property 4
"""

from __future__ import annotations

from decimal import Decimal

from app.services.voucher_sampling_algorithms import (
    SamplingParams,
    execute_sampling,
)


def _synthetic_units(n: int) -> list[dict]:
    """复刻 endpoint 两阶段路径的 synthetic_pop 构造（debit=单位代表金额 + _unit_id）。"""
    return [
        {
            "debit_amount": str(Decimal(100) * (i + 1)),
            "credit_amount": None,
            "voucher_date": f"2025-{((i // 800) % 12) + 1:02d}-{(i % 28) + 1:02d}",
            "voucher_no": f"V-{i:06d}",
            "_unit_id": f"id-{i:06d}",
        }
        for i in range(n)
    ]


def _idx_of(unit_id: str) -> int:
    return int(unit_id.split("-")[1])


class TestFullFrameSelection:
    def test_systematic_reaches_units_beyond_10000(self):
        # P1：12000 单位，系统抽样 interval=1000 → 选中 idx 0,1000,...,11000
        # 旧路径（population 截断到 10000）永远抽不到 idx>10000 的单位。
        pop = _synthetic_units(12000)
        r = execute_sampling(
            "systematic", pop, SamplingParams(start_point=1, interval=1000)
        )
        indices = [_idx_of(it["_unit_id"]) for it in r.items]
        assert max(indices) >= 11000
        assert any(i > 10000 for i in indices)

    def test_random_can_reach_beyond_10000(self):
        # P1：随机抽样在全量 12000 上，样本量足够大时应能触达 >10000 区间
        pop = _synthetic_units(12000)
        r = execute_sampling("random", pop, SamplingParams(sample_size=500), seed=123)
        indices = [_idx_of(it["_unit_id"]) for it in r.items]
        assert any(i > 10000 for i in indices)

    def test_mus_spans_full_population(self):
        # P1：MUS 在全量上，末段大额单位可被选中（累积金额法覆盖全体）
        pop = _synthetic_units(12000)
        r = execute_sampling("mus", pop, SamplingParams(mus_sample_size=200), seed=7)
        indices = [_idx_of(it["_unit_id"]) for it in r.items]
        assert max(indices) > 10000

    def test_specific_item_high_value_regardless_of_position(self):
        # P3：高值必选——把一个超大额单位放在 idx 11500，specific_item 阈值下必被选中
        pop = _synthetic_units(12000)
        pop[11500]["debit_amount"] = str(Decimal("99999999"))
        r = execute_sampling(
            "specific_item", pop, SamplingParams(materiality_threshold=Decimal("99999999"))
        )
        indices = [_idx_of(it["_unit_id"]) for it in r.items]
        assert 11500 in indices

    def test_seed_reproducible_full_frame(self):
        # P4：同 seed + 同全量总体 → 同选中单位
        pop = _synthetic_units(12000)
        r1 = execute_sampling("random", pop, SamplingParams(sample_size=100), seed=42)
        r2 = execute_sampling("random", pop, SamplingParams(sample_size=100), seed=42)
        assert [it["_unit_id"] for it in r1.items] == [it["_unit_id"] for it in r2.items]

    def test_unit_id_preserved_through_selection(self):
        # 选中项必须携带 _unit_id 供阶段 B 取回
        pop = _synthetic_units(11000)
        r = execute_sampling("random", pop, SamplingParams(sample_size=50), seed=1)
        assert all(it.get("_unit_id") is not None for it in r.items)
