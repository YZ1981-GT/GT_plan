"""Tests for AddressingService 语法糖归一 + 「全有或全无」归集（Task 2.2）

覆盖：
  - `_normalize_sugar` / `_classify_input`：report:/note:/adj:/tb: 语法糖在入口
    归一为 ACNR 输入形态（R1.6 单点收敛，替换 module_cell_resolver.resolve）。
  - `resolve_all` / `resolve_all_or_raise`：任一 found=False → 逐项归集无法解析
    清单、整体不执行、不返回部分结果（R1.4，TARGET_UNRESOLVABLE / RESOLVE_UNAVAILABLE）。

不涉及 ACNR/DB：resolve_target 以 stub 注入，仅验证归一与归集纯逻辑。
"""

import pytest

from app.services.custom_query.addressing_service import (
    AddressingService,
    ResolvedTarget,
    ResolveManyOutcome,
    TargetUnresolvableError,
    _classify_input,
    _normalize_sugar,
    ERR_UNRESOLVABLE,
    ERR_RESOLVE_UNAVAILABLE,
    ERR_CODE_TARGET_UNRESOLVABLE,
    ERR_CODE_RESOLVE_UNAVAILABLE,
)


# ─── 语法糖归一：report/note/tb → ACNR V1 URI ────────────────────────────────

def test_sugar_report_with_range_to_uri():
    assert _normalize_sugar("report:balance_sheet|C5:C10") == {
        "uri": "report://balance_sheet#C5:C10"
    }


def test_sugar_note_with_range_to_uri():
    assert _normalize_sugar("note:五-1-1|C3:D8") == {"uri": "note://五-1-1#C3:D8"}


def test_sugar_tb_with_range_to_uri():
    assert _normalize_sugar("tb:detail|C1:C50") == {"uri": "tb://detail#C1:C50"}


def test_sugar_without_range_to_uri():
    # 无 |cell_range 段时，仅归一 source（合法 ACNR URI）
    assert _normalize_sugar("report:balance_sheet") == {"uri": "report://balance_sheet"}
    assert _normalize_sugar("note:五、3") == {"uri": "note://五、3"}


# ─── 语法糖归一：adj → 索引 ns 引用（非 V1 URI 域）─────────────────────────────

def test_sugar_adj_to_index_ref():
    # adj 不是 ACNR V1 URI 域 → 归一为索引 ns 引用，cell_range 于寻址层丢弃
    assert _normalize_sugar("adj:aje|B2:E10") == {"index_ref": "adj:aje"}
    assert _normalize_sugar("adj:rcl") == {"index_ref": "adj:rcl"}


# ─── 边界：空 qualifier / 非语法糖 ──────────────────────────────────────────────

def test_sugar_empty_qualifier_returns_none():
    assert _normalize_sugar("report:") is None
    assert _normalize_sugar("tb:|C1:C5") is None


def test_normalize_sugar_non_sugar_returns_none():
    assert _normalize_sugar("D2/D2-2/E100") is None
    assert _normalize_sugar("WP('D2','明细表D2-2','E100')") is None


# ─── _classify_input 归一顺序：URI → 语法糖 → 公式 → 索引 ns → addr_id ─────────

def test_classify_real_uri_precedes_sugar():
    # 真实 URI（含 '://'）优先，不被 tb: 语法糖误吞
    assert _classify_input("tb://1001#审定数") == {"uri": "tb://1001#审定数"}


def test_classify_sugar_precedes_generic_index_ns():
    # note:五-1-1|... 应归一为 URI，而非通用 index_ref
    assert _classify_input("note:五-1-1|C3:D8") == {"uri": "note://五-1-1#C3:D8"}


def test_classify_formula_ref():
    assert _classify_input("WP('D2','明细表D2-2','E100')") == {
        "formula_ref": "WP('D2','明细表D2-2','E100')"
    }


def test_classify_generic_index_ns_unaffected():
    # 非语法糖前缀的索引 ns 仍走 index_ref
    assert _classify_input("cell:D2-2!E100") == {"index_ref": "cell:D2-2!E100"}


def test_classify_bare_addr_id():
    assert _classify_input("D2/D2-2/E100") == {"addr_id": "D2/D2-2/E100"}


# ─── 「全有或全无」归集：resolve_all / resolve_all_or_raise ──────────────────────

class _StubAddressingService(AddressingService):
    """以预置映射替换 resolve_target，避免触达 ACNR/DB。"""

    def __init__(self, table: dict[str, ResolvedTarget]):
        self._table = table

    async def resolve_target(self, raw, *, project_id=None, db=None, timeout_s=5.0):
        return self._table[raw]


def _found(raw: str) -> ResolvedTarget:
    return ResolvedTarget(raw=raw, found=True, addr_id=f"ADDR/{raw}")


def _missing(raw: str, error: str = ERR_UNRESOLVABLE) -> ResolvedTarget:
    return ResolvedTarget(raw=raw, found=False, error=error)


@pytest.mark.asyncio
async def test_resolve_all_success_returns_ordered():
    svc = _StubAddressingService({"a": _found("a"), "b": _found("b")})
    outcome = await svc.resolve_all(["a", "b"])
    assert isinstance(outcome, ResolveManyOutcome)
    assert outcome.ok is True
    assert outcome.error_code is None
    assert [t.raw for t in outcome.resolved] == ["a", "b"]
    assert outcome.unresolved == []


@pytest.mark.asyncio
async def test_resolve_all_any_unresolvable_all_or_nothing():
    svc = _StubAddressingService(
        {"a": _found("a"), "bad": _missing("bad"), "c": _found("c")}
    )
    outcome = await svc.resolve_all(["a", "bad", "c"])
    assert outcome.ok is False
    # 整体不执行、不返回部分结果
    assert outcome.resolved == []
    assert outcome.error_code == ERR_CODE_TARGET_UNRESOLVABLE
    # 逐项归集无法解析清单
    assert outcome.unresolved == [{"raw": "bad", "error": ERR_UNRESOLVABLE}]


@pytest.mark.asyncio
async def test_resolve_all_collects_multiple_unresolved():
    svc = _StubAddressingService(
        {"x": _missing("x"), "y": _found("y"), "z": _missing("z")}
    )
    outcome = await svc.resolve_all(["x", "y", "z"])
    assert outcome.ok is False
    assert [u["raw"] for u in outcome.unresolved] == ["x", "z"]


@pytest.mark.asyncio
async def test_resolve_all_resolve_unavailable_takes_precedence():
    # 任一 resolve 不可用/超时 → 归集码升级为 RESOLVE_UNAVAILABLE（R1.5）
    svc = _StubAddressingService(
        {
            "a": _found("a"),
            "down": _missing("down", ERR_RESOLVE_UNAVAILABLE),
            "bad": _missing("bad"),
        }
    )
    outcome = await svc.resolve_all(["a", "down", "bad"])
    assert outcome.ok is False
    assert outcome.error_code == ERR_CODE_RESOLVE_UNAVAILABLE


@pytest.mark.asyncio
async def test_resolve_all_empty_input_is_ok():
    svc = _StubAddressingService({})
    outcome = await svc.resolve_all([])
    assert outcome.ok is True
    assert outcome.resolved == []


@pytest.mark.asyncio
async def test_resolve_all_or_raise_success():
    svc = _StubAddressingService({"a": _found("a")})
    resolved = await svc.resolve_all_or_raise(["a"])
    assert [t.raw for t in resolved] == ["a"]


@pytest.mark.asyncio
async def test_resolve_all_or_raise_raises_with_unresolved():
    svc = _StubAddressingService({"a": _found("a"), "bad": _missing("bad")})
    with pytest.raises(TargetUnresolvableError) as exc_info:
        await svc.resolve_all_or_raise(["a", "bad"])
    err = exc_info.value
    assert err.error_code == ERR_CODE_TARGET_UNRESOLVABLE
    assert err.unresolved == [{"raw": "bad", "error": ERR_UNRESOLVABLE}]
