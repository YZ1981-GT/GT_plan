"""Tests for formula_runtime.value_loader — 批量真实值加载器。

覆盖：
- 按 domain 去重加载 (P1)
- 查询数随 domain 数增长，不随引用数线性增长 (P2)
- found/miss/ambiguous 结果分类
- 四表只读 (tb) / workpaper / report / note 批量值
- 空输入安全性

**Validates: Requirements 2, 11 | P1, P2**
"""

from __future__ import annotations

import asyncio
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.services.formula_runtime.contracts import CanonicalFormulaTarget
from app.services.formula_runtime.value_loader import (
    FormulaValueLoader,
    LoadIssue,
    LoadResult,
    DomainReader,
)


# ─── Helpers ─────────────────────────────────────────────────────────────────


class CountingReader:
    """记录 read_batch 调用次数的 mock reader。"""

    def __init__(self, values: dict[str, Decimal | str | None] | None = None):
        self.call_count = 0
        self.last_targets: list[CanonicalFormulaTarget] = []
        self._values = values or {}

    async def read_batch(
        self, targets: list[CanonicalFormulaTarget]
    ) -> dict[str, Decimal | str | None]:
        self.call_count += 1
        self.last_targets = targets
        result: dict[str, Decimal | str | None] = {}
        for t in targets:
            if t.addr_id in self._values:
                result[t.addr_id] = self._values[t.addr_id]
        return result


class ErrorReader:
    """总是抛异常的 reader。"""

    async def read_batch(
        self, targets: list[CanonicalFormulaTarget]
    ) -> dict[str, Decimal | str | None]:
        raise RuntimeError("reader failure")


class AmbiguousReader:
    """模拟 ambiguous 情况的 reader（返回相同 addr_id 多值情况由 loader 外部判断）。"""

    def __init__(self, ambiguous_ids: set[str]):
        self._ambiguous = ambiguous_ids

    async def read_batch(
        self, targets: list[CanonicalFormulaTarget]
    ) -> dict[str, Decimal | str | None]:
        result: dict[str, Decimal | str | None] = {}
        for t in targets:
            if t.addr_id not in self._ambiguous:
                result[t.addr_id] = Decimal("100.00")
        return result


def _make_target(
    domain: str = "tb",
    addr_id: str | None = None,
    project_id: UUID | None = None,
    year: int = 2025,
    locator: dict[str, str] | None = None,
    wp_id: UUID | None = None,
) -> CanonicalFormulaTarget:
    return CanonicalFormulaTarget(
        domain=domain,  # type: ignore[arg-type]
        project_id=project_id or uuid4(),
        year=year,
        addr_id=addr_id or f"{domain}_{uuid4().hex[:8]}",
        locator=locator or {},
        wp_id=wp_id,
    )


# ─── Unit tests: 基础功能 ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_empty_targets_returns_empty_result():
    """空输入应返回空结果，不调用任何 reader。"""
    reader = CountingReader()
    loader = FormulaValueLoader(readers={"tb": reader})
    result = await loader.load_many([])

    assert result.values == {}
    assert result.issues == []
    assert reader.call_count == 0


@pytest.mark.asyncio
async def test_single_domain_single_target_found():
    """单 domain 单 target 找到值。"""
    values = {"addr_1": Decimal("123.45")}
    reader = CountingReader(values)
    loader = FormulaValueLoader(readers={"tb": reader})

    target = _make_target(domain="tb", addr_id="addr_1")
    result = await loader.load_many([target])

    assert result.values == {"addr_1": Decimal("123.45")}
    assert result.issues == []
    assert result.found_count == 1
    assert result.miss_count == 0
    assert reader.call_count == 1


@pytest.mark.asyncio
async def test_single_domain_target_miss():
    """target 在 reader 中未找到应记为 miss。"""
    reader = CountingReader({})  # empty - no values
    loader = FormulaValueLoader(readers={"tb": reader})

    target = _make_target(domain="tb", addr_id="missing_addr")
    result = await loader.load_many([target])

    assert "missing_addr" not in result.values
    assert result.miss_count == 1
    assert result.issues[0].kind == "miss"
    assert result.issues[0].addr_id == "missing_addr"


@pytest.mark.asyncio
async def test_unknown_domain_all_miss():
    """无对应 reader 的 domain 全部记为 miss。"""
    loader = FormulaValueLoader(readers={})  # no readers at all

    target = _make_target(domain="workpaper", addr_id="wp_addr")
    result = await loader.load_many([target])

    assert result.miss_count == 1
    assert "no reader" in result.issues[0].detail


@pytest.mark.asyncio
async def test_reader_exception_records_error():
    """reader 抛异常时记录 error 级别 issue。"""
    loader = FormulaValueLoader(readers={"tb": ErrorReader()})

    target = _make_target(domain="tb", addr_id="err_addr")
    result = await loader.load_many([target])

    assert len(result.issues) == 1
    assert result.issues[0].kind == "error"
    assert "reader failure" in result.issues[0].detail


@pytest.mark.asyncio
async def test_multiple_domains_multiple_results():
    """多 domain 各自返回值。"""
    tb_reader = CountingReader({"tb_1": Decimal("100")})
    wp_reader = CountingReader({"wp_1": Decimal("200")})
    loader = FormulaValueLoader(readers={"tb": tb_reader, "workpaper": wp_reader})

    targets = [
        _make_target(domain="tb", addr_id="tb_1"),
        _make_target(domain="workpaper", addr_id="wp_1"),
    ]
    result = await loader.load_many(targets)

    assert result.values == {"tb_1": Decimal("100"), "wp_1": Decimal("200")}
    assert result.found_count == 2
    assert result.miss_count == 0
    assert tb_reader.call_count == 1
    assert wp_reader.call_count == 1


# ─── Unit tests: 去重与批量性 ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_dedup_same_addr_id_only_queried_once():
    """同一 addr_id 重复出现只查一次。

    **Validates: Requirements 2.3 (P1)**
    """
    values = {"dup_addr": Decimal("999")}
    reader = CountingReader(values)
    loader = FormulaValueLoader(readers={"tb": reader})

    # 同一 addr_id 出现 5 次
    targets = [_make_target(domain="tb", addr_id="dup_addr") for _ in range(5)]
    result = await loader.load_many(targets)

    assert result.values == {"dup_addr": Decimal("999")}
    # reader 只被调用一次（一个 domain 一次）
    assert reader.call_count == 1
    # reader 只收到去重后的 1 个 target
    assert len(reader.last_targets) == 1


@pytest.mark.asyncio
async def test_query_count_grows_with_domain_not_reference_count():
    """查询计数测试：查询数随 domain 数增长，不随引用数线性增长。

    **Validates: Requirements 11, 13.3 (P2)**

    场景：
    - 固定 4 个 domain，每 domain 内引用数从 1 到 100 不等
    - 无论单 domain 引用多少条，reader.read_batch 只调一次
    - 总查询数 = domain 数 = 4
    """
    readers: dict[str, CountingReader] = {}
    for domain in ("tb", "workpaper", "report", "note"):
        readers[domain] = CountingReader(
            {f"{domain}_{i}": Decimal(str(i)) for i in range(100)}
        )

    loader = FormulaValueLoader(readers=readers)  # type: ignore[arg-type]

    # 构建 targets: 4 domains × 各 50 个引用 = 200 targets
    targets: list[CanonicalFormulaTarget] = []
    for domain in ("tb", "workpaper", "report", "note"):
        for i in range(50):
            targets.append(_make_target(domain=domain, addr_id=f"{domain}_{i}"))  # type: ignore[arg-type]

    result = await loader.load_many(targets)

    # 总查询数 = 4（一个 domain 一次）
    total_calls = sum(r.call_count for r in readers.values())
    assert total_calls == 4, f"Expected 4 domain queries, got {total_calls}"

    # 每个 domain reader 只被调用一次
    for domain, reader in readers.items():
        assert reader.call_count == 1, f"{domain} reader called {reader.call_count} times"

    # 验证结果完整性
    assert result.found_count == 200


@pytest.mark.asyncio
async def test_query_count_scales_with_domains_added():
    """增加 domain 数时查询数线性增长（而非引用数增长时）。

    **Validates: Requirements 11, 13.3 (P2)**
    """
    # Scenario A: 1 domain, 100 refs → 1 query
    reader_a = CountingReader({f"a_{i}": Decimal("1") for i in range(100)})
    loader_a = FormulaValueLoader(readers={"tb": reader_a})
    targets_a = [_make_target(domain="tb", addr_id=f"a_{i}") for i in range(100)]
    await loader_a.load_many(targets_a)
    assert reader_a.call_count == 1

    # Scenario B: 3 domains, 100 refs total → 3 queries
    readers_b = {
        "tb": CountingReader({f"tb_{i}": Decimal("1") for i in range(34)}),
        "report": CountingReader({f"rpt_{i}": Decimal("2") for i in range(33)}),
        "note": CountingReader({f"note_{i}": Decimal("3") for i in range(33)}),
    }
    loader_b = FormulaValueLoader(readers=readers_b)  # type: ignore[arg-type]
    targets_b = (
        [_make_target(domain="tb", addr_id=f"tb_{i}") for i in range(34)]
        + [_make_target(domain="report", addr_id=f"rpt_{i}") for i in range(33)]
        + [_make_target(domain="note", addr_id=f"note_{i}") for i in range(33)]
    )
    await loader_b.load_many(targets_b)
    total_b = sum(r.call_count for r in readers_b.values())
    assert total_b == 3

    # 核心断言：3 domains = 3 queries, 不是 100 queries
    assert total_b == 3 * reader_a.call_count


# ─── Unit tests: LoadResult helpers ──────────────────────────────────────────


def test_load_result_counts():
    """LoadResult 的 found/miss/ambiguous count 正确计算。"""
    result = LoadResult(
        values={"a": Decimal("1"), "b": None, "c": Decimal("3")},
        issues=[
            LoadIssue(addr_id="d", kind="miss"),
            LoadIssue(addr_id="e", kind="miss"),
            LoadIssue(addr_id="f", kind="ambiguous"),
        ],
    )
    assert result.found_count == 2  # a, c have non-None values
    assert result.miss_count == 2
    assert result.ambiguous_count == 1


# ─── Property-based tests ────────────────────────────────────────────────────

VALID_DOMAINS = st.sampled_from(["tb", "workpaper", "report", "note"])

st_addr_id = st.text(min_size=1, max_size=30, alphabet=st.characters(categories=("L", "N", "P")))

st_target = st.builds(
    CanonicalFormulaTarget,
    domain=VALID_DOMAINS,
    project_id=st.builds(uuid4),
    year=st.integers(min_value=2000, max_value=2099),
    addr_id=st_addr_id,
    locator=st.just({}),
    wp_id=st.none(),
)


@settings(max_examples=5, deadline=None)
@given(targets=st.lists(st_target, min_size=0, max_size=20))
def test_property_dedup_canonical_resolve(targets: list[CanonicalFormulaTarget]):
    """P1: 对任意含重复等价引用的集合，批量加载每个 canonical 地址至多查询一次。

    **Validates: Requirements 2.1, 2.2, 2.3**
    """
    # 为每个 addr_id 预置一个固定值
    all_values: dict[str, Decimal | str | None] = {
        t.addr_id: Decimal(str(hash(t.addr_id) % 10000)) for t in targets
    }

    readers: dict[str, CountingReader] = {}
    for domain in ("tb", "workpaper", "report", "note"):
        readers[domain] = CountingReader(all_values)

    loader = FormulaValueLoader(readers=readers)  # type: ignore[arg-type]

    result = asyncio.get_event_loop().run_until_complete(loader.load_many(targets))

    # 结果中每个 unique addr_id 只出现一次
    unique_addrs = {t.addr_id for t in targets}
    assert set(result.values.keys()).issubset(unique_addrs)

    # 每个 domain reader 最多被调用一次
    for reader in readers.values():
        assert reader.call_count <= 1


@settings(max_examples=5, deadline=None)
@given(
    n_refs_per_domain=st.integers(min_value=1, max_value=50),
    n_domains=st.integers(min_value=1, max_value=4),
)
def test_property_batch_query_count(n_refs_per_domain: int, n_domains: int):
    """P2: 查询数随 domain 数增长，不随引用数线性增长。

    **Validates: Requirements 11, 13.3**
    """
    domain_names = ["tb", "workpaper", "report", "note"][:n_domains]

    readers: dict[str, CountingReader] = {}
    targets: list[CanonicalFormulaTarget] = []

    for domain in domain_names:
        values = {f"{domain}_{i}": Decimal(str(i)) for i in range(n_refs_per_domain)}
        readers[domain] = CountingReader(values)
        for i in range(n_refs_per_domain):
            targets.append(
                _make_target(domain=domain, addr_id=f"{domain}_{i}")  # type: ignore[arg-type]
            )

    loader = FormulaValueLoader(readers=readers)  # type: ignore[arg-type]
    asyncio.get_event_loop().run_until_complete(loader.load_many(targets))

    # 核心断言：总查询数 = domain 数
    total_calls = sum(r.call_count for r in readers.values())
    assert total_calls == n_domains, (
        f"Expected {n_domains} queries for {n_domains} domains × {n_refs_per_domain} refs, "
        f"got {total_calls}"
    )

    # 每个 domain reader 恰好被调用 1 次
    for domain in domain_names:
        assert readers[domain].call_count == 1
