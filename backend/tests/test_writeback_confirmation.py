"""Tests for WritebackConfirmationGate 确认窗口 + 乐观锁 stale 校验门
（Task 15.2, advanced-query-module）

覆盖 R14.2 / R14.7（+ R14.6 边界）：
  - 确认有效窗口默认 600s；预览未过期且目标 cell 旧值与预览一致 → 通过。
  - 预览过期（超出确认窗口）→ WRITEBACK_CONFLICT(409)、数据不变、提示重新预览。
  - 目标 cell 当前旧值与预览时捕获旧值不一致（外部改动）→ WRITEBACK_CONFLICT、提示重新预览。
  - 空预览 / 不应进入确认 → 拒绝（reason=empty）。
  - 非 workpaper / 无定位信息目标 → 无法门内复核，延后至写回乐观锁（deferred，不误判）。

不触达真实 DB / ACNR：AddressingService 以 stub 注入；workpaper 当前旧值复核以
monkeypatch 替换 `_read_workpaper_value` 从内存表读取。仅验证确认门纯逻辑。
"""

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from app.services.custom_query.addressing_service import (
    AddressingService,
    ResolvedTarget,
)
from app.services.custom_query import writeback_preview as wb
from app.services.custom_query.writeback_preview import (
    DEFAULT_CONFIRMATION_WINDOW_S,
    ERR_CODE_WRITEBACK_CONFLICT,
    RE_PREVIEW_NOTICE,
    ConfirmationCheck,
    WritebackConfirmationConflict,
    WritebackConfirmationGate,
    WritebackPreviewService,
    WritebackTarget,
)


# ─── stubs ───────────────────────────────────────────────────────────────────


class _StubAddressing(AddressingService):
    """raw → addr_id 直映射，避免触达 ACNR/DB。"""

    def __init__(self, *, missing: set[str] | None = None):
        self._missing = missing or set()

    async def resolve_target(self, raw, *, project_id=None, db=None, timeout_s=5.0):
        if raw in self._missing:
            return ResolvedTarget(raw=raw, found=False, error="unresolvable")
        return ResolvedTarget(raw=raw, found=True, addr_id=f"ADDR/{raw}")


def _preview_service(**kwargs) -> WritebackPreviewService:
    return WritebackPreviewService(addressing=_StubAddressing(**kwargs))


def _wp_target(cell_ref: str, *, old, new, wp_id="wp1", sheet="S") -> WritebackTarget:
    """workpaper 模块目标（携带完整定位，可门内复核）。"""
    return WritebackTarget(
        new_value=new,
        old_value=old,
        module="workpaper",
        wp_id=wp_id,
        sheet_name=sheet,
        cell_ref=cell_ref,
        raw=f"{wp_id}/{sheet}/{cell_ref}",
    )


async def _make_preview(targets, *, missing=None, window_s=DEFAULT_CONFIRMATION_WINDOW_S):
    svc = _preview_service(missing=missing or set())
    return await svc.generate(None, targets, project_id="p1", confirmation_window_s=window_s)


@pytest.fixture
def current_values(monkeypatch):
    """内存表模拟 workpaper 当前旧值；键为 cell_ref。

    monkeypatch `_read_workpaper_value` 使确认门的 stale 复核从此表读取。
    """
    store: dict[str, object] = {}

    async def _fake_read(db, wp_id, sheet_name, cell_ref):
        return store.get(cell_ref)

    monkeypatch.setattr(
        WritebackPreviewService, "_read_workpaper_value", staticmethod(_fake_read)
    )
    return store


_DB = object()  # 非 None 哨兵：使确认门进入 workpaper 只读复核分支


# ─── 通过：窗口内 + 旧值一致 ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_confirm_ok_when_fresh_and_values_match(current_values):
    preview = await _make_preview(
        [_wp_target("E100", old=10, new=20), _wp_target("E101", old="x", new="y")]
    )
    # 当前旧值与预览捕获一致
    current_values["E100"] = 10
    current_values["E101"] = "x"

    check = await WritebackConfirmationGate().validate(_DB, preview)
    assert isinstance(check, ConfirmationCheck)
    assert check.ok is True
    assert check.verified_items == 2
    assert check.deferred_items == 0


@pytest.mark.asyncio
async def test_confirm_ok_numeric_equivalent_old_value(current_values):
    # 预览捕获 old=100（int），当前读回 "100"（str）→ 数值等价，不算 stale
    preview = await _make_preview([_wp_target("E1", old=100, new=200)])
    current_values["E1"] = "100"
    check = await WritebackConfirmationGate().validate(_DB, preview)
    assert check.ok is True
    assert check.verified_items == 1


# ─── 拒绝：预览过期（确认窗口）R14.2 ────────────────────────────────────────


@pytest.mark.asyncio
async def test_confirm_rejects_expired_preview(current_values):
    preview = await _make_preview([_wp_target("E100", old=10, new=20)], window_s=600)
    current_values["E100"] = 10  # 旧值一致，但预览已过期
    # 把生成时刻推到 601s 前 → 超出 600s 窗口
    preview.created_at = datetime.now(timezone.utc) - timedelta(seconds=601)

    with pytest.raises(WritebackConfirmationConflict) as exc:
        await WritebackConfirmationGate().validate(_DB, preview)
    assert exc.value.error_code == ERR_CODE_WRITEBACK_CONFLICT
    assert exc.value.reason == "expired"
    assert exc.value.message == RE_PREVIEW_NOTICE


@pytest.mark.asyncio
async def test_confirm_ok_at_window_edge_inside(current_values):
    preview = await _make_preview([_wp_target("E100", old=10, new=20)], window_s=600)
    current_values["E100"] = 10
    # 599s 前生成 → 仍在窗口内
    now = datetime.now(timezone.utc)
    preview.created_at = now - timedelta(seconds=599)
    check = await WritebackConfirmationGate().validate(_DB, preview, now=now)
    assert check.ok is True


@pytest.mark.asyncio
async def test_confirm_expired_exactly_at_boundary(current_values):
    preview = await _make_preview([_wp_target("E100", old=10, new=20)], window_s=600)
    current_values["E100"] = 10
    now = datetime.now(timezone.utc)
    # 恰好 600s → now >= expires_at → 过期
    preview.created_at = now - timedelta(seconds=600)
    with pytest.raises(WritebackConfirmationConflict) as exc:
        await WritebackConfirmationGate().validate(_DB, preview, now=now)
    assert exc.value.reason == "expired"


# ─── 拒绝：目标旧值 stale（外部改动）R14.7 ──────────────────────────────────


@pytest.mark.asyncio
async def test_confirm_rejects_stale_value(current_values):
    preview = await _make_preview([_wp_target("E100", old=10, new=20)])
    current_values["E100"] = 999  # 预览后被外部改动 → stale
    with pytest.raises(WritebackConfirmationConflict) as exc:
        await WritebackConfirmationGate().validate(_DB, preview)
    assert exc.value.error_code == ERR_CODE_WRITEBACK_CONFLICT
    assert exc.value.reason == "stale"
    assert exc.value.message == RE_PREVIEW_NOTICE
    # 触发 stale 的条目被携带（供前端高亮 / 审计）
    assert len(exc.value.stale_items) == 1
    assert exc.value.stale_items[0].raw == "wp1/S/E100"


@pytest.mark.asyncio
async def test_confirm_stale_if_any_one_cell_changed(current_values):
    preview = await _make_preview(
        [_wp_target("E1", old=1, new=2), _wp_target("E2", old=3, new=4)]
    )
    current_values["E1"] = 1  # 一致
    current_values["E2"] = 77  # 改动 → 整体拒绝
    with pytest.raises(WritebackConfirmationConflict) as exc:
        await WritebackConfirmationGate().validate(_DB, preview)
    assert exc.value.reason == "stale"
    assert {it.raw for it in exc.value.stale_items} == {"wp1/S/E2"}


# ─── 拒绝：空预览不进入确认 R14.6 ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_confirm_rejects_empty_preview():
    preview = await _make_preview([])  # 无目标 → 空预览
    assert preview.is_empty is True
    with pytest.raises(WritebackConfirmationConflict) as exc:
        await WritebackConfirmationGate().validate(_DB, preview)
    assert exc.value.reason == "empty"


@pytest.mark.asyncio
async def test_confirm_rejects_all_unchanged_preview(current_values):
    # 新旧值全相同 → 生成的是空预览（enter_confirmation=False）→ 不允许确认
    preview = await _make_preview([_wp_target("E1", old=5, new=5)])
    assert preview.enter_confirmation is False
    with pytest.raises(WritebackConfirmationConflict) as exc:
        await WritebackConfirmationGate().validate(_DB, preview)
    assert exc.value.reason == "empty"


# ─── 延后：非 workpaper / 无定位 / 解析失败 → deferred（不误判 stale）─────────


@pytest.mark.asyncio
async def test_confirm_defers_non_workpaper_module(current_values):
    # report 模块无法门内只读复核 → deferred，交由写回乐观锁
    t = WritebackTarget(
        new_value=2, old_value=1, module="report", raw="report:X/A1"
    )
    preview = await _make_preview([t])
    check = await WritebackConfirmationGate().validate(_DB, preview)
    assert check.ok is True
    assert check.deferred_items == 1
    assert check.verified_items == 0


@pytest.mark.asyncio
async def test_confirm_defers_when_db_none(current_values):
    # db 为 None → 无法复核 → deferred
    preview = await _make_preview([_wp_target("E100", old=10, new=20)])
    check = await WritebackConfirmationGate().validate(None, preview)
    assert check.ok is True
    assert check.deferred_items == 1


@pytest.mark.asyncio
async def test_confirm_defers_unresolved_target(current_values):
    # 解析失败条目非本门 stale 范畴（15.3 写回以 TARGET_UNRESOLVABLE 中止）→ deferred
    preview = await _make_preview([_wp_target("E100", old=10, new=20)], missing={"wp1/S/E100"})
    assert preview.items[0].found is False
    check = await WritebackConfirmationGate().validate(_DB, preview)
    assert check.ok is True
    assert check.deferred_items == 1


@pytest.mark.asyncio
async def test_confirm_mixed_verified_and_deferred(current_values):
    wp_t = _wp_target("E1", old=1, new=2)
    report_t = WritebackTarget(new_value=9, old_value=8, module="report", raw="report:Y/B2")
    preview = await _make_preview([wp_t, report_t])
    current_values["E1"] = 1  # workpaper 一致
    check = await WritebackConfirmationGate().validate(_DB, preview)
    assert check.ok is True
    assert check.verified_items == 1
    assert check.deferred_items == 1


# ─── 预览序列化携带确认窗口元信息 ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_preview_to_dict_carries_window_meta():
    preview = await _make_preview([_wp_target("E1", old=1, new=2)], window_s=600)
    d = preview.to_dict()
    assert d["confirmation_window_s"] == 600
    assert "created_at" in d and "expires_at" in d
    # created_at + window == expires_at
    created = datetime.fromisoformat(d["created_at"])
    expires = datetime.fromisoformat(d["expires_at"])
    assert (expires - created) == timedelta(seconds=600)
