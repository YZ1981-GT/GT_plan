"""
test_h9_h8_lease_callback.py — H-F8 H9→H8 租赁两表反向回填集成测试

验证:
1. CW-217 (H9→H8 初始计量) 存在于 cross_wp_references.json 且结构正确
2. CW-242 (H8-7→H8 后续计量) 存在于 cross_wp_references.json 且结构正确
3. event_handler 订阅 WORKPAPER_SAVED + wp_code='H9' 过滤
4. event_handler 订阅 WORKPAPER_SAVED + wp_code='H8-7' 过滤
5. H9 保存 → stale_engine 传播 + cross-ref:updated 事件发布 (target=H8)
6. H8-7 保存 → stale_engine 传播 + cross-ref:updated 事件发布 (target=H8)
7. 非 H9/H8-7 的 wp_code 不触发租赁回填 handler

Spec: workpaper-h-fixed-assets-cycle / Sprint 2 / Task 2.19
"""
from __future__ import annotations

import inspect
import json
from pathlib import Path
from uuid import uuid4

import pytest

from app.models.audit_platform_schemas import EventPayload, EventType


DATA_DIR = Path(__file__).resolve().parent.parent / "data"
CROSS_WP_REF_PATH = DATA_DIR / "cross_wp_references.json"


# ─── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def references() -> list[dict]:
    assert CROSS_WP_REF_PATH.exists(), (
        f"cross_wp_references.json not found at {CROSS_WP_REF_PATH}"
    )
    data = json.loads(CROSS_WP_REF_PATH.read_text(encoding="utf-8"))
    return data["references"]


@pytest.fixture(scope="module")
def h9_to_h8_entries(references) -> list[dict]:
    """H9 → H8 且 category=data_flow_reverse 的条目"""
    return [
        r for r in references
        if r.get("source_wp") == "H9"
        and r.get("category") == "data_flow_reverse"
        and any(
            (t.get("wp_code") or "") == "H8"
            for t in r.get("targets", [])
        )
    ]


@pytest.fixture(scope="module")
def h87_to_h8_entries(references) -> list[dict]:
    """H8-7 → H8 且 category=data_flow_reverse 的条目"""
    return [
        r for r in references
        if r.get("source_wp") == "H8"
        and "H8-7" in (r.get("source_sheet") or "")
        and r.get("category") == "data_flow_reverse"
        and any(
            (t.get("wp_code") or "") == "H8"
            for t in r.get("targets", [])
        )
    ]


# ─── Test 1: CW-217 H9→H8 反向回填条目存在且结构正确 ────────────────────────


class TestH9ToH8ReverseRefEntry:
    """验证 CW-217 H9→H8 data_flow_reverse 条目存在于 cross_wp_references.json"""

    def test_at_least_one_reverse_entry(self, h9_to_h8_entries):
        """至少存在 1 条 H9→H8 反向回填条目"""
        assert len(h9_to_h8_entries) >= 1, (
            "H-F8 反向回填条目缺失: 需 ≥1 条 H9→H8 且 category=data_flow_reverse"
        )

    def test_ref_id_cw217(self, h9_to_h8_entries):
        """ref_id 应为 CW-217"""
        ref_ids = [r.get("ref_id") for r in h9_to_h8_entries]
        assert "CW-217" in ref_ids, (
            f"CW-217 not found in H9→H8 entries, got: {ref_ids}"
        )

    def test_source_sheet_h9_1(self, h9_to_h8_entries):
        """source_sheet 应引用 H9-1 审定表"""
        assert any(
            "H9-1" in (r.get("source_sheet") or "")
            for r in h9_to_h8_entries
        ), "至少需 1 条 source_sheet 含 'H9-1'"

    def test_source_cell_lease_liability(self, h9_to_h8_entries):
        """source_cell 应为 '租赁负债期末'"""
        assert any(
            "租赁负债期末" in (r.get("source_cell") or "")
            for r in h9_to_h8_entries
        ), "source_cell 应含 '租赁负债期末'"

    def test_target_h8_initial_measurement(self, h9_to_h8_entries):
        """target 应引用 H8 使用权资产初始计量"""
        for r in h9_to_h8_entries:
            for t in r["targets"]:
                if (t.get("wp_code") or "") == "H8":
                    assert "初始计量" in (t.get("cell") or ""), (
                        f"{r['ref_id']} H8 target cell 不含 '初始计量': {t.get('cell')}"
                    )

    def test_severity_warning(self, h9_to_h8_entries):
        """severity = warning"""
        for r in h9_to_h8_entries:
            assert r.get("severity") == "warning", (
                f"{r['ref_id']} severity 应为 warning, 实际为 {r.get('severity')}"
            )

    def test_trigger_workpaper_saved_h9(self, h9_to_h8_entries):
        """trigger 字段应配置 workpaper:saved:H9"""
        for r in h9_to_h8_entries:
            trig = (r.get("trigger") or "").lower()
            assert "h9" in trig, (
                f"{r['ref_id']} trigger 字段缺失或不含 'H9': {r.get('trigger')}"
            )

    def test_formula_uses_wp_syntax(self, h9_to_h8_entries):
        """target formula 使用 =WP('H9',...) 语法"""
        for r in h9_to_h8_entries:
            for t in r["targets"]:
                if (t.get("wp_code") or "") == "H8":
                    assert t["formula"].startswith("=WP('H9'"), (
                        f"{r['ref_id']} formula 不是 =WP('H9',...): {t['formula']}"
                    )


# ─── Test 2: CW-242 H8-7→H8 反向回填条目存在且结构正确 ─────────────────────


class TestH87ToH8ReverseRefEntry:
    """验证 CW-242 H8-7→H8 data_flow_reverse 条目存在于 cross_wp_references.json"""

    def test_at_least_one_reverse_entry(self, h87_to_h8_entries):
        """至少存在 1 条 H8-7→H8 反向回填条目"""
        assert len(h87_to_h8_entries) >= 1, (
            "H-F8 反向回填条目缺失: 需 ≥1 条 H8-7→H8 且 category=data_flow_reverse"
        )

    def test_ref_id_cw242(self, h87_to_h8_entries):
        """ref_id 应为 CW-242"""
        ref_ids = [r.get("ref_id") for r in h87_to_h8_entries]
        assert "CW-242" in ref_ids, (
            f"CW-242 not found in H8-7→H8 entries, got: {ref_ids}"
        )

    def test_source_sheet_h8_7(self, h87_to_h8_entries):
        """source_sheet 应引用 H8-7 租赁变更检查表"""
        assert any(
            "H8-7" in (r.get("source_sheet") or "")
            for r in h87_to_h8_entries
        ), "至少需 1 条 source_sheet 含 'H8-7'"

    def test_target_h8_subsequent_measurement(self, h87_to_h8_entries):
        """target 应引用 H8 后续计量"""
        for r in h87_to_h8_entries:
            for t in r["targets"]:
                if (t.get("wp_code") or "") == "H8":
                    assert "后续计量" in (t.get("cell") or ""), (
                        f"{r['ref_id']} H8 target cell 不含 '后续计量': {t.get('cell')}"
                    )

    def test_trigger_workpaper_saved_h8_7(self, h87_to_h8_entries):
        """trigger 字段应配置 workpaper:saved:H8-7"""
        for r in h87_to_h8_entries:
            trig = (r.get("trigger") or "").lower()
            assert "h8-7" in trig, (
                f"{r['ref_id']} trigger 字段缺失或不含 'H8-7': {r.get('trigger')}"
            )

    def test_formula_uses_wp_syntax(self, h87_to_h8_entries):
        """target formula 使用 =WP('H8',...) 语法"""
        for r in h87_to_h8_entries:
            for t in r["targets"]:
                if (t.get("wp_code") or "") == "H8":
                    assert t["formula"].startswith("=WP('H8'"), (
                        f"{r['ref_id']} formula 不是 =WP('H8',...): {t['formula']}"
                    )


# ─── Test 3: event_handler 注册验证 ──────────────────────────────────────────


class TestHLeaseEventHandlerRegistration:
    """验证 event_handlers.py 中 H9/H8-7 租赁回填 handler 已注册"""

    def test_handler_function_exists(self):
        """_on_h_lease_reverse_backfill 函数存在"""
        from app.services import event_handlers
        src = inspect.getsource(event_handlers)
        assert "_on_h_lease_reverse_backfill" in src

    def test_handler_subscribes_workpaper_saved(self):
        """handler 订阅 WORKPAPER_SAVED 事件"""
        from app.services import event_handlers
        src = inspect.getsource(event_handlers)
        assert "event_bus.subscribe(EventType.WORKPAPER_SAVED, _on_h_lease_reverse_backfill)" in src

    def test_handler_filters_h9(self):
        """handler 过滤 wp_code='H9'"""
        from app.services import event_handlers
        src = inspect.getsource(event_handlers)
        assert '"H9"' in src or "'H9'" in src

    def test_handler_filters_h8_7(self):
        """handler 过滤 wp_code='H8-7'"""
        from app.services import event_handlers
        src = inspect.getsource(event_handlers)
        assert '"H8-7"' in src or "'H8-7'" in src

    def test_wp_code_filter_set(self):
        """_H_LEASE_REVERSE_WP_CODES 集合包含 H9 和 H8-7"""
        from app.services import event_handlers
        src = inspect.getsource(event_handlers)
        assert "_H_LEASE_REVERSE_WP_CODES" in src


# ─── Test 4: H9 保存 → stale 传播 + cross-ref:updated 事件 ──────────────────


class TestH9SaveTriggersStaleAndCrossRef:
    """端到端: H9 保存 → stale_engine 传播 + CROSS_REF_UPDATED 事件发布"""

    @pytest.mark.asyncio
    async def test_h9_save_triggers_stale_propagation(self, monkeypatch):
        """H9 保存时 stale_engine.on_change 被调用"""
        from app.services.stale_propagation_engine import stale_engine
        from app.services.event_bus import event_bus
        from app.services.event_handlers import register_event_handlers

        # 确保 handlers 已注册
        register_event_handlers()

        stale_calls: list[tuple] = []

        async def mock_on_change(uri, project_id, year):
            stale_calls.append((uri, str(project_id), year))
            return {"affected": [], "total": 0, "degraded": False}

        monkeypatch.setattr(stale_engine, "on_change", mock_on_change)

        # 模拟 publish_immediate 避免真实发布
        published: list = []

        async def mock_publish_immediate(payload):
            published.append(payload)

        monkeypatch.setattr(event_bus, "publish_immediate", mock_publish_immediate)

        # 构造 H9 保存事件并直接 dispatch（绕过 debounce）
        payload = EventPayload(
            event_type=EventType.WORKPAPER_SAVED,
            project_id=uuid4(),
            year=2025,
            extra={"wp_code": "H9", "sheet": "审定表H9-1", "wp_id": str(uuid4())},
        )

        await event_bus._dispatch(payload)

        # 验证 stale_engine.on_change 被调用（URI 含 H9 + 租赁回填）
        h9_stale_calls = [c for c in stale_calls if "H9" in c[0] and "租赁回填" in c[0]]
        assert len(h9_stale_calls) >= 1, (
            f"H9 保存未触发租赁回填 stale_engine.on_change, all calls: {stale_calls}"
        )

    @pytest.mark.asyncio
    async def test_h9_save_emits_cross_ref_updated(self, monkeypatch):
        """H9 保存时发布 CROSS_REF_UPDATED 事件 (target=H8, ref_id=CW-217)"""
        from app.services.stale_propagation_engine import stale_engine
        from app.services.event_bus import event_bus
        from app.services.event_handlers import register_event_handlers

        register_event_handlers()

        async def mock_on_change(uri, project_id, year):
            return {"affected": [], "total": 0, "degraded": False}

        monkeypatch.setattr(stale_engine, "on_change", mock_on_change)

        published: list = []

        async def mock_publish_immediate(payload):
            published.append(payload)

        monkeypatch.setattr(event_bus, "publish_immediate", mock_publish_immediate)

        pid = uuid4()
        payload = EventPayload(
            event_type=EventType.WORKPAPER_SAVED,
            project_id=pid,
            year=2025,
            extra={"wp_code": "H9", "sheet": "审定表H9-1", "wp_id": str(uuid4())},
        )

        await event_bus._dispatch(payload)

        # 验证 CROSS_REF_UPDATED 事件被发布
        cross_ref_events = [
            p for p in published
            if hasattr(p, 'event_type') and p.event_type == EventType.CROSS_REF_UPDATED
        ]
        assert len(cross_ref_events) >= 1, (
            f"H9 保存未发布 CROSS_REF_UPDATED 事件, published: {[getattr(p, 'event_type', None) for p in published]}"
        )

        evt = cross_ref_events[0]
        assert evt.extra["target_wp_code"] == "H8"
        assert evt.extra["source_wp_code"] == "H9"
        assert evt.extra["ref_id"] == "CW-217"


# ─── Test 5: H8-7 保存 → stale 传播 + cross-ref:updated 事件 ────────────────


class TestH87SaveTriggersStaleAndCrossRef:
    """端到端: H8-7 保存 → stale_engine 传播 + CROSS_REF_UPDATED 事件发布"""

    @pytest.mark.asyncio
    async def test_h87_save_triggers_stale_propagation(self, monkeypatch):
        """H8-7 保存时 stale_engine.on_change 被调用"""
        from app.services.stale_propagation_engine import stale_engine
        from app.services.event_bus import event_bus
        from app.services.event_handlers import register_event_handlers

        register_event_handlers()

        stale_calls: list[tuple] = []

        async def mock_on_change(uri, project_id, year):
            stale_calls.append((uri, str(project_id), year))
            return {"affected": [], "total": 0, "degraded": False}

        monkeypatch.setattr(stale_engine, "on_change", mock_on_change)

        published: list = []

        async def mock_publish_immediate(payload):
            published.append(payload)

        monkeypatch.setattr(event_bus, "publish_immediate", mock_publish_immediate)

        payload = EventPayload(
            event_type=EventType.WORKPAPER_SAVED,
            project_id=uuid4(),
            year=2025,
            extra={"wp_code": "H8-7", "sheet": "租赁变更检查表H8-7", "wp_id": str(uuid4())},
        )

        await event_bus._dispatch(payload)

        # 验证 stale_engine.on_change 被调用（URI 含 H8-7 + 租赁回填）
        h87_stale_calls = [c for c in stale_calls if "H8-7" in c[0] and "租赁回填" in c[0]]
        assert len(h87_stale_calls) >= 1, (
            f"H8-7 保存未触发租赁回填 stale_engine.on_change, all calls: {stale_calls}"
        )

    @pytest.mark.asyncio
    async def test_h87_save_emits_cross_ref_updated(self, monkeypatch):
        """H8-7 保存时发布 CROSS_REF_UPDATED 事件 (target=H8, ref_id=CW-242)"""
        from app.services.stale_propagation_engine import stale_engine
        from app.services.event_bus import event_bus
        from app.services.event_handlers import register_event_handlers

        register_event_handlers()

        async def mock_on_change(uri, project_id, year):
            return {"affected": [], "total": 0, "degraded": False}

        monkeypatch.setattr(stale_engine, "on_change", mock_on_change)

        published: list = []

        async def mock_publish_immediate(payload):
            published.append(payload)

        monkeypatch.setattr(event_bus, "publish_immediate", mock_publish_immediate)

        pid = uuid4()
        payload = EventPayload(
            event_type=EventType.WORKPAPER_SAVED,
            project_id=pid,
            year=2025,
            extra={"wp_code": "H8-7", "sheet": "租赁变更检查表H8-7", "wp_id": str(uuid4())},
        )

        await event_bus._dispatch(payload)

        # 验证 CROSS_REF_UPDATED 事件被发布
        cross_ref_events = [
            p for p in published
            if hasattr(p, 'event_type') and p.event_type == EventType.CROSS_REF_UPDATED
        ]
        assert len(cross_ref_events) >= 1, (
            f"H8-7 保存未发布 CROSS_REF_UPDATED 事件, published: {[getattr(p, 'event_type', None) for p in published]}"
        )

        evt = cross_ref_events[0]
        assert evt.extra["target_wp_code"] == "H8"
        assert evt.extra["source_wp_code"] == "H8-7"
        assert evt.extra["ref_id"] == "CW-242"


# ─── Test 6: 非 H9/H8-7 的 wp_code 不触发租赁回填 ───────────────────────────


class TestNonLeaseWpCodeSkipped:
    """验证非 H9/H8-7 的 wp_code 不触发租赁回填 handler"""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("wp_code", ["H1", "H2", "H8", "D2", "F2", "H10"])
    async def test_non_lease_wp_code_no_cross_ref_event(self, monkeypatch, wp_code):
        """非 H9/H8-7 的 wp_code 不发布 CROSS_REF_UPDATED 事件"""
        from app.services.stale_propagation_engine import stale_engine
        from app.services.event_bus import event_bus
        from app.services.event_handlers import register_event_handlers

        register_event_handlers()

        stale_calls: list[tuple] = []

        async def mock_on_change(uri, project_id, year):
            stale_calls.append((uri, str(project_id), year))
            return {"affected": [], "total": 0, "degraded": False}

        monkeypatch.setattr(stale_engine, "on_change", mock_on_change)

        published: list = []

        async def mock_publish_immediate(payload):
            published.append(payload)

        monkeypatch.setattr(event_bus, "publish_immediate", mock_publish_immediate)

        payload = EventPayload(
            event_type=EventType.WORKPAPER_SAVED,
            project_id=uuid4(),
            year=2025,
            extra={"wp_code": wp_code, "sheet": f"审定表{wp_code}-1", "wp_id": str(uuid4())},
        )

        await event_bus._dispatch(payload)

        # 验证没有 CROSS_REF_UPDATED 事件（来自租赁回填 handler）
        cross_ref_events = [
            p for p in published
            if hasattr(p, 'event_type') and p.event_type == EventType.CROSS_REF_UPDATED
        ]
        assert len(cross_ref_events) == 0, (
            f"wp_code={wp_code} 不应触发 CROSS_REF_UPDATED, got: {cross_ref_events}"
        )


# ─── Test 7: 缺少 project_id 或 year 时 handler 跳过 ────────────────────────


class TestMissingFieldsSkipped:
    """验证缺少 project_id 或 year 时 handler 安全跳过"""

    @pytest.mark.asyncio
    async def test_missing_year_skips(self, monkeypatch):
        """year=None 时 handler 不触发 stale 传播"""
        from app.services.stale_propagation_engine import stale_engine
        from app.services.event_bus import event_bus
        from app.services.event_handlers import register_event_handlers

        register_event_handlers()

        stale_calls: list[tuple] = []

        async def mock_on_change(uri, project_id, year):
            stale_calls.append((uri, str(project_id), year))
            return {"affected": [], "total": 0, "degraded": False}

        monkeypatch.setattr(stale_engine, "on_change", mock_on_change)

        published: list = []

        async def mock_publish_immediate(payload):
            published.append(payload)

        monkeypatch.setattr(event_bus, "publish_immediate", mock_publish_immediate)

        payload = EventPayload(
            event_type=EventType.WORKPAPER_SAVED,
            project_id=uuid4(),
            year=None,
            extra={"wp_code": "H9", "sheet": "审定表H9-1", "wp_id": str(uuid4())},
        )

        await event_bus._dispatch(payload)

        # 租赁回填 handler 应跳过（year=None）
        h9_lease_stale = [c for c in stale_calls if "租赁回填" in c[0]]
        assert len(h9_lease_stale) == 0, (
            f"year=None 时不应触发租赁回填 stale, got: {h9_lease_stale}"
        )

    @pytest.mark.asyncio
    async def test_missing_extra_skips(self, monkeypatch):
        """extra={} (无 wp_code) 时 handler 不触发"""
        from app.services.stale_propagation_engine import stale_engine
        from app.services.event_bus import event_bus
        from app.services.event_handlers import register_event_handlers

        register_event_handlers()

        stale_calls: list[tuple] = []

        async def mock_on_change(uri, project_id, year):
            stale_calls.append((uri, str(project_id), year))
            return {"affected": [], "total": 0, "degraded": False}

        monkeypatch.setattr(stale_engine, "on_change", mock_on_change)

        published: list = []

        async def mock_publish_immediate(payload):
            published.append(payload)

        monkeypatch.setattr(event_bus, "publish_immediate", mock_publish_immediate)

        payload = EventPayload(
            event_type=EventType.WORKPAPER_SAVED,
            project_id=uuid4(),
            year=2025,
            extra={},
        )

        await event_bus._dispatch(payload)

        # 租赁回填 handler 应跳过（extra 无 wp_code）
        h_lease_stale = [c for c in stale_calls if "租赁回填" in c[0]]
        assert len(h_lease_stale) == 0


# ─── Test 8: CROSS_REF_UPDATED 事件类型存在 ──────────────────────────────────


class TestCrossRefUpdatedEventType:
    """验证 EventType.CROSS_REF_UPDATED 枚举成员存在"""

    def test_enum_member_exists(self):
        assert hasattr(EventType, "CROSS_REF_UPDATED")

    def test_enum_value(self):
        assert EventType.CROSS_REF_UPDATED.value == "cross_ref.updated"
