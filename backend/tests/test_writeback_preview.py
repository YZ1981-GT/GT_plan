"""Tests for WritebackPreview 回写预览生成（Task 15.1, advanced-query-module）

覆盖 R14.1 / R14.6：
  - 5s 内返回 WritebackPreview{items[≤10000]{addr_id, old_value, new_value}}，
    每 item 通过 AddressingService 解析 addr_id 并捕获新旧值。
  - 空预览（无 cell 将被修改）→ is_empty + 不进入确认流程 + 提示文案。
  - item 硬上限 10,000 截断。

不涉及 ACNR/DB：AddressingService 以 stub 注入，目标显式携带 old_value 以免触达 DB。
仅验证预览生成纯逻辑。
"""

import asyncio

import pytest

from app.services.custom_query.addressing_service import (
    AddressingService,
    ResolvedTarget,
)
from app.services.custom_query.writeback_preview import (
    EMPTY_PREVIEW_NOTICE,
    MAX_PREVIEW_ITEMS,
    WritebackPreview,
    WritebackPreviewError,
    WritebackPreviewItem,
    WritebackPreviewService,
    WritebackTarget,
    _values_equal,
)


# ─── stub AddressingService ─────────────────────────────────────────────────


class _StubAddressing(AddressingService):
    """以 raw → addr_id 直映射替换 resolve_target，避免触达 ACNR/DB。"""

    def __init__(self, *, missing: set[str] | None = None, delay: float = 0.0):
        self._missing = missing or set()
        self._delay = delay

    async def resolve_target(self, raw, *, project_id=None, db=None, timeout_s=5.0):
        if self._delay:
            await asyncio.sleep(self._delay)
        if raw in self._missing:
            return ResolvedTarget(raw=raw, found=False, error="unresolvable")
        return ResolvedTarget(
            raw=raw, found=True, addr_id=f"ADDR/{raw}", jump_route=f"/jump/{raw}"
        )


def _svc(**kwargs) -> WritebackPreviewService:
    return WritebackPreviewService(addressing=_StubAddressing(**kwargs))


def _target(raw: str, *, old: object, new: object) -> WritebackTarget:
    return WritebackTarget(new_value=new, raw=raw, old_value=old)


# ─── _values_equal 纯逻辑 ────────────────────────────────────────────────────


def test_values_equal_numeric_string_vs_number():
    assert _values_equal(100, "100") is True
    assert _values_equal(100.0, "100") is True
    assert _values_equal(100, 101) is False


def test_values_equal_none_and_empty_string():
    assert _values_equal(None, "") is True
    assert _values_equal(None, None) is True
    assert _values_equal("", "x") is False
    assert _values_equal(None, 0) is False


def test_values_equal_string_fallback():
    assert _values_equal("abc", "abc") is True
    assert _values_equal("abc", "abd") is False


# ─── 基本预览：解析 addr_id + 捕获新旧值 ─────────────────────────────────────


@pytest.mark.asyncio
async def test_generate_basic_items_carry_addr_old_new():
    svc = _svc()
    targets = [
        _target("D2/D2-2/E100", old=10, new=20),
        _target("D2/D2-2/E101", old="x", new="y"),
    ]
    preview = await svc.generate(None, targets, project_id="p1")

    assert isinstance(preview, WritebackPreview)
    assert preview.is_empty is False
    assert preview.enter_confirmation is True
    assert preview.item_count == 2

    it0 = preview.items[0]
    assert isinstance(it0, WritebackPreviewItem)
    assert it0.addr_id == "ADDR/D2/D2-2/E100"
    assert it0.old_value == 10
    assert it0.new_value == 20
    assert it0.found is True
    assert it0.changed is True


# ─── 空预览：无 cell 将被修改（R14.6）──────────────────────────────────────


@pytest.mark.asyncio
async def test_generate_no_targets_is_empty():
    preview = await _svc().generate(None, [], project_id="p1")
    assert preview.is_empty is True
    assert preview.enter_confirmation is False
    assert preview.notice == EMPTY_PREVIEW_NOTICE
    assert preview.item_count == 0


@pytest.mark.asyncio
async def test_generate_all_unchanged_is_empty():
    # 新旧值全相同 → 无 cell 将被修改 → 空预览、不进入确认
    svc = _svc()
    targets = [
        _target("a", old=5, new=5),
        _target("b", old="same", new="same"),
        _target("c", old=100, new="100"),  # 数值等价
    ]
    preview = await svc.generate(None, targets, project_id="p1")
    assert preview.is_empty is True
    assert preview.enter_confirmation is False
    assert preview.notice == EMPTY_PREVIEW_NOTICE


@pytest.mark.asyncio
async def test_generate_only_changed_items_included():
    svc = _svc()
    targets = [
        _target("changed", old=1, new=2),
        _target("unchanged", old=9, new=9),
    ]
    preview = await svc.generate(None, targets, project_id="p1")
    assert preview.item_count == 1
    assert preview.items[0].raw == "changed"


# ─── 解析失败的目标仍被暴露（不静默丢弃）─────────────────────────────────────


@pytest.mark.asyncio
async def test_generate_unresolved_target_surfaced():
    svc = _svc(missing={"bad"})
    targets = [_target("bad", old=1, new=2)]
    preview = await svc.generate(None, targets, project_id="p1")
    assert preview.item_count == 1
    it = preview.items[0]
    assert it.found is False
    assert it.addr_id is None
    assert it.error == "unresolvable"


@pytest.mark.asyncio
async def test_generate_unchanged_but_unresolved_still_surfaced():
    # 即便新旧值相同，解析失败也应暴露给用户（found=False）
    svc = _svc(missing={"bad"})
    targets = [_target("bad", old=7, new=7)]
    preview = await svc.generate(None, targets, project_id="p1")
    assert preview.is_empty is False
    assert preview.items[0].found is False


# ─── item 硬上限 10,000 截断（R14.1）────────────────────────────────────────


@pytest.mark.asyncio
async def test_generate_truncates_at_max_items():
    svc = _svc()
    targets = [
        WritebackTarget(new_value=i + 1, raw=f"r{i}", old_value=i)
        for i in range(MAX_PREVIEW_ITEMS + 50)
    ]
    preview = await svc.generate(None, targets, project_id="p1")
    assert preview.truncated is True
    assert preview.item_count == MAX_PREVIEW_ITEMS


@pytest.mark.asyncio
async def test_generate_no_truncation_under_limit():
    svc = _svc()
    targets = [
        WritebackTarget(new_value=i + 1, raw=f"r{i}", old_value=i)
        for i in range(10)
    ]
    preview = await svc.generate(None, targets, project_id="p1")
    assert preview.truncated is False
    assert preview.item_count == 10


# ─── 5s 时间预算：超时抛 WritebackPreviewError（R14.1）────────────────────────


@pytest.mark.asyncio
async def test_generate_timeout_raises():
    svc = _svc(delay=0.2)
    targets = [_target("slow", old=1, new=2)]
    with pytest.raises(WritebackPreviewError) as exc_info:
        await svc.generate(None, targets, project_id="p1", timeout_s=0.01)
    assert exc_info.value.error_code == "RESOLVE_UNAVAILABLE"


# ─── to_dict 序列化 ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_preview_to_dict_shape():
    svc = _svc()
    preview = await svc.generate(
        None, [_target("D2/S/E1", old=1, new=2)], project_id="p1"
    )
    d = preview.to_dict()
    assert d["is_empty"] is False
    assert d["enter_confirmation"] is True
    assert d["truncated"] is False
    assert d["item_count"] == 1
    item = d["items"][0]
    assert set(item.keys()) == {
        "addr_id",
        "old_value",
        "new_value",
        "raw",
        "found",
        "error",
        "changed",
    }
    assert item["addr_id"] == "ADDR/D2/S/E1"
    assert item["old_value"] == 1
    assert item["new_value"] == 2


@pytest.mark.asyncio
async def test_empty_preview_to_dict_notice():
    d = (await _svc().generate(None, [], project_id="p1")).to_dict()
    assert d["is_empty"] is True
    assert d["enter_confirmation"] is False
    assert d["notice"] == EMPTY_PREVIEW_NOTICE
    assert d["items"] == []


# ─── raw 兜底构造（wp_code/sheet_name/cell_ref）──────────────────────────────


@pytest.mark.asyncio
async def test_generate_builds_raw_from_wp_fields_when_missing():
    svc = _svc()
    target = WritebackTarget(
        new_value=2,
        old_value=1,
        wp_code="D2",
        sheet_name="D2-2",
        cell_ref="E100",
    )
    preview = await svc.generate(None, [target], project_id="p1")
    assert preview.items[0].raw == "D2/D2-2/E100"
    assert preview.items[0].addr_id == "ADDR/D2/D2-2/E100"
