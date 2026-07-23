"""WpSamplingEngine 可复现性测试（voucher-sampling-hardening P0-2）

WpSamplingEngine 此前三个抽样方法用裸 `random`，无 seed → 抽样结果不可复现，
违反"抽样须可复核/重跑"合规要求。P0-2 注入 rng=random.Random(seed)。
本文件验证：相同 seed → 相同选中集合；不同 seed → 通常不同；execute_sampling 回传 seed。

Validates: Requirements 9.x（可复现留痕）
"""

from __future__ import annotations

import random

from app.services.wp_sampling_engine import WpSamplingEngine


def _entries(n: int) -> list[dict]:
    return [
        {
            "voucher_no": f"V{i:04d}",
            "voucher_date": "2025-01-01",
            "account_code": "1122",
            "account_name": "应收账款",
            "debit_amount": float((i % 50 + 1) * 100),
            "credit_amount": 0.0,
            "amount": float((i % 50 + 1) * 100),
            "summary": "",
        }
        for i in range(n)
    ]


class TestRandomSampleReproducible:
    def test_same_seed_same_selection(self):
        eng = WpSamplingEngine()
        entries = _entries(100)
        s1 = eng._random_sample(entries, 10, random.Random(42))
        s2 = eng._random_sample(entries, 10, random.Random(42))
        assert [e["voucher_no"] for e in s1] == [e["voucher_no"] for e in s2]

    def test_different_seed_usually_differs(self):
        eng = WpSamplingEngine()
        entries = _entries(100)
        s1 = eng._random_sample(entries, 10, random.Random(1))
        s2 = eng._random_sample(entries, 10, random.Random(999))
        # 100 选 10，两个不同 seed 完全相同的概率极低
        assert [e["voucher_no"] for e in s1] != [e["voucher_no"] for e in s2]


class TestStratifiedSampleReproducible:
    def test_same_seed_same_selection(self):
        eng = WpSamplingEngine()
        entries = _entries(60)
        s1 = eng._stratified_sample(entries, 12, random.Random(7))
        s2 = eng._stratified_sample(entries, 12, random.Random(7))
        assert [e["voucher_no"] for e in s1] == [e["voucher_no"] for e in s2]


class TestMusSampleReproducible:
    def test_same_seed_same_start(self):
        eng = WpSamplingEngine()
        entries = _entries(100)
        s1 = eng._mus_sample(entries, 5000.0, 8, random.Random(3))
        s2 = eng._mus_sample(entries, 5000.0, 8, random.Random(3))
        assert [e["voucher_no"] for e in s1] == [e["voucher_no"] for e in s2]


class TestBackwardCompatible:
    def test_no_rng_falls_back_to_module_random(self):
        # 不传 rng → 回退模块 random（不崩，边界正确）
        eng = WpSamplingEngine()
        entries = _entries(10)
        assert len(eng._random_sample(entries, 5)) == 5
        assert len(eng._random_sample(entries, 100)) == 10  # 不超总体
        assert 0 < len(eng._stratified_sample(entries, 9)) <= 9
        assert len(eng._mus_sample(entries, 5000.0, 8)) <= 8


class TestExecuteSamplingReturnsSeed:
    def _run(self, coro):
        import asyncio

        return asyncio.get_event_loop().run_until_complete(coro)

    def test_returns_given_seed(self, monkeypatch):
        from uuid import uuid4

        eng = WpSamplingEngine()

        async def _fake_fetch(*a, **k):
            return _entries(50)

        monkeypatch.setattr(eng, "_fetch_candidates", _fake_fetch)
        res = self._run(
            eng.execute_sampling(None, uuid4(), 2025, ["1122"], method="random",
                                 sample_size=10, random_seed=42)
        )
        assert res["random_seed"] == 42
        assert res["sample_size"] == 10
        # 相同 seed 再抽一次 → 选中集合一致（可复现）
        res2 = self._run(
            eng.execute_sampling(None, uuid4(), 2025, ["1122"], method="random",
                                 sample_size=10, random_seed=42)
        )
        assert [e["voucher_no"] for e in res["entries"]] == [
            e["voucher_no"] for e in res2["entries"]
        ]

    def test_auto_seed_when_none(self, monkeypatch):
        from uuid import uuid4

        eng = WpSamplingEngine()

        async def _fake_fetch(*a, **k):
            return _entries(50)

        monkeypatch.setattr(eng, "_fetch_candidates", _fake_fetch)
        res = self._run(
            eng.execute_sampling(None, uuid4(), 2025, ["1122"], method="random",
                                 sample_size=5)
        )
        # 未传 seed → 自动生成并回传（非 None，可用于复现）
        assert isinstance(res["random_seed"], int)
        assert res["random_seed"] > 0

    def test_empty_population_returns_seed(self, monkeypatch):
        from uuid import uuid4

        eng = WpSamplingEngine()

        async def _fake_fetch(*a, **k):
            return []

        monkeypatch.setattr(eng, "_fetch_candidates", _fake_fetch)
        res = self._run(
            eng.execute_sampling(None, uuid4(), 2025, ["1122"], method="random",
                                 sample_size=5, random_seed=123)
        )
        assert res["random_seed"] == 123
        assert res["sample_size"] == 0
        assert res["entries"] == []
